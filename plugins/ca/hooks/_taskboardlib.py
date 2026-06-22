#!/usr/bin/env python3
# codeArbiter — task-board lifecycle helper for `.codearbiter/open-tasks.md`.
#
# Gives the backlog a parseable, crash-safe lifecycle (queued -> in-progress ->
# done) and a content-bearing ID, and supplies the SHARED count/staleness logic
# that both readers — session-start.py and statusline.py — route through, so the
# "in-flight tasks" number is computed in exactly one place.
#
# Design principles (mirroring _metricslib.py / _previewlib.py):
#   - Stdlib only; no third-party imports ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O.
#   - Pure functions are fully testable with synthetic board text (no real file
#     needed). read_board() is the ONLY function that touches the filesystem.
#
# Schema (one task = a top-level lifecycle line + indented content sub-bullets):
#
#   - [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)
#     - Desc: reject expired/forged tokens at the auth middleware
#     - Done when: an expired token returns 401; a valid one passes
#     - Boundaries: auth, secrets
#
#   marker  [ ] queued | [~] in-progress | [x] done
#   ID      <group>.<type>.<seq4>  (group = build phase, type = domain, seq >=4 digits)
#   dates   (started YYYY-MM-DD) / (done YYYY-MM-DD)
#
# Public API:
#   count_in_flight(text) -> int         top-level "- " lines excluding "- [x]"
#   parse_board(text) -> list[Task]      structured entries (partial fields ok)
#   validate_id(s) -> bool               the dotted-ID grammar
#   duplicate_ids(text) -> list[str]     IDs appearing more than once, first-seen order
#   stale_in_progress(text, today, threshold_days) -> dict(count, oldest_age, oldest_id)
#   stale_nudge_line(text, today, threshold_days) -> str | None   (ASCII)
#   startup_summary(text, today, threshold_days) -> list[str]     (the reader's lines)
#   read_board(path) -> str | None       thin file reader (not unit-tested)

import datetime
import re
from collections import namedtuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Boards larger than this are not body-parsed at startup; the reader degrades to
# a one-line notice instead of stalling. Mirrors statusline.py's "never read a
# large file" precedent (the > 65536 guard).
MAX_BOARD_BYTES = 65536

# Default age (in days) at which an in-progress task triggers the SessionStart
# nudge. Tunable (open-questions D-3); the mechanism takes `today` injected so it
# is value-independent in tests.
STALE_THRESHOLD_DAYS = 3

# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------

# One parsed task. `id` is None for a legacy bare bullet; date fields are None
# when absent or unparseable; list/str fields default empty (never raise).
Task = namedtuple(
    "Task", "state id title started done desc done_when boundaries raw lineno")

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_DONE_RE = re.compile(r"^- \[[xX]\]")        # a done top-level bullet
_TOP_RE = re.compile(r"^- ")                 # any top-level bullet (column 0)
_ID_RE = re.compile(r"^[a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[0-9]{4,}$")
# A token that LOOKS like an ID (three dot-separated parts) — accepts malformed
# IDs too, so validate_id() can later flag them rather than the parser hiding them.
_IDISH_RE = re.compile(r"^[^\s.]+\.[^\s.]+\.[^\s.]+$")
_SUB_RE = re.compile(r"^\s+-\s*([^:]+):\s*(.*)$")   # indented "  - Key: value"

_STATE_BY_MARK = {" ": "queued", "~": "in_progress", "x": "done", "X": "done"}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def count_in_flight(text):
    """In-flight count = top-level '- ' lines, excluding done ('- [x]').

    Counts queued ('- [ ]'), in-progress ('- [~]') AND legacy bare '- ' bullets
    (backward-compatible with the pre-schema file); excludes only done. Indented
    sub-bullets are never counted. This is the single source both readers use.
    """
    if not text:
        return 0
    return sum(1 for ln in text.splitlines()
               if _TOP_RE.match(ln) and not _DONE_RE.match(ln))


def validate_id(s):
    """True iff `s` matches <group>.<type>.<seq>, seq being >=4 digits.

    Rejects a missing component, a non-numeric or under-padded seq, and any
    uppercase (IDs are lowercase). Growth past 9999 is allowed (>=4 digits).
    """
    return bool(_ID_RE.match(s or ""))


