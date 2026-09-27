"""Tests for the v2 Claude accounting engine in _ledgerlib (spec
claude-statusline-accounting-integrity, CP-2/CP-3).

Every principal expected total is computed from fixture facts and literal
published $/MTok prices. None is derived by calling the production aggregation
under test. Local-day attribution uses the deterministic seams `_local_day`
(UTC date of the timestamp) and `_today`, so midnight tests do not depend on the
machine's timezone.
"""
import builtins
import itertools
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from fractions import Fraction
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _hooklib  # noqa: E402
import _ledgerlib as L  # noqa: E402
from _helpers import redirect_home, restore_home  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "statusline_accounting")
TODAY = "2026-09-27"
YESTERDAY = "2026-09-26"
SONNET5 = {"in": "2", "out": "10", "w5": "2.50", "w1": "4", "cr": "0.20"}
OPUS55 = {"in": "4", "out": "20", "w5": "5", "w1": "8", "cr": "0.20"}
HAIKU45 = {"in": "1", "out": "5", "w5": "1.25", "w1": "2", "cr": "0.10"}


def usd(rates, inp=0, out=0, w5=0, w1=0, cr=0):
    """Independent USD for one request from literal $/MTok rates."""
    return (inp * Fraction(rates["in"]) + out * Fraction(rates["out"])
            + w5 * Fraction(rates["w5"]) + w1 * Fraction(rates["w1"])
            + cr * Fraction(rates["cr"])) / 10**6


def A(rid, model="claude-sonnet-5", inp=100, out=50, ts=f"{TODAY}T10:00:00Z",
      w5=0, w1=0, cr=0, mid=True, sidechain=False, **extra):
    usage = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr,
             "cache_creation_input_tokens": w5 + w1,
             "cache_creation": {"ephemeral_5m_input_tokens": w5,
                                "ephemeral_1h_input_tokens": w1}}
    usage.update(extra)
    r = {"type": "assistant", "timestamp": ts, "isSidechain": sidechain,
         "message": {"role": "assistant", "model": model, "usage": usage,
                     "content": [{"type": "text", "text": "x"}]}}
    if rid is not None:
        r["requestId"] = rid
    if mid:
        r["message"]["id"] = f"msg_{rid}"
    return r


def UREC(text="Do the thing", ts=f"{TODAY}T09:59:00Z"):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def dollars(result):
    return Fraction(result["pd"], 10**12)


class AccountingCase(unittest.TestCase):
    """Scratch HOME + ledger + transcript tree, deterministic day seams."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ca-acct-")
        self._home = redirect_home(self.tmp)
        self._orig = os.environ.get("CODEARBITER_LEDGER")
        self.ledger = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        os.environ["CODEARBITER_LEDGER"] = self.ledger
        self.proj = os.path.join(self.tmp, "projects", "slug")
        os.makedirs(self.proj)
        self.sid = "sess-under-test"
        self.parent = os.path.join(self.proj, f"{self.sid}.jsonl")
        self.subdir = os.path.join(self.proj, self.sid, "subagents")
        self._patches = [mock.patch.object(L, "_local_day", lambda ts: ts[:10]),
                         mock.patch.object(L, "_today", lambda: TODAY)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        restore_home(self._home)
        if self._orig is None:
            os.environ.pop("CODEARBITER_LEDGER", None)
        else:
            os.environ["CODEARBITER_LEDGER"] = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ helpers
    def write(self, path, records, mode="w", raw=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode + "b") as f:
            for r in records:
                f.write((json.dumps(r) + "\n").encode("utf-8"))
            if raw is not None:
                f.write(raw)
        return path

    def child(self, name, records, mode="w", mtime=None):
        p = self.write(os.path.join(self.subdir, name), records, mode)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def data(self, cost=None, tx=None):
        d = {"session_id": self.sid, "transcript_path": tx or self.parent}
        if cost is not None:
            d["cost"] = {"total_cost_usd": cost}
        return d

    def update(self, cost=None, sid=None):
        return L.ledger_update(self.data(cost), sid or self.sid)

    def settle(self, limit=500, cost=None):
        """Render until coverage stops catching up; return the last result."""
        for _ in range(limit):
            rec, sess, day = self.update(cost)
            if sess["state"] != "catching_up":
                return rec, sess, day
        self.fail("accounting never converged")

    def copy_fixture_tree(self):
        """Materialize the fork-replay fixture as this session's parent + children."""
        shutil.copyfile(os.path.join(FIXTURES, "fork_replay", "parent.jsonl"), self.parent)
        src = os.path.join(FIXTURES, "fork_replay", "parent", "subagents")
        os.makedirs(self.subdir, exist_ok=True)
        for n in os.listdir(src):
            shutil.copyfile(os.path.join(src, n), os.path.join(self.subdir, n))


