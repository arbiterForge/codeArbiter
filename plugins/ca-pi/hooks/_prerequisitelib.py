#!/usr/bin/env python3
# codeArbiter — host-owned prerequisite confirmation for structured plans.
"""Capture an exact host-observed user decision and satisfy one prerequisite.

arm_user_prerequisite(...) -> dict
consume_user_prerequisite(...) -> dict
cancel_user_prerequisite(...) -> dict
supersede_user_prerequisite(...) -> dict
consume_from_hook(...) -> str

The adapter fixes the authority kind, verdict, actor, event shape, and engine
operation.  Callers select only an approved plan and one of its exact current
prerequisite records.  Confirmation is persisted before authority publication;
retries reuse the same event, receipt, operation ID, and mutation request.

The user-visible confirmation nonce is deliberately non-secret correlation
data, not a bearer credential. Possession never confers authority: the adapter
accepts it only in an exact prompt observed by the trusted UserPromptSubmit
boundary while the reviewed plan, approval, and prerequisite remain current.
The observed prompt is retained verbatim as the authority source because it is
the decision evidence; nonce unpredictability is not a security boundary.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
import time
from typing import Any

import _artifactlib
from _hooklib import acquire_lock, release_lock


PENDING_DIR = Path(".codearbiter/.markers/pending-prerequisites")
SOURCE_DIR = Path(".codearbiter/.artifacts/authority-sources")
FORMAT = "codearbiter.pending-user-prerequisite/0.1.0"
POLICY = "explicit-user-prerequisite-confirmation/0.1.0"
CONFIRMATION_LIFETIME_SECONDS = 15 * 60
CONFIRMATION_RE = re.compile(r"[A-Za-z0-9_-]{12,128}")
ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{0,127}")
HOST_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
SESSION_RE = re.compile(r"[A-Za-z0-9._:-]{1,256}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
RECEIPT_RE = re.compile(
    r"\.codearbiter/\.artifacts/receipts/[0-9a-f]{64}\.json"
)
STATES = frozenset({"ARMED", "CONFIRMED", "CAPTURED"})
STATE_FIELDS = {
    "format", "state", "request_id", "artifact_id", "prerequisite_id",
    "kind", "revision", "model_sha256", "normative_sha256", "record",
    "review_packet_sha256", "confirmation_sha256", "issued_at", "expires_at",
    "event", "authority_source", "receipt", "mutation_request",
}


class PrerequisiteError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pending_relative(artifact_id: str) -> Path:
    return PENDING_DIR / f"{_digest(artifact_id.encode('utf-8'))}.json"


def _prerequisite_busy() -> PrerequisiteError:
    return PrerequisiteError(
        "PREREQUISITE_BUSY",
        "another session is resolving this plan's prerequisite request",
    )


def _repository_lock_key(root: Path) -> bytes:
    """Return one key for every path alias to the same repository directory."""
    info = os.stat(root)
    device = int(getattr(info, "st_dev", 0))
    inode = int(getattr(info, "st_ino", 0))
    if device or inode:
        return f"stat:{device}:{inode}".encode("ascii")

    # Some Windows filesystems report no stable inode. Their path comparison is
    # case-insensitive, so casefold closes aliases that normcase alone may miss
    # on a non-native test host.
    resolved = str(root.resolve(strict=True))
    return b"path:" + os.path.normcase(resolved).casefold().encode("utf-8")


def _pending_lock_directory_name(temporary: Path | None = None) -> str:
    if hasattr(os, "getuid"):
        namespace = f"uid-{os.getuid()}"
    else:
        if temporary is None:
            temporary = Path(tempfile.gettempdir()).resolve(strict=True)
        temp_identity = (
            os.path.normcase(str(temporary)).casefold().encode("utf-8")
        )
        namespace = f"temp-{_digest(temp_identity)[:24]}"
    return f"codearbiter-prerequisite-locks-{namespace}"


def _pending_lock_root() -> Path:
    """Create and validate the private cross-process lock namespace."""
    try:
        temporary = Path(tempfile.gettempdir()).resolve(strict=True)
        lock_root = temporary / _pending_lock_directory_name(temporary)
        lock_root.mkdir(mode=0o700, exist_ok=True)
        info = lock_root.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & 0x400
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise OSError("prerequisite lock root is not a real directory")
        if hasattr(os, "getuid"):
            if info.st_uid != os.getuid():
                raise OSError("prerequisite lock root has the wrong owner")
            os.chmod(lock_root, 0o700)
            info = lock_root.lstat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise OSError("prerequisite lock root is not private")
        return lock_root
    except OSError as error:
        raise _prerequisite_busy() from error


@contextmanager
def _pending_transition_lock(root: Path, artifact_id: str):
    """Serialize one artifact's load-to-cleanup prerequisite transition."""
    # Keep the live OS lock outside the repository. Verification snapshots
    # recursively read ordinary marker files, and Windows denies that read
    # while acquire_lock holds its byte-range lock. The resolved repository
    # filesystem identity makes path aliases share a key, while the private
    # per-user namespace prevents another local account from redirecting or
    # pre-seeding the lock sidecar.
    repository_key = _repository_lock_key(root)
    lock_name = _digest(repository_key + b"\0" + artifact_id.encode("utf-8"))
    lock_root = _pending_lock_root()
    handle = acquire_lock(lock_root / lock_name)
    if handle is None:
        raise _prerequisite_busy()
    try:
        yield
    finally:
        release_lock(handle)


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
            raise PrerequisiteError(
                "UNSAFE_PREREQUISITE_PATH",
                "prerequisite state directories must be real directories",
            )
    return current


