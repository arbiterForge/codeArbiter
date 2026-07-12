#!/usr/bin/env python3
"""Validate the ca-codex package against the Codex CLI 0.144.1 baseline."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


BASELINE = "0.144.1"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
REQUIRED_INTERFACE_STRINGS = (
    "displayName", "shortDescription", "longDescription",
    "developerName", "category",
)
ALLOWED_INSTALLATION = {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}
ALLOWED_AUTHENTICATION = {"ON_INSTALL", "ON_USE"}


def _load_json(path: Path, label: str, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} must be valid JSON: {exc}")
        return None


def _valid_frontmatter(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line or line.startswith((" ", "\t", "#")) or ":" not in line:
            return False
        key, value = line.split(":", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key) or not value.strip():
            return False
        value = value.strip()
        if value.startswith('"'):
            if not value.endswith('"') or len(value) < 2:
                return False
            try:
                json.loads(value)
            except json.JSONDecodeError:
                return False
        elif value.startswith(("[", "{")) or ": " in value or " | " in value:
            return False
        fields[key] = value
    return bool(fields.get("name") and fields.get("description"))


def _validate_manifest(plugin_root: Path, errors: list[str]) -> None:
    path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest = _load_json(path, "plugin.json", errors)
    if not isinstance(manifest, dict):
        return
    if "displayName" in manifest:
        errors.append("plugin.json field `displayName` is not accepted")
    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"plugin.json field `{field}` must be a non-empty string")
    if isinstance(manifest.get("version"), str) and not SEMVER.fullmatch(manifest["version"]):
        errors.append("plugin.json field `version` must use strict SemVer")
    author = manifest.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        errors.append("plugin.json field `author.name` must be a non-empty string")
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        interface = {}
    for field in REQUIRED_INTERFACE_STRINGS:
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            errors.append(f"plugin.json field `interface.{field}` must be a non-empty string")
    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(v, str) for v in capabilities):
        errors.append("plugin.json field `interface.capabilities` must be an array of strings")
    prompts = interface.get("defaultPrompt")
    if not isinstance(prompts, list) or not all(isinstance(v, str) for v in prompts):
        errors.append("plugin.json field `interface.defaultPrompt` must be an array of strings")


def _validate_skills(plugin_root: Path, errors: list[str]) -> None:
    skills = plugin_root / "skills"
    if not skills.is_dir():
        return
    for path in sorted(skills.glob("*/SKILL.md")):
        try:
            valid = _valid_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            valid = False
        if not valid:
            errors.append(f"skill `{path.parent.name}` frontmatter must be valid YAML")


def _validate_marketplace(marketplace_path: Path, plugin_name: str,
                          errors: list[str]) -> None:
    marketplace = _load_json(marketplace_path, "marketplace.json", errors)
    if not isinstance(marketplace, dict):
        return
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        errors.append("marketplace.json field `plugins` must be an array")
        return
    entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == plugin_name), None)
    if entry is None:
        errors.append(f"marketplace plugin `{plugin_name}` is required")
        return
    source = entry.get("source")
    if not (isinstance(source, dict) and source.get("source") == "local"
            and isinstance(source.get("path"), str) and source["path"].startswith("./plugins/")):
        errors.append(f"marketplace plugin `{plugin_name}` source must be a local source object")
    policy = entry.get("policy") if isinstance(entry.get("policy"), dict) else {}
    if policy.get("installation") not in ALLOWED_INSTALLATION:
        errors.append(f"marketplace plugin `{plugin_name}` policy.installation is required")
    if policy.get("authentication") not in ALLOWED_AUTHENTICATION:
        errors.append(f"marketplace plugin `{plugin_name}` policy.authentication is required")
    if not isinstance(entry.get("category"), str) or not entry["category"].strip():
        errors.append(f"marketplace plugin `{plugin_name}` category is required")


def validate_plugin(plugin_root: Path, marketplace_path: Path) -> list[str]:
    errors: list[str] = []
    _validate_manifest(plugin_root, errors)
    _validate_skills(plugin_root, errors)
    _validate_marketplace(marketplace_path, plugin_root.name, errors)
    return errors


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[2]
    plugin = Path(argv[0]) if argv else repo / "plugins" / "ca-codex"
    marketplace = Path(argv[1]) if len(argv) > 1 else repo / ".agents" / "plugins" / "marketplace.json"
    print(f"Codex validation baseline: {BASELINE}")
    errors = validate_plugin(plugin, marketplace)
    if errors:
        print("Codex plugin validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Codex plugin validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
