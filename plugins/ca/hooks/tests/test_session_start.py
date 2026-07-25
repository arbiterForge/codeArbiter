"""Tests for session-start.py: has_source(), CONFIRM_RE, task counting."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module under test without executing main().
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "session_start",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "session-start.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

has_source = _mod.has_source
CONFIRM_RE = _mod.CONFIRM_RE
should_emit_briefing = _mod.should_emit_briefing
briefing_mode = _mod.briefing_mode
standup_marker_path = _mod.standup_marker_path
local_date_iso = _mod.local_date_iso
write_standup_marker = _mod.write_standup_marker
provenance_drift_line = _mod.provenance_drift_line

from _helpers import durable_plugin_copy, isolate_user_state, release_user_state  # noqa: E402


# Issue #442: this module writes user-GLOBAL state - the statusline pin in
# `~/.claude/settings.json`, and/or the `~/.codearbiter/` ledger and update
# cache. Running the suite used to do that to the DEVELOPER'S REAL HOME: the
# statusline pin was repointed at whatever plugin root the test process
# resolved (it broke the maintainer's statusline three times in one day), and
# `~/.codearbiter/` gained a ledger, its lock, five session shards and an
# update cache. CI never noticed, because a fresh runner has no pre-existing
# settings to clobber.
#
# The fixture is module-level rather than per-class ON PURPOSE. The leak is
# module-wide, this file has many test classes, and a per-class `setUp` is one
# forgotten override away from regressing - while `setUpModule` covers every
# class added later for free. `.github/scripts/test_suite_hermeticity.py` is the
# backstop that fails if any suite writes outside its temp dirs.
def setUpModule():
    global _USER_STATE
    _USER_STATE = isolate_user_state()


def tearDownModule():
    release_user_state(_USER_STATE)


# The real plugin payload root (parent of the hooks/ dir holding session-start.py).
_REAL_PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(_mod.__file__)))

# A ca-owned pin left behind by an OLD plugin-cache version — the genuine
# stale-pin condition the heal exists to repair.
STALE_CACHE_PIN = (
    '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.0.1'
    '\\hooks\\statusline.py"')


class TestHasSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_true_when_source_files_exist(self):
        # A .py file that isn't in the exclusion set counts as source.
        src = os.path.join(self.root, "src")
        os.makedirs(src)
        with open(os.path.join(src, "app.py"), "w") as f:
            f.write("# source\n")
        self.assertTrue(has_source(self.root))

    def test_returns_false_for_greenfield_repo(self):
        # Empty repo (only a .git dir) — nothing counts as source.
        git_dir = os.path.join(self.root, ".git")
        os.makedirs(git_dir)
        self.assertFalse(has_source(self.root))

    def test_excluded_top_dirs_not_counted(self):
        # Files inside excluded top-level dirs (.git, .codearbiter, .claude,
        # legacy) must NOT cause has_source to return True.
        for excl in (".git", ".codearbiter", ".claude", "legacy"):
            os.makedirs(os.path.join(self.root, excl), exist_ok=True)
            with open(os.path.join(self.root, excl, "file.py"), "w") as f:
                f.write("# excluded\n")
        self.assertFalse(has_source(self.root))

    def test_excluded_file_names_not_counted(self):
        # Scaffold-only filenames (README.md, LICENSE, etc.) don't count.
        for fn in ("README.md", "LICENSE", ".gitignore", "AGENTS.md",
                   "CLAUDE.md", ".gitmodules"):
            with open(os.path.join(self.root, fn), "w") as f:
                f.write("# excluded\n")
        self.assertFalse(has_source(self.root))

    def test_single_source_file_at_root_is_enough(self):
        with open(os.path.join(self.root, "main.py"), "w") as f:
            f.write("# main\n")
        self.assertTrue(has_source(self.root))

    def test_nested_source_file_is_found(self):
        nested = os.path.join(self.root, "pkg", "sub")
        os.makedirs(nested)
        with open(os.path.join(nested, "helper.py"), "w") as f:
            f.write("# helper\n")
        self.assertTrue(has_source(self.root))


class TestConfirmRe(unittest.TestCase):
    """CONFIRM_RE must match CONFIRM-NN tokens (any number of digits)."""

    def test_finds_two_confirm_markers(self):
        text = "Need answer on [CONFIRM-01] before proceeding.\n[CONFIRM-02] is also open.\n"
        matches = CONFIRM_RE.findall(text)
        self.assertEqual(len(matches), 2)

    def test_finds_no_confirm_markers_in_clean_text(self):
        text = "All questions resolved.\n"
        matches = CONFIRM_RE.findall(text)
        self.assertEqual(len(matches), 0)

    def test_multiple_confirms_on_same_line(self):
        text = "[CONFIRM-01] and [CONFIRM-02] both block this task."
        matches = CONFIRM_RE.findall(text)
        self.assertEqual(len(matches), 2)

    def test_confirm_with_high_number(self):
        text = "See [CONFIRM-99] for details."
        matches = CONFIRM_RE.findall(text)
        self.assertEqual(len(matches), 1)


class TestTaskCount(unittest.TestCase):
    """main() now delegates the in-flight count to _taskboardlib.count_in_flight
    (done items excluded). Bind the REAL shared helper, not a reimplementation."""

    def setUp(self):
        import _taskboardlib
        self._count_tasks = _taskboardlib.count_in_flight

    def test_zero_tasks(self):
        text = "# open-tasks\n\nNo tasks yet.\n"
        self.assertEqual(self._count_tasks(text), 0)

    def test_single_task(self):
        text = "# open-tasks\n- Implement foo\n"
        self.assertEqual(self._count_tasks(text), 1)

    def test_multiple_tasks(self):
        text = "# open-tasks\n- Task A\n- Task B\n- Task C\n"
        self.assertEqual(self._count_tasks(text), 3)

    def test_indented_lines_not_counted(self):
        # Only lines that START with "- " are tasks; indented sub-items are not.
        text = "# open-tasks\n- Task A\n  - sub-item\n- Task B\n"
        self.assertEqual(self._count_tasks(text), 2)

    def test_done_items_excluded(self):
        # The bug this feature fixes: '- [x]' done items must NOT inflate the count.
        text = "- [ ] a.b.0001 - A\n- [~] a.b.0002 - B\n- [x] a.b.0003 - C\n"
        self.assertEqual(self._count_tasks(text), 2)


class TestMalformedFrontmatter(unittest.TestCase):
    """An unclosed frontmatter must produce a stderr breadcrumb and not activate."""

    def test_malformed_frontmatter_dormant(self):
        import io
        from _hooklib import frontmatter_enabled

        with tempfile.TemporaryDirectory() as tmp:
            ctx = os.path.join(tmp, "CONTEXT.md")
            # Opening "---" with no closing delimiter.
            with open(ctx, "w") as f:
                f.write("---\narbiter: enabled\n# MISSING closing ---\n")
            enabled, malformed = frontmatter_enabled(ctx)
            self.assertFalse(enabled)
            self.assertTrue(malformed)


class TestHealStatuslineWiring(unittest.TestCase):
    """Regression (#fix): SessionStart must self-heal a stale ca-owned statusLine
    pin so a plugin update re-points the absolute path in settings.json instead of
    silently running the old (eventually-broken) version. Drives the real
    wire-statusline.py from the actual plugin root, against a temp settings file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # A DURABLE copy of the real plugin payload — see durable_plugin_copy().
        # (Was the real plugin root; that made the outcome depend on whether the
        # suite was run from a git worktree, once the heal started refusing one.)
        self.plugin = durable_plugin_copy(self._tmp.name)
        self.real_script = os.path.join(self.plugin, "hooks", "statusline.py")
        d = os.path.join(self._tmp.name, ".claude")
        os.makedirs(d)
        self.settings = os.path.join(d, "settings.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, obj):
        import json
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)

    def _read(self):
        import json
        with open(self.settings, encoding="utf-8") as f:
            return json.load(f)

    def test_stale_ours_pin_is_healed(self):
        self._write({"statusLine": {"type": "command",
                     "command": '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.0.1\\hooks\\statusline.py"'}})
        changed = _mod.heal_statusline_wiring(
            self.plugin, settings_path=self.settings, interp="python")
        self.assertTrue(changed)
        cmd = self._read()["statusLine"]["command"]
        self.assertIn(self.real_script, cmd)
        self.assertNotIn("2.0.1", cmd)

    def test_third_party_pin_left_alone(self):
        self._write({"statusLine": {"type": "command", "command": "theirs --x"}})
        changed = _mod.heal_statusline_wiring(
            self.plugin, settings_path=self.settings, interp="python")
        self.assertFalse(changed)
        self.assertEqual(self._read()["statusLine"]["command"], "theirs --x")

    def test_corrupt_settings_does_not_crash(self):
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        # Must degrade silently (return False), never raise — a wiring refresh
        # may not crash session startup.
        self.assertFalse(
            _mod.heal_statusline_wiring(
                self.plugin, settings_path=self.settings, interp="python"))

    def test_absent_settings_is_noop(self):
        missing = os.path.join(self._tmp.name, "nope", "settings.json")
        self.assertFalse(
            _mod.heal_statusline_wiring(
                self.plugin, settings_path=missing, interp="python"))

    def test_loader_failure_returns_false(self):
        # The `loader=` seam exists so a wire-statusline.py that fails to load
        # degrades to a no-op rather than crashing startup. A loader returning
        # None must short-circuit to False without touching settings.json.
        self._write({"statusLine": {"type": "command", "command": "x statusline.py"}})
        self.assertFalse(
            _mod.heal_statusline_wiring(
                self.plugin, settings_path=self.settings, interp="python",
                loader=lambda _p: None))


class TestHealRefusesNonDurableRoot(unittest.TestCase):
    """Found in-session on 2026-07-25, after it broke the maintainer's
    statusline three times in one day.

    `heal_statusline_wiring()` runs on EVERY SessionStart and rewrites the
    GLOBAL `~/.claude/settings.json` to the CURRENT plugin root. When the
    session starts inside a git worktree (subagents routinely run in
    `<repo>/.claude/worktrees/<id>/`) that root is the worktree's own
    `plugins/ca`, so the heal pinned the user's global statusline at a directory
    whose entire purpose is to be pruned:

        "...\\.claude\\worktrees\\wf_58ee3fa6-de1-8\\plugins\\ca\\hooks\\statusline.py"

    Contract: a session rooted in a non-durable checkout is INERT with respect
    to the user's global config — the existing pin is left exactly as it is
    (not healed, not cleared, no error). A genuinely stale pin from a real
    plugin-cache update must still heal, so BOTH directions are proven here."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # One real wire-statusline module, loaded once from the real payload and
        # injected through the `loader=` seam, so `plugin` is free to be any
        # shape at all — including one that does not exist on disk.
        self.ws = _mod._load_wire_statusline(_REAL_PLUGIN)
        self.assertIsNotNone(self.ws, "wire-statusline.py must load")
        d = os.path.join(self._tmp.name, ".claude")
        os.makedirs(d)
        self.settings = os.path.join(d, "settings.json")
        self._write({"statusLine": {"type": "command", "command": STALE_CACHE_PIN}})

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, obj):
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        self.before = self._bytes()

    def _bytes(self):
        with open(self.settings, "rb") as f:
            return f.read()

    def _heal(self, plugin, loader=None):
        return _mod.heal_statusline_wiring(
            plugin, settings_path=self.settings, interp="python",
            loader=loader or (lambda _p: self.ws))

    def _worktree_root(self):
        """The confirmed shape: a Claude Code subagent worktree checkout."""
        return os.path.join(self._tmp.name, "repo", ".claude", "worktrees",
                            "wf_58ee3fa6-de1-8", "plugins", "ca")

    def _durable_root(self):
        """The ordinary shape: an updated plugin-cache install."""
        return os.path.join(self._tmp.name, "home", ".claude", "plugins",
                            "cache", "codearbiter", "ca", "9.9.9")

    # --- proof 1: a worktree-rooted heal changes nothing -------------------

    def test_worktree_root_leaves_settings_byte_identical(self):
        self.assertFalse(self._heal(self._worktree_root()))
        self.assertEqual(self._bytes(), self.before)

    def test_worktree_root_pin_never_appears_in_settings(self):
        self._heal(self._worktree_root())
        with open(self.settings, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("worktrees", raw)
        self.assertEqual(json.loads(raw)["statusLine"]["command"], STALE_CACHE_PIN)

    def test_worktree_root_does_not_repair_an_already_worktree_pin(self):
        # The maintainer's observed corrupted state, re-entered from ANOTHER
        # worktree: leave it alone rather than swap one doomed pin for another.
        # A later session from a durable root is what repairs it.
        pinned = ('"python" "C:\\Users\\me\\repo\\.claude\\worktrees'
                  '\\wf_b7160646-041-2\\plugins\\ca\\hooks\\statusline.py"')
        self._write({"statusLine": {"type": "command", "command": pinned},
                     self.ws.OWNER_KEY: pinned})
        self.assertFalse(self._heal(self._worktree_root()))
        self.assertEqual(self._bytes(), self.before)

    def test_caller_refuses_even_an_unguarded_producer(self):
        # WHY THE CALLER GUARDS TOO. `heal_statusline_wiring` loads
        # wire-statusline.py FROM `plugin` — i.e. out of the very worktree it is
        # about to pin. A worktree cut from a pre-fix branch therefore supplies a
        # pre-fix, UNGUARDED producer, while session-start.py itself may have
        # been loaded from elsewhere (main() honours $CLAUDE_PLUGIN_ROOT
        # independently of where this file came from). The heal must refuse on
        # its own account, not on the loaded module's good behaviour.
        unguarded = _Unguarded(self.ws)
        self.assertFalse(self._heal(self._worktree_root(),
                                    loader=lambda _p: unguarded))
        self.assertEqual(self._bytes(), self.before)
        self.assertFalse(unguarded.refresh_called,
                         "the heal must bail BEFORE reaching the producer")

    # --- proof 2: a stale-but-durable pin still heals ----------------------

    def test_durable_stale_pin_still_heals(self):
        # The feature is NOT disabled: a real plugin-cache update still
        # re-points the pin at the new version's renderer.
        self.assertTrue(self._heal(self._durable_root()))
        cmd = json.loads(self._bytes().decode("utf-8"))["statusLine"]["command"]
        self.assertIn(os.path.join(self._durable_root(), "hooks", "statusline.py"), cmd)
        self.assertNotIn("2.0.1", cmd)

    def test_durable_root_repairs_a_worktree_pin_left_by_the_bug(self):
        # Forward fix: the corruption already on the maintainer's disk self-heals
        # the next time a session starts from a durable root.
        pinned = ('"python" "C:\\Users\\me\\repo\\.claude\\worktrees'
                  '\\wf_b7160646-041-2\\plugins\\ca\\hooks\\statusline.py"')
        self._write({"statusLine": {"type": "command", "command": pinned},
                     self.ws.OWNER_KEY: pinned})
        self.assertTrue(self._heal(self._durable_root()))
        cmd = json.loads(self._bytes().decode("utf-8"))["statusLine"]["command"]
        self.assertNotIn("worktrees", cmd)

    # --- proof 3: a third-party line is still never touched ----------------

    def test_worktree_root_still_never_touches_a_third_party_line(self):
        self._write({"statusLine": {"type": "command", "command": "theirs --x"}})
        self.assertFalse(self._heal(self._worktree_root()))
        self.assertEqual(self._bytes(), self.before)

    def test_durable_root_still_never_touches_a_third_party_line(self):
        # The pre-existing contract, re-proven on the path that DOES write.
        self._write({"statusLine": {"type": "command", "command": "theirs --x"}})
        self.assertFalse(self._heal(self._durable_root()))
        self.assertEqual(self._bytes(), self.before)


class _Unguarded:
    """A stand-in for a PRE-FIX vendored wire-statusline.py: every real function
    except `refresh_if_stale`, which unconditionally rewrites the pin exactly as
    the module did before 2026-07-25."""

    def __init__(self, real):
        self._real = real
        self.refresh_called = False

    def __getattr__(self, name):
        return getattr(self._real, name)

    def refresh_if_stale(self, settings, script_abs, interp):
        self.refresh_called = True
        desired = self._real.build_command(interp, script_abs)
        settings["statusLine"] = self._real.owned_statusline(desired)
        settings[self._real.OWNER_KEY] = desired
        return True


class TestMainHealsBeforeDormantGate(unittest.TestCase):
    """Regression (#fix): the heal must run from main() BEFORE the dormant early
    return, so a plugin update re-points the pin in EVERY session — even a
    non-arbiter (dormant) repo. This is the test that FAILS if the
    `heal_statusline_wiring(plugin)` call is deleted from main(); the direct-call
    tests above would all still pass, leaving the actual fix point unguarded."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # A dormant repo: no .codearbiter/CONTEXT.md -> main() exits early.
        self.repo = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.repo)
        # A fake HOME whose ~/.claude/settings.json carries a stale ca-owned pin.
        self.home = os.path.join(self._tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command",
                       "command": STALE_CACHE_PIN}}, f)
        # A DURABLE copy of the real payload — see durable_plugin_copy().
        self.plugin = durable_plugin_copy(self._tmp.name)
        self.real_script = os.path.join(self.plugin, "hooks", "statusline.py")

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_heals_stale_pin_in_dormant_repo(self):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            # expanduser("~") -> our fake HOME, so settings_path resolves into it;
            # CLAUDE_PLUGIN_ROOT -> the real plugin so statusline.py exists.
            with mock.patch.object(os.path, "expanduser", return_value=self.home), \
                 mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": self.plugin}), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _mod.main()
        finally:
            os.chdir(cwd)
        with open(self.settings, encoding="utf-8") as f:
            cmd = json.load(f)["statusLine"]["command"]
        self.assertIn(self.real_script, cmd)
        self.assertNotIn("2.0.1", cmd)


