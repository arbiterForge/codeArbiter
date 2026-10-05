#!/usr/bin/env python3
# codeArbiter — source-bound Tribunal run records.
#
# Stdlib only; no import-time I/O. Git plumbing is read-only, with no shell,
# external diff, filters, fsmonitor, replacements or lazy fetch. Worktree bytes
# are read directly, never through Git filters or an escaping link. Fingerprints
# intentionally compare literal reviewed bytes, including line endings.
# Explicit evidence_paths name represented file/gitlink inputs, not directories.
# Ignored or otherwise unrepresented declarations are refused, never omitted.
# The coordinator owns log writes. Exclusive per-run locks reject concurrent
# writers; a stranded lock requires explicit operator recovery, never takeover.
# Existing records are never rewritten. These are cooperative audit records,
# not cryptographically authenticated attestations (ADR-0010).
#
# Public API (all return dictionaries with ok; errors are fixed reason codes):
#   source_fingerprint(root, scope='.', reviewed_untracked=None,
#                      target_digest=None, active_run=None, evidence_paths=None) -> dict
#   start_run(root, scope='.', reviewed_untracked=None,
#             target_digest=None, detail=None, evidence_paths=None) -> dict
#   resume_status(root, run_dir, scope=None, target_digest=None, evidence_paths=None) -> dict
#   read_run(root, run_dir) -> dict
#   append_event(root, run_dir, event, **fields) -> dict
#   write_lead(root, run_dir, record) -> dict
#   dispose_lead(root, run_dir, lead_id, disposition, rationale) -> dict
#   read_leads(root, run_dir) -> dict
#   validate_finding(record) -> dict
#   triage_eligibility(finding, triage, verification=None) -> dict
#   append_triage(root, run_dir, finding, triage, verification=None) -> dict

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess

from _gitexec import git_executable, root_bound_git_env


REPORTS = ".codearbiter/reports"
MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_GIT_BYTES = 128 * 1024 * 1024
AUDIT_EVENTS = {"lens-launched", "lens-skipped", "lens-completed", "wave-flushed", "wave-triaged", "report-written"}
FOLLOWUP_EVENTS = {"issues-filed", "filing-skipped", "telemetry-sent", "telemetry-skipped", "run-completed"}
TERMINAL_EVENTS = {"run-completed", "run-aborted"}
DECISIONS = {"keep", "combine", "duplicate", "false-positive", "defer", "accept-risk", "decision-required", "verify-required", "investigate"}
SEVERITIES = {"critical", "high", "medium", "low"}
DISPOSITIONS = {"routed", "promoted", "dismissed", "deferred"}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OBJECT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


class _Invalid(ValueError):
    pass


def _public(function):
    @wraps(function)
    def safe(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except _Invalid as exc:
            return {"ok": False, "error": str(exc)}
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, subprocess.SubprocessError):
            return {"ok": False, "error": "unreadable-or-malformed-input"}
    return safe


def _require(condition, reason):
    if not condition:
        raise _Invalid(reason)


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _name(value):
    return isinstance(value, str) and bool(_NAME.fullmatch(value))


def _relative(value):
    _require(isinstance(value, str) and "\x00" not in value and "\\" not in value and ":" not in value, "invalid-relative-path")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and ".." not in path.parts and ".git" not in path.parts, "invalid-relative-path")
    return path.as_posix()


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _contained(root, relative, leaf_link=False):
    """Reject links/reparse points in ancestors before accessing any leaf."""
    relative = _relative(relative)
    current = root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if _linked(info):
            _require(leaf_link and index == len(parts) - 1 and stat.S_ISLNK(info.st_mode), "linked-path-refused")
    return current


def _root(root):
    path = Path(root).resolve(strict=True)
    _require(path.is_dir(), "invalid-repository-root")
    return path


