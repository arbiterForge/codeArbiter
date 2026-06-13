import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

# Load wire-statusline.py as a module (filename has a hyphen).
_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_HOOKS_DIR, "wire-statusline.py")
_spec = importlib.util.spec_from_file_location("wire_statusline", _SCRIPT)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def _make_settings(tmp, content=None):
    """Write a settings.json under tmp/.claude/ and return its path."""
    d = os.path.join(tmp, ".claude")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "settings.json")
    if content is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
    return path


def _make_plugin_root(tmp):
    """Create a fake plugin root with hooks/statusline.py present."""
    hooks_dir = os.path.join(tmp, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    script = os.path.join(hooks_dir, "statusline.py")
    open(script, "w").close()
    return tmp


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestFreshInstall(unittest.TestCase):
    """Fresh install: no prior statusline → writes ours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(self.tmp.name)
        self.root = _make_plugin_root(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_installs_our_line(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        sl = data.get("statusLine", {})
        self.assertIn("statusline.py", sl.get("command", ""))

    def test_backup_key_stored_as_none(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        self.assertIn(ws.BACKUP_KEY, data)
        self.assertIsNone(data[ws.BACKUP_KEY])

    def test_settings_file_created_if_absent(self):
        absent = os.path.join(self.tmp.name, "other", "settings.json")
        os.makedirs(os.path.dirname(absent))
        ws.main(["install", "--settings", absent,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertTrue(os.path.isfile(absent))


class TestInstallWithPriorThirdParty(unittest.TestCase):
    """Install over a third-party statusline → backs up theirs, wires ours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        prior = {"type": "command", "command": "my-custom-statusline --foo"}
        self.settings = _make_settings(
            self.tmp.name, {"statusLine": prior})
        self.root = _make_plugin_root(self.tmp.name)
        self.prior_cmd = prior["command"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_replaces_with_our_line(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        cmd = (data.get("statusLine") or {}).get("command", "")
        self.assertIn("statusline.py", cmd)

    def test_prior_line_backed_up(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        backup = data.get(ws.BACKUP_KEY)
        self.assertIsNotNone(backup)
        backed_cmd = backup.get("command") if isinstance(backup, dict) else backup
        self.assertEqual(backed_cmd, self.prior_cmd)


class TestUninstall(unittest.TestCase):
    """Uninstall → removes our line, restores the backed-up prior setting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        prior = {"type": "command", "command": "my-custom-statusline"}
        self.settings = _make_settings(
            self.tmp.name, {"statusLine": prior})
        self.root = _make_plugin_root(self.tmp.name)
        # Install first so there is something to uninstall.
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_removes_our_line(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        sl = data.get("statusLine")
        if sl is not None:
            cmd = sl.get("command") if isinstance(sl, dict) else sl
            self.assertNotIn("statusline.py", (cmd or ""))

    def test_restores_prior_line(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        sl = data.get("statusLine")
        self.assertIsNotNone(sl)
        cmd = sl.get("command") if isinstance(sl, dict) else sl
        self.assertIn("my-custom-statusline", cmd)

    def test_backup_key_removed_after_uninstall(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertNotIn(ws.BACKUP_KEY, data)


class TestIdempotentRefresh(unittest.TestCase):
    """Already our line → re-install refreshes cleanly, no duplicate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(self.tmp.name)
        self.root = _make_plugin_root(self.tmp.name)
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_install_does_not_add_duplicate_backup(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        # BACKUP_KEY should still only appear once (JSON keys are unique by spec)
        raw = open(self.settings, encoding="utf-8").read()
        self.assertEqual(raw.count(ws.BACKUP_KEY), 1)

    def test_second_install_statusline_still_ours(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        cmd = (data.get("statusLine") or {}).get("command", "")
        self.assertIn("statusline.py", cmd)


class TestCorruptedJson(unittest.TestCase):
    """Corrupted JSON input → aborts safely (no file written / overwritten)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        d = os.path.join(self.tmp.name, ".claude")
        os.makedirs(d)
        self.settings = os.path.join(d, "settings.json")
        with open(self.settings, "w") as f:
            f.write("{this is not valid JSON!!")
        self.original_mtime = os.path.getmtime(self.settings)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_raises_system_exit_on_corrupt_json(self):
        with self.assertRaises(SystemExit):
            ws.main(["install", "--settings", self.settings,
                     "--plugin-root", self.root, "--interp", "python"])

    def test_file_not_overwritten_on_corrupt_json(self):
        try:
            ws.main(["install", "--settings", self.settings,
                     "--plugin-root", self.root, "--interp", "python"])
        except SystemExit:
            pass
        # The corrupt file content should be unchanged.
        with open(self.settings) as f:
            content = f.read()
        self.assertIn("not valid JSON", content)


class TestStatusSubcommand(unittest.TestCase):
    """status subcommand → prints current state, changes nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        self.settings = _make_settings(
            self.tmp.name,
            {"statusLine": {"type": "command", "command": "some-other-line"}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_does_not_write_file(self):
        mtime_before = os.path.getmtime(self.settings)
        import time
        time.sleep(0.05)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.root])
        finally:
            sys.stdout = old_stdout
        mtime_after = os.path.getmtime(self.settings)
        self.assertAlmostEqual(mtime_before, mtime_after, delta=0.1)

    def test_status_prints_settings_info(self):
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.root])
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("settings.json", output)

    def test_status_shows_not_wired_to_codearbiter(self):
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.root])
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        # The third-party line is not ours, so "no" should appear
        self.assertIn("no", output.lower())

    def test_status_after_install_shows_wired(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.root])
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("YES", output)


class TestSpinnerVerbsFreshInstall(unittest.TestCase):
    """Fresh install: no prior spinnerVerbs → writes ours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(self.tmp.name)
        self.root = _make_plugin_root(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_sets_spinner_verbs(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        sv = data.get("spinnerVerbs")
        self.assertIsNotNone(sv)
        verbs = sv.get("verbs") if isinstance(sv, dict) else None
        self.assertIsInstance(verbs, list)
        self.assertGreater(len(verbs), 0)

    def test_install_spinner_verbs_backup_stored_as_none(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        self.assertIn(ws.SPINNER_BACKUP_KEY, data)
        self.assertIsNone(data[ws.SPINNER_BACKUP_KEY])

    def test_install_spinner_mode_is_replace(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        sv = data.get("spinnerVerbs", {})
        self.assertEqual(sv.get("mode"), "replace")


class TestSpinnerVerbsWithPriorCustomVerbs(unittest.TestCase):
    """Install over existing user spinnerVerbs → backs theirs up, sets ours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prior_verbs = {"mode": "replace", "verbs": ["Thinking", "Working"]}
        self.settings = _make_settings(
            self.tmp.name, {"spinnerVerbs": self.prior_verbs})
        self.root = _make_plugin_root(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_replaces_prior_verbs_with_ours(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        verbs = (data.get("spinnerVerbs") or {}).get("verbs", [])
        self.assertNotEqual(verbs, self.prior_verbs["verbs"])
        self.assertGreater(len(verbs), 2)

    def test_prior_verbs_backed_up(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        backup = data.get(ws.SPINNER_BACKUP_KEY)
        self.assertEqual(backup, self.prior_verbs)


class TestSpinnerVerbsUninstall(unittest.TestCase):
    """Uninstall → removes our verbs, restores prior."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prior_verbs = {"mode": "replace", "verbs": ["Thinking", "Working"]}
        self.settings = _make_settings(
            self.tmp.name, {"spinnerVerbs": self.prior_verbs})
        self.root = _make_plugin_root(self.tmp.name)
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_uninstall_restores_prior_verbs(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertEqual(data.get("spinnerVerbs"), self.prior_verbs)

    def test_uninstall_removes_spinner_backup_key(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertNotIn(ws.SPINNER_BACKUP_KEY, data)


class TestSpinnerVerbsUninstallNoPrior(unittest.TestCase):
    """Uninstall when no prior verbs → removes our key entirely."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(self.tmp.name)
        self.root = _make_plugin_root(self.tmp.name)
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_uninstall_removes_spinner_verbs_key(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertNotIn("spinnerVerbs", data)

    def test_uninstall_removes_spinner_backup_key(self):
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertNotIn(ws.SPINNER_BACKUP_KEY, data)


class TestSpinnerVerbsIdempotent(unittest.TestCase):
    """Re-install refreshes verb list cleanly, no duplicate backup."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(self.tmp.name)
        self.root = _make_plugin_root(self.tmp.name)
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_install_spinner_backup_key_appears_once(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        raw = open(self.settings, encoding="utf-8").read()
        self.assertEqual(raw.count(ws.SPINNER_BACKUP_KEY), 1)

    def test_second_install_verbs_still_set(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        verbs = (data.get("spinnerVerbs") or {}).get("verbs", [])
        self.assertGreater(len(verbs), 0)


if __name__ == "__main__":
    unittest.main()
