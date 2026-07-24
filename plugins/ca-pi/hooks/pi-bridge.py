#!/usr/bin/env python3
"""Bounded one-request Pi codec for exactly one shared core entry."""

import base64
import binascii
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
import _arbiterstatelib  # noqa: E402
import _hooklib  # noqa: E402
import _ledgerlib  # noqa: E402
import _planfilelib  # noqa: E402
import _segmentslib  # noqa: E402
import _taskboardlib  # noqa: E402

MAX_REQUEST_BYTES = 262_144
MAX_PLAN_CONTENT_BYTES = 92_160
MAX_CAPTURE_CHARS = 1_048_576
ALLOWED_KEYS = frozenset({"version", "event", "cwd", "sessionId", "tool", "input", "result"})
EVENT_KEYS = {
    "session_start": (frozenset({"version", "event", "cwd"}), frozenset({"version", "event", "cwd", "sessionId"})),
    "before_agent_start": (frozenset({"version", "event", "cwd"}), frozenset({"version", "event", "cwd", "sessionId"})),
    "tool_call": (frozenset({"version", "event", "cwd", "tool", "input"}), frozenset({"version", "event", "cwd", "sessionId", "tool", "input"})),
    "tool_result": (frozenset({"version", "event", "cwd", "tool", "input", "result"}), frozenset({"version", "event", "cwd", "sessionId", "tool", "input", "result"})),
    "prune_plan": (frozenset({"version", "event", "cwd", "input"}), frozenset({"version", "event", "cwd", "input"})),
    "footer_usage_update": (frozenset({"version", "event", "cwd", "input"}), frozenset({"version", "event", "cwd", "input"})),
    "footer_status_snapshot": (frozenset({"version", "event", "cwd"}), frozenset({"version", "event", "cwd", "sessionId"})),
    "plan_file": (frozenset({"version", "event", "cwd", "input"}), frozenset({"version", "event", "cwd", "input"})),
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
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]?|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-_])")
FOOTER_USAGE_KEYS = frozenset({"sessionKey", "scanStart", "scanEnd", "facts"})
FOOTER_USAGE_RESULT_KEYS = frozenset({
    "status", "session", "today", "acceptedThrough", "highWater",
})
FOOTER_USAGE_TOTAL_KEYS = frozenset({
    "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens", "costUsd",
})
FOOTER_USAGE_STATUSES = frozenset({"ok", "invalid", "corrupt", "lock_failed", "write_failed"})
FOOTER_MAX_COUNT = 1_000_000
FOOTER_MAX_STAGE = 128
FOOTER_MAX_PRUNE = 256


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


def _footer_usage_totals(value):
    if not isinstance(value, dict) or set(value) != FOOTER_USAGE_TOTAL_KEYS:
        return None
    for key in FOOTER_USAGE_TOTAL_KEYS - {"costUsd"}:
        amount = value[key]
        if type(amount) is not int or not 0 <= amount <= _ledgerlib.PI_MAX_TOKENS:
            return None
    cost = value["costUsd"]
    if type(cost) not in (int, float) or not math.isfinite(cost) \
            or not 0 <= cost <= _ledgerlib.PI_MAX_COST_USD:
        return None
    return {
        "inputTokens": value["inputTokens"],
        "outputTokens": value["outputTokens"],
        "cacheReadTokens": value["cacheReadTokens"],
        "cacheWriteTokens": value["cacheWriteTokens"],
        "costUsd": round(float(cost), 9),
    }


def _footer_usage_result(value):
    if not isinstance(value, dict) or set(value) != FOOTER_USAGE_RESULT_KEYS \
            or value.get("status") not in FOOTER_USAGE_STATUSES:
        return None
    session = _footer_usage_totals(value.get("session"))
    today = _footer_usage_totals(value.get("today"))
    accepted_through = value.get("acceptedThrough")
    high_water = value.get("highWater")
    if session is None or today is None or type(accepted_through) is not int \
            or not -1 <= accepted_through <= _ledgerlib.PI_MAX_POSITION \
            or type(high_water) is not int \
            or not -1 <= high_water <= _ledgerlib.PI_MAX_POSITION:
        return None
    return {
        "status": value["status"],
        "session": session,
        "today": today,
        "acceptedThrough": accepted_through,
        "highWater": high_water,
    }


def _footer_usage_update(request):
    """Project-independent bounded crossing into the shared user-global ledger."""
    value = request.get("input")
    if not isinstance(value, dict) or set(value) != FOOTER_USAGE_KEYS:
        result = None
    else:
        try:
            result = _footer_usage_result(_ledgerlib.pi_ledger_update(
                value["sessionKey"], value["scanStart"], value["scanEnd"], value["facts"]
            ))
        except Exception:  # noqa: BLE001 - footer accounting is advisory and fail-soft
            result = None
    if result is None:
        blank = {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "costUsd": 0.0,
        }
        result = {
            "status": "corrupt",
            "session": dict(blank),
            "today": dict(blank),
            "acceptedThrough": -1,
            "highWater": -1,
        }
    return {
        "version": 1,
        "outcome": "notice",
        "auditCode": "PI_FOOTER_USAGE",
        "resultPatch": {"footerUsage": result},
    }


