import contextlib
import copy
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


# #462: an unclosed file handle is not cosmetic on Windows -- it blocks the
# enclosing TemporaryDirectory's cleanup, so teardown RAISES instead of the
# assertion failing. That is the shape the intermittent suite showed: errors,
# not failures, with no code change between runs. A suite that is red once in
# four trains everyone to re-run first and diagnose never, which is how a real
# regression gets waved through.
def _read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


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
    root = os.path.join(tmp, ".claude", "plugins", "cache", "codearbiter", "ca", "9.9.9")
    hooks_dir = os.path.join(root, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    script = os.path.join(hooks_dir, "statusline.py")
    open(script, "w").close()
    return root


def _make_source_plugin_root(tmp):
    root = os.path.join(tmp, "codeArbiter", "plugins", "ca")
    hooks_dir = os.path.join(root, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    open(os.path.join(hooks_dir, "statusline.py"), "w").close()
    return root


def _make_worktree_plugin_root(tmp):
    """A plugin root inside a Claude Code subagent worktree —
    `<repo>/.claude/worktrees/<id>/plugins/ca` — the exact shape that corrupted
    the maintainer's global settings.json on 2026-07-25. Non-durable by
    construction: the whole purpose of the directory is that it gets pruned.

    Deliberately built with NO git metadata, so it pins the LEXICAL signal on
    its own — the shape confirmed in production must be caught for free."""
    root = os.path.join(tmp, "repo", ".claude", "worktrees",
                        "wf_58ee3fa6-de1-8", "plugins", "ca")
    hooks_dir = os.path.join(root, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    open(os.path.join(hooks_dir, "statusline.py"), "w").close()
    return root


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class _FixtureHost:
    """A test-only executing adapter with one authenticated package root."""

    def __init__(self, root_getter):
        self._root_getter = root_getter

    def plugin_root(self):
        return self._root_getter()


class _WireStatuslineTest(unittest.TestCase):
    """Run each fixture against its declared executing adapter root."""

    def run(self, result=None):
        host = _FixtureHost(lambda: self.root)
        with mock.patch.object(ws._hooklib, "get_host", return_value=host):
            return super().run(result)


class TestFreshInstall(_WireStatuslineTest):
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

    def test_install_records_exact_owned_command(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        self.assertEqual(data[ws.OWNER_KEY], data["statusLine"]["command"])

    def test_backup_key_stored_as_none(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        self.assertIn(ws.BACKUP_KEY, data)
        self.assertIsNone(data[ws.BACKUP_KEY])

    def test_uninstall_removes_statusline_when_no_prior_existed(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertIsNone(_read(self.settings)[ws.BACKUP_KEY])
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.root])
        data = _read(self.settings)
        self.assertNotIn("statusLine", data)
        self.assertNotIn(ws.BACKUP_KEY, data)
        self.assertNotIn(ws.OWNER_KEY, data)

    def test_settings_file_created_if_absent(self):
        absent = os.path.join(self.tmp.name, "other", "settings.json")
        os.makedirs(os.path.dirname(absent))
        ws.main(["install", "--settings", absent,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertTrue(os.path.isfile(absent))


class TestInstallWithPriorThirdParty(_WireStatuslineTest):
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

    def test_reinstall_then_uninstall_preserves_the_prior_statusline(self):
        for action in ("install", "install"):
            ws.main([action, "--settings", self.settings,
                "--plugin-root", self.root, "--interp", "python"])
        self.assertEqual(_read(self.settings)[ws.BACKUP_KEY]["command"], self.prior_cmd)
        ws.main(["uninstall", "--settings", self.settings,
            "--plugin-root", self.root])
        self.assertEqual(_read(self.settings)["statusLine"]["command"], self.prior_cmd)

    def test_prior_line_backed_up(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        backup = data.get(ws.BACKUP_KEY)
        self.assertIsNotNone(backup)
        backed_cmd = backup.get("command") if isinstance(backup, dict) else backup
        self.assertEqual(backed_cmd, self.prior_cmd)

    def test_statusline_filename_alone_is_unowned_and_backed_up_exactly(self):
        prior = {
            "type": "command",
            "command": '"python" "C:\\tools\\statusline.py" --theme ca',
            "padding": 7,
            "extra": {"preserve": True},
        }
        spath = _make_settings(self.tmp.name, {"statusLine": prior})
        ws.main(["install", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertEqual(_read(spath)[ws.BACKUP_KEY], prior)

    def test_install_reinstall_user_takeover_and_restore_preserves_whole_settings(self):
        def command():
            return '"python" "' + os.path.realpath(os.path.join(self.root, "hooks", "statusline.py")) + '"'

        def invoke(action):
            with contextlib.redirect_stdout(io.StringIO()):
                ws.main([action, "--settings", self.settings,
                         "--plugin-root", self.root, "--interp", "python"])

        prior_line = {"type": "command", "command": "original-line --theme", "padding": 7,
                      "extra": {"keep": [1, 2]}}
        prior_spinner = {"mode": "append", "verbs": ["original-spinner"]}
        original = {"statusLine": prior_line, "spinnerVerbs": prior_spinner, "theme": "fixture-theme",
                    "nested": {"unchanged": [1, True, None]}}
        spinner = copy.deepcopy(ws.ARBITER_SPINNER_VERBS)
        self.settings = _make_settings(self.tmp.name, copy.deepcopy(original))
        invoke("install")
        expected = copy.deepcopy(original)
        expected.update(statusLine={"type": "command", "command": command(), "padding": 0},
                        spinnerVerbs=spinner)
        expected[ws.BACKUP_KEY] = copy.deepcopy(prior_line)
        expected[ws.OWNER_KEY] = command()
        expected[ws.SPINNER_BACKUP_KEY] = copy.deepcopy(prior_spinner)
        expected[ws.SPINNER_OWNER_KEY] = copy.deepcopy(spinner)
        self.assertEqual(_read(self.settings), expected)

        old_command = command()
        self.root = _make_plugin_root(os.path.join(self.tmp.name, "second-durable-version"))
        self.assertNotEqual(command(), old_command)
        invoke("install")
        expected["statusLine"] = {"type": "command", "command": command(), "padding": 0}
        expected[ws.OWNER_KEY] = command()
        self.assertEqual(_read(self.settings), expected)

        user_line = {"type": "command", "command": "new-user-line", "padding": 11,
                     "extra": {"new": True}}
        user_spinner = {"mode": "append", "verbs": ["new-user-spinner"]}
        user = copy.deepcopy(expected)
        user["statusLine"] = copy.deepcopy(user_line)
        user["spinnerVerbs"] = copy.deepcopy(user_spinner)
        self.settings = _make_settings(self.tmp.name, user)
        raw = _read_bytes(self.settings)
        invoke("refresh")
        self.assertEqual(_read_bytes(self.settings), raw)
        self.assertEqual(_read(self.settings), user)

        invoke("install")
        takeover = copy.deepcopy(user)
        takeover.update(statusLine={"type": "command", "command": command(), "padding": 0},
                        spinnerVerbs=spinner)
        takeover[ws.BACKUP_KEY] = copy.deepcopy(user_line)
        takeover[ws.OWNER_KEY] = command()
        takeover[ws.SPINNER_BACKUP_KEY] = copy.deepcopy(user_spinner)
        takeover[ws.SPINNER_OWNER_KEY] = copy.deepcopy(spinner)
        self.assertEqual(_read(self.settings), takeover)
        invoke("uninstall")
        restored = copy.deepcopy(original)
        restored["statusLine"] = user_line
        restored["spinnerVerbs"] = user_spinner
        self.assertEqual(_read(self.settings), restored)


class TestUninstall(_WireStatuslineTest):
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

    def test_restores_exact_third_party_statusline_setting(self):
        prior = {
            "type": "command",
            "command": '"python" "/opt/acme/statusline.py" --label codearbiter/ca/2.0.1/hooks/statusline.py',
            "padding": 9,
            "extra": ["unchanged", 3],
        }
        spath = _make_settings(self.tmp.name, {"statusLine": prior})
        ws.main(["install", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", self.root])
        self.assertEqual(_read(spath)["statusLine"], prior)

    def test_prior_refresh_interval_round_trips_and_ours_adds_none(self):
        # Spec D-13 / AC-28: accounting correctness adds no periodic refresh; a
        # user's own refreshInterval survives install/uninstall byte-for-byte.
        self.assertNotIn("refreshInterval", ws.owned_statusline("x"))
        prior = {"type": "command", "command": "third-party --tick", "refreshInterval": 7}
        spath = _make_settings(self.tmp.name, {"statusLine": prior})
        ws.main(["install", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertNotIn("refreshInterval", _read(spath)["statusLine"])
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", self.root])
        self.assertEqual(_read(spath)["statusLine"], prior)

    def test_source_reinstall_preserves_original_backup_through_uninstall(self):
        prior = {"type": "command", "command": "third-party --exact", "padding": 6}
        spath = _make_settings(self.tmp.name, {"statusLine": prior})
        ws.main(["install", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        source_root = _make_source_plugin_root(self.tmp.name)
        self.root = source_root
        ws.main(["install", "--settings", spath,
                 "--plugin-root", source_root, "--interp", "python"])
        installed = _read(spath)
        self.assertEqual(installed[ws.BACKUP_KEY], prior)
        self.assertEqual(installed.get(ws.OWNER_KEY), installed["statusLine"]["command"])
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", source_root])
        restored = _read(spath)
        self.assertEqual(restored["statusLine"], prior)
        self.assertNotIn(ws.OWNER_KEY, restored)

    def test_legacy_backup_without_owner_preserves_later_third_party_statusline(self):
        absent = object()
        replacements = ({"type": "command", "command": "new-user-line", "padding": 4},
                        "new-user-string-line", None, absent)
        old_spinner = {"mode": "append", "verbs": ["old user spinner"]}
        new_spinner = {"mode": "append", "verbs": ["new user spinner"]}
        for replacement in replacements:
            for spinner in ("none", "owned", "replaced"):
                with self.subTest(replacement=replacement, spinner=spinner):
                    content = {ws.BACKUP_KEY: {"type": "command", "command": "stale-old-line"},
                               "theme": "user-theme", "nested": {"keep": [1, True, None]}}
                    if replacement is not absent:
                        content["statusLine"] = replacement
                    if spinner != "none":
                        content.update({"spinnerVerbs": ws.ARBITER_SPINNER_VERBS if spinner == "owned" else new_spinner,
                            ws.SPINNER_OWNER_KEY: ws.ARBITER_SPINNER_VERBS,
                            ws.SPINNER_BACKUP_KEY: old_spinner})
                    spath = _make_settings(self.tmp.name, content)
                    ws.main(["uninstall", "--settings", spath, "--plugin-root", self.root])
                    actual = _read(spath)
                    expected = {"theme": "user-theme", "nested": {"keep": [1, True, None]}}
                    if replacement is not absent:
                        expected["statusLine"] = replacement
                    if spinner != "none":
                        expected["spinnerVerbs"] = old_spinner if spinner == "owned" else new_spinner
                    self.assertEqual(actual, expected,
                        "legacy backup is not evidence of ownership of a later user choice")
                    before = _read_bytes(spath)
                    ws.main(["uninstall", "--settings", spath, "--plugin-root", self.root])
                    self.assertEqual(_read_bytes(spath), before, "settled uninstall must be idempotent")

    def test_legacy_owned_statusline_without_stamp_still_restores_backup(self):
        commands = ('python "' + os.path.join(self.root, "hooks", "statusline.py") + '"',
                    '"python" "C:\\src\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"')
        prior = {"type": "command", "command": "exact-prior", "extra": [1, None]}
        for command in commands:
            for current in (command, {"type": "command", "command": command}):
                with self.subTest(command=command, current=current):
                    spath = _make_settings(self.tmp.name, {"statusLine": current,
                        ws.BACKUP_KEY: prior, "keep": {"nested": True}})
                    ws.main(["uninstall", "--settings", spath, "--plugin-root", self.root])
                    self.assertEqual(_read(spath), {"statusLine": prior, "keep": {"nested": True}})

    def test_stamped_owner_mismatch_preserves_recognizable_legacy_replacement(self):
        replacement = {"type": "command", "command": '"python" "C:\\src\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"'}
        spath = _make_settings(self.tmp.name, {"statusLine": replacement,
            ws.OWNER_KEY: "different-owned-command", ws.BACKUP_KEY: "old-line", "keep": 7})
        ws.main(["uninstall", "--settings", spath, "--plugin-root", self.root])
        self.assertEqual(_read(spath), {"statusLine": replacement, "keep": 7})

    def test_stale_owner_marker_never_overwrites_user_replacement(self):
        owned = '"python" "C:\\source\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"'
        replacement = {"type": "command", "command": "user-new-line", "padding": 4}
        original = {"type": "command", "command": "user-old-line"}
        spath = _make_settings(self.tmp.name, {
            "statusLine": replacement,
            ws.OWNER_KEY: owned,
            ws.BACKUP_KEY: original,
        })
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", self.root])
        data = _read(spath)
        self.assertEqual(data["statusLine"], replacement)
        self.assertNotIn(ws.OWNER_KEY, data)
        self.assertNotIn(ws.BACKUP_KEY, data)


class TestLegacySourceMigration(_WireStatuslineTest):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        self.legacy = '"python" "C:\\src\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"'
        self.prior = {
            "type": "command",
            "command": '"node" "C:\\custom\\line.js" --theme exact',
            "padding": 8,
            "extra": {"keep": [1, 2]},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _settings(self, backup=True):
        content = {"statusLine": {"type": "command", "command": self.legacy}}
        if backup:
            content[ws.BACKUP_KEY] = self.prior
        return _make_settings(self.tmp.name, content)

    def _assert_migrated_then_restored(self, action):
        spath = self._settings()
        ws.main([action, "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        migrated = _read(spath)
        self.assertEqual(migrated[ws.BACKUP_KEY], self.prior)
        self.assertEqual(migrated[ws.OWNER_KEY], migrated["statusLine"]["command"])
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", self.root])
        self.assertEqual(_read(spath)["statusLine"], self.prior)

    def test_install_migrates_without_replacing_original_backup(self):
        self._assert_migrated_then_restored("install")

    def test_refresh_migrates_without_replacing_original_backup(self):
        self._assert_migrated_then_restored("refresh")

    def test_old_source_install_with_none_backup_is_owned(self):
        spath = self._settings(backup=False)
        ws.main(["install", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(spath)
        self.assertNotIn(ws.BACKUP_KEY, data)
        self.assertEqual(data[ws.OWNER_KEY], data["statusLine"]["command"])
        ws.main(["uninstall", "--settings", spath,
                 "--plugin-root", self.root])
        self.assertNotIn("statusLine", _read(spath))

    def test_legacy_source_and_cache_reinstall_preserves_original_backup(self):
        variants = {
            "source": '"python" "C:\\src\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"',
            "cache": '"python" "C:\\Users\\fixture\\.claude\\plugins\\cache\\codearbiter\\ca\\1.0.0\\hooks\\statusline.py"',
        }
        spinner = copy.deepcopy(ws.ARBITER_SPINNER_VERBS)
        command = '"python" "' + os.path.realpath(os.path.join(self.root, "hooks", "statusline.py")) + '"'
        for kind, legacy in variants.items():
            with self.subTest(kind=kind):
                prior = {"type": "command", "command": "original-" + kind, "padding": 8,
                         "extra": {"keep": [1, 2]}}
                original = {"statusLine": {"type": "command", "command": legacy},
                            ws.BACKUP_KEY: copy.deepcopy(prior), "spinnerVerbs": copy.deepcopy(spinner),
                            ws.SPINNER_OWNER_KEY: copy.deepcopy(spinner),
                            ws.SPINNER_BACKUP_KEY: {"mode": "append", "verbs": ["original-spinner"]},
                            "nested": {"preserve": kind}}
                self.settings = _make_settings(os.path.join(self.tmp.name, kind), copy.deepcopy(original))
                ws.main(["install", "--settings", self.settings,
                         "--plugin-root", self.root, "--interp", "python"])
                expected = copy.deepcopy(original)
                expected["statusLine"] = {"type": "command", "command": command, "padding": 0}
                expected[ws.OWNER_KEY] = command
                self.assertEqual(_read(self.settings), expected)

        foreign = {"type": "command", "command": '"python" "C:\\tools\\statusline.py"', "padding": 9,
                   "extra": {"foreign": True}}
        before = {"statusLine": foreign,
                  ws.BACKUP_KEY: {"type": "command", "command": "obsolete-backup"},
                  "spinnerVerbs": {"mode": "append", "verbs": ["current-spinner"]},
                  "nested": {"preserve": True}}
        self.settings = _make_settings(os.path.join(self.tmp.name, "near-match"), before)
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        expected = copy.deepcopy(before)
        expected[ws.BACKUP_KEY] = copy.deepcopy(foreign)
        expected[ws.OWNER_KEY] = command
        expected[ws.SPINNER_BACKUP_KEY] = copy.deepcopy(before["spinnerVerbs"])
        expected[ws.SPINNER_OWNER_KEY] = copy.deepcopy(spinner)
        expected["statusLine"] = {"type": "command", "command": command, "padding": 0}
        expected["spinnerVerbs"] = copy.deepcopy(spinner)
        self.assertEqual(_read(self.settings), expected)


class TestOwnershipDetection(unittest.TestCase):
    def test_recognizes_versioned_codearbiter_paths_with_windows_or_posix_quoting(self):
        owned = (
            '"C:\\Python\\python.exe" '
            '"C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.8.13\\hooks\\statusline.py"',
            "'/usr/bin/python3' '/home/me/.claude/plugins/cache/codearbiter/ca/2.7.0/hooks/statusline.py'",
        )
        for command in owned:
            with self.subTest(command=command):
                self.assertTrue(ws.is_ours({"type": "command", "command": command}))

    def test_rejects_filename_matches_and_signature_in_non_path_arguments(self):
        unowned = (
            '"python" "C:\\tools\\statusline.py"',
            'python /opt/acme/statusline.py --label codearbiter/ca/2.0.1/hooks/statusline.py',
            'python /opt/acme/statusline.py --note="uses /cache/codearbiter/ca/2.0.1/hooks/statusline.py"',
            'echo "codearbiter/ca/2.0.1/hooks/statusline.py"',
        )
        for command in unowned:
            with self.subTest(command=command):
                self.assertFalse(ws.is_ours({"type": "command", "command": command}))

    def test_requires_real_claude_plugin_cache_boundary(self):
        lookalike = 'python "/vendor/codearbiter/ca/2.8.13/hooks/statusline.py"'
        actual = 'python "/home/me/.claude/plugins/cache/codearbiter/ca/2.8.13/hooks/statusline.py"'
        self.assertFalse(ws.is_ours({"type": "command", "command": lookalike}))
        self.assertTrue(ws.is_ours({"type": "command", "command": actual}))

    def test_rejects_codex_cache_because_codex_has_no_statusline(self):
        command = 'python "/home/me/.claude/plugins/cache/codearbiter/ca-codex/0.2.4/hooks/statusline.py"'
        self.assertFalse(ws.is_ours({"type": "command", "command": command}))

    def test_posix_cache_signature_is_case_sensitive(self):
        commands = (
            'python "/home/me/.claude/plugins/cache/CodeArbiter/ca/2.8.13/hooks/statusline.py"',
            'PYTHON "/home/me/.claude/plugins/cache/codearbiter/ca/2.8.13/hooks/statusline.py"',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(ws.is_ours({"type": "command", "command": command}))

    def test_windows_cache_signature_is_case_insensitive(self):
        command = '"C:\\PYTHON\\PYTHON.EXE" "C:\\Users\\me\\.CLAUDE\\PLUGINS\\CACHE\\CODEARBITER\\CA\\2.8.13\\HOOKS\\STATUSLINE.PY"'
        self.assertTrue(ws.is_ours({"type": "command", "command": command}))


class TestIdempotentRefresh(_WireStatuslineTest):
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
        raw = _read_text(self.settings)
        self.assertEqual(raw.count(ws.BACKUP_KEY), 1)

    def test_second_install_statusline_still_ours(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        cmd = (data.get("statusLine") or {}).get("command", "")
        self.assertIn("statusline.py", cmd)


class TestCorruptedJson(_WireStatuslineTest):
    """Corrupted JSON input → aborts safely (no file written / overwritten)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        d = os.path.join(self.tmp.name, ".claude")
        os.makedirs(d, exist_ok=True)
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


class TestStatusSubcommand(_WireStatuslineTest):
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


class TestSpinnerVerbsFreshInstall(_WireStatuslineTest):
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


class TestSpinnerVerbsWithPriorCustomVerbs(_WireStatuslineTest):
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


class TestSpinnerVerbsUninstall(_WireStatuslineTest):
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


class TestSpinnerVerbsUninstallNoPrior(_WireStatuslineTest):
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


class TestSpinnerVerbsIdempotent(_WireStatuslineTest):
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
        raw = _read_text(self.settings)
        self.assertEqual(raw.count(ws.SPINNER_BACKUP_KEY), 1)

    def test_second_install_verbs_still_set(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        verbs = (data.get("spinnerVerbs") or {}).get("verbs", [])
        self.assertGreater(len(verbs), 0)


class TestSpinnerOwnershipIsExact(_WireStatuslineTest):
    """HW-05 (HOOK-F05): uninstall restored the pre-install spinnerVerbs
    backup whenever the backup key existed — even when the user had since set
    their OWN spinner — so uninstall clobbered a later user choice. The
    installed value is now stamped separately; uninstall restores only while
    the current value still equals that stamp."""

    PRIOR = {"mode": "replace", "verbs": ["Thinking", "Working"]}
    CUSTOM = {"mode": "append", "verbs": ["My own verb"]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _settings(self, content):
        self.settings = _make_settings(self.tmp.name, content)

    def _install(self):
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])

    def _uninstall(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ws.main(["uninstall", "--settings", self.settings,
                     "--plugin-root", self.root])
        return out.getvalue()

    def _set(self, **updates):
        data = _read(self.settings)
        data.update(updates)
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_install_stamps_the_exact_owned_value(self):
        self._settings({"spinnerVerbs": self.PRIOR})
        self._install()
        data = _read(self.settings)
        self.assertEqual(data[ws.SPINNER_OWNER_KEY], data["spinnerVerbs"])
        self.assertEqual(data[ws.SPINNER_BACKUP_KEY], self.PRIOR)

    def test_still_owned_uninstall_restores_previous_value(self):
        self._settings({"spinnerVerbs": self.PRIOR})
        self._install()
        self._uninstall()
        data = _read(self.settings)
        self.assertEqual(data.get("spinnerVerbs"), self.PRIOR)
        self.assertNotIn(ws.SPINNER_OWNER_KEY, data)
        self.assertNotIn(ws.SPINNER_BACKUP_KEY, data)

    def test_user_custom_spinner_after_install_survives_uninstall(self):
        """The audit clobber reproduction."""
        self._settings({"spinnerVerbs": self.PRIOR, "theme": "dark"})
        self._install()
        self._set(spinnerVerbs=self.CUSTOM)
        output = self._uninstall()
        data = _read(self.settings)
        self.assertEqual(data.get("spinnerVerbs"), self.CUSTOM)
        self.assertNotIn(ws.SPINNER_OWNER_KEY, data)
        self.assertNotIn(ws.SPINNER_BACKUP_KEY, data)
        self.assertEqual(data.get("theme"), "dark")
        self.assertIn("spinner ownership ended", output)

    def test_user_removed_spinner_after_install_is_not_recreated(self):
        self._settings({"spinnerVerbs": self.PRIOR})
        self._install()
        data = _read(self.settings)
        del data["spinnerVerbs"]
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self._uninstall()
        self.assertNotIn("spinnerVerbs", _read(self.settings))

    def test_reinstall_after_user_change_does_not_overwrite_silently_then_uninstall_restores_it(self):
        self._settings({})
        self._install()
        self._set(spinnerVerbs=self.CUSTOM)
        self._install()   # explicit re-install takes over WITH a fresh backup
        data = _read(self.settings)
        self.assertEqual(data[ws.SPINNER_BACKUP_KEY], self.CUSTOM)
        self._uninstall()
        self.assertEqual(_read(self.settings).get("spinnerVerbs"), self.CUSTOM)

    def test_legacy_backup_without_stamp_is_conservative(self):
        # Older installs wrote only the backup key. Restore only while the
        # current value is exactly the verbs codeArbiter installs.
        self._settings({"spinnerVerbs": ws.ARBITER_SPINNER_VERBS,
                        ws.SPINNER_BACKUP_KEY: self.PRIOR})
        self._uninstall()
        self.assertEqual(_read(self.settings).get("spinnerVerbs"), self.PRIOR)
        self._settings({"spinnerVerbs": self.CUSTOM,
                        ws.SPINNER_BACKUP_KEY: self.PRIOR})
        self._uninstall()
        data = _read(self.settings)
        self.assertEqual(data.get("spinnerVerbs"), self.CUSTOM)
        self.assertNotIn(ws.SPINNER_BACKUP_KEY, data)

    def test_repeated_uninstall_is_a_noop(self):
        self._settings({"spinnerVerbs": self.PRIOR, "keep": 1})
        self._install()
        self._uninstall()
        first = _read(self.settings)
        self._uninstall()
        self.assertEqual(_read(self.settings), first)

    def test_spinner_ownership_is_independent_of_statusline_replacement(self):
        self._settings({"spinnerVerbs": self.PRIOR})
        self._install()
        self._set(statusLine={"type": "command", "command": "other-statusline"})
        self._uninstall()
        data = _read(self.settings)
        self.assertEqual(data["statusLine"]["command"], "other-statusline")
        self.assertEqual(data.get("spinnerVerbs"), self.PRIOR)


class TestRefreshStalePathOnSessionStart(_WireStatuslineTest):
    """Regression (#fix): a ca-owned statusLine whose command points at an OLD
    plugin-version path must be REFRESHED to the current renderer path on its own
    — without a manual re-install. Previously nothing re-wired after a plugin
    update, so users kept running a stale (eventually-broken) statusline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        self.script_abs = os.path.realpath(
            os.path.join(self.root, "hooks", "statusline.py"))
        # A ca-owned line pinned to an OLD version dir (note: still 'ours' — the
        # MARKER 'statusline.py' is present — but a different absolute path).
        self.stale_cmd = (
            '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.0.1\\hooks\\statusline.py"')
        self.settings = _make_settings(
            self.tmp.name,
            {"statusLine": {"type": "command", "command": self.stale_cmd}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_stale_ours_path_is_refreshed(self):
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        cmd = (data.get("statusLine") or {}).get("command", "")
        self.assertIn(self.script_abs, cmd)
        self.assertNotIn("2.0.1", cmd)

    def test_refresh_does_not_rewrite_when_already_current(self):
        # First refresh brings it current; second must be a no-op (no churn): the
        # file mtime must not change on the second call.
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        import time
        mtime_before = os.path.getmtime(self.settings)
        time.sleep(0.05)
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertAlmostEqual(mtime_before, os.path.getmtime(self.settings), delta=0.02)

    def test_refresh_leaves_third_party_line_untouched(self):
        third = {"statusLine": {"type": "command", "command": "their-statusline --x"}}
        spath = _make_settings(self.tmp.name, third)
        ws.main(["refresh", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(spath)
        self.assertEqual(data["statusLine"]["command"], "their-statusline --x")

    def test_refresh_leaves_third_party_statusline_py_untouched(self):
        command = '"python" "C:\\tools\\statusline.py"'
        third = {"statusLine": {"type": "command", "command": command}}
        spath = _make_settings(self.tmp.name, third)
        ws.main(["refresh", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertEqual(_read(spath), third)

    def test_refresh_ignores_stale_owner_marker_after_user_replaces_line(self):
        old_owned = '"python" "C:\\source\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"'
        third_command = '"python" "C:\\tools\\statusline.py"'
        third = {
            ws.OWNER_KEY: old_owned,
            "statusLine": {"type": "command", "command": third_command},
        }
        spath = _make_settings(self.tmp.name, third)
        ws.main(["refresh", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        self.assertEqual(_read(spath), third)

    def test_refresh_migrates_legacy_cache_command_to_owner_marker(self):
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(self.settings)
        self.assertEqual(data[ws.OWNER_KEY], data["statusLine"]["command"])

    def test_refresh_does_not_wire_when_no_statusline(self):
        # refresh HEALS an existing ours-line; it must never wire a fresh line
        # where the user has none (that's what `install` is for).
        spath = _make_settings(self.tmp.name, {})
        ws.main(["refresh", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        data = _read(spath)
        self.assertNotIn("statusLine", data)

    def test_refresh_noop_when_renderer_missing(self):
        # Mid-update safety: if the current renderer (hooks/statusline.py) is not
        # present under the plugin root, refresh must NOT rewrite the pin to a path
        # that would 404 — leave settings.json untouched (no mtime churn).
        bare = os.path.join(self.tmp.name, "bareplugin")
        os.makedirs(os.path.join(bare, "hooks"))  # hooks/ but NO statusline.py
        self.root = bare
        import time
        mtime_before = os.path.getmtime(self.settings)
        time.sleep(0.05)
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", bare, "--interp", "python"])
        self.assertAlmostEqual(mtime_before, os.path.getmtime(self.settings), delta=0.02)
        self.assertEqual(_read(self.settings)["statusLine"]["command"], self.stale_cmd)

    def test_refresh_heals_bare_string_statusline(self):
        # is_ours() accepts a bare-string statusLine; the string-form branch of
        # refresh_if_stale must heal that shape too (not only dict-form).
        spath = _make_settings(
            self.tmp.name,
            {"statusLine": '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.0.1\\hooks\\statusline.py"'})
        ws.main(["refresh", "--settings", spath,
                 "--plugin-root", self.root, "--interp", "python"])
        sl = _read(spath).get("statusLine")
        cmd = sl.get("command") if isinstance(sl, dict) else sl
        self.assertIn(self.script_abs, cmd)
        self.assertNotIn("2.0.1", cmd)

    def test_refresh_preserves_spinner_backups_and_unrelated_settings(self):
        before = {"statusLine": {"type": "command", "command": self.stale_cmd},
                  ws.OWNER_KEY: self.stale_cmd,
                  ws.BACKUP_KEY: {"type": "command", "command": "prior-safe-line", "padding": 17},
                  "spinnerVerbs": {"mode": "replace", "verbs": ["custom-spinner"]},
                  ws.SPINNER_BACKUP_KEY: {"mode": "append", "verbs": ["prior-spinner"]},
                  ws.SPINNER_OWNER_KEY: {"mode": "replace", "verbs": ["old-owned-spinner"]},
                  "theme": "fixture-theme", "permissions": {"allow": ["inert-entry"]},
                  "nested": {"unchanged": [1, True, None]}}
        self.settings = _make_settings(self.tmp.name, copy.deepcopy(before))
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.root, "--interp", "python"])
        after = _read(self.settings)
        expected_command = ws.build_command("python", self.script_abs)
        expected = copy.deepcopy(before)
        expected["statusLine"] = ws.owned_statusline(expected_command)
        expected[ws.OWNER_KEY] = expected_command
        self.assertNotEqual(before["statusLine"], after["statusLine"])
        self.assertEqual(after, expected)


class TestNonDurableRootIsNeverPinned(_WireStatuslineTest):
    """Found in-session on 2026-07-25, after it broke the maintainer's
    statusline three times in one day.

    `~/.claude/settings.json` is GLOBAL and long-lived; a git-worktree plugin
    root is neither. Writing one into the other yields a statusline that
    renders nothing the moment the worktree is pruned — which is the entire
    point of a worktree.

    The guard lives HERE, in the producer, because every write to the pin flows
    through this module: `cmd_install`, `cmd_refresh`, AND
    `session-start.heal_statusline_wiring`, which calls `refresh_if_stale`
    directly. The two writing paths get DIFFERENT treatment, because their
    audiences differ:
      - `refresh` is AUTOMATIC (SessionStart) -> silent no-op, matching the
        surrounding degrade-silently contract.
      - `install` is EXPLICIT (a human ran /ca:statusline, or passed
        `--plugin-root <worktree>` by hand) -> LOUD refusal, because a silent
        no-op would leave that human believing it worked.
    Read-only and removal paths (`status`, `uninstall`) are never blocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.worktree_root = _make_worktree_plugin_root(self.tmp.name)
        self.durable_root = _make_plugin_root(self.tmp.name)
        self.root = self.worktree_root
        self.stale_cmd = (
            '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca'
            '\\2.0.1\\hooks\\statusline.py"')
        self.settings = _make_settings(
            self.tmp.name,
            {"statusLine": {"type": "command", "command": self.stale_cmd}})
        self.before = _read_bytes(self.settings)

    def tearDown(self):
        self.tmp.cleanup()

    # --- refresh: the automatic path (silent) ------------------------------

    def test_refresh_from_worktree_root_leaves_settings_byte_identical(self):
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.worktree_root, "--interp", "python"])
        self.assertEqual(_read_bytes(self.settings), self.before)

    def test_refresh_from_worktree_root_never_writes_a_worktree_path(self):
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.worktree_root, "--interp", "python"])
        with open(self.settings, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("worktrees", raw)
        self.assertEqual(json.loads(raw)["statusLine"]["command"], self.stale_cmd)

    def test_refresh_from_durable_root_still_heals(self):
        # NOT a feature kill-switch: a genuine plugin-cache update still
        # re-points the pin at the new version's renderer.
        self.root = self.durable_root
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", self.durable_root, "--interp", "python"])
        cmd = _read(self.settings)["statusLine"]["command"]
        expected = os.path.realpath(
            os.path.join(self.durable_root, "hooks", "statusline.py"))
        self.assertIn(expected, cmd)
        self.assertNotIn("2.0.1", cmd)

    def test_refresh_if_stale_declines_an_ephemeral_script_without_mutating(self):
        # The choke point session-start.heal_statusline_wiring calls DIRECTLY —
        # pinned separately from cmd_refresh so the heal cannot regress if
        # cmd_refresh is ever restructured.
        settings = {"statusLine": {"type": "command", "command": self.stale_cmd}}
        snapshot = json.dumps(settings, sort_keys=True)
        script = os.path.join(self.worktree_root, "hooks", "statusline.py")
        self.assertFalse(ws.refresh_if_stale(settings, script, "python"))
        self.assertEqual(json.dumps(settings, sort_keys=True), snapshot)

    def test_refresh_declines_a_linked_worktree_with_no_worktrees_segment(self):
        # The git signal earning its place: a worktree parked under an ordinary
        # name, which the lexical rule cannot see.
        root = os.path.join(self.tmp.name, "ca-feature")
        os.makedirs(os.path.join(root, "hooks"), exist_ok=True)
        open(os.path.join(root, "hooks", "statusline.py"), "w").close()
        with open(os.path.join(root, ".git"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write("gitdir: C:/Users/me/codeArbiter/.git/worktrees/ca-feature\n")
        self.root = root
        ws.main(["refresh", "--settings", self.settings,
                 "--plugin-root", root, "--interp", "python"])
        self.assertEqual(_read_bytes(self.settings), self.before)

    # --- install: the explicit path (loud) ---------------------------------

    def test_install_from_worktree_root_refuses_loudly(self):
        with self.assertRaises(SystemExit) as ctx:
            ws.main(["install", "--settings", self.settings,
                     "--plugin-root", self.worktree_root, "--interp", "python"])
        self.assertIn("REFUSING", str(ctx.exception))

    def test_install_from_worktree_root_leaves_settings_byte_identical(self):
        with contextlib.suppress(SystemExit):
            ws.main(["install", "--settings", self.settings,
                     "--plugin-root", self.worktree_root, "--interp", "python"])
        self.assertEqual(_read_bytes(self.settings), self.before)

    def test_install_from_durable_root_still_wires(self):
        self.root = self.durable_root
        ws.main(["install", "--settings", self.settings,
                 "--plugin-root", self.durable_root, "--interp", "python"])
        cmd = _read(self.settings)["statusLine"]["command"]
        expected = os.path.realpath(
            os.path.join(self.durable_root, "hooks", "statusline.py"))
        self.assertIn(expected, cmd)

    # --- read-only / removal: never blocked --------------------------------

    def test_uninstall_from_worktree_root_is_never_blocked(self):
        # Removal is always safe, and a user stuck with a worktree pin must be
        # able to get rid of it from wherever they happen to be.
        ws.main(["uninstall", "--settings", self.settings,
                 "--plugin-root", self.worktree_root])
        self.assertNotIn("statusLine", _read(self.settings))

    def test_status_from_worktree_root_still_reports_and_writes_nothing(self):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.worktree_root])
        self.assertIn("settings.json", captured.getvalue())
        self.assertEqual(_read_bytes(self.settings), self.before)


class TestPluginRootBoundary(_WireStatuslineTest):
    """An explicit path corroborates, never selects, the executing package."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        self.foreign_root = _make_plugin_root(
            os.path.join(self.tmp.name, "foreign"))
        self.settings = _make_settings(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_root_mismatch_is_rejected_before_wiring(self):
        # Mutation killed: returning --plugin-root directly permits this
        # executing adapter to wire any foreign executable path.
        with self.assertRaises(SystemExit) as caught:
            ws.main(["status", "--settings", self.settings,
                     "--plugin-root", self.foreign_root])
        self.assertIn("authenticated", str(caught.exception))

    def test_explicit_root_cannot_bypass_missing_adapter_boundary(self):
        # Mutation killed: an explicit root skips the authenticated executing
        # host and succeeds even when that host cannot establish its boundary.
        with mock.patch.object(
                ws._hooklib, "get_host",
                side_effect=ws.hostapi.PluginRootError("missing adapter boundary")):
            with self.assertRaises(ws.hostapi.PluginRootError):
                ws.main(["status", "--settings", self.settings,
                         "--plugin-root", self.root])

    def test_install_refusals_preserve_existing_settings(self):
        def snapshot(folder):
            return {p.relative_to(folder).as_posix(): None if p.is_dir() else p.read_bytes()
                    for p in sorted(folder.rglob("*"))}

        for kind in ("mismatched-root", "missing-adapter", "ephemeral-root", "missing-renderer",
                     "invalid-json", "unreadable-settings"):
            with self.subTest(kind=kind):
                folder = pathlib.Path(self.tmp.name, kind)
                folder.mkdir()
                self.root = _make_plugin_root(str(folder))
                self.settings = _make_settings(str(folder), {
                    "statusLine": {"type": "command", "command": "keep-line"},
                    "spinnerVerbs": {"mode": "append", "verbs": ["keep-spinner"]},
                    "nested": {"unchanged": [1, None]},
                })
                requested = self.root
                if kind == "mismatched-root":
                    requested = _make_plugin_root(str(folder / "foreign"))
                if kind == "ephemeral-root":
                    self.root = _make_worktree_plugin_root(str(folder))
                    requested = self.root
                if kind == "missing-renderer":
                    pathlib.Path(self.root, "hooks", "statusline.py").unlink()
                if kind == "invalid-json":
                    pathlib.Path(self.settings).write_bytes(b"{owned-invalid-json")
                before_bytes = _read_bytes(self.settings)
                before_tree = snapshot(folder)
                with contextlib.ExitStack() as stack:
                    expected_error = SystemExit
                    injected = None
                    if kind == "missing-adapter":
                        expected_error = ws.hostapi.PluginRootError
                        stack.enter_context(mock.patch.object(
                            ws._hooklib, "get_host", side_effect=expected_error("missing fixture boundary")))
                    if kind == "unreadable-settings":
                        expected_error = PermissionError
                        injected = stack.enter_context(mock.patch.object(
                            ws, "open", side_effect=PermissionError("owned read refusal"), create=True))
                    with self.assertRaises(expected_error):
                        ws.main(["install", "--settings", self.settings,
                                 "--plugin-root", requested, "--interp", "python"])
                    if injected is not None:
                        self.assertEqual(injected.call_count, 1)
                        self.assertEqual(pathlib.Path(injected.call_args.args[0]), pathlib.Path(self.settings))
                self.assertEqual(_read_bytes(self.settings), before_bytes)
                self.assertEqual(snapshot(folder), before_tree)


class TestSpinnerReleasedReaderRollback(_WireStatuslineTest):
    """HW-05: retain current data across the exact supported old reader."""

    RELEASED_READER = "ca-codex-v0.26.9@3f1bd13762ed9f25320e58907f9bf98a81128504"
    # Exact first-party core/pysrc/wire-statusline.py from this released commit.
    RELEASED_BLOB_SHA256 = "3ca9de6944a7911a126e1ae486c88a4c029b2684a7a24a3fa152f726f6cced92"
    RELEASED_FUNCTION_AST_SHA256 = "99dacd81e587cd91cc6c92ab4943c2ee45af0dad696788dd09ad05a25fab655c"
    RELEASED_FUNCTION_SOURCE_SHA256 = "5516122c7d4da79d2a24d13dd7822f3324b0c6895baf46eb59fc42ad42550f6b"
    LEGACY_BACKUP_KEY = "_codearbiterSpinnerVerbsBackup"
    RELEASED_UNINSTALL_SOURCE = 'def _uninstall_spinner_verbs(settings):\n    if SPINNER_BACKUP_KEY not in settings:\n        return\n    prior_sv = settings.pop(SPINNER_BACKUP_KEY)\n    if prior_sv is None:\n        settings.pop("spinnerVerbs", None)\n    else:\n        settings["spinnerVerbs"] = prior_sv'
    PRIOR = {"mode": "replace", "verbs": ["previous private spinner"]}
    CUSTOM = {"mode": "append", "verbs": ["new private user spinner"]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_plugin_root(self.tmp.name)
        self.settings = _make_settings(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, value):
        with open(self.settings, "w", encoding="utf-8") as stream:
            json.dump(value, stream)

    def _current(self, action):
        with contextlib.redirect_stdout(io.StringIO()):
            ws.main([action, "--settings", self.settings,
                     "--plugin-root", self.root, "--interp", "python"])

    def _released_uninstall(self, settings):
        import hashlib
        # Exact source bytes remain stable across Python AST schema versions.
        self.assertEqual(hashlib.sha256(self.RELEASED_UNINSTALL_SOURCE.encode()).hexdigest(),
                         self.RELEASED_FUNCTION_SOURCE_SHA256)
        namespace = {"__builtins__": {}, "SPINNER_BACKUP_KEY": self.LEGACY_BACKUP_KEY}
        exec(compile(self.RELEASED_UNINSTALL_SOURCE, "<ca-codex-v0.26.9-pure-spinner-reader>", "exec"), namespace)
        namespace["_uninstall_spinner_verbs"](settings)

    def test_released_reader_cannot_restore_over_new_user_spinner(self):
        self._write({"spinnerVerbs": self.PRIOR, "theme": "private-theme",
                     "nested": {"keep": [1, True, None]}})
        self._current("install")
        installed = _read(self.settings)
        self.assertEqual(installed[ws.SPINNER_BACKUP_KEY], self.PRIOR)
        self.assertEqual(installed[ws.SPINNER_OWNER_KEY], installed["spinnerVerbs"])
        installed["spinnerVerbs"] = self.CUSTOM
        installed["nested"]["later_user_choice"] = {"keep": "current"}
        self._write(installed)
        before = _read(self.settings)
        changed = _read(self.settings)
        self._released_uninstall(changed)
        self._write(changed)
        after = _read(self.settings)
        self.rollback_readback = {"before": before, "after": after}
        self.assertEqual(after["spinnerVerbs"], self.CUSTOM,
                         "released rollback reader restored an older spinner over the later user choice")
        self.assertEqual(after[ws.SPINNER_BACKUP_KEY], self.PRIOR,
                         "rollback must retain current backup metadata")
        self.assertEqual(after[ws.SPINNER_OWNER_KEY], before[ws.SPINNER_OWNER_KEY])
        self.assertEqual(after, before, "rollback reader must leave current settings and metadata intact")

    def test_literal_legacy_backup_migration_preserves_custom_and_unrelated_values(self):
        for label, current, expected in (
                ("owned", ws.ARBITER_SPINNER_VERBS, self.PRIOR),
                ("user-custom", self.CUSTOM, self.CUSTOM)):
            with self.subTest(state=label):
                unrelated = {"statusLine": {"type": "command", "command": "private-user-line"},
                             "theme": "private-theme", "nested": {"keep": [1, True, None]}}
                self._write(dict(unrelated, spinnerVerbs=current,
                                 **{self.LEGACY_BACKUP_KEY: self.PRIOR}))
                self._current("uninstall")
                after = _read(self.settings)
                self.assertEqual(after["spinnerVerbs"], expected)
                self.assertNotIn(self.LEGACY_BACKUP_KEY, after)
                self.assertEqual(after, dict(unrelated, spinnerVerbs=expected))

    def test_malformed_backup_metadata_never_grants_ownership_of_custom_spinner(self):
        malformed = (
            ("legacy", {self.LEGACY_BACKUP_KEY: "not-a-spinner-object"}),
            ("stamped", {ws.SPINNER_BACKUP_KEY: {"verbs": True},
                         ws.SPINNER_OWNER_KEY: ["not-an-owned-spinner-object"]}),
        )
        for label, metadata in malformed:
            with self.subTest(state=label):
                unrelated = {"statusLine": {"type": "command", "command": "private-user-line"},
                             "theme": "private-theme", "nested": {"keep": [1, True, None]}}
                self._write(dict(unrelated, spinnerVerbs=self.CUSTOM, **metadata))
                self._current("uninstall")
                after = _read(self.settings)
                self.assertEqual(after["spinnerVerbs"], self.CUSTOM)
                for key, value in unrelated.items():
                    self.assertEqual(after[key], value)


    def test_owned_refresh_protects_legacy_backup_from_released_reader(self):
        script = os.path.join(self.root, "hooks", "statusline.py")
        desired = ws.build_command("python", script)
        old_root = _make_plugin_root(os.path.join(self.tmp.name, "prior-durable-version"))
        stale = ws.build_command("python", os.path.join(old_root, "hooks", "statusline.py"))
        self.assertNotEqual(stale, desired)
        self.assertFalse(ws._durabilitylib.is_ephemeral_path(script))
        self.assertTrue(os.path.isfile(script))
        self.refresh_rollback_readbacks = []
        for label, command in (("stale-owned", stale), ("already-current-owned", desired)):
            with self.subTest(path_state=label):
                original = {"statusLine": ws.owned_statusline(command), ws.OWNER_KEY: command,
                            "spinnerVerbs": self.CUSTOM, self.LEGACY_BACKUP_KEY: self.PRIOR,
                            "theme": "private-theme", "nested": {"keep": [1, True, None]}}
                self.assertNotIn(ws.SPINNER_OWNER_KEY, original)
                self._write(original)
                loaded = _read(self.settings)
                self.assertTrue(ws.is_ours(loaded["statusLine"], loaded))
                # Exercise the shared mutation used directly by session-start,
                # persisting only its real changed flag, just like its callers.
                changed = ws.refresh_if_stale(loaded, script, "python")
                if changed:
                    ws.save_settings(self.settings, loaded)
                refreshed = _read(self.settings)
                self.assertEqual(refreshed["statusLine"], ws.owned_statusline(desired))
                self.assertEqual(refreshed[ws.OWNER_KEY], desired)
                self.assertEqual(refreshed["spinnerVerbs"], self.CUSTOM)
                self.assertEqual(refreshed[ws.SPINNER_BACKUP_KEY], self.PRIOR)
                before_old = _read(self.settings)
                after_old = _read(self.settings)
                self._released_uninstall(after_old)
                self._write(after_old)
                observed = _read(self.settings)
                self.refresh_rollback_readbacks.append({"path_state": label, "refresh_changed": changed,
                    "before_old_reader": before_old, "after_old_reader": observed})
                self.assertEqual(observed["spinnerVerbs"], self.CUSTOM,
                                 "released reader clobbered custom spinner after owned refresh")
                self.assertEqual(observed[ws.SPINNER_BACKUP_KEY], self.PRIOR)
                self.assertEqual(observed, before_old,
                                 "owned refresh must retain backup and unrelated settings across rollback")
                steady = _read(self.settings)
                self.assertFalse(ws.refresh_if_stale(steady, script, "python"))
                self.assertEqual(steady, observed, "current backup metadata must not cause repeated refresh writes")

    def test_mixed_backup_formats_refuse_writes_and_leave_refresh_inert(self):
        script = os.path.join(self.root, "hooks", "statusline.py")
        command = ws.build_command("python", script)
        original = {"statusLine": ws.owned_statusline(command), ws.OWNER_KEY: command,
                    "spinnerVerbs": self.CUSTOM, ws.SPINNER_BACKUP_KEY: self.PRIOR,
                    self.LEGACY_BACKUP_KEY: {"mode": "replace", "verbs": ["different prior"]},
                    "nested": {"keep": [1, True, None]}}
        self.assertNotEqual(ws.SPINNER_BACKUP_KEY, self.LEGACY_BACKUP_KEY)
        for action in ("install", "uninstall"):
            with self.subTest(action=action):
                self._write(original)
                before = _read_text(self.settings)
                with self.assertRaises(SystemExit):
                    self._current(action)
                self.assertEqual(_read_text(self.settings), before)
        loaded = _read(self.settings)
        self.assertFalse(ws.refresh_if_stale(loaded, script, "python"))
        self.assertEqual(loaded, original)
        before = _read_text(self.settings)
        self._current("refresh")
        self.assertEqual(_read_text(self.settings), before)

    def test_legacy_migration_keeps_foreign_and_ephemeral_refresh_inert(self):
        ephemeral = _make_worktree_plugin_root(os.path.join(self.tmp.name, "ephemeral"))
        for label, plugin, current in (
                ("foreign", self.root, {"type": "command", "command": "private-user-line"}),
                ("ephemeral", ephemeral, ws.owned_statusline(ws.build_command(
                    "python", os.path.join(ephemeral, "hooks", "statusline.py"))))):
            with self.subTest(boundary=label):
                self.root = plugin  # The fixture adapter must authenticate this executing root.
                original = {"statusLine": current, "spinnerVerbs": self.CUSTOM,
                            self.LEGACY_BACKUP_KEY: self.PRIOR, "keep": {"nested": True}}
                if label == "ephemeral":
                    original[ws.OWNER_KEY] = current["command"]
                self._write(original)
                before = _read_text(self.settings)
                loaded = _read(self.settings)
                self.assertFalse(ws.refresh_if_stale(loaded, os.path.join(
                    plugin, "hooks", "statusline.py"), "python"))
                self.assertEqual(loaded, original)
                with contextlib.redirect_stdout(io.StringIO()):
                    ws.main(["refresh", "--settings", self.settings,
                             "--plugin-root", plugin, "--interp", "python"])
                self.assertEqual(_read_text(self.settings), before)


if __name__ == "__main__":
    unittest.main()
