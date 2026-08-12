#!/usr/bin/env python3
# codeArbiter — mode plane: the three-value runtime posture (arbiter/dangerous/
# ops), its deterministic token flip, and the write-ahead audit-close ledger
# that backs it (#437, mode-plane-deterministic-flip).
#
# T-06 (pure refactor, no behavior change): the write-ahead ledger machinery —
# `_settle_dev_close` and its pending-close record — moved here verbatim from
# `core/pysrc/session-start.py` (formerly ~lines 551-810). `session-start.py`
# now imports `_settle_dev_close` (and the `_DEV_PENDING_CLOSE_MAX` constant,
# which a pre-existing test reads off the session-start module) from here;
# `clear_dev_marker` itself stays in session-start.py — this module owns the
# ledger MECHANISM, not the SessionStart-specific policy of when to invoke it.
#
# The proof this introduced no behavior change: the pre-existing
# `TestDevExitRetryablePendingClose` cases in
# `plugins/ca/hooks/tests/test_session_start.py` pass UNMODIFIED against the
# regenerated (sync-core.py) vendored copy, which now imports from this file.

from __future__ import annotations

import datetime
import json
import os
import re

from _activationlib import marker_root
from _hooklib import write_text_atomic


# ---------------------------------------------------------------------------
# T-16 — PERSONA_SENTINEL: a single stable literal embedded in every composed
# persona injection (T-31, Lane B), so a later transcript-pruning pass
# (`_prunelib`/`_prunepolicy`, T-49/T-50, R-5) can recognize an injected-
# persona line and mark it `pinned=True` — protected from folding,
# condensing, and eviction at EVERY tier, including aggressive (AC-26).
#
# Deliberately shaped as an HTML comment (renders invisibly in the persona
# markdown) and deliberately distinct from `_prunepolicy.MARKER_PREFIX`
# ("[ca-condensed ") — the two must never collide: one marks "this content
# was ELIDED by a prior prune pass", the other marks "this content must
# NEVER be elided". Exported here, not in `_prunelib`/`_prunepolicy`,
# because the INJECTOR (this module's consumers) is the single source that
# must emit it — a value redefined in two places is a value that can drift.
PERSONA_SENTINEL = "<!-- codearbiter:persona-sentinel -->"


# ---------------------------------------------------------------------------
# T-07 — the mode plane: three-value posture, resolved through marker_root
# ---------------------------------------------------------------------------
# `MODES` is the ONLY legal-value tuple; `dev` is retired (superseded by
# `dangerous`, R-3/ADR-0022 supersession). Index 0 is deliberately the safe
# default every anomaly falls back to.
MODES = ("arbiter", "dangerous", "ops")

# [[never-fold-unreadable-into-absent]] — the house rule this constant set
# exists to satisfy: a marker file that genuinely does not exist and one that
# exists but could not be read/parsed are DIFFERENT failure classes and must
# never collapse onto one diagnostic string. Every non-None diagnostic below
# still resolves the mode to MODES[0] ("arbiter") — these strings distinguish
# WHY, not WHAT the fallback is.
MODE_DIAG_ABSENT = "mode-marker-absent"
MODE_DIAG_UNREADABLE = "mode-marker-unreadable"
MODE_DIAG_UNRECOGNIZED = "mode-marker-unrecognized"


def mode_marker_path(root=None, payload=None):
    """Absolute path of the mode marker: `<root>/.codearbiter/.markers/mode`.

    `root` defaults to `_activationlib.marker_root(payload)` — deliberately
    NOT `project_root(payload)`: `marker_root` exists precisely because
    `project_root` splits marker state across linked worktrees (#604), and
    every other `.codearbiter/.markers/` writer (security-pass.py,
    migration-pass.py, the H-09b/H-10b/H-14 guards) already resolves through
    it. An explicit `root` is accepted as a test-only escape hatch for
    fixture isolation — production callers pass neither and let this resolve
    via the host seam."""
    if root is None:
        root = marker_root(payload)
    return os.path.join(root, ".codearbiter", ".markers", "mode")


