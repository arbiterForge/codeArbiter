"""Behavioral coverage for the git-level enforcement backstop (#161).

pre-bash.py gates git operations by matching the literal Bash command string, so
shell indirection (`g=git; c=commit; $g $c`) walks straight past it. _githooks.py
installs .git/hooks/pre-commit and pre-push that run git-enforce.py at the git
operation itself, where spelling no longer matters. These tests prove:

  * install() writes ours-hooks, is idempotent, and NEVER clobbers a foreign hook
  * git-enforce.py blocks a commit onto main — including via VARIABLE INDIRECTION,
    the exact bypass #161 is about — and allows a feature-branch commit
  * it blocks a crypto commit lacking a security-gate marker (H-09b)
  * pre-push blocks a protected-branch push (H-01), allows a feature fast-forward
  * a non-arbiter repo is a no-op

Stdlib only; a real throwaway git repo per test (git hooks only fire against a
real repo).
"""
import contextlib
import importlib.util as _ilu
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENFORCE = os.path.join(HOOKS, "git-enforce.py")

sys.path.insert(0, HOOKS)
import _githooks  # noqa: E402


def _load_git_enforce():
    """Import git-enforce.py fresh as a module (hyphenated filename, so a
    plain `import` can't name it — mirrors test_governs.py's pattern). A fresh
    module per call means monkeypatches in one test can never leak into
    another via a cached singleton."""
    spec = _ilu.spec_from_file_location("git_enforce_direct", ENFORCE)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd, check=True):
    r = _sh(["git"] + args, cwd)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _GitFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "main"], self.root)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        self._write(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), self.ARBITER)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _disable_arbiter(self):
        self._write(os.path.join(self.root, ".codearbiter", "CONTEXT.md"),
                    "# ctx\nno frontmatter\n")

    def enforce(self, phase, stdin=""):
        return _sh([sys.executable, ENFORCE, phase], self.root, input=stdin)


