"""Tests for _usagelib — the single owner of Claude transcript usage normalization,
request identity, reconciliation and pricing (spec D-5..D-10, D-26, D-27).

Every expected dollar amount here is computed from the published $/MTok list prices
written out literally in this file. None is derived by calling the production
pricing code, so the tests check the registry rather than restating it.
"""
import itertools
import json
import os
import random
import sys
import unittest
from fractions import Fraction

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _usagelib as U  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "statusline_accounting")


def pd(usd_per_mtok):
    """Published $/MTok -> integer picodollars per token, computed independently."""
    v = Fraction(str(usd_per_mtok)) * 10**6
    assert v.denominator == 1
    return int(v)


def usd(picodollars):
    return Fraction(picodollars, 10**12)


def rec(model="claude-sonnet-5", rid="req_a", mid="msg_a", ts="2026-09-27T10:00:00Z",
        **usage):
    u = {"input_tokens": 0, "output_tokens": 0}
    u.update(usage)
    r = {"type": "assistant", "timestamp": ts,
         "message": {"role": "assistant", "model": model, "usage": u}}
    if rid is not None:
        r["requestId"] = rid
    if mid is not None:
        r["message"]["id"] = mid
    return r


def load(name):
    with open(os.path.join(FIXTURES, *name.split("/")), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def accept(*records, day=lambda ts: "2026-09-27"):
    """Normalize and merge a sequence of records of ONE request (single source)."""
    fact = None
    for r in records:
        n = U.normalize(r, day)
        assert n["kind"] == "usage", n
        fact = n["fact"] if fact is None else U.merge(fact, n["fact"])
    return fact


# =========================================================================== T-04 pricing
PUBLISHED = {
    # model id: (input, output, 5m write, 1h write, cache read) $/MTok, captured 2026-09-27
    "claude-fable-5-1": (10, 50, "12.50", 20, "0.25"),
    "claude-opus-5-5": (4, 20, 5, 8, "0.20"),
    "claude-opus-5": (5, 25, "6.25", 10, "0.50"),
    "claude-sonnet-5": (2, 10, "2.50", 4, "0.20"),
    "claude-haiku-4-5": (1, 5, "1.25", 2, "0.10"),
}


class TestPricingRegistry(unittest.TestCase):

    def test_current_models_exact_rates(self):
        for model, rates in PUBLISHED.items():
            with self.subTest(model=model):
                self.assertEqual(U.rates(model), tuple(pd(r) for r in rates))

    def test_historical_opus_5_is_not_opus_5_5(self):
        self.assertEqual(U.rates("claude-opus-5"),
                         (pd(5), pd(25), pd("6.25"), pd(10), pd("0.50")))
        self.assertNotEqual(U.rates("claude-opus-5"), U.rates("claude-opus-5-5"))

    def test_fable_5_1_cache_read_is_the_published_quarter_dollar(self):
        self.assertEqual(U.rates("claude-fable-5-1")[4], pd("0.25"))

    def test_registry_records_capture_date_and_source(self):
        self.assertRegex(U.REGISTRY_CAPTURED, r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(U.REGISTRY_SOURCE.startswith("https://"))
        self.assertTrue(U.REGISTRY_VERSION)

    def test_every_rate_and_modifier_product_is_an_exact_integer(self):
        for model in U.known_models():
            for speed, geo in itertools.product(("standard", "fast"), ("global", "us")):
                r = U.rates(model, speed=speed, geo=geo)
                if r is None:
                    continue
                for v in r:
                    with self.subTest(model=model, speed=speed, geo=geo):
                        self.assertIsInstance(v, int)

    def test_unknown_model_has_no_rates(self):
        for m in ("some-unknown-model", "claude-opus-6", "claude-opus-5-5-preview",
                  "gpt-5", "", None, 7, ["claude-opus-5-5"]):
            with self.subTest(model=m):
                self.assertIsNone(U.rates(m))

    def test_aliases_are_explicit(self):
        self.assertEqual(U.canonical_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5")
        self.assertEqual(U.canonical_model("claude-opus-5[1m]"), "claude-opus-5")
        self.assertEqual(U.canonical_model("Claude-Opus-5-5"), "claude-opus-5-5")
        # [1m] only aliases where long context is billed at standard rates (4.6+).
        self.assertIsNone(U.rates("claude-sonnet-4-5[1m]"))
        # a non-alias suffix is not silently stripped
        self.assertIsNone(U.rates("claude-sonnet-5-experimental"))

    def test_synthetic_model_has_no_rates(self):
        self.assertIsNone(U.rates("<synthetic>"))

    def test_fast_mode_rates(self):
        # Fast: Opus 5.5 $8 in / $40 out; cache multipliers stack on the fast input
        # rate (5m 1.25x, 1h 2x, read 0.05x for Opus 5.5).
        self.assertEqual(U.rates("claude-opus-5-5", speed="fast"),
                         (pd(8), pd(40), pd(10), pd(16), pd("0.40")))
        self.assertEqual(U.rates("claude-opus-5", speed="fast"),
                         (pd(10), pd(50), pd("12.50"), pd(20), pd(1)))
        self.assertIsNone(U.rates("claude-sonnet-5", speed="fast"))

    def test_us_inference_geo_multiplier(self):
        self.assertEqual(U.rates("claude-sonnet-5", geo="us"),
                         (pd("2.2"), pd(11), pd("2.75"), pd("4.4"), pd("0.22")))
        # Opus 5 predates nothing here but 4.5 does: earlier models reject `us`.
        self.assertIsNone(U.rates("claude-opus-4-5", geo="us"))

    def test_web_search_is_priced_and_web_fetch_is_known_zero(self):
        self.assertEqual(U.TOOL_PRICES["web_search_requests"], pd(10) * 10**6 // 1000)
        self.assertEqual(U.TOOL_PRICES["web_fetch_requests"], 0)
        self.assertNotIn("code_execution_requests", U.TOOL_PRICES)


class TestPriceFact(unittest.TestCase):

    def test_simple_opus_5_5_cost(self):
        fact = accept(rec("claude-opus-5-5", input_tokens=1000, output_tokens=2000,
                          cache_read_input_tokens=10000,
                          cache_creation_input_tokens=300,
                          cache_creation={"ephemeral_5m_input_tokens": 100,
                                          "ephemeral_1h_input_tokens": 200}))
        p = U.price(fact)
        expected = (1000 * Fraction(4) + 2000 * Fraction(20) + 10000 * Fraction("0.20")
                    + 100 * Fraction(5) + 200 * Fraction(8)) / 10**6
        self.assertEqual(usd(p["pd"]), expected)
        self.assertEqual(p["in"], 1300)          # uncached + all cache writes
        self.assertEqual(p["out"], 2000)
        self.assertEqual(p["reasons"], set())

    def test_unknown_model_counts_tokens_but_no_dollars(self):
        p = U.price(accept(rec("claude-opus-9", input_tokens=10, output_tokens=5)))
        self.assertEqual((p["in"], p["out"], p["pd"]), (10, 5, 0))
        self.assertEqual(p["reasons"], {"unknown_model"})

    def test_never_falls_back_to_sonnet(self):
        p = U.price(accept(rec("mystery", input_tokens=10**6)))
        self.assertEqual(p["pd"], 0)

    def test_fast_mode_prices_at_fast_rate(self):
        p = U.price(accept(rec("claude-opus-5-5", input_tokens=10**6, output_tokens=10**6,
                               speed="fast")))
        self.assertEqual(usd(p["pd"]), 8 + 40)
        self.assertEqual(p["reasons"], set())

    def test_us_geo_prices_at_1_1x(self):
        p = U.price(accept(rec("claude-sonnet-5", input_tokens=10**6, inference_geo="us")))
        self.assertEqual(usd(p["pd"]), Fraction("2.2"))

    def test_standard_modifier_spellings_are_standard(self):
        for extra in ({}, {"speed": "standard"}, {"service_tier": "standard"},
                      {"inference_geo": "not_available"}, {"inference_geo": "global"},
                      {"speed": None, "service_tier": None, "inference_geo": None}):
            with self.subTest(extra=extra):
                p = U.price(accept(rec("claude-sonnet-5", input_tokens=10**6, **extra)))
                self.assertEqual(usd(p["pd"]), 2)
                self.assertEqual(p["reasons"], set())

    def test_unmodeled_modifiers_make_coverage_partial(self):
        for extra in ({"speed": "fast"},             # sonnet has no published fast rate
                      {"speed": "turbo"}, {"service_tier": "priority"},
                      {"service_tier": "batch"}, {"inference_geo": "eu"}):
            with self.subTest(extra=extra):
                p = U.price(accept(rec("claude-sonnet-5", input_tokens=10**6, **extra)))
                self.assertEqual(p["pd"], 0)
                self.assertEqual(p["in"], 10**6)
                self.assertIn("unpriced_modifier", p["reasons"])

    def test_conflicting_modifiers_across_representations_are_partial(self):
        # One request cannot be both standard and fast; which rate applies is unproven.
        p = U.price(accept(rec("claude-opus-5-5", input_tokens=10**6, speed="standard"),
                           rec("claude-opus-5-5", input_tokens=10**6, speed="fast")))
        self.assertEqual(p["pd"], 0)
        self.assertIn("unpriced_modifier", p["reasons"])

    def test_absent_modifier_is_no_vote_across_representations(self):
        # A streaming snapshot that omits a modifier must not conflict with a
        # later representation that states it (in either arrival order).
        cases = [({}, {"speed": "fast"}, "claude-opus-5-5", 8),
                 ({}, {"inference_geo": "not_available"}, "claude-sonnet-5", 2),
                 ({"inference_geo": "global"}, {"inference_geo": "not_available"},
                  "claude-sonnet-5", 2),
                 ({}, {"inference_geo": "us"}, "claude-sonnet-5", Fraction("2.2")),
                 ({"speed": None}, {"speed": "fast"}, "claude-opus-5-5", 8),
                 ({"speed": "  "}, {"speed": "fast"}, "claude-opus-5-5", 8)]
        for first, second, model, want in cases:
            for order in ((first, second), (second, first)):
                with self.subTest(order=order):
                    p = U.price(accept(rec(model, input_tokens=10**6, **order[0]),
                                       rec(model, input_tokens=10**6, **order[1])))
                    self.assertEqual(p["reasons"], set())
                    self.assertEqual(usd(p["pd"]), want)

    def test_synthetic_zero_record_is_non_billable(self):
        for r in load("synthetic.jsonl"):
            with self.subTest(r=r.get("requestId")):
                n = U.normalize(r, lambda ts: "d")
                self.assertEqual(n["kind"], "ignore")

    def test_synthetic_nonzero_is_an_unknown_model(self):
        p = U.price(accept(rec("<synthetic>", input_tokens=5)))
        self.assertEqual(p["reasons"], {"unknown_model"})
        self.assertEqual(p["in"], 5)


# =========================================================================== T-06 normalization
class TestNormalizeCounters(unittest.TestCase):

    def test_non_assistant_and_non_usage_records_are_ignored(self):
        for r in load("nonusage_types.jsonl") + load("cost_state.jsonl"):
            with self.subTest(type=r.get("type")):
                self.assertEqual(U.normalize(r, lambda ts: "d")["kind"], "ignore")

    def test_attachment_usage_summary_is_never_usage(self):
        att = {"type": "attachment", "timestamp": "2026-09-27T10:00:00Z",
               "attachment": {"type": "queued_command", "usage": {"totalTokens": 86090}}}
        self.assertEqual(U.normalize(att, lambda ts: "d")["kind"], "ignore")

    def test_non_object_values_are_ignored_not_raised(self):
        for v in ([], None, 3, "s", True, [{"type": "assistant"}]):
            with self.subTest(v=v):
                self.assertEqual(U.normalize(v, lambda ts: "d")["kind"], "ignore")

    def test_malformed_counters(self):
        for bad in (-1, float("nan"), float("inf"), True, 1.5, "100", 10**16, [1], {"a": 1}):
            with self.subTest(bad=bad):
                n = U.normalize(rec(input_tokens=bad), lambda ts: "d")
                self.assertEqual(n["kind"], "malformed")
                self.assertEqual(n["reason"], "malformed_record")

    def test_integral_float_counter_is_accepted(self):
        n = U.normalize(rec(input_tokens=100.0), lambda ts: "d")
        self.assertEqual(n["kind"], "usage")

    def test_non_object_usage_is_malformed(self):
        r = rec()
        r["message"]["usage"] = [1, 2]
        self.assertEqual(U.normalize(r, lambda ts: "d")["kind"], "malformed")

    def test_assistant_without_usage_is_ignored(self):
        r = rec()
        del r["message"]["usage"]
        self.assertEqual(U.normalize(r, lambda ts: "d")["kind"], "ignore")

    def test_missing_counters_default_to_zero(self):
        p = U.price(accept(rec("claude-sonnet-5", output_tokens=10)))
        self.assertEqual((p["in"], p["out"]), (0, 10))


class TestCacheClassification(unittest.TestCase):
    """AC-15 / AC-37: cache writes are a total plus a TTL classification."""

    def price(self, *usages, model="claude-sonnet-5"):
        return U.price(accept(*[rec(model, **u) for u in usages]))

    def test_no_cache(self):
        p = self.price(dict(input_tokens=10))
        self.assertEqual(p["reasons"], set())

    def test_cache_read_priced(self):
        p = self.price(dict(cache_read_input_tokens=10**6))
        self.assertEqual(usd(p["pd"]), Fraction("0.20"))
        self.assertEqual(p["in"], 0)

    def test_five_minute_write(self):
        p = self.price(dict(cache_creation_input_tokens=10**6,
                            cache_creation={"ephemeral_5m_input_tokens": 10**6,
                                            "ephemeral_1h_input_tokens": 0}))
        self.assertEqual(usd(p["pd"]), Fraction("2.50"))

    def test_one_hour_write(self):
        p = self.price(dict(cache_creation_input_tokens=10**6,
                            cache_creation={"ephemeral_5m_input_tokens": 0,
                                            "ephemeral_1h_input_tokens": 10**6}))
        self.assertEqual(usd(p["pd"]), 4)

    def test_aggregate_only_is_unknown_ttl_not_invented(self):
        p = self.price(dict(cache_creation_input_tokens=1000))
        self.assertEqual(p["pd"], 0)
        self.assertEqual(p["in"], 1000)          # tokens still count
        self.assertEqual(p["reasons"], {"unknown_cache_ttl"})

    def test_incomplete_split_prices_classified_part_only(self):
        p = self.price(dict(cache_creation_input_tokens=10**6,
                            cache_creation={"ephemeral_5m_input_tokens": 400000,
                                            "ephemeral_1h_input_tokens": 0}))
        self.assertEqual(usd(p["pd"]), Fraction("2.50") * Fraction(4, 10))
        self.assertEqual(p["in"], 10**6)
        self.assertEqual(p["reasons"], {"unknown_cache_ttl"})

    def test_split_exceeding_aggregate_never_prices_the_excess(self):
        p = self.price(dict(cache_creation_input_tokens=100,
                            cache_creation={"ephemeral_5m_input_tokens": 100,
                                            "ephemeral_1h_input_tokens": 100}))
        self.assertEqual(p["in"], 100)
        self.assertEqual(p["pd"], 0)
        self.assertEqual(p["reasons"], {"unknown_cache_ttl"})

    # ---- AC-37 refinement sequences (one request, several representations)
    AGG = dict(cache_creation_input_tokens=100)

    def split(self, c5, c1, agg=100):
        return dict(cache_creation_input_tokens=agg,
                    cache_creation={"ephemeral_5m_input_tokens": c5,
                                    "ephemeral_1h_input_tokens": c1})

    def assertWrites(self, p, total, priced_usd):
        self.assertEqual(p["in"], total)
        self.assertEqual(usd(p["pd"]), Fraction(priced_usd))

    def test_aggregate_only_then_complete_5m(self):
        p = self.price(self.AGG, self.split(100, 0))
        self.assertWrites(p, 100, Fraction("2.50") * 100 / 10**6)
        self.assertEqual(p["reasons"], set())

    def test_aggregate_only_then_complete_1h(self):
        p = self.price(self.AGG, self.split(0, 100))
        self.assertWrites(p, 100, Fraction(4) * 100 / 10**6)

    def test_partial_then_complete(self):
        p = self.price(self.split(40, 0), self.split(100, 0))
        self.assertWrites(p, 100, Fraction("2.50") * 100 / 10**6)

    def test_complete_then_less_complete_replay(self):
        p = self.price(self.split(100, 0), self.split(40, 0))
        self.assertWrites(p, 100, Fraction("2.50") * 100 / 10**6)
        self.assertEqual(p["reasons"], set())

    def test_aggregate_increase_with_partial_classification(self):
        p = self.price(self.split(40, 0, agg=50), self.split(40, 0, agg=100))
        self.assertWrites(p, 100, Fraction("2.50") * 40 / 10**6)
        self.assertEqual(p["reasons"], {"unknown_cache_ttl"})

    def test_conflicting_classifications_never_double_price(self):
        p = self.price(self.split(100, 0), self.split(0, 100))
        self.assertEqual(p["in"], 100)
        self.assertEqual(p["pd"], 0)
        self.assertEqual(p["reasons"], {"unknown_cache_ttl"})

    def test_refinement_is_order_independent(self):
        seqs = [self.AGG, self.split(40, 0), self.split(100, 0), self.split(60, 0, agg=80)]
        results = {json.dumps(U.price(accept(*[rec(**u) for u in perm])), sort_keys=True,
                              default=sorted)
                   for perm in itertools.permutations(seqs)}
        self.assertEqual(len(results), 1)


class TestIterations(unittest.TestCase):
    """D-26 / AC-44: advisor iterations are billable at their own model."""

    def test_observed_advisor_record(self):
        reps = load("advisor_iterations.jsonl")
        final = max(reps, key=lambda r: len(r["message"]["usage"].get("iterations") or []))
        u = final["message"]["usage"]
        its = u["iterations"]
        adv = its[1]
        model = final["message"]["model"]
        p = U.price(accept(*reps))
        top_rates = PUBLISHED[model] if model in PUBLISHED else None
        self.assertIsNotNone(top_rates, "fixture top-level model must be in PUBLISHED")
        adv_rates = PUBLISHED[adv["model"]]
        msg = [i for i in its if i["type"] == "message"]
        c5 = sum(i["cache_creation"]["ephemeral_5m_input_tokens"] for i in msg)
        c1 = sum(i["cache_creation"]["ephemeral_1h_input_tokens"] for i in msg)

        def cost(r, inp, out, cr, w5, w1):
            return (inp * Fraction(str(r[0])) + out * Fraction(str(r[1]))
                    + w5 * Fraction(str(r[2])) + w1 * Fraction(str(r[3]))
                    + cr * Fraction(str(r[4]))) / 10**6
        expected = (cost(top_rates, u["input_tokens"], u["output_tokens"],
                         u["cache_read_input_tokens"], c5, c1)
                    + cost(adv_rates, adv["input_tokens"], adv["output_tokens"],
                           adv["cache_read_input_tokens"],
                           adv["cache_creation"]["ephemeral_5m_input_tokens"],
                           adv["cache_creation"]["ephemeral_1h_input_tokens"]))
        self.assertEqual(usd(p["pd"]), expected)
        self.assertEqual(p["in"], u["input_tokens"] + u["cache_creation_input_tokens"]
                         + adv["input_tokens"] + adv["cache_creation_input_tokens"])
        self.assertEqual(p["out"], u["output_tokens"] + adv["output_tokens"])
        self.assertEqual(p["reasons"], set())

    def _iters(self, *its, model="claude-sonnet-5"):
        msg = [i for i in its if i["type"] == "message"]
        top = {k: sum(i.get(k, 0) for i in msg)
               for k in ("input_tokens", "output_tokens")}
        return rec(model, iterations=list(its), **top)

    def test_two_same_model_advisor_calls_in_one_turn_are_summed(self):
        r = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                        {"type": "advisor_message", "model": "claude-opus-5-5",
                         "input_tokens": 10**6, "output_tokens": 0},
                        {"type": "message", "input_tokens": 1, "output_tokens": 1},
                        {"type": "advisor_message", "model": "claude-opus-5-5",
                         "input_tokens": 10**6, "output_tokens": 0},
                        {"type": "message", "input_tokens": 1, "output_tokens": 1})
        p = U.price(accept(r))
        advisor_usd = 2 * 4       # two advisor calls x 1M input at Opus 5.5 $4
        top_usd = Fraction(3 * 2 + 3 * 10, 10**6)
        self.assertEqual(usd(p["pd"]), advisor_usd + top_usd)

    def test_advisor_snapshots_reconcile_by_max_not_sum(self):
        early = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                            {"type": "advisor_message", "model": "claude-opus-5-5",
                             "input_tokens": 10**6, "output_tokens": 0})
        late = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                           {"type": "advisor_message", "model": "claude-opus-5-5",
                            "input_tokens": 10**6, "output_tokens": 0},
                           {"type": "message", "input_tokens": 1, "output_tokens": 5})
        p = U.price(accept(early, late, early))
        self.assertEqual(usd(p["pd"]), 4 + Fraction(2 * 2 + 6 * 10, 10**6))

    def test_unknown_iteration_type_is_partial(self):
        r = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                        {"type": "critic_message", "model": "claude-opus-5-5",
                         "input_tokens": 100, "output_tokens": 0})
        p = U.price(accept(r))
        self.assertIn("unknown_iteration", p["reasons"])
        self.assertEqual(p["in"], 101)

    def test_advisor_without_model_is_unknown_model(self):
        r = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                        {"type": "advisor_message", "input_tokens": 100, "output_tokens": 0})
        p = U.price(accept(r))
        self.assertIn("unknown_model", p["reasons"])
        self.assertEqual(p["in"], 101)

    def test_zero_unknown_iteration_does_not_affect_coverage(self):
        r = self._iters({"type": "message", "input_tokens": 1, "output_tokens": 1},
                        {"type": "critic_message", "input_tokens": 0, "output_tokens": 0})
        self.assertEqual(U.price(accept(r))["reasons"], set())

    def test_stale_top_level_split_uses_iteration_split(self):
        reps = load("advisor_iterations.jsonl")
        self.assertNotIn("unknown_cache_ttl", U.price(accept(*reps))["reasons"])


