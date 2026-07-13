"""Focused tests for statusline palette selection and custom theme loading."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _colorlib
import _boxlib


class TestPaletteResolution(unittest.TestCase):
    def test_violet_is_the_unchanged_default(self):
        palette = _colorlib.resolve_palette()
        self.assertEqual(palette.accent_deep, _colorlib.RGB(108, 70, 180))
        self.assertEqual(palette.accent_mid, _colorlib.RGB(150, 92, 230))
        self.assertEqual(palette.accent_primary, _colorlib.RGB(178, 102, 255))
        self.assertEqual(palette.accent_bright, _colorlib.RGB(208, 140, 255))
        self.assertEqual(palette.gradient_from, _colorlib.RGB(120, 80, 200))
        self.assertEqual(palette.gradient_to, _colorlib.RGB(205, 140, 255))

    def test_every_builtin_is_complete_and_names_are_case_insensitive(self):
        for name in ("violet", "blue", "green", "amber", "mono"):
            lower = _colorlib.resolve_palette(name)
            upper = _colorlib.resolve_palette(name.upper())
            self.assertEqual(lower, upper)
            self.assertTrue(all(isinstance(value, _colorlib.RGB)
                                for value in lower.__dict__.values()))

    def test_unknown_theme_falls_back_to_violet(self):
        self.assertEqual(_colorlib.resolve_palette("ultraviolet"),
                         _colorlib.resolve_palette("violet"))

    def test_builtin_registry_rejects_mutation_and_resolver_stays_stable(self):
        violet = _colorlib.resolve_palette("violet")
        with self.assertRaises(TypeError):
            _colorlib.BUILTIN_PALETTES["violet"] = _colorlib.resolve_palette("blue")
        self.assertEqual(_colorlib.resolve_palette("violet"), violet)


class TestCustomPalette(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "theme.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, value):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    def test_complete_custom_palette(self):
        groups = {
            "accent": ("deep", "mid", "primary", "bright"),
            "text": ("muted", "normal", "on_accent"),
            "semantic": ("ok", "warn", "danger"),
            "gradient": ("from", "to"),
        }
        payload = {}
        channel = 1
        for group, keys in groups.items():
            payload[group] = {}
            for key in keys:
                payload[group][key] = f"#{channel:02x}{channel + 1:02x}{channel + 2:02x}"
                channel += 3
        self._write(payload)
        palette = _colorlib.resolve_palette("custom", self.path)
        self.assertEqual(palette.accent_deep, _colorlib.RGB(1, 2, 3))
        self.assertEqual(palette.gradient_to, _colorlib.RGB(34, 35, 36))

    def test_partial_custom_inherits_violet_and_ignores_bad_or_unknown_keys(self):
        self._write({"accent": {"primary": "#010203", "deep": "red", "extra": "#ffffff"},
                     "unknown": {"value": "#ffffff"}})
        palette = _colorlib.resolve_palette("custom", self.path)
        violet = _colorlib.resolve_palette("violet")
        self.assertEqual(palette.accent_primary, _colorlib.RGB(1, 2, 3))
        self.assertEqual(palette.accent_deep, violet.accent_deep)
        self.assertEqual(palette.semantic_ok, violet.semantic_ok)

    def test_bad_files_fail_fully_to_violet(self):
        violet = _colorlib.resolve_palette("violet")
        cases = (None, [], "not-an-object")
        for value in cases:
            self._write(value)
            self.assertEqual(_colorlib.resolve_palette("custom", self.path), violet)
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        self.assertEqual(_colorlib.resolve_palette("custom", self.path), violet)
        os.remove(self.path)
        self.assertEqual(_colorlib.resolve_palette("custom", self.path), violet)

    def test_oversized_file_is_rejected_before_json_parse(self):
        with open(self.path, "wb") as handle:
            handle.write(b" " * (_colorlib.MAX_THEME_BYTES + 1))
        with mock.patch("_colorlib.json.loads") as loads:
            self.assertEqual(_colorlib.resolve_palette("custom", self.path),
                             _colorlib.resolve_palette("violet"))
            loads.assert_not_called()

    def test_path_expands_environment_variables(self):
        self._write({"text": {"normal": "#abcdef"}})
        with mock.patch.dict(os.environ, {"THEME_HOME": self.tmp.name}):
            palette = _colorlib.resolve_palette("custom", "$THEME_HOME/theme.json")
        self.assertEqual(palette.text_normal, _colorlib.RGB(171, 205, 239))


class TestActivePaletteCompatibility(unittest.TestCase):
    def tearDown(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODEARBITER_THEME", None)
            os.environ.pop("CODEARBITER_THEME_FILE", None)
            importlib.reload(_colorlib)

    def test_reload_projects_environment_theme_to_legacy_exports(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "BLUE"}):
            mod = importlib.reload(_colorlib)
            self.assertEqual(mod.V2, mod.fg(*mod.ACTIVE_PALETTE.accent_primary))
            self.assertNotEqual(mod.V2, mod.fg(178, 102, 255))

    def test_custom_theme_file_is_not_touched_while_color_modules_import(self):
        theme_path = os.path.join(tempfile.gettempdir(), "must-not-open-theme.json")
        script = """
