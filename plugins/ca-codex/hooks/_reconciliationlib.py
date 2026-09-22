#!/usr/bin/env python3
"""Exact-prompt user authority for task/scope reconciliation mutations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import secrets
import stat
from typing import Any

import _approvallib
import _artifactauthoritylib
import _artifactlib
import _artifactpromptlib


ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{0,127}")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{12,128}")
PENDING_DIR = Path(".codearbiter/.markers/reconciliations")
SOURCE_DIR = Path(".codearbiter/.artifacts/authority-sources")


class ReconciliationError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pending(artifact_id: str) -> Path:
    return PENDING_DIR / f"{artifact_id}.json"


def _current(client: Any, artifact_id: str, target_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    identity = client.call("identity", {"artifact_id": artifact_id})
    snapshot = client.call("snapshot", {"artifact_id": artifact_id})
    record = client.call("read", {"artifact_id": artifact_id, "symbol": target_id, "mode": "exact"})
    record = record.get("record") if isinstance(record, dict) else None
    if (
        not isinstance(identity, dict) or identity.get("artifact_id") != artifact_id
        or not isinstance(identity.get("revision"), int)
        or not isinstance(identity.get("model_sha256"), str)
        or not isinstance(identity.get("normative_sha256"), str)
        or not isinstance(snapshot, dict) or not isinstance(snapshot.get("sha256"), str)
        or not isinstance(record, dict) or record.get("id") != target_id
    ):
        raise ReconciliationError("engine reconciliation target is malformed")
    return identity, snapshot, record


def arm_reconciliation(
    root: str | Path, client: Any, artifact_id: str, target_id: str,
    operation: str, *, target_state: str | None = None, reason: str = "",
    assessment: str, token: str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    if operation not in {"task-reconcile", "scope-reconcile"}:
        raise ReconciliationError("reconciliation operation is unsupported")
    if ID_RE.fullmatch(artifact_id) is None or ID_RE.fullmatch(target_id) is None:
        raise ReconciliationError("reconciliation IDs are invalid")
    if operation == "task-reconcile" and target_state not in {"PENDING", "REVIEW", "BLOCKED"}:
        raise ReconciliationError("task reconciliation state is invalid")
    if operation == "scope-reconcile" and target_state is not None:
        raise ReconciliationError("scope reconciliation has no target state")
    if not isinstance(assessment, str) or not assessment.strip() or not isinstance(reason, str):
        raise ReconciliationError("reconciliation assessment/reason is invalid")
    token = token or secrets.token_urlsafe(24)
    if TOKEN_RE.fullmatch(token) is None:
        raise ReconciliationError("reconciliation token is invalid")
    identity, snapshot, record = _current(client, artifact_id, target_id)
    reply = (
        f"reconcile-task {artifact_id} {target_id} {target_state} {token}"
        if operation == "task-reconcile"
        else f"reconcile-scope {artifact_id} {target_id} {token}"
    )
    pending = {
        "format": "codearbiter.pending-reconciliation/0.1.0",
        "operation": operation, "artifact_id": artifact_id, "target_id": target_id,
        "target_state": target_state, "reason": reason, "assessment": assessment,
        "identity": identity, "input_sha256": snapshot["sha256"],
        "record": record, "record_sha256": _digest(_canonical(record)),
        "prompt_sha256": _digest(reply.encode()),
    }
    relative = _pending(artifact_id)
    created = False
    try:
        pending_bytes = _canonical(pending)
        _approvallib._write_new(root, relative, pending_bytes)
        created = True
        _artifactpromptlib.register(
            root, "reconciliation", artifact_id, reply,
            binding_sha256=_digest(pending_bytes),
        )
    except FileExistsError as exc:
        raise ReconciliationError("PENDING_RECONCILIATION: reconciliation is already armed") from exc
    except Exception:
        if created:
            try:
                (root / relative).unlink()
            except OSError:
                pass
        raise
    return {"artifact_id": artifact_id, "target_id": target_id, "operation": operation, "reply": reply}


def _load(root: Path, artifact_id: str) -> dict[str, Any]:
    try:
        path = root / _pending(artifact_id)
        info = path.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            raise OSError("unsafe pending reconciliation")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReconciliationError("pending reconciliation is unreadable") from exc
    expected = {
        "format", "operation", "artifact_id", "target_id", "target_state",
        "reason", "assessment", "identity", "input_sha256", "record",
        "record_sha256", "prompt_sha256",
    }
    if (
        not isinstance(value, dict) or set(value) != expected
        or value.get("format") != "codearbiter.pending-reconciliation/0.1.0"
        or value.get("artifact_id") != artifact_id
        or ID_RE.fullmatch(value.get("artifact_id", "")) is None
        or ID_RE.fullmatch(value.get("target_id", "")) is None
        or value.get("operation") not in {"task-reconcile", "scope-reconcile"}
        or not isinstance(value.get("reason"), str)
        or not isinstance(value.get("assessment"), str) or not value["assessment"].strip()
        or not isinstance(value.get("identity"), dict)
        or not isinstance(value.get("record"), dict)
        or not isinstance(value.get("input_sha256"), str)
        or not isinstance(value.get("record_sha256"), str)
        or not isinstance(value.get("prompt_sha256"), str)
    ):
        raise ReconciliationError("pending reconciliation is malformed")
    if value["operation"] == "task-reconcile":
        if value["target_state"] not in {"PENDING", "REVIEW", "BLOCKED"}:
            raise ReconciliationError("pending reconciliation is malformed")
    else:
        if value["target_state"] is not None:
            raise ReconciliationError("pending reconciliation is malformed")
    if _digest(_canonical(value["record"])) != value["record_sha256"]:
        raise ReconciliationError("pending reconciliation is malformed")
    return value


def consume_reconciliation(
    root: str | Path, client: Any, prompt: str, *, host: str, session_id: str,
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    parts = prompt.split(" ") if isinstance(prompt, str) else []
    if len(parts) not in {4, 5} or parts[0] not in {"reconcile-task", "reconcile-scope"}:
        return {"matched": False, "reconciled": False}
    artifact_id, target_id = parts[1], parts[2]
    pending = _load(root, artifact_id)
    if not isinstance(host, str) or not host or not isinstance(session_id, str) or not session_id:
        raise ReconciliationError("reconciliation host context is invalid")
    try:
        binding = _artifactpromptlib.binding(root, "reconciliation", artifact_id)
    except _artifactpromptlib.PromptRouteError as exc:
        raise ReconciliationError("reconciliation authority binding is unavailable") from exc
    if binding != _digest(_canonical(pending)):
        raise ReconciliationError("pending reconciliation changed after arming")
    expected_prompt = (
        f"reconcile-task {pending['artifact_id']} {pending['target_id']} {pending['target_state']} {parts[-1]}"
        if pending["operation"] == "task-reconcile"
        else f"reconcile-scope {pending['artifact_id']} {pending['target_id']} {parts[-1]}"
    )
    if prompt != expected_prompt or _digest(prompt.encode()) != pending["prompt_sha256"]:
        return {"matched": False, "reconciled": False}
    if artifact_id != pending["artifact_id"] or target_id != pending["target_id"]:
        return {"matched": False, "reconciled": False}
    identity, snapshot, record = _current(client, artifact_id, target_id)
    if identity != pending["identity"] or snapshot["sha256"] != pending["input_sha256"] or record != pending["record"]:
        raise ReconciliationError("reconciliation target changed after arming")
    payload = {"input_sha256": pending["input_sha256"], "assessment": pending["assessment"]}
    if pending["operation"] == "task-reconcile":
        payload.update(task_sha256=pending["record_sha256"], target_state=pending["target_state"])
    event = {
        "kind": "reconciliation",
        "authority_kind": "user_workflow",
        "subject": {"artifact_id": artifact_id, "normative_sha256": identity["normative_sha256"], "record_id": target_id},
        "actor": "interactive repository user", "origin": f"{host}:UserPromptSubmit:{session_id}",
        "verdict": "reconciled", "payload": payload, "source_text": prompt,
    }
    try:
        captured = _artifactauthoritylib.capture_user_prompt(
            root, client, event, host=host, session_id=session_id,
        )
    except _artifactauthoritylib.AuthorityError as exc:
        raise ReconciliationError(str(exc)) from exc
    receipt = captured.get("receipt")
    if not isinstance(receipt, str) or not receipt.startswith(".codearbiter/.artifacts/receipts/"):
        raise ReconciliationError("capture returned no valid reconciliation receipt")
    request = {
        "artifact_id": artifact_id, "operation_id": f"host-user-reconcile-{_digest(_canonical(event))[:24]}",
        "expected": {"revision": identity["revision"], "model_sha256": identity["model_sha256"]},
        "receipt": receipt,
    }
    if pending["operation"] == "task-reconcile":
        request.update(task=target_id, state=pending["target_state"], reason=pending["reason"])
    else:
        request.update(scope=target_id)
    result = client.call(pending["operation"], request)
    (root / _pending(artifact_id)).unlink()
    _artifactpromptlib.unregister(root, "reconciliation", artifact_id)
    return {"matched": True, "reconciled": True, "artifact_id": artifact_id, "target_id": target_id, "receipt": receipt, "revision": result.get("revision")}


def consume_from_hook(*, root: str | Path, plugin_root: str | Path, prompt: str, host: str, session_id: str) -> str:
    attempted = isinstance(prompt, str) and prompt.startswith(("reconcile-task ", "reconcile-scope "))
    if not attempted:
        return ""
    try:
        routed = _artifactpromptlib.resolve("reconciliation", prompt)
        if routed is None:
            raise ReconciliationError("no matching armed reconciliation")
        client = _artifactlib.ArtifactClient(routed, Path(plugin_root) / "helpers" / "artifacts")
        result = consume_reconciliation(routed, client, prompt, host=host, session_id=session_id)
    except (ReconciliationError, _artifactlib.ArtifactError, _artifactpromptlib.PromptRouteError, OSError) as exc:
        return f"codeArbiter: reconciliation capture failed: {exc}"
    return f"codeArbiter: workflow reconciliation recorded for {result['artifact_id']}#{result['target_id']} (receipt {result['receipt']})."
