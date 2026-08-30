#!/usr/bin/env python3
"""Behavioral contracts for PR2 commit-C / commit-R provenance binding."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / ".github" / "scripts" / "verify_codex_candidate_provenance.py"


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class CandidateGraphTest(unittest.TestCase):
    def load_module(self):
        self.assertTrue(
            MODULE_PATH.is_file(),
            "the commit-C/commit-R verifier is not implemented",
        )
        spec = importlib.util.spec_from_file_location("candidate_provenance", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def make_graph(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Candidate Test")
        write(repo, "README.md", "base\n")
        git(repo, "add", "--", "README.md")
        git(repo, "commit", "-qm", "base")
        base = git(repo, "rev-parse", "HEAD")

        write(
            repo,
            "plugins/ca-codex/.codex-plugin/plugin.json",
            json.dumps({"name": "ca-codex", "version": "0.7.5"}) + "\n",
        )
        write(repo, "plugins/ca-codex/agents/probe.md", "# Probe\n")
        git(repo, "add", "--", "plugins/ca-codex")
        git(repo, "commit", "-qm", "candidate C")
        candidate = git(repo, "rev-parse", "HEAD")
        candidate_tree = git(repo, "rev-parse", "HEAD^{tree}")
        archive = repo / "candidate.zip"
        subprocess.run(
            [
                "git", "archive", "--format=zip", f"--output={archive}",
                candidate, "--", "plugins/ca-codex",
            ],
            cwd=repo,
            check=True,
        )
        archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()

        receipt = {
            "candidate": {
                "archive_sha256": archive_sha256,
                "source_commit": candidate,
                "source_tree": candidate_tree,
                "package": "ca-codex",
            }
        }
        write(
            repo,
            "docs/reports/codex-desktop-candidate-resolution.json",
            json.dumps(receipt) + "\n",
        )
        write(
            repo,
            "docs/reports/evidence/codex-desktop-candidate/attestation.jsonl",
            "{}\n",
        )
        git(repo, "add", "--", "docs/reports")
        git(repo, "commit", "-qm", "receipt R")
        head = git(repo, "rev-parse", "HEAD")
        return temporary, repo, base, candidate, head, receipt

    def test_optional_pr_receipt_is_non_blocking_only_when_the_file_is_absent(self):
        """An ordinary plugin PR does not need synthetic desktop evidence."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "desktop-receipt.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                try:
                    result = module.main([
                        "--mode", "pr",
                        "--repo", str(root),
                        "--receipt", str(missing),
                        "--base", "a" * 40,
                        "--head", "b" * 40,
                        "--allow-missing-receipt",
                        "--json",
                    ])
                except SystemExit as error:
                    result = error.code

            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "reason": "desktop receipt not supplied",
                    "verdict": "NOT_APPLICABLE",
                },
            )

    def test_missing_pr_receipt_remains_strict_without_the_opt_in_flag(self):
        """The verifier is strict by default even for pull requests."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = module.main([
                    "--mode", "pr",
                    "--repo", str(root),
                    "--receipt", str(root / "missing-receipt.json"),
                    "--base", "a" * 40,
                    "--head", "b" * 40,
                    "--json",
                ])

            self.assertEqual(result, 1)
            self.assertIn("candidate receipt is not valid UTF-8 JSON", stderr.getvalue())

    def test_optional_merge_group_receipt_is_non_blocking_only_when_absent(self):
        """Merge-queue candidates share the PR absence-only contract."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = module.main([
                    "--mode", "merge-group",
                    "--repo", str(root),
                    "--receipt", str(root / "missing-receipt.json"),
                    "--head", "b" * 40,
                    "--allow-missing-receipt",
                    "--json",
                ])

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(stdout.getvalue())["verdict"], "NOT_APPLICABLE")

    def test_optional_pr_receipt_still_rejects_malformed_present_evidence(self):
        """The optional boundary is absence-only, never validation-optional."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / "desktop-receipt.json"
            receipt.write_text("not json\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                try:
                    result = module.main([
                        "--mode", "pr",
                        "--repo", str(root),
                        "--receipt", str(receipt),
                        "--base", "a" * 40,
                        "--head", "b" * 40,
                        "--allow-missing-receipt",
                        "--json",
                    ])
                except (SystemExit, ValueError) as error:
                    result = getattr(error, "code", 2)

            self.assertEqual(result, 1)
            self.assertIn("candidate receipt is not valid UTF-8 JSON", stderr.getvalue())

    def test_optional_pr_receipt_still_runs_strict_attestation_validation(self):
        """Valid JSON without the strict desktop fields remains untrusted evidence."""
        module = self.load_module()
        temporary, repo, base, _candidate, head, _receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        receipt_path = repo / "docs/reports/codex-desktop-candidate-resolution.json"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main([
                "--mode", "pr",
                "--repo", str(repo),
                "--receipt", str(receipt_path),
                "--base", base,
                "--head", head,
                "--allow-missing-receipt",
                "--json",
            ])

        self.assertEqual(result, 1)
        self.assertIn("receipt desktop object is missing", stderr.getvalue())

    def test_optional_pr_receipt_rejects_a_dangling_receipt_symlink(self):
        """A present filesystem object cannot masquerade as an absent receipt."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / "desktop-receipt.json"
            try:
                os.symlink(root / "missing-target.json", receipt)
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = module.main([
                    "--mode", "pr",
                    "--repo", str(root),
                    "--receipt", str(receipt),
                    "--base", "a" * 40,
                    "--head", "b" * 40,
                    "--allow-missing-receipt",
                    "--json",
                ])

            self.assertEqual(result, 1)
            self.assertIn("candidate receipt is not valid UTF-8 JSON", stderr.getvalue())

    def test_release_cannot_opt_out_of_desktop_receipt_verification(self):
        """Release verification always requires the strict receipt boundary."""
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    module.main([
                        "--mode", "release",
                        "--repo", str(root),
                        "--receipt", str(root / "missing-receipt.json"),
                        "--final-ref", "a" * 40,
                        "--candidate-archive", str(root / "candidate.zip"),
                        "--allow-missing-receipt",
                    ])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn(
                "--allow-missing-receipt is not valid in release mode",
                stderr.getvalue(),
            )

    def test_accepts_one_attestation_only_r_commit_and_unchanged_merge_candidate(self):
        """A valid C→R graph must survive merge synthesis without payload drift."""
        module = self.load_module()
        temporary, repo, base, candidate, head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)

        result = module.verify_pr_candidate_graph(
            repo=repo,
            receipt=receipt,
            base=base,
            head=head,
        )

        self.assertEqual(result["candidate_commit"], candidate)
        self.assertEqual(result["candidate_file_count"], 2)
        self.assertEqual(result["commit_r_count"], 1)

    def test_option_shaped_candidate_never_invokes_git_archive(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "candidate.zip"
            with mock.patch.object(module.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "object ID"):
                    module._archive(Path(temporary), "--remote=.", destination)
            run.assert_not_called()

    def test_release_accepts_squash_safe_payload_equality_without_c_ancestry(self):
        """Release proof compares trusted bytes, not historical C ancestry."""
        module = self.load_module()
        temporary, repo, _base, candidate, head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        archive = repo / "trusted-candidate.zip"
        subprocess.run(
            [
                "git", "archive", "--format=zip", f"--output={archive}",
                candidate, "--", "plugins/ca-codex",
            ],
            cwd=repo,
            check=True,
        )

        result = module.verify_release_candidate_payload(
            repo=repo,
            receipt=receipt,
            final_ref=head,
            candidate_archive=archive,
        )

        self.assertEqual(result["candidate_commit"], candidate)
        self.assertEqual(result["candidate_file_count"], 2)

    def test_rejects_product_drift_hidden_in_commit_r(self):
        module = self.load_module()
        temporary, repo, base, _candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        write(repo, "README.md", "drift hidden in R\n")
        git(repo, "add", "--", "README.md")
        git(repo, "commit", "--amend", "--no-edit", "-q")

        with self.assertRaisesRegex(ValueError, "attestation files"):
            module.verify_pr_candidate_graph(
                repo=repo,
                receipt=receipt,
                base=base,
                head=git(repo, "rev-parse", "HEAD"),
            )

    def test_rejects_receipt_only_commit_r_without_detached_attestation(self):
        module = self.load_module()
        temporary, repo, base, candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        git(repo, "reset", "--soft", "HEAD^")
        git(repo, "reset", "-q")
        bundle = repo / "docs/reports/evidence/codex-desktop-candidate/attestation.jsonl"
        bundle.unlink()
        git(repo, "add", "--", "docs/reports")
        git(repo, "commit", "-qm", "receipt R without detached attestation")

        with self.assertRaisesRegex(ValueError, "detached attestation"):
            module.verify_pr_candidate_graph(
                repo=repo,
                receipt=receipt,
                base=base,
                head=git(repo, "rev-parse", "HEAD"),
            )

    def test_rejects_arbitrary_or_secret_like_commit_r_evidence(self):
        module = self.load_module()
        temporary, repo, base, _candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        write(
            repo,
            "docs/reports/evidence/codex-desktop-candidate/raw-login-output.txt",
            "device callback material must never be durable\n",
        )
        git(repo, "add", "--", "docs/reports")
        git(repo, "commit", "--amend", "--no-edit", "-q")

        with self.assertRaisesRegex(ValueError, "unexpected attestation path"):
            module.verify_pr_candidate_graph(
                repo=repo,
                receipt=receipt,
                base=base,
                head=git(repo, "rev-parse", "HEAD"),
            )

    def test_rejects_more_than_one_commit_after_candidate_c(self):
        module = self.load_module()
        temporary, repo, base, _candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        write(
            repo,
            "docs/reports/evidence/codex-desktop-candidate/late.json",
            "{}\n",
        )
        git(repo, "add", "--", "docs/reports/evidence")
        git(repo, "commit", "-qm", "unexpected second receipt commit")

        with self.assertRaisesRegex(ValueError, "exactly one"):
            module.verify_pr_candidate_graph(
                repo=repo,
                receipt=receipt,
                base=base,
                head=git(repo, "rev-parse", "HEAD"),
            )

    def test_rejects_merge_synthesis_that_changes_candidate_payload(self):
        module = self.load_module()
        temporary, repo, base, _candidate, head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        git(repo, "branch", "feature", head)
        git(repo, "checkout", "-qb", "main-update", base)
        write(repo, "plugins/ca-codex/agents/base-only.md", "unexpected\n")
        git(repo, "add", "--", "plugins/ca-codex")
        git(repo, "commit", "-qm", "concurrent main payload change")
        updated_base = git(repo, "rev-parse", "HEAD")

        with self.assertRaisesRegex(ValueError, "synthesized merge"):
            module.verify_pr_candidate_graph(
                repo=repo,
                receipt=receipt,
                base=updated_base,
                head=head,
            )

    def test_rejects_merge_synthesis_that_changes_candidate_owned_inputs(self):
        module = self.load_module()
        cases = (
            "core/pysrc/new-root-input.py",
            "tools/build-surface.py",
            ".github/actions/publish-release/action.yml",
            ".github/scripts/test_codex_skill_resources.py",
            ".github/scripts/verify_codex_candidate_provenance.py",
            ".github/workflows/release.yml",
        )
        for path in cases:
            with self.subTest(path=path):
                temporary, repo, base, _candidate, head, receipt = self.make_graph()
                self.addCleanup(temporary.cleanup)
                git(repo, "branch", "feature", head)
                git(repo, "checkout", "-qb", "main-update", base)
                write(repo, path, "base-side candidate input drift\n")
                git(repo, "add", "--", path)
                git(repo, "commit", "-qm", "concurrent candidate input change")

                with self.assertRaisesRegex(ValueError, "candidate-owned"):
                    module.verify_pr_candidate_graph(
                        repo=repo,
                        receipt=receipt,
                        base=git(repo, "rev-parse", "HEAD"),
                        head=head,
                    )

    def test_strict_receipt_verification_uses_the_exact_detached_bundle(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            candidate_archive = root / "candidate.zip"
            bundle_path = root / "attestation.jsonl"
            receipt_path.write_text(json.dumps({
                "candidate": {"source_commit": "c" * 40, "source_tree": "d" * 40},
                "desktop": {"build": "build", "runtime_version": "runtime"},
                "workflow": {"run_id": "123", "commit": "e" * 40},
            }), encoding="utf-8")
            candidate_archive.write_bytes(b"candidate")
            bundle_path.write_text("{}\n", encoding="utf-8")
            checker = mock.Mock()
            checker.validate_desktop_receipt.return_value = {"verdict": "PASS"}
            checker.verify_github_attestation.return_value = {"verified": True}

            with mock.patch.object(module, "_load_checker", return_value=checker):
                module.verify_strict_receipt(
                    receipt_path, candidate_archive, bundle_path=bundle_path
                )

            checker.verify_github_attestation.assert_called_once_with(
                receipt_path, "e" * 40, "123", bundle_path=bundle_path
            )

    def test_release_rejects_final_main_payload_drift(self):
        module = self.load_module()
        temporary, repo, _base, candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        archive = repo / "trusted-candidate.zip"
        subprocess.run(
            [
                "git", "archive", "--format=zip", f"--output={archive}",
                candidate, "--", "plugins/ca-codex",
            ],
            cwd=repo,
            check=True,
        )
        write(repo, "plugins/ca-codex/agents/probe.md", "# changed after merge\n")
        git(repo, "add", "--", "plugins/ca-codex")
        git(repo, "commit", "-qm", "final-main payload drift")

        with self.assertRaisesRegex(ValueError, "final-main"):
            module.verify_release_candidate_payload(
                repo=repo,
                receipt=receipt,
                final_ref=git(repo, "rev-parse", "HEAD"),
                candidate_archive=archive,
            )

    def test_merge_group_accepts_attested_payload_with_extra_queue_history(self):
        module = self.load_module()
        temporary, repo, _base, candidate, _head, receipt = self.make_graph()
        self.addCleanup(temporary.cleanup)
        write(repo, "QUEUE.md", "unrelated queued change\n")
        git(repo, "add", "--", "QUEUE.md")
        git(repo, "commit", "-qm", "merge queue synthesis")

        result = module.verify_merge_group_candidate(
            repo=repo,
            receipt=receipt,
            head=git(repo, "rev-parse", "HEAD"),
        )

        self.assertEqual(result["candidate_commit"], candidate)
        self.assertEqual(result["candidate_file_count"], 2)


if __name__ == "__main__":
    unittest.main()
