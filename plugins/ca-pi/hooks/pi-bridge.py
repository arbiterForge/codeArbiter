#!/usr/bin/env python3
"""Bounded one-request Pi codec for exactly one shared core entry."""

import contextlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _host import PiHost  # noqa: E402
from _prunepolicy import PrunePolicy, SemanticEntry, plan_prune  # noqa: E402

MAX_REQUEST_BYTES = 262_144
MAX_CAPTURE_CHARS = 1_048_576
ALLOWED_KEYS = frozenset({"version", "event", "cwd", "sessionId", "tool", "input", "result"})
EVENT_KEYS = {
    "session_start": (frozenset({"version", "event", "cwd"}), frozenset({"version", "event", "cwd", "sessionId"})),
    "before_agent_start": (frozenset({"version", "event", "cwd"}), frozenset({"version", "event", "cwd", "sessionId"})),
    "tool_call": (frozenset({"version", "event", "cwd", "tool", "input"}), frozenset({"version", "event", "cwd", "sessionId", "tool", "input"})),
    "tool_result": (frozenset({"version", "event", "cwd", "tool", "input", "result"}), frozenset({"version", "event", "cwd", "sessionId", "tool", "input", "result"})),
    "prune_plan": (frozenset({"version", "event", "cwd", "input"}), frozenset({"version", "event", "cwd", "input"})),
}
ENTRY_BY_EVENT = {
    ("session_start", None): "session-start.py",
    ("tool_call", "EXEC"): "pre-bash.py",
    ("tool_call", "WRITE"): "pre-write.py",
    ("tool_call", "EDIT"): "pre-edit.py",
    ("tool_call", "READ"): "pre-read.py",
    ("tool_result", "WRITE"): "post-write-edit.py",
    ("tool_result", "EDIT"): "post-write-edit.py",
}
RULE_RE = re.compile(r"\[((?:H|PI)-[A-Za-z0-9]+)\]")


class ProtocolError(ValueError):
    pass


class BoundedText(io.TextIOBase):
    """Text writer that never retains more than its UTF-8 byte budget."""

    def __init__(self, max_bytes):
        self.max_bytes = max_bytes
        self.parts = []
        self.size = 0
        self.overflowed = False

    def writable(self):
        return True

    def write(self, value):
        if not isinstance(value, str):
            raise TypeError("text writer requires str")
        encoded = value.encode("utf-8", "replace")
        remaining = max(0, self.max_bytes - self.size)
        if remaining:
            self.parts.append(encoded[:remaining])
            self.size += min(len(encoded), remaining)
        if len(encoded) > remaining:
            self.overflowed = True
        return len(value)

    def flush(self):
        return None

    def getvalue(self):
        return b"".join(self.parts).decode("utf-8", "replace")


def _json_value(value, depth=0):
    if depth > 16:
        raise ProtocolError("JSON nesting exceeds limit")
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolError("JSON number is not finite")
        return
    if isinstance(value, list):
        if len(value) > 10_000:
            raise ProtocolError("JSON list exceeds limit")
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 1_000 or any(not isinstance(key, str) for key in value):
            raise ProtocolError("JSON object exceeds limit")
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ProtocolError("unsupported JSON value")


