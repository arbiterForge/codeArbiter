#!/usr/bin/env python3
"""Private one-reply sprint approval adapter; no public registration.

The existing host hook records an actual reply. The native engine validates
both frozen definitions and commits their approvals in one journal transaction.
A retained submission can resume after interruption without another user reply;
merely arming a request is never approval or delegation.
"""
from __future__ import annotations

import hashlib
from functools import wraps
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

import _approvallib as approval
import _artifactlib
import _artifactauthoritylib
import _artifactpromptlib
import _replylib

FORMAT = "codearbiter.pending-user-approval/0.2.0"
SUBMISSION_FORMAT = "codearbiter.sprint-submission/0.1.0"
IDENTITY_KEYS = {"artifact_id", "kind", "revision", "model_sha256", "normative_sha256"}
PAIR_KEYS = {"format", "spec", "plan", "approved_plan_normative_sha256", "scope_sha256", "delegate_methods"}


def _hash(value: Any) -> str:
    return hashlib.sha256(approval._canonical(value)).hexdigest()


def _digest(value: Any) -> bool:
    return isinstance(value, str) and approval.SHA256_RE.fullmatch(value) is not None


def _serialized(function):
    """Reuse the existing private OS lock; no lock file enters the input snapshot."""
    @wraps(function)
    def run(root, *args, **kwargs):
        import _prerequisitelib
        root = _artifactlib._trusted_directory(root, "UNSAFE_ROOT")
        try:
            # One pending approval marker is shared by all pairs in this root.
            with _prerequisitelib._pending_transition_lock(root, "sprint-pair-approval"):
                return function(root, *args, **kwargs)
        except _prerequisitelib.PrerequisiteError as exc:
            raise approval.ApprovalError("APPROVAL_BUSY", "another session is completing this repository's paired approval") from exc
    return run


def validate_pending(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"format", "artifact_id", "kind", "pair", "spec_context", "plan_context", "prompt_sha256", "token_sha256", "request_key"}
    if set(value) != expected or value.get("format") != FORMAT or value.get("kind") != "sprint-pair":
        raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "paired pending shape is invalid")
    pair = value.get("pair")
    if not isinstance(pair, dict) or set(pair) != PAIR_KEYS or pair.get("format") != "codearbiter.sprint-pair/0.1.0" or type(pair.get("delegate_methods")) is not bool:
        raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "paired scope is malformed")
    for name in ("spec", "plan"):
        identity = pair.get(name)
        if (not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS
                or identity.get("kind") != name or not isinstance(identity.get("artifact_id"), str)
                or not identity["artifact_id"] or type(identity.get("revision")) is not int
                or identity["revision"] < 1
                or not all(_digest(identity.get(k)) for k in ("model_sha256", "normative_sha256"))):
            raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "paired identity is malformed")
        context = value.get(name + "_context")
        if (not isinstance(context, dict) or set(context) != {"context_ref", "context_sha256", "subject"}
                or not _digest(context.get("context_sha256"))
                or context.get("context_ref") != ".codearbiter/.artifacts/evidence-contexts/" + context["context_sha256"] + ".json"):
            raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "context locator is malformed")
        expected_norm = identity["normative_sha256"] if name == "spec" else pair["approved_plan_normative_sha256"]
        if context.get("subject") != {"artifact_id": identity["artifact_id"], "record_id": identity["artifact_id"], "normative_sha256": expected_norm}:
            raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "context belongs to a different pair")
    if (value.get("artifact_id") != pair["plan"]["artifact_id"]
            or not all(_digest(value.get(k)) for k in ("prompt_sha256", "token_sha256", "request_key"))
            or not all(_digest(pair.get(k)) for k in ("approved_plan_normative_sha256", "scope_sha256"))
            or value["request_key"] != _hash({"pair": pair, "prompt_sha256": value["prompt_sha256"]})):
        raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "paired request identity is invalid")
    return value


def _read(root: Path, relative: Path, limit: int = 65536) -> dict[str, Any]:
    parent = approval._safe_directory(root, relative.parent, create=False)
    fd = _artifactlib._open_pinned_regular(parent / relative.name)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "record is not bounded regular data")
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "record exceeds its bound")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    value = _artifactlib._decode(raw)
    if not isinstance(value, dict):
        raise approval.ApprovalError("INVALID_PENDING_APPROVAL", "record must be an object")
    return value


