"""Unit tests for the cold-miss nudge — O1–O11.

Mirror test_hook.py style: redirect_home/restore_home from _helpers, tempdir,
import _prunelib as P. Tests are isolated from the real ~ via home redirect.

Run via: python .github/scripts/test_prune_nudge.py
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest

# Ensure hooks/ and hooks/tests/ are importable.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

import _prunelib as P  # noqa: E402
from _helpers import make_transcript, redirect_home, restore_home  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript_with_ts(n_pairs=4, result_bytes=5000,
                              final_ts="2026-06-18T10:00:00Z"):
    """Build a transcript whose final assistant turn carries a top-level
    `timestamp` field.  The shared make_transcript() omits it — we need it for
    idle-time detection.
    """
    data = make_transcript(n_pairs=n_pairs, result_bytes=result_bytes,
                           final_assistant=True)
    # Re-parse the last non-blank line, inject the timestamp, re-serialize.
    lines = data.rstrip(b"\n").split(b"\n")
    last = json.loads(lines[-1])
    last["timestamp"] = final_ts
    lines[-1] = json.dumps(last, ensure_ascii=False, separators=(",", ":")).encode()
    return b"\n".join(lines) + b"\n"


def _big_rec(cold_nudged=False):
    """A session state record with a large freed_bytes (> 80 000 tokens @ 4 B)."""
    # 80 000 tokens * 4 bytes/token = 320 000 bytes freed — well above the floor.
    return {
        "freed_bytes": 400_000,
        "last_pruned_size": 1_200_000,
        "pct": 33.0,
        "cold_nudged": cold_nudged,
    }


# ---------------------------------------------------------------------------
# O1 — flag off → nudge_decision not-armed
# ---------------------------------------------------------------------------

class TestO1FlagOff(unittest.TestCase):
    def test_flag_unset(self):
        rec = _big_rec()
        armed, advisory, new_rec = P.nudge_decision(rec, idle_secs=300, e={})
        self.assertFalse(armed)
        self.assertEqual(advisory, "")

    def test_flag_off_explicit(self):
        rec = _big_rec()
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300, e={"CODEARBITER_PRUNE_NUDGE": "off"})
        self.assertFalse(armed)

    def test_flag_wrong_value(self):
        rec = _big_rec()
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300, e={"CODEARBITER_PRUNE_NUDGE": "yes"})
        self.assertFalse(armed)


# ---------------------------------------------------------------------------
# O2 — hook_run with PRUNE=dry or PRUNE=off + NUDGE=on → returns 0
# ---------------------------------------------------------------------------

class TestO2WrongMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".codearbiter"))
        with open(os.path.join(self.repo, ".codearbiter", "CONTEXT.md"), "w") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")
        claude_dir = os.path.join(self.tmp.name, ".claude", "projects", "test")
        os.makedirs(claude_dir, exist_ok=True)
        self.path = os.path.join(claude_dir, "sess.jsonl")
        ts = "2026-06-18T00:00:00Z"  # old enough to be "cold"
        with open(self.path, "wb") as f:
            f.write(_make_transcript_with_ts(n_pairs=6, result_bytes=20000,
                                              final_ts=ts))
        # Pre-seed state with a big freed_bytes record.
        P.save_state({"sess": _big_rec()})

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _env(self, **kw):
        e = {"CODEARBITER_PRUNE_KEEP_RECENT": "2",
             "CODEARBITER_PRUNE_MIN_SIZE": "1000",
             "CODEARBITER_PRUNE_MIN_GROWTH": "1000",
             "CODEARBITER_PRUNE_NUDGE": "on",
             "CODEARBITER_PRUNE_NUDGE_IDLE_SECS": "1",   # very low floor
             "CODEARBITER_PRUNE_NUDGE_MIN_TOKENS": "1"}  # very low floor
        e.update(kw)
        return e

    def payload(self):
        return {"hook_event_name": "UserPromptSubmit",
                "transcript_path": self.path,
                "session_id": "sess",
                "cwd": self.repo}

    def test_dry_mode_returns_0(self):
        rc = P.hook_run(self.payload(),
                        env=self._env(CODEARBITER_PRUNE="dry"))
        self.assertEqual(rc, 0)

    def test_off_mode_returns_0(self):
        rc = P.hook_run(self.payload(),
                        env=self._env(CODEARBITER_PRUNE="off"))
        self.assertEqual(rc, 0)

    def test_transcript_untouched_in_dry_mode(self):
        before = os.path.getsize(self.path)
        P.hook_run(self.payload(), env=self._env(CODEARBITER_PRUNE="dry"))
        self.assertEqual(os.path.getsize(self.path), before)


# ---------------------------------------------------------------------------
# O3 — cold + freed_bytes below floor → not-armed
# ---------------------------------------------------------------------------

class TestO3SmallDelta(unittest.TestCase):
    def test_below_floor_freed_bytes(self):
        # est_tokens(freed_bytes) < 80 000 when freed_bytes < 320 000
        rec = {"freed_bytes": 100_000, "last_pruned_size": 500_000, "pct": 20.0}
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertFalse(armed)

    def test_exactly_at_floor_tokens_passes(self):
        # 80 000 tokens * 4 = 320 000 bytes — on the threshold; should arm
        rec = {"freed_bytes": 320_000, "last_pruned_size": 1_000_000, "pct": 32.0}
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertTrue(armed)

    def test_custom_min_tokens_env(self):
        # With MIN_TOKENS=50 000 tokens, freed_bytes=210_000 (52 500 tokens) arms.
        rec = {"freed_bytes": 210_000, "last_pruned_size": 600_000, "pct": 35.0}
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300,
            e={"CODEARBITER_PRUNE_NUDGE": "on",
               "CODEARBITER_PRUNE_NUDGE_MIN_TOKENS": "50000"})
        self.assertTrue(armed)


# ---------------------------------------------------------------------------
# O4 — warm (idle < 240) → not-armed; no spurious cold_nudged set
# ---------------------------------------------------------------------------

class TestO4WarmSession(unittest.TestCase):
    def test_warm_not_armed(self):
        rec = _big_rec()
        armed, _, new_rec = P.nudge_decision(
            rec, idle_secs=100,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertFalse(armed)
        self.assertFalse(new_rec.get("cold_nudged"),
                         "warm submit must not set cold_nudged")

    def test_warm_at_boundary_not_armed(self):
        rec = _big_rec()
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=239,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertFalse(armed)

    def test_idle_none_not_armed(self):
        rec = _big_rec()
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=None,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertFalse(armed)


# ---------------------------------------------------------------------------
# O5 — all conditions hold → armed, advisory non-empty
# ---------------------------------------------------------------------------

class TestO5Armed(unittest.TestCase):
    def test_arms_when_all_hold(self):
        rec = _big_rec()
        armed, advisory, new_rec = P.nudge_decision(
            rec, idle_secs=300,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertTrue(armed)
        self.assertTrue(advisory, "advisory must be non-empty when armed")
        self.assertTrue(new_rec.get("cold_nudged"),
                        "cold_nudged must be set on arm")

    def test_custom_idle_floor(self):
        rec = _big_rec()
        # Default floor 240; custom floor 60 → armed at idle=70
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=70,
            e={"CODEARBITER_PRUNE_NUDGE": "on",
               "CODEARBITER_PRUNE_NUDGE_IDLE_SECS": "60"})
        self.assertTrue(armed)


# ---------------------------------------------------------------------------
# O6 — already cold_nudged=True → not-armed on second call
# ---------------------------------------------------------------------------

class TestO6AlreadyNudged(unittest.TestCase):
    def test_second_call_not_armed(self):
        rec = _big_rec(cold_nudged=True)
        armed, _, _ = P.nudge_decision(
            rec, idle_secs=300,
            e={"CODEARBITER_PRUNE_NUDGE": "on"})
        self.assertFalse(armed)


# ---------------------------------------------------------------------------
# O7 — two-step: cold_nudged + warm → clears → re-arms on next cold
# ---------------------------------------------------------------------------

class TestO7OncePerColdWindow(unittest.TestCase):
    def test_warm_clears_marker_then_cold_rearms(self):
        # Step 1: start with cold_nudged=True, submit while warm → clears
        rec = _big_rec(cold_nudged=True)
        e = {"CODEARBITER_PRUNE_NUDGE": "on"}
        armed1, _, rec2 = P.nudge_decision(rec, idle_secs=100, e=e)
        self.assertFalse(armed1)
        self.assertFalse(rec2.get("cold_nudged"),
                         "warm submit must clear cold_nudged")

        # Step 2: feed that cleared rec back; cold submit → arms again
        armed2, advisory2, rec3 = P.nudge_decision(rec2, idle_secs=300, e=e)
        self.assertTrue(armed2)
        self.assertTrue(advisory2)
        self.assertTrue(rec3.get("cold_nudged"))


# ---------------------------------------------------------------------------
# O8 — fail-open: bad inputs never raise, hook_run never returns 2 on error
# ---------------------------------------------------------------------------

class TestO8FailOpen(unittest.TestCase):
    def test_nudge_decision_none_rec(self):
        try:
            armed, _, _ = P.nudge_decision(None, idle_secs=300,
                                           e={"CODEARBITER_PRUNE_NUDGE": "on"})
            self.assertFalse(armed)
        except Exception as ex:
            self.fail(f"nudge_decision(None, ...) raised {ex!r}")

    def test_nudge_decision_freed_bytes_non_int(self):
        rec = {"freed_bytes": "not-a-number", "pct": 10.0}
        try:
            armed, _, _ = P.nudge_decision(rec, idle_secs=300,
                                           e={"CODEARBITER_PRUNE_NUDGE": "on"})
            self.assertFalse(armed)
        except Exception as ex:
            self.fail(f"nudge_decision with bad freed_bytes raised {ex!r}")

    def test_last_assistant_ts_bad_json(self):
        result = P._last_assistant_ts(b"{bad json\n")
        self.assertIsNone(result)

    def test_hook_run_never_returns_2_when_state_throws(self):
        """If load_state raises (monkeypatched), hook_run must still return 0."""
        import _prunelib as _P
        orig = _P.load_state

        def _boom():
            raise RuntimeError("injected")

        _P.load_state = _boom
        try:
            # We need a minimal valid environment; the hook will fail open at the
            # load_state call and return 0.
            tmp = tempfile.mkdtemp()
            hm = redirect_home(tmp)
            try:
                repo = os.path.join(tmp, "repo")
                os.makedirs(os.path.join(repo, ".codearbiter"))
                with open(os.path.join(repo, ".codearbiter", "CONTEXT.md"), "w") as f:
                    f.write("---\narbiter: enabled\n---\n# ctx\n")
                cd = os.path.join(tmp, ".claude", "projects", "t")
                os.makedirs(cd)
                tp = os.path.join(cd, "s.jsonl")
                with open(tp, "wb") as f:
                    f.write(make_transcript(n_pairs=8, result_bytes=20000))
                pl = {"hook_event_name": "UserPromptSubmit",
                      "transcript_path": tp,
                      "session_id": "s",
                      "cwd": repo}
                env = {"CODEARBITER_PRUNE": "on",
                       "CODEARBITER_PRUNE_NUDGE": "on",
                       "CODEARBITER_PRUNE_MIN_SIZE": "1000",
                       "CODEARBITER_PRUNE_MIN_GROWTH": "1000",
                       "CODEARBITER_PRUNE_KEEP_RECENT": "2"}
                rc = _P.hook_run(pl, env=env)
                self.assertEqual(rc, 0)
            finally:
                restore_home(hm)
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
        finally:
            _P.load_state = orig


# ---------------------------------------------------------------------------
# O9 — advisory is a pure function of rec numbers; no transcript content
# ---------------------------------------------------------------------------

class TestO9Advisory(unittest.TestCase):
    def test_advisory_contains_token_count_and_pct(self):
        rec = {"freed_bytes": 400_000, "last_pruned_size": 800_000,
               "pct": 33.0}
        advisory = P._nudge_advisory(rec)
        # ~(400_000 + 800_000) / 4 = 300_000 tokens → 300k
        self.assertIn("300k", advisory)
        self.assertIn("33", advisory)

    def test_advisory_contains_action_words(self):
        rec = {"freed_bytes": 400_000, "last_pruned_size": 800_000, "pct": 33.0}
        advisory = P._nudge_advisory(rec)
        self.assertIn("/compact", advisory)
        self.assertIn("--resume", advisory)
        self.assertIn("Submit again", advisory)

    def test_advisory_no_transcript_filler(self):
        rec = {"freed_bytes": 400_000, "last_pruned_size": 800_000, "pct": 33.0}
        advisory = P._nudge_advisory(rec)
        # The filler used in make_transcript is "X" * result_bytes
        self.assertNotIn("X" * 20, advisory,
                         "advisory must not contain transcript filler content")

    def test_advisory_pure_function_of_numbers(self):
        # Same rec → same advisory regardless of call order
        rec = {"freed_bytes": 500_000, "last_pruned_size": 1_000_000, "pct": 50.0}
        a1 = P._nudge_advisory(rec)
        a2 = P._nudge_advisory(rec)
        self.assertEqual(a1, a2)


# ---------------------------------------------------------------------------
# O10 — hook_run integration (full pipeline)
# ---------------------------------------------------------------------------

class TestO10Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".codearbiter"))
        with open(os.path.join(self.repo, ".codearbiter", "CONTEXT.md"), "w") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")
        claude_dir = os.path.join(self.tmp.name, ".claude", "projects", "test")
        os.makedirs(claude_dir, exist_ok=True)
        self.path = os.path.join(claude_dir, "sess.jsonl")
        # Old assistant timestamp → guaranteed idle
        old_ts = "2026-06-17T00:00:00Z"   # 24 hours ago relative to any "now"
        data = _make_transcript_with_ts(n_pairs=6, result_bytes=20000,
                                         final_ts=old_ts)
        with open(self.path, "wb") as f:
            f.write(data)
        self._original_size = len(data)
        # Pre-seed state: big freed_bytes, no marker.
        P.save_state({"sess": _big_rec(cold_nudged=False)})

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _env(self, **kw):
        e = {"CODEARBITER_PRUNE": "on",
             "CODEARBITER_PRUNE_NUDGE": "on",
             "CODEARBITER_PRUNE_KEEP_RECENT": "2",
             "CODEARBITER_PRUNE_MIN_SIZE": "1000",
             "CODEARBITER_PRUNE_MIN_GROWTH": "1000",
             # Very low thresholds so the nudge conditions are reliably met.
             "CODEARBITER_PRUNE_NUDGE_MIN_TOKENS": "1",
             "CODEARBITER_PRUNE_NUDGE_IDLE_SECS": "1"}
        e.update(kw)
        return e

    def _payload(self):
        return {"hook_event_name": "UserPromptSubmit",
                "transcript_path": self.path,
                "session_id": "sess",
                "cwd": self.repo}

    def test_armed_returns_2_and_advisory_on_stderr(self):
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            rc = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc, 2, "armed nudge must return 2")
        self.assertIn("Submit again", stderr_buf.getvalue())

    def test_armed_transcript_size_unchanged(self):
        """When the nudge fires (return 2), prune is skipped — transcript stays."""
        P.hook_run(self._payload(), env=self._env())
        self.assertEqual(os.path.getsize(self.path), self._original_size)

    def test_armed_sets_cold_nudged_in_state(self):
        P.hook_run(self._payload(), env=self._env())
        st = P.load_state()
        self.assertTrue(st.get("sess", {}).get("cold_nudged"),
                        "hook_run must persist cold_nudged=True after arming")

    def test_resubmit_returns_0(self):
        """Second call (marker already set) must return 0 — the override path."""
        P.hook_run(self._payload(), env=self._env())
        rc2 = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc2, 0)

    def test_nudge_off_is_identical_to_today(self):
        """With NUDGE unset, hook_run prunes normally and returns 0."""
        before = os.path.getsize(self.path)
        env_no_nudge = self._env()
        del env_no_nudge["CODEARBITER_PRUNE_NUDGE"]
        del env_no_nudge["CODEARBITER_PRUNE_NUDGE_MIN_TOKENS"]
        del env_no_nudge["CODEARBITER_PRUNE_NUDGE_IDLE_SECS"]
        # Reset state so the short-circuit doesn't fire.
        P.save_state({})
        rc = P.hook_run(self._payload(), env=env_no_nudge)
        self.assertEqual(rc, 0)
        self.assertLess(os.path.getsize(self.path), before,
                        "without nudge, hook_run should prune normally")


# ---------------------------------------------------------------------------
# O11 — prune.md mentions CODEARBITER_PRUNE_NUDGE
# ---------------------------------------------------------------------------

class TestO11Docs(unittest.TestCase):
    def test_prune_md_references_nudge_env(self):
        # _TESTS_DIR = plugins/ca/hooks/tests → go up 4 levels to repo root
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(_TESTS_DIR))))
        doc = os.path.join(repo_root, "plugins", "ca", "commands", "prune.md")
        with open(doc, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("CODEARBITER_PRUNE_NUDGE", text,
                      "prune.md must document the CODEARBITER_PRUNE_NUDGE env var")


def _warm_ts():
    """A `Z` timestamp at 'now' (UTC) → idle ~ 0 → warm."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Parser + idle extraction edge cases (MEDIUM coverage gaps + the offset bug)