def _read_mode_state(root=None, payload=None):
    """(state, diagnostic) off the mode marker file.

    `state` is the RAW dict mapping session_id -> whatever value was on disk
    for it (validation of an individual session's value is `current_mode`'s
    job, not this function's — a per-session bad value must still be visible
    to the caller so it can be reported, not silently dropped). Always a
    dict, never None, so callers never need a None-check. A file that is
    itself absent, unreadable, empty, or not a JSON object returns `{}` plus
    a diagnostic.

    `diagnostic` is None on a clean read (the file parses as a JSON object —
    individual bad entries inside it do not taint this diagnostic). Otherwise
    exactly one of MODE_DIAG_ABSENT / MODE_DIAG_UNREADABLE /
    MODE_DIAG_UNRECOGNIZED — `os.path.exists` (not `os.path.isfile`) gates the
    absent check, so a path that exists but cannot be opened as a normal file
    (a directory sitting at that path, or a real permissions error) falls
    through to the `open()` call and is correctly reported UNREADABLE rather
    than ABSENT. This is the portable, no-chmod-needed shape of the
    distinction: a directory path always fails `open()` (IsADirectoryError on
    POSIX, PermissionError on Windows — both are OSError) without depending
    on host-specific permission semantics."""
    path = mode_marker_path(root, payload)
    if not os.path.exists(path):
        return {}, MODE_DIAG_ABSENT
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:  # noqa: BLE001 — exists but could not be read
        return {}, MODE_DIAG_UNREADABLE
    text = text.strip()
    if not text:
        return {}, MODE_DIAG_UNRECOGNIZED
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001 — not valid JSON
        return {}, MODE_DIAG_UNRECOGNIZED
    if not isinstance(data, dict):
        return {}, MODE_DIAG_UNRECOGNIZED
    return data, None


def current_mode(session_id, root=None, payload=None):
    """(mode, diagnostic) for `session_id`.

    Resolves MODES[0] ("arbiter") whenever the marker file is absent, empty,
    unreadable, or unrecognized (AC-2) — WITH a diagnostic distinguishing
    which — and also when the file is clean but simply has no entry yet for
    this session (a fresh session legitimately starts arbiter; that is not an
    anomaly, so diagnostic is None). When the file is clean but THIS
    session's own recorded value is not a legal mode, that is reported the
    same as a file-level unrecognized value (MODE_DIAG_UNRECOGNIZED) — a
    garbage per-session entry is exactly as much an anomaly as a garbage
    file, and must not be swallowed silently."""
    state, diag = _read_mode_state(root, payload)
    if diag is not None:
        return MODES[0], diag
    if session_id not in state:
        return MODES[0], None
    value = state.get(session_id)
    if value not in MODES:
        return MODES[0], MODE_DIAG_UNRECOGNIZED
    return value, None


def write_mode(session_id, mode, root=None, payload=None):
    """Persist `mode` for `session_id` (T-08, AC-1).

    Read-modify-write over the marker's `{session_id: mode}` JSON object.
    The write itself is delegated ENTIRELY to `write_text_atomic` — this
    function does no `open()`/`write()` of its own — so an interrupted write
    can only ever land in write_text_atomic's own guarantee: a sibling temp
    file, then `os.replace()`; on any failure the temp is removed and `path`
    is left exactly as it was (untouched if it existed, absent if it did
    not). Returns True on a confirmed write, False on failure. Never
    raises — the caller (`flip`, T-11/T-14) decides what failure means."""
    path = mode_marker_path(root, payload)
    state, _diag = _read_mode_state(root, payload)
    state = dict(state)
    state[session_id] = mode
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomic(path, json.dumps(state), newline="\n")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# T-11 — flip(): the deterministic token-flip primitive every host caller
# (prompt-submit.py, pi-bridge.py) drives through. Three distinct sentinels,
# never a bare bool — a caller has to tell "already there" from "the write
# failed" apart to report either correctly to the user.
# ---------------------------------------------------------------------------
FLIP_FLIPPED = "flipped"
FLIP_NOOP = "noop"
FLIP_FAILED = "failed"


