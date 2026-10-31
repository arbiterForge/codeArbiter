#!/usr/bin/env python3
"""Probe selected work compatibility with two exact native candidate binaries.

The disposable repository is created here; no existing project is migrated.
An older client may read its own work, but must refuse a newer work field and
leave both the upgraded item and any later edit intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


PROTOCOL = "codearbiter.artifact-api/0.1.0"


def call(binary: Path, root: Path, operation: str, values: dict) -> tuple[int, dict]:
    request = json.dumps({"protocol": PROTOCOL, **values}, sort_keys=True).encode()
    completed = subprocess.run(
        [str(binary), operation, "--root", str(root), "--request", "-"],
        input=request, capture_output=True, check=False, timeout=90,
    )
    response = json.loads(completed.stdout)
    assert response["protocol"] == PROTOCOL and response["operation"] == operation
    assert response["ok"] is (completed.returncode == 0), response
    return completed.returncode, response


def ok(binary: Path, root: Path, operation: str, values: dict) -> dict:
    code, response = call(binary, root, operation, values)
    assert code == 0, response
    return response["result"]


def refuse(binary: Path, root: Path, operation: str, values: dict) -> str:
    code, response = call(binary, root, operation, values)
    assert code != 0, response
    return response["error"]["code"]


def exercise(old: Path, candidate: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="ca-work-old-client-") as temporary:
        root = Path(temporary).resolve(strict=True)
        original = ok(old, root, "work-create", {
            "operation_id": "old-work-create-001", "title": "Old work",
            "intent": "Preserve the saved identity", "work_type": "fix",
        })
        work_id = original["work_id"]
        before = ok(old, root, "work-get", {"work_id": work_id})
        assert before["work_id"] == work_id
        upgraded = ok(candidate, root, "work-update", {
            "operation_id": "new-work-cycle-001", "work_id": work_id,
            "expected": {"revision": before["revision"],
                         "model_sha256": before["model_sha256"]},
            "action": "set-cycle", "cycle_id": "selected-cycle",
        })
        path = root / upgraded["path"]
        upgraded_bytes = path.read_bytes()
        read_error = refuse(old, root, "work-get", {"work_id": work_id})
        write_error = refuse(old, root, "work-update", {
            "operation_id": "old-work-update-001", "work_id": work_id,
            "expected": {"revision": before["revision"],
                         "model_sha256": before["model_sha256"]},
            "action": "rename", "title": "Stale overwrite",
        })
        assert read_error == "INVALID_WORK", read_error
        assert write_error == "INVALID_WORK", write_error
        assert path.read_bytes() == upgraded_bytes, "old client changed upgraded work"

        later = ok(candidate, root, "work-update", {
            "operation_id": "new-work-rename-001", "work_id": work_id,
            "expected": {"revision": upgraded["revision"],
                         "model_sha256": upgraded["model_sha256"]},
            "action": "rename", "title": "Later edit survives",
        })
        later_bytes = path.read_bytes()
        assert refuse(old, root, "work-get", {"work_id": work_id}) == read_error
        assert path.read_bytes() == later_bytes, "old read changed a later edit"
        current = ok(candidate, root, "work-get", {"work_id": work_id})
        assert current["work_id"] == work_id
        assert current["title"] == "Later edit survives"
        assert current["cycle_id"] == "selected-cycle"
        assert current["revision"] == later["revision"]
        return {
            "old_sha256": hashlib.sha256(old.read_bytes()).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "older_read_error": read_error,
            "older_write_error": write_error,
            "old_client_preserved_upgraded_and_later_bytes": True,
            "current_client_retained_identity_and_later_edit": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.old.resolve(strict=True),
                              args.candidate.resolve(strict=True)), sort_keys=True))


if __name__ == "__main__":
    main()