class TestInstall(_GitFixture):
    def _hooks_dir(self):
        return os.path.join(self.root, ".git", "hooks")

    def test_install_writes_both_hooks(self):
        _githooks.install(self.root)
        for phase in ("pre-commit", "pre-push"):
            dest = os.path.join(self._hooks_dir(), phase)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as f:
                self.assertIn(_githooks.SENTINEL, f.read())
            self.assertTrue(os.access(dest, os.X_OK))

    def test_pi_identity_channel_persists_across_later_identityless_host_session(self):
        trusted_git = os.path.realpath(shutil.which("git"))
        trusted_python = os.path.realpath(sys.executable)
        dropin = _githooks._dropin_dir(self.root)
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=trusted_git), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=trusted_python):
            _githooks.install(self.root)
        shim_path = os.path.join(self._hooks_dir(), "pre-commit")
        with open(shim_path, encoding="utf-8") as f:
            pinned = f.read()
        self.assertIn(_githooks._TRUSTED_IDENTITY_FILE, pinned)
        self.assertIn('export CODEARBITER_GIT_EXECUTABLE="$G"', pinned)
        with open(_githooks._identity_file(dropin), encoding="utf-8") as f:
            identity = f.read()
        self.assertEqual(identity.splitlines()[0], trusted_python.replace("\\", "/"))

        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=None), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            self.assertEqual(_githooks.install(self.root), [])
        with open(shim_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), pinned)
        with open(_githooks._identity_file(dropin), encoding="utf-8") as f:
            self.assertEqual(f.read(), identity)

    def test_incomplete_or_failed_first_identity_registration_blocks(self):
        dropin = _githooks._dropin_dir(self.root)
        trusted_git = os.path.realpath(shutil.which("git"))
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=trusted_git), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "identity channel is incomplete"):
                _githooks.install(self.root)
        self.assertFalse(os.path.exists(_githooks._identity_file(dropin)))

        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=trusted_git), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=sys.executable), \
                mock.patch.object(
                    _githooks._hooklib, "write_text_atomic", side_effect=OSError("denied")):
            with self.assertRaisesRegex(RuntimeError, "could not persist"):
                _githooks.install(self.root)
        self.assertFalse(os.path.exists(_githooks._identity_file(dropin)))

    def test_incomplete_refresh_preserves_existing_complete_identity(self):
        dropin = _githooks._dropin_dir(self.root)
        trusted_git = os.path.realpath(shutil.which("git"))
        trusted_python = os.path.realpath(sys.executable)
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=trusted_git), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=trusted_python):
            self.assertTrue(_githooks._refresh_trusted_identity(dropin, "ca-pi"))
        with open(_githooks._identity_file(dropin), encoding="utf-8") as f:
            before = f.read()
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=trusted_git), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            self.assertTrue(_githooks._refresh_trusted_identity(dropin, "ca-pi"))
        with open(_githooks._identity_file(dropin), encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_shim_and_registry_render_windows_paths_for_posix_sh(self):
        with mock.patch.dict(
                os.environ,
                {
                    "CODEARBITER_GIT_EXECUTABLE": r"C:\Program Files\Git\cmd\git.exe",
                    "CODEARBITER_PYTHON_EXECUTABLE": r"C:\Python314\python.exe",
                },
                clear=False):
            shim = _githooks._shim(
                r"C:\repo with space\.git\codearbiter-hooksd", "pre-commit")
        self.assertIn("D='C:/repo with space/.git/codearbiter-hooksd'", shim)
        self.assertIn("trusted-executables.identity", shim)
        self.assertIn('IFS= read -r E < "$c"', shim)
        self.assertNotIn('$(cat "$c"', shim)
        self.assertIn('[0-9]*.[0-9]*.[0-9]*.path) continue', shim)

        dropin = os.path.join(self.root, ".git", "codearbiter-hooksd")
        self.assertTrue(_githooks._write_path_entry(
            dropin, "ca", r"C:\plugins\ca\hooks\git-enforce.py"))
        with open(os.path.join(dropin, "ca.path"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "C:/plugins/ca/hooks/git-enforce.py\n")

    def test_plugin_identity_survives_versioned_host_cache_layouts(self):
        fixtures = (
            ("ca", "2.9.0", ".claude-plugin"),
            ("ca-codex", "0.3.0", ".codex-plugin"),
        )
        for plugin, version, manifest_dir in fixtures:
            with self.subTest(plugin=plugin):
                package = os.path.join(self.root, "cache", plugin, version)
                hooks = os.path.join(package, "hooks")
                os.makedirs(os.path.join(package, manifest_dir), exist_ok=True)
                self._write(
                    os.path.join(package, manifest_dir, "plugin.json"),
                    '{"name": "' + plugin + '"}\n',
                )
                with mock.patch.object(
                        _githooks, "__file__", os.path.join(hooks, "_githooks.py")):
                    self.assertEqual(_githooks._plugin_name(), plugin)

    def test_versioned_cache_identity_fails_safe_when_manifest_is_damaged(self):
        package = os.path.join(self.root, "cache", "ca-codex", "0.3.0")
        hooks = os.path.join(package, "hooks")
        os.makedirs(os.path.join(package, ".codex-plugin"), exist_ok=True)
        self._write(os.path.join(package, ".codex-plugin", "plugin.json"), "not json\n")
        with mock.patch.object(
                _githooks, "__file__", os.path.join(hooks, "_githooks.py")):
            self.assertEqual(_githooks._plugin_name(), "ca-codex")

    def test_install_is_idempotent(self):
        _githooks.install(self.root)
        second = _githooks.install(self.root)
        self.assertEqual(second, [])  # already current -> no churn

    def test_foreign_hook_is_preserved(self):
        dest = os.path.join(self._hooks_dir(), "pre-commit")
        os.makedirs(self._hooks_dir(), exist_ok=True)
        self._write(dest, "#!/bin/sh\necho husky\n")
        _githooks.install(self.root)
        with open(dest, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("husky", body)
        self.assertNotIn(_githooks.SENTINEL, body)

    def test_uninstall_removes_only_own_dropin_entry(self):
        # ADR-0014: uninstall() removes ONLY this plugin's own drop-in
        # `<plugin>.path` entry -- never the shared, host-neutral shim file,
        # which a sibling plugin may still depend on. Leaving the (now
        # empty) drop-in dir behind is the fail-closed contract working as
        # designed, not a bug -- see TestDropInFailClosed below.
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        plugin = _githooks._plugin_name()
        entry = _githooks._path_entry_file(dropin, plugin)
        self.assertTrue(os.path.isfile(entry))
        actions = _githooks.uninstall(self.root)
        self.assertIn(f"{plugin}.path: removed", actions)
        self.assertFalse(os.path.isfile(entry))
        for phase in ("pre-commit", "pre-push"):
            self.assertTrue(os.path.isfile(os.path.join(self._hooks_dir(), phase)),
                            f"{phase} shim must survive uninstall of a single plugin")


class TestInstallSkipsReprobeWhenCurrent(_GitFixture):
    """performance-002 (#194): a second install() call for the SAME repo, with
    nothing changed, must skip the git-config/rev-parse re-probe entirely — the
    cheap on-disk cache proves the hooks are already current without spawning
    git at all. This is the semantic property the acceptance criteria asks for:
    a SPECIFIC re-probe skipped, not a raw platform-varying spawn count."""

    def _hooks_dir(self):
        return os.path.join(self.root, ".git", "hooks")

    def test_second_call_makes_zero_git_hooks_dir_probe_calls(self):
        # First call: genuine cold install — the probe (_git) legitimately runs.
        first_calls = []
        orig = _githooks._git

        def spy1(args, cwd):
            first_calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy1
        try:
            _githooks.install(self.root)
        finally:
            _githooks._git = orig
        self.assertTrue(first_calls, "cold install must resolve hooks_dir via git")

        # Second call against the SAME repo, nothing changed: the cached
        # hooks_dir + up-to-date shim check must short-circuit BEFORE hooks_dir()
        # ever calls _git — zero git-hooks-dir-probe spawns this time.
        second_calls = []

        def spy2(args, cwd):
            second_calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy2
        try:
            result = _githooks.install(self.root)
        finally:
            _githooks._git = orig
        self.assertEqual(result, [])
        self.assertEqual(second_calls, [],
                         "install() must skip the hooks_dir git-config/rev-parse "
                         "re-probe when the cached hooks are already current")

    def test_cache_miss_falls_through_to_full_probe(self):
        # A cache-miss (nothing installed yet, no cache file) must still fully
        # resolve and install via the real git-based probe — the fast path
        # never substitutes for a genuine cold install.
        cache_file = os.path.join(self.root, ".git", _githooks._HOOKSDIR_CACHE_NAME)
        self.assertFalse(os.path.isfile(cache_file))
        actions = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", actions)
        self.assertIn("pre-push: installed", actions)
        self.assertTrue(os.path.isfile(cache_file),
                        "a successful resolution must persist the hooks_dir cache")

    def test_stale_cached_hooks_dir_falls_through(self):
        # A cache file naming a directory that no longer exists must be treated
        # as a miss (never trusted blindly).
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        cache_file = os.path.join(self.root, ".git", _githooks._HOOKSDIR_CACHE_NAME)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(os.path.join(self.root, "_nonexistent_hooks_dir") + "\n")
        actions = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", actions)
        for phase in ("pre-commit", "pre-push"):
            self.assertTrue(os.path.isfile(os.path.join(self._hooks_dir(), phase)))

    def test_mismatched_enforcer_path_refreshes_dropin_entry_not_the_shim(self):
        # ADR-0014: the shim is host-neutral (it depends only on the shared
        # drop-in dir, never on this plugin's own enforcer path), so a plugin
        # update moving the install dir no longer requires rewriting the
        # SHIM file itself -- _hooks_current() correctly still reports
        # "current" for the shim (the fast path may fire), but install()
        # unconditionally refreshes THIS plugin's own `<plugin>.path` entry
        # every call regardless, so a version-bumped enforcer path is never
        # left stale.
        _githooks.install(self.root)  # writes the cache + the real enforcer path
        dropin = _githooks._dropin_dir(self.root)
        plugin = _githooks._plugin_name()
        entry = _githooks._path_entry_file(dropin, plugin)
        with open(entry, encoding="utf-8") as f:
            self.assertNotIn("/moved/enforcer.py", f.read())
        with mock.patch.object(_githooks, "_enforcer_path", return_value="/moved/enforcer.py"):
            actions = _githooks.install(self.root)
        self.assertEqual(actions, [],
                         "the shim file itself must NOT be rewritten for an enforcer-path-only change")
        with open(entry, encoding="utf-8") as f:
            self.assertIn("/moved/enforcer.py", f.read(),
                         "this plugin's own drop-in entry must self-heal every call")

    # ------------------------------------------------------------------
    # CRITICAL regression (security review, post-#194): a LOCAL core.hooksPath
    # change after a default-location install must NEVER be skipped past. The
    # realistic trigger is the user later adopting husky / pre-commit-
    # framework, which sets core.hooksPath in .git/config.
    # ------------------------------------------------------------------

    def test_local_hooks_path_added_after_install_is_not_skipped(self):
        # Cold install at the default location.
        first = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", first)
        default_dir = self._hooks_dir()
        for phase in ("pre-commit", "pre-push"):
            self.assertTrue(os.path.isfile(os.path.join(default_dir, phase)))

        # The user (or a tool like husky) now points core.hooksPath at a new,
        # repo-local directory.
        custom_dir = os.path.join(self.root, "customhooks")
        _git(["config", "core.hooksPath", "customhooks"], self.root)

        # Re-install MUST resolve into the NEW location — never silently skip
        # past it because the OLD (.git/hooks) shims are still "current".
        second = _githooks.install(self.root)
        self.assertNotEqual(second, [],
                            "a local core.hooksPath change must never be skipped as a no-op")
        for phase in ("pre-commit", "pre-push"):
            dest = os.path.join(custom_dir, phase)
            self.assertTrue(os.path.isfile(dest),
                            f"{phase} must be installed into the NEW hooksPath dir")
            with open(dest, encoding="utf-8") as f:
                self.assertIn(_githooks.SENTINEL, f.read())

    def test_local_hooks_path_removed_after_install_falls_back_to_default(self):
        # Symmetric case: install with a custom hooksPath already set, then
        # unset it — re-install must land back in the default .git/hooks, not
        # be skipped because SOME cached location happened to be current.
        custom_dir = os.path.join(self.root, "customhooks")
        _git(["config", "core.hooksPath", "customhooks"], self.root)
        first = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", first)
        for phase in ("pre-commit", "pre-push"):
            self.assertTrue(os.path.isfile(os.path.join(custom_dir, phase)))

        _git(["config", "--unset", "core.hooksPath"], self.root)

        second = _githooks.install(self.root)
        self.assertNotEqual(second, [],
                            "unsetting a local core.hooksPath must never be skipped as a no-op")
        default_dir = self._hooks_dir()
        for phase in ("pre-commit", "pre-push"):
            dest = os.path.join(default_dir, phase)
            self.assertTrue(os.path.isfile(dest),
                            f"{phase} must be (re)installed into the DEFAULT hooks dir")
            with open(dest, encoding="utf-8") as f:
                self.assertIn(_githooks.SENTINEL, f.read())

    def test_confirmed_no_local_hooks_path_true_when_config_silent(self):
        # Direct unit coverage of the confirmation helper itself: a bare repo
        # with no hooksPath key anywhere in .git/config confirms absent.
        self.assertTrue(_githooks._confirmed_no_local_hooks_path(self.root))

    def test_confirmed_no_local_hooks_path_false_when_set(self):
        _git(["config", "core.hooksPath", "customhooks"], self.root)
        self.assertFalse(_githooks._confirmed_no_local_hooks_path(self.root))

    def test_confirmed_no_local_hooks_path_false_on_include_directive(self):
        # An [include] directive could pull in a hooksPath from elsewhere —
        # our grammar-free substring scan doesn't follow it, so it must fail
        # SAFE (treat as "not confirmed absent"), never silently ignore it.
        cfg = os.path.join(self.root, ".git", "config")
        with open(cfg, "a", encoding="utf-8") as f:
            f.write("[include]\n\tpath = ../shared.gitconfig\n")
        self.assertFalse(_githooks._confirmed_no_local_hooks_path(self.root))

    # ------------------------------------------------------------------
    # HIGH regression (re-review): git's config grammar honors a variable on
    # the SAME line as its section header — `[core] hooksPath = x`,
    # `[core]hooksPath=x`, `[CORE]HooksPath=x` are all valid, real-git-honored
    # spellings a hand-rolled line-oriented section/key parser can miss. The
    # grammar-free substring scan must catch every one of these regardless.
    # ------------------------------------------------------------------

    def _append_raw_config(self, text):
        cfg = os.path.join(self.root, ".git", "config")
        with open(cfg, "a", encoding="utf-8") as f:
            f.write(text)

    def test_confirmed_no_local_hooks_path_false_on_same_line_spaced(self):
        self._append_raw_config("[core] hooksPath = customhooks\n")
        self.assertFalse(_githooks._confirmed_no_local_hooks_path(self.root))

    def test_confirmed_no_local_hooks_path_false_on_same_line_no_space(self):
        self._append_raw_config("[core]hooksPath=customhooks\n")
        self.assertFalse(_githooks._confirmed_no_local_hooks_path(self.root))

    def test_confirmed_no_local_hooks_path_false_on_upper_section_and_key(self):
        self._append_raw_config("[CORE]HooksPath=customhooks\n")
        self.assertFalse(_githooks._confirmed_no_local_hooks_path(self.root))

    def test_same_line_hooks_path_is_not_skipped_end_to_end(self):
        # End-to-end proof (not just the unit-level confirmation helper): a
        # cold install, then a SAME-LINE hooksPath spelling written directly
        # into .git/config (the same-line form real `git config` itself does
        # not produce, but real git STILL HONORS when reading — verified by
        # the sanity assertion below), then re-install must land in the
        # custom dir, never be skipped as a no-op.
        first = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", first)

        custom_dir = os.path.join(self.root, "customhooks")
        os.makedirs(custom_dir, exist_ok=True)
        self._append_raw_config("[core] hooksPath = customhooks\n")

        # Sanity: real git actually honors this same-line spelling (confirms
        # the repro is real, not an artifact of our own parsing).
        cfg_check = _git(["config", "--get", "core.hooksPath"], self.root)
        self.assertEqual(cfg_check.stdout.strip(), "customhooks",
                         "real git must honor the same-line hooksPath spelling "
                         "for this regression to be meaningful")

        second = _githooks.install(self.root)
        self.assertNotEqual(second, [],
                            "a same-line hooksPath spelling must never be skipped as a no-op")
        for phase in ("pre-commit", "pre-push"):
            dest = os.path.join(custom_dir, phase)
            self.assertTrue(os.path.isfile(dest),
                            f"{phase} must be installed into the NEW (same-line-configured) dir")
            with open(dest, encoding="utf-8") as f:
                self.assertIn(_githooks.SENTINEL, f.read())

    def test_cached_custom_hooks_path_is_never_fast_pathed(self):
        # Even if the shims at a CACHED custom hooksPath are still current and
        # no local override is newly detected, a cached hooks_dir that is not
        # the DEFAULT location must always re-confirm via the real probe —
        # never trust a cached custom path blindly.
        custom_dir = os.path.join(self.root, "customhooks")
        _git(["config", "core.hooksPath", "customhooks"], self.root)
        _githooks.install(self.root)  # writes cache pointing at customhooks

        calls = []
        orig = _githooks._git

        def spy(args, cwd):
            calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy
        try:
            result = _githooks.install(self.root)
        finally:
            _githooks._git = orig
        self.assertEqual(result, [])  # still a no-op...
        self.assertTrue(calls, "a cached CUSTOM hooksPath must always re-confirm via git, "
                              "never take the zero-spawn fast path")


class TestDropInSharedDir(_GitFixture):
    """ADR-0014 / #265 (AC-7): the drop-in dir the shim reads from resolves to
    the repo's git COMMON dir, so every linked worktree of a repo shares the
    SAME `.git/codearbiter-hooksd/` -- never a per-worktree copy, which would
    defeat the whole cross-host purpose (a shim installed from one worktree
    would never see an entry another worktree/host wrote)."""

    def test_linked_worktree_shares_the_same_dropin_dir_as_main(self):
        # realpath BOTH sides before comparing (portability, not a weakened
        # assertion): on macOS `/var` is itself a symlink to `/private/var`,
        # and `tempfile`-issued paths come back unresolved while git
        # internally canonicalizes the absolute paths IT writes (the linked
        # worktree's `gitdir:` pointer) -- so main_dropin and wt_dropin can
        # legitimately differ as STRINGS while naming the exact same
        # directory (the OS resolves `/var` <-> `/private/var` transparently
        # for every open/stat/makedirs call either side of the real shim
        # would ever make -- see the production-benign analysis in the class
        # docstring / commit note). realpath collapses that representational
        # difference without weakening what this test actually proves: main
        # and worktree resolve to the SAME directory.
        wt_dir = os.path.join(os.path.dirname(self.root), "wt")
        _git(["worktree", "add", "-q", "-b", "feat/wt", wt_dir], self.root)
        main_dropin = _githooks._dropin_dir(self.root)
        wt_dropin = _githooks._dropin_dir(wt_dir)
        self.assertIsNotNone(main_dropin)
        self.assertIsNotNone(wt_dropin)
        self.assertEqual(os.path.normcase(os.path.realpath(main_dropin)),
                         os.path.normcase(os.path.realpath(wt_dropin)))

    def test_git_common_dir_resolves_without_a_git_spawn_for_the_main_repo(self):
        # The common (non-worktree) case must be resolvable purely from the
        # filesystem -- required so the performance-002 fast path (see
        # TestInstallSkipsReprobeWhenCurrent) still makes zero git spawns.
        calls = []
        orig = _githooks._git

        def spy(args, cwd):
            calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy
        try:
            common = _githooks._git_common_dir(self.root)
        finally:
            _githooks._git = orig
        self.assertIsNotNone(common)
        self.assertEqual(calls, [], "the main-repo case must resolve with zero git spawns")


class TestDropInMultiPluginFailClosed(_GitFixture):
    """AC-7 (#265): two plugins registered in the shared drop-in dir -- the
    shim resolves through whichever entry is actually live, independent of
    write order, and BLOCKS (fails closed) when NOTHING resolves."""

    def _write_entry(self, dropin, name, target):
        os.makedirs(dropin, exist_ok=True)
        with open(
                os.path.join(dropin, f"{name}.path"), "w",
                encoding="utf-8", newline="\n") as f:
            f.write(target + "\n")

    def _stage(self, name, content):
        self._write(os.path.join(self.root, name), content)
        _git(["add", name], self.root)

    def _probe_enforcer(self, name, marker, returncode=0, read_stdin=False):
        path = os.path.join(self.root, name)
        source = "import pathlib, sys\n"
        if read_stdin:
            source += f"payload = sys.stdin.read(); pathlib.Path({marker!r}).write_text(payload, encoding='utf-8')\n"
        else:
            source += f"pathlib.Path({marker!r}).write_text('ran', encoding='utf-8')\n"
        source += f"raise SystemExit({returncode})\n"
        self._write(path, source)
        return _githooks._shell_path(path)

    def test_every_live_version_runs_and_any_block_wins(self):
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        os.remove(os.path.join(dropin, "ca.path"))
        allow_marker = os.path.join(self.root, "allow.marker")
        block_marker = os.path.join(self.root, "block.marker")
        self._write_entry(dropin, "aaa-older", self._probe_enforcer(
            "older-allow.py", allow_marker, returncode=0))
        self._write_entry(dropin, "zzz-newer", self._probe_enforcer(
            "newer-block.py", block_marker, returncode=9))
        hook = os.path.join(self.root, ".git", "hooks", "pre-commit")
        result = _sh(["sh", hook], self.root)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertTrue(os.path.isfile(allow_marker), "older live enforcer did not run")
        self.assertTrue(os.path.isfile(block_marker), "newer live enforcer did not run")

    def test_pre_push_input_is_replayed_to_every_live_enforcer(self):
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        first = os.path.join(self.root, "first.input")
        second = os.path.join(self.root, "second.input")
        self._write_entry(dropin, "ca", self._probe_enforcer(
            "first.py", first, read_stdin=True))
        self._write_entry(dropin, "ca-pi", self._probe_enforcer(
            "second.py", second, read_stdin=True))
        payload = "refs/heads/feat/x " + "1" * 40 + " refs/heads/feat/x " + "0" * 40 + "\n"
        hook = os.path.join(self.root, ".git", "hooks", "pre-push")
        result = _sh(["sh", hook], self.root, input=payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (first, second):
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), payload)

    def test_legacy_semver_registry_entry_is_never_executed(self):
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        stale_marker = os.path.join(self.root, "stale.marker")
        live_marker = os.path.join(self.root, "live.marker")
        self._write_entry(dropin, "0.3.0", self._probe_enforcer(
            "stale.py", stale_marker, returncode=7))
        self._write_entry(dropin, "ca", self._probe_enforcer(
            "live.py", live_marker, returncode=0))
        hook = os.path.join(self.root, ".git", "hooks", "pre-commit")
        result = _sh(["sh", hook], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(stale_marker), "version-derived stale entry executed")
        self.assertTrue(os.path.isfile(live_marker))

    def test_identity_bundle_with_extra_record_fails_closed(self):
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=None), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        marker = os.path.join(self.root, "extra-record.marker")
        self._write_entry(dropin, "ca", self._probe_enforcer("allow.py", marker))
        identity = "\n".join((
            _githooks._shell_path(sys.executable),
            _githooks._shell_path(os.path.realpath(shutil.which("git"))),
            "ca-pi",
            "unexpected-fourth-record",
        )) + "\n"
        with open(
                _githooks._identity_file(dropin), "w",
                encoding="utf-8", newline="\n") as f:
            f.write(identity)

        result = _sh([shutil.which("sh"), os.path.join(
            self.root, ".git", "hooks", "pre-commit")], self.root)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(marker), "malformed identity reached an enforcer")

    def test_identity_bundle_with_unterminated_extra_record_fails_closed(self):
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=None), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        marker = os.path.join(self.root, "unterminated-extra.marker")
        self._write_entry(dropin, "ca", self._probe_enforcer("allow.py", marker))
        identity = "\n".join((
            _githooks._shell_path(sys.executable),
            _githooks._shell_path(os.path.realpath(shutil.which("git"))),
            "ca-pi",
            "unexpected-fourth-record",
        ))
        with open(
                _githooks._identity_file(dropin), "w",
                encoding="utf-8", newline="\n") as f:
            f.write(identity)

        result = _sh([shutil.which("sh"), os.path.join(
            self.root, ".git", "hooks", "pre-commit")], self.root)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(marker), "unterminated extra record reached an enforcer")

    def test_broken_identity_symlink_fails_before_path_fallback(self):
        with mock.patch.object(
                _githooks, "trusted_git_executable", return_value=None), \
                mock.patch.object(
                    _githooks, "trusted_python_executable", return_value=None):
            _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        identity = _githooks._identity_file(dropin)
        os.symlink(os.path.join(dropin, "missing-identity"), identity)
        dummy = os.path.join(self.root, "dummy-enforcer.py")
        self._write(dummy, "# never parsed by the poisoned interpreter\n")
        self._write_entry(dropin, "ca", _githooks._shell_path(dummy))

        marker = _githooks._shell_path(os.path.join(self.root, "path-fallback.marker"))
        fake_bin = os.path.join(self.root, "fake-bin")
        fake_python = os.path.join(fake_bin, "python3")
        self._write(fake_python, "#!/bin/sh\nprintf ran > " + marker + "\nexit 0\n")
        os.chmod(fake_python, 0o755)
        env = dict(os.environ)
        env["PATH"] = fake_bin

        result = _sh([shutil.which("sh"), os.path.join(
            self.root, ".git", "hooks", "pre-commit")], self.root, env=env)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(marker), "broken identity fell back to PATH")

    def test_survivor_plugin_still_enforces_when_the_other_is_uninstalled(self):
        # AC-7a: this plugin's own install() writes a REAL, resolvable entry.
        # A second plugin is ALSO registered but its enforcer is gone (as if
        # uninstalled) -- the shim must still resolve to the survivor and
        # enforcement must still fire (a direct commit to main is BLOCKED).
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        self._write_entry(dropin, "other-plugin",
                          os.path.join(self.root, "_removed", "git-enforce.py"))
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "git commit -m x"], self.root)
        self.assertNotEqual(res.returncode, 0, res.stderr)
        self.assertIn("H-01", res.stderr + res.stdout)

    def test_survivor_enforces_regardless_of_which_entry_was_written_last(self):
        # Symmetric ordering: write the DEAD entry first, the REAL one last --
        # the loop must not stop at (or prefer) whichever was written most
        # recently; every entry is tried until one resolves.
        dropin = _githooks._dropin_dir(self.root)
        self._write_entry(dropin, "aaa-dead",
                          os.path.join(self.root, "_removed", "git-enforce.py"))
        _githooks.install(self.root)  # writes THIS plugin's real entry after
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "git commit -m x"], self.root)
        self.assertNotEqual(res.returncode, 0, res.stderr)
        self.assertIn("H-01", res.stderr + res.stdout)

    def test_zero_resolvable_enforcers_fails_closed_not_open(self):
        # AC-7b: every registered entry points at a missing file (or the dir
        # is emptied entirely) -- the shim must BLOCK (non-zero exit), never
        # silently allow (exit 0) the way the old single-embedded-path shim
        # did on its own staleness.
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        for name in os.listdir(dropin):
            if name.endswith(".path"):
                os.remove(os.path.join(dropin, name))
        self.assertEqual([n for n in os.listdir(dropin) if n.endswith(".path")], [])
        _git(["checkout", "-q", "-b", "feat/x"], self.root)  # not itself a protected branch
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "git commit -m x"], self.root)
        self.assertNotEqual(res.returncode, 0,
                           "an empty drop-in dir must fail CLOSED, not silently allow")
        log = _git(["rev-list", "--all", "--count"], self.root, check=False)
        self.assertEqual(log.stdout.strip(), "0", "nothing must be committed on a fail-closed block")

    def test_dropin_dir_missing_entirely_fails_closed(self):
        # The un-expanded "$D/*.path" glob-literal case: the drop-in dir
        # itself doesn't exist at all (not merely empty).
        _githooks.install(self.root)
        dropin = _githooks._dropin_dir(self.root)
        shutil.rmtree(dropin)
        _git(["checkout", "-q", "-b", "feat/y"], self.root)
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "git commit -m x"], self.root)
        self.assertNotEqual(res.returncode, 0,
                           "a missing drop-in dir must fail CLOSED, not silently allow")


