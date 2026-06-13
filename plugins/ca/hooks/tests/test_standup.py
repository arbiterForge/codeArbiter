"""Tests for _standuplib.py — pure parsers that turn git command OUTPUT STRINGS
into structured data. No I/O, no subprocess: every case is a fixture string in,
struct out (per the session-hygiene test idiom)."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _standuplib as sl

# Load the hyphenated session-start.py without executing main() — same idiom as
# test_session_start.py.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "session_start",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "session-start.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestParsePorcelain(unittest.TestCase):
    def test_empty_is_clean(self):
        self.assertEqual(
            sl.parse_porcelain(""),
            {"dirty": False, "staged": 0, "unstaged": 0, "untracked": 0},
        )

    def test_whitespace_only_is_clean(self):
        out = sl.parse_porcelain("\n  \n")
        self.assertFalse(out["dirty"])
        self.assertEqual((out["staged"], out["unstaged"], out["untracked"]), (0, 0, 0))

    def test_untracked_only(self):
        # `??` lines are untracked, not staged/unstaged.
        text = "?? newfile.py\n?? docs/notes.md\n"
        out = sl.parse_porcelain(text)
        self.assertTrue(out["dirty"])
        self.assertEqual(out["untracked"], 2)
        self.assertEqual(out["staged"], 0)
        self.assertEqual(out["unstaged"], 0)

    def test_staged_changes(self):
        # XY format: index column (X) non-space/non-? => staged.
        text = "M  staged_modified.py\nA  staged_added.py\n"
        out = sl.parse_porcelain(text)
        self.assertTrue(out["dirty"])
        self.assertEqual(out["staged"], 2)
        self.assertEqual(out["unstaged"], 0)
        self.assertEqual(out["untracked"], 0)

    def test_unstaged_changes(self):
        # Worktree column (Y) non-space => unstaged.
        text = " M worktree_modified.py\n D worktree_deleted.py\n"
        out = sl.parse_porcelain(text)
        self.assertTrue(out["dirty"])
        self.assertEqual(out["unstaged"], 2)
        self.assertEqual(out["staged"], 0)

    def test_mixed_staged_and_unstaged_same_file(self):
        # "MM" => both index and worktree modified: counts toward both.
        text = "MM both.py\n"
        out = sl.parse_porcelain(text)
        self.assertTrue(out["dirty"])
        self.assertEqual(out["staged"], 1)
        self.assertEqual(out["unstaged"], 1)
        self.assertEqual(out["untracked"], 0)

    def test_full_mix(self):
        text = (
            "M  staged.py\n"
            " M unstaged.py\n"
            "MM both.py\n"
            "?? untracked.py\n"
        )
        out = sl.parse_porcelain(text)
        self.assertTrue(out["dirty"])
        self.assertEqual(out["staged"], 2)    # staged.py, both.py
        self.assertEqual(out["unstaged"], 2)  # unstaged.py, both.py
        self.assertEqual(out["untracked"], 1)


class TestParseAheadBehind(unittest.TestCase):
    def test_happy_path(self):
        # rev-list --left-right --count gives "<behind>\t<ahead>".
        self.assertEqual(sl.parse_ahead_behind("2\t3"), (2, 3))

    def test_trailing_newline(self):
        self.assertEqual(sl.parse_ahead_behind("2\t3\n"), (2, 3))

    def test_both_zero(self):
        self.assertEqual(sl.parse_ahead_behind("0\t0"), (0, 0))

    def test_empty(self):
        self.assertEqual(sl.parse_ahead_behind(""), (0, 0))

    def test_whitespace_only(self):
        self.assertEqual(sl.parse_ahead_behind("   \n"), (0, 0))

    def test_malformed_single_field(self):
        self.assertEqual(sl.parse_ahead_behind("oops"), (0, 0))

    def test_malformed_non_numeric(self):
        self.assertEqual(sl.parse_ahead_behind("a\tb"), (0, 0))


class TestMergedBranchCandidates(unittest.TestCase):
    def test_gone_branch_is_candidate(self):
        text = (
            "* feature-x   abc1234 [origin/feature-x] WIP\n"
            "  old-feature def5678 [origin/old-feature: gone] old work\n"
            "  main        aaa0000 [origin/main] mainline\n"
        )
        out = sl.merged_branch_candidates(text, current="feature-x", default="main")
        self.assertEqual(out, ["old-feature"])

    def test_excludes_current_even_if_gone(self):
        text = "* gone-current 111aaaa [origin/gone-current: gone] on a stale branch\n"
        out = sl.merged_branch_candidates(text, current="gone-current", default="main")
        self.assertEqual(out, [])

    def test_excludes_default_even_if_gone(self):
        text = "  main 111aaaa [origin/main: gone] (unusual but exclude)\n"
        out = sl.merged_branch_candidates(text, current="feature-x", default="main")
        self.assertEqual(out, [])

    def test_non_gone_branches_not_candidates(self):
        text = (
            "* feature-x abc1234 [origin/feature-x] live\n"
            "  feature-y def5678 [origin/feature-y] also live\n"
        )
        out = sl.merged_branch_candidates(text, current="feature-x", default="main")
        self.assertEqual(out, [])

    def test_empty_input(self):
        self.assertEqual(
            sl.merged_branch_candidates("", current="feature-x", default="main"), []
        )

    def test_multiple_gone_candidates_order_preserved(self):
        text = (
            "* feature-x abc1234 [origin/feature-x] live\n"
            "  branch-a  111aaaa [origin/branch-a: gone] gone1\n"
            "  branch-b  222bbbb [origin/branch-b: gone] gone2\n"
        )
        out = sl.merged_branch_candidates(text, current="feature-x", default="main")
        self.assertEqual(out, ["branch-a", "branch-b"])


class TestFfPullEligible(unittest.TestCase):
    """SH-6: the ff-pull action is offered ONLY when the working tree is clean
    AND we are behind. A dirty tree withholds the offer (a fast-forward pull on a
    dirty tree is unsafe); behind==0 means nothing to pull. PURE: porcelain text
    + behind count in, bool out."""

    def test_clean_and_behind_is_eligible(self):
        self.assertTrue(sl.ff_pull_eligible("", behind=2))

    def test_clean_whitespace_only_and_behind_is_eligible(self):
        # Whitespace-only porcelain is clean per parse_porcelain.
        self.assertTrue(sl.ff_pull_eligible("\n  \n", behind=1))

    def test_dirty_and_behind_is_not_eligible(self):
        # A staged change makes the tree dirty -> withhold ff-pull even when behind.
        self.assertFalse(sl.ff_pull_eligible("M  a.py\n", behind=2))

    def test_unstaged_dirty_and_behind_is_not_eligible(self):
        self.assertFalse(sl.ff_pull_eligible(" M a.py\n", behind=2))

    def test_untracked_dirty_and_behind_is_not_eligible(self):
        # Untracked files count as dirty for the ff-pull safety check.
        self.assertFalse(sl.ff_pull_eligible("?? a.py\n", behind=2))

    def test_clean_but_not_behind_is_not_eligible(self):
        self.assertFalse(sl.ff_pull_eligible("", behind=0))

    def test_dirty_and_not_behind_is_not_eligible(self):
        self.assertFalse(sl.ff_pull_eligible("M  a.py\n", behind=0))


class TestMergedBranchCandidatesSH8(unittest.TestCase):
    """SH-8: the merged/gone-branch prune candidate set EXPLICITLY excludes the
    current branch (line begins `* `) and the default branch, and INCLUDES a
    `: gone]` branch. Consolidated exclusion-rule lock-in for SH-8."""

    def test_excludes_current_and_default_includes_gone(self):
        text = (
            "* feature   abc1234 [origin/feature: gone] current+gone (excluded)\n"
            "  main       aaa0000 [origin/main: gone] default+gone (excluded)\n"
            "  old-feature def5678 [origin/old-feature: gone] mergeable (included)\n"
        )
        out = sl.merged_branch_candidates(text, current="feature", default="main")
        # Current ("* feature") and default ("main") are excluded even though both
        # show `: gone]`; only the third, non-current/non-default gone branch wins.
        self.assertEqual(out, ["old-feature"])


class TestStaleWorktreeCandidates(unittest.TestCase):
    """SD-B1 / stale-worktree classifier: from parsed worktrees + the set of
    gone/merged branch names, return the NON-MAIN worktrees that are stale —
    branch gone/merged OR path missing on disk. The main worktree is NEVER a
    candidate. path_exists is injected so the disk check is deterministic."""

    def _wt(self, path, branch, is_main):
        return {"path": path, "branch": branch, "is_main": is_main}

    def test_branch_gone_is_candidate(self):
        worktrees = [self._wt("/wt/feat", "old-feature", False)]
        out = sl.stale_worktree_candidates(
            worktrees, {"old-feature"}, path_exists=lambda p: True
        )
        self.assertEqual(out, worktrees)

    def test_path_missing_is_candidate(self):
        # Branch is live, but the directory is gone on disk -> still stale.
        worktrees = [self._wt("/wt/feat", "live-branch", False)]
        out = sl.stale_worktree_candidates(
            worktrees, set(), path_exists=lambda p: False
        )
        self.assertEqual(out, worktrees)

    def test_main_worktree_never_a_candidate(self):
        # Even if main's branch were in the gone set AND its path were missing,
        # the main worktree is never returned.
        main_wt = self._wt("/repo", "main", True)
        out = sl.stale_worktree_candidates(
            [main_wt], {"main"}, path_exists=lambda p: False
        )
        self.assertEqual(out, [])

    def test_healthy_worktree_is_not_a_candidate(self):
        # Live branch (not in gone set) + path exists -> healthy, not stale.
        worktrees = [self._wt("/wt/feat", "live-branch", False)]
        out = sl.stale_worktree_candidates(
            worktrees, {"old-feature"}, path_exists=lambda p: True
        )
        self.assertEqual(out, [])

    def test_mixed_selects_only_stale_non_main_preserving_order(self):
        existing = {"/repo", "/wt/live"}
        worktrees = [
            self._wt("/repo", "main", True),            # main: never
            self._wt("/wt/gone", "old-feature", False), # gone branch -> stale
            self._wt("/wt/live", "live", False),        # healthy -> not stale
            self._wt("/wt/missing", "alive", False),    # path missing -> stale
        ]
        out = sl.stale_worktree_candidates(
            worktrees, {"old-feature"}, path_exists=lambda p: p in existing
        )
        self.assertEqual(
            [w["path"] for w in out], ["/wt/gone", "/wt/missing"]
        )

    def test_empty_input_is_empty(self):
        self.assertEqual(
            sl.stale_worktree_candidates([], {"x"}, path_exists=lambda p: True), []
        )

    def test_none_branch_worktree_with_existing_path_is_healthy(self):
        # A detached worktree (branch None) whose path exists is not stale: a None
        # branch is never in the gone set.
        worktrees = [self._wt("/wt/detached", None, False)]
        out = sl.stale_worktree_candidates(
            worktrees, {"old-feature"}, path_exists=lambda p: True
        )
        self.assertEqual(out, [])


class TestParseWorktrees(unittest.TestCase):
    def test_main_worktree_flagged(self):
        root = "/home/u/repo"
        text = (
            "worktree /home/u/repo\n"
            "HEAD abc1234\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /home/u/repo-feature\n"
            "HEAD def5678\n"
            "branch refs/heads/feature-x\n"
            "\n"
        )
        out = sl.parse_worktrees(text, repo_root=root)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {"path": "/home/u/repo", "branch": "main", "is_main": True})
        self.assertEqual(
            out[1],
            {"path": "/home/u/repo-feature", "branch": "feature-x", "is_main": False},
        )

    def test_detached_worktree_has_none_branch(self):
        root = "/home/u/repo"
        text = (
            "worktree /home/u/repo\n"
            "HEAD abc1234\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /home/u/repo-detached\n"
            "HEAD def5678\n"
            "detached\n"
            "\n"
        )
        out = sl.parse_worktrees(text, repo_root=root)
        self.assertEqual(out[1]["branch"], None)
        self.assertFalse(out[1]["is_main"])

    def test_empty_input(self):
        self.assertEqual(sl.parse_worktrees("", repo_root="/home/u/repo"), [])

    def test_repo_root_trailing_slash_tolerated(self):
        # A repo_root with a trailing separator must still match the main worktree.
        text = "worktree /home/u/repo\nHEAD abc\nbranch refs/heads/main\n\n"
        out = sl.parse_worktrees(text, repo_root="/home/u/repo/")
        self.assertTrue(out[0]["is_main"])

    def test_windows_style_paths(self):
        root = "C:/Users/u/repo"
        text = (
            "worktree C:/Users/u/repo\n"
            "HEAD abc1234\n"
            "branch refs/heads/main\n"
            "\n"
        )
        out = sl.parse_worktrees(text, repo_root=root)
        self.assertTrue(out[0]["is_main"])
        self.assertEqual(out[0]["branch"], "main")


class TestParseStashCount(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(sl.parse_stash_count(""), 0)

    def test_whitespace_only_is_zero(self):
        self.assertEqual(sl.parse_stash_count("\n  \n"), 0)

    def test_counts_lines(self):
        text = (
            "stash@{0}: WIP on feature-x: abc work\n"
            "stash@{1}: On main: def other\n"
        )
        self.assertEqual(sl.parse_stash_count(text), 2)

    def test_single_stash(self):
        self.assertEqual(sl.parse_stash_count("stash@{0}: WIP on x: abc\n"), 1)


class TestAnyActionable(unittest.TestCase):
    def test_all_falsy_or_missing(self):
        self.assertFalse(sl.any_actionable({}))

    def test_explicit_clean_summary(self):
        summary = {
            "dirty": False,
            "behind": 0,
            "ahead": 0,
            "unpushed": 0,
            "prune_candidates": [],
            "stale_worktrees": [],
            "stashes": 0,
        }
        self.assertFalse(sl.any_actionable(summary))

    def test_dirty_triggers(self):
        self.assertTrue(sl.any_actionable({"dirty": True}))

    def test_behind_triggers(self):
        self.assertTrue(sl.any_actionable({"behind": 1}))

    def test_ahead_triggers(self):
        self.assertTrue(sl.any_actionable({"ahead": 2}))

    def test_unpushed_triggers(self):
        self.assertTrue(sl.any_actionable({"unpushed": 3}))

    def test_prune_candidates_triggers(self):
        self.assertTrue(sl.any_actionable({"prune_candidates": ["old-feature"]}))

    def test_stale_worktrees_triggers(self):
        self.assertTrue(sl.any_actionable({"stale_worktrees": [{"path": "/x"}]}))

    def test_stashes_triggers(self):
        self.assertTrue(sl.any_actionable({"stashes": 1}))


class TestFirstOfDayGating(unittest.TestCase):
    """SH-1: first-of-day → emit + write marker; marker present → do not emit.

    The decision is a pure function of (root, local-date). The date is injected
    as an ISO string so the test is deterministic — no datetime.date.today()
    deep inside the code under test."""

    DATE = "2026-06-13"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _marker(self, date_iso):
        return os.path.join(self.root, ".codearbiter", ".markers",
                            f"standup-{date_iso}")

    def test_marker_path_shape(self):
        self.assertEqual(
            _mod.standup_marker_path(self.root, self.DATE),
            self._marker(self.DATE),
        )

    def test_no_marker_decides_emit(self):
        # No marker for D yet → emit the full briefing.
        self.assertTrue(_mod.should_emit_briefing(self.root, self.DATE))

    def test_write_marker_creates_markers_dir_lazily(self):
        # The .markers/ dir does not exist beforehand.
        markers_dir = os.path.join(self.root, ".codearbiter", ".markers")
        self.assertFalse(os.path.isdir(markers_dir))
        _mod.write_standup_marker(self.root, self.DATE)
        self.assertTrue(os.path.isdir(markers_dir))

    def test_write_marker_then_marker_file_exists(self):
        _mod.write_standup_marker(self.root, self.DATE)
        self.assertTrue(os.path.isfile(self._marker(self.DATE)))

    def test_marker_present_decides_suppress(self):
        # Given a marker already present for today → do NOT emit.
        _mod.write_standup_marker(self.root, self.DATE)
        self.assertFalse(_mod.should_emit_briefing(self.root, self.DATE))

    def test_marker_for_other_date_does_not_suppress(self):
        # A marker for a DIFFERENT date must not suppress today's briefing.
        _mod.write_standup_marker(self.root, "2026-06-12")
        self.assertTrue(_mod.should_emit_briefing(self.root, self.DATE))

    def test_emit_then_write_cycle_is_idempotent_suppress(self):
        # First-of-day: decision emit, then write marker; a second check for the
        # same date suppresses.
        self.assertTrue(_mod.should_emit_briefing(self.root, self.DATE))
        _mod.write_standup_marker(self.root, self.DATE)
        self.assertFalse(_mod.should_emit_briefing(self.root, self.DATE))


class TestBriefingMode(unittest.TestCase):
    """SH-2: three-mode briefing selection.

    Pure function of (marker_present, actionable) so the mode is decidable
    without git or a clock:
      - no marker                       -> "full"  (first session of the day)
      - marker present + actionable     -> "offer" (one concise offer line)
      - marker present + not actionable -> "none"  (stay silent)
    """

    def test_no_marker_is_full_regardless_of_actionable(self):
        # Regression guard for SH-1: first-of-day always gets the full briefing,
        # whether or not anything is actionable.
        self.assertEqual(_mod.briefing_mode(False, True), "full")
        self.assertEqual(_mod.briefing_mode(False, False), "full")

    def test_marker_present_and_actionable_is_offer(self):
        self.assertEqual(_mod.briefing_mode(True, True), "offer")

    def test_marker_present_and_not_actionable_is_none(self):
        self.assertEqual(_mod.briefing_mode(True, False), "none")

    def test_offer_line_is_exactly_one_line(self):
        # The offer text the hook emits in "offer" mode must be a SINGLE line:
        # exactly one trailing newline and no embedded newlines.
        line = _mod.OFFER_LINE
        self.assertTrue(line)
        self.assertEqual(line.count("\n"), 0)
        self.assertEqual(len(line.splitlines()), 1)


class _FakeProc:
    """Stand-in for subprocess.Popen: records whether the hook ever awaited it.
    A background fetch must be fully detached — the hook must NOT call .wait()
    or .communicate() (either would block on a hanging git fetch)."""

    def __init__(self):
        self.waited = False
        self.communicated = False

    def wait(self, *a, **k):
        self.waited = True
        raise AssertionError("background fetch must not be awaited (.wait called)")

    def communicate(self, *a, **k):
        self.communicated = True
        raise AssertionError("background fetch must not be awaited (.communicate called)")


class TestBackgroundFetch(unittest.TestCase):
    """SH-4: the hook kicks a DETACHED `git fetch` and returns without waiting on
    the network. Tested with an injected spawner — no real git, no real network."""

    def test_spawn_returns_promptly_without_waiting(self):
        # A spawner whose returned process would BLOCK if awaited. The function
        # under test must return it without ever calling .wait()/.communicate().
        proc = _FakeProc()
        calls = {"n": 0}

        def fake_spawner(args, root):
            calls["n"] += 1
            # sanity: it is a fetch, read-only
            self.assertIn("fetch", args)
            return proc

        start = time.time()
        out = _mod.spawn_background_fetch("/some/root", spawner=fake_spawner)
        elapsed = time.time() - start
        self.assertEqual(calls["n"], 1)
        self.assertIs(out, proc)
        self.assertFalse(proc.waited)
        self.assertFalse(proc.communicated)
        self.assertLess(elapsed, 1.0)  # returned promptly, did not block

    def test_hanging_fetch_does_not_block(self):
        # Even if the child "hangs" (modeled by a proc that raises if awaited),
        # spawn_background_fetch returns immediately.
        proc = _FakeProc()
        out = _mod.spawn_background_fetch("/root", spawner=lambda a, r: proc)
        self.assertIs(out, proc)
        self.assertFalse(proc.waited)

    def test_missing_or_failing_git_never_raises(self):
        # A spawner that blows up (git missing / OSError) must be swallowed:
        # offline is tolerated silently, the hook never errors.
        def boom(args, root):
            raise FileNotFoundError("git not found")

        out = _mod.spawn_background_fetch("/root", spawner=boom)
        self.assertIsNone(out)

    def test_default_spawner_detaches_and_devnulls(self):
        # With the real (default) spawner, assert Popen is invoked detached:
        # stdout/stderr -> DEVNULL, and the platform detach knob is set
        # (POSIX start_new_session=True, or Windows creationflags != 0). We stub
        # subprocess.Popen so no real process is launched.
        captured = {}

        class _Stub:
            def __init__(self, args, **kw):
                captured["args"] = args
                captured["kw"] = kw

        orig = _mod.subprocess.Popen
        _mod.subprocess.Popen = _Stub
        try:
            _mod.spawn_background_fetch("/root")
        finally:
            _mod.subprocess.Popen = orig
        kw = captured.get("kw", {})
        self.assertEqual(kw.get("stdout"), _mod.subprocess.DEVNULL)
        self.assertEqual(kw.get("stderr"), _mod.subprocess.DEVNULL)
        detached = kw.get("start_new_session") or kw.get("creationflags")
        self.assertTrue(detached, "child must be detached from the hook")
        self.assertIn("fetch", captured.get("args", []))

    def test_staleness_note_is_nonempty_single_line(self):
        # The briefing must NOTE that ahead/behind reflects the last fetch.
        note = _mod.STALE_REFS_NOTE
        self.assertTrue(note.strip())
        self.assertEqual(note.count("\n"), 0)


class TestGitRead(unittest.TestCase):
    """The git-invocation wrapper: runs a read-only git command, returns stdout
    text, and returns "" on ANY error (timeout, missing git, non-zero). The
    runner is injectable so tests never shell out to real git."""

    def test_returns_runner_output(self):
        def runner(args, root):
            self.assertEqual(root, "/r")
            return "hello\n"

        self.assertEqual(_mod.git_read(["status"], "/r", runner=runner), "hello\n")

    def test_runner_exception_degrades_to_empty(self):
        def runner(args, root):
            raise OSError("boom")

        self.assertEqual(_mod.git_read(["status"], "/r", runner=runner), "")

    def test_runner_returning_none_degrades_to_empty(self):
        self.assertEqual(_mod.git_read(["x"], "/r", runner=lambda a, r: None), "")


class TestAssembleSummary(unittest.TestCase):
    """SH content assembly: feed fake git command outputs through an injected
    runner; assert the parsed summary fields and any_actionable()."""

    # Map a git command (matched by a distinctive token) to a canned stdout.
    def _runner_from(self, table, raises_for=None):
        def runner(args, root):
            joined = " ".join(args)
            if raises_for and raises_for in joined:
                raise OSError("simulated read failure")
            for token, out in table.items():
                if token in joined:
                    return out
            return ""
        return runner

    def test_dirty_repo_is_actionable(self):
        table = {
            "status": "M  a.py\n?? b.py\n",
            "rev-list": "2\t3",
            "branch": (
                "* feature-x abc [origin/feature-x] live\n"
                "  old-feature def [origin/old-feature: gone] merged\n"
                "  main aaa [origin/main] mainline\n"
            ),
            "worktree": "worktree /root\nHEAD abc\nbranch refs/heads/feature-x\n\n",
            "stash": "stash@{0}: WIP on feature-x: zzz\n",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="feature-x", default="main",
        )
        self.assertTrue(summary["dirty"])
        self.assertEqual(summary["behind"], 2)
        self.assertEqual(summary["ahead"], 3)
        self.assertEqual(summary["unpushed"], 3)
        self.assertEqual(summary["prune_candidates"], ["old-feature"])
        self.assertEqual(summary["stashes"], 1)
        self.assertTrue(sl.any_actionable(summary))

    def test_dirty_repo_not_ff_pull_eligible(self):
        # SH-6 wired live: a dirty tree withholds ff-pull even when behind.
        table = {"status": "M  a.py\n", "rev-list": "2\t0",
                 "branch": "* main aaa [origin/main]\n", "worktree": "", "stash": ""}
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table), current="main", default="main")
        self.assertFalse(summary["ff_pull_eligible"])

    def test_clean_behind_is_ff_pull_eligible(self):
        # SH-6 wired live: clean tree AND behind>0 -> eligible.
        table = {"status": "", "rev-list": "2\t0",
                 "branch": "* main aaa [origin/main]\n", "worktree": "", "stash": ""}
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table), current="main", default="main")
        self.assertTrue(summary["ff_pull_eligible"])
        self.assertTrue(summary["upstream"])

    def test_clean_repo_all_zero_not_actionable(self):
        table = {
            "status": "",
            "rev-list": "0\t0",
            "branch": "* main aaa [origin/main] mainline\n",
            "worktree": "worktree /root\nHEAD abc\nbranch refs/heads/main\n\n",
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="main", default="main",
        )
        self.assertFalse(summary["dirty"])
        self.assertFalse(summary["ff_pull_eligible"])   # behind 0 -> not eligible
        self.assertEqual(summary["behind"], 0)
        self.assertEqual(summary["ahead"], 0)
        self.assertEqual(summary["unpushed"], 0)
        self.assertEqual(summary["prune_candidates"], [])
        self.assertEqual(summary["stashes"], 0)
        self.assertFalse(sl.any_actionable(summary))

    def test_one_command_failure_degrades_field_no_crash(self):
        # The stash command raises; that field degrades to 0, everything else
        # parses, and no exception escapes.
        table = {
            "status": "M  a.py\n",
            "rev-list": "1\t0",
            "branch": "* main aaa [origin/main] mainline\n",
            "worktree": "worktree /root\nHEAD abc\nbranch refs/heads/main\n\n",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table, raises_for="stash"),
            current="main", default="main",
        )
        self.assertEqual(summary["stashes"], 0)   # degraded, not crashed
        self.assertTrue(summary["dirty"])
        self.assertEqual(summary["behind"], 1)

    def test_no_upstream_rev_list_empty_yields_zero(self):
        # When there is no upstream, rev-list output is empty -> behind/ahead 0.
        table = {
            "status": "",
            "rev-list": "",
            "branch": "* feature-x abc [origin/feature-x] live\n",
            "worktree": "",
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="feature-x", default="main",
        )
        self.assertEqual(summary["behind"], 0)
        self.assertEqual(summary["ahead"], 0)
        self.assertFalse(summary["upstream"])   # empty rev-list -> no tracking branch
        self.assertFalse(summary["ff_pull_eligible"])


class TestAssembleSummaryStaleWorktrees(unittest.TestCase):
    """Assembly wiring (task 8 carry-over): assemble_summary must populate
    `stale_worktrees` from `worktree list --porcelain` parsed against the gone
    set derived from the same `branch -vv` text, and degrade gracefully."""

    def _runner_from(self, table, raises_for=None):
        def runner(args, root):
            joined = " ".join(args)
            if raises_for and raises_for in joined:
                raise OSError("simulated read failure")
            for token, out in table.items():
                if token in joined:
                    return out
            return ""
        return runner

    def test_stale_worktree_populated_and_actionable(self):
        # A side worktree on a `: gone]` branch -> stale candidate. Inject a
        # path_exists that says every path exists, so the ONLY staleness signal is
        # the gone branch (proves the gone-set derivation is wired up).
        table = {
            "status": "",
            "rev-list": "0\t0",
            "branch": (
                "* main aaa [origin/main] mainline\n"
                "  old-feature def [origin/old-feature: gone] merged\n"
            ),
            "worktree": (
                "worktree /root\nHEAD abc\nbranch refs/heads/main\n\n"
                "worktree /root-old\nHEAD def\nbranch refs/heads/old-feature\n\n"
            ),
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="main", default="main", path_exists=lambda p: True,
        )
        self.assertEqual(
            [w["path"] for w in summary["stale_worktrees"]], ["/root-old"]
        )
        self.assertTrue(sl.any_actionable(summary))

    def test_clean_repo_no_stale_worktrees_not_actionable(self):
        table = {
            "status": "",
            "rev-list": "0\t0",
            "branch": "* main aaa [origin/main] mainline\n",
            "worktree": "worktree /root\nHEAD abc\nbranch refs/heads/main\n\n",
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="main", default="main", path_exists=lambda p: True,
        )
        self.assertEqual(summary["stale_worktrees"], [])
        self.assertFalse(sl.any_actionable(summary))

    def test_worktree_read_failure_degrades_to_empty_no_crash(self):
        table = {
            "status": "",
            "rev-list": "0\t0",
            "branch": "* main aaa [origin/main] mainline\n",
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table, raises_for="worktree"),
            current="main", default="main", path_exists=lambda p: True,
        )
        self.assertEqual(summary["stale_worktrees"], [])

    def test_missing_path_makes_worktree_stale(self):
        # Branch is live (not gone), but the side worktree's directory is gone on
        # disk -> stale via the path_exists signal.
        table = {
            "status": "",
            "rev-list": "0\t0",
            "branch": (
                "* main aaa [origin/main] mainline\n"
                "  live-feature def [origin/live-feature] live\n"
            ),
            "worktree": (
                "worktree /root\nHEAD abc\nbranch refs/heads/main\n\n"
                "worktree /root-live\nHEAD def\nbranch refs/heads/live-feature\n\n"
            ),
            "stash": "",
        }
        summary = _mod.assemble_summary(
            "/root", runner=self._runner_from(table),
            current="main", default="main",
            path_exists=lambda p: p == "/root",  # /root-live is "gone" on disk
        )
        self.assertEqual(
            [w["path"] for w in summary["stale_worktrees"]], ["/root-live"]
        )
        self.assertTrue(sl.any_actionable(summary))


class _MainHarness(unittest.TestCase):
    """Shared scaffolding for exercising session-start.py main() deterministically.

    main() reaches git only through three module-level seams, which we patch so
    NO real git/network/clock is touched:
      - project_root()          -> the temp repo (instead of `git rev-parse`)
      - _default_git_runner     -> a recording, canned-output read runner
      - _detached_fetch_spawner -> a recording fake spawner (no Popen)
    statusline reuse (head_branch / arbiter_state) is pure file I/O on the temp
    repo, so it needs no patching."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        # A bare .git dir so statusline.head_branch can read .git/HEAD.
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        with open(os.path.join(self.root, ".git", "HEAD"), "w", encoding="utf-8") as f:
            f.write("ref: refs/heads/sprint/session-hygiene\n")
        self._saved = {
            "project_root": _mod.project_root,
            "_default_git_runner": _mod._default_git_runner,
            "_detached_fetch_spawner": _mod._detached_fetch_spawner,
        }
        _mod.project_root = lambda: self.root

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(_mod, name, fn)
        self._tmp.cleanup()

    def _write_context(self, text):
        cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(cad, exist_ok=True)
        with open(os.path.join(cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write(text)

    def _run_main(self):
        """Run main() to its sys.exit(0), capturing stdout. Returns the stdout
        text. main() always exits 0; any other code is a failure to surface."""
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                _mod.main()
        self.assertEqual(cm.exception.code, 0)
        return buf.getvalue()


# The full enabled+initialized fixture: enables the arbiter and marks the project
# initialized so main() runs all the way through the standup-briefing block.
_ENABLED_INITIALIZED_CONTEXT = (
    "---\n"
    "arbiter: enabled\n"
    "stage: 2\n"
    "---\n"
    "<!--INITIALIZED-->\n"
    "# Project\n"
)


class TestDormancyNoBriefing(_MainHarness):
    """SH-3: in a repo WITHOUT `arbiter: enabled`, main() emits NEITHER the daily
    briefing NOR the offer line — it goes dormant like every other hook.

    The briefing/offer code lives entirely inside the enabled+initialized branch,
    so this is a lock-in test of that structure. We also patch the git seams to
    blow up if reached, proving the dormant path performs no git at all."""

    def setUp(self):
        super().setUp()
        # If the dormant path ever reaches git, fail loudly rather than silently
        # shelling out to real git during the test.
        def _boom_runner(args, root):
            raise AssertionError(f"dormant path must not run git: {args}")

        def _boom_spawner(args, root):
            raise AssertionError(f"dormant path must not spawn git: {args}")

        _mod._default_git_runner = _boom_runner
        _mod._detached_fetch_spawner = _boom_spawner

    def _assert_dormant(self, out):
        self.assertNotIn("daily briefing", out)
        self.assertNotIn("=== codeArbiter startup state ===", out)
        self.assertNotIn(_mod.OFFER_LINE, out)
        # And no orchestrator persona / state injected at all.
        self.assertEqual(out, "")

    def test_missing_context_is_dormant(self):
        # No .codearbiter/CONTEXT.md at all.
        self._assert_dormant(self._run_main())

    def test_context_without_arbiter_flag_is_dormant(self):
        # CONTEXT.md exists but has no `arbiter: enabled`.
        self._write_context("---\nstage: 2\n---\n# Project, but arbiter not enabled\n")
        self._assert_dormant(self._run_main())

    def test_context_no_frontmatter_is_dormant(self):
        # A CONTEXT.md with no frontmatter block at all -> dormant, not malformed.
        self._write_context("# Project\nNo frontmatter here.\n")
        self._assert_dormant(self._run_main())


# READ-ONLY git allowlist (SH-5). Each entry is (verb, predicate(args)->bool):
# the verb must be the first git token, and the predicate vets the rest of the
# argv as non-mutating. Anything not matched here is treated as a violation.
def _is_readonly_git(args):
    """True iff `args` (the git argv AFTER `git -C <root>`) is a known READ-ONLY
    command with no mutating flags. Conservative: unknown verbs are NOT read-only,
    and any mutating sub-verb/flag disqualifies."""
    if not args:
        return False
    verb = args[0]
    rest = args[1:]
    # Mutating branch flags: -d/-D (delete), -m/-M (move), -f (force create/reset).
    _branch_mut = {"-d", "-D", "-m", "-M", "-f", "--delete", "--move", "--force"}
    # Mutating stash sub-verbs.
    _stash_mut = {"drop", "pop", "clear", "apply", "push", "save", "create", "store"}
    # Mutating worktree sub-verbs.
    _worktree_mut = {"add", "remove", "move", "prune", "lock", "unlock", "repair"}
    if verb in ("status", "rev-list", "rev-parse"):
        return True
    if verb == "branch":
        return not any(a in _branch_mut for a in rest)
    if verb == "stash":
        # Only `stash list` (and bare `stash` is interactive — disallow).
        return rest[:1] == ["list"]
    if verb == "worktree":
        return rest[:1] == ["list"]
    if verb == "fetch":
        # The detached refresh: refs-only, no working-tree/index change. Reject any
        # flag that would prune local refs destructively or write to the worktree.
        # --prune only removes stale remote-tracking refs (refs, not worktree); we
        # still treat the observed `fetch --quiet --no-tags` as the canonical form.
        return True
    return False


# Verbs that must NEVER appear — an explicit denylist mirrored from the spec, so
# a regression that swaps in a mutating verb fails loudly even if _is_readonly_git
# were ever loosened.
_MUTATING_VERBS = {
    "add", "commit", "checkout", "switch", "reset", "pull", "merge", "rebase",
    "push", "clean", "rm", "mv", "apply", "cherry-pick", "revert", "tag", "init",
    "clone", "gc", "prune", "restore",
}


class _RecordingRunner:
    """A read runner that records every git argv and returns canned output keyed
    by a distinctive token in the command (same idiom as TestAssembleSummary)."""

    def __init__(self, table):
        self.table = table
        self.calls = []  # list of argv lists (the args after `git -C <root>`)

    def __call__(self, args, root):
        self.calls.append(list(args))
        joined = " ".join(args)
        for token, out in self.table.items():
            if token in joined:
                return out
        return ""


class _RecordingSpawner:
    """A fake detached spawner: records the fetch argv, returns a sentinel proc,
    and is NEVER awaited (mirrors _FakeProc semantics for safety)."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, root):
        self.calls.append(list(args))
        return _FakeProc()


class TestReadOnlyProof(_MainHarness):
    """SH-5: a full enabled-path run issues ONLY read-only git, and the ONLY
    filesystem write is the standup marker.

    Every git command main() would run is captured via injected recording seams
    (read runner + fetch spawner); each captured argv is checked against the
    read-only allowlist and against the mutating-verb denylist."""

    def setUp(self):
        super().setUp()
        self._write_context(_ENABLED_INITIALIZED_CONTEXT)
        # A dirty/ahead/behind/stash/prune fixture so the briefing exercises EVERY
        # read command — including the prune-candidate and stash branches.
        self.runner = _RecordingRunner({
            "status": "M  a.py\n?? b.py\n",
            "rev-list": "2\t3",
            "branch": (
                "* sprint/session-hygiene abc [origin/sprint/session-hygiene] live\n"
                "  old-feature def [origin/old-feature: gone] merged\n"
                "  main aaa [origin/main] mainline\n"
            ),
            "stash": "stash@{0}: WIP on x: zzz\n",
        })
        self.spawner = _RecordingSpawner()
        _mod._default_git_runner = self.runner
        _mod._detached_fetch_spawner = self.spawner

    def _snapshot_tree(self):
        """Map of relative-path -> mtime+size for every file under root EXCEPT the
        .git dir, used to prove no tracked path changed except the marker."""
        snap = {}
        for cur, dirs, files in os.walk(self.root):
            if ".git" in dirs:
                dirs.remove(".git")
            for fn in files:
                full = os.path.join(cur, fn)
                rel = os.path.relpath(full, self.root)
                try:
                    st = os.stat(full)
                    snap[rel] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    snap[rel] = None
        return snap

    def test_every_git_command_is_read_only(self):
        out = self._run_main()
        # The full briefing actually ran (sanity: we exercised the briefing path).
        self.assertIn("daily briefing", out)

        # Some read command was issued, and the detached fetch was spawned exactly
        # once (and never awaited — _FakeProc raises if it is).
        self.assertTrue(self.runner.calls, "expected at least one read command")
        self.assertEqual(len(self.spawner.calls), 1)

        # Every captured git invocation (reads + the fetch) is read-only and uses
        # no mutating verb.
        all_invocations = list(self.runner.calls) + list(self.spawner.calls)
        for argv in all_invocations:
            with self.subTest(argv=argv):
                self.assertTrue(
                    _is_readonly_git(argv),
                    f"non-allowlisted git invocation: {argv}",
                )
                self.assertNotIn(
                    argv[0], _MUTATING_VERBS,
                    f"mutating git verb issued: {argv}",
                )
                # No mutating verb anywhere in the argv (defends `stash drop`,
                # `worktree remove`, `branch -D`, etc. expressed as sub-tokens).
                for tok in argv[1:]:
                    self.assertNotIn(
                        tok, _MUTATING_VERBS,
                        f"mutating sub-verb in argv: {argv}",
                    )

    def test_read_command_surface_is_within_allowlist(self):
        # Lock in the exact set of read verbs the assembly issues: status, rev-list,
        # branch, worktree, stash. (rev-parse is allowlisted but not issued by this
        # path; its presence in the allowlist is intentional headroom.)
        self._run_main()
        verbs = {argv[0] for argv in self.runner.calls}
        self.assertEqual(verbs, {"status", "rev-list", "branch", "worktree", "stash"})
        # The worktree read is the non-mutating `list --porcelain` form.
        for a in (a for a in self.runner.calls if a[0] == "worktree"):
            self.assertEqual(a[1:2], ["list"])
        # The branch read is the non-mutating `-vv` form.
        branch_calls = [a for a in self.runner.calls if a[0] == "branch"]
        self.assertTrue(branch_calls)
        for a in branch_calls:
            self.assertIn("-vv", a)
            self.assertFalse(
                any(x in {"-d", "-D", "-m", "-M", "-f"} for x in a[1:])
            )
        # The stash read is `stash list`, never a mutating sub-verb.
        for a in (a for a in self.runner.calls if a[0] == "stash"):
            self.assertEqual(a[1:2], ["list"])

    def test_fetch_is_refs_only_no_worktree_change(self):
        # The detached refresh must be the refs-only form: no working-tree/index
        # mutation flags, and certainly no mutating verb riding the fetch argv.
        self._run_main()
        self.assertEqual(len(self.spawner.calls), 1)
        argv = self.spawner.calls[0]
        self.assertEqual(argv[0], "fetch")
        self.assertIn("--quiet", argv)
        self.assertIn("--no-tags", argv)
        # No flag that would write the worktree/index or do a merge-on-fetch.
        forbidden = {"--update-head-ok", "--force", "-f", "--write-fetch-head",
                     "--prune", "--all"}
        self.assertFalse(
            any(x in forbidden for x in argv[1:]),
            f"fetch carried a non-refs-only flag: {argv}",
        )

    def test_only_filesystem_write_is_standup_marker(self):
        # Capture the tree before, run main(), diff after. The ONLY new/changed
        # path under root (excluding .git) must be the standup marker.
        before = self._snapshot_tree()
        self._run_main()
        after = self._snapshot_tree()

        date_iso = _mod.local_date_iso()
        marker_rel = os.path.relpath(
            _mod.standup_marker_path(self.root, date_iso), self.root
        )

        new_paths = set(after) - set(before)
        changed_paths = {p for p in (set(after) & set(before)) if after[p] != before[p]}
        removed_paths = set(before) - set(after)

        self.assertEqual(
            new_paths, {marker_rel},
            f"unexpected new files (only the standup marker is allowed): "
            f"{new_paths - {marker_rel}}",
        )
        self.assertEqual(changed_paths, set(), f"unexpected modified files: {changed_paths}")
        self.assertEqual(removed_paths, set(), f"unexpected removed files: {removed_paths}")
        # And the marker truly exists on disk.
        self.assertTrue(os.path.isfile(
            _mod.standup_marker_path(self.root, date_iso)
        ))


if __name__ == "__main__":
    unittest.main()