# =========================================================================== T-10 bounded streaming
class TestBoundedStreaming(AccountingCase):

    def _n_requests(self, n, prefix="r"):
        return [A(f"{prefix}{i}", inp=10, out=1) for i in range(n)]

    def test_budget_boundaries_defer_never_skip(self):
        for n in (4, 5, 6, 11):             # budget-1, exact, +1, multiple chunks
            with self.subTest(records=n):
                self.write(self.parent, self._n_requests(n))
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                with mock.patch.object(L, "ACCT_RECORD_BUDGET", 5):
                    rec, sess, _ = self.update()
                    consumed = min(n, 5)
                    with open(self.parent, "rb") as f:
                        lines = f.readlines()
                    self.assertEqual(rec["src"]["p"]["off"], sum(len(x) for x in lines[:consumed]))
                    self.assertEqual(sess["state"], "catching_up" if n > 5 else "complete")
                    _, sess, _ = self.settle()
                self.assertEqual(sess["in"], 10 * n)
                self.assertEqual(sess["out"], 1 * n)
                self.assertEqual(sess["state"], "complete")

    def test_byte_budget_bounds_reads(self):
        self.write(self.parent, self._n_requests(200))
        size = os.path.getsize(self.parent)
        reads = []
        real_open = builtins.open

        class Spy:
            def __init__(self, f):
                self.f = f

            def readline(self, *a):
                d = self.f.readline(*a)
                reads.append(len(d))
                return d

            def read(self, *a):
                d = self.f.read(*a)
                reads.append(len(d))
                return d

            def __iter__(self):
                for ln in self.f:
                    reads.append(len(ln))
                    yield ln

            def __enter__(self):
                self.f.__enter__()
                return self

            def __exit__(self, *a):
                return self.f.__exit__(*a)

            def __getattr__(self, k):
                return getattr(self.f, k)

        def spy_open(p, *a, **k):
            f = real_open(p, *a, **k)
            return Spy(f) if os.path.abspath(str(p)) == os.path.abspath(self.parent) else f

        budget = size // 4
        with mock.patch.object(L, "ACCT_BYTE_BUDGET", budget), \
                mock.patch.object(builtins, "open", spy_open):
            self.update()
        self.assertLessEqual(sum(reads), budget + 2 * L.FP_WINDOW + L.MAX_RECORD_BYTES)
        self.assertLess(sum(reads), size)
        with mock.patch.object(L, "ACCT_BYTE_BUDGET", budget):
            _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (2000, 200))   # deferred, never skipped

    def test_partial_trailing_line_waits_then_counts_once(self):
        whole = (json.dumps(A("tail", inp=7, out=3)) + "\n").encode()
        self.write(self.parent, [A("r0", inp=1, out=1)], raw=whole[:25])
        rec, sess, _ = self.update()
        self.assertEqual(sess["in"], 1)
        with open(self.parent, "ab") as f:
            f.write(whole[25:])
        _, sess, _ = self.update()
        self.assertEqual((sess["in"], sess["out"]), (8, 4))
        _, sess, _ = self.update()
        self.assertEqual((sess["in"], sess["out"]), (8, 4))

    def test_oversized_usage_line_is_passed_and_marked(self):
        big = A("big", inp=999, out=999)
        big["message"]["content"] = [{"type": "text", "text": "z" * 6000}]
        self.write(self.parent, [A("a", inp=1, out=1), big, A("b", inp=2, out=2)])
        with mock.patch.object(L, "MAX_RECORD_BYTES", 2048):
            _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 3))
        self.assertIn("oversized_record", sess["reasons"])
        self.assertEqual(sess["state"], "partial")

    def test_oversized_line_larger_than_render_budget_progresses(self):
        big = A("big", inp=999, out=999)
        big["message"]["content"] = [{"type": "text", "text": "z" * 50000}]
        self.write(self.parent, [A("a", inp=1, out=1), big, A("b", inp=2, out=2)])
        with mock.patch.object(L, "MAX_RECORD_BYTES", 2048), \
                mock.patch.object(L, "ACCT_BYTE_BUDGET", 8192):
            renders = 0
            while True:
                renders += 1
                _, sess, _ = self.update()
                if sess["state"] != "catching_up":
                    break
                self.assertLess(renders, 50)
        self.assertGreater(renders, 2)
        self.assertEqual((sess["in"], sess["out"]), (3, 3))
        self.assertIn("oversized_record", sess["reasons"])

    def test_oversized_non_usage_line_leaves_coverage_complete(self):
        user = UREC("q" * 9000)
        self.write(self.parent, [A("a", inp=1, out=1), user, A("b", inp=2, out=2)])
        with mock.patch.object(L, "MAX_RECORD_BYTES", 2048):
            _, sess, _ = self.settle()
        self.assertEqual(sess["state"], "complete")
        self.assertEqual(sess["in"], 3)


# =========================================================================== T-12 malformed coverage
class TestMalformedCoverage(AccountingCase):

    def test_usage_bearing_malformed_cases_are_partial(self):
        bad_lines = [
            b'{"type":"assistant","message":{"usage":{"input_tokens": 5}\n',  # undecodable
            b'["type":"assistant","usage":{}]\n',                                 # undecodable
        ]
        for i, bad in enumerate(bad_lines):
            with self.subTest(case=i):
                self.write(self.parent, [A("a", inp=1, out=1)], raw=bad)
                with open(self.parent, "ab") as f:
                    f.write((json.dumps(A("b", inp=2, out=2)) + "\n").encode())
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                _, sess, _ = self.settle()
                self.assertEqual(sess["in"], 3)
                self.assertIn("malformed_record", sess["reasons"])

    def test_malformed_counters_are_partial(self):
        for bad in (-1, True, 1.5, float("inf"), "12", 10**16):
            with self.subTest(bad=bad):
                r = A("x")
                r["message"]["usage"]["input_tokens"] = bad
                line = json.dumps(r).replace("Infinity", "1e999").encode() + b"\n"
                self.write(self.parent, [A("a", inp=1, out=1)], raw=line)
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                _, sess, _ = self.settle()
                self.assertEqual(sess["in"], 1)
                self.assertIn("malformed_record", sess["reasons"])

    def test_non_object_usage_is_partial(self):
        r = A("x")
        r["message"]["usage"] = "lots"
        self.write(self.parent, [r])
        _, sess, _ = self.settle()
        self.assertIn("malformed_record", sess["reasons"])

    def test_observed_non_usage_types_leave_coverage_complete(self):
        with open(os.path.join(FIXTURES, "nonusage_types.jsonl"), "rb") as f:
            raw = f.read()
        self.write(self.parent, [A("a", inp=1, out=1)], raw=raw + b"not json at all\n[1,2]\n")
        _, sess, _ = self.settle()
        self.assertEqual(sess["state"], "complete")
        self.assertEqual(sess["in"], 1)

    def test_escaped_usage_text_in_content_is_not_malformed(self):
        u = UREC('see {"type":"assistant","usage":{"input_tokens":5}} in the log')
        self.write(self.parent, [u, A("a", inp=1, out=1)])
        _, sess, _ = self.settle()
        self.assertEqual(sess["state"], "complete")

    def test_unproven_identity_is_excluded_and_partial(self):
        self.write(self.parent, [A("a", inp=1, out=1), A(None, inp=500, out=500, mid=False)])
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (1, 1))
        self.assertIn("unproven_identity", sess["reasons"])

    def test_synthetic_zero_records_do_not_affect_coverage(self):
        with open(os.path.join(FIXTURES, "synthetic.jsonl"), "rb") as f:
            raw = f.read()
        self.write(self.parent, [A("a", inp=1, out=1)], raw=raw)
        _, sess, _ = self.settle()
        self.assertEqual(sess["state"], "complete")


