import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import fixture, make_transcript  # noqa: E402


def prune(data, **cfgkw):
    cfg = P.Config(**cfgkw)
    lines = P.load_lines(data)
    idx = P.build_index(lines, cfg)
    report = P.apply_strategies(lines, idx, cfg)
    out = P.serialize(lines)
    errs = P.validate(data, out, lines, cfg)
    return out, report, errs


class TestStrategies(unittest.TestCase):
    def test_sidecar_collapse_shrinks_and_keeps_scalars(self):
        data = fixture("synthetic-small.jsonl")
        out, report, errs = prune(data, strategies=["sidecar-collapse"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertGreater(report["sidecar-collapse"]["lines"], 0)
        self.assertEqual(report["sidecar-collapse"]["metric_scope"], "file-only")
        # The condensed sidecar keeps small scalars and drops bulk.
        objs = P._parts_objs(out)
        u2 = next(o for o in objs if isinstance(o, dict) and o.get("uuid") == "u2")
        tur = u2["toolUseResult"]
        self.assertIn("_ca_condensed", tur)
        self.assertEqual(tur.get("status"), "ok")
        self.assertEqual(tur.get("exitCode"), 0)
        self.assertNotIn("prompt", tur)  # bulky string dropped
        self.assertLess(len(out), len(data))

    def test_sidecar_net_negative_eligibility_is_unchanged_for_unicode(self):
        data = (
            '{"type":"user","uuid":"u1","parentUuid":null,'
            '"toolUseResult":"' + ("😀" * 20) + '",'
            '"message":{"role":"user","content":"x"}}\n'
        ).encode("utf-8")
        out, report, errs = prune(
            data, strategies=["sidecar-collapse"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertEqual(out, data)
        self.assertEqual(report["sidecar-collapse"]["lines"], 0)

    def test_oversize_result_clamp_truncates_list_text(self):
        data = fixture("synthetic-small.jsonl")
        out, report, errs = prune(data, strategies=["oversize-result-clamp"],
                                  keep_recent=0, max_bytes=40)
        self.assertEqual(errs, [])
        self.assertGreater(report["oversize-result-clamp"]["lines"], 0)
        self.assertEqual(report["oversize-result-clamp"]["metric_scope"], "context")
        objs = P._parts_objs(out)
        u2 = next(o for o in objs if isinstance(o, dict) and o.get("uuid") == "u2")
        text = u2["message"]["content"][0]["content"][0]["text"]
        self.assertIn(P.MARKER_PREFIX, text)

    def test_protected_tail_untouched(self):
        # With a generous keep_recent, recent tool pairs are protected: nothing
        # prunes on a transcript whose only tool pairs are recent.
        data = make_transcript(n_pairs=2, result_bytes=20000)
        out, report, errs = prune(data, tier="gentle", keep_recent=10, max_bytes=8192)
        self.assertEqual(errs, [])
        self.assertEqual(out, data, "protected-tail pairs were modified")

    def test_old_pairs_pruned_recent_kept(self):
        data = make_transcript(n_pairs=6, result_bytes=20000)
        out, report, errs = prune(data, tier="gentle", keep_recent=2, max_bytes=8192)
        self.assertEqual(errs, [])
        self.assertLess(len(out), len(data))
        # The most recent tool_result text must still be full-size (unmarked).
        objs = P._parts_objs(out)
        last_tr = [o for o in objs if isinstance(o, dict)
                   and any(isinstance(b, dict) and b.get("type") == "tool_result"
                           for b in (o.get("message", {}) or {}).get("content", []) or [])][-1]
        txt = last_tr["message"]["content"][0]["content"][0]["text"]
        self.assertNotIn(P.MARKER_PREFIX, txt)

    def test_keep_recent_counts_turns_not_lines(self):
        # KEEP_RECENT's contract is TURNS: keep_recent=2 protects the 2 most
        # recent tool turns — each an assistant tool_use line PLUS its
        # tool_result line. Counting raw tool-bearing lines would protect only
        # 1 turn here (a silent 2x deviation an operator can't see).
        data = make_transcript(n_pairs=6, result_bytes=20000)
        out, report, errs = prune(data, tier="gentle", keep_recent=2, max_bytes=8192)
        self.assertEqual(errs, [])
        objs = P._parts_objs(out)

        def result_text(uuid):
            o = next(o for o in objs if isinstance(o, dict) and o.get("uuid") == uuid)
            return o["message"]["content"][0]["content"][0]["text"]
        # Pairs 4 and 5 are the two most recent turns: results stay full-size.
        self.assertNotIn(P.MARKER_PREFIX, result_text("ru4"))
        self.assertNotIn(P.MARKER_PREFIX, result_text("ru5"))
        # Pair 3 is the third most recent: pruned.
        self.assertIn(P.MARKER_PREFIX, result_text("ru3"))

    def test_no_strategy_grows_a_line(self):
        # Net-negative guard: tiny content is never enlarged by a marker.
        data = (b'{"type":"user","uuid":"u1","parentUuid":null,"toolUseResult":{"status":"ok"},'
                b'"message":{"role":"user","content":[{"type":"tool_result",'
                b'"tool_use_id":"toolu_1","content":"x"}]}}\n'
                b'{"type":"assistant","uuid":"a1","parentUuid":"u1",'
                b'"message":{"role":"assistant","content":[{"type":"tool_use",'
                b'"id":"toolu_1","name":"Bash","input":{}}]}}\n')
        out, report, errs = prune(data, tier="gentle", keep_recent=0, max_bytes=1)
        self.assertEqual(errs, [])
        self.assertEqual(out, data, "a strategy grew an already-tiny line")

    def test_validation_clean_on_full_gentle_prune(self):
        data = make_transcript(n_pairs=8, result_bytes=30000)
        out, report, errs = prune(data, tier="gentle", keep_recent=2, max_bytes=8192)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
