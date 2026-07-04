"""_configtuilib unit tests — capability truth tables, key decoding, launch
command construction, and the numbered-fallback flow end-to-end with injected
streams. No real terminal anywhere."""

import io
import json
import os
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HOOKS_DIR)
import _configlib  # noqa: E402
import _configtuilib as tui  # noqa: E402


class _Stream(io.StringIO):
    def __init__(self, text="", tty=False):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


class TestSupportsRaw(unittest.TestCase):
    def test_needs_both_ttys(self):
        self.assertFalse(tui.supports_raw(_Stream(tty=False), _Stream(tty=True), {}, "linux"))
        self.assertFalse(tui.supports_raw(_Stream(tty=True), _Stream(tty=False), {}, "linux"))

    def test_dumb_terminal_declines(self):
        self.assertFalse(tui.supports_raw(_Stream(tty=True), _Stream(tty=True),
                                          {"TERM": "dumb"}, "linux"))

    def test_native_platform_tty_accepts(self):
        # The per-key reader module always imports on its own platform
        # (termios on POSIX, msvcrt on Windows), so tty + sane TERM = raw.
        self.assertTrue(tui.supports_raw(_Stream(tty=True), _Stream(tty=True),
                                         {"TERM": "xterm"}, sys.platform))

    def test_stream_without_isatty_declines(self):
        class NoTty:
            pass
        self.assertFalse(tui.supports_raw(NoTty(), NoTty(), {}, "linux"))


class TestCanLaunch(unittest.TestCase):
    def test_truth_table(self):
        cases = [
            ({"TMUX": "/tmp/tmux-1"}, "linux", "tmux"),
            ({}, "darwin", "macos"),
            ({}, "win32", "windows"),
            ({"DISPLAY": ":0"}, "linux", "linux"),
            ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", "linux"),
            ({}, "linux", None),                      # headless SSH / container
            ({"TMUX": "x"}, "darwin", "tmux"),        # tmux beats a native window
        ]
        for environ, platform, want in cases:
            self.assertEqual(tui.can_launch(environ, platform), want, (environ, platform))


class TestLaunchCommand(unittest.TestCase):
    def test_tmux_splits(self):
        argv = tui.launch_command("tmux", "/x/configtool.py", {})
        self.assertEqual(argv[:2], ["tmux", "split-window"])
        self.assertIn("/x/configtool.py", argv[-1])

    def test_linux_honors_TERMINAL_then_falls_back(self):
        argv = tui.launch_command("linux", "/x/c.py", {"TERMINAL": "kitty"},
                                  which=lambda name: "/usr/bin/" + name)
        self.assertEqual(argv[0], "kitty")
        argv = tui.launch_command("linux", "/x/c.py", {},
                                  which=lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None)
        self.assertEqual(argv[0], "gnome-terminal")
        self.assertIn("--", argv)  # gnome-terminal takes --, not -e

    def test_linux_no_emulator_returns_none(self):
        self.assertIsNone(tui.launch_command("linux", "/x/c.py", {}, which=lambda n: None))

    def test_launch_degrades_to_instructions_when_headless(self):
        msg = tui.launch(__file__, environ={}, platform="linux")
        self.assertIn("run it yourself", msg)

    def test_launch_spawns_detached(self):
        calls = []
        msg = tui.launch("/x/c.py", environ={"TMUX": "y"}, platform="linux",
                         spawn=lambda argv: calls.append(argv))
        self.assertEqual(len(calls), 1)
        self.assertIn("tmux", msg)