class TestServerTools(unittest.TestCase):
    """AC-16 (synthetic records: no non-zero counter was observed locally)."""

    def test_web_search_priced_once_across_representations(self):
        r = rec("claude-sonnet-5", server_tool_use={"web_search_requests": 3,
                                                   "web_fetch_requests": 0})
        p = U.price(accept(r, r, r))
        self.assertEqual(usd(p["pd"]), Fraction(3 * 10, 1000))
        self.assertEqual(p["reasons"], set())

    def test_web_fetch_is_known_zero(self):
        p = U.price(accept(rec(server_tool_use={"web_fetch_requests": 4})))
        self.assertEqual(p["pd"], 0)
        self.assertEqual(p["reasons"], set())

    def test_unknown_or_code_execution_counter_is_partial(self):
        for name in ("code_execution_requests", "mystery_requests"):
            with self.subTest(name=name):
                p = U.price(accept(rec(server_tool_use={name: 1})))
                self.assertIn("unknown_charge", p["reasons"])

    def test_zero_unknown_counter_is_fine(self):
        p = U.price(accept(rec(input_tokens=1, server_tool_use={"mystery_requests": 0})))
        self.assertEqual(p["reasons"], set())

    def test_malformed_tool_counter(self):
        n = U.normalize(rec(server_tool_use={"web_search_requests": -2}), lambda ts: "d")
        self.assertEqual(n["kind"], "malformed")


