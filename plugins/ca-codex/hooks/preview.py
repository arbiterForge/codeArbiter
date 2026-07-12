#!/usr/bin/env python3
# codeArbiter — thin entry point for /ca:preview (architecture-006/#179).
#
# Wraps _previewlib.collect_diff / scan_secrets and prints the JSON-serialized
# form command prose needs, so the field-access/serialization step (reaching
# into ChangedFile.kinds and SecretFinding._asdict()) is import-covered
# (py_compile + unit tests) instead of living as inline `python -c`
# multi-statement blocks coupled to the lib's namedtuple internals. Mirrors
# doctor.py / taskwrite.py: entry point stays thin, all logic lives in
# _previewlib.
#
# Invoked by commands/preview.md as:
#   python3 "<plugin>/hooks/preview.py" diff    || python "<plugin>/hooks/preview.py" diff
#   python3 "<plugin>/hooks/preview.py" secrets || python "<plugin>/hooks/preview.py" secrets
#
# Read-only, mirrors _previewlib's own read-only contract (git rev-parse/diff/
# ls-files and read-only file opens only): this wrapper writes nothing.

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _hooklib  # noqa: E402 — set_host DI seam (#257)
import _previewlib  # noqa: E402


def diff_json():
    """JSON-serializable form of collect_diff(): path -> sorted kind list."""
    return {p: sorted(cf.kinds) for p, cf in _previewlib.collect_diff().items()}


def secrets_json():
    """JSON-serializable form of scan_secrets(): list of finding dicts, each
    already carrying the redacted (never plaintext) snippet."""
    return [f._asdict() for f in _previewlib.scan_secrets()]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="preview", add_help=True)
    parser.add_argument("mode", choices=("diff", "secrets"))
    args = parser.parse_args(argv)

    result = diff_json() if args.mode == "diff" else secrets_json()
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
    _hooklib.set_host(host)
    return main(argv)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
