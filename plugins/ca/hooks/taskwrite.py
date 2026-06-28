#!/usr/bin/env python3
# codeArbiter — the sanctioned task-board mutator behind /ca:task (resolves D-1).
#
# The ONLY blessed way to write .codearbiter/open-tasks.md: add a queued task,
# start one (flip to [~] + stamp the date, minting a dotted ID on pick-up), or
# mark one done. All board LOGIC is the pure text->text transforms in
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
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _taskboardlib as tb  # noqa: E402
from _hooklib import utf8_stdio  # noqa: E402


def project_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        top = out.stdout.strip()
        if top:
            return top
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def _date(s):
    """Parse a YYYY-MM-DD date, today when absent, or None when malformed."""
    if not s:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


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
    text = tb.read_board(board_path)
    if text is None:
        print(f"no board at {board_path} — is this an initialized repo?", file=sys.stderr)
        return 1

    if args.verb == "add":
        group = typ = None
        if args.gid:
            parts = args.gid.split(".")
            if len(parts) != 2 or not all(parts):
                print(f"bad --id '{args.gid}' (expected GROUP.TYPE, e.g. 'mvp1.store'; "
                      f"the 4-digit seq is minted automatically)", file=sys.stderr)
                return 1
            group, typ = parts
        boundaries = [b.strip() for b in args.boundaries.split(",")] if args.boundaries else None
        new = tb.add_entry(text, desc=args.desc, origin=args.origin, group=group,
                           type=typ, boundaries=boundaries, section=args.section)
        action = f"added queued task: {args.desc}"
    else:  # start / done
        state = "in_progress" if args.verb == "start" else "done"
        day = _date(args.date)
        if day is None:
            print(f"bad --date '{args.date}' (expected YYYY-MM-DD)", file=sys.stderr)
            return 1
        assign = getattr(args, "assign", None)
        new = tb.set_state(text, args.target, state, day, assign=assign)
        if new == text:
            print(f"no change: '{args.target}' not found or already {state}", file=sys.stderr)
            return 1
        action = f"marked {state}: {args.target}"

    # Atomic write: write to a sibling temp file, then os.replace() into place.
    # os.replace() is atomic on POSIX and a same-volume rename on Windows, so a
    # crash between open() and f.write() never leaves the board truncated.
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
    print(action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
