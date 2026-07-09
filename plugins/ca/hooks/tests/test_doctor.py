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


if __name__ == "__main__":
    unittest.main()
