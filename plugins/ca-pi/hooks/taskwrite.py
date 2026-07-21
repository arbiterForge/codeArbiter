#!/usr/bin/env python3
# codeArbiter — the sanctioned task-board mutator behind /ca:task (resolves D-1).
#
# The ONLY blessed way to write .codearbiter/open-tasks.md: add a queued task,
# start one (flip to [~] + stamp the date, minting a dotted ID on pick-up), or
# mark an in-progress task done. All board LOGIC is the pure text->text transforms in
# _taskboardlib; this is the thin I/O wrapper (read board -> transform -> write),
# the same shape as doctor.py / security-pass.py.
#
# Invoked by skill/command prose as:
#   python3 "<plugin>/hooks/taskwrite.py" <verb> ... || python "<plugin>/hooks/taskwrite.py" ...
#
# Verbs:
#   add  "<desc>" [--from ORIGIN] [--id GROUP.TYPE] [--boundaries a,b] [--section "## In-flight"]
#   start <ID-or-"title"> [--as GROUP.TYPE] [--date YYYY-MM-DD]
#   done  <ID-or-"title"> [--date YYYY-MM-DD]
#
# Rerun-safe: start/done are no-ops on an already-matching state; a missing target
# is reported, never a partial write.

import argparse
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _taskboardlib as tb  # noqa: E402
from _hooklib import (  # noqa: E402
    acquire_lock, project_root, release_lock, set_host, utf8_stdio,
)

# reliability-007 (#190): project_root() is now _hooklib.project_root —
# imported above, not a local copy. The prior local copy ran `git rev-parse
# --show-toplevel` from the hook's own cwd and fell back to os.getcwd(),
# skipping the CLAUDE_PROJECT_DIR-first read _hooklib.project_root() exists
# for; taskwrite mutates .codearbiter/open-tasks.md, so a wrong root silently
# wrote into the wrong repository's board.
#
# #271 C-2/C-3 — lock + re-read-under-lock CAS (spec D-4). taskwrite is the
# only *programmatic* board mutator, but it is NOT the only writer: the
# harvest/decompose paths mutate open-tasks.md directly via the host's own
# Edit/Write tool and will never take this lock (ADR-0008 tolerates that
# out-of-band path deliberately). A lock alone would therefore still let an
# interleaved external Edit get silently overwritten by a stale in-memory
# snapshot, AND would still let two lock-serialized taskwrite calls mint the
# SAME dotted id if each computed next_seq() against the text it opened with
# rather than the text current at write time. Taking the lock and THEN
# reading the board — re-running the pure transform against that fresh read —
# fixes both: an interleaved external edit is preserved (detected-loss instead
# of silent clobber), and next_seq() always runs against current text.
#
# Fail-soft choice: _ledgerlib's convention is to silently no-op when the lock
# handle is None (a statusline render is disposable — nobody is worse off if
# ONE render skips the ledger write). A board mutation is not disposable: it
# is the single user-visible effect of the whole `taskwrite` invocation, and
# /ca:task has no other way to report "your task was recorded." Silently
# proceeding unlocked on contention would silently reintroduce the exact race
# this fix exists to close (two writers both read-modify-write with no
# serialization at all). So on a None lock handle, taskwrite refuses to write
# and exits nonzero with a clear stderr message — the caller (a skill/command)
# sees a failed exit code and can retry, rather than a false "added"/"marked"
# success hiding a lost or colliding write.


def _date(s):
    """Parse a YYYY-MM-DD date, today when absent, or None when malformed."""
    if not s:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_gid(gid, option="--id"):
    """Split a ``GROUP.TYPE`` value, or None with an error message on a bad
    spelling. Pure — no I/O — so it can run before OR after the lock is held."""
    parts = gid.split(".")
    if (len(parts) != 2 or not all(parts)
            or not tb.validate_id(f"{gid}.0000")):
        return None, None, (f"bad {option} '{gid}' (expected GROUP.TYPE, e.g. 'mvp1.store'; "
                             f"the 4-digit seq is minted automatically)")
    return parts[0], parts[1], None


