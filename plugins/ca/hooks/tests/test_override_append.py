"""Locked mandatory append contract for ordinary override records (#671)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HOOKS = Path(__file__).resolve().parents[1]
HELPER = HOOKS / "append-override.py"
sys.path.insert(0, str(HOOKS))
from _hooklib import acquire_lock, audit_lock_key, release_lock  # noqa: E402
import _overrideappendlib as appender  # noqa: E402


class LockedOverrideAppendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "--initial-branch=main"], cwd=self.root, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "fixture@example.test"],
                       cwd=self.root, check=True)
        self.log = self.root / ".codearbiter" / "overrides.log"
        self.log.parent.mkdir()
        self.log.write_bytes(b"# append-only overrides\n")

    def tearDown(self):
        self.temp.cleanup()

    def run_helper(self, *args):
        self.assertTrue(HELPER.is_file(), "locked override append helper is missing")
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
        )

    def test_ordinary_override_is_attributed_and_durably_appended(self):
        result = self.run_helper("--gate", "H-05", "--reason", "specific justification")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        raw = self.log.read_bytes()
        self.assertTrue(raw.startswith(b"# append-only overrides\n"))
        self.assertIn(b"BY: fixture@example.test | GATE: H-05", raw)
        self.assertIn(b"REASON: specific justification", raw)

    def test_lock_contention_refuses_without_mutation(self):
        before = self.log.read_bytes()
        holder = acquire_lock(audit_lock_key(self.root, self.log))
        self.assertIsNotNone(holder)
        try:
            result = self.run_helper("--gate", "H-05", "--reason", "specific justification")
        finally:
            release_lock(holder)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("audit path lock", result.stderr)
        self.assertEqual(self.log.read_bytes(), before)

    def test_security_override_uses_specific_finding_shape(self):
        result = self.run_helper(
            "--security-finding", "specific critical primitive",
            "--reason", "user acknowledged exact finding",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        raw = self.log.read_bytes()
        self.assertIn(b"SECURITY-OVERRIDE | FINDING: specific critical primitive", raw)
        self.assertIn(b"REASON: user acknowledged exact finding", raw)

    def test_invalid_fields_refuse_without_mutation(self):
        before = self.log.read_bytes()
        for args in (
            ("--gate", "bad|gate", "--reason", "specific"),
            ("--gate", "H-05", "--reason", "contains\nnewline"),
            ("--security-finding", "", "--reason", "specific"),
        ):
            with self.subTest(args=args):
                result = self.run_helper(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.log.read_bytes(), before)

    def test_malformed_existing_log_variants_refuse_without_mutation(self):
        for raw in (b"\xef\xbb\xbfseed\n", b"seed\r\n", b"seed\x00\n", b"\xff\n", b"unterminated"):
            with self.subTest(raw=raw):
                self.log.write_bytes(raw)
                result = self.run_helper("--gate", "H-05", "--reason", "specific")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.log.read_bytes(), raw)

    def test_missing_directory_and_symlink_logs_refuse_without_external_mutation(self):
        self.log.unlink()
        result = self.run_helper("--gate", "H-05", "--reason", "specific")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

        outside = self.root / "outside"
        outside.write_bytes(b"outside\n")
        try:
            os.symlink(outside, self.log)
        except OSError as error:
            self.skipTest(f"symlink unavailable: {error}")
        result = self.run_helper("--gate", "H-05", "--reason", "specific")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_bytes(), b"outside\n")

    def test_changed_after_validation_refuses_and_releases_lock(self):
        before = self.log.read_bytes()
        changed = before + b"concurrent official row\n"
        handle = object()
        with mock.patch.object(appender.Path, "read_bytes", side_effect=(before, changed)), \
             mock.patch.object(appender, "acquire_lock", return_value=handle), \
             mock.patch.object(appender, "release_lock") as release:
            with self.assertRaisesRegex(appender.OverrideAppendError, "changed during validation"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)
        release.assert_called_once_with(handle)
        self.assertEqual(self.log.read_bytes(), before)

    def test_zero_progress_write_and_close_failure_release_the_lock(self):
        handle = object()
        with mock.patch.object(appender, "acquire_lock", return_value=handle), \
             mock.patch.object(appender, "release_lock") as release, \
             mock.patch.object(appender.os, "open", return_value=123), \
             mock.patch.object(appender.os, "write", return_value=0), \
             mock.patch.object(appender.os, "close"):
            with self.assertRaisesRegex(appender.OverrideAppendError, "made no progress"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)
        release.assert_called_once_with(handle)

        with mock.patch.object(appender, "acquire_lock", return_value=handle), \
             mock.patch.object(appender, "release_lock") as release, \
             mock.patch.object(appender.os, "open", return_value=123), \
             mock.patch.object(appender.os, "write", side_effect=lambda _fd, raw: len(raw)), \
             mock.patch.object(appender.os, "fsync"), \
             mock.patch.object(appender.os, "close", side_effect=OSError("close failed")):
            with self.assertRaisesRegex(OSError, "close failed"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)
        release.assert_called_once_with(handle)


if __name__ == "__main__":
    unittest.main()
