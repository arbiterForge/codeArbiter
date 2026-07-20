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
#   next_seq(text, group, type) -> int   next free seq in a group.type namespace
#   add_entry(text, *, desc, origin, group, type, boundaries, section) -> str
#   add_error(*, desc, origin, boundaries, section) -> str | None
#                                        field-specific validation error for add input
#   set_state(text, target, state, today, *, assign) -> str
#                                        state in {"queued","in_progress","done"}; unknown
#                                        state degrades gracefully (returns text unchanged)
#   transition_error(text, target, state) -> str | None
#                                        actionable error for a found task whose requested
#                                        transition violates queued -> in-progress -> done
#   already_promoted(text, origin) -> bool
#   extract_needs_triage(text, origin) -> list[Candidate]
#   extract_deferrable(text, origin) -> list[Candidate]
#   extract_low_confidence(text, origin) -> list[Candidate]
#   promote(board, questions, candidates, *, mode, today) -> PromoteResult
#                                        mode in {"interactive","auto"}; unknown mode
#                                        raises ValueError
#   classify_board_diff(old_text, new_text) -> bool
#                                        True iff the change is a clean done-flip,
#                                        start-flip, or single queued add (with its
#                                        missing section heading if needed); never raises
#   extract_task_ids(text) -> list[str]  valid dotted task-ids found in arbitrary text
#                                        (e.g. git log output); deduped, first-seen
#                                        order; never raises
#   find_board_drift(board_text, merged_ids, today) -> DriftResult
#                                        tasks whose work merged but board state is not
#                                        [x]; pure, never raises; DriftResult fields:
#                                        drifted (list[Task]), unknown (list[str]),
#                                        observed (datetime.date)

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

# Result of find_board_drift. All fields always present (never None):
#   drifted  — list[Task] whose state is not "done" and whose id is in merged_ids
#              (work merged but board was never flipped to [x]).
#   unknown  — list[str] of merged_ids absent from the board entirely
#              (informational; first-seen order, deduped; never treated as drift).
#   observed — datetime.date passed by the caller (stamps when the sweep ran).
DriftResult = namedtuple("DriftResult", "drifted unknown observed")

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
# A token that LOOKS like an ID (three OR MORE dot-separated parts) — accepts
# malformed IDs too (including an over-segmented "a.b.c.d"), so validate_id() can
# later flag them and set_state() can target them, rather than the parser hiding a
# 4-segment token inside the title where it becomes un-targetable and un-lintable.
_IDISH_RE = re.compile(r"^[^\s.]+(?:\.[^\s.]+){2,}$")
_SUB_RE = re.compile(r"^\s+-\s*([^:]+):\s*(.*)$")   # indented "  - Key: value"
# A lifecycle marker sitting at (or near) the start of a line — used by lint to
# catch a task whose marker is NOT in the canonical column-0 "- [m] " position
# (indented, "-[ ]" no-space, "* [ ]" wrong bullet, bare "[ ]"). Anchored to the
# line start so a "[x]" inside a title is NOT a false positive.
_STRAY_MARKER_RE = re.compile(r"^\s*[-*+]?\s*\[[ xX~]\]")
_CANON_TASK_RE = re.compile(r"^- \[[ xX~]\] ")      # a well-formed marked task line

_STATE_BY_MARK = {" ": "queued", "~": "in_progress", "x": "done", "X": "done"}

# classify_board_diff helpers — strip markers/stamps for content-equality comparison.
_STAMP_FULL_RE = re.compile(r'\s*\((?:started|done)\s+\d{4}-\d{2}-\d{2}\)')
_STATE_MARK_RE = re.compile(r'^- \[([ xX~])\]\s*')
_QUEUED_TOP_RE = re.compile(r'^- \[ \] .+')
_INDENTED_BULLET_RE = re.compile(r'^\s+- ')
_LINE_BREAK_RE = re.compile(r'[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]')
# extract_task_ids search pattern — non-anchored; two-part negative lookahead so
# trailing sentence punctuation (e.g. "mvp1.ui.0005.") is not blocked, while an
# extended alphanumeric suffix ("poc.auth.0001x") and a continuing dot-segment
# ("poc.auth.0001.extra") are both rejected:
#   (?![a-z0-9])        — no letter/digit immediately after the seq digits
#   (?!\.[a-z0-9])      — no dot immediately followed by a letter/digit (next segment)
# The negative lookbehind prevents matching a mid-word start or a token that is
# already part of a longer dotted sequence (preceded by "." or alphanum).
# Every candidate is additionally gated through validate_id() so only
# grammar-valid IDs are returned.
_TASK_ID_SCAN_RE = re.compile(
    r"(?<![a-z0-9.])([a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[0-9]{4,})(?![a-z0-9])(?!\.[a-z0-9])"
)


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


