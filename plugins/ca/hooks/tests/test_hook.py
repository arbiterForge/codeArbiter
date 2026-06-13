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
        # A large, prunable transcript — placed under ~/.claude/projects/ so the
        # N-1 transcript_path containment check passes (transcripts live there).
        claude_dir = os.path.join(self.tmp.name, ".claude", "projects", "test")
        os.makedirs(claude_dir, exist_ok=True)
        self.path = os.path.join(claude_dir, "sess.jsonl")
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

    def _read_jsonl(self, path):
        import json as _json
        with open(path, encoding="utf-8") as f:
            return [_json.loads(ln) for ln in f if ln.strip()]

    def test_dry_metrics_path_default_and_override(self):
        # Default lands in a dedicated metrics folder under ~/.codearbiter;
        # CODEARBITER_PRUNE_METRICS overrides the full path (with ~ expansion).
        default = P.dry_metrics_path({})
        self.assertEqual(
            os.path.normpath(default),
            os.path.normpath(os.path.join(
                os.path.expanduser("~"), ".codearbiter", "metrics", "prune-dry.jsonl")))
        override = P.dry_metrics_path({"CODEARBITER_PRUNE_METRICS": "~/custom/d.jsonl"})
        self.assertEqual(os.path.normpath(override),
                         os.path.normpath(os.path.expanduser("~/custom/d.jsonl")))

    def test_dry_mode_appends_metrics_and_never_writes_transcript(self):
        before = os.path.getsize(self.path)
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="dry"))
        self.assertEqual(rc, 0)
        # Dry never touches the live transcript.
        self.assertEqual(os.path.getsize(self.path), before)
        recs = self._read_jsonl(P.dry_metrics_path(self.env()))
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["mode"], "dry")
        self.assertEqual(r["session"], "sess")
        self.assertEqual(r["verdict"], "dry-run")
        self.assertEqual(r["validation_errors"], 0)
        self.assertGreater(r["bytes_before"], r["bytes_after"])
        self.assertIn("strategies", r)
        self.assertIn("ts", r)

    def test_dry_only_on_mode_does_not_write_dry_metrics(self):
        rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="on"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(P.dry_metrics_path(self.env())))

    def test_dry_metrics_accumulate_across_sessions_in_one_log(self):
        # Every session appends to the same dedicated log — the data-collection
        # contract: one shared file, append-only across sessions.
        for sid in ("sessA", "sessB", "sessC"):
            pl = self.payload()
            pl["session_id"] = sid
            rc = P.hook_run(pl, env=self.env(CODEARBITER_PRUNE="dry"))
            self.assertEqual(rc, 0)
        recs = self._read_jsonl(P.dry_metrics_path(self.env()))
        self.assertEqual([r["session"] for r in recs], ["sessA", "sessB", "sessC"])

    def test_dry_metrics_records_validation_failure_verdict(self):
        # When the would-be prune fails validation, the dry record captures the
        # refusal verdict and a non-zero error count — the go/no-go signal.
        import _prunelib as _P

        def boom(orig, new, lines, cfg):
            return ["synthetic chain break"]
        orig_validate = _P.validate
        _P.validate = boom
        try:
            rc = P.hook_run(self.payload(), env=self.env(CODEARBITER_PRUNE="dry"))
        finally:
            _P.validate = orig_validate
        self.assertEqual(rc, 0)
        recs = self._read_jsonl(P.dry_metrics_path(self.env()))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["verdict"], "refused: validation failed")
        self.assertEqual(recs[0]["validation_errors"], 1)

    def test_tail_is_settled_helper(self):
        good = P.load_lines(make_transcript(n_pairs=2, result_bytes=100))
        self.assertTrue(P.tail_is_settled(good))

    def test_tail_is_settled_false_when_last_line_is_queue_operation(self):
        # tail_is_settled must return False when the very last non-blank line is
        # a queue-operation JSON object (mid-turn state, not a clean boundary).
        data = make_transcript(n_pairs=2, result_bytes=100)
        import json as _json
        queue_line = (_json.dumps({"type": "queue-operation", "uuid": "qop1",
                                   "parentUuid": "afinal"}) + "\n").encode()
        lines = P.load_lines(data + queue_line)
        self.assertFalse(P.tail_is_settled(lines))

    def test_tail_is_settled_true_after_queue_operation_followed_by_result(self):
        # A queue-operation that is NOT the final line must not block settlement —
        # only the very last JSON line matters.
        import json as _json
        # Transcript: normal settled turn then a queue-op in the middle (not last).
        data = make_transcript(n_pairs=1, result_bytes=100, final_assistant=False)
        middle_queue = (_json.dumps({"type": "queue-operation", "uuid": "qm",
                                     "parentUuid": "ru0"}) + "\n").encode()
        final_result = (_json.dumps({
            "type": "user", "uuid": "rfinal", "parentUuid": "a0",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_0", "content": "ok"},
            ]},
        }) + "\n").encode()
        lines = P.load_lines(data + middle_queue + final_result)
        # The last line is a tool_result (not a queue-op) → loop is closed.
        self.assertTrue(P.tail_is_settled(lines))


class TestConfigFromEnv(unittest.TestCase):
    def test_valid_env_produces_correct_config(self):
        env = {
            "CODEARBITER_PRUNE_TIER": "aggressive",
            "CODEARBITER_PRUNE_MAXBYTES": "4096",
            "CODEARBITER_PRUNE_KEEP_RECENT": "5",
            "CODEARBITER_PRUNE_MIN_SIZE": "2097152",
            "CODEARBITER_PRUNE_MIN_GROWTH": "524288",
            "CODEARBITER_PRUNE_BACKUPS": "7",
            "CODEARBITER_PRUNE_LIVE_SECS": "120",
        }
        cfg = P.Config.from_env(env)
        self.assertEqual(cfg.tier, "aggressive")
        self.assertEqual(cfg.max_bytes, 4096)
        self.assertEqual(cfg.keep_recent, 5)
        self.assertEqual(cfg.min_size, 2097152)
        self.assertEqual(cfg.min_growth, 524288)
        self.assertEqual(cfg.backups, 7)
        self.assertEqual(cfg.live_secs, 120)
        self.assertIsNone(cfg.strategies)

    def test_non_numeric_maxbytes_falls_back_to_default(self):
        env = {"CODEARBITER_PRUNE_MAXBYTES": "not-a-number"}
        cfg = P.Config.from_env(env)
        self.assertEqual(cfg.max_bytes, 8192)  # hard-coded default

    def test_empty_strategies_string_produces_none(self):
        # An empty CODEARBITER_PRUNE_STRATEGIES var (unset) must result in
        # strategies=None so selected_strategies() falls back to the tier.
        env = {}  # key absent
        cfg = P.Config.from_env(env)
        self.assertIsNone(cfg.strategies)

    def test_strategies_string_parsed_into_list(self):
        env = {"CODEARBITER_PRUNE_STRATEGIES": "sidecar-collapse, reasoning-fold,"}
        cfg = P.Config.from_env(env)
        self.assertEqual(cfg.strategies, ["sidecar-collapse", "reasoning-fold"])

    def test_keyword_override_takes_precedence_over_env(self):
        env = {"CODEARBITER_PRUNE_TIER": "gentle", "CODEARBITER_PRUNE_MAXBYTES": "1024"}
        cfg = P.Config.from_env(env, tier="aggressive", max_bytes=512)
        self.assertEqual(cfg.tier, "aggressive")
        self.assertEqual(cfg.max_bytes, 512)


if __name__ == "__main__":
    unittest.main()
