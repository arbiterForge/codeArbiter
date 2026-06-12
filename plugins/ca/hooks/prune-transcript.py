#!/usr/bin/env python3
# codeArbiter — session-transcript pruner entry point.
#
# CLI today (Phase 1); a hook mode (UserPromptSubmit/PreCompact) is wired in a
# later phase. The pruning engine lives in _prunelib.py.
#
#   prune-transcript.py <path|session-id> [--execute] [--tier T]
#                       [--strategies a,b] [--keep-recent N] [--max-bytes N]
#   prune-transcript.py audit  <path>     # read-only integrity report
#   prune-transcript.py report <path>     # size / est-token breakdown only
#
# Dry-run is the default. --execute is required to write, and refuses a live
# transcript (mtime within LIVE_SECS) — the live session is only ever touched
# by the hook path. Stdlib only.

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _prunelib import (  # noqa: E402
    Config, audit, est_tokens, hook_run, load_lines, run,
)


def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def resolve(path_or_id):
    """Accept a direct path or a bare session id (resolved under ~/.claude)."""
    if os.path.isfile(path_or_id):
        return path_or_id
    hits = glob.glob(os.path.expanduser(
        f"~/.claude/projects/*/{path_or_id}.jsonl"))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"ambiguous session id (matches {len(hits)} files); pass a path")
    sys.exit(f"no such transcript: {path_or_id}")


def is_live(path, live_secs):
    try:
        return (time.time() - os.path.getmtime(path)) < live_secs
    except OSError:
        return False


def _fmt_bytes(n):
    n = float(n)
    for unit in ("B", "K", "M", "G"):
        if abs(n) < 1024 or unit == "G":
            return f"{int(n)}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def print_report(res):
    rows = res["strategies"]
    if rows:
        print(f"{'strategy':<24}{'lines':>7}{'before':>12}{'after':>12}{'est≈ saved':>12}")
        for name, r in rows.items():
            saved = est_tokens(r["bytes_before"] - r["bytes_after"])
            print(f"{name:<24}{r['lines']:>7}{r['bytes_before']:>12}"
                  f"{r['bytes_after']:>12}{saved:>12}")
    b0, b1 = res["bytes_before"], res["bytes_after"]
    pct = (100.0 * (b0 - b1) / b0) if b0 else 0.0
    print(f"\ntotal: {_fmt_bytes(b0)} -> {_fmt_bytes(b1)}  "
          f"({pct:.1f}% smaller, est≈{est_tokens(b0 - b1)} tokens freed)")
    if res["validation_errors"]:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in res["validation_errors"]:
            print("  -", e, file=sys.stderr)
    print(f"verdict: {res['verdict']}")


def cmd_audit(path):
    with open(path, "rb") as f:
        data = f.read()
    results = audit(data)
    width = max(len(lvl) for lvl, _ in results)
    for lvl, line in results:
        print(f"{lvl:<{width}}  {line}")
    return 1 if any(lvl == "FAIL" for lvl, _ in results) else 0


def cmd_report(path):
    with open(path, "rb") as f:
        data = f.read()
    lines = load_lines(data)
    n = sum(1 for ln in lines if ln.obj is not None)
    print(f"{os.path.basename(path)}: {len(data)} bytes, {len(lines)} lines "
          f"({n} JSON), est≈{est_tokens(len(data))} tokens")
    return 0


def main(argv=None):
    utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)

    # Hook mode: invoked by Claude Code with no argv and a hook JSON payload on
    # stdin. Detected by the hook_event_name field. Always exits 0.
    if not argv:
        raw = ""
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
        except Exception:  # noqa: BLE001
            raw = ""
        if raw.strip():
            try:
                payload = json.loads(raw)
            except Exception:  # noqa: BLE001
                payload = {}
            if isinstance(payload, dict) and payload.get("hook_event_name"):
                return hook_run(payload)
        print("usage: prune-transcript.py <path|session-id> [--execute] ...",
              file=sys.stderr)
        return 2

    if argv and argv[0] in ("audit", "report"):
        if len(argv) < 2:
            sys.exit(f"usage: prune-transcript.py {argv[0]} <path>")
        path = resolve(argv[1])
        return cmd_audit(path) if argv[0] == "audit" else cmd_report(path)

    ap = argparse.ArgumentParser(prog="prune-transcript.py")
    ap.add_argument("target", help="transcript path or session id")
    ap.add_argument("--execute", action="store_true",
                    help="write changes (default: dry-run)")
    ap.add_argument("--tier", default=None, choices=["gentle", "standard", "aggressive"])
    ap.add_argument("--strategies", default=None,
                    help="explicit comma-separated strategy list (overrides --tier)")
    ap.add_argument("--keep-recent", type=int, default=None)
    ap.add_argument("--max-bytes", type=int, default=None)
    args = ap.parse_args(argv)

    path = resolve(args.target)
    cfg = Config.from_env()
    if args.tier:
        cfg.tier = args.tier
    if args.strategies:
        cfg.strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    if args.keep_recent is not None:
        cfg.keep_recent = args.keep_recent
    if args.max_bytes is not None:
        cfg.max_bytes = args.max_bytes
    cfg.execute = args.execute

    if cfg.execute and is_live(path, cfg.live_secs):
        sys.exit(f"refusing --execute on a live transcript (modified < {cfg.live_secs}s ago).\n"
                 "Run against a copy, or let the hook handle the live session.")

    session = os.path.splitext(os.path.basename(path))[0]
    res = run(path, cfg, session=session)
    print_report(res)
    return 0 if not res["validation_errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
