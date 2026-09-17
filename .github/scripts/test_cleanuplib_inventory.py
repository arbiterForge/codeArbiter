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
target is validated against the caller's own exact, resolved allowlist
before any removal is even proposed).

This suite also regression-pins the findings from this module's 2026-09-17
independent review (NO-GO, 3 blocking / 5 high): B-2 (is_main must come from
Git's own first-record ordering, never a repo-root string comparison), B-3
(an unreadable worktree list must never default branch occupancy to
"confirmed unoccupied"), H-1 (a for-each-ref line without exactly 4 fields
is fully unreadable, not partially trusted), H-2/H-3/H-4 (validate_
resource_path is an exact-allowlist guard that returns the resolved path,
not a "nested under root" rule that refuses every real sibling worktree),
and H-5/M-3 (an unknown/unreadable input to classify_worktree_loss_surface
must force retain=True and stay a real bool, never a sentinel).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core", "pysrc"))

import _cleanuplib as cleanuplib  # noqa: E402


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

    def test_a_sha256_repository_oid_is_accepted_not_flagged_unreadable(self):
        # M-7: %(objectname) is 64 hex characters in a --object-format=sha256
        # repository -- refusing every branch there would be silently
        # unusable, not merely conservative.
        oid = "a" * 64
        text = "main\t" + oid + "\torigin/main\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertEqual(r.oid, oid)
        self.assertFalse(r.read_error)

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

    def test_upstream_gone_reads_only_the_track_field_never_the_whole_line(self):
        # A branch whose NAME contains "gone" must not be misread as having
        # a gone upstream -- only %(upstream:track) itself decides this.
        text = "release/gone-fix\tdddd4444dddd4444dddd4444dddd4444dddd4444\torigin/release/gone-fix\t[ahead 1]\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertFalse(r.upstream_gone)

    def test_a_line_missing_the_track_field_is_fully_unreadable(self):
        # H-1: the --format string always emits exactly 4 tab-separated
        # fields. A truncated read (here: 3 fields) must never partially
        # succeed with a fabricated "no upstream"/"not gone" -- the whole
        # record is unreadable.
        text = "feature/y\teeee5555eeee5555eeee5555eeee5555eeee5555\torigin/feature/y\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)
        self.assertIs(r.upstream, cleanuplib.UNREADABLE)
        self.assertIs(r.upstream_gone, cleanuplib.UNREADABLE)

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

    def test_a_unicode_line_separator_in_a_branch_name_does_not_fabricate_a_phantom_record(self):
        # Independent review follow-up, 2026-09-17: this parser split on
        # `str.splitlines()`, the exact same hazard HIGH-2 fixed in
        # parse_worktree_inventory's sibling function -- `git
        # check-ref-format` accepts a branch name containing U+2028, but
        # `str.splitlines()` treats it as a record separator while this
        # tab-delimited format does not. A `splitlines()` split truncates
        # the genuine branch's line mid-name and parses the remainder as a
        # second, fully "clean" record carrying the REAL branch's own OID
        # and a fabricated confirmed-absent upstream -- reopening H-1's
        # exact hazard (a confirmed-absent upstream fabricated from a
        # truncated read) through a different door.
        text = "refs/heads/a b\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\t\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.name, "a b")
        self.assertEqual(r.oid, "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111")

    def test_a_crlf_line_ending_does_not_corrupt_a_branch_row(self):
        # Every field this parser reads is stripped individually, so a
        # stray trailing "\r" from a CRLF-terminated line must never leak
        # into name/oid/upstream/upstream_gone.
        text = "main\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\torigin/main\t\r\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertEqual(r.name, "main")
        self.assertEqual(r.oid, "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111")
        self.assertEqual(r.upstream, "origin/main")
        self.assertFalse(r.read_error)

    def test_an_upstream_tracking_a_local_branch_is_also_stripped_to_its_short_name(self):
        # Independent review follow-up, 2026-09-17: %(upstream) is USUALLY
        # `refs/remotes/...` but is legally `refs/heads/...` when a branch
        # tracks another local branch (`git branch --set-upstream-to`) --
        # stripping only the remotes prefix left that shape unstripped,
        # silently breaking the "upstream is the short name" contract.
        text = "feature/y\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\trefs/heads/main\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        self.assertEqual(records[0].upstream, "main")

    def test_a_full_refname_is_stripped_by_fixed_prefix_not_gits_short_form(self):
        # Second independent review, HIGH-1: %(refname:short) shortens
        # differently depending on what else exists in the repo -- a branch
        # named "collide" that collides with a same-named tag comes back as
        # "heads/collide", not "collide". This module now reads the FULL
        # %(refname)/%(upstream) and strips the fixed "refs/heads/"/
        # "refs/remotes/" prefix itself, so the derived name/upstream never
        # depend on what else happens to exist in the repo.
        text = "refs/heads/collide\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\trefs/remotes/origin/collide\t\n"
        records = cleanuplib.parse_branch_ref_inventory(text)
        r = records[0]
        self.assertEqual(r.name, "collide")
        self.assertEqual(r.upstream, "origin/collide")
        self.assertFalse(r.read_error)


class TestWorktreeInventory(unittest.TestCase):
    def test_the_first_record_is_always_is_main_regardless_of_its_path(self):
        # B-2: Git's own documented guarantee is the ONLY signal used --
        # never a string comparison against a caller-supplied root, which a
        # linked worktree's own show-toplevel (or a Windows-vs-forward-slash
        # mismatch) would fail even for the genuine main worktree.
        text = (
            "worktree C:\\Users\\dev\\projects\\codeArbiter\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree C:\\Users\\dev\\projects\\codeArbiter-worktrees\\next-task\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\n"
            "branch refs/heads/feature/x\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].is_main)
        self.assertFalse(records[1].is_main)

    def test_a_detached_locked_worktree_surfaces_both_facts_together(self):
        # Named first-failing-proof fixture: detached AND locked at once.
        text = (
            "worktree /repo\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo-wt/spike\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\n"
            "detached\n"
            "locked mid-experiment, do not touch\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[1]
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
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: False)
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
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)

    def test_a_bare_repository_record_has_no_head_line_and_is_not_a_read_error(self):
        # M-4: `git worktree list --porcelain` emits `worktree <path>` then
        # `bare` with NO HEAD line at all for a bare repository entry --
        # that absence is expected, not a parse failure.
        text = "worktree /repo.git\nbare\n"
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.bare)
        self.assertFalse(r.read_error)
        self.assertIs(r.oid, cleanuplib.UNREADABLE)

    def test_a_non_bare_record_with_neither_branch_nor_detached_is_a_read_error(self):
        # CodeRabbit, 2026-09-17: a genuine, complete Git record for a
        # non-bare worktree always states EITHER `branch <ref>` OR
        # `detached` -- Git never omits both. A record with a valid HEAD
        # but neither signals a truncated read or format drift, not a
        # worktree that legitimately has no checkout state; treating it as
        # fully readable would let bind_branch_occupancy silently confirm
        # every OTHER branch as unoccupied from a list that might have
        # concealed one of them right here.
        text = "worktree /repo-wt/odd\nHEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.read_error)
        self.assertIsNone(r.branch)
        self.assertFalse(r.detached)

    def test_a_prunable_record_surfaces_its_reason(self):
        # M-5: Git's own "this worktree is prunable, and here is why" must
        # reach an inventory whose entire premise is authoritativeness.
        text = (
            "worktree /repo-wt/phantom\n"
            "HEAD dddd4444dddd4444dddd4444dddd4444dddd4444\n"
            "branch refs/heads/feature/phantom\n"
            "prunable gitdir file points to non-existent location\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.prunable)
        self.assertEqual(r.prunable_reason, "gitdir file points to non-existent location")

    def test_a_bare_prunable_line_with_no_reason_is_still_flagged(self):
        text = "worktree /repo-wt/phantom\nHEAD eeee5555eeee5555eeee5555eeee5555eeee5555\nprunable\n"
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.prunable)
        self.assertIsNone(r.prunable_reason)

    def test_a_c_quoted_lock_reason_is_unquoted_on_the_newline_delimited_path(self):
        # M-6: Git C-quotes a lock reason containing a raw newline onto one
        # porcelain line in the non-`-z` format; a caller must see the real
        # text, not the literal quote marks and backslash escapes.
        text = (
            'worktree /repo-wt/x\n'
            'HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n'
            'locked "line one\\nworktree /evil/phantom\\nline three"\n'
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertEqual(r.locked_reason, "line one\nworktree /evil/phantom\nline three")
        # The embedded "worktree " text must never be parsed as a second
        # record -- it is quoted onto ONE porcelain line.
        self.assertEqual(len(records), 1)

    def test_a_non_ascii_c_quoted_lock_reason_decodes_as_utf8_not_per_byte(self):
        # CodeRabbit, 2026-09-17: Git represents a multi-byte UTF-8
        # character as one octal escape per RAW BYTE -- "\302\265" is the
        # two bytes 0xC2 0xB5, together spelling "µ" (micro sign).
        # Converting each octal triplet to its own chr() independently
        # decodes each byte as a separate Latin-1-shaped code point instead,
        # corrupting "µ" into the two mojibake characters "Âµ".
        text = (
            'worktree /repo-wt/x\n'
            'HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n'
            'locked "reason: \\302\\265s timing budget"\n'
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        self.assertEqual(records[0].locked_reason, "reason: µs timing budget")

    def test_multiple_worktree_records_are_all_parsed(self):
        text = (
            "worktree /repo\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo-worktrees/feature\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\n"
            "branch refs/heads/feature/x\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.path for r in records], ["/repo", "/repo-worktrees/feature"])
        self.assertTrue(records[0].is_main)
        self.assertFalse(records[1].is_main)

    def test_empty_input_yields_an_empty_inventory(self):
        self.assertEqual(cleanuplib.parse_worktree_inventory(""), [])
        self.assertEqual(cleanuplib.parse_worktree_inventory(None), [])

    def test_a_unicode_line_separator_in_a_path_does_not_fabricate_a_phantom_record(self):
        # Second independent review, HIGH-2: `str.splitlines()` treats
        # U+2028 (and 8 other characters) as a line boundary, but Git's
        # non-`-z` porcelain format never does -- it only ever splits on
        # "\n". A worktree path that happens to contain a raw U+2028
        # (unusual, but not filesystem-illegal) followed by text shaped
        # like "worktree <path>" would, under `splitlines()`, be cut into
        # TWO raw lines: the genuine record's HEAD/branch lines then attach
        # to the SECOND half, fabricating a phantom worktree record at an
        # attacker/accident-controlled path with read_error=False. This
        # single logical porcelain line must survive as ONE record.
        path = "/repo-wt/x worktree /evil/phantom"
        text = (
            "worktree " + path + "\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\n"
            "branch refs/heads/main\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.path, path)
        self.assertEqual(r.branch, "main")
        self.assertFalse(r.read_error)

    def test_a_crlf_locked_line_is_still_recognized_as_locked(self):
        # Independent review follow-up, 2026-09-17: switching from
        # `str.splitlines()` to a literal "\n"-only split (HIGH-2's fix)
        # leaves a trailing "\r" on every line under CRLF input. The
        # bare-keyword lines `_apply_worktree_line` matches by EXACT
        # equality ("locked", "detached", "bare") would then silently fail
        # to match at all. For "detached"/"bare" that surfaces safely as
        # read_error=True (no branch/detached and no HEAD, respectively),
        # but for bare "locked" (no reason) it is fail-UNSAFE: a genuinely
        # locked worktree would come back locked=False, read_error=False --
        # exactly the "confirmed not locked" a disposal decision would
        # misuse. ("locked <reason>" survives even the buggy rstrip("\n")
        # via startswith()+strip() on the reason text, so it does not by
        # itself prove this fix -- the bare keyword is the real witness.)
        text = (
            "worktree /repo-wt/x\r\n"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\r\n"
            "branch refs/heads/feature/x\r\n"
            "locked\r\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.locked)
        self.assertFalse(r.read_error)

    def test_a_crlf_detached_and_bare_line_are_still_recognized(self):
        text = (
            "worktree /repo-wt/y\r\n"
            "HEAD bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\r\n"
            "detached\r\n"
        )
        records = cleanuplib.parse_worktree_inventory(text, path_exists_fn=lambda p: True)
        r = records[0]
        self.assertTrue(r.detached)
        self.assertFalse(r.read_error)

        bare_text = "worktree /repo.git\r\nbare\r\n"
        bare_records = cleanuplib.parse_worktree_inventory(bare_text, path_exists_fn=lambda p: True)
        br = bare_records[0]
        self.assertTrue(br.bare)
        self.assertFalse(br.read_error)


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
        records = cleanuplib.parse_worktree_inventory_nul(text, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.path, path)
        self.assertEqual(r.branch, "feature/x")
        self.assertFalse(r.read_error)
        self.assertTrue(r.is_main)

    def test_a_lock_reason_is_never_unquoted_on_the_nul_delimited_path(self):
        # M-6 counter-case: the -z format already carries the raw bytes for
        # a lock reason -- literal backslash-n text here is two real
        # characters, not an escape, and must survive verbatim.
        text = (
            "worktree /repo-wt/x\0"
            "HEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\0"
            "locked line one\\nliteral\0"
            "\0"
        )
        records = cleanuplib.parse_worktree_inventory_nul(text, path_exists_fn=lambda p: True)
        self.assertEqual(records[0].locked_reason, "line one\\nliteral")

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
        records = cleanuplib.parse_worktree_inventory_nul(text, path_exists_fn=lambda p: True)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[1].detached)
        self.assertFalse(records[1].is_main)

    def test_empty_input_yields_an_empty_inventory(self):
        self.assertEqual(cleanuplib.parse_worktree_inventory_nul(""), [])
        self.assertEqual(cleanuplib.parse_worktree_inventory_nul(None), [])


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
            path_exists_fn=lambda p: True,
        )
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertEqual(bound[0].occupied_by, "/repo-wt/x")
        # Occupancy binding must never mutate upstream_gone -- still just a
        # raw fact, still not eligibility (AC-07).
        self.assertTrue(bound[0].upstream_gone)

    def test_an_unoccupied_branch_in_a_confirmed_empty_list_stays_none(self):
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/y\tbbbb2222bbbb2222bbbb2222bbbb2222bbbb2222\t\t\n"
        )
        bound = cleanuplib.bind_branch_occupancy(branches, [])
        self.assertIsNone(bound[0].occupied_by)

    def test_an_unavailable_worktree_list_marks_occupancy_unreadable_not_unoccupied(self):
        # B-3: this is the blocking finding. `None` (never asked) and
        # UNREADABLE (asked, failed) must both mean "we do not know" --
        # never "confirmed not checked out anywhere", which is exactly the
        # answer a deletion guard would misuse to permit an unsafe delete.
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/z\tcccc3333cccc3333cccc3333cccc3333cccc3333\t\t\n"
        )
        bound_none = cleanuplib.bind_branch_occupancy(branches, None)
        bound_unreadable = cleanuplib.bind_branch_occupancy(branches, cleanuplib.UNREADABLE)
        self.assertIs(bound_none[0].occupied_by, cleanuplib.UNREADABLE)
        self.assertIs(bound_unreadable[0].occupied_by, cleanuplib.UNREADABLE)

    def test_a_detached_worktree_binds_nothing_since_it_names_no_branch(self):
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/z\tcccc3333cccc3333cccc3333cccc3333cccc3333\t\t\n"
        )
        worktrees = cleanuplib.parse_worktree_inventory(
            "worktree /repo-wt/detached\nHEAD cccc3333cccc3333cccc3333cccc3333cccc3333\ndetached\n",
            path_exists_fn=lambda p: True,
        )
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertIsNone(bound[0].occupied_by)

    def test_a_worktree_record_naming_a_branch_but_also_detached_does_not_bind(self):
        # M-8: the docstring's rule is "non-detached" -- a record that
        # (however unusually) carries both `detached` and a `branch` field
        # must not bind, matching the documented contract exactly.
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/odd\tdddd4444dddd4444dddd4444dddd4444dddd4444\t\t\n"
        )
        worktrees = [
            cleanuplib.WorktreeInventoryRecord(
                path="/repo-wt/odd", oid="dddd4444dddd4444dddd4444dddd4444dddd4444",
                branch="feature/odd", is_main=False, detached=True, locked=False,
                locked_reason=None, bare=False, prunable=False, prunable_reason=None,
                path_exists=True, read_error=False,
            )
        ]
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertIsNone(bound[0].occupied_by)

    def test_a_worktree_record_with_a_read_error_does_not_confirm_occupancy(self):
        # M-8: an untrustworthy worktree record (its OWN HEAD line could not
        # be parsed) must not be used as the basis for "this branch is
        # occupied" -- that would launder a read failure into a confirmed
        # fact via a different function than the one that flagged it.
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/broken\teeee5555eeee5555eeee5555eeee5555eeee5555\t\t\n"
        )
        worktrees = [
            cleanuplib.WorktreeInventoryRecord(
                path="/repo-wt/broken", oid=cleanuplib.UNREADABLE,
                branch="feature/broken", is_main=False, detached=False, locked=False,
                locked_reason=None, bare=False, prunable=False, prunable_reason=None,
                path_exists=True, read_error=True,
            )
        ]
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        # CodeRabbit, 2026-09-17: a read-error record's own branch identity
        # is exactly the unknown quantity -- the corrupted record COULD
        # have been naming this very branch, so the correct answer is
        # "unknown", not "confirmed unoccupied".
        self.assertIs(bound[0].occupied_by, cleanuplib.UNREADABLE)

    def test_a_read_error_elsewhere_in_the_list_does_not_undo_a_confirmed_match(self):
        # A branch a CLEAN record actually names stays confirmed occupied
        # even when some OTHER record in the same list is unreadable --
        # good data is not punished for a neighbor's corruption.
        branches = cleanuplib.parse_branch_ref_inventory(
            "feature/good\tffff6666ffff6666ffff6666ffff6666ffff6666\t\t\n"
            "feature/mystery\t1111777711117777111177771111777711117777\t\t\n"
        )
        worktrees = [
            cleanuplib.WorktreeInventoryRecord(
                path="/repo-wt/good", oid="ffff6666ffff6666ffff6666ffff6666ffff6666",
                branch="feature/good", is_main=False, detached=False, locked=False,
                locked_reason=None, bare=False, prunable=False, prunable_reason=None,
                path_exists=True, read_error=False,
            ),
            cleanuplib.WorktreeInventoryRecord(
                path="/repo-wt/broken", oid=cleanuplib.UNREADABLE,
                branch=None, is_main=False, detached=False, locked=False,
                locked_reason=None, bare=False, prunable=False, prunable_reason=None,
                path_exists=True, read_error=True,
            ),
        ]
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        by_name = {b.name: b.occupied_by for b in bound}
        self.assertEqual(by_name["feature/good"], "/repo-wt/good")
        self.assertIs(by_name["feature/mystery"], cleanuplib.UNREADABLE)

    def test_a_branch_shadowed_by_a_same_named_tag_still_binds_to_its_worktree(self):
        # Second independent review, HIGH-1 end-to-end: with the old
        # %(refname:short) join key, a branch named "collide" that shares
        # its name with a tag would come back from for-each-ref as
        # "heads/collide", which would never match the porcelain list's
        # "collide" -- silently reporting a live, checked-out branch as
        # "confirmed unoccupied". Feeding the FULL refname (as for-each-ref
        # always emits, tag collision or not) proves the fixed-prefix strip
        # matches regardless of what else exists in the repo.
        branches = cleanuplib.parse_branch_ref_inventory(
            "refs/heads/collide\taaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\t\t\n"
        )
        worktrees = cleanuplib.parse_worktree_inventory(
            "worktree /repo-wt/collide\nHEAD aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111\nbranch refs/heads/collide\n",
            path_exists_fn=lambda p: True,
        )
        bound = cleanuplib.bind_branch_occupancy(branches, worktrees)
        self.assertEqual(bound[0].occupied_by, "/repo-wt/collide")


