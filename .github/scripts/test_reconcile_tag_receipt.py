#!/usr/bin/env python3
# codeArbiter — offline provenance candidate regression tests (LG03).

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import reconcile_tag_receipt as candidate


COMMIT = "a" * 40
OBJECT = "b" * 40
WORKFLOW = "c" * 40
TAG = "ca-codex-v0.7.5"
IDENTITY = {"object_sha": OBJECT, "object_type": "tag", "commit_sha": COMMIT}
EXPECTED = {"repo": "arbiterForge/codeArbiter", "tag": TAG, "commit": COMMIT,
            "run_id": 123, "run_attempt": 2, "workflow_sha": WORKFLOW}
RECEIPT = {"schema_version": 1, "repo": EXPECTED["repo"], "tag": TAG,
           "identity": IDENTITY, "source": {"kind": "hosted-tag-observation",
           "run_id": 123, "run_attempt": 2, "workflow_sha": WORKFLOW}}
MANIFEST = {"$comment": ["Historical metadata remains unchanged."],
            "verified_at": "2026-08-08", "namespaces": ["v*", "ca-codex-v*"],
            "extension": {"arbitrary": [1, True, None, "kept"]},
            "tags": {"v1.0.0": {"object_sha": "d" * 40, "object_type": "commit",
                     "commit_sha": "d" * 40, "note": "preserve per-entry metadata"}}}


