#!/usr/bin/env python3
"""Exercise greenfield population with an isolated installed candidate writer."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_artifact_authoring import build_installation


DOCUMENTS = ("CONTEXT", "tech-stack", "coding-standards", "security-controls", "code-map")


class TestGreenfieldContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner, cls.installation = build_installation()
        cls.plugin = cls.installation.parent.parent

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-greenfield-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        # The paired Markdown writer serves repositories that keep the older format.
        self.cli("--format", "markdown")
        self.state = self.root / ".codearbiter"
        self.interview = self.state / "plans/decomposition"
        self.interview.mkdir(parents=True)
        self.source = self.interview / "layer-4-tech-shape.md"
        self.source.write_text(
            "# Technical shape\nQuestion: Which runtime?\n"
            "User answer: Python; a local-only CSV report tool.\n"
            "No source code or manifest exists yet.\n", encoding="utf-8")
        self.drafts = self.root / ".codearbiter/.decompose-draft"
        self.drafts.mkdir()

    def cli(self, *arguments, success=True):
        result = subprocess.run(
            [sys.executable, "-B", str(self.plugin / "hooks/init-codearbiter.py"),
             "--root", str(self.root), *arguments], cwd=self.root, env=self.env,
            capture_output=True, encoding="utf-8", timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def preview(self, document):
        draft = self.drafts / f"{document}.md"
        text = ("---\narbiter: enabled\nstage: 1\n---\n# Project: CSV reports\n"
                if document == "CONTEXT" else f"# {document.replace('-', ' ').capitalize()}\n")
        text += ("## Planned architecture\nNo implementation paths exist yet.\n"
                 if document == "code-map" else "A local-only Python CSV report tool.\n")
        draft.write_text(text, encoding="utf-8")
        return json.loads(self.cli(
            "--context-draft", str(draft), "--document", document,
            "--source", self.source.relative_to(self.root).as_posix()).stdout)

    def apply(self, preview, *, success=True):
        return self.cli("--context-apply", preview["preview_ref"],
                        "--preview-sha256", preview["preview_sha256"], success=success)

    def populate(self):
        for document in DOCUMENTS:
            preview = self.preview(document)
            self.assertFalse(preview["evidence_assessed"])
            self.assertNotIn("receipt", preview)
            outcome = json.loads(self.apply(preview).stdout)
            self.assertEqual(outcome["transaction"]["state"], "committed")

    def test_protected_greenfield_population_finalizes_and_replays(self):
        guard = r'''
import importlib.util, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, sys.argv[1])
import _activationlib, _artifactlib
from _protectedstatelib import lookup_policy, ProtectedPolicy
root = pathlib.Path(sys.argv[2])
assert _activationlib.frontmatter_enabled(root / ".codearbiter/CONTEXT.md")[0]
assert _artifactlib.context_writer_qualified()
spec = importlib.util.spec_from_file_location("pre_write", pathlib.Path(sys.argv[1]) / "pre-write.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for target in _artifactlib._CONTEXT_TARGETS.values():
    assert lookup_policy(target, root=root) == ProtectedPolicy.HELPER_ONLY
    try:
        module._guard_op(str(root), {"kind": "write", "file_path": str(root / target),
                                   "content": "---\narbiter: enabled\nstage: 1\n---\n"})
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("direct write admitted: " + target)
'''
        checked = subprocess.run(
            [sys.executable, "-I", "-B", "-", str(self.plugin / "hooks"), str(self.root)],
            input=guard, cwd=self.root, env=self.env, capture_output=True,
            encoding="utf-8", timeout=60)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(checked.stderr.count("H-22"), 5, checked.stderr)
        self.populate()
        before = (self.state / "CONTEXT.md").read_bytes()
        preview = json.loads(self.cli("--context-finalize").stdout)
        self.assertEqual((self.state / "CONTEXT.md").read_bytes(), before)
        committed = json.loads(self.apply(preview).stdout)
        self.assertEqual(committed["transaction"]["state"], "committed")
        self.assertFalse(committed["transaction"]["replay"])
        replayed = json.loads(self.apply(preview).stdout)
        self.assertTrue(replayed["transaction"]["replay"])
        shutil.rmtree(self.drafts)
        self.assertTrue(self.source.is_file())
        for document in DOCUMENTS:
            record = json.loads((self.state / f".provenance/{document}.json").read_bytes())
            self.assertEqual(record["schema"], 2)
            self.assertEqual(record["document"]["digest"], hashlib.sha256(
                (self.state / f"{document}.md").read_bytes()).hexdigest())
            claim = record["fields"][0]["claims"][0]
            self.assertEqual(claim["semantic_review"]["state"], "unreviewed")
            self.assertEqual((self.root / claim["evidence"][0]["path"]).read_bytes(), self.source.read_bytes())
        context = (self.state / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertEqual(context.splitlines().count("<!--INITIALIZED-->"), 1)
        self.assertFalse(list((self.state / ".artifacts/receipts").glob("*.json")))
        self.assertIn("ALREADY_INITIALIZED", self.cli("--context-finalize", success=False).stderr)

    def test_missing_and_changed_inputs_preserve_uninitialized_state(self):
        before = (self.state / "CONTEXT.md").read_bytes()
        self.cli("--context-finalize", success=False)
        self.assertEqual((self.state / "CONTEXT.md").read_bytes(), before)
        self.populate()
        preview = json.loads(self.cli("--context-finalize").stdout)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "User answer: UTF-8 output.\n",
                               encoding="utf-8")
        rejected = self.apply(preview, success=False)
        self.assertIn("SOURCE_EVIDENCE_CONFLICT", rejected.stderr)
        self.assertNotIn("<!--INITIALIZED-->", (self.state / "CONTEXT.md").read_text(encoding="utf-8"))
        self.populate()
        refreshed = json.loads(self.cli("--context-finalize").stdout)
        outcome = json.loads(self.apply(refreshed).stdout)
        self.assertEqual(outcome["transaction"]["state"], "committed")


if __name__ == "__main__":
    unittest.main()
