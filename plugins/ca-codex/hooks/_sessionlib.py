#!/usr/bin/env python3
# codeArbiter — statusline true-session-start resolver (extracted from
# statusline.py, architecture-004).
#
# Owns resolving the wall-clock session start from Claude Code's own session
# metadata (~/.claude/sessions/<pid>.json, matched on sessionId) — the same start
# time /usage reports, including idle/suspend gaps the current transcript alone
# can't show. The result is cached into the caller's ledger record so the O(N)
# directory scan runs at most once per session.
#
# Design principles (mirroring _ledgerlib.py):
#   - Stdlib only; no third-party imports ever.
#   - Zero side effects at import time.
#   - Never raise on malformed input — degrade to None.
#
# Public API:
#   session_start(sid, rec=None) -> float|None

import json
import os


def num(x, default=0.0):
    """Coerce any host value to float; tolerate strings, None, and containers."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _session_start_scan(sid):
    """The O(N) fallback: scan ~/.claude/sessions/*.json for the one whose
    sessionId matches `sid` and read its startedAt. The metadata file is named by
    the host PID, not the sessionId, so a direct name lookup isn't possible from
    here — a match-on-content scan is the only correct resolver. The caller caches
    the result in the ledger so this scan runs at most once per session."""
    d = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for nm in names:
        if not nm.endswith(".json"):
            continue
        fp = os.path.join(d, nm)
        try:
            if os.path.getsize(fp) > 65536:   # metadata is <1KB; never read a large file
                continue
            with open(fp, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and meta.get("sessionId") == sid:
            sa = num(meta.get("startedAt"), None)
            if sa:
                return sa / 1000.0 if sa > 1e12 else sa   # ms epoch -> seconds
    return None


def session_start(sid, rec=None):
    """True session start (epoch seconds) from Claude Code's own session metadata
    (~/.claude/sessions/<pid>.json, matched on sessionId). This is the wall-clock
    start /usage reports, INCLUDING idle/suspend gaps the current transcript can't
    show. None if unavailable -> caller falls back to the transcript.

    Fast path: the resolved value is cached in the ledger record (`rec["sess_start"]`),
    which ledger_update persists, so subsequent renders skip the per-render directory
    scan entirely. On a cache miss the full scan runs once and seeds the cache."""
    if not sid:
        return None
    if isinstance(rec, dict):
        cached = num(rec.get("sess_start"), None)
        if cached:
            return cached
    sa = _session_start_scan(sid)
    if sa and isinstance(rec, dict):
        rec["sess_start"] = sa   # seed the ledger cache; ledger_update persists it
    return sa