class ReconcileTests(unittest.TestCase):
    # LG03-APPEND: preserve every prior field and add precisely one identity.
    def test_append_preserves_metadata_entries_and_inputs(self):
        manifest, receipt = copy.deepcopy(MANIFEST), copy.deepcopy(RECEIPT)
        result = candidate.reconcile(manifest, receipt, EXPECTED)
        wanted = copy.deepcopy(MANIFEST)
        wanted["tags"][TAG] = IDENTITY
        self.assertEqual(result, wanted)
        self.assertEqual(manifest, MANIFEST)
        self.assertEqual(receipt, RECEIPT)

    # LG03-NOOP: equal identity is idempotent; conflict never updates history.
    def test_equal_existing_identity_is_noop_preserving_extra_metadata(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["tags"][TAG] = {**IDENTITY, "note": "untouched"}
        self.assertIsNone(candidate.reconcile(manifest, RECEIPT, EXPECTED))

    def test_conflicting_existing_identity_refuses(self):
        for field, value in (("object_sha", "e" * 40), ("commit_sha", "e" * 40),
                             ("object_type", "commit")):
            with self.subTest(field=field):
                manifest = copy.deepcopy(MANIFEST)
                manifest["tags"][TAG] = {**IDENTITY, field: value}
                with self.assertRaises(ValueError):
                    candidate.reconcile(manifest, RECEIPT, EXPECTED)

    # LG03-BIND: caller expectations are required, not copied from receipt claims.
    def test_every_expected_binding_must_match(self):
        for field, value in (("repo", "other/repo"), ("tag", "v1.0.1"), ("commit", "d" * 40),
                             ("run_id", 124), ("run_attempt", 3), ("workflow_sha", "d" * 40)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    candidate.reconcile(MANIFEST, RECEIPT, {**EXPECTED, field: value})

    def test_exact_receipt_schema_and_types(self):
        variants = []
        for field, value in (("schema_version", True), ("schema_version", 2),
                             ("repo", None), ("tag", "v01.0.0"), ("identity", []), ("source", [])):
            variants.append({**RECEIPT, field: value})
        variants.extend([{**RECEIPT, "extra": 1}, {k: v for k, v in RECEIPT.items() if k != "tag"}])
        for field, value in (("kind", "original-publication"), ("run_id", True), ("run_id", "123"),
                             ("run_attempt", 0), ("workflow_sha", WORKFLOW.upper()), ("extra", 1)):
            variants.append({**RECEIPT, "source": {**RECEIPT["source"], field: value}})
        for field, value in (("object_sha", "0" * 40), ("object_type", "blob"),
                             ("commit_sha", "A" * 40), ("extra", 1)):
            variants.append({**RECEIPT, "identity": {**IDENTITY, field: value}})
        variants.append({**RECEIPT, "identity": {**IDENTITY, "object_type": "commit"}})
        for receipt in variants:
            with self.subTest(receipt=receipt):
                with self.assertRaises(ValueError):
                    candidate.reconcile(MANIFEST, receipt, EXPECTED)

    # LG03-HISTORY: validate all existing identities, not only the proposed entry.
    def test_invalid_existing_manifest_entries_refuse(self):
        entries = [None, [], {}, {**IDENTITY, "object_sha": "0" * 40},
                   {**IDENTITY, "object_type": "blob"}, {**IDENTITY, "commit_sha": "no"},
                   {**IDENTITY, "object_type": "commit"}]
        for entry in entries:
            with self.subTest(entry=entry):
                manifest = copy.deepcopy(MANIFEST)
                manifest["tags"]["v1.0.0"] = entry
                with self.assertRaises(ValueError):
                    candidate.reconcile(manifest, RECEIPT, EXPECTED)
        for manifest in ([], {}, {"tags": []}, {"tags": {"invalid": IDENTITY}}):
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    candidate.reconcile(manifest, RECEIPT, EXPECTED)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt = self.root / "receipt.json"
        self.manifest = self.root / "manifest.json"
        self.output = self.root / "candidate.json"
        self.receipt.write_text(json.dumps(RECEIPT), encoding="utf-8")
        self.manifest.write_text(json.dumps(MANIFEST, indent=3) + "\n", encoding="utf-8")

    def args(self):
        result = ["--receipt", str(self.receipt), "--manifest", str(self.manifest),
                  "--output", str(self.output), "--expected-manifest-sha256",
                  hashlib.sha256(self.manifest.read_bytes()).hexdigest()]
        for key, value in EXPECTED.items():
            result.extend(["--expected-" + key.replace("_", "-"), str(value)])
        return result

    def invoke(self, args=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = candidate.main(self.args() if args is None else args)
        return result, stdout.getvalue(), stderr.getvalue()

    # LG03-CLI: real external Python CLI, no network or process mock.
    def test_real_cli_creates_candidate_and_preserves_source_bytes(self):
        originals = self.manifest.read_bytes(), self.receipt.read_bytes()
        result = subprocess.run([sys.executable, str(Path(candidate.__file__)), *self.args()],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = copy.deepcopy(MANIFEST)
        expected["tags"][TAG] = IDENTITY
        self.assertEqual(json.loads(self.output.read_bytes()), expected)
        self.assertEqual((self.manifest.read_bytes(), self.receipt.read_bytes()), originals)

    def test_equal_receipt_noop_creates_no_output(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["tags"][TAG] = IDENTITY
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        original = self.manifest.read_bytes()
        for _ in range(2):
            self.assertEqual(self.invoke()[0], 0)
            self.assertFalse(self.output.exists())
            self.assertEqual(self.manifest.read_bytes(), original)

    # LG03-JSON: bounded strict JSON, including nested duplicate keys/nonfinite values.
    def test_malformed_json_refuses_without_candidate(self):
        for path in (self.receipt, self.manifest):
            original = path.read_bytes()
            for payload in (b"[]", b"null", b"{", b'{"tags":{},"tags":{}}',
                            b'{"nested":{"x":1,"x":2}}', b'{"n":NaN}',
                            b'{"n":Infinity}', b'{"n":1e999}', b"\xff"):
                with self.subTest(path=path.name, payload=payload):
                    path.write_bytes(payload)
                    self.assertEqual(self.invoke()[0], 1)
                    self.assertFalse(self.output.exists())
            path.write_bytes(original)

    def test_oversize_documents_refuse(self):
        for path, bound in ((self.receipt, 16 * 1024), (self.manifest, 2 * 1024 * 1024)):
            original = path.read_bytes()
            path.write_bytes(b" " * (bound + 1))
            self.assertEqual(self.invoke()[0], 1)
            self.assertFalse(self.output.exists())
            path.write_bytes(original)

    # LG03-STALE: expected source bytes and recheck at publication are mandatory.
    def test_stale_or_malformed_expected_digest_refuses(self):
        for digest in ("d" * 64, "A" * 64, "x", "0" * 63):
            args = self.args()
            args[args.index("--expected-manifest-sha256") + 1] = digest
            self.assertEqual(self.invoke(args)[0], 1)
            self.assertFalse(self.output.exists())

    def test_manifest_change_while_candidate_is_being_written_refuses(self):
        args = self.args()
        changed = self.manifest.read_bytes() + b" "
        with patch.object(os, "fsync", side_effect=lambda _: self.manifest.write_bytes(changed)):
            self.assertEqual(self.invoke(args)[0], 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.manifest.read_bytes(), changed)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["manifest.json", "receipt.json"])

    # LG03-EXCLUSIVE: no overwrite, aliases or symlink output escape.
    def test_output_cannot_replace_input_or_existing_output(self):
        self.output.write_text("prior candidate", encoding="utf-8")
        for path in (self.output, self.manifest, self.receipt):
            original = path.read_bytes()
            args = self.args()
            args[args.index("--output") + 1] = str(path)
            self.assertEqual(self.invoke(args)[0], 1)
            self.assertEqual(path.read_bytes(), original)

    def test_symlink_input_and_output_refuse(self):
        link = self.root / "link"
        try:
            link.symlink_to(self.manifest)
        except OSError as error:
            self.skipTest(f"Symlink unavailable: {error.errno}")
        for flag in ("--manifest", "--output"):
            args = self.args()
            args[args.index(flag) + 1] = str(link)
            self.assertEqual(self.invoke(args)[0], 1)
            self.assertFalse(self.output.exists())

    def test_missing_duplicate_unknown_cli_flags_refuse(self):
        for args in ([], self.args()[:-2], self.args() + ["--unknown"],
                     self.args() + ["--expected-run-id", "123"]):
            self.assertEqual(self.invoke(args)[0], 2)
            self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
