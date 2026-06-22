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
#   - Never raise on malformed input — a board a human typo'd must degrade to a
#     surfaced warning, never a crash (this is the SessionStart linchpin's path).
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
#   count_in_flight(text) -> int         top-level "- " lines (with content) excluding "- [x]"
#   parse_board(text) -> list[Task]      structured entries (partial fields ok)
#   validate_id(s) -> bool               the dotted-ID grammar
#   duplicate_ids(text) -> list[str]     IDs appearing more than once, first-seen order
#   stale_in_progress(text, today, threshold_days) -> dict(count, oldest_age, oldest_id)
#   undated_in_progress(text) -> list[Task]   [~] tasks with no parseable start date
#   stale_nudge_line(text, today, threshold_days) -> str | None   (ASCII)
#   lint_board(text) -> list[str]        independent "task at risk of dropping off" warnings
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
# Content after the bullet/marker — a bare "- " or empty "- [ ]" is not a task.
# Group 1 (greedy, optional) absorbs the marker so it can't be mistaken for the
# body; group 2 is the actual content.
_CONTENT_RE = re.compile(r"^- (\[[ xX~]\]\s*)?(.*)$")
_ID_RE = re.compile(r"[a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[0-9]{4,}\Z")
# A token that LOOKS like an ID (three dot-separated parts) — accepts malformed
# IDs too, so validate_id() can later flag them rather than the parser hiding them.
_IDISH_RE = re.compile(r"^[^\s.]+\.[^\s.]+\.[^\s.]+$")
_SUB_RE = re.compile(r"^\s+-\s*([^:]+):\s*(.*)$")   # indented "  - Key: value"
# A lifecycle marker sitting at (or near) the start of a line — used by lint to
# catch a task whose marker is NOT in the canonical column-0 "- [m] " position
# (indented, "-[ ]" no-space, "* [ ]" wrong bullet, bare "[ ]"). Anchored to the
# line start so a "[x]" inside a title is NOT a false positive.
_STRAY_MARKER_RE = re.compile(r"^\s*[-*+]?\s*\[[ xX~]\]")
_CANON_TASK_RE = re.compile(r"^- \[[ xX~]\] ")      # a well-formed marked task line

_STATE_BY_MARK = {" ": "queued", "~": "in_progress", "x": "done", "X": "done"}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def _has_content(line):
    """True iff a top-level bullet has a non-empty body after its marker.

    Excludes a stray bare "- " or an empty "- [ ]" so a placeholder dash never
    inflates the count (it is instead surfaced by lint_board)."""
    m = _CONTENT_RE.match(line)
    return bool(m and m.group(2).strip())


def count_in_flight(text):
    """In-flight count = top-level '- ' lines WITH content, excluding done.

    Counts queued ('- [ ]'), in-progress ('- [~]') AND legacy bare '- ' bullets
    (backward-compatible with the pre-schema file); excludes done ('- [x]') and
    empty placeholder bullets. Indented sub-bullets are never counted. This is
    the single source both readers use.
    """
    if not text:
        return 0
    return sum(1 for ln in text.splitlines()
               if _TOP_RE.match(ln) and not _DONE_RE.match(ln) and _has_content(ln))


def validate_id(s):
    """True iff `s` matches <group>.<type>.<seq>, seq being >=4 digits.

    Rejects a missing component, a non-numeric or under-padded seq, uppercase,
    and trailing whitespace/newline (anchored with \\Z, not $). Growth past 9999
    is allowed (>=4 digits).
    """
    return bool(_ID_RE.match(s or ""))


