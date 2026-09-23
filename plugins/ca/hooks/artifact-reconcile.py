#!/usr/bin/env python3
"""Arm an exact user-workflow reconciliation request."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _artifactlib
import _reconciliationlib


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--target-id")
    parser.add_argument("--operation", choices=("task-reconcile", "scope-reconcile"))
    parser.add_argument("--target-state", choices=("PENDING", "REVIEW", "BLOCKED"))
    parser.add_argument("--reason", default="")
    parser.add_argument("--assessment")
    parser.add_argument("--cancel", action="store_true", help="cancel an armed request before its mutation attempt")
    parser.add_argument("--cancel-orphan", action="store_true", help="cancel a pending request whose prompt route was never registered")
    parser.add_argument("--recover", action="store_true", help="replay an in-flight mutation before clearing its marker")
    parser.add_argument("--prompt", help="exact armed prompt required for --cancel")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve(strict=True)
    if args.cancel_orphan:
        if args.cancel or args.recover or args.prompt or args.target_id or args.operation or args.target_state or args.assessment:
            parser.error("--cancel-orphan excludes arming and exact-prompt cancellation fields")
        print(json.dumps(_reconciliationlib.cancel_orphaned_reconciliation(root, args.artifact_id), sort_keys=True))
        return 0
    if args.cancel:
        if args.recover or args.prompt is None or args.target_id or args.operation or args.target_state or args.assessment:
            parser.error("--cancel requires --prompt and excludes arming fields")
        print(json.dumps(_reconciliationlib.cancel_reconciliation(root, args.artifact_id, args.prompt), sort_keys=True))
        return 0
    if args.recover:
        if args.prompt or args.target_id or args.operation or args.target_state or args.assessment:
            parser.error("--recover excludes arming and cancellation fields")
        client = _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))
        print(json.dumps(_reconciliationlib.recover_reconciliation(root, client, args.artifact_id), sort_keys=True))
        return 0
    if not args.target_id or not args.operation or not args.assessment or args.prompt is not None:
        parser.error("arming requires --target-id, --operation, and --assessment, without --prompt")
    client = _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))
    print(json.dumps(_reconciliationlib.arm_reconciliation(
        root, client, args.artifact_id, args.target_id, args.operation,
        target_state=args.target_state, reason=args.reason, assessment=args.assessment,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
