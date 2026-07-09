import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

# Ensure hooks/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# doctor.py uses a module-level `results` list that accumulates (level, line)
# tuples. We import doctor and reset that list between tests to isolate them.
import doctor  # noqa: E402
import _hooklib  # noqa: E402


def _reset():
    """Clear the module-level results accumulator between test cases."""
    doctor.results.clear()


def _levels():
    return [lvl for lvl, _ in doctor.results]


def _lines():
    return [line for _, line in doctor.results]


def _has(keyword):
    """True if any result line contains `keyword`."""
    return any(keyword in line for _, line in doctor.results)


class TestCheckHost(unittest.TestCase):
    """observability-004 (#268): check_host() surfaces the resolved host name
    (or a WARN when hostapi.load_host() failed closed to "unknown", #255)."""

    def setUp(self):
        _reset()

    def tearDown(self):
        _reset()

    def test_named_host_is_ok(self):
        class FakeHost:
            name = "codex"

        doctor.check_host(FakeHost())
        ok_lines = [line for lvl, line in doctor.results if lvl == "OK"]
        self.assertTrue(any("codex" in line for line in ok_lines))
        self.assertNotIn("WARN", _levels())

    def test_claude_host_is_ok(self):
        doctor.check_host(doctor.hostapi.Host())
        ok_lines = [line for lvl, line in doctor.results if lvl == "OK"]
        self.assertTrue(any("claude" in line for line in ok_lines))

    def test_unknown_host_is_warn(self):
        doctor.check_host(doctor.hostapi.FailClosedHost())
        self.assertEqual(_levels(), ["WARN"])
        self.assertIn("unknown", _lines()[0])


class TestCheckPayloadMissingScript(unittest.TestCase):
    """check_payload: missing hook scripts → FAIL."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        # Build a minimal valid plugin.json and hooks.json but omit all hook scripts.
        plugin_dir = os.path.join(root, ".claude-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": "1.0.0"}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a", "b"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        self.root = root

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def test_missing_scripts_produce_fail(self):
        doctor.check_payload(self.root)
        self.assertIn("FAIL", _levels())

    def test_fail_line_mentions_missing(self):
        doctor.check_payload(self.root)
        fail_lines = [line for lvl, line in doctor.results if lvl == "FAIL"]
        self.assertTrue(any("missing" in line.lower() for line in fail_lines))

    def test_output_contains_fail_keyword(self):
        doctor.check_payload(self.root)
        fail_lines = [line for lvl, line in doctor.results if lvl == "FAIL"]
        self.assertTrue(len(fail_lines) > 0)


class TestCheckPayloadValidScripts(unittest.TestCase):
    """check_payload: all scripts present → OK (no FAIL)."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        plugin_dir = os.path.join(root, ".claude-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": "2.1.0"}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        # Create all required hook scripts.
        for script in doctor.HOOK_SCRIPTS:
            open(os.path.join(hooks_dir, script), "w").close()
        self.root = root

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def test_no_fail_when_all_scripts_present(self):
        doctor.check_payload(self.root)
        self.assertNotIn("FAIL", _levels())

    def test_ok_present_for_scripts(self):
        doctor.check_payload(self.root)
        ok_lines = [line for lvl, line in doctor.results if lvl == "OK"]
        self.assertTrue(any("hook scripts" in line for line in ok_lines))

    def test_version_reported_in_ok(self):
        doctor.check_payload(self.root)
        ok_lines = [line for lvl, line in doctor.results if lvl == "OK"]
        self.assertTrue(any("2.1.0" in line for line in ok_lines))