class TestPreCommitEnforce(_GitFixture):
    def _stage(self, name, content):
        self._write(os.path.join(self.root, name), content)
        _git(["add", name], self.root)

    def test_direct_commit_to_main_is_blocked(self):
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_variable_indirection_commit_is_blocked_at_git_layer(self):
        # The #161 bypass: build `git commit` from shell vars. pre-bash never sees
        # a git token, but the git hook fires on the real operation. Run a REAL
        # indirected commit with our hook installed and assert it aborts.
        _githooks.install(self.root)
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "g=git; c=commit; $g $c -m sneaky"], self.root)
        self.assertNotEqual(res.returncode, 0, "indirected commit should have been blocked")
        self.assertIn("H-01", res.stderr + res.stdout)
        # nothing committed
        log = _git(["rev-list", "--all", "--count"], self.root, check=False)
        self.assertEqual(log.stdout.strip(), "0")

    def test_feature_branch_commit_is_allowed(self):
        _git(["checkout", "-q", "-b", "feat/x"], self.root)
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_crypto_commit_without_marker_is_blocked(self):
        _git(["checkout", "-q", "-b", "feat/c"], self.root)
        self._stage("c.js", 'const h = crypto.createHash("md5");\n')
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-09b", res.stderr)

    def test_dormant_repo_is_noop(self):
        self._disable_arbiter()
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 0, res.stderr)

    # coverage-002 (#193): H-10b secret-only block, H-14 migration block, and
    # both pre_commit() fail-closed git-read branches — previously untested.

    def test_secret_only_commit_without_marker_is_blocked_h10b_not_h09b(self):
        _git(["checkout", "-q", "-b", "feat/s"], self.root)
        # No crypto/TLS token here (no hashing or signing call) — SECRET_RE only.
        # Built via concatenation (not a literal line in this source file) so
        # this repo's OWN commit-gate doesn't flag test_git_hooks.py's own diff
        # as introducing a secret — the fixture file written to disk still
        # carries the real literal line SECRET_RE must match.
        key_line = "api" + "_key" + ' = "' + "abcd1234efgh5678" + '"\n'
        self._stage("s.py", key_line)
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-10b", res.stderr)
        self.assertNotIn("H-09b", res.stderr)

    def test_migration_without_gate_pass_is_blocked_h14(self):
        _git(["checkout", "-q", "-b", "feat/m"], self.root)
        self._stage("db/migrations/0001_init.sql", "CREATE TABLE t (id int);\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-14", res.stderr)

    def test_cached_diff_read_failure_fails_closed(self):
        # Point PATH at a nonexistent dir so EVERY git spawn in pre_commit()
        # fails, including the very first (current_branch) — the H-01 fail-closed
        # branch fires
        # before either the H-09b/H-10b or H-14 read site is reached. Kept as
        # end-to-end evidence that an entirely unreadable git still fails
        # CLOSED, not open; test_git_enforce_lib.py below isolates the two
        # DISTINCT pre_commit() read-failure branches (cached_added_lines vs
        # cached_names) that coverage-002 calls out, via direct monkeypatching
        # (subprocess-level PATH-stripping can't differentiate the two, since
        # both read sites fail identically once git itself is unspawnable).
        _git(["checkout", "-q", "-b", "feat/g"], self.root)
        self._stage("f.txt", "x\n")
        # PATH is SET to a nonexistent dir (not unset): POSIX execvp falls back
        # to its default /usr/bin:/bin when PATH is absent and would still find
        # git, defeating the fail-closed premise on non-Windows CI.
        env = {k: v for k, v in os.environ.items() if k.upper() != "PATHEXT"}
        env["PATH"] = os.path.join(self.root, "_nonexistent_bin")
        res = _sh([sys.executable, ENFORCE, "pre-commit"], self.root, env=env)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("failing closed", res.stderr)