def _request(raw):
    def unique_object(pairs):
        output = {}
        for key, item in pairs:
            if key in output:
                raise ProtocolError("duplicate JSON object key")
            output[key] = item
        return output

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            parse_constant=lambda token: (_ for _ in ()).throw(ProtocolError(f"invalid JSON constant {token}")),
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("request is not one UTF-8 JSON object") from exc
    if not isinstance(value, dict) or set(value) - ALLOWED_KEYS:
        raise ProtocolError("request keys are invalid")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ProtocolError("request version is invalid")
    for key in ("event", "cwd"):
        if not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 32_768:
            raise ProtocolError(f"request {key} is invalid")
    schema = EVENT_KEYS.get(value["event"])
    if schema is None:
        raise ProtocolError("request event is invalid")
    required, allowed = schema
    if not required.issubset(value) or not set(value).issubset(allowed):
        raise ProtocolError("request shape is invalid for event")
    if not os.path.isabs(value["cwd"]) or not os.path.isdir(value["cwd"]):
        raise ProtocolError("request cwd is not an absolute directory")
    for key in ("sessionId", "tool"):
        if key in value and (not isinstance(value[key], str) or len(value[key]) > 1_024):
            raise ProtocolError(f"request {key} is invalid")
    for key in ("input", "result"):
        if key in value:
            if not isinstance(value[key], dict):
                raise ProtocolError(f"request {key} must be an object")
            _json_value(value[key])
    return value