class TestCheckPayloadStaleSibling(unittest.TestCase):
    """check_payload: stale sibling dir under /plugins/cache/ → WARN."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        # Build a cache-style path: <tmp>/plugins/cache/ca/2.0.0/
        cache_base = os.path.join(self.tmp.name, "plugins", "cache", "ca")
        root = os.path.join(cache_base, "2.0.0")
        # Create a sibling dir to trigger the multi-version warning.
        sibling = os.path.join(cache_base, "1.9.0")
        os.makedirs(root)
        os.makedirs(sibling)
        # Minimal plugin.json (hooks.json missing → will also FAIL, that's fine)
        plugin_dir = os.path.join(root, ".claude-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": "2.0.0"}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        for script in doctor.HOOK_SCRIPTS:
            open(os.path.join(hooks_dir, script), "w").close()
        self.root = root

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def test_stale_sibling_produces_warn(self):
        doctor.check_payload(self.root)
        self.assertIn("WARN", _levels())

    def test_warn_mentions_stale_versions(self):
        doctor.check_payload(self.root)
        warn_lines = [line for lvl, line in doctor.results if lvl == "WARN"]
        self.assertTrue(any("2.0.0" in line or "1.9.0" in line for line in warn_lines))


class TestCheckPayloadHostAware(unittest.TestCase):
    """#263 (reliability-001): check_payload must resolve the manifest via
    host.manifest_relpath(), not a hard-coded `.claude-plugin/plugin.json` —
    a ca-codex-shaped install (manifest at `.codex-plugin/plugin.json` ONLY,
    no `.claude-plugin/` at all) was previously reported UNHEALTHY (FAIL) on
    every healthy install."""

    class _FakeCodexHost:
        def manifest_relpath(self):
            return os.path.join(".codex-plugin", "plugin.json")

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def _build_codex_shaped_root(self, version="1.2.3"):
        root = self.tmp.name
        plugin_dir = os.path.join(root, ".codex-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": version}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        for script in doctor.HOOK_SCRIPTS:
            open(os.path.join(hooks_dir, script), "w").close()
        return root

    def test_codex_shaped_install_is_healthy_under_codex_host(self):
        root = self._build_codex_shaped_root()
        doctor.check_payload(root, self._FakeCodexHost())
        self.assertNotIn("FAIL", _levels())

    def test_codex_shaped_install_version_reported(self):
        root = self._build_codex_shaped_root("1.2.3")
        doctor.check_payload(root, self._FakeCodexHost())
        ok_lines = [line for lvl, line in doctor.results if lvl == "OK"]
        self.assertTrue(any("1.2.3" in line for line in ok_lines))

    def test_codex_shaped_install_fails_under_default_claude_host(self):
        # Same root, but resolved via the default (Claude) host — no
        # .claude-plugin/ exists here, so this must still FAIL. Confirms the
        # fix is host-SELECTIVE, not a blanket "try both paths" workaround.
        root = self._build_codex_shaped_root()
        doctor.check_payload(root, doctor.hostapi.Host())
        self.assertIn("FAIL", _levels())

    def test_claude_shaped_install_still_healthy_under_default_host(self):
        # No host arg passed at all — resolves via hostapi.load_host(), the
        # pre-#263 default path, and must stay byte-identical for Claude.
        root = self.tmp.name
        plugin_dir = os.path.join(root, ".claude-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": "2.1.0"}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        for script in doctor.HOOK_SCRIPTS:
            open(os.path.join(hooks_dir, script), "w").close()
        doctor.check_payload(root)
        self.assertNotIn("FAIL", _levels())


class TestCheckRepoEnabled(unittest.TestCase):
    """check_repo: arbiter-enabled CONTEXT.md → OK."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        cad = os.path.join(self.tmp.name, ".codearbiter")
        os.makedirs(cad)
        self.ctx = os.path.join(cad, "CONTEXT.md")

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def _write_ctx(self, content):
        with open(self.ctx, "w", encoding="utf-8") as f:
            f.write(content)

    def test_enabled_and_initialized_all_ok(self):
        self._write_ctx(
            "---\narbiter: enabled\n---\n\n<!-- INITIALIZED -->\n"
        )
        # check_repo() uses git internally; we test via frontmatter_enabled directly
        # to avoid git dependency in tests.
        from _hooklib import frontmatter_enabled
        enabled, malformed = frontmatter_enabled(self.ctx)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_enabled_without_initialized_marker(self):
        self._write_ctx("---\narbiter: enabled\n---\n\n_No marker yet._\n")
        from _hooklib import frontmatter_enabled
        enabled, malformed = frontmatter_enabled(self.ctx)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_malformed_frontmatter_unclosed(self):
        self._write_ctx("---\narbiter: enabled\n# no closing ---\n")
        from _hooklib import frontmatter_enabled
        enabled, malformed = frontmatter_enabled(self.ctx)
        self.assertFalse(enabled)
        self.assertTrue(malformed)

    def test_dormant_not_enabled(self):
        # arbiter key present but not set to enabled
        self._write_ctx("---\narbiter: disabled\n---\n")
        from _hooklib import frontmatter_enabled
        enabled, malformed = frontmatter_enabled(self.ctx)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_no_frontmatter_dormant(self):
        self._write_ctx("# Just a markdown file\n")
        from _hooklib import frontmatter_enabled
        enabled, malformed = frontmatter_enabled(self.ctx)
        self.assertFalse(enabled)
        self.assertFalse(malformed)


