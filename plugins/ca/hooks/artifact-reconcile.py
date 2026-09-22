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
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--operation", required=True, choices=("task-reconcile", "scope-reconcile"))
    parser.add_argument("--target-state", choices=("PENDING", "REVIEW", "BLOCKED"))
    parser.add_argument("--reason", default="")
    parser.add_argument("--assessment", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve(strict=True)
    client = _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))
    print(json.dumps(_reconciliationlib.arm_reconciliation(
        root, client, args.artifact_id, args.target_id, args.operation,
        target_state=args.target_state, reason=args.reason, assessment=args.assessment,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
