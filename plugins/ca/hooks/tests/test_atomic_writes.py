"""Reliability hardening (issue #191): route bare open('w') writers through
_hooklib's atomic temp+os.replace primitive so a crash mid-write leaves the
PRIOR valid file intact instead of a torn/truncated one.

Covers:
  reliability-008 — _prunelib.save_state (global cross-session prune-state.json)
  reliability-010 — _githooks.install (git-hook shim write)
  reliability-009 — wire-statusline.save_settings (per-pid temp name) AND
                     session-start.heal_statusline_wiring (reload-before-save)

(reliability-016, _provenancelib.write_provenance, was already fixed in a
prior tribunal pass — see .github/scripts/test_provenancelib.py
WriteProvenanceAtomicTest — and is not re-covered here.)
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

import _githooks  # noqa: E402
import _prunelib as P  # noqa: E402
from _helpers import redirect_home, restore_home  # noqa: E402


# ---------------------------------------------------------------------------
# reliability-008 — _prunelib.save_state
# ---------------------------------------------------------------------------

class SaveStateAtomicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def test_crash_mid_write_leaves_previous_state_intact(self):
        P.save_state({"sess1": {"last_run_ts": 1}})
        self.assertEqual(P.load_state(), {"sess1": {"last_run_ts": 1}})

        # save_state is fail-open (best-effort): a crash mid-write must be
        # swallowed, never propagate and never break the caller's turn.
        with patch("os.replace", side_effect=OSError("simulated crash")):
            P.save_state({"sess1": {"last_run_ts": 2}})

        # The PRIOR, complete state must survive — never partially overwritten.
        self.assertEqual(P.load_state(), {"sess1": {"last_run_ts": 1}})

        # No stray .tmp file left behind in ~/.codearbiter/.
        d = os.path.dirname(P.state_path())
        leftovers = [n for n in os.listdir(d) if n != "prune-state.json"]
        self.assertEqual(leftovers, [], f"no temp file should linger: {leftovers}")

    def test_uses_atomic_write_primitive(self):
        """save_state must route through _hooklib.write_text_atomic, not a
        bare open('w') — proven by spying on the shared primitive."""
        calls = []
        orig = P._hooklib.write_text_atomic

        def spy(path, text, newline=None):
            calls.append(path)
            return orig(path, text, newline=newline)

        with patch.object(P._hooklib, "write_text_atomic", side_effect=spy):
            P.save_state({"a": 1})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], P.state_path())


# ---------------------------------------------------------------------------
# reliability-010 — _githooks.install
# ---------------------------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30, check=True)


class GitHooksInstallAtomicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "main"], self.root)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_crash_mid_write_leaves_prior_shim_intact(self):
        _githooks.install(self.root)
        dest = os.path.join(self.root, ".git", "hooks", "pre-commit")
        with open(dest, encoding="utf-8") as f:
            prior = f.read()
        self.assertIn(_githooks.SENTINEL, prior)

        # Force install() to actually attempt a REWRITE (not the idempotent
        # no-op skip) by pointing the enforcer at a different path, then crash
        # os.replace mid-install.
        with patch.object(_githooks, "_enforcer_path", return_value="/new/enforcer.py"):
            with patch("os.replace", side_effect=OSError("simulated crash")):
                _githooks.install(self.root)  # must not raise (caught internally)

        with open(dest, encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(after, prior,
                         "a crash mid-write must leave the PRIOR sentinel-bearing shim intact")
        self.assertIn(_githooks.SENTINEL, after,
                      "the surviving shim must still carry the sentinel (never a torn write)")

        hd = os.path.dirname(dest)
        leftovers = [n for n in os.listdir(hd)
                     if n not in ("pre-commit", "pre-push") and not n.endswith(".sample")]
        self.assertEqual(leftovers, [], f"no temp file should linger: {leftovers}")

    def test_crash_on_fresh_install_leaves_no_partial_shim(self):
        """No prior hook at all: a crash mid-write must leave NO file behind
        (never a sentinel-less partial the foreign-hook guard would then
        preserve forever)."""
        dest = os.path.join(self.root, ".git", "hooks", "pre-commit")
        self.assertFalse(os.path.exists(dest))
        with patch("os.replace", side_effect=OSError("simulated crash")):
            _githooks.install(self.root)
        self.assertFalse(os.path.exists(dest),
                         "a crashed fresh install must not leave a partial shim")


# ---------------------------------------------------------------------------
# reliability-009 — wire-statusline.save_settings: per-pid/unique temp name
# ---------------------------------------------------------------------------

def _load_wire_statusline():
    import importlib.util as ilu
    path = os.path.join(_HOOKS_DIR, "wire-statusline.py")
    spec = ilu.spec_from_file_location("wire_statusline_atomic_test", path)
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SaveSettingsAtomicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = os.path.join(self.tmp.name, ".claude")
        os.makedirs(d)
        self.settings = os.path.join(d, "settings.json")
        self.ws = _load_wire_statusline()

    def tearDown(self):
        self.tmp.cleanup()

    def test_does_not_stage_to_the_fixed_sibling_tmp_name(self):
        captured = {}
        real_replace = os.replace

        def spy(src, dst):
            captured["src"] = src
            return real_replace(src, dst)

        with patch("os.replace", side_effect=spy):
            self.ws.save_settings(self.settings, {"a": 1})
        fixed_name = self.settings + ".tmp"
        self.assertNotEqual(
            captured.get("src"), fixed_name,
            "save_settings must stage to a UNIQUE per-process temp file, "
            "not the fixed sibling .tmp name two concurrent writers could collide on")

    def test_crash_mid_write_leaves_prior_settings_intact(self):
        self.ws.save_settings(self.settings, {"a": 1})
        with patch("os.replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                self.ws.save_settings(self.settings, {"a": 2})
        with open(self.settings, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"a": 1})
        leftovers = [n for n in os.listdir(os.path.dirname(self.settings))
                     if n != os.path.basename(self.settings)]
        self.assertEqual(leftovers, [], f"no temp file should linger: {leftovers}")


# ---------------------------------------------------------------------------
# reliability-009 — session-start.heal_statusline_wiring: reload-before-save
# ---------------------------------------------------------------------------

import importlib.util as _ilu  # noqa: E402

_SS_SPEC = _ilu.spec_from_file_location(
    "session_start_atomic_test",
    os.path.join(_HOOKS_DIR, "session-start.py"))
_ss = _ilu.module_from_spec(_SS_SPEC)
_SS_SPEC.loader.exec_module(_ss)


class HealReloadBeforeSaveTest(unittest.TestCase):
    """The settings-heal must re-read settings.json immediately before saving
    and SKIP (never overwrite) when it changed since the initial load — the
    concurrent-session clobber this fix closes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = os.path.dirname(os.path.dirname(os.path.abspath(_ss.__file__)))
        d = os.path.join(self.tmp.name, ".claude")
        os.makedirs(d)
        self.settings = os.path.join(d, "settings.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, obj):
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)

    def _read(self):
        with open(self.settings, encoding="utf-8") as f:
            return json.load(f)

    def _stale_ours(self):
        return {"statusLine": {"type": "command",
                "command": '"python" "C:\\Users\\me\\.claude\\plugins\\cache\\codearbiter\\ca\\2.0.1\\hooks\\statusline.py"'}}

    def test_skips_when_settings_changed_between_load_and_save(self):
        self._write(self._stale_ours())

        real_ws = _ss._load_wire_statusline(self.plugin)
        calls = {"n": 0}
        orig_load = real_ws.load_settings

        concurrent = {"statusLine": {"type": "command", "command": "concurrent-writer --x"}}

        def flaky_load(path):
            calls["n"] += 1
            if calls["n"] == 1:
                return orig_load(path)
            # Simulate a concurrent writer's edit actually landing ON DISK
            # between our initial load and the reload-before-save check.
            with open(path, "w", encoding="utf-8") as f:
                json.dump(concurrent, f, indent=2)
            return copy.deepcopy(concurrent), True

        real_ws.load_settings = flaky_load
        save_calls = []
        orig_save = real_ws.save_settings

        def spy_save(path, data):
            save_calls.append(copy.deepcopy(data))
            return orig_save(path, data)

        real_ws.save_settings = spy_save

        changed = _ss.heal_statusline_wiring(
            self.plugin, settings_path=self.settings, interp="python",
            loader=lambda _p: real_ws)

        self.assertFalse(changed, "heal must skip when settings changed underneath it")
        self.assertEqual(save_calls, [],
                         "save_settings must never be called on a detected concurrent change")
        self.assertGreaterEqual(calls["n"], 2,
                                "heal must reload settings.json before saving")
        # The concurrent writer's edit must survive completely untouched.
        on_disk = self._read()
        self.assertEqual(on_disk["statusLine"]["command"], "concurrent-writer --x")

    def test_saves_when_unchanged_between_load_and_save(self):
        self._write(self._stale_ours())
        changed = _ss.heal_statusline_wiring(
            self.plugin, settings_path=self.settings, interp="python")
        self.assertTrue(changed)
        cmd = self._read()["statusLine"]["command"]
        self.assertNotIn("2.0.1", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
