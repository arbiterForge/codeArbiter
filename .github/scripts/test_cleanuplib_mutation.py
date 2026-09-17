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

Also covers defects found by independent review (2026-09-17):
- B-1/B-3: the executor now REQUIRES a ProofResult and derives force
  eligibility from proof.method == "pr_delivery" -- never a caller-supplied
  boolean. A caller cannot "force" a deletion just by asserting a flag; only
  a real PR-delivery proof unlocks the -D-equivalent path.
- B-4: the journal records the proof's method/target/PR fields, not just
  branch/expected_oid, so the audit trail can distinguish a proven batch
  from an unproven one.
- B-6: worktree occupancy is revalidated fresh (via a callable, not a
  static snapshot) immediately before every mutation attempt, including
  the forced retry -- not just once at guard time.
- H-1: a read failure (current_oid_fn raising) is never folded into
  "branch is absent" -- reconcile marks it "unknown", never "applied".
- H-2: journal retention comfortably exceeds the proposal's own named
  40-branch batch example.
- H-3 (partial): repository_id is threaded through and validated for
  consistency across records in the same journal.
- H-4: a claimed-successful delete is reverified before being marked
  "applied".
- H-5: an outcome update for an unknown operation_id never rewrites the
  journal file.
- H-6/M-1: reconcile's kind-scoping and the retention of "unknown" records
  through compaction are both directly tested (previously mutation gaps).
- M-2: a bare string passed where a branch collection is expected raises,
  rather than silently matching by substring.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


OID_A = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
OID_B = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
OID_C = "cccc3333cccc3333cccc3333cccc3333cccc3333"
REPO = "arbiterForge/codeArbiter"


def _proven(method="ancestry", candidate_sha=OID_A, pr_number=None, pr_merge_commit=None, target_repo=REPO):
    return cleanuplib.ProofResult(
        proven=True, method=method, target_ref="origin/main", target_sha=OID_B,
        target_repo=target_repo, candidate_sha=candidate_sha, pr_number=pr_number,
        pr_merge_commit=pr_merge_commit,
        preserves_original_identity=(method == "ancestry"), corroboration=None, reason=None,
    )


def _unproven(candidate_sha=OID_A, reason="not proven", target_repo=REPO):
    return cleanuplib.ProofResult(
        proven=False, method=None, target_ref="origin/main", target_sha=OID_B,
        target_repo=target_repo, candidate_sha=candidate_sha, pr_number=None, pr_merge_commit=None,
        preserves_original_identity=False, corroboration=None, reason=reason,
    )


def _fn(mapping):
    """A current_oid_fn stub: returns mapping.get(branch), i.e. None means
    confirmed absent. Never raises -- see _raising_fn for the unreadable case."""
    return lambda branch: mapping.get(branch)


def _raising_fn(exc=RuntimeError("git call failed")):
    def _f(branch):
        raise exc
    return _f


def _worktrees(names=()):
    names = frozenset(names)
    return lambda: names


class JournalTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ca-cleanuplib-journal-")
        os.makedirs(os.path.join(self.root, ".codearbiter"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def journal_path(self):
        return cleanuplib._journal_path(self.root)


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
        import json
        with open(self.journal_path(), "w", encoding="utf-8") as f:
            json.dump({"schema": "cleanup-journal/v2", "operations": []}, f)
        with self.assertRaises(cleanuplib.JournalCorruptError):
            cleanuplib.load_journal(self.root)

    def test_a_journal_with_no_schema_field_at_all_raises(self):
        import json
        with open(self.journal_path(), "w", encoding="utf-8") as f:
            json.dump({"operations": []}, f)
        with self.assertRaises(cleanuplib.JournalCorruptError):
            cleanuplib.load_journal(self.root)

    def test_append_pending_then_load_shows_the_pending_record(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
            repository_id=REPO,
        )
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 1)
        record = journal["operations"][0]
        self.assertEqual(record["operation_id"], op_id)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["target"]["branch"], "x")
        self.assertEqual(record["repository_id"], REPO)

    def test_update_outcome_changes_status_and_records_result(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
            repository_id=REPO,
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

    def test_updating_an_unknown_operation_id_never_rewrites_the_journal_file(self):
        # H-5: the outcome-write path must check membership BEFORE writing,
        # not write unconditionally and check afterward.
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
            repository_id=REPO,
        )
        before = None
        with open(self.journal_path(), "rb") as f:
            before = f.read()
        with self.assertRaises(KeyError):
            cleanuplib.update_operation_outcome(self.root, "does-not-exist", "applied", {})
        with open(self.journal_path(), "rb") as f:
            after = f.read()
        self.assertEqual(before, after)
        self.assertIsNotNone(op_id)

    def test_two_operations_get_distinct_ids(self):
        id1 = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={}, repository_id=REPO)
        id2 = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={}, repository_id=REPO)
        self.assertNotEqual(id1, id2)

    def test_a_mismatched_repository_id_is_rejected(self):
        # H-3 (partial): Scope.repository_id exists (T-02) and previously
        # nothing in T-05 consulted it. A journal must never silently mix
        # records for two different repositories under one path.
        cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x"}, repository_id=REPO,
        )
        with self.assertRaises(ValueError):
            cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"branch": "y"},
                repository_id="someone-else/other-repo",
            )

    def test_a_missing_repository_id_is_rejected(self):
        # CodeRabbit review (2026-09-17): append_pending_operation must not
        # accept an absent identity -- an unbound record can never be
        # cross-checked against anything.
        with self.assertRaises(ValueError):
            cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"branch": "x"}, repository_id=None,
            )

    def test_an_empty_repository_id_is_rejected(self):
        with self.assertRaises(ValueError):
            cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"branch": "x"}, repository_id="",
            )

    def test_the_same_repository_id_repeated_is_accepted(self):
        cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"branch": "x"}, repository_id=REPO)
        # Must not raise.
        cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"branch": "y"}, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 2)

    def test_lock_contention_raises_and_never_touches_the_journal_file(self):
        from _hooklib import acquire_lock, release_lock

        journal_path = self.journal_path()
        os.makedirs(os.path.dirname(journal_path), exist_ok=True)
        held = acquire_lock(journal_path)
        self.assertIsNotNone(held, "test setup failed to acquire its own lock")
        try:
            with self.assertRaises(RuntimeError):
                cleanuplib.append_pending_operation(
                    self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
                    repository_id=REPO,
                )
            self.assertFalse(
                os.path.exists(journal_path),
                "a contended write must not create/corrupt the journal file",
            )
        finally:
            release_lock(held)
        cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "x", "expected_oid": OID_A},
            repository_id=REPO,
        )
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 1)

    def test_compaction_keeps_all_unresolved_records_regardless_of_count(self):
        ids = [
            cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"n": i}, repository_id=REPO,
            )
            for i in range(45)
        ]
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), 45)
        self.assertEqual({op["operation_id"] for op in journal["operations"]}, set(ids))

    def test_compaction_bounds_completed_records_above_the_named_forty_branch_batch(self):
        # H-2: the proposal's own example is a 40-branch bulk delete. The
        # retention bound must comfortably exceed that so the audit trail
        # for the exact authorized batch is not truncated mid-operation.
        self.assertGreater(cleanuplib._MAX_COMPLETED_RECORDS, 40)
        ids = []
        total = cleanuplib._MAX_COMPLETED_RECORDS + 10
        for i in range(total):
            op_id = cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"n": i}, repository_id=REPO,
            )
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"n": i})
            ids.append(op_id)
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(len(journal["operations"]), cleanuplib._MAX_COMPLETED_RECORDS)
        kept_ids = {op["operation_id"] for op in journal["operations"]}
        self.assertEqual(kept_ids, set(ids[-cleanuplib._MAX_COMPLETED_RECORDS:]))

    def test_a_forty_branch_batch_survives_retention_entirely(self):
        # The exact named scenario: 40 branches, one authorized batch, none
        # compacted away before the batch even finishes.
        ids = []
        for i in range(40):
            op_id = cleanuplib.append_pending_operation(
                self.root, kind="branch_delete", target={"n": i}, repository_id=REPO,
            )
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"n": i})
            ids.append(op_id)
        journal = cleanuplib.load_journal(self.root)
        kept_ids = {op["operation_id"] for op in journal["operations"]}
        self.assertEqual(kept_ids, set(ids))

    def test_compaction_never_drops_a_pending_record_to_make_room(self):
        for i in range(cleanuplib._MAX_COMPLETED_RECORDS):
            op_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": i}, repository_id=REPO)
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {})
        pending_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": "last"}, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        ids = {op["operation_id"] for op in journal["operations"]}
        self.assertIn(pending_id, ids)

    def test_compaction_never_drops_an_unknown_record_to_make_room(self):
        # M-1: "unknown" records (from a reconciliation that could not
        # resolve, or a re-verification failure) must never be compacted
        # away, exactly like "pending" -- only applied/skipped/failed are
        # bounded history.
        for i in range(cleanuplib._MAX_COMPLETED_RECORDS):
            op_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": i}, repository_id=REPO)
            cleanuplib.update_operation_outcome(self.root, op_id, "applied", {})
        unknown_id = cleanuplib.append_pending_operation(self.root, kind="branch_delete", target={"n": "unresolved"}, repository_id=REPO)
        cleanuplib.update_operation_outcome(self.root, unknown_id, "unknown", {"detail": "could not resolve"})
        journal = cleanuplib.load_journal(self.root)
        ids = {op["operation_id"] for op in journal["operations"]}
        self.assertIn(unknown_id, ids)


