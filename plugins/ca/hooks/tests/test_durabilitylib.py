"""Unit tests for _durabilitylib — "may this path be pinned into a long-lived
global config?".

Found in-session on 2026-07-25, after `heal_statusline_wiring()` rewrote the
maintainer's GLOBAL ~/.claude/settings.json to a git-worktree path three times
in one day. The worktree is then pruned — that is what worktrees are FOR — and
the statusline renders nothing.

Two independent signals, because each alone has a blind spot:
  * LEXICAL  — a `worktrees` / `*-worktrees` path segment. Covers the confirmed
               `<repo>/.claude/worktrees/<id>/` shape and the
               `../.codearbiter-worktrees/<slug>` layout, with zero I/O.
  * GIT      — the path lives inside a LINKED git worktree, detected by git's
               own on-disk marker: a linked worktree's `.git` is a FILE reading
               `gitdir: <common>/.git/worktrees/<name>`, never a directory.
               Catches a worktree parked anywhere under any name.

Both directions matter, so both are pinned here: a false positive costs one
un-refreshed pin the user fixes with a single /ca:statusline run, while a false
negative corrupts their global config.
"""

import os
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import _durabilitylib as dl


def _mkdirs(*parts):
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class TestHasWorktreeSegment(unittest.TestCase):
    """The zero-I/O lexical signal. Segment equality, never substring."""

    def test_claude_subagent_worktree_matches(self):
        # The exact shape observed on the maintainer's machine.
        self.assertTrue(dl.has_worktree_segment(
            r"C:\Users\me\repo\.claude\worktrees\wf_58ee3fa6-de1-8"
            r"\plugins\ca\hooks\statusline.py"))

    def test_codearbiter_worktrees_layout_matches(self):
        # The layout the using-git-worktrees skill creates.
        self.assertTrue(dl.has_worktree_segment(
            "/home/me/.codearbiter-worktrees/add-widget/plugins/ca/hooks/statusline.py"))

    def test_plugin_cache_install_does_not_match(self):
        self.assertFalse(dl.has_worktree_segment(
            r"C:\Users\me\.claude\plugins\cache\codearbiter\ca\2.8.13"
            r"\hooks\statusline.py"))

    def test_source_checkout_does_not_match(self):
        self.assertFalse(dl.has_worktree_segment(
            "/home/me/projects/codeArbiter/plugins/ca/hooks/statusline.py"))

    def test_substring_is_not_a_segment(self):
        # `worktrees-archive` is a directory of its own name, not a container of
        # worktrees. Matching it would decline to heal a perfectly durable root.
        self.assertFalse(dl.has_worktree_segment(
            "/srv/worktrees-archive/ca/hooks/statusline.py"))
        self.assertFalse(dl.has_worktree_segment(
            "/srv/myworktreesbackup/ca/hooks/statusline.py"))

    def test_case_insensitive(self):
        self.assertTrue(dl.has_worktree_segment(r"C:\repo\.claude\WorkTrees\x\y"))

    def test_mixed_separators(self):
        # A Windows path can be read out of a POSIX-written config and vice versa.
        self.assertTrue(dl.has_worktree_segment("C:/repo/.claude\\worktrees/x/y"))

    def test_junk_input_is_false_never_raises(self):
        for junk in (None, "", 17, [], {}, object()):
            self.assertFalse(dl.has_worktree_segment(junk))


