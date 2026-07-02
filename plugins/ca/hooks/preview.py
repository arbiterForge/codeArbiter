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


if __name__ == "__main__":
    sys.exit(main())
