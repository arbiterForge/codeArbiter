#!/usr/bin/env python3
"""Fail when README badges, core discovery, or the full catalog drift.

The mechanical backstop for the release skill's surface-sync step (release/SKILL.md
Phase 1 step 5). The badge bug that motivated this guard: a 2.5.0 release left the
README version badge at 2.4.6, the commands badge at 36, and the full-catalog table
missing the /ca:task row entirely. None of those defects had a mechanical guard.

Invariants enforced (all derived from the repo, never hand-asserted):
  1. README version badge == plugins/ca/.claude-plugin/plugin.json `version`.
  2. README core-lane/skills/agents badges == canonical source counts.
  3. README does not market the raw command-file count.
  4. The marked README chooser enumerates exactly the registry's core lanes.
  5. The canonical catalog (plugins/ca/COMMANDS.md) enumerates every command file.

Run: python .github/scripts/check_badge_consistency.py   (exit 1 on any drift)
"""
import json
import re
import sys
from pathlib import Path

# ---- pure parsers -------------------------------------------------------------

def parse_version_badge(text):
    m = re.search(r"badge/version-(\d+\.\d+\.\d+)-", text)
    return m.group(1) if m else None


def parse_count_badges(text):
    out = {}
    for kind in ("core_lanes", "skills", "agents"):
        m = re.search(r"badge/%s-(\d+)-" % kind, text)
        if m:
            out[kind] = int(m.group(1))
    return out


def parse_raw_command_count_claims(text):
    """Raw route-file counts that must not be used as product marketing."""
    claims = re.findall(r"badge/commands-(\d+)-", text)
    claims += re.findall(r"(?<![-\w])(\d+)\s+commands\b", text)
    claims += re.findall(r"commands/\s*\((\d+)\)", text)
    return claims


def parse_ca_slugs(text):
    """`/ca:<slug>` tokens that appear in markdown table rows (lines starting with |)."""
    slugs = set()
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            slugs.update(re.findall(r"/ca:([a-z][a-z0-9-]*)", line))
    return slugs


def parse_readme_core_slugs(text):
    """Routes inside the single marked README core-lane chooser."""
    match = re.search(
        r"<!-- core-lane-chooser:start -->(.*?)<!-- core-lane-chooser:end -->",
        text,
        re.DOTALL,
    )
    return parse_ca_slugs(match.group(1)) if match else set()


# ---- repo gatherers -----------------------------------------------------------

def command_file_slugs(root):
    d = root / "plugins" / "ca" / "commands"
    return {p.stem for p in d.glob("*.md") if p.stem.upper() != "INDEX"}


def count_skills(root):
    d = root / "plugins" / "ca" / "skills"
    return sum(1 for p in d.iterdir() if p.is_dir())


def count_agents(root):
    d = root / "plugins" / "ca" / "agents"
    return sum(1 for p in d.glob("*.md") if p.stem.upper() != "INDEX")


def plugin_version(root):
    data = json.loads((root / "plugins" / "ca" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return data.get("version")


def registry_core_slugs(root):
    data = json.loads((root / "core" / "surface" / "command-routes.json").read_text(encoding="utf-8"))
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise ValueError("core/surface/command-routes.json: commands must be an object")
    return {slug for slug, entry in commands.items() if entry.get("visibility") == "core"}


# ---- the consistency rule (pure) ----------------------------------------------

def consistency_errors(readme_version, plugin_version, badge_counts, raw_command_count_claims,
                       real_counts, catalog_slugs, cmd_file_slugs, readme_core_slugs,
                       registry_core_slugs):
    errors = []
    if readme_version != plugin_version:
        errors.append("README version badge %r != plugin.json version %r"
                      % (readme_version, plugin_version))
    for kind in ("core_lanes", "skills", "agents"):
        if badge_counts.get(kind) != real_counts.get(kind):
            label = kind.replace("_", " ")
            errors.append("README %s badge %r != actual %r"
                          % (label, badge_counts.get(kind), real_counts.get(kind)))
    if raw_command_count_claims:
        errors.append("README raw command-count marketing is forbidden: %s"
                      % raw_command_count_claims)
    if readme_core_slugs != registry_core_slugs:
        miss = registry_core_slugs - readme_core_slugs
        extra = readme_core_slugs - registry_core_slugs
        errors.append("README core-lane chooser drift; missing: %s extra: %s"
                      % (sorted(miss), sorted(extra)))
    if catalog_slugs != cmd_file_slugs:
        miss = cmd_file_slugs - catalog_slugs
        extra = catalog_slugs - cmd_file_slugs
        errors.append("canonical COMMANDS.md catalog drift — missing: %s extra: %s"
                      % (sorted(miss), sorted(extra)))
    return errors


def check(root):
    root = Path(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    catalog = (root / "plugins" / "ca" / "COMMANDS.md").read_text(encoding="utf-8")
    cmd_slugs = command_file_slugs(root)
    core_slugs = registry_core_slugs(root)
    real_counts = {
        "core_lanes": len(core_slugs),
        "skills": count_skills(root),
        "agents": count_agents(root),
    }
    return consistency_errors(
        readme_version=parse_version_badge(readme),
        plugin_version=plugin_version(root),
        badge_counts=parse_count_badges(readme),
        raw_command_count_claims=parse_raw_command_count_claims(readme),
        real_counts=real_counts,
        catalog_slugs=parse_ca_slugs(catalog),
        cmd_file_slugs=cmd_slugs,
        readme_core_slugs=parse_readme_core_slugs(readme),
        registry_core_slugs=core_slugs,
    )


def main():
    root = Path(__file__).resolve().parents[2]
    errors = check(root)
    if errors:
        print("::error::README badge/core-lane/catalog drift; run the release surface-sync step:")
        for e in errors:
            print("  - " + e)
        return 1
    print("badge/core-lane/catalog consistent with the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
