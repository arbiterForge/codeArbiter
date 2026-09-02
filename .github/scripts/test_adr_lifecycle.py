#!/usr/bin/env python3
"""ADR-0033 lifecycle integrity contract."""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import adr_lifecycle as al
    import check_adr_lifecycle as cal
except ImportError:
    al = None
    cal = None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


ADR = b"""---\nstatus: accepted\ndate: 2026-09-02\ntitle: T\ndecided-by: user@example.com\nsupersedes: none\ngoverns: src/*\n---\n# ADR-0001 \xe2\x80\x94 T\n\n## Status\nAccepted\n\n## Context\nC\n\n## Decision\nD\n\n## Alternatives considered\n- none\n\n## Consequences\nK\n\n## Risks\nR\n"""


def _tech_checker_commands(text):
    return [line.strip() for line in text.splitlines()
            if "check_adr_lifecycle.py" in line and not line.lstrip().startswith("#")]


def _ci_checker_commands(text):
    """Extract normalized YAML run scalars that invoke the lifecycle checker."""
    lines = text.splitlines()
    commands = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", lines[index])
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        value = match.group(2).strip()
        if value in ("|", ">", "|-", ">-"):
            parts = []
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                if line.strip() and not line.lstrip().startswith("#"):
                    parts.append(line.strip())
                index += 1
            value = " ".join(parts)
        else:
            index += 1
        value = value.strip("'\"")
        if "check_adr_lifecycle.py" in value:
            commands.append(value)
    return commands