# =========================================================================== T-14 migration
class TestMigration(AccountingCase):

    def _legacy(self, sid, **rec):
        base = {"first_ts": time.time() - 100, "last_ts": time.time(), "last_day": TODAY,
                "host_cost": 7.5, "reqs": {"r_old": {"d": TODAY, "m": "claude-sonnet-5",
                                                     "in": 9999, "out": 9999, "cr": 0,
                                                     "c5": 0, "c1": 0}},
                "tx_off": 10**9, "tx_path": self.parent, "burn": [1, 2],
                "today": {"in": 9999.0, "out": 9999.0, "cost": 7.5, "date": TODAY}}
        base.update(rec)
        path = L._session_file(self.ledger, sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sid": sid, "rec": base}, f)
        return path

    def test_legacy_shard_migrates_without_deletion(self):
        self._legacy(self.sid, first_ts=1790000000.0)
        with open(L._start_file(self.ledger, self.sid), "w", encoding="utf-8") as f:
            json.dump({"sid": self.sid, "sess_start": 1790000001.0}, f)
        self.write(self.parent, [A("r1", inp=100, out=50)])
        rec, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (100, 50))       # replayed, not 9999
        self.assertEqual(dollars(sess), usd(SONNET5, inp=100, out=50))  # never host_cost
        self.assertEqual(rec["first_ts"], 1790000000.0)
        self.assertEqual(rec["sess_start"], 1790000001.0)
        self.assertEqual(sess["host"], 7.5)                           # host seed only

    def test_corrupt_legacy_and_sibling_shards_fail_soft(self):
        d = L._session_dir(self.ledger)
        os.makedirs(d, exist_ok=True)
        with open(L._session_file(self.ledger, self.sid), "w", encoding="utf-8") as f:
            f.write("{not json")
        with open(os.path.join(d, "f" * 64 + ".json"), "w", encoding="utf-8") as f:
            f.write("[]")
        with open(os.path.join(d, "e" * 64 + ".acct.json"), "w", encoding="utf-8") as f:
            f.write("garbage")
        self.write(self.parent, [A("r1", inp=3, out=2)])
        _, sess, day = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 2))
        self.assertEqual((day["in"], day["out"]), (3, 2))

    def test_corrupt_own_summary_rebuilds_from_replay(self):
        self.write(self.parent, [A("r1", inp=3, out=2)])
        self.settle()
        with open(L._acct_file(self.ledger, self.sid), "w", encoding="utf-8") as f:
            f.write("{")
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 2))

    def test_legacy_snapshot_is_never_read_on_the_render_path(self):
        os.makedirs(os.path.dirname(self.ledger), exist_ok=True)
        with open(self.ledger, "w", encoding="utf-8") as f:
            json.dump({"sessions": {"x": {"last_ts": time.time()}}}, f)
        self.write(self.parent, [A("r1")])
        seen = []
        real = builtins.open

        def spy(p, *a, **k):
            seen.append(os.path.abspath(str(p)))
            return real(p, *a, **k)
        with mock.patch.object(builtins, "open", spy):
            self.update()
        self.assertNotIn(os.path.abspath(self.ledger), seen)

    def test_unmigrated_session_active_today_makes_today_partial(self):
        self._legacy("other-live-session")
        self.write(self.parent, [A("r1")])
        _, sess, day = self.settle()
        self.assertEqual(sess["state"], "complete")
        self.assertIn("unmigrated_session", day["reasons"])


# =========================================================================== T-16 multi-source
class TestMultiSource(AccountingCase):

    def test_child_counts_scale_and_old_children_count(self):
        old = time.time() - 10 * 3600
        for n in (0, 1, 12, 13, 64):
            with self.subTest(children=n):
                shutil.rmtree(os.path.join(self.proj, self.sid), ignore_errors=True)
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                self.write(self.parent, [A("p1", inp=1000, out=100)])
                for c in range(n):
                    self.child(f"agent-c{c:03d}.jsonl",
                               [UREC(f"child {c}"), A(f"c{c}", inp=10, out=1, sidechain=True)],
                               mtime=old if c % 2 else None)
                with open(os.path.join(self.subdir if n else self.proj, "agent-x.meta.json"),
                          "w", encoding="utf-8") as f:
                    f.write('{"agentType":"x"}')
                _, sess, _ = self.settle()
                self.assertEqual(sess["in"], 1000 + 10 * n)
                self.assertEqual(sess["out"], 100 + n)
                self.assertEqual(sess["state"], "complete")

    def test_fork_replay_counted_once_with_owner_rule(self):
        self.copy_fixture_tree()
        rec, sess, _ = self.settle()
        parent = read_jsonl(self.parent)
        kids = {n: read_jsonl(os.path.join(self.subdir, n))
                for n in os.listdir(self.subdir)}
        # Independent: max output per requestId across ALL sources, counted once.
        best = {}
        for r in parent + [x for v in kids.values() for x in v]:
            if r.get("type") == "assistant":
                u = r["message"]["usage"]
                best[r["requestId"]] = max(best.get(r["requestId"], 0), u["output_tokens"])
        self.assertEqual(sess["out"], sum(best.values()))
        shared = kids["agent-fxchild1.jsonl"][1]["requestId"]
        own = {n: {r["requestId"] for r in v[2:] if r.get("type") == "assistant"}
               for n, v in kids.items()}
        for n in kids:
            self.assertEqual(rec["src"]["c:" + n]["tok"][1], sum(best[r] for r in own[n]))
        parent_rids = {r["requestId"] for r in parent if r.get("type") == "assistant"}
        self.assertIn(shared, parent_rids)
        self.assertEqual(rec["src"]["p"]["tok"][1], sum(best[r] for r in parent_rids))

    def test_totals_independent_of_source_scan_order(self):
        self.copy_fixture_tree()
        self.child("agent-extra.jsonl", [A("e1", out=5, sidechain=True)])
        results = set()
        for perm in itertools.permutations(range(3)):
            shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)

            def order(ids, perm=perm):
                ids = sorted(ids)
                return [ids[i] for i in perm if i < len(ids)] + ids[len(perm):]
            with mock.patch.object(L, "_order_sources", order), \
                    mock.patch.object(L, "ACCT_SOURCE_BUDGET", 1):
                _, sess, day = self.settle()
            results.add((sess["in"], sess["out"], sess["pd"], tuple(sess["reasons"]),
                         day["in"], day["pd"]))
        self.assertEqual(len(results), 1)

    def test_discovery_bound_is_partial_and_bounded(self):
        self.write(self.parent, [A("p1")])
        for c in range(6):
            self.child(f"agent-{c}.jsonl", [A(f"c{c}", sidechain=True)])
        scans = []
        real = os.scandir

        def spy(p):
            scans.append(p)
            return real(p)
        with mock.patch.object(L, "DISCOVERY_BOUND", 4), mock.patch.object(L.os, "scandir", spy):
            _, sess, _ = self.settle()
        self.assertIn("discovery_bound", sess["reasons"])
        self.assertEqual(sess["state"], "partial")
        self.assertEqual(sess["in"], 100 + 4 * 100)

    def test_new_unscanned_child_prevents_complete(self):
        self.write(self.parent, [A("p1")])
        self.settle()
        self.child("agent-new.jsonl", [A("n1", sidechain=True)])
        with mock.patch.object(L, "ACCT_SOURCE_BUDGET", 0):
            _, sess, _ = self.update()
        self.assertEqual(sess["state"], "catching_up")