# =========================================================================== T-08 identity/merge
class TestIdentity(unittest.TestCase):

    def ident(self, r):
        return U.classify_identity(r)

    def test_request_id_preferred(self):
        self.assertEqual(self.ident(rec(rid="req_1", mid="msg_1")), ("rid:req_1", "mid:msg_1"))

    def test_message_id_fallback(self):
        self.assertEqual(self.ident(rec(rid=None, mid="msg_1")), ("mid:msg_1", None))

    def test_invalid_ids_are_unproven(self):
        for bad in (None, "", 5, 5.0, True, False, [], ["a"], {}, {"a": 1},
                    "x" * 257, "bad\nid", "tab\tid", "\x7f"):
            with self.subTest(bad=bad):
                r = rec(rid=None, mid=None)
                r["requestId"] = bad
                r["message"]["id"] = bad
                self.assertEqual(self.ident(r), (None, None))

    def test_domain_separation(self):
        # A real requestId that LOOKS like a key of another class stays in its class.
        a = self.ident(rec(rid="mid:msg_1", mid=None))[0]
        b = self.ident(rec(rid=None, mid="msg_1"))[0]
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("rid:"))

    def test_unhashable_ids_never_raise(self):
        r = rec(rid=None, mid=None)
        r["requestId"] = {"nested": ["x"]}
        r["message"]["id"] = [["y"]]
        self.assertEqual(self.ident(r), (None, None))


