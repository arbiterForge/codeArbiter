#!/usr/bin/env python3
"""Self-tests for the read-only two-phase Pi support verifier."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
VERIFIER = REPO / ".github" / "scripts" / "verify_pi_support.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_pi_support_contract", VERIFIER)
    if spec is None or spec.loader is None:
        raise AssertionError("verifier module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def evidence(mode: str = "preclosure") -> dict:
    rows = []
    for version in ("0.80.5", "0.80.10"):
        rows.append({"version": version, "platform": "windows-local", "architecture": "x64", "resultCode": "PI-LOCAL-SUPPORTED", "passed": True, "timingMs": 10, "diagnosticCode": "NONE"})
        for platform in ("windows", "linux", "macos"):
            rows.append({"version": version, "platform": platform, "architecture": "pending", "resultCode": "PI-HOSTED-PENDING", "passed": False, "timingMs": 0, "diagnosticCode": "HOSTED_PENDING"})
    rows.extend([
        {"version": "codeql", "platform": "github", "architecture": "pending", "resultCode": "PI-CODEQL-PENDING", "passed": False, "timingMs": 0, "diagnosticCode": "HOSTED_PENDING"},
        {"version": "0.80.9", "platform": "windows-local", "architecture": "x64", "resultCode": "PI-LATEST-CANARY", "passed": False, "timingMs": 5, "diagnosticCode": "NONBLOCKING_CANARY"},
    ])
    return {"schema": "codearbiter-pi-promotion-v1", "mode": mode, "commit": None, "rows": rows}


def fixture(root: Path) -> None:
    (root / ".codearbiter" / "plans").mkdir(parents=True)
    (root / "docs" / "reports" / "pi-support").mkdir(parents=True)
    (root / "core" / "surface" / "skills" / "ca-feature").mkdir(parents=True)
    (root / "plugins" / "ca-pi" / "skills" / "ca-feature").mkdir(parents=True)
    tasks = "\n".join(f"### Task {number}: fixture\n\n**Status:** {'ACCEPTED' if number <= 12 else 'IN_PROGRESS'}" for number in range(1, 15))
    obligations = "\n".join(f"| PI-AC-{number:02d} fixture | AC {number} | 1 | {'COVERED' if number <= 34 or number == 36 else 'OPEN'} |" for number in range(1, 39))
    owns = "\n".join(f"**Owns:** PI-AC-{number:02d}" for number in range(1, 39))
    (root / ".codearbiter" / "plans" / "pi-support.md").write_text(obligations + "\n" + tasks + "\n" + owns + "\n", encoding="utf-8")
    bindings = {f"PI-AC-{number:02d}": ["fixture:test"] for number in range(1, 39)}
    shared = root / "core" / "surface" / "skills" / "ca-feature" / "SKILL.md"
    generated = root / "plugins" / "ca-pi" / "skills" / "ca-feature" / "SKILL.md"
    shared.write_text("fixture generated surface\n", encoding="utf-8")
    shutil.copyfile(shared, generated)
    promotion = evidence()
    (root / "docs" / "reports" / "pi-support" / "promotion.json").write_text(json.dumps(promotion), encoding="utf-8")
    (root / "docs" / "reports" / "pi-support" / "promotion.md").write_text(
        load_verifier().render_promotion_markdown(promotion), encoding="utf-8",
    )
    (root / ".pi-support-fixture.json").write_text(json.dumps({
        "branch": "feat/pi-support",
        "bindings": bindings,
        "generatedPairs": [[str(shared.relative_to(root)), str(generated.relative_to(root))]],
        "localChecks": True,
        "runtimeTreeAbsent": True,
        "packageInventoryClean": True,
        "forbiddenDuplicationAbsent": True,
    }), encoding="utf-8")


def run_verifier(root: Path, mode: str = "preclosure") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(VERIFIER), "--root", str(root), "--fixture-mode", "--mode", mode], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


class VerifyPiSupportTest(unittest.TestCase):
    def test_real_gate_plan_includes_public_codex_docs(self):
        module = load_verifier()
        labels = {label for label, _command in module._gate_commands()}
        self.assertIn("public-codex-docs", labels)

    def test_final_hosted_attestation_requires_repo_aggregate(self):
        module = load_verifier()
        expected = {
            f"[CHECK] | [PI  ] | Adapter contract  <os: {os_name} · runtime: Pi {version}>"
            for os_name in ("ubuntu-latest", "windows-latest", "macos-latest")
            for version in ("0.80.5", "0.80.10")
        } | {
            "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>",
            "[GATE ] | [REPO] | Merge readiness",
        }
        self.assertEqual(module.REQUIRED_HOSTED_CHECKS, expected)
        workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            'name: "[CHECK] | [PI  ] | Adapter contract  <os: ${{ matrix.os }} · runtime: Pi ${{ matrix.pi-version }}>"',
            workflow,
        )
        for name in expected - {candidate for candidate in expected if "Adapter contract" in candidate}:
            self.assertIn(f'name: "{name}"', workflow)

    def test_promotion_rejects_extra_rows_and_nonfinite_timing(self):
        module = load_verifier()
        extra = evidence()
        extra["rows"].append({"version": "rogue", "platform": "windows", "architecture": "x64", "resultCode": "ROGUE", "passed": True, "timingMs": 1, "diagnosticCode": "NONE"})
        self.assertFalse(module.strict_promotion(extra, "preclosure")[0])
        poisoned = evidence()
        poisoned["rows"][0]["timingMs"] = float("nan")
        self.assertFalse(module.strict_promotion(poisoned, "preclosure")[0])

    def test_promotion_rejects_private_text_in_every_string_field(self):
        module = load_verifier()
        for field in ("version", "platform", "architecture", "resultCode", "diagnosticCode"):
            poisoned = evidence()
            poisoned["rows"][0][field] = "copied proprietary task instructions from private repository"
            self.assertFalse(module.strict_promotion(poisoned, "preclosure")[0], field)

    def test_final_rejects_pending_hosted_architecture(self):
        module = load_verifier()
        final = evidence("final")
        final["commit"] = "a" * 40
        for row in final["rows"]:
            if row["version"] in {"0.80.5", "0.80.10"} and row["platform"] in {"windows", "linux", "macos"}:
                row.update(resultCode="PI-HOSTED-SUPPORTED", passed=True, timingMs=10, diagnosticCode="NONE")
            elif row["version"] == "codeql":
                row.update(resultCode="PI-CODEQL-HIGH", passed=True, timingMs=10, diagnosticCode="NONE")
        self.assertFalse(module.strict_promotion(final, "final")[0])
        for row in final["rows"]:
            if row["platform"] in {"windows", "linux", "macos"} or row["version"] == "codeql":
                row["architecture"] = "x64"
        self.assertTrue(module.strict_promotion(final, "final")[0])

    def test_promotion_requires_exact_local_and_codeql_states(self):
        module = load_verifier()
        local_pending = evidence()
        local_pending["rows"][0]["architecture"] = "pending"
        self.assertFalse(module.strict_promotion(local_pending, "preclosure")[0])
        local_failed = evidence()
        local_failed["rows"][0]["diagnosticCode"] = "LOCAL_FAILED"
        self.assertFalse(module.strict_promotion(local_failed, "preclosure")[0])
        contradictory_pass = evidence()
        next(row for row in contradictory_pass["rows"] if row["resultCode"] == "PI-LATEST-CANARY").update(
            passed=True, diagnosticCode="VERSION_UNSUPPORTED",
        )
        self.assertFalse(module.strict_promotion(contradictory_pass, "preclosure")[0])
        contradictory_fail = evidence()
        next(row for row in contradictory_fail["rows"] if row["resultCode"] == "PI-LATEST-CANARY").update(
            passed=False, diagnosticCode="NONE",
        )
        self.assertFalse(module.strict_promotion(contradictory_fail, "preclosure")[0])

    def test_hosted_attestation_requires_every_exact_success_on_one_sha(self):
        module = load_verifier()
        commit = "a" * 40
        checks = [
            {"name": name, "head_sha": commit, "status": "completed", "conclusion": "success"}
            for name in module.REQUIRED_HOSTED_CHECKS
        ]
        self.assertTrue(module._hosted_checks_match(checks, commit))
        self.assertFalse(module._hosted_checks_match(checks[:-1], commit))
        checks[0]["conclusion"] = "failure"
        self.assertFalse(module._hosted_checks_match(checks, commit))
        checks[0]["conclusion"] = "success"
        checks[0]["head_sha"] = "b" * 40
        self.assertFalse(module._hosted_checks_match(checks, commit))

    def test_final_commit_must_resolve_as_an_ancestor(self):
        module = load_verifier()
        current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
        self.assertTrue(module._commit_is_ancestor(REPO, current))
        self.assertFalse(module._commit_is_ancestor(REPO, "a" * 40))
        self.assertFalse(module._promotion_commit_is_valid(REPO, {"mode": "final", "commit": "a" * 40}, False))

    def test_final_attested_commit_rejects_later_code_but_allows_evidence_only_descendants(self):
        module = load_verifier()
        with tempfile.TemporaryDirectory(prefix="ca-pi-attestation-") as raw:
            root = Path(raw)
            def git(*args: str) -> str:
                return subprocess.run(
                    ["git", *args], cwd=root, text=True, encoding="utf-8",
                    capture_output=True, check=True,
                ).stdout.strip()
            git("init")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "fixture")
            (root / "seed.txt").write_text("seed\n", encoding="utf-8")
            git("add", "seed.txt"); git("commit", "-m", "seed")
            evidence_commit = git("rev-parse", "HEAD")
            report = root / "docs" / "reports" / "pi-support" / "promotion.json"
            report.parent.mkdir(parents=True)
            report.write_text("{}\n", encoding="utf-8")
            git("add", report.relative_to(root).as_posix()); git("commit", "-m", "evidence")
            self.assertTrue(module._descendant_is_evidence_only(root, evidence_commit))
            sprint_log = root / ".codearbiter" / "sprint-log.md"
            sprint_log.parent.mkdir(parents=True)
            sprint_log.write_text("- decision\n", encoding="utf-8")
            self.assertTrue(module._descendant_is_evidence_only(root, evidence_commit))
            git("add", sprint_log.relative_to(root).as_posix()); git("commit", "-m", "audit evidence")
            self.assertTrue(module._descendant_is_evidence_only(root, evidence_commit))
            (root / "seed.txt").write_text("unstaged code drift\n", encoding="utf-8")
            self.assertFalse(module._descendant_is_evidence_only(root, evidence_commit))
            git("restore", "seed.txt")
            code = root / "plugins" / "ca-pi" / "tools" / "src" / "extension.ts"
            code.parent.mkdir(parents=True)
            code.write_text("export {};\n", encoding="utf-8")
            self.assertFalse(module._descendant_is_evidence_only(root, evidence_commit))
            git("add", code.relative_to(root).as_posix())
            self.assertFalse(module._descendant_is_evidence_only(root, evidence_commit))
            git("commit", "-m", "code drift")
            self.assertFalse(module._descendant_is_evidence_only(root, evidence_commit))

    def test_real_bindings_are_concrete_successful_gate_labels(self):
        module = load_verifier()
        labels = {label for label, _command in module._gate_commands()} | {
            "branch", "statuses", "promotion", "promotion-security", "package-inventory",
            "surface-idempotency", "host-packages-idempotency", "repository-gates",
            "promotion-markdown", "hosted-attestation",
        }
        self.assertEqual(set(module.OBLIGATION_BINDINGS), set(module.OBLIGATIONS))
        self.assertNotIn("plan-owner", json.dumps(module.OBLIGATION_BINDINGS))
        for obligation, bindings in module.OBLIGATION_BINDINGS.items():
            self.assertTrue(bindings, obligation)
            self.assertEqual(set(bindings) - labels, set(), obligation)

    def test_plan_status_parser_strips_real_em_dash_suffix(self):
        module = load_verifier()
        with tempfile.TemporaryDirectory(prefix="ca-pi-plan-") as raw:
            path = Path(raw) / "plan.md"
            path.write_text("### Task 1: fixture\n\n**Status:** ACCEPTED — 2026-07-16\n", encoding="utf-8")
            tasks, _obligations, _owners = module.parse_plan(path)
            self.assertEqual(tasks, {1: "ACCEPTED"})

    def test_security_gate_validates_sanitized_promotion_evidence_without_raw_values(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw)
            path = root / "promotion.json"
            path.write_text(json.dumps(evidence()), encoding="utf-8")
            script = REPO / ".github" / "scripts" / "test_pi_security.py"
            completed = subprocess.run([sys.executable, str(script), "--evidence", str(path)], text=True, encoding="utf-8", capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0)
            self.assertIn("PI-SEC-PROMOTION-EVIDENCE", completed.stdout)
            poisoned = evidence(); poisoned["rows"][0]["diagnosticCode"] = "C:/Users/operator/auth.json"
            path.write_text(json.dumps(poisoned), encoding="utf-8")
            rejected = subprocess.run([sys.executable, str(script), "--evidence", str(path)], text=True, encoding="utf-8", capture_output=True, check=False)
            self.assertEqual(rejected.returncode, 1)
            self.assertNotIn("operator", rejected.stdout)

    def test_verifier_rejects_one_missing_obligation(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            path = root / ".pi-support-fixture.json"
            document = json.loads(path.read_text(encoding="utf-8")); document["bindings"].pop("PI-AC-29")
            path.write_text(json.dumps(document), encoding="utf-8")
            result = run_verifier(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("PI-AC-29", result.stdout)

    def test_verifier_rejects_partial_or_dirty_generation(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            (root / "plugins" / "ca-pi" / "skills" / "ca-feature" / "SKILL.md").write_text("mutated\n", encoding="utf-8")
            result = run_verifier(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("generated surface", result.stdout)

    def test_verifier_rejects_missing_or_drifted_promotion_markdown(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            markdown = root / "docs" / "reports" / "pi-support" / "promotion.md"
            markdown.unlink()
            self.assertNotEqual(run_verifier(root).returncode, 0)
            markdown.write_text("private prose drift\n", encoding="utf-8")
            self.assertNotEqual(run_verifier(root).returncode, 0)

    def test_preclosure_allows_only_explicit_hosted_pending_rows(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            self.assertEqual(run_verifier(root).returncode, 0)
            promotion = root / "docs" / "reports" / "pi-support" / "promotion.json"
            document = json.loads(promotion.read_text(encoding="utf-8"))
            document["rows"][0]["passed"] = False
            document["rows"][0]["diagnosticCode"] = "LOCAL_FAILED"
            promotion.write_text(json.dumps(document), encoding="utf-8")
            self.assertNotEqual(run_verifier(root).returncode, 0)

    def test_second_preclosure_allows_task_13_accepted_with_final_hosted_evidence(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            plan = root / ".codearbiter" / "plans" / "pi-support.md"
            text = plan.read_text(encoding="utf-8")
            text = text.replace(
                "### Task 13: fixture\n\n**Status:** IN_PROGRESS",
                "### Task 13: fixture\n\n**Status:** ACCEPTED",
            ).replace(
                "| PI-AC-35 fixture | AC 35 | 1 | OPEN |",
                "| PI-AC-35 fixture | AC 35 | 1 | COVERED |",
            )
            plan.write_text(text, encoding="utf-8")
            document = evidence("final")
            document["commit"] = "a" * 40
            for row in document["rows"]:
                if row["version"] in {"0.80.5", "0.80.10"} and row["platform"] in {"windows", "linux", "macos"}:
                    row.update(architecture="x64", resultCode="PI-HOSTED-SUPPORTED", passed=True, timingMs=10, diagnosticCode="NONE")
                elif row["version"] == "codeql":
                    row.update(architecture="x64", resultCode="PI-CODEQL-HIGH", passed=True, timingMs=10, diagnosticCode="NONE")
            promotion = root / "docs" / "reports" / "pi-support" / "promotion.json"
            promotion.write_text(json.dumps(document), encoding="utf-8")
            (promotion.parent / "promotion.md").write_text(
                load_verifier().render_promotion_markdown(document), encoding="utf-8",
            )
            result = run_verifier(root)
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_final_requires_same_committed_sha_and_all_supported_hosted_cells(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            result = run_verifier(root, "final")
            self.assertEqual(result.returncode, 1)
            self.assertIn("hosted", result.stdout.lower())

    def test_verifier_is_read_only_and_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-verify-") as raw:
            root = Path(raw); fixture(root)
            before = digest_tree(root)
            first = run_verifier(root)
            middle = digest_tree(root)
            second = run_verifier(root)
            after = digest_tree(root)
            self.assertEqual((first.returncode, second.returncode), (0, 0))
            self.assertEqual((before, middle, after), (before, before, before))


if __name__ == "__main__":
    unittest.main(verbosity=2)