class TestAdversarialCombinations(AccountingCase):
    """Spec adversarial-matrix rows not covered by a single-mechanism test."""

    def test_background_child_growth_while_parent_is_unchanged(self):
        self.write(self.parent, [A("p1", inp=1000, out=100)])
        self.child("agent-bg.jsonl", [A("bg0", inp=10, out=1, sidechain=True)])
        rec, base, _ = self.settle()
        parent_tok = list(rec["src"]["p"]["tok"])
        self.child("agent-bg.jsonl", [A(f"bg{i}", inp=10, out=1, sidechain=True)
                                      for i in range(1, 301)], mode="a")
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 25):
            _, first, _ = self.update()
            self.assertEqual(first["state"], "catching_up")
            self.assertLess(first["in"], 1000 + 10 * 301)
            rec, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (1000 + 10 * 301, 100 + 301))
        self.assertEqual(sess["state"], "complete")
        self.assertEqual(list(rec["src"]["p"]["tok"]), parent_tok)

    def test_sibling_fork_replay_counted_once_with_smallest_owner(self):
        self.write(self.parent, [A("p1", inp=1000, out=100)])
        self.child("agent-y.jsonl", [A("shared", inp=20, out=50, sidechain=True),
                                     A("y-own", inp=1, out=2, sidechain=True)])
        self.child("agent-x.jsonl", [A("shared", inp=20, out=5, sidechain=True)])
        rec, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (1000 + 20 + 1, 100 + 50 + 2))
        self.assertEqual(dollars(sess), usd(SONNET5, inp=1021, out=152))
        self.assertEqual(rec["src"]["c:agent-x.jsonl"]["tok"][1], 50)
        self.assertEqual(rec["src"]["c:agent-y.jsonl"]["tok"][1], 2)


# =========================================================================== T-18 starvation
class TestMessageIdOnly(AccountingCase):

    def test_mid_only_and_full_identity_merge_in_either_order(self):
        mid_only = A("m1", inp=10, out=2)
        del mid_only["requestId"]
        full = A("m1", inp=10, out=40)
        for order in ((mid_only, full), (full, mid_only)):
            shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
            self.write(self.parent, [order[0]])
            self.settle()
            self.write(self.parent, [order[1]], mode="a")
            _, sess, _ = self.settle()
            self.assertEqual((sess["in"], sess["out"]), (10, 40))


