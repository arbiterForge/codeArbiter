import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import make_transcript, redirect_home, restore_home  # noqa: E402


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "sess.jsonl")
        self.data = make_transcript(n_pairs=6, result_bytes=20000)
        with open(self.path, "wb") as f:
            f.write(self.data)
        # Keep backups inside the tempdir so the suite never touches ~/ (all platforms).
        self._home = redirect_home(self.tmp.name)

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def cfg(self, **kw):
        return P.Config(tier="gentle", keep_recent=2, max_bytes=8192,
                        execute=True, **kw)

    def test_execute_shrinks_and_stays_valid(self):
        res = P.run(self.path, self.cfg(), session="sess")
        self.assertTrue(res["executed"], res["verdict"])
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertLess(len(landed), len(self.data))
        self.assertEqual(P._post_write_check(self.data, landed), [])

    def test_backup_created(self):
        P.run(self.path, self.cfg(), session="sess")
        backups = os.listdir(P.backup_dir())
        self.assertTrue(any(b.startswith("sess.") for b in backups))

    def test_abort_if_file_changed_between_stat_and_write(self):
        # Simulate the session moving on after we captured pre_stat.
        with open(self.path, "rb") as f:
            data = f.read()
            pre = os.fstat(f.fileno())
        # Append (changes size + mtime) before the write.
        with open(self.path, "ab") as f:
            f.write(b'{"type":"user","uuid":"late","parentUuid":"afinal"}\n')
        lines = P.load_lines(data)
        idx = P.build_index(lines, self.cfg())
        P.apply_strategies(lines, idx, self.cfg())
        out = P.serialize(lines)
        ok, verdict = P.write_in_place(self.path, out, pre, self.cfg(), session="sess")
        self.assertFalse(ok)
        self.assertIn("changed since read", verdict)

    def test_ftruncate_skipped_on_concurrent_append(self):
        # The _probe seam appends a full valid line right after our write but
        # before the truncate decision; write_in_place must NOT truncate it away.
        with open(self.path, "rb") as f:
            data = f.read()
            pre = os.fstat(f.fileno())
        lines = P.load_lines(data)
        idx = P.build_index(lines, self.cfg())
        P.apply_strategies(lines, idx, self.cfg())
        out = P.serialize(lines)
        appended = b'{"type":"user","uuid":"race","parentUuid":"afinal"}\n'

        def probe(path):
            with open(path, "ab") as f:
                f.write(appended)

        ok, verdict = P.write_in_place(self.path, out, pre, self.cfg(),
                                       session="sess", _probe=probe)
        self.assertFalse(ok)
        self.assertIn("concurrent append", verdict)
        # The appended line survived, and the original prefix was restored.
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertTrue(landed.endswith(appended))
        self.assertTrue(landed.startswith(data))

    def test_rollback_on_postwrite_validation_failure(self):
        orig = P._post_write_check
        P._post_write_check = lambda a, b: ["injected failure"]
        try:
            res = P.run(self.path, self.cfg(), session="sess")
        finally:
            P._post_write_check = orig
        # The result must report that execution did NOT occur.
        self.assertFalse(res["executed"])
        self.assertIn("rolled-back", res["verdict"])
        # After a post-write failure the file must be restored to the original.
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertEqual(landed, self.data)

    def test_unsafe_session_id_cannot_escape_backup_dir(self):
        # A traversal-laden session_id must be reduced to a safe component, so the
        # backup lands inside backup_dir() and not outside it.
        P.run(self.path, self.cfg(), session="../../evil/x")
        outside = os.path.join(self.tmp.name, "evil")
        self.assertFalse(os.path.exists(outside))
        backups = os.listdir(P.backup_dir())
        self.assertTrue(backups)  # something was written, and it's in the backup dir
        self.assertTrue(all(os.sep not in b and "/" not in b for b in backups))

    def test_refuse_to_write_through_symlink(self):
        link = os.path.join(self.tmp.name, "link.jsonl")
        try:
            os.symlink(self.path, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this platform")
        with open(link, "rb") as f:
            pre = os.fstat(f.fileno())
        ok, verdict = P.write_in_place(link, b"{}\n", pre, self.cfg(), session="sess")
        self.assertFalse(ok)
        self.assertIn("symlink", verdict)
        # The real target is untouched.
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_rollback_preserves_append_during_postwrite_failure(self):
        # An append that lands AFTER our truncate but BEFORE the rollback (the
        # post-write-validation failure path) must survive the restore. The
        # monkeypatched checker is the seam: it appends, then forces the failure.
        appended = b'{"type":"user","uuid":"race2","parentUuid":"afinal"}\n'

        def fail_and_append(a, b):
            with open(self.path, "ab") as f:
                f.write(appended)
            return ["injected failure"]
        orig_check = P._post_write_check
        P._post_write_check = fail_and_append
        try:
            res = P.run(self.path, self.cfg(), session="sess")
        finally:
            P._post_write_check = orig_check
        self.assertFalse(res["executed"])
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertEqual(landed, self.data + appended)

    def test_refuse_execute_on_validation_failure(self):
        # Force a validation failure pre-write by injecting a bad serialize.
        cfg = self.cfg()
        with open(self.path, "rb") as f:
            data = f.read()
        lines = P.load_lines(data)
        errs = P.validate(data, data + b"x", lines, cfg)  # larger => v_shrink
        self.assertTrue(errs)


class TestSelfHeal(unittest.TestCase):
    """A process killed between write_in_place's write and its truncate leaves
    new_bytes + the original's leftover tail — spliced mid-line. self_heal must
    detect that corpse on the next run and restore from the session backup."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "sess.jsonl")
        self.data = make_transcript(n_pairs=6, result_bytes=20000)
        with open(self.path, "wb") as f:
            f.write(self.data)
        self._home = redirect_home(self.tmp.name)

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _pruned_bytes(self):
        cfg = P.Config(tier="gentle", keep_recent=2, max_bytes=8192)
        lines = P.load_lines(self.data)
        idx = P.build_index(lines, cfg)
        P.apply_strategies(lines, idx, cfg)
        return P.serialize(lines)

    def _plant_backup(self, content=None):
        d = P.backup_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess.20260101T000000Z.jsonl"), "wb") as f:
            f.write(self.data if content is None else content)

    def _write_corpse(self, extra=b""):
        # The exact mid-write-kill artifact: new_bytes fully written and fsynced,
        # truncate never ran -> short prefix + leftover original tail, splice
        # boundary inside an old line. `extra` simulates post-crash live appends.
        new = self._pruned_bytes()
        self.assertLess(len(new), len(self.data))
        corpse = new + self.data[len(new):] + extra
        with open(self.path, "wb") as f:
            f.write(corpse)
        return corpse

    def test_heals_truncate_point_splice(self):
        self._write_corpse()
        with open(self.path, "rb") as f:
            self.assertTrue(any(lvl == "FAIL" for lvl, _ in P.audit(f.read())))
        self._plant_backup()
        healed, note = P.self_heal(self.path, "sess")
        self.assertTrue(healed, note)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_heal_preserves_lines_appended_after_crash(self):
        appended = b'{"type":"user","uuid":"post","parentUuid":"afinal"}\n'
        self._write_corpse(extra=appended)
        self._plant_backup()
        healed, note = P.self_heal(self.path, "sess")
        self.assertTrue(healed, note)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data + appended)

    def test_noop_on_clean_file(self):
        self._plant_backup()
        healed, note = P.self_heal(self.path, "sess")
        self.assertFalse(healed)
        self.assertEqual(note, "clean")
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_refuses_corrupt_file_without_backup(self):
        corpse = self._write_corpse()
        healed, note = P.self_heal(self.path, "sess")
        self.assertFalse(healed)
        self.assertIn("no backup", note)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), corpse)  # untouched, left for a human

    def test_does_not_heal_growing_file_with_partial_final_line(self):
        # A healthy live session mid-append: exactly one unparseable line, but it
        # is the FINAL line and the file is LARGER than the last backup. This is
        # not a crash splice (the bad line sits past len(backup)), so self_heal
        # must leave it alone — healing here would clobber an in-progress append.
        partial = b'{"type":"user","uuid":"partial-append-in-progress'
        with open(self.path, "wb") as f:
            f.write(self.data + partial)
        self._plant_backup()  # backup == self.data, smaller than the grown file
        healed, note = P.self_heal(self.path, "sess")
        self.assertFalse(healed, note)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data + partial)  # untouched

    def test_refuses_non_splice_corruption(self):
        # A file shorter than the backup is not an interrupted truncate (the
        # truncate completing IS the success path); leave it alone.
        mangled = self.data[:100] + b"GARBAGE-NOT-JSON\n"
        with open(self.path, "wb") as f:
            f.write(mangled)
        self._plant_backup()
        healed, note = P.self_heal(self.path, "sess")
        self.assertFalse(healed)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), mangled)

    def test_run_execute_self_heals_then_prunes(self):
        # End to end: a crashed prior prune's corpse, then a normal execute run —
        # it must restore from backup and complete a clean prune of the original.
        self._write_corpse()
        self._plant_backup()
        cfg = P.Config(tier="gentle", keep_recent=2, max_bytes=8192, execute=True)
        res = P.run(self.path, cfg, session="sess")
        self.assertTrue(res["executed"], res["verdict"])
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertFalse(any(lvl == "FAIL" for lvl, _ in P.audit(landed)))
        self.assertLess(len(landed), len(self.data))


if __name__ == "__main__":
    unittest.main()
