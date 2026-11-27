"""Negative controls for the exact reviewed acquisition boundary; no network."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import acquire_nixpacks as acquire


def elf():
    raw = bytearray(64)
    raw[:7] = b"\x7fELF\x02\x01\x01"
    raw[18:20] = (62).to_bytes(2, "little")
    return bytes(raw)


def archive(payload=None, name="nixpacks", kind=tarfile.REGTYPE, extra=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as stream:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = "/outside"
        member.size = len(payload or elf()) if kind == tarfile.REGTYPE else 0
        stream.addfile(member, io.BytesIO(payload or elf()) if member.size else None)
        if extra:
            stream.addfile(tarfile.TarInfo("extra"))
    return output.getvalue()


class AcquisitionTests(unittest.TestCase):
    def check(self, raw):
        with (mock.patch.object(acquire, "ARCHIVE_SIZE", len(raw)),
              mock.patch.object(acquire, "ARCHIVE_SHA256", hashlib.sha256(raw).hexdigest())):
            return acquire.verified_binary(raw)

    def test_exact_archive_yields_only_the_expected_linux_binary(self):
        self.assertEqual(self.check(archive()), elf())

    def test_changed_archive_bytes_cannot_reuse_the_reviewed_digest(self):
        raw = archive()
        with (mock.patch.object(acquire, "ARCHIVE_SIZE", len(raw)),
              mock.patch.object(acquire, "ARCHIVE_SHA256", "0" * 64)):
            with self.assertRaisesRegex(ValueError, "archive digest"):
                acquire.verified_binary(raw)

    def test_archive_size_bound_precedes_extraction(self):
        with mock.patch.object(acquire, "ARCHIVE_SIZE", 1):
            with self.assertRaisesRegex(ValueError, "archive size"):
                acquire.verified_binary(archive())

    def test_paths_links_and_extra_members_are_not_extracted(self):
        for raw in (archive(name="../nixpacks"), archive(kind=tarfile.SYMTYPE),
                    archive(kind=tarfile.LNKTYPE), archive(extra=True)):
            with self.subTest(sha256=hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError, "archive member"):
                    self.check(raw)

    def test_other_executable_formats_and_architectures_refuse(self):
        for index, value in ((0, 0), (4, 1), (5, 2), (18, 183)):
            payload = bytearray(elf())
            payload[index] = value
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "ELF"):
                    self.check(archive(bytes(payload)))

    def test_non_linux_profile_refuses_before_download_or_write(self):
        with (mock.patch.object(acquire.platform, "system", return_value="Windows"),
              mock.patch.object(acquire, "download", side_effect=AssertionError("must not download"))):
            with self.assertRaisesRegex(ValueError, "Linux amd64"):
                acquire.acquire("unused")

    def test_only_approved_https_redirects_are_admitted(self):
        acquire.approved_url("https://release-assets.githubusercontent.com/asset?opaque=signature")
        for url in ("http://github.com/asset", "https://example.invalid/asset",
                    "https://user:password@github.com/asset", "https://github.com:444/asset"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "approved HTTPS"):
                acquire.approved_url(url)

    def test_probe_has_no_ambient_provider_or_runtime_options(self):
        with mock.patch.dict(os.environ, {"PATH": "reviewed-path", "OPENAI_API_KEY": "dummy",
                                         "NODE_OPTIONS": "dummy", "NIXPACKS_PKGS": "dummy"}, clear=True):
            self.assertEqual(acquire.process_environment(), {"PATH": "reviewed-path"})

    def test_linked_github_command_file_refuses_before_external_work(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            sentinel, command = root / "sentinel", root / "command"
            sentinel.write_bytes(b"do not change\n")
            os.link(sentinel, command)
            with (mock.patch.dict(os.environ, {"GITHUB_PATH": str(command)}),
                  mock.patch.object(acquire, "acquire", side_effect=AssertionError("must not acquire")) as install,
                  mock.patch.object(acquire.sys, "argv", ["acquire", "--parent", str(root), "--output", str(root / "receipt"), "--github-path"])):
                self.assertEqual(acquire.main(), 1)
                self.assertEqual(sentinel.read_bytes(), b"do not change\n")
                self.assertFalse((root / "receipt").exists())
                install.assert_not_called()

    def test_new_owned_binary_and_receipt_preserve_existing_runner_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            sentinel = root / "keep"
            sentinel.write_bytes(b"existing runner data")
            path_file = root / "github-path"
            path_file.write_text("existing-path\n", encoding="utf-8")
            output = root / "receipt.json"
            with (mock.patch.object(acquire.platform, "system", return_value="Linux"),
                  mock.patch.object(acquire.platform, "machine", return_value="x86_64"),
                  mock.patch.object(acquire, "download", return_value=b"fixture archive"),
                  mock.patch.object(acquire, "verified_binary", return_value=elf()),
                  mock.patch.object(acquire.subprocess, "run", return_value=SimpleNamespace(stdout=b"nixpacks 1.41.0\n")) as run,
                  mock.patch.dict(os.environ, {"GITHUB_PATH": str(path_file)}),
                  mock.patch.object(acquire.sys, "argv", ["acquire", "--parent", str(root), "--output", str(output), "--github-path"])):
                self.assertEqual(acquire.main(), 0)
                record = json.loads(output.read_text(encoding="utf-8"))
                binary = Path(record["bin_dir"]) / "nixpacks"
                self.assertEqual(binary.read_bytes(), elf())
                self.assertEqual(run.call_args.args[0], [str(binary), "--version"])
                self.assertEqual(run.call_args.kwargs["stdin"], acquire.subprocess.DEVNULL)
                self.assertEqual(path_file.read_text(encoding="utf-8"), "existing-path\n" + record["bin_dir"] + "\n")
                self.assertEqual(sentinel.read_bytes(), b"existing runner data")
                prior = output.read_bytes()
                self.assertEqual(acquire.main(), 1)
                self.assertEqual(output.read_bytes(), prior)
                self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
