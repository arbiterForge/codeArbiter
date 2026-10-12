#!/usr/bin/env python3
"""Exercise the actual artifact CLI and retain native statement coverage.

The instrumented executable is a disposable test build, never an installed or
release-qualified candidate. Production bridge environment isolation is intact.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "core/artifacts"
PROTOCOL = "codearbiter.artifact-api/0.1.0"
BINARY: Path | None = None
COUNTERS: Path | None = None


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-cli-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve(strict=True)

    def invoke(self, operation="capabilities", request=None, *, raw=None, flags=()):
        self.assertIsNotNone(BINARY, "run this suite through its script entry point")
        arguments = [str(BINARY)]
        if operation is not None:
            arguments.append(operation)
            arguments.extend(["--root", str(self.root)])
        if request is not None:
            raw = json.dumps({"protocol": PROTOCOL, **request}).encode()
        if raw is not None:
            arguments.extend(["--request", "-"])
        arguments.extend(flags)
        # Only the test executable receives this explicit coverage destination.
        environment = {"GOCOVERDIR": str(COUNTERS)}
        for name in ("SystemRoot", "WINDIR"):
            if name in os.environ:
                environment[name] = os.environ[name]
        result = subprocess.run(arguments, input=raw, capture_output=True,
                                cwd=self.root, env=environment, timeout=30)
        self.assertLessEqual(len(result.stdout), 65536)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["protocol"], PROTOCOL)
        return result, envelope

    def assert_error(self, result, envelope, code):
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], code)
        self.assertIn(code.encode(), result.stderr)

    def successful(self, operation, request):
        result, envelope = self.invoke(operation, request)
        self.assertEqual(result.returncode, 0, envelope)
        self.assertTrue(envelope["ok"], envelope)
        return envelope["result"]

    @staticmethod
    def expected(identity):
        return {key: identity[key] for key in ("revision", "model_sha256")}

    def files(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def initial_draft_pair(self):
        from test_artifact_authoring import spec_normative, plan_normative
        spec = spec_normative()
        self.successful("create", {
            "operation_id": "cli-initial-spec", "artifact_id": "SPEC-INITIAL",
            "kind": "spec", "slug": "initial", "title": spec["title"],
            "summary": spec["summary"], "normative": spec,
        })
        spec = self.successful("identity", {"artifact_id": "SPEC-INITIAL"})
        plan = plan_normative(spec["artifact_id"], spec["normative_sha256"])
        self.successful("create", {
            "operation_id": "cli-initial-plan", "artifact_id": "PLAN-INITIAL",
            "kind": "plan", "slug": "initial", "title": plan["title"],
            "summary": plan["summary"], "normative": plan,
            "spec_id": spec["artifact_id"],
        })
        plan = self.successful("identity", {"artifact_id": "PLAN-INITIAL"})
        for identity in (spec, plan):
            self.assertTrue(self.successful("validate", {
                "artifact_id": identity["artifact_id"], "gate": "ready",
            })["valid"])
        return spec, plan

    def draft_bind_request(self, spec, plan):
        return {"artifact_id": plan["artifact_id"], "spec_id": spec["artifact_id"],
                "operation_id": "cli-draft-rebind", "expected": self.expected(plan),
                "binding_mode": "draft_preview", "spec_expected": self.expected(spec)}

    def test_initial_draft_pair_can_rebind_after_spec_revision(self):
        spec, plan = self.initial_draft_pair()
        self.successful("apply", {
            "artifact_id": spec["artifact_id"], "operation_id": "cli-revise-spec",
            "expected": self.expected(spec), "changes": [{"op": "header.update", "fields": {
                "summary": "Typed draft correction before the initial combined approval.",
            }}],
        })
        spec = self.successful("identity", {"artifact_id": spec["artifact_id"]})
        self.assertTrue(self.successful("validate", {
            "artifact_id": spec["artifact_id"], "gate": "ready",
        })["valid"])
        result, envelope = self.invoke("validate", {
            "artifact_id": plan["artifact_id"], "gate": "ready",
        })
        self.assertEqual(result.returncode, 2, envelope)
        self.assertEqual([row["code"] for row in envelope["result"]["diagnostics"]],
                         ["STALE_SPEC"])
        request = self.draft_bind_request(spec, plan)
        default = {key: value for key, value in request.items()
                   if key not in ("binding_mode", "spec_expected")}
        before = self.files()
        result, envelope = self.invoke("plan-bind", default)
        self.assert_error(result, envelope, "AUTHORITY_UNVERIFIED")
        self.assertEqual(self.files(), before)

        result, envelope = self.invoke("plan-bind", request)
        self.assertEqual(result.returncode, 0, envelope)
        rebound = envelope["result"]
        self.assertEqual(rebound["artifact_id"], plan["artifact_id"])
        self.assertEqual(rebound["path"], plan["path"])
        self.assertEqual(rebound["revision"], plan["revision"] + 1)
        self.assertEqual(self.successful("identity", {"artifact_id": spec["artifact_id"]}), spec)
        for identity in (spec, rebound):
            ready = self.successful("validate", {
                "artifact_id": identity["artifact_id"], "gate": "ready",
            })
            self.assertTrue(ready["valid"], ready)
            self.assertFalse(ready["authority"]["authority_verified"], ready)

        preview = self.successful("sprint-approval-context", {
            "artifact_id": plan["artifact_id"], "spec_id": spec["artifact_id"],
            "delegate_methods": False, "prompt_sha256": "a" * 64,
        })
        self.assertFalse(preview["canonical_changed"])
        self.assertEqual(preview["pair"]["plan"]["artifact_id"], plan["artifact_id"])
        page = self.successful("read", {
            "artifact_id": plan["artifact_id"], "symbol": "T-001", "mode": "contextual",
        })
        headers = {row["artifact_id"]: row["record"] for row in page["items"]
                   if row["kind"] == "document_context"}
        self.assertEqual(headers[plan["artifact_id"]]["spec_ref"], {
            "artifact_id": spec["artifact_id"],
            "normative_sha256": spec["normative_sha256"], "binding_mode": "draft_preview",
        })
        for header in headers.values():
            self.assertEqual(header["governance"]["state"], "draft")
            self.assertEqual(header["governance"]["approvals"], [])
        result, envelope = self.invoke("eligible", {"artifact_id": plan["artifact_id"]})
        self.assert_error(result, envelope, "DRAFT_BINDING")
        after = self.files()
        replay = self.successful("plan-bind", request)
        self.assertTrue(replay["transaction"]["replay"])
        self.assertEqual(self.files(), after)

    def test_draft_rebind_schema_is_closed_and_requires_exact_source_cas(self):
        spec, plan = self.initial_draft_pair()
        request = self.draft_bind_request(spec, plan)
        cases = [
            {"binding_mode": "approved_source"}, {"binding_mode": True},
            {"spec_expected": {"revision": spec["revision"]}},
            {"spec_expected": {**self.expected(spec), "extra": True}},
            {"spec_expected": {**self.expected(spec), "revision": True}},
            {"spec_expected": {**self.expected(spec), "revision": 0}},
            {"spec_expected": {**self.expected(spec), "model_sha256": "bad"}},
            {"unexpected": True},
        ]
        requests = [{**request, **changed} for changed in cases]
        requests.extend({key: value for key, value in request.items() if key != omitted}
                        for omitted in ("binding_mode", "spec_expected"))
        for candidate in requests:
            with self.subTest(candidate=candidate):
                before = self.files()
                result, envelope = self.invoke("plan-bind", candidate)
                self.assert_error(result, envelope, "INVALID_MODEL")
                self.assertEqual(self.files(), before)

    def test_draft_rebind_checks_both_members_revision_and_hash(self):
        spec, plan = self.initial_draft_pair()
        request = self.draft_bind_request(spec, plan)
        for member in ("expected", "spec_expected"):
            for changed in ({"revision": 2}, {"model_sha256": "0" * 64}):
                with self.subTest(member=member, changed=changed):
                    candidate = {**request, member: {**request[member], **changed}}
                    before = self.files()
                    result, envelope = self.invoke("plan-bind", candidate)
                    self.assert_error(result, envelope, "REVISION_CONFLICT")
                    self.assertEqual(self.files(), before)

    def test_draft_rebind_rejects_cross_spec_selection(self):
        from test_artifact_authoring import spec_normative
        spec, plan = self.initial_draft_pair()
        normative = spec_normative()
        other = self.successful("create", {
            "operation_id": "cli-other-spec", "artifact_id": "SPEC-OTHER",
            "kind": "spec", "slug": "other", "title": normative["title"],
            "summary": normative["summary"], "normative": normative,
        })
        before = self.files()
        result, envelope = self.invoke("plan-bind", self.draft_bind_request(other, plan))
        self.assert_error(result, envelope, "PAIR_MISMATCH")
        self.assertEqual(self.files(), before)

    def test_draft_rebind_runs_full_ready_and_keeps_invalid_changes_atomic(self):
        from test_artifact_authoring import spec_normative
        spec, plan = self.initial_draft_pair()
        valid_change = [{"op": "record.update", "symbol": "T-001", "fields": {
            "steps": ["Retain the original negative oracle.", "Apply the typed correction."],
        }}]
        invalid_changes = [
            [{"op": "header.update", "fields": {"summary": " "}}],
            [{"op": "record.update", "symbol": "T-001", "fields": {"steps": []}}],
            [{"op": "record.update", "symbol": "T-001", "fields": {"criterion_refs": ["SPEC-INITIAL#AC-001", "SPEC-INITIAL#AC-MISSING"]}}],
        ]
        for number, changes in enumerate(invalid_changes):
            with self.subTest(changes=changes):
                before = self.files()
                result, envelope = self.invoke("plan-bind", {
                    **self.draft_bind_request(spec, plan), "changes": changes,
                })
                self.assertNotEqual(result.returncode, 0, envelope)
                self.assertIn(envelope["error"]["code"], {"NOT_READY", "INVALID_CRITERION_REF"})
                self.assertEqual(self.files(), before)

        self.successful("apply", {
            "artifact_id": spec["artifact_id"], "operation_id": "cli-not-ready-spec",
            "expected": self.expected(spec), "changes": [{"op": "header.update", "fields": {"summary": " "}}],
        })
        spec = self.successful("identity", {"artifact_id": spec["artifact_id"]})
        before = self.files()
        result, envelope = self.invoke("plan-bind", self.draft_bind_request(spec, plan))
        self.assert_error(result, envelope, "NOT_READY")
        self.assertEqual(self.files(), before)

        self.successful("apply", {
            "artifact_id": spec["artifact_id"], "operation_id": "cli-ready-spec-again",
            "expected": self.expected(spec), "changes": [{"op": "header.update", "fields": {
                "summary": spec_normative()["summary"],
            }}],
        })
        spec = self.successful("identity", {"artifact_id": spec["artifact_id"]})
        rebound = self.successful("plan-bind", {
            **self.draft_bind_request(spec, plan), "changes": valid_change,
        })
        task = self.successful("read", {"artifact_id": plan["artifact_id"], "symbol": "T-001", "mode": "exact"})
        self.assertEqual(task["record"]["steps"], valid_change[0]["fields"]["steps"])
        self.assertTrue(self.successful("validate", {"artifact_id": rebound["artifact_id"], "gate": "ready"})["valid"])

    def test_draft_rebind_revisions_keep_old_approval_context_obsolete(self):
        spec, plan = self.initial_draft_pair()
        old_context = self.successful("sprint-approval-context", {
            "artifact_id": plan["artifact_id"], "spec_id": spec["artifact_id"],
            "delegate_methods": False, "prompt_sha256": "a" * 64,
        })
        original_plan = plan
        for revision in range(2):
            self.successful("apply", {
                "artifact_id": spec["artifact_id"], "operation_id": f"cli-fresh-spec-{revision}",
                "expected": self.expected(spec), "changes": [{"op": "header.update", "fields": {
                    "summary": f"Typed correction {revision} before genuine approval.",
                }}],
            })
            spec = self.successful("identity", {"artifact_id": spec["artifact_id"]})
            plan = self.successful("plan-bind", {
                **self.draft_bind_request(spec, plan), "operation_id": f"cli-fresh-bind-{revision}",
            })
            before = self.files()
            result, envelope = self.invoke("plan-bind", {
                **self.draft_bind_request(spec, original_plan), "operation_id": f"cli-stale-bind-{revision}",
            })
            self.assert_error(result, envelope, "REVISION_CONFLICT")
            self.assertEqual(self.files(), before)
            current = self.successful("sprint-approval-context", {
                "artifact_id": plan["artifact_id"], "spec_id": spec["artifact_id"],
                "delegate_methods": False, "prompt_sha256": "a" * 64,
            })
            self.assertNotEqual(current["pair"], old_context["pair"])
            self.assertNotEqual(current["spec_context"]["context_sha256"], old_context["spec_context"]["context_sha256"])
            self.assertNotEqual(current["plan_context"]["context_sha256"], old_context["plan_context"]["context_sha256"])
            self.assertFalse(self.successful("identity", {"artifact_id": plan["artifact_id"]})["authority"]["authority_verified"])

    def test_draft_rebind_rejects_authority_and_execution_source_fixtures(self):
        from test_artifact_authoring import refusal_only_model_container
        spec, plan = self.initial_draft_pair()
        # Add the prerequisite through the real typed API before constructing
        # inert adverse states. No event, observation, receipt or approval is issued.
        self.successful("apply", {
            "artifact_id": plan["artifact_id"], "operation_id": "cli-add-prerequisite",
            "expected": self.expected(plan), "changes": [{"op": "record.add", "collection": "prerequisites", "record": {
                "id": "GATE-01", "title": "Retain the prerequisite", "requirement": "Genuine prerequisite proof required.", "source_refs": [],
            }}],
        })
        spec_path = self.root / spec["path"]
        plan_path = self.root / plan["path"]
        spec_bytes, plan_bytes = spec_path.read_bytes(), plan_path.read_bytes()
        approval_claim = {
            "authority_kind": "user_workflow", "source_ref": "missing-refusal-only-source",
            "normative_sha256": "0" * 64, "attestation_level": "workflow_attested",
            "source_sha256": "0" * 64, "artifact_id": "SPEC-INITIAL",
        }
        cases = []
        for member in ("spec", "plan"):
            for state in ("ready", "approved", "superseded"):
                cases.append((f"{member}-{state}", member, "INITIAL_APPROVAL_ONLY",
                              lambda data, state=state: data["governance"].update(state=state)))
            cases.append((f"{member}-approval-claim", member, "INITIAL_APPROVAL_ONLY",
                          lambda data: data["governance"].update(approvals=[approval_claim])))
        for state in ("IN_PROGRESS", "REVIEW", "ACCEPTED", "BLOCKED", "STALE"):
            cases.append((f"task-{state}", "plan", "INITIAL_APPROVAL_ONLY",
                          lambda data, state=state: data["execution"]["tasks"]["T-001"].update(state=state)))
        for key, value in (("evidence_refs", ["missing-refusal-only-evidence"]),
                           ("completion_review_receipt", "missing-refusal-only-review"),
                           ("completion_sha256", "0" * 64)):
            cases.append((key, "plan", "INITIAL_APPROVAL_ONLY",
                          lambda data, key=key, value=value: data["execution"]["tasks"]["T-001"].update({key: value})))
        cases.extend([
            ("prerequisite-evidence", "plan", "INITIAL_APPROVAL_ONLY",
             lambda data: data["execution"]["prerequisite_evidence"].update({"GATE-01": ["missing-refusal-only-evidence"]})),
            ("satisfied-prerequisite", "plan", "INITIAL_APPROVAL_ONLY",
             lambda data: (data["execution"]["prerequisites"].update({"GATE-01": "satisfied"}),
                           data["execution"]["prerequisite_evidence"].update({"GATE-01": ["missing-refusal-only-evidence"]}))),
            ("scope-evidence", "plan", "INITIAL_APPROVAL_ONLY",
             lambda data: data["execution"]["scopes"].update({"CP-01": {"base_input_sha256": "0" * 64, "plan_sha256": "0" * 64}})),
            ("approved-source-binding", "plan", "DRAFT_BINDING",
             lambda data: data["normative"]["spec_ref"].update(binding_mode="approved_source")),
            ("different-slug", "spec", "PAIR_MISMATCH", lambda data: data.update(slug="other")),
            ("different-spec-ref-id", "plan", "PAIR_MISMATCH",
             lambda data: data["normative"]["spec_ref"].update(artifact_id="SPEC-OTHER")),
        ])
        for number, (name, member, code, mutate) in enumerate(cases):
            with self.subTest(case=name):
                spec_path.write_bytes(spec_bytes)
                plan_path.write_bytes(plan_bytes)
                path, original = (spec_path, spec_bytes) if member == "spec" else (plan_path, plan_bytes)
                path.write_bytes(refusal_only_model_container(original, mutate))
                relative = path.relative_to(self.root).as_posix()
                repair = self.successful("repair-preview", {"path": relative})
                self.successful("repair-apply", {
                    "path": relative, "operation_id": f"cli-refusal-render-{number}",
                    "expected_bytes_sha256": repair["expected_bytes_sha256"], "preview_sha256": repair["preview_sha256"],
                })
                current_spec = self.successful("identity", {"artifact_id": "SPEC-INITIAL"})
                current_plan = self.successful("identity", {"artifact_id": "PLAN-INITIAL"})
                before = self.files()
                result, envelope = self.invoke("plan-bind", {
                    **self.draft_bind_request(current_spec, current_plan), "operation_id": f"cli-refusal-bind-{number}",
                })
                self.assert_error(result, envelope, code)
                self.assertEqual(self.files(), before)
                self.assertFalse(any("/authority-sources/" in path or "/observations/" in path or "/receipts/" in path
                                     for path in before))

    def test_default_and_help_report_capabilities(self):
        for operation in (None, "capabilities", "--version", "--help", "help"):
            with self.subTest(operation=operation):
                result, envelope = self.invoke(operation)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(envelope["ok"])
                self.assertEqual(envelope["operation"], "capabilities")
                self.assertTrue(envelope["result"]["repository_operations_available"])
                self.assertEqual(envelope["result"]["public_registrations_added"], 0)

    def test_invalid_requests_preserve_the_repository(self):
        cases = [
            (b"{", "INVALID_JSON"),
            (b"[]", "INVALID_REQUEST"),
            (b'{} {}', "TRAILING_JSON"),
        ]
        for raw, code in cases:
            with self.subTest(code=code):
                result, envelope = self.invoke(raw=raw)
                self.assert_error(result, envelope, code)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_argument_and_request_file_errors_are_structured(self):
        cases = [
            (("--unknown",), "INVALID_ARGUMENT"),
            (("unexpected-positional",), "INVALID_ARGUMENT"),
            (("--request", str(self.root / "missing.json")), "REQUEST_UNAVAILABLE"),
        ]
        for flags, code in cases:
            with self.subTest(code=code, flags=flags):
                result, envelope = self.invoke(flags=flags)
                self.assert_error(result, envelope, code)
        result, envelope = self.invoke("not-an-operation")
        self.assert_error(result, envelope, "UNKNOWN_OPERATION")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_request_file_and_stdin_have_the_same_protocol_result(self):
        request = self.root / "request.json"
        request.write_text(json.dumps({"protocol": PROTOCOL}), encoding="utf-8")
        file_result, file_envelope = self.invoke(flags=("--request", str(request)))
        stdin_result, stdin_envelope = self.invoke(request={})
        self.assertEqual(file_result.returncode, 0, file_result.stderr)
        self.assertEqual(stdin_result.returncode, 0, stdin_result.stderr)
        self.assertEqual(file_envelope, stdin_envelope)

    def test_draft_creation_and_validation_exit_status(self):
        result, envelope = self.invoke("create", {
            "operation_id": "cli-draft-fixture", "artifact_id": "SPEC-CLI-FIXTURE",
            "kind": "spec", "slug": "cli-fixture", "title": "CLI fixture",
            "summary": "Disposable unapproved draft for executable tests.",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(envelope["ok"])
        result, envelope = self.invoke("validate", {
            "artifact_id": "SPEC-CLI-FIXTURE", "gate": "structural",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(envelope["ok"])
        self.assertTrue(envelope["result"]["valid"])
        result, envelope = self.invoke("validate", {
            "artifact_id": "SPEC-CLI-FIXTURE", "gate": "approved",
        })
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(envelope["ok"])
        self.assertFalse(envelope["result"]["valid"])

    def batch_spec(self):
        from test_artifact_authoring import spec_normative
        normative = spec_normative()
        normative["scope"] = [{"id": f"SCOPE-{number:02d}", "statement": "λ" * 700}
                              for number in range(1, 5)]
        result, envelope = self.invoke("create", {
            "operation_id": "cli-batch-create", "artifact_id": "SPEC-BATCH",
            "kind": "spec", "slug": "batch", "title": normative["title"],
            "summary": normative["summary"], "normative": normative,
        })
        self.assertEqual(result.returncode, 0, envelope)
        result, envelope = self.invoke("identity", {"artifact_id": "SPEC-BATCH"})
        self.assertEqual(result.returncode, 0, envelope)
        return envelope["result"]

    def test_native_batch_pages_are_exact_bounded_and_non_authorizing(self):
        identity = self.batch_spec()
        ids = ["SCOPE-04", "SCOPE-02", "SCOPE-01", "SCOPE-03"]
        request = {"artifact_id": "SPEC-BATCH", "symbols": ids,
                   "model_sha256": identity["model_sha256"], "offset": 0, "budget": 4096}
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        seen, pages = [], 0
        while True:
            result, envelope = self.invoke("read-batch", request)
            self.assertEqual(result.returncode, 0, envelope)
            self.assertLessEqual(len(result.stdout), 4096)
            page = envelope["result"]
            self.assertFalse(page["context_complete"])
            self.assertNotIn("context_ticket", page)
            self.assertEqual(page["mode"], "exact")
            self.assertEqual(page["model_sha256"], identity["model_sha256"])
            self.assertEqual(page["offset"], len(seen))
            self.assertEqual(page["total"], len(ids))
            for row in page["records"]:
                code, exact = self.invoke("read", {"artifact_id": "SPEC-BATCH", "symbol": row["id"], "mode": "exact", "budget": 4096})
                self.assertEqual(code.returncode, 0, exact)
                self.assertEqual(row["record"], exact["result"]["record"])
                seen.append(row["id"])
            pages += 1
            if page["next_offset"] is None:
                break
            self.assertEqual(page["next_offset"], len(seen))
            self.assertLess(pages, len(ids))
            request["offset"] = page["next_offset"]
        self.assertGreater(pages, 1)
        self.assertEqual(seen, ids)
        self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes()
                                  for path in self.root.rglob("*") if path.is_file()})

    def test_native_batch_rejects_stale_missing_and_duplicate_selection(self):
        identity = self.batch_spec()
        request = {"artifact_id": "SPEC-BATCH", "symbols": ["SCOPE-01"],
                   "model_sha256": identity["model_sha256"], "budget": 4096}
        cases = [
            ({"symbols": []}, "INVALID_MODEL"),
            ({"symbols": ["SCOPE-01", "SCOPE-01"]}, "INVALID_MODEL"),
            ({"symbols": ["SCOPE-01", "SCOPE-MISSING"]}, "SYMBOL_NOT_FOUND"),
            ({"model_sha256": "0" * 64}, "STALE_CURSOR"),
            ({"unexpected": True}, "INVALID_MODEL"),
        ]
        for changed, code in cases:
            with self.subTest(changed=changed):
                result, envelope = self.invoke("read-batch", {**request, **changed})
                self.assert_error(result, envelope, code)
                self.assertNotIn("result", envelope)


def main() -> int:
    global BINARY, COUNTERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.coverage_output.absolute()
    if output.exists() or output.with_suffix(output.suffix + ".json").exists():
        parser.error("coverage output and sidecar must be new files")
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("artifact_coverage", REPO / "tools/artifact-coverage.py")
    assert spec is not None and spec.loader is not None
    coverage = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = coverage
    spec.loader.exec_module(coverage)
    identity = coverage.source_identity(MODULE)
    environment = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off",
                       GOWORK="off", GOENV="off", GOFLAGS="", CGO_ENABLED="0")
    with tempfile.TemporaryDirectory(prefix="ca-cli-coverage-") as directory:
        scratch = Path(directory).resolve(strict=True)
        BINARY = scratch / ("ca-artifact.exe" if os.name == "nt" else "ca-artifact")
        COUNTERS = scratch / "counters"
        COUNTERS.mkdir()
        subprocess.run([
            "go", "build", "-buildvcs=false", "-cover", "-covermode=atomic",
            "-coverpkg=./...", "-o", str(BINARY), "./cmd/ca-artifact",
        ], cwd=MODULE, env=environment, check=True)
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(CliTests))
        if not result.wasSuccessful():
            return 1
        subprocess.run([
            "go", "tool", "covdata", "textfmt", "-i=" + str(COUNTERS), "-o=" + str(output),
        ], cwd=MODULE, env=environment, check=True)
    metadata = coverage.integration_metadata(MODULE, output, identity)
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"integration_profile": str(output), "tests": result.testsRun}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
