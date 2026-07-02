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
#   frontmatter(path) -> dict                       parsed leading YAML frontmatter block
#   frontmatter_text(text) -> dict                   same parse, given already-read text (performance-003)
#   count_matches(path, pattern) -> int              regex match count in a file (0 on any I/O error)
#   count_matches_text(text, pattern) -> int          same count, given already-read text (performance-003)
#   arbiter_state(root, count_in_flight=None, read_board=None, frontmatter_enabled=None,
#                 ctx_text=None, ot_text=None, oq_text=None) -> dict|None
#   dev_active(root) -> bool                        True when the /dev marker is present
#
# performance-003 (#194): SessionStart's main() already reads CONTEXT.md,
# open-tasks.md, and open-questions.md before the display-only governance line
# is ever rendered. The optional ctx_text/ot_text/oq_text kwargs on
# arbiter_state let a caller that already holds that content thread it through
# instead of paying for a second disk read of the same file in the same
# process. None (the default) means "not supplied" -> falls back to the
# original read-from-disk behavior, so every existing caller (the standalone
# statusline.py render, direct arbiter_state(root) calls in tests) is
# unaffected.

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


def frontmatter_text(text):
    """Parse a properly-closed leading YAML frontmatter block out of already-read
    `text` into a key map (see frontmatter() for the on-disk counterpart — this is
    the pure text half, extracted for performance-003 so a caller holding the
    content already can skip a second disk read). Tolerates a leading UTF-8 BOM
    character (\\ufeff) on the first line the same way frontmatter()'s utf-8-sig
    decode does, regardless of how the caller's text was originally decoded."""
    fm = {}
    lines = (text or "").splitlines()
    if not lines:
        return fm
    first = lines[0].lstrip("﻿")
    if first.strip() != "---":
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


def frontmatter(path):
    """Parse a properly-closed leading YAML frontmatter block into a key map. The
    *arbiter-enabled* decision is NOT made here — that activation contract is owned
    by _hooklib.frontmatter_enabled (see arbiter_state) so the box and the
    enforcement hooks read it one way. This reader exists only to surface the
    remaining display keys (e.g. `stage`) the boolean gate doesn't carry."""
    try:
        # utf-8-sig transparently strips a leading BOM (Windows editors / PowerShell
        # Out-File default to UTF-8-with-BOM); plain utf-8 would leave it on line 1
        # and break the "---" frontmatter check.
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}
    return frontmatter_text(text)


def count_matches_text(text, pattern):
    """Regex match count against already-read `text` (see count_matches() for the
    on-disk counterpart — the pure text half, extracted for performance-003)."""
    return len(re.findall(pattern, text or "", re.MULTILINE))


def count_matches(path, pattern):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return 0
    return count_matches_text(text, pattern)


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


def _arbiter_enabled(ctx_path, frontmatter_enabled=None, ctx_text=None):
    """The arbiter-enabled gate, owned by _hooklib.frontmatter_enabled when the lib
    is importable (so the box and the enforcement hooks agree on the activation
    contract). Falls back to the local frontmatter() parser only if the import
    failed — the defensive degrade path, never a hard dependency.

    When `ctx_text` is supplied (performance-003: the caller already read
    CONTEXT.md), the decision is made from that text — no re-read of ctx_path."""
    if ctx_text is not None:
        return frontmatter_text(ctx_text).get("arbiter", "").lower() == "enabled"
    if frontmatter_enabled is not None:
        try:
            enabled, _malformed = frontmatter_enabled(ctx_path)
            return enabled
        except Exception:  # noqa: BLE001 — degrade to the local parser, never crash
            pass
    return frontmatter(ctx_path).get("arbiter", "").lower() == "enabled"


def arbiter_state(root, count_in_flight=None, read_board=None, frontmatter_enabled=None,
                   ctx_text=None, ot_text=None, oq_text=None):
    cad = os.path.join(root, ".codearbiter")
    mkey = _arbiter_mtime_key(cad)
    cached = _ARBITER_CACHE.get(root)
    if cached is not None and cached[0] == mkey:
        return cached[1]
    result = _arbiter_state_uncached(cad, count_in_flight, read_board, frontmatter_enabled,
                                      ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)
    _ARBITER_CACHE[root] = (mkey, result)
    return result


def _arbiter_state_uncached(cad, count_in_flight=None, read_board=None, frontmatter_enabled=None,
                             ctx_text=None, ot_text=None, oq_text=None):
    ctx_path = os.path.join(cad, "CONTEXT.md")
    if not _arbiter_enabled(ctx_path, frontmatter_enabled, ctx_text=ctx_text):
        return None
    # performance-003: reuse the caller's already-read CONTEXT.md/open-tasks.md/
    # open-questions.md text when supplied, instead of a second disk read. `None`
    # (the default) preserves the exact original read-from-disk behavior.
    fm = frontmatter_text(ctx_text) if ctx_text is not None else frontmatter(ctx_path)
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
        board_text = ot_text if ot_text is not None else (read_board(ot_path) or "")
        tasks = count_in_flight(board_text)
    else:
        # Degraded fallback (only if _taskboardlib failed to import): mirror
        # count_in_flight's done-exclusion inline so the segment never silently
        # re-inflates to the pre-schema count. Never crashes the box.
        tasks = (count_matches_text(ot_text, r"^- (?!\[[xX]\])") if ot_text is not None
                 else count_matches(ot_path, r"^- (?!\[[xX]\])"))
    q = (count_matches_text(oq_text, r"CONFIRM-[0-9]+") if oq_text is not None
         else count_matches(os.path.join(cad, "open-questions.md"), r"CONFIRM-[0-9]+"))
    return {
        "stage": fm.get("stage", "-"),
        "tasks": tasks,
        "q": q,
        "over": max(0, total_over - base),
        "sprint": os.path.exists(os.path.join(cad, "sprint-active")),
    }


def dev_active(root):
    """True when /dev developer-override mode is on — signalled by a transient marker
    the orchestrator drops on /dev and clears on /arbiter (a local UI flag, not a log)."""
    return os.path.exists(os.path.join(root, ".codearbiter", ".markers", "dev-active"))
