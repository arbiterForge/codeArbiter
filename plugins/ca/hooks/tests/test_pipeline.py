import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import fixture, make_transcript  # noqa: E402


class TestPipeline(unittest.TestCase):
    def test_roundtrip_no_strategies_byte_identical(self):
        data = fixture("synthetic-small.jsonl")
        lines = P.load_lines(data)
        self.assertEqual(P.serialize(lines), data)

    def test_roundtrip_unknown_types_untouched(self):
        # The fixture contains a "future-thing" line and oddly-spaced JSON; with
        # strategies applied, those clean lines must remain byte-identical.
        data = fixture("synthetic-small.jsonl")
        cfg = P.Config(tier="gentle", keep_recent=0, max_bytes=40)
        lines = P.load_lines(data)
        idx = P.build_index(lines, cfg)
        P.apply_strategies(lines, idx, cfg)
        out = P.serialize(lines).split(b"\n")
        orig = data.split(b"\n")
        for i, ln in enumerate(lines):
            if not ln.dirty:
                self.assertEqual(out[i], orig[i], f"clean line {i} drifted")

    def test_partial_trailing_line_preserved(self):
        # No trailing newline: the final non-empty line must survive verbatim.
        data = make_transcript(n_pairs=2, result_bytes=100, trailing_newline=False)
        self.assertFalse(data.endswith(b"\n"))
        lines = P.load_lines(data)
        self.assertEqual(P.serialize(lines), data)

    def test_trailing_newline_preserved(self):
        data = make_transcript(n_pairs=2, result_bytes=100, trailing_newline=True)
        self.assertTrue(data.endswith(b"\n"))
        lines = P.load_lines(data)
        self.assertEqual(P.serialize(lines), data)

    def test_bom_and_nonascii_preserved(self):
        body = '{"type":"summary","uuid":"x","parentUuid":null,"text":"café — 日本語 ✂"}'
        data = P.BOM + body.encode("utf-8") + b"\n"
        lines = P.load_lines(data)
        self.assertTrue(lines[0].bom)
        self.assertEqual(lines[0].obj.get("text"), "café — 日本語 ✂")
        self.assertEqual(P.serialize(lines), data)

    def test_blank_interior_line_preserved(self):
        data = b'{"type":"a","uuid":"1"}\n\n{"type":"b","uuid":"2"}\n'
        lines = P.load_lines(data)
        self.assertIsNone(lines[1].obj)
        self.assertEqual(P.serialize(lines), data)

    def test_idempotent(self):
        data = make_transcript(n_pairs=4, result_bytes=20000)
        cfg = P.Config(tier="gentle", keep_recent=1, max_bytes=8192)

        def prune_once(d):
            lines = P.load_lines(d)
            idx = P.build_index(lines, cfg)
            P.apply_strategies(lines, idx, cfg)
            return P.serialize(lines)
        once = prune_once(data)
        twice = prune_once(once)
        self.assertEqual(once, twice, "second prune changed already-pruned output")


if __name__ == "__main__":
    unittest.main()
