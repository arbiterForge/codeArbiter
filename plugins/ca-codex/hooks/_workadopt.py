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
    warnings = board.lint_board(text)
    if warnings:
        raise ValueError("malformed or duplicate legacy task: " + warnings[0])
    lines = text.splitlines()
    tasks = board.parse_board(text)
    if len(tasks) != sum(line.startswith("- ") for line in lines):
        raise ValueError("legacy board has an unaccounted task row")
    result = []
    for task in tasks:
        bounds = board.task_block(lines, task)
        if bounds is None or bounds[0] != task.lineno - 1:
            raise ValueError("legacy task block is not selectable")
        block = "\n".join(lines[bounds[0]:bounds[1]])
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
            seed = f"{location}\0{task.lineno}\0{block}".encode("utf-8")
            origin = "legacy:" + location + "#" + hashlib.sha256(seed).hexdigest()[:32]
        # Preserve IDs already exposed by the legacy adapter, even when the
        # historical source does not fit the native origin grammar.
        work_id = metadata.get("Work ID") or _worklib._id(legacy_origin or origin)
        if _ID.fullmatch(work_id) is None:
            raise ValueError("invalid legacy work ID")
        alias = task.id
        title = _worklib._title(task, legacy_origin) if legacy_origin else task.title
        intent = task.desc or title
        work_type = metadata.get("Work type") or "unknown"
        if (not title or len(title) > 240 or not intent or len(intent) > 4000
                or work_type not in {"feature", "fix", "chore", "spike", "unknown"}):
            raise ValueError("legacy task title, intent or work type cannot fit native work")
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
        })
    return result


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
    rows = _rows(active[1], "open")
    if archive:
        rows.extend(_rows(archive[1], "archive"))
    if len(rows) > 123:
        raise ValueError("legacy board has too many rows for one native transaction")
    for key in ("work_id", "origin", "alias"):
        values = [row[key] for row in rows if row[key] is not None]
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate legacy {key} across active and archive boards")
    boards = {"open": {"sha256": hashlib.sha256(active[0]).hexdigest(), "size": len(active[0])},
              "archive": None if archive is None else {
                  "sha256": hashlib.sha256(archive[0]).hexdigest(), "size": len(archive[0])}}
    return {"boards": boards, "rows": rows, "count": len(rows), "owner": "legacy"}


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
