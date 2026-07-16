#!/usr/bin/env python3
"""Unit tests for tools/sync-core.py — the canonical-core vendoring tool
(ADR-0011, codex-support M1).

Run: python .github/scripts/test_sync_core.py

Drives the tool against a synthetic REPO/core/pysrc + plugin tree in a temp
dir (module-level REPO/CORE/PLUGINS are monkeypatched per test), so every
property is provable without touching the real repo: successful vendoring,
--check pass/fail on in-sync/drifted/missing copies, write-mode drift repair,
and the hardened non-zero/clear-message error paths for an unreadable source
file, an unwritable destination, and an empty/missing core dir.

Stdlib only.
"""
import contextlib
import importlib.util
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "sync-core.py"

_spec = importlib.util.spec_from_file_location("sync_core", _TOOL)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

IS_WINDOWS = os.name == "nt"


def _write(root, rel, data):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    p.write_bytes(data)
    return p


class _SyntheticRepoFixture(unittest.TestCase):
    """Builds a synthetic REPO/core/pysrc + two plugin hooks/ dirs and points
    the module's REPO/CORE/PLUGINS at it for the duration of the test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        self.core = os.path.join(self.repo, "core", "pysrc")
        self.plugin_a = os.path.join("plugins", "ca", "hooks")
        self.plugin_b = os.path.join("plugins", "ca-codex", "hooks")
        os.makedirs(self.core)
        os.makedirs(os.path.join(self.repo, self.plugin_a))
        os.makedirs(os.path.join(self.repo, self.plugin_b))

        _write(self.core, "hostapi.py", "hostapi source\n")
        _write(self.core, "_hooklib.py", "hooklib source\n")

        self._patches = [
            mock.patch.object(S, "REPO", self.repo),
            mock.patch.object(S, "CORE", self.core),
            mock.patch.object(
                S,
                "load_host_descriptors",
                return_value=(
                    SimpleNamespace(hooks_dir=self.plugin_a),
                    SimpleNamespace(hooks_dir=self.plugin_b),
                ),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def vendored_path(self, plugin, name):
        return os.path.join(self.repo, plugin, name)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = S.main(argv)
        return rc, out.getvalue(), err.getvalue()


class TestSuccessfulSync(_SyntheticRepoFixture):
    def test_write_mode_vendors_byte_identical_copies(self):
        rc, out, err = self.run_main([])
        self.assertEqual(rc, 0)
        for plugin in (self.plugin_a, self.plugin_b):
            for name in ("hostapi.py", "_hooklib.py"):
                dst = self.vendored_path(plugin, name)
                self.assertTrue(os.path.isfile(dst))
                with open(dst, "rb") as f:
                    dst_bytes = f.read()
                with open(os.path.join(self.core, name), "rb") as f:
                    src_bytes = f.read()
                self.assertEqual(dst_bytes, src_bytes)

    def test_write_mode_reports_count(self):
        rc, out, err = self.run_main([])
        self.assertEqual(rc, 0)
        self.assertIn("4 file(s) written", out)  # 2 core files x 2 plugins


class TestCheckMode(_SyntheticRepoFixture):
    def test_check_passes_when_in_sync(self):
        self.run_main([])  # vendor first
        rc, out, err = self.run_main(["--check"])
        self.assertEqual(rc, 0)
        self.assertIn("OK", out)

    def test_check_fails_on_modified_vendored_copy(self):
        self.run_main([])
        modified = self.vendored_path(self.plugin_a, "hostapi.py")
        with open(modified, "wb") as f:
            f.write(b"drifted content\n")
        rc, out, err = self.run_main(["--check"])
        self.assertNotEqual(rc, 0)
        self.assertIn("hostapi.py", out)

    def test_check_fails_on_missing_vendored_file(self):
        self.run_main([])
        missing = self.vendored_path(self.plugin_b, "_hooklib.py")
        os.remove(missing)
        rc, out, err = self.run_main(["--check"])
        self.assertNotEqual(rc, 0)
        self.assertIn("_hooklib.py", out)

    def test_check_never_writes_when_drifted(self):
        # --check must be read-only: a drifted vendored copy is reported, not
        # silently repaired.
        self.run_main([])
        modified = self.vendored_path(self.plugin_a, "hostapi.py")
        with open(modified, "wb") as f:
            f.write(b"drifted content\n")
        self.run_main(["--check"])
        with open(modified, "rb") as f:
            self.assertEqual(f.read(), b"drifted content\n")


class TestWriteModeRepairsDrift(_SyntheticRepoFixture):
    def test_sync_repairs_a_drifted_copy(self):
        self.run_main([])
        modified = self.vendored_path(self.plugin_a, "hostapi.py")
        with open(modified, "wb") as f:
            f.write(b"drifted content\n")
        rc, out, err = self.run_main([])
        self.assertEqual(rc, 0)
        with open(os.path.join(self.core, "hostapi.py"), "rb") as f:
            src_bytes = f.read()
        with open(modified, "rb") as f:
            self.assertEqual(f.read(), src_bytes)
        # A verifying --check must now pass.
        rc2, out2, err2 = self.run_main(["--check"])
        self.assertEqual(rc2, 0)


class TestUnreadableSourceFile(_SyntheticRepoFixture):
    def test_unreadable_source_produces_clear_nonzero_error(self):
        bad_src = os.path.join(self.core, "hostapi.py")
        real_open = open

        def _boom_open(path, mode="r", *a, **kw):
            if os.path.abspath(path) == os.path.abspath(bad_src) and "r" in mode:
                raise OSError("simulated permission denied")
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", side_effect=_boom_open):
            rc, out, err = self.run_main([])
        self.assertNotEqual(rc, 0)
        self.assertIn("hostapi.py", err)
        # Must not have crashed with a raw traceback (assertion above already
        # proves run_main returned rather than propagating an exception, but
        # spell out the intent).
        self.assertNotIn("Traceback", err)

    @unittest.skipIf(IS_WINDOWS, "chmod-based unreadability is unreliable on Windows")
    def test_unreadable_source_via_real_permission_denial_posix(self):
        bad_src = os.path.join(self.core, "hostapi.py")
        os.chmod(bad_src, 0o000)
        try:
            if os.access(bad_src, os.R_OK):
                self.skipTest("running as a user that bypasses file permissions (e.g. root)")
            rc, out, err = self.run_main([])
            self.assertNotEqual(rc, 0)
            self.assertIn("hostapi.py", err)
        finally:
            os.chmod(bad_src, 0o644)


class TestUnwritableDestination(_SyntheticRepoFixture):
    def test_unwritable_destination_produces_clear_nonzero_error(self):
        dst_dir = os.path.join(self.repo, self.plugin_a)
        bad_dst = os.path.join(dst_dir, "hostapi.py")
        real_open = open

        def _boom_open(path, mode="r", *a, **kw):
            if os.path.abspath(path) == os.path.abspath(bad_dst) and "w" in mode:
                raise OSError("simulated write failure")
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", side_effect=_boom_open):
            rc, out, err = self.run_main([])
        self.assertNotEqual(rc, 0)
        self.assertIn("hostapi.py", err)
        self.assertNotIn("Traceback", err)


class TestEmptyOrMissingCoreDir(_SyntheticRepoFixture):
    def test_missing_core_dir_is_a_clear_nonzero_error(self):
        missing_core = os.path.join(self.repo, "core", "does-not-exist")
        with mock.patch.object(S, "CORE", missing_core):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    S.main([])
            self.assertNotEqual(cm.exception.code, 0)
            self.assertIn("does-not-exist", err.getvalue())

    def test_empty_core_dir_is_a_clear_nonzero_error(self):
        empty_core = os.path.join(self.repo, "core", "empty")
        os.makedirs(empty_core)
        with mock.patch.object(S, "CORE", empty_core):
            rc, out, err = self.run_main([])
        self.assertNotEqual(rc, 0)
        self.assertIn("no .py files found", err)


class TestArgvHandling(_SyntheticRepoFixture):
    def test_unknown_argument_is_a_clear_nonzero_error(self):
        rc, out, err = self.run_main(["--bogus"])
        self.assertNotEqual(rc, 0)
        self.assertIn("unknown argument", err)


if __name__ == "__main__":
    unittest.main()