def _strip_stamps_and_marker(line):
    """Strip the state marker and (started/done YYYY-MM-DD) stamps for content comparison.

    Used by classify_board_diff to check whether two task lines differ only in their
    state marker and date stamp, and not in their descriptive content.
    """
    line = _STATE_MARK_RE.sub('', line)
    line = _STAMP_FULL_RE.sub('', line)
    return line.rstrip()


def _is_valid_state_flip(old_line, new_line):
    """True iff old_line → new_line is a valid done-flip ([~]→[x]+done) or
    start-flip ([ ]→[~]+started), with all other content unchanged. A start may
    also mint one valid dotted ID on an ID-less task, matching ``set_state``'s
    ``assign`` path."""
    old_m = _STATE_MARK_RE.match(old_line)
    new_m = _STATE_MARK_RE.match(new_line)
    if not old_m or not new_m:
        return False
    old_mark = old_m.group(1).lower()
    new_mark = new_m.group(1).lower()
    # done-flip: [~] → [x], new line must carry (done YYYY-MM-DD)
    if old_mark == '~' and new_mark == 'x':
        if _extract_date(new_line, 'done') is None:
            return False
        return _strip_stamps_and_marker(old_line) == _strip_stamps_and_marker(new_line)
    # start-flip: [ ] → [~], new line must carry (started YYYY-MM-DD)
    if old_mark == ' ' and new_mark == '~':
        if _extract_date(new_line, 'started') is None:
            return False
        old_content = _strip_stamps_and_marker(old_line)
        new_content = _strip_stamps_and_marker(new_line)
        if old_content == new_content:
            return True
        old_task = parse_board(old_line)[0]
        new_task = parse_board(new_line)[0]
        if old_task.id is not None or not validate_id(new_task.id):
            return False
        minted_prefix = f"{new_task.id} - "
        return (new_content.startswith(minted_prefix)
                and new_content[len(minted_prefix):] == old_content)
    return False


def _is_valid_queued_block(lines):
    """True iff `lines` form a single valid queued entry: one `- [ ] desc` top-level
    line (non-empty) optionally followed by indented sub-bullets only (e.g. Boundaries)."""
    if not lines or not _QUEUED_TOP_RE.match(lines[0]):
        return False
    return all(_INDENTED_BULLET_RE.match(ln) for ln in lines[1:])


def _is_valid_new_section_add(lines):
    """True iff ``lines`` are one new level-two section plus one queued entry.

    This is the exact shape ``add_entry`` emits when its requested section does
    not yet exist. The queued entry may carry its normal indented metadata, but
    no free-form content or second entry is accepted.
    """
    return (len(lines) >= 2
            and re.match(r"^##\s+\S.*$", lines[0]) is not None
            and _is_valid_queued_block(lines[1:]))