class TestGuardBranchDeletion(unittest.TestCase):
    def test_clean_case_raises_nothing(self):
        cleanuplib.guard_branch_deletion(
            "feature", OID_A, current_branch="main", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"feature": OID_A}),
        )  # no exception

    def test_refuses_the_current_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="feature", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"feature": OID_A}),
            )
        self.assertIn("current branch", ctx.exception.reason)

    def test_refuses_the_default_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "main", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"main": OID_A}),
            )
        self.assertIn("default", ctx.exception.reason)

    def test_refuses_an_explicitly_protected_branch(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "release/pinned", OID_A, current_branch="other", default_branch="main",
                protected_branches=("release/pinned",), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"release/pinned": OID_A}),
            )
        self.assertIn("protected", ctx.exception.reason)

    def test_refuses_a_branch_occupied_by_a_worktree(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(["feature"]),
                current_oid_fn=_fn({"feature": OID_A}),
            )
        self.assertIn("worktree", ctx.exception.reason)

    def test_worktree_occupancy_is_read_fresh_not_from_a_stale_snapshot(self):
        # B-6: worktree_branches_fn is called AT GUARD TIME, not bound to a
        # value computed earlier -- proven by a callable whose answer
        # changes between construction and the guard call.
        state = {"occupied": frozenset()}
        # Sanity: with nothing occupied yet, the guard passes cleanly.
        cleanuplib.guard_branch_deletion(
            "feature", OID_A, current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=lambda: state["occupied"],
            current_oid_fn=_fn({"feature": OID_A}),
        )
        state["occupied"] = frozenset({"feature"})
        with self.assertRaises(cleanuplib.GuardRefusal):
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=lambda: state["occupied"],
                current_oid_fn=_fn({"feature": OID_A}),
            )

    def test_refuses_when_the_tip_moved_since_inspection(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"feature": OID_B}),
            )
        self.assertIn("stale target", ctx.exception.reason)

    def test_refuses_when_the_branch_no_longer_exists(self):
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({}),
            )
        self.assertIn("no longer exists", ctx.exception.reason)

    def test_refuses_rather_than_crashes_when_current_state_is_unreadable(self):
        # H-1: a read failure must be fail-safe (refuse), and must NOT be
        # confused with "branch confirmed absent."
        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_raising_fn(),
            )
        self.assertIn("could not determine", ctx.exception.reason)

    def test_refuses_rather_than_crashes_when_worktree_state_is_unreadable(self):
        def _raising_worktrees():
            raise RuntimeError("git worktree list failed")

        with self.assertRaises(cleanuplib.GuardRefusal) as ctx:
            cleanuplib.guard_branch_deletion(
                "feature", OID_A, current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_raising_worktrees,
                current_oid_fn=_fn({"feature": OID_A}),
            )
        self.assertIn("worktree occupancy", ctx.exception.reason)

    def test_a_bare_string_protected_branches_raises_instead_of_substring_matching(self):
        # M-2: protected_branches="main" must not silently refuse branch
        # "ai" via `"ai" in "main"` substring semantics.
        with self.assertRaises(TypeError):
            cleanuplib.guard_branch_deletion(
                "ai", OID_A, current_branch="other", default_branch="release",
                protected_branches="main", worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"ai": OID_A}),
            )

    def test_a_bare_string_worktree_branches_result_raises(self):
        with self.assertRaises(TypeError):
            cleanuplib.guard_branch_deletion(
                "ai", OID_A, current_branch="other", default_branch="release",
                protected_branches=(), worktree_branches_fn=lambda: "main",
                current_oid_fn=_fn({"ai": OID_A}),
            )

    def test_rejects_a_non_full_sha_expected_oid(self):
        # M-4: an abbreviated OID must be rejected up front with a clear
        # error rather than silently causing every comparison to "skip" as
        # stale with no diagnosis.
        with self.assertRaises(ValueError):
            cleanuplib.guard_branch_deletion(
                "feature", "abc123", current_branch="other", default_branch="main",
                protected_branches=(), worktree_branches_fn=_worktrees(),
                current_oid_fn=_fn({"feature": "abc123"}),
            )