def _bounded_footer_text(value, maximum):
    if not isinstance(value, str):
        return None
    clean = ANSI_RE.sub("", value)
    clean = "".join(char for char in clean if ord(char) >= 32 and not 127 <= ord(char) <= 159)
    return "".join(list(clean)[:maximum]) or None


def _footer_status_snapshot(request):
    """Read the existing shared status sources after the TypeScript trust gate."""
    unavailable = {"version": 1, "outcome": "allow", "auditCode": "PI_FOOTER_STATUS_UNAVAILABLE"}
    try:
        state = _arbiterstatelib.arbiter_state(
            request["cwd"],
            _taskboardlib.count_in_flight,
            _taskboardlib.read_board,
            _hooklib.frontmatter_enabled,
        )
    except Exception:  # noqa: BLE001 - one unavailable segment never breaks the footer
        state = None
    if not isinstance(state, dict):
        return unavailable
    stage = _bounded_footer_text(state.get("stage"), FOOTER_MAX_STAGE)
    counts = (state.get("tasks"), state.get("q"), state.get("over"))
    sprint = state.get("sprint")
    if stage is None or any(type(value) is not int or not 0 <= value <= FOOTER_MAX_COUNT
                            for value in counts) or type(sprint) is not bool:
        return unavailable
    session_id = request.get("sessionId")
    prune = None
    if isinstance(session_id, str) and session_id:
        try:
            prune = _bounded_footer_text(_segmentslib.seg_prune({}, session_id), FOOTER_MAX_PRUNE)
        except Exception:  # noqa: BLE001 - prune is an independent optional segment
            prune = None
    try:
        dev = _arbiterstatelib.dev_active(request["cwd"])
    except Exception:  # noqa: BLE001 - dev is a fail-soft display fact
        return unavailable
    if type(dev) is not bool:
        return unavailable
    return {
        "version": 1,
        "outcome": "notice",
        "auditCode": "PI_FOOTER_STATUS",
        "resultPatch": {"footerStatus": {
            "status": "ok",
            "stage": stage,
            "tasks": counts[0],
            "questions": counts[1],
            "overrides": counts[2],
            "sprint": sprint,
            "dev": dev,
            "prune": prune,
        }},
    }


def _plan_file_request(value):
    if not isinstance(value, dict) or value.get("action") not in ("read", "replace"):
        raise ProtocolError("plan file input is invalid")
    if value["action"] == "read":
        if set(value) != {"slug", "kind", "action"}:
            raise ProtocolError("plan file input is invalid")
        return value
    if set(value) != {"slug", "kind", "action", "expectedHash", "contentBase64"}:
        raise ProtocolError("plan file input is invalid")
    encoded = value["contentBase64"]
    if not isinstance(encoded, str) or len(encoded) > ((MAX_PLAN_CONTENT_BYTES + 2) // 3) * 4:
        raise ProtocolError("plan file content is invalid")
    try:
        raw = encoded.encode("ascii", "strict")
        decoded = base64.b64decode(raw, validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ProtocolError("plan file content is invalid") from exc
    if base64.b64encode(decoded) != raw or len(decoded) > MAX_PLAN_CONTENT_BYTES:
        raise ProtocolError("plan file content is invalid")
    try:
        content = decoded.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ProtocolError("plan file content is invalid") from exc
    return {"slug": value.get("slug"), "kind": value.get("kind"), "action": "replace",
            "expectedHash": value.get("expectedHash"), "content": content}


def _plan_file_response(result):
    output = dict(result)
    if "content" in output:
        content = output.pop("content")
        if content is None:
            output["contentBase64"] = None
        elif isinstance(content, str):
            raw = content.encode("utf-8", "strict")
            if len(raw) > MAX_PLAN_CONTENT_BYTES:
                raise ProtocolError("plan file result is invalid")
            output["contentBase64"] = base64.b64encode(raw).decode("ascii")
        else:
            raise ProtocolError("plan file result is invalid")
    return output


def dispatch(request):
    if request["event"] == "plan_file":
        result = _planfilelib.plan_file_operation(request["cwd"], _plan_file_request(request["input"]))
        return {
            "version": 1,
            "outcome": "notice",
            "auditCode": "PI_PLAN_FILE",
            "resultPatch": {"planFile": _plan_file_response(result)},
        }
    if request["event"] == "footer_usage_update":
        return _footer_usage_update(request)
    if request["event"] == "footer_status_snapshot":
        return _footer_status_snapshot(request)
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
