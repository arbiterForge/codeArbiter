#!/usr/bin/env python3
"""HW-10 — the closed durable workflow-recovery contract (W-F04, HOOK-B04).

Checks `core/workflow-recovery-contract.json` (the design owner) and the
runtime owner's generated copy in `core/pysrc/_workflowrecoverylib.py`:

* only registered kinds and bounded safe fields are admitted; an unknown
  version or kind is unavailable, never silently accepted or rewritten;
* every transition names a legal from/event/guard/to/effect/reject;
* no forbidden trigger (age, validation pass, branch deletion, generic CLI
  success, ...) can settle an obligation or grant authority;
* Git-common recovery state is never verification input;
* `work_ref: none` registers ordinary work without a task.

Stdlib + unittest only: `python .github/scripts/test_workflow_recovery_contract.py`.
"""

import copy
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "core", "pysrc"))

import _workflowrecoverylib as wr  # noqa: E402

CONTRACT_PATH = os.path.join(REPO, "core", "workflow-recovery-contract.json")
with open(CONTRACT_PATH, encoding="utf-8") as _f:
    CONTRACT = json.load(_f)


def sample_record(**overrides):
    repository = "a" * 32
    origin = "spec:widget#triage-1"
    record = {
        "schema_version": 1,
        "kind": "terminal-harvest",
        "repository_id": repository,
        "worktree_id": "b" * 32,
        "workflow_run_id": "tdd:2026-11-12T10:00:00Z",
        "obligation_id": wr.obligation_id(repository, "tdd:2026-11-12T10:00:00Z",
                                          "terminal-harvest", origin),
        "origin": origin,
        "work_ref": "none",
        "source": {"workflow": "tdd:phase-6", "locator": "spec:widget",
                   "fingerprint": "sha256:" + "c" * 64},
        "candidate": {"revision": 1, "kind": "work", "blocking": "nonblocking",
                      "title": "Handle the empty widget list",
                      "provenance": "tdd Phase 6 NEEDS-TRIAGE"},
        "state": "pending",
        "record_revision": 1,
        "created_at": "2026-11-12T10:00:00Z",
        "updated_at": "2026-11-12T10:00:00Z",
        "last_transition": "WR-01",
        "history": [{"transition": "WR-01", "at": "2026-11-12T10:00:00Z",
                     "record_revision": 1}],
    }
    record.update(overrides)
    return record


