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

    def test_command_source_documents_the_gate_identifier_the_helper_accepts(self):
        # #1081: the command told the model to pass "<gate bypassed>", a description the
        # helper refuses. Pin the documented format and examples to GATE_RE.
        import re

        command = (HOOKS.parent / "commands" / "override.md").read_text(encoding="utf-8")
        flow = " ".join(command.split())
        self.assertIn("`--gate` takes a compact gate identifier", flow)
        examples = re.search(r"for example `([^`]+)` or `([^`]+)`", flow)
        self.assertIsNotNone(examples, "the --gate rule must give identifier examples")
        for example in examples.groups():
            with self.subTest(example=example):
                self.assertIsNotNone(appender.GATE_RE.fullmatch(example))
                result = self.run_helper("--gate", example, "--reason", "specific justification")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        placeholder = re.search(r'--gate "<([^>]+)>"', command).group(1)
        self.assertIsNotNone(appender.GATE_RE.fullmatch(placeholder),
                             f"placeholder <{placeholder}> must read as an identifier")

    def test_security_producers_are_documented_as_standalone_commands(self):
        command = (HOOKS.parent / "commands" / "override.md").read_text(
            encoding="utf-8")
        self.assertNotIn("PY=python3", command)
        producers = [line.strip() for line in command.splitlines()
                     if "/hooks/security-pass.py" in line]
        self.assertEqual(len(producers), 2, producers)
        for producer in producers:
            self.assertTrue(producer.startswith('python "'), producer)
            self.assertNotIn("$PY", producer)
        self.assertIn("--binary-override", producers[1])
        self.assertIn("one standalone command", command)

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

    def test_historical_carriage_return_is_preserved_while_new_row_is_appended(self):
        historical = b"first row\nlegacy row with stray CR\rinside\n"
        self.log.write_bytes(historical)

        result = self.run_helper("--gate", "H-05", "--reason", "specific justification")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        raw = self.log.read_bytes()
        self.assertTrue(raw.startswith(historical))
        self.assertEqual(raw[:len(historical)], historical)
        self.assertIn(b"BY: fixture@example.test | GATE: H-05", raw[len(historical):])

    def test_malformed_existing_log_variants_refuse_without_mutation(self):
        for raw in (b"\xef\xbb\xbfseed\n", b"seed\x00\n", b"\xff\n", b"unterminated"):
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

    def test_hardlinked_log_refuses_without_external_mutation(self):
        outside = self.root / "outside-hardlink"
        try:
            os.link(self.log, outside)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")
        before = outside.read_bytes()
        result = self.run_helper("--gate", "H-05", "--reason", "specific")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("single-link", result.stderr)
        self.assertEqual(self.log.read_bytes(), before)
        self.assertEqual(outside.read_bytes(), before)

    def test_special_file_type_is_rejected_before_any_content_read(self):
        fifo_mode = mock.Mock(st_mode=appender.stat.S_IFIFO)
        with mock.patch.object(appender.Path, "lstat", return_value=fifo_mode), \
             mock.patch.object(
                 appender.Path,
                 "read_bytes",
                 side_effect=AssertionError("special file content must not be read"),
             ):
            with self.assertRaisesRegex(appender.OverrideAppendError, "single-link"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)

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

    def test_identity_swap_after_open_refuses_before_append(self):
        handle = object()
        opened = self.log.lstat()
        replaced = mock.Mock(
            st_mode=opened.st_mode, st_nlink=1,
            st_dev=opened.st_dev, st_ino=opened.st_ino + 1,
            st_file_attributes=0,
        )
        with (mock.patch.object(appender, "_root", return_value=self.root),
              mock.patch.object(appender, "_identity",
                                return_value="test@example.com"),
              mock.patch.object(appender, "_validate_file_type",
                                return_value=opened),
              mock.patch.object(appender, "acquire_lock", return_value=handle),
              mock.patch.object(appender, "release_lock") as release,
              mock.patch.object(appender.os, "open", return_value=123),
              mock.patch.object(appender.os, "fstat", return_value=opened),
              mock.patch.object(appender.Path, "lstat", return_value=replaced),
              mock.patch.object(appender.os, "write") as write,
              mock.patch.object(appender.os, "close") as close):
            with self.assertRaisesRegex(
                    appender.OverrideAppendError, "changed identity"):
                appender.append_override(
                    gate="H-05", reason="specific", cwd=self.root)
        write.assert_not_called()
        close.assert_called_once_with(123)
        release.assert_called_once_with(handle)

    def test_zero_progress_write_and_close_failure_release_the_lock(self):
        handle = object()
        opened = self.log.lstat()
        with mock.patch.object(appender, "_root", return_value=self.root), \
             mock.patch.object(appender, "_identity", return_value="test@example.com"), \
             mock.patch.object(appender, "acquire_lock", return_value=handle), \
             mock.patch.object(appender, "release_lock") as release, \
             mock.patch.object(appender.os, "open", return_value=123), \
             mock.patch.object(appender.os, "fstat", return_value=opened), \
             mock.patch.object(appender.os, "write", return_value=0), \
             mock.patch.object(appender.os, "close"):
            with self.assertRaisesRegex(appender.OverrideAppendError, "made no progress"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)
        release.assert_called_once_with(handle)

        with mock.patch.object(appender, "_root", return_value=self.root), \
             mock.patch.object(appender, "_identity", return_value="test@example.com"), \
             mock.patch.object(appender, "acquire_lock", return_value=handle), \
             mock.patch.object(appender, "release_lock") as release, \
             mock.patch.object(appender.os, "open", return_value=123), \
             mock.patch.object(appender.os, "fstat", return_value=opened), \
             mock.patch.object(appender.os, "write", side_effect=lambda _fd, raw: len(raw)), \
             mock.patch.object(appender.os, "fsync"), \
             mock.patch.object(appender.os, "close", side_effect=OSError("close failed")):
            with self.assertRaisesRegex(OSError, "close failed"):
                appender.append_override(gate="H-05", reason="specific", cwd=self.root)
        release.assert_called_once_with(handle)


if __name__ == "__main__":
    unittest.main()