# ---------------------------------------------------------------------------

class TestParseAndIdleEdges(unittest.TestCase):
    def test_parse_plain_z(self):
        # Returns an int epoch, and the arithmetic is sane: +90s parses 90 higher.
        t0 = P._parse_iso8601("2026-06-18T10:00:00Z")
        t1 = P._parse_iso8601("2026-06-18T10:01:30Z")
        self.assertIsInstance(t0, int)
        self.assertEqual(t1 - t0, 90)

    def test_parse_fractional_seconds_z(self):
        # Fractional seconds are dropped; same epoch as the whole-second form.
        self.assertEqual(P._parse_iso8601("2026-06-18T10:00:00.123456Z"),
                         P._parse_iso8601("2026-06-18T10:00:00Z"))

    def test_parse_positive_offset_returns_none(self):
        # Offset-bearing timestamps are treated as unknown — never silently UTC.
        self.assertIsNone(P._parse_iso8601("2026-06-18T10:00:00+05:00"))

    def test_parse_negative_offset_returns_none(self):
        # The bug the audit caught: -offset must behave the same as +offset.
        self.assertIsNone(P._parse_iso8601("2026-06-18T10:00:00-05:00"))

    def test_parse_garbage_returns_none(self):
        self.assertIsNone(P._parse_iso8601("not a date"))
        self.assertIsNone(P._parse_iso8601(None))

    def test_last_assistant_ts_no_assistant_turn(self):
        # A transcript with no assistant line → None (fail open, no nudge).
        data = (b'{"type":"user","uuid":"u0","parentUuid":null,'
                b'"message":{"role":"user","content":"hi"}}\n')
        self.assertIsNone(P._last_assistant_ts(data))

    def test_last_assistant_ts_assistant_without_timestamp(self):
        # make_transcript emits assistant turns but NO top-level timestamp → None.
        data = make_transcript(n_pairs=2, result_bytes=100, final_assistant=True)
        self.assertIsNone(P._last_assistant_ts(data))

    def test_idle_seconds_none_when_ts_absent(self):
        data = make_transcript(n_pairs=1, result_bytes=100)
        self.assertIsNone(P._idle_seconds(data, now=1.0e9))