def _apply(args, text):
    """Pure text -> (new_text, action) | (None, error_msg) transform against
    the board text the caller hands in. Deliberately takes NO lock and does NO
    I/O itself — the caller (main()) re-runs this against a FRESH read taken
    INSIDE the lock (#271 C-3/D-4), so next_seq()'s duplicate-id mint and any
    interleaved external Edit are both resolved against current text, never a
    stale snapshot."""
    if args.verb == "add":
        boundaries = ([b.strip() for b in args.boundaries.split(",")]
                      if args.boundaries is not None else None)
        err = tb.add_error(desc=args.desc, origin=args.origin,
                           boundaries=boundaries, section=args.section)
        if err:
            return None, err
        group = typ = None
        if args.gid is not None:
            group, typ, err = _parse_gid(args.gid)
            if err:
                return None, err
        new = tb.add_entry(text, desc=args.desc, origin=args.origin, group=group,
                           type=typ, boundaries=boundaries, section=args.section)
        return new, f"added queued task: {args.desc}"

    # start / done
    state = "in_progress" if args.verb == "start" else "done"
    day = _date(args.date)
    if day is None:
        return None, f"bad --date '{args.date}' (expected YYYY-MM-DD)"
    assign = getattr(args, "assign", None)
    if assign is not None:
        _, _, err = _parse_gid(assign, option="--as")
        if err:
            return None, err
    transition_error = tb.transition_error(text, args.target, state)
    if transition_error:
        return None, transition_error
    new = tb.set_state(text, args.target, state, day, assign=assign)
    if new == text:
        return None, f"no change: '{args.target}' not found or already {state}"
    return new, f"marked {state}: {args.target}"


def main(argv=None):
    utf8_stdio()
    p = argparse.ArgumentParser(prog="taskwrite", add_help=True)
    sub = p.add_subparsers(dest="verb", required=True)

    pa = sub.add_parser("add")
    pa.add_argument("desc")
    pa.add_argument("--from", dest="origin", default=None)
    pa.add_argument("--id", dest="gid", default=None, help="GROUP.TYPE to mint a dotted ID")
    pa.add_argument("--boundaries", default=None)
    pa.add_argument("--section", default="## In-flight")

    ps = sub.add_parser("start")
    ps.add_argument("target")
    ps.add_argument("--as", dest="assign", default=None, help="GROUP.TYPE to mint on pick-up")
    ps.add_argument("--date", default=None)

    pd = sub.add_parser("done")
    pd.add_argument("target")
    pd.add_argument("--date", default=None)

    args = p.parse_args(argv)

    root = project_root()
    board_path = os.path.join(root, ".codearbiter", "open-tasks.md")

    # An uninitialized repo (no board at all) is a static precondition, not
    # part of the race this fix closes — check it BEFORE touching the lock so
    # a run against an uninitialized repo creates no side effect (no
    # .codearbiter/ dir, no lock sidecar file), exactly as before #271.
    if not os.path.isfile(board_path):
        print(f"no board at {board_path} — is this an initialized repo?", file=sys.stderr)
        return 1

    # #271 C-3 (spec D-4): take the lock FIRST, THEN read the board — everything
    # from here to the write is inside the critical section, so the read this
    # transaction acts on is guaranteed fresh relative to any other
    # lock-taking writer. Fail-soft nuance: unlike _ledgerlib's disposable
    # statusline write, a board mutation must never be silently dropped on
    # contention — refuse and exit nonzero instead (see module docstring).
    lock = acquire_lock(board_path)
    if lock is None:
        print(f"could not acquire the task-board lock ({board_path}.lock) — "
              f"another writer holds it; no changes were written, retry the "
              f"{args.verb}", file=sys.stderr)
        return 1
    try:
        text = tb.read_board(board_path)
        if text is None:
            print(f"no board at {board_path} — is this an initialized repo?", file=sys.stderr)
            return 1

        new, action_or_err = _apply(args, text)
        if new is None:
            print(action_or_err, file=sys.stderr)
            return 1
        action = action_or_err

        # Atomic write: write to a sibling temp file, then os.replace() into
        # place. os.replace() is atomic on POSIX and a same-volume rename on
        # Windows, so a crash between open() and f.write() never leaves the
        # board truncated.
        board_dir = os.path.dirname(board_path)
        fd, tmp_path = tempfile.mkstemp(dir=board_dir, suffix=".tmp", prefix="open-tasks.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
            os.replace(tmp_path, board_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
    finally:
        release_lock(lock)
    print(action)
    return 0


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Delegates to main(argv) and returns its exit code,
    exactly as the old `sys.exit(main())` guard propagated it.

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    set_host(host)
    return main(argv)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
