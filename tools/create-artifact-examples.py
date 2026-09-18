#!/usr/bin/env python3
"""Generate draft spec/plan examples with the real binary, not a Python renderer.

Input normative content is the reviewed design reference packaged as testdata.
This does not issue an approval or mark any implementation task complete.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess

PROTOCOL = "codearbiter.artifact-api/0.1.0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit("Output must be absent or empty; do not overwrite a live artifact store.")
    root.mkdir(parents=True, exist_ok=True)
    binary = args.binary.resolve(strict=True)
    source = Path(__file__).resolve().parents[1] / "core/artifacts/testdata/reference"

    def call(operation: str, **request: object) -> dict:
        result = subprocess.run(
            [str(binary), operation, "--root", str(root), "--request", "-"],
            input=json.dumps({"protocol": PROTOCOL, **request}),
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        body = json.loads(result.stdout)
        draft_diagnostic = (operation == "validate" and result.returncode == 2
                            and body.get("ok") and body.get("result", {}).get("valid") is False)
        if not body.get("ok") or (result.returncode != 0 and not draft_diagnostic):
            raise RuntimeError(f"{operation}: {body}; {result.stderr}")
        return body["result"]

    spec = json.loads((source / "spec.json").read_text(encoding="utf-8"))
    plan = json.loads((source / "plan.json").read_text(encoding="utf-8"))
    call("create", operation_id="example-spec-create-001", artifact_id=spec["artifact_id"],
         kind="spec", slug=spec["slug"], title=spec["normative"]["title"],
         summary=spec["normative"]["summary"], normative=spec["normative"])
    identity = call("identity", artifact_id=spec["artifact_id"])
    plan["normative"]["spec_ref"] = {
        "artifact_id": spec["artifact_id"],
        "normative_sha256": identity["normative_sha256"],
        "binding_mode": "draft_preview",
    }
    call("create", operation_id="example-plan-create-001", artifact_id=plan["artifact_id"],
         kind="plan", slug=plan["slug"], title=plan["normative"]["title"],
         summary=plan["normative"]["summary"], normative=plan["normative"], spec_id=spec["artifact_id"])
    identities = [call("identity", artifact_id=x["artifact_id"]) for x in (spec, plan)]
    checks = [call("validate", artifact_id=x["artifact_id"], gate="ready") for x in (spec, plan)]
    output = {"generator": "compiled ca-artifact", "approvals_issued": 0,
              "implementation_tasks_accepted": 0, "identities": identities, "validation": checks,
              "all_ready": all(c["valid"] for c in checks),
              "readiness_note": "Faithful draft reproduction, not a promise the historical plan satisfies every tightened runtime gate. Missing verification details are reported, never invented."}
    # Outside canonical state, for humans. This report is not an evidence receipt.
    (root / "generation-report.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
