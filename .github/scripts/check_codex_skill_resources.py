#!/usr/bin/env python3
"""Offline contract checker for the tracked Codex skill-resource fixture.

Stage 1 deliberately separates deterministic fixture validation from live
runtime characterization.  This command performs no network or credential
access; later stages add explicit live modes and durable receipt import.
"""

from __future__ import annotations

import argparse
import base64
from bisect import bisect_right
import hashlib
import io
import json
import ntpath
import os
import platform
import posixpath
import queue
import re
import shlex
import shutil
import stat
import string
import subprocess
import sys
import tempfile
import threading
import unicodedata
import zipfile
from pathlib import Path, PureWindowsPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / ".github" / "fixtures" / "codex-skill-resources"
RESOURCE_FILES = (
    Path("skills/probe/SKILL.md"),
    Path("routines/nested.md"),
    Path("agents/probe.md"),
)
PAYLOAD_FILES = (Path(".codex-plugin/plugin.json"),) + RESOURCE_FILES
EXPECTED_LINKS = {
    Path("skills/probe/SKILL.md"): ("../../routines/nested.md",),
    Path("routines/nested.md"): ("../agents/probe.md",),
    Path("agents/probe.md"): (),
}
REQUIRED_CELLS = frozenset({
    ("cli", "0.143.0"),
    ("cli", "0.145.0"),
    ("app-server", "0.143.0"),
    ("app-server", "0.145.0"),
})
PINNED_RELEASES = {
    "0.143.0": {
        "provenance": "npm:@openai/codex@0.143.0",
        "integrity": "sha512-6h53sNtESIYncWVwU7zEjdVajwcad/0H94MOrgGqhwBMa9RRUDVG6DU9E9euC7yRdtrsKDAkJkz/m5moZ6MU3A==",
        "native_executable_sha256": "5728e3ddf1480103bad235560e95cf7764ea3069f06029f9b2f39eb74a8066f6",
    },
    "0.145.0": {
        "provenance": "npm:@openai/codex@0.145.0",
        "integrity": "sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ==",
        "native_executable_sha256": "83751f15cb6a0a7b97df67752c001e3fe1c20e18ffbfec3ff63567296205eb6c",
    },
}
ADVISORY_RELEASE = {
    "version": "0.149.0",
    "provenance": "npm:@openai/codex@0.149.0",
    "integrity": "sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ==",
    "native_executable_sha256": "14b7e6b2356e82d1d9275579eaa588757b4e0a501b65dcc19fccdf77bd83dc00",
}
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
REFERENCE_DEFINITION = re.compile(
    r"(?m)^[ \t]{0,3}\[(?P<label>[^\]\n]+)\]:[ \t]*"
    r"(?:<(?P<angle>[^>\n]+)>|(?P<plain>(?:\\.|[^\s\\])+))"
    r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^\)\n]*\)))?[ \t]*$"
)
REFERENCE_RESOURCE_LINK = re.compile(
    r"\[(?P<text>[^\]\n]+)\]\[(?P<label>[^\]\n]*)\]"
)
SYMBOLIC_SEGMENT = re.compile(r"<[a-z][a-z0-9-]*>")
SYMBOLIC_TARGET_CHARS = re.compile(r"^[A-Za-z0-9_./<>-]+$")
SYMBOLIC_SENTINEL = ":codearbiter-symbol:"
SYMBOLIC_INLINE_LINK = re.compile(
    r"\[[^\]\r\n]*\]\("
    r"(?P<target>[A-Za-z0-9_./-]*(?:<[a-z][a-z0-9-]*>"
    r"[A-Za-z0-9_./-]*)+)"
    r"(?:[ \t\r\n]+(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\([^\)\r\n]*\)))?"
    r"[ \t\r\n]*\)"
)
NONCE = re.compile(r"(?m)^nonce:\s*([^\s]+)\s*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_NONCES = {
    Path("skills/probe/SKILL.md"): "skill-probe-nonce-7f4d",
    Path("routines/nested.md"): "nested-routine-nonce-2ca1",
    Path("agents/probe.md"): "agent-probe-nonce-91be",
}
SEARCH_OR_GLOB = re.compile(
    r"(?i)(?:\b(?:find|grep|rg|glob|rglob|walk|get-childitem)\b|(?:^|\s)-recurse\b|[*?])"
)
EXPECTED_CANDIDATE_ARCHIVE_LIMITS = {
    "max_archive_bytes": 8 * 1024 * 1024,
    "max_entries": 1024,
    "max_entry_uncompressed_bytes": 2 * 1024 * 1024,
    "max_total_uncompressed_bytes": 32 * 1024 * 1024,
    "max_compression_ratio": 100,
}
SECRET_VALUE = re.compile(
    r"(?i)(?:\bBearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk|gh[oprsu])[-_][A-Za-z0-9_-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"\b(?:api[_-]?key|apikey|password|passphrase|client[_-]?secret|secret|token|"
    r"key|credential|private|cert|access[_-]?token|refresh[_-]?token|oauth[_-]?token|"
    r"device[_-]?code|session(?:[_-]?(?:id|token))?|cookie)"
    r"\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}|"
    r"(?-i:(?<![A-Z0-9-])[A-Z0-9]{4}(?:-[A-Z0-9]{4}){1,3}(?![A-Z0-9-])))"
)
PACKAGE_VERSION_ID = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
OPAQUE_CREDENTIAL_COMPONENT = re.compile(r"[A-Za-z0-9]{24,}")


class _DuplicateJsonMember(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMember
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _windows_normalized(path: object) -> PureWindowsPath | None:
    if not _nonempty_string(path):
        return None
    raw = str(path).replace("/", "\\")
    normalized = PureWindowsPath(ntpath.normpath(raw))
    if not normalized.is_absolute() or not normalized.drive:
        return None
    return normalized


def _windows_contained(root: PureWindowsPath, target: PureWindowsPath) -> bool:
    root_parts = tuple(part.casefold() for part in root.parts)
    target_parts = tuple(part.casefold() for part in target.parts)
    return target_parts[:len(root_parts)] == root_parts


def _secret_bearing(value: object, path: tuple[str, ...] = ()) -> list[str]:
    """Reject secret material and unreviewed fields that commonly carry it."""
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_VALUE.search(key_text):
                findings.append(".".join((*path, key_text)))
            lowered = key_text.casefold().replace("-", "_")
            sensitive_key = any(
                token in lowered
                for token in (
                    "api_key", "access_token", "authorization", "auth_file", "callback",
                    "cookie", "credential", "device_code", "password", "raw_login", "secret",
                )
            )
            if sensitive_key and item not in (False, None, "", [], {}):
                findings.append(".".join((*path, key_text)))
            findings.extend(_secret_bearing(item, (*path, key_text)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_secret_bearing(item, (*path, str(index))))
    elif isinstance(value, str) and SECRET_VALUE.search(value):
        findings.append(".".join(path))
    return findings


def _paths_sha256(root: Path, paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(paths, key=lambda item: item.as_posix()):
        path = root / relative_path
        relative = relative_path.as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes() if path.is_file() else b""
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def fixture_sha256(root: Path) -> str:
    """Hash only the byte-identical installable plugin resource payload."""
    return _paths_sha256(root, PAYLOAD_FILES)


def evidence_contract_sha256(matrix: dict[str, Any]) -> str:
    """Hash the independently evolving matrix/evidence contract."""
    canonical = json.dumps(matrix, separators=(",", ":"), sort_keys=True)
    return _sha256_text(canonical)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _errors_sha256(errors: list[str]) -> str:
    return _sha256_text(json.dumps(errors, separators=(",", ":"), sort_keys=True))


def _contained(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label} is missing: {path.as_posix()}")
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        errors.append(f"{label} is invalid JSON: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return value


def _validate_manifest(root: Path, errors: list[str]) -> None:
    manifest = _read_json(root / ".codex-plugin" / "plugin.json", errors, "plugin manifest")
    for key in ("name", "version", "description"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            errors.append(f"plugin manifest {key!r} must be a non-empty string")
    if manifest.get("name") != "codex-skill-resource-probe":
        errors.append("plugin manifest name must be 'codex-skill-resource-probe'")


def _validate_resource_links(root: Path, errors: list[str]) -> None:
    nonces: dict[str, Path] = {}
    for relative in RESOURCE_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"required resource does not exist: {relative.as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        match = NONCE.search(text)
        if match is None:
            errors.append(f"required resource has no nonce: {relative.as_posix()}")
        else:
            nonce = match.group(1)
            previous = nonces.get(nonce)
            if previous is not None:
                errors.append(
                    f"duplicate nonce {nonce!r} in {previous.as_posix()} and {relative.as_posix()}"
                )
            nonces[nonce] = relative
        links = LINK.findall(text)
        expected_links = EXPECTED_LINKS[relative]
        if tuple(links) != expected_links:
            errors.append(
                f"{relative.as_posix()} outgoing link set must be exactly {expected_links!r}"
            )
        for target_text in links:
            target = (path.parent / target_text).resolve()
            resolved_root = root.resolve()
            if not _contained(resolved_root, target):
                errors.append(
                    f"link from {relative.as_posix()} escapes fixture root: {target_text!r}"
                )
            elif not target.is_file():
                errors.append(
                    f"link target does not exist from {relative.as_posix()}: {target_text!r}"
                )


def _valid_npm_integrity(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha512-"):
        return False
    try:
        decoded = base64.b64decode(value.removeprefix("sha512-"), validate=True)
    except Exception:
        return False
    return len(decoded) == 64


def _repo_relative_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def _validate_matrix(matrix: dict[str, Any], errors: list[str]) -> None:
    if matrix.get("schema_version") != 1:
        errors.append("matrix schema_version must be 1")
    cells = matrix.get("required_cells")
    if not isinstance(cells, list):
        errors.append("required_cells must be a list")
        cells = []
    actual: list[tuple[object, object]] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append(f"required cell #{index + 1} must be an object")
            continue
        surface, version = cell.get("surface"), cell.get("version")
        actual.append((surface, version))
        if surface not in {"cli", "app-server"}:
            errors.append(f"required cell #{index + 1} surface {surface!r} is not backend-only")
        if cell.get("desktop_shell_proven") is not False:
            errors.append(f"required cell #{index + 1} desktop_shell_proven must be false")
        pin = PINNED_RELEASES.get(version) if isinstance(version, str) else None
        provenance = cell.get("provenance")
        integrity = cell.get("integrity")
        executable = cell.get("native_executable_sha256")
        if not isinstance(provenance, str) or not provenance.strip():
            errors.append(f"required cell #{index + 1} provenance must be non-empty")
        elif pin is not None and provenance != pin["provenance"]:
            errors.append(f"required cell #{index + 1} provenance does not match pinned npm package")
        if not isinstance(integrity, str) or not integrity.strip():
            errors.append(f"required cell #{index + 1} integrity must be non-empty")
        elif not _valid_npm_integrity(integrity):
            errors.append(f"required cell #{index + 1} integrity format must be npm sha512 base64")
        elif pin is not None and integrity != pin["integrity"]:
            errors.append(f"required cell #{index + 1} integrity does not match pinned integrity")
        if not isinstance(executable, str) or not SHA256.fullmatch(executable):
            errors.append(f"required cell #{index + 1} native_executable_sha256 must be lowercase SHA-256")
        elif pin is not None and executable != pin["native_executable_sha256"]:
            errors.append(f"required cell #{index + 1} native_executable_sha256 does not match pinned executable")
    if len(cells) != len(REQUIRED_CELLS) or set(actual) != REQUIRED_CELLS:
        errors.append(
            "required matrix cells must be exactly CLI/app-server 0.143.0 and 0.145.0"
        )
    durable = matrix.get("durable_record")
    if not isinstance(durable, dict):
        errors.append("durable_record must be an object binding report and receipts")
        return
    if durable.get("status") not in {"pending", "complete"}:
        errors.append("durable_record status must be pending or complete")
    for key in ("report", "receipt_directory", "receipt_filename_template", "fixture_sha256_field"):
        value = durable.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"durable_record {key!r} must be a non-empty string")
    if durable.get("fixture_sha256_field") != "fixture_sha256":
        errors.append("durable_record fixture_sha256_field must bind fixture_sha256")
    if durable.get("receipt_filename_template") != "{surface}-{version}.json":
        errors.append("durable_record receipt_filename_template must bind surface and version")
    for key in ("report", "receipt_directory"):
        if _repo_relative_path(durable.get(key)) is None:
            errors.append(f"durable_record {key!r} must be a contained repository-relative path")


def _receipt_errors(
    receipt: object,
    expected: dict[str, Any],
    fixture_hash: str,
    evidence_contract_hash: str,
    label: str,
) -> list[str]:
    if not isinstance(receipt, dict):
        return [f"{label} must be a JSON object"]
    if _secret_bearing(receipt):
        return [f"{label} contains secret-bearing output"]
    common_fields = {
        "authentication_mode",
        "desktop_shell_proven",
        "effective_approval_policy",
        "effective_sandbox",
        "entry_path",
        "environment",
        "errors",
        "errors_sha256",
        "evidence_class",
        "evidence_contract_sha256",
        "fixture_sha256",
        "installed_plugin_root",
        "integrity",
        "native_executable_sha256",
        "network_policy",
        "operation_transcript_sha256",
        "provenance",
        "requested_approval_policy",
        "requested_sandbox",
        "resource_reads",
        "schema_version",
        "stderr_sha256",
        "stdout_sha256",
        "surface",
        "verdict",
        "version",
    }
    surface_fields = {
        "cli": {"skill_invocation_evidence"},
        "app-server": {"selected_skill", "selected_skill_path"},
    }.get(receipt.get("surface"), set())
    required_fields = common_fields | surface_fields
    missing_fields = sorted(required_fields - set(receipt))
    if set(receipt) - required_fields:
        return [f"{label} contains untrusted fields"]
    environment_value = receipt.get("environment")
    if isinstance(environment_value, dict) and set(environment_value) - {
        "base_image", "codex_home", "execution_environment", "machine", "os",
        "os_identity", "platform", "release",
    }:
        return [f"{label} contains untrusted fields"]
    reads_value = receipt.get("resource_reads")
    if isinstance(reads_value, list) and any(
        isinstance(read, dict) and set(read) - {"path", "nonce"}
        for read in reads_value
    ):
        return [f"{label} contains untrusted fields"]
    skill_value = receipt.get("skill_invocation_evidence")
    if isinstance(skill_value, dict) and set(skill_value) - {
        "name", "path", "source", "status",
    }:
        return [f"{label} contains untrusted fields"]

    errors: list[str] = []
    expected_surface = expected.get("surface")
    expected_version = expected.get("version")
    if not _nonempty_string(expected_surface):
        errors.append(f"{label} expected matrix surface is missing")
    if not _nonempty_string(expected_version):
        errors.append(f"{label} expected matrix version is missing")
    if (receipt.get("surface"), receipt.get("version")) != (
        expected_surface, expected_version
    ):
        errors.append(f"{label} does not match expected cell surface/version")
    if missing_fields:
        errors.append(
            f"{label} top-level fields must be exact; "
            f"missing={missing_fields!r}"
        )
    if receipt.get("verdict") != "PASS":
        errors.append(f"{label} verdict must be PASS")
    if receipt.get("evidence_class") != "supported":
        errors.append(f"{label} evidence_class must be supported")
    if receipt.get("desktop_shell_proven") is not False:
        errors.append(f"{label} desktop_shell_proven must be false")
    for field in ("provenance", "integrity", "native_executable_sha256"):
        if field not in expected or receipt.get(field) != expected.get(field):
            errors.append(f"{label} {field} does not match pinned matrix")
    if receipt.get("fixture_sha256") != fixture_hash:
        errors.append(f"{label} fixture_sha256 does not match fixture hash")
    if receipt.get("evidence_contract_sha256") != evidence_contract_hash:
        errors.append(f"{label} evidence_contract_sha256 does not match matrix contract hash")

    if receipt.get("schema_version") != 1:
        errors.append(f"{label} schema_version must be 1")
    if receipt.get("authentication_mode") != "chatgpt":
        errors.append(f"{label} authentication_mode must be chatgpt")
    for field, value in (
        ("requested_sandbox", "read-only"),
        ("effective_sandbox", "read-only"),
        ("requested_approval_policy", "never"),
        ("effective_approval_policy", "never"),
        ("network_policy", "model-api-only; tool-network-disabled"),
    ):
        if receipt.get(field) != value:
            errors.append(f"{label} {field} must be {value}")

    environment = receipt.get("environment")
    codex_home = None
    if not isinstance(environment, dict):
        errors.append(f"{label} environment must be an object")
    else:
        expected_environment_fields = {
            "base_image",
            "codex_home",
            "execution_environment",
            "machine",
            "os",
            "os_identity",
            "platform",
            "release",
        }
        if set(environment) != expected_environment_fields:
            errors.append(
                f"{label} environment fields must be exact; "
                f"missing={sorted(expected_environment_fields - set(environment))!r}, "
                f"extra={sorted(set(environment) - expected_environment_fields)!r}"
            )
        if environment.get("execution_environment") != "isolated-clean-home":
            errors.append(
                f"{label} environment.execution_environment must be isolated-clean-home"
            )
        for field in ("machine", "os", "os_identity", "platform", "release"):
            if not _nonempty_string(environment.get(field)):
                errors.append(f"{label} environment.{field} must be non-empty")
        if "base_image" not in environment or not (
            environment.get("base_image") is None
            or _nonempty_string(environment.get("base_image"))
        ):
            errors.append(f"{label} environment.base_image must be null or non-empty")
        codex_home = _windows_normalized(environment.get("codex_home"))
        if codex_home is None:
            errors.append(f"{label} environment.codex_home must be an absolute Windows path")
        else:
            parent_tail = tuple(
                part.casefold() for part in codex_home.parent.parts[-4:]
            )
            version_parts = (
                expected_version.split(".")
                if _nonempty_string(expected_version)
                else []
            )
            expected_home_prefix = (
                f"{expected_surface}-{version_parts[0]}{version_parts[1]}-auth-"
                if _nonempty_string(expected_surface) and len(version_parts) >= 2
                else ""
            )
            expected_home_name = re.fullmatch(
                re.escape(expected_home_prefix) + r"[0-9]{8}T[0-9]{4}Z",
                codex_home.name,
                flags=re.IGNORECASE,
            )
            if parent_tail != (
                "appdata", "local", "temp", "codearbiter-stage1-oauth"
            ) or expected_home_name is None:
                errors.append(
                    f"{label} environment.codex_home must be the recorded one-use OS-temporary auth root"
                )

    installed_root = _windows_normalized(receipt.get("installed_plugin_root"))
    if installed_root is None:
        errors.append(f"{label} installed_plugin_root must be an absolute Windows path")
    elif codex_home is not None:
        expected_relative_root = PureWindowsPath(
            "plugins/cache/codex-skill-resource-characterization/"
            "codex-skill-resource-probe/0.0.0"
        )
        try:
            relative_root = installed_root.relative_to(codex_home)
        except ValueError:
            relative_root = None
        if relative_root != expected_relative_root:
            errors.append(
                f"{label} installed_plugin_root must be the isolated installed fixture root"
            )

    entry_path = _windows_normalized(receipt.get("entry_path"))
    expected_entry = (
        installed_root / PureWindowsPath("skills/probe/SKILL.md")
        if installed_root is not None
        else None
    )
    if entry_path is None or entry_path != expected_entry:
        errors.append(f"{label} entry_path must name the installed absolute SKILL.md")

    reads = receipt.get("resource_reads")
    actual_reads: dict[PureWindowsPath, object] = {}
    if not isinstance(reads, list) or len(reads) != 3:
        errors.append(f"{label} resource_reads must contain exactly three objects")
        reads = []
    for index, read in enumerate(reads):
        if not isinstance(read, dict) or set(read) != {"path", "nonce"}:
            errors.append(
                f"{label} resource_reads item #{index + 1} must contain only path and nonce"
            )
            continue
        path = _windows_normalized(read.get("path"))
        nonce = read.get("nonce")
        if path is None or not _nonempty_string(nonce):
            errors.append(
                f"{label} resource_reads item #{index + 1} path/nonce must be strings"
            )
            continue
        if path in actual_reads:
            errors.append(f"{label} resource_reads paths must be distinct")
        actual_reads[path] = nonce
    if installed_root is not None:
        expected_reads = {
            installed_root / PureWindowsPath(relative.as_posix()): nonce
            for relative, nonce in EXPECTED_NONCES.items()
        }
        if actual_reads != expected_reads:
            errors.append(f"{label} resource_reads must bind the exact three paths/nonces")

    receipt_errors = receipt.get("errors")
    if receipt_errors != []:
        errors.append(f"{label} errors must be an empty array for a PASS receipt")
    if receipt.get("errors_sha256") != _errors_sha256([]):
        errors.append(f"{label} errors_sha256 must bind the empty errors array")
    for field in (
        "operation_transcript_sha256",
        "stdout_sha256",
        "stderr_sha256",
    ):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            errors.append(f"{label} {field} must be a lowercase SHA-256")
    canonical_ready = (
        isinstance(reads, list)
        and len(reads) == 3
        and all(
            isinstance(read, dict)
            and set(read) == {"path", "nonce"}
            and _nonempty_string(read.get("path"))
            and _nonempty_string(read.get("nonce"))
            for read in reads
        )
        and all(
            _nonempty_string(receipt.get(field))
            for field in (
                "entry_path", "requested_sandbox", "effective_sandbox",
                "requested_approval_policy", "effective_approval_policy",
            )
        )
    )
    if canonical_ready:
        canonical_observation = {
            "entry_path": receipt["entry_path"],
            "resource_reads": receipt["resource_reads"],
            "requested_sandbox": receipt["requested_sandbox"],
            "effective_sandbox": receipt["effective_sandbox"],
            "requested_approval_policy": receipt["requested_approval_policy"],
            "effective_approval_policy": receipt["effective_approval_policy"],
        }
        canonical_hashes = _canonical_live_evidence_hashes(
            canonical_observation, [], "", ""
        )
        for field, expected_hash in zip(
            (
                "operation_transcript_sha256", "stdout_sha256", "stderr_sha256",
            ),
            canonical_hashes,
        ):
            if receipt.get(field) != expected_hash:
                errors.append(f"{label} {field} does not match canonical evidence")

    if receipt.get("surface") == "cli":
        skill = receipt.get("skill_invocation_evidence")
        expected_skill = {
            "name": "codex-skill-resource-probe:probe",
            "path": receipt.get("entry_path"),
            "source": "direct-entry-read",
            "status": "completed",
        }
        if skill != expected_skill:
            errors.append(
                f"{label} skill_invocation_evidence must bind the exact completed entry read"
            )
    elif receipt.get("surface") == "app-server":
        if receipt.get("selected_skill") != "codex-skill-resource-probe:probe":
            errors.append(f"{label} selected_skill must name the probe skill")
        if receipt.get("selected_skill_path") != receipt.get("entry_path"):
            errors.append(f"{label} selected_skill_path must equal entry_path")
    return errors


def validate_durable_artifacts(
    repository: Path, matrix: dict[str, Any], expected_fixture_sha256: str
) -> dict[str, Any]:
    """Validate durable evidence only when its declared artifacts are present.

    A pending matrix with no artifacts is an honest pre-report state. Once a
    report or receipt path exists, partial or mismatched evidence is invalid;
    it cannot be treated as a completed backend matrix.
    """
    durable = matrix.get("durable_record")
    if not isinstance(durable, dict):
        return {"state": "invalid", "complete": False, "errors": ["matrix has no durable_record"]}
    report_relative = _repo_relative_path(durable.get("report"))
    receipts_relative = _repo_relative_path(durable.get("receipt_directory"))
    if report_relative is None or receipts_relative is None:
        return {
            "state": "invalid", "complete": False,
            "errors": ["durable_record paths are not contained repository-relative paths"],
        }
    report = repository / report_relative
    receipt_directory = repository / receipts_relative
    if not report.exists() and not receipt_directory.exists():
        return {"state": "pending", "complete": False, "errors": []}
    errors: list[str] = []
    report_text = ""
    if not report.is_file():
        errors.append("durable report is missing")
    else:
        report_text = report.read_text(encoding="utf-8")
        if expected_fixture_sha256 not in report_text:
            errors.append("durable report does not bind fixture_sha256")
        if evidence_contract_sha256(matrix) not in report_text:
            errors.append("durable report does not bind evidence contract hash")
    cells = matrix.get("required_cells")
    if not isinstance(cells, list):
        cells = []
    template = durable.get("receipt_filename_template")
    if not isinstance(template, str):
        template = ""
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        name = template.format(surface=cell.get("surface"), version=cell.get("version"))
        receipt_path = receipt_directory / name
        label = f"receipt {name}"
        if not receipt_path.is_file():
            errors.append(f"{label} is missing")
            continue
        try:
            raw_receipt = receipt_path.read_text(encoding="utf-8")
            if SECRET_VALUE.search(raw_receipt):
                raise ValueError("untrusted receipt")
            receipt = json.loads(
                raw_receipt,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, ValueError):
            errors.append(f"{label} is invalid or contains untrusted fields")
            continue
        receipt_errors = _receipt_errors(
            receipt,
            cell,
            expected_fixture_sha256,
            evidence_contract_sha256(matrix),
            label,
        )
        if receipt_errors:
            errors.extend(receipt_errors)
            continue
        receipt_digest = sha256_file(receipt_path)
        if receipt_digest not in report_text:
            errors.append(f"{label} SHA-256 is not bound by durable report")
    return {"state": "complete" if not errors else "invalid", "complete": not errors, "errors": errors}


def validate_fixture(
    root: Path, *, repository: Path = REPO_ROOT
) -> dict[str, Any]:
    """Return deterministic fixture data and every offline contract violation."""
    root = root.resolve()
    repository = repository.resolve()
    errors: list[str] = []
    _validate_manifest(root, errors)
    _validate_resource_links(root, errors)
    matrix = _read_json(root / "matrix.json", errors, "matrix")
    _validate_matrix(matrix, errors)
    digest = fixture_sha256(root) if root.is_dir() else ""
    contract_digest = evidence_contract_sha256(matrix)
    durable_evidence = validate_durable_artifacts(repository, matrix, digest)
    errors.extend(durable_evidence["errors"])
    return {
        "fixture_sha256": digest,
        "evidence_contract_sha256": contract_digest,
        "matrix": matrix,
        "durable_evidence": durable_evidence,
        "errors": errors,
    }


def validate_durable_record(
    record: dict[str, Any], matrix: dict[str, Any], expected_fixture_sha256: str
) -> list[str]:
    """Fail closed when a later report/receipt record drifts from this fixture."""
    errors: list[str] = []
    durable = matrix.get("durable_record")
    if not isinstance(record, dict):
        return ["durable record must be an object"]
    if not isinstance(durable, dict):
        return ["matrix has no valid durable_record binding"]
    for field in ("report", "receipt_directory"):
        expected = durable.get(field)
        if record.get(field) != expected:
            errors.append(f"durable record {field} does not match matrix binding")
    field = durable.get("fixture_sha256_field")
    if not isinstance(field, str) or record.get(field) != expected_fixture_sha256:
        errors.append("durable record fixture_sha256 does not match fixture hash")
    if record.get("evidence_contract_sha256") != evidence_contract_sha256(matrix):
        errors.append("durable record evidence_contract_sha256 does not match matrix contract")
    return errors


def validate_live_observation(
    observation: object,
    installed_plugin_root: Path,
    operation_transcript: str,
    operation_events: list[dict[str, Any]],
) -> list[str]:
    """Validate a host observation without trusting its claimed verdict.

    ``operation_transcript`` is deliberately limited to executed operation text;
    prompts and ordinary agent prose may mention forbidden fallback techniques.
    """
    if not isinstance(observation, dict):
        return ["live observation must be a JSON object"]
    observation_fields = frozenset({
        "entry_path", "resource_reads", "requested_sandbox", "effective_sandbox",
        "requested_approval_policy", "effective_approval_policy",
    })
    if set(observation) != observation_fields:
        return ["live observation must contain exact fields"]
    errors: list[str] = []
    root = installed_plugin_root.resolve()
    entry_value = observation.get("entry_path")
    entry = Path(entry_value) if isinstance(entry_value, str) else Path()
    if not isinstance(entry_value, str) or not entry.is_absolute():
        errors.append("entry_path must be absolute")
    elif entry.resolve() != (root / "skills" / "probe" / "SKILL.md").resolve():
        errors.append("entry_path must name the installed probe skill")

    reads = observation.get("resource_reads")
    if not isinstance(reads, list) or len(reads) != 3:
        errors.append("resource_reads must contain exactly three direct reads")
        reads = []
    actual_nonces: list[object] = []
    actual_paths: set[Path] = set()
    for index, read in enumerate(reads):
        if not isinstance(read, dict):
            errors.append(f"resource read #{index + 1} must be an object")
            continue
        if set(read) != {"path", "nonce"}:
            errors.append(f"resource read #{index + 1} must contain exact fields")
            continue
        path_value = read.get("path")
        path = Path(path_value) if isinstance(path_value, str) else Path()
        if not isinstance(path_value, str) or not path.is_absolute():
            errors.append(f"resource read #{index + 1} path must be absolute")
            continue
        resolved = path.resolve()
        if not _contained(root, resolved):
            errors.append(f"resource read #{index + 1} path must be contained in installed plugin")
            continue
        actual_paths.add(resolved)
        actual_nonces.append(read.get("nonce"))
    expected_paths = {(root / relative).resolve() for relative in RESOURCE_FILES}
    if actual_paths != expected_paths:
        errors.append("resource reads must name the exact three installed fixture paths")
    if len(set(actual_nonces)) != 3:
        errors.append("resource reads must return three distinct nonces")
    expected_nonces = set(EXPECTED_NONCES.values())
    if set(actual_nonces) != expected_nonces:
        errors.append("resource reads do not return the fixture's exact nonces")

    if SEARCH_OR_GLOB.search(operation_transcript):
        errors.append("operation transcript contains cache search/glob fallback")
    successful_reads, command_errors = _successful_direct_reads(operation_events or [])
    errors.extend(command_errors)
    for expected_path in expected_paths:
        if expected_path not in successful_reads:
            errors.append(
                f"operation evidence has no successful direct-read event for {expected_path.name}"
            )
        elif EXPECTED_NONCES[expected_path.relative_to(root)] not in successful_reads[expected_path]:
            errors.append(
                f"successful direct-read event for {expected_path.name} has no expected nonce output"
            )
    if len(successful_reads) != len(expected_paths):
        errors.append("operation evidence must contain exactly three successful direct reads")
    requested_sandbox = observation.get("requested_sandbox")
    effective_sandbox = observation.get("effective_sandbox")
    if requested_sandbox != "read-only":
        errors.append("requested sandbox must be read-only")
    if effective_sandbox != requested_sandbox:
        errors.append("effective sandbox does not match requested read-only sandbox")
    requested_approval = observation.get("requested_approval_policy")
    effective_approval = observation.get("effective_approval_policy")
    if requested_approval != "never":
        errors.append("requested approval policy must be never")
    if effective_approval != requested_approval:
        errors.append("effective approval policy does not match requested never policy")
    return errors


def _completed_command_items(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        method = str(message.get("method", "")).casefold()
        message_type = str(message.get("type", "")).casefold().replace("_", ".")
        item: object = None
        if method == "item/completed":
            params = message.get("params")
            item = params.get("item") if isinstance(params, dict) else None
        elif message_type == "item.completed":
            item = message.get("item")
        elif message_type == "command.completed":
            item = message
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).casefold().replace("_", "").replace("-", "")
        if message_type == "command.completed" or item_type == "commandexecution":
            items.append(item)
    return items


def _unquote_token(value: object) -> str:
    token = str(value).strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _direct_read_representation(value: object) -> Path | None:
    if isinstance(value, list) and all(isinstance(token, str) for token in value):
        tokens = list(value)
        raw = " ".join(tokens)
    elif isinstance(value, str):
        raw = value
        try:
            tokens = shlex.split(value, posix=False)
        except ValueError:
            return None
    else:
        return None
    if any(marker in raw for marker in (";", "&&", "||", "|", ">", "<", "*", "?")):
        return None
    tokens = [_unquote_token(token) for token in tokens]
    if not tokens:
        return None
    lowered = [Path(token).name.casefold() for token in tokens]
    wrapper = lowered[0]
    powershell_wrapper = wrapper in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
    cmd_wrapper = wrapper in {"cmd", "cmd.exe"}
    if powershell_wrapper or cmd_wrapper:
        markers = {"-command", "-c"} if powershell_wrapper else {"/c"}
        marker_indexes = [index for index, token in enumerate(lowered) if token in markers]
        if len(marker_indexes) != 1:
            return None
        marker_index = marker_indexes[0]
        options = lowered[1:marker_index]
        if powershell_wrapper:
            option_index = 0
            while option_index < len(options):
                option = options[option_index]
                if option in {"-nologo", "-noprofile", "-noninteractive"}:
                    option_index += 1
                elif (
                    option == "-executionpolicy"
                    and option_index + 1 < len(options)
                    and options[option_index + 1] == "bypass"
                ):
                    option_index += 2
                else:
                    return None
        elif any(option not in {"/d", "/q", "/s"} for option in options):
            return None
        body = tokens[marker_index + 1:]
        if not body:
            return None
        if len(body) == 1:
            try:
                tokens = shlex.split(body[0], posix=False)
            except ValueError:
                return None
            tokens = [_unquote_token(token) for token in tokens]
        else:
            tokens = body
        lowered = [Path(token).name.casefold() for token in tokens]
    if not lowered or lowered[0] not in {"get-content", "get-content.exe"}:
        return None
    arguments = tokens[1:]
    folded = [value.casefold() for value in arguments]
    if "-literalpath" not in folded:
        return None
    path_index = folded.index("-literalpath") + 1
    if path_index >= len(arguments):
        return None
    path_value = arguments[path_index]
    remaining = arguments[:path_index - 1] + arguments[path_index + 1:]
    if any(value.casefold() not in {"-raw"} for value in remaining):
        return None
    path = Path(path_value)
    return path.resolve() if path.is_absolute() else None


def _direct_read_path(item: dict[str, Any]) -> Path | None:
    representations: list[object] = []
    for field in ("command", "commandLine", "command_line", "argv"):
        if field in item:
            representations.append(item[field])
    if not representations:
        return None
    paths = [_direct_read_representation(value) for value in representations]
    if any(path is None for path in paths):
        return None
    resolved = {path for path in paths if path is not None}
    return next(iter(resolved)) if len(resolved) == 1 else None


def _successful_direct_reads(
    messages: list[dict[str, Any]],
) -> tuple[dict[Path, str], list[str]]:
    successful: dict[Path, str] = {}
    errors: list[str] = []
    items = _completed_command_items(messages)
    for index, item in enumerate(items):
        exit_code = item.get("exit_code", item.get("exitCode"))
        status = str(item.get("status", "")).casefold()
        path = _direct_read_path(item)
        if exit_code != 0 or status not in {"completed", "success", "succeeded"} or path is None:
            errors.append(f"command event #{index + 1} is not a successful direct read")
            continue
        output = item.get(
            "aggregated_output", item.get("aggregatedOutput", item.get("output", ""))
        )
        successful[path] = output if isinstance(output, str) else ""
    if len(items) != 3:
        errors.append("operation evidence must contain exactly three completed command events")
    return successful, errors


def _failure_classification(stdout: str, stderr: str) -> str:
    failure_text = f"{stdout}\n{stderr}".lower()
    if "401 unauthorized" in failure_text and (
        "missing bearer" in failure_text or "missing basic authentication" in failure_text
    ):
        return "authentication-required"
    if "policy" in failure_text and (
        "read-only" in failure_text or "sandbox" in failure_text
    ) and any(word in failure_text for word in ("reject", "block", "denied", "deny")):
        return "read-only-policy-rejection"
    return "runtime-or-contract-failure"


def _canonical_live_evidence_hashes(
    observed: dict[str, Any], errors: list[str], stdout: str, stderr: str
) -> tuple[str, str, str]:
    """Hash only reconstructed allowlisted facts, never raw runtime streams."""
    if errors:
        classification = _failure_classification(stdout, stderr)
        return (
            _sha256_text(f"live-operation-evidence:v1:{classification}"),
            _sha256_text(f"live-stdout-classification:v1:{classification}"),
            _sha256_text(
                "" if stderr == "" else f"live-stderr-classification:v1:{classification}"
            ),
        )
    reads = sorted(
        (
            {"path": read["path"], "nonce": read["nonce"], "method": "direct-read"}
            for read in observed["resource_reads"]
        ),
        key=lambda read: (read["path"], read["nonce"]),
    )
    observation = {
        "entry_path": observed["entry_path"],
        "resource_reads": [
            {"path": read["path"], "nonce": read["nonce"]} for read in reads
        ],
        "requested_sandbox": observed["requested_sandbox"],
        "effective_sandbox": observed["effective_sandbox"],
        "requested_approval_policy": observed["requested_approval_policy"],
        "effective_approval_policy": observed["effective_approval_policy"],
    }
    return (
        _sha256_text(
            "live-operation-evidence:v1:"
            + json.dumps(reads, separators=(",", ":"), sort_keys=True)
        ),
        _sha256_text(
            "live-observation-evidence:v1:"
            + json.dumps(observation, separators=(",", ":"), sort_keys=True)
        ),
        _sha256_text("" if stderr == "" else "live-stderr-classification:v1:present"),
    )


def build_live_receipt(
    *,
    surface: str,
    version: str,
    expected: dict[str, Any],
    fixture_hash: str,
    evidence_contract_hash: str,
    executable: Path,
    installed_plugin_root: Path,
    observation: object,
    operation_transcript: str,
    operation_events: list[dict[str, Any]] | None = None,
    stdout: str,
    stderr: str,
    network_policy: str,
    advisory: bool,
) -> dict[str, Any]:
    """Build a deterministic, non-secret backend receipt from observed behavior."""
    untrusted = bool(_secret_bearing({
        "observation": observation,
        "operation_transcript": operation_transcript,
        "operation_events": operation_events or [],
        "stdout": stdout,
        "stderr": stderr,
    }))
    observation_errors = validate_live_observation(
        observation, installed_plugin_root, operation_transcript, operation_events
    )
    errors = (
        ["live evidence contains untrusted output"] if untrusted else observation_errors
    )
    executable_hash = sha256_file(executable)
    if executable_hash != expected.get("native_executable_sha256"):
        errors.append("native executable hash does not match pinned matrix")
    persist_observation = not errors and isinstance(observation, dict)
    observed = observation if persist_observation else {}
    observed_reads = [
        {"path": read["path"], "nonce": read["nonce"]}
        for read in observed.get("resource_reads", [])
        if isinstance(read, dict) and set(read) == {"path", "nonce"}
    ]
    canonical_hashes = (
        None
        if untrusted
        else _canonical_live_evidence_hashes(observed, errors, stdout, stderr)
    )
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": "advisory" if advisory else "supported",
        "verdict": "FAIL" if errors else "PASS",
        "surface": surface,
        "version": version,
        "desktop_shell_proven": False,
        "provenance": expected.get("provenance"),
        "integrity": expected.get("integrity"),
        "native_executable_sha256": executable_hash,
        "fixture_sha256": fixture_hash,
        "evidence_contract_sha256": evidence_contract_hash,
        "installed_plugin_root": str(installed_plugin_root.resolve()),
        "entry_path": observed.get("entry_path"),
        "resource_reads": observed_reads,
        "requested_sandbox": observed.get("requested_sandbox"),
        "effective_sandbox": observed.get("effective_sandbox"),
        "requested_approval_policy": observed.get("requested_approval_policy"),
        "effective_approval_policy": observed.get("effective_approval_policy"),
        "network_policy": network_policy,
        "environment": {
            "os": os.name,
            "platform": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "os_identity": platform.platform(),
            "execution_environment": (
                "container" if os.environ.get("CA_CODEX_BASE_IMAGE") else "isolated-clean-home"
            ),
            "base_image": os.environ.get("CA_CODEX_BASE_IMAGE"),
        },
        "operation_transcript_sha256": canonical_hashes[0] if canonical_hashes else None,
        "stdout_sha256": canonical_hashes[1] if canonical_hashes else None,
        "stderr_sha256": (
            canonical_hashes[2] if canonical_hashes else (_sha256_text("") if stderr == "" else None)
        ),
        "errors": errors,
    }
    receipt["errors_sha256"] = _errors_sha256(errors)
    if errors:
        receipt["failure"] = {
            "classification": _failure_classification(stdout, stderr),
            "stdout_sha256": receipt["stdout_sha256"],
            "stderr_sha256": receipt["stderr_sha256"],
            "operation_transcript_sha256": receipt["operation_transcript_sha256"],
            "errors_sha256": receipt["errors_sha256"],
        }
    return receipt


def _codex_command(executable: Path) -> list[str]:
    """Return an executable prefix; Python scripts are supported as test drivers."""
    if executable.suffix.lower() == ".py":
        return [sys.executable, str(executable)]
    return [str(executable)]


def _isolated_environment(
    codex_home: Path,
    extra_environment: dict[str, str] | None = None,
    *,
    profile_root: Path | None = None,
) -> dict[str, str]:
    """Build a process environment without inheriting credential-bearing values."""
    allowed = {
        "COMSPEC", "LANG", "LC_ALL", "PATH", "PATHEXT", "SYSTEMDRIVE",
        "SYSTEMROOT", "TEMP", "TMP", "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    profile_root = (profile_root or codex_home.parent / "profile").resolve()
    appdata = profile_root / "AppData" / "Roaming"
    local_appdata = profile_root / "AppData" / "Local"
    xdg_config = profile_root / ".config"
    xdg_cache = profile_root / ".cache"
    for directory in (profile_root, appdata, local_appdata, xdg_config, xdg_cache):
        directory.mkdir(parents=True, exist_ok=True)
    environment["CODEX_HOME"] = str(codex_home.resolve())
    environment["HOME"] = str(profile_root.resolve())
    environment["USERPROFILE"] = str(profile_root.resolve())
    environment["APPDATA"] = str(appdata.resolve())
    environment["LOCALAPPDATA"] = str(local_appdata.resolve())
    environment["XDG_CONFIG_HOME"] = str(xdg_config.resolve())
    environment["XDG_CACHE_HOME"] = str(xdg_cache.resolve())
    environment["PYTHONIOENCODING"] = "utf-8"
    for key, value in (extra_environment or {}).items():
        upper = key.upper()
        if any(secret in upper for secret in ("TOKEN", "SECRET", "PASSWORD", "COOKIE", "API_KEY")):
            raise ValueError(f"refusing credential-like live environment key: {key}")
        environment[key] = value
    return environment


def validated_authenticated_codex_home(
    value: str,
    repository: Path,
    *,
    surface: str,
    version: str,
    advisory: bool,
) -> Path:
    """Return a controller-owned temporary Codex home or fail closed."""
    candidate = Path(value)
    if not candidate.is_absolute():
        raise ValueError("--authenticated-codex-home must be an absolute path")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise ValueError("--authenticated-codex-home must name an existing directory")
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if resolved == temporary_root or not _contained(temporary_root, resolved):
        raise ValueError("--authenticated-codex-home must be below the OS temporary directory")
    version_parts = version.split(".")
    version_token = (
        "".join(version_parts[:2])
        if len(version_parts) >= 2 and all(part.isdigit() for part in version_parts[:2])
        else ""
    )
    cell = "advisory" if advisory else surface
    expected_parent = temporary_root / "codearbiter-stage1-oauth"
    expected_name = re.fullmatch(
        re.escape(f"{cell}-{version_token}-auth-") + r"[0-9]{8}T[0-9]{4}Z",
        resolved.name,
        flags=re.IGNORECASE,
    )
    if resolved.parent != expected_parent or not version_token or expected_name is None:
        raise ValueError(
            "--authenticated-codex-home must name the exact controller-owned cell root"
        )
    repository = repository.resolve()
    if resolved == repository or _contained(repository, resolved):
        raise ValueError("--authenticated-codex-home must be outside the repository")
    return resolved


def _run_command(
    command: list[str], *, environment: dict[str, str], cwd: Path, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _chatgpt_login_error(
    prefix: list[str], environment: dict[str, str], repository: Path
) -> str | None:
    """Verify ChatGPT login without returning or retaining command output."""
    result = _run_command(
        prefix + ["login", "status"], environment=environment, cwd=repository
    )
    status_text = "\n".join((result.stdout, result.stderr))
    if result.returncode == 0 and re.search(
        r"(?im)^\s*Logged in using ChatGPT\s*$", status_text
    ):
        return None
    return "isolated CODEX_HOME must report a successful ChatGPT login"


def reported_codex_version(stdout: str) -> str | None:
    match = re.search(r"(?m)^codex-cli\s+([^\s]+)\s*$", stdout)
    return match.group(1) if match else None


def _prepare_marketplace(root: Path, fixture_root: Path) -> Path:
    marketplace = root / "marketplace"
    (marketplace / ".agents" / "plugins").mkdir(parents=True)
    shutil.copytree(fixture_root, marketplace / "plugin")
    manifest = {
        "name": "codex-skill-resource-characterization",
        "owner": {"name": "arbiterForge"},
        "plugins": [
            {"name": "codex-skill-resource-probe", "source": "./plugin"}
        ],
    }
    (marketplace / ".agents" / "plugins" / "marketplace.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return marketplace


def _operation_transcript(stdout: str) -> str:
    operations: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {
                    "command", "commandLine", "command_line", "argv", "query", "pattern"
                }:
                    operations.append(
                        " ".join(str(item) for item in child)
                        if isinstance(child, list) else str(child)
                    )
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for line in stdout.splitlines():
        try:
            collect(json.loads(line))
        except json.JSONDecodeError:
            continue
    return "\n".join(operations)


def _jsonl_messages(stdout: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            messages.append(value)
    return messages


def _cli_skill_invocation_evidence(
    messages: list[dict[str, Any]], expected_name: str, expected_path: Path
) -> tuple[dict[str, Any] | None, list[str]]:
    invocation_events: list[tuple[object, object]] = []
    for message in messages:
        message_type = str(message.get("type", "")).casefold().replace("_", ".")
        candidate: object = None
        status: object = message.get("status")
        is_invocation = False
        if message_type in {"skill.invoked", "skill.invocation.completed"}:
            is_invocation = True
            candidate = message.get("skill")
        elif message_type == "item.completed":
            item = message.get("item")
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).casefold().replace("_", "")
                if item_type == "skillinvocation":
                    is_invocation = True
                    candidate = item
                    status = item.get("status")
        if is_invocation:
            invocation_events.append((candidate, status))
    error = (
        "CLI skill invocation evidence: complete skill invocation event set must be exactly one successful "
        "codex-skill-resource-probe:probe event at the installed absolute SKILL.md path"
    )
    if invocation_events:
        if len(invocation_events) != 1:
            return None, [error]
        candidate, status = invocation_events[0]
        if not isinstance(candidate, dict):
            return None, [error]
        path_value = candidate.get("path")
        path = Path(path_value) if isinstance(path_value, str) else Path()
        if not (
            candidate.get("name") == expected_name
            and path.is_absolute()
            and path.resolve() == expected_path.resolve()
            and str(status).casefold() in {"completed", "success", "succeeded"}
        ):
            return None, [error]
        return {
            "name": expected_name,
            "path": str(expected_path.resolve()),
            "status": str(status),
            "source": "host-skill-event",
        }, []

    expected_nonce = EXPECTED_NONCES[Path("skills/probe/SKILL.md")]
    entry_reads: list[dict[str, Any]] = []
    for item in _completed_command_items(messages):
        path = _direct_read_path(item)
        output = item.get(
            "aggregated_output", item.get("aggregatedOutput", item.get("output", ""))
        )
        if (
            path == expected_path.resolve()
            and item.get("exit_code", item.get("exitCode")) == 0
            and str(item.get("status", "")).casefold()
            in {"completed", "success", "succeeded"}
            and isinstance(output, str)
            and expected_nonce in output
        ):
            entry_reads.append(item)
    if len(entry_reads) != 1:
        return None, [error]
    return {
        "name": expected_name,
        "path": str(expected_path.resolve()),
        "status": "completed",
        "source": "direct-entry-read",
    }, []


def _add_receipt_errors(
    receipt: dict[str, Any], errors: list[str], stdout: str, stderr: str
) -> None:
    if not errors:
        return
    untrusted = bool(_secret_bearing({"errors": errors, "stdout": stdout, "stderr": stderr}))
    untrusted = untrusted or any(
        not isinstance(error, str)
        or len(error) > 256
        or any(ord(character) < 32 for character in error)
        or OPAQUE_CREDENTIAL_COMPONENT.search(error) is not None
        for error in errors
    )
    if untrusted:
        receipt["errors"] = ["live evidence contains untrusted output"]
        receipt["errors_sha256"] = _errors_sha256(receipt["errors"])
        receipt["verdict"] = "FAIL"
        receipt["operation_transcript_sha256"] = None
        receipt["stdout_sha256"] = None
        receipt["stderr_sha256"] = None
        receipt["failure"] = {
            "classification": "runtime-or-contract-failure",
            "stdout_sha256": None,
            "stderr_sha256": None,
            "operation_transcript_sha256": None,
            "errors_sha256": receipt["errors_sha256"],
        }
        return
    receipt["errors"].extend(errors)
    receipt["errors_sha256"] = _errors_sha256(receipt["errors"])
    receipt["verdict"] = "FAIL"
    receipt["failure"] = {
        "classification": _failure_classification(stdout, stderr),
        "stdout_sha256": receipt["stdout_sha256"],
        "stderr_sha256": receipt["stderr_sha256"],
        "operation_transcript_sha256": receipt["operation_transcript_sha256"],
        "errors_sha256": receipt["errors_sha256"],
    }


def _verify_installed_bytes(
    fixture_root: Path, installed_root: Path
) -> list[str]:
    errors: list[str] = []
    compared = (Path(".codex-plugin/plugin.json"),) + RESOURCE_FILES
    for relative in compared:
        source = fixture_root / relative
        installed = installed_root / relative
        if not installed.is_file():
            errors.append(f"installed plugin is missing {relative.as_posix()}")
        elif installed.read_bytes() != source.read_bytes():
            errors.append(f"installed plugin bytes drift for {relative.as_posix()}")
    return errors


def run_cli_live(
    *,
    executable: Path,
    version: str,
    expected: dict[str, Any],
    fixture_root: Path,
    repository: Path,
    advisory: bool = False,
    authenticated_codex_home: Path | None = None,
    extra_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one fresh, isolated CLI probe and return a fail-closed receipt."""
    executable = executable.resolve()
    fixture_hash = fixture_sha256(fixture_root)
    matrix = _read_json(fixture_root / "matrix.json", [], "matrix")
    contract_hash = evidence_contract_sha256(matrix)
    with tempfile.TemporaryDirectory(prefix="codearbiter-codex-resource-") as temporary:
        root = Path(temporary)
        codex_home = (
            authenticated_codex_home.resolve()
            if authenticated_codex_home is not None
            else root / "codex-home"
        )
        if authenticated_codex_home is None:
            codex_home.mkdir()
        if sha256_file(executable) != expected.get("native_executable_sha256"):
            receipt = build_live_receipt(
                surface="cli",
                version=version,
                expected=expected,
                fixture_hash=fixture_hash,
                evidence_contract_hash=contract_hash,
                executable=executable,
                installed_plugin_root=codex_home / "plugins" / "unresolved",
                observation={},
                operation_transcript="",
                operation_events=[],
                stdout="",
                stderr="",
                network_policy="model-api-only; tool-network-disabled",
                advisory=advisory,
            )
            receipt["environment"]["codex_home"] = str(codex_home)
            return receipt
        environment = _isolated_environment(
            codex_home, extra_environment, profile_root=root / "profile"
        )
        prefix = _codex_command(executable)
        harness_errors: list[str] = []

        if authenticated_codex_home is not None:
            authentication_error = _chatgpt_login_error(prefix, environment, repository)
            if authentication_error is not None:
                receipt = build_live_receipt(
                    surface="cli",
                    version=version,
                    expected=expected,
                    fixture_hash=fixture_hash,
                    evidence_contract_hash=contract_hash,
                    executable=executable,
                    installed_plugin_root=codex_home / "plugins" / "unresolved",
                    observation={},
                    operation_transcript="",
                    operation_events=[],
                    stdout="",
                    stderr="",
                    network_policy="model-api-only; tool-network-disabled",
                    advisory=advisory,
                )
                receipt["environment"]["codex_home"] = str(codex_home)
                _add_receipt_errors(receipt, [authentication_error], "", "")
                return receipt

        version_result = _run_command(prefix + ["--version"], environment=environment, cwd=repository)
        if version_result.returncode != 0 or reported_codex_version(version_result.stdout) != version:
            harness_errors.append(f"requested Codex version {version} was not reported by exact binary")

        marketplace = _prepare_marketplace(root, fixture_root)
        add_marketplace = _run_command(
            prefix + ["plugin", "marketplace", "add", str(marketplace), "--json"],
            environment=environment,
            cwd=repository,
        )
        add_plugin = _run_command(
            prefix + ["plugin", "add", "codex-skill-resource-probe@codex-skill-resource-characterization", "--json"],
            environment=environment,
            cwd=repository,
        )
        if add_marketplace.returncode != 0:
            harness_errors.append("host-native marketplace installation failed")
        if add_plugin.returncode != 0:
            harness_errors.append("host-native plugin installation failed")

        output_path = root / "probe-result.json"
        schema_path = root / "probe-result.schema.json"
        schema_path.write_text(
            json.dumps({
                "type": "object",
                "required": [
                    "entry_path", "resource_reads", "requested_sandbox",
                    "effective_sandbox", "requested_approval_policy",
                    "effective_approval_policy",
                ],
                "properties": {
                    "entry_path": {"type": "string"},
                    "resource_reads": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["path", "nonce"],
                            "properties": {
                                "path": {"type": "string"},
                                "nonce": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "requested_sandbox": {"type": "string"},
                    "effective_sandbox": {"type": "string"},
                    "requested_approval_policy": {"type": "string"},
                    "effective_approval_policy": {"type": "string"},
                },
                "additionalProperties": False,
            }),
            encoding="utf-8",
        )
        prompt = (
            "Invoke only $codex-skill-resource-probe:probe. Use exactly three "
            "Get-Content -LiteralPath commands: first directly read the selected entry "
            "SKILL.md at its absolute source path, then follow each of its two relative "
            "links with one Get-Content -LiteralPath command. Do not run any other command; "
            "do not search, glob, enumerate caches, or use network access. Return the entry "
            "absolute path, all three absolute read paths and nonces, and requested/effective "
            "read-only sandbox and never approval policy as the required JSON object."
        )
        live_result = _run_command(
            prefix + [
                "exec", "--json", "--ephemeral", "--ignore-rules",
                "--skip-git-repo-check", "--sandbox", "read-only",
                "--config", 'approval_policy="never"',
                "--config", 'web_search="disabled"',
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
                "--cd", str(repository.resolve()), prompt,
            ],
            environment=environment,
            cwd=repository,
        )
        if live_result.returncode != 0:
            harness_errors.append(f"Codex CLI probe exited {live_result.returncode}")
        try:
            observation: object = json.loads(output_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            observation = {}
            harness_errors.append(f"Codex CLI did not emit a valid observation: {type(error).__name__}")

        entry_value = observation.get("entry_path") if isinstance(observation, dict) else None
        entry = Path(entry_value) if isinstance(entry_value, str) else Path()
        if entry.is_absolute():
            installed_root = entry.resolve().parents[2]
        else:
            installed_root = codex_home / "plugins" / "unresolved"
        plugins_root = (codex_home / "plugins").resolve()
        if not _contained(plugins_root, installed_root.resolve()):
            harness_errors.append("reported installed plugin root is outside isolated CODEX_HOME/plugins")
        else:
            harness_errors.extend(_verify_installed_bytes(fixture_root, installed_root))

        operations = _operation_transcript(live_result.stdout)
        operation_events = _jsonl_messages(live_result.stdout)
        invocation, invocation_errors = _cli_skill_invocation_evidence(
            operation_events,
            "codex-skill-resource-probe:probe",
            (installed_root / "skills" / "probe" / "SKILL.md").resolve(),
        )
        harness_errors.extend(invocation_errors)
        receipt = build_live_receipt(
            surface="cli",
            version=version,
            expected=expected,
            fixture_hash=fixture_hash,
            evidence_contract_hash=contract_hash,
            executable=executable,
            installed_plugin_root=installed_root,
            observation=observation,
            operation_transcript=operations,
            operation_events=operation_events,
            stdout=live_result.stdout,
            stderr=live_result.stderr,
            network_policy="model-api-only; tool-network-disabled",
            advisory=advisory,
        )
        receipt["environment"]["codex_home"] = str(codex_home.resolve())
        if authenticated_codex_home is not None:
            receipt["authentication_mode"] = "chatgpt"
        receipt["skill_invocation_evidence"] = invocation
        _add_receipt_errors(receipt, harness_errors, live_result.stdout, live_result.stderr)
        return receipt


class _JsonlClient:
    """Small synchronous JSONL client with bounded reads for app-server stdio."""

    def __init__(
        self, command: list[str], environment: dict[str, str], cwd: Path
    ) -> None:
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.messages: list[dict[str, Any]] = []
        self.stderr_lines: list[str] = []
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()

        def read_stdout() -> None:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self._stdout_queue.put(line)
            self._stdout_queue.put(None)

        def read_stderr() -> None:
            assert self.process.stderr is not None
            self.stderr_lines.extend(self.process.stderr.readlines())

        self._stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("app-server stdin is unavailable")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _next(self, timeout: float = 20.0) -> dict[str, Any]:
        try:
            line = self._stdout_queue.get(timeout=timeout)
        except queue.Empty as error:
            raise TimeoutError("timed out waiting for app-server JSONL") from error
        if line is None:
            raise RuntimeError("app-server closed stdout before protocol completion")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError("app-server emitted non-JSON stdout") from error
        if not isinstance(message, dict):
            raise RuntimeError("app-server JSONL message is not an object")
        self.messages.append(message)
        return message

    def request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            message = self._next()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"app-server {method} returned an error")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError(f"app-server {method} result is not an object")
                return result

    def notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def read_until(self, method: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        while True:
            message = self._next()
            collected.append(message)
            if message.get("method") == method:
                return collected

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self._stdout_thread.join(timeout=2)
        self._stderr_thread.join(timeout=2)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()

    @property
    def stdout_text(self) -> str:
        return "\n".join(json.dumps(message, sort_keys=True) for message in self.messages)

    @property
    def stderr_text(self) -> str:
        return "".join(self.stderr_lines)


def _sandbox_name(value: object) -> str | None:
    if value == "read-only":
        return "read-only"
    if isinstance(value, dict):
        names = {
            "readOnly": "read-only",
            "workspaceWrite": "workspace-write",
            "dangerFullAccess": "danger-full-access",
        }
        return names.get(value.get("type"))
    return None


def _agent_observation(messages: list[dict[str, Any]]) -> object:
    for message in reversed(messages):
        if message.get("method") != "item/completed":
            continue
        params = message.get("params")
        item = params.get("item") if isinstance(params, dict) else None
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            continue
        text = item.get("text")
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {}
    return {}


def run_app_server_live(
    *,
    executable: Path,
    version: str,
    expected: dict[str, Any],
    fixture_root: Path,
    repository: Path,
    advisory: bool = False,
    authenticated_codex_home: Path | None = None,
    extra_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one isolated app-server protocol probe over exact-binary stdio."""
    executable = executable.resolve()
    fixture_hash = fixture_sha256(fixture_root)
    matrix = _read_json(fixture_root / "matrix.json", [], "matrix")
    contract_hash = evidence_contract_sha256(matrix)
    with tempfile.TemporaryDirectory(prefix="codearbiter-codex-resource-") as temporary:
        root = Path(temporary)
        codex_home = (
            authenticated_codex_home.resolve()
            if authenticated_codex_home is not None
            else root / "codex-home"
        )
        if authenticated_codex_home is None:
            codex_home.mkdir()
        if sha256_file(executable) != expected.get("native_executable_sha256"):
            receipt = build_live_receipt(
                surface="app-server",
                version=version,
                expected=expected,
                fixture_hash=fixture_hash,
                evidence_contract_hash=contract_hash,
                executable=executable,
                installed_plugin_root=codex_home / "plugins" / "unresolved",
                observation={},
                operation_transcript="",
                operation_events=[],
                stdout="",
                stderr="",
                network_policy="model-api-only; tool-network-disabled",
                advisory=advisory,
            )
            receipt["environment"]["codex_home"] = str(codex_home)
            receipt["selected_skill"] = "codex-skill-resource-probe:probe"
            receipt["selected_skill_path"] = None
            return receipt
        environment = _isolated_environment(
            codex_home, extra_environment, profile_root=root / "profile"
        )
        prefix = _codex_command(executable)
        harness_errors: list[str] = []

        if authenticated_codex_home is not None:
            authentication_error = _chatgpt_login_error(prefix, environment, repository)
            if authentication_error is not None:
                receipt = build_live_receipt(
                    surface="app-server",
                    version=version,
                    expected=expected,
                    fixture_hash=fixture_hash,
                    evidence_contract_hash=contract_hash,
                    executable=executable,
                    installed_plugin_root=codex_home / "plugins" / "unresolved",
                    observation={},
                    operation_transcript="",
                    operation_events=[],
                    stdout="",
                    stderr="",
                    network_policy="model-api-only; tool-network-disabled",
                    advisory=advisory,
                )
                receipt["environment"]["codex_home"] = str(codex_home)
                receipt["selected_skill"] = "codex-skill-resource-probe:probe"
                receipt["selected_skill_path"] = None
                _add_receipt_errors(receipt, [authentication_error], "", "")
                return receipt

        version_result = _run_command(prefix + ["--version"], environment=environment, cwd=repository)
        if version_result.returncode != 0 or reported_codex_version(version_result.stdout) != version:
            harness_errors.append(f"requested Codex version {version} was not reported by exact binary")
        marketplace = _prepare_marketplace(root, fixture_root)
        add_marketplace = _run_command(
            prefix + ["plugin", "marketplace", "add", str(marketplace), "--json"],
            environment=environment,
            cwd=repository,
        )
        add_plugin = _run_command(
            prefix + ["plugin", "add", "codex-skill-resource-probe@codex-skill-resource-characterization", "--json"],
            environment=environment,
            cwd=repository,
        )
        if add_marketplace.returncode != 0:
            harness_errors.append("host-native marketplace installation failed")
        if add_plugin.returncode != 0:
            harness_errors.append("host-native plugin installation failed")

        client = _JsonlClient(
            prefix + [
                "app-server", "--stdio", "--config", 'approval_policy="never"',
                "--config", 'sandbox_mode="read-only"',
                "--config", 'web_search="disabled"',
            ],
            environment,
            repository,
        )
        selected_name = "codex-skill-resource-probe:probe"
        selected_path = Path()
        thread_result: dict[str, Any] = {}
        observation: object = {}
        try:
            initialized = client.request(
                1,
                "initialize",
                {
                    "clientInfo": {
                        "name": "codearbiter-skill-resource-checker",
                        "version": "1",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            initialized_home = initialized.get("codexHome")
            if not isinstance(initialized_home, str) or Path(initialized_home).resolve() != codex_home.resolve():
                harness_errors.append("initialize.codexHome does not match isolated CODEX_HOME")
            client.notification("initialized")
            skills = client.request(
                2,
                "skills/list",
                {"cwds": [str(repository.resolve())], "forceReload": True},
            )
            matches: list[dict[str, Any]] = []
            for entry in skills.get("data", []):
                if not isinstance(entry, dict):
                    continue
                for skill in entry.get("skills", []):
                    if isinstance(skill, dict) and skill.get("name") == selected_name:
                        matches.append(skill)
            if len(matches) != 1:
                raise RuntimeError("skills/list did not return exactly one namespaced probe skill")
            path_value = matches[0].get("path")
            selected_path = Path(path_value) if isinstance(path_value, str) else Path()
            if not selected_path.is_absolute():
                raise RuntimeError("skills/list selected skill path is not absolute")
            installed_root = selected_path.resolve().parents[2]
            if not _contained((codex_home / "plugins").resolve(), installed_root):
                harness_errors.append("skills/list selected path is outside isolated CODEX_HOME/plugins")
            else:
                harness_errors.extend(_verify_installed_bytes(fixture_root, installed_root))

            thread_result = client.request(
                3,
                "thread/start",
                {
                    "cwd": str(repository.resolve()),
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "ephemeral": True,
                },
            )
            thread = thread_result.get("thread")
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise RuntimeError("thread/start did not return a thread id")
            effective_sandbox = _sandbox_name(thread_result.get("sandbox"))
            effective_approval = thread_result.get("approvalPolicy")
            sandbox_value = thread_result.get("sandbox")
            if (
                not isinstance(sandbox_value, dict)
                or sandbox_value.get("type") != "readOnly"
                or sandbox_value.get("networkAccess") is not False
            ):
                effective_sandbox = None
                harness_errors.append(
                    "effective app-server sandbox object must be readOnly with networkAccess false"
                )
            client.request(
                4,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [
                        {
                            "type": "text",
                            "text": (
                                "Use the selected probe skill. Follow its relative links with exactly "
                                "three direct reads; do not search, glob, enumerate caches, or use network. "
                                "Return one JSON object: entry_path must be the selected absolute SKILL.md "
                                "path; resource_reads must be an array of exactly three objects, and each "
                                "object must contain only path and nonce strings, where path is the absolute "
                                "file read and nonce is the exact nonce found in that file."
                            ),
                        },
                        {"type": "skill", "name": selected_name, "path": str(selected_path.resolve())},
                    ],
                },
            )
            completed = client.read_until("turn/completed")
            completion = completed[-1].get("params")
            completed_turn = completion.get("turn") if isinstance(completion, dict) else None
            completion_status = (
                completed_turn.get("status") if isinstance(completed_turn, dict) else None
            )
            if completion_status != "completed":
                harness_errors.append("turn/completed status must be completed")
            observation = _agent_observation(completed)
            if isinstance(observation, dict):
                observation["requested_sandbox"] = "read-only"
                observation["effective_sandbox"] = effective_sandbox
                observation["requested_approval_policy"] = "never"
                observation["effective_approval_policy"] = effective_approval
        except (RuntimeError, TimeoutError, OSError, ValueError) as error:
            harness_errors.append(
                f"app-server protocol failed: {type(error).__name__}"
            )
        finally:
            client.close()

        installed_root = (
            selected_path.resolve().parents[2]
            if selected_path.is_absolute()
            else codex_home / "plugins" / "unresolved"
        )
        stdout = client.stdout_text
        stderr = client.stderr_text
        operations = _operation_transcript(stdout)
        receipt = build_live_receipt(
            surface="app-server",
            version=version,
            expected=expected,
            fixture_hash=fixture_hash,
            evidence_contract_hash=contract_hash,
            executable=executable,
            installed_plugin_root=installed_root,
            observation=observation,
            operation_transcript=operations,
            operation_events=client.messages,
            stdout=stdout,
            stderr=stderr,
            network_policy="model-api-only; tool-network-disabled",
            advisory=advisory,
        )
        receipt["environment"]["codex_home"] = str(codex_home.resolve())
        if authenticated_codex_home is not None:
            receipt["authentication_mode"] = "chatgpt"
        receipt["selected_skill"] = selected_name
        receipt["selected_skill_path"] = (
            str(selected_path.resolve()) if selected_path.is_absolute() else None
        )
        _add_receipt_errors(receipt, harness_errors, stdout, stderr)
        return receipt


def _candidate_sha256(path: Path) -> str:
    """Hash an archive directly or a directory as a deterministic path/byte tree."""
    path = path.resolve()
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        return ""
    digest = hashlib.sha256()
    files = _candidate_package_files(path)
    for relative_path in sorted(files):
        relative = relative_path.encode("utf-8")
        content = files[relative_path]
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _candidate_archive_limits() -> dict[str, int]:
    """Return checker-owned ZIP resource limits without trusting the candidate."""
    return dict(EXPECTED_CANDIDATE_ARCHIVE_LIMITS)


def _candidate_package_files(path: Path) -> dict[str, bytes]:
    """Read candidate-owned package files without trusting receipt declarations."""
    path_metadata = path.lstat() if path.exists() or path.is_symlink() else None
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        path.is_symlink()
        or path_metadata is not None
        and getattr(path_metadata, "st_file_attributes", 0) & reparse_flag
    ):
        raise ValueError("candidate package argument must not be a symbolic link")
    path = path.resolve()
    files: dict[str, bytes] = {}
    if path.is_file():
        limits = _candidate_archive_limits()
        if path.stat().st_size > limits["max_archive_bytes"]:
            raise ValueError("candidate archive exceeds the archive-byte limit")
    if path.is_file() and zipfile.is_zipfile(path):
        prefix = "plugins/ca-codex/"
        entries: list[tuple[str, zipfile.ZipInfo]] = []
        archive_paths: list[tuple[str, bool]] = []
        with zipfile.ZipFile(path) as archive:
            archive_entries = archive.infolist()
            if len(archive_entries) > limits["max_entries"]:
                raise ValueError("candidate archive exceeds the entry-count limit")
            total_uncompressed = 0
            for info in archive_entries:
                name = info.filename
                if "\\" in name:
                    raise ValueError("candidate archive path uses a Windows separator")
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("candidate archive contains a non-regular file")
                if info.is_dir():
                    if kind not in (0, stat.S_IFDIR):
                        raise ValueError("candidate archive directory has a non-directory mode")
                    directory = name.rstrip("/")
                    if directory.startswith(prefix):
                        relative_directory = directory[len(prefix):]
                        if relative_directory:
                            archive_paths.append((relative_directory, True))
                    continue
                if kind == stat.S_IFDIR:
                    raise ValueError("candidate archive file has a directory mode")
                if not name.startswith(prefix):
                    raise ValueError("candidate archive contains a file outside plugins/ca-codex")
                relative = name[len(prefix):]
                normalized = posixpath.normpath(relative)
                if (
                    not relative
                    or normalized != relative
                    or normalized.startswith("../")
                ):
                    raise ValueError("candidate archive has an unsafe path")
                if info.flag_bits & 0x1:
                    raise ValueError("candidate archive contains an encrypted file")
                if info.file_size > limits["max_entry_uncompressed_bytes"]:
                    raise ValueError("candidate archive entry exceeds the size limit")
                if info.file_size > limits["max_total_uncompressed_bytes"] - total_uncompressed:
                    raise ValueError("candidate archive exceeds the total expansion limit")
                total_uncompressed += info.file_size
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size
                    > info.compress_size * limits["max_compression_ratio"]
                ):
                    raise ValueError("candidate archive exceeds the compression-ratio limit")
                archive_paths.append((normalized, False))
                entries.append((normalized, info))
            _validate_candidate_archive_paths(archive_paths)
            actual_total = 0
            for relative, info in entries:
                output = io.BytesIO()
                actual_entry = 0
                with archive.open(info, "r") as source:
                    while chunk := source.read(64 * 1024):
                        actual_entry += len(chunk)
                        actual_total += len(chunk)
                        if (
                            actual_entry > info.file_size
                            or actual_entry > limits["max_entry_uncompressed_bytes"]
                            or actual_total > limits["max_total_uncompressed_bytes"]
                        ):
                            raise ValueError("candidate archive expanded beyond declared bounds")
                        output.write(chunk)
                if actual_entry != info.file_size:
                    raise ValueError("candidate archive entry size does not match metadata")
                files[relative] = output.getvalue()
        return files
    if path.is_dir():
        limits = _candidate_archive_limits()
        package_root = path / "plugins" / "ca-codex"
        package_metadata = package_root.lstat() if package_root.exists() or package_root.is_symlink() else None
        if (
            package_root.is_symlink()
            or package_metadata is not None
            and getattr(package_metadata, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("candidate package root must not be a symbolic link")
        if not package_root.is_dir():
            package_root = path
        package_root = package_root.resolve()
        entries: list[tuple[str, Path, os.stat_result]] = []
        pending = [package_root]
        seen_entries = 0
        while pending:
            directory = pending.pop()
            names: list[str] = []
            with os.scandir(directory) as scan:
                for scanned in scan:
                    seen_entries += 1
                    if seen_entries > limits["max_entries"]:
                        raise ValueError("candidate directory exceeds the entry-count limit")
                    names.append(scanned.name)
            for name in sorted(names):
                item = directory / name
                metadata = item.lstat()
                if (
                    item.is_symlink()
                    or getattr(metadata, "st_file_attributes", 0) & reparse_flag
                ):
                    raise ValueError("candidate package contains a symbolic or reparse link")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(item)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("candidate package contains a non-regular file")
                if metadata.st_size > limits["max_entry_uncompressed_bytes"]:
                    raise ValueError("candidate directory entry exceeds the size limit")
                resolved = item.resolve()
                try:
                    relative = resolved.relative_to(package_root).as_posix()
                except ValueError as error:
                    raise ValueError("candidate package file escapes package root") from error
                entries.append((relative, item, metadata))
        _validate_candidate_paths(relative for relative, _, _ in entries)
        total_bytes = 0
        for relative, item, metadata in entries:
            output = io.BytesIO()
            with item.open("rb") as source:
                opened = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                ):
                    raise ValueError("candidate directory entry changed while being read")
                size = opened.st_size
                if size > limits["max_entry_uncompressed_bytes"]:
                    raise ValueError("candidate directory entry exceeds the size limit")
                if size > limits["max_total_uncompressed_bytes"] - total_bytes:
                    raise ValueError("candidate directory exceeds the total-size limit")
                while True:
                    remaining_expected = size - output.tell()
                    chunk = source.read(min(64 * 1024, remaining_expected + 1))
                    if not chunk:
                        break
                    output.write(chunk)
                    if output.tell() > size:
                        raise ValueError("candidate directory entry changed while being read")
            content = output.getvalue()
            if len(content) != size:
                raise ValueError("candidate directory entry changed while being read")
            total_bytes += len(content)
            files[relative] = content
        return files
    raise ValueError("candidate package must be a ca-codex directory or ZIP archive")


WINDOWS_RESERVED_COMPONENTS = frozenset({
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    "com¹", "com²", "com³", "lpt¹", "lpt²", "lpt³",
})
WINDOWS_INVALID_COMPONENT = frozenset('<>:"/\\|?*')


def _windows_candidate_key(relative: str) -> tuple[str, ...]:
    parts = relative.split("/")
    normalized: list[str] = []
    for component in parts:
        if (
            not component
            or component in {".", ".."}
            or component.endswith((".", " "))
            or any(ord(character) < 32 or character in WINDOWS_INVALID_COMPONENT for character in component)
            or component.split(".", 1)[0].rstrip(" .").casefold()
            in WINDOWS_RESERVED_COMPONENTS
        ):
            raise ValueError("candidate package path is not Windows-safe")
        normalized.append(unicodedata.normalize("NFC", component.casefold()))
    return tuple(normalized)


def _validate_candidate_paths(paths: Any) -> None:
    keyed: dict[tuple[str, ...], str] = {}
    for relative in paths:
        key = _windows_candidate_key(relative)
        if key in keyed:
            raise ValueError("candidate package contains a case or Unicode-normalized path collision")
        keyed[key] = relative
    for key in keyed:
        if any(key[:index] in keyed for index in range(1, len(key))):
            raise ValueError("candidate package contains a file/directory prefix collision")


def _validate_candidate_archive_paths(paths: Any) -> None:
    """Validate explicit ZIP files and directories using Windows extraction semantics."""
    keyed: dict[tuple[str, ...], tuple[str, bool]] = {}
    for relative, is_directory in paths:
        key = _windows_candidate_key(relative)
        if key in keyed:
            raise ValueError("candidate package contains a case or Unicode-normalized path collision")
        keyed[key] = (relative, is_directory)
    for key in keyed:
        for index in range(1, len(key)):
            prefix = keyed.get(key[:index])
            if prefix is not None and not prefix[1]:
                raise ValueError("candidate package contains a file/directory prefix collision")


def _markdown_reference_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _markdown_target(value: str) -> str:
    return re.sub(
        rf"\\([{re.escape(string.punctuation)}])",
        r"\1",
        value,
    )


def _markdown_html_tag_spans(text: str) -> list[tuple[int, int]]:
    """Return syntactically bounded CommonMark-style raw HTML tag spans."""
    spans: list[tuple[int, int]] = []
    index = 0
    name_pattern = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
    attribute_pattern = re.compile(r"[A-Za-z_:][A-Za-z0-9_.:-]*")
    while index < len(text):
        start = text.find("<", index)
        if start < 0:
            break
        cursor = start + 1
        closing = cursor < len(text) and text[cursor] == "/"
        if closing:
            cursor += 1
        name = name_pattern.match(text, cursor)
        if name is None:
            index = start + 1
            continue
        cursor = name.end()
        valid = True
        if closing:
            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1
            valid = cursor < len(text) and text[cursor] == ">"
            if valid:
                cursor += 1
        else:
            while cursor < len(text):
                whitespace_start = cursor
                while cursor < len(text) and text[cursor] in " \t":
                    cursor += 1
                if cursor < len(text) and text[cursor] == ">":
                    cursor += 1
                    break
                if text.startswith("/>", cursor):
                    cursor += 2
                    break
                if cursor == whitespace_start:
                    valid = False
                    break
                attribute = attribute_pattern.match(text, cursor)
                if attribute is None:
                    valid = False
                    break
                cursor = attribute.end()
                while cursor < len(text) and text[cursor] in " \t":
                    cursor += 1
                if cursor >= len(text) or text[cursor] != "=":
                    continue
                cursor += 1
                while cursor < len(text) and text[cursor] in " \t":
                    cursor += 1
                if cursor >= len(text):
                    valid = False
                    break
                if text[cursor] in "\"'":
                    quote = text[cursor]
                    cursor += 1
                    closing_quote = text.find(quote, cursor)
                    if closing_quote < 0 or "\n" in text[cursor:closing_quote]:
                        valid = False
                        break
                    cursor = closing_quote + 1
                else:
                    value = re.match(r"[^ \t\r\n\"'=<>`]+", text[cursor:])
                    if value is None:
                        valid = False
                        break
                    cursor += value.end()
            else:
                valid = False
        if valid:
            spans.append((start, cursor))
            index = cursor
        else:
            index = start + 1
    return spans


def _mask_markdown_literal_regions(text: str) -> str:
    """Blank CommonMark literal regions while preserving offsets and line breaks."""
    masked = list(text)
    symbolic_targets = [
        (match.group("target"), match.start("target"))
        for match in SYMBOLIC_INLINE_LINK.finditer(text)
        if not _escaped_at(text, match.start())
        and not (
            match.start() > 0
            and text[match.start() - 1] == "!"
            and not _escaped_at(text, match.start() - 1)
        )
    ]
    symbolic_targets.extend(
        (match.group("plain"), match.start("plain"))
        for match in REFERENCE_DEFINITION.finditer(text)
        if match.group("plain") is not None
        and SYMBOLIC_SEGMENT.search(match.group("plain"))
    )
    symbolic_segments = {
        (offset + segment.start(), offset + segment.end())
        for target, offset in symbolic_targets
        for segment in SYMBOLIC_SEGMENT.finditer(target)
    }

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            if masked[index] not in "\r\n":
                masked[index] = " "

    for match in re.finditer(r"<!--[\s\S]*?-->", text):
        blank(*match.span())
    for span in _markdown_html_tag_spans(text):
        if span not in symbolic_segments:
            blank(*span)

    offset = 0
    fence: tuple[str, int] | None = None
    quote_fence: tuple[str, int] | None = None
    list_fence: tuple[str, int, int] | None = None
    indented_code = False
    previous_blank = True
    for line in text.splitlines(keepends=True):
        visible = "".join(masked[offset:offset + len(line)])
        line_blank = not visible.strip()
        line_indented = visible.startswith("\t") or visible.startswith("    ")
        quote = re.match(r"^(?: {0,3}>[ \t]?)+(?P<body>.*)$", visible)
        quote_body = quote.group("body") if quote else ""
        if list_fence is not None:
            marker_character, marker_length, content_indent = list_fence
            if line_blank:
                blank(offset, offset + len(line))
                previous_blank = True
                offset += len(line)
                continue
            leading_spaces = len(visible) - len(visible.lstrip(" "))
            if leading_spaces >= content_indent:
                list_body = visible[content_indent:]
                blank(offset, offset + len(line))
                closing = re.match(
                    rf" {{0,3}}{re.escape(marker_character)}{{{marker_length},}}"
                    rf"[ \t]*(?:\r?\n)?$",
                    list_body,
                )
                if closing:
                    list_fence = None
                previous_blank = line_blank
                offset += len(line)
                continue
            list_fence = None
        list_item = re.match(
            r"^(?P<prefix> {0,3}(?:[-+*]|[0-9]{1,9}[.)])[ \t]+)(?P<body>.*)$",
            visible,
        )
        list_marker = (
            re.match(r" {0,3}(`{3,}|~{3,})", list_item.group("body"))
            if list_item else None
        )
        if fence is None and quote_fence is None and list_marker:
            run = list_marker.group(1)
            list_fence = (run[0], len(run), len(list_item.group("prefix")))
            blank(offset, offset + len(line))
            previous_blank = line_blank
            offset += len(line)
            continue
        if quote_fence is not None:
            if quote:
                blank(offset, offset + len(line))
                closing = re.match(
                    rf" {{0,3}}{re.escape(quote_fence[0])}{{{quote_fence[1]},}}"
                    rf"[ \t]*(?:\r?\n)?$",
                    quote_body,
                )
                if closing:
                    quote_fence = None
                previous_blank = line_blank
                offset += len(line)
                continue
            quote_fence = None
        quote_marker = re.match(r" {0,3}(`{3,}|~{3,})", quote_body) if quote else None
        if fence is None and quote_marker:
            run = quote_marker.group(1)
            quote_fence = (run[0], len(run))
            blank(offset, offset + len(line))
            previous_blank = line_blank
            offset += len(line)
            continue
        if fence is None and quote and (
            quote.group("body").startswith("\t")
            or quote.group("body").startswith("    ")
        ):
            blank(offset, offset + len(line))
            previous_blank = line_blank
            offset += len(line)
            continue
        if fence is None and indented_code:
            if line_blank or line_indented:
                blank(offset, offset + len(line))
                previous_blank = line_blank
                offset += len(line)
                continue
            indented_code = False
        if fence is None and previous_blank and line_indented:
            indented_code = True
            blank(offset, offset + len(line))
            previous_blank = line_blank
            offset += len(line)
            continue
        marker = re.match(r" {0,3}(`{3,}|~{3,})", visible)
        if fence is None and marker:
            run = marker.group(1)
            fence = (run[0], len(run))
            blank(offset, offset + len(line))
        elif fence is not None:
            blank(offset, offset + len(line))
            closing = re.match(
                rf" {{0,3}}{re.escape(fence[0])}{{{fence[1]},}}[ \t]*(?:\r?\n)?$",
                visible,
            )
            if closing:
                fence = None
        previous_blank = line_blank
        offset += len(line)

    visible = "".join(masked)
    index = 0
    while index < len(visible):
        if visible[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < len(visible) and visible[run_end] == "`":
            run_end += 1
        delimiter = visible[index:run_end]
        closing = -1
        search = run_end
        while search < len(visible):
            candidate = visible.find("`", search)
            if candidate < 0:
                break
            candidate_end = candidate
            while candidate_end < len(visible) and visible[candidate_end] == "`":
                candidate_end += 1
            if candidate_end - candidate == len(delimiter):
                closing = candidate
                break
            search = candidate_end
        if closing < 0:
            index = run_end
            continue
        blank(index, closing + len(delimiter))
        visible = "".join(masked)
        index = closing + len(delimiter)

    visible = "".join(masked)
    for match in re.finditer(
        r"(?<!\\)(?:\\|!)\[[^\]\n]*\](?:\([^\n)]*\)|\[[^\]\n]*\])?",
        visible,
    ):
        blank(*match.span())
    return "".join(masked)


def _inside(span_start: int, spans: list[tuple[int, int]]) -> bool:
    index = bisect_right(spans, (span_start, sys.maxsize)) - 1
    return index >= 0 and span_start < spans[index][1]


def _escaped_at(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return bool(backslashes % 2)


def _inline_markdown_links(text: str) -> list[tuple[str, tuple[int, int]]]:
    """Scan inline links with bounded bracket/parenthesis balancing."""
    results: list[tuple[str, tuple[int, int]]] = []
    index = 0
    while index < len(text):
        if (
            text[index] != "["
            or _escaped_at(text, index)
            or index > 0 and text[index - 1] == "!" and not _escaped_at(text, index - 1)
        ):
            index += 1
            continue

        label_depth = 1
        cursor = index + 1
        while cursor < len(text) and label_depth:
            if text[cursor] in "\r\n":
                break
            if text[cursor] == "\\" and cursor + 1 < len(text):
                cursor += 2
                continue
            if text[cursor] == "[":
                label_depth += 1
            elif text[cursor] == "]":
                label_depth -= 1
            cursor += 1
        if label_depth or cursor >= len(text) or text[cursor] != "(":
            index += 1
            continue

        cursor += 1
        while cursor < len(text) and text[cursor] in " \t":
            cursor += 1
        destination_start = cursor
        destination_end = cursor
        if cursor < len(text) and text[cursor] == "<":
            destination_start = cursor + 1
            cursor += 1
            while cursor < len(text) and text[cursor] not in ">\r\n":
                if text[cursor] == "\\" and cursor + 1 < len(text):
                    cursor += 2
                else:
                    cursor += 1
            if cursor >= len(text) or text[cursor] != ">":
                raise ValueError("candidate resource contains an unsupported inline link")
            destination_end = cursor
            cursor += 1
        else:
            parenthesis_depth = 0
            while cursor < len(text):
                character = text[cursor]
                if character == "\\" and cursor + 1 < len(text):
                    cursor += 2
                    continue
                if character == "(":
                    parenthesis_depth += 1
                    if parenthesis_depth > 32:
                        raise ValueError("candidate resource inline link nesting exceeds limit")
                elif character == ")":
                    if parenthesis_depth == 0:
                        destination_end = cursor
                        break
                    parenthesis_depth -= 1
                elif character in " \t\r\n" and parenthesis_depth == 0:
                    destination_end = cursor
                    break
                cursor += 1
            else:
                raise ValueError("candidate resource contains an unterminated inline link")

        while cursor < len(text) and text[cursor] in " \t\r\n":
            cursor += 1
        if cursor >= len(text):
            raise ValueError("candidate resource contains an unterminated inline link")
        if text[cursor] != ")":
            opener = text[cursor]
            closer = {"\"": "\"", "'": "'", "(": ")"}.get(opener)
            if closer is None:
                raise ValueError("candidate resource contains an unsupported inline link title")
            cursor += 1
            while cursor < len(text):
                if text[cursor] == "\\" and cursor + 1 < len(text):
                    cursor += 2
                    continue
                if text[cursor] == closer:
                    break
                if text[cursor] in "\r\n" and opener != "(":
                    raise ValueError("candidate resource contains an unsupported inline link title")
                cursor += 1
            if cursor >= len(text):
                raise ValueError("candidate resource contains an unterminated inline link title")
            cursor += 1
            while cursor < len(text) and text[cursor] in " \t\r\n":
                cursor += 1
            if cursor >= len(text) or text[cursor] != ")":
                raise ValueError("candidate resource contains an unterminated inline link")
        results.append((text[destination_start:destination_end], (index, cursor + 1)))
        index = cursor + 1
    return results


def _validate_reference_destination(target: str) -> None:
    depth = 0
    index = 0
    while index < len(target):
        character = target[index]
        if character == "\\" and index + 1 < len(target):
            if target[index + 1] in string.punctuation:
                index += 2
                continue
        if character == "(":
            depth += 1
            if depth > 32:
                raise ValueError("candidate resource reference destination nesting exceeds limit")
        elif character == ")":
            if depth == 0:
                raise ValueError("candidate resource reference destination is unbalanced")
            depth -= 1
        index += 1
    if depth:
        raise ValueError("candidate resource reference destination is unbalanced")


def _markdown_resource_links(text: str) -> list[str]:
    """Parse the constrained inline and full/collapsed reference link grammar."""
    visible = _mask_markdown_literal_regions(text)
    definitions: dict[str, str] = {}
    definition_spans: list[tuple[int, int]] = []
    for match in REFERENCE_DEFINITION.finditer(visible):
        label = _markdown_reference_label(match.group("label"))
        if label in definitions:
            raise ValueError("candidate resource contains a duplicate reference definition")
        plain_target = match.group("plain")
        target = match.group("angle") or plain_target
        if plain_target is not None:
            _validate_reference_destination(plain_target)
        definitions[label] = _markdown_target(target)
        definition_spans.append(match.span())

    inline_matches = _inline_markdown_links(visible)
    inline_spans = [span for _, span in inline_matches]
    links = [_markdown_target(target) for target, _ in inline_matches]
    reference_spans: list[tuple[int, int]] = []
    definition_or_inline_spans = sorted(definition_spans + inline_spans)
    for match in REFERENCE_RESOURCE_LINK.finditer(visible):
        if (
            _inside(match.start(), definition_or_inline_spans)
            or _escaped_at(visible, match.start())
            or match.start() > 0
            and visible[match.start() - 1] == "!"
            and not _escaped_at(visible, match.start() - 1)
        ):
            continue
        label = _markdown_reference_label(match.group("label") or match.group("text"))
        if label not in definitions:
            raise ValueError("candidate resource contains an unresolved reference-style link")
        links.append(definitions[label])
        reference_spans.append(match.span())
    occupied = sorted(definition_or_inline_spans + reference_spans)
    for match in re.finditer(r"\[([^\]\n]+)\]", visible):
        if (
            _inside(match.start(), occupied)
            or _escaped_at(visible, match.start())
            or match.start() > 0
            and visible[match.start() - 1] == "!"
            and not _escaped_at(visible, match.start() - 1)
        ):
            continue
        label = _markdown_reference_label(match.group(1))
        if label in definitions:
            links.append(definitions[label])
    return links


_TEMPLATE_RESOURCE_DESTINATIONS = (
    re.compile(r"^agents/<(?:agent|name)>\.md$"),
    re.compile(r"^routines/<(?:name|other-skill)>/SKILL\.md$"),
    re.compile(r"^routines/tribunal/references/lenses/<lens-slug>\.md$"),
    re.compile(r"^skills/ca-<name>/SKILL\.md$"),
)


def _supported_template_resource(resolved: str) -> bool:
    if not re.search(r"<[A-Za-z][A-Za-z0-9-]*>", resolved):
        return False
    if any(pattern.fullmatch(resolved) for pattern in _TEMPLATE_RESOURCE_DESTINATIONS):
        return True
    raise ValueError(
        f"candidate resource link uses an unsupported template destination: {resolved}"
    )


def candidate_resource_contract(
    path: Path,
    *,
    files: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    """Derive the exact packaged Markdown resource set and contained read graph."""
    if files is None:
        files = _candidate_package_files(path)
    return _candidate_resource_contract_from_files(files)


def _candidate_resource_contract_from_files(files: dict[str, bytes]) -> dict[str, Any]:
    """Derive the resource graph from one already bounded immutable snapshot."""
    resource_paths = sorted(
        relative
        for relative in files
        if relative.endswith(".md")
        and (
            relative.split("/", 1)[0] in {"agents", "includes", "routines", "skills"}
            or "/" not in relative
        )
    )
    if not resource_paths:
        raise ValueError("candidate package has no Markdown resources")
    resource_set = set(resource_paths)
    reads: list[dict[str, str]] = []
    for source in resource_paths:
        try:
            text = files[source].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"candidate resource is not UTF-8: {source}") from error
        for reference in _markdown_resource_links(text):
            target = reference.split("#", 1)[0]
            if SYMBOLIC_SEGMENT.search(target):
                if not target.casefold().endswith(".md"):
                    continue
                symbolic, symbolic_count = SYMBOLIC_SEGMENT.subn(SYMBOLIC_SENTINEL, target)
                if (
                    not SYMBOLIC_TARGET_CHARS.fullmatch(target)
                    or "<" in symbolic
                    or ">" in symbolic
                ):
                    raise ValueError(
                        f"candidate resource link has an invalid symbolic target: "
                        f"{source} -> {reference}"
                    )
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(source), symbolic)
                )
                if resolved.count(SYMBOLIC_SENTINEL) != symbolic_count:
                    raise ValueError(
                        f"candidate resource link normalization removes a symbolic segment: "
                        f"{source} -> {reference}"
                    )
                if target.startswith(("/", "\\")) or resolved.startswith("../"):
                    raise ValueError(
                        f"candidate resource link is escaped: {source} -> {reference}"
                    )
                resolved_template = posixpath.normpath(
                    posixpath.join(posixpath.dirname(source), target)
                )
                _supported_template_resource(resolved_template)
                continue
            if (
                not target
                or target.startswith(("#", "/", "\\"))
                or "://" in target
                or target.startswith(("mailto:", "${", "{{"))
                or not target.casefold().endswith(".md")
            ):
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
            if resolved.startswith("../"):
                raise ValueError(
                    f"candidate resource link is escaped or unresolved: {source} -> {reference}"
                )
            if _supported_template_resource(resolved):
                continue
            if resolved not in resource_set:
                raise ValueError(
                    f"candidate resource link is escaped or unresolved: {source} -> {reference}"
                )
            read = {
                "source_path": source,
                "reference": reference,
                "resolved_path": resolved,
            }
            if read not in reads:
                reads.append(read)
    reads.sort(key=lambda item: (
        item["source_path"], item["reference"], item["resolved_path"]
    ))
    manifest = {
        "files": [
            {"path": relative, "sha256": hashlib.sha256(files[relative]).hexdigest()}
            for relative in resource_paths
        ],
        "relative_reads": reads,
    }
    canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True)
    return {
        "sha256": _sha256_text(canonical),
        "selected_paths": resource_paths,
        "relative_reads": reads,
    }


def _candidate_front_matter(
    files: dict[str, bytes],
    path: str,
    required_fields: tuple[str, ...],
) -> dict[str, str]:
    """Parse the deliberately scalar front matter used by shipped Codex resources."""
    try:
        text = files[path].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"candidate resource is not UTF-8: {path}") from error
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"candidate resource has no front matter: {path}")
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"candidate resource has unterminated front matter: {path}") from error
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*):[ \t]*(.*)", line)
        if match is None:
            raise ValueError(f"candidate resource has invalid front matter: {path}")
        key = match.group(1)
        if key in fields:
            raise ValueError(
                f"candidate resource has duplicate front matter field {key}: {path}"
            )
        value = match.group(2).strip()
        begins_quoted = value[:1] in {'"', "'"}
        ends_quoted = value[-1:] in {'"', "'"}
        if begins_quoted or ends_quoted:
            if len(value) < 2 or not begins_quoted or value[-1] != value[0]:
                raise ValueError(
                    f"candidate resource has malformed quoted front matter: {path}"
                )
            if value[0] == '"':
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"candidate resource has malformed quoted front matter: {path}"
                    ) from error
                if not isinstance(decoded, str):
                    raise ValueError(
                        f"candidate resource has invalid quoted front matter: {path}"
                    )
                value = decoded
            else:
                interior = value[1:-1]
                if "'" in interior.replace("''", ""):
                    raise ValueError(
                        f"candidate resource has malformed quoted front matter: {path}"
                    )
                value = interior.replace("''", "'")
        fields[key] = value
    for field in required_fields:
        if not fields.get(field):
            raise ValueError(
                f"candidate resource front matter is missing {field}: {path}"
            )
    return fields


def _candidate_json(files: dict[str, bytes], path: str, label: str) -> object:
    try:
        text = files[path].decode("utf-8")
    except KeyError as error:
        raise ValueError(f"candidate {label} is missing") from error
    except UnicodeDecodeError as error:
        raise ValueError(f"candidate {label} is not UTF-8") from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonMember as error:
        raise ValueError(f"candidate {label} has a duplicate JSON member") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"candidate {label} is invalid JSON") from error


HOOK_EVENTS = frozenset(("SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit"))
HOOK_GROUP_FIELDS = frozenset(("matcher", "hooks"))
HOOK_ENTRY_FIELDS = frozenset((
    "type", "command", "commandWindows", "timeout", "statusMessage",
    "additionalContextLimit",
))
HOOK_COMMAND = {
    "command": re.compile(
        r'^python3 "\$\{PLUGIN_ROOT\}/hooks/([A-Za-z0-9._-]+\.py)"$'
    ),
    "commandWindows": re.compile(
        r'^python "\$\{PLUGIN_ROOT\}/hooks/([A-Za-z0-9._-]+\.py)"$'
    ),
}
EXPECTED_HOOK_MANIFEST_SHA256 = (
    "1a6f938ca91046b9e525e58de6afcfb543fa512e4a541e87b400e74575a7b062"
)


def _candidate_hook_targets(hooks: object) -> list[str]:
    if not isinstance(hooks, dict) or set(hooks) != {"hooks"}:
        raise ValueError("candidate hook manifest schema is invalid")
    events = hooks["hooks"]
    if not isinstance(events, dict) or not events or not set(events).issubset(HOOK_EVENTS):
        raise ValueError("candidate hook manifest schema has invalid events")
    targets: list[str] = []
    for groups in events.values():
        if not isinstance(groups, list) or not groups:
            raise ValueError("candidate hook manifest event must contain hook groups")
        for group in groups:
            if (
                not isinstance(group, dict)
                or "hooks" not in group
                or not set(group).issubset(HOOK_GROUP_FIELDS)
                or "matcher" in group and not isinstance(group["matcher"], str)
            ):
                raise ValueError("candidate hook manifest schema has an invalid group")
            entries = group["hooks"]
            if not isinstance(entries, list) or not entries:
                raise ValueError("candidate hook group must contain hook entries")
            for entry in entries:
                if (
                    not isinstance(entry, dict)
                    or set(entry) - HOOK_ENTRY_FIELDS
                    or entry.get("type") != "command"
                ):
                    raise ValueError("candidate hook manifest schema has an invalid entry")
                if "timeout" in entry and (
                    not isinstance(entry["timeout"], int)
                    or isinstance(entry["timeout"], bool)
                    or entry["timeout"] <= 0
                ):
                    raise ValueError("candidate hook manifest schema has an invalid timeout")
                if "statusMessage" in entry and (
                    not isinstance(entry["statusMessage"], str)
                    or not entry["statusMessage"].strip()
                ):
                    raise ValueError("candidate hook manifest schema has an invalid status")
                if "additionalContextLimit" in entry and (
                    not isinstance(entry["additionalContextLimit"], int)
                    or isinstance(entry["additionalContextLimit"], bool)
                    or entry["additionalContextLimit"] <= 0
                ):
                    raise ValueError("candidate hook manifest schema has an invalid limit")
                for command_field, grammar in HOOK_COMMAND.items():
                    command = entry.get(command_field)
                    match = grammar.fullmatch(command) if isinstance(command, str) else None
                    if match is None:
                        raise ValueError(
                            "candidate hook command grammar is invalid or does not use PLUGIN_ROOT"
                        )
                    targets.append(f"hooks/{match.group(1)}")
    canonical = json.dumps(hooks, separators=(",", ":"), sort_keys=True)
    if _sha256_text(canonical) != EXPECTED_HOOK_MANIFEST_SHA256:
        raise ValueError("candidate hook inventory does not match the approved contract")
    return targets


def candidate_static_contract(path: Path) -> dict[str, Any]:
    """Validate the complete inert ca-codex package shape used for release."""
    files = _candidate_package_files(path)
    manifest_path = ".codex-plugin/plugin.json"
    manifest = _candidate_json(files, manifest_path, "plugin manifest")
    if not isinstance(manifest, dict):
        raise ValueError("candidate plugin manifest must be an object")
    if manifest.get("name") != "ca-codex":
        raise ValueError("candidate manifest name must be ca-codex")
    version = manifest.get("version")
    if not isinstance(version, str) or PACKAGE_VERSION_ID.fullmatch(version) is None:
        raise ValueError("candidate plugin manifest version is invalid")

    for relative in sorted(files):
        if relative.startswith("skills/ca-") and relative.endswith("/SKILL.md"):
            fields = _candidate_front_matter(files, relative, ("name", "description"))
            expected_name = posixpath.basename(posixpath.dirname(relative))
            if fields["name"] != expected_name:
                raise ValueError(
                    f"candidate skill front matter name does not match its path: {relative}"
                )
        elif relative.startswith("routines/") and relative.endswith("/SKILL.md"):
            fields = _candidate_front_matter(files, relative, ("name", "description"))
            expected_name = posixpath.basename(posixpath.dirname(relative))
            if fields["name"] != expected_name:
                raise ValueError(
                    f"candidate routine front matter name does not match its path: {relative}"
                )
        elif (
            relative.startswith("agents/")
            and relative.endswith(".md")
            and posixpath.basename(relative) != "INDEX.md"
        ):
            fields = _candidate_front_matter(
                files, relative, ("name", "description", "classification")
            )
            expected_name = posixpath.basename(relative)[:-3]
            if fields["name"] != expected_name:
                raise ValueError(
                    f"candidate agent front matter name does not match its path: {relative}"
                )

    hooks_path = "hooks/hooks.json"
    hooks = _candidate_json(files, hooks_path, "hook manifest")
    for relative_target in _candidate_hook_targets(hooks):
        if relative_target not in files:
            raise ValueError(f"candidate hook target is missing: {relative_target}")

    resources = candidate_resource_contract(path, files=files)
    package_manifest = {
        "files": [
            {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}
            for relative, content in sorted(files.items())
        ]
    }
    package_sha256 = _sha256_text(
        json.dumps(package_manifest, separators=(",", ":"), sort_keys=True)
    )
    return {
        "sha256": package_sha256,
        "package_sha256": package_sha256,
        "plugin_version": version,
        "selected_paths": resources["selected_paths"],
        "relative_reads": resources["relative_reads"],
        "resource_sha256": resources["sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-only", action="store_true", help="validate offline fixture only")
    parser.add_argument("--live", action="store_true", help="run an isolated backend characterization")
    parser.add_argument("--surface", choices=("cli", "app-server"))
    parser.add_argument("--codex-version", help="exact Codex version, or latest with --advisory")
    parser.add_argument("--codex-binary", help="exact Codex executable to run")
    parser.add_argument(
        "--authenticated-codex-home",
        help="existing controller-owned temporary CODEX_HOME with fresh ChatGPT login",
    )
    parser.add_argument("--candidate-package", help="exact ca-codex directory or ZIP archive")
    parser.add_argument(
        "--candidate-contract-only", action="store_true",
        help="validate the complete inert ca-codex package contract",
    )
    parser.add_argument("--advisory", action="store_true", help="record drift without satisfying required cells")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def _resolve_binary(value: str | None, parser: argparse.ArgumentParser) -> Path:
    if value:
        direct = Path(value)
        resolved = direct.resolve() if direct.is_file() else None
        if resolved is None:
            located = shutil.which(value)
            resolved = Path(located).resolve() if located else None
    else:
        located = shutil.which("codex")
        resolved = Path(located).resolve() if located else None
    if resolved is None or not resolved.is_file():
        parser.error("an exact --codex-binary is required when codex is not on PATH")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    modes = sum(bool(value) for value in (
        args.fixtures_only, args.live, args.candidate_contract_only,
    ))
    if modes != 1:
        parser.error(
            "select exactly one of --fixtures-only, --live, or --candidate-contract-only"
        )

    if args.candidate_contract_only:
        if any((
            args.surface, args.codex_version, args.codex_binary,
            args.advisory, args.authenticated_codex_home,
        )):
            parser.error("backend switches cannot be combined with --candidate-contract-only")
        if not args.candidate_package:
            parser.error("--candidate-contract-only requires --candidate-package")
        candidate_path = Path(args.candidate_package).absolute()
        if not candidate_path.exists():
            parser.error("--candidate-package must name an existing archive or directory")
        try:
            result = candidate_static_contract(candidate_path)
        except ValueError as error:
            result = {"verdict": "FAIL", "errors": [str(error)]}
        else:
            result = {**result, "verdict": "PASS", "errors": []}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for error in result["errors"]:
                print(f"ERROR: {error}")
            if not result["errors"]:
                print(f"candidate static contract valid: {result['sha256']}")
        return 0 if result["verdict"] == "PASS" else 1

    if args.fixtures_only:
        if any((
            args.surface, args.codex_version, args.codex_binary,
            args.candidate_package, args.advisory, args.authenticated_codex_home,
        )):
            parser.error("live/candidate switches cannot be combined with --fixtures-only")
        result = validate_fixture(FIXTURE_ROOT)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for error in result["errors"]:
                print(f"ERROR: {error}")
            if not result["errors"]:
                print(
                    f"fixture valid: {result['fixture_sha256']} "
                    f"(durable evidence {result['durable_evidence']['state']})"
                )
        return 1 if result["errors"] else 0

    if args.surface is None or args.codex_version is None:
        parser.error("--live requires --surface and --codex-version")
    if args.candidate_package or args.candidate_contract_only:
        parser.error("candidate switches cannot be combined with --live")

    effective_version = args.codex_version
    if args.advisory:
        if args.codex_version == "latest":
            effective_version = ADVISORY_RELEASE["version"]
        if effective_version != ADVISORY_RELEASE["version"]:
            parser.error("the characterized advisory cell is Codex 0.149.0 (or --codex-version latest)")
        expected = dict(ADVISORY_RELEASE)
    else:
        pin = PINNED_RELEASES.get(effective_version)
        if pin is None:
            parser.error("supported live cells are pinned to Codex 0.143.0 and 0.145.0")
        expected = dict(pin)
    expected.update({"surface": args.surface, "version": effective_version})
    executable = _resolve_binary(args.codex_binary, parser)
    authenticated_codex_home = None
    if args.authenticated_codex_home:
        try:
            authenticated_codex_home = validated_authenticated_codex_home(
                args.authenticated_codex_home,
                REPO_ROOT,
                surface=args.surface,
                version=effective_version,
                advisory=args.advisory,
            )
        except ValueError as error:
            parser.error(str(error))
    if args.surface == "cli":
        result = run_cli_live(
            executable=executable,
            version=effective_version,
            expected=expected,
            fixture_root=FIXTURE_ROOT,
            repository=REPO_ROOT,
            advisory=args.advisory,
            authenticated_codex_home=authenticated_codex_home,
        )
    else:
        result = run_app_server_live(
            executable=executable,
            version=effective_version,
            expected=expected,
            fixture_root=FIXTURE_ROOT,
            repository=REPO_ROOT,
            advisory=args.advisory,
            authenticated_codex_home=authenticated_codex_home,
        )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for error in result["errors"]:
            print(f"ERROR: {error}")
        print(f"{result['surface']} {result['version']} {result['verdict']}")
    return 0 if result["verdict"] == "PASS" or args.advisory else 1


if __name__ == "__main__":
    raise SystemExit(main())
