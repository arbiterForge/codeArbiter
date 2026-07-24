#!/usr/bin/env python3
# codeArbiter — thin entry point for /ca:metrics (architecture-006/#179).
#
# Wraps _metricslib.compute and prints its JSON-serialized result, so the
# field-access/serialization step /ca:metrics needs is import-covered
# (py_compile + unit tests) instead of living as an inline `python -c`
# multi-statement block in command prose. Mirrors doctor.py / taskwrite.py:
# entry point stays thin, all computation lives in _metricslib.
#
# Invoked by commands/metrics.md as:
#   python3 "<plugin>/hooks/metrics.py" --root "<dir>" [--window N]
#   || python "<plugin>/hooks/metrics.py" --root "<dir>" [--window N]
#
# Read-only: _metricslib.compute() never writes; this wrapper only prints its
# return value. json.dumps is called with its default ensure_ascii=True so the
# arrow glyphs (up/down/right arrows) are ASCII-escaped on the way out — this
# avoids a UnicodeEncodeError on Windows cp1252 consoles. Do NOT pass
# ensure_ascii=False here; the command prose renders the real glyphs itself
# from the parsed JSON, not from this process's raw stdout.

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _hooklib  # noqa: E402 — set_host DI seam (#257)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
import _metricslib  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="metrics", add_help=True)
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--window", type=int, default=None)
    args = parser.parse_args(argv)

    if args.window is not None:
        result = _metricslib.compute(args.root, window_size=args.window)
    else:
        result = _metricslib.compute(args.root)
    print(json.dumps(result))
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
    return _entrylib.dispatch(host, argv, main, _hooklib.set_host,
                               pass_argv=True, propagate_result=True)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