class TestEmbeddedCopyIsTheOwner(unittest.TestCase):
    def test_embedded_contract_equals_the_json_owner(self):
        self.assertEqual(wr.CONTRACT, CONTRACT)

    def test_generator_check_is_clean(self):
        result = subprocess.run(
            [sys.executable, os.path.join(REPO, "tools", "build-workflow-recovery-contract.py"),
             "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestAdmission(unittest.TestCase):
    def test_valid_registered_record_is_admitted(self):
        self.assertEqual(wr.classify(sample_record()), (wr.ADMITTED, []))

    def test_work_ref_none_registers_ordinary_work_without_a_task(self):
        self.assertEqual(wr.classify(sample_record(work_ref="none"))[0], wr.ADMITTED)
        self.assertEqual(wr.classify(sample_record(work_ref="native:w-0001"))[0], wr.ADMITTED)
        self.assertNotEqual(wr.classify(sample_record(work_ref="task please"))[0], wr.ADMITTED)

    def test_unknown_version_is_unavailable_not_rewritten(self):
        self.assertEqual(wr.classify(sample_record(schema_version=2))[0],
                         wr.REASON_UNSUPPORTED_VERSION)
        self.assertIn(wr.REASON_UNSUPPORTED_VERSION, CONTRACT["unavailable_reasons"])

    def test_unknown_kind_is_unavailable(self):
        self.assertEqual(wr.classify(sample_record(kind="instruction-replay"))[0],
                         wr.REASON_UNKNOWN_KIND)
        self.assertEqual(list(CONTRACT["kinds"]), ["terminal-harvest"])

    def test_closed_record_rejects_additional_and_forbidden_fields(self):
        for extra in ({"notes": "x"}, {"authorized": True}, {"command": "rm -rf /"},
                      {"argv": ["sh"]}, {"transcript": "..."}):
            record = sample_record()
            record.update(extra)
            outcome, errors = wr.classify(record, registration=True)
            self.assertEqual(outcome, wr.REASON_INVALID, extra)
            self.assertTrue(errors)
        nested = sample_record()
        nested["candidate"] = dict(nested["candidate"], permission="granted")
        self.assertEqual(wr.classify(nested, registration=True)[0], wr.REASON_INVALID)

    def test_on_disk_defect_is_corrupt_not_invalid(self):
        record = sample_record()
        del record["origin"]
        self.assertEqual(wr.classify(record)[0], wr.REASON_CORRUPT)
        self.assertEqual(wr.classify("not a record")[0], wr.REASON_CORRUPT)

    def test_bounded_fields(self):
        long_title = sample_record()
        long_title["candidate"] = dict(long_title["candidate"], title="x" * 201)
        self.assertEqual(wr.classify(long_title, registration=True)[0], wr.REASON_INVALID)
        big = sample_record()
        big["candidate"] = dict(big["candidate"], description="y" * 4000,
                                boundaries=["z" * 128] * 16)
        self.assertEqual(wr.classify(big)[0], wr.ADMITTED)
        too_many = sample_record()
        too_many["candidate"] = dict(too_many["candidate"], boundaries=["z"] * 17)
        self.assertEqual(wr.classify(too_many, registration=True)[0], wr.REASON_INVALID)
        self.assertEqual(CONTRACT["bounds"]["registration_max_bytes"], 65536)
        self.assertEqual(CONTRACT["bounds"]["scan_max_summaries"], 32)
        self.assertEqual(CONTRACT["bounds"]["scan_max_bytes"], 262144)
        self.assertEqual(CONTRACT["bounds"]["batch_max_candidates"], 32)

    def test_errors_never_echo_the_offending_value(self):
        record = sample_record(origin="SECRET-VALUE-../../x")
        _outcome, errors = wr.classify(record, registration=True)
        self.assertTrue(errors)
        self.assertFalse(any("SECRET-VALUE" in e for e in errors))

    def test_origin_cannot_traverse(self):
        self.assertNotEqual(wr.classify(sample_record(origin="../../etc/passwd#1"),
                                        registration=True)[0], wr.ADMITTED)

    def test_unregistered_producer_and_candidate_kind_are_rejected(self):
        bad_source = sample_record()
        bad_source["source"] = dict(bad_source["source"], workflow="shell:anything")
        self.assertEqual(wr.classify(bad_source, registration=True)[0], wr.REASON_INVALID)
        bad_kind = sample_record()
        bad_kind["candidate"] = dict(bad_kind["candidate"], kind="script")
        self.assertEqual(wr.classify(bad_kind, registration=True)[0], wr.REASON_INVALID)

    def test_state_specific_requirements(self):
        self.assertEqual(wr.classify(sample_record(state="settled"))[0], wr.REASON_CORRUPT)
        self.assertEqual(wr.classify(sample_record(state="claimed"))[0], wr.REASON_CORRUPT)
        self.assertEqual(wr.classify(sample_record(state="unavailable"))[0], wr.REASON_CORRUPT)
        self.assertEqual(wr.classify(sample_record(state="unavailable",
                                                   reason="source-stale"))[0], wr.ADMITTED)
        self.assertEqual(wr.classify(sample_record(state="absent"))[0], wr.REASON_CORRUPT)


class TestIdentities(unittest.TestCase):
    def test_obligation_id_is_stable_and_origin_bound(self):
        a = wr.obligation_id("r", "run", "terminal-harvest", "spec:x#triage-1")
        self.assertEqual(a, wr.obligation_id("r", "run", "terminal-harvest", "spec:x#triage-1"))
        self.assertNotEqual(a, wr.obligation_id("r", "run", "terminal-harvest", "spec:x#triage-2"))
        self.assertRegex(a, CONTRACT["record"]["fields"]["obligation_id"]["pattern"])

    def test_effect_identity_changes_with_candidate_revision(self):
        one = wr.effect_operation_id("ob-x", 1, "native-work", "create")
        self.assertEqual(one, wr.effect_operation_id("ob-x", 1, "native-work", "create"))
        self.assertNotEqual(one, wr.effect_operation_id("ob-x", 2, "native-work", "create"))
        self.assertRegex(one, CONTRACT["record"]["fields"]["claim"]["fields"]
                         ["effect_operation_id"]["pattern"])


class TestTransitionTable(unittest.TestCase):
    def setUp(self):
        self.states = set(CONTRACT["states"])
        self.events = CONTRACT["events"]
        self.rows = CONTRACT["transitions"]

    def _from_states(self, row):
        if row["from"] == "any-persisted":
            return self.states - {"absent"}
        return set(row["from"].split("|"))

    def test_every_row_is_complete_and_legal(self):
        ids = [row["id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for row in self.rows:
            for field in ("id", "from", "event", "guard", "to", "effects", "on_reject"):
                self.assertTrue(isinstance(row.get(field), str) and row[field].strip(),
                                "{} lacks {}".format(row.get("id"), field))
            self.assertTrue(self._from_states(row) <= self.states, row["id"])
            self.assertIn(row["event"], self.events, row["id"])
            self.assertIn(row["to"], self.states | {"observed"}, row["id"])
            if row["to"] == "settled" and row["from"] != "settled":
                dispositions = set(row["disposition"].split("|"))
                self.assertTrue(dispositions <= set(CONTRACT["settled_dispositions"]), row["id"])

    def test_every_event_is_used_and_every_state_is_handled(self):
        used = {row["event"] for row in self.rows}
        self.assertEqual(used, set(self.events))
        for state in self.states - {"absent"}:
            self.assertTrue(any(state in self._from_states(r) for r in self.rows), state)
        # Read-only reentry exists for the two unresolved resting states.
        for state in ("pending", "unavailable"):
            scans = [r for r in self.rows if r["event"] == "scan" and state in self._from_states(r)]
            self.assertTrue(scans, state)
            self.assertTrue(all(r["to"] == state for r in scans), state)

    def test_settled_is_entered_only_by_observed_or_explicit_events(self):
        allowed = set(CONTRACT["settled_entry_events"])
        for row in self.rows:
            if row["to"] == "settled" and row["from"] != "settled":
                self.assertIn(row["event"], allowed, row["id"])
        self.assertEqual(allowed, {"decline", "target-readback-proves-effect",
                                   "reconcile-proves-effect", "cancel", "supersede"})

    def test_no_forbidden_trigger_drives_any_transition(self):
        forbidden = set(CONTRACT["forbidden_transition_triggers"])
        for trigger in ("elapsed-age", "validation-pass", "branch-deletion",
                        "generic-cli-success", "error", "absent-response"):
            self.assertIn(trigger, forbidden)
        for row in self.rows:
            self.assertNotIn(row["event"], forbidden, row["id"])
        self.assertTrue(forbidden.isdisjoint(self.events))

    def test_settled_is_terminal_and_never_reopened(self):
        for row in self.rows:
            if "settled" in self._from_states(row) and row["from"] != "any-persisted":
                self.assertEqual(row["to"], "settled", row["id"])
        self.assertEqual(CONTRACT["terminal_states"], ["settled"])

    def test_claims_are_never_stolen_by_time(self):
        busy = wr.transition("WR-12")
        self.assertIn("no TTL-based theft", busy["effects"])
        lost = wr.transition("WR-10")
        self.assertIn("never blindly replays", lost["effects"])

    def test_corrections_cannot_clear_denial_or_stop(self):
        self.assertEqual(set(CONTRACT["correction_cannot_clear"]),
                         {"authorization-denied", "explicit-stop"})
        for reason in CONTRACT["unavailable_reasons"]:
            self.assertIn(reason, CONTRACT["reason_recovery"], reason)
        self.assertEqual(set(CONTRACT["reason_recovery"]), set(CONTRACT["unavailable_reasons"]))

    def test_no_field_can_carry_a_reusable_grant(self):
        fields = json.dumps(CONTRACT["record"]["fields"]).lower()
        self.assertNotIn('"authorized"', fields)
        self.assertNotIn('"approved"', fields)
        for key in ("authorized", "approval", "permission", "grant", "command", "shell"):
            self.assertIn(key, CONTRACT["record"]["forbidden_keys"])

    def test_result_forbids_empty_success_for_incomplete_reads(self):
        result = CONTRACT["result"]
        self.assertEqual(result["fields"]["inventory"], ["complete", "partial", "unavailable"])
        self.assertEqual(result["fields"]["write"], ["committed", "not-committed", "uncertain"])
        self.assertIn("never reports zero", result["empty_success_forbidden"])


class TestStorageIsNeverVerificationInput(unittest.TestCase):
    def test_contract_places_state_under_git_common_and_excludes_it(self):
        storage = CONTRACT["storage"]
        self.assertEqual(storage["base"], "git-common-dir")
        self.assertEqual(storage["subtree"], "codearbiter/workflow-recovery/v1")
        self.assertEqual(storage["verification_input"], "never")
        self.assertEqual(storage["caller_supplied_root"], "forbidden-in-installed-operation")

    def test_native_input_policy_still_refuses_git_paths(self):
        """The exclusion this contract relies on is the native engine's, not a
        promise here: pin that InputIncludes still refuses .git paths."""
        path = os.path.join(REPO, "core", "artifacts", "internal", "validate", "input_policy.go")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertRegex(source, r"func IsGitPath\(p string\) bool")
        body = source[source.index("func InputIncludes"):]
        self.assertRegex(body.split("\n}\n", 1)[0],
                         r"if IsRuntimeMarkerPath\(target\) \|\| IsGitPath\(target\) \{\s*return false")


class TestAdrBoundariesAndNonGoals(unittest.TestCase):
    def test_adr_boundaries_preserved(self):
        boundaries = CONTRACT["adr_boundaries"]
        self.assertIn("before staging", boundaries["ADR-0008"])
        self.assertIn("does not supersede", boundaries["ADR-0036"])
        self.assertIn("no universal gate", boundaries["ADR-0043"])

    def test_non_goals_exclude_daemon_database_replay_and_gate(self):
        text = " ".join(CONTRACT["non_goals"])
        for phrase in ("daemon", "database", "generic command", "universal permission"):
            self.assertIn(phrase, text)

    def test_retention_never_ages_out_unresolved_records(self):
        self.assertIn("never aged out", CONTRACT["retention"]["unresolved"])
        self.assertIn("nothing older is evicted", CONTRACT["retention"]["capacity"])


if __name__ == "__main__":
    unittest.main()
