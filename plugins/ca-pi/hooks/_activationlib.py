#!/usr/bin/env python3
# codeArbiter - ACTIVATION: which Host this process is running under, where the
# project root is, and whether the arbiter is switched on for it.
#
# Extracted from _hooklib (issue #321, architecture-002) as slice 4, the last and
# the one with real teeth. Measured like the others: this cluster references
# NOTHING from the rest of _hooklib. The edge runs the other way for the first
# time - _log_gate_event (which stays behind) calls get_host() and
# project_root() - so _hooklib imports from here and never the reverse. Still
# one-way, still no cycle.
#
# WHY THESE BELONG TOGETHER: they are the three answers every hook needs before
# it can decide anything, and they share two process-lifetime caches. `_HOST` and
# `_ROOT_CACHE` exist because a hook is a single-shot process whose host identity
# and project root cannot change mid-run; arbiter_active reads the root to find
# CONTEXT.md, and project_root reads the host. Splitting them would put a cache
# in one module and its only writer in another.
#
# ON THE MUTABLE GLOBALS, because this is the trap in this slice:
# `_HOST` is deliberately NOT re-exported by _hooklib. `from _activationlib
# import _HOST` binds the VALUE at import time, so a later set_host() would
# rebind the name HERE and leave _hooklib holding a stale None forever - the
# exact silent-divergence bug the partition exists to prevent. The three
# accessors ARE re-exported, and they all read and write this module's global,
# so every caller sees one cache no matter which module it imported them from.
# That is the opposite of slice 3's lesson (re-export the privates) and for a
# precise reason: a FUNCTION binding stays live, a VALUE binding does not.
# Verified: nothing in the repo reads _hooklib._HOST directly.

from __future__ import annotations

import os
import re

import hostapi


# The loaded Host is process-cached: hooks are single-shot processes, and the
# host's identity cannot change mid-process (its methods read env/payload state
# live at call time, so caching the OBJECT changes no verdict).
_HOST = None

def get_host():
    """The process's Host instance (hostapi.load_host(), cached)."""
    global _HOST
    if _HOST is None:
        _HOST = hostapi.load_host()
    return _HOST


def set_host(host):
    """Dependency-injection seam (#257 architecture-001/performance-002).

    Primes the module-cached `_HOST` that `get_host()` reads. Every entry
    script's `run(host, argv=None)` calls this BEFORE `main()`, so the Host
    instance the `__main__` guard already resolved via `hostapi.load_host()`
    is the SAME object `get_host()` serves inside `main()` — closing two
    defects at once: (1) `main()` no longer triggers its own redundant
    `hostapi.load_host()` (a second `_host.py` load per invocation), and
    (2) `run(host)` stops silently ignoring its `host` argument — a test that
    calls `run(fake_host)` now genuinely exercises `fake_host`, not whatever
    `load_host()` resolves from disk. In production the injected host IS the
    `load_host()` result the guard already computed, so this changes no
    behavior — it only removes the redundant second load and makes the
    existing `run(host)` parameter live."""
    global _HOST
    _HOST = host


def reset_host():
    """Test-only: clear the injected/cached `_HOST` so the next `get_host()`
    lazy-loads afresh. Production hook processes are single-shot and never need
    this; but `set_host()` makes `_HOST` a process-lifetime singleton, so a test
    that calls `run(fake_host)` must reset it in tearDown — otherwise the fake
    leaks into any later in-process test that calls `get_host()` without its own
    patch, silently running against the wrong host and masking a gate
    regression (security review #257, LOW)."""
    global _HOST
    _HOST = None

