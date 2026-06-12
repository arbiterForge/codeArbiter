import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _prunelib as P  # noqa: E402
from _helpers import make_transcript  # noqa: E402


def to_bytes(objs):
    return ("\n".join(P._dumps(o) for o in objs) + "\n").encode("utf-8")


def asst(uuid, parent, blocks):
    return {"type": "assistant", "uuid": uuid, "parentUuid": parent,
            "requestId": "r" + uuid, "message": {"role": "assistant", "content": blocks}}


def user_result(uuid, parent, tool_id, content):
    return {"type": "user", "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": content}]}}


def prune(data, **cfgkw):
    cfg = P.Config(**cfgkw)
    lines = P.load_lines(data)
    idx = P.build_index(lines, cfg)
    report = P.apply_strategies(lines, idx, cfg)
    out = P.serialize(lines)
    return out, report, P.validate(data, out, lines, cfg)


class TestPhase23(unittest.TestCase):
    def test_reasoning_fold_removes_old_keeps_recent(self):
        data = make_transcript(n_pairs=4, result_bytes=2000)
        out, report, errs = prune(data, strategies=["reasoning-fold"], keep_recent=2)
        self.assertEqual(errs, [])
        self.assertGreater(report["reasoning-fold"]["lines"], 0)
        objs = P._parts_objs(out)
        thinking_by_uuid = {}
        for o in objs:
            if isinstance(o, dict) and o.get("type") == "assistant":
                blks = o["message"]["content"]
                thinking_by_uuid[o["uuid"]] = any(
                    isinstance(b, dict) and b.get("type") == "thinking" for b in blks)
        self.assertFalse(thinking_by_uuid["a0"], "old thinking should be folded")
        self.assertTrue(thinking_by_uuid["a3"], "recent thinking must be protected")

    def test_aged_result_condense_shrinks_to_head(self):
        data = make_transcript(n_pairs=4, result_bytes=5000)
        out, report, errs = prune(data, strategies=["aged-result-condense"], keep_recent=1)
        self.assertEqual(errs, [])
        self.assertGreater(report["aged-result-condense"]["bytes_before"]
                           - report["aged-result-condense"]["bytes_after"], 1000)
        self.assertLess(len(out), len(data))

    def test_mcp_payload_condense(self):
        big = {"query": "Z" * 4000, "n": 3, "flag": True}
        objs = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": "go"}},
            asst("a0", "u0", [{"type": "tool_use", "id": "t0",
                               "name": "mcp__github__search_code", "input": big}]),
            user_result("u1", "a0", "t0", "ok"),
            asst("afinal", "u1", [{"type": "text", "text": "done"}]),
        ]
        data = to_bytes(objs)
        out, report, errs = prune(data, strategies=["mcp-payload-condense"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertEqual(report["mcp-payload-condense"]["lines"], 1)
        o = next(o for o in P._parts_objs(out)
                 if isinstance(o, dict) and o.get("uuid") == "a0")
        inp = o["message"]["content"][0]["input"]
        self.assertIn("_ca_condensed", inp)
        self.assertEqual(inp.get("n"), 3)          # small scalar kept
        self.assertNotIn("query", inp)             # bulky dropped

    def test_shell_tail_keep_keeps_verdict(self):
        body = "\n".join(f"line {i}" for i in range(200)) + "\nEXIT 0"
        objs = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": "go"}},
            asst("a0", "u0", [{"type": "tool_use", "id": "t0", "name": "Bash",
                               "input": {"command": "run"}}]),
            user_result("u1", "a0", "t0", [{"type": "text", "text": body}]),
            asst("afinal", "u1", [{"type": "text", "text": "done"}]),
        ]
        data = to_bytes(objs)
        out, report, errs = prune(data, strategies=["shell-tail-keep"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertEqual(report["shell-tail-keep"]["lines"], 1)
        txt = next(o for o in P._parts_objs(out) if isinstance(o, dict)
                   and o.get("uuid") == "u1")["message"]["content"][0]["content"][0]["text"]
        self.assertIn("EXIT 0", txt)               # tail/verdict preserved
        self.assertIn(P.MARKER_PREFIX, txt)
        self.assertNotIn("line 0\n", txt)          # head dropped

    def test_superseded_read_only_when_later_edit_same_path(self):
        read_body = "OLD CONTENTS " * 50
        # Case A: a later Edit of the same path -> read result is superseded.
        objs_a = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": "go"}},
            asst("a0", "u0", [{"type": "tool_use", "id": "t0", "name": "Read",
                               "input": {"file_path": "/x.py"}}]),
            user_result("u1", "a0", "t0", [{"type": "text", "text": read_body}]),
            asst("a1", "u1", [{"type": "tool_use", "id": "t1", "name": "Edit",
                               "input": {"file_path": "/x.py"}}]),
            user_result("u2", "a1", "t1", "edited"),
            asst("afinal", "u2", [{"type": "text", "text": "done"}]),
        ]
        out, report, errs = prune(to_bytes(objs_a),
                                  strategies=["superseded-read-condense"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertEqual(report["superseded-read-condense"]["lines"], 1)

        # Case B: no later edit of that path -> read result left intact.
        objs_b = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": "go"}},
            asst("a0", "u0", [{"type": "tool_use", "id": "t0", "name": "Read",
                               "input": {"file_path": "/y.py"}}]),
            user_result("u1", "a0", "t0", [{"type": "text", "text": read_body}]),
            asst("afinal", "u1", [{"type": "text", "text": "done"}]),
        ]
        out_b, report_b, errs_b = prune(to_bytes(objs_b),
                                        strategies=["superseded-read-condense"], keep_recent=0)
        self.assertEqual(errs_b, [])
        self.assertEqual(report_b["superseded-read-condense"]["lines"], 0)

    def test_reminder_fold_keeps_first_occurrence(self):
        rem = "<system-reminder>Do the thing carefully and consistently.</system-reminder>" * 3
        objs = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": [{"type": "text", "text": rem}]}},
            asst("a0", "u0", [{"type": "text", "text": "ok"}]),
            {"type": "user", "uuid": "u1", "parentUuid": "a0",
             "message": {"role": "user", "content": [{"type": "text", "text": rem}]}},
            asst("a1", "u1", [{"type": "text", "text": "ok2"}]),
            {"type": "user", "uuid": "u2", "parentUuid": "a1",
             "message": {"role": "user", "content": [{"type": "text", "text": rem}]}},
            asst("afinal", "u2", [{"type": "text", "text": "done"}]),
        ]
        data = to_bytes(objs)
        out, report, errs = prune(data, strategies=["repeat-reminder-fold"], keep_recent=0)
        self.assertEqual(errs, [])
        objs2 = P._parts_objs(out)
        first = next(o for o in objs2 if isinstance(o, dict) and o.get("uuid") == "u0")
        self.assertNotIn(P.MARKER_PREFIX, first["message"]["content"][0]["text"])
        later = next(o for o in objs2 if isinstance(o, dict) and o.get("uuid") == "u1")
        self.assertIn(P.MARKER_PREFIX, later["message"]["content"][0]["text"])

    def test_inline_image_evict(self):
        objs = [
            {"type": "user", "uuid": "u0", "parentUuid": None,
             "message": {"role": "user", "content": [
                 {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                              "data": "A" * 5000}}]}},
            asst("a0", "u0", [{"type": "text", "text": "got it"}]),
            asst("afinal", "a0", [{"type": "text", "text": "done"}]),
        ]
        data = to_bytes(objs)
        out, report, errs = prune(data, strategies=["inline-image-evict"], keep_recent=0)
        self.assertEqual(errs, [])
        self.assertEqual(report["inline-image-evict"]["lines"], 1)
        o = next(o for o in P._parts_objs(out) if isinstance(o, dict) and o.get("uuid") == "u0")
        self.assertIn(P.MARKER_PREFIX, o["message"]["content"][0]["source"]["data"])

    def test_full_aggressive_validation_clean(self):
        data = make_transcript(n_pairs=8, result_bytes=30000)
        out, report, errs = prune(data, tier="aggressive", keep_recent=2, max_bytes=8192)
        self.assertEqual(errs, [])
        self.assertLess(len(out), len(data))


if __name__ == "__main__":
    unittest.main()