class TestCheckRepoOutputFormat(unittest.TestCase):
    """Output format: every result line must contain FAIL, WARN, or OK."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        _reset()
        self.tmp.cleanup()

    def _full_valid_root(self):
        """Build a root that passes check_payload without FAILs."""
        root = self.tmp.name
        plugin_dir = os.path.join(root, ".claude-plugin")
        os.makedirs(plugin_dir, exist_ok=True)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({"version": "1.0.0"}, f)
        hooks_dir = os.path.join(root, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        hooks_config = {"hooks": {"UserPromptSubmit": [{"hooks": ["a"]}]}}
        with open(os.path.join(hooks_dir, "hooks.json"), "w") as f:
            json.dump(hooks_config, f)
        for script in doctor.HOOK_SCRIPTS:
            open(os.path.join(hooks_dir, script), "w").close()
        return root

    def test_all_result_levels_are_known_keywords(self):
        self._full_valid_root()
        doctor.check_payload(self.tmp.name)
        for lvl, line in doctor.results:
            self.assertIn(lvl, ("OK", "WARN", "FAIL"),
                          f"unexpected level {lvl!r} in {line!r}")

    def test_result_line_contains_level_word(self):
        """When check_payload is called, each (level, line) pair is well-formed."""
        self._full_valid_root()
        doctor.check_payload(self.tmp.name)
        for lvl, line in doctor.results:
            self.assertIsInstance(lvl, str)
            self.assertIsInstance(line, str)
            self.assertGreater(len(line), 0)


class TestRunHostDISeam(unittest.TestCase):
    """#257 (architecture-001/performance-002): run(host) must WIRE the host it
    is given, not silently discard it. Before this fix, main() re-resolved the
    host itself via a fresh hostapi.load_host() call, so run(fake_host) ran
    against whatever load_host() found on disk (real "claude" in this bare
    checkout) — never the injected fake_host. Drives the REAL run(host) entry
    point (not check_host()/main() directly) and asserts the injected host's
    distinguishing `.name` reaches doctor's printed output, proving run(host)
    is now a live dependency-injection seam."""

    def setUp(self):
        _reset()
        _hooklib.reset_host()  # isolate from any other test's set_host()

    def tearDown(self):
        _reset()
        _hooklib.reset_host()  # do not leak the injected fake into later tests

    class _FakeInjectedHost:
        """A host observably different from the real disk-loaded default
        (name="claude") — if run(host) actually wires it, this name (never
        "claude") is what doctor's output must carry."""
        name = "fake-injected-host-257"

        def manifest_relpath(self):
            return os.path.join(".claude-plugin", "plugin.json")

        def plugin_root(self):
            return os.getcwd()

    def test_run_host_wires_the_injected_host_not_the_disk_default(self):
        fake = self._FakeInjectedHost()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                doctor.run(fake)
            except SystemExit:
                # main() exits 1 when any check FAILs (expected here — no real
                # plugin payload exists at cwd) — the printed lines above the
                # exit are what this test cares about, so tolerate it.
                pass
        out = buf.getvalue()
        self.assertIn("resolved host: fake-injected-host-257", out)
        self.assertNotIn("resolved host: claude", out)

    def test_run_host_primes_get_host_before_main_runs(self):
        # Direct proof of the DI seam itself: after run(host) starts, the
        # process-cached Host _hooklib.get_host() serves is the SAME object
        # identity as the one passed to run() — not a second hostapi.load_host()
        # result.
        fake = self._FakeInjectedHost()
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                doctor.run(fake)
            except SystemExit:
                pass
        self.assertIs(_hooklib.get_host(), fake)


if __name__ == "__main__":
    unittest.main()
