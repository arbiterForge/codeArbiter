#!/usr/bin/env python3
"""Local work items backed by the installation-pinned native artifact engine.

This is a thin semantic front. Work identity, CAS, journaling and the HTML view
belong to the engine. A fresh repository with a legacy task board must use an
explicit adoption before native work creation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _artifactlib  # noqa: E402
import hostapi  # noqa: E402
from _hooklib import project_root, set_host, utf8_stdio  # noqa: E402


def _client(root):
    return _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))


def _selected_client(root):
    board = os.path.join(root, ".codearbiter", "open-tasks.md")
    if os.path.isfile(board):
        work_dir = os.path.join(root, ".codearbiter", "work")
        if os.path.lexists(work_dir):
            if not os.path.isdir(work_dir) or os.path.islink(work_dir):
                raise ValueError("both legacy and native work owners exist; preserve the project for selected adoption or repair")
            with os.scandir(work_dir) as entries:
                if next(entries, None) is not None:
                    raise ValueError("both legacy and native work owners exist; preserve the project for selected adoption or repair")
        import _worklib
        return _worklib.LegacyClient(root)
    return _client(root)


def _operation_id(action, work_id, expected, fields):
    raw = json.dumps([action, work_id, expected, fields], sort_keys=True,
                     ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return "work-" + hashlib.sha256(raw).hexdigest()[:40]


def _parser():
    parser = argparse.ArgumentParser(prog="work")
    sub = parser.add_subparsers(dest="verb", required=True)
    create = sub.add_parser("create", help="Create a distinct stable local work item")
    create.add_argument("--title", required=True)
    create.add_argument("--intent", required=True)
    create.add_argument("--type", choices=("feature", "fix", "chore", "spike", "unknown"), required=True)
    create.add_argument("--spec-id")
    create.add_argument("--plan-id")
    create.add_argument("--origin", help="Stable source key; also makes uncertain creates retryable")
    create.add_argument("--operation-id", help="Stable request ID; reuse it when retrying an uncertain create (required without --origin)")
    get = sub.add_parser("get", help="Read one work item by stable ID")
    get.add_argument("work_id")
    context = sub.add_parser("context", help="Read bounded selected work and attached document context")
    context.add_argument("work_id")
    context.add_argument("--budget", type=int, default=16384)
    context.add_argument("--path", action="append", help="Select knowledge relevant to this work path")
    context.add_argument("--knowledge-ref", action="append", help="Select an exact knowledge record even without a path")
    view = sub.add_parser("view", help="Print an inert HTML overview of selected native work")
    view.add_argument("work_id")
    listing = sub.add_parser("list", help="Page through active and archived local work")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=32)
    listing.add_argument("--membership-sha256")
    listing.add_argument("--budget", type=int, default=16384)
    project_view = sub.add_parser("project-view", help="Print one bounded, derived native project work page")
    project_view.add_argument("--offset", type=int, default=0)
    project_view.add_argument("--limit", type=int, default=16)
    project_view.add_argument("--membership-sha256")
    origins = sub.add_parser("origins", help="Find exact source keys across active and archived work")
    origins.add_argument("--origin", action="append", required=True)
    sub.add_parser("provider-get", help="Read the selected native GitHub provider binding")
    configure = sub.add_parser("provider-configure", help="Save a finite native GitHub provider binding")
    configure.add_argument("--repository", required=True, help="GitHub owner/repository")
    configure.add_argument("--credential-ref", choices=("GH_TOKEN", "GITHUB_TOKEN", "CODEARBITER_GITHUB_TOKEN"), required=True)
    configure.add_argument("--timing", choices=("after_merge", "immediate"), default="after_merge")
    configure.add_argument("--operation-id", required=True)
    configure.add_argument("--expected-config-sha256")
    stage = sub.add_parser("stage-sync", help="Save a selected create-issue intent without sending it")
    stage.add_argument("work_id")
    stage.add_argument("--operation-id", required=True)
    sync = sub.add_parser("sync", help="Send one pending GitHub issue effect after its configured timing condition")
    sync.add_argument("work_id")
    sync.add_argument("--pull-number", type=int, help="Merged default-branch PR containing this pending work intent")
    reconcile = sub.add_parser("reconcile-issue", help="Read back an exact issue after an uncertain create")
    reconcile.add_argument("work_id")
    reconcile.add_argument("--number", type=int, required=True)
    for verb in ("rename", "attach", "start", "complete", "reopen", "archive"):
        command = sub.add_parser(verb)
        command.add_argument("work_id")
        command.add_argument("--operation-id", help="Stable request ID; reuse it with the same expected revision when retrying")
        command.add_argument("--expected-revision", type=int)
        command.add_argument("--expected-model-sha256")
        if verb == "rename":
            command.add_argument("--title", required=True)
        if verb == "attach":
            command.add_argument("--spec-id")
            command.add_argument("--plan-id")
    return parser


def _dispatch(args, client):
    if args.verb == "create":
        if not args.operation_id and not args.origin:
            raise ValueError("create needs --operation-id or --origin so an uncertain result can be retried without duplicating work")
        operation_id = args.operation_id or _operation_id(
            "create", args.origin, None,
            {"title": args.title, "intent": args.intent, "work_type": args.type,
             "spec_id": args.spec_id, "plan_id": args.plan_id})
        request = {"operation_id": operation_id, "title": args.title, "intent": args.intent,
                   "work_type": args.type}
        for field in ("spec_id", "plan_id", "origin"):
            if value := getattr(args, field):
                request[field] = value
        result = client.call("work-create", request)
        result["operation_id"] = operation_id
        return result
    if args.verb == "get":
        return client.call("work-get", {"work_id": args.work_id})
    if args.verb == "context":
        request = {"work_id": args.work_id, "budget": args.budget}
        if args.path:
            request["paths"] = args.path
        if args.knowledge_ref:
            request["knowledge_refs"] = args.knowledge_ref
        return client.call("work-context", request)
    if args.verb == "view":
        return client.call("work-view", {"work_id": args.work_id})
    if args.verb in ("list", "project-view"):
        request = {"offset": args.offset, "limit": args.limit}
        if args.verb == "list":
            request["budget"] = args.budget
        if args.membership_sha256:
            request["membership_sha256"] = args.membership_sha256
        return client.call("work-list" if args.verb == "list" else "project-view", request)
    if args.verb == "origins":
        return client.call("work-origins", {"origins": args.origin})
    if args.verb == "provider-get":
        return client.call("work-provider-get", {})
    if args.verb == "provider-configure":
        request = {"operation_id": args.operation_id, "repository": args.repository,
                   "credential_ref": args.credential_ref, "effect_timing": args.timing}
        if args.expected_config_sha256:
            request["expected_config_sha256"] = args.expected_config_sha256
        return client.call("work-provider-configure", request)
    if args.verb == "stage-sync":
        config = client.call("work-provider-get", {})
        current = client.call("work-get", {"work_id": args.work_id})
        return client.call("work-effect-stage", {"operation_id": args.operation_id,
            "work_id": args.work_id, "binding_generation": config["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
    if args.verb in ("sync", "reconcile-issue"):
        if getattr(client, "legacy", False):
            raise ValueError("GitHub effects require selected native work ownership")
        import _workgithub
        if args.verb == "sync":
            return _workgithub.sync(client.root, client, args.work_id, pull_number=args.pull_number)
        return _workgithub.reconcile_issue(client.root, client, args.work_id, args.number)

    if not args.operation_id:
        raise ValueError(f"{args.verb} needs --operation-id so an uncertain result can be retried without overwriting later work")
    if getattr(client, "legacy", False):
        if args.verb not in ("start", "complete", "archive"):
            raise ValueError(f"{args.verb} is not yet supported by the legacy board adapter")
        if args.expected_revision is not None:
            raise ValueError("legacy work uses an expected board SHA-256, not a native revision")
        current = client.call("work-get", {"work_id": args.work_id})
        expected = args.expected_model_sha256 or current["board_sha256"]
        return client.call("work-update", {
            "operation_id": args.operation_id, "work_id": args.work_id,
            "expected_board_sha256": expected, "action": args.verb,
        })
    supplied = (args.expected_revision is not None, args.expected_model_sha256 is not None)
    if supplied[0] != supplied[1]:
        raise ValueError("expected revision and model SHA-256 must be supplied together")
    if all(supplied):
        expected = {"revision": args.expected_revision, "model_sha256": args.expected_model_sha256}
    else:
        current = client.call("work-get", {"work_id": args.work_id})
        expected = {"revision": current["revision"], "model_sha256": current["model_sha256"]}
    fields = {"title": args.title} if args.verb == "rename" else {}
    if args.verb == "attach":
        fields = {field: value for field in ("spec_id", "plan_id")
                  if (value := getattr(args, field)) is not None}
        if not fields:
            raise ValueError("attach needs --spec-id or --plan-id")
    operation_id = args.operation_id
    result = client.call("work-update", {"operation_id": operation_id, "work_id": args.work_id,
                                         "expected": expected, "action": args.verb, **fields})
    result["operation_id"] = operation_id
    return result


def _dispatch_request(payload, client):
    """One bounded semantic request; native validation owns the work contract."""
    if type(payload) is not dict or set(payload) != {"schema", "operation", "request"}:
        raise ValueError("invalid versioned work request")
    if payload["schema"] != "codearbiter.work-request/0.1.0":
        raise ValueError("unsupported work request schema")
    operation = payload["operation"]
    if type(operation) is not str or operation not in {
        "work-create", "work-get", "work-context", "work-view", "work-list", "work-origins", "work-update", "project-view",
        "work-provider-get", "work-provider-configure", "work-effect-stage"
    }:
        raise ValueError("unsupported work operation")
    if type(payload["request"]) is not dict:
        raise ValueError("work request body must be an object")
    return client.call(operation, payload["request"])


def main(argv=None):
    utf8_stdio()
    try:
        raw_view = False
        if list(sys.argv[1:] if argv is None else argv) == ["--request", "-"]:
            raw = sys.stdin.read(65537)
            if len(raw.encode("utf-8")) > 65536:
                raise ValueError("work request exceeds 64 KiB")
            result = _dispatch_request(json.loads(raw), _selected_client(project_root()))
        else:
            args = _parser().parse_args(argv)
            result = _dispatch(args, _selected_client(project_root()))
            raw_view = args.verb in ("view", "project-view")
    except _artifactlib.ArtifactError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}))
        return 1
    except (OSError, ValueError, KeyError) as exc:
        result = {"ok": False, "error": str(exc)}
        if code := getattr(exc, "code", None):
            result["code"] = code
        print(json.dumps(result))
        return 1
    if raw_view:
        print(result["html"])
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run(host, argv=None):
    """Host-seam entry point (ADR-0011)."""
    set_host(host)
    return main(argv)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
