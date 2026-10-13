#!/usr/bin/env python3
"""Exact-candidate cold installed context qualification, never host authority."""

import json
import os
from pathlib import Path
import subprocess
import unittest

import _contextverificationlib as verification
import test_artifact_installed_host as installed


ROOT = Path(__file__).resolve().parents[2]
DECLARATION = ROOT / ".github/fixtures/context-onboarding/installed-cells.json"
FORMAT = "codearbiter.context-installed-cells/0.1.0"
REQUIRED = frozenset({"claude", "codex"})


def load_cell(path: Path) -> dict:
    """Reject absent, invented, or incomplete runtime candidate facts."""
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise verification.VerificationError("observed installed-cell manifest is absent")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"format", "cell"} or data["format"] != FORMAT:
        raise verification.VerificationError("observed installed-cell manifest has invalid shape")
    cell = data["cell"]
    keys = {"host", "candidate_root", "plugin_root", "repository", "binary_sha256",
            "candidate_commit", "candidate_tree", "candidate_manifest_path",
            "candidate_manifest_sha256", "python_executable", "empty_path_dir",
            "development_root", "authorization"}
    if not isinstance(cell, dict) or set(cell) != keys or cell["host"] not in REQUIRED:
        raise verification.VerificationError("observed installed cell is incomplete or unsupported")
    if cell["authorization"] != "fixture-only-installed-candidate":
        raise verification.VerificationError("installed cell lacks fixture action permission")
    if any(not isinstance(cell[key], str) or not cell[key]
           for key in keys):
        raise verification.VerificationError("observed installed cell contains empty facts")
    return cell


class InstalledContextQualification(unittest.TestCase):
    def shortDescription(self):
        return None

    def test_t044_installed_context_kind(self):
        """Run the actual cold installed candidate through context read/write/recovery."""
        manifest = os.environ.get("CA_CONTEXT_INSTALLED_CELLS", "")
        self.assertTrue(manifest, "exact runtime installed-cell manifest is required")
        cell = load_cell(Path(manifest))
        self.assertIn(cell["host"], REQUIRED)
        development = Path(cell["development_root"]).resolve(strict=True)
        repository = Path(cell["repository"]).resolve(strict=True)
        candidate = Path(cell["candidate_root"]).resolve(strict=True)
        self.assertFalse(repository.is_relative_to(development))
        self.assertFalse(candidate.is_relative_to(development))
        invocation = verification.build_installed_invocation(
            host=cell["host"], candidate_root=candidate,
            plugin_root=Path(cell["plugin_root"]), repository=repository,
            binary_sha256=cell["binary_sha256"],
            candidate_commit=cell["candidate_commit"],
            candidate_tree=cell["candidate_tree"],
            candidate_manifest_path=Path(cell["candidate_manifest_path"]),
            candidate_manifest_sha256=cell["candidate_manifest_sha256"],
            python_executable=Path(cell["python_executable"]),
            empty_path_dir=Path(cell["empty_path_dir"]),
        )
        self.assertNotIn("PYTHONPATH", invocation.environment)
        argv = (*invocation.argv, "--context-kind", "--development-root", str(development),
                "--candidate-commit", cell["candidate_commit"],
                "--candidate-tree", cell["candidate_tree"],
                "--candidate-manifest-sha256", cell["candidate_manifest_sha256"])
        completed = subprocess.run(argv, cwd=invocation.cwd,
                                   env=invocation.environment, capture_output=True,
                                   timeout=180, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr[-1024:])
        self.assertEqual(completed.stderr, b"")
        result = json.loads(completed.stdout)
        self.assertEqual(result["format"], "codearbiter.installed-context-workflow/0.1.0")
        self.assertEqual(result["host"], cell["host"])
        self.assertEqual(result["binary_sha256"], cell["binary_sha256"])
        self.assertEqual(result["candidate_commit"], cell["candidate_commit"])
        self.assertEqual(result["candidate_tree"], cell["candidate_tree"])
        self.assertEqual(result["candidate_manifest_sha256"], cell["candidate_manifest_sha256"])
        self.assertEqual(result["outcomes"], {
            "read": "pass", "create": "committed", "update": "committed",
            "recovery": "pass", "disabled": "refused", "missing": "refused",
        })
        self.assertEqual(result["proof_kind"], "candidate-preflight")
        self.assertFalse(result["live_qualified"])

    def test_t044_rejects_missing_candidate_identity(self):
        """A declaration with no observed candidate cannot qualify a cell."""
        declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
        self.assertEqual(declaration["format"], FORMAT)
        self.assertEqual(set(declaration["required_hosts"]), REQUIRED)
        self.assertEqual(declaration["candidate_facts"], "runtime-required")
        with self.assertRaises(verification.VerificationError):
            load_cell(DECLARATION)

    def test_t044_rejects_nonisolated_environment(self):
        """The workflow child cannot read development-checkout resources."""
        with self.assertRaisesRegex(RuntimeError, "development checkout"):
            installed.enforce_runtime_event(
                "open", (str(ROOT / "core/pysrc/_artifactlib.py"), "r", 0),
                binary=ROOT / "absent", binary_sha256="0" * 64,
                permit_verifier_children=False,
            )


if __name__ == "__main__":
    unittest.main()
