#!/usr/bin/env python3
"""Validate, capture, and install repository-reviewed Pi host dependency locks."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import date
from typing import Any
from urllib.parse import quote, urlsplit


PACKAGE = "@earendil-works/pi-coding-agent"
REGISTRY = "https://registry.npmjs.org"
REGISTRY_ARGS = (f"--registry={REGISTRY}", f"--@earendil-works:registry={REGISTRY}")
SUPPORTED = ("0.84.1",)
LOCK_ROOT = Path(".github/fixtures/pi-hosts")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SOURCE_REPOSITORY = "https://github.com/earendil-works/pi"
ZERO_AUDIT = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "total": 0}
REVIEW_FIELDS = {
    "schema", "package", "version", "registry", "root_integrity", "lock_sha256",
    "source_repository", "source_tag", "source_commit", "reviewed_at", "reviewer",
    "licenses", "audits", "lifecycle_scripts", "signatures", "provenance", "result",
}
CANDIDATE_FIELDS = {
    "schema", "package", "version", "registry", "root_integrity", "lock_sha256",
    "source_repository", "source_commit", "result",
}
NPM_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "PROGRAMW6432",
}
MAX_METADATA_PACKAGES = 1024
MAX_METADATA_DEPTH = 64
MAX_METADATA_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_METADATA_QUERY_SECONDS = 30
MAX_METADATA_WALK_SECONDS = 600
MAX_LOCK_GENERATION_SECONDS = 120
MAX_METADATA_CACHE_BYTES = 512 * 1024 * 1024
MAX_CACHE_ADD_SECONDS = 60
MAX_ARCHIVE_MEMBERS = 10000
MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"reviewed host graph is unreadable: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"reviewed host graph must be a JSON object: {path}")
    return value


def _approved_registry_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "registry.npmjs.org"
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith("/")
    )


def _registry_dependency(specification: Any) -> tuple[str | None, str]:
    if not isinstance(specification, str) or not specification.strip():
        raise ValueError("candidate dependency specification is not a registry version")
    value = specification.strip()
    lowered = value.lower()
    forbidden = (
        "file:", "git:", "git+", "http:", "https:", "ssh:", "github:",
        "gitlab:", "bitbucket:", "workspace:", "link:", "./", "../", "/", "\\",
    )
    if lowered.startswith(forbidden) or "/" in value and not value.startswith("npm:@"):
        raise ValueError(f"candidate dependency specification is not registry-only: {value}")
    if value.startswith("npm:"):
        alias = value[4:]
        if alias.startswith("@"):
            separator = alias.find("@", 1)
        else:
            separator = alias.rfind("@")
        if separator <= 0:
            raise ValueError(f"candidate dependency specification is not a valid registry alias: {value}")
        package_name = alias[:separator]
        if PACKAGE_NAME.fullmatch(package_name) is None:
            raise ValueError(f"candidate dependency specification has an invalid registry alias: {value}")
        nested = alias[separator + 1:]
        _, nested_spec = _registry_dependency(nested)
        return package_name, nested_spec
    return None, value


def _metadata_record(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        if not raw:
            raise ValueError("candidate registry metadata returned no matching version")
        raw = raw[-1]
    if not isinstance(raw, dict):
        raise ValueError("candidate registry metadata is not an object")
    if not _approved_registry_url(raw.get("dist.tarball")):
        raise ValueError("candidate registry metadata has an unapproved tarball source")
    if not str(raw.get("dist.integrity", "")).startswith("sha512-"):
        raise ValueError("candidate registry metadata has no SHA-512 integrity")
    return raw


def _read_response_chunk(
    response: Any, deadline: float, max_seconds: float, limit: int, message: str,
) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError(message)
    stream = getattr(response, "fp", None)
    raw = getattr(stream, "raw", None)
    sock = getattr(raw, "_sock", None)
    if sock is not None:
        sock.settimeout(max(0.001, min(max_seconds, remaining)))
    reader = getattr(response, "read1", response.read)
    chunk = reader(min(64 * 1024, limit))
    if time.monotonic() >= deadline:
        raise ValueError(message)
    return chunk


def _fetch_registry_packument(package_name: str, deadline: float) -> dict[str, Any]:
    if PACKAGE_NAME.fullmatch(package_name) is None:
        raise ValueError(f"candidate registry metadata has an invalid package name: {package_name}")
    last_error: OSError | http.client.HTTPException | None = None
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("candidate registry metadata exceeded the aggregate time budget")
        try:
            connection = http.client.HTTPSConnection(
                "registry.npmjs.org", timeout=min(MAX_METADATA_QUERY_SECONDS, remaining),
            )
            try:
                connection.request(
                    "GET", "/" + quote(package_name, safe="@"),
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "codeArbiter-pi-host-lock/1",
                    },
                )
                response = connection.getresponse()
                if response.status != 200:
                    raise ValueError(f"candidate registry metadata returned HTTP {response.status}")
                length = response.getheader("Content-Length")
                if length is not None and int(length) > MAX_METADATA_OUTPUT_BYTES:
                    raise ValueError("candidate registry metadata exceeded the output limit")
                chunks: list[bytes] = []
                size = 0
                while True:
                    if time.monotonic() >= deadline:
                        raise ValueError("candidate registry metadata exceeded the aggregate time budget")
                    chunk = _read_response_chunk(
                        response, deadline, MAX_METADATA_QUERY_SECONDS,
                        MAX_METADATA_OUTPUT_BYTES + 1 - size,
                        "candidate registry metadata exceeded the aggregate time budget",
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_METADATA_OUTPUT_BYTES:
                        raise ValueError("candidate registry metadata exceeded the output limit")
                value = json.loads(b"".join(chunks).decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("candidate registry metadata is not an object")
                return value
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as error:
            last_error = error
            if attempt < 2:
                delay = 0.25 * (attempt + 1)
                if time.monotonic() + delay >= deadline:
                    raise ValueError("candidate registry metadata exceeded the aggregate time budget") from error
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def _npm_semver_module(npm: str) -> Path:
    npm_path = Path(npm).resolve()
    if npm_path.name.lower() not in {"npm-cli.js", "npm-cli"}:
        prefix = _npm_command_prefix(npm)
        if len(prefix) == 2:
            npm_path = Path(prefix[1]).resolve()
    candidates = [
        npm_path.parent.parent / "node_modules" / "semver",
        npm_path.parent / "node_modules" / "semver",
    ]
    for candidate in candidates:
        if (candidate / "package.json").is_file():
            return candidate
    raise ValueError("npm's bundled semver module is unavailable")


def _select_registry_version(
    npm: str, specification: str, packument: dict[str, Any],
    environment: dict[str, str], deadline: float,
) -> str:
    versions = packument.get("versions")
    tags = packument.get("dist-tags", {})
    if not isinstance(versions, dict) or not isinstance(tags, dict):
        raise ValueError("candidate registry metadata has no version inventory")
    if VERSION.fullmatch(specification):
        selected = specification
    elif specification in tags:
        selected = tags[specification]
    else:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("candidate registry metadata exceeded the aggregate time budget")
        module = _npm_semver_module(npm)
        node = shutil.which("node") or "node"
        script = (
            "const fs=require('fs'),s=require(process.argv[1]);"
            "const v=JSON.parse(fs.readFileSync(0,'utf8'));"
            "const r=s.maxSatisfying(v,process.argv[2],{includePrerelease:false});"
            "if(!r)process.exit(2);process.stdout.write(r)"
        )
        completed = subprocess.run(
            [node, "-e", script, str(module), specification],
            input=json.dumps(list(versions)), capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=min(MAX_METADATA_QUERY_SECONDS, remaining), env=environment,
        )
        selected = completed.stdout.strip()
    if not isinstance(selected, str) or VERSION.fullmatch(selected) is None or selected not in versions:
        raise ValueError("candidate registry metadata returned no matching exact version")
    return selected


def _run_registry_metadata(
    npm: str, package_name: str, specification: str,
    environment: dict[str, str], deadline: float,
) -> Any:
    packument = _fetch_registry_packument(package_name, deadline)
    selected = _select_registry_version(npm, specification, packument, environment, deadline)
    record = packument["versions"][selected]
    if not isinstance(record, dict) or not isinstance(record.get("dist"), dict):
        raise ValueError("candidate registry metadata version is malformed")
    repository = record.get("repository")
    repository_url = repository.get("url") if isinstance(repository, dict) else repository
    if isinstance(repository_url, str):
        repository_url = repository_url.removeprefix("git+").removesuffix(".git")
    return {
        "version": selected,
        "dist.integrity": record["dist"].get("integrity"),
        "dist.tarball": record["dist"].get("tarball"),
        "repository.url": repository_url,
        "gitHead": record.get("gitHead"),
        "dependencies": record.get("dependencies", {}),
        "optionalDependencies": record.get("optionalDependencies", {}),
        "peerDependencies": record.get("peerDependencies", {}),
        "peerDependenciesMeta": record.get("peerDependenciesMeta", {}),
    }


def resolve_candidate(specification: str) -> dict[str, str]:
    _, safe_specification = _registry_dependency(specification)
    npm = shutil.which("npm") or "npm"
    with tempfile.TemporaryDirectory(prefix="ca-pi-resolve-") as raw:
        environment = _npm_environment(Path(raw), os.environ)
        metadata = _metadata_record(_run_registry_metadata(
            npm, PACKAGE, safe_specification, environment,
            time.monotonic() + MAX_METADATA_WALK_SECONDS,
        ))
    version = metadata.get("version")
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise ValueError("candidate registry metadata did not resolve an exact stable version")
    return {"package": PACKAGE, "version": version}


def _npm_command_prefix(npm: str) -> list[str]:
    npm_path = Path(npm)
    if npm_path.suffix.lower() not in {".cmd", ".bat"}:
        return [npm]
    cli = npm_path.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not cli.is_file():
        raise ValueError(f"npm CLI entry point is unavailable beside the Windows wrapper: {cli}")
    node = shutil.which("node") or str(npm_path.parent / "node.exe")
    return [node, str(cli)]


def _preflight_registry_graph(
    npm: str, version: str, cache: Path, environment: dict[str, str], *, deadline: float | None = None,
    resolved: list[tuple[str, str, str, str]] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_METADATA_WALK_SECONDS if deadline is None else deadline
    pending = [(PACKAGE, version, 0)]
    visited: set[tuple[str, str]] = set()
    root: dict[str, Any] | None = None
    while pending:
        if time.monotonic() >= deadline:
            raise ValueError("candidate registry metadata exceeded the aggregate time budget")
        package_name, specification, depth = pending.pop()
        if depth > MAX_METADATA_DEPTH:
            raise ValueError("candidate registry metadata exceeded the depth limit")
        alias_name, safe_specification = _registry_dependency(specification)
        resolved_name = alias_name or package_name
        if PACKAGE_NAME.fullmatch(resolved_name) is None:
            raise ValueError(f"candidate registry metadata has an invalid package name: {resolved_name}")
        identity = (resolved_name, safe_specification)
        if identity in visited:
            continue
        if len(visited) >= MAX_METADATA_PACKAGES:
            raise ValueError("candidate registry metadata exceeded the package count limit")
        metadata = _metadata_record(_run_registry_metadata(
            npm, resolved_name, safe_specification, environment, deadline,
        ))
        exact_version = metadata.get("version")
        if not isinstance(exact_version, str) or VERSION.fullmatch(exact_version) is None:
            raise ValueError("candidate registry metadata did not resolve an exact stable version")
        if resolved is not None:
            resolved.append((
                resolved_name,
                exact_version,
                metadata["dist.tarball"],
                metadata["dist.integrity"],
            ))
        visited.add(identity)
        if root is None:
            root = metadata
        optional_dependencies = metadata.get("optionalDependencies", {}) or {}
        peer_metadata = metadata.get("peerDependenciesMeta", {}) or {}
        if not isinstance(optional_dependencies, dict) or not isinstance(peer_metadata, dict):
            raise ValueError("candidate registry metadata optional dependency controls are not objects")
        for field in ("dependencies", "optionalDependencies", "peerDependencies"):
            dependencies = metadata.get(field, {})
            if dependencies is None:
                continue
            if not isinstance(dependencies, dict):
                raise ValueError(f"candidate registry metadata {field} is not an object")
            for child_name, child_specification in dependencies.items():
                if not isinstance(child_name, str) or PACKAGE_NAME.fullmatch(child_name) is None:
                    raise ValueError(f"candidate registry metadata {field} has an invalid package name")
                pending.append((child_name, child_specification, depth + 1))
    if root is None:
        raise ValueError("candidate registry metadata preflight returned no root package")
    return root


def _seed_registry_cache(
    npm: str, packages: list[tuple[str, str, str, str]], cache: Path,
    environment: dict[str, str], deadline: float,
) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ca-pi-tarballs-", dir=cache.parent) as raw_downloads:
        download_root = Path(raw_downloads)
        for index, (package_name, version, tarball, integrity) in enumerate(packages):
            if (
                PACKAGE_NAME.fullmatch(package_name) is None
                or VERSION.fullmatch(version) is None
                or not _approved_registry_url(tarball)
                or not integrity.startswith("sha512-")
            ):
                raise ValueError("candidate registry cache seed is not bound to validated metadata")
            archive = download_root / f"{index}.tgz"
            command = [
                *_npm_command_prefix(npm), "cache", "add", str(archive), "--ignore-scripts",
                *REGISTRY_ARGS, "--cache", str(cache),
            ]
            last_error: OSError | http.client.HTTPException | subprocess.CalledProcessError | subprocess.TimeoutExpired | None = None
            for attempt in range(3):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("candidate registry cache seed exceeded the aggregate time budget")
                cache_bytes = sum(path.stat().st_size for path in cache.rglob("*") if path.is_file())
                byte_budget = MAX_METADATA_CACHE_BYTES - cache_bytes
                if byte_budget <= 0:
                    raise ValueError("candidate registry cache exceeded the byte limit")
                try:
                    try:
                        _download_registry_tarball(
                            package_name, version, tarball, integrity, archive,
                            deadline=deadline, byte_budget=byte_budget,
                        )
                    except ValueError as error:
                        raise ValueError(
                            f"candidate registry cache seed rejected {package_name}@{version}: {error}"
                        ) from error
                    subprocess.run(
                        command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=min(MAX_CACHE_ADD_SECONDS, remaining), env=environment,
                    )
                    last_error = None
                    break
                except (OSError, http.client.HTTPException, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    last_error = error
                    if attempt < 2:
                        delay = 0.25 * (attempt + 1)
                        if time.monotonic() + delay >= deadline:
                            raise ValueError("candidate registry cache seed exceeded the aggregate time budget") from error
                        time.sleep(delay)
            if last_error is not None:
                raise last_error
            archive.unlink(missing_ok=True)
            cache_bytes = sum(path.stat().st_size for path in cache.rglob("*") if path.is_file())
            if cache_bytes > MAX_METADATA_CACHE_BYTES:
                raise ValueError("candidate registry cache exceeded the byte limit")


class _DeadlineReader:
    def __init__(self, stream: Any, deadline: float, message: str):
        self.stream = stream
        self.deadline = deadline
        self.message = message

    def read(self, size: int = -1) -> bytes:
        if time.monotonic() >= self.deadline:
            raise ValueError(self.message)
        bounded = 64 * 1024 if size < 0 else min(size, 64 * 1024)
        value = self.stream.read(bounded)
        if time.monotonic() >= self.deadline:
            raise ValueError(self.message)
        return value


def _read_archive_json(archive: tarfile.TarFile, member: tarfile.TarInfo, deadline: float) -> Any:
    if member.size > MAX_METADATA_OUTPUT_BYTES:
        raise ValueError("candidate tarball package metadata exceeded the output limit")
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError("candidate tarball has no valid package metadata")
    chunks = []
    size = 0
    while True:
        if time.monotonic() >= deadline:
            raise ValueError("candidate registry cache seed exceeded the aggregate time budget")
        chunk = stream.read(min(64 * 1024, MAX_METADATA_OUTPUT_BYTES + 1 - size))
        if time.monotonic() >= deadline:
            raise ValueError("candidate registry cache seed exceeded the aggregate time budget")
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_METADATA_OUTPUT_BYTES:
            raise ValueError("candidate tarball package metadata exceeded the output limit")
    return json.loads(b"".join(chunks).decode("utf-8"))


def _download_registry_tarball(
    package_name: str, version: str, tarball: str, integrity: str, destination: Path,
    *, deadline: float, byte_budget: int, require_shrinkwrap: bool = False,
) -> dict[str, Any]:
    parsed = urlsplit(tarball)
    if not _approved_registry_url(tarball):
        raise ValueError("candidate tarball download is not on the approved registry")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("candidate registry cache seed exceeded the aggregate time budget")
    try:
        expected = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("candidate tarball integrity is not valid SHA-512 SRI") from error
    if len(expected) != hashlib.sha512().digest_size:
        raise ValueError("candidate tarball integrity is not valid SHA-512 SRI")
    connection = http.client.HTTPSConnection(
        parsed.hostname, timeout=min(MAX_CACHE_ADD_SECONDS, remaining),
    )
    try:
        connection.request("GET", parsed.path, headers={"User-Agent": "codeArbiter-pi-host-lock/1"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"candidate registry tarball returned HTTP {response.status}")
        length = response.getheader("Content-Length")
        if length is not None and int(length) > byte_budget:
            raise ValueError("candidate registry cache exceeded the byte limit")
        digest = hashlib.sha512()
        written = 0
        with destination.open("wb") as stream:
            while chunk := _read_response_chunk(
                response, deadline, MAX_CACHE_ADD_SECONDS, byte_budget + 1 - written,
                "candidate registry cache seed exceeded the aggregate time budget",
            ):
                written += len(chunk)
                if written > byte_budget:
                    raise ValueError("candidate registry cache exceeded the byte limit")
                digest.update(chunk)
                stream.write(chunk)
    finally:
        connection.close()
    if not hmac.compare_digest(digest.digest(), expected):
        destination.unlink(missing_ok=True)
        raise ValueError("candidate registry tarball does not match preflight integrity")
    try:
        with destination.open("rb") as raw_archive, tarfile.open(
            fileobj=_DeadlineReader(
                raw_archive, deadline,
                "candidate registry cache seed exceeded the aggregate time budget",
            ),
            mode="r|gz",
        ) as archive:
            manifest_members = []
            shrinkwrap_members = []
            alternate_metadata_members = []
            manifest = None
            shrinkwrap = None
            uncompressed_bytes = 0
            for index, member in enumerate(archive):
                if time.monotonic() >= deadline:
                    raise ValueError("candidate registry cache seed exceeded the aggregate time budget")
                if index >= MAX_ARCHIVE_MEMBERS:
                    raise ValueError("candidate tarball exceeded the archive member limit")
                if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise ValueError("candidate tarball contains a link or special file")
                if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ValueError("candidate tarball exceeded the member byte limit")
                uncompressed_bytes += member.size
                if uncompressed_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise ValueError("candidate tarball exceeded the uncompressed byte limit")
                if member.isfile() and member.name == "package/package.json":
                    manifest_members.append(member)
                    manifest = _read_archive_json(archive, member, deadline)
                elif (
                    member.isfile()
                    and member.name.count("/") == 1
                    and member.name.rsplit("/", 1)[-1] == "package.json"
                ):
                    alternate_metadata_members.append(member)
                if member.isfile() and member.name == "package/npm-shrinkwrap.json":
                    shrinkwrap_members.append(member)
                    if require_shrinkwrap:
                        shrinkwrap = _read_archive_json(archive, member, deadline)
                elif (
                    member.isfile()
                    and member.name.count("/") == 1
                    and member.name.rsplit("/", 1)[-1] == "npm-shrinkwrap.json"
                ):
                    alternate_metadata_members.append(member)
            if uncompressed_bytes > max(destination.stat().st_size, 1) * MAX_ARCHIVE_COMPRESSION_RATIO:
                raise ValueError("candidate tarball exceeded the compression ratio limit")
            if len(manifest_members) != 1:
                raise ValueError("candidate tarball must contain exactly one canonical package manifest")
            if alternate_metadata_members:
                raise ValueError("candidate tarball contains alternate package identity metadata")
            if require_shrinkwrap and len(shrinkwrap_members) != 1:
                raise ValueError("candidate tarball must contain exactly one canonical npm shrinkwrap")
    except (tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("candidate tarball has no valid package identity") from error
    if not isinstance(manifest, dict) or manifest.get("name") != package_name or manifest.get("version") != version:
        raise ValueError("candidate tarball package identity does not match preflight metadata")
    if require_shrinkwrap and (
        not isinstance(shrinkwrap, dict)
        or shrinkwrap.get("name") != package_name
        or shrinkwrap.get("version") != version
        or shrinkwrap.get("lockfileVersion") != 3
        or not isinstance(shrinkwrap.get("packages"), dict)
        or not isinstance(shrinkwrap["packages"].get(""), dict)
        or shrinkwrap["packages"][""].get("name") != package_name
        or shrinkwrap["packages"][""].get("version") != version
    ):
        raise ValueError("candidate tarball shrinkwrap identity does not match preflight metadata")
    return {"manifest": manifest, "shrinkwrap": shrinkwrap}


def _wrapper_lock_from_published_shrinkwrap(
    version: str, root_metadata: dict[str, Any], published: dict[str, Any],
) -> dict[str, Any]:
    source_packages = published.get("packages")
    if not isinstance(source_packages, dict) or not isinstance(source_packages.get(""), dict):
        raise ValueError("candidate published shrinkwrap has no package inventory")
    if len(source_packages) > MAX_METADATA_PACKAGES:
        raise ValueError("candidate published shrinkwrap exceeded the package count limit")
    prefix = f"node_modules/{PACKAGE}"
    packages: dict[str, Any] = {
        "": {
            "name": f"@codearbiter/pi-host-{version}",
            "version": "0.0.0",
            "dependencies": {PACKAGE: version},
        },
    }
    for key, raw_value in source_packages.items():
        if not isinstance(key, str) or not isinstance(raw_value, dict):
            raise ValueError("candidate published shrinkwrap package inventory is malformed")
        if key and (
            not key.startswith("node_modules/")
            or "\\" in key
            or any(part in {"", ".", ".."} for part in key.split("/"))
        ):
            raise ValueError(f"candidate published shrinkwrap path is unsafe: {key}")
        if key.count("node_modules/") > MAX_METADATA_DEPTH:
            raise ValueError(f"candidate published shrinkwrap exceeded the depth limit: {key}")
        target = prefix if key == "" else f"{prefix}/{key}"
        if target in packages:
            raise ValueError(f"candidate published shrinkwrap path collides: {key}")
        value = json.loads(json.dumps(raw_value))
        if key == "":
            value.pop("name", None)
            value["version"] = version
            value["resolved"] = root_metadata["dist.tarball"]
            value["integrity"] = root_metadata["dist.integrity"]
            value["hasShrinkwrap"] = True
        packages[target] = value
    return {
        "name": f"@codearbiter/pi-host-{version}",
        "version": "0.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": packages,
    }


def _npm_environment(destination: Path, ambient: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if ambient is None else ambient
    clean = {
        key: value for key, value in source.items()
        if key.upper() in NPM_ENV_ALLOWLIST
    }
    config = destination / ".npm-config"
    config.mkdir(parents=True, exist_ok=True)
    user_config = config / "user.npmrc"
    global_config = config / "global.npmrc"
    user_config.write_text("", encoding="utf-8", newline="\n")
    global_config.write_text("", encoding="utf-8", newline="\n")
    clean.update({
        "NPM_CONFIG_CACHE": str(destination / ".npm-cache"),
        "NPM_CONFIG_USERCONFIG": str(user_config),
        "NPM_CONFIG_GLOBALCONFIG": str(global_config),
    })
    return clean


def _lock_dir(root: Path, version: str) -> Path:
    if version not in SUPPORTED:
        raise ValueError(f"Pi {version} is not in the reviewed supported set: {', '.join(SUPPORTED)}")
    return root.resolve() / LOCK_ROOT / version


def _validate_review_receipt(review: dict[str, Any], version: str) -> None:
    if review.get("result") != "PASS":
        raise ValueError("host lock is pending dependency review")
    if set(review) != REVIEW_FIELDS or review.get("schema") != "codearbiter-pi-host-lock-review-v2":
        raise ValueError("dependency review receipt has missing or unknown fields")
    if review.get("source_repository") != SOURCE_REPOSITORY or review.get("source_tag") != f"v{version}":
        raise ValueError("dependency review source identity mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(review.get("source_commit", ""))):
        raise ValueError("dependency review source commit is invalid")
    try:
        date.fromisoformat(str(review.get("reviewed_at", "")))
    except ValueError as error:
        raise ValueError("dependency review date is invalid") from error
    if review.get("reviewer") != "ca-add-dep:C019-DEPENDENCY":
        raise ValueError("dependency review identity is invalid")
    licenses = review.get("licenses")
    if not isinstance(licenses, dict) or set(licenses) != {"result", "observed"}:
        raise ValueError("dependency review license evidence is incomplete")
    if licenses.get("result") != "PASS" or not isinstance(licenses.get("observed"), list) or not licenses["observed"]:
        raise ValueError("dependency review license evidence did not pass")
    audits = review.get("audits")
    if not isinstance(audits, dict) or set(audits) != {"production", "all"}:
        raise ValueError("dependency review audit evidence is incomplete")
    if audits.get("production") != ZERO_AUDIT or audits.get("all") != ZERO_AUDIT:
        raise ValueError("dependency review audit evidence did not pass")
    if review.get("lifecycle_scripts") != {
        "result": "PASS", "policy": "ignore-scripts", "transitive_hooks_present": True,
    }:
        raise ValueError("dependency review lifecycle-script evidence did not pass")
    signatures = review.get("signatures")
    if not isinstance(signatures, dict) or signatures.get("result") != "PASS" or signatures.get("verified", 0) <= 0:
        raise ValueError("dependency review signature evidence did not pass")
    provenance = review.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("result") != "PASS" or provenance.get("attestations_verified", 0) <= 0:
        raise ValueError("dependency review provenance evidence did not pass")


def _locked_dependency_target(
    packages: dict[str, Any], owner: str, dependency_name: str,
) -> dict[str, Any] | None:
    current = owner
    candidates = []
    while current:
        candidates.append(f"{current}/node_modules/{dependency_name}")
        marker = current.rfind("/node_modules/")
        if marker < 0:
            break
        current = current[:marker]
    candidates.append(f"node_modules/{dependency_name}")
    for candidate in candidates:
        value = packages.get(candidate)
        if isinstance(value, dict):
            return value
    return None


def _validate_locked_dependency_edges(packages: dict[str, Any]) -> None:
    for owner, value in packages.items():
        if not isinstance(owner, str) or not isinstance(value, dict):
            raise ValueError("reviewed lock package inventory is malformed")
        peer_metadata = value.get("peerDependenciesMeta", {}) or {}
        if not isinstance(peer_metadata, dict):
            raise ValueError(f"reviewed lock peer dependency metadata is malformed at {owner}")
        for field in ("dependencies", "optionalDependencies", "peerDependencies"):
            dependencies = value.get(field, {}) or {}
            if not isinstance(dependencies, dict):
                raise ValueError(f"reviewed lock {field} is malformed at {owner}")
            for dependency_name, specification in dependencies.items():
                if not isinstance(dependency_name, str) or PACKAGE_NAME.fullmatch(dependency_name) is None:
                    raise ValueError(f"reviewed lock dependency name is invalid at {owner}")
                try:
                    alias_name, _ = _registry_dependency(specification)
                except ValueError as error:
                    raise ValueError(
                        f"reviewed lock dependency is not registry-only at {owner}: {dependency_name}"
                    ) from error
                target = _locked_dependency_target(packages, owner, dependency_name)
                optional_peer = (
                    field == "peerDependencies"
                    and isinstance(peer_metadata.get(dependency_name), dict)
                    and peer_metadata[dependency_name].get("optional") is True
                )
                if target is None and not optional_peer:
                    raise ValueError(
                        f"reviewed lock dependency has no complete locked target at {owner}: {dependency_name}"
                    )
                if target is not None and alias_name is not None and target.get("name") != alias_name:
                    raise ValueError(
                        f"reviewed lock registry alias identity mismatch at {owner}: {dependency_name}"
                    )


def _validate_directory(directory: Path, version: str, *, require_reviewed: bool) -> dict[str, str]:
    manifest_path = directory / "package.json"
    lock_path = directory / "package-lock.json"
    review_path = directory / "review.json"
    manifest = _read_json(manifest_path)
    lock = _read_json(lock_path)
    review = _read_json(review_path)
    expected = {PACKAGE: version}
    if manifest.get("private") is not True or manifest.get("dependencies") != expected:
        raise ValueError("reviewed manifest must be private and pin the exact Pi version")
    if lock.get("lockfileVersion") != 3:
        raise ValueError("reviewed lock must use lockfileVersion 3")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
        raise ValueError("reviewed lock has no package inventory")
    if packages[""].get("dependencies") != expected:
        raise ValueError("reviewed lock root version does not match the manifest")
    agent = packages.get(f"node_modules/{PACKAGE}")
    if not isinstance(agent, dict) or agent.get("version") != version:
        raise ValueError("reviewed lock does not contain the exact Pi package")
    _validate_locked_dependency_edges(packages)
    for key, value in packages.items():
        if not key or not isinstance(value, dict):
            continue
        if value.get("link") is True:
            raise ValueError(f"reviewed lock link entry is forbidden at {key}")
        resolved = value.get("resolved")
        integrity = value.get("integrity")
        if (
            not _approved_registry_url(resolved)
            or not isinstance(integrity, str)
            or not integrity.startswith("sha512-")
        ):
            raise ValueError(f"reviewed lock registry or integrity violation at {key}")
    digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if review.get("lock_sha256") != digest:
        raise ValueError("reviewed lock digest does not match reviewed bytes")
    if review.get("package") != PACKAGE or review.get("version") != version:
        raise ValueError("reviewed lock identity mismatch")
    if review.get("registry") != REGISTRY or review.get("root_integrity") != agent.get("integrity"):
        raise ValueError("reviewed root registry or integrity mismatch")
    if require_reviewed:
        _validate_review_receipt(review, version)
    elif (
        set(review) != CANDIDATE_FIELDS
        or review.get("schema") != "codearbiter-pi-host-lock-review-v1"
        or review.get("result") != "PENDING_REVIEW"
        or review.get("source_repository") != SOURCE_REPOSITORY
        or re.fullmatch(r"[0-9a-f]{40}", str(review.get("source_commit", ""))) is None
    ):
        raise ValueError("captured candidate must remain an exact pending dependency review receipt")
    return {"package": PACKAGE, "version": version, "lock_sha256": digest}


def validate_host_lock(root: Path, version: str) -> dict[str, str]:
    return _validate_directory(_lock_dir(root, version), version, require_reviewed=True)


def install_plan(root: Path, version: str, prefix: Path) -> dict[str, Any]:
    validate_host_lock(root, version)
    directory = _lock_dir(root, version)
    destination = prefix.resolve()
    cache = destination / ".npm-cache"
    return {
        "cwd": str(directory),
        "prefix": str(destination),
        "path_entry": str(destination / "node_modules" / ".bin"),
        "command": [
            shutil.which("npm") or "npm", "ci", "--ignore-scripts", *REGISTRY_ARGS,
            "--cache", str(cache), "--prefix", str(destination),
        ],
    }


def install(root: Path, version: str, prefix: Path) -> dict[str, Any]:
    plan = install_plan(root, version, prefix)
    destination = Path(plan["prefix"])
    repository = root.resolve()
    if destination == repository or destination.is_relative_to(repository):
        raise ValueError("isolated Pi prefix must be outside the repository")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"isolated Pi prefix is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    source = Path(plan["cwd"])
    for name in ("package.json", "package-lock.json", ".npmrc"):
        shutil.copyfile(source / name, destination / name)
    npm_environment = _npm_environment(destination)
    subprocess.run(plan["command"], cwd=source, check=True, env=npm_environment)
    _audit_install(destination, source, version)
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with Path(github_path).open("a", encoding="utf-8") as stream:
            stream.write(plan["path_entry"] + "\n")
    return plan


def _audit_install(destination: Path, cwd: Path, version: str) -> None:
    npm = shutil.which("npm") or "npm"
    cache_args = [*REGISTRY_ARGS, "--cache", str(destination / ".npm-cache")]
    npm_environment = _npm_environment(destination)
    checks = [
        [npm, "audit", "--omit=dev", "--audit-level=high", "--ignore-scripts", *cache_args, "--prefix", str(destination)],
        [npm, "audit", "--audit-level=high", "--ignore-scripts", *cache_args, "--prefix", str(destination)],
        [npm, "audit", "signatures", "--ignore-scripts", *cache_args, "--prefix", str(destination)],
        [npm, "ls", "--all", "--json", "--ignore-scripts", *cache_args, "--prefix", str(destination)],
    ]
    for command in checks:
        completed = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8", env=npm_environment,
        )
        if command[1:3] == ["ls", "--all"]:
            inventory = json.loads(completed.stdout)
            agent = inventory.get("dependencies", {}).get(PACKAGE, {})
            if not isinstance(agent, dict) or agent.get("version") != version:
                raise ValueError("installed Pi dependency tree does not match the exact reviewed version")


def capture_candidate(version: str, output: Path) -> dict[str, str]:
    if VERSION.fullmatch(version) is None:
        raise ValueError("candidate must be an exact stable semver")
    destination = output.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"candidate lock destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": f"@codearbiter/pi-host-{version}",
        "version": "0.0.0",
        "private": True,
        "dependencies": {PACKAGE: version},
    }
    (destination / "package.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (destination / ".npmrc").write_text(
        f"registry={REGISTRY}/\n@earendil-works:registry={REGISTRY}/\nignore-scripts=true\npackage-lock=true\n",
        encoding="utf-8",
        newline="\n",
    )
    npm = shutil.which("npm") or "npm"
    cache = destination / ".npm-cache"
    npm_environment = _npm_environment(destination)
    metadata_deadline = time.monotonic() + MAX_METADATA_WALK_SECONDS
    root_metadata = _metadata_record(_run_registry_metadata(
        npm, PACKAGE, version, npm_environment, metadata_deadline,
    ))
    if root_metadata.get("version") != version:
        raise ValueError("candidate root metadata did not resolve the exact requested version")
    if root_metadata.get("repository.url") != SOURCE_REPOSITORY or re.fullmatch(
        r"[0-9a-f]{40}", str(root_metadata.get("gitHead", "")),
    ) is None:
        raise ValueError("candidate registry metadata has no approved source identity")
    for field in ("dependencies", "optionalDependencies", "peerDependencies"):
        dependencies = root_metadata.get(field, {}) or {}
        if not isinstance(dependencies, dict):
            raise ValueError(f"candidate registry metadata {field} is not an object")
        for package_name, specification in dependencies.items():
            if not isinstance(package_name, str) or PACKAGE_NAME.fullmatch(package_name) is None:
                raise ValueError(f"candidate registry metadata {field} has an invalid package name")
            _registry_dependency(specification)
    with tempfile.TemporaryDirectory(prefix="ca-pi-root-", dir=destination) as raw_root:
        root_archive = Path(raw_root) / "package.tgz"
        verified_root = _download_registry_tarball(
            PACKAGE, version, root_metadata["dist.tarball"], root_metadata["dist.integrity"],
            root_archive, deadline=metadata_deadline, byte_budget=MAX_METADATA_CACHE_BYTES,
            require_shrinkwrap=True,
        )
        lock = _wrapper_lock_from_published_shrinkwrap(
            version, root_metadata, verified_root["shrinkwrap"],
        )
    lock_path = destination / "package-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("captured candidate lock has no package inventory")
    preflighted = {
        (PACKAGE, version): (root_metadata["dist.tarball"], root_metadata["dist.integrity"]),
    }
    verified_bytes = 0
    with tempfile.TemporaryDirectory(prefix="ca-pi-lock-verify-", dir=destination) as raw_verify:
        verify_root = Path(raw_verify)
        for index, (key, value) in enumerate(packages.items()):
            if not key or not isinstance(value, dict):
                continue
            package_name = value.get("name") or key.rsplit("node_modules/", 1)[-1]
            package_version = value.get("version")
            resolved = value.get("resolved")
            integrity = value.get("integrity")
            preflight_identity = preflighted.get((package_name, package_version))
            if preflight_identity is not None:
                expected_resolved, expected_integrity = preflight_identity
                if resolved != expected_resolved or integrity not in {None, expected_integrity}:
                    raise ValueError(f"candidate registry metadata mismatch at {key}")
                value["integrity"] = expected_integrity
                continue
            if not _approved_registry_url(resolved):
                raise ValueError(f"candidate registry or integrity mismatch at {key}")
            if isinstance(integrity, str) and integrity.startswith("sha512-"):
                continue
            if integrity is not None or not isinstance(package_name, str) or PACKAGE_NAME.fullmatch(package_name) is None:
                raise ValueError(f"candidate registry or integrity mismatch at {key}")
            if not isinstance(package_version, str) or VERSION.fullmatch(package_version) is None:
                raise ValueError(f"candidate registry or integrity mismatch at {key}")
            metadata = _metadata_record(_run_registry_metadata(
                npm, package_name, package_version, npm_environment, metadata_deadline,
            ))
            if metadata.get("version") != package_version or metadata.get("dist.tarball") != resolved:
                raise ValueError(f"candidate registry metadata mismatch at {key}")
            expected_integrity = metadata["dist.integrity"]
            archive = verify_root / f"{index}.tgz"
            _download_registry_tarball(
                package_name, package_version, resolved, expected_integrity, archive,
                deadline=metadata_deadline, byte_budget=MAX_METADATA_CACHE_BYTES - verified_bytes,
            )
            verified_bytes += archive.stat().st_size
            archive.unlink()
            value["integrity"] = expected_integrity
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    agent = packages[f"node_modules/{PACKAGE}"]
    review = {
        "schema": "codearbiter-pi-host-lock-review-v1",
        "package": PACKAGE,
        "version": version,
        "registry": REGISTRY,
        "root_integrity": agent["integrity"],
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "source_repository": root_metadata.get("repository.url"),
        "source_commit": root_metadata.get("gitHead"),
        "result": "PENDING_REVIEW",
    }
    (destination / "review.json").write_text(
        json.dumps(review, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    if cache.exists():
        shutil.rmtree(cache)
    config = destination / ".npm-config"
    if config.exists():
        shutil.rmtree(config)
    return _validate_directory(destination, version, require_reviewed=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "plan", "install"):
        command = subparsers.add_parser(name)
        command.add_argument("--version", required=True)
        if name in {"plan", "install"}:
            command.add_argument("--prefix", required=True, type=Path)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--version", required=True)
    capture_parser.add_argument("--output", required=True, type=Path)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--spec", default="latest")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_host_lock(args.root, args.version)
        elif args.command == "plan":
            result = install_plan(args.root, args.version, args.prefix)
        elif args.command == "install":
            result = install(args.root, args.version, args.prefix)
        elif args.command == "capture":
            result = capture_candidate(args.version, args.output)
        elif args.command == "resolve":
            result = resolve_candidate(args.spec)
        else:
            raise AssertionError(f"unhandled command: {args.command}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Pi host-lock error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
