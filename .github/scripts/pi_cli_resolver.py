#!/usr/bin/env python3
"""Resolve an installed Pi launcher to its package CLI without config reads."""
from __future__ import annotations

import json
from pathlib import Path


def _declared_cli(package_root: Path) -> Path | None:
    """The manifest's `pi` bin; Pi 1.0.0 moved it from dist/cli.js to dist/bundle/cli.js."""
    try:
        manifest = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bin_field = manifest.get("bin") if isinstance(manifest, dict) else None
    target = bin_field if isinstance(bin_field, str) else (
        bin_field.get("pi") if isinstance(bin_field, dict) else None
    )
    if manifest.get("name") != "@earendil-works/pi-coding-agent" or not isinstance(target, str):
        return None
    root = package_root.resolve()
    candidate = (package_root / target).resolve()
    return candidate if candidate.is_relative_to(root) and candidate.is_file() else None


def resolve_pi_cli_path(executable: str | Path) -> Path:
    """Support npm global and isolated local-prefix launcher layouts."""
    launcher = Path(executable)
    roots = [launcher.parent / "node_modules" / "@earendil-works" / "pi-coding-agent"]
    if launcher.parent.name == ".bin" and launcher.parent.parent.name == "node_modules":
        roots.append(launcher.parent.parent / "@earendil-works" / "pi-coding-agent")
    for root in roots:
        candidate = _declared_cli(root)
        if candidate is not None:
            return candidate
    resolved = launcher.resolve()
    if resolved.suffix == ".js" and resolved.is_file():
        return resolved
    raise AssertionError(f"cannot resolve Pi CLI package adjacent to {executable}")