def _mode_audit_line(verb, mode, host_name=None, now=None):
    """One `MODE: <name> enter|exit` audit row (Decided parameters: Audit
    verb). `now` (epoch seconds) is injectable for deterministic tests;
    defaults to the real current time."""
    ts = (datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
          if now is not None
          else datetime.datetime.now(datetime.timezone.utc))
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f"[{ts_str}] | BY: session-mode | HOST: {host_name or 'unknown'} "
            f"| MODE: {mode} {verb} | NOTE: —\n")


def flip(session_id, mode, root=None, payload=None, host_name=None, now=None):
    """Attempt to set `session_id`'s mode to `mode`. Returns one of
    FLIP_FLIPPED / FLIP_NOOP / FLIP_FAILED. Never raises.

    AC-6: a flip TO THE ALREADY-ACTIVE mode is a no-op — no write is even
    attempted and no audit row is appended, so `overrides.log` is left
    byte-identical. This is also the mechanism behind T-14's fail-direction
    asymmetry: once a failed flip has left the session's resolved mode
    unchanged, any LATER flip back to that same resolved mode is a no-op
    under ANY filesystem state — including a markers directory that cannot
    be written to at all — because a no-op never touches disk.

    On a genuine transition the order is deliberate: write first, audit row
    ONLY on a confirmed write. AC-11's `ledger_backs` exists to catch exactly
    the opposite ordering — a ledger row minted for a flip that never
    actually landed, which would let an unbacked marker masquerade as an
    audited one."""
    root = root if root is not None else marker_root(payload)
    current, _diag = current_mode(session_id, root=root, payload=payload)
    if current == mode:
        return FLIP_NOOP
    if not write_mode(session_id, mode, root=root, payload=payload):
        return FLIP_FAILED
    _append_override_line(root, _mode_audit_line("enter", mode, host_name=host_name, now=now))
    return FLIP_FLIPPED


# ---------------------------------------------------------------------------
# T-12 — the token table: `mode --arbiter|--dangerous|--ops`, matched
# WHOLE-PROMPT, never substring (Decided parameters: Token). Pure text logic,
# no I/O — every host's prompt-seam interceptor (Claude/Codex/Pi) imports
# this so the matching rule can never drift between hosts.
# ---------------------------------------------------------------------------
MODE_TOKEN_REPORT = "report"   # bare `mode`: report current + legal values, write nothing

_MODE_TOKEN_RE = re.compile(r"mode(?:\s+--(arbiter|dangerous|ops))?", re.I)


def match_mode_token(prompt):
    """Classify `prompt` against the mode control-token table.

    Returns one of MODES (a flip request), MODE_TOKEN_REPORT (bare `mode`),
    or None (not a control token at all — the prompt reaches the model
    unmodified).

    Whole-prompt only: `re.fullmatch` against the prompt after stripping
    SURROUNDING whitespace (never internal) means a token embedded anywhere
    in a longer prompt — before, after, or on another line — cannot match,
    because fullmatch requires the ENTIRE stripped string to be consumed by
    the pattern and the pattern contains no `\\n`. Case-insensitive (`re.I`);
    surrounding whitespace of any kind (spaces, tabs, newlines) is
    insensitive because it is stripped before matching."""
    if not isinstance(prompt, str):
        return None
    stripped = prompt.strip()
    if not stripped:
        return None
    m = _MODE_TOKEN_RE.fullmatch(stripped)
    if not m:
        return None
    name = m.group(1)
    if name is None:
        return MODE_TOKEN_REPORT
    return name.lower()


# ---------------------------------------------------------------------------
# T-13 — ledger_backs(): the AC-11 compensating control. The deterministic
# flip removes ADR-0022's tier-2 confirmation for dangerous-mode entry (its
# supersession, per the spec's ADR conflict note); this is the load-bearing
# replacement — the injector refuses to compose a non-arbiter body the audit
# trail does not back.
# ---------------------------------------------------------------------------
_LEGACY_DEV_ENTER_RE = re.compile(r"\|\s*DEV:\s*enter\s*(?:\||$)", re.M)


