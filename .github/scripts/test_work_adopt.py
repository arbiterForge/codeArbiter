"""Selected legacy-board adoption inventory, before any native cutover."""

import hashlib
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core" / "pysrc"))

import _workadopt  # noqa: E402
import _worklib  # noqa: E402
import work  # noqa: E402


class AdoptionInventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-work-adopt-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.board = self.root / ".codearbiter" / "open-tasks.md"

    def test_inventories_keyed_and_unkeyed_rows_without_changing_board(self):
        raw = ("# Open tasks\n\n## In flight\n"
               "- [~] demo.feat.0001 - Build parser (started 2026-10-30) (from spec:parser#T-1)\n"
               "  - Desc: Parse input safely\n"
               "- [ ] Follow up on UI\n").encode("utf-8")
        self.board.write_bytes(raw)
        result = _workadopt.preview(self.root)
        self.assertEqual(self.board.read_bytes(), raw)
        self.assertEqual(result["boards"]["open"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIsNone(result["boards"]["archive"])
        self.assertEqual([row["state"] for row in result["rows"]], ["active", "queued"])
        self.assertEqual(result["rows"][0]["alias"], "demo.feat.0001")
        self.assertEqual(result["rows"][0]["origin"], "spec:parser#T-1")
        self.assertEqual(result["rows"][0]["title"], "Build parser")
        block = "- [ ] Follow up on UI"
        origin = "legacy:row#" + hashlib.sha256(block.encode("utf-8")).hexdigest()[:32]
        self.assertEqual(result["rows"][1]["origin"], origin)
        self.assertEqual(result["rows"][1]["work_id"], _worklib._id(origin))
        self.assertNotEqual(result["rows"][0]["work_id"], result["rows"][1]["work_id"])

    def test_scaffold_instructions_and_fenced_example_are_not_adopted(self):
        raw = ("# Open tasks\n\n"
               "Schema (one task = a lifecycle line + indented content sub-bullets):\n\n"
               "```\n- [~] poc.auth.0001 - Example (started 2026-06-18)\n```\n\n"
               "- Marker: `[ ]` queued | `[~]` in-progress | `[x]` done. In-progress and done\n"
               "- ID `<group>.<type>.<seq>`: `group` = build phase (poc/mvp1/v1...), `type` =\n"
               "- `Desc` / `Done when` / `Boundaries` are filled when known (`TBD` until then).\n\n"
               "## In-flight\n"
               "- [ ] demo.feat.0001 - Actual work\n").encode("utf-8")
        self.board.write_bytes(raw)
        result = _workadopt.preview(self.root)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["alias"], "demo.feat.0001")
        self.assertEqual(self.board.read_bytes(), raw)
        self.board.write_bytes(raw.replace(b"## In-flight", b"- Unrecognized preamble note\n## In-flight"))
        with self.assertRaisesRegex(ValueError, "unaccounted scaffold preamble"):
            _workadopt.preview(self.root)

    def test_refuses_malformed_marker_and_duplicate_alias(self):
        self.board.write_text("# Open\n* [ ] Missed row\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed"):
            _workadopt.preview(self.root)
        self.board.write_text("- [ ] demo.feat.0001 - A\n- [ ] demo.feat.0001 - B\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _workadopt.preview(self.root)

    def test_refuses_existing_native_owner_and_linked_board(self):
        self.board.write_text("- [ ] Do work\n", encoding="utf-8")
        native = self.root / ".codearbiter" / "work"
        native.mkdir()
        (native / "project.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "native"):
            _workadopt.preview(self.root)
        (native / "project.json").unlink()
        native.rmdir()
        elsewhere = self.root / "elsewhere.md"
        elsewhere.write_text("- [ ] Other work\n", encoding="utf-8")
        self.board.unlink()
        try:
            self.board.symlink_to(elsewhere)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "linked"):
            _workadopt.preview(self.root)

    def test_facade_exposes_read_only_preview(self):
        self.board.write_text("- [ ] Inspect import\n", encoding="utf-8")
        args = work._parser().parse_args(["adopt-preview"])
        result = work._dispatch(args, _worklib.LegacyClient(self.root))
        self.assertEqual(result["count"], 1)
        self.assertTrue(self.board.exists())

    def test_archived_row_is_inventoried_and_cross_board_alias_collision_refused(self):
        self.board.write_text("- [ ] demo.feat.0001 - Open item\n", encoding="utf-8")
        archive = self.root / ".codearbiter" / "done-tasks.md"
        archive.write_text("# Done\n- [x] demo.feat.0002 - Finished (done 2026-10-30)\n", encoding="utf-8")
        result = _workadopt.preview(self.root)
        self.assertEqual(result["rows"][1]["state"], "archived")
        self.assertEqual(result["rows"][1]["completed_at"], "2026-10-30")
        self.assertIsNotNone(result["boards"]["archive"])
        archive.write_text("- [x] demo.feat.0001 - Different row\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate legacy alias"):
            _workadopt.preview(self.root)

    def test_keyed_legacy_row_keeps_its_pre_adoption_work_id(self):
        self.board.write_text("- [ ] demo.feat.0001 - Review follow-up "
                              "(from review:pr854-integration)\n", encoding="utf-8")
        before = _worklib.dispatch(str(self.root), "work-list", {"offset": 0, "limit": 10})
        selected = before["entries"][0]["work_id"]
        preview = _workadopt.preview(self.root)
        self.assertEqual(preview["rows"][0]["work_id"], selected)
        self.assertNotEqual(preview["rows"][0]["origin"], "review:pr854-integration")


    def test_nonregular_archive_and_replay_refuse_before_read(self):
        self.board.write_text("- [ ] Ordinary work\n", encoding="utf-8")
        legacy = self.root / ".codearbiter" / "legacy"
        legacy.mkdir()
        (legacy / "open-tasks.md").write_text("- [ ] Saved work\n", encoding="utf-8")
        real_open = os.open
        real_path_open = Path.open
        for replay, name in [(False, "done-tasks.md"),
                             (True, "open-tasks.md"), (True, "done-tasks.md")]:
            with self.subTest(replay=replay, name=name):
                target = (legacy if replay else self.board.parent) / name
                if not target.exists():
                    target.write_bytes(b"")
                read_fd, write_fd = os.pipe()
                os.close(write_fd)  # EOF: even the broken reader cannot block.
                self.addCleanup(os.close, read_fd)
                opened = []
                reads = []

                def acquire(path, flags, *args, **kwargs):
                    if Path(path) == target:
                        fd = os.dup(read_fd)
                        opened.append(fd)
                        return fd
                    return real_open(path, flags, *args, **kwargs)

                def acquire_old(path, *args, **kwargs):
                    if path == target:
                        fd = os.dup(read_fd)
                        opened.append(fd)
                        handle = os.fdopen(fd, "rb")
                        read = mock.Mock(wraps=handle.read)
                        handle.read = read
                        reads.append(read)
                        return handle
                    return real_path_open(path, *args, **kwargs)

                native = mock.Mock()
                with mock.patch("os.open", side_effect=acquire), \
                        mock.patch.object(Path, "open", acquire_old):
                    with self.assertRaisesRegex(ValueError, "regular"):
                        if replay:
                            _workadopt.adopt(self.root, native, "owned-op", replay=True)
                        else:
                            _workadopt.preview(self.root)
                native.call.assert_not_called()
                self.assertTrue(opened)
                for read in reads:
                    read.assert_not_called()
                for fd in opened:
                    with self.assertRaises(OSError):
                        os.fstat(fd)



    def test_reader_preserves_optional_size_utf8_and_regular_controls(self):
        target = self.board.parent / "done-tasks.md"
        self.assertIsNone(_workadopt._read(target, 3, optional=True))
        with self.assertRaisesRegex(ValueError, "absent"):
            _workadopt._read(target, 3)
        target.write_bytes(b"abc")
        self.assertEqual(_workadopt._read(target, 3), (b"abc", "abc"))
        with self.assertRaisesRegex(ValueError, "read limit"):
            _workadopt._read(target, 2)
        target.write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "not UTF-8"):
            _workadopt._read(target, 3)
        target.unlink()
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "regular"):
            _workadopt._read(target, 3, optional=True)

    def test_reader_rejects_link_before_open(self):
        self.board.write_bytes(b"owned")
        target = self.board.parent / "done-tasks.md"
        try:
            target.symlink_to(self.board)
        except OSError:
            self.skipTest("symlinks unavailable")
        with mock.patch("os.open") as acquire:
            with self.assertRaisesRegex(ValueError, "linked"):
                _workadopt._read(target, 16, optional=True)
        acquire.assert_not_called()
        self.assertEqual(self.board.read_bytes(), b"owned")

    def test_reader_rejects_reparse_metadata_before_open(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG | 0o600,
                               st_file_attributes=0x400)
        with mock.patch.object(Path, "lstat", return_value=info), \
                mock.patch("os.open") as acquire:
            with self.assertRaisesRegex(ValueError, "linked"):
                _workadopt._read(self.board, 16)
        acquire.assert_not_called()

    def test_reader_closes_descriptor_on_acquisition_validation_or_read_error(self):
        self.board.write_bytes(b"owned")
        real_open = os.open
        real_fdopen = os.fdopen
        for stage in ["fstat", "fdopen", "read"]:
            with self.subTest(stage=stage):
                opened = []

                def acquire(*args, **kwargs):
                    fd = real_open(*args, **kwargs)
                    opened.append(fd)
                    return fd

                def wrap(*args, **kwargs):
                    handle = real_fdopen(*args, **kwargs)
                    handle.read = mock.Mock(side_effect=OSError("owned read failure"))
                    return handle

                fault = (mock.patch("os.fstat", side_effect=OSError("owned stat failure"))
                         if stage == "fstat" else
                         mock.patch("os.fdopen", side_effect=OSError("owned wrap failure"))
                         if stage == "fdopen" else
                         mock.patch("os.fdopen", side_effect=wrap))
                with mock.patch("os.open", side_effect=acquire), fault:
                    with self.assertRaisesRegex(OSError, "owned"):
                        _workadopt._read(self.board, 16)
                self.assertEqual(len(opened), 1)
                with self.assertRaises(OSError):
                    os.fstat(opened[0])
        self.assertEqual(self.board.read_bytes(), b"owned")

    def test_reader_rejects_acquisition_identity_drift_without_read(self):
        real_open = os.open
        for change in ["wrong_descriptor", "replaced_path", "removed_path"]:
            with self.subTest(change=change):
                self.board.write_bytes(b"original")
                replacement = self.root / "replacement.md"
                replacement.write_bytes(b"replacement")
                opened = []

                def acquire(path, flags, *args, **kwargs):
                    if change == "replaced_path":
                        replacement.replace(self.board)
                    elif change == "removed_path":
                        self.board.unlink()
                    fd = real_open(replacement if change in {"wrong_descriptor", "removed_path"}
                                   else path, flags, *args, **kwargs)
                    opened.append(fd)
                    return fd

                with mock.patch("os.open", side_effect=acquire), \
                        mock.patch("os.fdopen") as read:
                    with self.assertRaisesRegex(ValueError, "changed during acquisition"):
                        _workadopt._read(self.board, 16, optional=True)
                read.assert_not_called()
                self.assertEqual(len(opened), 1)
                with self.assertRaises(OSError):
                    os.fstat(opened[0])

    def test_reader_requests_safe_available_flags_and_bounded_read(self):
        self.board.write_bytes(b"abcdef")
        real_open = os.open
        real_fdopen = os.fdopen
        reads = []

        def wrap(*args, **kwargs):
            handle = real_fdopen(*args, **kwargs)
            spy = mock.Mock(wraps=handle.read)
            handle.read = spy
            reads.append(spy)
            return handle

        with mock.patch("os.open", wraps=real_open) as acquire, \
                mock.patch("os.fdopen", side_effect=wrap):
            with self.assertRaisesRegex(ValueError, "read limit"):
                _workadopt._read(self.board, 3)
        flags = acquire.call_args.args[1]
        for name in ["O_BINARY", "O_NONBLOCK", "O_NOFOLLOW", "O_CLOEXEC"]:
            required = getattr(os, name, 0)
            self.assertEqual(flags & required, required, name)
        reads[0].assert_called_once_with(4)



    def test_replay_regular_snapshots_keep_exact_request_and_optional_absence(self):
        legacy = self.board.parent / "legacy"
        legacy.mkdir()
        raw = b"- [ ] Preserved saved work\n"
        active = legacy / "open-tasks.md"
        active.write_bytes(raw)
        native = mock.Mock()
        native.call.return_value = {"operation_id": "owned-op", "replayed": True}
        result = _workadopt.adopt(self.root, native, "owned-op", replay=True)
        self.assertEqual(result, native.call.return_value)
        native.call.assert_called_once()
        operation, request = native.call.call_args.args
        self.assertEqual(operation, "work-adopt")
        self.assertEqual(request["operation_id"], "owned-op")
        self.assertEqual(request["expected_board_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIsNone(request["expected_archive_sha256"])
        self.assertEqual(len(request["rows"]), 1)
        self.assertEqual(request["rows"][0]["title"], "Preserved saved work")
        self.assertNotIn("legacy_origin", request["rows"][0])
        self.assertEqual(active.read_bytes(), raw)
        self.assertFalse(self.board.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
