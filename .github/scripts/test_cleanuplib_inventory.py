#!/usr/bin/env python3
"""Tests for core/pysrc/_cleanuplib.py's authoritative, bounded branch/
worktree inventory (T-03).

Covers AC-05 (an unknown/malformed item blocks only itself -- it still
appears in the inventory rather than being silently dropped), AC-07
(discovery is separated from proof -- upstream "gone" is a raw fact here,
never merged eligibility), AC-09 (a branch occupied by a surviving worktree
is identified by cross-referencing the real worktree list, never guessed
from a display marker), AC-11 (the whole worktree loss surface -- dirty,
untracked, ignored-only, locked, current, nested-repo -- is retained, and a
missing path is surfaced, never auto-abandoned), and AC-13 (a filesystem
target is validated against the real, resolved repository root before any
removal is even proposed).

Named first-failing-proof fixtures from the plan, each with its own test:
a plus-prefixed / worktree-occupied branch, a detached/locked worktree, a
missing worktree path, an unreadable git-status read, a non-ASCII/NUL-
delimited worktree path, and a worktree with ignored-only content. None of
these may be classified as safely empty/clean from a missing field or a
failed command; a gone-but-unmerged branch must remain unproven.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


REPO_ROOT = "/repo"


class TestBranchRefInventory(unittest.TestCase):
    def test_a_clean_tracking_branch_is_parsed_with_full_oid(self):
        text = "main\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\torigin/main\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.name, "main")
        self.assertEqual(r.oid, "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111")
        self.assertEqual(r.upstream, "origin/main")
        self.assertFalse(r.upstream_gone)
        self.assertFalse(r.read_error)
        self.assertIsNone(r.occupied_by)

    def test_a_branch_with_no_upstream_configured_is_a_real_none_not_an_error(self):
        text = "scratch\tbbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\t\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertIsNone(r.upstream)
        self.assertFalse(r.upstream_gone)
        self.assertFalse(r.read_error)

    def test_gone_upstream_is_a_raw_fact_never_merged_eligibility(self):
        # AC-07: this module makes no eligibility claim whatsoever. A
        # gone-but-unmerged branch is reported exactly as gone -- nothing
        # here says "safe to delete".
        text = "feature/x\tcccc3333cccc3333cccc3333cccc3333cccc3333\torigin/feature/x\t[gone]\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertTrue(r.upstream_gone)
        # The record exposes no "eligible"/"merged"/"safe" field at all --
        # proven by construction: BranchRefRecord's own field list.
        self.assertNotIn("eligible", cleanuplib.BranchRefRecord._fields)
        self.assertNotIn("merged", cleanuplib.BranchRefRecord._fields)

    def test_a_malformed_line_is_not_silently_dropped_from_the_inventory(self):
        # AC-05: an unknown/malformed item blocks only itself -- it must
        # still show up, flagged, rather than vanishing from the count.
        text = "just-a-name-no-oid-no-tabs\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)

    def test_a_short_abbreviated_oid_is_flagged_not_silently_accepted(self):
        # T-03 requires FULL ref IDs -- an abbreviated OID is exactly the
        # kind of "looks fine, isn't actually authoritative" input this
        # inventory must refuse to launder into a trusted full SHA.
        text = "feature/y\tabc1234\torigin/feature/y\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)

    def test_blank_lines_are_skipped(self):
        text = "\n\nmain\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\t\t\n\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        self.assertEqual(len(records), 1)

    def test_empty_input_yields_an_empty_inventory(self):
        self.assertEqual(cleanuplib.parse_branch_ref_inventory(""), [])
        self.assertEqual(cleanuplib.parse_branch_ref_inventory(None), [])


class TestWorktreeInventory(unittest.TestCase):
    def test_the_main_worktree_is_identified_by_matching_repo_root(self):
        text = "worktree /repo\nHEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\nbranch refs/heads/main\n"
        records = cleanuplib.parse_worktree_inventory(text, REPO_ROOT, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertTrue(r.is_main)
        self.assertEqual(r.branch, "main")
        self.assertEqual(r.oid, "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111")

    def test_a_detached_locked_worktree_surfaces_both_facts_together(self):
        # Named first-failing-proof fixture: detached AND locked at once.
        text = (
            "worktree /repo-wt/spike\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\n"
            "detached\n"
            "locked mid-experiment, do not touch\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, REPO_ROOT, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.detached)
        self.assertIsNone(r.branch)
        self.assertTrue(r.locked)
        self.assertEqual(r.locked_reason, "mid-experiment, do not touch")
        self.assertFalse(r.is_main)

    def test_a_missing_path_is_surfaced_never_auto_abandoned(self):
        # Named first-failing-proof fixture: the record still reports
        # path_exists=False as a fact; it is the CALLER's job to decide
        # what that means, never this parser's.
        text = "worktree /repo-wt/gone\nHEAD cccc3333cccc3333cccc3333cccc3333cccc3333\nbranch refs/heads/feature/gone\n"
        records = cleanuplib.parse_worktree_inventory(text, REPO_ROOT, path_exists_fn=lambda p: False)
        r = records[0]
        self.assertFalse(r.path_exists)
        # Still a full, unflagged record otherwise -- a missing path is not
        # itself a read error.
        self.assertFalse(r.read_error)

    def test_a_worktree_missing_its_head_line_is_flagged_read_error_not_none(self):
        # An unreadable HEAD must never be silently treated the same as "no
        # branch" (a real, confirmed state) -- it gets its own explicit
        # UNREADABLE marker and read_error=True.
        text = "worktree /repo-wt/broken\nbranch refs/heads/feature/broken\n"
        records = cleanuplib.parse_worktree_inventory(text, REPO_ROOT, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)

    def test_multiple_worktree_records_are_all_parsed(self):
        text = (
            "worktree /repo\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo-wt/feature\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\n"
            "branch refs/heads/feature/x\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, REPO_ROOT, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.path for r in records], ["/repo", "/repo-wt/feature"])

    def test_empty_input_yields_an_empty_inventory(self):
        self.assertEqual(cleanuplib.parse_worktree_inventory("", REPO_ROOT), [])
        self.assertEqual(cleanuplib.parse_worktree_inventory(None, REPO_ROOT), [])


class TestWorktreeInventoryNulDelimited(unittest.TestCase):
    def test_a_non_ascii_nul_delimited_path_round_trips_intact(self):
        # Named first-failing-proof fixture: -z output NUL-terminates each
        # line (and uses an empty field to end a record) instead of using
        # blank lines -- required for a path that itself could contain a
        # newline. Also proves non-ASCII path bytes are preserved as-is.
        path = "/repo-wt/féature-日本"
        text = (
            "worktree " + path + "\0"
            "HEAD dddd4444dddd4444dddd4444dddd4444dddd4444\0"
            "branch refs/heads/feature/x\0"
            "\0"
        )
        records = cleanuplib.parse_worktree_inventory_nul(text, REPO_ROOT, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.path, path)
        self.assertEqual(r.branch, "feature/x")
        self.assertFalse(r.read_error)

    def test_multiple_nul_terminated_records_are_all_parsed(self):
        text = (
            "worktree /repo\0"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\0"
            "branch refs/heads/main\0"
            "\0"
            "worktree /repo-wt/x\0"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\0"
            "detached\0"
            "\0"
        )
        records = cleanuplib.parse_worktree_inventory_nul(text, REPO_ROOT, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[1].detached)

    def test_empty_input_yields_an_empty_inventory(self):
        self.assertEqual(cleanuplib.parse_worktree_inventory_nul("", REPO_ROOT), [])
        self.assertEqual(cleanuplib.parse_worktree_inventory_nul(None, REPO_ROOT), [])


class TestBindBranchOccupancy(unittest.TestCase):
    def test_a_branch_checked_out_in_another_worktree_is_bound_to_its_path(self):
        # Named first-failing-proof fixture ("plus-prefixed occupied
        # branch"): this module derives occupancy from the REAL worktree
        # list -- a strictly more robust source than a display-only "+"
        # marker, which names occupancy without ever naming the occupying
        # path. A caller relying on this inventory gets the actual path.
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/x\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\torigin/feature/x\t[gone]\n"
        )
        worktrees = cleanuplib.parse_worktree_inventory(
            "worktree /repo-wt/x\nHEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\nbranch refs/heads/feature/x\n",
            REPO_ROOT, path_exists_fn=lambda p: True,
        )
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertEqual(bound[0].occupied_by, "/repo-wt/x")
        # Occupancy binding must never mutate upstream_gone -- still just a
        # raw fact, still not eligibility (AC-07).
        self.assertTrue(bound[0].upstream_gone)

    def test_an_unoccupied_branch_stays_none(self):
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/y\tbbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\t\t\n"
        )
        worktrees = []
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertIsNone(bound[0].occupied_by)

    def test_a_detached_worktree_binds_nothing_since_it_names_no_branch(self):
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/z\tcccc3333cccc3333cccc3333cccc3333cccc3333\t\t\n"
        )
        worktrees = cleanuplib.parse_worktree_inventory(
            "worktree /repo-wt/detached\nHEAD cccc3333cccc3333cccc3333cccc3333cccc3333\ndetached\n",
            REPO_ROOT, path_exists_fn=lambda p: True,
        )
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertIsNone(bound[0].occupied_by)


class TestWorktreeLossSurface(unittest.TestCase):
    def test_a_fully_clean_worktree_is_not_retained(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertFalse(surface.retain)

    def test_an_unreadable_status_is_never_treated_as_clean(self):
        # Named first-failing-proof fixture: a failed `git status` read
        # (represented as None or the UNREADABLE sentinel) must never be
        # folded into "no output means clean".
        surface_none = cleanuplib.classify_worktree_loss_surface(
            status_text=None, is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        surface_sentinel = cleanuplib.classify_worktree_loss_surface(
            status_text=cleanuplib.UNREADABLE, is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertTrue(surface_none.retain)
        self.assertTrue(surface_none.read_error)
        self.assertTrue(surface_sentinel.retain)
        self.assertTrue(surface_sentinel.read_error)

    def test_dirty_content_is_retained(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text=" M modified-file.py\n", is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertTrue(surface.dirty)
        self.assertTrue(surface.retain)

    def test_ignored_only_content_is_still_retained_not_silently_clean(self):
        # Named first-failing-proof fixture: a worktree containing ONLY
        # git-ignored files (e.g. build output) is not "nothing here" --
        # AC-11 explicitly names unknown-ignored content as retained.
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="!! build/output.o\n", is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertTrue(surface.ignored_only)
        self.assertFalse(surface.dirty)
        self.assertTrue(surface.retain)

    def test_untracked_only_content_is_retained(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="?? scratch-notes.txt\n", is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertTrue(surface.untracked)
        self.assertTrue(surface.retain)

    def test_a_locked_worktree_is_retained_even_if_clean(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=True, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertTrue(surface.retain)

    def test_the_currently_executing_worktree_is_retained_even_if_clean(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=True, has_nested_repo=False,
        )
        self.assertTrue(surface.retain)

    def test_a_nested_repository_boundary_is_retained_even_if_clean(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False, has_nested_repo=True,
        )
        self.assertTrue(surface.retain)


class TestValidateResourcePath(unittest.TestCase):
    def test_a_path_genuinely_nested_under_repo_root_is_accepted(self):
        ok, reason = cleanuplib.validate_resource_path(
            "/repo/worktrees/feature", REPO_ROOT, real_path_fn=lambda p: p,
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_a_sibling_directory_sharing_only_a_string_prefix_is_refused(self):
        # A naive `str.startswith(repo_root)` check would wrongly accept
        # this -- "/repo-wt" starts with "/repo" as TEXT but is a sibling
        # directory, not anything nested under it. The separator-boundary
        # check must catch this exact collision.
        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/feature", REPO_ROOT, real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    def test_a_path_resolving_to_the_repo_root_itself_is_refused(self):
        # AC-13: never operate on the root itself, even if some caller
        # asked -- a symlink/junction could resolve a decoy path back to
        # the thing that must never be touched.
        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/decoy", REPO_ROOT, real_path_fn=lambda p: REPO_ROOT,
        )
        self.assertFalse(ok)
        self.assertIn("root", reason)

    def test_a_path_that_escapes_above_repo_root_is_refused(self):
        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/escape", REPO_ROOT, real_path_fn=lambda p: "/etc",
        )
        self.assertFalse(ok)

    def test_an_empty_path_is_refused(self):
        ok, reason = cleanuplib.validate_resource_path("", REPO_ROOT, real_path_fn=lambda p: p)
        self.assertFalse(ok)

    def test_a_resolution_failure_is_refused_never_defaulted_to_safe(self):
        def raising_real_path(p):
            raise OSError("cannot resolve")

        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/broken-link", REPO_ROOT, real_path_fn=raising_real_path,
        )
        self.assertFalse(ok)
        self.assertIn("could not", reason)


if __name__ == "__main__":
    unittest.main()