class TestInLinkedWorktree(unittest.TestCase):
    """The git signal, read straight off disk — no subprocess.

    Git's own marker: in a LINKED worktree `.git` is a FILE containing
    `gitdir: <common>/.git/worktrees/<name>`; in the main worktree `.git` is a
    DIRECTORY. A submodule also uses a `.git` file, but its gitdir points at
    `<super>/.git/modules/<name>` — durable, and must not be confused for one.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_linked_worktree_gitfile_is_ephemeral(self):
        repo = _mkdirs(self.root, "ca-feature")
        _write(os.path.join(repo, ".git"),
               "gitdir: C:/Users/me/projects/codeArbiter/.git/worktrees/ca-feature\n")
        deep = _mkdirs(repo, "plugins", "ca", "hooks")
        self.assertTrue(dl.in_linked_worktree(deep))

    def test_signal_survives_a_file_argument(self):
        repo = _mkdirs(self.root, "ca-feature")
        _write(os.path.join(repo, ".git"),
               "gitdir: /home/me/codeArbiter/.git/worktrees/ca-feature\n")
        hooks = _mkdirs(repo, "plugins", "ca", "hooks")
        script = os.path.join(hooks, "statusline.py")
        _write(script, "")
        self.assertTrue(dl.in_linked_worktree(script))

    def test_main_checkout_gitdir_is_durable(self):
        repo = _mkdirs(self.root, "codeArbiter")
        _mkdirs(repo, ".git")
        deep = _mkdirs(repo, "plugins", "ca", "hooks")
        self.assertFalse(dl.in_linked_worktree(deep))

    def test_submodule_gitfile_is_durable(self):
        # A submodule is a normal, long-lived checkout: `.git` is a file, but it
        # points into `modules/`, not `worktrees/`.
        sub = _mkdirs(self.root, "super", "vendor", "ca")
        _write(os.path.join(sub, ".git"),
               "gitdir: ../../.git/modules/vendor/ca\n")
        self.assertFalse(dl.in_linked_worktree(_mkdirs(sub, "hooks")))

    def test_no_git_anywhere_is_durable(self):
        # The ordinary install: the plugin cache is not a git repository at all.
        cache = _mkdirs(self.root, ".claude", "plugins", "cache",
                        "codearbiter", "ca", "2.8.13", "hooks")
        self.assertFalse(dl.in_linked_worktree(cache))

    def test_unreadable_or_garbage_gitfile_is_durable(self):
        repo = _mkdirs(self.root, "weird")
        _write(os.path.join(repo, ".git"), "this is not a gitdir pointer\n")
        self.assertFalse(dl.in_linked_worktree(_mkdirs(repo, "hooks")))

    def test_nearest_boundary_wins(self):
        # A real main checkout that merely SITS somewhere below an unrelated
        # linked-worktree marker must read as durable: the walk stops at the
        # first `.git` it meets, which is the repository the path belongs to.
        outer = _mkdirs(self.root, "outer")
        _write(os.path.join(outer, ".git"), "gitdir: /x/.git/worktrees/outer\n")
        inner = _mkdirs(outer, "nested", "codeArbiter")
        _mkdirs(inner, ".git")
        self.assertFalse(dl.in_linked_worktree(_mkdirs(inner, "plugins", "ca")))

    def test_junk_input_is_false_never_raises(self):
        for junk in (None, "", 17, [], {}):
            self.assertFalse(dl.in_linked_worktree(junk))


class TestIsEphemeralPath(unittest.TestCase):
    """The combined predicate the pin writers actually call."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_lexical_signal_alone_is_enough(self):
        # No git anywhere near it — the confirmed case, decided for free.
        self.assertTrue(dl.is_ephemeral_path(
            os.path.join(self.tmp.name, "repo", ".claude", "worktrees",
                         "wf_58ee3fa6-de1-8", "plugins", "ca", "hooks",
                         "statusline.py")))

    def test_git_signal_alone_is_enough(self):
        # A worktree parked under an ordinary name: the lexical rule cannot see
        # it, so this is exactly what the git signal is here to catch.
        repo = _mkdirs(self.tmp.name, "ca-feature")
        _write(os.path.join(repo, ".git"), "gitdir: /x/.git/worktrees/ca-feature\n")
        script = os.path.join(_mkdirs(repo, "plugins", "ca", "hooks"),
                              "statusline.py")
        self.assertFalse(dl.has_worktree_segment(script))
        self.assertTrue(dl.is_ephemeral_path(script))

    def test_plugin_cache_install_is_durable(self):
        cache = os.path.join(self.tmp.name, ".claude", "plugins", "cache",
                             "codearbiter", "ca", "2.8.13", "hooks",
                             "statusline.py")
        _mkdirs(os.path.dirname(cache))
        self.assertFalse(dl.is_ephemeral_path(cache))

    def test_junk_input_is_false_never_raises(self):
        for junk in (None, "", 17, [], {}):
            self.assertFalse(dl.is_ephemeral_path(junk))


class TestHotPathCost(unittest.TestCase):
    """This predicate is consulted on EVERY SessionStart, before the dormant
    gate, in every repo on the machine. It must not spawn a process.

    An earlier draft shelled out to `git rev-parse --git-dir --git-common-dir`.
    That probe fails by design in the ordinary plugin-cache install (not a git
    repo at all), so it bought nothing there while charging every session a
    process spawn plus a timeout hazard. Git's on-disk marker gives the same
    answer from a handful of stat() calls."""

    def test_module_does_not_import_subprocess(self):
        self.assertFalse(
            hasattr(dl, "subprocess"),
            "_durabilitylib must stay subprocess-free: it runs on the "
            "SessionStart hot path in every repo.")


if __name__ == "__main__":
    unittest.main()