class TestMerge(unittest.TestCase):

    def test_larger_equal_smaller_replays(self):
        a = rec(input_tokens=10, output_tokens=5)
        b = rec(input_tokens=10, output_tokens=50)
        c = rec(input_tokens=10, output_tokens=20)
        p = U.price(accept(a, b, c))
        self.assertEqual((p["in"], p["out"]), (10, 50))

    def test_merge_is_commutative_associative_idempotent(self):
        reps = load("streaming_snapshots.jsonl") + load("advisor_iterations.jsonl")[:3]
        # re-key everything to one request so they reconcile together
        for r in reps:
            r["requestId"] = "req_same"
        facts = [U.normalize(r, lambda ts: ts[:10])["fact"] for r in reps]
        canon = None
        rng = random.Random(7)
        for _ in range(40):
            order = facts[:]
            rng.shuffle(order)
            merged = order[0]
            for f in order[1:]:
                merged = U.merge(merged, f)
            merged = U.merge(merged, order[rng.randrange(len(order))])   # idempotent
            s = json.dumps(merged, sort_keys=True)
            canon = canon or s
            self.assertEqual(s, canon)

    def test_model_conflict_is_partial_not_last_write_wins(self):
        p = U.price(accept(rec("claude-sonnet-5", input_tokens=10**6),
                           rec("claude-opus-5-5", input_tokens=10**6)))
        self.assertIn("model_conflict", p["reasons"])
        self.assertEqual(p["pd"], 0)
        self.assertEqual(p["in"], 10**6)          # never summed across the conflict

    def test_alias_equivalent_models_do_not_conflict(self):
        p = U.price(accept(rec("claude-haiku-4-5", input_tokens=10**6),
                           rec("claude-haiku-4-5-20251001", input_tokens=10**6)))
        self.assertEqual(p["reasons"], set())
        self.assertEqual(usd(p["pd"]), 1)

    def test_event_time_is_minimum_and_order_independent(self):
        early = rec(ts="2026-09-26T23:59:00Z", input_tokens=1)
        late = rec(ts="2026-09-27T00:01:00Z", input_tokens=2)
        day = lambda ts: ts[:10]  # noqa: E731
        a = accept(early, late, day=day)
        b = accept(late, early, day=day)
        self.assertEqual(a, b)
        self.assertEqual(U.event_day(a), "2026-09-26")
        self.assertEqual(U.days_seen(a), ["2026-09-26", "2026-09-27"])

    def test_untrustworthy_timestamps(self):
        for ts in (None, "", "yesterday", 1790000000, "1899-01-01T00:00:00Z",
                   "2999-01-01T00:00:00Z", ["2026-09-27T00:00:00Z"]):
            with self.subTest(ts=ts):
                r = rec(input_tokens=1)
                r["timestamp"] = ts
                f = accept(r, day=lambda t: t[:10])
                self.assertIsNone(U.event_day(f))

    def test_trustworthy_timestamp_wins_over_missing(self):
        r1 = rec(input_tokens=1)
        r1["timestamp"] = None
        r2 = rec(input_tokens=1, ts="2026-09-27T10:00:00Z")
        f = accept(r1, r2, day=lambda t: t[:10])
        self.assertEqual(U.event_day(f), "2026-09-27")

    def test_fork_replay_fixture_merges_to_parent_maximum(self):
        parent = load("fork_replay/parent.jsonl")
        child = load("fork_replay/parent/subagents/agent-fxchild1.jsonl")
        rid = child[1]["requestId"]
        reps = [r for r in parent if r.get("requestId") == rid] + [child[1]]
        p = U.price(accept(*reps))
        final_out = max(r["message"]["usage"]["output_tokens"] for r in reps)
        self.assertEqual(p["out"], final_out)


class TestUsageBearing(unittest.TestCase):

    def test_detects_assistant_usage_lines_only(self):
        for r in load("advisor_iterations.jsonl"):
            self.assertTrue(U.usage_bearing(json.dumps(r).encode()))
        for r in load("nonusage_types.jsonl"):
            self.assertFalse(U.usage_bearing(json.dumps(r).encode()))

    def test_compact_and_spaced_json_forms(self):
        self.assertTrue(U.usage_bearing(b'{"type":"assistant","message":{"usage":{}}}'))
        self.assertTrue(U.usage_bearing(b'{"type": "assistant", "message": {"usage": {}}}'))

    def test_escaped_usage_in_content_is_not_usage(self):
        line = json.dumps({"type": "user", "message": {"content": '{"type":"assistant","usage":{}}'}})
        self.assertFalse(U.usage_bearing(line.encode()))


if __name__ == "__main__":
    unittest.main()
