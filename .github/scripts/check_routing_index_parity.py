#!/usr/bin/env python3
"""Fail when a skill/agent INDEX.md or routing-table.md drifts from the
bodies it is supposed to catalog (issue #592).

The one-line surface summaries the orchestrator routes by (`skills/INDEX.md`,
`agents/INDEX.md`, `includes/routing-table.md`) are documentation, and
documentation drifts from the bodies it describes. Because these indexes
ARE the routing surface -- "skill bodies load on routing only" means a stale
row can send the orchestrator to a skill that no longer exists, or leave a
real skill unreachable -- that drift used to be an authoring discipline
(skill-author Phase 5 prose asked the author to keep them in sync by hand).
This script makes the discipline a mechanical, CI-checked invariant instead.

CHECK LEVEL CHOSEN: Level 1, "Inventory parity" (issue #592's own ascending
list). Rationale: it is the only level with zero false positives on this
tree. Level 2/3 (verify or generate INDEX one-liners from each skill's
frontmatter `description`) was tried during design and rejected: the
INDEX.md one-liners and the SKILL.md/agent frontmatter descriptions are
DELIBERATELY different prose today (compare `tdd`'s INDEX row to its
frontmatter `description` -- same facts, different sentences), so an
exact-match check is red on the entire tree with no actual drift, and a
fuzzy/word-overlap check invents a similarity threshold with no principled
value. Widening to Level 2/3 is future work; it would mean either
regenerating all 51 INDEX one-liners from frontmatter (a payload rewrite
well outside this issue) or hand-tuning a fuzzy matcher's false-positive
rate. Level 1 covers exactly the violation classes named in the issue's own
mutation-proof list: a missing row, an orphan row, and a dangling route.

Checks, run identically across all FOUR generated surfaces (`core/surface`,
`plugins/ca`, `plugins/ca-codex`, `plugins/ca-pi` -- AC-3):

  1. Every skill/routine directory (one containing a `SKILL.md`) has exactly
     one row in that surface's `skills/INDEX.md` (or `routines/INDEX.md`),
     and that row's link target resolves to the real file.
  2. Every agent file (`agents/*.md`, excluding `INDEX.md`) has exactly one
     row in that surface's `agents/INDEX.md`, and that row's link target
     resolves to the real file. `plugins/ca-codex` carries no `agents/`
     directory (Codex has no separate agent-dispatch surface -- reviewer
     personas are named in prose, never a standalone file) and is skipped
     for this half only.
  3. `plugins/ca-codex/skills/INDEX.md` -- a DIFFERENT index from the 23
     shared routines above: the 38 `$ca-*` command-wrapper skills -- gets
     the same inventory-parity treatment against `plugins/ca-codex/skills/`.
  4. `includes/routing-table.md` routes only to things that exist: every
     bare (non-command, non-path) backtick token in a row's "Primary route"
     or "Also dispatch" column must name either a real skill/routine on
     this surface or a real agent name (agents are host-agnostic concepts
     even on `ca-codex`, which has no per-agent file to check against, so
     agent names are validated against `core/surface`'s canonical
     `agents/INDEX.md`). `{{CMD:...}}` and `/command` tokens are out of
     scope -- `check_command_catalog.py` already owns command-catalog
     parity. A short, explicit allowlist covers the handful of tokens that
     are real but are neither a skill nor an agent name (`core`,
     `anti-slop-design`, `medium-documents` -- reference-bundle/doc names
     that legitimately appear in those two columns).

Non-mutating: reads the repo tree, prints a report, exits 0 or 1.

WIRING: a step in the `hooks` job in .github/workflows/ci.yml, alongside
`test_routing_and_cleanup_surface.py` (same job, same gating condition,
same "read the committed surfaces, nothing else" contract).

Run: python .github/scripts/check_routing_index_parity.py   (exit 1 on drift)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from codex_agent_routes import validate_agent_routes

REPO_ROOT = Path(__file__).resolve().parents[2]

_LINK_ROW_RE = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|")
_WRAPPER_ROW_RE = re.compile(r"^\|\s*`\$([A-Za-z0-9_-]+)`\s*\|")
_IDENT_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SEPARATOR_ROW_RE = re.compile(r"^[|:\-\s]+$")

# Real tokens in routing-table.md's "Primary route" / "Also dispatch"
# columns that name neither a skill/routine nor an agent -- reference-bundle
# and doc names. Kept short and explicit on purpose: anything not in this
# set and not a known skill/routine/agent name fails the check.
ROUTING_TABLE_NON_SKILL_ALLOWLIST = {"core", "anti-slop-design", "medium-documents"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_link_rows(text: str) -> list[tuple[str, str]]:
    """`| [name](target) | ... |` rows -- used by skills/routines/agents
    INDEX.md files."""
    rows = []
    for line in text.splitlines():
        m = _LINK_ROW_RE.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def parse_wrapper_rows(text: str) -> list[str]:
    """`` | `$name` | ... | `` rows -- ca-codex's command-wrapper skills
    index, which names skills by token rather than by markdown link."""
    rows = []
    for line in text.splitlines():
        m = _WRAPPER_ROW_RE.match(line)
        if m:
            rows.append(m.group(1))
    return rows


def parse_routing_table_route_tokens(text: str) -> set[str]:
    """Backtick tokens from the "Primary route" and "Also dispatch" columns
    of every data row (columns 1 and 2 after the leading "Invocation cue")."""
    tokens: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if _SEPARATOR_ROW_RE.match(stripped):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        for col in (cells[1], cells[2]):
            tokens.update(re.findall(r"`([^`]+)`", col))
    return tokens


def dir_skill_names(dir_path: Path) -> set[str]:
    """Names of subdirectories that are actually skills/routines -- ones
    containing a SKILL.md, so an empty scaffold directory is not counted."""
    if not dir_path.is_dir():
        return set()
    return {
        p.name
        for p in dir_path.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    }


def dir_agent_names(dir_path: Path) -> set[str]:
    """Names of agent files -- `agents/*.md`, excluding INDEX.md."""
    if not dir_path.is_dir():
        return set()
    return {
        p.stem
        for p in dir_path.glob("*.md")
        if p.stem.upper() != "INDEX"
    }


def check_link_index_parity(
    surface_label: str,
    entries_on_disk: set[str],
    index_rows: list[tuple[str, str]],
    expected_target_fn,
    index_rel: str,
    dir_root: Path,
) -> list[str]:
    """Generic inventory-parity check for a `[name](target)`-row INDEX.md:
    every on-disk entry has exactly one row, every row points at a real,
    correctly-named file."""
    errors: list[str] = []
    row_names = [n for n, _ in index_rows]

    seen: set[str] = set()
    for n in row_names:
        if n in seen:
            errors.append(f"{index_rel}: duplicate INDEX row for {n!r}")
        seen.add(n)

    row_name_set = set(row_names)
    for name in sorted(entries_on_disk - row_name_set):
        errors.append(
            f"{index_rel}: {surface_label} {name!r} exists on disk but has no INDEX row"
        )

    for name, target in index_rows:
        if name not in entries_on_disk:
            errors.append(
                f"{index_rel}: INDEX row {name!r} does not point at an "
                f"existing {surface_label} (target {target!r})"
            )
            continue
        expected = expected_target_fn(name)
        if target != expected:
            errors.append(
                f"{index_rel}: INDEX row {name!r} links to {target!r}, expected {expected!r}"
            )
        elif not (dir_root / target).is_file():
            errors.append(
                f"{index_rel}: INDEX row {name!r} links to {target!r}, which does not exist on disk"
            )
    return errors


def check_wrapper_index_parity(
    entries_on_disk: set[str], row_names: list[str], index_rel: str
) -> list[str]:
    """Same inventory-parity contract as check_link_index_parity, for
    ca-codex's `` `$name` ``-style wrapper-skill index (no per-row link
    target to validate -- just presence)."""
    errors: list[str] = []
    seen: set[str] = set()
    for n in row_names:
        if n in seen:
            errors.append(f"{index_rel}: duplicate INDEX row for {n!r}")
        seen.add(n)

    row_name_set = set(row_names)
    for name in sorted(entries_on_disk - row_name_set):
        errors.append(f"{index_rel}: wrapper skill {name!r} exists on disk but has no INDEX row")
    for name in sorted(row_name_set - entries_on_disk):
        errors.append(
            f"{index_rel}: INDEX row references {name!r} but no such wrapper skill exists on disk"
        )
    return errors


def check_routing_table_dangling(
    routing_table_rel: str, text: str, known_names: set[str]
) -> list[str]:
    """Every bare skill/agent-shaped backtick token in the routing table's
    route columns must name something that actually exists."""
    errors = []
    for token in sorted(parse_routing_table_route_tokens(text)):
        if not _IDENT_RE.match(token):
            continue
        if token in ROUTING_TABLE_NON_SKILL_ALLOWLIST:
            continue
        if token not in known_names:
            errors.append(
                f"{routing_table_rel}: routes to `{token}`, which is not a "
                "known skill/routine/agent on this surface"
            )
    return errors


def check(repo: Path = REPO_ROOT) -> tuple[list[str], dict]:
    """Return (errors, stats). `stats` reports what was actually measured,
    so a CI log line can prove the check executed rather than passing on an
    empty comparison."""
    errors: list[str] = []
    stats = {
        "surfaces": 0,
        "skills_checked": 0,
        "agents_checked": 0,
        "routing_rows_checked": 0,
        "codex_literal_route_lines": 0,
        "codex_literal_route_occurrences": 0,
        "codex_generic_route_lines": 0,
        "codex_generic_route_occurrences": 0,
    }

    core_agents_index = repo / "core" / "surface" / "agents" / "INDEX.md"
    core_agent_names = {n for n, _ in parse_link_rows(read(core_agents_index))}

    # (surface label, root dir, skills-or-routines subdir name, has agents dir)
    surfaces = [
        ("core/surface", repo / "core" / "surface", "skills", True),
        ("plugins/ca", repo / "plugins" / "ca", "skills", True),
        ("plugins/ca-codex", repo / "plugins" / "ca-codex", "routines", True),
        ("plugins/ca-pi", repo / "plugins" / "ca-pi", "routines", True),
    ]

    for label, root, skills_subdir, has_agents in surfaces:
        stats["surfaces"] += 1

        skills_dir = root / skills_subdir
        skills_index_rel = f"{label}/{skills_subdir}/INDEX.md"
        skills_index_path = skills_dir / "INDEX.md"
        skill_names = dir_skill_names(skills_dir)
        skill_rows = parse_link_rows(read(skills_index_path)) if skills_index_path.is_file() else []
        errors += check_link_index_parity(
            "skill" if skills_subdir == "skills" else "routine",
            skill_names,
            skill_rows,
            lambda n: f"{n}/SKILL.md",
            skills_index_rel,
            skills_dir,
        )
        stats["skills_checked"] += len(skill_names)

        known_names = set(skill_names)

        if has_agents:
            agents_dir = root / "agents"
            agents_index_rel = f"{label}/agents/INDEX.md"
            agents_index_path = agents_dir / "INDEX.md"
            agent_names = dir_agent_names(agents_dir)
            agent_rows = parse_link_rows(read(agents_index_path)) if agents_index_path.is_file() else []
            errors += check_link_index_parity(
                "agent",
                agent_names,
                agent_rows,
                lambda n: f"{n}.md",
                agents_index_rel,
                agents_dir,
            )
            stats["agents_checked"] += len(agent_names)
            known_names |= agent_names

        if label == "plugins/ca-codex":
            route_errors, route_stats = validate_agent_routes(root)
            errors += [f"{label}/{error}" for error in route_errors]
            stats["codex_literal_route_lines"] = route_stats["literal_route_lines"]
            stats["codex_literal_route_occurrences"] = route_stats["literal_route_occurrences"]
            stats["codex_generic_route_lines"] = route_stats["generic_route_lines"]
            stats["codex_generic_route_occurrences"] = route_stats["generic_route_occurrences"]

        # ca-codex additionally ships a second, unrelated index: the
        # command-wrapper skills under skills/ (distinct from routines/).
        if label == "plugins/ca-codex":
            wrapper_dir = root / "skills"
            wrapper_index_rel = f"{label}/skills/INDEX.md"
            wrapper_index_path = wrapper_dir / "INDEX.md"
            wrapper_names = dir_skill_names(wrapper_dir)
            wrapper_rows = parse_wrapper_rows(read(wrapper_index_path)) if wrapper_index_path.is_file() else []
            errors += check_wrapper_index_parity(wrapper_names, wrapper_rows, wrapper_index_rel)
            stats["skills_checked"] += len(wrapper_names)

        # Agent names are a host-agnostic concept: validate routing-table
        # tokens against this surface's own skills/routines plus the
        # canonical (core) agent-name set, since ca-codex has no per-agent
        # file of its own to check tokens against.
        routing_table_rel = f"{label}/includes/routing-table.md"
        routing_table_path = root / "includes" / "routing-table.md"
        routing_text = read(routing_table_path) if routing_table_path.is_file() else ""
        errors += check_routing_table_dangling(
            routing_table_rel, routing_text, known_names | core_agent_names
        )
        stats["routing_rows_checked"] += sum(
            1 for line in routing_text.splitlines() if line.strip().startswith("|")
        )

    return errors, stats


def main() -> int:
    errors, stats = check()
    print(
        f"routing/index parity: checked {stats['surfaces']} surfaces, "
        f"{stats['skills_checked']} skill/routine/wrapper entries, "
        f"{stats['agents_checked']} agent entries, "
        f"{stats['routing_rows_checked']} routing-table rows, "
        f"{stats['codex_literal_route_lines']} Codex literal-route lines/"
        f"{stats['codex_literal_route_occurrences']} occurrences, "
        f"{stats['codex_generic_route_lines']} generic-route lines/"
        f"{stats['codex_generic_route_occurrences']} occurrences"
    )
    if errors:
        print("::error::INDEX/routing-surface drift detected:")
        for e in errors:
            print("  - " + e)
        return 1
    print("INDEX.md / routing-table.md are in sync with the skill/agent bodies on every surface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