class TestMainSkipsHealUnderNoStatuslineHost(unittest.TestCase):
    """coverage-004 (#267): the has_statusline gate at main()'s heal call site
    (ADR-0011) must actually be exercised end-to-end under a host with no
    statusline surface (Codex), not merely asserted as a flag value. Drives the
    REAL main() entry — mirrors TestMainHealsBeforeDormantGate's harness
    exactly, except get_host() is patched (#257: main() now resolves via
    _hooklib.get_host(), not a direct hostapi.load_host()) to return a
    has_statusline=False host — and asserts the stale ca-owned pin is left
    UNTOUCHED (the heal never runs) while the rest of startup (the dormant
    early-exit) still completes normally."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # A dormant repo: no .codearbiter/CONTEXT.md -> main() exits early.
        self.repo = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.repo)
        # A fake HOME whose ~/.claude/settings.json carries a stale ca-owned pin.
        self.home = os.path.join(self._tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        self.stale_command = STALE_CACHE_PIN
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command",
                       "command": self.stale_command}}, f)
        # A DURABLE copy of the real payload, so this test proves the
        # has_statusline gate specifically — not the durability guard.
        self.plugin = durable_plugin_copy(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_skips_heal_when_host_has_no_statusline(self):
        # A real Host subclass — the same shape production loads from _host.py —
        # with only has_statusline flipped off (the Codex capability profile).
        class NoStatuslineHost(_mod.hostapi.Host):
            has_statusline = False

        no_statusline_host = NoStatuslineHost()

        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            # expanduser("~") -> our fake HOME, so IF the heal ran it would
            # resolve into it; CLAUDE_PLUGIN_ROOT -> the real plugin so
            # statusline.py exists (proving a skip, not a load-time failure).
            with mock.patch.object(os.path, "expanduser", return_value=self.home), \
                 mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": self.plugin}), \
                 mock.patch.object(_mod, "get_host",
                                    return_value=no_statusline_host), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _mod.main()
        finally:
            os.chdir(cwd)
        # The heal must NEVER have run: the stale pin is untouched byte-for-byte.
        with open(self.settings, encoding="utf-8") as f:
            cmd = json.load(f)["statusLine"]["command"]
        self.assertEqual(cmd, self.stale_command)


class TestStartupStateHostLine(unittest.TestCase):
    """observability-004 (#268): the startup-state banner names the RESOLVED
    host (`host.name`) so a dormant/broken host (FailClosedHost -> "unknown",
    #255) is visible right in the banner instead of looking identical to a
    working install. The line prints for ANY arbiter-enabled repo, even one
    not yet initialized (it sits before the INITIALIZED check in main())."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        cad = os.path.join(self.repo, ".codearbiter")
        os.makedirs(cad)
        with open(os.path.join(cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\n---\n\n_stub, not initialized_\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self, host):
        buf = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            # get_host() (#257: main() resolves the Host via _hooklib.get_host(),
            # not a direct hostapi.load_host(), so that is the mock target).
            with mock.patch.object(_mod, "get_host", return_value=host), \
                 mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.repo}), \
                 contextlib.redirect_stdout(buf), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _mod.main()
        finally:
            os.chdir(cwd)
        return buf.getvalue()

    def test_named_host_appears_in_banner(self):
        class CodexHost(_mod.hostapi.Host):
            name = "codex"

        out = self._run_main(CodexHost())
        self.assertIn("host: codex", out)

    def test_unknown_host_appears_in_banner(self):
        # FailClosedHost (#255) — the dormant/broken-install case this
        # feature exists to surface.
        out = self._run_main(_mod.hostapi.FailClosedHost())
        self.assertIn("host: unknown", out)


class TestDevExitAudit(unittest.TestCase):
    """observability-001: when SessionStart clears a LIVE dev-active marker (a
    prior session entered /ca:dev and ended without /ca:arbiter), it must append
    a synthetic DEV: exit line to overrides.log BEFORE removing the marker — so
    the audit trail keeps a matched DEV: enter/exit pair instead of an orphaned
    enter. Append-only (never rewrites); no append when there is no live marker."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ca = os.path.join(self.root, ".codearbiter")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.markers)
        self.log = os.path.join(self.ca, "overrides.log")
        self.marker = os.path.join(self.markers, "dev-active")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_log(self, text):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(text)

    def _read_log(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def _drop_marker(self):
        with open(self.marker, "w", encoding="utf-8") as f:
            f.write("active\n")

    def test_live_marker_appends_dev_exit_and_removes_marker(self):
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        self.assertFalse(os.path.isfile(self.marker), "live marker must be removed")
        log = self._read_log()
        self.assertIn("DEV: exit", log)
        self.assertIn("BY: session-cleanup", log)
        # append-only: the prior DEV: enter line is preserved.
        self.assertIn("DEV: enter", log)

    def test_live_marker_close_line_is_attributed_to_the_resolved_host(self):
        # ADR-0012/observability-001: the synthetic close line must carry
        # HOST: <name> so a shared overrides.log is host-attributable.
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        self._drop_marker()
        _mod.clear_dev_marker(self.root, "codex")
        log = self._read_log()
        self.assertIn("HOST: codex", log)

    def test_live_marker_close_line_defaults_host_when_not_supplied(self):
        # Callers that omit host_name (e.g. legacy call sites, this test suite's
        # own default-arg calls) still get a HOST: field, resolved internally.
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        log = self._read_log()
        self.assertRegex(log, r"HOST: \S+")

    def test_no_marker_appends_nothing(self):
        seed = "[2026-01-01T00:00:00Z] | BY: x | GATE: none | REASON: seed\n"
        self._seed_log(seed)
        self.assertFalse(os.path.isfile(self.marker))
        _mod.clear_dev_marker(self.root)
        self.assertEqual(self._read_log(), seed, "no marker -> overrides.log untouched")

    # -- #271 C-4/C-5: session-scoped clearing -------------------------------
    # A repo-global marker with no owner concept meant ANY SessionStart
    # (including one from a totally different, concurrently-running session)
    # would unconditionally clear it and write a false DEV: exit. These tests
    # simulate two sessions sharing one repo: session A's own SessionStart
    # runs (recording itself as the last-known active session) BEFORE it
    # enters /dev; session B's SessionStart must not clobber A's still-live
    # marker.

    def test_concurrent_live_session_marker_is_not_clobbered(self):
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        # Session A's own SessionStart, BEFORE it enters /dev (no marker yet).
        _mod.clear_dev_marker(self.root, session_id="sess-A")
        # A enters /dev.
        self._drop_marker()
        # Session B starts concurrently, while A is still live in dev mode.
        _mod.clear_dev_marker(self.root, session_id="sess-B")
        self.assertTrue(os.path.isfile(self.marker),
                         "session B must not clear session A's live marker")
        log = self._read_log()
        self.assertNotIn("DEV: exit", log,
                          "session B must not write a false DEV: exit for session A")

    def test_same_session_resume_does_not_clobber_its_own_marker(self):
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        _mod.clear_dev_marker(self.root, session_id="sess-A")
        self._drop_marker()
        # The SAME session resumes/compacts mid-dev — not "ended".
        _mod.clear_dev_marker(self.root, session_id="sess-A")
        self.assertTrue(os.path.isfile(self.marker))
        self.assertNotIn("DEV: exit", self._read_log())

    def test_stale_owner_beyond_liveness_window_is_still_cleared(self):
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        _mod.clear_dev_marker(self.root, session_id="sess-A", now=1000.0)
        self._drop_marker()
        later = 1000.0 + _mod.DEV_SESSION_LIVENESS_WINDOW + 1
        _mod.clear_dev_marker(self.root, session_id="sess-B", now=later)
        self.assertFalse(os.path.isfile(self.marker),
                          "a genuinely abandoned marker must still self-heal eventually")
        self.assertIn("DEV: exit", self._read_log())

    def test_no_session_id_degrades_to_unconditional_clear(self):
        # Codex parity unverified: a host that supplies no session_id at all
        # must fall back to today's behavior rather than never clearing.
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        _mod.clear_dev_marker(self.root, session_id="sess-A")
        self._drop_marker()
        _mod.clear_dev_marker(self.root, session_id=None)
        self.assertFalse(os.path.isfile(self.marker))
        self.assertIn("DEV: exit", self._read_log())

    def test_no_prior_owner_record_degrades_to_unconditional_clear(self):
        # A marker present with NO recorded owner at all (e.g. a legacy
        # marker, or the very first session ever) — no signal to protect a
        # concurrent session, so proceed exactly as before #271.
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        self._drop_marker()
        _mod.clear_dev_marker(self.root, session_id="sess-B")
        self.assertFalse(os.path.isfile(self.marker))
        self.assertIn("DEV: exit", self._read_log())

    def test_unrelated_sessions_do_not_reset_the_owners_clock(self):
        """The liveness window must be anchored to the OWNER's last activity,
        never to whatever session most recently started. A sequence of
        unrelated sessions (B, C, D, ...), each only minutes apart, must NOT
        keep resetting the clock — the marker must still self-heal once
        DEV_SESSION_LIVENESS_WINDOW has elapsed from A's own last activity,
        even though many other unrelated sessions started in the meantime."""
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        t0 = 1000.0
        _mod.clear_dev_marker(self.root, session_id="sess-A", now=t0)
        self._drop_marker()

        # A crashes. Unrelated sessions B, C, D, ... start every 5 minutes —
        # each individually well inside the window relative to the LAST
        # observer, but the total elapsed time relative to A's t0 exceeds it.
        step = 5 * 60
        t = t0
        for i in range(200):  # 200 * 5min = ~16.7h of unrelated activity
            t += step
            _mod.clear_dev_marker(self.root, session_id=f"sess-unrelated-{i}", now=t)
            if t - t0 >= _mod.DEV_SESSION_LIVENESS_WINDOW:
                break

        self.assertGreaterEqual(t - t0, _mod.DEV_SESSION_LIVENESS_WINDOW,
                                 "test setup must actually cross the window")
        self.assertFalse(os.path.isfile(self.marker),
                          "unrelated sessions must not reset A's clock and keep the marker immortal")
        self.assertIn("DEV: exit", self._read_log())

    def test_owner_heartbeat_past_window_is_never_clobbered(self):
        """The OWNER itself resuming/compacting repeatedly, well past the 6h
        mark, must keep its own marker alive indefinitely — only an UNRELATED
        session's passive observation must decline to refresh the clock."""
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev@example.com | DEV: enter | NOTE: —\n")
        t0 = 1000.0
        _mod.clear_dev_marker(self.root, session_id="sess-A", now=t0)
        self._drop_marker()

        t = t0
        for _ in range(10):
            t += _mod.DEV_SESSION_LIVENESS_WINDOW - 1  # always just under the bound
            _mod.clear_dev_marker(self.root, session_id="sess-A", now=t)

        self.assertGreater(t - t0, _mod.DEV_SESSION_LIVENESS_WINDOW,
                            "test setup must actually run past one window's worth of elapsed time")
        self.assertTrue(os.path.isfile(self.marker),
                         "the owner's own heartbeat must never be clobbered by its own resume")
        self.assertNotIn("DEV: exit", self._read_log())

    def test_append_is_a_single_line_after_existing_content(self):
        seed = "[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n"
        self._seed_log(seed)
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        log = self._read_log()
        self.assertTrue(log.startswith(seed), "existing lines must remain a prefix (pure append)")
        self.assertEqual(len(log.splitlines()), 2, "exactly one DEV: exit line appended")


class TestDevExitRetryablePendingClose(unittest.TestCase):
    """#396: a failed overrides.log append must not destroy the only signal that
    a DEV: exit is still owed. `clear_dev_marker` stages a durable pending-close
    record BEFORE attempting the append and clears it only once the append (and
    the marker removal) are confirmed — so a locked/failing log leaves a
    retryable record instead of an orphaned DEV: enter."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ca = os.path.join(self.root, ".codearbiter")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.markers)
        self.log = os.path.join(self.ca, "overrides.log")
        self.marker = os.path.join(self.markers, "dev-active")
        # The durable retry state lives beside the marker it settles.
        self.pending = os.path.join(self.markers, "dev-close-pending.json")
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_log(self, text):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(text)

    def _read_log(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def _drop_marker(self):
        with open(self.marker, "w", encoding="utf-8") as f:
            f.write("active\n")

    def _exit_lines(self):
        return [ln for ln in self._read_log().splitlines() if "DEV: exit" in ln]

    @contextlib.contextmanager
    def _append_fails(self):
        """Make ONLY the append-mode open of overrides.log raise OSError."""
        real_open = open

        def fake_open(file, mode="r", *a, **kw):
            if "a" in mode and str(file).endswith("overrides.log"):
                raise OSError("locked")
            return real_open(file, mode, *a, **kw)

        with mock.patch("builtins.open", fake_open):
            yield

    def test_append_failure_leaves_a_durable_retryable_close_record(self):
        # AC-1: returns successfully, but the owed close survives on disk.
        self._drop_marker()
        with self._append_fails():
            _mod.clear_dev_marker(self.root)
        self.assertEqual(self._exit_lines(), [], "the append really did fail")
        self.assertTrue(os.path.isfile(self.pending),
                        "a failed append must leave a durable pending-close record")
        with open(self.pending, encoding="utf-8") as f:
            rec = json.load(f)
        self.assertTrue(any("DEV: exit" in ln for ln in rec.get("lines", [])),
                        "the pending record must carry the owed DEV: exit line")

    def test_later_session_appends_the_missing_exit_exactly_once(self):
        # AC-2: the next SessionStart flushes the owed close and clears the
        # retry state — even though the marker is already gone by then.
        self._drop_marker()
        with self._append_fails():
            _mod.clear_dev_marker(self.root)
        self.assertFalse(os.path.isfile(self.marker))
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1,
                         "the owed DEV: exit must land exactly once on retry")
        self.assertFalse(os.path.isfile(self.pending),
                         "a confirmed append must clear the pending-close record")
        # And a third session must not append it again.
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1, "no duplicate on a later session")

    def test_crash_after_append_before_cleanup_does_not_duplicate(self):
        # AC-3: an already-landed close line is recognised on retry (bounded
        # tail scan), so a crash between the append and the record cleanup
        # yields ONE close row, not two.
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        landed = self._exit_lines()
        self.assertEqual(len(landed), 1)
        # Simulate the crash: the record was never cleaned up.
        with open(self.pending, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"lines": [landed[0] + "\n"], "marker_mtime": None}, f)
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1,
                         "an already-appended close must not be appended twice")
        self.assertFalse(os.path.isfile(self.pending),
                         "the settled record must be cleared")

    def test_marker_removal_failure_does_not_duplicate_the_close_row(self):
        # AC-3/AC-4: the append lands, but the marker cleanup fails. The next
        # SessionStart still sees a live marker and must NOT mint a second
        # close row for the same marker.
        self._drop_marker()
        real_remove = os.remove

        def fake_remove(path, *a, **kw):
            if str(path).endswith("dev-active"):
                raise OSError("locked")
            return real_remove(path, *a, **kw)

        with mock.patch("os.remove", fake_remove):
            _mod.clear_dev_marker(self.root)
        self.assertTrue(os.path.isfile(self.marker), "marker cleanup really did fail")
        self.assertEqual(len(self._exit_lines()), 1)
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1,
                         "the same marker must not be closed twice in the audit trail")
        self.assertFalse(os.path.isfile(self.marker), "the retry removes the marker")
        self.assertFalse(os.path.isfile(self.pending))

    def test_clean_close_leaves_no_pending_record_behind(self):
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1)
        self.assertFalse(os.path.isfile(self.marker))
        self.assertFalse(os.path.isfile(self.pending),
                         "the happy path must not leave retry state on disk")

    def test_corrupt_pending_record_is_discarded_not_jammed(self):
        # A record that carries no recoverable line must not wedge the
        # mechanism shut (nothing to replay, so drop it and carry on).
        with open(self.pending, "w", encoding="utf-8", newline="\n") as f:
            f.write("{not json")
        _mod.clear_dev_marker(self.root)
        self.assertFalse(os.path.isfile(self.pending))
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        self.assertEqual(len(self._exit_lines()), 1)

    def test_a_removed_marker_leaves_no_tombstone_in_the_pending_record(self):
        # The marker_mtime field is a TOMBSTONE — "this marker has already been
        # closed in the trail". It is only meaningful while that marker still
        # EXISTS. When the append fails but the removal succeeds, the record
        # must keep the owed line and forget the marker: naming a marker that
        # is gone lets its mtime collide with an unrelated future marker.
        self._drop_marker()
        with self._append_fails():
            _mod.clear_dev_marker(self.root)
        self.assertFalse(os.path.isfile(self.marker), "the marker really was removed")
        with open(self.pending, encoding="utf-8") as f:
            rec = json.load(f)
        self.assertTrue(rec.get("lines"), "the owed close must still be staged")
        self.assertIsNone(rec.get("marker_mtime"),
                          "a record whose marker is gone must not keep its identity")

    def test_a_stale_tombstone_cannot_suppress_a_later_sessions_close(self):
        # The consequence of leaking the tombstone: a LATER dev session whose
        # marker happens to land on the same mtime (2s-granularity FAT32/exFAT/
        # SMB/WSL mounts do this routinely) is mistaken for the already-closed
        # one, and its close row is silently dropped — the exact unmatched
        # `DEV: enter` #396 exists to prevent.
        self._drop_marker()
        first_mtime = os.path.getmtime(self.marker)
        with self._append_fails():
            _mod.clear_dev_marker(self.root)
        self.assertFalse(os.path.isfile(self.marker))

        # A second, unrelated /ca:dev entry whose marker collides on mtime.
        self._drop_marker()
        os.utime(self.marker, (first_mtime, first_mtime))
        _mod.clear_dev_marker(self.root)

        self.assertEqual(len(self._exit_lines()), 2,
                         "two dev sessions owe two close rows, not one")
        self.assertFalse(os.path.isfile(self.pending))

    def test_a_freshly_minted_close_is_never_deduped_against_the_trail(self):
        # The dedupe tail scan compares WHOLE LINES, and a close row is
        # timestamped only to the second — so two genuinely distinct closes
        # minted in the same second are byte-identical. The scan exists to stop
        # a crash-after-append REPLAY from landing twice; it must never be
        # applied to the freshly minted line, which by construction cannot
        # already be on the trail. Otherwise the second session's close is
        # swallowed by the first session's owed copy of it.
        same_second = ("[2026-01-01T00:00:07Z] | BY: session-cleanup | HOST: claude "
                       "| DEV: exit | NOTE: cleared by SessionStart\n")
        self._drop_marker()
        with self._append_fails():
            _mod._settle_dev_close(self.root, marker=self.marker, new_line=same_second)
        self.assertEqual(self._exit_lines(), [], "the first append really did fail")

        self._drop_marker()
        _mod._settle_dev_close(self.root, marker=self.marker, new_line=same_second)
        self.assertEqual(len(self._exit_lines()), 2,
                         "two owed closes must both land even when the second "
                         "granularity makes their lines identical")
        self.assertFalse(os.path.isfile(self.pending))

    def test_the_pending_close_cap_never_discards_a_close_silently(self):
        # The record is bounded to _DEV_PENDING_CLOSE_MAX, so a long-lived
        # write failure DOES lose the oldest owed rows. That loss must not be
        # silent: it is counted while the log is unwritable and written to the
        # trail as one attributable note the moment the log accepts writes.
        cap = _mod._DEV_PENDING_CLOSE_MAX
        owed = [
            f"[2026-01-01T00:00:{i:02d}Z] | BY: session-cleanup | HOST: claude "
            f"| DEV: exit | NOTE: owed close {i}\n"
            for i in range(cap + 4)
        ]
        with self._append_fails():
            for line in owed:
                _mod._settle_dev_close(self.root, new_line=line)

        with open(self.pending, encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(len(rec.get("lines") or []), cap, "the record stays bounded")
        self.assertEqual(rec.get("dropped"), 4,
                         "every discarded close row must be counted, not forgotten")

        # overrides.log becomes writable again: the owed rows AND the note land.
        _mod._settle_dev_close(self.root)
        self.assertEqual(len(self._exit_lines()), cap,
                         "every retained owed close must land exactly once")
        notes = [ln for ln in self._read_log().splitlines()
                 if "DEV: close-dropped" in ln]
        self.assertEqual(len(notes), 1,
                         "the discarded closes must be reported once on the trail")
        self.assertIn("4", notes[0], "the note must carry how many were discarded")
        self.assertFalse(os.path.isfile(self.pending),
                         "a fully settled record is cleared")


class TestStandupBriefingGating(unittest.TestCase):
    """#61 regression: pin the once-per-LOCAL-day briefing contract so the
    documented behavior (and the absence of a marker/timezone misfire) cannot
    silently regress.

    Conclusion of the #61 investigation: the briefing is correct-but-surprising,
    NOT a bug. The full briefing shows once per local day (first session); later
    same-day sessions emit an offer line ONLY when something is actionable, and
    nothing otherwise. A prior-day marker never suppresses today (rules out the
    marker-staleness hypothesis)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_session_of_day_emits(self):
        # No marker for today -> emit the full briefing.
        self.assertTrue(should_emit_briefing(self.root, "2026-06-18"))

    def test_marker_present_suppresses_same_day(self):
        write_standup_marker(self.root, "2026-06-18")
        self.assertFalse(should_emit_briefing(self.root, "2026-06-18"))

    def test_prior_day_marker_does_NOT_suppress_today(self):
        # The marker is date-keyed: yesterday's marker is irrelevant to today.
        # This is the guard against the "stale marker persists" hypothesis.
        write_standup_marker(self.root, "2026-06-17")
        self.assertTrue(should_emit_briefing(self.root, "2026-06-18"))

    def test_write_marker_is_idempotent(self):
        write_standup_marker(self.root, "2026-06-18")
        write_standup_marker(self.root, "2026-06-18")  # must not raise
        self.assertTrue(os.path.isfile(standup_marker_path(self.root, "2026-06-18")))

    def test_marker_path_is_date_keyed_under_markers_dir(self):
        p = standup_marker_path(self.root, "2026-06-18")
        self.assertEqual(
            p,
            os.path.join(self.root, ".codearbiter", ".markers", "standup-2026-06-18"),
        )

    def test_local_date_iso_accepts_injected_date(self):
        import datetime
        self.assertEqual(local_date_iso(datetime.date(2026, 6, 18)), "2026-06-18")

    def test_briefing_mode_first_session_is_full_regardless_of_actionable(self):
        # marker absent -> "full" whether or not the repo is actionable.
        self.assertEqual(briefing_mode(marker_present=False, actionable=False), "full")
        self.assertEqual(briefing_mode(marker_present=False, actionable=True), "full")

    def test_briefing_mode_later_session_offers_only_when_actionable(self):
        # marker present -> "offer" iff actionable, else "none" (silent).
        self.assertEqual(briefing_mode(marker_present=True, actionable=True), "offer")
        self.assertEqual(briefing_mode(marker_present=True, actionable=False), "none")


class TestProvenanceDriftLine(unittest.TestCase):
    """T-16: provenance_drift_line — passive SessionStart drift notice.

    AC-06: returns '' when docs are fresh (stored hash == current oid).
    AC-07: returns one ASCII line with /ca:context-check when drift > 0.
    AC-08: returns '' on any degrade (missing dir, runner raises); never raises.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        import _provenancelib
        self._pl = _provenancelib

    def tearDown(self):
        self._tmp.cleanup()

    def _write_prov(self, doc, rel_path, stored_hash):
        """Write a minimal provenance record with one drift_trigger:true entry."""
        prov_dir = os.path.join(self.root, ".codearbiter", ".provenance")
        record = self._pl.new_record(doc, entries=[{
            "path": rel_path,
            "hash": stored_hash,
            "drift_trigger": True,
            "claims": [],
        }])
        self._pl.write_provenance(os.path.join(prov_dir, f"{doc}.json"), record)

    def _make_runner(self, oid):
        """Return a fake batch_hash-compatible runner that returns `oid` for every path."""
        def fake_runner(args, stdin_text):
            paths = [ln for ln in stdin_text.splitlines() if ln]
            return "\n".join(oid for _ in paths) + ("\n" if paths else "")
        return fake_runner

    def test_drift_gt_0_returns_line_with_context_check(self):
        """drift_trigger:true entry with diverged hash -> non-empty line containing /ca:context-check."""
        stored_oid = "a" * 40
        diverged_oid = "b" * 40
        # Create the source file under root so os.path.exists(<root>/<rel_path>) is True.
        src_dir = os.path.join(self.root, "plugins", "ca", "tools")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "package.json"), "w") as f:
            f.write("{}\n")
        rel_path = "plugins/ca/tools/package.json"
        self._write_prov("tech-stack", rel_path, stored_oid)
        result = provenance_drift_line(self.root, runner=self._make_runner(diverged_oid))
        self.assertTrue(result, "drift>0 must return a non-empty line")
        self.assertIn("/ca:context-check", result)

    def test_clean_returns_empty_string(self):
        """stored hash == current oid -> returns ''."""
        stored_oid = "a" * 40
        src_dir = os.path.join(self.root, "plugins", "ca", "tools")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "package.json"), "w") as f:
            f.write("{}\n")
        rel_path = "plugins/ca/tools/package.json"
        self._write_prov("tech-stack", rel_path, stored_oid)
        result = provenance_drift_line(self.root, runner=self._make_runner(stored_oid))
        self.assertEqual(result, "")

    def test_missing_provenance_dir_returns_empty_string(self):
        """No .codearbiter/.provenance/ dir -> '' (degrade-to-silence)."""
        result = provenance_drift_line(self.root, runner=self._make_runner("a" * 40))
        self.assertEqual(result, "")

    def test_runner_raises_returns_empty_string_no_raise(self):
        """runner that raises -> '' without raising; degrade never crashes startup."""
        stored_oid = "a" * 40
        src_dir = os.path.join(self.root, "plugins", "ca", "tools")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "package.json"), "w") as f:
            f.write("{}\n")
        rel_path = "plugins/ca/tools/package.json"
        self._write_prov("tech-stack", rel_path, stored_oid)

        def bad_runner(args, stdin_text):
            raise RuntimeError("git unavailable in test")

        # Must not raise; must return "".
        result = provenance_drift_line(self.root, runner=bad_runner)
        self.assertEqual(result, "")


class TestUpdateNoticeLine(unittest.TestCase):
    """update-available notifier (AC-1/AC-2/AC-3) — SessionStart's read-only half.
    update_notice_line() must read ONLY the cache + installed plugin.json version
    (one file read, no network) and never raise."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = os.path.join(self._tmp.name, "plugin")
        os.makedirs(os.path.join(self.plugin, ".claude-plugin"))
        with open(os.path.join(self.plugin, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "ca", "version": "2.8.2"}, f)
        self.state_path = os.path.join(self._tmp.name, "update-state.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_cache(self, latest, checked_at=1000.0):
        with open(self.state_path, "w") as f:
            json.dump({"latest": latest, "checked_at": checked_at}, f)

    def test_ac1_newer_cached_latest_yields_notice(self):
        self._write_cache("2.10.0")
        with mock.patch.dict(os.environ, {"CODEARBITER_UPDATE_STATE": self.state_path}):
            line = _mod.update_notice_line(self.plugin)
        self.assertIn("update available 2.8.2 -> 2.10.0", line)
        self.assertIn("/plugin marketplace update codearbiter", line)

    def test_ac2_equal_cached_latest_yields_no_notice(self):
        self._write_cache("2.8.2")
        with mock.patch.dict(os.environ, {"CODEARBITER_UPDATE_STATE": self.state_path}):
            line = _mod.update_notice_line(self.plugin)
        self.assertEqual(line, "")

    def test_ac2_no_cache_file_yields_no_notice(self):
        # Cache never written yet (first-ever session) — must not error or notice.
        with mock.patch.dict(os.environ, {"CODEARBITER_UPDATE_STATE": self.state_path}):
            line = _mod.update_notice_line(self.plugin)
        self.assertEqual(line, "")

    def test_ac3_corrupt_cache_degrades_to_no_notice_no_raise(self):
        with open(self.state_path, "w") as f:
            f.write("{ not valid json")
        with mock.patch.dict(os.environ, {"CODEARBITER_UPDATE_STATE": self.state_path}):
            try:
                line = _mod.update_notice_line(self.plugin)
            except Exception as e:  # noqa: BLE001
                self.fail(f"update_notice_line must never raise, raised: {e}")
        self.assertEqual(line, "")


class TestSpawnBackgroundUpdateRefresh(unittest.TestCase):
    """AC-3: the network refresh must be off the SessionStart hot path — a detached,
    never-awaited spawn. A spawner that raises (network stack unreachable / OS
    refuses the spawn) must degrade to None, never propagate."""

    def test_spawner_invoked_with_plugin_root(self):
        seen = {}

        def fake_spawner(plugin):
            seen["plugin"] = plugin
            return "proc-handle"

        result = _mod.spawn_background_update_refresh("/some/plugin", spawner=fake_spawner)
        self.assertEqual(result, "proc-handle")
        self.assertEqual(seen["plugin"], "/some/plugin")

    def test_spawner_raising_is_swallowed(self):
        def bad_spawner(plugin):
            raise OSError("no process table slots")

        try:
            result = _mod.spawn_background_update_refresh("/some/plugin", spawner=bad_spawner)
        except Exception as e:  # noqa: BLE001
            self.fail(f"spawn_background_update_refresh must fail-silent, raised: {e}")
        self.assertIsNone(result)

    def test_default_spawner_never_awaited_and_returns_handle_or_none(self):
        # Use the REAL default spawner but target a harmless, fast, no-op python
        # invocation in place of the real refresh script, proving the call returns
        # immediately (a Popen handle) rather than blocking on the child.
        import time as _time
        plugin_dir = tempfile.mkdtemp()
        try:
            hooks_dir = os.path.join(plugin_dir, "hooks")
            os.makedirs(hooks_dir)
            # A trivial script standing in for update-refresh.py.
            with open(os.path.join(hooks_dir, "update-refresh.py"), "w") as f:
                f.write("import time\ntime.sleep(0.05)\n")
            t0 = _time.time()
            proc = _mod.spawn_background_update_refresh(plugin_dir)
            elapsed = _time.time() - t0
            self.assertLess(elapsed, 1.0, "spawn must return immediately, never await the child")
            if proc is not None:
                # #462: wait() alone leaves the handle's pipes open, and the
                # ResourceWarning it raises at GC time is the quiet half of the
                # intermittent-teardown problem. communicate() drains and closes.
                try:
                    proc.communicate(timeout=5)
                except Exception:  # noqa: BLE001
                    proc.kill()
                    proc.communicate(timeout=5)
        finally:
            import shutil
            shutil.rmtree(plugin_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
