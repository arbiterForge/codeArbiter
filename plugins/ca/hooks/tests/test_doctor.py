import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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


class TestCheckRepoRootBinding(unittest.TestCase):
    """Root discovery and attribution must describe the process checkout."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self.tmp.name, "target")
        self.foreign = os.path.join(self.tmp.name, "foreign")
        self.original_cwd = os.getcwd()
        for root, email in ((self.target, "target@example.invalid"),
                            (self.foreign, "foreign@example.invalid")):
            os.makedirs(root)
            initialized = doctor.subprocess.run(
                ["git", "init", "-q", "-b", "main"], cwd=root,
                capture_output=True, text=True)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            configured = doctor.subprocess.run(
                ["git", "config", "user.email", email], cwd=root,
                capture_output=True, text=True)
            self.assertEqual(configured.returncode, 0, configured.stderr)
        context = os.path.join(self.target, ".codearbiter")
        os.makedirs(context)
        with open(os.path.join(context, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")

    def tearDown(self):
        os.chdir(self.original_cwd)
        _reset()
        self.tmp.cleanup()

    def test_ambient_repository_selectors_cannot_rebind_root_or_attribution(self):
        hostile = {
            "GIT_DIR": os.path.join(self.foreign, ".git"),
            "GIT_WORK_TREE": self.foreign,
            "GIT_COMMON_DIR": os.path.join(self.foreign, ".git"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": "*",
        }
        os.chdir(self.target)

        with mock.patch.dict(os.environ, hostile, clear=False):
            root = doctor.check_repo()

        self.assertEqual(os.path.realpath(root), os.path.realpath(self.target))
        lines = "\n".join(line for _, line in doctor.results)
        self.assertIn("target@example.invalid", lines)
        self.assertNotIn("foreign@example.invalid", lines)


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


class TestCheckGitHookBackstop(unittest.TestCase):
    """Doctor must inspect the hook directory selected by the real Git binary."""

    def setUp(self):
        _reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.xdg_home = os.path.join(self.home, "xdg")
        os.makedirs(self.xdg_home)
        self._env_patch = mock.patch.dict(
            os.environ,
            {"HOME": self.home, "USERPROFILE": self.home,
             "XDG_CONFIG_HOME": self.xdg_home},
            clear=False)
        self._env_patch.start()
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.root)
        subprocess = doctor.subprocess
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=self.root,
            check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.email", "doctor@example.com"], cwd=self.root,
            check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.name", "Doctor Test"], cwd=self.root,
            check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "commit.gpgSign", "false"], cwd=self.root,
            check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "core.hooksPath",
             os.path.join(self.root, ".git", "hooks")], cwd=self.root,
            check=True, capture_output=True, text=True)
        ctx = os.path.join(self.root, ".codearbiter")
        os.makedirs(ctx)
        with open(os.path.join(ctx, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")

    def tearDown(self):
        _reset()
        self._env_patch.stop()
        self.tmp.cleanup()

    def _install_live_backstop(self, root=None):
        root = root or self.root
        doctor._githooks.install(root)
        dropin = doctor._githooks._dropin_dir(root)
        os.makedirs(dropin, exist_ok=True)
        enforcer = os.path.join(self.tmp.name, "durable", "git-enforce.py")
        os.makedirs(os.path.dirname(enforcer), exist_ok=True)
        with open(enforcer, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(0)\n")
        entry = doctor._githooks._path_entry_file(dropin, "ca")
        with open(entry, "w", encoding="utf-8", newline="\n") as f:
            f.write(doctor._githooks._shell_path(enforcer) + "\n")
        return doctor._githooks.hooks_dir(root), dropin

    def test_missing_managed_hooks_in_gits_effective_directory_is_a_failure(self):
        with mock.patch.dict(
                os.environ,
                {"HOME": self.home, "USERPROFILE": self.home},
                clear=False):
            doctor.subprocess.run(
                ["git", "config", "core.hooksPath", "~/.doctor-hooks"],
                cwd=self.root, check=True, capture_output=True, text=True)
            dropin = doctor._githooks._dropin_dir(self.root)
            os.makedirs(dropin)
            doctor.check_git_hook_freshness(self.root)

        failures = [line for level, line in doctor.results if level == "FAIL"]
        self.assertTrue(
            any("git-hook backstop" in line and "effective" in line for line in failures),
            f"doctor reported a healthy backstop without managed hooks: {doctor.results}")

    def test_fixture_install_does_not_escape_through_ambient_global_hookspath(self):
        external_hooks = os.path.join(self.tmp.name, "ambient-hooks")
        with open(os.path.join(self.home, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write(f"[core]\n\thooksPath = {external_hooks.replace(os.sep, '/')}\n")

        with mock.patch.dict(
                os.environ,
                {"HOME": self.home, "USERPROFILE": self.home},
                clear=False):
            hooks_dir, _ = self._install_live_backstop()

        self.assertEqual(
            os.path.normcase(os.path.abspath(hooks_dir)),
            os.path.normcase(os.path.join(self.root, ".git", "hooks")))
        self.assertFalse(os.path.exists(os.path.join(external_hooks, "pre-commit")))

    def test_live_fire_cannot_be_rebound_by_ambient_repository_selectors(self):
        self._install_live_backstop()
        foreign = os.path.join(self.tmp.name, "foreign")
        os.makedirs(foreign)
        initialized = doctor.subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=foreign,
            capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        hostile = {
            "GIT_DIR": os.path.join(foreign, ".git"),
            "GIT_WORK_TREE": foreign,
            "GIT_COMMON_DIR": os.path.join(foreign, ".git"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": "*",
        }

        with mock.patch.dict(os.environ, hostile, clear=False):
            _reset()
            doctor.check_git_hook_freshness(self.root)

        self.assertFalse(
            any(level == "FAIL" for level, _ in doctor.results), doctor.results)
        self.assertTrue(
            any(level == "OK" and "live-fire" in line
                for level, line in doctor.results), doctor.results)

    def test_registry_with_only_a_missing_enforcer_is_a_failure(self):
        doctor._githooks.install(self.root)
        dropin = doctor._githooks._dropin_dir(self.root)
        os.makedirs(dropin, exist_ok=True)
        entry = doctor._githooks._path_entry_file(
            dropin, doctor._githooks._plugin_name())
        with open(entry, "w", encoding="utf-8") as f:
            f.write(os.path.join(self.tmp.name, "removed", "git-enforce.py") + "\n")

        doctor.check_git_hook_freshness(self.root)

        failures = [line for level, line in doctor.results if level == "FAIL"]
        self.assertTrue(
            any("git-hook backstop" in line and "live enforcer" in line
                for line in failures),
            f"doctor treated a dead-only registry as healthy: {doctor.results}")

    @unittest.skipIf(os.name == "nt", "Git for Windows does not use POSIX mode bits")
    def test_non_executable_managed_shim_is_a_failure(self):
        hooks_dir, _ = self._install_live_backstop()
        pre_commit = os.path.join(hooks_dir, "pre-commit")
        os.chmod(pre_commit, 0o644)

        actual = doctor.subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "must not land"],
            cwd=self.root, capture_output=True, text=True)
        self.assertEqual(
            actual.returncode, 0,
            "the discriminator requires actual Git to ignore the inoperable shim")
        doctor.check_git_hook_freshness(self.root)

        failures = [line for level, line in doctor.results if level == "FAIL"]
        self.assertTrue(
            any("git-hook backstop" in line and "executable" in line
                for line in failures),
            f"doctor treated a Git-ignored shim as healthy: {doctor.results}")

    def test_malformed_trusted_identity_fails_the_git_live_fire_probe(self):
        _, dropin = self._install_live_backstop()
        with open(doctor._githooks._identity_file(dropin), "w", encoding="utf-8") as f:
            f.write("malformed-one-record-only\n")

        actual = doctor.subprocess.run(
            ["git", "hook", "run", "pre-push"], cwd=self.root,
            capture_output=True, text=True)
        self.assertNotEqual(
            actual.returncode, 0,
            "the discriminator requires the real managed shim to reject the identity")
        doctor.check_git_hook_freshness(self.root)

        failures = [line for level, line in doctor.results if level == "FAIL"]
        self.assertTrue(
            any("git-hook backstop" in line and "live-fire" in line
                for line in failures),
            f"doctor ignored an inoperable trusted identity: {doctor.results}")

    def test_live_backstop_passes_actual_git_probe_in_primary_and_linked_worktrees(self):
        doctor.subprocess.run(
            ["git", "add", ".codearbiter/CONTEXT.md"], cwd=self.root,
            check=True, capture_output=True, text=True)
        seed = doctor.subprocess.run(
            ["git", "commit", "-q", "-m", "seed"], cwd=self.root,
            capture_output=True, text=True)
        self.assertEqual(seed.returncode, 0, seed.stderr + seed.stdout)
        self._install_live_backstop()
        linked = os.path.join(self.tmp.name, "linked")
        doctor.subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "feat/linked", linked],
            cwd=self.root, check=True, capture_output=True, text=True)

        for checkout in (self.root, linked):
            with self.subTest(checkout=checkout):
                _reset()
                doctor.check_git_hook_freshness(checkout)
                self.assertFalse(
                    any(level == "FAIL" for level, _ in doctor.results), doctor.results)
                self.assertTrue(
                    any(level == "OK" and "live-fire" in line
                        for level, line in doctor.results),
                    f"doctor did not prove Git hook execution in {checkout}: {doctor.results}")


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

        def cmd_ref(self, name):
            # Part of the Host runtime-vocabulary contract (M3/D6): doctor
            # renders command pointers through get_host().cmd_ref(), so any
            # injected host must supply it. Distinctive spelling (never
            # "/ca:") so output provably carries THIS host's vocabulary.
            return "/fake257:" + name

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

    def test_injected_host_vocabulary_reaches_statusline_pointer(self):
        # M3/D6 regression: check_statusline's not-wired pointer renders
        # through get_host().cmd_ref("statusline"), a path only taken on a
        # machine whose ~/.claude/settings.json has no statusline (CI's bare
        # runner — a dev machine with the statusline wired skips it, which is
        # how a fake missing cmd_ref stayed green locally). Force the bare
        # path by pointing the home dir at an empty temp dir, and assert the
        # INJECTED host's spelling is what the pointer carries.
        fake = self._FakeInjectedHost()
        _hooklib.set_host(fake)
        with tempfile.TemporaryDirectory() as home:
            saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
            os.environ["HOME"] = home
            os.environ["USERPROFILE"] = home
            try:
                doctor.check_statusline(os.getcwd())
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertTrue(_has("/fake257:statusline"),
                        f"expected the injected host's cmd_ref spelling in "
                        f"the statusline pointer; got: {_lines()}")


if __name__ == "__main__":
    unittest.main()
