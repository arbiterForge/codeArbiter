"""Tests for _ledgerlib — the cost/token ledger subsystem extracted from
statusline.py (T-12). Stdlib unittest only; no subprocess, no real ~/.codearbiter.

Covers the ledger's filesystem layer: v2 summary persistence, TTL pruning,
locking, write amplification and persist_sess_start, plus the separate Pi usage
ledger. Pricing is tested in test_usagelib.py and transcript accounting in
test_ledger_accounting.py.
"""
import json
import glob
import shutil
import inspect
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, time as datetime_time, timedelta
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _hooklib
import _ledgerlib as L
from _helpers import redirect_home, restore_home


# Successful-contention tests need scheduler headroom; production's bounded
# fail-soft latency has separate assertions below.
CONCURRENCY_TEST_WAIT = 5.0


# Pricing now lives in test_usagelib.py, and transcript accumulation (bounded
# streaming, identity, reconciliation, coverage) in test_ledger_accounting.py.
# This file keeps the persistence, pruning, locking and write-amplification
# contracts of the ledger's filesystem layer.


# =========================================================================== persistence
class TestPersistence(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._home = redirect_home(self.tmp)
        self._orig = os.environ.get("CODEARBITER_LEDGER")
        self.ledger = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        os.environ["CODEARBITER_LEDGER"] = self.ledger

    def tearDown(self):
        restore_home(self._home)
        if self._orig is None:
            os.environ.pop("CODEARBITER_LEDGER", None)
        else:
            os.environ["CODEARBITER_LEDGER"] = self._orig

    def _write_tx(self, entries, name="transcript.jsonl"):
        tx = os.path.join(self.tmp, name)
        with open(tx, "w", encoding="utf-8") as f:
            for o in entries:
                f.write(json.dumps(o) + "\n")
        return tx

    def _assistant(self, req, inp=200, out=100):
        return {"type": "assistant", "requestId": req,
                "timestamp": "2026-01-01T12:00:00Z",
                "message": {"model": "claude-sonnet-4-6",
                            "usage": {"input_tokens": inp, "output_tokens": out}}}

    def _summary(self, sid):
        with open(L._acct_file(self.ledger, sid), encoding="utf-8") as f:
            return json.load(f)["rec"]

    def _serialize_transactions(self, first, second, while_first_holds=None):
        """Prove the second writer cannot acquire until the first releases."""
        real_acquire = L._acquire_lock
        first_acquired = threading.Event()
        second_attempted = threading.Event()
        second_acquired = threading.Event()
        release_first = threading.Event()
        outputs = {}

        def coordinated_acquire(path, wait_seconds=None):
            if threading.current_thread().name == "ledger-second":
                second_attempted.set()
            # Serialization tests need scheduler headroom, not the render's
            # 20 ms try-lock; production's bounded wait is asserted separately.
            token = real_acquire(path, CONCURRENCY_TEST_WAIT)
            if token is not None and threading.current_thread().name == "ledger-first":
                first_acquired.set()
                self.assertTrue(release_first.wait(CONCURRENCY_TEST_WAIT))
            elif token is not None and threading.current_thread().name == "ledger-second":
                second_acquired.set()
            return token

        one = threading.Thread(target=lambda: outputs.setdefault("first", first()),
                               name="ledger-first")
        two = threading.Thread(target=lambda: outputs.setdefault("second", second()),
                               name="ledger-second")
        with mock.patch.object(L, "_acquire_lock", side_effect=coordinated_acquire):
            one.start()
            self.assertTrue(first_acquired.wait(CONCURRENCY_TEST_WAIT))
            if while_first_holds:
                while_first_holds()
            two.start()
            self.assertTrue(second_attempted.wait(CONCURRENCY_TEST_WAIT))
            # Time-bounded negative wait (E-4): the second thread gets a real
            # window to sneak an acquisition through before the first releases.
            self.assertFalse(second_acquired.wait(0.2))
            release_first.set()
            self.assertTrue(second_acquired.wait(CONCURRENCY_TEST_WAIT))
            one.join(CONCURRENCY_TEST_WAIT)
            two.join(CONCURRENCY_TEST_WAIT)
        self.assertFalse(one.is_alive())
        self.assertFalse(two.is_alive())
        return outputs

    def test_ledger_update_returns_three_tuple(self):
        tx = self._write_tx([self._assistant("r1")])
        out = L.ledger_update({"transcript_path": tx}, "sid-1")
        self.assertIsInstance(out, tuple)
        self.assertEqual(len(out), 3)

    def test_ledger_update_no_sid_is_unavailable_not_zero_claim(self):
        _rec, sess, day = L.ledger_update({}, None)
        self.assertEqual(sess["in"], 0.0)
        self.assertEqual(sess["state"], "unavailable")
        self.assertEqual(day["state"], "unavailable")

    def test_ledger_update_writes_v2_summary_not_the_legacy_snapshot(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-write")
        self.assertEqual(self._summary("sid-write")["sid"], "sid-write")
        self.assertFalse(os.path.exists(self.ledger))

    def test_ledger_update_dedup(self):
        tx = self._write_tx([self._assistant("r1", inp=100, out=50),
                             self._assistant("r1", inp=100, out=50)])
        _rec, sess, _day = L.ledger_update({"transcript_path": tx}, "sid-dup")
        self.assertEqual(sess["in"], 100.0)
        self.assertEqual(sess["out"], 50.0)

    def test_ttl_prunes_stale_v2_session_files(self):
        L.ledger_update({}, "old")
        acct = L._acct_file(self.ledger, "old")
        with open(acct, encoding="utf-8") as f:
            payload = json.load(f)
        payload["rec"]["last_ts"] = time.time() - (L.SESSION_TTL + 100)
        with open(acct, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        L._atomic_json(L._start_file(self.ledger, "old"), {"sid": "old", "sess_start": 1.0})
        os.makedirs(L._ev_dir(self.ledger, "old"), exist_ok=True)
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-fresh")
        self.assertFalse(os.path.exists(acct))
        self.assertFalse(os.path.exists(L._start_file(self.ledger, "old")))
        self.assertFalse(os.path.exists(L._ev_dir(self.ledger, "old")))
        self.assertTrue(os.path.exists(L._acct_file(self.ledger, "sid-fresh")))

    def test_host_cost_is_kept_separate_from_reconstructed_cost(self):
        tx = self._write_tx([self._assistant("r1", inp=10**6, out=0)])
        data = {"transcript_path": tx, "cost": {"total_cost_usd": 4.20}}
        _rec, sess, _day = L.ledger_update(data, "sid-cost")
        self.assertAlmostEqual(sess["cost"], 3.0)       # 1M input @ Sonnet 4.6 $3
        self.assertEqual(sess["host"], 4.20)

    def test_persist_sess_start_seeds_cache(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-ss")
        self.assertTrue(L.persist_sess_start("sid-ss", 1700000000.0))
        rec, _s, _d = L.ledger_update({"transcript_path": tx}, "sid-ss")
        self.assertEqual(rec["sess_start"], 1700000000.0)
        self.assertEqual(self._summary("sid-ss")["sess_start"], 1700000000.0)

    def test_persist_sess_start_idempotent(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-ss2")
        self.assertTrue(L.persist_sess_start("sid-ss2", 123.0))
        self.assertFalse(L.persist_sess_start("sid-ss2", 123.0))

    def test_persist_sess_start_unknown_session(self):
        self.assertFalse(L.persist_sess_start("nope", 5.0))

    def test_persist_sess_start_blank_args(self):
        self.assertFalse(L.persist_sess_start(None, 5.0))
        self.assertFalse(L.persist_sess_start("sid", 0))

    def test_concurrent_distinct_session_updates_both_survive(self):
        tx_a = self._write_tx([self._assistant("a1", inp=10, out=1)], "a.jsonl")
        tx_b = self._write_tx([self._assistant("b1", inp=20, out=2)], "b.jsonl")
        with mock.patch.object(L, "_today", lambda: "2026-01-01"):
            outputs = self._serialize_transactions(
                lambda: L.ledger_update({"transcript_path": tx_a,
                                         "cost": {"total_cost_usd": 1.0}}, "sid-a"),
                lambda: L.ledger_update({"transcript_path": tx_b,
                                         "cost": {"total_cost_usd": 2.0}}, "sid-b"))
        self.assertEqual(self._summary("sid-a")["host"]["max"], 1.0)
        self.assertEqual(self._summary("sid-b")["host"]["max"], 2.0)
        self.assertEqual(outputs["second"][2]["in"], 30.0)

    def test_persist_sess_start_cannot_discard_concurrent_cost_update(self):
        """The session-start cache write must not replace fresher accounting."""
        L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "sid-race")
        outputs = self._serialize_transactions(
            lambda: L.persist_sess_start("sid-race", 123.0),
            lambda: L.ledger_update({"cost": {"total_cost_usd": 9.0}}, "sid-race"))
        self.assertTrue(outputs["first"])
        rec = self._summary("sid-race")
        self.assertEqual(rec["sess_start"], 123.0)
        self.assertEqual(rec["host"]["max"], 9.0)

    def test_same_session_concurrent_updates_do_not_regress_accounting(self):
        tx = self._write_tx([self._assistant("r1", inp=100, out=50)])
        L.ledger_update({"transcript_path": tx, "cost": {"total_cost_usd": 1.0}}, "sid-same")
        with open(tx, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._assistant("r2", inp=200, out=80)) + "\n")

        def append_newer_request():
            with open(tx, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._assistant("r3", inp=300, out=90)) + "\n")

        outputs = self._serialize_transactions(
            lambda: L.ledger_update({"transcript_path": tx,
                                     "cost": {"total_cost_usd": 2.0}}, "sid-same"),
            lambda: L.ledger_update({"transcript_path": tx,
                                     "cost": {"total_cost_usd": 3.0}}, "sid-same"),
            append_newer_request)
        rec = self._summary("sid-same")
        self.assertEqual(rec["host"]["max"], 3.0)
        self.assertEqual(rec["src"]["p"]["off"], os.path.getsize(tx))
        self.assertEqual(outputs["second"][1]["in"], 600.0)
        self.assertEqual(outputs["second"][1]["out"], 220.0)

    def test_failed_atomic_replace_preserves_target_and_removes_temp(self):
        os.makedirs(os.path.dirname(self.ledger), exist_ok=True)
        with open(self.ledger, "w", encoding="utf-8") as f:
            json.dump({"valid": True}, f)
        with mock.patch.object(L.os, "replace", side_effect=OSError("interrupted")):
            self.assertFalse(L._atomic_json(self.ledger, {"valid": False}))
        with open(self.ledger, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"valid": True})
        self.assertEqual(glob.glob(f"{self.ledger}.*.tmp"), [])

    def test_expired_legacy_shards_are_deleted_by_mtime_without_being_read(self):
        stale = {"last_ts": time.time()}            # content says live; mtime says expired
        legacy = L._session_file(self.ledger, "expired")
        start = L._start_file(self.ledger, "expired")
        self.assertTrue(L._atomic_json(legacy, {"sid": "expired", "rec": stale}))
        self.assertTrue(L._atomic_json(start, {"sid": "expired", "sess_start": 123.0}))
        old = time.time() - L.SESSION_TTL - 60
        os.utime(legacy, (old, old))
        reads = []
        real = L._read_json

        def spy(path, default=None):
            reads.append(path)
            return real(path, default)
        with mock.patch.object(L, "_read_json", spy):
            L.ledger_update({}, "fresh")
        self.assertFalse(os.path.exists(legacy))
        self.assertFalse(os.path.exists(start))
        self.assertNotIn(legacy, reads)

    def test_bare_filename_ledger_path_works(self):
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmp)
            os.environ["CODEARBITER_LEDGER"] = "ledger.json"
            L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "bare")
            self.assertTrue(os.path.exists(L._acct_file("ledger.json", "bare")))
        finally:
            os.chdir(old_cwd)

    def test_render_lock_contention_uses_bounded_try_lock_and_stale_view(self):
        L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "contended")
        owner = L._acquire_lock(self.ledger)
        self.assertIsNotNone(owner)
        try:
            # Drive the real lock's deadline clock deterministically: the render
            # gets exactly its UI_LOCK_WAIT budget, then must fall back to the
            # committed summary without another retry sleep.
            wait = L.UI_LOCK_WAIT
            with mock.patch.object(_hooklib, "time") as clock:
                clock.monotonic.side_effect = (100.0, 100.0 + wait - 0.001, 100.0 + wait)
                rec, sess, day = L.ledger_update({}, "contended")
            self.assertEqual(clock.monotonic.call_count, 3)
            self.assertEqual(clock.sleep.call_args_list, [mock.call(0.005)])
            self.assertTrue(sess["stale"])
            self.assertEqual(sess["host"], 1.0)
            self.assertEqual(rec["sid"], "contended")
            wait = _hooklib.LOCK_WAIT
            with mock.patch.object(_hooklib, "time") as clock:
                clock.monotonic.side_effect = (200.0, 200.0 + wait - 0.001, 200.0 + wait)
                self.assertFalse(L.persist_sess_start("contended", 123.0))
        finally:
            L._release_lock(owner)

    def test_lock_release_allows_next_transaction(self):
        owner = L._acquire_lock(self.ledger)
        self.assertIsNotNone(owner)
        L._release_lock(owner)
        next_owner = L._acquire_lock(self.ledger)
        self.assertIsNotNone(next_owner)
        L._release_lock(next_owner)

    def test_non_owner_cannot_release_live_lock(self):
        owner = L._acquire_lock(self.ledger)
        self.assertIsNotNone(owner)
        try:
            L._release_lock(None)
            wait = _hooklib.LOCK_WAIT
            with mock.patch.object(_hooklib, "time") as clock:
                clock.monotonic.side_effect = (
                    300.0, 300.0 + wait - 0.001, 300.0 + wait,
                )
                self.assertIsNone(L._acquire_lock(self.ledger))
            self.assertEqual(clock.monotonic.call_count, 3)
            clock.sleep.assert_called_once_with(0.005)
        finally:
            L._release_lock(owner)

    def test_malformed_other_summary_is_deleted_and_own_bad_start_ignored(self):
        directory = L._session_dir(self.ledger)
        os.makedirs(directory, exist_ok=True)
        bad_summary = os.path.join(directory, "b" * 64 + ".acct.json")
        with open(bad_summary, "w", encoding="utf-8") as f:
            f.write("not json")
        with open(L._start_file(self.ledger, "fresh"), "w", encoding="utf-8") as f:
            f.write("[]")
        rec, _s, _d = L.ledger_update({}, "fresh")
        self.assertFalse(os.path.exists(bad_summary))
        self.assertNotIn("sess_start", rec)

    def test_nonnumeric_session_start_metadata_is_ignored(self):
        L.ledger_update({}, "live")
        self.assertTrue(L._atomic_json(L._start_file(self.ledger, "live"),
                                       {"sid": "live", "sess_start": "invalid"}))
        rec, _s, _d = L.ledger_update({}, "live")
        self.assertNotIn("sess_start", rec)

    def test_misnamed_stale_summary_cannot_delete_embedded_sid_files(self):
        L.ledger_update({}, "victim")
        self.assertTrue(L.persist_sess_start("victim", 123.0))
        victim_summary = L._acct_file(self.ledger, "victim")
        victim_start = L._start_file(self.ledger, "victim")
        with open(victim_summary, encoding="utf-8") as f:
            payload = json.load(f)
        payload["rec"]["last_ts"] = time.time() - L.SESSION_TTL - 1
        misnamed = os.path.join(L._session_dir(self.ledger), "c" * 64 + ".acct.json")
        self.assertTrue(L._atomic_json(misnamed, payload))
        L.ledger_update({}, "other")
        self.assertFalse(os.path.exists(misnamed))
        self.assertTrue(os.path.exists(victim_summary))
        self.assertTrue(os.path.exists(victim_start))


