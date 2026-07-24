#!/usr/bin/env python3
"""Fail-safe, shadow-mode CI impact selection.

This module is deliberately dependency-free so it can run in the existing CI
``changes`` job.  Its predictions are advisory in the first release: unknown
or malformed input deliberately expands to the broad validation lane.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


LANES = frozenset({"CHECK", "WATCH", "GATE", "SHIP"})
SCOPES = frozenset({"REPO", "CORE", "CA", "CDX", "PI", "SBX"})


class ImpactMapError(ValueError):
    """Raised when the declarative impact map cannot be trusted."""


@dataclass(frozen=True)
class Check:
    id: str
    lane: str
    scope: str
    contract: str
    dimensions: tuple[str, ...] = ()
    reproduce: str | None = None


@dataclass(frozen=True)
class Edge:
    kind: str
    glob: str | None = None
    source_prefix: str | None = None
    check_ids: tuple[str, ...] = ()
    host_checks: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ImpactMap:
    checks: tuple[Check, ...]
    edges: tuple[Edge, ...]

    @property
    def checks_by_id(self) -> dict[str, Check]:
        return {check.id: check for check in self.checks}

    @property
    def broad_lane(self) -> Check:
        return self.checks_by_id["broad-lane"]


@dataclass(frozen=True)
class ImpactResult:
    selected: tuple[Check, ...]
    modeled_checks: tuple[Check, ...]
    fallback: bool
    reason: str
    matched_paths: tuple[str, ...]

    @classmethod
    def broad_lane(cls, map_: ImpactMap, reason: str) -> "ImpactResult":
        return cls(
            selected=(map_.broad_lane,),
            modeled_checks=map_.checks,
            fallback=True,
            reason=reason,
            matched_paths=(),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "fallback": self.fallback,
            "reason": self.reason,
            "matched_paths": list(self.matched_paths),
            "selected": [
                {
                    "id": check.id,
                    "name": render_check_name(check),
                    "lane": check.lane,
                    "scope": check.scope,
                    "contract": check.contract,
                    "dimensions": list(check.dimensions),
                    "advisory": check.lane == "WATCH",
                    "reason": self._check_reason(),
                    "reproduce": check.reproduce,
                }
                for check in self.selected
            ],
            "predicted_not_selected": self._predicted_not_selected(),
        }

    def receipt_markdown(self) -> str:
        mode = "fallback to broad validation" if self.fallback else "mapped selection"
        lines = [
            "## CI impact receipt",
            "",
            f"**Mode:** {mode}",
            f"**Reason:** {self.reason}",
            "",
            "### Predicted contracts",
            "",
        ]
        for check in self.selected:
            status = "advisory" if check.lane == "WATCH" else "required"
            lines.append(f"- `{render_check_name(check)}` — {status}")
            lines.append(f"  - Reason: {self._check_reason()}")
            if check.reproduce:
                lines.append(f"  - Reproduce: `{check.reproduce}`")
        predicted_not_selected = self._predicted_not_selected()
        lines.extend(["", "### Predicted not selected", ""])
        if predicted_not_selected:
            lines.extend(f"- `{check_id}`" for check_id in predicted_not_selected)
        else:
            lines.append("- None; fallback mode does not claim irrelevance.")
        lines.extend(
            [
                "",
                "### Shadow-mode note",
                "",
                "The planner does not skip any existing CI job in this release.",
            ]
        )
        return "\n".join(lines) + "\n"

    def _check_reason(self) -> str:
        if self.fallback:
            return self.reason
        if len(self.matched_paths) == 1:
            return f"matched path: {self.matched_paths[0]}"
        return "matched paths: " + ", ".join(self.matched_paths)

    def _predicted_not_selected(self) -> list[str]:
        if self.fallback:
            return []
        selected_ids = {check.id for check in self.selected}
        # This is a map-level prediction only.  Shadow mode never changes jobs.
        return [
            check.id
            for check in self.modeled_checks
            if check.id != "broad-lane" and check.id not in selected_ids
        ]


def render_check_name(check: Check) -> str:
    """Render the fixed-width, typed check-name grammar used by CI."""
    lane = check.lane.ljust(5)
    scope = check.scope.ljust(4)
    suffix = "" if not check.dimensions else "  <" + " · ".join(check.dimensions) + ">"
    return f"[{lane}] | [{scope}] | {check.contract}{suffix}"


def load_map(path: Path) -> ImpactMap:
    """Load and validate a version-one impact map before any evaluation."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ImpactMapError(f"impact map not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ImpactMapError(f"invalid JSON in impact map: {error.msg}") from error

    if not isinstance(raw, dict):
        raise ImpactMapError("impact map root must be an object")
    if raw.get("schema") != 1:
        raise ImpactMapError("impact map field 'schema' must equal 1")
    checks_raw = _list_field(raw, "checks")
    edges_raw = _list_field(raw, "edges")

    checks = tuple(_load_check(entry, index) for index, entry in enumerate(checks_raw))
    check_ids = [check.id for check in checks]
    duplicate_ids = _duplicates(check_ids)
    if duplicate_ids:
        raise ImpactMapError(f"duplicate check id: {duplicate_ids[0]}")
    if "broad-lane" not in check_ids:
        raise ImpactMapError("impact map must define the broad-lane check")

    known_ids = set(check_ids)
    edges = tuple(_load_edge(entry, index, known_ids) for index, entry in enumerate(edges_raw))
    if not edges:
        raise ImpactMapError("impact map field 'edges' must not be empty")
    duplicate_edges = _duplicates(_edge_identity(edge) for edge in edges)
    if duplicate_edges:
        raise ImpactMapError(f"duplicate impact edge: {duplicate_edges[0]}")
    return ImpactMap(checks=checks, edges=edges)


