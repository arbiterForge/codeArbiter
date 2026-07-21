#!/usr/bin/env python3
"""Resolve an installed Pi launcher to its package CLI without config reads."""
from __future__ import annotations

from pathlib import Path


def resolve_pi_cli_path(executable: str | Path) -> Path:
    """Support npm global and isolated local-prefix launcher layouts."""
    launcher = Path(executable)
    candidates = [
        launcher.parent / "node_modules" / "@earendil-works"
        / "pi-coding-agent" / "dist" / "cli.js",
    ]
    if launcher.parent.name == ".bin" and launcher.parent.parent.name == "node_modules":
        candidates.append(
            launcher.parent.parent / "@earendil-works"
            / "pi-coding-agent" / "dist" / "cli.js"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    resolved = launcher.resolve()
    if resolved.suffix == ".js" and resolved.is_file():
        return resolved
    raise AssertionError(f"cannot resolve Pi CLI package adjacent to {executable}")
