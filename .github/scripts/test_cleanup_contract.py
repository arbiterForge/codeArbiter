#!/usr/bin/env python3
"""Tests for core/pysrc/_cleanuplib.py's shared decision and interaction
fixtures (T-02).

Covers AC-01 (existing explicit intent needs zero additional confirmations),
AC-02 (a generic proposal offers one enumerated batch, at most once),
AC-03 (scope stays closed -- a branch-only scope never covers another
resource kind, so no forbidden scope expansion), AC-04 (an accepted work
lifecycle's own housekeeping needs no repeat authorization), AC-05
(independent safe work -- an unknown/error decision blocks only itself,
except a whole-operation error which blocks everything), AC-12 (a unique
loss always needs its own separate, explicitly named decision, never
silently folded into routine cleanup authorization), and AC-26 (bounded
interaction cost -- these are the pure classifiers other prompt-count
proofs are built from).

These are pure policy-decision tests over typed objects. A pass here proves
the DATA MODEL supports zero-ambiguity classification; it is not proof that
any live orchestration route obeys it -- that wiring is T-06's job, which
consumes these same fixtures.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


def _branch(name):
    return cleanuplib.Target(kind="branch", locator=name, expected_identity="deadbeef")


REPOSITORY_ID = "arbiterForge/codeArbiter"


class TestScopeCovers(unittest.TestCase):
    def test_an_unauthorized_proposal_covers_nothing(self):
        # scope=None is the pre-authorization state: nothing is covered yet.
        self.assertFalse(cleanuplib.scope_covers(None, _branch("feature"), REPOSITORY_ID))

    def test_a_branch_only_scope_covers_a_named_branch_member(self):
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertTrue(cleanuplib.scope_covers(scope, _branch("feature"), REPOSITORY_ID))

    def test_a_branch_only_scope_never_covers_a_task_archive_candidate(self):
        # AC-03 / the plan's own named first-failing-proof case: a
        # branch-only scope presented with task-archive candidates must not
        # authorize them, regardless of any name collision.
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        task_archive_target = cleanuplib.Target(
            kind="task_archive", locator="feature", expected_identity=None,
        )
        self.assertFalse(cleanuplib.scope_covers(scope, task_archive_target, REPOSITORY_ID))

    def test_a_scope_never_covers_a_member_outside_its_bound_snapshot(self):
        # A later-discovered target is not silently added to an existing
        # operation, even when its kind matches.
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertFalse(cleanuplib.scope_covers(scope, _branch("late-discovered"), REPOSITORY_ID))

    def test_a_scope_with_no_authorization_source_covers_nothing_even_with_bound_members(self):
        # source=None means the proposal is not yet authorized, so it must
        # cover nothing -- regardless of whether members happens to already
        # be populated (e.g. a displayed-but-not-yet-accepted snapshot).
        # Checking members alone would let a bound-but-unauthorized Scope
        # slip through.
        scope = cleanuplib.Scope(
            source=None, resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertFalse(cleanuplib.scope_covers(scope, _branch("feature"), REPOSITORY_ID))

    def test_a_not_yet_enumerated_proposal_scope_covers_nothing(self):
        # A Scope with source set but members still None represents "offered,
        # not yet bound to a concrete snapshot" -- nothing is authorized yet.
        scope = cleanuplib.Scope(
            source="snapshot_reply", resource_kinds=frozenset({"branch"}),
            members=None, repository_id="arbiterForge/codeArbiter",
        )
        self.assertFalse(cleanuplib.scope_covers(scope, _branch("feature"), REPOSITORY_ID))

    def test_an_unrecognized_authorization_source_covers_nothing(self):
        scope = cleanuplib.Scope(
            source="assumed_from_vibes", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id=REPOSITORY_ID,
        )
        self.assertFalse(cleanuplib.scope_covers(scope, _branch("feature"), REPOSITORY_ID))

    def test_a_scope_from_another_repository_covers_nothing(self):
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/another-repo",
        )
        self.assertFalse(cleanuplib.scope_covers(scope, _branch("feature"), REPOSITORY_ID))


class TestRequiredConfirmationCount(unittest.TestCase):
    def test_forty_eligible_refs_plus_direct_instruction_need_zero_questions(self):
        # AC-01 / the plan's own first-failing-proof case.
        members = frozenset("branch-%d" % i for i in range(40))
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=members, repository_id="arbiterForge/codeArbiter",
        )
        self.assertEqual(cleanuplib.required_confirmation_count(scope), 0)

    def test_a_generic_proposal_with_no_scope_yet_needs_exactly_one_offer(self):
        # AC-02: standup / "show me what needs cleaning" -- at most 1 per
        # proposed scope, never zero (the user must still say yes) and
        # never per-item.
        self.assertEqual(cleanuplib.required_confirmation_count(None), 1)

    def test_a_snapshot_reply_bound_scope_needs_zero_further_questions(self):
        # "Remove the 37 branches listed above; keep the other three" binds
        # the displayed operation; the reply itself is the authorization.
        scope = cleanuplib.Scope(
            source="snapshot_reply", resource_kinds=frozenset({"branch"}),
            members=frozenset({"a", "b", "c"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertEqual(cleanuplib.required_confirmation_count(scope), 0)

    def test_an_accepted_lifecycle_scope_needs_zero_questions_for_its_own_housekeeping(self):
        # AC-04: work's own accepted disposable housekeeping needs no
        # separate per-completion confirmation.
        scope = cleanuplib.Scope(
            source="accepted_lifecycle", resource_kinds=frozenset({"worktree", "file"}),
            members=frozenset({"work-42-worktree"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertEqual(cleanuplib.required_confirmation_count(scope), 0)

    def test_a_decline_leaves_the_scope_unauthorized_and_never_fans_out_per_branch(self):
        # "A decline must not emit one offer per branch" -- the plan's own
        # first-failing-proof case. A declined proposal simply never
        # becomes a Scope; there is no per-item prompt primitive to fall
        # into, and re-asking for the same declined proposal is not this
        # function's job to inflate.
        declined = None  # the user said no; no Scope was ever created
        self.assertEqual(cleanuplib.required_confirmation_count(declined), 1)
        # Critically: asking N times for N branches is not a valid reading.
        # There is exactly one call site, one answer, regardless of set size.

    def test_an_unresolved_unique_loss_always_adds_its_own_separate_decision(self):
        # AC-12: a unique loss is never satisfied by routine cleanup
        # authorization, on top of ANY authorization source, including one
        # that would otherwise need zero further questions.
        scope = cleanuplib.Scope(
            source="direct_instruction", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertEqual(
            cleanuplib.required_confirmation_count(scope, has_unresolved_unique_loss=True), 1,
        )

    def test_multiple_unique_losses_still_share_one_decision_not_one_each(self):
        # "Multiple named losses may share one explicit decision, but are
        # never hidden in routine cleanup" -- the flag is boolean, not a
        # count, so N unique losses still contribute exactly one question.
        scope = cleanuplib.Scope(
            source="accepted_lifecycle", resource_kinds=frozenset({"file"}),
            members=frozenset({"a", "b", "c"}), repository_id="arbiterForge/codeArbiter",
        )
        self.assertEqual(
            cleanuplib.required_confirmation_count(scope, has_unresolved_unique_loss=True), 1,
        )

    def test_an_unrecognized_authorization_source_raises_rather_than_being_treated_as_covered(self):
        bad_scope = cleanuplib.Scope(
            source="assumed_from_vibes", resource_kinds=frozenset({"branch"}),
            members=frozenset({"feature"}), repository_id="arbiterForge/codeArbiter",
        )
        with self.assertRaises(ValueError):
            cleanuplib.required_confirmation_count(bad_scope)


class TestMakeDecision(unittest.TestCase):
    def test_an_error_outcome_blocks_the_whole_operation(self):
        # AC-05: invalid repository identity or corrupt operation state
        # blocks the whole operation, not just its own target.
        decision = cleanuplib.make_decision(_branch("feature"), "error", "corrupt operation journal")
        self.assertTrue(decision.blocks_operation)

    def test_an_unknown_outcome_blocks_only_its_own_target(self):
        # AC-05: an unknown, changed or retained item blocks only itself
        # and its dependants -- other eligible authorized items still
        # complete independently.
        decision = cleanuplib.make_decision(_branch("feature"), "unknown", "ambiguous PR record")
        self.assertFalse(decision.blocks_operation)

    def test_an_eligible_outcome_never_blocks_anything(self):
        decision = cleanuplib.make_decision(_branch("feature"), "eligible", "ancestry proven")
        self.assertFalse(decision.blocks_operation)

    def test_an_excluded_outcome_never_blocks_anything(self):
        decision = cleanuplib.make_decision(_branch("main"), "excluded", "is the default branch")
        self.assertFalse(decision.blocks_operation)

    def test_a_unique_loss_outcome_never_blocks_anything_by_itself(self):
        # Blocking is not how a unique loss is handled -- it is surfaced as
        # its own separate decision (see required_confirmation_count above),
        # not treated as an operation-halting error.
        decision = cleanuplib.make_decision(_branch("feature"), "unique_loss", "only copy of unmerged work")
        self.assertFalse(decision.blocks_operation)

    def test_an_unrecognized_outcome_raises(self):
        with self.assertRaises(ValueError):
            cleanuplib.make_decision(_branch("feature"), "vibes_based", "no")


if __name__ == "__main__":
    unittest.main()