def evaluate(map_: ImpactMap, changed_paths: list[str], hosts: tuple[Any, ...]) -> ImpactResult:
    """Evaluate paths conservatively using the supplied host descriptors."""
    if not changed_paths:
        return ImpactResult.broad_lane(map_, "no changed paths reported")

    selected_ids: list[str] = []
    for raw_path in changed_paths:
        path = _normalise_changed_path(raw_path)
        if path is None:
            return ImpactResult.broad_lane(map_, f"invalid changed path: {raw_path}")
        matched, diagnostic = _match_path(map_, path, hosts)
        if matched is None:
            reason = diagnostic or f"unmapped path: {path}"
            return ImpactResult.broad_lane(map_, reason)
        if not matched:
            return ImpactResult.broad_lane(map_, f"unmapped path: {path}")
        selected_ids.extend(check.id for check in matched)

    checks = map_.checks_by_id
    selected = tuple(checks[check_id] for check_id in _unique(selected_ids))
    return ImpactResult(
        selected=selected,
        modeled_checks=map_.checks,
        fallback=False,
        reason="all changed paths mapped",
        matched_paths=tuple(sorted(_unique(changed_paths))),
    )


def _load_check(raw: Any, index: int) -> Check:
    if not isinstance(raw, dict):
        raise ImpactMapError(f"checks[{index}] must be an object")
    check_id = _text_field(raw, "id", f"checks[{index}]")
    lane = _text_field(raw, "lane", f"checks[{index}]")
    scope = _text_field(raw, "scope", f"checks[{index}]")
    contract = _text_field(raw, "contract", f"checks[{index}]")
    if lane not in LANES:
        raise ImpactMapError(f"checks[{index}].lane must be one of {sorted(LANES)}")
    if scope not in SCOPES:
        raise ImpactMapError(f"checks[{index}].scope must be one of {sorted(SCOPES)}")
    if any(char in contract for char in "\r\n"):
        raise ImpactMapError(f"checks[{index}].contract must be one line")
    reproduce = raw.get("reproduce")
    if reproduce is not None:
        if not isinstance(reproduce, str) or not reproduce.strip() or any(
            char in reproduce for char in "\r\n"
        ):
            raise ImpactMapError(
                f"checks[{index}].reproduce must be a non-empty one-line string"
            )
    return Check(
        id=check_id,
        lane=lane,
        scope=scope,
        contract=contract,
        reproduce=reproduce,
    )


def _load_edge(raw: Any, index: int, known_ids: set[str]) -> Edge:
    if not isinstance(raw, dict):
        raise ImpactMapError(f"edges[{index}] must be an object")
    kind = raw.get("kind", "glob")
    if kind == "descriptor_surface":
        return _load_descriptor_surface_edge(raw, index, known_ids)
    if kind != "glob":
        raise ImpactMapError(f"edges[{index}].kind must be 'glob' or 'descriptor_surface'")
    glob = _text_field(raw, "glob", f"edges[{index}]")
    if not _valid_relative_glob(glob):
        raise ImpactMapError(f"edges[{index}].glob must be a relative POSIX glob")
    check_ids_raw = _list_field(raw, "checks", f"edges[{index}]")
    if not check_ids_raw:
        raise ImpactMapError(f"edges[{index}].checks must not be empty")
    check_ids: list[str] = []
    for check_id in check_ids_raw:
        if not isinstance(check_id, str) or not check_id:
            raise ImpactMapError(f"edges[{index}].checks must contain non-empty strings")
        if check_id not in known_ids:
            raise ImpactMapError(f"edges[{index}] references unknown check: {check_id}")
        check_ids.append(check_id)
    duplicates = _duplicates(check_ids)
    if duplicates:
        raise ImpactMapError(f"edges[{index}] repeats check: {duplicates[0]}")
    return Edge(kind="glob", glob=glob, check_ids=tuple(check_ids))


def _load_descriptor_surface_edge(
    raw: dict[str, Any], index: int, known_ids: set[str]
) -> Edge:
    prefix = _text_field(raw, "source_prefix", f"edges[{index}]")
    if not prefix.endswith("/") or not _valid_relative_glob(prefix):
        raise ImpactMapError(
            f"edges[{index}].source_prefix must be a relative POSIX directory prefix"
        )
    checks = raw.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ImpactMapError(f"edges[{index}].checks must be a non-empty host mapping")
    host_checks: list[tuple[str, str]] = []
    for host, check_id in checks.items():
        if not isinstance(host, str) or not host:
            raise ImpactMapError(f"edges[{index}].checks has an invalid host name")
        if not isinstance(check_id, str) or check_id not in known_ids:
            raise ImpactMapError(
                f"edges[{index}].checks.{host} references unknown check: {check_id}"
            )
        host_checks.append((host, check_id))
    return Edge(
        kind="descriptor_surface",
        source_prefix=prefix,
        host_checks=tuple(host_checks),
    )


