#!/usr/bin/env python3
"""codeArbiter: read-only lifecycle merge selector for an installed plugin.

CLI: --root REPO --base-ref COMMIT --current-ref COMMIT --merge-method
Success emits exactly merge or squash; every unavailable proof fails closed.
"""

import argparse
import sys

from _adrlifecyclegit import GitPrerequisiteError, merge_method


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--current-ref", required=True)
    parser.add_argument("--merge-method", required=True, action="store_true")
    args = parser.parse_args(argv)
    try:
        errors, method = merge_method(args.root, args.base_ref, args.current_ref)
    except (GitPrerequisiteError, OSError, RuntimeError, ValueError) as exc:
        errors, method = ["could not verify lifecycle refs: %s" % exc], None
    if errors:
        for error in errors:
            print("::error::" + error, file=sys.stderr)
        return 1
    print(method)
    return 0


if __name__ == "__main__":
    sys.exit(main())