class TestMessageIdOnlyAfterEviction(AccountingCase):

    def test_mid_only_record_finds_its_request_in_cold_storage(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self.write(self.parent, [A("m1", inp=10, out=2)]
                       + [A(f"f{i}", inp=1, out=1) for i in range(60)])
            self.settle()
            self.assertTrue(L._read_json(L._hot_file(self.ledger, self.sid)) is not None)
            late = A("m1", inp=10, out=40)
            del late["requestId"]
            self.write(self.parent, [late], mode="a")
            _, sess, _ = self.settle()
            self.assertEqual((sess["in"], sess["out"]), (10 + 60, 40 + 60))
            again = A("m1", inp=10, out=40)
            del again["requestId"]
            self.write(self.parent, [again], mode="a")
            _, sess, _ = self.settle()
            self.assertEqual((sess["in"], sess["out"]), (10 + 60, 40 + 60))


class TestColdMembershipFilter(AccountingCase):
    """The per-partition filter may only prove absence. A request evicted to
    cold storage and later replayed by a forked child is still counted once,
    whether the filter is present, malformed, or the partition has split."""

    def _cold_session(self, n=60):
        self.write(self.parent, [A(f"p{i}", inp=1, out=1) for i in range(n)])
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], n)
        hot = L._read_json(L._hot_file(self.ledger, self.sid))
        self.assertTrue(hot["f"], "eviction must leave per-partition filters")
        return hot

    def _cold_keys(self):
        ev = L._ev_dir(self.ledger, self.sid)
        out = {}
        for n in os.listdir(ev):
            with open(os.path.join(ev, n), encoding="utf-8") as f:
                out[n[1:-5]] = set(json.load(f)["ev"])
        return out

    def test_fork_replay_of_evicted_request_counted_once(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self._cold_session()
            cold = set().union(*self._cold_keys().values())
            self.assertIn("rid:p0", cold)
            self.child("agent-fork.jsonl", [A("p0", inp=1, out=1, sidechain=True)])
            _, sess, _ = self.settle()
            self.assertEqual((sess["in"], sess["out"]), (60, 60))

    def test_malformed_filters_fall_back_to_the_partition(self):
        bad_values = ([64, "!!not-base64!!"], [8, "AAAA"], "x", [True, "AA=="], None, [0, ""])
        for bad in bad_values:
            with self.subTest(bad=bad), mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(
                    L, "PART_MAX", 16):
                shutil.rmtree(os.path.join(self.proj, self.sid), ignore_errors=True)
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                hot = self._cold_session()
                hot["f"] = {prefix: bad for prefix in hot["f"]}
                with open(L._hot_file(self.ledger, self.sid), "w", encoding="utf-8") as f:
                    json.dump(hot, f)
                self.child("agent-fork.jsonl", [A("p0", inp=1, out=1, sidechain=True)])
                _, sess, _ = self.settle()
                self.assertEqual((sess["in"], sess["out"]), (60, 60))

    def test_split_partitions_keep_every_member(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            hot = self._cold_session(200)
            parts = self._cold_keys()
            self.assertGreater(len(parts), 1)
            for prefix, keys in parts.items():
                for key in keys:
                    self.assertFalse(L._filter_absent(hot["f"][prefix], key), (prefix, key))

    def test_later_eviction_into_a_filtered_partition_refilters_it(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self._cold_session()
            before = self._cold_keys()
            self.write(self.parent, [A(f"q{i}", inp=1, out=1) for i in range(20)], mode="a")
            _, sess, _ = self.settle()
            self.assertEqual(sess["in"], 80)
            after = self._cold_keys()
            grown = [(p, k) for p, ks in after.items() if p in before
                     for k in ks - before[p] if k.startswith("rid:q")]
            self.assertTrue(grown, "a later eviction must land in an existing partition")
            self.child("agent-fork.jsonl",
                       [A(k[len("rid:"):], inp=1, out=1, sidechain=True) for _p, k in grown])
            _, sess, _ = self.settle()
            self.assertEqual((sess["in"], sess["out"]), (80, 80))

    def test_new_key_put_into_a_partition_keeps_the_filter_a_superset(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self._cold_session()
            rec = L._load_summary(self.ledger, self.sid)
            store = L._Store(self.ledger, self.sid, rec)
            prefix = next(p for p, seq in rec["parts"].items() if seq)
            store.put("rid:brand-new", {"s": {}}, prefix)
            self.assertTrue(store.flush(rec["seq"] + 1))
            self.assertFalse(L._filter_absent(store.hot["f"][prefix], "rid:brand-new"))

    def test_new_identities_read_no_cold_partition(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self._cold_session(200)
            self.write(self.parent, [A(f"fresh{k}", inp=1, out=1) for k in range(3)], mode="a")
            reads = []
            real = L._read_json

            def spy(path, default=None):
                if (".ev" + os.sep) in path:
                    reads.append(path)
                return real(path, default)
            with mock.patch.object(L, "_read_json", spy):
                _, sess, _ = self.update()
            self.assertEqual(sess["in"], 203)
            self.assertEqual(reads, [])


class TestTodayAcrossSessions(AccountingCase):

    def test_other_session_backlog_makes_today_catching_up(self):
        other_tx = self.write(os.path.join(self.proj, "other.jsonl"),
                              [A(f"o{i}", inp=1, out=1) for i in range(30)])
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 5):
            L.ledger_update({"session_id": "other", "transcript_path": other_tx}, "other")
        self.write(self.parent, [A("p1", inp=1, out=1)])
        _, sess, day = self.settle()
        self.assertEqual(sess["state"], "complete")
        self.assertEqual(day["state"], "catching_up")


class TestStarvation(AccountingCase):

    def test_parent_growing_faster_than_the_budget_cannot_starve_children(self):
        self.write(self.parent, [A("p0", inp=1, out=1)])
        for c in range(4):
            self.child(f"agent-{c}.jsonl", [A(f"k{c}_{i}", inp=1, out=0, sidechain=True)
                                            for i in range(30)])
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 40):
            for i in range(40):
                self.write(self.parent, [A(f"g{i}_{k}", inp=0, out=1) for k in range(60)],
                           mode="a")
                rec, _, _ = self.update()
                kids = sum(s["tok"][0] for k, s in rec["src"].items() if k != "p")
                if kids == 120:
                    break
            else:
                self.fail("children starved while the parent outgrew the budget")

    def test_growing_parent_cannot_starve_children(self):
        self.write(self.parent, [A(f"p{i}", inp=1, out=1) for i in range(50)])
        for c in range(20):
            self.child(f"agent-{c:02d}.jsonl", [A(f"c{c}_{i}", inp=1, out=1, sidechain=True)
                                                for i in range(30)])
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 40), \
                mock.patch.object(L, "ACCT_SOURCE_BUDGET", 4):
            for i in range(200):
                self.write(self.parent, [A(f"grow{i}", inp=1, out=1)], mode="a")
                _, sess, _ = self.update()
                if sess["in"] >= 50 + i + 1 + 600:
                    break
            else:
                self.fail("children starved by a growing parent")
            self.assertLess(i, 120)
            _, sess, _ = self.settle()
        self.assertEqual(sess["state"], "complete")


# =========================================================================== T-20 replacement/lifecycle
class TestReplacementLifecycle(AccountingCase):

    def _child_bytes(self, prefix, n, pad):
        return [A(f"{prefix}{i}", inp=1, out=1, sidechain=True, note="p" * pad) for i in range(n)]

    def setUp(self):
        super().setUp()
        self.write(self.parent, [A("p1", inp=1000, out=100)])
        self.child("agent-a.jsonl", [A("a1", inp=10, out=1, sidechain=True)])
        self.child("agent-b.jsonl", self._child_bytes("b", 40, 200))
        _, self.base, _ = self.settle()

    def test_same_size_replacement_rebuilds_only_that_source(self):
        p = os.path.join(self.subdir, "agent-b.jsonl")
        size = os.path.getsize(p)
        recs = self._child_bytes("X", 40, 200)
        self.child("agent-b.jsonl", recs)
        self.assertEqual(os.path.getsize(p), size)
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], self.base["in"])
        rec, _, _ = self.update()
        self.assertEqual(rec["src"]["c:agent-a.jsonl"]["tok"], [10, 1])
        self.assertEqual(rec["src"]["p"]["tok"], [1000, 100])

    def test_same_size_replacement_changing_only_the_head(self):
        recs = self._child_bytes("b", 40, 200)
        recs[0] = A("b0", inp=9, out=1, sidechain=True, note="p" * 200)   # same byte length
        p = os.path.join(self.subdir, "agent-b.jsonl")
        size = os.path.getsize(p)
        self.child("agent-b.jsonl", recs)
        self.assertEqual(os.path.getsize(p), size)
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], self.base["in"] + 8)

    def test_larger_replacement(self):
        self.child("agent-b.jsonl", self._child_bytes("Y", 60, 200))
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], 1000 + 10 + 60)

    def test_truncation(self):
        self.child("agent-b.jsonl", self._child_bytes("b", 5, 200))
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], 1000 + 10 + 5)

    def test_vanish_after_eof_preserves_accounting(self):
        os.remove(os.path.join(self.subdir, "agent-b.jsonl"))
        _, sess, _ = self.settle()
        self.assertEqual(sess["in"], self.base["in"])
        self.assertEqual(sess["state"], "complete")

    def test_vanish_then_reappear_counts_once(self):
        p = os.path.join(self.subdir, "agent-b.jsonl")
        with open(p, "rb") as f:
            content = f.read()
        os.remove(p)
        self.settle()
        with open(p, "wb") as f:
            f.write(content)
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (self.base["in"], self.base["out"]))
        self.assertEqual(sess["state"], "complete")
        self.child("agent-b.jsonl", [A("b-late", inp=7, out=3, sidechain=True)], mode="a")
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (self.base["in"] + 7, self.base["out"] + 3))

    def test_reappeared_unscanned_source_is_live_again(self):
        self.child("agent-c.jsonl", [A("c1", inp=5, out=5, sidechain=True)])
        p = os.path.join(self.subdir, "agent-c.jsonl")
        with open(p, "rb") as f:
            content = f.read()
        with mock.patch.object(L, "ACCT_SOURCE_BUDGET", 0):
            self.update()                              # discovered, not yet scanned
            os.remove(p)
            _, gone, _ = self.update()
            self.assertIn("source_vanished_with_backlog", gone["reasons"])
            with open(p, "wb") as f:
                f.write(content)
            _, back, _ = self.update()
        self.assertNotIn("source_vanished_with_backlog", back["reasons"])
        self.assertEqual(back["state"], "catching_up")
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["state"]), (self.base["in"] + 5, "complete"))

    def test_vanish_with_backlog_is_partial_and_preserves_subtotal(self):
        self.child("agent-c.jsonl", self._child_bytes("c", 30, 50))
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 10):
            _, first, _ = self.update()
        os.remove(os.path.join(self.subdir, "agent-c.jsonl"))
        _, sess, _ = self.settle()
        self.assertGreaterEqual(sess["in"], self.base["in"])
        self.assertIn("source_vanished_with_backlog", sess["reasons"])

    def test_listing_failure_keeps_known_sources(self):
        with mock.patch.object(L.os, "scandir", side_effect=PermissionError("denied")):
            _, sess, _ = self.update()
        self.assertEqual(sess["in"], self.base["in"])
        self.assertEqual(sess["state"], "catching_up")

    def test_replaced_co_observed_fork_request_recomputes(self):
        shared = A("shared", inp=10, out=500)
        self.write(self.parent, [shared], mode="a")
        self.child("agent-f.jsonl", [A("shared", inp=10, out=2, sidechain=True),
                                     A("f1", inp=5, out=5, sidechain=True)])
        _, sess, _ = self.settle()
        self.assertEqual(sess["out"], self.base["out"] + 500 + 5)
        self.child("agent-f.jsonl", [A("f2", inp=7, out=7, sidechain=True)])
        _, sess, _ = self.settle()
        self.assertEqual(sess["out"], self.base["out"] + 500 + 7)


