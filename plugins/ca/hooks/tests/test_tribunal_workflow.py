"""T-05 workflow obligations for SPEC-TRIBUNAL-VNEXT-001.

AC01/02/04/05/32/33: documented CLI drives a real source-bound run and history.
AC06/07/08/27/28: published examples, durable leads, root causes and eligibility.
AC10/11/12/13: thin inventory/profile/cost wiring exercises the actual libraries.
AC09/15/16/17/18/35/37: reject contradictory authority/scope/privacy contracts.
Host rendering and usage compatibility also live in test_build_surface.py.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
CORE = REPO / "core" / "pysrc"
CLI = CORE / "tribunal.py"
SURFACE = REPO / "core" / "surface"
TRIBUNAL = SURFACE / "skills" / "tribunal"
sys.path.insert(0, str(CORE))
import _tribunalinventorylib as inventory


def resource(name):
    return (TRIBUNAL / "references" / (name + ".md")).read_text(encoding="utf-8")


def example(name, schema):
    for block in re.findall(r"```json\n(.*?)\n```", resource(name), re.S):
        block = re.sub(r"{{IF:[^}]+}}.*?{{END}}", "", block, flags=re.S)
        value = json.loads(block)
        if isinstance(value, dict) and value.get("schema") == schema:
            return value
    raise AssertionError("Missing executable %s example in %s" % (schema, name))


class WorkflowCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q")
        self.git("config", "user.name", "Tribunal workflow fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "contract.txt").write_text("Preserve queued writes.\n", encoding="utf-8")
        (self.root / "package.json").write_text(json.dumps({
            "name": "fixture", "scripts": {"test": "DO_NOT_EXECUTE"},
            "dependencies": {"example": "1.0.0"}}), encoding="utf-8")
        self.git("add", "--", ".")
        self.git("-c", "core.hooksPath=" + os.devnull, "commit", "-qm", "fixture", "--no-gpg-sign")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env,
                              capture_output=True, check=True, shell=False)

    def cli(self, *args, success=True, markdown=False):
        result = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                                cwd=self.root, env=self.env, capture_output=True,
                                encoding="utf-8", shell=False)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr or result.stdout)
        return result.stdout if markdown else json.loads(result.stdout)

    def test_inventory_cli_is_inert_library_projection_with_declared_limits(self):
        actual = self.cli("inventory", "--scope", ".", "--history-limit", "3")
        expected = inventory.collect_inventory(self.root, history_limit=3)
        self.assertEqual(actual, expected)
        rendered = self.cli("inventory", "--format", "markdown", "--history-limit", "3", markdown=True)
        self.assertEqual(rendered, inventory.render_inventory_md(expected))
        self.assertEqual(actual["judgment"], "not-performed")
        self.assertFalse((self.root / "DO_NOT_EXECUTE").exists())
        refused = self.cli("inventory", "--max-file-bytes", "0", success=False)
        self.assertEqual(refused["status"], "unavailable")

    def test_profile_and_cost_cli_preserve_host_capability_and_token_semantics(self):
        caps = {"agents": False, "fresh_threads": True, "model_override": True,
                "reasoning_override": False, "models": ["host-model"],
                "profiles": {"deep": {"model": "host-model", "reasoning": "invented"}}}
        actual = self.cli("profile", "deep", "--capabilities", json.dumps(caps))
        self.assertEqual(actual, inventory.resolve_profile("deep", caps))
        self.assertEqual(actual["execution"], "fresh-thread")
        self.assertEqual(actual["settings"], {"model": "host-model"})
        caps["fresh_threads"] = False
        self.assertEqual(self.cli("profile", "deep", "--capabilities", json.dumps(caps))["independence"],
                         "limited-shared-context")
        args = ("estimate", "--packet-bytes", "4096", "--profiles", '{"deep":2,"standard":1}',
                "--verification-candidates", "1", "--extraction-bytes", "256")
        one = self.cli(*args, "--concurrency", "1")
        five = self.cli(*args, "--concurrency", "5")
        self.assertEqual(one["token_band"], five["token_band"])
        self.assertEqual(one, inventory.estimate_cost(4096, {"deep": 2, "standard": 1},
                         verification_candidates=1, extraction_bytes=256))
        self.assertEqual(self.cli("estimate", "--packet-bytes", "-1", "--profiles", '{}',
                                 success=False)["status"], "unavailable")

    def test_documented_records_drive_a_run_and_followup_only_recovery(self):
        finding = example("finding-record", "finding/v1")
        decision = example("schemas", "triage/v1")
        verification = example("schemas", "verification/v1")
        lead = example("schemas", "lead/v1")
        started = self.cli("start", "--scope", "src", "--evidence-path", "contract.txt",
                           "--detail", '{"waves":[["reliability"]]}')
        run = started["run_dir"]
        self.assertEqual(self.cli("resume-status", run)["state"], "audit")
        self.cli("lead", run, "--record", json.dumps(lead))
        self.cli("lead", run, "--id", lead["id"], "--disposition", "promoted",
                 "--rationale", "Owned by " + finding["id"])
        self.assertEqual(self.cli("lead", run)["leads"][0]["disposition"], "promoted")
        result = self.cli("triage", run, "--finding", json.dumps(finding), "--record", json.dumps(decision),
                          "--verification", json.dumps(verification))
        self.assertTrue(result["eligibility"]["plan_eligible"])
        self.assertEqual(result["record"]["root_cause_key"], finding["root_cause_key"])
        self.cli("event", run, "wave-triaged", "--data", '{"wave":1}')
        self.cli("event", run, "report-written")
        status = self.cli("resume-status", run)
        self.assertTrue(status["can_resume_follow_up"])
        self.assertFalse(status["can_resume_audit"])
        self.cli("event", run, "lens-launched", success=False)
        self.cli("event", run, "run-completed", success=False)
        decision["issue_ref"] = "https://example.invalid/issues/1"
        self.cli("triage", run, "--finding", json.dumps(finding), "--record", json.dumps(decision),
                 "--verification", json.dumps(verification))
        self.cli("event", run, "issues-filed", "--data", '{"count":1}')
        self.cli("event", run, "telemetry-skipped", "--data", '{"detail":"declined"}')
        self.cli("event", run, "run-completed")
        self.assertEqual(self.cli("resume-status", run)["state"], "terminal")
        history = self.cli("read-run", run)
        self.assertEqual(history["triage"][-1]["issue_ref"], decision["issue_ref"])
        self.assertEqual(history["events"][-1]["event"], "run-completed")

    def test_eligibility_cli_rejects_unverified_refuted_or_shared_context_serious_work(self):
        finding = example("finding-record", "finding/v1")
        decision = example("schemas", "triage/v1")
        verified = example("schemas", "verification/v1")
        for outcome, independence, eligible in (("confirmed", "independent", True),
                ("narrowed", "independent", True), ("refuted", "independent", False),
                ("inconclusive", "independent", False), ("confirmed", "limited", False)):
            with self.subTest(outcome=outcome, independence=independence):
                proof = dict(verified, outcome=outcome, verification_independence=independence)
                result = self.cli("eligibility", "--finding", json.dumps(finding),
                                  "--record", json.dumps(decision), "--verification", json.dumps(proof))
                self.assertEqual(result["filing_eligible"], eligible)
                self.assertEqual(result["plan_eligible"], eligible)
        finding.update(severity="medium", requires_verification=True)
        decision["final_severity"] = "medium"
        result = self.cli("eligibility", "--finding", json.dumps(finding), "--record", json.dumps(decision))
        self.assertFalse(result["plan_eligible"])
        self.assertEqual(result["recommended_decision"], "verify-required")

    def test_frozen_external_evidence_drift_refuses_followup_and_preserves_history(self):
        self.assertIn("--evidence-path", resource("schemas"))
        run = self.cli("start", "--scope", "src", "--evidence-path", "contract.txt")["run_dir"]
        self.cli("event", run, "report-written")
        before = (Path(run) / "run.jsonl").read_bytes()
        (self.root / "contract.txt").write_text("Changed requirement\n", encoding="utf-8")
        self.assertEqual(self.cli("resume-status", run)["state"], "source-drift")
        self.cli("event", run, "filing-skipped", success=False)
        self.assertEqual((Path(run) / "run.jsonl").read_bytes(), before)
        legacy = self.root / ".codearbiter/reports/legacy"
        legacy.mkdir()
        (legacy / "run.jsonl").write_text('{"schema":"run/v1","event":"report-written"}\n', encoding="utf-8")
        self.assertEqual(self.cli("resume-status", str(legacy))["state"], "legacy-unbound")
        self.assertEqual(len(self.cli("read-run", str(legacy))["events"]), 1)

    def test_design_discussion_receipt_survives_resume_without_defect_eligibility(self):
        for name in ("schemas", "report", "issue-filing"):
            self.assertIn("discussion_refs", resource(name))
        finding = example("finding-record", "finding/v1")
        decision = example("schemas", "triage/v1")
        finding.update(claim_type="design-choice", severity="medium", requires_verification=False)
        decision.update(decision="decision-required", final_severity="medium")
        run = self.cli("start")["run_dir"]
        args = ("triage", run, "--finding", json.dumps(finding))
        self.cli(*args, "--record", json.dumps(decision))
        self.cli("event", run, "report-written")
        decision["issue_ref"] = "https://example.invalid/issues/discussion"
        self.cli(*args, "--record", json.dumps(decision), success=False)
        receipt = {"discussion_refs": [{"id": finding["id"], "url": decision["issue_ref"],
                    "root_cause_key": finding["root_cause_key"], "dedup_key": finding["dedup_key"]}]}
        self.cli("event", run, "issues-filed", "--data", json.dumps({"detail": receipt}))
        status = self.cli("resume-status", run)
        self.assertEqual(status["filing"], "issues-filed")
        self.assertTrue(status["can_resume_follow_up"])
        history = self.cli("read-run", run)
        self.assertEqual(history["events"][-1]["detail"], receipt)
        self.cli("event", run, "issues-filed", "--data", json.dumps({"detail": receipt}), success=False)


class WorkflowContract(unittest.TestCase):
    def test_assignment_has_bounded_scopes_verifier_and_no_execution_tools(self):
        text = (SURFACE / "agents/tribunal-lens-reviewer.md").read_text(encoding="utf-8")
        tools = re.search(r"^tools: (.+)$", text, re.M).group(1).split(", ")
        self.assertEqual(tools, ["Read", "Grep", "Glob", "Write"])
        for field in ("MODE:", "Finding scope:", "Evidence scope:", "Source binding:",
                      "Trusted bundle:", "Permitted expansion:", "Packet:",
                      "Findings dir:", "Pending leads dir:", "Verification dir:"):
            self.assertIn(field, text)
        for obligation in ("candidate repository copies", "untrusted evidence", "disprove", "verification/v1"):
            self.assertIn(obligation, text)
        self.assertNotIn("Exposure section", text)
        self.assertIn("Exposure metric", text)

    def test_mappers_classify_only_unresolved_semantics_and_cannot_self_authorize(self):
        for name in ("map-structure", "map-deps"):
            text = (SURFACE / "agents" / (name + ".md")).read_text(encoding="utf-8")
            with self.subTest(mapper=name):
                self.assertNotIn("Bash", text)
                for obligation in ("inventory.json", "unresolved", "bounded packet", "untrusted evidence",
                                   "cannot grant", "candidate repository copies"):
                    self.assertIn(obligation, text)
                self.assertNotIn("git log --since", text)

    def test_lifecycle_and_serious_claim_contracts_remove_old_shortcuts(self):
        skill = (TRIBUNAL / "SKILL.md").read_text(encoding="utf-8")
        triage = resource("triage")
        for obsolete in ("Younger than 7 days", "skip the estimate", "AI-authorship markers",
                         "high-iteration areas", "RUN_ID` = `<UTC-date>"):
            self.assertNotIn(obsolete, skill)
        for command in ("resume-status", "inventory", "start", "eligibility", "triage", "lead", "event"):
            self.assertIn("`" + command + "`", skill)
        self.assertNotIn("Optional for criticals", triage)
        self.assertNotIn("Severity priors", triage)
        serious_row = next(line for line in triage.splitlines() if line.startswith("| critical / high |"))
        self.assertIn("verify-required", serious_row)
        for name in ("triage", "report", "issue-filing"):
            self.assertIn("plan_eligible" if name != "issue-filing" else "filing_eligible", resource(name))
        for obligation in ("independent caller authorization", "source, command, and working directory",
                           "search universe", "finding_scope", "evidence_scope"):
            self.assertIn(obligation, skill)

    def test_telemetry_keeps_tag_consent_but_excludes_new_source_identity(self):
        text = resource("telemetry")
        self.assertIn("--tag <label>", text)
        self.assertIn("explicit per-run authorization", text)
        self.assertIn("source fingerprints", text)
        self.assertIn("never auto-populate", text)
        # Inspect the published payload's actual keys, not just a privacy promise.
        blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
        payload = re.sub(r"{{IF:[^}]+}}.*?{{END}}", "", blocks[0], flags=re.S)
        value = json.loads(payload)
        prohibited = {"source_digest", "fingerprint", "repository", "repository_root", "head", "paths", "evidence"}
        self.assertFalse(prohibited & set(value))
        self.assertNotIn('"opus"', payload)
        self.assertEqual(value["schema"], "telemetry/v1")


if __name__ == "__main__":
    unittest.main()