class TestPreCommitFailClosedBranches(_GitFixture):
    """coverage-002 (#193): isolate pre_commit()'s two DISTINCT git-read
    fail-closed branches — cached_added_lines() -> None (H-09b/H-10b) and
    cached_names() -> None (H-14) — by calling pre_commit() in-process with one
    read function monkeypatched to fail while the other succeeds normally. A
    subprocess-level git-unreadable test (see test_cached_diff_read_failure_
    fails_closed above) can't isolate these: once git itself can't be spawned,
    BOTH reads fail identically and only ever exercises the first one
    (current_branch, H-01)."""

    def setUp(self):
        super().setUp()
        _git(["checkout", "-q", "-b", "feat/branches"], self.root)
        self._write(os.path.join(self.root, "f.txt"), "x\n")
        _git(["add", "f.txt"], self.root)

    def test_added_lines_read_failure_fails_closed_h09b(self):
        ge = _load_git_enforce()
        ge.cached_added_lines = lambda cwd: None
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                ge.pre_commit(self.root)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("H-09b", buf.getvalue())
        self.assertIn("failing closed", buf.getvalue())

    def test_staged_names_read_failure_fails_closed_h14(self):
        ge = _load_git_enforce()
        ge.cached_added_lines = lambda cwd: []  # no sensitive content -> pass H-09b/H-10b
        ge.cached_names = lambda cwd: None
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                ge.pre_commit(self.root)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("H-14", buf.getvalue())
        self.assertIn("failing closed", buf.getvalue())


