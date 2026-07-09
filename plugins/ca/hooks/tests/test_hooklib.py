import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _hooklib  # noqa: E402
from _hooklib import frontmatter_enabled, project_root  # noqa: E402


def _write_ctx(tmp, content):
    """Write content (str or bytes) to a CONTEXT.md in tmp and return its path."""
    path = os.path.join(tmp, "CONTEXT.md")
    if isinstance(content, str):
        content = content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(content)
    return path


class TestFrontmatterEnabled(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_frontmatter_returns_false_false(self):
        # A file whose first line is NOT "---" is dormant — not malformed.
        path = _write_ctx(self.tmp, "# Just a heading\narbiter: enabled\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_valid_frontmatter_arbiter_enabled(self):
        path = _write_ctx(self.tmp, "---\narbiter: enabled\n---\n# Body\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_unclosed_frontmatter_returns_false_true(self):
        # Opening "---" with no closing "---" is the fail-loud case.
        path = _write_ctx(self.tmp, "---\narbiter: enabled\n# no closing delimiter\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertTrue(malformed)

    def test_bom_on_first_line_frontmatter_enabled(self):
        # A UTF-8 BOM (\xef\xbb\xbf) before the opening "---" must be tolerated.
        content = b"\xef\xbb\xbf---\narbiter: enabled\n---\n# Body\n"
        path = _write_ctx(self.tmp, content)
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_arbiter_enabled_mixed_case(self):
        # The regex is case-insensitive; "Enabled" must be accepted.
        path = _write_ctx(self.tmp, "---\narbiter: Enabled\n---\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertTrue(enabled)
        self.assertFalse(malformed)

    def test_arbiter_disabled_returns_false_false(self):
        # "arbiter: disabled" is a valid, closed frontmatter — dormant, not malformed.
        path = _write_ctx(self.tmp, "---\narbiter: disabled\n---\n# ctx\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_missing_file_returns_false_false(self):
        # A nonexistent file must not raise — dormant, not malformed.
        path = os.path.join(self.tmp, "does_not_exist.md")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_empty_file_returns_false_false(self):
        path = _write_ctx(self.tmp, "")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)

    def test_closed_frontmatter_without_arbiter_key(self):
        # A properly closed frontmatter that lacks the arbiter key is dormant.
        path = _write_ctx(self.tmp, "---\ntitle: My project\nauthor: Alice\n---\n# Body\n")
        enabled, malformed = frontmatter_enabled(path)
        self.assertFalse(enabled)
        self.assertFalse(malformed)


class TestProjectRootMemoization(unittest.TestCase):
    """#260 (performance-001/003): project_root() resolves at most once per
    (CLAUDE_PROJECT_DIR, process cwd) — repeated calls within that same
    context must not re-spawn git — while a genuine env/cwd change (as
    integration tests simulate across scenarios) must still get a FRESH
    resolution, never a stale cached one."""

    def setUp(self):
        _hooklib._reset_root_cache()
        self._env = os.environ.get("CLAUDE_PROJECT_DIR")
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env
        _hooklib._reset_root_cache()

    def test_repeated_calls_resolve_the_host_only_once(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLAUDE_PROJECT_DIR"] = d
            calls = []
            real = _hooklib.get_host()

            def _spy(payload=None):
                calls.append(payload)
                return d

            with mock.patch.object(real, "project_root", side_effect=_spy):
                self.assertEqual(project_root(), d)
                self.assertEqual(project_root(), d)
                self.assertEqual(project_root(), d)
            self.assertEqual(len(calls), 1,
                              "project_root() must resolve the Host only once "
                              "per (env, cwd) context")

    def test_payload_bearing_first_call_and_later_no_arg_calls_stay_consistent(self):
        # A first call WITH a payload, then later no-arg calls (the
        # block()/remind()/warn() gate-logging pattern) in the SAME (env,
        # cwd) context must return the SAME cached value, never re-resolve.
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLAUDE_PROJECT_DIR"] = d
            calls = []
            real = _hooklib.get_host()

            def _spy(payload=None):
                calls.append(payload)
                return d

            with mock.patch.object(real, "project_root", side_effect=_spy):
                first = project_root({"cwd": "/somewhere/irrelevant"})
                second = project_root()
                third = project_root()
            self.assertEqual(first, d)
            self.assertEqual(second, d)
            self.assertEqual(third, d)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], {"cwd": "/somewhere/irrelevant"})

    def test_env_change_busts_the_cache(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            os.environ["CLAUDE_PROJECT_DIR"] = d1
            self.assertEqual(os.path.realpath(project_root()), os.path.realpath(d1))
            os.environ["CLAUDE_PROJECT_DIR"] = d2
            self.assertEqual(os.path.realpath(project_root()), os.path.realpath(d2))

    def test_cwd_change_busts_the_cache(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            try:
                os.chdir(d1)
                r1 = project_root()
                os.chdir(d2)
                r2 = project_root()
            finally:
                # Release both dirs before the `with` blocks try to remove
                # them — a Windows process cwd inside a TemporaryDirectory
                # blocks its own cleanup (WinError 32).
                os.chdir(self._cwd)
            # Neither d1 nor d2 is a git repo, so both resolve to the
            # respective cwd itself (final fallback) — proving the second
            # call re-resolved rather than replaying the first cwd's answer.
            self.assertEqual(os.path.realpath(r1), os.path.realpath(d1))
            self.assertEqual(os.path.realpath(r2), os.path.realpath(d2))
            self.assertNotEqual(os.path.realpath(r1), os.path.realpath(r2))

    def test_reset_helper_forces_a_fresh_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLAUDE_PROJECT_DIR"] = d
            calls = []
            real = _hooklib.get_host()

            def _spy(payload=None):
                calls.append(payload)
                return d

            with mock.patch.object(real, "project_root", side_effect=_spy):
                project_root()
                _hooklib._reset_root_cache()
                project_root()
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