def classify_board_diff(old_text, new_text):
    """True iff the change from old_text to new_text is a clean task-board transition.

    A clean transition is EXACTLY ONE of:
    - done-flip: one task's marker changes [~] → [x], a (done YYYY-MM-DD) stamp is
      added, and no other content changes (a prior (started ...) stamp is allowed to
      drop; nothing else may change);
    - start-flip: one task's marker changes [ ] → [~], a (started YYYY-MM-DD) stamp
      is added, and no other content changes except an ID-less task may gain the
      single valid dotted ID minted by the writer's pick-up path;
    - add: exactly one new queued top-level entry `- [ ] desc` (optionally with a
      dotted id, a (from <origin>) back-ref, and/or an indented `- Boundaries:`
      sub-bullet) is inserted or appended, and no existing line is changed. If
      its requested section is absent, the writer's one new level-two heading
      immediately followed by that entry may be appended with it.

    Returns False for anything else: reworded description, deleted entry, marker
    change without the required date stamp, multiple simultaneous transitions, an
    edit to an unrelated line, or any content change beyond those above.

    Never raises — empty, None, or garbled input degrades to False (same crash-safe
    invariant as all other _taskboardlib pure functions).
    """
    try:
        if not old_text or not new_text:
            return False
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        # ── state-flip branch: same line count, exactly one line changed ──────
        if len(old_lines) == len(new_lines):
            changed = [(old_lines[i], new_lines[i])
                       for i in range(len(old_lines))
                       if old_lines[i] != new_lines[i]]
            return len(changed) == 1 and _is_valid_state_flip(*changed[0])

        # ── add branch: new has more lines; all old lines intact, extra is one ─
        if len(new_lines) > len(old_lines):
            n_extra = len(new_lines) - len(old_lines)
            # find how many leading lines are already identical (the common prefix)
            k = 0
            while k < len(old_lines) and old_lines[k] == new_lines[k]:
                k += 1
            extra = new_lines[k:k + n_extra]
            # the lines after the inserted block must equal the old suffix
            if new_lines[k + n_extra:] != old_lines[k:]:
                return False
            if _is_valid_queued_block(extra):
                return True
            return (k == len(old_lines)
                    and _is_valid_new_section_add(extra)
                    and all(line.strip() != extra[0].strip() for line in old_lines))

        # new has fewer lines than old — a deletion, never a clean transition
        return False
    except Exception:
        return False


def extract_task_ids(text):
    """Scan arbitrary text and return valid dotted task-ids in first-seen order.

    Finds ids matching <group>.<type>.<seq> where seq is >=4 digits — the same
    grammar validate_id enforces (e.g. 'v2.rev.0020', 'poc.auth.0001'). Tokens
    that do not match the grammar (issue refs like '#142', version shorthands
    like 'v2', dates, bare words, extended tokens like 'poc.auth.0001x') are
    silently ignored. Deduplicates while preserving first-seen order.

    Never raises — None, empty, or garbled input returns [] (crash-safe
    invariant, same as classify_board_diff and all other pure functions here).
    """
    try:
        if not text:
            return []
        seen_set = set()
        seen_list = []
        for m in _TASK_ID_SCAN_RE.finditer(text):
            candidate = m.group(1)
            if validate_id(candidate) and candidate not in seen_set:
                seen_set.add(candidate)
                seen_list.append(candidate)
        return seen_list
    except Exception:
        return []


def find_board_drift(board_text, merged_ids, today):
    """Detect task-board drift: tasks whose work merged but board state is not [x].

    board_text  — the open-tasks.md text.
    merged_ids  — list/iterable of dotted task-ids referenced in merged work,
                  typically produced upstream by extract_task_ids.
    today       — a datetime.date; stored as DriftResult.observed so the caller
                  can stamp the report with the sweep date (not a dead parameter).

    Returns a DriftResult namedtuple:
      drifted  — Task records with state 'queued' or 'in_progress' whose id is
                 in merged_ids (work merged, board not yet flipped to done).
      unknown  — merged_ids absent from the board entirely (informational;
                 first-seen order, deduped; never reported as drift or done).
      observed — today (the observation date).

    Never raises. None/empty board_text or merged_ids returns an empty
    DriftResult (drifted=[], unknown=[], observed=today). A merged_id not
    present on the board surfaces in unknown only — the function writes nothing;
    it is pure and returns data only.
    """
    try:
        if not board_text or not merged_ids:
            return DriftResult([], [], today)

        # Build an id -> Task index; id=None legacy bullets are not addressable.
        board_by_id = {}
        for t in parse_board(board_text):
            if t.id is not None:
                board_by_id[t.id] = t

        drifted = []
        unknown = []
        seen_unknown = set()

        for mid in merged_ids:
            if mid in board_by_id:
                t = board_by_id[mid]
                if t.state != "done":
                    drifted.append(t)
                # done → already [x], excluded from drift (AC-09)
            else:
                # absent from the board → informational unknown, never drift
                if mid not in seen_unknown:
                    seen_unknown.add(mid)
                    unknown.append(mid)

        return DriftResult(drifted, unknown, today)
    except Exception:
        return DriftResult([], [], today)


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


