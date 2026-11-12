#!/usr/bin/env python3
"""Negative tests: the ledger refuses dishonest status claims (P-02)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage_ledger as cl  # noqa: E402

SHA = "a" * 40


class LedgerHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name) / "ledger.json"
        cls._orig = cl.LEDGER
        cl.LEDGER = cls.base
        with contextlib.redirect_stdout(io.StringIO()):
            assert cl.init(force=True) == 0
        cls.pristine = cls.base.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cl.LEDGER = cls._orig
        cls._tmp.cleanup()

    def setUp(self):
        self.base.write_text(self.pristine, encoding="utf-8")
        self.data = json.loads(self.pristine)

    def run_check(self, complete=False):
        self.base.write_text(json.dumps(self.data), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cl.check(complete)
        return code, json.loads(out.getvalue())

    def row(self):
        return next(iter(self.data["transitions"].values()))

    def test_fresh_ledger_accounts_for_everything(self):
        code, report = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(report["counts"]["transitions"], {"PLANNED": 1748})

    def test_fresh_ledger_is_not_promotable(self):
        code, _ = self.run_check(complete=True)
        self.assertEqual(code, 1)

    def test_status_without_evidence_fails(self):
        self.row()["status"] = "TESTED"
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("without evidence", report["problems"][0])

    def test_review_only_cannot_claim_tested(self):
        self.row().update(status="TESTED", evidence=[{"kind": "review", "ref": "comment", "commit": SHA}])
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("executed evidence", report["problems"][0])

    def test_evidence_needs_exact_commit(self):
        self.row().update(status="TESTED", evidence=[{"kind": "test", "ref": "t", "commit": "abc"}])
        code, _ = self.run_check()
        self.assertEqual(code, 1)

    def test_installed_needs_installed_run(self):
        self.row().update(status="INSTALLED_QUALIFIED", evidence=[{"kind": "test", "ref": "t", "commit": SHA}])
        code, _ = self.run_check()
        self.assertEqual(code, 1)

    def test_not_applicable_needs_contract(self):
        self.row().update(status="NOT_APPLICABLE", evidence=[{"kind": "conformance-check", "ref": "t", "commit": SHA}])
        code, _ = self.run_check()
        self.assertEqual(code, 1)

    def test_missing_row_fails(self):
        self.data["transitions"].pop(next(iter(self.data["transitions"])))
        code, _ = self.run_check()
        self.assertEqual(code, 1)

    def test_unknown_task_fails(self):
        self.row()["task_ids"] = ["ZZ-99"]
        code, _ = self.run_check()
        self.assertEqual(code, 1)

    def test_valid_tested_row_passes(self):
        self.row().update(status="TESTED", evidence=[{"kind": "sequence-test", "ref": "t", "commit": SHA}])
        code, _ = self.run_check()
        self.assertEqual(code, 0)

    def test_init_refuses_to_overwrite_live_ledger(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cl.init(force=False), 1)


if __name__ == "__main__":
    unittest.main()
