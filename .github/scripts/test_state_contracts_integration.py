"""P-02 admission negatives use a real disposable Git history, not product claims."""
import copy
import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

import check_state_contracts_integration as owner

REPO = Path(os.environ.get("CODEARBITER_TEST_SOURCE_REPO", Path(__file__).resolve().parents[2]))
SOURCE = subprocess.run(["git", "--no-lazy-fetch", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, check=True).stdout.decode().strip()
C = owner.CORPUS


class IntegrationIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_blobs = {}
        cls.tmp = tempfile.TemporaryDirectory(prefix="ca-integration-ledger-fixture-")
        cls.repo = Path(cls.tmp.name)
        def git(*args):
            return subprocess.run(["git", *args], cwd=cls.repo, capture_output=True, check=True).stdout.decode().strip()
        cls.git = staticmethod(git)
        git("init", "-q")
        git("config", "user.name", "Disposable integrity fixture")
        git("config", "user.email", "fixture@example.invalid")
        def put(path, data):
            p = cls.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
        cls.put = staticmethod(put)
        def original(path):
            return subprocess.run(["git", "show", SOURCE + ":" + path], cwd=REPO, capture_output=True, check=True).stdout
        manifest = json.loads(original(C + "MANIFEST.json"))
        put(C + "MANIFEST.json", original(C + "MANIFEST.json"))
        for entry in manifest["files"]:
            put(C + entry["path"], original(C + entry["path"]))
        cls.input = "plugins/ca-pi/tools/test/setup-disposable-home.ts"
        put(cls.input, original(cls.input))
        put(C + "execution/tools/coverage_ledger.py", original(C + "execution/tools/coverage_ledger.py"))
        cls.progress = json.loads(original(C + "execution/progress.json"))
        put(C + "execution/progress.json", cls.progress)
        cls.ledger = json.loads(original(C + "execution/coverage-ledger.json"))
        for group in ("findings", "machines", "transitions", "added_transitions"):
            for row in cls.ledger[group].values():
                row.update(status="PLANNED", evidence=[])
        put(C + "execution/coverage-ledger.json", cls.ledger)
        git("add", ".")
        git("commit", "-qm", "Original partial program fixture")
        cls.tested = git("rev-parse", "HEAD")
        cls.identity = "pi-qualification:disposable-home:01"
        cls.cell = "disposition:transitions:" + cls.identity
        cls.raw_path = "retained/raw.txt"
        put(cls.raw_path, b"explicit test fixture raw observation\n")
        cls.proof_path = "retained/proof.json"
        cls.proof = {"schema": "codearbiter-disposition-evidence/1", "source_commit": cls.tested,
            "kind": "test", "result": "PASSED", "producer": {"class": "local-host", "identity": "explicit admission test fixture"},
            "inputs": {cls.input: hashlib.sha256(original(cls.input)).hexdigest()}, "disposition_ids": [cls.cell],
            "raw_evidence": [{"path": cls.raw_path, "sha256": hashlib.sha256((cls.repo / cls.raw_path).read_bytes()).hexdigest()}],
            "commands": [{"argv": ["python", "fixture.py"], "exit_code": 0}]}
        put(cls.proof_path, cls.proof)
        cls.claimed = copy.deepcopy(cls.ledger)
        cls.claimed["transitions"][cls.identity].update(status="TESTED", evidence=[{"kind": "test", "commit": cls.tested,
            "ref": cls.proof_path, "sha256": hashlib.sha256((cls.repo / cls.proof_path).read_bytes()).hexdigest()}])
        put(C + "execution/coverage-ledger.json", cls.claimed)
        git("add", ".")
        git("commit", "-qm", "Retain original proof")
        cls.current = git("rev-parse", "HEAD")
        put(cls.input, b"changed current owner bytes\n")
        git("add", ".")
        git("commit", "-qm", "Current inputs change without rewriting history")
        cls.stale = git("rev-parse", "HEAD")
        git("rm", "-q", cls.input)
        git("commit", "-qm", "Current input unavailable")
        cls.unavailable = git("rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def load(self, commit, path):
        key = (commit, path)
        if key in self.overrides:
            return self.overrides[key]
        if key not in self.original_blobs:
            self.original_blobs[key] = owner.readiness.blob(self.repo, commit, path)
        return self.original_blobs[key]

    def setUp(self):
        self.overrides = {}

    def check(self, source=None):
        return owner.validate(self.repo, source or self.current, self.load)

    def replace_ledger(self, ledger):
        self.overrides[self.current, C + "execution/coverage-ledger.json"] = json.dumps(ledger).encode()

    def test_planned_and_implemented_partial_program_pass_without_publication(self):
        ledger = copy.deepcopy(self.ledger)
        row = ledger["transitions"][self.identity]
        row.update(status="IMPLEMENTED", evidence=[{"kind": "review", "commit": self.tested, "ref": self.input}])
        self.replace_ledger(ledger)
        report = self.check()
        self.assertEqual(report["result"], "PASSED")
        self.assertFalse(report["product_qualification"])
        self.assertEqual(report["publication_readiness"], "NOT_ASSESSED")

    def test_original_proof_passes_and_records_applicable(self):
        self.assertEqual(self.check()["current_applicability"][self.cell]["status"], "APPLICABLE")

    def test_stale_history_passes_integration_but_strict_publication_refuses(self):
        report = self.check(self.stale)
        self.assertEqual(report["current_applicability"][self.cell]["status"], "STALE")
        self.assertFalse(report["recorded_statuses_changed"])
        row = self.claimed["transitions"][self.identity]
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            owner.readiness.authenticate_disposition(self.repo, self.stale, self.cell, row, {self.input}, self.load, {})

    def test_unavailable_current_input_is_unknown_not_passed_applicability(self):
        self.assertEqual(self.check(self.unavailable)["current_applicability"][self.cell]["status"], "UNKNOWN")

    def test_changed_original_raw_proof_refuses_even_when_current_source_stale(self):
        self.overrides[self.stale, self.raw_path] = b"forged retained observation"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            self.check(self.stale)

    def test_changed_original_input_refuses_even_when_current_source_stale(self):
        self.overrides[self.tested, self.input] = b"forged original input"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            self.check(self.stale)

    def test_frozen_intake_changed_bytes_refuse(self):
        self.overrides[self.current, C + "PROGRAM.md"] = b"changed frozen contract"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "frozen intake identity"):
            self.check()

    def test_rehashed_frozen_file_and_manifest_cannot_rebaseline(self):
        original_manifest = json.loads(self.load(self.current, C + "MANIFEST.json"))
        replacement = b"rewritten frozen program contract"
        entry = next(x for x in original_manifest["files"] if x["path"] == "PROGRAM.md")
        entry.update(bytes=len(replacement), sha256=hashlib.sha256(replacement).hexdigest())
        self.overrides[self.current, C + "PROGRAM.md"] = replacement
        self.overrides[self.current, C + "MANIFEST.json"] = json.dumps(original_manifest).encode()
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "accepted frozen intake manifest identity"):
            self.check()

    def test_missing_and_extra_population_refuse(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                ledger = copy.deepcopy(self.ledger)
                if missing:
                    ledger["transitions"].pop(self.identity)
                else:
                    ledger["transitions"]["extra"] = copy.deepcopy(ledger["transitions"][self.identity])
                self.replace_ledger(ledger)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "population differs"):
                    self.check()

    def test_unknown_owner_status_task_and_bad_reference_refuse(self):
        mutations = [("owner", "invented"), ("status", "DONE"), ("task_ids", ["XX-99"]),
                     ("evidence", [{"kind": "test", "commit": self.tested, "ref": "../escape"}])]
        for field, value in mutations:
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.claimed)
                ledger["transitions"][self.identity][field] = value
                self.replace_ledger(ledger)
                with self.assertRaises(owner.readiness.ReadinessError):
                    self.check()

    def test_missing_commands_and_scope_refuse(self):
        for field in ("commands", "disposition_ids"):
            with self.subTest(field=field):
                proof = copy.deepcopy(self.proof)
                proof[field] = []
                encoded = json.dumps(proof).encode()
                self.overrides[self.current, self.proof_path] = encoded
                ledger = copy.deepcopy(self.claimed)
                ledger["transitions"][self.identity]["evidence"][0]["sha256"] = hashlib.sha256(encoded).hexdigest()
                self.replace_ledger(ledger)
                with self.assertRaises(owner.readiness.ReadinessError):
                    self.check()

    def claim_with_raw_origin(self, producer_class, hosted_field):
        proof = copy.deepcopy(self.proof)
        proof["producer"]["class"] = producer_class
        proof["raw_evidence"][0][hosted_field] = 1
        if producer_class == "hosted":
            # This is the reported bypass: one marker satisfied the hosted
            # class while the valid local path avoided every API observation.
            proof["raw_evidence"][0]["run_id"] = 1
        encoded = json.dumps(proof).encode()
        self.overrides[self.current, self.proof_path] = encoded
        ledger = copy.deepcopy(self.claimed)
        ledger["transitions"][self.identity]["evidence"][0]["sha256"] = hashlib.sha256(encoded).hexdigest()
        self.replace_ledger(ledger)
        return ledger["transitions"][self.identity]

    def test_hosted_claim_cannot_borrow_valid_local_raw_path(self):
        for field in ("run_id", "job_id", "artifact_id"):
            with self.subTest(field=field):
                self.claim_with_raw_origin("hosted", field)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "mixed original raw evidence origin"):
                    self.check()

    def test_publication_rejects_hosted_identity_fields_on_local_raw_path(self):
        for field in ("run_id", "job_id", "artifact_id"):
            with self.subTest(field=field):
                row = self.claim_with_raw_origin("local-host", field)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "mixed original raw evidence origin"):
                    owner.readiness.authenticate_disposition(self.repo, self.current, self.cell,
                                                            row, {self.input}, self.load, {})

    def test_added_transition_requires_matching_declared_population(self):
        ledger = copy.deepcopy(self.ledger)
        ledger["added_transitions"]["invented"] = copy.deepcopy(ledger["transitions"][self.identity])
        self.replace_ledger(ledger)
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "population differs"):
            self.check()


