#!/usr/bin/env python3
"""R-06 / C-F06: typed qualification outcomes stay distinct from exit codes.

Ordinary lanes keep their compatible exits (a missing token still exits 0),
but each checker now records what that exit established, and a REQUIRED
consumer (major-release readiness) accepts only affirmative evidence.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = load("_verdictlib")
COMMIT = "a" * 40


def record(check, outcome, *, commit=COMMIT, evidence=None):
    return V.observation(check, outcome, f"{check} {outcome}", scope="test",
                         source={"repository": "o/r", "commit": commit}, evidence=evidence)


class SourceIdentityTest(unittest.TestCase):
    def test_recovery_checkout_is_distinct_from_later_workflow_event(self):
        root = HERE.parents[1]
        checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        event = 'b' * 40
        with patch.dict(os.environ, {'GITHUB_SHA': event}):
            identity = V.source_identity(root=root)
        self.assertEqual(identity['commit'], checkout)
        self.assertEqual(identity['event_commit'], event)

    def test_unavailable_checkout_is_not_replaced_by_event_identity(self):
        with patch.dict(os.environ, {'GITHUB_SHA': 'b' * 40}), \
                patch.object(V.subprocess, 'run', side_effect=OSError('git unavailable')):
            self.assertEqual(V.source_identity()['commit'], 'unknown')


class RequiredAggregationTest(unittest.TestCase):
    REQUIRED = ["tags", "protection", "codex-host"]

    def test_only_affirmative_evidence_satisfies_a_required_check(self):
        ok = [record(c, "verified") for c in self.REQUIRED]
        self.assertEqual(V.require(ok, self.REQUIRED, commit=COMMIT), [])
        for outcome in ("skipped", "unavailable", "rejected"):
            with self.subTest(outcome=outcome):
                records = [record("tags", outcome)] + ok[1:]
                problems = V.require(records, self.REQUIRED, commit=COMMIT)
                self.assertEqual(len(problems), 1)
                self.assertIn(outcome, problems[0])

    def test_missing_duplicate_or_other_source_evidence_is_not_a_pass(self):
        ok = [record(c, "verified") for c in self.REQUIRED]
        self.assertIn("no observation", V.require(ok[1:], self.REQUIRED, commit=COMMIT)[0])
        self.assertIn("exactly one", V.require(ok + [ok[0]], self.REQUIRED, commit=COMMIT)[0])
        stale = [record("tags", "verified", commit="b" * 40)] + ok[1:]
        self.assertIn("not " + COMMIT, V.require(stale, self.REQUIRED, commit=COMMIT)[0])

    def test_not_applicable_needs_a_declaration_and_evidence(self):
        ok = [record(c, "verified") for c in self.REQUIRED[1:]]
        bare = [record("tags", "not-applicable")] + ok
        self.assertIn("not a declared outcome", V.require(bare, self.REQUIRED, commit=COMMIT)[0])
        allowed = frozenset({"tags"})
        self.assertIn("without evidence", V.require(bare, self.REQUIRED, commit=COMMIT,
                                                    not_applicable_allowed=allowed)[0])
        evidenced = [record("tags", "not-applicable", evidence=["ADR-x scope"])] + ok
        self.assertEqual(V.require(evidenced, self.REQUIRED, commit=COMMIT,
                                   not_applicable_allowed=allowed), [])

    def test_ordinary_consumers_declare_their_own_accepted_outcomes(self):
        skipped = record("codex-host", "skipped")
        self.assertTrue(V.satisfies(skipped, {"verified", "skipped"}))  # optional dev lane
        self.assertFalse(V.satisfies(skipped, {"verified"}))            # required lane

    def test_malformed_observations_are_refused(self):
        with self.assertRaises(V.VerdictError):
            V.observation("x", "passed", "r", scope="s")
        with self.assertRaises(V.VerdictError):
            V.require([{"check": "tags", "outcome": "verified"}], ["tags"], commit=COMMIT)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "v.jsonl"
            path.write_text("not json\n", encoding="utf-8")
            with self.assertRaises(V.VerdictError):
                V.read(path)


class CheckerObservationTest(unittest.TestCase):
    """Each checker keeps its exit code and records the honest outcome."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "verdict.jsonl"

    def observed(self):
        records = V.read(self.path)
        self.assertEqual(len(records), 1)
        return records[0]

    def quiet(self, call):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return call()

    def test_branch_protection_forbidden_read_is_unavailable_not_verified(self):
        module = load("check_branch_protection")
        queue = lambda query, variables: (200, {"data": {"repository": {"mergeQueue": None}}})
        forbidden = lambda path: (403, {"message": "Resource not accessible"})
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token="x",
            rest=forbidden, graphql=queue))
        self.assertEqual(code, 0)  # compatible exit
        self.assertEqual(self.observed()["outcome"], "unavailable")

    def test_branch_protection_without_token_is_skipped(self):
        module = load("check_branch_protection")
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token=""))
        self.assertEqual((code, self.observed()["outcome"]), (0, "skipped"))

    def test_branch_protection_violation_and_compliance(self):
        module = load("check_branch_protection")
        protection = {"required_status_checks": {"strict": True,
                      "contexts": [module.MERGE_READINESS_CONTEXT]},
                      "required_linear_history": {"enabled": False}}
        rest = lambda path: (200, protection if path.endswith("/protection")
                             else {"allow_merge_commit": True})
        queue = lambda query, variables: (200, {"data": {"repository": {"mergeQueue": None}}})
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token="x",
            rest=rest, graphql=queue))
        self.assertEqual((code, self.observed()["outcome"]), (0, "verified"))
        self.path.unlink()
        unprotected = lambda path: ((404, {}) if path.endswith("/protection")
                                    else (200, {"allow_merge_commit": True}))
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token="x",
            rest=unprotected, graphql=queue))
        self.assertEqual((code, self.observed()["outcome"]), (1, "rejected"))

    def test_tag_audit_without_token_is_skipped_and_unavailable_api_is_unavailable(self):
        module = load("check_tag_immutability")
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token=""))
        self.assertEqual((code, self.observed()["outcome"]), (0, "skipped"))
        self.path.unlink()
        code = self.quiet(lambda: module.main(
            ["--repo", "o/r", "--verdict-output", str(self.path)], token="t",
            rest=lambda path: (503, {})))
        self.assertEqual((code, self.observed()["outcome"]), (0, "unavailable"))

    def test_optional_codex_host_absent_is_skipped_required_absent_is_unavailable(self):
        module = load("check_codex_host")
        with patch.object(module, "codex_version", return_value=None):
            with patch.dict(os.environ, {"CA_REQUIRE_CODEX": ""}):
                code = self.quiet(lambda: module.main(["--json", "--verdict-output", str(self.path)]))
            self.assertEqual((code, self.observed()["outcome"]), (0, "skipped"))
            self.path.unlink()
            with patch.dict(os.environ, {"CA_REQUIRE_CODEX": "1"}):
                code = self.quiet(lambda: module.main(["--json", "--verdict-output", str(self.path)]))
            self.assertEqual((code, self.observed()["outcome"]), (1, "unavailable"))

    def test_payload_gate_records_first_introduction_and_invalid_base_distinctly(self):
        module = load("payload_version_gate")
        cases = [((module.PASS, "ca-x is new on the base - first introduction, version 0.1.0"),
                  "verified"),
                 ((module.FAIL, "::error::base manifest is invalid"), "rejected")]
        for (code, message), outcome in cases:
            with self.subTest(outcome=outcome):
                if self.path.exists():
                    self.path.unlink()
                with patch.object(module, "gate", return_value=(code, message)), \
                        patch.object(module.integration_candidate, "select", return_value=None):
                    result = self.quiet(lambda: module.main(
                        ["--plugin", "plugins/ca", "--base", "origin/main",
                         "--verdict-output", str(self.path)]))
                self.assertEqual(result, code)
                self.assertEqual(self.observed()["outcome"], outcome)
                self.assertEqual(self.observed()["reason"], message)


if __name__ == "__main__":
    unittest.main()