class TestKeyDecode(unittest.TestCase):
    def _posix(self, chars):
        it = iter(chars)
        return tui.decode_posix(lambda: next(it))

    def test_posix_sequences(self):
        self.assertEqual(self._posix("\r"), "ENTER")
        self.assertEqual(self._posix("\n"), "ENTER")
        self.assertEqual(self._posix("q"), "q")
        self.assertEqual(self._posix("\x1b[A"), "UP")
        self.assertEqual(self._posix("\x1b[B"), "DOWN")
        self.assertEqual(self._posix("\x1b[C"), "RIGHT")
        self.assertEqual(self._posix("\x1b[D"), "LEFT")
        self.assertEqual(self._posix("\x1bx"), "ESC")

    def test_windows_sequences(self):
        def w(chars):
            it = iter(chars)
            return tui.decode_windows(lambda: next(it))
        self.assertEqual(w("\r"), "ENTER")
        self.assertEqual(w("\xe0H"), "UP")
        self.assertEqual(w("\x00P"), "DOWN")
        self.assertEqual(w("\x1b"), "ESC")
        self.assertEqual(w("k"), "k")


class TestFallbackPick(unittest.TestCase):
    def test_number_selects_blank_backs_out(self):
        out = _Stream()
        self.assertEqual(tui.pick(["a", "b"], "t", out, _Stream("2\n"), raw=False), 1)
        self.assertIsNone(tui.pick(["a", "b"], "t", out, _Stream("\n"), raw=False))
        self.assertIsNone(tui.pick(["a", "b"], "t", out, _Stream("q\n"), raw=False))

    def test_out_of_range_reprompts(self):
        out = _Stream()
        self.assertEqual(tui.pick(["a", "b"], "t", out, _Stream("9\n1\n"), raw=False), 0)


class TestRawPick(unittest.TestCase):
    def test_arrow_navigation_and_enter(self):
        keys = iter(["DOWN", "DOWN", "ENTER"])
        idx = tui.pick(["a", "b", "c"], "t", _Stream(), _Stream(), raw=True,
                       key_reader=lambda _stdin: next(keys))
        self.assertEqual(idx, 2)

    def test_wraps_and_quits(self):
        keys = iter(["UP", "q"])
        idx = tui.pick(["a", "b"], "t", _Stream(), _Stream(), raw=True,
                       key_reader=lambda _stdin: next(keys))
        self.assertIsNone(idx)


class TestInteractiveFlowFallback(unittest.TestCase):
    def test_end_to_end_set_via_numbered_menus(self):
        reg = _configlib.load_registry()
        groups = list(reg["groups"])
        babysit_menu = str(groups.index("babysit") + 1)
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                "user": os.path.join(tmp, "u", "settings.json"),
                "project": os.path.join(tmp, "p", ".claude", "settings.json"),
                "local": os.path.join(tmp, "p", ".claude", "settings.local.json"),
            }
            # group -> setting 1 (CODEARBITER_BABYSIT) -> value "on" (2)
            # -> scope user (1) -> confirm yes (1) -> back -> quit
            stdin = _Stream("%s\n1\n2\n1\n1\n\n\n" % babysit_menu)
            out = _Stream()
            writes = tui.run_interactive(reg, environ={}, paths=paths,
                                         stdin=stdin, stdout=out, raw=False)
            self.assertEqual(writes, 1)
            with open(paths["user"], encoding="utf-8") as f:
                self.assertEqual(json.load(f)["env"]["CODEARBITER_BABYSIT"], "on")
            self.assertIn("NEXT session start", out.getvalue())

    def test_sensitive_setting_shows_note_and_writes_nothing(self):
        reg = _configlib.load_registry()
        groups = list(reg["groups"])
        farm_menu = str(groups.index("farm") + 1)
        farm_names = [e["name"] for e in reg["settings"] if e["group"] == "farm"]
        key_menu = str(farm_names.index("FARM_API_KEY") + 1)
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                "user": os.path.join(tmp, "u", "settings.json"),
                "project": os.path.join(tmp, "p", ".claude", "settings.json"),
                "local": os.path.join(tmp, "p", ".claude", "settings.local.json"),
            }
            stdin = _Stream("%s\n%s\n\n\n" % (farm_menu, key_menu))
            out = _Stream()
            writes = tui.run_interactive(reg, environ={}, paths=paths,
                                         stdin=stdin, stdout=out, raw=False)
            self.assertEqual(writes, 0)
            self.assertIn("sensitive", out.getvalue())
            self.assertFalse(os.path.exists(paths["user"]))


if __name__ == "__main__":
    unittest.main()