def add_error(*, desc, origin=None, boundaries=None, section="## In-flight"):
    """Return a field-specific error for an add input, else ``None``.

    These constraints keep every accepted field on the physical line where the
    board schema expects it. The section must be one canonical level-two heading;
    descriptions are nonblank; optional metadata cannot contain line breaks.
    """
    if not isinstance(desc, str) or not desc.strip():
        return "bad description: expected nonblank single-line text"
    if _LINE_BREAK_RE.search(desc):
        return "bad description: expected nonblank single-line text"
    if (not isinstance(section, str)
            or _LINE_BREAK_RE.search(section)
            or re.fullmatch(r"## \S(?:.*\S)?", section) is None):
        return ("bad --section: expected one canonical level-two heading, "
                "e.g. '## In-flight'")
    if origin is not None and (not isinstance(origin, str)
                               or _LINE_BREAK_RE.search(origin)):
        return "bad --from: expected single-line text"
    if boundaries is not None:
        if not isinstance(boundaries, (list, tuple)):
            return "bad --boundaries: expected comma-separated single-line values"
        invalid = any(not isinstance(boundary, str)
                      or not boundary.strip()
                      or _LINE_BREAK_RE.search(boundary)
                      for boundary in boundaries)
        if invalid:
            return ("bad --boundaries: each comma-separated boundary must be "
                    "nonblank single-line text")
    return None


def add_entry(text, *, desc, origin=None, group=None, type=None,
              boundaries=None, section="## In-flight"):
    """Append a queued entry. ID-less by default; mints `<group>.<type>.<NNNN>`
    when both group and type are given. Optional `(from <origin>)` back-ref and a
    `Boundaries` sub-bullet. Invalid fields fail soft by returning ``text``
    unchanged, so no input can inject an orphan/malformed physical line."""
    if add_error(desc=desc, origin=origin, boundaries=boundaries, section=section):
        return text
    desc = desc.strip()
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


def transition_error(text, target, state):
    """Return an actionable error when a found task cannot enter ``state``.

    The sanctioned writer's lifecycle is queued -> in-progress -> done. Missing
    targets and unknown states are left to ``set_state`` and its caller so their
    existing graceful-degradation messages stay unchanged. Re-done is also left
    to ``set_state`` as the established safe no-op.
    """
    if state not in ("in_progress", "done"):
        return None
    lines = text.splitlines()
    idx = _find_task_line(lines, target)
    if idx < 0:
        return None
    task = parse_board(lines[idx])[0]
    if state == "done" and task.state == "queued":
        return f"cannot mark '{target}' done: task is queued; start it first"
    if state == "in_progress" and task.state == "done":
        return f"cannot start '{target}': task is already done"
    if state == "in_progress" and task.state == "in_progress":
        return f"no change: '{target}' is already in_progress"
    return None


def set_state(text, target, state, today, *, assign=None):
    """Flip a task's marker and stamp the matching date. `target` is a dotted id
    or the title of an ID-less item (use the id when the desc contains parentheses
    — title matching is best-effort). `in_progress` ALWAYS stamps `(started …)`;
    `done` accepts only an in-progress task and stamps `(done …)`. With
    `assign="group.type"` on an ID-less target,
    mints the dotted ID at pick-up. A queued-to-done transition is rejected, a
    re-`done` is a no-op, and a missing target
    returns the text unchanged (no raise). An unknown `state` value degrades
    gracefully: returns `text` unchanged rather than raising KeyError (coding
    standard: never raise on malformed user input — this is a hook-stdin path).

    Valid state values: "queued", "in_progress", "done"."""
    if (state not in _MARK_BY_STATE
            or (assign is not None and not validate_id(f"{assign}.0000"))
            or transition_error(text, target, state)):
        return text
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
    (caller confirms, then applies); mode="auto" applies and returns an audit.

    Valid mode values: "interactive", "auto". Any other value raises ValueError
    so a typo (e.g. mode="dry-run") is caught immediately rather than silently
    applying all candidates to persistent state."""
    _VALID_MODES = ("interactive", "auto")
    if mode not in _VALID_MODES:
        raise ValueError(
            f"promote: unknown mode {mode!r}; expected one of {_VALID_MODES}"
        )
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
