#!/usr/bin/env python3
# codeArbiter — thin entry point for the pr-babysitter config resolver
# (architecture-006/#179).
#
# Wraps _babysitlib.main (the CLI shim over babysit_config) so /ca:pr and
# /ca:watch invoke a thin, non-underscore entry hook instead of running the
# underscore library itself as a script. Mirrors doctor.py / taskwrite.py:
# entry point stays thin, all resolution logic lives in _babysitlib.
#
# Invoked by command prose as:
#   python3 "<plugin>/hooks/babysit.py" --root "<dir>"
#   || python "<plugin>/hooks/babysit.py" --root "<dir>"
#
# Prints one JSON line, e.g. {"enabled": true, "on_red": "propose"}. Fail-safe:
# _babysitlib.main() itself never raises past its own try/except (any resolver
# error degrades to the OFF default) — this wrapper adds no additional risk.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _babysitlib  # noqa: E402


def main(argv=None):
    return _babysitlib.main(argv)


if __name__ == "__main__":
    sys.exit(main())
