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
import re
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _artifactlib  # noqa: E402
import hostapi  # noqa: E402
from _hooklib import project_root, set_host, utf8_stdio  # noqa: E402


def _client(root):
    return _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))


def _selected_client(root):
    board = os.path.join(root, ".codearbiter", "open-tasks.md")
    if os.path.lexists(board):
        info = os.lstat(board)
        reparse = getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if reparse or not stat.S_ISREG(info.st_mode):
            raise ValueError("legacy work board is not a regular file; preserve it for inspection")
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
    create.add_argument("--cycle-id", help="Optional local cycle grouping key")
    create.add_argument("--operation-id", help="Stable request ID; reuse it when retrying an uncertain create (required without --origin)")
    get = sub.add_parser("get", help="Read one work item by stable ID")
    get.add_argument("work_id")
    context = sub.add_parser("context", help="Read bounded selected work and attached document context")
    context.add_argument("work_id")
    context.add_argument("--budget", type=int, default=16384)
    context.add_argument("--legacy-offset", type=int, help="Read the next page of an adopted task's original details")
    context.add_argument("--path", action="append", help="Select knowledge relevant to this work path")
    context.add_argument("--knowledge-ref", action="append", help="Select an exact knowledge record even without a path")
    view = sub.add_parser("view", help="Print or save an inert HTML overview of selected native work")
    view.add_argument("work_id")
    view.add_argument("--save", action="store_true", help="Refresh a derived local HTML page and print its path")
    listing = sub.add_parser("list", help="Page through active and archived local work")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=32)
    listing.add_argument("--membership-sha256")
    listing.add_argument("--budget", type=int, default=16384)
    project_view = sub.add_parser("project-view", help="Print one bounded, derived native project work page")
    project_view.add_argument("--offset", type=int, default=0)
    project_view.add_argument("--limit", type=int, default=16)
    project_view.add_argument("--membership-sha256")
    cycle_view = sub.add_parser("cycle-view", help="Print a bounded, derived view of one cycle")
    cycle_view.add_argument("cycle_id")
    cycle_view.add_argument("--offset", type=int, default=0)
    cycle_view.add_argument("--limit", type=int, default=16)
    cycle_view.add_argument("--membership-sha256")
    origins = sub.add_parser("origins", help="Find exact source keys across active and archived work")
    origins.add_argument("--origin", action="append", required=True)
    sub.add_parser("adopt-preview", help="Inventory legacy board rows and preimages without changing ownership")
    adopt = sub.add_parser("adopt", help="Select one journaled cutover from the legacy board to native work")
    adopt.add_argument("--operation-id", required=True, help="Stable ID for an uncertain cutover retry")
    sub.add_parser("provider-get", help="Read the selected native GitHub provider binding")
    configure = sub.add_parser("provider-configure", help="Save a finite native GitHub provider binding")
    configure.add_argument("--repository", required=True, help="GitHub owner/repository")
    configure.add_argument("--credential-ref", choices=("GH_TOKEN", "GITHUB_TOKEN", "CODEARBITER_GITHUB_TOKEN"), required=True)
    configure.add_argument("--timing", choices=("after_merge", "immediate"), default="after_merge")
    configure.add_argument("--operation-id", required=True)
    configure.add_argument("--expected-config-sha256")
    sub.add_parser("project-get", help="Read the selected optional GitHub Project binding")
    project_discover = sub.add_parser("project-discover", help="Resolve a GitHub Projects v2 board URL to its node ID")
    project_discover.add_argument("--project-url", required=True)
    project_configure = sub.add_parser("project-configure", help="Bind one GitHub Projects v2 board to this issue provider")
    project_choice = project_configure.add_mutually_exclusive_group(required=True)
    project_choice.add_argument("--project-url", help="Canonical user or organization Projects v2 URL")
    project_choice.add_argument("--project-node-id", help="Already known GitHub Projects v2 node ID")
    project_configure.add_argument("--operation-id", required=True)
    project_configure.add_argument("--expected-config-sha256")
    project_stage = sub.add_parser("project-stage", help="Save a Project item intent for an already bound issue")
    project_stage.add_argument("work_id")
    project_stage.add_argument("--operation-id", required=True)
    project_sync = sub.add_parser("project-sync", help="Add one pending bound issue to its configured Project")
    project_sync.add_argument("work_id")
    project_reconcile = sub.add_parser("project-reconcile", help="Reconcile an uncertain Project add; retry the idempotent add if absent")
    project_reconcile.add_argument("work_id")
    project_fields = sub.add_parser("project-fields", help="Read bounded single-select fields and option IDs from the attached Project")
    project_fields.add_argument("work_id")
    field_observe = sub.add_parser("project-field-observe", help="Read one attached Project field's current option")
    field_observe.add_argument("work_id")
    field_observe.add_argument("--field-id", required=True)
    field_stage = sub.add_parser("project-field-stage", help="Read the current option and stage one selected Project option")
    field_stage.add_argument("work_id")
    field_stage.add_argument("--field-id", required=True)
    field_stage.add_argument("--option-id", required=True)
    field_stage.add_argument("--operation-id", required=True)
    field_sync = sub.add_parser("project-field-sync", help="Send one pending Project option update")
    field_sync.add_argument("work_id")
    field_reconcile = sub.add_parser("project-field-reconcile", help="Reconcile an uncertain field update; retry if its saved baseline remains")
    field_reconcile.add_argument("work_id")
    stage = sub.add_parser("stage-sync", help="Save a selected create-issue intent without sending it")
    stage.add_argument("work_id")
    stage.add_argument("--operation-id", required=True)
    stage_status = sub.add_parser("stage-status", help="Save an explicit update for a bound GitHub issue status")
    stage_status.add_argument("work_id")
    stage_status.add_argument("--state", choices=("open", "closed"), required=True)
    stage_status.add_argument("--operation-id", required=True)
    sync = sub.add_parser("sync", help="Send one pending GitHub issue effect after its configured timing condition")
    sync.add_argument("work_id")
    sync.add_argument("--pull-number", type=int, help="Merged default-branch PR containing this pending work intent")
    reconcile = sub.add_parser("reconcile-issue", help="Read back an exact issue after an uncertain create")
    reconcile.add_argument("work_id")
    reconcile.add_argument("--number", type=int, required=True)
    adopt_issue = sub.add_parser("adopt-issue", help="Bind an existing issue with this work identity marker")
    adopt_issue.add_argument("work_id")
    adopt_issue.add_argument("--number", type=int, required=True)
    adopt_issue.add_argument("--operation-id", required=True)
    reconcile_status = sub.add_parser("reconcile-status", help="Read back an uncertain issue status update without resending")
    reconcile_status.add_argument("work_id")
    reconcile_status.add_argument("--accept-remote", action="store_true", help="After inspection, retain the observed remote status as a conflict")
    observe_pr = sub.add_parser("observe-pr", help="Read a GitHub PR that changes this canonical work item and record its delivery state")
    observe_pr.add_argument("work_id")
    observe_pr.add_argument("--number", type=int, required=True)
    observe_pr.add_argument("--credential-ref", choices=("GH_TOKEN", "GITHUB_TOKEN", "CODEARBITER_GITHUB_TOKEN"), default="CODEARBITER_GITHUB_TOKEN")
    observe_pr.add_argument("--operation-id", required=True, help="Stable ID for an uncertain local record retry")
    for verb in ("rename", "attach", "start", "complete", "reopen", "archive", "set-cycle"):
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
        if verb == "set-cycle":
            cycle = command.add_mutually_exclusive_group(required=True)
            cycle.add_argument("--cycle-id")
            cycle.add_argument("--clear", action="store_true")
    return parser


