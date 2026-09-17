#!/usr/bin/env python3
"""Tests for core/pysrc/_cleanuplib.py's T-05 slice: the operation journal and
the guarded, revalidating branch-deletion executor.

Covers AC-06 (reject stale execution targets -- a late ref move between
inspection and apply is refused, never swept in), AC-09 (protected/occupied
refs are never eligible), AC-14 (one guarded executor that verifies evidence
itself rather than trusting a caller-supplied flag), and AC-19 (per-item
intent is journaled before mutation, outcomes are recorded, and a crash-time
reconciliation resolves pending records from actual state rather than
retrying blindly).

Scope: branch deletion only. Worktree-removal guarding is a distinct,
not-yet-built increment sharing this same journal/executor pattern.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


OID_A = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
OID_B = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"


class JournalTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ca-cleanuplib-journal-")
        os.makedirs(os.path.join(self.root, ".codearbiter"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def journal_path(self):
        return os.path.join(self.root, ".codearbiter", ".resources.json")


class TestJournalBasics(JournalTestCase):
    def test_missing_journal_loads_as_an_empty_envelope(self):
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(journal["operations"], [])

    def test_corrupt_journal_raises_rather_than_silently_resetting(self):
        with open(self.journal_path(), "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(cleanuplib.JournalCorruptError):
            cleanuplib.load_journal(self.root)

    def test_a_journal_with_an_incompatible_schema_raises_rather_than_being_adopted(self):
        # An unrecognized schema (a future version, or a hand-edited/foreign
        # file that merely happens to have an "operations" list) must not be
        # silently loaded, mutated, and rewritten as if it were ours.
        with open(self.journal_path(), "w", encoding="utf-8") as f:
            json.dump({"schema": "cleanup-journal/v2", "operations": []}, f)
        with self.assertRaises(cleanuplib.JournalCorruptError):
            cleanuplib.load_journal(self.root)

    def test_a_journal_with_no_schema_field_at_all_raises(self):
        with open(self.journal_path(), "w", encoding="utf-8") as f:
            json.dump({"operations": []}, f)
        with self.assertRaises(cleanuplib.JournalCorruptError):
            cleanuplib.load_journal(self.root)

    def test_append_pending_then_load_shows_the_pending_record(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
        )
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 1)
        record = journal["operations"][0]
        self.assertEqual(record["operation_id"], op_id)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["target"]["branch"], "x")

    def test_update_outcome_changes_status_and_records_result(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
        )
        cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"detail": "deleted"})
        journal = cleanuplib.load_journal(self.root)
        record = journal["operations"][0]
        self.assertEqual(record["status"], "applied")
        self.assertEqual(record["result"]["detail"], "deleted")
        self.assertIn("completed_at", record)

    def test_updating_an_unknown_operation_id_raises(self):
        with self.assertRaises(KeyError):
            cleanuplib.update_operation_outcome(self.root, "does-not-exist", "applied", {})

    def test_two_operations_get_distinct_ids(self):
        id1 = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={})
        id2 = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={})
        self.assertNotEqual(id1, id2)

    def test_compaction_keeps_all_unresolved_records_regardless_of_count(self):
        ids = [
            cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": i})
            for i in range(25)
        ]
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 25)
        self.assertEqual({op["operation_id"] for op in journal["operations"]}, set(ids))

    def test_compaction_bounds_completed_records_to_the_most_recent_twenty(self):
        ids = []
        for i in range(25):
            op_id = cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"n": i},
            )
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"n": i})
            ids.append(op_id)
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 20)
        kept_ids = {op["operation_id"] for op in journal["operations"]}
        # The most recent 20 survive; the earliest 5 are compacted away.
        self.assertEqual(kept_ids, set(ids[-20:]))

    def test_lock_contention_raises_and_never_touches_the_journal_file(self):
        # AC-19's "partial failure" case at the journal-write seam itself: a
        # concurrent writer already holds the lock. _with_locked_journal
        # deliberately diverges from _hooklib's fail-soft contract (see its
        # docstring) -- a disposable statusline render can no-op on a missed
        # lock, but a mutation-backend journal write cannot, so it raises
        # RuntimeError instead. Confirm both halves: the raise, AND that no
        # partial/corrupt file was written in the process (no silent data loss).
        from _hooklib import acquire_lock, release_lock

        journal_path = self.journal_path()
        os.makedirs(os.path.dirname(journal_path), exist_ok=True)
        held = acquire_lock(journal_path)
        self.assertIsNotNone(held, "test setup failed to acquire its own lock")
        try:
            with self.assertRaises(RuntimeError):
                cleanuplib.append_pending_operation(
                    self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
                )
            self.assertFalse(
                os.path.exists(journal_path),
                "a contended write must not create/corrupt the journal file",
            )
        finally:
            release_lock(held)
        # Confirm the lock's release actually clears the contention -- the
        # same call now succeeds and produces exactly one clean record.
        cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
        )
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 1)

    def test_compaction_never_drops_a_pending_record_to_make_room(self):
        # 20 completed, then 1 pending -- the pending one must survive even
        # though it would be the 21st record.
        for i in range(20):
            op_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": i})
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {})
        pending_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": "last"})
        journal = cleanuplib.load_journal(self.root)
        ids = {op["operation_id"] for op in journal["operations"]}
        self.assertIn(pending_id, ids)


class TestGuardBranchDeletion(unittest.TestCase):
    def _oid_fn(self, mapping):
        return lambda branch: mapping.get(branch)

    def test_clean_case_raises_nothing(self):
        cleanuplib.guard_branch_deletion(
            "feature", OID_A, current_branch="main", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=self._oid_fn({"feature": OID_A}),
        )  # no exception

    def test_refuses_the_current_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="feature", default_branch="main",
                protected_branches=(), worktree_branches=(),
                current_oid_fn=self._oid_fn({"feature": OID_A}),
            )
        self.assertIn("current branch", ctx.exception.reason)

    def test_refuses_the_default_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "main", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches=(),
                current_oid_fn=self._oid_fn({"main": OID_A}),
            )
        self.assertIn("default", ctx.exception.reason)

    def test_refuses_an_explicitly_protected_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "release/pinned", OID_A, current_branch="other", default_branch="main",
                protected_branches=("release/pinned",), worktree_branches=(),
                current_oid_fn=self._oid_fn({"release/pinned": OID_A}),
            )
        self.assertIn("protected", ctx.exception.reason)

    def test_refuses_a_branch_occupied_by_a_worktree(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches=("feature",),
                current_oid_fn=self._oid_fn({"feature": OID_A}),
            )
        self.assertIn("worktree", ctx.exception.reason)

    def test_refuses_when_the_tip_moved_since_inspection(self):
        # The AC-06 "inject a ref move at the mutation seam" case.
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches=(),
                current_oid_fn=self._oid_fn({"feature": OID_B}),
            )
        self.assertIn("stale target", ctx.exception.reason)

    def test_refuses_when_the_branch_no_longer_exists(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches=(),
                current_oid_fn=self._oid_fn({}),
            )
        self.assertIn("no longer exists", ctx.exception.reason)


class TestExecuteBranchDeletion(JournalTestCase):
    def _oid_fn(self, mapping):
        return lambda branch: mapping.get(branch)

    def test_happy_path_journals_pending_then_applied(self):
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=self._oid_fn({"feature": OID_A}),
            delete_fn=delete_fn, allow_force=False,
        )
        self.assertEqual(result.status, "applied")
        # AC-06 (atomic compare-and-delete): the real deletion primitive must
        # receive expected_oid itself, so a concrete implementation can use
        # an atomic compare-and-delete (e.g. `git update-ref -d <ref>
        # <expected_oid>`) rather than a plain `branch -d`/`-D` that performs
        # its own unrelated lookup and could delete a tip our guard never saw.
        self.assertEqual(calls, [("feature", False, OID_A)])
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(journal["operations"][0]["status"], "applied")

    def test_guard_refusal_journals_skipped_and_never_calls_delete_fn(self):
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "main", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=self._oid_fn({"main": OID_A}),
            delete_fn=delete_fn, allow_force=False,
        )
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, [])
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(journal["operations"][0]["status"], "skipped")

    def test_d_failure_without_allow_force_is_recorded_as_failed(self):
        def delete_fn(branch, force, expected_oid):
            return False, "not fully merged"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=self._oid_fn({"feature": OID_A}),
            delete_fn=delete_fn, allow_force=False,
        )
        self.assertEqual(result.status, "failed")

    def test_d_failure_with_allow_force_retries_as_D_when_tip_still_matches(self):
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((force, expected_oid))
            if not force:
                return False, "not fully merged"
            return True, "force-deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=self._oid_fn({"feature": OID_A}),
            delete_fn=delete_fn, allow_force=True,
        )
        # Both attempts must carry the SAME expected_oid the guard validated
        # -- the retry is not a license to re-derive a fresh "current" value.
        self.assertEqual(calls, [(False, OID_A), (True, OID_A)])
        self.assertEqual(result.status, "applied")

    def test_tip_change_before_the_forced_retry_refuses_and_never_calls_D(self):
        # The exact adversarial case the spec names: a ref move injected
        # AT the mutation seam, between the failed -d and the -D retry.
        calls = []
        state = {"feature": OID_A}

        def delete_fn(branch, force, expected_oid):
            calls.append(force)
            if not force:
                state["feature"] = OID_B  # ref moves after the -d attempt
                return False, "not fully merged"
            return True, "force-deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches=(),
            current_oid_fn=lambda b: state.get(b),
            delete_fn=delete_fn, allow_force=True,
        )
        self.assertEqual(calls, [False])  # -D never attempted
        self.assertEqual(result.status, "skipped")
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(journal["operations"][0]["status"], "skipped")


class TestReconcilePendingOperations(JournalTestCase):
    def test_a_pending_branch_delete_whose_branch_is_now_gone_reconciles_to_applied(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "applied")
        self.assertIn("reconciled", record["result"]["detail"])

    def test_a_pending_branch_delete_whose_branch_still_matches_stays_pending(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_A)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "pending")

    def test_a_pending_branch_delete_whose_branch_has_a_different_tip_is_flagged_unknown_not_applied(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_B)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "unknown")

    def test_reconcile_does_not_touch_already_resolved_records(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
        )
        cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"detail": "deleted"})
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_A)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["result"]["detail"], "deleted")  # unchanged


if __name__ == "__main__":
    unittest.main()