# project_root() memoization (performance-001/003, #260). A hook is a
# single-shot process, so CLAUDE_PROJECT_DIR and the process cwd cannot
# change mid-process — but the resolved VALUE is cached keyed on those two
# inputs (not unconditionally) rather than as one bare value, so an env/cwd
# change is a cache MISS, never a stale hit. This keeps the production
# single-shot contract (the same hook process always sees an unchanging
# env/cwd, so it resolves at most once) while staying correct for the
# in-process integration-test harnesses that legitimately re-target
# project_root() across many fixtures/envs within one Python process
# (`python -m unittest discover` runs the whole suite in ONE interpreter —
# an unconditional single-value cache would leak the FIRST test's resolved
# root into every later test that calls project_root() or warn()/block()/
# remind() in-process). A payload's `cwd` is deliberately NOT part of the
# cache key: within one real hook process the payload is parsed at most once
# and never changes, so a payload-bearing call and a later no-payload call in
# the SAME (env, cwd) context are the SAME logical resolution and must return
# the SAME value — exactly the "payload-bearing first call, later no-arg
# calls stay consistent" contract. (A payload-only scenario — Codex, no
# CLAUDE_PROJECT_DIR — still resolves once: the first call's payload wins and
# is cached against the current (env, cwd); env/cwd don't change either.)
_ROOT_CACHE = {}


def _root_cache_key():
    return (os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd())


def _reset_root_cache():
    """Test-only: drop every memoized project_root() resolution. Production
    hook processes never need this (each is single-shot); integration tests
    that simulate MANY logical hook invocations in one Python process and
    need a resolution to be genuinely re-computed (rather than served from an
    still-valid (env, cwd) cache entry) call this between scenarios."""
    _ROOT_CACHE.clear()


def marker_root(payload=None):
    """The root `.codearbiter/.markers/` gate passes (security-pass.py,
    migration-pass.py, and the H-09b/H-10b/H-14 guards) are written to and
    read from (#604) — see `hostapi.Host.marker_root`'s docstring for why
    this is NOT the same thing as `project_root()` in a linked worktree.

    Not memoized like `project_root()` above: called at most once or twice
    per hook process (the marker checks, or a single `security-pass.py` /
    `migration-pass.py` run), so the extra git spawn a linked-worktree
    escalation occasionally costs is not worth a second cache to avoid."""
    return get_host().marker_root(payload)

ARBITER_RE = re.compile(r"^\s*arbiter:\s*enabled\s*$", re.I)
_BODY_MARKER_RE = re.compile(r"^\s*<!--\s*INITIALIZED\s*-->\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(?:[^`~].*)?$")

def context_state_text(text):
    """Return (enabled, malformed, initialized) from one CONTEXT.md parse."""
    lines = (text or "").splitlines()
    if not lines:
        return (False, False, False)
    first = lines[0].lstrip("﻿")  # tolerate a leading UTF-8 BOM
    if first.strip() != "---":
        return (False, False, False)
    enabled = False
    body_start = None
    for index, ln in enumerate(lines[1:], 1):
        if ln.strip() == "---":
            body_start = index + 1
            break
        if ARBITER_RE.match(ln):
            enabled = True
    if body_start is None:
        return (False, True, False)
    if not enabled:
        return (False, False, False)

    fence_char = ""
    fence_length = 0
    in_comment = False
    for ln in lines[body_start:]:
        stripped = ln.strip()
        if fence_char:
            if re.fullmatch(r" {0,3}" + re.escape(fence_char) +
                            "{" + str(fence_length) + r",}\s*", ln):
                fence_char = ""
            continue
        if in_comment:
            if "-->" in ln:
                in_comment = False
            continue
        fence = _FENCE_RE.match(ln)
        if fence:
            fence_char, fence_length = fence.group(1)[0], len(fence.group(1))
            continue
        if _BODY_MARKER_RE.fullmatch(ln):
            return (True, False, True)
        if "<!--" in stripped and "-->" not in stripped:
            in_comment = True
    return (True, False, False)


def frontmatter_enabled_text(text):
    """(enabled, malformed) for CONTEXT.md content; shared with body parsing."""
    enabled, malformed, _initialized = context_state_text(text)
    return (enabled, malformed)


def initialized_body_text(text):
    """True only for a standalone marker in an enabled CONTEXT.md body."""
    return context_state_text(text)[2]


