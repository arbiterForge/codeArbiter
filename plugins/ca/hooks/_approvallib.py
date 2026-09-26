#!/usr/bin/env python3
"""Host-owned approval capture for structured artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any

import _artifactlib
import _artifactauthoritylib
import _artifactpromptlib
import _replylib


PENDING = Path(".codearbiter/.markers/pending-user-approval.json")
SOURCE_DIR = Path(".codearbiter/.artifacts/authority-sources")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{12,128}")
HOST_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
SESSION_RE = re.compile(r"[A-Za-z0-9._:-]{1,256}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ApprovalError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _identity(client: Any, artifact_id: str) -> dict[str, Any]:
    identity = client.call("identity", {"artifact_id": artifact_id})
    required = {
        "artifact_id": str,
        "kind": str,
        "revision": int,
        "model_sha256": str,
        "normative_sha256": str,
    }
    if any(type(identity.get(key)) is not kind for key, kind in required.items()):
        raise ApprovalError("INVALID_IDENTITY", "artifact identity is incomplete")
    if identity["artifact_id"] != artifact_id:
        raise ApprovalError("INVALID_IDENTITY", "engine returned another artifact")
    for key in ("model_sha256", "normative_sha256"):
        if not SHA256_RE.fullmatch(identity[key]):
            raise ApprovalError("INVALID_IDENTITY", f"{key} is malformed")
    return identity


def _ready(client: Any, identity: dict[str, Any]) -> None:
    result = client.call(
        "validate",
        {"artifact_id": identity["artifact_id"], "gate": "ready"},
        permit_invalid=True,
    )
    if (
        result.get("valid") is not True
        or result.get("artifact_id") != identity["artifact_id"]
        or result.get("model_sha256") != identity["model_sha256"]
        or result.get("normative_sha256") != identity["normative_sha256"]
    ):
        raise ApprovalError("NOT_READY", "only the exact current ready artifact can be armed")


def _safe_directory(root: Path, relative: Path, *, create: bool) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                raise
            current.mkdir()
            info = current.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise ApprovalError(
                "UNSAFE_APPROVAL_PATH", "approval state directories must be real directories"
            )
    return current


def _write_new(root: Path, relative: Path, data: bytes) -> None:
    parent = _safe_directory(root, relative.parent, create=True)
    path = parent / relative.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o600)
    completed = False
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        completed = True
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if not completed:
            try:
                path.unlink()
            except OSError:
                pass


def arm_user_approval(
    root: str | Path,
    client: Any,
    artifact_id: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    identity = _identity(client, artifact_id)
    _ready(client, identity)
    token = token or secrets.token_urlsafe(24)
    if not TOKEN_RE.fullmatch(token):
        raise ApprovalError("INVALID_TOKEN", "approval token has an invalid shape")
    pending = {
        "format": "codearbiter.pending-user-approval/0.1.0",
        "artifact_id": identity["artifact_id"],
        "kind": identity["kind"],
        "revision": identity["revision"],
        "model_sha256": identity["model_sha256"],
        "normative_sha256": identity["normative_sha256"],
        "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
    }
    try:
        _write_new(root, PENDING, _canonical(pending))
    except FileExistsError as exc:
        raise ApprovalError(
            "PENDING_APPROVAL", "resolve or clear the existing approval request first"
        ) from exc
    try:
        _artifactpromptlib.register(
            root, "approval", artifact_id, f"approve {artifact_id} {token}"
        )
    except _artifactpromptlib.PromptRouteError:
        (root / PENDING).unlink()
        raise
    reply = f"approve {artifact_id} {token}"
    code = _replylib.offer_code(root, "approval", artifact_id, reply,
                                names=[artifact_id], short_prefix=["approve"])
    envelope = _replylib.ask_envelope(
        root, "approval", artifact_id, code_fields=code,
        question=(f"Approve {identity['kind']} {artifact_id} revision {identity['revision']} "
                  f"as you reviewed it? (normative {identity['normative_sha256'][:12]})"),
        header=f"Approve {code.get('code', '')}",
        description=f"Records your approval of this exact revision. Same as typing {code.get('short_reply')}.",
    )
    return {
        "artifact_id": artifact_id,
        "reply": reply,
        **code,
        **({"ask_envelope": envelope} if envelope else {}),
        "model_sha256": identity["model_sha256"],
        "normative_sha256": identity["normative_sha256"],
    }


def _load_pending(root: Path) -> dict[str, Any] | None:
    try:
        parent = _safe_directory(root, PENDING.parent, create=False)
    except FileNotFoundError:
        return None
    path = parent / PENDING.name
    try:
        info = path.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if (
            stat.S_ISLNK(info.st_mode)
            or reparse
            or not stat.S_ISREG(info.st_mode)
            or info.st_size > 16384
        ):
            raise ApprovalError(
                "INVALID_PENDING_APPROVAL",
                "pending approval is not bounded regular data",
            )
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError) as exc:
        raise ApprovalError("INVALID_PENDING_APPROVAL", "pending approval is unreadable") from exc
    if isinstance(value, dict) and value.get("format") == "codearbiter.pending-user-approval/0.2.0":
        import _sprintapprovallib
        return _sprintapprovallib.validate_pending(value)
    expected = {
        "format", "artifact_id", "kind", "revision", "model_sha256",
        "normative_sha256", "token_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ApprovalError("INVALID_PENDING_APPROVAL", "pending approval shape is invalid")
    if (
        value["format"] != "codearbiter.pending-user-approval/0.1.0"
        or not isinstance(value["artifact_id"], str)
        or not value["artifact_id"]
        or not isinstance(value["kind"], str)
        or not value["kind"]
        or type(value["revision"]) is not int
        or not isinstance(value["model_sha256"], str)
        or SHA256_RE.fullmatch(value["model_sha256"]) is None
        or not isinstance(value["normative_sha256"], str)
        or SHA256_RE.fullmatch(value["normative_sha256"]) is None
        or not isinstance(value["token_sha256"], str)
        or SHA256_RE.fullmatch(value["token_sha256"]) is None
    ):
        raise ApprovalError("INVALID_PENDING_APPROVAL", "pending approval values are invalid")
    return value


def cancel_user_approval(root: str | Path, artifact_id: str) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    pending = _load_pending(root)
    if pending is None:
        raise ApprovalError("NO_PENDING_APPROVAL", "there is no approval request to cancel")
    if pending["artifact_id"] != artifact_id:
        raise ApprovalError(
            "PENDING_APPROVAL_MISMATCH",
            "the pending approval request belongs to another artifact",
        )
    if pending["format"] == "codearbiter.pending-user-approval/0.2.0":
        import _sprintapprovallib
        return _sprintapprovallib.cancel(root, pending)
    (root / PENDING).unlink()
    _artifactpromptlib.unregister(root, "approval", artifact_id)
    return {"artifact_id": artifact_id, "cancelled": True}


def consume_user_approval(
    root: str | Path,
    client: Any,
    prompt: str,
    *,
    host: str,
    session_id: str,
    seam: str = "UserPromptSubmit",
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    if seam not in {"UserPromptSubmit", "AskUserQuestion"}:
        raise ApprovalError("INVALID_HOST_CONTEXT", "approval seam is unsupported")
    pending = _load_pending(root)
    if pending is None or not isinstance(prompt, str):
        return {"matched": False, "approved": False}
    if pending["format"] == "codearbiter.pending-user-approval/0.2.0":
        import _sprintapprovallib
        return _sprintapprovallib.consume(root, client, pending, prompt, host=host, session_id=session_id, seam=seam)
    parts = prompt.split(" ")
    if len(parts) != 3 or parts[0] != "approve" or parts[1] != pending["artifact_id"]:
        return {"matched": False, "approved": False}
    token = parts[2]
    if not TOKEN_RE.fullmatch(token) or not secrets.compare_digest(
        hashlib.sha256(token.encode("ascii")).hexdigest(), pending["token_sha256"]
    ):
        return {"matched": False, "approved": False}
    if not HOST_RE.fullmatch(host) or not SESSION_RE.fullmatch(session_id):
        raise ApprovalError("INVALID_HOST_CONTEXT", "host approval context is malformed")

    current = _identity(client, pending["artifact_id"])
    for field in ("kind", "revision", "model_sha256", "normative_sha256"):
        if current[field] != pending[field]:
            raise ApprovalError("STALE_APPROVAL", "artifact changed after approval was requested")
    _ready(client, current)

    event = {
        "kind": "approval",
        "authority_kind": "user_workflow",
        "subject": {
            "artifact_id": current["artifact_id"],
            "normative_sha256": current["normative_sha256"],
            "record_id": current["artifact_id"],
        },
        "actor": "interactive repository user",
        "origin": f"{host}:{seam}:{session_id}",
        "verdict": "approved",
        "payload": {},
        "source_text": prompt,
    }
    try:
        captured = _artifactauthoritylib.capture_user_prompt(
            root, client, event, host=host, session_id=session_id,
        )
    except _artifactauthoritylib.AuthorityError as exc:
        raise ApprovalError("INVALID_AUTHORITY_SOURCE", str(exc)) from exc
    receipt = captured.get("receipt")
    if not isinstance(receipt, str) or not receipt:
        raise ApprovalError("INVALID_RECEIPT", "capture returned no receipt")
    approved = client.call(
        "approve",
        {
            "artifact_id": current["artifact_id"],
            "operation_id": f"host-user-approval-{hashlib.sha256(_canonical(event)).hexdigest()[:24]}",
            "expected": {
                "revision": current["revision"],
                "model_sha256": current["model_sha256"],
            },
            "receipt": receipt,
        },
    )
    (root / PENDING).unlink()
    _artifactpromptlib.unregister(root, "approval", current["artifact_id"])
    return {
        "matched": True,
        "approved": True,
        "artifact_id": current["artifact_id"],
        "authority_source": captured["authority_source"],
        "receipt": receipt,
        "revision": approved.get("revision"),
    }


def consume_from_hook(*, root: str | Path, plugin_root: str | Path, prompt: str,
                      host: str, session_id: str, seam: str = "UserPromptSubmit") -> str:
    raw = prompt
    prepared = _replylib.prepare(raw, "approval")
    prompt = prepared["text"]
    attempted = prepared["attempted"]

    def missed(reason: str) -> str:
        _replylib.record_near_miss(root, raw, reason)
        return prepared["notice"] or _replylib.miss_notice("approve K7MQ")

    if prepared["notice"]:
        return missed("code")
    try:
        routed = _artifactpromptlib.resolve("approval", prompt)
        root = routed or Path(root)
        if not (Path(root) / PENDING).exists():
            return missed("no-pending") if attempted else ""
        client = _artifactlib.ArtifactClient(
            root, Path(plugin_root) / "helpers" / "artifacts"
        )
        result = consume_user_approval(
            root, client, prompt, host=host, session_id=session_id, seam=seam
        )
    except (ApprovalError, _artifactlib.ArtifactError,
            _artifactpromptlib.PromptRouteError, OSError) as exc:
        if attempted:
            _replylib.record_near_miss(root, raw, "capture-failed")
            return f"codeArbiter: approval capture failed: {exc}"
        return ""
    if not result.get("approved"):
        return missed("mismatch") if attempted else ""
    return (
        "codeArbiter: workflow approval recorded for "
        f"{result['artifact_id']} (receipt {result['receipt']})."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    arm = sub.add_parser("arm")
    arm.add_argument("--root", required=True)
    arm.add_argument("--artifact-id", required=True)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("--root", required=True)
    cancel.add_argument("--artifact-id", required=True)
    pair = sub.add_parser("arm-sprint")
    pair.add_argument("--root", required=True)
    pair.add_argument("--spec-id", required=True)
    pair.add_argument("--plan-id", required=True)
    pair.add_argument("--delegate-methods", action="store_true")
    resume = sub.add_parser("resume-sprint")
    resume.add_argument("--root", required=True)
    resume.add_argument("--plan-id", required=True)
    smarts = sub.add_parser("smarts")
    smarts.add_argument("--root", required=True)
    smarts.add_argument("--request-file", required=True)
    args = parser.parse_args(argv)
    if args.command == "cancel":
        print(json.dumps(cancel_user_approval(args.root, args.artifact_id)))
        return 0
    client = _artifactlib.ArtifactClient(
        args.root, _artifactlib.helper_installation(__file__)
    )
    if args.command == "smarts":
        import _sprintapprovallib
        print(json.dumps(_sprintapprovallib.apply_decision(client, args.request_file)))
        return 0
    if args.command in {"arm-sprint", "resume-sprint"}:
        import _sprintapprovallib
        result = (_sprintapprovallib.arm(args.root, client, args.spec_id, args.plan_id, delegate_methods=args.delegate_methods)
                  if args.command == "arm-sprint" else _sprintapprovallib.resume(args.root, client, args.plan_id))
    else:
        result = arm_user_approval(args.root, client, args.artifact_id)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApprovalError, _artifactlib.ArtifactError,
            _artifactpromptlib.PromptRouteError) as exc:
        sys.stderr.write(str(exc) + "\n")
        raise SystemExit(1)