class LifecycleContractTest(unittest.TestCase):
    def setUp(self):
        if al is None:
            self.fail("adr_lifecycle module is missing")
        if cal is None:
            self.fail("check_adr_lifecycle module is missing")

    def _acceptance(self):
        obligations = [{
            "id": "0001-test.o1",
            "section": "Decision",
            "text": "D",
            "text_sha256": _sha(b"D"),
        }]
        return {
            "schema": "adr-lifecycle/v1",
            "event": "acceptance",
            "adr": "0001-test",
            "recorded_at": "2026-09-02T12:00:00Z",
            "source_commit": "a" * 40,
            "blob_sha256": _sha(ADR),
            "body_sha256": _sha(al.immutable_body(ADR)),
            "obligations": obligations,
            "obligations_sha256": al.obligation_set_digest(obligations),
            "obligations_sealed": True,
        }

    def _git(self, root, *args):
        result = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, check=False,
            env=dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                     GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com"),
        )
        self.assertEqual(
            result.returncode, 0,
            "%s\nstdout=%s\nstderr=%s" %
            (" ".join(args), result.stdout.decode(errors="replace"),
             result.stderr.decode(errors="replace")),
        )
        return result.stdout.decode().strip()

    def _write_ledger(self, root, events):
        path = os.path.join(root, ".codearbiter", "decisions", "adr-lifecycle.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    def _committed_evidence_repo(self, root, input_digest=None, input_path="src/x.py"):
        self._git(root, "init", "-b", "main")
        decisions = os.path.join(root, ".codearbiter", "decisions")
        os.makedirs(decisions)
        os.makedirs(os.path.join(root, "src"))
        with open(os.path.join(decisions, "0001-test.md"), "wb") as handle:
            handle.write(ADR)
        with open(os.path.join(root, "src", "x.py"), "wb") as handle:
            handle.write(b"source-v1")
        self._git(root, "add", ".codearbiter/decisions/0001-test.md", "src/x.py")
        self._git(root, "commit", "-m", "seed accepted ADR and implementation input")
        source_commit = self._git(root, "rev-parse", "HEAD")
        digest = input_digest or _sha(b"source-v1")
        acceptance = self._acceptance()
        acceptance["source_commit"] = source_commit
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": source_commit, "input_digests": {input_path: digest},
            "evidence": "repository implementation commit %s" % source_commit,
        }
        verification = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": source_commit, "input_digests": {input_path: digest},
            "proof_contract": "repo-ci/v1", "producer": "github-actions/run-1",
            "command": "python test.py", "observed_at": "2026-09-02T12:00:00Z",
            "valid_until": "2026-09-03T12:00:00Z", "claim_scope": "repository",
            "claim": "repository test contract passed",
        }
        return acceptance, implementation, verification

    def _run_checker(self, root, *args, env=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = cal.main(["--root", root, *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_body_digest_excludes_mutable_status_but_binds_decision_body(self):
        changed_status = ADR.replace(b"status: accepted", b"status: superseded").replace(
            b"## Status\nAccepted", b"## Status\nSuperseded")
        changed_decision = ADR.replace(b"## Decision\nD", b"## Decision\nDifferent")
        self.assertEqual(al.immutable_body(ADR), al.immutable_body(changed_status))
        self.assertNotEqual(al.immutable_body(ADR), al.immutable_body(changed_decision))

    def test_integrity_digest_binds_metadata_and_heading_outside_status_fields(self):
        for changed in (
            ADR.replace(b"title: T", b"title: Changed"),
            ADR.replace(b"date: 2026-09-02", b"date: 2026-09-03"),
            ADR.replace(b"decided-by: user@example.com", b"decided-by: other@example.com"),
            ADR.replace(b"supersedes: none", b"supersedes: 0000-old"),
            ADR.replace(b"governs: src/*", b"governs: lib/*"),
            ADR.replace(b"# ADR-0001 \xe2\x80\x94 T", b"# ADR-0001 \xe2\x80\x94 Changed"),
        ):
            with self.subTest(changed=changed[:100]):
                self.assertNotEqual(al.immutable_body(ADR), al.immutable_body(changed))

    def test_status_attribution_is_bound_but_recognized_value_transition_is_mutable(self):
        attributed = ADR.replace(
            b"## Status\nAccepted",
            b"## Status\nAccepted - approved by user@example.com",
        )
        changed_attribution = attributed.replace(
            b"approved by user@example.com", b"approved by other@example.com")
        transitioned = attributed.replace(b"status: accepted", b"status: superseded").replace(
            b"## Status\nAccepted", b"## Status\nSuperseded")
        self.assertNotEqual(
            al.immutable_body(attributed), al.immutable_body(changed_attribution))
        self.assertEqual(al.immutable_body(attributed), al.immutable_body(transitioned))

    def test_status_section_rejects_arbitrary_or_frontmatter_mismatched_values(self):
        arbitrary = ADR.replace(b"## Status\nAccepted", b"## Status\nUnreviewed prose")
        mismatched = ADR.replace(b"status: accepted", b"status: proposed")
        for blob in (arbitrary, mismatched):
            with self.subTest(blob=blob[:120]):
                with self.assertRaises(ValueError):
                    al.immutable_body(blob)

    def test_malformed_or_duplicate_status_structure_fails_closed(self):
        malformed = ADR.replace(b"status: accepted\n", b"status accepted\n")
        duplicate = ADR.replace(b"status: accepted\n", b"status: accepted\nstatus: proposed\n")
        duplicate_heading = ADR.replace(
            b"## Context\nC\n", b"## Status\nAccepted again\n\n## Context\nC\n")
        for blob in (malformed, duplicate, duplicate_heading):
            with self.subTest(blob=blob[:100]):
                with self.assertRaises(ValueError):
                    al.immutable_body(blob)

    def test_second_acceptance_binding_is_rejected(self):
        event = self._acceptance()
        errors = al.validate_events([event, dict(event)], {"0001-test": ADR})
        self.assertTrue(any("second acceptance" in e for e in errors), errors)

    def test_legacy_baseline_must_be_unsealed_and_never_claims_acceptance_time(self):
        event = self._acceptance()
        event.update(event="baseline", obligations=[], obligations_sealed=False,
                     obligations_sha256=al.obligation_set_digest([]))
        event.pop("source_commit")
        event["observed_commit"] = "c" * 40
        self.assertEqual(al.validate_events([event], {"0001-test": ADR}), [])
        event["obligations_sealed"] = True
        errors = al.validate_events([event], {"0001-test": ADR})
        self.assertTrue(any("baseline" in e and "unsealed" in e for e in errors), errors)

    def test_blob_mutation_rejects_bound_accepted_body(self):
        event = self._acceptance()
        changed = ADR.replace(b"## Decision\nD", b"## Decision\nChanged")
        errors = al.validate_events([event], {"0001-test": changed})
        self.assertTrue(any("immutable-body digest" in e for e in errors), errors)

    def test_status_only_transition_preserves_the_bound_immutable_body(self):
        event = self._acceptance()
        changed_status = ADR.replace(b"status: accepted", b"status: superseded").replace(
            b"## Status\nAccepted", b"## Status\nSuperseded")
        self.assertEqual(al.validate_events([event], {"0001-test": changed_status}), [])

    def test_acceptance_source_commit_must_contain_the_exact_bound_git_blob(self):
        validator = getattr(al, "validate_source_blobs", None)
        self.assertIsNotNone(validator, "source-commit blob validation is missing")
        event = self._acceptance()
        key = (event["source_commit"], event["adr"])
        self.assertEqual(validator([event], {key: ADR}), [])
        errors = validator([event], {key: ADR + b"tampered"})
        self.assertTrue(any("source-commit blob digest" in e for e in errors), errors)

    def test_acceptance_and_baseline_source_blobs_must_be_accepted(self):
        acceptance = self._acceptance()
        proposed = ADR.replace(b"status: accepted", b"status: proposed").replace(
            b"## Status\nAccepted", b"## Status\nProposed")
        acceptance.update(
            blob_sha256=_sha(proposed), body_sha256=_sha(al.immutable_body(proposed)))
        key = (acceptance["source_commit"], acceptance["adr"])
        errors = al.validate_source_blobs([acceptance], {key: proposed})
        self.assertTrue(any("must be accepted" in error for error in errors), errors)

        baseline = dict(
            acceptance,
            event="baseline",
            observed_commit="c" * 40,
            obligations=[],
            obligations_sha256=al.obligation_set_digest([]),
            obligations_sealed=False,
        )
        baseline.pop("source_commit")
        rejected = ADR.replace(b"status: accepted", b"status: rejected").replace(
            b"## Status\nAccepted", b"## Status\nRejected")
        baseline.update(
            blob_sha256=_sha(rejected), body_sha256=_sha(al.immutable_body(rejected)))
        key = (baseline["observed_commit"], baseline["adr"])
        errors = al.validate_source_blobs([baseline], {key: rejected})
        self.assertTrue(any("must be accepted" in error for error in errors), errors)

    def test_baseline_observed_commit_must_contain_the_migration_blob(self):
        event = self._acceptance()
        event.update(event="baseline", obligations=[], obligations_sealed=False,
                     obligations_sha256=al.obligation_set_digest([]),
                     observed_commit="c" * 40)
        event.pop("source_commit")
        key = (event["observed_commit"], event["adr"])
        self.assertEqual(al.validate_source_blobs([event], {key: ADR}), [])
        errors = al.validate_source_blobs([event], {key: ADR + b"tampered"})
        self.assertTrue(any("migration-snapshot blob digest" in e for e in errors), errors)

    def test_sealed_obligation_set_digest_and_stable_ids_are_required(self):
        event = self._acceptance()
        event["obligations_sha256"] = "0" * 64
        errors = al.validate_events([event], {"0001-test": ADR})
        self.assertTrue(any("obligation-set digest" in e for e in errors), errors)
        event = self._acceptance()
        event["obligations"][0]["id"] = "foreign.o1"
        errors = al.validate_events([event], {"0001-test": ADR})
        self.assertTrue(any("stem-scoped" in e for e in errors), errors)
        event = self._acceptance()
        event["obligations"][0]["section"] = "Risks"
        event["obligations_sha256"] = al.obligation_set_digest(event["obligations"])
        errors = al.validate_events([event], {"0001-test": ADR})
        self.assertTrue(any("section binding" in e for e in errors), errors)

    def test_sealed_acceptance_requires_at_least_one_obligation(self):
        event = self._acceptance()
        event["obligations"] = []
        event["obligations_sha256"] = al.obligation_set_digest([])
        errors = al.validate_events([event], {"0001-test": ADR})
        self.assertTrue(any("sealed acceptance obligation set is empty" in e
                            for e in errors), errors)

        self.assertEqual(al.validate_events([self._acceptance()], {"0001-test": ADR}), [])
        baseline = self._acceptance()
        baseline["event"] = "baseline"
        baseline.pop("source_commit")
        baseline["observed_commit"] = "a" * 40
        baseline["obligations_sealed"] = False
        baseline["obligations"] = []
        baseline["obligations_sha256"] = al.obligation_set_digest([])
        self.assertEqual(al.validate_events([baseline], {"0001-test": ADR}), [])

    def test_verified_export_requires_implementation_fresh_inputs_and_current_blob(self):
        acceptance = self._acceptance()
        input_digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented",
            "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40,
            "input_digests": {"src/x.py": input_digest},
            "evidence": "PR #1 commit " + "b" * 40,
        }
        verification = {
            "schema": "adr-lifecycle/v1", "event": "verified",
            "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40,
            "input_digests": {"src/x.py": input_digest},
            "proof_contract": "repo-ci/v1",
            "producer": "github-actions/run-1",
            "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z",
            "valid_until": "2026-09-03T12:00:00Z",
            "claim": "repository test contract passed",
            "claim_scope": "repository",
        }
        events = [acceptance, implementation, verification]
        exported, errors = al.verified_export(
            events, {"0001-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-02T13:00:00Z")
        self.assertEqual(errors, [])
        self.assertEqual([x["obligation"] for x in exported], ["0001-test.o1"])
        self.assertEqual(exported[0]["input_digests"], {"src/x.py": input_digest})
        for field in ("producer", "command", "observed_at", "valid_until",
                      "claim_scope", "claim"):
            self.assertIn(field, exported[0])
        stale, errors = al.verified_export(
            events, {"0001-test": ADR}, {"src/x.py": b"source-v2"},
            now="2026-09-02T13:00:00Z")
        self.assertEqual(stale, [])
        self.assertTrue(any("input digest" in e for e in errors), errors)
        expired, errors = al.verified_export(
            events, {"0001-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-04T13:00:00Z")
        self.assertEqual(expired, [])
        self.assertTrue(any("expired" in e for e in errors), errors)

        implementation["input_digests"] = {"src/x.py": _sha(b"source-v2")}
        exported, errors = al.verified_export(
            events, {"0001-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-02T13:00:00Z")
        self.assertEqual(exported, [])
        self.assertTrue(any("implementation input digest" in e for e in errors), errors)

    def test_evidence_fields_order_and_uniqueness_are_required(self):
        acceptance = self._acceptance()
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented",
            "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40,
            "input_digests": {"src/x.py": "1" * 64},
            "evidence": "repository implementation commit",
        }
        verification = {
            "schema": "adr-lifecycle/v1", "event": "verified",
            "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40,
            "input_digests": {"src/x.py": "1" * 64},
            "proof_contract": "repo-ci/v1",
            "producer": "github-actions/run-1",
            "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z",
            "valid_until": "2026-09-03T12:00:00Z",
            "claim": "repository test contract passed",
            "claim_scope": "repository",
        }
        errors = al.validate_events([acceptance, verification, implementation], {"0001-test": ADR})
        self.assertTrue(any("before implementation" in e for e in errors), errors)
        errors = al.validate_events(
            [acceptance, implementation, verification,
             dict(verification, event_id="verify-2")],
            {"0001-test": ADR},
        )
        self.assertFalse(any("duplicate verified" in e for e in errors), errors)
        duplicate_id = dict(verification)
        errors = al.validate_events(
            [acceptance, implementation, verification, duplicate_id],
            {"0001-test": ADR},
        )
        self.assertTrue(any("duplicate event_id" in e for e in errors), errors)
        missing_scope = dict(verification)
        missing_scope.pop("claim_scope")
        errors = al.validate_events(
            [acceptance, implementation, missing_scope], {"0001-test": ADR})
        self.assertTrue(any("claim_scope" in e for e in errors), errors)

    def test_expired_evidence_can_be_renewed_append_only_and_invalidated_by_id(self):
        acceptance = self._acceptance()
        digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40, "input_digests": {"src/x.py": digest},
            "evidence": "implementation commit",
        }
        expired = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-old",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40, "input_digests": {"src/x.py": digest},
            "proof_contract": "repo-ci/v1", "producer": "ci/run-old",
            "command": "python test.py", "observed_at": "2026-09-01T12:00:00Z",
            "valid_until": "2026-09-02T12:00:00Z", "claim_scope": "repository",
            "claim": "repository test contract passed",
        }
        renewed = dict(
            expired,
            event_id="verify-new",
            producer="ci/run-new",
            observed_at="2026-09-02T12:30:00Z",
            valid_until="2026-09-03T12:30:00Z",
        )
        exported, errors = al.verified_export(
            [acceptance, implementation, expired, renewed],
            {"0001-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-02T13:00:00Z",
        )
        self.assertEqual(errors, [])
        self.assertEqual(exported[0]["producer"], "ci/run-new")
        invalidation = {
            "schema": "adr-lifecycle/v1", "event": "invalidated",
            "event_id": "invalidate-new", "target_event_id": "verify-new",
            "recorded_at": "2026-09-02T12:45:00Z", "reason": "proof withdrawn",
        }
        exported, errors = al.verified_export(
            [acceptance, implementation, expired, renewed, invalidation],
            {"0001-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-02T13:00:00Z",
        )
        self.assertEqual(exported, [])
        self.assertTrue(any("no current verification" in e for e in errors), errors)

    def test_evidence_commits_and_path_digests_are_recomputed_from_git_bytes(self):
        acceptance = self._acceptance()
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40,
            "input_digests": {"src/x.py": _sha(b"source-v1")},
            "evidence": "implementation commit",
        }
        self.assertEqual(
            al.validate_evidence_sources(
                [acceptance, implementation], {("b" * 40, "src/x.py"): b"source-v1"}),
            [],
        )
        errors = al.validate_evidence_sources(
            [acceptance, implementation], {("b" * 40, "src/x.py"): b"tampered"})
        self.assertTrue(any("Git input digest" in e for e in errors), errors)

    def test_time_boundaries_are_timezone_aware_and_ordered(self):
        acceptance = self._acceptance()
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40, "input_digests": {"src/x.py": _sha(b"x")},
            "evidence": "implementation commit",
        }
        proof = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1",
            "source_commit": "b" * 40, "input_digests": {"src/x.py": _sha(b"x")},
            "proof_contract": "repo-ci/v1", "producer": "ci/run",
            "command": "python test.py", "observed_at": "2026-09-03T12:00:00",
            "valid_until": "2026-09-02T12:00:00Z", "claim_scope": "repository",
            "claim": "repository test contract passed",
        }
        errors = al.validate_events([acceptance, implementation, proof], {"0001-test": ADR})
        self.assertTrue(any("timezone" in e or "after valid_until" in e for e in errors), errors)

    def test_any_structural_ledger_error_suppresses_all_verified_claims(self):
        acceptance = self._acceptance()
        broken = dict(acceptance, schema="unsupported")
        exported, errors = al.verified_export(
            [broken], {"0001-test": ADR}, {}, now="2026-09-02T13:00:00Z")
        self.assertEqual(exported, [])
        self.assertTrue(errors)

    def test_verified_required_strings_and_implementation_evidence_fail_closed(self):
        acceptance = self._acceptance()
        digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "evidence": "implementation commit",
        }
        verification = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "proof_contract": "repo-ci/v1",
            "producer": "ci/run", "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z", "valid_until": "2026-09-03T12:00:00Z",
            "claim_scope": "repository", "claim": "repository test contract passed",
        }
        for field in ("proof_contract", "producer", "command", "observed_at",
                      "valid_until", "claim"):
            for malformed in (None, "", "   ", []):
                with self.subTest(field=field, malformed=malformed):
                    bad = dict(verification, **{field: malformed})
                    exported, errors = al.verified_export(
                        [acceptance, implementation, bad], {"0001-test": ADR},
                        {"src/x.py": b"source-v1"}, now="2026-09-02T13:00:00Z")
                    self.assertEqual(exported, [])
                    self.assertTrue(any(field in error for error in errors), errors)
        identity_cases = {
            "event_id": ("", "event_id"),
            "adr": (None, "ADR"),
            "obligation": (None, "obligation"),
            "source_commit": (None, "source_commit"),
            "claim_scope": (None, "claim_scope"),
        }
        for field, (malformed, diagnostic) in identity_cases.items():
            with self.subTest(field=field, malformed=malformed):
                bad = dict(verification, **{field: malformed})
                exported, errors = al.verified_export(
                    [acceptance, implementation, bad], {"0001-test": ADR},
                    {"src/x.py": b"source-v1"}, now="2026-09-02T13:00:00Z")
                self.assertEqual(exported, [])
                self.assertTrue(any(diagnostic in error for error in errors), errors)
        for malformed in (None, "", "   ", [], {}):
            with self.subTest(implementation_evidence=malformed):
                bad = dict(implementation, evidence=malformed)
                exported, errors = al.verified_export(
                    [acceptance, bad, verification], {"0001-test": ADR},
                    {"src/x.py": b"source-v1"}, now="2026-09-02T13:00:00Z")
                self.assertEqual(exported, [])
                self.assertTrue(any("implementation evidence" in error for error in errors), errors)

    def test_duplicate_obligations_and_invalidations_fail_closed(self):
        acceptance = self._acceptance()
        duplicate = dict(acceptance["obligations"][0])
        acceptance["obligations"].append(duplicate)
        acceptance["obligations_sha256"] = al.obligation_set_digest(acceptance["obligations"])
        exported, errors = al.verified_export(
            [acceptance], {"0001-test": ADR}, {}, now="2026-09-02T13:00:00Z")
        self.assertEqual(exported, [])
        self.assertTrue(any("duplicate obligation id" in error for error in errors), errors)

        acceptance = self._acceptance()
        digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "evidence": "implementation commit",
        }
        verification = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "proof_contract": "repo-ci/v1",
            "producer": "ci/run", "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z", "valid_until": "2026-09-03T12:00:00Z",
            "claim_scope": "repository", "claim": "repository test contract passed",
        }
        base = [acceptance, implementation, verification]
        cases = {
            "forward target": ([acceptance, {
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-forward", "target_event_id": "verify-1",
                "recorded_at": "2026-09-02T12:30:00Z", "reason": "withdrawn",
            }, implementation, verification], "target"),
            "unknown target": (base + [{
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-unknown", "target_event_id": "verify-missing",
                "recorded_at": "2026-09-02T12:30:00Z", "reason": "withdrawn",
            }], "target"),
            "duplicate invalidation id": (base + [{
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-1", "target_event_id": "verify-1",
                "recorded_at": "2026-09-02T12:30:00Z", "reason": "withdrawn",
            }, {
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-1", "target_event_id": "impl-1",
                "recorded_at": "2026-09-02T12:31:00Z", "reason": "withdrawn",
            }], "duplicate event_id"),
            "missing reason": (base + [{
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-no-reason", "target_event_id": "verify-1",
                "recorded_at": "2026-09-02T12:30:00Z",
            }], "reason"),
            "malformed recorded_at": (base + [{
                "schema": "adr-lifecycle/v1", "event": "invalidated",
                "event_id": "invalidate-bad-time", "target_event_id": "verify-1",
                "recorded_at": "not-a-time", "reason": "withdrawn",
            }], "recorded_at"),
        }
        for name, (events, diagnostic) in cases.items():
            with self.subTest(name=name):
                exported, errors = al.verified_export(
                    events, {"0001-test": ADR}, {"src/x.py": b"source-v1"},
                    now="2026-09-02T13:00:00Z")
                self.assertEqual(exported, [])
                self.assertTrue(any(diagnostic in error for error in errors), errors)

    def test_one_incomplete_obligation_suppresses_otherwise_valid_claims(self):
        acceptance = self._acceptance()
        second = dict(acceptance["obligations"][0], id="0001-test.o2")
        acceptance["obligations"].append(second)
        acceptance["obligations_sha256"] = al.obligation_set_digest(
            acceptance["obligations"])
        digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "evidence": "implementation commit",
        }
        proof = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-1",
            "adr": "0001-test", "obligation": "0001-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "proof_contract": "repo-ci/v1",
            "producer": "ci/run", "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z", "valid_until": "2026-09-03T12:00:00Z",
            "claim_scope": "repository", "claim": "repository test contract passed",
        }
        exported, errors = al.verified_export(
            [acceptance, implementation, proof], {"0001-test": ADR},
            {"src/x.py": b"source-v1"}, now="2026-09-02T13:00:00Z")
        self.assertEqual(exported, [])
        self.assertTrue(any("0001-test.o2" in error for error in errors), errors)

    def test_unsealed_or_unimplemented_obligations_never_export(self):
        baseline = self._acceptance()
        baseline.update(event="baseline", obligations=[], obligations_sealed=False,
                        obligations_sha256=al.obligation_set_digest([]))
        baseline.pop("source_commit")
        baseline["observed_commit"] = "c" * 40
        exported, errors = al.verified_export(
            [baseline], {"0001-test": ADR}, {}, now="2026-09-02T13:00:00Z")
        self.assertEqual(exported, [])
        self.assertTrue(any("unsealed" in e for e in errors), errors)

    def test_incomplete_adr_does_not_hide_another_fully_verified_adr(self):
        incomplete = self._acceptance()
        complete = self._acceptance()
        complete["adr"] = "0002-test"
        complete["obligations"][0]["id"] = "0002-test.o1"
        complete["obligations_sha256"] = al.obligation_set_digest(
            complete["obligations"])
        digest = _sha(b"source-v1")
        implementation = {
            "schema": "adr-lifecycle/v1", "event": "implemented", "event_id": "impl-2",
            "adr": "0002-test", "obligation": "0002-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "evidence": "implementation commit",
        }
        proof = {
            "schema": "adr-lifecycle/v1", "event": "verified", "event_id": "verify-2",
            "adr": "0002-test", "obligation": "0002-test.o1", "source_commit": "b" * 40,
            "input_digests": {"src/x.py": digest}, "proof_contract": "repo-ci/v1",
            "producer": "ci/run", "command": "python test.py",
            "observed_at": "2026-09-02T12:00:00Z", "valid_until": "2026-09-03T12:00:00Z",
            "claim_scope": "repository", "claim": "repository test contract passed",
        }
        exported, errors = al.verified_export(
            [incomplete, complete, implementation, proof],
            {"0001-test": ADR, "0002-test": ADR}, {"src/x.py": b"source-v1"},
            now="2026-09-02T13:00:00Z")
        self.assertEqual([row["adr"] for row in exported], ["0002-test"])
        self.assertTrue(any("0001-test.o1" in error for error in errors), errors)

    def test_append_only_requires_base_bytes_as_exact_prefix(self):
        self.assertEqual(al.append_only_error(b"one\n", b"one\ntwo\n"), None)
        self.assertIsNotNone(al.append_only_error(b"one\n", b"changed\ntwo\n"))

    def test_ci_base_selection_covers_pull_request_merge_group_and_push(self):
        self.assertEqual(
            cal.select_base_ref("pull_request", {"pull_request": {"base": {"sha": "pr-base"}}}),
            "pr-base",
        )
        self.assertEqual(
            cal.select_base_ref("merge_group", {"merge_group": {"base_sha": "queue-base"}}),
            "queue-base",
        )
        self.assertEqual(cal.select_base_ref("push", {"before": "push-base"}), "push-base")
        with self.assertRaises(ValueError):
            cal.select_base_ref("workflow_dispatch", {})

    def test_verified_json_stdout_is_exactly_one_machine_payload(self):
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, ".codearbiter", "decisions")
            os.makedirs(directory)
            ledger = os.path.join(directory, "adr-lifecycle.jsonl")
            with open(ledger, "w", encoding="utf-8") as handle:
                handle.write("")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = cal.main([
                    "--root", root, "--verified-json", "--current-ref", "HEAD",
                    "--now", "2026-09-02T13:00:00Z",
                ])
            self.assertEqual(result, 0)
            self.assertEqual(stdout.getvalue(), "[]\n")
            self.assertEqual(stderr.getvalue(), "")

            with open(ledger, "w", encoding="utf-8") as handle:
                handle.write("not-json\n")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = cal.main([
                    "--root", root, "--verified-json", "--current-ref", "HEAD",
                    "--now", "2026-09-02T13:00:00Z",
                ])
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "[]\n")
            self.assertIn("::error::", stderr.getvalue())

    def test_verified_json_recomputes_real_committed_inputs_and_fails_closed(self):
        expected = {
            "adr": "0001-test", "obligation": "0001-test.o1",
            "claim": "repository test contract passed", "claim_scope": "repository",
            "command": "python test.py", "input_digests": {"src/x.py": _sha(b"source-v1")},
            "observed_at": "2026-09-02T12:00:00Z", "producer": "github-actions/run-1",
            "proof_contract": "repo-ci/v1", "source_commit": None,
            "valid_until": "2026-09-03T12:00:00Z",
        }
        with tempfile.TemporaryDirectory() as root:
            acceptance, implementation, verification = self._committed_evidence_repo(root)
            expected["source_commit"] = implementation["source_commit"]
            self._write_ledger(root, [acceptance, implementation, verification])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "record lifecycle evidence")
            result, stdout, stderr = self._run_checker(
                root, "--verified-json", "--current-ref", "HEAD",
                "--now", "2026-09-02T13:00:00Z")
            self.assertEqual(result, 0, stderr)
            self.assertEqual(stdout, json.dumps([expected], sort_keys=True,
                                                separators=(",", ":")) + "\n")
            self.assertEqual(stderr, "")

        for name, digest, path in (
                ("missing", _sha(b"source-v1"), "src/missing.py"),
                ("tampered", "0" * 64, "src/x.py")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                acceptance, implementation, verification = self._committed_evidence_repo(
                    root, input_digest=digest, input_path=path)
                self._write_ledger(root, [acceptance, implementation, verification])
                self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
                self._git(root, "commit", "-m", "record invalid lifecycle evidence")
                result, stdout, stderr = self._run_checker(
                    root, "--verified-json", "--current-ref", "HEAD",
                    "--now", "2026-09-02T13:00:00Z")
                self.assertEqual(result, 1)
                self.assertEqual(stdout, "[]\n")
                self.assertIn("::error::", stderr)
                self.assertNotIn("Traceback", stderr)

    def test_verified_json_preserves_complete_adr_when_another_is_incomplete(self):
        expected_digest = _sha(b"source-v1")
        with tempfile.TemporaryDirectory() as root:
            incomplete, _, _ = self._committed_evidence_repo(root)
            decisions = os.path.join(root, ".codearbiter", "decisions")
            second_adr = ADR.replace(b"ADR-0001", b"ADR-0002")
            with open(os.path.join(decisions, "0002-test.md"), "wb") as handle:
                handle.write(second_adr)
            self._git(root, "add", ".codearbiter/decisions/0002-test.md")
            self._git(root, "commit", "-m", "add second accepted ADR")
            source_commit = self._git(root, "rev-parse", "HEAD")

            complete = self._acceptance()
            complete.update({
                "adr": "0002-test",
                "source_commit": source_commit,
                "blob_sha256": _sha(second_adr),
                "body_sha256": _sha(al.immutable_body(second_adr)),
            })
            complete["obligations"][0]["id"] = "0002-test.o1"
            complete["obligations_sha256"] = al.obligation_set_digest(
                complete["obligations"])
            implementation = {
                "schema": "adr-lifecycle/v1", "event": "implemented",
                "event_id": "impl-2", "adr": "0002-test",
                "obligation": "0002-test.o1", "source_commit": source_commit,
                "input_digests": {"src/x.py": expected_digest},
                "evidence": "repository implementation commit %s" % source_commit,
            }
            verification = {
                "schema": "adr-lifecycle/v1", "event": "verified",
                "event_id": "verify-2", "adr": "0002-test",
                "obligation": "0002-test.o1", "source_commit": source_commit,
                "input_digests": {"src/x.py": expected_digest},
                "proof_contract": "repo-ci/v1", "producer": "github-actions/run-2",
                "command": "python test.py", "observed_at": "2026-09-02T12:00:00Z",
                "valid_until": "2026-09-03T12:00:00Z", "claim_scope": "repository",
                "claim": "second repository test contract passed",
            }
            self._write_ledger(root, [incomplete, complete, implementation, verification])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "record mixed lifecycle evidence")

            result, stdout, stderr = self._run_checker(
                root, "--verified-json", "--current-ref", "HEAD",
                "--now", "2026-09-02T13:00:00Z")
            expected = [{
                "adr": "0002-test", "obligation": "0002-test.o1",
                "claim": "second repository test contract passed",
                "claim_scope": "repository", "source_commit": source_commit,
                "input_digests": {"src/x.py": expected_digest},
                "proof_contract": "repo-ci/v1", "producer": "github-actions/run-2",
                "command": "python test.py", "observed_at": "2026-09-02T12:00:00Z",
                "valid_until": "2026-09-03T12:00:00Z",
            }]
            self.assertEqual(result, 0, stderr)
            self.assertEqual(stdout, json.dumps(
                expected, sort_keys=True, separators=(",", ":")) + "\n")
            self.assertIn("0001-test.o1", stderr)
            self.assertIn("::warning::", stderr)
            self.assertNotIn("::error::", stderr)

    def test_checker_ignores_ambient_repository_selectors_for_explicit_root(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as foreign:
            acceptance, implementation, verification = self._committed_evidence_repo(root)
            self._write_ledger(root, [acceptance, implementation, verification])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "record lifecycle evidence")

            self._git(foreign, "init", "-b", "foreign")
            with open(os.path.join(foreign, "foreign.txt"), "w", encoding="utf-8") as handle:
                handle.write("foreign repository\n")
            self._git(foreign, "add", "foreign.txt")
            self._git(foreign, "commit", "-m", "foreign repository")

            result, stdout, stderr = self._run_checker(
                root, "--verified-json", "--current-ref", "HEAD",
                "--now", "2026-09-02T13:00:00Z",
                env={
                    "GIT_DIR": os.path.join(foreign, ".git"),
                    "GIT_WORK_TREE": foreign,
                    "GIT_OBJECT_DIRECTORY": os.path.join(foreign, ".git", "objects"),
                },
            )
            self.assertEqual(result, 0, stderr)
            self.assertEqual(len(json.loads(stdout)), 1)
            self.assertEqual(stderr, "")

    def test_github_events_compare_real_committed_ledger_blobs(self):
        with tempfile.TemporaryDirectory() as root:
            acceptance, implementation, verification = self._committed_evidence_repo(root)
            self._write_ledger(root, [acceptance])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "record acceptance")
            base = self._git(root, "rev-parse", "HEAD")
            base_bytes = cal._ledger_at(root, base)
            self._write_ledger(root, [acceptance, implementation, verification])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "append evidence")
            self.assertEqual(cal._ledger_at(root, "HEAD")[:len(base_bytes)], base_bytes)
            payloads = {
                "pull_request": {"pull_request": {"base": {"sha": base}}},
                "merge_group": {"merge_group": {"base_sha": base}},
                "push": {"before": base},
            }
            for event_name, payload in payloads.items():
                with self.subTest(event_name=event_name):
                    event_path = os.path.join(root, "event-%s.json" % event_name)
                    with open(event_path, "w", encoding="utf-8") as handle:
                        json.dump(payload, handle)
                    result, stdout, stderr = self._run_checker(
                        root, "--github-event", "--current-ref", "HEAD",
                        env={"GITHUB_EVENT_NAME": event_name,
                             "GITHUB_EVENT_PATH": event_path})
                    self.assertEqual((result, stderr), (0, ""))
                    self.assertIn("ADR lifecycle bindings valid", stdout)

    def test_github_event_ledger_rewrite_truncation_and_bad_bases_fail_closed(self):
        for mutation in ("rewrite", "truncate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                acceptance, implementation, verification = self._committed_evidence_repo(root)
                self._write_ledger(root, [acceptance, implementation, verification])
                self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
                self._git(root, "commit", "-m", "record base ledger")
                base = self._git(root, "rev-parse", "HEAD")
                if mutation == "rewrite":
                    changed = dict(acceptance, recorded_at="2026-09-02T12:01:00Z")
                    self._write_ledger(root, [changed, implementation, verification])
                else:
                    self._write_ledger(root, [acceptance])
                self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
                self._git(root, "commit", "-m", mutation + " ledger")
                event_path = os.path.join(root, "event.json")
                with open(event_path, "w", encoding="utf-8") as handle:
                    json.dump({"before": base}, handle)
                result, _stdout, stderr = self._run_checker(
                    root, "--github-event", "--current-ref", "HEAD",
                    env={"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": event_path})
                self.assertEqual(result, 1)
                self.assertIn("rewrites or truncates base history", stderr)

        bad_event_bases = {
            ("pull_request", "missing"): {"pull_request": {"base": {}}},
            ("pull_request", "all-zero"): {
                "pull_request": {"base": {"sha": "0" * 40}}},
            ("merge_group", "missing"): {"merge_group": {}},
            ("merge_group", "all-zero"): {"merge_group": {"base_sha": "0" * 40}},
            ("push", "missing"): {},
            ("push", "all-zero"): {"before": "0" * 40},
        }
        for (event_name, condition), payload in bad_event_bases.items():
            with self.subTest(event_name=event_name, condition=condition), \
                    tempfile.TemporaryDirectory() as root:
                acceptance, implementation, verification = self._committed_evidence_repo(root)
                self._write_ledger(root, [acceptance, implementation, verification])
                self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
                self._git(root, "commit", "-m", "record ledger")
                event_path = os.path.join(root, "event.json")
                with open(event_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
                result, stdout, stderr = self._run_checker(
                    root, "--github-event", "--current-ref", "HEAD",
                    env={"GITHUB_EVENT_NAME": event_name,
                         "GITHUB_EVENT_PATH": event_path})
                self.assertEqual(result, 1)
                self.assertNotIn("ADR lifecycle bindings valid", stdout)
                self.assertIn("no usable base commit", stderr)
                self.assertNotIn("Traceback", stderr)

        with tempfile.TemporaryDirectory() as root:
            acceptance, implementation, verification = self._committed_evidence_repo(root)
            self._write_ledger(root, [acceptance, implementation, verification])
            self._git(root, "add", ".codearbiter/decisions/adr-lifecycle.jsonl")
            self._git(root, "commit", "-m", "record ledger")
            event_path = os.path.join(root, "event.json")
            with open(event_path, "w", encoding="utf-8") as handle:
                json.dump({"before": "f" * 40}, handle)
            result, stdout, stderr = self._run_checker(
                root, "--github-event", "--current-ref", "HEAD",
                env={"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": event_path})
            self.assertEqual(result, 1)
            self.assertNotIn("ADR lifecycle bindings valid", stdout)
            self.assertIn("could not inspect", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_security_controls_define_lifecycle_ledger_identity_and_enforcement(self):
        root = os.path.dirname(os.path.dirname(HERE))
        with open(os.path.join(root, ".codearbiter", "security-controls.md"),
                  encoding="utf-8") as handle:
            controls = handle.read()
        audit = controls.split("## Audit trail", 1)[1].split("\n---", 1)[0]
        self.assertIn(".codearbiter/decisions/adr-lifecycle.jsonl", audit)
        self.assertIn("case-folded", audit)
        self.assertIn("append-only", audit)
        self.assertIn("H-05", audit)
        self.assertIn("H-11", audit)
        self.assertIn("committed Git blobs", audit)
        self.assertIn("exact byte prefix", audit)

    def test_malformed_typed_events_stay_inside_machine_error_envelope(self):
        binding = self._acceptance()
        null_baseline = dict(
            binding,
            event="baseline",
            observed_commit=None,
            obligations=[],
            obligations_sha256=al.obligation_set_digest([]),
            obligations_sealed=False,
        )
        null_baseline.pop("source_commit")
        malformed_events = [
            [{
                "schema": "adr-lifecycle/v1", "event": "implemented",
                "event_id": "impl-null", "adr": "0001-test",
                "obligation": "0001-test.o1", "source_commit": "b" * 40,
                "input_digests": None, "evidence": "x",
            }],
            [{
                "schema": "adr-lifecycle/v1", "event": "verified",
                "event_id": "verify-list", "adr": "0001-test",
                "obligation": "0001-test.o1", "source_commit": "b" * 40,
                "input_digests": [], "proof_contract": "repo-ci/v1",
                "producer": "ci/run", "command": "test", "claim_scope": "repository",
                "claim": "x", "observed_at": "2026-09-02T12:00:00Z",
                "valid_until": "2026-09-03T12:00:00Z",
            }],
            [dict(binding, obligations=None)],
            [dict(binding, source_commit=None)],
            [null_baseline],
        ]
        for events in malformed_events:
            with self.subTest(events=events):
                with tempfile.TemporaryDirectory() as root:
                    directory = os.path.join(root, ".codearbiter", "decisions")
                    os.makedirs(directory)
                    with open(os.path.join(directory, "0001-test.md"), "wb") as handle:
                        handle.write(ADR)
                    with open(os.path.join(directory, "adr-lifecycle.jsonl"), "w",
                              encoding="utf-8") as handle:
                        for event in events:
                            handle.write(json.dumps(event) + "\n")
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        result = cal.main([
                            "--root", root, "--verified-json", "--current-ref", "HEAD",
                            "--now", "2026-09-02T13:00:00Z",
                        ])
                    self.assertEqual(result, 1)
                    self.assertEqual(stdout.getvalue(), "[]\n")
                    self.assertIn("::error::", stderr.getvalue())
                    self.assertNotIn("Traceback", stderr.getvalue())

    def test_bound_superseded_adr_remains_available_for_lifecycle_validation(self):
        reader = getattr(al, "read_adrs", None)
        self.assertIsNotNone(reader, "all-state ADR reader is missing")
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, ".codearbiter", "decisions")
            os.makedirs(directory)
            with open(os.path.join(directory, "0001-test.md"), "wb") as handle:
                handle.write(ADR.replace(b"status: accepted", b"status: superseded").replace(
                    b"## Status\nAccepted", b"## Status\nSuperseded"))
            self.assertIn("0001-test", reader(root))
            self.assertNotIn("0001-test", al.read_accepted_adrs(root))

    def test_accepted_reader_rejects_duplicate_or_malformed_status(self):
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, ".codearbiter", "decisions")
            os.makedirs(directory)
            with open(os.path.join(directory, "0001-test.md"), "wb") as handle:
                handle.write(ADR.replace(
                    b"status: accepted\n", b"status: accepted\nstatus: proposed\n"))
            errors = []
            accepted = al.read_accepted_adrs(root, errors=errors)
            self.assertEqual(accepted, {})
            self.assertTrue(any("duplicate frontmatter key" in error for error in errors), errors)

    def test_repository_ledger_and_all_accepted_adrs_validate(self):
        root = os.path.dirname(os.path.dirname(HERE))
        events = al.read_jsonl(os.path.join(
            root, ".codearbiter", "decisions", "adr-lifecycle.jsonl"))
        blobs = al.read_accepted_adrs(root)
        errors = al.validate_events(events, blobs, require_all_accepted=True)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_canonical_adr_skill_distinguishes_acceptance_from_delivery(self):
        root = os.path.dirname(os.path.dirname(HERE))
        skill_path = os.path.join(
            root, "core", "surface", "skills", "decision-lifecycle", "SKILL.md")
        template_path = os.path.join(
            root, "core", "surface", "skills", "decision-lifecycle", "references",
            "adr-template.md")
        with open(skill_path, encoding="utf-8") as handle:
            skill = handle.read()
        with open(template_path, encoding="utf-8") as handle:
            template = handle.read()
        self.assertIn("Accepted/Planned", skill)
        self.assertIn("changes both the frontmatter `status:` field and the `## Status` value",
                      template)
        self.assertIn("without changing any other body content", template)
        self.assertRegex(
            skill,
            r"(?s)commit the accepted ADR.*append.*acceptance binding.*subsequent commit",
        )
        self.assertIn("adr-lifecycle.jsonl", skill)
        self.assertIn("sealed obligation", skill)
        self.assertIn("only the recognized status value", skill)
        self.assertIn("approval attribution", skill)
        self.assertIn("Implemented", template)
        self.assertIn("Verified", template)
        self.assertRegex(template, r"(?s)accepted.*does not imply.*implementation")

    def test_security_controls_separate_append_only_enforcement_from_jsonl_validation(self):
        root = os.path.dirname(os.path.dirname(HERE))
        path = os.path.join(root, ".codearbiter", "security-controls.md")
        with open(path, encoding="utf-8") as handle:
            controls = handle.read()
        self.assertIn("H-05 enforces append-only write", controls)
        self.assertIn("lifecycle checker separately validates JSONL syntax", controls)
        self.assertIn("event\ncompleteness, schema, and committed-prefix integrity", controls)

    def test_ci_runs_lifecycle_and_destructive_registry_contracts(self):
        root = os.path.dirname(os.path.dirname(HERE))
        with open(os.path.join(root, ".github", "workflows", "ci.yml"), encoding="utf-8") as handle:
            workflow = handle.read()
        self.assertIn("python .github/scripts/test_adr_lifecycle.py", workflow)
        ci_command = (
            "python .github/scripts/check_adr_lifecycle.py --github-event --current-ref HEAD")
        self.assertEqual(_ci_checker_commands(workflow), [ci_command])
        self.assertIn("python .github/scripts/check_destructive_registry.py", workflow)
        push_prefix = workflow.split("permissions:", 1)[0]
        self.assertIn('- ".codearbiter/decisions/**"', push_prefix)
        with open(os.path.join(root, ".codearbiter", "tech-stack.md"), encoding="utf-8") as handle:
            tech_stack = handle.read()
        self.assertIn("python .github/scripts/test_adr_lifecycle.py", tech_stack)
        local_command = "python .github/scripts/check_adr_lifecycle.py"
        self.assertEqual(_tech_checker_commands(tech_stack), [local_command])
        self.assertIn("python .github/scripts/check_destructive_registry.py", tech_stack)

        for mutated in (
                tech_stack + "\n" + local_command + "\n",
                tech_stack.replace(local_command, local_command + " --current-ref HEAD")):
            with self.subTest(context="tech-stack", mutated=mutated[-120:]):
                self.assertNotEqual(_tech_checker_commands(mutated), [local_command])
        workflow_run = "        run: " + ci_command
        for mutated in (
                workflow + "\n" + workflow_run + "\n",
                workflow.replace(workflow_run, workflow_run + " --now 2026-09-02T13:00:00Z")):
            with self.subTest(context="ci", mutated=mutated[-160:]):
                self.assertNotEqual(_ci_checker_commands(mutated), [ci_command])


if __name__ == "__main__":
    unittest.main()
