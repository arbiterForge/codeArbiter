#!/usr/bin/env python3
"""Tests for core/pysrc/_cleanuplib.py's integration-proof evaluator (T-04).

Covers AC-07 (ancestry, separated from branch-discovery/upstream state, works
without gh), AC-08 (repository-qualified PR delivery proof; tree-equality is
corroboration only, never sufficient alone), and AC-10 (original commit
identity is preserved by ancestry landings, never claimed for squash/PR
delivery landings).

Also covers a defect found by independent review (2026-09-17): the ancestry
path checked no repository binding at all, so ANY target_sha the caller
supplied "proved" ancestry regardless of which repository it actually came
from -- only the PR-delivery path was repository-qualified. `target_repo`
is now a required, explicitly asserted fact checked unconditionally before
either proof path runs.
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


def _evaluate(candidate_sha=CANDIDATE, target_ref=TARGET_REF, target_sha=TARGET_SHA,
              target_repo=INTEGRATION_REPO, integration_repo=INTEGRATION_REPO,
              is_ancestor=_always_false, pr_record=None, tree_equal_fn=None):
    return cleanuplib.evaluate_merge_proof(
        candidate_sha, target_ref, target_sha, target_repo, integration_repo,
        is_ancestor, pr_record=pr_record, tree_equal_fn=tree_equal_fn,
    )


class TestAncestryProof(unittest.TestCase):
    """AC-07: ancestry targets the authorized integration ref; no gh required."""

    def test_ancestor_of_target_is_proven_without_any_pr_or_tree_input(self):
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])
        result = _evaluate(is_ancestor=is_ancestor)
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
        result = _evaluate(is_ancestor=is_ancestor)
        self.assertFalse(result.proven)

    def test_ancestry_is_rejected_when_the_fetched_target_repo_is_not_the_authorized_one(self):
        # The defect this closes: is_ancestor(candidate, target_sha) being
        # True is not proof by itself -- target_sha must also be asserted to
        # have come from the authorized integration_repo. A caller (or a
        # bug upstream of this function) that resolved target_sha from the
        # WRONG repository -- a fork, an unrelated repo, a stale local
        # remote -- must never "prove" ancestry just because the two shas
        # happen to relate in whatever history the caller queried.
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])  # would otherwise prove
        result = _evaluate(target_repo="some-fork/codeArbiter", is_ancestor=is_ancestor)
        self.assertFalse(result.proven)
        self.assertIn("integration repository", result.reason)

    def test_ancestry_repo_check_runs_before_ancestry_and_reports_a_specific_reason(self):
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])
        result = _evaluate(target_repo="attacker/codeArbiter", is_ancestor=is_ancestor)
        self.assertFalse(result.proven)
        self.assertIsNone(result.method)
        self.assertIn("attacker/codeArbiter", result.reason)
        self.assertIn(INTEGRATION_REPO, result.reason)


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
        result = _evaluate(is_ancestor=is_ancestor, pr_record=self._pr(merge_commit_sha=merge_sha))
        self.assertTrue(result.proven)
        self.assertEqual(result.method, "pr_delivery")
        self.assertEqual(result.pr_number, 799)
        # AC-10: a squash delivery is never represented as preserving the
        # original branch commits' identity.
        self.assertFalse(result.preserves_original_identity)

    def test_valid_squash_landing_survives_additional_default_commits_afterward(self):
        # "Later default advancement ... is not a failure when the exact
        # landing is demonstrably retained in the authorized target." Proven
        # by using a target_sha that represents the default branch's tip
        # SEVERAL commits after the original squash landed -- distinct from
        # the basic happy-path test above, which uses the landing's own
        # immediate target. The landing commit must still be found retained
        # in whatever target_sha is currently fetched, however far ahead.
        merge_sha = "dddd4444dddd4444dddd4444dddd4444dddd4444"
        later_target_sha = "ffff6666ffff6666ffff6666ffff6666ffff6666"
        is_ancestor = _is_ancestor_factory([(merge_sha, later_target_sha)])
        result = _evaluate(
            target_sha=later_target_sha, is_ancestor=is_ancestor,
            pr_record=self._pr(merge_commit_sha=merge_sha),
        )
        self.assertTrue(result.proven)
        self.assertEqual(result.target_sha, later_target_sha)

    def test_wrong_base_repository_is_rejected(self):
        result = _evaluate(pr_record=self._pr(base_repo="some-fork/codeArbiter"))
        self.assertFalse(result.proven)
        self.assertIn("integration repository", result.reason)

    def test_fork_name_collision_is_rejected_by_repo_qualification(self):
        result = _evaluate(pr_record=self._pr(base_repo="attacker/codeArbiter"))
        self.assertFalse(result.proven)

    def test_changed_head_after_recorded_merge_is_rejected(self):
        # local tip moved after the PR merged -- head_sha no longer matches
        stale_head = "eeee5555eeee5555eeee5555eeee5555eeee5555"
        result = _evaluate(pr_record=self._pr(head_sha=stale_head))
        self.assertFalse(result.proven)
        self.assertIn("does not match candidate tip", result.reason)

    def test_closed_but_unmerged_pr_is_rejected(self):
        result = _evaluate(pr_record=self._pr(state="CLOSED"))
        self.assertFalse(result.proven)
        self.assertIn("not MERGED", result.reason)

    def test_missing_landing_object_not_retained_in_target_is_rejected(self):
        # merge_commit_sha exists on the PR record but is NOT an ancestor of
        # the fetched target -- the landing commit was never retained there.
        result = _evaluate(pr_record=self._pr())
        self.assertFalse(result.proven)
        self.assertIn("not retained", result.reason)

    def test_ambiguous_or_incomplete_pr_record_missing_fields_is_rejected(self):
        incomplete = {"number": 799, "state": "MERGED"}  # no head_sha, base_repo, merge_commit_sha
        result = _evaluate(pr_record=incomplete)
        self.assertFalse(result.proven)
        self.assertIn("missing required field", result.reason)

    def test_equal_tree_with_no_pr_record_and_no_ancestry_is_not_proof(self):
        # Tree-equality-only evidence must never grant eligibility by itself.
        result = _evaluate(pr_record=None, tree_equal_fn=lambda a, b: True)
        self.assertFalse(result.proven)
        self.assertIn("corroboration only", result.reason)
        self.assertIsNotNone(result.corroboration)

    def test_equal_tree_alongside_an_invalid_pr_record_is_still_not_proof(self):
        result = _evaluate(pr_record=self._pr(state="CLOSED"), tree_equal_fn=lambda a, b: True)
        self.assertFalse(result.proven)

    def test_base_ref_value_is_irrelevant_to_the_delivery_proof(self):
        # "A historical base-ref rename or an indirect integration is
        # acceptable when that same landing commit is retained." Proven by
        # showing the IDENTICAL scenario succeeds identically whether the PR
        # record carries the original base ref, a renamed one, or none at
        # all -- base_ref is not a field evaluate_merge_proof reads, so its
        # value (or absence) must never change the outcome. A test that only
        # supplies one arbitrary base_ref value would pass for ANY value,
        # including a typo; this proves irrelevance by construction.
        merge_sha = "dddd4444dddd4444dddd4444dddd4444dddd4444"
        is_ancestor = _is_ancestor_factory([(merge_sha, TARGET_SHA)])
        outcomes = set()
        for base_ref_value in ("main", "master-legacy", None):
            pr = self._pr(merge_commit_sha=merge_sha)
            if base_ref_value is not None:
                pr["base_ref"] = base_ref_value
            result = _evaluate(is_ancestor=is_ancestor, pr_record=pr)
            outcomes.add((result.proven, result.method, result.pr_merge_commit))
        self.assertEqual(len(outcomes), 1)
        ((proven, method, landing),) = outcomes
        self.assertTrue(proven)
        self.assertEqual(method, "pr_delivery")
        self.assertEqual(landing, merge_sha)

    def test_no_pr_record_and_no_gh_leaves_the_reason_specific_not_generic(self):
        result = _evaluate(pr_record=None)
        self.assertFalse(result.proven)
        self.assertIn("no PR delivery record", result.reason)


class TestStructuredUnprovenReason(unittest.TestCase):
    """Every decision has a structured proof or a specific unproven reason (T-04 Done-when)."""

    def test_unproven_result_always_carries_a_non_empty_reason(self):
        result = _evaluate()
        self.assertFalse(result.proven)
        self.assertTrue(result.reason)
        self.assertIsNone(result.method)

    def test_invalid_empty_candidate_sha_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            _evaluate(candidate_sha="")

    def test_invalid_empty_target_sha_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            _evaluate(target_sha="")

    def test_invalid_empty_target_repo_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            _evaluate(target_repo="")

    def test_invalid_none_target_repo_is_rejected_up_front(self):
        with self.assertRaises(ValueError):
            _evaluate(target_repo=None)


class TestProofResultCarriesTargetRepo(unittest.TestCase):
    """CodeRabbit review (2026-09-17): the authorized repository identity
    must survive on the ProofResult itself, so a downstream consumer
    (execute_branch_deletion) can bind a proof to the repository_id it is
    actually operating on, rather than trusting that the caller re-derived
    the same repository correctly a second time."""

    def test_a_proven_ancestry_result_carries_the_integration_repo(self):
        is_ancestor = _is_ancestor_factory([(CANDIDATE, TARGET_SHA)])
        result = _evaluate(is_ancestor=is_ancestor)
        self.assertEqual(result.target_repo, INTEGRATION_REPO)

    def test_an_unproven_result_still_carries_the_integration_repo(self):
        result = _evaluate()
        self.assertEqual(result.target_repo, INTEGRATION_REPO)

    def test_a_repo_mismatch_result_carries_the_authorized_integration_repo_not_the_bad_one(self):
        result = _evaluate(target_repo="someone-else/other-repo")
        self.assertFalse(result.proven)
        self.assertEqual(result.target_repo, INTEGRATION_REPO)


if __name__ == "__main__":
    unittest.main()
