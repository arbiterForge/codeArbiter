"""Selected legacy-board work adapter.

The Markdown board remains the only writer in this mode. Its existing
origin correlation key supplies a portable, title-independent work ID.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import secrets

import _taskboardlib as board
import taskwrite

_WORK_ID = re.compile(r"WORK-[A-F0-9]{32}\Z")
_BOARD_MAX = 1 << 20
_ARCHIVE_MAX = 16 << 20


class LegacyWorkError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class LegacyClient:
    legacy = True
    def __init__(self, root):
        self.root = root

    def call(self, operation, request):
        return dispatch(self.root, operation, request)


def _source(origin, operation_id):
    if origin is not None and not isinstance(origin, str):
        raise ValueError("legacy work origin must be text")
    value = origin if origin else "work-op:" + operation_id
    if not value.strip() or len(value) > 256 or re.search(r"[\r\n()]", value):
        raise ValueError("legacy work origin must be a single line without parentheses (max 256 characters)")
    return value


def _id(source):
    digest = hashlib.sha256(("codearbiter-legacy-work-v1\0" + source).encode("utf-8")).hexdigest()
    return "WORK-" + digest[:32].upper()


def _title(task, source):
    # parse_board intentionally removes every "(from ...)" phrase for legacy
    # consumers. Work reads must remove only the writer's final marker.
    body = re.sub(r"^- (?:\[[ xX~]\]\s*)?", "", task.raw)
    if task.id:
        body = body[len(task.id):].lstrip()
        body = re.sub(r"^[—–-]+\s*", "", body)
    body = re.sub(r"\s*\((?:started|done)\s+[^)]*\)\s*$", "", body)
    return body.removesuffix(f"(from {source})").strip()


def _read_bounded(path, limit, *, optional=False):
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
    except FileNotFoundError:
        if optional:
            return ""
        raise ValueError(f"legacy work owner is missing {path.name}") from None
    if len(raw) > limit:
        raise ValueError(f"legacy {path.name} exceeds its bounded read limit")
    return raw.decode("utf-8")


def _scan(root):
    base = Path(root) / ".codearbiter"
    open_text = _read_bounded(base / "open-tasks.md", _BOARD_MAX)
    archive_text = _read_bounded(base / "done-tasks.md", _ARCHIVE_MAX,
                                 optional=True)
    found = {}
    seen_sources = {}
    seen_operations = {}
    unkeyed = 0
    for text, archived in ((open_text, False), (archive_text, True)):
        lines = text.splitlines()
        for task in board.parse_board(text):
            source = board.origin_for_task(lines, task)
            if source is None:
                unkeyed += 1  # selected adoption, never a guessed title key
                continue
            fields = {}
            for line in lines[task.lineno:]:
                if line.startswith("- ") or (line and not line[:1].isspace()):
                    break
                field = re.fullmatch(r"  - (Work origin|Work type|Work ID|Work operation ID|Spec ID|Plan ID): (.*)", line)
                if field:
                    if field.group(1) in fields:
                        raise ValueError(f"duplicate legacy {field.group(1)} metadata")
                    fields[field.group(1)] = field.group(2)
            operation_id = fields.get("Work operation ID")
            if operation_id:
                prior_source = seen_operations.setdefault(operation_id, source)
                if prior_source != source:
                    raise ValueError("legacy work operation ID belongs to multiple origins")
            work_id = fields.get("Work ID") or _id(source)
            if _WORK_ID.fullmatch(work_id) is None:
                raise ValueError(f"invalid legacy work ID for origin {source!r}")
            prior_id = seen_sources.setdefault(source, work_id)
            if prior_id != work_id:
                raise ValueError(f"duplicate legacy work origin {source!r}")
            record = {
                "work_id": work_id, "owner": "legacy", "origin": source,
                "title": _title(task, source),
                "intent": task.desc, "work_type": fields.get("Work type"),
                "spec_id": fields.get("Spec ID"), "plan_id": fields.get("Plan ID"),
                "state": "archived" if archived else {
                    "queued": "queued", "in_progress": "active", "done": "complete",
                }.get(task.state, task.state),
                "check_status": "unknown", "legacy_id": task.id,
                "started_at": task.started.isoformat() if task.started else None,
                "completed_at": task.done.isoformat() if task.done else None,
            }
            bounds = board.task_block(lines, task)
            if bounds is None:
                raise ValueError("legacy work block is not selectable")
            physical = "\n".join(lines[bounds[0]:bounds[1]])
            record["board_sha256"] = hashlib.sha256(
                (("archive" if archived else "open") + "\0" + physical).encode("utf-8")
            ).hexdigest()
            previous = found.get(work_id)
            if previous is not None:
                # Archive writes the done copy first. An identical board copy
                # may remain after a crash; report that state without inventing
                # a second item or choosing between distinct rows.
                if (archived and previous["state"] == "complete"
                        and all(previous[key] == record[key] for key in
                                ("title", "intent", "work_type", "spec_id", "plan_id", "origin"))):
                    previous["archive_pending"] = True
                    continue
                raise ValueError(f"duplicate legacy work origin {source!r}")
            found[work_id] = record
    return found, unkeyed


def _records(root):
    return _scan(root)[0]


def dispatch(root, operation, request):
    fields = {
        "work-create": {"operation_id", "title", "intent", "work_type",
                        "origin", "spec_id", "plan_id"},
        "work-get": {"work_id"},
        "work-context": {"work_id", "budget"},
        "work-list": {"offset", "limit", "budget", "membership_sha256"},
        "work-update": {"operation_id", "work_id", "expected_board_sha256", "action"},
    }.get(operation)
    if fields is None:
        raise ValueError(f"{operation} is not yet supported by the legacy board adapter")
    if type(request) is not dict:
        raise ValueError("legacy work request must be an object")
    unknown = set(request) - fields
    if unknown:
        raise ValueError(f"unknown legacy work request field: {sorted(unknown)[0]}")
    if operation == "work-create":
        _records(root)  # refuse malformed/unreadable prior state before the board writer runs
        origin = request.get("origin")
        operation_id = request.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("legacy work create needs a stable operation_id")
        source = _source(origin, operation_id)
        if not isinstance(request.get("title"), str) or not isinstance(request.get("intent"), str):
            raise ValueError("legacy work create needs title and intent")
        if request.get("work_type") not in ("feature", "fix", "chore", "spike", "unknown"):
            raise ValueError("legacy work create needs a supported work_type")
        for field in ("spec_id", "plan_id"):
            if request.get(field) is not None and not isinstance(request[field], str):
                raise ValueError(f"{field} must be one artifact ID")
        args = ["add", request["title"], "--from", source, "--desc", request["intent"],
                "--work-type", request["work_type"],
                "--work-id", "WORK-" + secrets.token_hex(16).upper(),
                "--work-operation-id", operation_id]
        for field, flag in (("spec_id", "--spec-id"), ("plan_id", "--plan-id")):
            if request.get(field) is not None:
                args.extend((flag, request[field]))
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = taskwrite.main(args, root=root)
        if code != 0:
            raise ValueError(errors.getvalue().strip() or "legacy board write failed")
        record = next((item for item in _records(root).values()
                       if item["origin"] == source), None)
        if record is None:
            raise ValueError("legacy board write did not yield its work origin")
        record["reused"] = output.getvalue().startswith("already promoted:")
        record["input_differs"] = any((
            record["title"] != request["title"],
            record["intent"] != request["intent"],
            record["work_type"] != request["work_type"],
            record["spec_id"] != request.get("spec_id"),
            record["plan_id"] != request.get("plan_id"),
        ))
        return record
    if operation == "work-get":
        work_id = request.get("work_id")
        if not isinstance(work_id, str) or _WORK_ID.fullmatch(work_id) is None:
            raise ValueError("invalid work ID")
        record = _records(root).get(work_id)
        if record is None:
            raise ValueError(f"unknown legacy work ID {work_id}")
        return record
    if operation == "work-context":
        budget = request.get("budget", 16384)
        if type(budget) is not int or not 1024 <= budget <= 65536:
            raise ValueError("invalid legacy work context budget")
        record = dispatch(root, "work-get", {"work_id": request.get("work_id")})
        result = {"work": record, "context_complete": False,
                  "omitted": ["legacy board stores only selected work; attached documents require exact artifact reads"]}
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) + 512 > budget:
            raise LegacyWorkError("RESPONSE_TOO_LARGE", "selected legacy work context exceeds budget")
        return result
    if operation == "work-list":
        offset, limit, budget = (request.get("offset", 0), request.get("limit", 32),
                                 request.get("budget", 16384))
        if (type(offset) is not int or offset < 0 or type(limit) is not int
                or not 1 <= limit <= 64 or type(budget) is not int
                or not 1024 <= budget <= 65536):
            raise ValueError("invalid legacy work listing bounds")
        records, unkeyed = _scan(root)
        ids = sorted(records)
        digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()
        if offset > len(ids):
            raise ValueError("legacy work offset is outside the listing")
        if offset and request.get("membership_sha256") != digest:
            raise ValueError("legacy work membership changed during listing")
        result = {"owner": "legacy", "membership_sha256": digest, "entries": [],
                  "offset": offset, "total": len(ids), "next_offset": None,
                  "unkeyed_count": unkeyed, "content_snapshot": False}
        for work_id in ids[offset:offset + limit]:
            entry = records[work_id]
            selected = {key: entry.get(key) for key in
                        ("work_id", "title", "work_type", "state", "check_status",
                         "spec_id", "plan_id", "legacy_id", "origin")}
            candidate = result["entries"] + [selected]
            if len(json.dumps({**result, "entries": candidate}).encode("utf-8")) + 512 > budget:
                if not result["entries"]:
                    raise ValueError("one legacy work entry exceeds the response budget")
                break
            result["entries"] = candidate
        next_offset = offset + len(result["entries"])
        result["next_offset"] = next_offset if next_offset < len(ids) else None
        return result
    if operation == "work-update":
        action = request.get("action")
        if action not in ("start", "complete", "archive"):
            raise ValueError("legacy work update supports start, complete and archive")
        if (not isinstance(request.get("operation_id"), str)
                or not request["operation_id"].strip()):
            raise ValueError("legacy work update needs a stable operation_id")
        expected = request.get("expected_board_sha256")
        if not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None:
            raise ValueError("legacy work update needs an expected board SHA-256")
        current = dispatch(root, "work-get", {"work_id": request.get("work_id")})
        args = [("done" if action == "complete" else action),
                current["work_id"], "--from", current["origin"]]
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = taskwrite.main(args, root=root, expected_work_id=current["work_id"],
                                  expected_board_sha256=expected)
        if code != 0:
            message = errors.getvalue().strip() or "legacy board update failed"
            if message.startswith("legacy work revision conflict:"):
                raise LegacyWorkError("REVISION_CONFLICT", message)
            raise ValueError(message)
        changed = dispatch(root, "work-get", {"work_id": current["work_id"]})
        changed["operation_id"] = request["operation_id"]
        return changed
    raise ValueError(f"{operation} is not yet supported by the legacy board adapter")
