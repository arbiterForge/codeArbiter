"""Tests for session-start.py: has_source(), CONFIRM_RE, task counting."""
import os
import sys
import tempfile
import unittest

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
    """The task counter in main() sums lines starting with '- '. Test the
    logic in isolation (no subprocess / filesystem side-effects)."""

    def _count_tasks(self, text):
        """Mirror the counting logic from session-start.py main()."""
        return sum(1 for ln in text.splitlines() if ln.startswith("- "))

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


if __name__ == "__main__":
    unittest.main()