def _list_field(raw: dict[str, Any], key: str, owner: str = "impact map") -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ImpactMapError(f"{owner} field '{key}' must be a list")
    return value


def _text_field(raw: dict[str, Any], key: str, owner: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImpactMapError(f"{owner}.{key} must be a non-empty string")
    return value


def _normalise_changed_path(path: str) -> str | None:
    if not isinstance(path, str) or not path or "\\" in path:
        return None
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or path.startswith("./"):
        return None
    return path


def _valid_relative_glob(glob: str) -> bool:
    return _normalise_changed_path(glob) is not None


def affected_surface_hosts(path: str, hosts: tuple[Any, ...]) -> tuple[str, ...]:
    """Return hosts whose descriptor renders this surface template.

    This mirrors ``tools/build-surface.py``: rules are evaluated in order, a
    matching exact exclusion suppresses a host, and the first matching rule
    wins.  The caller only passes paths below ``core/surface/``.
    """
    relative = path.removeprefix("core/surface/")
    affected: list[str] = []
    for host in hosts:
        for rule in host.surface_rules:
            if not relative.startswith(rule.source_prefix):
                continue
            if relative not in rule.exclude:
                affected.append(host.name)
            break
    return tuple(affected)


def _match_path(
    map_: ImpactMap, path: str, hosts: tuple[Any, ...]
) -> tuple[tuple[Check, ...] | None, str | None]:
    known = map_.checks_by_id
    selected_ids: list[str] = []
    matched = False
    for edge in map_.edges:
        if edge.kind == "glob" and edge.glob is not None:
            if fnmatch.fnmatchcase(path, edge.glob):
                matched = True
                selected_ids.extend(edge.check_ids)
            continue
        if edge.kind != "descriptor_surface" or edge.source_prefix is None:
            continue
        if not path.startswith(edge.source_prefix):
            continue
        matched = True
        affected = affected_surface_hosts(path, hosts)
        if not affected:
            return None, f"surface path matches no host descriptor: {path}"
        host_checks = dict(edge.host_checks)
        for host in affected:
            check_id = host_checks.get(host)
            if check_id is None:
                return None, f"descriptor has no mapped contract: {host}"
            selected_ids.append(check_id)
    if not matched:
        return (), None
    return tuple(known[check_id] for check_id in _unique(selected_ids)), None


def _edge_identity(edge: Edge) -> str:
    if edge.kind == "glob":
        return f"glob:{edge.glob}"
    return f"{edge.kind}:{edge.source_prefix}"


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def main(argv: list[str] | None = None) -> int:
    """Write a planner receipt without granting it authority to fail or skip CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True, dest="map_path")
    parser.add_argument("--hosts", type=Path, required=True, dest="hosts_path")
    parser.add_argument("--changed-files", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    arguments = parser.parse_args(argv)

    try:
        map_ = load_map(arguments.map_path)
        hosts = _load_hosts(arguments.hosts_path)
        result = evaluate(map_, shlex.split(arguments.changed_files), hosts)
    except (ImpactMapError, OSError, ValueError) as error:
        result = ImpactResult(
            selected=(
                Check(
                    id="broad-lane",
                    lane="CHECK",
                    scope="REPO",
                    contract="Broad validation",
                ),
            ),
            modeled_checks=(),
            fallback=True,
            reason=f"planner error: {error}",
            matched_paths=(),
        )

    arguments.output.write_text(
        json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with arguments.summary.open("a", encoding="utf-8", newline="\n") as summary:
        summary.write(result.receipt_markdown())
    return 0


def _load_hosts(hosts_path: Path) -> tuple[Any, ...]:
    """Load the canonical host file only; do not support alternate descriptor roots."""
    resolved = hosts_path.resolve()
    repository = resolved.parent.parent
    canonical = repository / "core" / "hosts.json"
    if resolved != canonical.resolve():
        raise ImpactMapError("--hosts must name the repository's core/hosts.json")
    try:
        from host_descriptors import DescriptorError, load_host_descriptors
    except ImportError as error:
        descriptor_path = Path(__file__).with_name("host_descriptors.py")
        spec = importlib.util.spec_from_file_location("ci_impact_host_descriptors", descriptor_path)
        if spec is None or spec.loader is None:
            raise ImpactMapError(
                f"cannot load host descriptor loader: {descriptor_path}"
            ) from error
        descriptor_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = descriptor_module
        spec.loader.exec_module(descriptor_module)
        DescriptorError = descriptor_module.DescriptorError
        load_host_descriptors = descriptor_module.load_host_descriptors
    try:
        return load_host_descriptors(str(repository))
    except DescriptorError as error:
        raise ImpactMapError(f"cannot load host descriptors: {error}") from error


if __name__ == "__main__":
    sys.exit(main())
