#!/usr/bin/env python3
"""Behavioral contracts for trusted static ca-codex candidate verification."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / ".github" / "scripts" / "verify_codex_static_candidate.py"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "ca-codex"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_static_candidate", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return result.stdout.strip()


class StaticCandidateContractTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Static Candidate Test")
        shutil.copytree(PLUGIN_ROOT, self.repo / "plugins" / "ca-codex")
        fake = self.repo / ".github" / "scripts" / "check_codex_static_package.py"
        fake.parent.mkdir(parents=True)
        fake.write_text("raise RuntimeError('candidate verifier executed')\n", encoding="utf-8")
        git(self.repo, "add", "--", ".")
        git(self.repo, "commit", "-qm", "candidate")
        self.commit = git(self.repo, "rev-parse", "HEAD")

    def verify(self, **expectations):
        return self.module.verify_static_candidate(
            repo=self.repo, final_ref=self.commit, **expectations
        )

    def test_binds_exact_commit_tree_archive_and_static_contract(self):
        first = self.verify()
        untracked = self.repo / "plugins" / "ca-codex" / "hooks" / "untracked.py"
        untracked.write_text("raise RuntimeError('must remain unarchived')\n", encoding="utf-8")
        second = self.verify()
        self.assertEqual(first, second)
        self.assertEqual(first["verdict"], "PASS")
        self.assertEqual(first["source_commit"], self.commit)
        self.assertEqual(first["source_tree"], git(self.repo, "rev-parse", "HEAD^{tree}"))
        self.assertRegex(first["archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["package_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["resource_sha256"], r"^[0-9a-f]{64}$")

    def test_candidate_owned_verifier_is_inert_data(self):
        trusted = self.module._load_trusted_checker()
        with mock.patch.object(self.module, "_load_trusted_checker", return_value=trusted) as loader:
            self.verify()
        loader.assert_called_once_with()

    def test_rejects_option_shaped_and_nonexistent_refs(self):
        with mock.patch.object(self.module, "_git") as git_call, self.assertRaisesRegex(
            ValueError, "exact lowercase"
        ):
            self.module.verify_static_candidate(repo=self.repo, final_ref="--help")
        git_call.assert_not_called()
        with self.assertRaisesRegex(ValueError, "does not resolve"):
            self.module.verify_static_candidate(repo=self.repo, final_ref="f" * 40)

    def test_rejects_malformed_tree_identity(self):
        with mock.patch.object(
            self.module, "_git", side_effect=(self.commit, "not-a-tree-id")
        ), self.assertRaisesRegex(ValueError, "tree is not an exact Git object ID"):
            self.module._exact_commit(self.repo, self.commit)

    def test_archive_creation_fails_closed_on_git_error_or_missing_output(self):
        destination = self.repo / "candidate.zip"
        cases = (
            SimpleNamespace(returncode=1, stderr="archive failed", stdout=""),
            SimpleNamespace(returncode=0, stderr="", stdout=""),
        )
        for completed in cases:
            with self.subTest(returncode=completed.returncode), mock.patch.object(
                self.module.subprocess, "run", return_value=completed
            ), self.assertRaises(ValueError):
                self.module._archive(self.repo, self.commit, destination)

    def test_rejects_malformed_candidate_package(self):
        manifest = self.repo / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json"
        manifest.write_text("not json\n", encoding="utf-8")
        git(self.repo, "add", "--", str(manifest.relative_to(self.repo)))
        git(self.repo, "commit", "-qm", "malformed")
        malformed = git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(ValueError):
            self.module.verify_static_candidate(repo=self.repo, final_ref=malformed)

    def test_rejects_digest_mismatches_and_malformed_expectations(self):
        result = self.verify()
        fields = (
            ("expected_archive_sha256", result["archive_sha256"]),
            ("expected_package_sha256", result["package_sha256"]),
            ("expected_resource_sha256", result["resource_sha256"]),
        )
        for argument, digest in fields:
            with self.subTest(argument=argument), self.assertRaisesRegex(ValueError, "does not match"):
                self.verify(**{argument: ("0" if digest[0] != "0" else "1") + digest[1:]})
            with self.subTest(argument=f"malformed-{argument}"), self.assertRaisesRegex(
                ValueError, "exact lowercase SHA-256"
            ):
                self.verify(**{argument: "not-a-digest"})

    def test_rejects_oversized_archive_before_hash_or_checker(self):
        def oversized(_repo, _commit, destination):
            with destination.open("wb") as stream:
                stream.truncate(self.module.MAX_ARCHIVE_BYTES + 1)

        with mock.patch.object(self.module, "_archive", side_effect=oversized), mock.patch.object(
            self.module, "_sha256_file"
        ) as hasher, mock.patch.object(self.module, "_load_trusted_checker") as checker, self.assertRaisesRegex(
            ValueError, "archive-byte limit"
        ):
            self.verify()
        hasher.assert_not_called()
        checker.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