def _git(root, *args, data=None):
    env = {key: value for key, value in root_bound_git_env().items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    try:
        executable = git_executable()
    except RuntimeError:
        raise _Invalid("git-executable-unavailable") from None
    result = subprocess.run(
        [executable, "--no-pager", "--no-lazy-fetch", "-c", "core.fsmonitor=false",
         "-c", "core.hooksPath=" + os.devnull, "-c", "core.untrackedCache=false", *args],
        cwd=root, env=env, input=data, capture_output=True, shell=False, timeout=30)
    _require(result.returncode == 0, "git-plumbing-unavailable")
    _require(len(result.stdout) <= MAX_GIT_BYTES, "git-output-over-limit")
    return result.stdout


def _git_text(root, *args):
    return _git(root, *args).decode("utf-8", "surrogateescape").strip()


def _identity(root):
    actual = Path(_git_text(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    _require(actual == root, "repository-root-mismatch")
    common = _git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return {"root": os.path.normcase(str(root)), "common_dir": os.path.normcase(str(Path(common).resolve(strict=True)))}


def _entries(raw, staged):
    entries = []
    for item in raw.split(b"\x00"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        fields = metadata.decode("ascii").split()
        mode, oid = (fields[0], fields[1]) if staged else (fields[0], fields[2])
        _require(mode in {"100644", "100755", "120000", "160000"} and _OBJECT.fullmatch(oid), "invalid-git-entry")
        stage = int(fields[2]) if staged else 0
        _require(stage in {0, 1, 2, 3}, "invalid-index-stage")
        entries.append({"path": _relative(path.decode("utf-8", "surrogateescape")), "mode": mode, "object": oid, "stage": stage})
    return sorted(entries, key=lambda entry: (entry["path"], entry["stage"]))


def _blobs(root, entries):
    objects = sorted({entry["object"] for entry in entries if entry["mode"] != "160000"})
    if not objects:
        return {}
    raw = _git(root, "cat-file", "--batch", data=("\n".join(objects) + "\n").encode("ascii"))
    values, cursor = {}, 0
    for oid in objects:
        end = raw.index(b"\n", cursor)
        returned, kind, length = raw[cursor:end].decode("ascii").split()
        _require(returned == oid and kind == "blob", "invalid-git-blob")
        size = int(length)
        _require(0 <= size <= MAX_GIT_BYTES and end + size + 1 < len(raw), "invalid-git-blob")
        content = raw[end + 1:end + size + 1]
        _require(raw[end + size + 1:end + size + 2] == b"\n", "invalid-git-blob")
        values[oid] = hashlib.sha256(content).hexdigest()
        cursor = end + size + 2
    _require(cursor == len(raw), "invalid-git-blob")
    return values


def _worktree_entry(root, name, indexed, allow_submodules=True):
    path = _contained(root, name, leaf_link=True)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"path": name, "mode": "missing", "content": None}
    if indexed and indexed["mode"] == "160000":
        _require(stat.S_ISDIR(info.st_mode), "invalid-submodule-directory")
        if not any(path.iterdir()):
            return {"path": name, "mode": "160000", "content": indexed["object"]}
        # One declared gitlink level is supported, including child dirty and
        # untracked bytes. Nested populated gitlinks require their own audit.
        _require(allow_submodules, "nested-submodule-requires-separate-audit")
        child = _fingerprint(path, ".", None, None, allow_submodules=False)
        return {"path": name, "mode": "160000", "content": child["head"],
                "submodule_digest": child["digest"], "submodule_clean": child["clean"]}
    if stat.S_ISLNK(info.st_mode):
        data, mode = os.fsencode(os.readlink(path)), "120000"
    else:
        _require(stat.S_ISREG(info.st_mode) and not _linked(info), "non-regular-input")
        _require(info.st_size <= MAX_GIT_BYTES, "source-file-over-limit")
        with path.open("rb") as handle:
            data = handle.read(MAX_GIT_BYTES + 1)
        _require(len(data) <= MAX_GIT_BYTES, "source-file-over-limit")
        mode = "100755" if info.st_mode & 0o111 else "100644"
        if os.name == "nt":
            mode = indexed["mode"] if indexed and indexed["mode"] in {"100644", "100755"} else "100644"
    return {"path": name, "mode": mode, "content": hashlib.sha256(data).hexdigest()}


def _fingerprint(root, scope, reviewed_untracked, target_digest, active_run=None, evidence_paths=None, allow_submodules=True):
    scope = _relative(scope)
    _contained(root, scope, leaf_link=True)
    _require(evidence_paths is None or isinstance(evidence_paths, list), "invalid-evidence-paths")
    evidence_paths = sorted({_relative(path) for path in evidence_paths or []})
    for path in evidence_paths:
        _contained(root, path, leaf_link=True)
    _require(target_digest is None or isinstance(target_digest, str) and _DIGEST.fullmatch(target_digest), "invalid-target-digest")
    identity = _identity(root)
    head = _git_text(root, "rev-parse", "--verify", "HEAD")
    _require(_OBJECT.fullmatch(head), "invalid-head")
    excluded = active_run.relative_to(root).as_posix() if active_run else None
    all_heads = _entries(_git(root, "ls-tree", "-rz", "--full-tree", "HEAD"), False)
    all_indexes = _entries(_git(root, "ls-files", "--stage", "-z"), True)
    gitlinks = {entry["path"] for entry in all_heads + all_indexes if entry["mode"] == "160000"}

    def selected(name):
        # A scope within a gitlink conservatively binds that whole child.
        included = any(path == "." or name == path or name.startswith(path + "/") or
                       name in gitlinks and path.startswith(name + "/") for path in [scope, *evidence_paths])
        return included and not (excluded and (name == excluded or name.startswith(excluded + "/")))

    head_entries = [entry for entry in all_heads if selected(entry["path"])]
    index_entries = [entry for entry in all_indexes if selected(entry["path"])]
    available = {_relative(path.decode("utf-8", "surrogateescape")) for path in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\x00") if path}
    available = {name for name in available if selected(name)}
    _require(reviewed_untracked is None or isinstance(reviewed_untracked, list), "invalid-untracked-selection")
    untracked = sorted(available if reviewed_untracked is None else {_relative(name) for name in reviewed_untracked})
    _require(all(name in available for name in untracked), "untracked-input-unavailable")
    represented = {entry["path"] for entry in head_entries + index_entries} | set(untracked)
    _require(all(path in represented for path in evidence_paths), "evidence-input-unavailable")
    blobs = _blobs(root, head_entries + index_entries)

    def content_entries(entries):
        return [{"path": entry["path"], "mode": entry["mode"], "stage": entry["stage"],
                 "content": entry["object"] if entry["mode"] == "160000" else blobs[entry["object"]]} for entry in entries]

    indexed = {entry["path"]: entry for entry in index_entries}
    tracked = sorted({entry["path"] for entry in head_entries + index_entries})
    worktree = [_worktree_entry(root, name, indexed.get(name), allow_submodules) for name in tracked]
    untracked_content = [_worktree_entry(root, name, None) for name in untracked]
    heads, indexes = content_entries(head_entries), content_entries(index_entries)
    clean_index = heads == indexes
    plain_worktree = [{key: entry[key] for key in ("path", "mode", "content")} for entry in worktree]
    clean_worktree = [dict(entry, stage=0) for entry in plain_worktree] == indexes and all(entry.get("submodule_clean", True) for entry in worktree)
    result = {"schema": "tribunal-source/v1", "repository": identity, "head": head, "scope": scope, "evidence_paths": evidence_paths,
              "clean": clean_index and clean_worktree and not untracked,
              "head_tree_digest": _digest(heads), "index_digest": _digest(indexes), "worktree_digest": _digest(worktree),
              "untracked_digest": _digest(untracked_content), "reviewed_untracked": untracked,
              "untracked_policy": "all" if reviewed_untracked is None else "selected", "target_digest": target_digest}
    result["digest"] = _digest(result)
    return result


def _run_path(root, run_dir):
    path = Path(run_dir)
    if not path.is_absolute():
        path = root / path
    relative = path.relative_to(root).as_posix()
    parts = PurePosixPath(relative).parts
    _require(len(parts) == 3 and "/".join(parts[:2]) == REPORTS and _name(parts[2]), "invalid-run-directory")
    path = _contained(root, relative)
    _require(path.is_dir(), "run-directory-unavailable")
    return path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def _parse(data):
    def invalid_number(value):
        raise _Invalid("invalid-json-number")
    value = json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid_number)
    _require(isinstance(value, dict), "invalid-record")
    return value


def _read_bytes(root, path, optional=False):
    _contained(root, path.relative_to(root).as_posix())
    try:
        with path.open("rb") as handle:
            value = handle.read(MAX_RECORD_BYTES + 1)
    except FileNotFoundError:
        if optional:
            return None
        raise
    _require(len(value) <= MAX_RECORD_BYTES, "record-over-limit")
    return value


def _records(root, path):
    value = _read_bytes(root, path, optional=True)
    if not value:
        return []
    _require(value.endswith(b"\n"), "incomplete-log-record")
    return [_parse(line) for line in value.splitlines()]


def _binding(root, folder):
    raw = _read_bytes(root, folder / "source.json", optional=True)
    if raw is None:
        return None
    value = _parse(raw)
    _require(value.get("schema") == "tribunal-run/v1" and value.get("run_id") == folder.name, "invalid-run-binding")
    fp = value.get("fingerprint")
    _require(isinstance(fp, dict) and fp.get("schema") == "tribunal-source/v1", "invalid-source-binding")
    _require(fp.get("digest") == _digest({key: entry for key, entry in fp.items() if key != "digest"}), "invalid-source-binding")
    _require(isinstance(fp.get("repository"), dict) and fp["repository"].get("root") == os.path.normcase(str(root)), "repository-root-mismatch")
    _require(isinstance(fp.get("evidence_paths"), list), "invalid-source-binding")
    _require(fp.get("untracked_policy") in {"all", "selected"} and isinstance(fp.get("reviewed_untracked"), list), "invalid-source-binding")
    return value


def _cursor(events, fingerprint):
    _require(events and events[0].get("event") == "run-started" and events[0].get("source_digest") == fingerprint["digest"], "unbound-run-log")
    state, filing, telemetry, last_wave = "audit", None, None, 0
    for index, entry in enumerate(events):
        event = entry.get("event")
        _require(entry.get("schema") == "run/v1", "invalid-run-event")
        if index == 0:
            continue
        _require(state != "terminal", "event-after-terminal")
        _require(event in AUDIT_EVENTS | FOLLOWUP_EVENTS | {"run-aborted"}, "invalid-run-event")
        if event in AUDIT_EVENTS:
            _require(state == "audit", "audit-already-reported")
        if event in FOLLOWUP_EVENTS:
            _require(state == "follow-up", "report-required")
        if event == "report-written":
            state = "follow-up"
        elif event in {"issues-filed", "filing-skipped"}:
            _require(filing is None, "filing-already-disposed")
            filing = event
        elif event in {"telemetry-sent", "telemetry-skipped"}:
            _require(telemetry is None, "telemetry-already-disposed")
            telemetry = event
        elif event == "wave-triaged":
            wave = entry.get("wave")
            _require(type(wave) is int and wave > last_wave, "invalid-wave")
            last_wave = wave
        elif event == "run-completed":
            _require(filing is not None and telemetry is not None, "followup-dispositions-required")
        if event in TERMINAL_EVENTS:
            state = "terminal"
    return {"state": state, "filing": filing, "telemetry": telemetry, "last_triaged_wave": last_wave,
            "detail": events[0].get("detail")}


def _status(root, folder, scope=None, target_digest=None, evidence_paths=None):
    try:
        binding = _binding(root, folder)
        if binding is None:
            return {"ok": True, "state": "legacy-unbound", "can_resume_audit": False, "can_resume_follow_up": False}
        fp = binding["fingerprint"]
        cursor = _cursor(_records(root, folder / "run.jsonl"), fp)
    except (ValueError, KeyError, TypeError, OSError):
        return {"ok": False, "state": "invalid", "error": "invalid-run-records", "can_resume_audit": False, "can_resume_follow_up": False}
    if cursor["state"] != "terminal":
        try:
            current = _fingerprint(root, fp["scope"] if scope is None else scope,
                                   None if fp["untracked_policy"] == "all" else fp["reviewed_untracked"],
                                   fp["target_digest"] if target_digest is None else target_digest, folder,
                                   fp["evidence_paths"] if evidence_paths is None else evidence_paths)
            unchanged = current == fp
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            unchanged = False
        if not unchanged:
            cursor["state"] = "source-drift"
    return {"ok": True, **cursor, "can_resume_audit": cursor["state"] == "audit",
            "can_resume_follow_up": cursor["state"] == "follow-up"}


def _write(root, path, record, append=False):
    _contained(root, path.relative_to(root).as_posix())
    data = _json(record) + b"\n"
    _require(len(data) <= MAX_RECORD_BYTES, "record-over-limit")
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_EXCL)
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "ab" if append else "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def _lock(root, folder):
    path = folder / ".write-lock"
    try:
        _write(root, path, {"at": _now()})
    except FileExistsError:
        raise _Invalid("run-busy-recovery-required") from None
    try:
        yield
    finally:
        path.unlink()


def _writable(root, folder, followup=False):
    status = _status(root, folder)
    allowed = {"audit", "follow-up"} if followup else {"audit"}
    _require(status.get("ok") and status["state"] in allowed, "run-not-writable")


@_public
def source_fingerprint(root, scope=".", reviewed_untracked=None, target_digest=None, active_run=None, evidence_paths=None):
    root = _root(root)
    if active_run is not None:
        active_run = _run_path(root, active_run)
        _require(_binding(root, active_run) is not None, "unowned-run-exclusion")
    return {"ok": True, "fingerprint": _fingerprint(root, scope, reviewed_untracked, target_digest, active_run, evidence_paths)}


def _new_run_id(scope):
    slug = re.sub(r"[^a-z0-9]+", "-", scope.lower()).strip("-")[:40] or "all"
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + slug + "-" + secrets.token_hex(4)


@_public
def start_run(root, scope=".", reviewed_untracked=None, target_digest=None, detail=None, evidence_paths=None):
    root, scope = _root(root), _relative(scope)
    initial = _fingerprint(root, scope, reviewed_untracked, target_digest, evidence_paths=evidence_paths)
    _json(detail)
    reports = _contained(root, REPORTS)
    reports.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        run_id = _new_run_id(scope)
        _require(_name(run_id), "invalid-run-id")
        folder = reports / run_id
        try:
            folder.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise _Invalid("run-allocation-exhausted")
    current = _fingerprint(root, scope, reviewed_untracked, target_digest, folder, evidence_paths)
    _require(current == initial, "source-changed-during-start")
    binding = {"schema": "tribunal-run/v1", "run_id": run_id, "created_at": _now(), "fingerprint": current}
    _write(root, folder / "source.json", binding)
    _write(root, folder / "run.jsonl", {"schema": "run/v1", "event": "run-started", "source_digest": current["digest"], "detail": detail, "at": _now()})
    return {"ok": True, "run_id": run_id, "run_dir": str(folder), "fingerprint": current}


@_public
def resume_status(root, run_dir, scope=None, target_digest=None, evidence_paths=None):
    root = _root(root)
    return _status(root, _run_path(root, run_dir), scope, target_digest, evidence_paths)


@_public
def read_run(root, run_dir):
    """Read historical records without migrating, rebinding or rewriting them."""
    root = _root(root)
    folder = _run_path(root, run_dir)
    return {"ok": True, "events": _records(root, folder / "run.jsonl"), "triage": _records(root, folder / "triage.jsonl")}


@_public
def append_event(root, run_dir, event, **fields):
    root = _root(root)
    folder = _run_path(root, run_dir)
    _require(not ({"schema", "event", "at", "source_digest"} & fields.keys()), "reserved-event-field")
    _require(isinstance(event, str) and event in AUDIT_EVENTS | FOLLOWUP_EVENTS | {"run-aborted"}, "invalid-run-event")
    with _lock(root, folder):
        binding = _binding(root, folder)
        _require(binding is not None, "legacy-unbound")
        if event != "run-aborted":
            _writable(root, folder, followup=True)
        record = {"schema": "run/v1", "event": event, **fields, "at": _now()}
        _cursor(_records(root, folder / "run.jsonl") + [record], binding["fingerprint"])
        _write(root, folder / "run.jsonl", record, append=True)
    return {"ok": True, "record": record}


def _locations(value):
    _require(isinstance(value, list) and value, "locations-required")
    for entry in value:
        _require(isinstance(entry, dict) and _text(entry.get("path")) and _text(entry.get("lines")), "invalid-location")
        _relative(entry["path"])


def _lead(record):
    _require(isinstance(record, dict) and record.get("schema") == "lead/v1", "invalid-lead")
    for field in ("id", "source_lens", "target_lens"):
        _require(_name(record.get(field)), "invalid-lead-identity")
    _require(record["id"].startswith(record["source_lens"] + "-"), "invalid-lead-identity")
    _locations(record.get("locations"))
    for field in ("observation", "reason", "created_at"):
        _require(_text(record.get(field)), "invalid-lead-field")
    _require(record.get("disposition") == "open", "invalid-initial-lead-disposition")
    _json(record)


@_public
def write_lead(root, run_dir, record):
    _lead(record)
    root = _root(root)
    folder = _run_path(root, run_dir)
    with _lock(root, folder):
        _writable(root, folder)
        directory = _contained(root, (folder.relative_to(root) / "leads" / record["source_lens"]).as_posix())
        directory.mkdir(parents=True, exist_ok=True)
        _write(root, directory / (record["id"] + ".json"), record)
    return {"ok": True, "record": record}


def _read_leads(root, folder):
    directory = _contained(root, (folder.relative_to(root) / "leads").as_posix())
    records = {}
    if directory.exists():
        for lens in sorted(directory.iterdir()):
            _contained(root, lens.relative_to(root).as_posix())
            _require(lens.is_dir() and _name(lens.name), "invalid-lead-directory")
            for path in sorted(lens.iterdir()):
                _require(path.suffix == ".json", "invalid-lead-file")
                record = _parse(_read_bytes(root, path))
                _lead(record)
                _require(record["source_lens"] == lens.name and path.stem == record["id"] and record["id"] not in records, "invalid-lead-identity")
                records[record["id"]] = {**record, "disposition_history": []}
    for entry in _records(root, folder / "lead-dispositions.jsonl"):
        _require(entry.get("schema") == "lead-disposition/v1" and entry.get("id") in records and entry.get("disposition") in DISPOSITIONS and _text(entry.get("rationale")), "invalid-lead-disposition")
        record = records[entry["id"]]
        record["disposition"] = entry["disposition"]
        record["disposition_history"].append(entry)
    return list(records.values())


@_public
def read_leads(root, run_dir):
    root = _root(root)
    return {"ok": True, "leads": _read_leads(root, _run_path(root, run_dir))}


@_public
def dispose_lead(root, run_dir, lead_id, disposition, rationale):
    _require(_name(lead_id) and disposition in DISPOSITIONS and _text(rationale), "invalid-lead-disposition")
    root = _root(root)
    folder = _run_path(root, run_dir)
    with _lock(root, folder):
        _writable(root, folder, followup=True)
        _require(any(record["id"] == lead_id for record in _read_leads(root, folder)), "unknown-lead")
        record = {"schema": "lead-disposition/v1", "id": lead_id, "disposition": disposition, "rationale": rationale, "at": _now()}
        _write(root, folder / "lead-dispositions.jsonl", record, append=True)
    return {"ok": True, "record": record}


def _confidence(value):
    return type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1


def _finding(record):
    _require(isinstance(record, dict) and record.get("schema") == "finding/v1", "invalid-finding")
    _require(_name(record.get("id")) and _name(record.get("lens")), "invalid-finding-identity")
    _require(record.get("severity") in SEVERITIES and _confidence(record.get("confidence")), "invalid-finding-score")
    _locations(record.get("locations"))
    _require(_text(record.get("evidence")) and _text(record.get("recommendation")), "finding-evidence-required")
    _require(record.get("claim_type", "fact") in {"fact", "design-choice"}, "invalid-claim-type")
    if "root_cause_key" in record:
        _require(_text(record["root_cause_key"]), "invalid-root-cause")
    for field in ("corroborates", "related_lenses"):
        if field in record:
            _require(isinstance(record[field], list) and all(_name(value) for value in record[field]), "invalid-corroboration")
    _json(record)


@_public
def validate_finding(record):
    _finding(record)
    return {"ok": True, "finding": record}


def _eligibility(finding, triage, verification):
    _finding(finding)
    _require(isinstance(triage, dict) and triage.get("schema") == "triage/v1" and triage.get("id") == finding["id"], "invalid-triage")
    decision = triage.get("decision")
    _require(decision in DECISIONS and triage.get("final_severity") in SEVERITIES and _confidence(triage.get("final_confidence")), "invalid-triage-decision")
    _require(_text(triage.get("rationale")), "triage-rationale-required")
    _require(decision != "decision-required" or finding.get("claim_type") == "design-choice", "factual-uncertainty-is-not-design-choice")
    serious = finding["severity"] in {"critical", "high"} or triage["final_severity"] in {"critical", "high"}
    required = serious or finding.get("requires_verification") is True
    if serious:
        _require(_text(triage.get("counter_argument")), "serious-counter-argument-required")
    outcome, independent = None, False
    if verification is not None:
        _require(isinstance(verification, dict) and verification.get("schema") == "verification/v1" and verification.get("id") == finding["id"], "invalid-verification")
        outcome = verification.get("outcome")
        _require(outcome in {"confirmed", "narrowed", "refuted", "inconclusive"} and _text(verification.get("evidence")), "invalid-verification-outcome")
        _require(verification.get("verification_independence") in {"independent", "limited"}, "invalid-verification-independence")
        independent = verification["verification_independence"] == "independent"
    verified = independent and outcome in {"confirmed", "narrowed"}
    eligible = decision in {"keep", "combine"} and outcome not in {"refuted", "inconclusive"} and (not required or verified)
    recommended = "false-positive" if outcome == "refuted" else "verify-required" if required and not verified else decision
    root_cause = triage.get("root_cause_key", finding.get("root_cause_key", finding.get("dedup_key", finding["id"])))
    _require(_text(root_cause), "invalid-root-cause")
    _json(triage)
    return {"ok": True, "filing_eligible": eligible, "plan_eligible": eligible,
            "requires_verification": required and not verified, "recommended_decision": recommended,
            "root_cause_key": root_cause, "related_lenses": sorted(set([finding["lens"], *finding.get("related_lenses", [])]))}


@_public
def triage_eligibility(finding, triage, verification=None):
    return _eligibility(finding, triage, verification)


@_public
def append_triage(root, run_dir, finding, triage, verification=None):
    eligibility = _eligibility(finding, triage, verification)
    _require(eligibility["plan_eligible"] or triage["decision"] not in {"keep", "combine"}, "triage-requires-verification")
    _require(not triage.get("issue_ref") or eligibility["filing_eligible"], "finding-not-filing-eligible")
    root = _root(root)
    folder = _run_path(root, run_dir)
    record = {**triage, "root_cause_key": eligibility["root_cause_key"], "related_lenses": eligibility["related_lenses"],
              "corroborates": finding.get("corroborates", []), "verification": verification}
    with _lock(root, folder):
        _writable(root, folder, followup=True)
        _records(root, folder / "triage.jsonl")
        _write(root, folder / "triage.jsonl", record, append=True)
    return {"ok": True, "record": record, "eligibility": eligibility}
