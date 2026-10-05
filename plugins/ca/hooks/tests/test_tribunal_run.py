"""Behavioral obligations for SPEC-TRIBUNAL-VNEXT-001 / T-01.

AC01/02: fingerprint bytes, index, HEAD, scope, target, own-output and untracked.
AC03: exclusive allocation preserves forced collisions.
AC04/05: report resumes only follow-ups; dispositions gate terminal completion.
AC06: durable leads and append-only dispositions survive process recreation.
AC07/08: cross-lens root identity and factual uncertainty/design separation.
AC27/28: independently verified serious work only; no refuted filing.
AC32/33: legacy read-only history and issue references remain intact.
AC37: real Git, hostile config, malformed input, containment and CLI exercise.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / "core" / "pysrc" / "_tribunalrunlib.py"
CLI = SOURCE.with_name("tribunal.py")
sys.path.insert(0, str(SOURCE.parent))


def load_library():
    spec = importlib.util.spec_from_file_location("tribunal_run_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = load_library()


def finding(**updates):
    value = {
        "schema": "finding/v1", "id": "reliability-001", "lens": "reliability",
        "title": "Preserve queued writes", "category": "reliability",
        "severity": "high", "confidence": 0.9, "observed": True,
        "locations": [{"path": "src/app.py", "lines": "2-4"}],
        "evidence": "The second writer replaces the first writer's queued state.",
        "impact": "Queued work is lost.", "recommendation": "Serialize mutation.",
        "dedup_key": "reliability:src/app.py:queued-writes",
        "created_at": "2026-10-05T12:00:00Z",
    }
    value.update(updates)
    return value


def triage(**updates):
    value = {
        "schema": "triage/v1", "id": "reliability-001", "decision": "keep",
        "final_severity": "high", "final_confidence": 0.9,
        "counter_argument": "The caller might serialize; tracing shows it does not.",
        "rationale": "The boundary trace establishes a lost update.",
        "decided_at": "2026-10-05T12:00:00Z",
    }
    value.update(updates)
    return value


def verification(outcome="confirmed", **updates):
    value = {
        "schema": "verification/v1", "id": "reliability-001",
        "outcome": outcome, "evidence": "Independent trace confirms ownership.",
        "verification_independence": "independent",
    }
    value.update(updates)
    return value


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q")
        self.git("config", "user.name", "Tribunal fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("src/app.py", b"print('reviewed')\n")
        self.write("outside.txt", b"outside scope\n")
        self.write(".gitignore", b"ignored.txt\n")
        self.git("add", "--", ".")
        self.git("-c", "core.hooksPath=" + os.devnull, "commit", "-qm", "fixture", "--no-gpg-sign")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, env=self.env,
                                capture_output=True, check=True, shell=False)
        return result.stdout.decode("utf-8").strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def success(self, value):
        self.assertTrue(value.get("ok"), value)
        return value

    def start(self, **kwargs):
        return Path(self.success(run.start_run(self.root, **kwargs))["run_dir"])

    def fingerprint(self, **kwargs):
        return self.success(run.source_fingerprint(self.root, **kwargs))["fingerprint"]

    def test_fingerprint_binds_bytes_index_and_root(self):
        initial = self.fingerprint()
        self.assertTrue(initial["clean"])
        self.assertEqual(initial["head"], self.git("rev-parse", "HEAD"))
        self.assertEqual(initial["scope"], ".")
        self.assertEqual(len(initial["digest"]), 64)
        self.write("src/app.py", b"print('staged')\n")
        dirty = self.fingerprint()
        self.assertFalse(dirty["clean"])
        self.assertNotEqual(initial["digest"], dirty["digest"])
        self.git("add", "--", "src/app.py")
        staged = self.fingerprint()
        self.write("src/app.py", b"print('reviewed')\n")
        worktree_restored = self.fingerprint()
        self.assertNotEqual(dirty["index_digest"], staged["index_digest"])
        self.assertNotEqual(initial["digest"], worktree_restored["digest"])
        self.assertEqual(staged["index_digest"], worktree_restored["index_digest"])
        self.assertNotEqual(staged["worktree_digest"], worktree_restored["worktree_digest"])

    def test_scope_ignores_unreviewed_files_and_target_changes_binding(self):
        first = self.fingerprint(scope="src", target_digest="a" * 64)
        self.write("outside.txt", b"not reviewed\n")
        self.assertEqual(first, self.fingerprint(scope="./src/", target_digest="a" * 64))
        self.assertNotEqual(first["digest"], self.fingerprint(scope="src", target_digest="b" * 64)["digest"])
        self.assertFalse(run.source_fingerprint(self.root, scope="../elsewhere")["ok"])
        self.assertFalse(run.source_fingerprint(self.root, target_digest="bad")["ok"])

    def test_declared_external_evidence_is_bound_without_widening_finding_scope(self):
        folder = self.start(scope="src", evidence_paths=["outside.txt"])
        binding = json.loads((folder / "source.json").read_text(encoding="utf-8"))["fingerprint"]
        self.assertEqual(binding["scope"], "src")
        self.assertEqual(binding["evidence_paths"], ["outside.txt"])
        self.assertEqual(run.resume_status(self.root, folder)["state"], "audit")
        self.write("outside.txt", b"changed reviewed caller\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")

    def test_declared_evidence_must_name_represented_inputs(self):
        self.write("ignored.txt", b"contract = allow\n")
        self.write("unselected.txt", b"not selected for review\n")
        for evidence in ("ignored.txt", "missing.txt", "src", "unselected.txt"):
            with self.subTest(evidence=evidence):
                result = run.start_run(self.root, scope="src", evidence_paths=[evidence], reviewed_untracked=[])
                self.assertEqual(result, {"ok": False, "error": "evidence-input-unavailable"})
        self.write("ignored.txt", b"contract = deny\n")
        self.assertEqual(run.start_run(self.root, scope="src", evidence_paths=["ignored.txt"]),
                         {"ok": False, "error": "evidence-input-unavailable"})

    def test_source_drift_rejects_persistent_writes_without_changing_records(self):
        folder = self.start(scope="src")
        lead = {"schema": "lead/v1", "id": "reliability-001", "source_lens": "reliability",
                "target_lens": "appsec", "locations": [{"path": "src/app.py", "lines": "1"}],
                "observation": "Caller identity may be lost.", "reason": "Auth owner not yet traced.",
                "created_at": "2026-10-05T12:00:00Z", "disposition": "open"}
        self.success(run.write_lead(self.root, folder, lead))
        self.success(run.dispose_lead(self.root, folder, lead["id"], "routed", "Appsec owns trace."))
        self.success(run.append_triage(self.root, folder, finding(), triage(), verification()))

        def records():
            return {path.relative_to(folder).as_posix(): path.read_bytes()
                    for path in folder.rglob("*") if path.is_file()}

        before = records()
        self.write("src/app.py", b"changed reviewed source\n")
        operations = [
            ("event", lambda: run.append_event(self.root, folder, "lens-completed", lens="reliability")),
            ("new lead", lambda: run.write_lead(self.root, folder, dict(lead, id="reliability-002"))),
            ("lead disposition", lambda: run.dispose_lead(self.root, folder, lead["id"], "dismissed", "Trace complete.")),
            ("triage", lambda: run.append_triage(self.root, folder, finding(), triage(), verification())),
        ]
        for name, operation in operations:
            with self.subTest(operation=name):
                self.assertEqual(operation(), {"ok": False, "error": "run-not-writable"})
                self.assertEqual(records(), before)

    def test_populated_gitlink_binds_child_source_and_rejects_child_drift(self):
        child = self.root / "child"
        self.git("clone", "-q", "--no-hardlinks", str(self.root), str(child))
        child_head = self.git("rev-parse", "HEAD")
        self.git("update-index", "--add", "--cacheinfo", "160000," + child_head + ",child")
        self.git("-c", "core.hooksPath=" + os.devnull, "commit", "-qm", "gitlink", "--no-gpg-sign")
        folder = self.start()
        subtree = self.fingerprint(scope="child/src")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "audit")
        (child / "src/app.py").write_bytes(b"changed child source\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")
        self.assertNotEqual(subtree["digest"], self.fingerprint(scope="child/src")["digest"])

    def test_malformed_nested_binding_is_a_refusal_without_traceback(self):
        folder = self.start()
        path = folder / "source.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        fp = value["fingerprint"]
        fp["repository"] = []
        fp["digest"] = hashlib.sha256(json.dumps({key: entry for key, entry in fp.items() if key != "digest"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        path.write_text(json.dumps(value), encoding="utf-8")
        result = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), "resume-status", str(folder)], capture_output=True, text=True, shell=False)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_cli_rejects_reserved_event_arguments_without_traceback(self):
        folder = self.start()
        result = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), "event", str(folder), "report-written", "--data", '{"event":"run-completed"}'], capture_output=True, text=True, shell=False)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_own_output_is_stable_but_historical_reports_and_new_inputs_drift(self):
        self.write(".codearbiter/reports/old/report.md", b"historical evidence\n")
        folder = self.start()
        before = (folder / "source.json").read_bytes()
        (folder / "report.md").write_text("generated output", encoding="utf-8")
        self.success(run.append_event(self.root, folder, "lens-completed", lens="reliability"))
        self.assertEqual(self.success(run.resume_status(self.root, folder))["state"], "audit")
        self.assertEqual(before, (folder / "source.json").read_bytes())
        self.write(".codearbiter/reports/old/report.md", b"changed evidence\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")

    def test_selected_untracked_and_ignored_inputs(self):
        self.write("src/reviewed.txt", b"reviewed untracked\n")
        folder = self.start(reviewed_untracked=["src/reviewed.txt"])
        self.write("ignored.txt", b"ignored\n")
        self.write("unselected.txt", b"not selected\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "audit")
        self.write("src/reviewed.txt", b"changed same selected input\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")
        self.assertFalse(run.start_run(self.root, reviewed_untracked=["ignored.txt"])["ok"])

    def test_new_untracked_default_and_index_deletion_invalidate_resume(self):
        folder = self.start()
        self.write("new.txt", b"new reviewed input\n")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")
        (self.root / "new.txt").unlink()
        self.git("rm", "--cached", "--", "src/app.py")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")

    def test_head_scope_target_and_cross_repository_resume_are_rejected(self):
        folder = self.start(target_digest="a" * 64)
        self.assertEqual(run.resume_status(self.root, folder, scope="src")["state"], "source-drift")
        self.assertEqual(run.resume_status(self.root, folder, target_digest="b" * 64)["state"], "source-drift")
        self.git("-c", "core.hooksPath=" + os.devnull, "commit", "--allow-empty", "-qm", "head changed", "--no-gpg-sign")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "source-drift")
        other = Path(self.temp.name) / "other"
        other.mkdir()
        result = run.resume_status(other, folder)
        self.assertFalse(result.get("can_resume_audit", False))
        self.assertFalse(result["ok"])

    def test_exclusive_allocation_retries_collision_without_modifying_history(self):
        reports = self.root / ".codearbiter" / "reports"
        reports.mkdir(parents=True)
        old = reports / "20261005T120000000000Z-all-00000000"
        old.mkdir()
        (old / "report.md").write_bytes(b"keep this exact prior report")
        with mock.patch.object(run, "_new_run_id", side_effect=[old.name, "20261005T120000000000Z-all-11111111"]):
            fresh = self.start()
        self.assertNotEqual(fresh, old)
        self.assertEqual((old / "report.md").read_bytes(), b"keep this exact prior report")
        self.assertEqual(list(old.iterdir()), [old / "report.md"])

    def test_report_followup_dispositions_and_terminal_state(self):
        folder = self.start(detail={"waves": [["reliability"], ["appsec"]]})
        self.success(run.append_event(self.root, folder, "wave-triaged", wave=1))
        self.success(run.append_event(self.root, folder, "report-written"))
        status = self.success(load_library().resume_status(self.root, folder))
        self.assertEqual(status["state"], "follow-up")
        self.assertFalse(status["can_resume_audit"])
        self.assertTrue(status["can_resume_follow_up"])
        self.assertFalse(run.append_event(self.root, folder, "lens-launched", lens="appsec")["ok"])
        self.assertFalse(run.append_event(self.root, folder, "run-completed")["ok"])
        self.success(run.append_event(self.root, folder, "filing-skipped", detail="Owner skipped filing."))
        self.assertFalse(run.append_event(self.root, folder, "run-completed")["ok"])
        self.success(run.append_event(self.root, folder, "telemetry-skipped", detail="No opt-in."))
        self.success(run.append_event(self.root, folder, "run-completed"))
        self.assertEqual(run.resume_status(self.root, folder)["state"], "terminal")
        self.assertFalse(run.append_event(self.root, folder, "run-aborted")["ok"])

    def test_abort_is_terminal_and_malformed_or_rebound_logs_cannot_resume(self):
        folder = self.start()
        self.success(run.append_event(self.root, folder, "run-aborted", detail="Owner stopped."))
        self.assertEqual(run.resume_status(self.root, folder)["state"], "terminal")
        folder = self.start()
        with (folder / "run.jsonl").open("ab") as handle:
            handle.write(b'{"event":')
        self.assertEqual(run.resume_status(self.root, folder)["state"], "invalid")
        folder = self.start()
        source = json.loads((folder / "source.json").read_text(encoding="utf-8"))
        source["fingerprint"]["head"] = "0" * 40
        (folder / "source.json").write_text(json.dumps(source), encoding="utf-8")
        self.assertEqual(run.resume_status(self.root, folder)["state"], "invalid")

    def test_durable_leads_append_disposition_and_cannot_overwrite_or_escape(self):
        folder = self.start()
        lead = {"schema": "lead/v1", "id": "reliability-001", "source_lens": "reliability",
                "target_lens": "appsec", "locations": [{"path": "src/app.py", "lines": "1"}],
                "observation": "Caller identity may be lost.", "reason": "Auth owner not yet traced.",
                "created_at": "2026-10-05T12:00:00Z", "disposition": "open"}
        self.success(run.write_lead(self.root, folder, lead))
        path = folder / "leads" / "reliability" / "reliability-001.json"
        original = path.read_bytes()
        self.assertFalse(run.write_lead(self.root, folder, lead)["ok"])
        self.success(run.dispose_lead(self.root, folder, lead["id"], "routed", "Appsec owns trace."))
        prefix = (folder / "lead-dispositions.jsonl").read_bytes()
        self.success(run.dispose_lead(self.root, folder, lead["id"], "dismissed", "Middleware preserves identity."))
        self.assertTrue((folder / "lead-dispositions.jsonl").read_bytes().startswith(prefix))
        leads = self.success(load_library().read_leads(self.root, folder))["leads"]
        self.assertEqual(leads[0]["disposition"], "dismissed")
        self.assertEqual(len(leads[0]["disposition_history"]), 2)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(run.write_lead(self.root, folder, dict(lead, id="../escape"))["ok"])

    def test_legacy_history_is_readable_without_rewriting_issue_references(self):
        folder = self.root / ".codearbiter/reports/2026-07-01-all"
        folder.mkdir(parents=True)
        old = b'{"schema":"run/v1","event":"run-started","detail":"legacy"}\n'
        (folder / "run.jsonl").write_bytes(old)
        decisions = b'{"schema":"triage/v1","id":"reliability-001","issue_ref":"https://github.com/example/repo/issues/1"}\n'
        (folder / "triage.jsonl").write_bytes(decisions)
        status = self.success(run.resume_status(self.root, folder))
        self.assertEqual(status["state"], "legacy-unbound")
        history = self.success(run.read_run(self.root, folder))
        self.assertEqual(history["triage"][0]["issue_ref"], "https://github.com/example/repo/issues/1")
        self.assertFalse(run.append_event(self.root, folder, "lens-launched")["ok"])
        self.assertEqual(old, (folder / "run.jsonl").read_bytes())
        self.assertEqual(decisions, (folder / "triage.jsonl").read_bytes())

    def test_triage_append_preserves_original_issue_reference_and_root_identity(self):
        folder = self.start()
        candidate = finding(root_cause_key="state:queue:lost-update", corroborates=["appsec-002"], related_lenses=["appsec"])
        self.success(run.append_triage(self.root, folder, candidate, triage(), verification()))
        prefix = (folder / "triage.jsonl").read_bytes()
        decision = triage(issue_ref="https://github.com/example/repo/issues/1")
        self.success(run.append_triage(self.root, folder, candidate, decision, verification()))
        self.assertTrue((folder / "triage.jsonl").read_bytes().startswith(prefix))
        entries = self.success(run.read_run(self.root, folder))["triage"]
        self.assertEqual(entries[-1]["issue_ref"], decision["issue_ref"])
        self.assertEqual(entries[-1]["root_cause_key"], candidate["root_cause_key"])
        self.assertFalse(run.append_triage(self.root, folder, candidate, decision, verification("refuted"))["ok"])

    def test_git_config_cannot_run_diff_filter_fsmonitor_or_shell_payloads(self):
        sentinel = Path(self.temp.name) / "executed.txt"
        executable = Path(self.temp.name) / "hostile.py"
        executable.write_text("from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('executed')\n", encoding="utf-8")
        command = '"' + sys.executable.replace("\\", "/") + '" "' + str(executable).replace("\\", "/") + '"'
        for key in ["core.fsmonitor", "diff.external", "diff.hostile.textconv", "filter.hostile.clean"]:
            self.git("config", key, command)
        self.write(".gitattributes", b"*.py diff=hostile filter=hostile\n")
        self.write("src/app.py", b"changed\n")
        self.success(run.source_fingerprint(self.root))
        self.assertFalse(sentinel.exists())

    def test_selected_git_identity_is_not_silently_ignored(self):
        self.assertTrue(run.source_fingerprint(self.root)["ok"])
        with mock.patch.dict(os.environ, {"CODEARBITER_GIT_EXECUTABLE": str(self.root / "missing-git.exe")}):
            result = run.source_fingerprint(self.root)
        self.assertFalse(result["ok"])

    def test_symlink_contents_never_read_external_bytes(self):
        external = Path(self.temp.name) / "outside-secret.txt"
        external.write_bytes(b"external original")
        link = self.root / "src/link.txt"
        try:
            link.symlink_to(external)
        except (OSError, NotImplementedError):
            # Windows without link privilege: a directory junction still exercises containment.
            target = Path(self.temp.name) / "external-dir"
            target.mkdir()
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, shell=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(lambda: link.rmdir() if link.exists() else None)
            self.assertFalse(run.source_fingerprint(self.root, scope="src/link.txt")["ok"])
        else:
            before = self.fingerprint()
            external.write_bytes(b"changed outside source")
            self.assertEqual(before, self.fingerprint())
            self.assertFalse(run.source_fingerprint(self.root, scope="src/link.txt/child")["ok"])

    def test_cli_start_resume_event_lead_and_triage_are_local_json_operations(self):
        def command(*args):
            result = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args], capture_output=True, text=True, shell=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return self.success(json.loads(result.stdout))
        started = command("start", "--scope", "src")
        folder = started["run_dir"]
        self.assertEqual(command("resume-status", folder)["state"], "audit")
        command("triage", folder, "--finding", json.dumps(finding()), "--record", json.dumps(triage()), "--verification", json.dumps(verification()))
        command("event", folder, "report-written")
        self.assertEqual(command("resume-status", folder)["state"], "follow-up")
        invalid = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), "event", folder, "run-completed"], capture_output=True, text=True, shell=False)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse(json.loads(invalid.stdout)["ok"])


class FindingEligibilityTests(unittest.TestCase):
    def test_legacy_finding_and_additive_cross_lens_identity(self):
        original = finding()
        self.assertTrue(run.validate_finding(original)["ok"])
        shared = "state:queue:lost-update"
        a = finding(root_cause_key=shared, related_lenses=["appsec"], corroborates=["appsec-002"])
        b = finding(id="appsec-002", lens="appsec", root_cause_key=shared, related_lenses=["reliability"])
        first = run.triage_eligibility(a, triage(), verification())
        second = run.triage_eligibility(b, triage(id="appsec-002", decision="combine"), verification(id="appsec-002"))
        self.assertTrue(first["filing_eligible"])
        self.assertEqual(first["root_cause_key"], second["root_cause_key"])
        self.assertEqual(a["lens"], "reliability")
        self.assertEqual(b["lens"], "appsec")
        self.assertEqual(original, finding())

    def test_uncertainty_does_not_become_design_decision(self):
        uncertain = run.triage_eligibility(finding(confidence=0.4), triage(decision="decision-required"))
        self.assertFalse(uncertain["ok"])
        actual_design = run.triage_eligibility(finding(claim_type="design-choice", severity="medium"), triage(decision="decision-required", final_severity="medium"))
        self.assertTrue(actual_design["ok"])
        self.assertFalse(actual_design["filing_eligible"])

    def test_serious_candidates_require_independent_confirmation_or_narrowing(self):
        for outcome in [None, "inconclusive", "refuted", "confirmed", "narrowed"]:
            with self.subTest(outcome=outcome):
                result = run.triage_eligibility(finding(), triage(), verification(outcome) if outcome else None)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["filing_eligible"], outcome in {"confirmed", "narrowed"})
                self.assertEqual(result["plan_eligible"], outcome in {"confirmed", "narrowed"})
        limited = run.triage_eligibility(finding(), triage(), verification(verification_independence="limited"))
        self.assertFalse(limited["filing_eligible"])
        promoted = run.triage_eligibility(finding(severity="medium"), triage(final_severity="critical"))
        self.assertFalse(promoted["filing_eligible"])
        downgraded = run.triage_eligibility(finding(), triage(final_severity="low"))
        self.assertFalse(downgraded["filing_eligible"])

    def test_malformed_records_cannot_claim_verification_or_filing(self):
        valid = run.triage_eligibility(finding(), triage(), verification())
        self.assertTrue(valid["filing_eligible"])
        malformed = [None, [], {}, finding(confidence=float("nan")), finding(locations=[]), finding(corroborates="appsec-002")]
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                self.assertFalse(run.validate_finding(candidate)["ok"])
        for bad in [verification(id="wrong-001"), verification(outcome="yes"), verification(evidence=""), {"outcome": "confirmed"}]:
            with self.subTest(verification=bad):
                self.assertFalse(run.triage_eligibility(finding(), triage(), bad)["ok"])


if __name__ == "__main__":
    unittest.main()
