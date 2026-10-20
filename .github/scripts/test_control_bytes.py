#!/usr/bin/env python3
"""Tests for check_control_bytes.py."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_control_bytes as check  # noqa: E402


def _repo(files: dict[str, bytes]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ca-ctl-"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


class ControlBytes(unittest.TestCase):
    def test_clean_text_with_tab_cr_lf_passes(self):
        root = _repo({"a.py": b"x = 1\r\n\tif x:\n    pass\n"})
        self.assertEqual(check.main([str(root)]), 0)

    def test_every_disallowed_byte_is_reported(self):
        # NUL marks a file binary; the binary tests below cover it.
        for byte in sorted(check.CONTROL - {0}):
            with self.subTest(byte=byte):
                root = _repo({"a.py": b"ok\nbad " + bytes([byte]) + b"\n"})
                self.assertEqual(check.findings(root, "a.py"),
                                 [f"a.py:2:5: control byte 0x{byte:02x}"])
                self.assertEqual(check.main([str(root)]), 1)

    def test_allowed_set_is_exactly_tab_lf_cr(self):
        self.assertEqual(set(range(0x20)) | {0x7F}, check.CONTROL | {0x09, 0x0A, 0x0D})
        self.assertNotIn(0x09, check.CONTROL)

    def test_binary_file_is_skipped(self):
        root = _repo({"img.bin": b"\x89PNG\x00\x01\x02\x08"})
        self.assertEqual(check.main([str(root)]), 0)

    def test_nul_past_the_probe_is_text(self):
        root = _repo({"late.txt": b"a" * check.BINARY_PROBE + b"\x00\x08"})
        self.assertEqual(check.main([str(root)]), 1)

    def test_symlink_and_gitlink_entries_are_not_read(self):
        root = _repo({"a.py": b"ok\n"})
        blob = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                              input=b"target\x08", stdout=subprocess.PIPE,
                              check=True).stdout.decode().strip()
        head = "0123456789abcdef0123456789abcdef01234567"
        for info in (f"120000,{blob},link", f"160000,{head},sub"):
            subprocess.run(["git", "-C", str(root), "update-index", "--add",
                            "--cacheinfo", info], check=True)
        (root / "sub").mkdir()
        self.assertEqual(check.tracked_files(root), ["a.py"])
        self.assertEqual(check.main([str(root)]), 0)

    def test_non_utf8_pathname_is_listed_not_fatal(self):
        root = _repo({"a.py": b"ok\n"})
        blob = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                              input=b"ok\n", stdout=subprocess.PIPE,
                              check=True).stdout.decode().strip()
        # An index entry whose name is not valid UTF-8 (Latin-1 "caf\xe9").
        subprocess.run(["git", "-C", str(root), "update-index", "--add", "--index-info"],
                       input=b"100644 " + blob.encode() + b"\tcaf\xe9.txt\n", check=True)
        names = check.tracked_files(root)
        self.assertIn("a.py", names)
        self.assertEqual(len(names), 2)
        self.assertIn("caf\udce9.txt", names)
        self.assertEqual(check.main([str(root)]), 0)

    def test_untracked_file_is_not_scanned(self):
        root = _repo({"a.py": b"ok\n"})
        (root / "stray.py").write_bytes(b"\x08")
        self.assertEqual(check.main([str(root)]), 0)

    def test_repository_is_clean(self):
        repo = HERE.parent.parent
        self.assertEqual(check.main([str(repo)]), 0)


if __name__ == "__main__":
    unittest.main()