def _extract_date(text, kind):
    """Parse `(kind YYYY-MM-DD)` from `text`; None if absent or unparseable.

    Iterates every `(kind ...)` occurrence and returns the first that parses, so
    a decoy phrase like "(started by Bob)" before the real "(started 2026-06-18)"
    does not shadow the real date.
    """
    for m in re.finditer(r"\(" + kind + r"\s+([^)]*)\)", text):
        try:
            return datetime.datetime.strptime(m.group(1).strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def parse_board(text):
    """Parse board text into a list of Task records.

    A top-level bullet opens a task; the indented `- Key: value` lines beneath it
    fill Desc / Done when / Boundaries. A heading or any non-indented, non-bullet
    line CLOSES the open task, so sub-fields never leak across a `## section`
    boundary. Absent or `TBD` fields yield empty/`TBD` values — never raises.
    """
    tasks = []
    cur = None

    def _flush():
        if cur is not None:
            tasks.append(Task(**cur))

    for i, raw in enumerate(text.splitlines() if text else []):
        if _TOP_RE.match(raw):
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
        elif raw.strip() and not raw[:1].isspace():
            # a non-indented, non-bullet line (e.g. "## heading") closes the task
            _flush()
            cur = None
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
    title = re.sub(r"\((?:started|done)\s+[^)]*\)", "", rest)
    title = re.sub(r"\(from\s+[^)]*\)", "", title).strip()   # back-ref is metadata, not title
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

    `today` is injected (a datetime.date) so the result is reproducible. A [~]
    task with a missing/garbage started date is age-unknown — never counted
    stale here (see undated_in_progress, which surfaces it separately).
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
    # `id or ""` keeps the sort key total-orderable: a legacy bare [~] bullet has
    # id=None, and (int, None) vs (int, str) would raise on a same-age tie.
    aged.sort(key=lambda p: (p[0], p[1] or ""), reverse=True)
    return {"count": len(aged), "oldest_age": aged[0][0], "oldest_id": aged[0][1]}


def undated_in_progress(text):
    """In-progress ([~]) tasks with no parseable started date.

    These can never age, so the stale nudge would miss them forever — the most
    common abandoned-work shape (a human flips to [~] and forgets the date). The
    reader surfaces them as their own class so they cannot drop off the map.
    """
    return [t for t in parse_board(text)
            if t.state == "in_progress" and t.started is None]


def stale_nudge_line(text, today, threshold_days=STALE_THRESHOLD_DAYS):
    """The one-line startup nudge, or None when nothing is stale. ASCII-only so
    it never trips a Windows console encoding on print."""
    r = stale_in_progress(text, today, threshold_days)
    if not r["count"]:
        return None
    return (f"stale in-progress: {r['count']} "
            f"(oldest {r['oldest_id']}, {r['oldest_age']}d) -- verify or close")


def lint_board(text):
    """Independent ground-truth checks that SURFACE a task at risk of dropping
    off the map. Returns human-readable warning lines (empty when clean).

    Catches what count_in_flight is structurally blind to: a lifecycle marker
    that is NOT a counted column-0 task line (indented, "-[ ]" no-space, "* [ ]"
    wrong bullet, bare "[ ]"), plus invalid and duplicate IDs. This is the live
    surface for validate_id / duplicate_ids — without it they are dead code and
    a one-character slip hides a real task with zero signal.
    """
    warnings = []
    if not text:
        return warnings
    stray = [i for i, ln in enumerate(text.splitlines(), 1)
             if _STRAY_MARKER_RE.match(ln) and not _CANON_TASK_RE.match(ln)]
    if stray:
        warnings.append(
            f"{len(stray)} task line(s) look malformed (marker not at column 0, "
            f"first at line {stray[0]}) -- check open-tasks.md")
    bad = sorted({t.id for t in parse_board(text) if t.id and not validate_id(t.id)})
    if bad:
        warnings.append("invalid task id(s): " + ", ".join(bad[:3]))
    dups = duplicate_ids(text)
    if dups:
        warnings.append("duplicate task id(s): " + ", ".join(dups[:3]))
    return warnings


def startup_summary(text, today, threshold_days=STALE_THRESHOLD_DAYS):
    """The task-board lines the SessionStart hook prints.

    Oversize boards degrade to a single notice (never body-parsed). Otherwise:
    the in-flight count, the stale-in-progress nudge, an undated-in-progress
    notice, and any lint warnings (malformed / invalid / duplicate entries).
    """
    if text is None:
        return []
    nbytes = len(text.encode("utf-8", "replace"))
    if nbytes > MAX_BOARD_BYTES:
        return [f"task board too large ({nbytes // 1024}KB) -- open "
                ".codearbiter/open-tasks.md directly"]
    lines = [f"in-flight tasks: {count_in_flight(text)}"]
    nudge = stale_nudge_line(text, today, threshold_days)
    if nudge:
        lines.append(nudge)
    undated = undated_in_progress(text)
    if undated:
        lines.append(f"in-progress with no start date: {len(undated)} "
                     f"(cannot age -- add a date or close)")
    lines.extend(lint_board(text))
    return lines


# ---------------------------------------------------------------------------
# Writer transforms (pure: text in -> new text out; the /ca:task command does I/O)
# ---------------------------------------------------------------------------

# A harvested follow-up candidate. kind in {"work", "decision"}; blocking marks a
# decision that must gate (routed to a [CONFIRM-NN]/escalation, never the
# non-gating Deferred-decisions section). Defaults keep the 4-arg constructions valid.
Candidate = namedtuple("Candidate", "kind desc origin boundaries blocking")
Candidate.__new__.__defaults__ = (False,)
# The outcome of a promote pass.
PromoteResult = namedtuple("PromoteResult", "candidates board questions audit applied")

_MARK_BY_STATE = {"queued": " ", "in_progress": "~", "done": "x"}


def next_seq(text, group, type):
    """Next free 4-digit seq in the `group.type` ID namespace (1 when none)."""
    prefix = f"{group}.{type}."
    mx = 0
    for t in parse_board(text):
        if t.id and t.id.startswith(prefix):
            tail = t.id[len(prefix):]
            if tail.isdigit():
                mx = max(mx, int(tail))
    return mx + 1


def _join(lines, original):
    return "\n".join(lines) + ("\n" if original.endswith("\n") else "")


def _insert_under_section(text, block, section):
    """Insert `block` immediately after the `section` heading, creating the
    section at the end if it is absent."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == section.strip():
            lines.insert(i + 1, block)
            return _join(lines, text or "\n")
    base = text if (text == "" or text.endswith("\n")) else text + "\n"
    return f"{base}{section}\n{block}\n"


def add_entry(text, *, desc, origin=None, group=None, type=None,
              boundaries=None, section="## In-flight"):
    """Append a queued entry. ID-less by default; mints `<group>.<type>.<NNNN>`
    when both group and type are given. Optional `(from <origin>)` back-ref and a
    `Boundaries` sub-bullet. The desc is collapsed to one physical line so a
    multi-line candidate can never inject an orphan/malformed second bullet."""
    desc = (desc or "").replace("\r", " ").replace("\n", " ").strip()
    tid = f"{group}.{type}.{next_seq(text, group, type):04d}" if (group and type) else None
    body = f"{tid} - {desc}" if tid else desc
    line = f"- [ ] {body}"
    if origin:
        line += f"  (from {origin})"
    if boundaries:
        line += f"\n  - Boundaries: {', '.join(boundaries)}"
    return _insert_under_section(text, line, section)


def _find_task_line(lines, target):
    """Index of the task line matching `target` (a dotted id, or the title of an
    ID-less item), or -1. PREFERS an open match: a done line never shadows a live
    task of the same title (it is only used as a fallback for an id-targeted
    re-`done`)."""
    fallback = -1
    for i, ln in enumerate(lines):
        if not _TOP_RE.match(ln):
            continue
        parsed = parse_board(ln)
        if not parsed:
            continue
        t = parsed[0]
        if t.id == target or (t.id is None and t.title == target):
            if t.state != "done":
                return i
            if fallback < 0:
                fallback = i
    return fallback


def set_state(text, target, state, today, *, assign=None):
    """Flip a task's marker and stamp the matching date. `target` is a dotted id
    or the title of an ID-less item (use the id when the desc contains parentheses
    — title matching is best-effort). `in_progress` ALWAYS stamps `(started …)`;
    `done` stamps `(done …)`. With `assign="group.type"` on an ID-less target,
    mints the dotted ID at pick-up. A re-`done` is a no-op; a missing target
    returns the text unchanged (no raise). The line is mutated in place so the
    description text (and the `(from …)` back-ref) is preserved verbatim."""
    lines = text.splitlines()
    idx = _find_task_line(lines, target)
    if idx < 0:
        return text
    raw = lines[idx]
    t = parse_board(raw)[0]
    if state == "done" and t.state == "done":
        return text
    m = re.match(r"^- (?:\[[ xX~]\] )?(.*)$", raw)
    rest = m.group(1) if m else raw[2:]
    if assign and t.id is None and "." in assign:   # mint a dotted ID on pick-up
        g, ty = assign.split(".", 1)
        rest = f"{g}.{ty}.{next_seq(text, g, ty):04d} - {rest}"
    rest = re.sub(r"\s*\((?:started|done)\s+[^)]*\)", "", rest).rstrip()  # drop old stamp, keep the rest
    line = f"- [{_MARK_BY_STATE[state]}] {rest}"
    if state == "in_progress":
        line += f"  (started {today.isoformat()})"
    elif state == "done":
        line += f"  (done {today.isoformat()})"
    lines[idx] = line
    return _join(lines, text)


def already_promoted(text, origin):
    """True iff an OPEN (non-done) entry already carries `(from <origin>)`."""
    needle = f"(from {origin})"
    return any(_TOP_RE.match(ln) and not _DONE_RE.match(ln) and needle in ln
               for ln in text.splitlines())


# ---------------------------------------------------------------------------
# Harvest extractors (pure: artifact text -> candidate list)
# ---------------------------------------------------------------------------

def extract_needs_triage(text, origin):
    """Candidates from `[NEEDS-TRIAGE]` markers (tdd / brainstorming /
    writing-plans / commit-gate residue). kind=work."""
    out = []
    for ln in (text or "").splitlines():
        if "[NEEDS-TRIAGE]" in ln:
            desc = ln.split("[NEEDS-TRIAGE]", 1)[1].strip(" \t-:")
            out.append(Candidate("work", desc, f"{origin}#triage-{len(out) + 1}", []))
    return out


def extract_deferrable(text, origin):
    """Candidates from a checkpoint doc's `### DEFERRABLE` section. The real
    checkpoint-aggregator emits a markdown TABLE (`| Finding | Source | Severity |`);
    a hand-written bullet list is also accepted. The heading must START with
    DEFERRABLE (so a prose `###` mentioning the word doesn't trigger), and only
    column-0 bullets / table rows are taken (nested sub-bullets are ignored).
    kind=work (re-tag to decision at the confirm step if it is really a decision)."""
    out, in_def = [], False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("###"):
            in_def = s.lstrip("# ").upper().startswith("DEFERRABLE")
            continue
        if not in_def:
            continue
        if s.startswith("|"):                       # table row
            cells = [c.strip() for c in s.strip("|").split("|")]
            first = cells[0] if cells else ""
            if not first or first.lower() == "finding" or set(first) <= set("-: "):
                continue                            # header / separator row
            desc = first
        elif ln.startswith("- ") or ln.startswith("* "):   # column-0 bullet only
            desc = ln[2:].strip()
        else:
            continue
        out.append(Candidate("work", desc, f"{origin}#deferrable-{len(out) + 1}", []))
    return out


def extract_low_confidence(text, origin):
    """Candidates from `sprint-log.md` `confidence: low` auto-decisions. kind=work."""
    out = []
    for ln in (text or "").splitlines():
        if ln.lstrip().startswith("#") and "confidence: low" in ln.lower():
            title = re.split(r"·\s*confidence:\s*low", ln.lstrip("#").strip(),
                             flags=re.I)[0].strip()
            out.append(Candidate("work", title, f"{origin}#{len(out) + 1}", []))
    return out


# ---------------------------------------------------------------------------
# Promote (route + dedup + apply)
# ---------------------------------------------------------------------------

def _add_deferred_decision(questions, desc, origin):
    block = f"- **(harvested)** {desc}  (from {origin})"
    lines = questions.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("## deferred decisions"):
            lines.insert(i + 1, block)
            return _join(lines, questions or "\n")
    base = questions if (questions == "" or questions.endswith("\n")) else questions + "\n"
    return f"{base}\n## Deferred decisions\n{block}\n"


def promote(board, questions, candidates, *, mode, today):
    """Route follow-up candidates: work -> board, decision -> questions. Dedups by
    origin. mode="interactive" returns the fresh candidates WITHOUT mutating
    (caller confirms, then applies); mode="auto" applies and returns an audit."""
    fresh = []
    for c in candidates:
        if c.kind == "work" and already_promoted(board, c.origin):
            continue
        if c.kind == "decision" and f"(from {c.origin})" in questions:
            continue
        fresh.append(c)
    if mode == "interactive":
        return PromoteResult(fresh, board, questions, [], False)
    nb, nq, audit = board, questions, []
    for c in fresh:
        if c.kind == "work":
            nb = add_entry(nb, desc=c.desc, origin=c.origin,
                           boundaries=(c.boundaries or None))
            audit.append(f"work -> open-tasks: {c.desc} (from {c.origin})")
        elif getattr(c, "blocking", False):
            # A blocking decision must GATE — it is never filed into the
            # non-gating Deferred-decisions section. Escalate for a [CONFIRM-NN].
            audit.append(f"ESCALATE (blocking decision — author a [CONFIRM-NN]): "
                         f"{c.desc} (from {c.origin})")
        else:
            nq = _add_deferred_decision(nq, c.desc, c.origin)
            audit.append(f"decision -> open-questions: {c.desc} (from {c.origin})")
    return PromoteResult(fresh, nb, nq, audit, True)


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