# =========================================================================== T-22 principal fixture
class TestPrincipalTotals(AccountingCase):

    def test_independent_all_source_total(self):
        self.write(self.parent, [
            UREC("start"),
            A("p1", "claude-opus-5-5", inp=1000, out=200, w5=300, w1=100, cr=5000, out_note=None),
            A("p1", "claude-opus-5-5", inp=1000, out=900, w5=300, w1=100, cr=5000),   # snapshot
            A("p2", "claude-sonnet-5", inp=50, out=10,
              server_tool_use={"web_search_requests": 2, "web_fetch_requests": 3}),
            A("p3", "claude-opus-5-5", inp=10**6, out=0, speed="fast"),
        ])
        self.child("agent-k1.jsonl", [
            UREC("child one"),
            A("p1", "claude-opus-5-5", inp=1000, out=5, w5=300, w1=100, cr=5000, sidechain=True),
            A("k1", "claude-haiku-4-5-20251001", inp=400, out=40, cr=2000, sidechain=True),
        ])
        adv = A("k2", "claude-sonnet-5", inp=2, out=4, sidechain=True,
                iterations=[{"type": "message", "input_tokens": 1, "output_tokens": 2},
                            {"type": "advisor_message", "model": "claude-opus-5-5",
                             "input_tokens": 3000, "output_tokens": 300},
                            {"type": "message", "input_tokens": 1, "output_tokens": 2}])
        self.child("agent-k2.jsonl", [adv])
        _, sess, _ = self.settle()
        expected = (usd(OPUS55, inp=1000, out=900, w5=300, w1=100, cr=5000)
                    + usd(SONNET5, inp=50, out=10) + Fraction(2 * 10, 1000)
                    + Fraction(8, 1)                                   # 1M fast input @ $8
                    + usd(HAIKU45, inp=400, out=40, cr=2000)
                    + usd(SONNET5, inp=2, out=4) + usd(OPUS55, inp=3000, out=300))
        self.assertEqual(dollars(sess), expected)
        self.assertEqual(sess["in"], 1400 + 50 + 10**6 + 400 + 2 + 3000)
        self.assertEqual(sess["out"], 900 + 10 + 0 + 40 + 4 + 300)
        self.assertEqual(sess["state"], "complete")

    def test_host_cost_never_overrides_or_adds(self):
        self.write(self.parent, [A("p1", inp=10**6, out=0)])
        for host in (None, 0.01, 2.0, 999.0):
            _, sess, _ = self.update(cost=host)
            self.assertEqual(dollars(sess), 2)


# =========================================================================== T-24 calendar
class TestCalendar(AccountingCase):

    def test_parent_cross_midnight(self):
        self.write(self.parent, [A("y", inp=100, out=10, ts=f"{YESTERDAY}T23:59:00Z"),
                                 A("t", inp=1, out=1, ts=f"{TODAY}T00:01:00Z")])
        _, sess, day = self.settle()
        self.assertEqual((sess["in"], day["in"]), (101, 1))
        self.assertEqual(dollars(sess), usd(SONNET5, inp=101, out=11))
        self.assertEqual(dollars(day), usd(SONNET5, inp=1, out=1))

    def test_child_started_yesterday_completed_today(self):
        self.write(self.parent, [A("p", inp=1, out=1)])
        self.child("agent-m.jsonl", [A("m1", inp=500, out=5, ts=f"{YESTERDAY}T23:30:00Z",
                                       sidechain=True),
                                     A("m2", inp=7, out=7, ts=f"{TODAY}T00:30:00Z",
                                       sidechain=True)])
        _, sess, day = self.settle()
        self.assertEqual(sess["in"], 508)
        self.assertEqual(day["in"], 8)

    def test_unknown_event_time_is_session_only_and_today_partial(self):
        r = A("nt", inp=40, out=4)
        r["timestamp"] = "garbage"
        self.write(self.parent, [A("ok", inp=1, out=1), r])
        _, sess, day = self.settle()
        self.assertEqual(sess["in"], 41)
        self.assertEqual(day["in"], 1)
        self.assertIn("unknown_event_time", day["reasons"])
        self.assertEqual(sess["state"], "complete")

    def test_cross_midnight_replay_is_deterministic_and_flagged(self):
        late = A("x", inp=100, out=10, ts=f"{TODAY}T00:00:05Z")
        early = A("x", inp=100, out=10, ts=f"{YESTERDAY}T23:59:55Z", sidechain=True)
        outcomes = set()
        for parent_rec, child_rec in ((late, early), (early, late)):
            for first in ("parent", "child"):
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                shutil.rmtree(os.path.join(self.proj, self.sid), ignore_errors=True)
                self.write(self.parent, [A("base", inp=1, out=1)])
                if first == "child":
                    self.child("agent-r.jsonl", [child_rec])
                    self.settle()
                    self.write(self.parent, [parent_rec], mode="a")
                else:
                    self.write(self.parent, [parent_rec], mode="a")
                    self.settle()
                    self.child("agent-r.jsonl", [child_rec])
                _, sess, day = self.settle()
                outcomes.add((sess["in"], day["in"], "conflicting_event_day" in day["reasons"]))
        self.assertEqual(outcomes, {(101, 1, True)})