# =========================================================================== Pi usage persistence
class TestPiUsageLedger(unittest.TestCase):
    """Separate, content-free Pi usage shards keyed by a caller-derived digest."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp = self._temp.name
        self._home = redirect_home(self.tmp)
        self._orig_pi = os.environ.get("CODEARBITER_PI_LEDGER")
        self._orig_claude = os.environ.get("CODEARBITER_LEDGER")
        self.pi_ledger = os.path.join(self.tmp, ".codearbiter", "pi-usage-ledger.json")
        self.claude_ledger = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        os.environ.pop("CODEARBITER_PI_LEDGER", None)
        os.environ["CODEARBITER_LEDGER"] = self.claude_ledger
        self.session_key = "a" * 64
        local_now = datetime.now().astimezone()
        self.local_day = local_now.date()
        self.timestamp = datetime.combine(
            self.local_day, datetime_time(12, 0), tzinfo=local_now.tzinfo
        ).isoformat()

    def tearDown(self):
        restore_home(self._home)
        for name, value in (("CODEARBITER_PI_LEDGER", self._orig_pi),
                            ("CODEARBITER_LEDGER", self._orig_claude)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._temp.cleanup()

    def _require_api(self):
        self.assertTrue(callable(getattr(L, "pi_ledger_update", None)),
                        "T05a RED: pi_ledger_update is not implemented")
        self.assertTrue(callable(getattr(L, "pi_ledger_path", None)),
                        "T05a RED: pi_ledger_path is not implemented")

    def _require_scan_api(self):
        self._require_api()
        parameters = inspect.signature(L.pi_ledger_update).parameters
        self.assertIn("scan_start", parameters,
                      "T05a correction RED: acknowledged scan ranges are not implemented")
        self.assertIn("scan_end", parameters,
                      "T05a correction RED: acknowledged scan ranges are not implemented")

    def _require_path_api(self):
        self._require_scan_api()
        self.assertIn("path", inspect.signature(L.pi_ledger_update).parameters,
                      "T05a correction RED: explicit safe test path is not implemented")

    def _fact(self, position, timestamp=None, **overrides):
        fact = {
            "position": position,
            "timestamp": timestamp or self.timestamp,
            "inputTokens": 10,
            "outputTokens": 4,
            "cacheReadTokens": 3,
            "cacheWriteTokens": 2,
            "costUsd": 0.25,
        }
        fact.update(overrides)
        return fact

    def _update(self, facts, session_key=None, scan_start=None, scan_end=None, path=None):
        self._require_api()
        if scan_start is None or scan_end is None:
            if isinstance(facts, list) and facts \
                    and isinstance(facts[0], dict) and isinstance(facts[-1], dict):
                scan_start = facts[0].get("position", 0) if scan_start is None else scan_start
                scan_end = facts[-1].get("position", scan_start) if scan_end is None else scan_end
            else:
                scan_start = 0 if scan_start is None else scan_start
                scan_end = scan_start if scan_end is None else scan_end
        arguments = (
            self.session_key if session_key is None else session_key,
            scan_start,
            scan_end,
            facts,
        )
        return L.pi_ledger_update(*arguments) if path is None \
            else L.pi_ledger_update(*arguments, path=path)

    def _shard_path(self, session_key=None):
        return os.path.join(f"{self.pi_ledger}.sessions",
                            f"{session_key or self.session_key}.json")

    def test_replay_and_next_contiguous_range_add_only_new_positions(self):
        first = [self._fact(0), self._fact(3)]
        result = self._update(first, scan_start=0, scan_end=3)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["acceptedThrough"], 3)
        self.assertEqual(result["highWater"], 3)
        self.assertEqual(result["session"]["inputTokens"], 20)

        replay = self._update(first, scan_start=0, scan_end=3)
        self.assertEqual(replay, result)

        continued = self._update([self._fact(8)], scan_start=4, scan_end=8)
        self.assertEqual(continued["status"], "ok")
        self.assertEqual(continued["acceptedThrough"], 8)
        self.assertEqual(continued["highWater"], 8)
        self.assertEqual(continued["session"], {
            "inputTokens": 30, "outputTokens": 12,
            "cacheReadTokens": 9, "cacheWriteTokens": 6,
            "costUsd": 0.75,
        })

    def test_replay_acknowledges_requested_range_separately_from_durable_high_water(self):
        advanced = self._update(
            [self._fact(0), self._fact(8)], scan_start=0, scan_end=8
        )
        self.assertEqual(advanced["status"], "ok")
        self.assertEqual(advanced["acceptedThrough"], 8)
        self.assertEqual(advanced["highWater"], 8)

        replay = self._update([self._fact(0)], scan_start=0, scan_end=3)
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(replay["acceptedThrough"], 3)
        self.assertEqual(replay["highWater"], 8)
        self.assertEqual(replay["session"], advanced["session"])

    def test_scan_range_failure_blocks_later_range_until_retry(self):
        self._require_scan_api()
        first = [self._fact(2)]
        with mock.patch.object(L, "_atomic_json", return_value=False):
            failed = self._update(first, scan_start=0, scan_end=2)
        self.assertEqual(failed["status"], "write_failed")
        self.assertEqual(failed["acceptedThrough"], -1)
        self.assertEqual(failed["highWater"], -1)

        later = self._update([], scan_start=3, scan_end=3)
        self.assertEqual(later["status"], "invalid")
        self.assertFalse(os.path.exists(self._shard_path()))

        retried = self._update(first, scan_start=0, scan_end=2)
        self.assertEqual(retried["status"], "ok")
        self.assertEqual(retried["highWater"], 2)
        continued = self._update([], scan_start=3, scan_end=3)
        self.assertEqual(continued["status"], "ok")
        self.assertEqual(continued["highWater"], 3)
        self.assertEqual(continued["session"], retried["session"])

    def test_scan_range_rejects_overlap_gap_and_out_of_range_fact(self):
        self._require_scan_api()
        first = self._update([self._fact(3)], scan_start=0, scan_end=3)
        self.assertEqual(first["highWater"], 3)

        overlap = self._update([self._fact(4)], scan_start=2, scan_end=4)
        gap = self._update([], scan_start=5, scan_end=5)
        outside = self._update([self._fact(5)], scan_start=4, scan_end=4)
        self.assertEqual(overlap["status"], "invalid")
        self.assertEqual(gap["status"], "invalid")
        self.assertEqual(outside["status"], "invalid")

        valid = self._update([], scan_start=4, scan_end=4)
        self.assertEqual(valid["status"], "ok")
        self.assertEqual(valid["highWater"], 4)
        self.assertEqual(valid["session"], first["session"])
        replay = self._update([self._fact(3)], scan_start=0, scan_end=3)
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(replay["acceptedThrough"], 3)
        self.assertEqual(replay["highWater"], 4)
        self.assertEqual(replay["session"], valid["session"])
        self.assertEqual(replay["today"], valid["today"])

    def test_replayed_range_repairs_root_cache_after_shard_success(self):
        with mock.patch.object(L, "_write_pi_snapshot",
                               return_value=False) as cache_write:
            failed = self._update([self._fact(0)], scan_start=0, scan_end=0)
        cache_write.assert_called_once()
        self.assertEqual(failed["status"], "write_failed")
        self.assertEqual(failed["highWater"], 0)
        self.assertTrue(os.path.exists(self._shard_path()))
        self.assertFalse(os.path.exists(self.pi_ledger))

        repaired = self._update([self._fact(0)], scan_start=0, scan_end=0)
        self.assertEqual(repaired["status"], "ok")
        self.assertEqual(repaired["highWater"], 0)
        self.assertTrue(
            os.path.exists(self.pi_ledger),
            "an acknowledged-range replay did not repair the root cache",
        )
        with open(self.pi_ledger, encoding="utf-8") as stream:
            snapshot = json.load(stream)
        self.assertEqual(snapshot["today"], repaired["today"])

    def test_replay_pruning_rewrites_cache_from_retained_shards(self):
        keys = ("a" * 64, "b" * 64, "c" * 64)
        for key, updated_at in zip(keys, (100, 200, 300)):
            with mock.patch.object(L.time, "time", return_value=updated_at):
                result = self._update([self._fact(0)], key)
            self.assertEqual(result["status"], "ok")
        with open(self.pi_ledger, encoding="utf-8") as stream:
            before = json.load(stream)
        self.assertEqual(before["today"]["inputTokens"], 30)

        with mock.patch.object(L, "PI_MAX_SHARDS", 2):
            replay = self._update([self._fact(0)], keys[0])
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(replay["today"]["inputTokens"], 20)
        self.assertTrue(os.path.exists(self._shard_path(keys[0])))
        self.assertFalse(os.path.exists(self._shard_path(keys[1])))
        self.assertTrue(os.path.exists(self._shard_path(keys[2])))
        with open(self.pi_ledger, encoding="utf-8") as stream:
            after = json.load(stream)
        self.assertEqual(after["today"], replay["today"])

    def test_same_timestamp_at_distinct_positions_counts_both(self):
        result = self._update([self._fact(0), self._fact(1)], scan_start=0, scan_end=1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["highWater"], 1)
        self.assertEqual(result["session"]["inputTokens"], 20)
        self.assertEqual(result["today"]["inputTokens"], 20)

    def test_local_midnight_splits_today_from_whole_session(self):
        zone = datetime.now().astimezone().tzinfo
        yesterday = datetime.combine(
            self.local_day - timedelta(days=1), datetime_time(23, 59), tzinfo=zone
        ).isoformat()
        today = datetime.combine(
            self.local_day, datetime_time(0, 1), tzinfo=zone
        ).isoformat()
        result = self._update([
            self._fact(0, yesterday, inputTokens=100, costUsd=1.0),
            self._fact(1, today, inputTokens=7, costUsd=0.5),
        ])
        self.assertEqual(result["session"]["inputTokens"], 107)
        self.assertEqual(result["session"]["costUsd"], 1.5)
        self.assertEqual(result["today"]["inputTokens"], 7)
        self.assertEqual(result["today"]["costUsd"], 0.5)

    def test_maximum_chunk_then_followup_chunk_advances_high_water(self):
        self._require_api()
        first = [self._fact(position, inputTokens=1, outputTokens=0,
                            cacheReadTokens=0, cacheWriteTokens=0, costUsd=0)
                 for position in range(L.PI_MAX_SCAN_ENTRIES)]
        one = self._update(first)
        two = self._update([
            self._fact(position, inputTokens=1, outputTokens=0,
                       cacheReadTokens=0, cacheWriteTokens=0, costUsd=0)
            for position in range(L.PI_MAX_SCAN_ENTRIES, L.PI_MAX_SCAN_ENTRIES + 45)
        ])
        self.assertEqual(one["highWater"], L.PI_MAX_SCAN_ENTRIES - 1)
        self.assertEqual(two["highWater"], L.PI_MAX_SCAN_ENTRIES + 44)
        self.assertEqual(two["session"]["inputTokens"], L.PI_MAX_SCAN_ENTRIES + 45)

    def test_two_sessions_serialize_on_shared_real_os_lock(self):
        self._require_api()
        real_acquire = L._acquire_lock
        first_acquired = threading.Event()
        second_attempted = threading.Event()
        second_acquired = threading.Event()
        release_first = threading.Event()
        outputs = {}

        def coordinated_acquire(path):
            if threading.current_thread().name == "pi-ledger-second":
                second_attempted.set()
            handle = real_acquire(path)
            if handle is not None and threading.current_thread().name == "pi-ledger-first":
                first_acquired.set()
                self.assertTrue(release_first.wait(CONCURRENCY_TEST_WAIT))
            elif handle is not None and threading.current_thread().name == "pi-ledger-second":
                second_acquired.set()
            return handle

        one = threading.Thread(
            target=lambda: outputs.setdefault("first", self._update([self._fact(0)])),
            name="pi-ledger-first",
        )
        two = threading.Thread(
            target=lambda: outputs.setdefault(
                "second", self._update([self._fact(0)], "b" * 64)
            ),
            name="pi-ledger-second",
        )
        with mock.patch.object(_hooklib, "LOCK_WAIT", CONCURRENCY_TEST_WAIT), \
                mock.patch.object(L, "_acquire_lock", side_effect=coordinated_acquire):
            one.start()
            self.assertTrue(first_acquired.wait(CONCURRENCY_TEST_WAIT))
            two.start()
            self.assertTrue(second_attempted.wait(CONCURRENCY_TEST_WAIT))
            self.assertFalse(second_acquired.wait(0.2))
            release_first.set()
            self.assertTrue(second_acquired.wait(CONCURRENCY_TEST_WAIT))
            one.join(CONCURRENCY_TEST_WAIT)
            two.join(CONCURRENCY_TEST_WAIT)
        self.assertFalse(one.is_alive())
        self.assertFalse(two.is_alive())
        self.assertEqual(outputs["first"]["status"], "ok")
        self.assertEqual(outputs["second"]["status"], "ok")
        self.assertEqual(outputs["second"]["today"]["inputTokens"], 20)

    def test_corrupt_shard_fails_soft_without_replacing_it(self):
        self._require_api()
        os.makedirs(os.path.dirname(self._shard_path()), exist_ok=True)
        original = b"not-json-and-must-survive"
        with open(self._shard_path(), "wb") as stream:
            stream.write(original)
        result = self._update([self._fact(0)])
        self.assertEqual(result, {
            "status": "corrupt",
            "session": L.pi_blank_totals(),
            "today": L.pi_blank_totals(),
            "acceptedThrough": -1,
            "highWater": -1,
        })
        with open(self._shard_path(), "rb") as stream:
            self.assertEqual(stream.read(), original)

    def test_oversized_malformed_and_regressive_chunks_fail_without_writes(self):
        self._require_api()
        invalid_chunks = (
            [self._fact(position) for position in range(L.PI_MAX_SCAN_ENTRIES + 1)],
            [self._fact(2), self._fact(1)],
            [self._fact(1), self._fact(1)],
            [dict(self._fact(1), message="must-not-persist")],
            [{"position": 1}],
            "not-a-list",
        )
        for index, facts in enumerate(invalid_chunks, 1):
            key = f"{index:064x}"
            with self.subTest(index=index):
                result = self._update(facts, key)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(set(result), {
                    "status", "session", "today", "acceptedThrough", "highWater"
                })
                self.assertFalse(os.path.exists(self._shard_path(key)))

    def test_identity_numeric_and_date_bounds_fail_soft(self):
        self._require_api()
        invalid = (
            ("", [self._fact(0)]),
            ("raw-session-id", [self._fact(0)]),
            ("A" * 64, [self._fact(0)]),
            ("a" * 63, [self._fact(0)]),
            (self.session_key, [self._fact(True)]),
            (self.session_key, [self._fact(0, inputTokens=-1)]),
            (self.session_key, [self._fact(0, outputTokens=1.5)]),
            (self.session_key, [self._fact(0, cacheReadTokens=1_000_000_000_000_001)]),
            (self.session_key, [self._fact(0, costUsd=float("nan"))]),
            (self.session_key, [self._fact(0, costUsd=10 ** 1000)]),
            (self.session_key, [self._fact(0, "not-a-date")]),
            (self.session_key, [self._fact(0, "2026-07-19\u008012:00:00+00:00")]),
            (self.session_key, [self._fact(0, "1999-12-31T23:59:59Z")]),
            (self.session_key, [self._fact(0, "2101-01-01T00:00:00Z")]),
        )
        for index, (key, facts) in enumerate(invalid):
            with self.subTest(index=index):
                result = self._update(facts, key)
                self.assertEqual(result["status"], "invalid")

    def test_lock_and_write_failures_use_fixed_status_and_preserve_shard(self):
        initial = self._update([self._fact(0)])
        self.assertEqual(initial["status"], "ok")
        with open(self._shard_path(), "rb") as stream:
            original = stream.read()
        with mock.patch.object(L, "_acquire_lock", return_value=None):
            locked = self._update([self._fact(1)])
        self.assertEqual(locked["status"], "lock_failed")
        with mock.patch.object(L, "_acquire_lock", side_effect=OSError("lock path unavailable")):
            lock_error = self._update([self._fact(1)])
        self.assertEqual(lock_error["status"], "lock_failed")
        with mock.patch.object(L, "_atomic_json", return_value=False):
            failed = self._update([self._fact(1)])
        self.assertEqual(failed["status"], "write_failed")
        with open(self._shard_path(), "rb") as stream:
            self.assertEqual(stream.read(), original)

    def test_oversized_shard_is_rejected_before_json_parse_and_preserved(self):
        self._require_api()
        self.assertTrue(hasattr(L, "PI_MAX_SHARD_BYTES"),
                        "T05a RED: persisted shard byte bound is not implemented")
        os.makedirs(os.path.dirname(self._shard_path()), exist_ok=True)
        original = b"{" + (b" " * L.PI_MAX_SHARD_BYTES) + b"}"
        with open(self._shard_path(), "wb") as stream:
            stream.write(original)
        reader = mock.Mock(side_effect=AssertionError("oversized shard must not be parsed"))
        with mock.patch.object(L, "_read_json", reader):
            result = self._update([self._fact(0)])
        self.assertEqual(result["status"], "corrupt")
        reader.assert_not_called()
        with open(self._shard_path(), "rb") as stream:
            self.assertEqual(stream.read(), original)

    def test_sixty_fifth_local_day_evicts_oldest_bucket_not_session_total(self):
        base = datetime(2020, 1, 1).date()
        result = None
        for position in range(L.PI_MAX_DAYS + 1):
            day = (base + timedelta(days=position)).isoformat()
            result = self._update([
                self._fact(position, f"{day}T12:00:00Z", inputTokens=1,
                           outputTokens=0, cacheReadTokens=0,
                           cacheWriteTokens=0, costUsd=0),
            ], scan_start=position, scan_end=position)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["highWater"], L.PI_MAX_DAYS)
        self.assertEqual(result["session"]["inputTokens"], L.PI_MAX_DAYS + 1)
        with open(self._shard_path(), encoding="utf-8") as stream:
            shard = json.load(stream)
        self.assertEqual(len(shard["days"]), L.PI_MAX_DAYS)
        self.assertNotIn(base.isoformat(), shard["days"])
        self.assertIn((base + timedelta(days=L.PI_MAX_DAYS)).isoformat(), shard["days"])
        self.assertIs(type(shard["updatedAt"]), int)

    def test_shard_retention_ignores_unrelated_files_and_keeps_current(self):
        keys = ("a" * 64, "b" * 64, "c" * 64)
        with mock.patch.object(L, "PI_MAX_SHARDS", 2):
            with mock.patch.object(L.time, "time", return_value=100):
                self.assertEqual(self._update([self._fact(0)], keys[0])["status"], "ok")
            with mock.patch.object(L.time, "time", return_value=200):
                self.assertEqual(self._update([self._fact(0)], keys[1])["status"], "ok")
            directory = f"{self.pi_ledger}.sessions"
            unrelated = (
                os.path.join(directory, "keep-note.txt"),
                os.path.join(directory, "interrupted.tmp"),
                os.path.join(directory, "not-a-pi-session.json"),
            )
            for path in unrelated:
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("unrelated")
            with mock.patch.object(L.time, "time", return_value=50):
                current = self._update([self._fact(0)], keys[2])
        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["today"]["inputTokens"], 20)
        self.assertFalse(os.path.exists(self._shard_path(keys[0])))
        self.assertTrue(os.path.exists(self._shard_path(keys[1])))
        self.assertTrue(os.path.exists(self._shard_path(keys[2])))
        for path in unrelated:
            self.assertTrue(os.path.exists(path))

    def test_valid_session_shard_retention_bound_is_256(self):
        self.assertEqual(L.PI_MAX_SHARDS, 256)

    def test_unrelated_entries_do_not_consume_recognized_shard_scan_bound(self):
        directory = f"{self.pi_ledger}.sessions"
        os.makedirs(directory, exist_ok=True)
        unrelated = (
            os.path.join(directory, "keep-note.txt"),
            os.path.join(directory, "interrupted.tmp"),
            os.path.join(directory, "not-a-pi-session.json"),
        )
        for path in unrelated:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("unrelated")
        with mock.patch.object(L, "PI_MAX_DIRECTORY_ENTRIES", 1):
            result = self._update([self._fact(0)])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["today"]["inputTokens"], 10)
        for path in unrelated:
            self.assertTrue(os.path.exists(path))

    def test_current_shard_symlink_is_rejected_without_overwrite(self):
        initial = self._update([self._fact(0)])
        self.assertEqual(initial["status"], "ok")
        shard_path = self._shard_path()
        target = os.path.join(self.tmp, "outside-pi-shard.json")
        os.replace(shard_path, target)
        try:
            os.symlink(target, shard_path)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"filesystem symlink unavailable: {type(error).__name__}")
        with open(target, "rb") as stream:
            original = stream.read()

        result = self._update([self._fact(1)], scan_start=1, scan_end=1)
        self.assertEqual(result["status"], "corrupt")
        self.assertTrue(os.path.islink(shard_path))
        with open(target, "rb") as stream:
            self.assertEqual(stream.read(), original)

    def test_aggregate_skips_exact_name_directory_and_symlink_entries(self):
        initial = self._update([self._fact(0)])
        self.assertEqual(initial["status"], "ok")
        directory_entry = self._shard_path("d" * 64)
        os.makedirs(directory_entry)
        target = os.path.join(self.tmp, "not-a-shard.json")
        with open(target, "wb") as stream:
            stream.write(b"must-not-be-opened-as-a-shard")
        symlink_entry = self._shard_path("e" * 64)
        try:
            os.symlink(target, symlink_entry)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"filesystem symlink unavailable: {type(error).__name__}")

        replay = self._update([self._fact(0)])
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(replay["today"], initial["today"])
        self.assertTrue(os.path.isdir(directory_entry))
        self.assertTrue(os.path.islink(symlink_entry))

    def test_pi_default_path_ignores_runtime_environment_override(self):
        os.environ["CODEARBITER_PI_LEDGER"] = self.claude_ledger
        try:
            self.assertEqual(L.pi_ledger_path(), self.pi_ledger)
            result = self._update([self._fact(0)])
        finally:
            os.environ.pop("CODEARBITER_PI_LEDGER", None)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(os.path.exists(self.pi_ledger))
        self.assertFalse(os.path.exists(self.claude_ledger))

    def test_explicit_nonoverlapping_test_path_is_used(self):
        self._require_path_api()
        explicit = os.path.join(self.tmp, "injected", "pi.json")
        result = self._update([self._fact(0)], path=explicit)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(os.path.exists(explicit))
        self.assertTrue(os.path.exists(self._shard_path().replace(self.pi_ledger, explicit)))

    def test_explicit_claude_aliases_reject_before_lock_or_write(self):
        self._require_path_api()
        os.makedirs(os.path.dirname(self.claude_ledger), exist_ok=True)
        with open(self.claude_ledger, "wb") as stream:
            stream.write(b'{"claude":"preserved"}')
        lexical_parent = os.path.join(os.path.dirname(self.claude_ledger), "alias-parent")
        os.makedirs(lexical_parent, exist_ok=True)
        aliases = (
            os.path.join(lexical_parent, "..", os.path.basename(self.claude_ledger)),
            os.path.join(f"{self.claude_ledger}.sessions", "pi-anchor.json"),
            os.path.dirname(self.claude_ledger),
        )
        for explicit in aliases:
            with self.subTest(explicit=explicit), \
                    mock.patch.object(L, "_acquire_lock") as acquire:
                result = self._update([self._fact(0)], path=explicit)
                self.assertEqual(result["status"], "invalid")
                acquire.assert_not_called()
        with open(self.claude_ledger, "rb") as stream:
            self.assertEqual(stream.read(), b'{"claude":"preserved"}')

    def test_explicit_claude_lock_paths_reject_before_lock_or_write(self):
        self._require_path_api()
        claude_lock = f"{self.claude_ledger}.lock"
        candidates = (
            claude_lock,
            os.path.join(claude_lock, "nested", "pi-ledger.json"),
        )
        for explicit in candidates:
            with self.subTest(explicit=explicit), \
                    mock.patch.object(L, "_acquire_lock", return_value=None) as acquire, \
                    mock.patch.object(L, "_atomic_json") as atomic:
                result = self._update([self._fact(0)], path=explicit)
                self.assertEqual(result["status"], "invalid")
                acquire.assert_not_called()
                atomic.assert_not_called()

    def test_reserved_lock_realpath_aliases_reject_before_lock_or_write(self):
        self._require_path_api()
        os.makedirs(os.path.dirname(self.claude_ledger), exist_ok=True)
        claude_lock = f"{self.claude_ledger}.lock"
        with open(claude_lock, "wb") as stream:
            stream.write(b"claude-lock-sentinel")
        claude_sessions = f"{self.claude_ledger}.sessions"
        os.makedirs(claude_sessions)

        anchor_alias = os.path.join(self.tmp, "pi-anchor-lock-alias.json")
        sessions_owner = os.path.join(self.tmp, "pi-sessions-lock-alias.json")
        lock_owner = os.path.join(self.tmp, "pi-lock-sessions-alias.json")
        try:
            os.symlink(claude_lock, anchor_alias)
            os.symlink(claude_lock, f"{sessions_owner}.sessions")
            os.symlink(claude_sessions, f"{lock_owner}.lock", target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"filesystem symlink unavailable: {type(error).__name__}")

        for explicit in (anchor_alias, sessions_owner, lock_owner):
            with self.subTest(explicit=explicit), \
                    mock.patch.object(L, "_acquire_lock", return_value=None) as acquire, \
                    mock.patch.object(L, "_atomic_json") as atomic:
                result = self._update([self._fact(0)], path=explicit)
                self.assertEqual(result["status"], "invalid")
                acquire.assert_not_called()
                atomic.assert_not_called()
        with open(claude_lock, "rb") as stream:
            self.assertEqual(stream.read(), b"claude-lock-sentinel")

    def test_explicit_symlink_alias_to_claude_rejects_before_lock(self):
        self._require_path_api()
        os.makedirs(os.path.dirname(self.claude_ledger), exist_ok=True)
        with open(self.claude_ledger, "wb") as stream:
            stream.write(b'{"claude":"preserved"}')
        alias = os.path.join(self.tmp, "pi-ledger-alias.json")
        try:
            os.symlink(self.claude_ledger, alias)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"filesystem symlink unavailable: {type(error).__name__}")
        with mock.patch.object(L, "_acquire_lock") as acquire:
            result = self._update([self._fact(0)], path=alias)
        self.assertEqual(result["status"], "invalid")
        acquire.assert_not_called()
        self.assertTrue(os.path.islink(alias))
        with open(self.claude_ledger, "rb") as stream:
            self.assertEqual(stream.read(), b'{"claude":"preserved"}')

    def test_pi_path_schema_and_shards_are_separate_and_content_free(self):
        self._require_api()
        os.makedirs(os.path.dirname(self.claude_ledger), exist_ok=True)
        claude_bytes = b'{"claude":"untouched"}'
        with open(self.claude_ledger, "wb") as stream:
            stream.write(claude_bytes)
        result = self._update([self._fact(0)])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(L.pi_ledger_path(), self.pi_ledger)
        self.assertNotEqual(L.pi_ledger_path(), L.ledger_path())
        self.assertEqual(
            L.pi_ledger_path(),
            os.path.join(os.path.expanduser("~"), ".codearbiter", "pi-usage-ledger.json"),
        )
        with open(self.claude_ledger, "rb") as stream:
            self.assertEqual(stream.read(), claude_bytes)
        with open(self.pi_ledger, encoding="utf-8") as stream:
            snapshot = json.load(stream)
        with open(self._shard_path(), encoding="utf-8") as stream:
            shard = json.load(stream)
        self.assertEqual(set(snapshot), {"schema", "date", "today"})
        self.assertEqual(snapshot["schema"], "codearbiter.pi-usage-ledger/v1")
        self.assertEqual(set(shard), {
            "schema", "sessionKey", "highWater", "updatedAt", "totals", "days"
        })
        self.assertEqual(shard["schema"], "codearbiter.pi-usage-session/v1")
        self.assertEqual(shard["sessionKey"], self.session_key)
        self.assertIs(type(shard["updatedAt"]), int)
        self.assertEqual(set(shard["totals"]), {
            "inputTokens", "outputTokens", "cacheReadTokens",
            "cacheWriteTokens", "costUsd",
        })
        self.assertEqual(set(shard["days"]), {self.local_day.isoformat()})
        self.assertEqual(set(shard["days"][self.local_day.isoformat()]),
                         set(shard["totals"]))
        self.assertNotIn("message", shard)
        self.assertNotIn("content", shard)
        self.assertNotIn("path", shard)
        self.assertNotIn("command", shard)
        self.assertNotIn("environment", shard)


# =========================================================================== render write amplification
class TestRenderWriteAmplification(unittest.TestCase):
    """#392 — the statusline renders in a fresh process on every refresh, so a
    render that changed nothing must not replace any file, and a render that DID
    change something must parse each file it reads exactly once."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._home = redirect_home(self.tmp)
        self._orig = os.environ.get("CODEARBITER_LEDGER")
        self.ledger = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        os.environ["CODEARBITER_LEDGER"] = self.ledger
        self.today = datetime.now().strftime("%Y-%m-%d")

    def tearDown(self):
        restore_home(self._home)
        if self._orig is None:
            os.environ.pop("CODEARBITER_LEDGER", None)
        else:
            os.environ["CODEARBITER_LEDGER"] = self._orig

    # ------------------------------------------------------------------ helpers
    def _assistant(self, req, inp=200, out=100):
        # A local-offset "now" timestamp so these tokens land in the CURRENT day.
        return {"type": "assistant", "requestId": req,
                "timestamp": datetime.now().astimezone().isoformat(),
                "message": {"model": "claude-sonnet-4-6",
                            "usage": {"input_tokens": inp, "output_tokens": out}}}

    def _write_tx(self, entries, name="transcript.jsonl"):
        tx = os.path.join(self.tmp, name)
        with open(tx, "w", encoding="utf-8") as f:
            for o in entries:
                f.write(json.dumps(o) + "\n")
        return tx

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _record_writes(self):
        writes = []
        real = L._atomic_json

        def spy(path, value):
            writes.append(path)
            return real(path, value)

        return writes, mock.patch.object(L, "_atomic_json", side_effect=spy)

    def _record_reads(self):
        reads = []
        real = L._read_json

        def spy(path, default=None):
            reads.append(path)
            return real(path, default)

        return reads, mock.patch.object(L, "_read_json", side_effect=spy)

    def _seed_peer(self, sid, tokens_in, pd):
        rec = L._fresh_summary(sid, time.time())
        rec["days"][self.today] = {"in": tokens_in, "out": 0, "pd": pd, "rc": {}}
        rec["tot"] = {"in": tokens_in, "out": 0, "pd": pd}
        rec["last_day"] = self.today
        rec["cov"] = {"state": "complete", "reasons": [], "src_reasons": []}
        self.assertTrue(L._atomic_json(L._acct_file(self.ledger, sid),
                                       {"schema": L.ACCT_SCHEMA, "sid": sid, "seq": 0,
                                        "rec": rec}))

    # ------------------------------------------------------------------ tests
    def test_unchanged_render_replaces_no_file(self):
        tx = self._write_tx([self._assistant("r1")])
        data = {"transcript_path": tx, "cost": {"total_cost_usd": 1.25}}
        L.ledger_update(data, "quiet")
        writes, patcher = self._record_writes()
        with patcher:
            L.ledger_update(data, "quiet")
        self.assertEqual(writes, [])

    def test_unchanged_render_preserves_summary_bytes(self):
        tx = self._write_tx([self._assistant("r1")])
        data = {"transcript_path": tx, "cost": {"total_cost_usd": 1.25}}
        L.ledger_update(data, "quiet")
        acct = L._acct_file(self.ledger, "quiet")
        before = self._read(acct)
        L.ledger_update(data, "quiet")
        self.assertEqual(self._read(acct), before)

    def test_changed_render_reads_each_file_once(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx, "cost": {"total_cost_usd": 1.0}}, "hot")
        for other in ("a", "b", "c"):
            self._seed_peer(other, 10, 5)
        tx = self._write_tx([self._assistant("r1"), self._assistant("r2")])
        reads, patcher = self._record_reads()
        with patcher:
            L.ledger_update({"transcript_path": tx, "cost": {"total_cost_usd": 2.0}}, "hot")
        for path in set(reads):
            self.assertEqual(reads.count(path), 1, f"{path} was parsed twice")
        self.assertNotIn(self.ledger, reads)

    def test_last_ts_heartbeat_is_throttled_then_refreshed(self):
        L.ledger_update({}, "beat")
        acct = L._acct_file(self.ledger, "beat")
        stamped = self._read(acct)["rec"]["last_ts"]
        L.ledger_update({}, "beat")
        self.assertEqual(self._read(acct)["rec"]["last_ts"], stamped)
        payload = self._read(acct)
        payload["rec"]["last_ts"] = time.time() - L.LEDGER_HEARTBEAT - 5
        self.assertTrue(L._atomic_json(acct, payload))
        L.ledger_update({}, "beat")
        self.assertGreater(self._read(acct)["rec"]["last_ts"], time.time() - L.LEDGER_HEARTBEAT)

    def test_heartbeat_throttle_stays_far_inside_the_ttl(self):
        self.assertLess(L.LEDGER_HEARTBEAT, L.SESSION_TTL / 10)

    def test_quiet_render_still_prunes_expired_peer(self):
        tx = self._write_tx([self._assistant("r1")])
        data = {"transcript_path": tx}
        L.ledger_update(data, "live")
        self._seed_peer("ghost", 1, 1)
        ghost = L._acct_file(self.ledger, "ghost")
        payload = self._read(ghost)
        payload["rec"]["last_ts"] = time.time() - L.SESSION_TTL - 1
        self.assertTrue(L._atomic_json(ghost, payload))
        L.ledger_update(data, "live")
        self.assertFalse(os.path.exists(ghost))
        self.assertTrue(os.path.exists(L._acct_file(self.ledger, "live")))

    def test_host_change_alone_is_persisted(self):
        L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "cost")
        L.ledger_update({"cost": {"total_cost_usd": 3.5}}, "cost")
        host = self._read(L._acct_file(self.ledger, "cost"))["rec"]["host"]
        self.assertEqual((host["latest"], host["max"]), (3.5, 3.5))

    def test_daily_totals_exact_across_session_counts(self):
        for count in (1, 10, 100):
            with self.subTest(sessions=count):
                directory = L._session_dir(self.ledger)
                shutil.rmtree(directory, ignore_errors=True)
                for index in range(count):
                    self._seed_peer(f"peer-{index}", 7, 250)
                _rec, _sess, day = L.ledger_update({}, "current")
                self.assertEqual(day["in"], 7.0 * count)
                self.assertEqual(day["pd"], 250 * count)

    def test_expired_peers_still_pruned_with_many_live_peers(self):
        for index in range(10):
            self._seed_peer(f"peer-{index}", 1, 0)
        self._seed_peer("gone", 1, 0)
        gone = L._acct_file(self.ledger, "gone")
        payload = self._read(gone)
        payload["rec"]["last_ts"] = time.time() - L.SESSION_TTL - 1
        self.assertTrue(L._atomic_json(gone, payload))
        L.ledger_update({}, "current")
        self.assertFalse(os.path.exists(gone))
        for index in range(10):
            self.assertTrue(os.path.exists(L._acct_file(self.ledger, f"peer-{index}")))

    def test_concurrent_sessions_keep_their_own_totals(self):
        first = self._write_tx([self._assistant("a1", inp=100, out=10)], "a.jsonl")
        second = self._write_tx([self._assistant("b1", inp=300, out=20)], "b.jsonl")
        _r, sess_a, _d = L.ledger_update({"transcript_path": first}, "sid-a")
        _r, sess_b, day = L.ledger_update({"transcript_path": second}, "sid-b")
        self.assertEqual(sess_a["in"], 100.0)
        self.assertEqual(sess_b["in"], 300.0)
        self.assertEqual(day["in"], 400.0)
        _r, _s, day = L.ledger_update({"transcript_path": first}, "sid-a")
        self.assertEqual(day["in"], 400.0)


# =========================================================================== clone hoists
class TestParseIsoHasOneOwner(unittest.TestCase):
    """#334 item 3 — _fmtlib.parse_iso and _ledgerlib.parse_iso were byte-identical
    bodies; _fmtlib is the documented owner and _ledgerlib must re-export it."""

    def test_ledgerlib_reexports_the_fmtlib_implementation(self):
        import _fmtlib
        self.assertIs(L.parse_iso, _fmtlib.parse_iso)

    def test_ledgerlib_defines_no_second_parse_iso_body(self):
        source = inspect.getsource(L)
        self.assertNotIn("def parse_iso(", source)


# =========================================================================== import-purity
class TestNoImportSideEffects(unittest.TestCase):
    """The lib must do zero file/network I/O at import time (the _*lib invariant)."""

    def test_reimport_is_clean(self):
        import importlib
        mod = importlib.reload(L)
        self.assertTrue(hasattr(mod, "ledger_update"))
        self.assertTrue(hasattr(mod, "burn_samples"))


if __name__ == "__main__":
    unittest.main()
