"""Tests for _ledgerlib — the cost/token ledger subsystem extracted from
statusline.py (T-12). Stdlib unittest only; no subprocess, no real ~/.codearbiter.

Covers the three concerns the extraction exists to make independently testable:
pricing (price_for / api_cost), transcript accumulation (_tx_accumulate / _agg_reqs
/ _totals / ledger_update dedup + day attribution), and JSON persistence
(ledger_update write + TTL prune, persist_sess_start fast-path cache).
"""
import json
import glob
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


# =========================================================================== pricing
class TestPricing(unittest.TestCase):

    def test_price_for_known_families(self):
        self.assertEqual(L.price_for("claude-opus-4-8"), L.API_PRICES["opus"])
        self.assertEqual(L.price_for("claude-sonnet-4-6"), L.API_PRICES["sonnet"])
        self.assertEqual(L.price_for("claude-haiku-x"), L.API_PRICES["haiku"])
        self.assertEqual(L.price_for("fable-1"), L.API_PRICES["fable"])

    def test_price_for_unknown_defaults_to_sonnet(self):
        self.assertEqual(L.price_for("some-unknown-model"), L.API_PRICES["sonnet"])

    def test_price_for_non_string_coerced(self):
        # str(model) coercion: a None model must not crash, falls to default.
        self.assertEqual(L.price_for(None), L.API_PRICES["sonnet"])

    def test_api_cost_input_output(self):
        # opus: input 5.0, output 25.0 per 1M.
        tok = {"opus": {"in": 1_000_000, "out": 1_000_000,
                        "c5": 0, "c1": 0, "cr": 0}}
        # 1M * 5.0/1e6 + 1M * 25.0/1e6 = 5 + 25 = 30
        self.assertAlmostEqual(L.api_cost(tok), 30.0)

    def test_api_cost_includes_cache_reads(self):
        # cache reads (cr) are priced even though they're excluded from token counts.
        tok = {"sonnet": {"in": 0, "out": 0, "c5": 0, "c1": 0, "cr": 1_000_000}}
        # sonnet cache_read = 0.30 per 1M
        self.assertAlmostEqual(L.api_cost(tok), 0.30)

    def test_api_cost_empty_is_zero(self):
        self.assertEqual(L.api_cost({}), 0.0)
        self.assertEqual(L.api_cost(None), 0.0)

    def test_api_cost_skips_non_dict_values(self):
        self.assertEqual(L.api_cost({"opus": "not-a-dict"}), 0.0)


