"""Selected legacy-board adoption inventory, before any native cutover."""

import hashlib
import sys
import tempfile
import unittest
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
        self.assertTrue(result["rows"][1]["origin"].startswith("legacy:open#"))
        self.assertNotEqual(result["rows"][0]["work_id"], result["rows"][1]["work_id"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
