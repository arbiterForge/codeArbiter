#!/usr/bin/env python3
"""Behavioral contracts for trusted-tree static ca-codex candidate verification."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
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


class StaticCandidateProvenanceTest(unittest.TestCase):
    def load_module(self):
        self.assertTrue(MODULE_PATH.is_file(), "the static candidate verifier is missing")
        spec = importlib.util.spec_from_file_location("candidate_provenance", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def make_candidate(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Candidate Test")
        write(
            repo,
            "plugins/ca-codex/.codex-plugin/plugin.json",
            json.dumps({"name": "ca-codex", "version": "0.7.5"}) + "\n",
        )
        write(
            repo,
            "plugins/ca-codex/skills/ca-probe/SKILL.md",
            "---\nname: ca-probe\ndescription: Probe skill.\n---\n\n"
            "# Probe\n\n[Agent](../../agents/probe.md)\n",
        )
        write(
            repo,
            "plugins/ca-codex/routines/probe/SKILL.md",
            "---\nname: probe\ndescription: Probe routine.\n"
            "disable-model-invocation: true\n---\n\n# Probe routine\n",
        )
        write(
            repo,
            "plugins/ca-codex/agents/probe.md",
            "---\nname: probe\ndescription: Probe agent.\nclassification: reviewer\n"
            "---\n\n# Probe agent\n",
        )
        shutil.copytree(
            REPO_ROOT / "plugins" / "ca-codex" / "hooks",
            repo / "plugins" / "ca-codex" / "hooks",
        )
        write(
            repo,
            "plugins/ca-codex/hooks/session-start.py",
            "raise SystemExit('candidate hook must remain inert')\n",
        )
        write(repo, ".github/scripts/check_codex_skill_resources.py", "raise SystemExit('untrusted')\n")
        git(repo, "add", "--", ".")
        git(repo, "commit", "-qm", "candidate")
        commit = git(repo, "rev-parse", "HEAD")
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        return temporary, repo, commit, tree

    def run_main(self, module, repo: Path, commit: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                status = module.main([
                    "--repo", str(repo),
                    "--final-ref", commit,
                    "--json",
                ])
            except SystemExit as error:
                status = error.code
        return status, stdout.getvalue(), stderr.getvalue()

    def test_verifies_exact_commit_tree_archive_and_static_package(self):
        module = self.load_module()
        temporary, repo, commit, tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)

        status, stdout, stderr = self.run_main(module, repo, commit)

        self.assertEqual(status, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["source_commit"], commit)
        self.assertEqual(result["source_tree"], tree)
        self.assertRegex(result["archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["package_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["resource_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["plugin_version"], "0.7.5")

    def test_executes_the_trusted_checker_not_candidate_owned_verifier_code(self):
        module = self.load_module()
        temporary, repo, commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)
        checker = mock.Mock()
        checker.candidate_static_contract.return_value = {
            "package_sha256": "a" * 64,
            "resource_sha256": "b" * 64,
            "plugin_version": "0.7.5",
            "selected_paths": [],
            "relative_reads": [],
        }

        with mock.patch.object(module, "_load_trusted_checker", return_value=checker):
            result = module.verify_static_candidate(repo=repo, final_ref=commit)

        checker.candidate_static_contract.assert_called_once()
        self.assertEqual(result["package_sha256"], "a" * 64)

    def test_rejects_option_shaped_ref_before_invoking_git(self):
        module = self.load_module()
        with mock.patch.object(module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "40-character commit"):
                module.verify_static_candidate(
                    repo=Path("unused"), final_ref="--upload-pack=malicious"
                )
        run.assert_not_called()

    def test_rejects_a_nonexistent_exact_commit(self):
        module = self.load_module()
        temporary, repo, _commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)

        status, _stdout, stderr = self.run_main(module, repo, "f" * 40)

        self.assertEqual(status, 1)
        self.assertIn("does not resolve to a commit", stderr)

    def test_rejects_malformed_candidate_package_shape(self):
        module = self.load_module()
        temporary, repo, _commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)
        manifest = repo / "plugins/ca-codex/.codex-plugin/plugin.json"
        manifest.unlink()
        git(repo, "add", "-u")
        git(repo, "commit", "-qm", "remove manifest")
        commit = git(repo, "rev-parse", "HEAD")

        status, _stdout, stderr = self.run_main(module, repo, commit)

        self.assertEqual(status, 1)
        self.assertIn("plugin manifest", stderr)

    def test_same_commit_produces_the_same_archive_digest(self):
        module = self.load_module()
        temporary, repo, commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)

        first = module.verify_static_candidate(repo=repo, final_ref=commit)
        second = module.verify_static_candidate(repo=repo, final_ref=commit)

        self.assertEqual(first["archive_sha256"], second["archive_sha256"])

    def test_rejects_expected_candidate_digest_mismatch(self):
        module = self.load_module()
        temporary, repo, commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)
        actual = module.verify_static_candidate(repo=repo, final_ref=commit)

        for field, argument in (
            ("archive_sha256", "expected_archive_sha256"),
            ("package_sha256", "expected_package_sha256"),
            ("resource_sha256", "expected_resource_sha256"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, f"{field.replace('_', ' ')} does not match"
            ):
                module.verify_static_candidate(
                    repo=repo,
                    final_ref=commit,
                    **{argument: "0" * 64},
                )
            self.assertRegex(actual[field], r"^[0-9a-f]{64}$")

    def test_rejects_oversized_archive_before_hashing_content(self):
        module = self.load_module()
        temporary, repo, commit, _tree = self.make_candidate()
        self.addCleanup(temporary.cleanup)

        def oversized_archive(_repo, _commit, destination):
            destination.write_bytes(b"x" * 9)

        with mock.patch.object(module, "MAX_ARCHIVE_BYTES", 8), mock.patch.object(
            module, "_archive", side_effect=oversized_archive
        ), mock.patch.object(module, "_sha256_file") as digest:
            with self.assertRaisesRegex(ValueError, "archive-byte limit"):
                module.verify_static_candidate(repo=repo, final_ref=commit)
        digest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