# =========================================================================== T-26 history scaling
class TestHistoryScaling(AccountingCase):

    def _evidence_bytes_loaded(self, render):
        loaded = []
        real = L._read_json

        def spy(path, default=None):
            v = real(path, default)
            if path.endswith(".hot.json") or (".ev" + os.sep) in path:
                try:
                    loaded.append(os.path.getsize(path))
                except OSError:
                    pass
            return v
        with mock.patch.object(L, "_read_json", spy):
            render()
        return loaded

    def test_no_change_and_incremental_costs_do_not_grow_with_history(self):
        observations = {}
        for n in (1000, 10000, 100000):
            shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
            self.write(self.parent, [A(f"h{i}", inp=1, out=1) for i in range(n)])
            with mock.patch.object(L, "ACCT_RECORD_BUDGET", 10**6), \
                    mock.patch.object(L, "ACCT_BYTE_BUDGET", 10**9):
                _, sess, _ = self.settle()
            self.assertEqual(sess["in"], n)
            quiet = self._evidence_bytes_loaded(lambda: self.update())
            self.write(self.parent, [A(f"new{n}_{k}", inp=1, out=1) for k in range(3)], mode="a")
            inc = self._evidence_bytes_loaded(lambda: self.update())
            observations[n] = (quiet, inc)
            self.assertEqual(quiet, [])
            self.assertLessEqual(len(inc), 1 + 3)
            for size in inc:
                self.assertLessEqual(size, L.PART_MAX * 1200)

    def test_derived_totals_equal_from_scratch_recomputation(self):
        self.write(self.parent, [A(f"h{i}", inp=i % 7, out=i % 5, ts=f"{TODAY}T10:{i % 60:02d}:00Z")
                                 for i in range(3000)]
                   + [A(f"h{i}", inp=i % 7, out=(i % 5) + 3) for i in range(0, 3000, 11)])
        with mock.patch.object(L, "ACCT_RECORD_BUDGET", 700):
            _, sess, day = self.settle()
        exp_in = sum(i % 7 for i in range(3000))
        exp_out = sum((i % 5) + (3 if i % 11 == 0 else 0) for i in range(3000))
        self.assertEqual((sess["in"], sess["out"]), (exp_in, exp_out))
        self.assertEqual(dollars(sess), usd(SONNET5, inp=exp_in, out=exp_out))

    def test_partition_splits_when_it_would_exceed_the_ceiling(self):
        with mock.patch.object(L, "HOT_MAX", 8), mock.patch.object(L, "PART_MAX", 16):
            self.write(self.parent, [A(f"s{i}", inp=1, out=1) for i in range(200)])
            _, sess, _ = self.settle()
            self.assertEqual(sess["in"], 200)
            ev = L._ev_dir(self.ledger, self.sid)
            sizes = []
            for n in os.listdir(ev):
                with open(os.path.join(ev, n), encoding="utf-8") as f:
                    sizes.append(len(json.load(f)["ev"]))
            self.assertGreater(len(sizes), 1)
            self.assertLessEqual(max(sizes), 16)
            # replaying every request again must dedupe across the cold store
            self.write(self.parent, [A(f"s{i}", inp=1, out=1) for i in range(200)], mode="a")
            _, sess, _ = self.settle()
            self.assertEqual(sess["in"], 200)


# =========================================================================== T-28 coverage
class TestCoverage(AccountingCase):

    def test_no_transcript_is_unavailable(self):
        _, sess, day = L.ledger_update({"session_id": self.sid}, self.sid)
        self.assertEqual(sess["state"], "unavailable")

    def test_reasons_per_scope(self):
        self.write(self.parent, [A("y", "mystery-model", ts=f"{YESTERDAY}T10:00:00Z"),
                                 A("t", inp=1, out=1)])
        _, sess, day = self.settle()
        self.assertEqual(sess["state"], "partial")
        self.assertIn("unknown_model", sess["reasons"])
        self.assertEqual(day["state"], "complete")

    def test_complete_session(self):
        self.write(self.parent, [A("t", inp=1, out=1)])
        _, sess, day = self.settle()
        self.assertEqual((sess["state"], day["state"]), ("complete", "complete"))
        self.assertEqual(sess["reasons"], [])


# =========================================================================== T-30 host estimate
class TestHostEstimate(AccountingCase):

    def setUp(self):
        super().setUp()
        self.write(self.parent, [A("p", inp=10**6, out=0)])

    def test_disappearance_keeps_state(self):
        self.update(cost=3.0)
        for bad in (None, "x", float("nan"), -1, True, float("inf")):
            with self.subTest(bad=bad):
                d = self.data()
                d["cost"] = {"total_cost_usd": bad}
                rec, sess, _ = L.ledger_update(d, self.sid)
                self.assertEqual(sess["host"], 3.0)
                self.assertEqual(dollars(sess), 2)
        self.assertTrue(rec["host"]["missing"])

    def test_regression_is_anomalous_and_max_kept(self):
        self.update(cost=5.0)
        rec, sess, _ = self.update(cost=4.0)
        self.assertEqual(sess["host"], 5.0)
        self.assertEqual(rec["host"]["latest"], 4.0)
        self.assertTrue(rec["host"]["anom"])
        self.assertEqual(dollars(sess), 2)

    def test_new_session_starts_at_zero(self):
        self.update(cost=5.0)
        _, sess, _ = L.ledger_update({"session_id": "other", "cost": {"total_cost_usd": 0.5}},
                                     "other")
        self.assertEqual(sess["host"], 0.5)

    def test_disagreement_is_diagnostic_only(self):
        for host in (1.0, 3.0):
            _, sess, _ = self.update(cost=host)
            self.assertEqual(dollars(sess), 2)
        self.assertAlmostEqual(sess["host_delta"], 3.0 - 2.0)


# =========================================================================== T-32 burn
class TestBurn(AccountingCase):

    def test_parent_only_burn_ignores_children_and_fork_replays(self):
        self.write(self.parent, [A("p1", inp=100, out=10), A("p1", inp=100, out=50),
                                 A("p2", inp=200, out=20)])
        rec, _, _ = self.settle()
        before = L.burn_samples(rec)
        self.assertEqual(before, [150.0, 220.0])
        self.child("agent-z.jsonl", [A("p2", inp=200, out=5, sidechain=True),
                                     A("z1", inp=9999, out=9999, sidechain=True)])
        rec, _, _ = self.settle()
        self.assertEqual(L.burn_samples(rec), before)


# =========================================================================== T-33 concurrency + lock
class TestBurnRing(AccountingCase):

    def test_update_to_an_evicted_request_is_not_re_appended(self):
        n = L.BURN_RING + 5
        self.write(self.parent, [A(f"b{i}", inp=1, out=i) for i in range(n)])
        rec, _, _ = self.settle()
        before = L.burn_samples(rec)
        self.write(self.parent, [A("b0", inp=1, out=10**6)], mode="a")
        rec, _, _ = self.settle()
        self.assertEqual(L.burn_samples(rec), before)


