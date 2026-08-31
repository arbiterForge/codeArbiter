#!/usr/bin/env python3
"""Validate a ca-codex package as inert, bounded static data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import sys
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
RESOURCE_CHECKER_PATH = SCRIPT_ROOT / "check_codex_skill_resources.py"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
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


class _DuplicateJsonMember(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMember
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON value is not permitted: {value}")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_resource_checker():
    if not RESOURCE_CHECKER_PATH.is_file():
        raise ValueError("trusted candidate resource checker is missing")
    spec = importlib.util.spec_from_file_location(
        "codearbiter_trusted_candidate_resources", RESOURCE_CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise ValueError("trusted candidate resource checker cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _candidate_front_matter(
    files: dict[str, bytes], path: str, required_fields: tuple[str, ...]
) -> dict[str, str]:
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
    resource_checker = _load_resource_checker()
    files = resource_checker._candidate_package_files(path)
    manifest = _candidate_json(files, ".codex-plugin/plugin.json", "plugin manifest")
    if not isinstance(manifest, dict):
        raise ValueError("candidate plugin manifest must be an object")
    if manifest.get("name") != "ca-codex":
        raise ValueError("candidate manifest name must be ca-codex")
    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
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

    hooks = _candidate_json(files, "hooks/hooks.json", "hook manifest")
    for target in _candidate_hook_targets(hooks):
        if target not in files:
            raise ValueError(f"candidate hook target is missing: {target}")

    resources = resource_checker._candidate_resource_contract_from_files(files)
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
        "verdict": "PASS",
        "package_sha256": package_sha256,
        "plugin_version": version,
        "resource_sha256": resources["sha256"],
        "resource_count": len(resources["selected_paths"]),
        "relative_read_count": len(resources["relative_reads"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-package", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = candidate_static_contract(args.candidate_package)
    except (OSError, UnicodeError, ValueError, KeyError) as error:
        result = {"verdict": "FAIL", "errors": [str(error)]}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"candidate static contract valid: {result['package_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
