#!/usr/bin/env python3
"""Check ADR-0026 destructive-operation registry/resident-copy parity.

The routing-table block is authoritative. The arbiter keeps a resident copy
because tier classification happens before the routing table is loaded. This
checker compares the bullet text item-for-item without semantic normalization.

Run: python .github/scripts/check_destructive_registry.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


HEADING = "Destructive operations (tier-2 regardless of cue)"
BLOCK_HEADING_RE = re.compile(rf"^#{{2,6}} {re.escape(HEADING)}$")
REPO = Path(__file__).resolve().parents[2]


def extract_operations(text: str) -> tuple[str, ...]:
    """Return the one declared block's bullets, preserving exact item text."""
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if BLOCK_HEADING_RE.fullmatch(line)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one '{HEADING}' block, found {len(matches)}")

    operations: list[str] = []
    for line in lines[matches[0] + 1 :]:
        if not line:
            continue
        if line.startswith("- "):
            operations.append(line[2:])
            continue
        if operations:
            break
        raise ValueError(f"'{HEADING}' must be followed by a bullet list")
    if not operations:
        raise ValueError(f"'{HEADING}' has no operations")
    return tuple(operations)


def render_block(operations: tuple[str, ...], *, heading_level: int) -> str:
    """Render a registry fixture using the repository's byte-comparable form."""
    if heading_level < 2 or heading_level > 6:
        raise ValueError("heading_level must be between 2 and 6")
    bullets = "\n".join(f"- {operation}" for operation in operations)
    return f"{'#' * heading_level} {HEADING}\n\n{bullets}\n"


def compare_surfaces(registry_text: str, resident_text: str) -> list[str]:
    """Return diagnostics for missing, malformed, or non-identical blocks."""
    try:
        registry = extract_operations(registry_text)
    except ValueError as exc:
        return [f"authoritative registry invalid: {exc}"]
    try:
        resident = extract_operations(resident_text)
    except ValueError as exc:
        return [f"resident copy invalid: {exc}"]
    if registry != resident:
        return [
            "destructive operations item-for-item mismatch: "
            f"registry={registry!r}; resident={resident!r}"
        ]
    return []


def main() -> int:
    pairs = (
        ("core/surface/includes/routing-table.md", "core/surface/arbiter.md"),
        ("plugins/ca/includes/routing-table.md", "plugins/ca/arbiter.md"),
        ("plugins/ca-codex/includes/routing-table.md", "plugins/ca-codex/arbiter.md"),
        ("plugins/ca-pi/includes/routing-table.md", "plugins/ca-pi/arbiter.md"),
    )
    errors: list[str] = []
    for registry_rel, resident_rel in pairs:
        registry_text = (REPO / registry_rel).read_text(encoding="utf-8")
        resident_text = (REPO / resident_rel).read_text(encoding="utf-8")
        errors.extend(
            f"{registry_rel} -> {resident_rel}: {error}"
            for error in compare_surfaces(registry_text, resident_text)
        )
    if errors:
        print("ADR destructive-operation parity: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("ADR destructive-operation parity: PASS (4 surface pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