def passive_activation_inventory(root):
    """Read only the explicit root's activation marker; execute no project tools.

    This is a pre-session inspection result, not proof of repository identity,
    host capability, network policy, or permission to activate. The caller must
    inventory sensitive paths before sending any source to a model.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root) or os.path.islink(root):
        raise ValueError("passive inspection requires an existing, non-link directory")
    state_dir = os.path.join(root, ".codearbiter")
    ctx = os.path.join(state_dir, "CONTEXT.md")
    if os.path.islink(state_dir) or os.path.islink(ctx):
        raise ValueError("passive inspection refuses linked context paths")
    if os.path.lexists(state_dir) and not os.path.isdir(state_dir):
        raise ValueError(".codearbiter is not a directory")
    if os.path.lexists(ctx) and not os.path.isfile(ctx):
        raise ValueError("CONTEXT.md is not a regular file")
    exists = os.path.isfile(ctx)
    enabled = malformed = initialized = False
    if exists:
        if os.path.getsize(ctx) > 1024 * 1024:
            raise ValueError("CONTEXT.md exceeds passive inspection read limit")
        with open(ctx, encoding="utf-8") as stream:
            enabled, malformed, initialized = context_state_text(stream.read(1024 * 1024 + 1))
    effect = {"capability": "unverified", "authorization": "not_established",
              "performed": False}
    activation_behaviors = {
        "git_hooks_exclusions": "scaffold may write Git-local exclusions and hooks; active startup may refresh hooks",
        "git_fetch": "active startup may spawn detached Git fetch",
        "update_refresh": "active startup may spawn detached update refresh",
        "inference_transport": "host-selected model may receive approved source after authorization",
    }
    return {
        "profile": "passive-before-activation",
        "root": root,
        "root_identity": "caller_supplied_unverified",
        "context": {"exists": exists, "enabled": enabled,
                    "initialized": initialized, "malformed": malformed},
        "effects": {name: {**effect, "activation_behavior": behavior}
                    for name, behavior in activation_behaviors.items()},
        "source_reads": "none",
        "sensitive_path_inventory": "pending",
    }


def frontmatter_enabled(ctx_path):
    """Return (enabled, malformed) for CONTEXT.md ON DISK. `enabled` iff
    `arbiter: enabled` appears in a properly-closed leading YAML frontmatter
    block. `malformed` iff a block opens (`---` on line 1) but never closes — the
    fail-loud case. A file with no frontmatter at all is simply dormant (not
    malformed). Unreadable file -> (False, False)."""
    try:
        with open(ctx_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        return (False, False)
    return frontmatter_enabled_text(text)


def arbiter_active(root):
    """True iff this repo opted in (`arbiter: enabled` in CONTEXT.md frontmatter).
    Every enforcement hook gates on this so the plugin is genuinely dormant in
    repos that never opted in — the plugin.json activation contract."""
    enabled, _ = frontmatter_enabled(os.path.join(root, ".codearbiter", "CONTEXT.md"))
    return enabled

def project_root(payload=None):
    """The project root. `CLAUDE_PROJECT_DIR` is the harness's own authoritative
    signal and is trusted first: a hook subprocess is not guaranteed to start
    with the project directory as its cwd, and a `git rev-parse` from elsewhere
    can resolve to a different repo entirely (e.g. the plugin's own marketplace
    clone). The env-first read also saves one git spawn per hook invocation.
    Test harnesses that spawn hooks into fixture repos must pin the variable to
    the fixture, as the production harness pins it to the project.

    The resolution itself lives on the Host seam (hostapi.Host.project_root,
    ADR-0011) — this function keeps its public signature (now accepting an
    optional `payload`, architecture-006/#260, so a caller that already has
    the parsed hook payload can hand it through to the payload-cwd leg) and
    delegates, so every existing no-arg caller/import keeps working unchanged.

    Memoized per (CLAUDE_PROJECT_DIR, process cwd) — see _ROOT_CACHE above for
    the full contract (performance-001/003, #260): at most one resolution
    (and at most one git spawn) per that key, so the repeated project_root()
    reads inside block()/remind()/warn()'s gate-event logging don't each pay
    a fresh subprocess."""
    key = _root_cache_key()
    if key not in _ROOT_CACHE:
        _ROOT_CACHE[key] = get_host().project_root(payload)
    return _ROOT_CACHE[key]