def _write_new(root: Path, relative: Path, data: bytes) -> None:
    parent = _safe_directory(root, relative.parent, create=True)
    path = parent / relative.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o600)
    completed = False
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        completed = True
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if not completed:
            try:
                path.unlink()
            except OSError:
                pass


def _replace_state(root: Path, relative: Path, value: dict[str, Any]) -> None:
    suffix = secrets.token_hex(8)
    temporary = relative.with_name(f".{relative.name}.{suffix}.tmp")
    _write_new(root, temporary, _canonical(value))
    source = root / temporary
    target = root / relative
    try:
        os.replace(source, target)
        if os.name != "nt":
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        try:
            source.unlink()
        except FileNotFoundError:
            pass


def _publish_new(root: Path, relative: Path, data: bytes) -> None:
    """Publish complete bytes atomically without replacing an existing name."""
    suffix = secrets.token_hex(8)
    temporary = relative.with_name(f".{relative.name}.{suffix}.tmp")
    _write_new(root, temporary, data)
    source = root / temporary
    target = root / relative
    linked = False
    try:
        os.link(source, target)
        linked = True
        if os.name != "nt":
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        try:
            source.unlink()
        except FileNotFoundError:
            pass
    if not linked:
        raise OSError("content-addressed publication did not complete")


def _read_bounded_regular(root: Path, relative: Path, *, limit: int) -> bytes:
    parent = _safe_directory(root, relative.parent, create=False)
    path = parent / relative.name
    info = path.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if (
        stat.S_ISLNK(info.st_mode)
        or reparse
        or not stat.S_ISREG(info.st_mode)
        or info.st_size > limit
    ):
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE",
            "prerequisite state is not bounded regular data",
        )
    data = path.read_bytes()
    if len(data) > limit:
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "prerequisite state exceeds its bound"
        )
    return data


