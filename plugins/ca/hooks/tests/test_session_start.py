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
        # Real plugin root = parent of the hooks/ dir holding session-start.py.
        self.plugin = os.path.dirname(
            os.path.dirname(os.path.abspath(_mod.__file__)))
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
                     "command": '"python" "C:\\old\\ca\\2.0.1\\hooks\\statusline.py"'}})
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
                       "command": '"python" "C:\\old\\ca\\2.0.1\\hooks\\statusline.py"'}}, f)
        self.plugin = os.path.dirname(os.path.dirname(os.path.abspath(_mod.__file__)))
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
        self.stale_command = '"python" "C:\\old\\ca\\2.0.1\\hooks\\statusline.py"'
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command",
                       "command": self.stale_command}}, f)
        self.plugin = os.path.dirname(os.path.dirname(os.path.abspath(_mod.__file__)))

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

    def test_append_is_a_single_line_after_existing_content(self):
        seed = "[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n"
        self._seed_log(seed)
        self._drop_marker()
        _mod.clear_dev_marker(self.root)
        log = self._read_log()
        self.assertTrue(log.startswith(seed), "existing lines must remain a prefix (pure append)")
        self.assertEqual(len(log.splitlines()), 2, "exactly one DEV: exit line appended")


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
                proc.wait(timeout=5)
        finally:
            import shutil
            shutil.rmtree(plugin_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