import builtins, importlib, os, sys
theme = os.environ['CODEARBITER_THEME_FILE']
real_open = builtins.open
real_getsize = os.path.getsize
def guarded_open(path, *args, **kwargs):
    if os.path.abspath(path) == os.path.abspath(theme):
        raise AssertionError('custom theme opened during import')
    return real_open(path, *args, **kwargs)
def guarded_getsize(path):
    if os.path.abspath(path) == os.path.abspath(theme):
        raise AssertionError('custom theme statted during import')
    return real_getsize(path)
builtins.open = guarded_open
os.path.getsize = guarded_getsize
for name in ('_colorlib', '_fmtlib', '_boxlib', '_segmentslib', 'statusline'):
    importlib.import_module(name)
"""
        env = dict(os.environ, PYTHONPATH=_HOOKS_DIR, CODEARBITER_THEME="custom",
                   CODEARBITER_THEME_FILE=theme_path)
        run = subprocess.run([sys.executable, "-c", script], text=True,
                             capture_output=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_box_fallback_defines_ansi_when_colorlib_import_is_partial(self):
        script = """
import importlib, sys, types
sys.modules['_colorlib'] = types.SimpleNamespace(RESET='')
boxlib = importlib.import_module('_boxlib')
box = boxlib.Box(20)
box.top('status')
assert isinstance(box.render(), str)
"""
        env = dict(os.environ, PYTHONPATH=_HOOKS_DIR)
        run = subprocess.run([sys.executable, "-c", script], text=True,
                             capture_output=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_custom_palette_activates_once_for_all_render_consumers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "theme.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"accent": {"deep": "#010203", "primary": "#040506",
                                       "bright": "#070809"},
                           "text": {"muted": "#0a0b0c", "normal": "#0d0e0f"},
                           "gradient": {"from": "#101112", "to": "#131415"}}, handle)
            script = """
import json, os, statusline as sl
payload = json.dumps({'model': {'display_name': 'Test'},
                      'context_window': {'used_percentage': 20}})
reads = 0
real_read = sl._colorlib._read_custom
def counted_read(path):
    global reads
    reads += 1
    return real_read(path)
sl._colorlib._read_custom = counted_read
out = sl.render(payload)
again = sl.render(payload)
if reads != 2:
    raise AssertionError('expected one custom theme read per render, got %d' % reads)
if out != again:
    raise AssertionError('repeated custom renders were not byte-stable')
box = sl._boxlib.Box(40)
box.top('status')
combined = out + box.render() + sl._fmtlib.sparkline([1, 2, 3]) \
           + sl._segmentslib.seg_pr({'pr': {'number': 1, 'state': 'merged'}})
required = [(1,2,3), (4,5,6), (7,8,9), (10,11,12), (13,14,15),
            (16,17,18), (19,20,21)]
missing = [rgb for rgb in required if sl.fg(*rgb) not in combined]
if missing:
    raise AssertionError('missing custom colors: %r' % (missing,))
if sl.V2 != sl._colorlib.V2 or sl._boxlib._V0 != sl._colorlib.V0 \
        or sl._fmtlib._V2 != sl._colorlib.V2 or sl._segmentslib.V2 != sl._colorlib.V2:
    raise AssertionError('consumers did not receive one coherent palette')