def _identity(client: Any, artifact_id: str) -> dict[str, Any]:
    identity = client.call("identity", {"artifact_id": artifact_id})
    required = {
        "artifact_id": str,
        "kind": str,
        "revision": int,
        "model_sha256": str,
        "normative_sha256": str,
    }
    if any(type(identity.get(key)) is not kind for key, kind in required.items()):
        raise PrerequisiteError("INVALID_IDENTITY", "artifact identity is incomplete")
    if identity["artifact_id"] != artifact_id or identity["kind"] != "plan":
        raise PrerequisiteError("INVALID_IDENTITY", "prerequisites require the exact plan")
    for key in ("model_sha256", "normative_sha256"):
        if SHA256_RE.fullmatch(identity[key]) is None:
            raise PrerequisiteError("INVALID_IDENTITY", f"{key} is malformed")
    return identity


def _approved(client: Any, identity: dict[str, Any]) -> None:
    result = client.call(
        "validate",
        {"artifact_id": identity["artifact_id"], "gate": "approved"},
        permit_invalid=True,
    )
    authority = result.get("authority")
    if (
        result.get("valid") is not True
        or result.get("artifact_id") != identity["artifact_id"]
        or result.get("model_sha256") != identity["model_sha256"]
        or result.get("normative_sha256") != identity["normative_sha256"]
        or not isinstance(authority, dict)
        or authority.get("state") != "approved"
        or authority.get("authority_verified") is not True
    ):
        raise PrerequisiteError(
            "AUTHORITY_UNVERIFIED",
            "only the exact current approved plan can arm a prerequisite",
        )


def _prerequisite_record(
    client: Any, identity: dict[str, Any], prerequisite_id: str
) -> dict[str, Any]:
    result = client.call(
        "read",
        {
            "artifact_id": identity["artifact_id"],
            "symbol": prerequisite_id,
            "mode": "exact",
        },
    )
    if any(result.get(field) != identity[field] for field in (
        "artifact_id", "revision", "model_sha256", "normative_sha256"
    )):
        raise PrerequisiteError("STALE_PREREQUISITE", "prerequisite read changed identity")
    record = result.get("record")
    if (
        not isinstance(record, dict)
        or set(record) != {"id", "title", "requirement", "source_refs"}
        or record.get("id") != prerequisite_id
        or not isinstance(record.get("title"), str)
        or not record["title"]
        or not isinstance(record.get("requirement"), str)
        or not record["requirement"]
        or not isinstance(record.get("source_refs"), list)
        or any(not isinstance(value, str) for value in record["source_refs"])
    ):
        raise PrerequisiteError(
            "UNKNOWN_PREREQUISITE", "symbol is not an exact prerequisite record"
        )
    return record


def _review_packet(identity: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy": POLICY,
        "artifact": {
            key: identity[key]
            for key in (
                "artifact_id", "kind", "revision", "model_sha256", "normative_sha256"
            )
        },
        "prerequisite": record,
    }


def _validate_record(value: Any, prerequisite_id: str) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"id", "title", "requirement", "source_refs"}
        and value.get("id") == prerequisite_id
        and isinstance(value.get("title"), str)
        and bool(value["title"])
        and isinstance(value.get("requirement"), str)
        and bool(value["requirement"])
        and isinstance(value.get("source_refs"), list)
        and all(isinstance(item, str) for item in value["source_refs"])
    )


