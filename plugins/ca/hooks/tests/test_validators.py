import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import fixture, make_transcript  # noqa: E402


class TestValidators(unittest.TestCase):
    def test_preexisting_orphans_not_fatal(self):
        # The corrupt fixture has a GHOST parentUuid and an orphan tool_result,
        # but if we change nothing, validate must not invent new failures for
        # pre-existing irregularities.
        data = fixture("corrupt.jsonl")
        lines = P.load_lines(data)
        out = P.serialize(lines)  # untouched
        errs = P.validate(data, out, lines, P.Config())
        self.assertEqual([e for e in errs if e.startswith("v_chain")], [])

    def test_new_orphan_detected(self):
        data = make_transcript(n_pairs=2, result_bytes=100)
        lines = P.load_lines(data)
        # Maliciously break a parentUuid to simulate a buggy strategy.
        for ln in lines:
            if isinstance(ln.obj, dict) and ln.obj.get("uuid") == "afinal":
                ln.obj["parentUuid"] = "DOES-NOT-EXIST"
                ln.dirty = True
                break
        out = P.serialize(lines)
        errs = P.validate(data, out, lines, P.Config())
        self.assertTrue(any(e.startswith("v_chain") for e in errs))

    def test_unpaired_tool_result_detected_by_audit(self):
        data = fixture("corrupt.jsonl")
        results = P.audit(data)
        self.assertTrue(any(lvl in ("WARN",) and "tool_result" in msg
                            for lvl, msg in results))
        self.assertTrue(any(lvl == "FAIL" and "unparseable" in msg
                            for lvl, msg in results))

    def test_shrink_violation_detected(self):
        data = b'{"type":"a","uuid":"1","parentUuid":null}\n'
        lines = P.load_lines(data)
        bigger = data + data
        errs = P.validate(data, bigger, lines, P.Config())
        self.assertTrue(any(e.startswith("v_shrink") for e in errs))

    def test_linecount_violation_detected(self):
        data = b'{"type":"a","uuid":"1"}\n{"type":"b","uuid":"2"}\n'
        lines = P.load_lines(data)
        fewer = b'{"type":"a","uuid":"1"}\n'
        errs = P.validate(data, fewer, lines, P.Config())
        self.assertTrue(any(e.startswith("v_linecount") for e in errs))

    def test_identity_violation_on_untouched_line(self):
        data = make_transcript(n_pairs=1, result_bytes=50)
        lines = P.load_lines(data)
        # Tamper with the serialized output without marking dirty.
        out = P.serialize(lines)
        parts = out.split(b"\n")
        parts[0] = parts[0].replace(b'"go"', b'"GO!"')
        tampered = b"\n".join(parts)
        errs = P.validate(data, tampered, lines, P.Config())
        self.assertTrue(any(e.startswith("v_identity") for e in errs))


if __name__ == "__main__":
    unittest.main()
