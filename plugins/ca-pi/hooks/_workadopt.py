"""Read-only inventory for an explicitly selected legacy work cutover.

The board remains authoritative until a later native transaction publishes all
work records and snapshots and removes the board. Preview never mutates it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

import _taskboardlib as board
import _worklib
from _hooklib import acquire_lock, release_lock


_ORIGIN = re.compile(r"[A-Za-z][A-Za-z0-9:._-]{0,127}#[A-Za-z0-9][A-Za-z0-9:._-]{0,127}\Z")
_ID = re.compile(r"WORK-[A-F0-9]{32}\Z")
_META = re.compile(r"  - (Work origin|Work type|Work ID|Work operation ID|Spec ID|Plan ID): (.*)\Z")


def _source_name(location):
    return ".codearbiter/done-tasks.md" if location == "archive" else ".codearbiter/open-tasks.md"


def _row_origin(block):
    """Return a portable correlation key for one exact physical source row."""
    return "legacy:row#" + hashlib.sha256(block.encode("utf-8")).hexdigest()[:32]


def _fit_title_and_intent(title, description, location, line):
    full_title = title
    if len(title) > 240:
        title = title[:240]
    intent = description or (full_title if len(full_title) > 240 else title)
    if not title or not intent or len(intent) > 4000:
        raise ValueError(
            f"{_source_name(location)} line {line}: title or description cannot fit "
            "the native 240/4,000 character limits"
        )
    return title, intent


def _read(path, limit, *, optional=False):
    if path.is_symlink():
        raise ValueError(f"linked legacy {path.name} cannot be adopted")
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
    except FileNotFoundError:
        if optional:
            return None
        raise ValueError(f"legacy work owner {path.name} is absent") from None
    if len(raw) > limit:
        raise ValueError(f"legacy {path.name} exceeds its adoption read limit")
    try:
        return raw, raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"legacy {path.name} is not UTF-8") from exc


def _rows(text, location):
    lines = text.splitlines()
    inventory_text = board.task_rows_text(text, strict=True)
    warnings = board.lint_board(inventory_text)
    if warnings:
        raise ValueError("malformed or duplicate legacy task: " + warnings[0])
    tasks = board.parse_board(inventory_text)
    if len(tasks) != sum(line.startswith("- ") for line in inventory_text.splitlines()):
        raise ValueError("legacy board has an unaccounted task row")
    result = []
    seen_blocks = set()
    for task in tasks:
        bounds = board.task_block(lines, task)
        if bounds is None or bounds[0] != task.lineno - 1:
            raise ValueError("legacy task block is not selectable")
        block = "\n".join(lines[bounds[0]:bounds[1]])
        if block in seen_blocks:
            raise ValueError(
                f"{_source_name(location)} line {task.lineno}: duplicate exact legacy task block"
            )
        seen_blocks.add(block)
        metadata = {}
        for line in lines[bounds[0] + 1:bounds[1]]:
            if line.startswith("  - Work ") or line.startswith("  - Spec ID:") or line.startswith("  - Plan ID:"):
                match = _META.fullmatch(line)
                if match is None or match.group(1) in metadata:
                    raise ValueError("unsupported or duplicate legacy work metadata")
                metadata[match.group(1)] = match.group(2)
        legacy_origin = board.origin_for_task(lines, task)
        if metadata.get("Work origin") and metadata["Work origin"] != legacy_origin:
            raise ValueError("legacy origin metadata disagrees with the task row")
        if legacy_origin and _ORIGIN.fullmatch(legacy_origin):
            origin = legacy_origin
        elif legacy_origin:
            origin = "legacy:origin#" + hashlib.sha256(legacy_origin.encode("utf-8")).hexdigest()[:32]
        else:
            origin = _row_origin(block)
        # Preserve IDs already exposed by the legacy adapter, even when the
        # historical source does not fit the native origin grammar.
        work_id = metadata.get("Work ID") or _worklib._id(legacy_origin or origin)
        if _ID.fullmatch(work_id) is None:
            raise ValueError("invalid legacy work ID")
        alias = task.id
        title = _worklib._title(task, legacy_origin) if legacy_origin else task.title
        title, intent = _fit_title_and_intent(title, task.desc, location, task.lineno)
        work_type = metadata.get("Work type") or "unknown"
        if work_type not in {"feature", "fix", "chore", "spike", "unknown"}:
            raise ValueError(f"{_source_name(location)} line {task.lineno}: invalid legacy work type")
        result.append({
            "location": location,
            "work_id": work_id, "origin": origin, "legacy_origin": legacy_origin,
            "alias": alias, "title": title, "intent": intent, "work_type": work_type,
            "state": "archived" if location == "archive" else {
                "queued": "queued", "in_progress": "active", "done": "complete"}[task.state],
            "started_at": task.started.isoformat() if task.started else None,
            "completed_at": task.done.isoformat() if task.done else None,
            "line": task.lineno, "block_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
            "spec_id": metadata.get("Spec ID"), "plan_id": metadata.get("Plan ID"),
            "_block": block, "_explicit_work_id": "Work ID" in metadata,
        })
    return result


def _same_archive_copy(open_row, archive_row):
    return (open_row["state"] == "complete" and archive_row["state"] == "archived"
            and open_row["_block"] == archive_row["_block"])


def _coalesce_archive_copies(open_rows, archive_rows):
    """Prefer the archived pointer for an exact copy left in open after a crash."""
    rows = list(open_rows)
    coalesced = 0
    for archive_row in archive_rows:
        match = next((index for index, open_row in enumerate(rows)
                      if open_row["location"] == "open"
                      and _same_archive_copy(open_row, archive_row)), None)
        if match is None:
            rows.append(archive_row)
        else:
            rows[match] = archive_row
            coalesced += 1
    return rows, coalesced


def _normalize_row_identities(rows):
    shared = {}
    for row in rows:
        if row["legacy_origin"]:
            shared[row["legacy_origin"]] = shared.get(row["legacy_origin"], 0) + 1
    for row in rows:
        if row["legacy_origin"] and shared[row["legacy_origin"]] > 1:
            row["origin"] = _row_origin(row["_block"])
            if not row["_explicit_work_id"]:
                row["work_id"] = _worklib._id(row["origin"])
        del row["_block"]
        del row["_explicit_work_id"]
    return rows


def _inventory(root, *, snapshot=False):
    """Read board or saved snapshot bytes; caller serializes live-board reads."""
    base = Path(root) / ".codearbiter"
    if not snapshot:
        work = base / "work"
        if work.is_symlink() or (work.exists() and any(work.iterdir())):
            raise ValueError("native work owner already exists; preserve it for inspection")
    source = base / "legacy" if snapshot else base
    active = _read(source / "open-tasks.md", 1 << 20)
    archive = _read(source / "done-tasks.md", 8 << 20, optional=True)
    open_rows = _rows(active[1], "open")
    archive_rows = _rows(archive[1], "archive") if archive else []
    source_row_count = len(open_rows) + len(archive_rows)
    rows, coalesced = _coalesce_archive_copies(open_rows, archive_rows)
    rows = _normalize_row_identities(rows)
    if len(rows) > 507:
        raise ValueError("legacy board has too many rows for one native transaction")
    for key in ("work_id", "origin", "alias"):
        values = [row[key] for row in rows if row[key] is not None]
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate legacy {key} across active and archive boards")
    boards = {"open": {"sha256": hashlib.sha256(active[0]).hexdigest(), "size": len(active[0])},
              "archive": None if archive is None else {
                  "sha256": hashlib.sha256(archive[0]).hexdigest(), "size": len(archive[0])}}
    return {"boards": boards, "rows": rows, "count": len(rows), "owner": "legacy",
            "source_row_count": source_row_count, "adopted_logical_count": len(rows),
            "crash_copy_coalesced_count": coalesced}


def _locked(root, action):
    board_path = Path(root) / ".codearbiter" / "open-tasks.md"
    if not board_path.is_file() or board_path.is_symlink():
        raise ValueError("legacy work owner is absent or linked")
    lock = acquire_lock(board_path)
    if lock is None:
        raise ValueError("legacy board writer is busy; retry adoption inventory")
    try:
        return action()
    finally:
        release_lock(lock)


def preview(root):
    """Inventory every task row and exact board preimage without cutover."""
    return _locked(root, lambda: _inventory(root))


def adopt(root, native_client, operation_id, *, replay=False):
    """Inventory under the board lock; native cutover reacquires it and checks hashes."""
    def _apply():
        inventory = _inventory(root, snapshot=replay)
        rows = [{key: value for key, value in row.items() if key not in {"legacy_origin"}}
                for row in inventory["rows"]]
        return {
            "operation_id": operation_id,
            "expected_board_sha256": inventory["boards"]["open"]["sha256"],
            "expected_archive_sha256": None if inventory["boards"]["archive"] is None
            else inventory["boards"]["archive"]["sha256"],
            "rows": rows,
        }
    request = _apply() if replay else _locked(root, _apply)
    return native_client.call("work-adopt", request)