def ledger_backs(root, mode):
    """True iff `overrides.log` (at `root`) holds a matching
    `MODE: <mode> enter` row.

    A legacy `DEV: enter` row backs `mode == "dangerous"` ONLY — dev was
    retired INTO dangerous (T-47 converts a live `dev-active` marker to
    `dangerous` exactly once), so a pre-mode-plane audit trail's DEV: enter
    rows must continue to authorize it. A legacy row must NEVER back `ops`:
    `ops` did not exist when any DEV: row could have been written, so
    accepting one there would be a fail-OPEN into a mode the operator never
    actually requested — the exact failure this function exists to prevent,
    just relocated to a different mode.

    Read-only and tolerant: an absent or unreadable log answers False,
    never raises — consistent with this module's fail-toward-arbiter
    convention (a missing ledger can never AUTHORIZE anything)."""
    try:
        with open(_overrides_log_path(root), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001 — absent/unreadable log -> nothing backs it
        return False
    enter_re = re.compile(r"\|\s*MODE:\s*" + re.escape(mode) + r"\s+enter\s*(?:\||$)", re.M)
    if enter_re.search(text):
        return True
    if mode == "dangerous" and _LEGACY_DEV_ENTER_RE.search(text):
        return True
    return False


# --- #396: a durable, retryable DEV: exit -----------------------------------
# The synthetic close line is the ONLY thing that keeps the append-only audit
# trail's DEV: enter/exit pairs matched after an abandoned maintainer session.
# It used to be written best-effort ("except OSError: pass") and the marker was
# then removed regardless — so a locked file, a full disk, or a permission blip
# permanently erased the obligation and left an orphaned DEV: enter that no
# later session could know about.
#
# The fix is a small write-ahead record: the owed line is staged on disk BEFORE
# the append is attempted, and the record is deleted only once BOTH the append
# is confirmed AND the marker it settles is gone. That single record therefore
# carries three facts at once:
#
#   "lines"        — close lines still owed to overrides.log. Emptied one at a
#                    time as each append is confirmed.
#   "marker_mtime" — the identity of the dev-active marker this close belongs
#                    to. While the record still names a LIVE marker, the
#                    force-close path knows that marker has already been
#                    closed in the audit trail and refuses to mint a second
#                    row for it — which is what makes a failed `os.remove`
#                    idempotent rather than duplicating the close. It is
#                    cleared the moment that marker is gone: an mtime only
#                    identifies a file that still EXISTS, and a stale one is
#                    free to collide with an unrelated future marker (2s
#                    granularity on FAT32/exFAT/SMB/WSL mounts makes that a
#                    real event, not a theoretical one) and suppress a close
#                    that is genuinely owed.
#   "dropped"      — how many owed close lines the bound below has discarded.
#                    The cap keeps the record small, but the loss must not be
#                    silent: the count is written to the trail as one
#                    attributable note the moment overrides.log accepts writes.
#
# Replayed lines carry the timestamp they were MINTED with, not the time they
# land, so a delayed replay leaves overrides.log non-chronological. Enter/exit
# pairing is by timestamp, so that is correct — but an audit reader must not
# assume file order is time order.
#
# Every boundary is covered:
#   crash before the append      -> record present, line owed  -> replayed
#   crash after the append       -> record present, line owed  -> the bounded
#                                   tail scan sees the line already landed and
#                                   drops it instead of appending a duplicate
#   marker removal fails         -> record present, no line owed -> the next
#                                   session only retries the removal
#
# That tail scan is applied ONLY to lines read back off the record — the ones
# that might have landed before a crash. A line minted in THIS process cannot
# already be on the trail, and must never be dedupe-checked: close rows are
# timestamped to the second, so two distinct closes minted in the same second
# are byte-identical, and checking the fresh one against an owed copy of itself
# would silently swallow a close that is genuinely owed.
#
# Everything here is best-effort by the module's standing convention: session
# startup must never be bricked by audit bookkeeping, so nothing raises.
_DEV_PENDING_CLOSE_MAX = 8        # bounded: never accumulate owed lines forever
_DEV_PENDING_SCAN_BYTES = 64 * 1024   # bounded tail scan for the dedupe check


def _dev_pending_close_path(root):
    return os.path.join(root, ".codearbiter", ".markers", "dev-close-pending.json")


def _overrides_log_path(root):
    return os.path.join(root, ".codearbiter", "overrides.log")


def _read_dev_pending_close(root):
    """The pending-close record as
    {"lines": [...], "marker_mtime": float|None, "dropped": int}, or None when
    there is nothing usable on disk. A record that exists but carries no
    replayable line, no marker identity and no unreported drop is reported as
    None so the caller discards it — a corrupt record must never wedge the
    mechanism shut. Never raises."""
    try:
        with open(_dev_pending_close_path(root), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        lines = [ln for ln in (data.get("lines") or [])
                 if isinstance(ln, str) and ln.strip()][:_DEV_PENDING_CLOSE_MAX]
        mtime = data.get("marker_mtime")
        mtime = float(mtime) if isinstance(mtime, (int, float)) else None
        dropped = data.get("dropped")
        # `isinstance(True, int)` is True, so booleans are excluded explicitly.
        dropped = (int(dropped) if isinstance(dropped, int)
                   and not isinstance(dropped, bool) and dropped > 0 else 0)
        if not lines and mtime is None and not dropped:
            return None
        return {"lines": lines, "marker_mtime": mtime, "dropped": dropped}
    except Exception:  # noqa: BLE001 — absent/corrupt record -> no signal
        return None


def _write_dev_pending_close(root, rec):
    """Atomically persist the pending-close record. Never raises — a write
    failure only costs the retry signal this call was trying to create, which
    is exactly the pre-#396 behavior and still must not brick startup."""
    try:
        path = _dev_pending_close_path(root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomic(path, json.dumps(rec), newline="\n")
    except Exception:  # noqa: BLE001 — must never brick session startup
        pass


def _discard_dev_pending_close(root):
    try:
        os.remove(_dev_pending_close_path(root))
    except OSError:
        pass


def _overrides_has_line(root, line):
    """True iff `line` already appears in the tail of overrides.log. Bounded to
    the last _DEV_PENDING_SCAN_BYTES — a replay always happens on the very next
    SessionStart, so the line it is looking for is at (or near) the end. An
    unreadable log answers False: re-appending a close row is a far smaller
    harm than silently dropping one.

    Read in BINARY and decoded here on purpose: a byte offset is only
    meaningful to seek() on a binary stream, and the comparison is made on the
    stripped line so the platform EOL the append produced never matters."""
    needle = line.strip()
    if not needle:
        return False
    try:
        path = _overrides_log_path(root)
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > _DEV_PENDING_SCAN_BYTES:
                f.seek(size - _DEV_PENDING_SCAN_BYTES)
            tail = f.read().decode("utf-8", "replace")
        return needle in tail
    except Exception:  # noqa: BLE001 — cannot confirm -> assume not present
        return False


def _append_override_line(root, line):
    """Append one audit line to overrides.log. True on a confirmed write."""
    try:
        with open(_overrides_log_path(root), "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except OSError:
        return False


def _dev_dropped_close_note(count, host_name=None):
    """One audit line accounting for close rows the pending-close cap had to
    discard. Deliberately NOT a `DEV: exit` row — it closes nothing; it records
    that N closes can never be written, so a reader of the append-only trail
    can attribute the unmatched entries instead of finding an unexplained gap.
    """
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f"[{ts}] | BY: session-cleanup | HOST: {host_name or 'unknown'} "
            f"| DEV: close-dropped | NOTE: {count} owed close row(s) discarded - the "
            f"pending-close cap ({_DEV_PENDING_CLOSE_MAX}) was reached while "
            f"overrides.log was unwritable; that many maintainer sessions have "
            f"no matching close row\n")


def _settle_dev_close(root, marker=None, new_line=None, host_name=None):
    """Drive the pending-close record to settlement; the single place the owed
    DEV: exit is appended and the retry state is cleared.

    `marker` is the dev-active path when one is live (its mtime becomes the
    close identity), None when there is no marker to settle. `new_line` is a
    freshly minted close line to take on, or None when this is a pure replay of
    whatever is already owed. `host_name` only attributes the cap-overflow note
    below; the close lines themselves already carry their own HOST field.
    Returns the number of close lines appended by THIS call. Never raises."""
    if (marker is None and new_line is None
            and not os.path.isfile(_dev_pending_close_path(root))):
        return 0    # nothing owed, nothing to settle — the overwhelming case
    rec = _read_dev_pending_close(root)
    owed = list(rec["lines"]) if rec else []
    prev_mtime = rec["marker_mtime"] if rec else None
    dropped = rec["dropped"] if rec else 0

    marker_mtime = None
    if marker:
        try:
            marker_mtime = os.path.getmtime(marker)
        except OSError:
            marker_mtime = None

    # Everything already in `owed` came off disk, so it MAY have reached the
    # trail before a crash and has to be dedupe-checked. Anything appended
    # below is minted in this process and cannot possibly be there yet.
    replays = len(owed)

    if new_line is not None:
        # Already closed THIS marker (the append landed, only the removal
        # failed) -> do not mint a second row for it; just retry the cleanup.
        already_closed = (rec is not None and prev_mtime is not None
                          and marker_mtime is not None
                          and prev_mtime == marker_mtime)
        if not already_closed:
            owed.append(new_line)
    if len(owed) > _DEV_PENDING_CLOSE_MAX:
        # Bounded, but never SILENT. A permanently-unwritable overrides.log
        # would otherwise accumulate owed lines forever, so the oldest are
        # discarded — and counted, so the loss is itself auditable rather than
        # reintroducing exactly the unmatched `DEV: enter` this record exists
        # to prevent.
        overflow = len(owed) - _DEV_PENDING_CLOSE_MAX
        dropped += overflow
        owed = owed[-_DEV_PENDING_CLOSE_MAX:]
        replays = max(0, replays - overflow)   # the discards come off the front

    if owed or dropped or marker_mtime is not None:
        # Write-ahead: the obligation is durable BEFORE the append is tried.
        _write_dev_pending_close(root, {"lines": owed,
                                        "marker_mtime": marker_mtime,
                                        "dropped": dropped})

    # The overflow note goes in FIRST — the rows it accounts for are older than
    # everything still owed. It is minted fresh each attempt, so it is not
    # deduped by the tail scan; a crash between this append and the write-back
    # below can repeat it once, which is the same "a duplicate beats a loss"
    # trade the close rows themselves make.
    if dropped and _append_override_line(root, _dev_dropped_close_note(dropped, host_name)):
        dropped = 0

    appended = 0
    remaining = []
    stalled = False
    for idx, line in enumerate(owed):
        if stalled:
            remaining.append(line)   # the log is failing — everything after
            continue                 # the first failure is still owed
        if idx < replays and _overrides_has_line(root, line):
            continue                 # crash-after-append: already in the trail
        if not _append_override_line(root, line):
            stalled = True
            remaining.append(line)   # still owed — replay on the next session
            continue
        appended += 1

    marker_gone = True
    if marker:
        try:
            os.remove(marker)
        except OSError:
            marker_gone = not os.path.isfile(marker)

    # Keep the record ONLY while it still carries information: a line still
    # owed, an unreported cap overflow, or the identity of a marker that
    # survived its own removal (the tombstone that stops the next session
    # minting a second close for it). A marker that IS gone takes its tombstone
    # with it — a dead marker's mtime identifies nothing, and leaving it behind
    # lets an unrelated future marker collide with it and lose a real close.
    if remaining or dropped or (not marker_gone and marker_mtime is not None):
        _write_dev_pending_close(root, {"lines": remaining,
                                        "marker_mtime": (None if marker_gone
                                                         else marker_mtime),
                                        "dropped": dropped})
    else:
        _discard_dev_pending_close(root)
    return appended