# =========================================================================== accumulation
class TestAccumulation(unittest.TestCase):

    def _line(self, req, model="claude-sonnet", inp=100, out=50,
              ts="2026-01-01T00:00:00Z"):
        return {"type": "assistant", "requestId": req, "timestamp": ts,
                "message": {"id": f"m_{req}", "model": model,
                            "usage": {"input_tokens": inp, "output_tokens": out}}}

    def _write(self, entries, td):
        path = os.path.join(td, "tx.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for o in entries:
                f.write(json.dumps(o) + "\n")
        return path

    def test_basic_two_requests(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write([self._line("r1"), self._line("r2")], td)
            rec = {}
            self.assertTrue(L._tx_accumulate(rec, path))
            self.assertEqual(len(rec["reqs"]), 2)

    def test_dedup_by_request_id_upsert(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write(
                [self._line("dup", inp=100, out=50),
                 self._line("dup", inp=150, out=70)], td)
            rec = {}
            L._tx_accumulate(rec, path)
            self.assertEqual(len(rec["reqs"]), 1)
            self.assertEqual(rec["reqs"]["dup"]["in"], 150.0)
            self.assertEqual(rec["reqs"]["dup"]["out"], 70.0)

    def test_nonexistent_file_returns_false(self):
        self.assertFalse(L._tx_accumulate({}, os.path.join(tempfile.gettempdir(),
                                                            "nope_ledger_xyz.jsonl")))

    def test_incremental_offset(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write([self._line("r1")], td)
            rec = {}
            L._tx_accumulate(rec, path)
            off1 = rec["tx_off"]
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._line("r2")) + "\n")
            L._tx_accumulate(rec, path)
            self.assertEqual(len(rec["reqs"]), 2)
            self.assertGreater(rec["tx_off"], off1)

    def test_agg_reqs_groups_by_model(self):
        reqs = {
            "a": {"d": "2026-01-01", "m": "opus", "in": 10, "out": 5,
                  "c5": 0, "c1": 0, "cr": 0},
            "b": {"d": "2026-01-01", "m": "opus", "in": 20, "out": 8,
                  "c5": 0, "c1": 0, "cr": 0},
            "c": {"d": "2026-01-02", "m": "sonnet", "in": 30, "out": 9,
                  "c5": 0, "c1": 0, "cr": 0},
        }
        agg = L._agg_reqs(reqs)
        self.assertEqual(agg["opus"]["in"], 30.0)
        self.assertEqual(agg["opus"]["out"], 13.0)
        self.assertEqual(agg["sonnet"]["in"], 30.0)

    def test_agg_reqs_only_filters_by_day(self):
        reqs = {
            "a": {"d": "2026-01-01", "m": "opus", "in": 10, "out": 5,
                  "c5": 0, "c1": 0, "cr": 0},
            "c": {"d": "2026-01-02", "m": "opus", "in": 30, "out": 9,
                  "c5": 0, "c1": 0, "cr": 0},
        }
        agg = L._agg_reqs(reqs, only="2026-01-02")
        self.assertEqual(agg["opus"]["in"], 30.0)
        self.assertEqual(agg["opus"]["out"], 9.0)

    def test_totals_excludes_cache_reads_from_count(self):
        # cr (cache reads) must NOT inflate the displayed "in"; c5/c1 (writes) do.
        models = {"opus": {"in": 100, "c5": 20, "c1": 10, "cr": 9999, "out": 40}}
        t = L._totals(models)
        self.assertEqual(t["in"], 130.0)   # 100 + 20 + 10, cr excluded
        self.assertEqual(t["out"], 40.0)

    def test_burn_samples_window(self):
        rec = {"burn": list(range(50))}
        s = L.burn_samples(rec)
        self.assertEqual(len(s), 24)          # last-24 window
        self.assertEqual(s[-1], 49.0)

    def test_burn_samples_too_few(self):
        self.assertEqual(L.burn_samples({"burn": [5]}), [])
        self.assertEqual(L.burn_samples({}), [])


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

    def _write_tx(self, entries):
        tx = os.path.join(self.tmp, "transcript.jsonl")
        with open(tx, "w", encoding="utf-8") as f:
            for o in entries:
                f.write(json.dumps(o) + "\n")
        return tx

    def _assistant(self, req, inp=200, out=100):
        return {"type": "assistant", "requestId": req,
                "timestamp": "2026-01-01T12:00:00Z",
                "message": {"model": "claude-sonnet-4-6",
                            "usage": {"input_tokens": inp, "output_tokens": out}}}

    def _serialize_transactions(self, first, second, while_first_holds=None):
        """Prove the second writer cannot acquire until the first releases."""
        real_acquire = L._acquire_lock
        first_acquired = threading.Event()
        second_attempted = threading.Event()
        second_acquired = threading.Event()
        release_first = threading.Event()
        outputs = {}

        def coordinated_acquire(path):
            if threading.current_thread().name == "ledger-second":
                second_attempted.set()
            token = real_acquire(path)
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
        # NB: acquire_lock's retry deadline (core/pysrc/_hooklib.py) reads its
        # OWN module global `LOCK_WAIT` at call time, not `_ledgerlib.LOCK_WAIT`
        # (a same-named but distinct binding imported for back-compat re-export
        # only — see _ledgerlib.py's header comment). Patching `L.LOCK_WAIT`
        # alone is inert; patch `_hooklib.LOCK_WAIT`, the name the real retry
        # loop actually consults, so this harness's headroom is real.
        with mock.patch.object(_hooklib, "LOCK_WAIT", CONCURRENCY_TEST_WAIT), \
                mock.patch.object(L, "_acquire_lock", side_effect=coordinated_acquire):
            one.start()
            self.assertTrue(first_acquired.wait(CONCURRENCY_TEST_WAIT))
            if while_first_holds:
                while_first_holds()
            two.start()
            self.assertTrue(second_attempted.wait(CONCURRENCY_TEST_WAIT))
            # Time-bounded negative wait (E-4): waiting for second_attempted
            # only proves the second thread got scheduled and reached the
            # lock call — it says nothing about whether the lock actually
            # excluded it. Give the second thread a real window to sneak an
            # acquisition through before the first releases; if serialization
            # were broken, this wait would very likely observe it fire.
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

    def test_ledger_update_no_sid_blanks(self):
        _rec, sess, day = L.ledger_update({}, None)
        self.assertEqual(sess["in"], 0.0)
        self.assertEqual(day["in"], 0.0)

    def test_ledger_update_writes_file(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-write")
        self.assertTrue(os.path.isfile(self.ledger))
        with open(self.ledger, encoding="utf-8") as f:
            led = json.load(f)
        self.assertIn("sid-write", led["sessions"])

    def test_ledger_update_dedup(self):
        tx = self._write_tx([self._assistant("r1", inp=100, out=50),
                             self._assistant("r1", inp=100, out=50)])
        _rec, sess, _day = L.ledger_update({"transcript_path": tx}, "sid-dup")
        self.assertEqual(sess["in"], 100.0)
        self.assertEqual(sess["out"], 50.0)

    def test_ledger_update_ttl_prunes_stale_session(self):
        # Seed a ledger with a session older than the TTL; it must be pruned.
        os.makedirs(os.path.dirname(self.ledger), exist_ok=True)
        stale_ts = time.time() - (L.SESSION_TTL + 100)
        with open(self.ledger, "w", encoding="utf-8") as f:
            json.dump({"sessions": {"old": {"last_ts": stale_ts}}}, f)
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-fresh")
        with open(self.ledger, encoding="utf-8") as f:
            led = json.load(f)
        self.assertNotIn("old", led["sessions"])
        self.assertIn("sid-fresh", led["sessions"])

    def test_host_cost_overrides_estimate(self):
        tx = self._write_tx([self._assistant("r1")])
        data = {"transcript_path": tx, "cost": {"total_cost_usd": 4.20}}
        _rec, sess, _day = L.ledger_update(data, "sid-cost")
        self.assertEqual(sess["cost"], 4.20)

    def test_persist_sess_start_seeds_cache(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-ss")
        self.assertTrue(L.persist_sess_start("sid-ss", 1700000000.0))
        with open(self.ledger, encoding="utf-8") as f:
            led = json.load(f)
        self.assertEqual(led["sessions"]["sid-ss"]["sess_start"], 1700000000.0)

    def test_persist_sess_start_idempotent(self):
        tx = self._write_tx([self._assistant("r1")])
        L.ledger_update({"transcript_path": tx}, "sid-ss2")
        self.assertTrue(L.persist_sess_start("sid-ss2", 123.0))
        # Second call with the same value is a no-op (returns False).
        self.assertFalse(L.persist_sess_start("sid-ss2", 123.0))

    def test_persist_sess_start_unknown_session(self):
        # No ledger yet / unknown sid -> no write, no crash.
        self.assertFalse(L.persist_sess_start("nope", 5.0))

    def test_persist_sess_start_blank_args(self):
        self.assertFalse(L.persist_sess_start(None, 5.0))
        self.assertFalse(L.persist_sess_start("sid", 0))

    def test_concurrent_distinct_session_updates_both_survive(self):
        outputs = self._serialize_transactions(
            lambda: L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "sid-a"),
            lambda: L.ledger_update({"cost": {"total_cost_usd": 2.0}}, "sid-b"))
        with open(self.ledger, encoding="utf-8") as f:
            sessions = json.load(f)["sessions"]
        self.assertEqual(set(sessions), {"sid-a", "sid-b"})
        self.assertEqual(sessions["sid-a"]["host_cost"], 1.0)
        self.assertEqual(sessions["sid-b"]["host_cost"], 2.0)
        self.assertEqual(outputs["second"][2]["cost"], 3.0)

    def test_persist_sess_start_cannot_discard_concurrent_cost_update(self):
        """The session-start cache write must not replace fresher accounting."""
        L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "sid-race")
        outputs = self._serialize_transactions(
            lambda: L.persist_sess_start("sid-race", 123.0),
            lambda: L.ledger_update({"cost": {"total_cost_usd": 9.0}}, "sid-race"))
        self.assertTrue(outputs["first"])
        with open(self.ledger, encoding="utf-8") as f:
            rec = json.load(f)["sessions"]["sid-race"]
        self.assertEqual(rec["sess_start"], 123.0)
        self.assertEqual(rec["host_cost"], 9.0)

    def test_same_session_concurrent_updates_do_not_regress_accounting(self):
        tx = self._write_tx([self._assistant("r1", inp=100, out=50)])
        L.ledger_update({"transcript_path": tx,
                         "cost": {"total_cost_usd": 1.0}}, "sid-same")
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
        with open(self.ledger, encoding="utf-8") as f:
            rec = json.load(f)["sessions"]["sid-same"]
        self.assertEqual(rec["host_cost"], 3.0)
        self.assertEqual(set(rec["reqs"]), {"r1", "r2", "r3"})
        self.assertEqual(rec["tx_off"], os.path.getsize(tx))
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

    def test_expired_session_and_start_shards_are_deleted(self):
        stale = {"last_ts": time.time() - L.SESSION_TTL - 1}
        self.assertTrue(L._atomic_json(L._session_file(self.ledger, "expired"),
                                       {"sid": "expired", "rec": stale}))
        self.assertTrue(L._atomic_json(L._start_file(self.ledger, "expired"),
                                       {"sid": "expired", "sess_start": 123.0}))
        L.ledger_update({}, "fresh")
        self.assertFalse(os.path.exists(L._session_file(self.ledger, "expired")))
        self.assertFalse(os.path.exists(L._start_file(self.ledger, "expired")))

    def test_bare_filename_ledger_path_works(self):
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmp)
            os.environ["CODEARBITER_LEDGER"] = "ledger.json"
            L.ledger_update({"cost": {"total_cost_usd": 1.0}}, "bare")
            with open("ledger.json", encoding="utf-8") as f:
                self.assertIn("bare", json.load(f)["sessions"])
        finally:
            os.chdir(old_cwd)

    def test_lock_contention_times_out_fail_soft_within_latency_bound(self):
        owner = L._acquire_lock(self.ledger)
        self.assertIsNotNone(owner)
        try:
            started = time.monotonic()
            rec, sess, day = L.ledger_update({}, "contended")
            elapsed = time.monotonic() - started
            self.assertEqual((rec, sess, day), ({}, {"in": 0.0, "out": 0.0,
                                                     "cost": 0.0},
                                                    {"in": 0.0, "out": 0.0,
                                                     "cost": 0.0}))
            self.assertFalse(L.persist_sess_start("contended", 123.0))
            self.assertLessEqual(elapsed, 0.35)
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
            started = time.monotonic()
            self.assertIsNone(L._acquire_lock(self.ledger))
            self.assertLessEqual(time.monotonic() - started, 0.35)
        finally:
            L._release_lock(owner)

    def test_malformed_session_and_start_shards_are_deleted(self):
        directory = L._session_dir(self.ledger)
        os.makedirs(directory, exist_ok=True)
        bad_session = os.path.join(directory, "bad.json")
        bad_start = os.path.join(directory, "bad.start.json")
        with open(bad_session, "w", encoding="utf-8") as f:
            f.write("not json")
        with open(bad_start, "w", encoding="utf-8") as f:
            f.write("[]")
        L.ledger_update({}, "fresh")
        self.assertFalse(os.path.exists(bad_session))
        self.assertFalse(os.path.exists(bad_start))

    def test_nonnumeric_live_session_start_metadata_is_deleted(self):
        L.ledger_update({}, "live")
        start = L._start_file(self.ledger, "live")
        self.assertTrue(L._atomic_json(start,
                                       {"sid": "live", "sess_start": "invalid"}))
        L.ledger_update({}, "other")
        self.assertFalse(os.path.exists(start))

    def test_misnamed_stale_shard_cannot_delete_embedded_sid_files(self):
        L.ledger_update({}, "victim")
        self.assertTrue(L.persist_sess_start("victim", 123.0))
        victim_shard = L._session_file(self.ledger, "victim")
        victim_start = L._start_file(self.ledger, "victim")
        misnamed = os.path.join(L._session_dir(self.ledger), "misnamed.json")
        stale = {"last_ts": time.time() - L.SESSION_TTL - 1}
        self.assertTrue(L._atomic_json(misnamed,
                                       {"sid": "victim", "rec": stale}))
        L.ledger_update({}, "other")
        self.assertFalse(os.path.exists(misnamed))
        self.assertTrue(os.path.exists(victim_shard))
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


# =========================================================================== import-purity
class TestNoImportSideEffects(unittest.TestCase):
    """The lib must do zero file/network I/O at import time (the _*lib invariant)."""

    def test_reimport_is_clean(self):
        import importlib
        mod = importlib.reload(L)
        self.assertTrue(hasattr(mod, "ledger_update"))
        self.assertTrue(hasattr(mod, "price_for"))


if __name__ == "__main__":
    unittest.main()
