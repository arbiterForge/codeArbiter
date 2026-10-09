#!/usr/bin/env python3
# codeArbiter — private bridge for the isolated native Pi approval dialog.
"""Inspect one armed artifact or consume the exact native dialog return.

The sole-extension host controller owns input provenance, trust and lifecycle.
This bridge is not a public approval command or an attestation against arbitrary
same-user code. It preserves the shared one-shot identity and receipt controls.
handle(request, client) -> bounded Pi bridge response (client is a fixture seam).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

import _approvallib
import _artifactlib

UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def handle(request, client=None):
    if not isinstance(request, dict) or request.get("version") != 1:
        raise ValueError("invalid request")
    event = request.get("event")
    expected = {"version", "event", "cwd"}
    if event == "native_approval_consume":
        expected |= {"sessionId", "input"}
    elif event != "native_approval_inspect":
        raise ValueError("unsupported request")
    if set(request) != expected or not isinstance(request["cwd"], str):
        raise ValueError("invalid request shape")
    root = _artifactlib._trusted_directory(Path(request["cwd"]), "UNSAFE_ROOT")
    if client is None:
        client = _artifactlib.ArtifactClient(root, _artifactlib.helper_installation(__file__))
    if event == "native_approval_inspect":
        pending = _approvallib._load_pending(root)
        if (pending is None or pending["format"] != "codearbiter.pending-user-approval/0.1.0"
                or pending["kind"] not in {"spec", "plan"}):
            raise ValueError("no supported pending approval")
        current = _approvallib._identity(client, pending["artifact_id"])
        if any(current[field] != pending[field] for field in (
                "kind", "revision", "model_sha256", "normative_sha256")):
            raise ValueError("stale pending approval")
        _approvallib._ready(client, current)
        result = {key: pending[key] for key in (
            "artifact_id", "kind", "revision", "model_sha256", "normative_sha256")}
        result["pending_sha256"] = hashlib.sha256(_approvallib._canonical(pending)).hexdigest()
    else:
        value = request["input"]
        if (not isinstance(value, dict) or set(value) != {"reply", "generation", "pending_sha256"}
                or not isinstance(value["reply"], str) or len(value["reply"].encode("utf-8")) > 512
                or not isinstance(request["sessionId"], str) or UUID.fullmatch(request["sessionId"]) is None
                or not isinstance(value["generation"], str) or UUID.fullmatch(value["generation"]) is None
                or not isinstance(value["pending_sha256"], str)
                or _approvallib.SHA256_RE.fullmatch(value["pending_sha256"]) is None):
            raise ValueError("invalid native input binding")
        captured = _approvallib.consume_user_approval(
            root, client, value["reply"], host="pi", seam="PiNativeInput",
            session_id=request["sessionId"] + ":" + value["generation"],
            expected_pending_sha256=value["pending_sha256"],
        )
        result = {key: captured[key] for key in ("matched", "approved", "artifact_id") if key in captured}
    return {"version": 1, "outcome": "allow", "resultPatch": result}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def main():
    try:
        data = sys.stdin.buffer.read(16_385)
        if len(sys.argv) != 1 or len(data) > 16_384:
            raise ValueError("invalid request size")
        request = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
        response = handle(request)
    except (ValueError, OSError, _approvallib.ApprovalError, _artifactlib.ArtifactError):
        # No source reply, token, path, or potentially sensitive host error is logged.
        response = {"version": 1, "outcome": "block", "auditCode": "PI_NATIVE_APPROVAL_UNAVAILABLE"}
    print(json.dumps(response, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
