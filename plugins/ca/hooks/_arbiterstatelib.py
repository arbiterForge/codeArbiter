#!/usr/bin/env python3
# codeArbiter — statusline arbiter-state parsing (extracted from statusline.py,
# architecture-004).
#
# Owns reading the .codearbiter/ project-state directory into the compact dict the
# arbiter segment renders: frontmatter parsing, override/question counting, the
# mtime-keyed cache (a StopHook-driven statusline re-renders on every tool-call
# completion, so re-parsing 5 small files on every render would be wasteful), and
# the dev-mode marker check.
#
# The task-in-flight count and the arbiter-enabled gate are OWNED elsewhere
# (_taskboardlib.count_in_flight / _hooklib.frontmatter_enabled) so the box and the
# enforcement hooks agree on both contracts. This module never imports them
# directly — the caller (statusline.py) passes its own guarded-imported references
# through, so a test that monkeypatches statusline's fallback (e.g.
# `mod._count_in_flight = None`) is observed correctly on the next call.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed user input — degrade to a safe default.
#
# Public API:
#   frontmatter(path) -> dict                      parsed leading YAML frontmatter block
#   count_matches(path, pattern) -> int             regex match count in a file (0 on any I/O error)
#   arbiter_state(root, count_in_flight=None, read_board=None, frontmatter_enabled=None) -> dict|None
#   dev_active(root) -> bool                        True when the /dev marker is present

import os
import re

# mtime-keyed memo: statusline.py is a short-lived subprocess, but a single render
# can resolve arbiter_state more than once (safe() probes), and the StopHook fires
# the whole script on every tool-call completion. Caching on max(input mtime) makes
# the 5 .codearbiter/ reads happen at most once per (root, change), re-reading only
# when one of the inputs actually changes between renders.
_ARBITER_CACHE = {}        # root -> (mtime_key, result)
_ARBITER_FILES = ("CONTEXT.md", "overrides.log", "last-checkpoint",
                  "open-tasks.md", "open-questions.md", "sprint-active")


def frontmatter(path):
    """Parse a properly-closed leading YAML frontmatter block into a key map. The
    *arbiter-enabled* decision is NOT made here — that activation contract is owned
    by _hooklib.frontmatter_enabled (see arbiter_state) so the box and the
    enforcement hooks read it one way. This reader exists only to surface the
    remaining display keys (e.g. `stage`) the boolean gate doesn't carry."""
    fm = {}
    try:
        # utf-8-sig transparently strips a leading BOM (Windows editors / PowerShell
        # Out-File default to UTF-8-with-BOM); plain utf-8 would leave it on line 1
        # and break the "---" frontmatter check.
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return fm
    if not lines or lines[0].strip() != "---":
        return fm
    closed = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    # A valid YAML frontmatter block is bounded by BOTH delimiters; an unterminated
    # block (no closing "---") is malformed — don't honor keys parsed to EOF.
    return fm if closed else {}


def count_matches(path, pattern):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return len(re.findall(pattern, f.read(), re.MULTILINE))
    except OSError:
        return 0


def _arbiter_mtime_key(cad):
    """Max mtime across the arbiter input files (missing files stat as -1.0). Two
    renders with the same key saw identical inputs, so the cached state is valid."""
    latest = -1.0
    for nm in _ARBITER_FILES:
        try:
            latest = max(latest, os.stat(os.path.join(cad, nm)).st_mtime)
        except OSError:
            pass
    return latest


def _arbiter_enabled(ctx_path, frontmatter_enabled=None):
    """The arbiter-enabled gate, owned by _hooklib.frontmatter_enabled when the lib
    is importable (so the box and the enforcement hooks agree on the activation
    contract). Falls back to the local frontmatter() parser only if the import
    failed — the defensive degrade path, never a hard dependency."""
    if frontmatter_enabled is not None:
        try:
            enabled, _malformed = frontmatter_enabled(ctx_path)
            return enabled
        except Exception:  # noqa: BLE001 — degrade to the local parser, never crash
            pass
    return frontmatter(ctx_path).get("arbiter", "").lower() == "enabled"


def arbiter_state(root, count_in_flight=None, read_board=None, frontmatter_enabled=None):
    cad = os.path.join(root, ".codearbiter")
    mkey = _arbiter_mtime_key(cad)
    cached = _ARBITER_CACHE.get(root)
    if cached is not None and cached[0] == mkey:
        return cached[1]
    result = _arbiter_state_uncached(cad, count_in_flight, read_board, frontmatter_enabled)
    _ARBITER_CACHE[root] = (mkey, result)
    return result


def _arbiter_state_uncached(cad, count_in_flight=None, read_board=None, frontmatter_enabled=None):
    if not _arbiter_enabled(os.path.join(cad, "CONTEXT.md"), frontmatter_enabled):
        return None
    fm = frontmatter(os.path.join(cad, "CONTEXT.md"))
    total_over = count_matches(os.path.join(cad, "overrides.log"), r"^(?!\s*#)(?!\s*$).+")
    # last-checkpoint holds the override COUNT at the last /ca:checkpoint. A value
    # outside [0, total] is not a valid count (e.g. a timestamp from a stale writer)
    # -> fail safe to 0 so overrides are surfaced, never silently hidden.
    try:
        with open(os.path.join(cad, "last-checkpoint"), encoding="utf-8") as f:
            base = int(f.read().strip() or "0")
    except (OSError, ValueError):
        base = 0
    if base < 0 or base > total_over:
        base = 0
    ot_path = os.path.join(cad, "open-tasks.md")
    if count_in_flight is not None:
        tasks = count_in_flight(read_board(ot_path) or "")
    else:
        # Degraded fallback (only if _taskboardlib failed to import): mirror
        # count_in_flight's done-exclusion inline so the segment never silently
        # re-inflates to the pre-schema count. Never crashes the box.
        tasks = count_matches(ot_path, r"^- (?!\[[xX]\])")
    return {
        "stage": fm.get("stage", "-"),
        "tasks": tasks,
        "q": count_matches(os.path.join(cad, "open-questions.md"), r"CONFIRM-[0-9]+"),
        "over": max(0, total_over - base),
        "sprint": os.path.exists(os.path.join(cad, "sprint-active")),
    }


def dev_active(root):
    """True when /dev developer-override mode is on — signalled by a transient marker
    the orchestrator drops on /dev and clears on /arbiter (a local UI flag, not a log)."""
    return os.path.exists(os.path.join(root, ".codearbiter", ".markers", "dev-active"))
