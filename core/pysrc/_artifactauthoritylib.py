#!/usr/bin/env python3
# codeArbiter — durable closed authority producers for structured artifacts.
"""Supervise verification and correlate independent Codex review evidence.

arm_request(...) -> dict
run_verification(...) -> dict
observe_codex_hook(...) -> dict
publish_request(...) -> dict

The artifact engine owns every target binding.  Callers select only an activity
and record; they cannot supply an authority kind, verdict, evidence payload, or
reviewer identity.  External work is journaled before launch, observations are
immutable and content-addressed, and replay never silently reruns a completed
attempt.  Codex review correlation uses stable hook fields and deliberately
ignores transcript bytes whose format is not a public contract.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any

from _gitexec import git_executable, root_bound_git_env


OBSERVATION_DIR = Path(".codearbiter/.artifacts/observations")
SOURCE_DIR = Path(".codearbiter/.artifacts/authority-sources")
STATE_FORMAT = "codearbiter.authority-run/0.1.0"
OBSERVATION_FORMAT = "codearbiter.observation/0.2.0"
EVENT_FORMAT = "codearbiter.workflow-event/0.2.0"
DECISION_FORMAT = "codearbiter.review-decision/0.1.0"
ACTIVITIES = frozenset({"verification", "spec_review", "quality_review"})
REVIEW_ACTIVITIES = frozenset({"spec_review", "quality_review"})
STATES = frozenset({
    "ARMED", "LAUNCHING", "LAUNCHED", "RUNNING", "COMPLETED", "REJECTED",
    "FAILED", "ABANDONED", "CAPTURED",
})
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{0,127}")
REQUEST_RE = re.compile(r"[0-9a-f]{64}")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{12,128}")
HOST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}")
MAX_STATE = 1 << 20
MAX_OUTPUT = 8 << 20
MAX_DECISION = 65536
REGISTRY_PARENT = Path(tempfile.gettempdir())


class AuthorityError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorityError("INVALID_AUTHORITY_STATE", "state is not finite JSON") from exc


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integrity(value: dict[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("integrity_sha256", None)
    return _digest(_canonical(unsigned))


def _real_root(root: str | Path) -> Path:
    try:
        resolved = Path(root).resolve(strict=True)
        info = resolved.lstat()
    except OSError as exc:
        raise AuthorityError("UNSAFE_REPOSITORY", "repository root is unavailable") from exc
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise AuthorityError("UNSAFE_REPOSITORY", "repository root must be a real directory")
    return resolved


def _safe_directory(root: Path, relative: Path, *, create: bool) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                raise
            current.mkdir()
            info = current.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise AuthorityError("UNSAFE_AUTHORITY_PATH", "authority directories must be real")
    return current


def _atomic_replace(root: Path, relative: Path, data: bytes) -> None:
    parent = _safe_directory(root, relative.parent, create=True)
    temporary = parent / f".{relative.name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short authority-state write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, root / relative)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _publish_immutable(root: Path, relative: Path, data: bytes) -> None:
    parent = _safe_directory(root, relative.parent, create=True)
    target = parent / relative.name
    temporary = parent / f".{relative.name}.{secrets.token_hex(8)}.tmp"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(temporary, flags, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short immutable observation write")
            view = view[written:]
        os.fsync(fd)
    finally:
        if 'fd' in locals():
            os.close(fd)
    try:
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = target.read_bytes()
            if existing != data:
                raise AuthorityError("AUTHORITY_COLLISION", "content-addressed bytes differ")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _request_path(request_id: str) -> Path:
    if not isinstance(request_id, str) or REQUEST_RE.fullmatch(request_id) is None:
        raise AuthorityError("INVALID_REQUEST_ID", "request identity is malformed")
    return Path(f"{request_id}.json")


def _spool_root(root: Path) -> Path:
    try:
        result = subprocess.run(
            [git_executable(), "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", timeout=5, check=False, env=root_bound_git_env(),
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise OSError("git common directory unavailable")
        common = Path(result.stdout.strip()).resolve(strict=True)
        info = common.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise OSError("git common directory is unsafe")
        worktree_id = _digest(_canonical(_repository_identity(root)))[:32]
        spool = _safe_directory(
            common, Path("codearbiter") / "authority-runs" / worktree_id, create=True
        )
        spool_info = spool.lstat()
        spool_reparse = getattr(spool_info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(spool_info.st_mode) or spool_reparse or not stat.S_ISDIR(spool_info.st_mode):
            raise OSError("authority spool is unsafe")
        return spool
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthorityError("AUTHORITY_BUSY", "resolved git-common authority spool is unavailable") from exc


def _save(root: Path, value: dict[str, Any]) -> None:
    value = dict(value)
    value["integrity_sha256"] = _integrity(value)
    _atomic_replace(_spool_root(root), _request_path(value["request_id"]), _canonical(value))


def _load(root: Path, request_id: str) -> dict[str, Any]:
    path = _spool_root(root) / _request_path(request_id)
    try:
        info = path.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISREG(info.st_mode):
            raise OSError("not regular")
        if info.st_size > MAX_STATE:
            raise OSError("oversized")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthorityError("INVALID_AUTHORITY_STATE", "request state is unreadable") from exc
    allowed = {
        "format", "request_id", "state", "activity", "repository", "context",
        "context_ref", "context_sha256", "attempt", "launch", "observation_ref",
        "observation_sha256", "receipt", "integrity_sha256", "payload",
        "authority_source", "dispatch_prompt", "review_contract_sha256",
        "required_coverage", "wrapper", "command_bindings", "recovery",
        "launch_envelope", "workspace_roots",
    }
    if (
        not isinstance(value, dict)
        or set(value) - allowed
        or value.get("format") != STATE_FORMAT
        or value.get("request_id") != request_id
        or value.get("activity") not in ACTIVITIES
        or value.get("state") not in STATES
        or not isinstance(value.get("context"), dict)
        or not isinstance(value.get("repository"), dict)
        or not isinstance(value.get("command_bindings", []), list)
        or not isinstance(value.get("workspace_roots", {}), dict)
        or any(not isinstance(key, str) or not isinstance(path, str)
               for key, path in value.get("workspace_roots", {}).items())
        or value.get("integrity_sha256") != _integrity(value)
        or not isinstance(value.get("context_ref"), str)
        or SHA256_RE.fullmatch(value.get("context_sha256", "")) is None
    ):
        raise AuthorityError("INVALID_AUTHORITY_STATE", "request state failed validation")
    return value


def _validate_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", f"{field} is malformed")
    return value


def _context(
    root: Path, client: Any, artifact_id: str, record_id: str, activity: str
) -> tuple[dict[str, Any], str, str]:
    result = client.call("evidence-context", {
        "artifact_id": artifact_id, "record_id": record_id, "activity": activity,
    })
    if not isinstance(result, dict):
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "engine context result is malformed")
    context_hash = _validate_hash(result.get("context_sha256"), "context_sha256")
    context_ref = result.get("context_ref")
    expected_ref = f".codearbiter/.artifacts/evidence-contexts/{context_hash}.json"
    if context_ref != expected_ref:
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "context locator is not content addressed")
    try:
        raw = (root / expected_ref).read_bytes()
        context = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "context bytes are unavailable") from exc
    if _digest(raw) != context_hash or raw != _canonical(context):
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "context bytes changed or are not canonical")
    subject = context.get("subject") if isinstance(context, dict) else None
    if (
        not isinstance(context, dict)
        or context.get("format") != "codearbiter.evidence-context/0.1.0"
        or not isinstance(subject, dict)
        or subject.get("artifact_id") != artifact_id
        or subject.get("record_id") != record_id
        or context["activity"] != activity
        or not ID_RE.fullmatch(artifact_id)
        or not ID_RE.fullmatch(record_id)
    ):
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "engine context changed selection")
    for field in ("input_sha256", "spec_sha256", "plan_sha256"):
        _validate_hash(context.get(field), field)
    _validate_hash(subject.get("normative_sha256"), "normative_sha256")
    if activity in {"verification", "spec_review"}:
        _validate_hash(context.get("task_sha256"), "task_sha256")
    if activity == "verification":
        commands = context.get("commands")
        if not isinstance(commands, list) or not commands:
            raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "verification has no commands")
        for command in commands:
            definition = command.get("definition") if isinstance(command, dict) else None
            if (
                not isinstance(command, dict)
                or set(command) != {"definition_sha256", "definition"}
                or not isinstance(definition, dict)
                or not {"argv", "cwd", "expected_exit", "required_tests"} <= set(definition)
                or not isinstance(definition.get("argv"), list)
                or not definition.get("argv")
                or any(not isinstance(item, str) or not item for item in definition.get("argv", []))
                or not isinstance(definition.get("cwd"), str)
                or not definition.get("cwd")
                or type(definition.get("expected_exit")) is not int
                or not 0 <= definition.get("expected_exit", -1) <= 255
                or not isinstance(definition.get("required_tests"), list)
                or any(not isinstance(item, str) or not item for item in definition.get("required_tests", []))
                or len(set(definition.get("required_tests", []))) != len(definition.get("required_tests", []))
            ):
                raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "command definition is malformed")
            _validate_hash(command["definition_sha256"], "definition_sha256")
    elif activity == "spec_review":
        if not isinstance(context.get("task"), dict):
            raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "review task is absent")
    else:
        _validate_hash(context.get("base_input_sha256"), "base_input_sha256")
        if not isinstance(context.get("task_hashes"), dict) or not isinstance(context.get("tasks"), list):
            raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "quality-review scope is incomplete")
    return context, context_ref, context_hash


def _review_binding(context: dict[str, Any]) -> tuple[str, list[str]]:
    contract = {
        "format": DECISION_FORMAT,
        "decision": ["pass", "changes_requested"],
        "finding_severity": ["BLOCK", "WARN", "INFO"],
        "required_fields": [
            "format", "request_id", "target_sha256", "contract_sha256",
            "decision", "coverage", "findings", "assessment",
        ],
    }
    records = [context["task"]] if context["activity"] == "spec_review" else context["tasks"]
    coverage = sorted({
        ref for record in records for ref in record.get("criterion_refs", [])
        if isinstance(ref, str) and ref
    })
    if not coverage:
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "review target has no criterion coverage")
    return _digest(_canonical(contract)), coverage


def _repository_identity(root: Path) -> dict[str, str]:
    info = os.stat(root)
    return {
        "path": str(root),
        "filesystem_id": f"{int(getattr(info, 'st_dev', 0))}:{int(getattr(info, 'st_ino', 0))}",
    }


def _registry_root() -> Path:
    namespace = f"uid-{os.getuid()}" if hasattr(os, "getuid") else "current-user"
    root = REGISTRY_PARENT.resolve(strict=True) / f"codearbiter-authority-{namespace}"
    try:
        root.mkdir(mode=0o700, exist_ok=True)
        info = root.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise OSError("unsafe registry")
        if hasattr(os, "getuid"):
            if info.st_uid != os.getuid():
                raise OSError("foreign registry")
            os.chmod(root, 0o700)
    except OSError as exc:
        raise AuthorityError("AUTHORITY_BUSY", "authority registry is unavailable") from exc
    return root


def _register_request(root: Path, request: dict[str, Any]) -> None:
    pointer = {
        "format": "codearbiter.authority-pointer/0.1.0",
        "request_id": request["request_id"],
        "repository": request["repository"],
    }
    pointer["integrity_sha256"] = _integrity(pointer)
    registry = _registry_root()
    target = registry / f"{request['request_id']}.json"
    data = _canonical(pointer)
    try:
        existing = target.read_bytes()
    except FileNotFoundError:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(target, flags, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short authority-pointer write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        if existing != data:
            raise AuthorityError("AUTHORITY_COLLISION", "request registry entry differs")


def _registered_requests() -> list[tuple[Path, dict[str, Any]]]:
    results = []
    for path in _registry_root().glob("*.json"):
        try:
            raw = path.read_bytes()
            if len(raw) > 16384:
                continue
            pointer = json.loads(raw.decode("utf-8"))
            repository = pointer.get("repository") if isinstance(pointer, dict) else None
            if (
                not isinstance(pointer, dict)
                or pointer.get("format") != "codearbiter.authority-pointer/0.1.0"
                or pointer.get("request_id") != path.stem
                or pointer.get("integrity_sha256") != _integrity(pointer)
                or not isinstance(repository, dict)
            ):
                continue
            root = _real_root(repository.get("path"))
            if _repository_identity(root) != repository:
                continue
            results.append((root, _load(root, path.stem)))
        except (AuthorityError, OSError, UnicodeError, ValueError):
            continue
    return results


def _registered_request(request_id: str) -> tuple[Path, dict[str, Any]]:
    matches = [item for item in _registered_requests() if item[1]["request_id"] == request_id]
    if len(matches) != 1:
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "authority request routing is ambiguous")
    return matches[0]


def _ordinary_spawn_marker(session_id: str, turn_id: str) -> Path:
    key = _digest(_canonical({"session_id": session_id, "turn_id": turn_id}))
    return _registry_root() / f"ordinary-spawn-{key}.marker"


def _record_ordinary_spawn(session_id: str, turn_id: str) -> None:
    marker = _ordinary_spawn_marker(session_id, turn_id)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        os.write(fd, b"ordinary spawn observed\n")
        os.fsync(fd)
    finally:
        os.close(fd)


def _reject_overlapping_authority(session_id: str, turn_id: str) -> None:
    for root, request in _registered_requests():
        launch = request.get("launch") or {}
        if (
            request["state"] in {"LAUNCHING", "RUNNING"}
            and launch.get("parent_session_id") == session_id
            and launch.get("parent_turn_id") == turn_id
        ):
            request["state"] = "REJECTED"
            request["recovery"] = {
                "mode": "overlapping-subagent-launch",
                "rerun_permitted": False,
            }
            _save(root, request)


def _git_text(directory: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [git_executable(), "-C", str(directory), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=15, env=root_bound_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "git workspace identity is unavailable") from exc
    if result.returncode != 0:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "git workspace identity is unavailable")
    return result.stdout.decode("utf-8", "strict").strip()


def _path_identity(path: Path) -> str:
    info = path.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace path is replaceable indirection")
    return f"{int(getattr(info, 'st_dev', 0))}:{int(getattr(info, 'st_ino', 0))}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(1 << 20)
                if not block:
                    break
                digest.update(block)
    except OSError as exc:
        raise AuthorityError("UNSUPPORTED_EXECUTABLE", "declared executable is unreadable") from exc
    return digest.hexdigest()


def _workspace_for(
    root: Path, label: str, workspace_roots: dict[str, str]
) -> tuple[Path, Path, Path]:
    if label in workspace_roots:
        cwd = _real_root(workspace_roots[label])
        declared_top = _real_root(_git_text(cwd, "rev-parse", "--show-toplevel"))
        if declared_top != cwd:
            raise AuthorityError("UNSUPPORTED_WORKSPACE", "mapped workspace is not an exact Git worktree root")
    elif label in {".", "current worktree", "candidate worktree"}:
        cwd = root
    else:
        candidate = Path(label)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AuthorityError("UNSUPPORTED_WORKSPACE", "declared cwd escapes the artifact worktree")
        cwd = _resolved_directory(root / candidate)
    worktree = _real_root(_git_text(cwd, "rev-parse", "--show-toplevel"))
    if label not in workspace_roots and worktree != root:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "declared cwd is not in the artifact worktree")
    common = _real_root(_git_text(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    artifact_common = _real_root(_git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if common != artifact_common:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace does not share the artifact git-common-dir")
    return cwd, worktree, common


def _resolve_executable(name: str, cwd: Path) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or candidate.parent != Path("."):
        path = (cwd / candidate).resolve(strict=True) if not candidate.is_absolute() else candidate.resolve(strict=True)
    else:
        located = shutil.which(name, path=os.environ.get("PATH", ""))
        if not located:
            raise AuthorityError("UNSUPPORTED_EXECUTABLE", "declared executable is not resolvable")
        path = Path(located).resolve(strict=True)
    if not path.is_file():
        raise AuthorityError("UNSUPPORTED_EXECUTABLE", "declared executable is not a regular file")
    _path_identity(path)
    return path


def _bind_commands(
    root: Path, context: dict[str, Any], workspace_roots: dict[str, str]
) -> list[dict[str, Any]]:
    bindings = []
    for command in context["commands"]:
        definition = command["definition"]
        cwd, worktree, common = _workspace_for(root, definition["cwd"], workspace_roots)
        executable = _resolve_executable(definition["argv"][0], cwd)
        bindings.append({
            "definition_sha256": command["definition_sha256"],
            "argv": [str(executable), *definition["argv"][1:]],
            "cwd": str(cwd),
            "cwd_filesystem_id": _path_identity(cwd),
            "workspace_root": str(worktree),
            "workspace_filesystem_id": _path_identity(worktree),
            "git_common_dir": str(common),
            "git_common_filesystem_id": _path_identity(common),
            "executable_sha256": _file_sha256(executable),
        })
    return bindings


def _workspace_snapshots(bindings: list[dict[str, Any]]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for binding in bindings:
        cwd = _resolved_directory(binding["cwd"])
        root = _real_root(binding["workspace_root"])
        common = _real_root(binding["git_common_dir"])
        if (
            _path_identity(cwd) != binding["cwd_filesystem_id"]
            or _path_identity(root) != binding["workspace_filesystem_id"]
            or _path_identity(common) != binding["git_common_filesystem_id"]
            or _file_sha256(Path(binding["argv"][0])) != binding["executable_sha256"]
        ):
            raise AuthorityError("WORKSPACE_DRIFT", "workspace or executable identity changed")
        status = _git_text(root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
        listed = _git_text(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        content = hashlib.sha256()
        for relative in sorted(item for item in listed.split("\0") if item):
            encoded = relative.encode("utf-8")
            candidate = root / relative
            try:
                info = candidate.lstat()
                reparse = getattr(info, "st_file_attributes", 0) & 0x400
                if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISREG(info.st_mode):
                    raise OSError("workspace member is not a real regular file")
                data = candidate.read_bytes()
            except OSError as exc:
                raise AuthorityError("WORKSPACE_DRIFT", "workspace content cannot be frozen") from exc
            content.update(len(encoded).to_bytes(8, "big"))
            content.update(encoded)
            content.update(len(data).to_bytes(8, "big"))
            content.update(data)
        unique[str(root)] = {
            "root": str(root),
            "filesystem_id": binding["workspace_filesystem_id"],
            "git_common_dir": str(common),
            "git_common_filesystem_id": binding["git_common_filesystem_id"],
            "head": _git_text(root, "rev-parse", "HEAD"),
            "status_sha256": _digest(status.encode("utf-8")),
            "content_sha256": content.hexdigest(),
        }
    return [unique[key] for key in sorted(unique)]


def _dispatch_prompt(request: dict[str, Any]) -> str:
    context = request["context"]
    return (
        f"[CODEARBITER_AUTHORITY_REQUEST:{request['request_id']}]\n"
        f"Target repository: {request['repository']['path']}\n"
        f"Frozen context: {request['context_ref']} sha256={request['context_sha256']}\n"
        "Frozen target data follows as canonical JSON:\n"
        + _canonical(context).decode("ascii") + "\n"
        "Act as a fresh read-only independent codeArbiter reviewer. Do not edit files or "
        "delegate. Review only the frozen target and return exactly one JSON object using "
        f"format {DECISION_FORMAT}. Bind request_id={request['request_id']}, "
        f"target_sha256={context['input_sha256']}, "
        f"contract_sha256={request['review_contract_sha256']}. Required coverage: "
        + json.dumps(request["required_coverage"], ensure_ascii=True)
        + ". Fields: format, request_id, target_sha256, contract_sha256, decision "
          "(pass or changes_requested), coverage (unique strings), findings (objects with "
          "severity, code, message), assessment (non-empty string)."
    )


def arm_request(
    root: str | Path,
    client: Any,
    artifact_id: str,
    record_id: str,
    activity: str,
    *,
    request_nonce: str | None = None,
    workspace_roots: dict[str, str | Path] | None = None,
    **unexpected: Any,
) -> dict[str, Any]:
    if unexpected:
        raise AuthorityError(
            "INVALID_AUTHORITY_REQUEST",
            "authority, verdict, payload, and observations are not caller inputs",
        )
    if activity not in ACTIVITIES:
        raise AuthorityError("INVALID_AUTHORITY_REQUEST", "activity is unsupported")
    root = _real_root(root)
    nonce = request_nonce or secrets.token_urlsafe(24)
    if not isinstance(nonce, str) or TOKEN_RE.fullmatch(nonce) is None:
        raise AuthorityError("INVALID_AUTHORITY_REQUEST", "request nonce is malformed")
    context, context_ref, context_sha256 = _context(
        root, client, artifact_id, record_id, activity
    )
    frozen_workspaces: dict[str, str] = {}
    if workspace_roots is not None:
        if activity != "verification" or not isinstance(workspace_roots, dict):
            raise AuthorityError("INVALID_AUTHORITY_REQUEST", "workspace roots apply only to verification")
        labels = {command["definition"]["cwd"] for command in context["commands"]}
        if set(workspace_roots) != labels:
            raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace map must exactly cover declared cwd labels")
        frozen_workspaces = {label: str(_real_root(path)) for label, path in workspace_roots.items()}
    command_bindings = _bind_commands(root, context, frozen_workspaces) if activity == "verification" else []
    seed = _canonical({
        "repository": _repository_identity(root), "context": context, "nonce": nonce,
        "command_bindings": command_bindings,
        "workspace_roots": frozen_workspaces,
    })
    request_id = _digest(seed)
    request = {
        "format": STATE_FORMAT,
        "request_id": request_id,
        "state": "ARMED",
        "activity": activity,
        "repository": _repository_identity(root),
        "context": context,
        "context_ref": context_ref,
        "context_sha256": context_sha256,
        "attempt": None,
        "launch": None,
        "observation_ref": None,
        "observation_sha256": None,
        "receipt": None,
        "wrapper": None,
        "recovery": None,
        "command_bindings": command_bindings,
        "workspace_roots": frozen_workspaces,
    }
    if activity in REVIEW_ACTIVITIES:
        request["review_contract_sha256"], request["required_coverage"] = _review_binding(context)
        request["dispatch_prompt"] = _dispatch_prompt(request)
        request["launch_envelope"] = {
            "message": request["dispatch_prompt"],
            "task_name": f"authority_{request_id[:12]}",
            "fork_turns": "none",
        }
    _save(root, request)
    _register_request(root, request)
    result = {
        "request_id": request_id,
        "request_path": str(_spool_root(root) / _request_path(request_id)),
        "activity": activity,
    }
    if activity in REVIEW_ACTIVITIES:
        result["dispatch_prompt"] = request["dispatch_prompt"]
        result["review_contract_sha256"] = request["review_contract_sha256"]
        result["required_coverage"] = request["required_coverage"]
        result["launch_envelope"] = request["launch_envelope"]
    return result


def _bounded_output(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise AuthorityError("INVALID_PROCESS_RESULT", "process output must be bytes")
    if len(value) > MAX_OUTPUT:
        raise AuthorityError("PROCESS_OUTPUT_TOO_LARGE", "process output exceeds 8 MiB")
    return bytes(value)


def _unittest_collector(stdout: bytes, stderr: bytes, required: list[str]) -> list[dict[str, str]]:
    text = (stdout + b"\n" + stderr).decode("utf-8", "replace")
    results = []
    for name in required:
        pattern = re.compile(r"(?m)^" + re.escape(name) + r"(?:\s+\([^\r\n]*\))?\s+\.\.\.\s+ok\s*$")
        matches = pattern.findall(text)
        if not matches:
            raise AuthorityError("MISSING_TEST_RESULT", f"required test did not pass: {name}")
        if len(matches) != 1:
            raise AuthorityError("DUPLICATE_TEST_RESULT", f"required test appeared more than once: {name}")
        results.append({"name": name, "status": "pass"})
    return results


def _named_line_collector(stdout: bytes, stderr: bytes, required: list[str]) -> list[dict[str, str]]:
    # Intentional producer gap: current SingedTerra movement, walls, and
    # fall-damage harnesses emit umbrella summaries for some plan aggregates.
    # Those summaries are not semantic evidence; only exact PASS names qualify.
    text = (stdout + b"\n" + stderr).decode("utf-8", "replace")
    passed: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("PASS: "):
            name = stripped[6:].rstrip(".")
            passed[name] = passed.get(name, 0) + 1
    duplicates = [name for name in required if passed.get(name, 0) > 1]
    if duplicates:
        raise AuthorityError("DUPLICATE_TEST_RESULT", "required PASS lines are duplicated: " + ", ".join(duplicates))
    missing = [name for name in required if passed.get(name, 0) != 1]
    if missing:
        raise AuthorityError(
            "MISSING_TEST_RESULT", "required explicit PASS lines are absent: " + ", ".join(missing)
        )
    return [{"name": name, "status": "pass"} for name in required]


def _vitest_verbose_collector(stdout: bytes, stderr: bytes, required: list[str]) -> list[dict[str, str]]:
    text = (stdout + b"\n" + stderr).decode("utf-8", "replace")
    passed: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("✓ ", "√ ")):
            name = stripped[2:].rsplit(" > ", 1)[-1]
            name = re.sub(r"\s+\d+(?:\.\d+)?m?s$", "", name)
            passed[name] = passed.get(name, 0) + 1
    duplicates = [name for name in required if passed.get(name, 0) > 1]
    if duplicates:
        raise AuthorityError("DUPLICATE_TEST_RESULT", "required Vitest cases are duplicated: " + ", ".join(duplicates))
    missing = [name for name in required if passed.get(name, 0) != 1]
    if missing:
        raise AuthorityError(
            "MISSING_TEST_RESULT", "required exact Vitest case names are absent: " + ", ".join(missing)
        )
    return [{"name": name, "status": "pass"} for name in required]


def _exit_only_collector(_stdout: bytes, _stderr: bytes, required: list[str]) -> list[dict[str, str]]:
    if required:
        raise AuthorityError("UNSUPPORTED_COLLECTOR", "exit-only profile cannot attest named tests")
    return []


COLLECTORS: dict[str, Callable[[bytes, bytes, list[str]], list[dict[str, str]]]] = {
    "python-unittest-text/0.1.0": _unittest_collector,
    "codearbiter-named-lines/0.1.0": _named_line_collector,
    "vitest-verbose/0.1.0": _vitest_verbose_collector,
    "exit-only/0.1.0": _exit_only_collector,
}


def _collector_profile(argv: list[str], required: list[str]) -> str:
    if not required:
        return "exit-only/0.1.0"
    lowered = [part.casefold() for part in argv]
    if len(lowered) >= 3 and lowered[1:3] == ["-m", "unittest"]:
        return "python-unittest-text/0.1.0"
    if "vitest" in lowered and "--reporter=verbose" in lowered:
        return "vitest-verbose/0.1.0"
    if "tsx" in lowered or lowered[:3] == ["npm", "run", "test:client"] or lowered[:3] == ["npm", "run", "check"]:
        return "codearbiter-named-lines/0.1.0"
    raise AuthorityError("UNSUPPORTED_COLLECTOR", "declared runner has no qualified collector")


def _minimal_environment() -> tuple[dict[str, str], str]:
    names = (
        "PATH", "PATHEXT", "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP",
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL",
    )
    environment = {name: os.environ[name] for name in names if name in os.environ}
    return environment, _digest(_canonical(environment))


def _resolved_directory(value: Any) -> Path:
    if not isinstance(value, (str, Path)):
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace resolver returned no directory")
    try:
        path = Path(value).resolve(strict=True)
        info = path.lstat()
    except OSError as exc:
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace directory is unavailable") from exc
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise AuthorityError("UNSUPPORTED_WORKSPACE", "workspace must be a real directory")
    return path


def _run_contained(
    argv: list[str], *, cwd: str, env: dict[str, str], timeout_seconds: float = 1800.0
) -> subprocess.CompletedProcess:
    """Bound output and descendants with POSIX sessions or a Windows Job Object."""
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise AuthorityError("INVALID_PROCESS_TIMEOUT", "process timeout must be positive")
    job = None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise AuthorityError("UNSUPPORTED_PROCESS_CONTAINMENT", "CreateJobObjectW failed")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            kernel32.CloseHandle(job)
            raise AuthorityError("UNSUPPORTED_PROCESS_CONTAINMENT", "job limits could not be installed")
        try:
            process = subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                creationflags=0x00000200 | 0x00000004,  # NEW_PROCESS_GROUP | SUSPENDED
            )
            if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
                process.kill()
                process.wait()
                raise AuthorityError("UNSUPPORTED_PROCESS_CONTAINMENT", "child could not enter Job Object")
            if ntdll.NtResumeProcess(wintypes.HANDLE(int(process._handle))) != 0:
                kernel32.TerminateJobObject(job, 1)
                process.wait()
                raise AuthorityError("UNSUPPORTED_PROCESS_CONTAINMENT", "suspended child could not resume")
        except Exception:
            kernel32.CloseHandle(job)
            raise
    else:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            start_new_session=True,
        )
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            if len(buffers[name]) + len(chunk) > MAX_OUTPUT:
                overflow.set()
            else:
                buffers[name].extend(chunk)

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            if overflow.is_set() or time.monotonic() >= deadline:
                if os.name == "nt":
                    kernel32.TerminateJobObject(job, 1)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                if overflow.is_set():
                    raise AuthorityError("PROCESS_OUTPUT_TOO_LARGE", "process output exceeds 8 MiB")
                raise AuthorityError("VERIFICATION_PROCESS_FAILED", "verification process timed out")
            time.sleep(0.02)
    finally:
        if job is not None:
            kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE ends surviving descendants.
            job = None
        elif process.poll() is not None:
            try:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        for thread in threads:
            thread.join(timeout=10)
        process.stdout.close()
        process.stderr.close()
    if overflow.is_set():
        raise AuthorityError("PROCESS_OUTPUT_TOO_LARGE", "process output exceeds 8 MiB")
    return subprocess.CompletedProcess(argv, process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]))


def _observation(root: Path, request: dict[str, Any], value: dict[str, Any]) -> None:
    raw = _canonical(value)
    digest = _digest(raw)
    relative = OBSERVATION_DIR / f"{digest}.json"
    _publish_immutable(root, relative, raw)
    request["observation_ref"] = relative.as_posix()
    request["observation_sha256"] = digest


def _closed_observation(
    request: dict[str, Any], payload: dict[str, Any], producer_profile: str,
    producer_run_id: str, producer_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "format": OBSERVATION_FORMAT,
        "kind": request["activity"],
        "subject": request["context"]["subject"],
        "context_ref": request["context_ref"],
        "context_sha256": request["context_sha256"],
        "payload_sha256": _digest(_canonical(payload)),
        "producer_profile": producer_profile,
        "producer_run_id": producer_run_id,
        "producer_result": producer_result,
        "producer_result_sha256": _digest(_canonical(producer_result)),
    }


def capture_user_prompt(
    root: str | Path, client: Any, event: dict[str, Any], *, host: str, session_id: str
) -> dict[str, Any]:
    """Capture one exact host UserPromptSubmit event through a closed observation."""
    root = _real_root(root)
    if (
        not isinstance(event, dict)
        or event.get("kind") not in {"approval", "prerequisite", "reconciliation", "farm_authorization"}
        or event.get("authority_kind") != "user_workflow"
        or not isinstance(event.get("subject"), dict)
        or not isinstance(event.get("source_text"), str)
        or not event["source_text"]
    ):
        raise AuthorityError("INVALID_PROMPT_EVENT", "user prompt event is malformed")
    producer_run_id = f"{_host_id(host, 'host')}:{_host_id(session_id, 'session_id')}"
    prompt_sha256 = _digest(event["source_text"].encode("utf-8"))
    subject = event["subject"]
    result = client.call("evidence-context", {
        "artifact_id": subject.get("artifact_id"),
        "record_id": subject.get("record_id"),
        "activity": event["kind"],
        "prompt_sha256": prompt_sha256,
    })
    if not isinstance(result, dict):
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "prompt context result is malformed")
    context_ref = result.get("context_ref")
    context_sha256 = _validate_hash(result.get("context_sha256"), "context_sha256")
    if context_ref != f".codearbiter/.artifacts/evidence-contexts/{context_sha256}.json":
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "prompt context is not content addressed")
    try:
        context_raw = (root / context_ref).read_bytes()
        context = json.loads(context_raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "prompt context is unavailable") from exc
    if (
        _digest(context_raw) != context_sha256
        or context_raw != _canonical(context)
        or context.get("activity") != event["kind"]
        or context.get("subject") != subject
        or context.get("prompt_sha256") != prompt_sha256
    ):
        raise AuthorityError("INVALID_EVIDENCE_CONTEXT", "prompt context changed its authority binding")
    producer_result = {"host": host, "session_id": session_id, "prompt_sha256": prompt_sha256}
    observation = {
        "format": OBSERVATION_FORMAT,
        "kind": event["kind"],
        "subject": subject,
        "context_ref": context_ref,
        "context_sha256": context_sha256,
        "payload_sha256": _digest(_canonical(event.get("payload"))),
        "producer_profile": "host-user-prompt/0.1.0",
        "producer_run_id": producer_run_id,
        "producer_result": producer_result,
        "producer_result_sha256": _digest(_canonical(producer_result)),
    }
    observation_raw = _canonical(observation)
    observation_sha256 = _digest(observation_raw)
    observation_ref = OBSERVATION_DIR / f"{observation_sha256}.json"
    _publish_immutable(root, observation_ref, observation_raw)
    current_event = dict(event)
    current_event["format"] = EVENT_FORMAT
    current_event["observation_ref"] = observation_ref.as_posix()
    current_event["observation_sha256"] = observation_sha256
    event_raw = _canonical(current_event)
    event_sha256 = _digest(event_raw)
    source_ref = SOURCE_DIR / f"{event_sha256}.json"
    _publish_immutable(root, source_ref, event_raw)
    captured = client.call("capture-observation", {
        "source_ref": source_ref.as_posix(), "source_sha256": event_sha256,
    })
    if not isinstance(captured, dict) or not isinstance(captured.get("receipt"), str):
        raise AuthorityError("INVALID_RECEIPT", "observed prompt capture returned no receipt")
    return {
        **captured, "authority_source": source_ref.as_posix(),
        "observation_ref": observation_ref.as_posix(),
    }


def run_verification(
    root: str | Path,
    client: Any,
    request_id: str,
) -> dict[str, Any]:
    root = _real_root(root)
    request = _load(root, request_id)
    if request["activity"] != "verification":
        raise AuthorityError("INVALID_AUTHORITY_REQUEST", "request is not verification")
    if request["state"] == "COMPLETED":
        return {
            "request_id": request_id, "state": "COMPLETED",
            "commands": request["payload"]["commands"],
        }
    if request["state"] != "ARMED":
        raise AuthorityError("INTERRUPTED_ATTEMPT", "verification attempt cannot be rerun")
    wrapper = request.get("wrapper")
    if not isinstance(wrapper, dict) or wrapper.get("state") != "AUTHORIZED":
        raise AuthorityError(
            "UNAUTHORIZED_VERIFIER",
            "verification requires a correlated PreToolUse authorization",
        )
    if _bind_commands(root, request["context"], request["workspace_roots"]) != request["command_bindings"]:
        raise AuthorityError("WORKSPACE_DRIFT", "effective argv or workspace changed after arm")
    fresh_context, fresh_ref, fresh_hash = _context(
        root, client, request["context"]["subject"]["artifact_id"],
        request["context"]["subject"]["record_id"], "verification",
    )
    if (fresh_context, fresh_ref, fresh_hash) != (
        request["context"], request["context_ref"], request["context_sha256"],
    ):
        raise AuthorityError("WORKSPACE_DRIFT", "repository content changed after arm")
    workspace_before = _workspace_snapshots(request["command_bindings"])
    if workspace_before != wrapper.get("workspace_before"):
        raise AuthorityError("WORKSPACE_DRIFT", "workspace changed after wrapper authorization")

    environment, environment_sha256 = _minimal_environment()
    request["state"] = "RUNNING"
    request["attempt"] = secrets.token_hex(16)
    _save(root, request)
    commands = []
    for command, binding in zip(request["context"]["commands"], request["command_bindings"]):
        definition = command["definition"]
        collector = COLLECTORS[_collector_profile(definition["argv"], definition["required_tests"])]
        cwd = _resolved_directory(binding["cwd"])
        try:
            completed = _run_contained(list(binding["argv"]), cwd=str(cwd), env=environment)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuthorityError("VERIFICATION_PROCESS_FAILED", "verification process did not complete") from exc
        stdout = _bounded_output(completed.stdout)
        stderr = _bounded_output(completed.stderr)
        if type(completed.returncode) is not int or not 0 <= completed.returncode <= 255:
            raise AuthorityError("INVALID_PROCESS_RESULT", "process exit is invalid")
        if completed.returncode != definition["expected_exit"]:
            raise AuthorityError("FAILED_VERIFICATION", "process exit differs from approved definition")
        tests = collector(stdout, stderr, list(definition["required_tests"]))
        commands.append({
            "definition_sha256": command["definition_sha256"],
            "exit": completed.returncode,
            "tests": tests,
            "stdout_sha256": _digest(stdout),
            "stderr_sha256": _digest(stderr),
        })
    workspace_after = _workspace_snapshots(request["command_bindings"])
    if workspace_after != workspace_before:
        raise AuthorityError("WORKSPACE_DRIFT", "verification changed the frozen workspace")
    final_context, final_ref, final_hash = _context(
        root, client, request["context"]["subject"]["artifact_id"],
        request["context"]["subject"]["record_id"], "verification",
    )
    if (final_context, final_ref, final_hash) != (
        request["context"], request["context_ref"], request["context_sha256"],
    ):
        raise AuthorityError("WORKSPACE_DRIFT", "verification changed repository content")
    producer_result = {
        "environment_sha256": environment_sha256,
        "command_bindings": request["command_bindings"],
        "workspace_before": workspace_before,
        "workspace_after": workspace_after,
        "commands": commands,
    }
    payload = {
        "input_sha256": request["context"]["input_sha256"],
        "spec_sha256": request["context"]["spec_sha256"],
        "task_sha256": request["context"]["task_sha256"],
        "commands": commands,
    }
    observation = _closed_observation(
        request, payload, "declared-command/0.1.0", request["attempt"],
        producer_result,
    )
    _observation(root, request, observation)
    request["payload"] = payload
    request["state"] = "COMPLETED"
    _save(root, request)
    return {"request_id": request_id, "state": "COMPLETED", "commands": commands}


def _request_id_from_prompt(message: Any) -> str:
    if not isinstance(message, str):
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "spawn message is absent")
    match = re.match(r"\[CODEARBITER_AUTHORITY_REQUEST:([0-9a-f]{64})\]\n", message)
    if match is None:
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "spawn message has no authority request")
    return match.group(1)


def _host_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or HOST_ID_RE.fullmatch(value) is None:
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", f"{field} is malformed")
    return value


def _verification_selector(event: dict[str, Any]) -> tuple[str, Path] | None:
    """Recognize only the closed wrapper selector, never caller-authored child argv."""
    if event.get("tool_name") not in {
        "Bash", "shell_command", "exec_command", "unified_exec",
    }:
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "exec input is malformed")
    command = tool_input.get("command", tool_input.get("cmd"))
    if not isinstance(command, str):
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "exec command is absent")
    if any(marker in command for marker in ("\n", "\r", ";", "&&", "||", "|", ">", "<", "`")):
        if "artifact-authority" in command:
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "verifier wrapper command is compound")
        return None
    try:
        tokens = [token.strip('"') for token in shlex.split(command, posix=False)]
    except ValueError as exc:
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "verifier wrapper command is malformed") from exc
    if len(tokens) != 7:
        return None
    if (
        Path(tokens[0]).name.lower() not in {
            "python", "python.exe", "python3", "python3.exe", "py", "py.exe",
        }
        or Path(tokens[1]).name.lower() != "artifact-authority.py"
        or tokens[2] != "verify"
        or tokens[3] != "--root"
        or tokens[5] != "--request-id"
        or REQUEST_RE.fullmatch(tokens[6]) is None
    ):
        return None
    return tokens[6], _real_root(tokens[4])


def observe_verifier_hook(
    invocation_root: str | Path, event: dict[str, Any]
) -> dict[str, Any] | None:
    """Authorize/corroborate the wrapper; native exit/output remain result evidence."""
    _real_root(invocation_root)
    if not isinstance(event, dict) or event.get("hook_event_name") not in {"PreToolUse", "PostToolUse"}:
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "verifier hook event is unsupported")
    selected = _verification_selector(event)
    if selected is None:
        return None
    request_id, selected_root = selected
    root, request = _registered_request(request_id)
    if root != selected_root or request["activity"] != "verification":
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "verifier target does not match its request")
    session_id = _host_id(event.get("session_id"), "session_id")
    turn_id = _host_id(event.get("turn_id"), "turn_id")
    tool_use_id = _host_id(event.get("tool_use_id"), "tool_use_id")
    if event["hook_event_name"] == "PreToolUse":
        if request["state"] != "ARMED" or request.get("wrapper") is not None:
            raise AuthorityError("INTERRUPTED_ATTEMPT", "verifier wrapper is not armable")
        current_bindings = _bind_commands(root, request["context"], request["workspace_roots"])
        if current_bindings != request["command_bindings"]:
            raise AuthorityError("WORKSPACE_DRIFT", "effective child argv or cwd changed")
        for command in request["context"]["commands"]:
            definition = command["definition"]
            _collector_profile(definition["argv"], definition["required_tests"])
        workspace_before = _workspace_snapshots(current_bindings)
        request["wrapper"] = {
            "state": "AUTHORIZED", "session_id": session_id,
            "turn_id": turn_id, "tool_use_id": tool_use_id,
            "command_bindings": current_bindings,
            "workspace_before": workspace_before,
        }
        _save(root, request)
        return {
            "request_id": request_id, "state": "AUTHORIZED",
            "command_bindings": current_bindings, "workspace_before": workspace_before,
        }
    wrapper = request.get("wrapper")
    if (
        not isinstance(wrapper, dict)
        or wrapper.get("session_id") != session_id
        or wrapper.get("turn_id") != turn_id
        or wrapper.get("tool_use_id") != tool_use_id
        or request["state"] != "COMPLETED"
    ):
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "verifier completion is not correlated")
    response = event.get("tool_response")
    if not isinstance(response, dict) or response.get("exit_code") != 0:
        raise AuthorityError("FAILED_VERIFICATION", "verifier wrapper did not report exit 0")
    wrapper["state"] = "CORROBORATED"
    _save(root, request)
    return {"request_id": request_id, "state": "CORROBORATED"}


def _parse_decision(raw: Any, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_DECISION:
        raise AuthorityError("INVALID_REVIEW_DECISION", "review decision is absent or oversized")
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise AuthorityError("INVALID_REVIEW_DECISION", "review decision is not JSON") from exc
    expected = {
        "format", "request_id", "target_sha256", "contract_sha256", "decision",
        "coverage", "findings", "assessment",
    }
    context = request["context"]
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("format") != DECISION_FORMAT
        or value.get("request_id") != request["request_id"]
        or value.get("target_sha256") != context["input_sha256"]
        or value.get("contract_sha256") != request["review_contract_sha256"]
        or value.get("decision") not in {"pass", "changes_requested"}
        or not isinstance(value.get("assessment"), str)
        or not value["assessment"].strip()
        or not isinstance(value.get("coverage"), list)
        or len(set(value["coverage"])) != len(value["coverage"])
        or not isinstance(value.get("findings"), list)
    ):
        raise AuthorityError("INVALID_REVIEW_DECISION", "review decision failed its closed schema")
    if set(value["coverage"]) != set(request["required_coverage"]):
        raise AuthorityError("INCOMPLETE_REVIEW", "review coverage is incomplete")
    for finding in value["findings"]:
        if (
            not isinstance(finding, dict)
            or set(finding) != {"severity", "code", "message"}
            or finding["severity"] not in {"BLOCK", "WARN", "INFO"}
            or not all(isinstance(finding[key], str) and finding[key] for key in ("code", "message"))
        ):
            raise AuthorityError("INVALID_REVIEW_DECISION", "review finding is malformed")
    if value["decision"] != "pass" or any(
        finding["severity"] == "BLOCK" for finding in value["findings"]
    ):
        raise AuthorityError("REVIEW_REJECTED", "independent reviewer did not pass the target")
    return value


def observe_codex_hook(root: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    _real_root(root)  # Invocation repository is observed but cannot select authority.
    if not isinstance(event, dict):
        raise AuthorityError("UNSUPPORTED_HOST_SEAM", "hook event is malformed")
    name = event.get("hook_event_name")
    session_id = _host_id(event.get("session_id"), "session_id")

    if name == "PreToolUse":
        if event.get("tool_name") != "spawn_agent":
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "only spawn_agent can launch a reviewer")
        tool_use_id = _host_id(event.get("tool_use_id"), "tool_use_id")
        turn_id = _host_id(event.get("turn_id"), "turn_id")
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "spawn input is malformed")
        message = tool_input.get("message")
        if not isinstance(message, str) or not message.startswith("[CODEARBITER_AUTHORITY_REQUEST:"):
            _record_ordinary_spawn(session_id, turn_id)
            _reject_overlapping_authority(session_id, turn_id)
            return None
        request_id = _request_id_from_prompt(message)
        root, request = _registered_request(request_id)
        if request["activity"] not in REVIEW_ACTIVITIES or request["state"] != "ARMED":
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "review request is not launchable")
        if tool_input != request.get("launch_envelope"):
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "review launch envelope was changed")
        if _ordinary_spawn_marker(session_id, turn_id).exists():
            request["state"] = "REJECTED"
            request["recovery"] = {
                "mode": "overlapping-subagent-launch",
                "rerun_permitted": False,
            }
            _save(root, request)
            raise AuthorityError(
                "UNSUPPORTED_HOST_SEAM",
                "authority review cannot share a parent turn with another subagent launch",
            )
        request["launch"] = {
            "parent_session_id": session_id, "parent_turn_id": turn_id,
            "tool_use_id": tool_use_id, "post_confirmed": False,
            "agent_id": None, "agent_type": None,
            "task_name": tool_input["task_name"],
            "fork_turns": tool_input["fork_turns"],
        }
        request["state"] = "LAUNCHING"
        _save(root, request)
        return {"request_id": request_id, "state": "LAUNCHING"}

    if name == "PostToolUse":
        if event.get("tool_name") != "spawn_agent":
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "post-tool event is not reviewer launch")
        tool_use_id = _host_id(event.get("tool_use_id"), "tool_use_id")
        turn_id = _host_id(event.get("turn_id"), "turn_id")
        response = event.get("tool_response")
        if not isinstance(response, dict):
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "spawn result is malformed")
        task_name = _host_id(response.get("task_name"), "task_name")
        matches = []
        for candidate_root, candidate in _registered_requests():
            launch = candidate.get("launch") or {}
            if (
                candidate["state"] in {"LAUNCHING", "RUNNING"}
                and launch.get("parent_session_id") == session_id
                and launch.get("parent_turn_id") == turn_id
                and launch.get("tool_use_id") == tool_use_id
            ):
                matches.append((candidate_root, candidate))
        if not matches:
            return None
        if len(matches) != 1:
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "review launch correlation is ambiguous")
        root, request = matches[0]
        if task_name != request["launch"].get("task_name"):
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "spawn result task_name differs")
        request["launch"]["post_confirmed"] = True
        _save(root, request)
        return {"request_id": request["request_id"], "state": request["state"]}

    if name in {"SubagentStart", "SubagentStop"}:
        agent_id = _host_id(event.get("agent_id"), "agent_id")
        turn_id = _host_id(event.get("turn_id"), "turn_id")
        matches = []
        same_turn = []
        for candidate_root, candidate in _registered_requests():
            launch = candidate.get("launch") or {}
            if (
                launch.get("parent_session_id") == session_id
                and launch.get("parent_turn_id") == turn_id
                and candidate["state"] in {"LAUNCHING", "RUNNING"}
            ):
                same_turn.append((candidate_root, candidate))
            if name == "SubagentStart" and (
                candidate["state"] == "LAUNCHING"
                and launch.get("parent_session_id") == session_id
                and launch.get("parent_turn_id") == turn_id
            ):
                matches.append((candidate_root, candidate))
            elif name == "SubagentStop" and (
                launch.get("parent_session_id") == session_id
                and launch.get("parent_turn_id") == turn_id
                and launch.get("agent_id") == agent_id
            ):
                matches.append((candidate_root, candidate))
        if not matches and not same_turn:
            return None
        if not matches and same_turn:
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "subagent does not match the active authority launch")
        if len(matches) != 1:
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "subagent correlation is ambiguous")
        root, request = matches[0]
        agent_type = _host_id(event.get("agent_type"), "agent_type")
        if name == "SubagentStart":
            request["launch"]["agent_id"] = agent_id
            request["launch"]["agent_type"] = agent_type
            request["state"] = "RUNNING"
            _save(root, request)
            return {"request_id": request["request_id"], "state": "RUNNING"}
        if (
            request["state"] != "RUNNING"
            or request["launch"].get("agent_type") != agent_type
            or request["launch"].get("post_confirmed") is not True
        ):
            raise AuthorityError("UNSUPPORTED_HOST_SEAM", "subagent stop is out of order")
        try:
            decision = _parse_decision(event.get("last_assistant_message"), request)
        except AuthorityError:
            request["state"] = "REJECTED"
            _save(root, request)
            raise
        payload = {
            "input_sha256": request["context"]["input_sha256"],
            "spec_sha256": request["context"]["spec_sha256"],
            "assessment": decision["assessment"],
        }
        if request["activity"] == "spec_review":
            payload["task_sha256"] = request["context"]["task_sha256"]
        else:
            payload["base_input_sha256"] = request["context"]["base_input_sha256"]
            payload["task_hashes"] = request["context"]["task_hashes"]
        producer_result = {"launch": request["launch"], "decision": decision}
        observation = _closed_observation(
            request, payload, "codex-review/0.1.0", agent_id,
            producer_result,
        )
        _observation(root, request, observation)
        request["payload"] = payload
        request["state"] = "COMPLETED"
        _save(root, request)
        return {"request_id": request["request_id"], "state": "COMPLETED"}

    raise AuthorityError("UNSUPPORTED_HOST_SEAM", "hook event is not supported")


def _event(request: dict[str, Any]) -> dict[str, Any]:
    context = request["context"]
    activity = request["activity"]
    if activity == "verification":
        authority_kind = "verification_runner"
        actor = "codeArbiter supervised verifier"
        origin = f"codex:verification-run:{request['request_id']}"
        source_text = "Observed exact declared-command completion and qualified named-test results."
    else:
        authority_kind = "review_workflow"
        actor = "independent codex reviewer"
        origin = f"codex:subagent:{request['launch']['agent_id']}"
        source_text = "Observed a correlated fresh Codex reviewer completion with a closed passing decision."
    return {
        "format": EVENT_FORMAT,
        "kind": activity,
        "authority_kind": authority_kind,
        "subject": context["subject"],
        "actor": actor,
        "origin": origin,
        "verdict": "passed",
        "payload": request["payload"],
        "source_text": source_text,
        "observation_ref": request["observation_ref"],
        "observation_sha256": request["observation_sha256"],
    }


def publish_request(
    root: str | Path, client: Any, request_id: str
) -> dict[str, Any]:
    root = _real_root(root)
    request = _load(root, request_id)
    if request["state"] == "CAPTURED":
        return {
            "request_id": request_id, "receipt": request["receipt"],
            "authority_source": request["authority_source"],
        }
    if request["state"] != "COMPLETED":
        raise AuthorityError("AUTHORITY_NOT_COMPLETE", "successful observation is absent")
    if request["activity"] == "verification":
        wrapper = request.get("wrapper")
        if not isinstance(wrapper, dict) or wrapper.get("state") != "CORROBORATED":
            raise AuthorityError("AUTHORITY_NOT_COMPLETE", "verifier wrapper completion is uncorroborated")
    current, current_ref, current_hash = _context(
        root, client, request["context"]["subject"]["artifact_id"],
        request["context"]["subject"]["record_id"],
        request["activity"],
    )
    if (
        current != request["context"]
        or current_ref != request["context_ref"]
        or current_hash != request["context_sha256"]
    ):
        raise AuthorityError("STALE_AUTHORITY_REQUEST", "engine evidence context changed")
    observation_path = root / request["observation_ref"]
    try:
        observation = observation_path.read_bytes()
    except OSError as exc:
        raise AuthorityError("INVALID_OBSERVATION", "observation is unavailable") from exc
    if _digest(observation) != request["observation_sha256"]:
        raise AuthorityError("INVALID_OBSERVATION", "observation digest differs")
    event = _event(request)
    raw = _canonical(event)
    digest = _digest(raw)
    relative = SOURCE_DIR / f"{digest}.json"
    _publish_immutable(root, relative, raw)
    captured = client.call("capture-observation", {
        "source_ref": relative.as_posix(), "source_sha256": digest,
    })
    receipt = captured.get("receipt")
    if not isinstance(receipt, str) or not receipt:
        raise AuthorityError("INVALID_RECEIPT", "capture returned no receipt")
    request["state"] = "CAPTURED"
    request["receipt"] = receipt
    request["authority_source"] = relative.as_posix()
    _save(root, request)
    return {"request_id": request_id, "receipt": receipt, "authority_source": relative.as_posix()}


def recover_request(root: str | Path, request_id: str, disposition: str) -> dict[str, Any]:
    """Retain an uncertain attempt and close it without ever rerunning commands."""
    root = _real_root(root)
    if disposition not in {"failed", "abandoned"}:
        raise AuthorityError("INVALID_RECOVERY", "recovery disposition must be failed or abandoned")
    request = _load(root, request_id)
    recoverable_completed = (
        request["state"] == "COMPLETED"
        and request["activity"] == "verification"
        and isinstance(request.get("wrapper"), dict)
        and request["wrapper"].get("state") != "CORROBORATED"
    )
    recoverable_authorized = (
        request["state"] == "ARMED"
        and request["activity"] == "verification"
        and isinstance(request.get("wrapper"), dict)
        and request["wrapper"].get("state") == "AUTHORIZED"
    )
    if request["state"] not in {"RUNNING", "LAUNCHING"} and not recoverable_completed and not recoverable_authorized:
        raise AuthorityError("INVALID_RECOVERY", "only an interrupted active attempt can be recovered")
    request["state"] = disposition.upper()
    request["recovery"] = {
        "disposition": disposition,
        "previous_attempt": request.get("attempt"),
        "rerun_permitted": False,
    }
    _save(root, request)
    return {"request_id": request_id, "state": request["state"], "rerun_permitted": False}
