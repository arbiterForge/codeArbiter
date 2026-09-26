#!/usr/bin/env python3
# codeArbiter — cross-repository routing for exact artifact authority prompts.
"""Register and resolve target repositories without granting prompt authority."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

import _replylib


REGISTRY_PARENT = Path(tempfile.gettempdir())
FORMAT = "codearbiter.artifact-prompt-route/0.1.0"


class PromptRouteError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    info = root.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise PromptRouteError("artifact prompt target is not a real directory")
    return {
        "path": str(root),
        "filesystem_id": f"{int(getattr(info, 'st_dev', 0))}:{int(getattr(info, 'st_ino', 0))}",
    }


def _registry() -> Path:
    namespace = f"uid-{os.getuid()}" if hasattr(os, "getuid") else "current-user"
    root = REGISTRY_PARENT.resolve(strict=True) / f"codearbiter-prompt-routes-{namespace}"
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise PromptRouteError("artifact prompt registry is unsafe")
    if hasattr(os, "getuid"):
        if info.st_uid != os.getuid():
            raise PromptRouteError("artifact prompt registry has another owner")
        os.chmod(root, 0o700)
    return root


def _key(route: str, artifact_id: str, repository: dict[str, str]) -> str:
    return _digest(_canonical({"route": route, "artifact_id": artifact_id, "repository": repository}))


def register(root: str | Path, route: str, artifact_id: str, prompt: str,
             *, binding_sha256: str | None = None) -> None:
    if route not in {"approval", "prerequisite", "reconciliation"} or not isinstance(prompt, str) or not prompt:
        raise PromptRouteError("artifact prompt route is invalid")
    if binding_sha256 is not None and (
        not isinstance(binding_sha256, str)
        or len(binding_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in binding_sha256)
    ):
        raise PromptRouteError("artifact prompt binding is invalid")
    repository = _identity(Path(root))
    value = {
        "format": FORMAT,
        "route": route,
        "artifact_id": artifact_id,
        "prompt_sha256": _digest(prompt.encode("utf-8")),
        "repository": repository,
    }
    if binding_sha256 is not None:
        value["binding_sha256"] = binding_sha256
    value["integrity_sha256"] = _digest(_canonical(value))
    registry = _registry()
    key = _key(route, artifact_id, repository)
    path = registry / f"{key}.json"
    data = _canonical(value)
    # Each caller owns an exclusively created pending marker before registering.
    # A prior route at this key therefore belongs to an interrupted request.
    fd, temporary = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=registry)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short prompt-route write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def resolve(route: str, prompt: str) -> Path | None:
    if route not in {"approval", "prerequisite", "reconciliation"} or not isinstance(prompt, str):
        return None
    prompt_hash = _digest(prompt.encode("utf-8"))
    matches = []
    for path in _registry().glob("*.json"):
        try:
            raw = path.read_bytes()
            if len(raw) > 16384:
                continue
            value = json.loads(raw.decode("utf-8"))
            unsigned = dict(value)
            integrity = unsigned.pop("integrity_sha256", None)
            repository = value.get("repository")
            if (
                value.get("format") != FORMAT
                or value.get("route") != route
                or value.get("prompt_sha256") != prompt_hash
                or integrity != _digest(_canonical(unsigned))
                or not isinstance(repository, dict)
            ):
                continue
            root = Path(repository.get("path", ""))
            if _identity(root) != repository:
                continue
            matches.append(root.resolve(strict=True))
        except (OSError, UnicodeError, ValueError, PromptRouteError):
            continue
    unique = {str(path): path for path in matches}
    if len(unique) > 1:
        raise PromptRouteError("artifact authority prompt matches multiple repositories")
    return next(iter(unique.values()), None)


def unregister(root: str | Path, route: str, artifact_id: str) -> None:
    repository = _identity(Path(root))
    path = _registry() / f"{_key(route, artifact_id, repository)}.json"
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    # A request's short reply code dies with its route.
    _replylib.retire_code(root, route, artifact_id)


def binding(root: str | Path, route: str, artifact_id: str) -> str | None:
    repository = _identity(Path(root))
    path = _registry() / f"{_key(route, artifact_id, repository)}.json"
    try:
        raw = path.read_bytes()
        if len(raw) > 16384:
            raise OSError("oversized prompt route")
        value = json.loads(raw.decode("utf-8"))
        unsigned = dict(value)
        integrity = unsigned.pop("integrity_sha256", None)
    except (OSError, UnicodeError, ValueError) as exc:
        raise PromptRouteError("artifact prompt route is unreadable") from exc
    if (
        value.get("format") != FORMAT
        or value.get("route") != route
        or value.get("artifact_id") != artifact_id
        or value.get("repository") != repository
        or integrity != _digest(_canonical(unsigned))
    ):
        raise PromptRouteError("artifact prompt route is malformed")
    result = value.get("binding_sha256")
    if not isinstance(result, str) or len(result) != 64 or any(
        ch not in "0123456789abcdef" for ch in result
    ):
        raise PromptRouteError("artifact prompt route has no closed binding")
    return result
