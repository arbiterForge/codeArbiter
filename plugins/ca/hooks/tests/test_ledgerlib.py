"""Tests for _ledgerlib — the cost/token ledger subsystem extracted from
statusline.py (T-12). Stdlib unittest only; no subprocess, no real ~/.codearbiter.

Covers the three concerns the extraction exists to make independently testable:
pricing (price_for / api_cost), transcript accumulation (_tx_accumulate / _agg_reqs
/ _totals / ledger_update dedup + day attribution), and JSON persistence
(ledger_update write + TTL prune, persist_sess_start fast-path cache).
"""
import json
import glob
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

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
        with mock.patch.object(L, "LOCK_WAIT", CONCURRENCY_TEST_WAIT), \
                mock.patch.object(L, "_acquire_lock", side_effect=coordinated_acquire):
            one.start()
            self.assertTrue(first_acquired.wait(CONCURRENCY_TEST_WAIT))
            if while_first_holds:
                while_first_holds()
            two.start()
            self.assertTrue(second_attempted.wait(CONCURRENCY_TEST_WAIT))
            self.assertFalse(second_acquired.is_set())
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