"""
            env = dict(os.environ, PYTHONPATH=_HOOKS_DIR, CODEARBITER_THEME="custom",
                       CODEARBITER_THEME_FILE=path, COLUMNS="80")
            run = subprocess.run([sys.executable, "-c", script], text=True,
                                 capture_output=True, env=env)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_concurrent_theme_switches_never_mix_consumer_palettes(self):
        import statusline as sl
        payload = json.dumps({"model": {"display_name": "Test"},
                              "context_window": {"used_percentage": 20}})
        real_activate = sl._colorlib.activate_palette
        activation_count = 0
        count_lock = threading.Lock()

        themes = {}

        def slow_activate(*args, **kwargs):
            nonlocal activation_count
            with count_lock:
                activation_count += 1
            palette = real_activate(themes[threading.current_thread().name])
            time.sleep(0.02)
            return palette

        outputs = []

        def worker(theme):
            themes[threading.current_thread().name] = theme
            outputs.append((theme, sl.render(payload)))

        with mock.patch.object(sl._colorlib, "activate_palette", side_effect=slow_activate):
            threads = [threading.Thread(target=worker, args=(theme,))
                       for theme in ("blue", "green", "blue", "green")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(activation_count, len(threads))
        blue = sl.fg(*sl._colorlib.BUILTIN_PALETTES["blue"].accent_primary)
        green = sl.fg(*sl._colorlib.BUILTIN_PALETTES["green"].accent_primary)
        expected = {"blue": blue, "green": green}
        unexpected = {"blue": green, "green": blue}
        self.assertTrue(all(expected[theme] in output and unexpected[theme] not in output
                            for theme, output in outputs))

    def test_gradient_defaults_to_active_palette_and_explicit_endpoints_win(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "green"}):
            mod = importlib.reload(_colorlib)
            themed = mod.gradient_h("ab", 2)
            explicit = mod.gradient_h("ab", 2, (1, 2, 3), (4, 5, 6))
            self.assertIn(mod.fg(*mod.ACTIVE_PALETTE.gradient_from), themed)
            self.assertIn(mod.fg(*mod.ACTIVE_PALETTE.gradient_to), themed)
            self.assertIn(mod.fg(1, 2, 3), explicit)
            self.assertIn(mod.fg(4, 5, 6), explicit)
            self.assertEqual(mod.vlen(themed), mod.vlen(explicit))

    def test_box_sheen_uses_active_palette_without_changing_width(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "green"}):
            mod = importlib.reload(_colorlib)
            boxlib = importlib.reload(_boxlib)
            box = boxlib.Box(40)
            box.top("status")
            rendered = box.render()
            self.assertIn(mod.fg(*mod.ACTIVE_PALETTE.gradient_to), rendered)
            self.assertNotIn(mod.fg(90, 60, 150), rendered)
            self.assertEqual(mod.vlen(rendered), 40)

    def test_violet_box_keeps_its_legacy_darker_sheen(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "violet"}):
            mod = importlib.reload(_colorlib)
            boxlib = importlib.reload(_boxlib)
            box = boxlib.Box(40)
            box.top("status")
            rendered = box.render()
            self.assertIn(mod.fg(90, 60, 150), rendered)
            self.assertIn(mod.fg(170, 110, 240), rendered)

    def test_no_color_makes_every_builtin_layout_byte_identical(self):
        renderer = os.path.join(_HOOKS_DIR, "statusline.py")
        payload = json.dumps({"session_id": "palette-layout-test",
                              "workspace": {"current_dir": self.tmp_path()},
                              "model": {"display_name": "Test"}})
        outputs = []
        for theme in ("violet", "blue", "green", "amber", "mono"):
            env = dict(os.environ, CODEARBITER_THEME=theme, NO_COLOR="1",
                       COLUMNS="80", CODEARBITER_STATUSLINE_WIDTH="80")
            run = subprocess.run([sys.executable, renderer], input=payload, text=True,
                                 capture_output=True, env=env, check=True)
            self.assertNotIn("\033[", run.stdout)
            outputs.append(run.stdout)
        self.assertTrue(all(output == outputs[0] for output in outputs[1:]))

    def test_empty_no_color_value_still_strips_all_sgr(self):
        renderer = os.path.join(_HOOKS_DIR, "statusline.py")
        payload = json.dumps({"session_id": "palette-empty-no-color",
                              "workspace": {"current_dir": self.tmp_path()},
                              "model": {"display_name": "Test"}})
        env = dict(os.environ, CODEARBITER_THEME="blue", NO_COLOR="",
                   COLUMNS="80", CODEARBITER_STATUSLINE_WIDTH="80")
        run = subprocess.run([sys.executable, renderer], input=payload, text=True,
                             capture_output=True, env=env, check=True)
        self.assertTrue(run.stdout)
        self.assertNotIn("\033[", run.stdout)

    @staticmethod
    def tmp_path():
        return tempfile.gettempdir()


if __name__ == "__main__":
    unittest.main()