def _load_entry(filename):
    path = os.path.realpath(os.path.join(HERE, filename))
    if os.path.commonpath((path, os.path.realpath(HERE))) != os.path.realpath(HERE):
        raise ProtocolError("entry escapes package")
    spec = importlib.util.spec_from_file_location("ca_pi_entry_" + uuid.uuid4().hex, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("shared entry cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "run", None)):
        raise RuntimeError("shared entry has no run seam")
    return module


def _payload(request, host):
    tool = request.get("tool", "")
    tool_input = request.get("input", {})
    if request["event"] == "tool_call" and host.normalize_tool(tool) == "READ":
        tool_input = host.normalize_tool_input(tool, tool_input)
    return {
        "cwd": request["cwd"],
        "session_id": request.get("sessionId", ""),
        "hook_event_name": request["event"],
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_response": request.get("result", {}),
    }


def _run_entry(request, filename, host):
    module = _load_entry(filename)
    stdin = io.StringIO(json.dumps(_payload(request, host), ensure_ascii=False))
    stdout = BoundedText(MAX_CAPTURE_CHARS)
    stderr = BoundedText(MAX_CAPTURE_CHARS)
    previous = sys.stdin
    code = 0
    try:
        sys.stdin = stdin
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                result = module.run(host)
                code = int(result or 0)
            except SystemExit as exc:
                code = int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 1
    finally:
        sys.stdin = previous
    out = stdout.getvalue()
    err = stderr.getvalue()
    if stdout.overflowed or stderr.overflowed:
        raise RuntimeError("shared entry output overflow")
    return code, out, err


def _rule(text):
    match = RULE_RE.search(text)
    return match.group(1) if match else None


def _prune_plan(request):
    value = request.get("input")
    if not isinstance(value, dict) or set(value) != {"entries", "policy"}:
        raise ProtocolError("prune plan input is invalid")
    rows, raw_policy = value["entries"], value["policy"]
    if not isinstance(rows, list) or not rows or len(rows) > 10_000:
        raise ProtocolError("prune plan entries are invalid")
    if not isinstance(raw_policy, dict) or set(raw_policy) != {"tier", "keepRecent", "maxBytes"}:
        raise ProtocolError("prune policy is invalid")
    tier = raw_policy["tier"]
    keep_recent = raw_policy["keepRecent"]
    max_bytes = raw_policy["maxBytes"]
    if tier not in ("gentle", "standard", "aggressive") \
            or type(keep_recent) is not int or not 0 <= keep_recent <= 1000 \
            or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_REQUEST_BYTES:
        raise ProtocolError("prune policy is invalid")
    entries = []
    entry_ids = set()
    expected = {"id", "ordinal", "role", "kind", "byteSize", "toolBearing", "marked"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected:
            raise ProtocolError("semantic entry is invalid")
        if not isinstance(row["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,1023}", row["id"]) \
                or row["id"] in entry_ids \
                or type(row["ordinal"]) is not int or row["ordinal"] != len(entries) \
                or row["role"] not in ("user", "assistant", "tool", "system", "other") \
                or row["kind"] not in ("message", "tool-result", "compaction", "metadata") \
                or type(row["byteSize"]) is not int or not 0 <= row["byteSize"] <= MAX_REQUEST_BYTES \
                or type(row["toolBearing"]) is not bool or type(row["marked"]) is not bool:
            raise ProtocolError("semantic entry is invalid")
        entry_ids.add(row["id"])
        entries.append(SemanticEntry(
            id=row["id"], ordinal=row["ordinal"], role=row["role"], kind=row["kind"],
            byte_size=row["byteSize"], tool_bearing=row["toolBearing"], marked=row["marked"],
        ))
    plan = plan_prune(entries, PrunePolicy(
        tier=tier, keep_recent=keep_recent, max_bytes=max_bytes,
    ))
    if plan.first_kept_id is None:
        raise ProtocolError("prune plan has no kept boundary")
    return {
        "version": 1,
        "outcome": "notice",
        "auditCode": "PI_PRUNE_PLAN",
        "resultPatch": {"prunePlan": {
            "firstKeptEntryId": plan.first_kept_id,
            "protectedIds": list(plan.protected_ids),
            "actions": [{"entryId": entry_id, "action": action}
                        for entry_id, action in plan.actions],
            "metrics": {
                "entriesBefore": plan.metrics["entries_before"],
                "candidateEntries": plan.metrics["candidate_entries"],
                "protectedEntries": plan.metrics["protected_entries"],
                "markedCandidates": plan.metrics["marked_candidates"],
            },
            "auditCodes": list(plan.audit_codes),
            "fingerprint": plan.fingerprint,
        }},
    }


def dispatch(request):
    if request["event"] == "prune_plan":
        return _prune_plan(request)
    host = PiHost(request["cwd"])
    category = host.normalize_tool(request.get("tool", ""))
    if request["event"] == "tool_call" and category == "OTHER":
        return {
            "version": 1,
            "outcome": "block",
            "ruleId": "PI-UNKNOWN",
            "message": "Unknown Pi tool is potentially mutating and is blocked; classify it or run /ca-doctor.",
            "auditCode": "PI_UNKNOWN_BLOCK",
        }
    filename = ENTRY_BY_EVENT.get((request["event"], category))
    if filename is None:
        filename = ENTRY_BY_EVENT.get((request["event"], None))
    if filename is None:
        return {"version": 1, "outcome": "allow", "auditCode": "PI_NO_ROUTE"}
    code, stdout, stderr = _run_entry(request, filename, host)
    if code == 2:
        message = stderr.strip() or "shared core blocked the operation"
        response = {"version": 1, "outcome": "block", "message": message, "auditCode": "PI_CORE_BLOCK"}
        rule = _rule(message)
        if rule:
            response["ruleId"] = rule
        return response
    if code != 0:
        raise RuntimeError(stderr.strip() or f"shared entry exited {code}")
    if request["event"] == "tool_call" and category == "READ" and stdout.strip():
        try:
            hook_output = json.loads(stdout)
            context = hook_output["hookSpecificOutput"]["additionalContext"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("shared read output is malformed") from exc
        return {"version": 1, "outcome": "notice", "context": context, "auditCode": "PI_CORE_NOTICE"}
    message = stderr.strip()
    if message:
        response = {"version": 1, "outcome": "notice", "message": message, "auditCode": "PI_CORE_NOTICE"}
        rule = _rule(message)
        if rule:
            response["ruleId"] = rule
        return response
    if stdout:
        return {"version": 1, "outcome": "notice", "context": stdout, "auditCode": "PI_CORE_CONTEXT"}
    return {"version": 1, "outcome": "allow", "auditCode": "PI_CORE_ALLOW"}


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise ProtocolError("request overflow")
    response = dispatch(_request(raw))
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # transport reports only a fixed class, never request data
        sys.stderr.write(f"PI bridge error ({type(exc).__name__})\n")
        sys.exit(1)