def _extract_date(text, kind):
    """Parse `(kind YYYY-MM-DD)` from `text`; None if absent or unparseable."""
    m = re.search(r"\(" + kind + r"\s+([^)]*)\)", text)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_board(text):
    """Parse board text into a list of Task records.

    A top-level bullet opens a task; the indented `- Key: value` lines beneath it
    (until the next top-level bullet) fill Desc / Done when / Boundaries. Absent
    or `TBD` fields yield empty/`TBD` values — parsing never raises.
    """
    tasks = []
    cur = None

    def _flush():
        if cur is not None:
            tasks.append(Task(**cur))

    for i, raw in enumerate(text.splitlines() if text else []):
        top = _TOP_RE.match(raw)
        if top:
            mark_m = re.match(r"^- \[([ xX~])\]\s*(.*)$", raw)
            if mark_m:
                state = _STATE_BY_MARK.get(mark_m.group(1), "queued")
                body = mark_m.group(2)
            else:
                state = "queued"               # legacy bare "- ..." bullet
                body = raw[2:]
            _flush()
            tid, title = _split_id_title(body)
            cur = dict(
                state=state, id=tid, title=title,
                started=_extract_date(body, "started"),
                done=_extract_date(body, "done"),
                desc="", done_when="", boundaries=[], raw=raw, lineno=i + 1)
            continue
        sub = _SUB_RE.match(raw)
        if sub and cur is not None:
            key = sub.group(1).strip().lower()
            val = sub.group(2).strip()
            if key == "desc":
                cur["desc"] = val
            elif key in ("done when", "done-when"):
                cur["done_when"] = val
            elif key == "boundaries":
                cur["boundaries"] = ([] if val.upper() == "TBD"
                                     else [b.strip() for b in val.split(",") if b.strip()])
    _flush()
    return tasks


def _split_id_title(body):
    """Pull an ID-ish first token (and a title) out of a bullet body.

    Returns (id_or_None, title). The ID is the leading token when it has three
    dot-separated parts (valid OR malformed — validate_id flags bad ones later).
    Strips a leading separator and any trailing (started/done ...) parenthetical
    from the title.
    """
    body = body.strip()
    toks = body.split(None, 1)
    if toks and _IDISH_RE.match(toks[0]):
        tid = toks[0]
        rest = toks[1] if len(toks) > 1 else ""
        rest = re.sub(r"^[—–\-]+\s*", "", rest)   # strip leading em/en/hyphen dash
    else:
        tid = None
        rest = body
    title = re.sub(r"\((?:started|done)\s+[^)]*\)", "", rest).strip()
    return tid, title


def duplicate_ids(text):
    """IDs that appear more than once on the board, in first-duplicate order."""
    seen, dups = set(), []
    for t in parse_board(text):
        if t.id is None:
            continue
        if t.id in seen and t.id not in dups:
            dups.append(t.id)
        seen.add(t.id)
    return dups


def stale_in_progress(text, today, threshold_days=STALE_THRESHOLD_DAYS):
    """In-progress tasks whose (started) age is >= threshold_days.

    `today` is injected (a datetime.date) so the result is reproducible and
    value-independent. A [~] task with a missing/garbage started date is
    age-unknown — never counted stale, never a crash.
    """
    aged = []
    for t in parse_board(text):
        if t.state != "in_progress" or t.started is None:
            continue
        age = (today - t.started).days
        if age >= threshold_days:
            aged.append((age, t.id))
    if not aged:
        return {"count": 0, "oldest_age": None, "oldest_id": None}
    aged.sort(reverse=True)   # largest age first
    return {"count": len(aged), "oldest_age": aged[0][0], "oldest_id": aged[0][1]}


def stale_nudge_line(text, today, threshold_days=STALE_THRESHOLD_DAYS):
    """The one-line startup nudge, or None when nothing is stale. ASCII-only so
    it never trips a Windows console encoding on print."""
    r = stale_in_progress(text, today, threshold_days)
    if not r["count"]:
        return None
    return (f"stale in-progress: {r['count']} "
            f"(oldest {r['oldest_id']}, {r['oldest_age']}d) -- verify or close")


def startup_summary(text, today, threshold_days=STALE_THRESHOLD_DAYS):
    """The task-board lines the SessionStart hook prints.

    Oversize boards degrade to a single notice (never body-parsed). Otherwise:
    the in-flight count, plus the stale-in-progress nudge when any apply.
    """
    if text is None:
        return []
    if len(text.encode("utf-8", "replace")) > MAX_BOARD_BYTES:
        kb = len(text.encode("utf-8", "replace")) // 1024
        return [f"task board too large ({kb}KB) -- open "
                ".codearbiter/open-tasks.md directly"]
    lines = [f"in-flight tasks: {count_in_flight(text)}"]
    nudge = stale_nudge_line(text, today, threshold_days)
    if nudge:
        lines.append(nudge)
    return lines


# ---------------------------------------------------------------------------
# Thin file reader (not unit-tested — pure logic is tested with synthetic text)
# ---------------------------------------------------------------------------

def read_board(path):
    """Read board text, or None if it cannot be read. Never raises."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None
