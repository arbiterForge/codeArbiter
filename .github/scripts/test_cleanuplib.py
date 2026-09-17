#!/usr/bin/env python3
"""Tests for core/pysrc/_cleanuplib.py's integration-proof evaluator (T-04).

Covers AC-07 (ancestry, separated from branch-discovery/upstream state, works
without gh), AC-08 (repository-qualified PR delivery proof; tree-equality is
corroboration only, never sufficient alone), and AC-10 (original commit
identity is preserved by ancestry landings, never claimed for squash/PR
delivery landings).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


CANDIDATE = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
TARGET_REF = "origin/main"
TARGET_SHA = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
INTEGRATION_REPO = "arbiterForge/codeArbiter"


def _is_ancestor_factory(true_for):
    """Build an is_ancestor(a, b) stub that's True only for the given (a, b) pairs."""
    true_for = set(true_for)

    def _is_ancestor(a, b):
        return (a, b) in true_for

    return _is_ancestor


def _always_false(*_args, **_kwargs):
    return False


class TestAncestryProof(unittest.TestCase):
    """AC-07: ancestry targets the authorized integration ref; no gh required."""

    def test_ancestor_of_target_is_proven_without_any_pr_or_tree_input(self):
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
        )
        self.assertTrue(result.proven)
        self.assertEqual(result.method, "ancestry")
        self.assertTrue(result.preserves_original_identity)
        self.assertIsNone(result.pr_number)

    def test_ancestry_targets_the_authorized_ref_not_an_arbitrary_upstream(self):
        # is_ancestor is only true against a DIFFERENT sha than the authorized
        # target -- e.g. the candidate's own (now-deleted) upstream tip, not
        # origin/main. A passing check against the wrong ref must not prove
        # anything here: the caller is required to pass the authorized
        # target's own sha, and the evaluator never substitutes another one.
        wrong_target_sha = "cccc3333cccc3333cccc3333cccc3333cccc3333"
        is_ancestor = _is_ancestor_factory([(CANDIDATE, wrong_target_sha)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
        )
        self.assertFalse(result.proven)

    def test_gone_upstream_state_plays_no_role_in_the_evaluator_at_all(self):
        # The evaluator's signature has no upstream-state parameter -- gone,
        # absent or still-existing upstream is a standup/discovery concern
        # that never reaches this function. Ancestry alone decides.
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
        )
        self.assertTrue(result.proven)