def _dispatch(args, client):
    if args.verb == "create":
        if not args.operation_id and not args.origin:
            raise ValueError("create needs --operation-id or --origin so an uncertain result can be retried without duplicating work")
        operation_id = args.operation_id or _operation_id(
            "create", args.origin, None,
            {"title": args.title, "intent": args.intent, "work_type": args.type,
             "spec_id": args.spec_id, "plan_id": args.plan_id, "cycle_id": args.cycle_id})
        request = {"operation_id": operation_id, "title": args.title, "intent": args.intent,
                   "work_type": args.type}
        for field in ("spec_id", "plan_id", "origin", "cycle_id"):
            if value := getattr(args, field):
                request[field] = value
        result = client.call("work-create", request)
        result["operation_id"] = operation_id
        return result
    if args.verb == "get":
        return client.call("work-get", {"work_id": args.work_id})
    if args.verb == "context":
        request = {"work_id": args.work_id, "budget": args.budget}
        if args.legacy_offset is not None:
            request["legacy_offset"] = args.legacy_offset
        if args.path:
            request["paths"] = args.path
        if args.knowledge_ref:
            request["knowledge_refs"] = args.knowledge_ref
        return client.call("work-context", request)
    if args.verb == "view":
        return client.call("work-view", {"work_id": args.work_id})
    if args.verb in ("list", "project-view", "cycle-view"):
        request = {"offset": args.offset, "limit": args.limit}
        if args.verb == "list":
            request["budget"] = args.budget
        if args.membership_sha256:
            request["membership_sha256"] = args.membership_sha256
        if args.verb == "cycle-view":
            request["cycle_id"] = args.cycle_id
        return client.call({"list": "work-list", "project-view": "project-view", "cycle-view": "cycle-view"}[args.verb], request)
    if args.verb == "origins":
        return client.call("work-origins", {"origins": args.origin})
    if args.verb == "adopt-preview":
        if not getattr(client, "legacy", False):
            raise ValueError("adoption preview requires selected legacy board ownership")
        import _workadopt
        return _workadopt.preview(client.root)
    if args.verb == "adopt":
        import _workadopt
        return _workadopt.adopt(client.root, _client(client.root), args.operation_id,
                                replay=not getattr(client, "legacy", False))
    if args.verb == "provider-get":
        return client.call("work-provider-get", {})
    if args.verb == "provider-configure":
        request = {"operation_id": args.operation_id, "repository": args.repository,
                   "credential_ref": args.credential_ref, "effect_timing": args.timing}
        if args.expected_config_sha256:
            request["expected_config_sha256"] = args.expected_config_sha256
        return client.call("work-provider-configure", request)
    if args.verb == "project-get":
        return client.call("work-project-get", {})
    if args.verb == "project-discover":
        if getattr(client, "legacy", False):
            raise ValueError("GitHub Projects require selected native work ownership")
        import _workgithub
        return _workgithub.discover_project(client.root, client, args.project_url)
    if args.verb == "project-configure":
        project_node_id = args.project_node_id
        if args.project_url:
            if getattr(client, "legacy", False):
                raise ValueError("GitHub Projects require selected native work ownership")
            import _workgithub
            project_node_id = _workgithub.discover_project(client.root, client, args.project_url)["project_node_id"]
        request = {"operation_id": args.operation_id, "project_node_id": project_node_id}
        if args.expected_config_sha256:
            request["expected_config_sha256"] = args.expected_config_sha256
        return client.call("work-project-configure", request)
    if args.verb == "project-stage":
        config = client.call("work-project-get", {})
        current = client.call("work-get", {"work_id": args.work_id})
        return client.call("work-project-stage", {
            "operation_id": args.operation_id, "work_id": args.work_id,
            "binding_generation": config["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
    if args.verb in ("stage-sync", "stage-status"):
        config = client.call("work-provider-get", {})
        current = client.call("work-get", {"work_id": args.work_id})
        request = {"operation_id": args.operation_id,
            "work_id": args.work_id, "binding_generation": config["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}}
        if args.verb == "stage-status":
            request.update(kind="status_update", desired_state=args.state)
        return client.call("work-effect-stage", request)
    if args.verb in ("sync", "reconcile-issue", "reconcile-status", "adopt-issue", "observe-pr",
                     "project-sync", "project-reconcile", "project-fields", "project-field-observe",
                     "project-field-stage", "project-field-sync", "project-field-reconcile"):
        if getattr(client, "legacy", False):
            raise ValueError("GitHub effects require selected native work ownership")
        import _workgithub
        if args.verb == "observe-pr":
            return _workgithub.observe_pull(client.root, client, args.work_id, args.number,
                                            credential_ref=args.credential_ref,
                                            operation_id=args.operation_id)
        if args.verb == "sync":
            return _workgithub.sync(client.root, client, args.work_id, pull_number=args.pull_number)
        if args.verb == "project-sync":
            return _workgithub.sync_project(client.root, client, args.work_id)
        if args.verb == "project-reconcile":
            return _workgithub.reconcile_project(client.root, client, args.work_id)
        if args.verb == "project-fields":
            return _workgithub.project_fields(client.root, client, args.work_id)
        if args.verb == "project-field-observe":
            return _workgithub.observe_project_field(client.root, client, args.work_id, args.field_id)
        if args.verb == "project-field-stage":
            return _workgithub.stage_project_field(client.root, client, args.work_id,
                                                   args.field_id, args.option_id, args.operation_id)
        if args.verb == "project-field-sync":
            return _workgithub.sync_project_field(client.root, client, args.work_id)
        if args.verb == "project-field-reconcile":
            return _workgithub.reconcile_project_field(client.root, client, args.work_id)
        if args.verb == "reconcile-issue":
            return _workgithub.reconcile_issue(client.root, client, args.work_id, args.number)
        if args.verb == "adopt-issue":
            return _workgithub.adopt_issue(client.root, client, args.work_id, args.number,
                                           operation_id=args.operation_id)
        return _workgithub.reconcile_status(client.root, client, args.work_id,
                                            accept_remote=args.accept_remote)

    if not args.operation_id:
        raise ValueError(f"{args.verb} needs --operation-id so an uncertain result can be retried without overwriting later work")
    if getattr(client, "legacy", False):
        if args.verb == "set-cycle":
            raise ValueError("cycle grouping requires selected native work ownership")
        if args.expected_revision is not None:
            raise ValueError("legacy work uses an expected board SHA-256, not a native revision")
        current = client.call("work-get", {"work_id": args.work_id})
        expected = args.expected_model_sha256 or current["board_sha256"]
        fields = {"title": args.title} if args.verb == "rename" else {}
        if args.verb == "attach":
            fields = {field: value for field in ("spec_id", "plan_id")
                      if (value := getattr(args, field)) is not None}
            if not fields:
                raise ValueError("attach needs --spec-id or --plan-id")
        return client.call("work-update", {
            "operation_id": args.operation_id, "work_id": args.work_id,
            "expected_board_sha256": expected, "action": args.verb,
            **fields,
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
    if args.verb == "set-cycle":
        fields = {"cycle_id": None if args.clear else args.cycle_id}
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
        "work-create", "work-get", "work-context", "work-view", "work-list", "work-origins", "work-update", "project-view", "cycle-view",
        "work-provider-get", "work-provider-configure", "work-effect-stage",
        "work-project-get", "work-project-configure", "work-project-stage", "work-project-stage-field"
    }:
        raise ValueError("unsupported work operation")
    if type(payload["request"]) is not dict:
        raise ValueError("work request body must be an object")
    return client.call(operation, payload["request"])


_DERIVED_VIEW_MARKER = "<!-- codeArbiter derived work view; regenerate from canonical work with work.py view --save -->"


def _save_derived_view(root, result):
    """Materialize one replaceable snapshot without changing canonical work."""
    view_path = result["view_path"]
    if (not isinstance(view_path, str) or
            re.fullmatch(r"\.codearbiter/views/work/WORK-[A-Za-z0-9-]+\.html", view_path) is None or
            view_path != f'.codearbiter/views/work/{result["work_id"]}.html'):
        raise ValueError("native work view returned an unsafe path")
    html = result["html"]
    if not isinstance(html, str) or not html.startswith("<!doctype html>\n" + _DERIVED_VIEW_MARKER):
        raise ValueError("native work view is not a recognized derived page")
    directory = root
    for part in (".codearbiter", "views", "work"):
        directory = os.path.join(directory, part)
        if not os.path.lexists(directory):
            os.mkdir(directory)
        info = os.lstat(directory)
        if (not stat.S_ISDIR(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise ValueError(f"derived view directory is unsafe: {directory}")
    target = os.path.join(directory, os.path.basename(view_path))
    if os.path.lexists(target):
        info = os.lstat(target)
        if (not stat.S_ISREG(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise ValueError(f"derived view target is unsafe: {target}")
        with open(target, encoding="utf-8") as handle:
            if not handle.read(512).startswith("<!doctype html>\n" + _DERIVED_VIEW_MARKER):
                raise ValueError(f"derived view target has unrecognized content: {target}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=directory,
                                         prefix=".work-view-", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            handle.write(html)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return {key: result[key] for key in ("work_id", "revision", "model_sha256", "view_path", "canonical")}


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
            root = project_root()
            result = _dispatch(args, _selected_client(root))
            if args.verb == "view" and args.save:
                result = _save_derived_view(root, result)
            else:
                raw_view = args.verb in ("view", "project-view", "cycle-view")
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
