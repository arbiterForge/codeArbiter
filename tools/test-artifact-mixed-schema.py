#!/usr/bin/env python3
"""Candidate-only mixed-schema probe using two exact native ca-artifact binaries.

This fixture never reads an existing user's repository. It is intentionally
separate from normal task execution: the older binary must fail closed on
new-schema writes and there is no destructive universal rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from test_artifact_authoring import spec_normative, plan_normative

PROTOCOL = "codearbiter.artifact-api/0.1.0"


def call(binary: Path, root: Path, operation: str, values: dict) -> tuple[int, dict]:
    request = json.dumps({"protocol": PROTOCOL, **values}, sort_keys=True).encode("utf-8")
    completed = subprocess.run(
        [str(binary), operation, "--root", str(root), "--request", "-"],
        input=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=90,
    )
    try:
        response = json.loads(completed.stdout.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise AssertionError(f"{binary.name} {operation}: no valid bounded result") from error
    assert response.get("operation") == operation, response
    assert response.get("protocol") == PROTOCOL, response
    assert response.get("ok") is (completed.returncode == 0), (operation, response)
    return completed.returncode, response


def ok(binary: Path, root: Path, operation: str, values: dict) -> dict:
    code, response = call(binary, root, operation, values)
    assert code == 0, (operation, response.get("error"))
    return response["result"]


def refuse(binary: Path, root: Path, operation: str, values: dict, code: str) -> None:
    returncode, result = call(binary, root, operation, values)
    assert returncode != 0 and result.get("error", {}).get("code") == code, (
        operation, result,
    )


def identity(binary: Path, root: Path, artifact: str) -> dict:
    return ok(binary, root, "identity", {"artifact_id": artifact})


def exercise(old: Path, current: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="ca-artifact-mixed-schema-") as tmp:
        root = Path(tmp)
        for binary in (old, current):
            assert binary.is_file()
        old_caps = ok(old, root, "capabilities", {})
        new_caps = ok(current, root, "capabilities", {})
        assert old_caps["schema_version"] == "0.3.1", old_caps
        assert new_caps["schema_version"] == "0.3.2", new_caps
        spec = spec_normative()
        old_spec = ok(old, root, "create", {
            "operation_id": "mixed-spec-0001", "artifact_id": "SPEC-FLOW",
            "kind": "spec", "slug": "flow", "title": spec["title"],
            "summary": spec["summary"], "normative": spec,
        })
        sid = identity(old, root, "SPEC-FLOW")
        plan = plan_normative("SPEC-FLOW", sid["normative_sha256"])
        ok(old, root, "create", {
            "operation_id": "mixed-plan-0001", "artifact_id": "PLAN-FLOW",
            "kind": "plan", "slug": "flow", "title": plan["title"],
            "summary": plan["summary"], "spec_id": "SPEC-FLOW",
            "normative": plan,
        })
        # A stop requested during a historical session must survive a later
        # schema upgrade. The old engine's negative task transition is safe:
        # it does not grant authority or require an artificial approval.
        first = identity(old, root, "PLAN-FLOW")
        ok(old, root, "task-block", {
            "artifact_id": "PLAN-FLOW", "operation_id": "mixed-stop-0001",
            "expected": {
                "revision": first["revision"],
                "model_sha256": first["model_sha256"],
            },
            "task": "T-001", "reason": "Existing user stop; do not redispatch.",
        })
        plan_file = root / ".codearbiter" / "plans" / "flow.html"
        before_bytes = plan_file.read_bytes()
        before = identity(old, root, "PLAN-FLOW")
        assert identity(current, root, "PLAN-FLOW")["model_sha256"] == before["model_sha256"]
        assert plan_file.read_bytes() == before_bytes, "current reader silently rewrote old bytes"
        assert re.search(rb'"schema_version"\s*:\s*"0\.3\.1"', before_bytes)

        reported_check = {
            "artifact_id": "PLAN-FLOW", "operation_id": "mixed-check-0001",
            "expected": {"revision": before["revision"], "model_sha256": before["model_sha256"]},
            "task": "T-001",
            "check": {
                "cwd": ".", "argv": ["python", "--version"], "outcome": "unknown",
                "summary": "No command was run in this compatibility fixture.",
                "source": "Synthetic boundary test; not verification evidence.",
                "origin": "agent_report",
            },
        }
        result = ok(current, root, "task-check", reported_check)
        upgraded = plan_file.read_bytes()
        replay = ok(current, root, "task-check", reported_check)
        assert replay.get("transaction", {}).get("replay") is True
        assert plan_file.read_bytes() == upgraded, "idempotent retry duplicated an upgrade"
        # Native rollback and forward recovery require the journal's *real*
        # pre-upgrade bytes, not an invented dump or model-visible receipt.
        journal = json.loads((root / ".codearbiter/.artifacts/transactions/mixed-check-0001.json").read_text(encoding="utf-8"))
        assert journal["state"] == "committed"
        entries = [entry for entry in journal["entries"] if entry["path"] == ".codearbiter/plans/flow.html"]
        assert len(entries) == 1
        assert entries[0]["before_sha256"] == hashlib.sha256(before_bytes).hexdigest()
        assert (root / entries[0]["backup"]).read_bytes() == before_bytes
        assert plan_file.read_bytes() == upgraded
        assert upgraded != before_bytes and re.search(rb'"schema_version"\s*:\s*"0\.3\.2"', upgraded)

        # Real post-upgrade edit: a second reported note, separately journaled.
        # An older before-image is now *not* a safe downgrade candidate:
        # restoring it would discard the second operation and its history.
        after_upgrade = identity(current, root, "PLAN-FLOW")
        later_check = {
            "artifact_id": "PLAN-FLOW", "operation_id": "mixed-check-0002",
            "expected": {
                "revision": after_upgrade["revision"],
                "model_sha256": after_upgrade["model_sha256"],
            },
            "task": "T-001",
            "check": {
                "cwd": ".", "argv": ["python", "--version"], "outcome": "unknown",
                "summary": "Later compatibility note; no command executed.",
                "source": "Synthetic forward-recovery test; not verification evidence.",
                "origin": "agent_report",
            },
        }
        ok(current, root, "task-check", later_check)
        after_later_edit = plan_file.read_bytes()
        assert after_later_edit != upgraded, "a later 0.3.2 edit made no new state"
        later_journal = json.loads(
            (root / ".codearbiter/.artifacts/transactions/mixed-check-0002.json").read_text(encoding="utf-8")
        )
        assert later_journal["state"] == "committed"
        later_entries = [
            entry for entry in later_journal["entries"]
            if entry["path"] == ".codearbiter/plans/flow.html"
        ]
        assert len(later_entries) == 1
        assert later_entries[0]["before_sha256"] == hashlib.sha256(upgraded).hexdigest()
        assert (root / later_entries[0]["backup"]).read_bytes() == upgraded

        # A delayed response to the ORIGINAL upgrade may be safely retried
        # but must never roll back a later change. Same for the second write.
        assert ok(current, root, "task-check", reported_check)["transaction"]["replay"] is True
        assert ok(current, root, "task-check", later_check)["transaction"]["replay"] is True
        assert plan_file.read_bytes() == after_later_edit, (
            "replaying an old committed operation erased newer saved work"
        )
        # The old schema before-image is retained for recovery, not an
        # automatic restore after subsequent committed revisions.
        assert hashlib.sha256(after_later_edit).hexdigest() != entries[0]["before_sha256"]
        newer = identity(current, root, "PLAN-FLOW")
        assert newer["revision"] > after_upgrade["revision"] > before["revision"]
        # This engine scans the complete canonical artifact pair. A historical
        # client fails closed for the *repository*, not just the new-schema
        # plan, instead of silently reinterpreting mixed models.
        refuse(old, root, "identity", {"artifact_id": "SPEC-FLOW"}, "UNSUPPORTED_VERSION")
        refuse(old, root, "identity", {"artifact_id": "PLAN-FLOW"}, "UNSUPPORTED_VERSION")
        assert plan_file.read_bytes() == after_later_edit
        refuse(old, root, "task-start", {
            "artifact_id": "PLAN-FLOW", "operation_id": "old-client-write-0001",
            "expected": {"revision": before["revision"], "model_sha256": before["model_sha256"]},
            "task": "T-001", "context_ticket": "legacy-client-unusable-with-new-schema",
        }, "UNSUPPORTED_VERSION")
        assert plan_file.read_bytes() == after_later_edit, "old client changed post-upgrade work"

        packet = ok(current, root, "task-context", {
            "artifact_id": "PLAN-FLOW", "task": "T-001",
            "model_sha256": newer["model_sha256"],
        })
        checks = packet["reported_checks"]
        assert packet["state"] == "BLOCKED", "schema upgrade cleared an explicit stop"
        assert "user stop" in (packet["reason"] or "")
        assert len(checks) >= 2, "second committed note disappeared after upgrade"
        assert checks[-1]["reported_outcome"] == "unknown"
        assert checks[-1]["summary"] == "Later compatibility note; no command executed."
        assert checks[-1]["named_tests_verified"] is False
        assert checks[-1]["evidence_assessed"] is False

        export = ok(current, root, "export", {
            "artifact_id": "PLAN-FLOW", "operation_id": "mixed-export-0001",
            "model_sha256": newer["model_sha256"],
            "target": ".codearbiter/exports/mixed-schema-safety.html",
        })
        path = root / " .codearbiter/exports/mixed-schema-safety.html".strip()
        assert export["standalone"] is True and export["canonical"] is False
        assert hashlib.sha256(path.read_bytes()).hexdigest() == export["sha256"]
        assert b"Later compatibility note; no command executed." in path.read_bytes(), (
            "standalone forward export omitted later saved work"
        )
        assert plan_file.read_bytes() == after_later_edit, "standalone export modified canonical plan"

        return {
            "old_schema": old_caps["schema_version"],
            "candidate_schema": new_caps["schema_version"],
            "historical_read_preserved_bytes": True,
            "older_client_write_rejected": True,
            "new_check_reporting_is_not_verification": True,
            "standalone_export_preserved_canonical_plan": True,
            "plan_identity_retained": newer["artifact_id"] == before["artifact_id"],
            "recorded_user_stop_preserved": packet["state"] == "BLOCKED",
            "idempotent_upgrade_retry": replay["transaction"]["replay"],
            "actual_journal_before_image_preserved": True,
            "post_upgrade_edits_preserved": True,
            "earlier_committed_retry_never_rolls_back_later_work": True,
            "forward_export_includes_later_edit": True,
            "latest_revision": newer["revision"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    outcome = exercise(args.old.resolve(strict=True), args.candidate.resolve(strict=True))
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
