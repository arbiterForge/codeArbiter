#!/usr/bin/env python3
"""Validate the Codex package's shipped Markdown agent-route closure.

Codex charters are packaged Markdown resources, not native registrations.  A
route therefore remains executable only when every literal resource link and
the one supported generic ``agents/<name>.md`` form resolve against the
package's exact ``agents/INDEX.md`` inventory.  Keep this check independent of
the source tree: callers may pass either a checkout plugin root or an
installed/cache copy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_MD_LINK = re.compile(r"\]\(([^)]+)\)")
_INDEX_ROW = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|")
_ROUTE_CONTRACT = re.compile(
    r"(?m)^<!-- codearbiter-codex-agent-route-contract: "
    r"literal_route_lines=(?P<literal_route_lines>\d+) "
    r"literal_route_occurrences=(?P<literal_route_occurrences>\d+) "
    r"generic_route_lines=(?P<generic_route_lines>\d+) "
    r"generic_route_occurrences=(?P<generic_route_occurrences>\d+) -->$"
)
_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SUPPORTED_GENERICS = frozenset({"<agent>", "<name>"})
_ROUTE_STAT_KEYS = (
    "literal_route_lines",
    "literal_route_occurrences",
    "generic_route_lines",
    "generic_route_occurrences",
)


@dataclass(frozen=True)
class AgentRoute:
    source: Path
    line: int
    target: str
    name: str
    generic: bool


def _markdown_files(root: Path):
    for path in root.rglob("*.md"):
        if path.is_file() and not path.is_symlink() and path.name != "INDEX.md":
            yield path


def _resolved_agents_dir(root: Path) -> tuple[Path | None, list[str]]:
    """Resolve the charter authority without following it outside the package."""
    agents_dir = root / "agents"
    try:
        resolved = agents_dir.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        return None, [f"agents/: cannot resolve strictly: {error}"]
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, ["agents/: directory symlink escapes package"]
    if not resolved.is_dir():
        return None, ["agents/: must resolve strictly as a directory"]
    return resolved, []


def _regular_resource_errors(path: Path, authority: Path, label: str) -> list[str]:
    """Require one non-symlink regular file inside the resolved authority."""
    if path.is_symlink():
        return [f"{label}: symlinked resource is not permitted"]
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        return [f"{label}: cannot resolve strictly: {error}"]
    try:
        resolved.relative_to(authority)
    except ValueError:
        return [f"{label}: resource escapes the resolved agents directory"]
    if not resolved.is_file():
        return [f"{label}: must resolve strictly as a regular file"]
    return []


def _index_inventory(
    agents_dir: Path, resolved_agents_dir: Path
) -> tuple[set[str], set[str], list[str]]:
    errors: list[str] = []
    index = agents_dir / "INDEX.md"
    disk = {path.stem for path in agents_dir.glob("*.md") if path.name != "INDEX.md"}
    index_errors = _regular_resource_errors(
        index, resolved_agents_dir, "agents/INDEX.md"
    )
    if index_errors:
        return disk, set(), index_errors

    rows: list[tuple[str, str]] = []
    for line in index.read_text(encoding="utf-8").splitlines():
        match = _INDEX_ROW.match(line)
        if match:
            rows.append((match.group(1), match.group(2)))

    seen: set[str] = set()
    indexed: set[str] = set()
    for name, target in rows:
        if name in seen:
            errors.append(f"agents/INDEX.md: duplicate INDEX row for {name!r}")
        seen.add(name)
        indexed.add(name)
        expected = f"{name}.md"
        if target != expected:
            errors.append(
                f"agents/INDEX.md: INDEX row {name!r} links to {target!r}, "
                f"expected {expected!r}"
            )
        errors.extend(
            _regular_resource_errors(
                agents_dir / target,
                resolved_agents_dir,
                f"agents/INDEX.md: target {target!r}",
            )
        )
        if name not in disk:
            errors.append(f"agents/INDEX.md: INDEX row {name!r} has no resource on disk")

    for name in sorted(disk - indexed):
        errors.append(f"agents/INDEX.md: agent resource {name!r} has no INDEX row")
    return disk, indexed, errors


def _route_contract(
    agents_dir: Path, resolved_agents_dir: Path
) -> tuple[dict[str, int], list[str]]:
    """Read the generator-owned expected route counts from the shipped index."""
    index = agents_dir / "INDEX.md"
    index_errors = _regular_resource_errors(
        index, resolved_agents_dir, "agents/INDEX.md"
    )
    if index_errors:
        return {}, index_errors
    matches = list(_ROUTE_CONTRACT.finditer(index.read_text(encoding="utf-8")))
    if len(matches) != 1:
        return {}, [
            "agents/INDEX.md: requires exactly one generated Codex agent-route contract"
        ]
    return {key: int(matches[0].group(key)) for key in _ROUTE_STAT_KEYS}, []


def expected_route_stats(plugin_root: Path) -> tuple[dict[str, int], list[str]]:
    """Read a source or shipped Codex package's generator-owned receipt."""
    root = plugin_root.resolve()
    resolved_agents_dir, errors = _resolved_agents_dir(root)
    if errors:
        return {}, errors
    return _route_contract(root / "agents", resolved_agents_dir)