def _validate_confirmed_state(value: dict[str, Any]) -> None:
    event = value["event"]
    expected_subject = {
        "artifact_id": value["artifact_id"],
        "normative_sha256": value["normative_sha256"],
        "record_id": value["prerequisite_id"],
    }
    expected_payload = {
        "adapter_policy": POLICY,
        "request_id": value["request_id"],
        "review_packet_sha256": value["review_packet_sha256"],
        "prerequisite": value["record"],
    }
    if (
        not isinstance(event, dict)
        or set(event) != {
            "format", "kind", "authority_kind", "subject", "actor", "origin",
            "verdict", "payload", "source_text",
        }
        or event.get("format") != "codearbiter.workflow-event/0.1.0"
        or event.get("kind") != "prerequisite"
        or event.get("authority_kind") != "user_workflow"
        or event.get("subject") != expected_subject
        or event.get("actor") != "interactive repository user"
        or not isinstance(event.get("origin"), str)
        or re.fullmatch(
            r"[A-Za-z0-9_-]{1,32}:UserPromptSubmit:[A-Za-z0-9._:-]{1,256}",
            event["origin"],
        ) is None
        or event.get("verdict") != "satisfied"
        or event.get("payload") != expected_payload
    ):
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE",
            "confirmed event does not match the fixed prerequisite policy",
        )
    match = _match_prompt(event.get("source_text"))
    if (
        match is None
        or match[:2] != (value["artifact_id"], value["prerequisite_id"])
        or not secrets.compare_digest(
            _digest(match[2].encode("ascii")), value["confirmation_sha256"]
        )
    ):
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE",
            "confirmed source text does not match the armed request",
        )
    expected_source = (
        SOURCE_DIR / f"{_digest(_canonical(event))}.json"
    ).as_posix()
    if value["authority_source"] != expected_source:
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE",
            "confirmed authority source does not match the event",
        )


def _expected_mutation_request(value: dict[str, Any]) -> dict[str, Any]:
    operation_suffix = _digest(value["request_id"].encode("ascii"))[:24]
    return {
        "artifact_id": value["artifact_id"],
        "operation_id": f"host-user-prerequisite-{operation_suffix}",
        "expected": {
            "revision": value["revision"],
            "model_sha256": value["model_sha256"],
        },
        "prerequisite": value["prerequisite_id"],
        "receipt": value["receipt"],
    }


def _load_pending(root: Path, artifact_id: str) -> dict[str, Any] | None:
    relative = _pending_relative(artifact_id)
    try:
        raw = _read_bounded_regular(root, relative, limit=65536)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "prerequisite state is unreadable"
        ) from exc
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "prerequisite state is invalid JSON"
        ) from exc
    if not isinstance(value, dict) or set(value) != STATE_FIELDS:
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "prerequisite state shape is invalid"
        )
    if (
        value["format"] != FORMAT
        or value["state"] not in STATES
        or value["artifact_id"] != artifact_id
        or any(not isinstance(value[key], str) or not value[key] for key in (
            "request_id", "artifact_id", "prerequisite_id", "kind",
            "model_sha256", "normative_sha256", "review_packet_sha256",
            "confirmation_sha256",
        ))
        or type(value["revision"]) is not int
        or type(value["issued_at"]) is not int
        or type(value["expires_at"]) is not int
        or value["expires_at"] <= value["issued_at"]
        or any(SHA256_RE.fullmatch(value[key]) is None for key in (
            "model_sha256", "normative_sha256", "review_packet_sha256", "confirmation_sha256"
        ))
        or not _validate_record(value["record"], value["prerequisite_id"])
    ):
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "prerequisite state values are invalid"
        )
    if value["state"] == "ARMED":
        if any(value[key] is not None for key in (
            "event", "authority_source", "receipt", "mutation_request"
        )):
            raise PrerequisiteError(
                "INVALID_PENDING_PREREQUISITE", "armed state contains later-phase data"
            )
    elif value["state"] == "CONFIRMED":
        if (
            not isinstance(value["event"], dict)
            or not isinstance(value["authority_source"], str)
            or value["receipt"] is not None
            or value["mutation_request"] is not None
        ):
            raise PrerequisiteError(
                "INVALID_PENDING_PREREQUISITE", "confirmed state is incomplete"
            )
        _validate_confirmed_state(value)
    elif (
        not isinstance(value["event"], dict)
        or not isinstance(value["authority_source"], str)
        or not isinstance(value["receipt"], str)
        or RECEIPT_RE.fullmatch(value["receipt"]) is None
        or not isinstance(value["mutation_request"], dict)
    ):
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "captured state is incomplete"
        )
    else:
        _validate_confirmed_state(value)
        if value["mutation_request"] != _expected_mutation_request(value):
            raise PrerequisiteError(
                "INVALID_PENDING_PREREQUISITE",
                "captured mutation request does not match the confirmed decision",
            )
    return value


