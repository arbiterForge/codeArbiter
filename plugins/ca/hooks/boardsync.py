#!/usr/bin/env python3
# codeArbiter — board-drift reconcile entrypoint (advisory, read-only sweep).
#
# Surfaces drift between task-board state and merged-commit references.
# Writes nothing — open-tasks.md is never opened for writing by this module.
#
# Design invariants:
#   - reconcile_report(board_text, log_text, today) -> str is pure; never raises.
#   - main(argv) is the thin I/O shell: reads board read-only via read_board(),
#     reads merged-commit text from stdin (the caller pipes `git log` output — no
#     subprocess in this module, mirroring how _standuplib stays subprocess-free),
#     then calls reconcile_report and prints the result.
#   - Stdlib only. No subprocess calls. No write paths of any kind.
#
# Public API:
#   reconcile_report(board_text, log_text, today) -> str
#   main(argv=None)

import argparse
import datetime
import os
import sys

# Handles both "run as script" and "imported from the tests/ sub-dir": ensures
# the hooks package directory is on sys.path so _taskboardlib resolves cleanly
# regardless of cwd or how Python was invoked.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _hooklib  # noqa: E402 — set_host DI seam (#257)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
import _taskboardlib as tb  # noqa: E402


def reconcile_report(board_text, log_text, today):
    """Return a human-readable advisory drift report string.

    Calls extract_task_ids(log_text), then find_board_drift against board_text,
    and formats the result: drifted tasks (id + state) and unknown ids, or a
    clean 'no drift detected' line when nothing needs attention.

    Pure — never raises. None/empty inputs degrade to a clean (empty) report.

    Drifted = task whose board state is not [x] but whose id appeared in the
    merged-commit log (work landed, board not flipped). Unknown = id in the log
    absent from the board entirely (informational only; never treated as drift).
    """
    try:
        merged_ids = tb.extract_task_ids(log_text or "")
        result = tb.find_board_drift(board_text or "", merged_ids, today)
        lines = [f"Board drift sweep — {result.observed.isoformat()}"]
        if not result.drifted and not result.unknown:
            lines.append("  no drift detected")
        else:
            if result.drifted:
                lines.append("  DRIFTED (merged but not [x]):")
                for t in result.drifted:
                    lines.append(f"    {t.id}  state={t.state}")
            if result.unknown:
                lines.append("  UNKNOWN ids (in log but not on board):")
                for uid in result.unknown:
                    lines.append(f"    {uid}")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return "Board drift sweep — error during report (input may be malformed)"


def main(argv=None):
    """Thin I/O entrypoint for the board-drift advisory sweep.

    Reads the board file read-only via _taskboardlib.read_board (never opens it
    for writing). Reads merged-commit text from stdin. Prints the advisory report
    produced by reconcile_report. Writes nothing.

    Subcommands:
      reconcile [--board PATH]   surface drift; board is never written.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="boardsync",
        description="Advisory board-drift sweep — never writes open-tasks.md.",
    )
    sub = parser.add_subparsers(dest="command")

    rec = sub.add_parser("reconcile", help="surface board drift (read-only)")
    rec.add_argument(
        "--board",
        default=".codearbiter/open-tasks.md",
        metavar="PATH",
        help="path to open-tasks.md (default: .codearbiter/open-tasks.md)",
    )

    args = parser.parse_args(argv)

    if args.command == "reconcile":
        # Defense-in-depth: honor the module's crash-safe invariant for the I/O
        # path too (read_board / stdin), not just reconcile_report — a malformed
        # --board or a stdin read error degrades to the advisory report, never a
        # traceback. (Security review 2026-06-26, LOW.)
        today = datetime.date.today()
        try:
            board_text = tb.read_board(args.board)
            log_text = sys.stdin.read()
            report = reconcile_report(board_text or "", log_text, today)
        except Exception:
            report = reconcile_report("", "", today)
        print(report)
    else:
        parser.print_help()


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main(argv) unchanged — main()'s return value
    stays discarded exactly as the old bare `main()` guard discarded it (so
    the process still exits 0 on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, _hooklib.set_host,
                               pass_argv=True, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