class TestExecuteBranchDeletion(JournalTestCase):
    def test_happy_path_deletes_and_verifies_gone(self):
        calls = []
        oid_state = {"feature": OID_A}

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            del oid_state[branch]
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(method="ancestry", candidate_sha=OID_A),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=lambda b: oid_state.get(b), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "applied")
        # AC-06 (atomic compare-and-delete): the real deletion primitive must
        # receive expected_oid itself, so a concrete implementation can use
        # an atomic compare-and-delete rather than a plain branch -d/-D.
        self.assertEqual(calls, [("feature", False, OID_A)])
        journal = cleanuplib.load_journal(self.root)
        record = journal["operations"][0]
        self.assertEqual(record["status"], "applied")
        # B-4: the journal records the proof's own fields, not just the bare
        # branch/oid target.
        self.assertEqual(record["proof"]["method"], "ancestry")
        self.assertEqual(record["repository_id"], REPO)

    def test_an_unproven_proof_is_skipped_and_never_calls_delete_fn(self):
        # B-3: the executor requires proof.proven -- "proven-merged" is
        # never caller honor. A branch with NO merge evidence at all must
        # be refused even if every other guard check would pass.
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "totally-unmerged-unique-work",
            _unproven(candidate_sha=OID_A, reason="not an ancestor of origin/main, and no PR delivery record supplied"),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"totally-unmerged-unique-work": OID_A}),
            delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, [])
        self.assertIn("not proven", result.detail)

    def test_a_proof_for_a_different_repository_than_repository_id_is_skipped(self):
        # CodeRabbit review (2026-09-17): ProofResult.target_repo is the
        # repository the proof was actually validated against. A proof
        # computed for one repository must never authorize a deletion
        # journaled/executed under a different repository_id.
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature",
            _proven(candidate_sha=OID_A, target_repo="someone-else/other-repo"),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"feature": OID_A}), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, [])
        self.assertIn("someone-else/other-repo", result.detail)
        self.assertIn(REPO, result.detail)

    def test_guard_refusal_journals_skipped_and_never_calls_delete_fn(self):
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append((branch, force, expected_oid))
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "main", _proven(candidate_sha=OID_A),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"main": OID_A}), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "skipped")
        self.assertEqual(calls, [])

    def test_d_failure_without_pr_delivery_proof_is_recorded_as_failed_never_forced(self):
        # B-1: an ancestry-method proof never permits the force/-D-equivalent
        # path, regardless of any caller wish -- there is no allow_force
        # flag left to set. If the plain attempt fails for an
        # ancestry-proven branch, that is itself suspicious; it fails for
        # investigation rather than escalating.
        calls = []

        def delete_fn(branch, force, expected_oid):
            calls.append(force)
            return False, "not fully merged"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(method="ancestry", candidate_sha=OID_A),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"feature": OID_A}), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(calls, [False])  # force NEVER attempted
        self.assertEqual(result.status, "failed")

    def test_pr_delivery_proof_permits_the_forced_retry_when_the_plain_attempt_fails(self):
        calls = []
        oid_state = {"feature": OID_A}

        def delete_fn(branch, force, expected_oid):
            calls.append(force)
            if not force:
                return False, "not fully merged (expected -- squash landing)"
            del oid_state[branch]
            return True, "force-deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature",
            _proven(method="pr_delivery", candidate_sha=OID_A, pr_number=801, pr_merge_commit=OID_C),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=lambda b: oid_state.get(b), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(calls, [False, True])
        self.assertEqual(result.status, "applied")
        journal = cleanuplib.load_journal(self.root)
        self.assertEqual(journal["operations"][0]["proof"]["pr_number"], 801)

    def test_tip_change_before_the_forced_retry_refuses_and_never_calls_the_forced_attempt(self):
        # The exact adversarial case the spec names: a ref move injected AT
        # the mutation seam, between the failed plain attempt and the
        # forced retry.
        calls = []
        state = {"feature": OID_A}

        def delete_fn(branch, force, expected_oid):
            calls.append(force)
            if not force:
                state["feature"] = OID_B  # ref moves after the plain attempt
                return False, "not fully merged"
            return True, "force-deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(method="pr_delivery", candidate_sha=OID_A, pr_number=1, pr_merge_commit=OID_C),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=lambda b: state.get(b), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(calls, [False])  # forced attempt never made
        self.assertEqual(result.status, "skipped")

    def test_worktree_occupancy_appearing_before_the_forced_retry_refuses(self):
        # B-6: occupancy must be revalidated at the SAME seam as the OID,
        # not only checked once at guard time.
        calls = []
        occupied = {"branches": frozenset()}

        def delete_fn(branch, force, expected_oid):
            calls.append(force)
            if not force:
                occupied["branches"] = frozenset({"feature"})  # a worktree appears
                return False, "not fully merged"
            return True, "force-deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(method="pr_delivery", candidate_sha=OID_A, pr_number=1, pr_merge_commit=OID_C),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=lambda: occupied["branches"],
            current_oid_fn=_fn({"feature": OID_A}), delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(calls, [False])
        self.assertEqual(result.status, "skipped")
        self.assertIn("worktree", result.detail)

    def test_delete_fn_claiming_success_but_ref_still_resolving_is_recorded_as_failed(self):
        # H-4: a claimed-successful delete is reverified, never trusted
        # absolutely. The ref still resolving after a claimed success is a
        # contradiction, not an "applied" outcome.
        def delete_fn(branch, force, expected_oid):
            return True, "deleted"  # lying -- oid_state below is untouched

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(candidate_sha=OID_A),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=_fn({"feature": OID_A}),  # still resolves after "success"
            delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("still resolves", result.detail)

    def test_post_delete_verification_failure_is_unknown_not_applied(self):
        # If we cannot even confirm the branch is gone after delete_fn
        # claims success, that is honestly "unknown," never "applied" --
        # never fold an unreadable check into a positive result either.
        # The guard's own pre-delete read must still succeed (it sees the
        # real tip); only the POST-delete verification read fails.
        calls = {"n": 0}

        def flaky_oid_fn(branch):
            calls["n"] += 1
            if calls["n"] == 1:
                return OID_A  # the guard's pre-delete check
            raise RuntimeError("git call failed")  # the post-delete verification

        def delete_fn(branch, force, expected_oid):
            return True, "deleted"

        result = cleanuplib.execute_branch_deletion(
            self.root, "feature", _proven(candidate_sha=OID_A),
            current_branch="other", default_branch="main",
            protected_branches=(), worktree_branches_fn=_worktrees(),
            current_oid_fn=flaky_oid_fn, delete_fn=delete_fn, repository_id=REPO,
        )
        self.assertEqual(result.status, "unknown")


