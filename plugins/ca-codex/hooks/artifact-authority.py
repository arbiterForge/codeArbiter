#!/usr/bin/env python3
# codeArbiter — thin internal CLI for production artifact authority.
"""Arm, execute, and publish closed authority requests; not a public command."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _artifactauthoritylib  # noqa: E402
import _artifactlib  # noqa: E402
import hostapi  # noqa: E402


def _workspace_map(values: list[str]) -> dict[str, Path]:
    result = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("workspace must be LABEL=PATH")
        label, raw = value.split("=", 1)
        if not label or not raw or label in result:
            raise argparse.ArgumentTypeError("workspace labels and paths must be unique")
        result[label] = Path(raw)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    arm = sub.add_parser("arm")
    arm.add_argument("--root", required=True)
    arm.add_argument("--artifact-id", required=True)
    arm.add_argument("--record-id", required=True)
    arm.add_argument(
        "--activity", required=True,
        choices=("verification", "spec_review", "quality_review"),
    )
    arm.add_argument("--workspace", action="append", default=[], metavar="LABEL=PATH")
    arm.add_argument(
        "--host", choices=sorted(_artifactauthoritylib.HOSTS), default=None,
        help="observing host; defaults to the host this package was built for",
    )
    arm.add_argument(
        "--reviewer-model", choices=sorted(_artifactauthoritylib.CLAUDE_REVIEWER_MODELS),
        default="opus", help="Claude reviewer model pinned into the launch envelope",
    )
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--request-id", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--root", required=True)
    publish.add_argument("--request-id", required=True)
    recover = sub.add_parser("recover")
    recover.add_argument("--root", required=True)
    recover.add_argument("--request-id", required=True)
    recover.add_argument("--disposition", required=True, choices=("failed", "abandoned"))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve(strict=True)
    client = _artifactlib.ArtifactClient(
        root, _artifactlib.helper_installation(__file__)
    )
    if args.command == "arm":
        workspaces = _workspace_map(args.workspace)
        host = args.host or hostapi.load_host().name
        if host not in _artifactauthoritylib.HOSTS:
            raise _artifactauthoritylib.AuthorityError(
                "UNSUPPORTED_HOST_SEAM", f"host {host} has no verification or review authority"
            )
        result = _artifactauthoritylib.arm_request(
            root, client, args.artifact_id, args.record_id, args.activity,
            workspace_roots=workspaces or None, host=host,
            reviewer_model=args.reviewer_model,
        )
    elif args.command == "verify":
        result = _artifactauthoritylib.run_verification(
            root, client, args.request_id,
        )
    elif args.command == "publish":
        result = _artifactauthoritylib.publish_request(root, client, args.request_id)
    else:
        result = _artifactauthoritylib.recover_request(
            root, args.request_id, args.disposition
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (_artifactauthoritylib.AuthorityError, _artifactlib.ArtifactError) as exc:
        sys.stderr.write(str(exc) + "\n")
        raise SystemExit(1)