class TestPrDeliveryProof(unittest.TestCase):
    """AC-08: repository-qualified PR delivery proof for a non-ancestry (squash) landing."""

    def _pr(self, **overrides):
        record = {
            "number": 799,
            "state": "MERGED",
            "head_sha": CANDIDATE,
            "base_repo": INTEGRATION_REPO,
            "merge_commit_sha": "dddd4444dddd4444dddd4444dddd4444dddd4444",
        }
        record.update(overrides)
        return record

    def test_valid_squash_landing_is_proven_and_does_not_preserve_original_identity(self):
        merge_sha = "dddd4444dddd4444dddd4444dddd4444dddd4444"
        is_ancestor = _is_ancestor_factory([(merge_sha, TARGET_SHA)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
            pr_record=self._pr(merge_commit_sha=merge_sha),
        )
        self.assertTrue(result.proven)
        self.assertEqual(result.method, "pr_delivery")
        self.assertEqual(result.pr_number, 799)
        # AC-10: a squash delivery is never represented as preserving the
        # original branch commits' identity.
        self.assertFalse(result.preserves_original_identity)

    def test_valid_squash_landing_survives_additional_default_commits_afterward(self):
        # "Later default advancement ... is not a failure when the exact
        # landing is demonstrably retained in the authorized target."
        merge_sha = "dddd4444dddd4444dddd4444dddd4444dddd4444"
        is_ancestor = _is_ancestor_factory([(merge_sha, TARGET_SHA)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
            pr_record=self._pr(merge_commit_sha=merge_sha),
        )
        self.assertTrue(result.proven)

    def test_wrong_base_repository_is_rejected(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=self._pr(base_repo="some-fork/codeArbiter"),
        )
        self.assertFalse(result.proven)
        self.assertIn("integration repository", result.reason)

    def test_fork_name_collision_is_rejected_by_repo_qualification(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=self._pr(base_repo="attacker/codeArbiter"),
        )
        self.assertFalse(result.proven)

    def test_changed_head_after_recorded_merge_is_rejected(self):
        # local tip moved after the PR merged -- head_sha no longer matches
        stale_head = "eeee5555eeee5555eeee5555eeee5555eeee5555"
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=self._pr(head_sha=stale_head),
        )
        self.assertFalse(result.proven)
        self.assertIn("does not match candidate tip", result.reason)

    def test_closed_but_unmerged_pr_is_rejected(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=self._pr(state="CLOSED"),
        )
        self.assertFalse(result.proven)
        self.assertIn("not MERGED", result.reason)

    def test_missing_landing_object_not_retained_in_target_is_rejected(self):
        # merge_commit_sha exists on the PR record but is NOT an ancestor of
        # the fetched target -- the landing commit was never retained there.
        is_ancestor = _always_false
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
            pr_record=self._pr(),
        )
        self.assertFalse(result.proven)
        self.assertIn("not retained", result.reason)

    def test_ambiguous_or_incomplete_pr_record_missing_fields_is_rejected(self):
        incomplete = {"number": 799, "state": "MERGED"}  # no head_sha, base_repo, merge_commit_sha
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=incomplete,
        )
        self.assertFalse(result.proven)
        self.assertIn("missing required field", result.reason)

    def test_equal_tree_with_no_pr_record_and_no_ancestry_is_not_proof(self):
        # Tree-equality-only evidence must never grant eligibility by itself.
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=None, tree_equal_fn=lambda a, b: True,
        )
        self.assertFalse(result.proven)
        self.assertIn("corroboration only", result.reason)
        self.assertIsNotNone(result.corroboration)

    def test_equal_tree_alongside_an_invalid_pr_record_is_still_not_proof(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=self._pr(state="CLOSED"), tree_equal_fn=lambda a, b: True,
        )
        self.assertFalse(result.proven)

    def test_renamed_base_ref_is_accepted_when_landing_is_retained(self):
        # "A historical base-ref rename or an indirect integration is
        # acceptable when that same landing commit is retained."
        merge_sha = "dddd4444dddd4444dddd4444dddd4444dddd4444"
        is_ancestor = _is_ancestor_factory([(merge_sha, TARGET_SHA)])
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, is_ancestor,
            pr_record=self._pr(merge_commit_sha=merge_sha, base_ref="master-legacy"),
        )
        self.assertTrue(result.proven)

    def test_no_pr_record_and_no_gh_leaves_the_reason_specific_not_generic(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            pr_record=None,
        )
        self.assertFalse(result.proven)
        self.assertIn("no PR delivery record", result.reason)


class TestStructuredUnprovenReason(unittest.TestCase):
    """Every decision has a structured proof or a specific unproven reason (T-04 Done-when)."""

    def test_unproven_result_always_carries_a_non_empty_reason(self):
        result = cleanuplib.evaluate_merge_proof(
            CANDIDATE, TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
        )
        self.assertFalse(result.proven)
        self.assertTrue(result.reason)
        self.assertIsNone(result.method)

    def test_invalid_empty_candidate_sha_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            cleanuplib.evaluate_merge_proof(
                "", TARGET_REF, TARGET_SHA, INTEGRATION_REPO, _always_false,
            )

    def test_invalid_empty_target_sha_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            cleanuplib.evaluate_merge_proof(
                CANDIDATE, TARGET_REF, "", INTEGRATION_REPO, _always_false,
            )


if __name__ == "__main__":
    unittest.main()