@_serialized
def arm(root: str | Path, client: Any, spec_id: str, plan_id: str, *, delegate_methods: bool = False, token: str | None = None) -> dict[str, Any]:
    root = _artifactlib._trusted_directory(root, "UNSAFE_ROOT")
    if type(delegate_methods) is not bool:
        raise approval.ApprovalError("INVALID_DELEGATION", "delegation must be an explicit boolean")
    token = token or secrets.token_urlsafe(24)
    if not approval.TOKEN_RE.fullmatch(token):
        raise approval.ApprovalError("INVALID_TOKEN", "approval token has an invalid shape")
    mode = "delegate-methods" if delegate_methods else "approve-only"
    reply = f"approve-sprint {spec_id} {plan_id} {mode} {token}"
    ph = hashlib.sha256(reply.encode("utf-8")).hexdigest()
    context = client.call("sprint-approval-context", {"artifact_id": plan_id, "spec_id": spec_id, "delegate_methods": delegate_methods, "prompt_sha256": ph})
    pending = {"format": FORMAT, "artifact_id": plan_id, "kind": "sprint-pair", "pair": context["pair"], "spec_context": context["spec_context"], "plan_context": context["plan_context"], "prompt_sha256": ph, "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest()}
    pending["request_key"] = _hash({"pair": pending["pair"], "prompt_sha256": ph})
    validate_pending(pending)
    try:
        approval._write_new(root, approval.PENDING, approval._canonical(pending))
    except FileExistsError as exc:
        raise approval.ApprovalError("PENDING_APPROVAL", "resolve the existing approval request first") from exc
    try:
        _artifactpromptlib.register(root, "approval", plan_id, reply)
    except _artifactpromptlib.PromptRouteError:
        (root / approval.PENDING).unlink()
        raise
    code = _replylib.offer_code(root, "approval", plan_id, reply, names=[spec_id, plan_id],
                                short_prefix=["approve-sprint", "delegate" if delegate_methods else "approve-only"])
    return {"spec_artifact_id": spec_id, "artifact_id": plan_id, "pair": pending["pair"], "reply": reply, **code, "delegation": context.get("scope"), "approved": False}


def _submission_path(pending: dict[str, Any]) -> Path:
    return approval.PENDING.parent / ("sprint-submission-" + pending["request_key"] + ".json")


def _base_request(pending: dict[str, Any]) -> dict[str, Any]:
    pair = pending["pair"]
    return {"artifact_id": pair["plan"]["artifact_id"], "spec_id": pair["spec"]["artifact_id"], "operation_id": "sprint-approval-" + pending["request_key"][:32], "expected": {k: pair["plan"][k] for k in ("revision", "model_sha256")}, "spec_expected": {k: pair["spec"][k] for k in ("revision", "model_sha256")}}


def _submission(root: Path, pending: dict[str, Any]) -> dict[str, Any] | None:
    try:
        value = _read(root, _submission_path(pending))
    except FileNotFoundError:
        return None
    if set(value) != {"format", "request_key", "request"} or value.get("format") != SUBMISSION_FORMAT or value.get("request_key") != pending["request_key"]:
        raise approval.ApprovalError("INVALID_SUBMISSION", "submission belongs to a different armed pair")
    request = value.get("request")
    base = _base_request(pending)
    if not isinstance(request, dict) or set(request) != set(base) | {"spec_source", "plan_source"} or any(request.get(k) != v for k, v in base.items()):
        raise approval.ApprovalError("INVALID_SUBMISSION", "submission changed its frozen transaction")
    for key in ("spec_source", "plan_source"):
        source = request[key]
        if (not isinstance(source, dict) or set(source) != {"source_ref", "source_sha256"}
                or not _digest(source.get("source_sha256"))
                or source.get("source_ref") != ".codearbiter/.artifacts/authority-sources/" + source["source_sha256"] + ".json"):
            raise approval.ApprovalError("INVALID_SUBMISSION", "submission source locator is invalid")
    return request


def _source(root: Path, pending: dict[str, Any], name: str, prompt: str, host: str, session_id: str, seam: str = "UserPromptSubmit") -> dict[str, str]:
    locator = pending[name + "_context"]
    context = _read(root, Path(locator["context_ref"]))
    if (_hash(context) != locator["context_sha256"] or context.get("subject") != locator["subject"]
            or context.get("prompt_sha256") != pending["prompt_sha256"]
            or context.get("record") != {"sprint_pair": pending["pair"]}):
        raise approval.ApprovalError("INVALID_AUTHORITY_SOURCE", "the armed engine context changed")
    payload = {"sprint_pair": pending["pair"]}
    producer = {"host": host, "session_id": session_id, "prompt_sha256": pending["prompt_sha256"]}
    observed = {"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": context["subject"], "context_ref": locator["context_ref"], "context_sha256": locator["context_sha256"], "payload_sha256": _hash(payload), "producer_profile": "host-user-pair/0.1.0", "producer_run_id": f"{host}:{session_id}", "producer_result": producer, "producer_result_sha256": _hash(producer)}
    oh = _hash(observed)
    observation_ref = Path(".codearbiter/.artifacts/observations") / f"{oh}.json"
    _artifactauthoritylib._publish_immutable(root, observation_ref, approval._canonical(observed))
    event = {"format": "codearbiter.workflow-event/0.2.0", "kind": "approval", "authority_kind": "user_workflow", "subject": context["subject"], "actor": "interactive repository user", "origin": f"{host}:{seam}:{session_id}", "verdict": "approved", "payload": payload, "source_text": prompt, "observation_ref": observation_ref.as_posix(), "observation_sha256": oh}
    eh = _hash(event)
    source_ref = Path(".codearbiter/.artifacts/authority-sources") / f"{eh}.json"
    _artifactauthoritylib._publish_immutable(root, source_ref, approval._canonical(event))
    return {"source_ref": source_ref.as_posix(), "source_sha256": eh}


def _execute(root: Path, client: Any, pending: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    try:
        result = client.call("sprint-approve", request)
    except _artifactlib.ArtifactError as exc:
        if exc.code != "RECOVERY_REQUIRED":
            raise
        # Complete only the exact previously observed submission. A different
        # pending transaction is not a reason to recover an unrelated operation.
        client.call("recover", {"operation_id": request["operation_id"], "mode": "complete"})
        result = client.call("sprint-approve", request)
    if (result.get("authority_kind") != "user_workflow"
            or result.get("spec", {}).get("artifact_id") != request["spec_id"]
            or result.get("plan", {}).get("artifact_id") != request["artifact_id"]
            or not isinstance(result.get("receipt"), str)):
        raise approval.ApprovalError("INVALID_RECEIPT", "transaction returned an incomplete paired receipt")
    # Remove the arm before the retained submission: a crash here must not
    # leave an armed request whose only observed reply has already been erased.
    if approval._load_pending(root) != pending:
        raise approval.ApprovalError("PENDING_APPROVAL_MISMATCH", "pending pair changed during completion")
    _artifactpromptlib.unregister(root, "approval", pending["artifact_id"])
    (root / approval.PENDING).unlink()
    (root / _submission_path(pending)).unlink(missing_ok=True)
    return {"matched": True, "approved": True, "artifact_id": request["artifact_id"], "spec_artifact_id": request["spec_id"], "receipt": result["receipt"], "spec_receipt": result.get("spec_receipt"), "grant_receipt": result.get("grant_receipt"), "operation_id": request["operation_id"]}


@_serialized
def consume(root: Path, client: Any, pending: dict[str, Any], prompt: str, *, host: str, session_id: str, seam: str = "UserPromptSubmit") -> dict[str, Any]:
    if seam not in {"UserPromptSubmit", "AskUserQuestion"}:
        raise approval.ApprovalError("INVALID_HOST_CONTEXT", "approval seam is unsupported")
    validate_pending(pending)
    if approval._load_pending(root) != pending:
        return {"matched": False, "approved": False}
    parts = prompt.split(" ")
    pair = pending["pair"]
    mode = "delegate-methods" if pair["delegate_methods"] else "approve-only"
    if len(parts) != 5 or parts[:4] != ["approve-sprint", pair["spec"]["artifact_id"], pair["plan"]["artifact_id"], mode]:
        return {"matched": False, "approved": False}
    if (not approval.TOKEN_RE.fullmatch(parts[4])
            or not secrets.compare_digest(hashlib.sha256(parts[4].encode("ascii")).hexdigest(), pending["token_sha256"])
            or not secrets.compare_digest(hashlib.sha256(prompt.encode("utf-8")).hexdigest(), pending["prompt_sha256"])):
        return {"matched": False, "approved": False}
    if not approval.HOST_RE.fullmatch(host) or not approval.SESSION_RE.fullmatch(session_id):
        raise approval.ApprovalError("INVALID_HOST_CONTEXT", "host approval context is malformed")
    request = _submission(root, pending)
    if request is None:
        for name in ("spec", "plan"):
            current = approval._identity(client, pair[name]["artifact_id"])
            if any(current.get(k) != v for k, v in pair[name].items()):
                raise approval.ApprovalError("STALE_APPROVAL", "a paired artifact changed after review was requested")
        request = _base_request(pending)
        request["spec_source"] = _source(root, pending, "spec", prompt, host, session_id, seam)
        request["plan_source"] = _source(root, pending, "plan", prompt, host, session_id, seam)
        record = {"format": SUBMISSION_FORMAT, "request_key": pending["request_key"], "request": request}
        try:
            approval._write_new(root, _submission_path(pending), approval._canonical(record))
        except FileExistsError:
            # A concurrent genuine observer wins once. Replay its original
            # sources rather than substituting a later session's metadata.
            request = _submission(root, pending)
            if request is None:
                raise approval.ApprovalError("INVALID_SUBMISSION", "concurrent submission disappeared")
    return _execute(root, client, pending, request)


@_serialized
def resume(root: str | Path, client: Any, plan_id: str) -> dict[str, Any]:
    root = _artifactlib._trusted_directory(root, "UNSAFE_ROOT")
    pending = approval._load_pending(root)
    if pending is None or pending.get("format") != FORMAT or pending["artifact_id"] != plan_id:
        raise approval.ApprovalError("NO_PENDING_APPROVAL", "no matching paired approval is pending")
    request = _submission(root, pending)
    if request is None:
        raise approval.ApprovalError("NO_OBSERVED_APPROVAL", "arming alone is not a user reply; there is nothing to resume")
    try:
        return _execute(root, client, pending, request)
    except _artifactlib.ArtifactError as exc:
        if exc.code not in {"REVISION_CONFLICT", "OPERATION_ROLLED_BACK"}:
            raise
        # The engine checks journal replay before CAS. Only these closed-set
        # outcomes establish that this exact old mutation did not commit.
        if approval._load_pending(root) != pending:
            raise approval.ApprovalError("PENDING_APPROVAL_MISMATCH", "pending request changed during failed-transaction recovery") from exc
        _artifactpromptlib.unregister(root, "approval", pending["artifact_id"])
        (root / approval.PENDING).unlink()
        (root / _submission_path(pending)).unlink(missing_ok=True)
        return {"matched": True, "approved": False, "artifact_id": plan_id,
                "operation_id": request["operation_id"], "diagnostic": exc.code,
                "reapproval_required": True}


@_serialized
def cancel(root: Path, pending: dict[str, Any]) -> dict[str, Any]:
    if approval._load_pending(root) != pending:
        raise approval.ApprovalError("PENDING_APPROVAL_MISMATCH", "pending pair changed before cancellation")
    if _submission(root, pending) is not None:
        raise approval.ApprovalError("SUBMITTED_APPROVAL", "recover the observed transaction before cancelling its pending state")
    _artifactpromptlib.unregister(root, "approval", pending["artifact_id"])
    (root / approval.PENDING).unlink()
    return {"artifact_id": pending["artifact_id"], "cancelled": True}


def apply_decision(client: Any, request_file: str | Path) -> dict[str, Any]:
    """Read a bounded inert request; only the native closed producer grants authority."""
    path = Path(request_file)
    fd = _artifactlib._open_pinned_regular(path)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise approval.ApprovalError("INVALID_SMARTS", "decision request must be bounded regular data")
        data = os.read(fd, 65537)
        if len(data) > 65536:
            raise approval.ApprovalError("INVALID_SMARTS", "decision request exceeds the context budget")
    finally:
        os.close(fd)
    request = _artifactlib._decode(data)
    if not isinstance(request, dict):
        raise approval.ApprovalError("INVALID_SMARTS", "decision request must be a JSON object")
    return client.call("smarts-apply", request)