def _route_from_link(source: Path, root: Path, raw: str, line: int) -> tuple[AgentRoute | None, str | None]:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    target = target.split("#", 1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None, None

    raw_parts = target.replace("\\", "/").split("/")
    names_agent_path = "agents" in raw_parts
    candidate = (source.parent / target).resolve(strict=False)
    try:
        relative = candidate.relative_to(root.resolve())
    except ValueError:
        if names_agent_path:
            return None, f"{source.relative_to(root)}:{line}: agent route escapes package: {raw!r}"
        return None, None

    if not names_agent_path and (not relative.parts or relative.parts[0] != "agents"):
        return None, None
    if len(relative.parts) != 2 or relative.parts[0] != "agents" or relative.suffix != ".md":
        return None, f"{source.relative_to(root)}:{line}: partial agent resource route: {raw!r}"

    stem = relative.stem
    if stem.startswith("<") or stem.endswith(">"):
        if stem not in _SUPPORTED_GENERICS:
            return None, (
                f"{source.relative_to(root)}:{line}: unsupported generic agent route "
                f"{stem!r}; supported forms are {sorted(_SUPPORTED_GENERICS)!r}"
            )
        return AgentRoute(source, line, raw, stem, True), None
    if not _NAME.fullmatch(stem):
        return None, f"{source.relative_to(root)}:{line}: invalid agent resource name {stem!r}"
    return AgentRoute(source, line, raw, stem, False), None


def discover_agent_routes(plugin_root: Path) -> tuple[list[AgentRoute], list[str], dict[str, int]]:
    """Return every Markdown literal/generic agent route and measured counts."""
    root = plugin_root.resolve()
    routes: list[AgentRoute] = []
    errors: list[str] = []
    literal_lines: set[tuple[Path, int]] = set()
    generic_lines: set[tuple[Path, int]] = set()
    for source in _markdown_files(root):
        text = source.read_text(encoding="utf-8")
        for match in _MD_LINK.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            route, error = _route_from_link(source, root, match.group(1), line)
            if error:
                errors.append(error)
            if route is None:
                continue
            routes.append(route)
            (generic_lines if route.generic else literal_lines).add((route.source, route.line))
    stats = {
        "literal_route_lines": len(literal_lines),
        "literal_route_occurrences": sum(not route.generic for route in routes),
        "generic_route_lines": len(generic_lines),
        "generic_route_occurrences": sum(route.generic for route in routes),
    }
    return routes, errors, stats


def validate_agent_routes(
    plugin_root: Path, expected_stats: dict[str, int] | None = None
) -> tuple[list[str], dict[str, int]]:
    """Fail closed on resource/index/route drift in a shipped Codex package."""
    root = plugin_root.resolve()
    agents_dir = root / "agents"
    resolved_agents_dir, authority_errors = _resolved_agents_dir(root)
    if authority_errors:
        return authority_errors, {
            "literal_route_lines": 0,
            "literal_route_occurrences": 0,
            "generic_route_lines": 0,
            "generic_route_occurrences": 0,
            "agents_indexed": 0,
        }

    inventory, indexed, errors = _index_inventory(agents_dir, resolved_agents_dir)
    if expected_stats is None:
        expected_stats, contract_errors = _route_contract(
            agents_dir, resolved_agents_dir
        )
        errors.extend(contract_errors)
    routes, route_errors, stats = discover_agent_routes(root)
    errors.extend(route_errors)
    for key, expected in expected_stats.items():
        actual = stats[key]
        if actual != expected:
            errors.append(
                f"agents/INDEX.md: {key} contract requires {expected}, "
                f"but shipped Markdown has {actual}"
            )
    for route in routes:
        if route.generic:
            if not inventory:
                errors.append(
                    f"{route.source.relative_to(root)}:{route.line}: generic agent route "
                    "has no indexed charter inventory"
                )
            continue
        if route.name not in inventory:
            errors.append(
                f"{route.source.relative_to(root)}:{route.line}: agent route {route.name!r} "
                "has no exact shipped resource"
            )
        if route.name not in indexed:
            errors.append(
                f"{route.source.relative_to(root)}:{route.line}: agent route {route.name!r} "
                "has no exact INDEX membership"
            )
    stats["agents_indexed"] = len(indexed)
    return sorted(set(errors)), stats