class IntegrationWorkflowWiringTest(unittest.TestCase):
    COMMANDS = [
        "python docs/state-contracts-major/execution/tools/coverage_ledger.py check",
        "python .github/scripts/check_state_contracts_integration.py",
        "python .github/scripts/test_state_contracts_integration.py",
    ]

    def workflow(self):
        path = Path(os.environ.get("CODEARBITER_TEST_CI_PATH", REPO / ".github/workflows/ci.yml"))
        return path.read_text(encoding="utf-8")

    def job(self, text, name):
        match = re.search(r"(?ms)^  " + re.escape(name) + r":\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", text)
        self.assertIsNotNone(match, "missing " + name + " job")
        return match.group(1)

    def test_actual_owning_ci_runs_partial_check_for_ledger_only_children(self):
        text = self.workflow()
        hooks_filter = re.search(r"(?ms)^            hooks:\n(.*?)(?=^            [A-Za-z0-9_-]+:|\Z)", text).group(1)
        self.assertNotIn("docs/state-contracts-major/**", hooks_filter)
        job = self.job(text, "program-integrity")
        self.assertIn("    needs: changes\n", job)
        self.assertIn("    if: needs.changes.outputs.program_integrity == 'true'\n", job)
        self.assertIn("      fail-fast: false\n", job)
        self.assertIn("        os: [ubuntu-latest, windows-latest, macos-latest]\n", job)
        self.assertIn("    runs-on: ${{ matrix.os }}\n", job)
        self.assertIn("    timeout-minutes: 5\n", job)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", job)
        self.assertIn("actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", job)
        self.assertIn('python-version: "3.14"', job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("persist-credentials: false", job)
        self.assertNotIn("setup-go@", job)
        self.assertNotIn("build-artifacts.py", job)
        self.assertNotIn("continue-on-error:", job)
        self.assertNotIn("--require-complete", job)
        self.assertEqual(re.findall(r"(?m)^        run: (.*)$", job), self.COMMANDS)
        self.assertEqual(re.findall(r"(?m)^        if: (.*)$", job), [])
        hooks = self.job(text, "hooks")
        self.assertIn("    timeout-minutes: 20\n", hooks)
        for command in self.COMMANDS:
            self.assertNotIn(command, hooks)
        aggregate = self.job(text, "ci-passed")
        self.assertIn("      - program-integrity\n", aggregate)
        required = re.search(r'(?m)^          required_results="([^"\n]*)"$', aggregate).group(1)
        self.assertIn("${{ needs['program-integrity'].result }}", required)
        self.assertIn('program_integrity_required="${{ needs.changes.outputs.program_integrity }}"', aggregate)
        self.assertIn('program_integrity_result="${{ needs[\'program-integrity\'].result }}"', aggregate)

    def test_metadata_only_paths_select_integrity_without_full_hooks(self):
        text = self.workflow()
        def patterns(name):
            match = re.search(r"(?ms)^            " + re.escape(name) + r":\n(.*?)(?=^            [A-Za-z0-9_-]+:|\Z)", text)
            self.assertIsNotNone(match, "missing dedicated " + name + " filter")
            return re.findall(r"(?m)^              - '([^']+)'$", match.group(1))
        program, hooks = patterns("program_integrity"), patterns("hooks")
        self.assertEqual(program, ["docs/state-contracts-major/**", ".github/scripts/check_state_contracts_integration.py",
                                   ".github/scripts/test_state_contracts_integration.py", ".github/scripts/major_readiness.py",
                                   ".github/workflows/ci.yml"])
        for path in ("docs/state-contracts-major/execution/coverage-ledger.json",
                     "docs/state-contracts-major/execution/progress.json"):
            with self.subTest(path=path):
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in program))
                self.assertFalse(any(fnmatch.fnmatchcase(path, pattern) for pattern in hooks))
        self.assertRegex(text, r"(?m)^      program_integrity: \$\{\{ steps\.filter\.outputs\.program_integrity == 'true' ")

    def test_hosted_proof_token_is_step_local_and_job_permissions_are_read_only(self):
        text = self.workflow()
        job = self.job(text, "program-integrity")
        pre = job.split("    steps:\n", 1)[0]
        permissions = re.search(r"(?m)^    permissions:\n((?:      [^\n]+\n)+)", pre).group(1)
        self.assertEqual(permissions, "      contents: read\n      actions: read\n")
        steps = re.split(r"(?m)^      - ", job.split("    steps:\n", 1)[1])[1:]
        consumers = [step for step in steps if "run: python .github/scripts/check_state_contracts_integration.py" in step]
        self.assertEqual(len(consumers), 1)
        self.assertIn("        env:\n          GH_TOKEN: ${{ github.token }}\n", consumers[0])
        for step in steps:
            if step != consumers[0]:
                self.assertNotIn("GH_TOKEN:", step)
        self.assertNotIn("GH_TOKEN:", self.job(text, "hooks"))

    def test_selected_integrity_failure_cancellation_and_skip_refuse_actual_merge_gate(self):
        text = self.workflow()
        self.job(text, "program-integrity")
        aggregate = self.job(text, "ci-passed")
        body = aggregate.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in body.splitlines() if line.startswith("          "))
        import shutil
        bash = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else None
        if bash is None or not bash.is_file():
            found = shutil.which("bash")
            self.assertIsNotNone(found, "supported CI requires Bash for its actual merge gate")
            bash = Path(found)
        for selected, result, expected in [(True, "success", 0), (True, "failure", 1),
                                           (True, "cancelled", 1), (True, "skipped", 1), (True, "", 1),
                                           (False, "skipped", 0)]:
            with self.subTest(selected=selected, result=result):
                def value(match):
                    expression = match.group(1).strip()
                    if expression == "needs.changes.outputs.program_integrity":
                        return "true" if selected else "false"
                    if expression == "needs.changes.outputs.hooks":
                        return "false"  # Ledger-only change: full hooks are unselected.
                    if expression == "needs['program-integrity'].result":
                        return result
                    if expression == "needs.changes.outputs.artifacts":
                        return "false"
                    self.assertTrue(expression.endswith(".result"), expression)
                    return "success"
                actual = re.sub(r"\$\{\{(.*?)\}\}", value, script)
                with tempfile.TemporaryDirectory(prefix="ca-merge-gate-fixture-") as home:
                    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
                    env.update(HOME=home, USERPROFILE=home)
                    process = subprocess.run([str(bash), "--noprofile", "--norc", "-c", actual],
                                             env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(process.returncode, expected, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