def arm_user_prerequisite(
    root: str | Path,
    client: Any,
    artifact_id: str,
    prerequisite_id: str,
    *,
    confirmation_nonce: str | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    if ID_RE.fullmatch(artifact_id) is None or ID_RE.fullmatch(prerequisite_id) is None:
        raise PrerequisiteError("INVALID_PREREQUISITE", "artifact and prerequisite IDs are invalid")
    identity = _identity(client, artifact_id)
    _approved(client, identity)
    record = _prerequisite_record(client, identity, prerequisite_id)
    final_identity = _identity(client, artifact_id)
    if final_identity != identity:
        raise PrerequisiteError("STALE_PREREQUISITE", "plan changed while arming")
    _approved(client, final_identity)
    packet_sha256 = _digest(_canonical(_review_packet(identity, record)))
    confirmation_nonce = confirmation_nonce or secrets.token_urlsafe(32)
    if CONFIRMATION_RE.fullmatch(confirmation_nonce) is None:
        raise PrerequisiteError(
            "INVALID_CONFIRMATION", "prerequisite confirmation nonce has an invalid shape"
        )
    issued_at = int(time.time()) if now is None else now
    if type(issued_at) is not int or issued_at < 0:
        raise PrerequisiteError("INVALID_TIME", "prerequisite issue time is invalid")
    request_id = secrets.token_urlsafe(18)
    pending = {
        "format": FORMAT,
        "state": "ARMED",
        "request_id": request_id,
        "artifact_id": artifact_id,
        "prerequisite_id": prerequisite_id,
        "kind": identity["kind"],
        "revision": identity["revision"],
        "model_sha256": identity["model_sha256"],
        "normative_sha256": identity["normative_sha256"],
        "record": record,
        "review_packet_sha256": packet_sha256,
        "confirmation_sha256": _digest(confirmation_nonce.encode("ascii")),
        "issued_at": issued_at,
        "expires_at": issued_at + CONFIRMATION_LIFETIME_SECONDS,
        "event": None,
        "authority_source": None,
        "receipt": None,
        "mutation_request": None,
    }
    relative = _pending_relative(artifact_id)
    try:
        _write_new(root, relative, _canonical(pending))
    except FileExistsError as exc:
        raise PrerequisiteError(
            "PENDING_PREREQUISITE",
            "resolve or cancel this plan's existing prerequisite request first",
        ) from exc
    return {
        "artifact_id": artifact_id,
        "prerequisite_id": prerequisite_id,
        "title": record["title"],
        "requirement": record["requirement"],
        "review_packet_sha256": packet_sha256,
        "reply": (
            f"satisfy-prerequisite {artifact_id} {prerequisite_id} "
            f"{confirmation_nonce}"
        ),
        "pending": relative.as_posix(),
    }


def _match_prompt(prompt: Any) -> tuple[str, str, str] | None:
    if not isinstance(prompt, str):
        return None
    parts = prompt.split(" ")
    if (
        len(parts) != 4
        or parts[0] != "satisfy-prerequisite"
        or ID_RE.fullmatch(parts[1]) is None
        or ID_RE.fullmatch(parts[2]) is None
        or CONFIRMATION_RE.fullmatch(parts[3]) is None
    ):
        return None
    return parts[1], parts[2], parts[3]


def _confirm(
    root: Path,
    client: Any,
    pending: dict[str, Any],
    prompt: str,
    *,
    host: str,
    session_id: str,
    now: int,
) -> dict[str, Any]:
    if now > pending["expires_at"]:
        raise PrerequisiteError(
            "EXPIRED_PREREQUISITE", "the prerequisite confirmation request expired"
        )
    if not HOST_RE.fullmatch(host) or not SESSION_RE.fullmatch(session_id):
        raise PrerequisiteError("INVALID_HOST_CONTEXT", "host prerequisite context is malformed")
    current = _identity(client, pending["artifact_id"])
    for field in ("kind", "revision", "model_sha256", "normative_sha256"):
        if current[field] != pending[field]:
            raise PrerequisiteError(
                "STALE_PREREQUISITE", "plan changed after prerequisite review was armed"
            )
    _approved(client, current)
    record = _prerequisite_record(client, current, pending["prerequisite_id"])
    packet_sha256 = _digest(_canonical(_review_packet(current, record)))
    if record != pending["record"] or packet_sha256 != pending["review_packet_sha256"]:
        raise PrerequisiteError(
            "STALE_PREREQUISITE", "prerequisite definition changed after review was armed"
        )
    event = {
        "format": "codearbiter.workflow-event/0.1.0",
        "kind": "prerequisite",
        "authority_kind": "user_workflow",
        "subject": {
            "artifact_id": current["artifact_id"],
            "normative_sha256": current["normative_sha256"],
            "record_id": pending["prerequisite_id"],
        },
        "actor": "interactive repository user",
        "origin": f"{host}:UserPromptSubmit:{session_id}",
        "verdict": "satisfied",
        "payload": {
            "adapter_policy": POLICY,
            "request_id": pending["request_id"],
            "review_packet_sha256": pending["review_packet_sha256"],
            "prerequisite": pending["record"],
        },
        "source_text": prompt,
    }
    event_bytes = _canonical(event)
    source_rel = SOURCE_DIR / f"{_digest(event_bytes)}.json"
    confirmed = dict(pending)
    confirmed.update(
        state="CONFIRMED",
        event=event,
        authority_source=source_rel.as_posix(),
    )
    _replace_state(root, _pending_relative(pending["artifact_id"]), confirmed)
    return confirmed


def _publish_event(root: Path, pending: dict[str, Any]) -> tuple[str, str]:
    event_bytes = _canonical(pending["event"])
    digest = _digest(event_bytes)
    source_rel = SOURCE_DIR / f"{digest}.json"
    if pending["authority_source"] != source_rel.as_posix():
        raise PrerequisiteError(
            "INVALID_PENDING_PREREQUISITE", "authority source does not match the event"
        )
    try:
        _publish_new(root, source_rel, event_bytes)
    except FileExistsError:
        try:
            existing = _read_bounded_regular(root, source_rel, limit=65536)
        except (FileNotFoundError, OSError) as exc:
            raise PrerequisiteError(
                "INVALID_AUTHORITY_SOURCE", "authority source is unreadable"
            ) from exc
        if existing != event_bytes:
            raise PrerequisiteError(
                "INVALID_AUTHORITY_SOURCE", "content-addressed source differs"
            )
    return source_rel.as_posix(), digest


def consume_user_prerequisite(
    root: str | Path,
    client: Any,
    prompt: str,
    *,
    host: str,
    session_id: str,
    now: int | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    match = _match_prompt(prompt)
    if match is None:
        return {"matched": False, "satisfied": False}
    artifact_id, prerequisite_id, confirmation_nonce = match
    if not (root / _pending_relative(artifact_id)).exists():
        return {"matched": False, "satisfied": False}
    with _pending_transition_lock(root, artifact_id):
        pending = _load_pending(root, artifact_id)
        if pending is None or pending["prerequisite_id"] != prerequisite_id:
            return {"matched": False, "satisfied": False}
        if not secrets.compare_digest(
            _digest(confirmation_nonce.encode("ascii")), pending["confirmation_sha256"]
        ):
            return {"matched": False, "satisfied": False}
        observed_at = int(time.time()) if now is None else now
        if type(observed_at) is not int or observed_at < 0:
            raise PrerequisiteError("INVALID_TIME", "prerequisite confirmation time is invalid")
        if pending["state"] == "ARMED":
            pending = _confirm(
                root,
                client,
                pending,
                prompt,
                host=host,
                session_id=session_id,
                now=observed_at,
            )
        source_ref, source_sha256 = _publish_event(root, pending)
        if pending["state"] == "CONFIRMED":
            captured = client.call(
                "capture",
                {"source_ref": source_ref, "source_sha256": source_sha256},
            )
            receipt = captured.get("receipt")
            if not isinstance(receipt, str) or RECEIPT_RE.fullmatch(receipt) is None:
                raise PrerequisiteError("INVALID_RECEIPT", "capture returned no valid receipt")
            operation_suffix = _digest(pending["request_id"].encode("ascii"))[:24]
            mutation_request = {
                "artifact_id": pending["artifact_id"],
                "operation_id": f"host-user-prerequisite-{operation_suffix}",
                "expected": {
                    "revision": pending["revision"],
                    "model_sha256": pending["model_sha256"],
                },
                "prerequisite": pending["prerequisite_id"],
                "receipt": receipt,
            }
            captured_state = dict(pending)
            captured_state.update(
                state="CAPTURED", receipt=receipt, mutation_request=mutation_request
            )
            _replace_state(root, _pending_relative(artifact_id), captured_state)
            pending = captured_state
        result = client.call("prerequisite", pending["mutation_request"])
        (root / _pending_relative(artifact_id)).unlink()
        return {
            "matched": True,
            "satisfied": True,
            "artifact_id": artifact_id,
            "prerequisite_id": prerequisite_id,
            "authority_source": source_ref,
            "receipt": pending["receipt"],
            "revision": result.get("revision"),
            "replayed": bool((result.get("transaction") or {}).get("replayed")),
        }


def cancel_user_prerequisite(
    root: str | Path, artifact_id: str, prerequisite_id: str
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    if not (root / _pending_relative(artifact_id)).exists():
        raise PrerequisiteError(
            "NO_PENDING_PREREQUISITE", "there is no prerequisite request to cancel"
        )
    with _pending_transition_lock(root, artifact_id):
        pending = _load_pending(root, artifact_id)
        if pending is None:
            raise PrerequisiteError(
                "NO_PENDING_PREREQUISITE", "there is no prerequisite request to cancel"
            )
        if pending["prerequisite_id"] != prerequisite_id:
            raise PrerequisiteError(
                "PENDING_PREREQUISITE_MISMATCH",
                "the pending request belongs to another prerequisite",
            )
        if pending["state"] != "ARMED":
            raise PrerequisiteError(
                "PREREQUISITE_RECOVERY_REQUIRED",
                "a confirmed prerequisite decision must be recovered, not cancelled",
            )
        (root / _pending_relative(artifact_id)).unlink()
        return {
            "artifact_id": artifact_id,
            "prerequisite_id": prerequisite_id,
            "cancelled": True,
        }


def supersede_user_prerequisite(
    root: str | Path,
    client: Any,
    artifact_id: str,
    prerequisite_id: str,
) -> dict[str, Any]:
    """Clear a confirmed stale request after excluding a committed replay."""
    root = Path(root).resolve(strict=True)
    if not (root / _pending_relative(artifact_id)).exists():
        raise PrerequisiteError(
            "NO_PENDING_PREREQUISITE", "there is no prerequisite request to supersede"
        )
    with _pending_transition_lock(root, artifact_id):
        pending = _load_pending(root, artifact_id)
        if pending is None:
            raise PrerequisiteError(
                "NO_PENDING_PREREQUISITE", "there is no prerequisite request to supersede"
            )
        if pending["prerequisite_id"] != prerequisite_id:
            raise PrerequisiteError(
                "PENDING_PREREQUISITE_MISMATCH",
                "the pending request belongs to another prerequisite",
            )
        if pending["state"] == "ARMED":
            raise PrerequisiteError(
                "PREREQUISITE_NOT_CONFIRMED",
                "an unconfirmed request should be cancelled, not superseded",
            )
        current = _identity(client, artifact_id)
        if all(current[field] == pending[field] for field in (
            "kind", "revision", "model_sha256", "normative_sha256"
        )):
            raise PrerequisiteError(
                "PREREQUISITE_STILL_CURRENT",
                "the confirmed request still matches the current plan identity",
            )
        if pending["state"] == "CAPTURED":
            try:
                result = client.call("prerequisite", pending["mutation_request"])
            except _artifactlib.ArtifactError as exc:
                if exc.code != "REVISION_CONFLICT":
                    raise
            else:
                (root / _pending_relative(artifact_id)).unlink()
                return {
                    "artifact_id": artifact_id,
                    "prerequisite_id": prerequisite_id,
                    "superseded": False,
                    "satisfied": True,
                    "receipt": pending["receipt"],
                    "revision": result.get("revision"),
                    "replayed": bool((result.get("transaction") or {}).get("replayed")),
                }
        (root / _pending_relative(artifact_id)).unlink()
        return {
            "artifact_id": artifact_id,
            "prerequisite_id": prerequisite_id,
            "superseded": True,
            "satisfied": False,
            "authority_source": pending["authority_source"],
            "receipt": pending["receipt"],
        }


def consume_from_hook(
    *,
    root: str | Path,
    plugin_root: str | Path,
    prompt: str,
    host: str,
    session_id: str,
) -> str:
    attempted = isinstance(prompt, str) and prompt.startswith("satisfy-prerequisite")
    match = _match_prompt(prompt)
    if match is None:
        return (
            "codeArbiter: prerequisite capture failed: exact confirmation syntax required"
            if attempted
            else ""
        )
    if not (Path(root) / _pending_relative(match[0])).exists():
        return (
            "codeArbiter: prerequisite capture failed: no matching armed request"
            if attempted
            else ""
        )
    try:
        client = _artifactlib.ArtifactClient(
            root, Path(plugin_root) / "helpers" / "artifacts"
        )
        result = consume_user_prerequisite(
            root, client, prompt, host=host, session_id=session_id
        )
    except (PrerequisiteError, _artifactlib.ArtifactError, OSError) as exc:
        return f"codeArbiter: prerequisite capture failed: {exc}"
    if not result.get("satisfied"):
        return "codeArbiter: prerequisite capture failed: confirmation did not match"
    return (
        "codeArbiter: workflow prerequisite recorded for "
        f"{result['artifact_id']}#{result['prerequisite_id']} "
        f"(receipt {result['receipt']})."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    arm = sub.add_parser("arm")
    arm.add_argument("--root", required=True)
    arm.add_argument("--artifact-id", required=True)
    arm.add_argument("--prerequisite-id", required=True)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("--root", required=True)
    cancel.add_argument("--artifact-id", required=True)
    cancel.add_argument("--prerequisite-id", required=True)
    supersede = sub.add_parser("supersede")
    supersede.add_argument("--root", required=True)
    supersede.add_argument("--artifact-id", required=True)
    supersede.add_argument("--prerequisite-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "cancel":
        print(json.dumps(cancel_user_prerequisite(
            args.root, args.artifact_id, args.prerequisite_id
        )))
        return 0
    client = _artifactlib.ArtifactClient(
        args.root, _artifactlib.helper_installation(__file__)
    )
    if args.command == "supersede":
        print(json.dumps(supersede_user_prerequisite(
            args.root, client, args.artifact_id, args.prerequisite_id
        )))
        return 0
    print(json.dumps(arm_user_prerequisite(
        args.root, client, args.artifact_id, args.prerequisite_id
    )))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PrerequisiteError, _artifactlib.ArtifactError) as exc:
        sys.stderr.write(str(exc) + "\n")
        raise SystemExit(1)