# ---------------------------------------------------------------------------
# Shared armed-eligible integration harness (cold transcript + big delta)
# ---------------------------------------------------------------------------

class _ArmedHarness(unittest.TestCase):
    """setUp builds an arbiter repo + a cold transcript whose state record has a
    large freed_bytes and a SMALL last_pruned_size (so a later warm submit's
    grown transcript actually prunes, exercising the carry-forward path)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".codearbiter"))
        with open(os.path.join(self.repo, ".codearbiter", "CONTEXT.md"), "w") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")
        self.claude_dir = os.path.join(self.tmp.name, ".claude", "projects", "test")
        os.makedirs(self.claude_dir, exist_ok=True)
        self.path = os.path.join(self.claude_dir, "sess.jsonl")
        self._write_transcript("2026-06-17T00:00:00Z")  # cold
        P.save_state({"sess": {"freed_bytes": 400_000,
                               "last_pruned_size": 1000, "pct": 33.0}})

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _write_transcript(self, ts, result_bytes=20000):
        with open(self.path, "wb") as f:
            f.write(_make_transcript_with_ts(n_pairs=6, result_bytes=result_bytes,
                                             final_ts=ts))

    def _env(self, **kw):
        e = {"CODEARBITER_PRUNE": "on", "CODEARBITER_PRUNE_NUDGE": "on",
             "CODEARBITER_PRUNE_KEEP_RECENT": "2",
             "CODEARBITER_PRUNE_MIN_SIZE": "1000",
             "CODEARBITER_PRUNE_MIN_GROWTH": "1000",
             "CODEARBITER_PRUNE_NUDGE_MIN_TOKENS": "1",
             "CODEARBITER_PRUNE_NUDGE_IDLE_SECS": "1"}
        e.update(kw)
        return e

    def _payload(self):
        return {"hook_event_name": "UserPromptSubmit", "transcript_path": self.path,
                "session_id": "sess", "cwd": self.repo}


# ---------------------------------------------------------------------------
# O8 (hook_run level) — a fault INSIDE the nudge block fails open, never 2
# ---------------------------------------------------------------------------

class TestO8bNudgeBlockFailOpen(_ArmedHarness):
    def test_exception_in_nudge_block_returns_0(self):
        # The armed conditions hold (this env returns 2 normally — see O10). Force
        # nudge_decision (called only inside the nudge block's try/except) to raise
        # and prove the block fails open to 0 rather than escaping or returning 2.
        orig = P.nudge_decision
        P.nudge_decision = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            rc = P.hook_run(self._payload(), env=self._env())
        finally:
            P.nudge_decision = orig
        self.assertEqual(rc, 0,
                         "a fault inside the nudge block must fail open to 0, never 2")

    def test_armed_baseline_returns_2(self):
        # Guard: prove the harness IS armed, so the fail-open test above is meaningful.
        rc = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# O10 — warm submit clears cold_nudged AND that clear persists through a prune
# ---------------------------------------------------------------------------

class TestO10bWarmResetPersistence(_ArmedHarness):
    def test_cold_arm_then_warm_clears_and_persists_through_prune(self):
        # 1) Cold submit arms: returns 2, persists cold_nudged=True, skips prune.
        rc1 = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc1, 2)
        self.assertTrue(P.load_state()["sess"].get("cold_nudged"))

        # 2) A warm, GROWN transcript arrives (recent timestamp, larger body so it
        #    exceeds min_growth and actually prunes — exercising the carry-forward).
        self._write_transcript(_warm_ts(), result_bytes=40000)
        before = os.path.getsize(self.path)
        rc2 = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc2, 0, "warm submit must not block")

        # 3) The clear is persisted to disk (not just decided in memory)...
        self.assertFalse(P.load_state()["sess"].get("cold_nudged"),
                         "warm submit must persist the cold_nudged clear")
        # ...and the prune actually ran (carry-forward path, not a short-circuit).
        self.assertLess(os.path.getsize(self.path), before,
                        "warm grown transcript should have pruned")


# ---------------------------------------------------------------------------
# O2 (LOW) — dry mode never ENTERS the nudge block (no state mutation)
# ---------------------------------------------------------------------------

class TestO2bDryModeSkipsNudgeBlock(_ArmedHarness):
    def test_dry_mode_does_not_touch_cold_nudged(self):
        # Armed-eligible state, but PRUNE=dry → cfg.execute False → nudge block
        # is gated out entirely; the cold_nudged marker is never written.
        P.hook_run(self._payload(), env=self._env(CODEARBITER_PRUNE="dry"))
        self.assertIsNone(P.load_state().get("sess", {}).get("cold_nudged"),
                          "dry mode must not enter the nudge block")


if __name__ == "__main__":
    unittest.main(verbosity=2)