class TestReconcilePendingOperations(JournalTestCase):
    def test_a_pending_branch_delete_whose_branch_is_now_gone_reconciles_to_applied(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "applied")
        self.assertIn("reconciled", record["result"]["detail"])

    def test_a_pending_branch_delete_whose_branch_still_matches_stays_pending(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_A, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "pending")

    def test_a_pending_branch_delete_whose_branch_has_a_different_tip_is_flagged_unknown_not_applied(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_B, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "unknown")

    def test_a_pending_branch_delete_whose_state_is_unreadable_is_flagged_unknown_never_applied(self):
        # H-1: this is the exact defect found by review -- a read failure
        # (current_oid_fn raising) must never be folded into "branch is
        # absent, mark applied."
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=_raising_fn(), repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "unknown")
        self.assertNotEqual(record["status"], "applied")

    def test_reconcile_does_not_touch_already_resolved_records(self):
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        cleanuplib.update_operation_outcome(self.root, op_id, "applied", {"detail": "deleted"})
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: OID_A, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["result"]["detail"], "deleted")  # unchanged

    def test_reconcile_ignores_a_pending_record_of_a_different_kind(self):
        # H-6: reconcile's kind=="branch_delete" scoping was mutation-
        # uncovered -- nothing proved a non-branch_delete pending record
        # (e.g. a future worktree_remove) is left untouched by branch
        # reconciliation semantics.
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="worktree_remove", target={"path": "/tmp/wt"}, repository_id=REPO,
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "pending")

    def test_reconcile_requires_a_non_empty_repository_id(self):
        # CodeRabbit review (2026-09-17): reconcile must require and
        # validate the current repository identity, not silently process
        # every record regardless of whose repository it belongs to.
        cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id=REPO,
        )
        with self.assertRaises(ValueError):
            cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None, repository_id=None)
        with self.assertRaises(ValueError):
            cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None, repository_id="")

    def test_reconcile_never_touches_a_pending_record_for_a_different_repository(self):
        # A journal path could in principle hold records for a repository
        # other than the one currently reconciling (a caller bug, or a
        # shared path) -- reconcile must never resolve those from THIS
        # repository's git state.
        op_id = cleanuplib.append_pending_operation(
            self.root, kind="branch_delete", target={"branch": "feature", "expected_oid": OID_A},
            repository_id="someone-else/other-repo",
        )
        cleanuplib.reconcile_pending_operations(self.root, current_oid_fn=lambda b: None, repository_id=REPO)
        journal = cleanuplib.load_journal(self.root)
        record = next(op for op in journal["operations"] if op["operation_id"] == op_id)
        self.assertEqual(record["status"], "pending")


if __name__ == "__main__":
    unittest.main()
