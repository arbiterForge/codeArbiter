import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import make_transcript, redirect_home, restore_home  # noqa: E402


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # HOME redirect keeps state/backups/logs out of the real ~ (all platforms).
        self._home = redirect_home(self.tmp.name)
        # An arbiter-enabled fake repo (cwd) so the gate passes.
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".codearbiter"))
        with open(os.path.join(self.repo, ".codearbiter", "CONTEXT.md"), "w") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")
        # A large, prunable transcript.
        self.path = os.path.join(self.repo, "sess.jsonl")
        with open(self.path, "wb") as f:
            f.write(make_transcript(n_pairs=8, result_bytes=30000))

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def payload(self, event="UserPromptSubmit"):
        return {"hook_event_name": event, "transcript_path": self.path,
                "session_id": "sess", "cwd": self.repo}

    def env(self, **kw):
        e = {"CODEARBITER_PRUNE_KEEP_RECENT": "2", "CODEARBITER_PRUNE_MIN_SIZE": "1000",
             "CODEARBITER_PRUNE_MIN_GROWTH": "1000"}
        e.update(kw)
        return e

    def test_disabled_by_default_noop(self):
        before = os.path.getsize(self.path)
        rc = P.hook_run(self.payload(), env=self.env())  # CODEARBITER_PRUNE unset
        self.assertEqual(rc, 0)
        self.assertEqual(os.path.getsize(self.path), before)
        self.assertEqual(P.load_state(), {})

    def test_on_prunes_and_records_state(self):
        before = os.path.getsize(self.path)
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        self.assertLess(os.path.getsize(self.path), before)
        st = P.load_state()
        self.assertIn("sess", st)
        self.assertGreater(st["sess"]["pct"], 0)

    def test_userpromptsubmit_and_precompact_both_handled(self):
        for ev in ("UserPromptSubmit", "PreCompact", "Stop"):
            with open(self.path, "wb") as f:
                f.write(make_transcript(n_pairs=8, result_bytes=30000))
            P.save_state({})
            rc = P.hook_run(self.payload(ev), env=self.env(CODEARBITER_PRUNE="on"))
            self.assertEqual(rc, 0)
            self.assertIn("sess", P.load_state())

    def test_short_circuit_no_growth(self):
        # First run prunes; a second run on the now-smaller file must short
        # circuit (no growth since last prune).
        P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        size_after = os.path.getsize(self.path)
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        self.assertEqual(os.path.getsize(self.path), size_after)

    def test_min_size_floor(self):
        small = os.path.join(self.repo, "small.jsonl")
        with open(small, "wb") as f:
            f.write(make_transcript(n_pairs=1, result_bytes=10))
        pl = self.payload()
        pl["transcript_path"] = small
        rc = P.hook_run(pl, env=self.env(CODEARBITER_PRUNE="on",
                                         CODEARBITER_PRUNE_MIN_SIZE="1000000"))
        self.assertEqual(rc, 0)
        self.assertEqual(P.load_state(), {})  # below floor -> untouched

    def test_tail_coherence_abort_on_open_tool_loop(self):
        # Append an assistant turn with a tool_use that has no matching result:
        # the loop is open, so the hook must not prune.
        open_turn = (b'{"type":"assistant","uuid":"aopen","parentUuid":"afinal",'
                     b'"message":{"role":"assistant","content":[{"type":"tool_use",'
                     b'"id":"toolu_open","name":"Bash","input":{}}]}}\n')
        with open(self.path, "ab") as f:
            f.write(open_turn)
        before = os.path.getsize(self.path)
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        self.assertEqual(os.path.getsize(self.path), before)

    def test_gate_off_when_not_arbiter_repo(self):
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        path = os.path.join(plain, "s.jsonl")
        with open(path, "wb") as f:
            f.write(make_transcript(n_pairs=8, result_bytes=30000))
        before = os.path.getsize(path)
        pl = {"hook_event_name": "UserPromptSubmit", "transcript_path": path,
              "session_id": "x", "cwd": plain}
        rc = P.hook_run(pl, env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        self.assertEqual(os.path.getsize(path), before)  # dormant repo -> noop

    def test_hook_self_heals_crash_corpse_then_prunes(self):
        # A prior prune died between write and truncate, leaving a mid-line
        # splice. The next hook run (mode=on) must restore from the backup
        # BEFORE any gate reads the file, then prune normally.
        with open(self.path, "rb") as f:
            data = f.read()
        cfg = P.Config(tier="gentle", keep_recent=2, max_bytes=8192)
        lines = P.load_lines(data)
        P.apply_strategies(lines, P.build_index(lines, cfg), cfg)
        new = P.serialize(lines)
        with open(self.path, "wb") as f:
            f.write(new + data[len(new):])  # the crash corpse
        d = P.backup_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess.20260101T000000Z.jsonl"), "wb") as f:
            f.write(data)
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        with open(self.path, "rb") as f:
            landed = f.read()
        self.assertFalse(any(lvl == "FAIL" for lvl, _ in P.audit(landed)))
        self.assertLess(len(landed), len(data))
        self.assertIn("sess", P.load_state())

    def test_tail_is_settled_helper(self):
        good = P.load_lines(make_transcript(n_pairs=2, result_bytes=100))
        self.assertTrue(P.tail_is_settled(good))


if __name__ == "__main__":
    unittest.main()