class TestWorktreeLossSurface(unittest.TestCase):
    def test_a_fully_clean_worktree_is_not_retained(self):
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertFalse(surface.retain)
        self.assertIs(surface.retain, False)

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

    def test_a_read_error_on_the_owning_inventory_record_forces_retain(self):
        # H-5: this is the ONLY function that produces the retention
        # verdict, so a caller MUST be able to fold an inventory record's
        # own read_error into it -- otherwise that fact is structurally
        # unreachable from the disposal decision.
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False, has_nested_repo=False,
            record_read_error=True,
        )
        self.assertTrue(surface.retain)
        self.assertIs(surface.retain, True)

    def test_an_unreadable_lock_or_nested_repo_signal_forces_retain_as_a_real_bool(self):
        # M-3: UNREADABLE must never poison the `retain` field itself (a
        # bare `or` chain would return the sentinel object, not a bool).
        surface_locked = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=cleanuplib.UNREADABLE,
            is_current_worktree=False, has_nested_repo=False,
        )
        surface_nested = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False,
            has_nested_repo=cleanuplib.UNREADABLE,
        )
        self.assertIs(surface_locked.retain, True)
        self.assertIs(surface_nested.retain, True)

    def test_a_none_lock_current_or_nested_repo_signal_forces_retain_as_a_real_bool(self):
        # Second independent review, MEDIUM-1: a caller that has not yet
        # determined one of these three signals has no principled way to
        # spell "unknown" other than `None` or the `UNREADABLE` sentinel --
        # if only `UNREADABLE` were recognized, `None` sneaking through
        # (e.g. `is_locked=None`) with every other signal False would let
        # the `or` chain return the literal `None` instead of a real bool,
        # and would fold "not yet determined" into "confirmed absent".
        surface_locked = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=None, is_current_worktree=False, has_nested_repo=False,
        )
        surface_current = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=None, has_nested_repo=False,
        )
        surface_nested = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=False, is_current_worktree=False, has_nested_repo=None,
        )
        self.assertIs(surface_locked.retain, True)
        self.assertIs(surface_current.retain, True)
        self.assertIs(surface_nested.retain, True)

    def test_a_non_bool_truthy_signal_still_yields_a_real_bool_retain(self):
        # Independent review follow-up, 2026-09-17: the unknown-input check
        # only refuses `UNREADABLE` and `None` -- it does not refuse an
        # arbitrary other non-bool value a careless caller might pass for
        # is_locked/is_current_worktree/has_nested_repo (e.g. 1/0). `retain`
        # must still come back a REAL bool (M-3), never whatever type
        # happened to be the last truthy/falsy operand in the `or` chain.
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="", is_locked=1, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertIs(surface.retain, True)

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

    def test_ignored_content_alongside_dirty_content_is_not_ignored_only(self):
        # M-1: "ignored_only" must mean what it says -- ignored content
        # coexisting with staged/dirty content is not "only" ignored.
        surface = cleanuplib.classify_worktree_loss_surface(
            status_text="R  a.txt -> b.txt\n!! build/output.o\n",
            is_locked=False, is_current_worktree=False, has_nested_repo=False,
        )
        self.assertFalse(surface.ignored_only)
        self.assertTrue(surface.dirty)
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
    def test_an_exact_allowlist_match_is_accepted_and_returns_the_resolved_path(self):
        # H-3: the resolved path is returned so a caller acts on what this
        # guard actually validated, never the original unresolved string.
        # Second independent review, MEDIUM-2: an identity `real_path_fn`
        # can't distinguish "returns resolved" from "returns the original
        # path" -- a mutant that returned `path` instead of `resolved`
        # would still pass. A `real_path_fn` that maps the candidate to a
        # DIFFERENT string than what was passed in proves which one this
        # function actually returns.
        def real_path_fn(p):
            return {
                "/repo/worktrees/feature-link": "/repo/worktrees/feature",
                "/repo/worktrees/feature": "/repo/worktrees/feature",
            }[p]

        ok, resolved = cleanuplib.validate_resource_path(
            "/repo/worktrees/feature-link", ["/repo/worktrees/feature"], real_path_fn=real_path_fn,
        )
        self.assertTrue(ok)
        self.assertEqual(resolved, "/repo/worktrees/feature")

    def test_a_genuine_sibling_worktree_is_accepted(self):
        # H-2: Git worktrees are conventionally SIBLINGS of the repo root,
        # not descendants -- this is the real layout the guard must permit,
        # which the old "nested under repo_root" rule refused outright.
        ok, resolved = cleanuplib.validate_resource_path(
            "/repo-worktrees/next-task", ["/repo-worktrees/next-task", "/repo"],
            real_path_fn=lambda p: p,
        )
        self.assertTrue(ok)
        self.assertEqual(resolved, "/repo-worktrees/next-task")

    def test_a_path_not_on_the_allowlist_is_refused_even_if_nested_under_repo_root(self):
        # There is no longer an implicit "nested under a root is fine" rule
        # -- only an exact match against the caller's own authorized set.
        ok, reason = cleanuplib.validate_resource_path(
            "/repo/some/other/dir", ["/repo/worktrees/feature"], real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    def test_a_sibling_directory_sharing_only_a_string_prefix_is_refused(self):
        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/feature", ["/repo"], real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    def test_a_candidate_that_resolves_to_a_bare_root_is_refused_even_if_allowlisted(self):
        # H-4a: exact-match alone is not enough protection against a caller
        # bug that puts a bare volume/filesystem root itself on the
        # allowlist -- the target must never BE a root, no matter what
        # string comparison says.
        ok, reason = cleanuplib.validate_resource_path(
            "/", ["/"], real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    def test_a_candidate_that_resolves_to_a_bare_windows_drive_root_is_refused(self):
        ok, reason = cleanuplib.validate_resource_path(
            "C:\\", ["C:\\"], real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    def test_a_candidate_that_resolves_to_a_bare_unc_share_root_is_refused(self):
        # H-4b: a UNC share root ("\\\\server\\share") must never itself be
        # an accepted target, even if a caller's allowlist names it exactly.
        ok, reason = cleanuplib.validate_resource_path(
            "\\\\srv\\share", ["\\\\srv\\share"], real_path_fn=lambda p: p,
        )
        self.assertFalse(ok)

    @unittest.skipUnless(os.name == "nt", "case-insensitive comparison is a Windows-specific guarantee")
    def test_case_only_difference_still_matches_on_windows(self):
        # H-4c: a caller whose allowlist entry came from a differently-cased
        # source (e.g. an env var) must still match a genuine child on the
        # platform where the filesystem itself is case-insensitive.
        ok, resolved = cleanuplib.validate_resource_path(
            "C:\\Repo\\wt", ["c:\\repo\\wt"], real_path_fn=lambda p: p,
        )
        self.assertTrue(ok)

    def test_an_exact_case_match_always_works_on_every_platform(self):
        ok, resolved = cleanuplib.validate_resource_path(
            "/Repo/WT", ["/Repo/WT"], real_path_fn=lambda p: p,
        )
        self.assertTrue(ok)

    def test_an_unresolvable_allowlist_entry_is_skipped_not_fatal(self):
        def real_path_fn(p):
            if p == "/broken":
                raise OSError("cannot resolve")
            return p

        ok, resolved = cleanuplib.validate_resource_path(
            "/repo/worktrees/feature", ["/broken", "/repo/worktrees/feature"],
            real_path_fn=real_path_fn,
        )
        self.assertTrue(ok)
        self.assertEqual(resolved, "/repo/worktrees/feature")

    def test_a_path_that_escapes_to_an_unauthorized_location_is_refused(self):
        # A symlink/junction that resolves to somewhere never on the
        # allowlist -- e.g. "/etc" -- must be refused even though the
        # UNRESOLVED string never appears anywhere suspicious.
        def real_path_fn(p):
            return "/etc" if p == "/repo-wt/escape" else p

        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/escape", ["/repo/worktrees/feature"], real_path_fn=real_path_fn,
        )
        self.assertFalse(ok)

    def test_an_empty_path_is_refused(self):
        ok, reason = cleanuplib.validate_resource_path("", ["/repo"], real_path_fn=lambda p: p)
        self.assertFalse(ok)

    def test_an_empty_or_blank_path_never_reaches_real_path_fn(self):
        # Second independent review, MEDIUM-3: the empty-path guard must
        # fire BEFORE real_path_fn is ever called. This matters because the
        # production default, os.path.realpath(""), does NOT fail or
        # return empty -- it (unintuitively) resolves to the CURRENT
        # WORKING DIRECTORY -- so the guard's safety depends entirely on
        # never reaching that call for an empty/blank path, not on
        # real_path_fn happening to refuse it.
        #
        # A real_path_fn that RAISES on an unexpected input would be
        # swallowed by this function's own "resolution failure is refused"
        # handling (both paths return ok=False), so it cannot tell "the
        # guard fired first" apart from "real_path_fn was called and
        # failed". Instead, real_path_fn here RESOLVES the empty/blank
        # candidate to something that WOULD match the allowlist -- so the
        # only way this test can observe ok=False is if the early guard
        # refused the candidate before real_path_fn ever ran.
        mapping = {
            "": "/repo/worktrees/feature",
            "   ": "/repo/worktrees/feature",
            "/repo/worktrees/feature": "/repo/worktrees/feature",
        }
        real_path_fn = mapping.__getitem__

        ok, reason = cleanuplib.validate_resource_path(
            "", ["/repo/worktrees/feature"], real_path_fn=real_path_fn,
        )
        self.assertFalse(ok)
        ok_ws, reason_ws = cleanuplib.validate_resource_path(
            "   ", ["/repo/worktrees/feature"], real_path_fn=real_path_fn,
        )
        self.assertFalse(ok_ws)

    def test_an_empty_allowlist_refuses_everything(self):
        ok, reason = cleanuplib.validate_resource_path("/repo/x", [], real_path_fn=lambda p: p)
        self.assertFalse(ok)

    def test_a_resolution_failure_on_the_candidate_path_is_refused_never_defaulted_to_safe(self):
        def raising_real_path(p):
            raise OSError("cannot resolve")

        ok, reason = cleanuplib.validate_resource_path(
            "/repo-wt/broken-link", ["/repo-wt/broken-link"], real_path_fn=raising_real_path,
        )
        self.assertFalse(ok)
        self.assertIn("could not", reason)


if __name__ == "__main__":
    unittest.main()