class TestPrePushEnforce(_GitFixture):
    def test_push_to_protected_branch_is_blocked(self):
        line = "refs/heads/feat/x abc123 refs/heads/main def456\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_feature_fast_forward_push_is_allowed(self):
        _git(["checkout", "-q", "-b", "feat/x"], self.root)
        self._write(os.path.join(self.root, "f.txt"), "x\n")
        _git(["add", "f.txt"], self.root)
        _git(["commit", "-q", "-m", "ok", "--no-verify"], self.root)
        sha = _git(["rev-parse", "HEAD"], self.root).stdout.strip()
        zero = "0" * 40
        line = f"refs/heads/feat/x {sha} refs/heads/feat/x {zero}\n"  # create -> no force
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 0, res.stderr)

    # coverage-001 (#193): H-02 (force / non-fast-forward) is otherwise
    # completely untested — the two cases above only exercise H-01 and a
    # create-ref push (which short-circuits H-02 via the all-zero remote sha).

    def _commit(self, name, content, msg):
        self._write(os.path.join(self.root, name), content)
        _git(["add", name], self.root)
        _git(["commit", "-q", "-m", msg, "--no-verify"], self.root)
        return _git(["rev-parse", "HEAD"], self.root).stdout.strip()

    def test_non_fast_forward_push_is_blocked_h02(self):
        # A real non-fast-forward: local and remote diverge from a common base,
        # neither a descendant of the other, both refs non-zero (not a
        # create/delete) — merge-base --is-ancestor(remote, local) is False.
        base = self._commit("base.txt", "base\n", "base")
        local_sha = self._commit("local.txt", "local\n", "local")
        _git(["checkout", "-q", "-b", "alt", base], self.root)
        remote_sha = self._commit("remote.txt", "remote\n", "remote")
        _git(["checkout", "-q", "main"], self.root)
        line = f"refs/heads/feat/x {local_sha} refs/heads/feat/x {remote_sha}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-02", res.stderr)

    def test_genuine_fast_forward_update_is_allowed_h02(self):
        # A true (non-create) fast-forward: remote_sha IS an ancestor of
        # local_sha, both refs non-zero.
        remote_sha = self._commit("base2.txt", "base\n", "base2")
        local_sha = self._commit("child.txt", "child\n", "child")
        line = f"refs/heads/feat/y {local_sha} refs/heads/feat/y {remote_sha}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_unresolvable_merge_base_fails_closed_h02(self):
        # remote_sha names a commit this repo has never heard of — `git
        # merge-base --is-ancestor` errors (unknown revision), which must
        # resolve CLOSED (block), not silently pass as "not force".
        local_sha = self._commit("f3.txt", "x\n", "local3")
        bogus_remote = "f" * 40
        line = f"refs/heads/feat/z {local_sha} refs/heads/feat/z {bogus_remote}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-02", res.stderr)


if __name__ == "__main__":
    unittest.main()