class TestLockAndConcurrency(AccountingCase):

    def test_held_lock_returns_stale_snapshot_quickly(self):
        self.write(self.parent, [A("p", inp=5, out=5)])
        _, sess0, day0 = self.settle(cost=1.0)
        self.write(self.parent, [A("q", inp=5, out=5)], mode="a")
        owner = _hooklib.acquire_lock(self.ledger)
        try:
            t0 = time.monotonic()
            _, sess, day = self.update()
            elapsed = time.monotonic() - t0
        finally:
            _hooklib.release_lock(owner)
        self.assertLess(elapsed, 0.5)
        self.assertTrue(sess["stale"])
        self.assertEqual((sess["in"], sess["pd"], sess["state"]),
                         (sess0["in"], sess0["pd"], sess0["state"]))
        self.assertEqual(day["in"], day0["in"])
        self.assertEqual(sess["host"], 1.0)

    def test_held_lock_without_snapshot_is_unavailable_not_zero(self):
        self.write(self.parent, [A("p", inp=5, out=5)])
        owner = _hooklib.acquire_lock(self.ledger)
        try:
            _, sess, day = self.update()
        finally:
            _hooklib.release_lock(owner)
        self.assertEqual(sess["state"], "unavailable")
        self.assertTrue(sess["stale"])

    def test_render_lock_wait_is_bounded(self):
        self.assertLessEqual(L.UI_LOCK_WAIT, 0.02)
        seen = []
        real = L._acquire_lock

        def spy(path, wait_seconds=None):
            seen.append(wait_seconds)
            return real(path, wait_seconds)
        self.write(self.parent, [A("p")])
        with mock.patch.object(L, "_acquire_lock", spy):
            self.update()
        self.assertEqual(seen, [L.UI_LOCK_WAIT])

    def test_crash_between_evidence_and_summary_is_detected(self):
        self.write(self.parent, [A("p1", inp=1, out=1)])
        self.settle()
        self.write(self.parent, [A("p2", inp=2, out=2)], mode="a")
        real = L._atomic_json

        def fail_summary(path, value):
            if path.endswith(".acct.json"):
                return False
            return real(path, value)
        with mock.patch.object(L, "_atomic_json", fail_summary):
            self.update()
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 3))

    def test_crash_writing_evidence_leaves_state_consistent(self):
        self.write(self.parent, [A("p1", inp=1, out=1)])
        self.settle()
        self.write(self.parent, [A("p2", inp=2, out=2)], mode="a")
        real = L._atomic_json

        def fail_hot(path, value):
            if path.endswith(".hot.json"):
                return False
            return real(path, value)
        with mock.patch.object(L, "_atomic_json", fail_hot):
            self.update()
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 3))
        self.write(self.parent, [A("p2", inp=2, out=2)], mode="a")     # replayed snapshot
        _, sess, _ = self.settle()
        self.assertEqual((sess["in"], sess["out"]), (3, 3))

    def test_session_start_write_cannot_erase_accounting(self):
        self.write(self.parent, [A("p1", inp=1, out=1)])
        self.settle()
        self.assertTrue(L.persist_sess_start(self.sid, 123.0))
        self.write(self.parent, [A("p2", inp=2, out=2)], mode="a")
        rec, sess, _ = self.settle()
        self.assertEqual(rec["sess_start"], 123.0)
        self.assertEqual(sess["in"], 3)

    def test_distinct_sessions_keep_their_own_totals_and_today_sums(self):
        other_tx = self.write(os.path.join(self.proj, "other.jsonl"), [A("o1", inp=7, out=7)])
        L.ledger_update({"session_id": "other", "transcript_path": other_tx}, "other")
        self.write(self.parent, [A("p1", inp=1, out=1)])
        _, sess, day = self.settle()
        self.assertEqual(sess["in"], 1)
        self.assertEqual(day["in"], 8)


# =========================================================================== T-43 structural I/O
class TestStructuralIO(AccountingCase):

    def _io(self, fn):
        counters = {"tx_read": 0, "ledger_writes": 0, "evidence_reads": 0}
        real_open, real_replace = builtins.open, os.replace
        tx_root = os.path.abspath(self.proj)

        class Spy:
            def __init__(self, f):
                self.f = f

            def read(self, *a):
                d = self.f.read(*a)
                counters["tx_read"] += len(d)
                return d

            def readline(self, *a):
                d = self.f.readline(*a)
                counters["tx_read"] += len(d)
                return d

            def __enter__(self):
                self.f.__enter__()
                return self

            def __exit__(self, *a):
                return self.f.__exit__(*a)

            def __getattr__(self, k):
                return getattr(self.f, k)

        def spy_open(p, *a, **k):
            f = real_open(p, *a, **k)
            s = os.path.abspath(str(p))
            if s.endswith(".hot.json") or ".ev" + os.sep in s:
                if not (a and "w" in a[0]):
                    counters["evidence_reads"] += 1
            if s.startswith(tx_root) and s.endswith(".jsonl"):
                return Spy(f)
            return f

        def spy_replace(a, b):
            counters["ledger_writes"] += 1
            return real_replace(a, b)
        with mock.patch.object(builtins, "open", spy_open), mock.patch.object(L.os, "replace", spy_replace):
            fn()
        return counters

    def _setup(self, children):
        self.write(self.parent, [A(f"p{i}") for i in range(30)])
        for c in range(children):
            self.child(f"agent-{c:03d}.jsonl", [A(f"c{c}_{i}", sidechain=True) for i in range(5)])
        self.settle(cost=1.0)
        self.update(cost=1.0)

    def test_no_change_render_reads_and_writes_nothing(self):
        for n in (0, 1, 12, 13, 64):
            with self.subTest(children=n):
                shutil.rmtree(os.path.dirname(self.ledger), ignore_errors=True)
                shutil.rmtree(os.path.join(self.proj, self.sid), ignore_errors=True)
                self._setup(n)
                c = self._io(lambda: self.update(cost=1.0))
                self.assertEqual(c, {"tx_read": 0, "ledger_writes": 0, "evidence_reads": 0})

    def test_host_only_change_writes_summary_only(self):
        self._setup(2)
        c = self._io(lambda: self.update(cost=2.0))
        self.assertEqual(c, {"tx_read": 0, "ledger_writes": 1, "evidence_reads": 0})

    def test_heartbeat_writes_at_most_once_per_interval(self):
        self._setup(1)
        acct = L._acct_file(self.ledger, self.sid)
        with open(acct, encoding="utf-8") as f:
            payload = json.load(f)
        payload["rec"]["last_ts"] = time.time() - L.LEDGER_HEARTBEAT - 5
        with open(acct, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        first = self._io(lambda: self.update(cost=1.0))
        second = self._io(lambda: self.update(cost=1.0))
        self.assertEqual(first["ledger_writes"], 1)
        self.assertEqual(second["ledger_writes"], 0)
        self.assertEqual(first["tx_read"] + first["evidence_reads"], 0)

    def test_incremental_render_writes_summary_and_hot_only(self):
        self._setup(3)
        self.write(self.parent, [A("fresh1"), A("fresh2")], mode="a")
        c = self._io(lambda: self.update(cost=1.0))
        self.assertEqual(c["ledger_writes"], 2)
        self.assertLessEqual(c["evidence_reads"], 1)


class TestPresentationSummaries(AccountingCase):

    def test_child_summary_carries_label_models_tokens(self):
        self.write(self.parent, [A("p")])
        self.child("agent-lbl.jsonl", [UREC("Write the parser\nmore text"),
                                       A("c1", "claude-haiku-4-5-20251001", inp=30, out=3,
                                         w5=5, sidechain=True)])
        rec, _, _ = self.settle()
        s = rec["src"]["c:agent-lbl.jsonl"]
        import _subagentslib
        self.assertEqual(s["label"], _subagentslib.sub_label("Write the parser\nmore text"))
        self.assertTrue(s["label"].startswith("Write the parser"))
        self.assertEqual(s["models"], ["claude-haiku-4-5-20251001"])
        self.assertEqual(s["tok"], [35, 3])


if __name__ == "__main__":
    unittest.main()
