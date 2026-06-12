# Shared test builders for the pruner suite. Bulky transcripts are generated
# here (into tempdirs by the callers) rather than checked in.
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


def _line(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def make_transcript(n_pairs=5, result_bytes=20000, trailing_newline=True,
                    final_assistant=True):
    """Build a realistic transcript: user prompt, then n_pairs of
    assistant(tool_use) / user(tool_result + toolUseResult), each result
    `result_bytes` of filler, optionally a final assistant text turn.
    Returns bytes."""
    big = "X" * result_bytes
    lines = [_line({"type": "user", "uuid": "u0", "parentUuid": None,
                    "sessionId": "s", "message": {"role": "user", "content": "go"}})]
    prev = "u0"
    for i in range(n_pairs):
        au, uu, tid = f"a{i}", f"ru{i}", f"toolu_{i}"
        lines.append(_line({
            "type": "assistant", "uuid": au, "parentUuid": prev, "requestId": f"r{i}",
            "sessionId": "s", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "reasoning " * 50, "signature": "sig"},
                {"type": "text", "text": "running tool"},
                {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "echo hi"}},
            ]}}))
        lines.append(_line({
            "type": "user", "uuid": uu, "parentUuid": au, "sessionId": "s",
            "toolUseResult": {"status": "ok", "exitCode": 0, "stdout": big, "prompt": big},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid,
                 "content": [{"type": "text", "text": big}]},
            ]}}))
        prev = uu
    if final_assistant:
        lines.append(_line({
            "type": "assistant", "uuid": "afinal", "parentUuid": prev, "requestId": "rf",
            "sessionId": "s", "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": "all done"}]}}))
    data = "\n".join(lines)
    if trailing_newline:
        data += "\n"
    return data.encode("utf-8")
