#!/usr/bin/env python3
"""Fail when the README badges / prose counts / full-catalog table drift from the repo.

The mechanical backstop for the release skill's surface-sync step (release/SKILL.md
Phase 1 step 5). The badge bug that motivated this guard: a 2.5.0 release left the
README version badge at 2.4.6, the commands badge at 36, and the full-catalog table
missing the /ca:task row entirely — none of which any existing CI job caught.

Invariants enforced (all derived from the repo, never hand-asserted):
  1. README version badge == plugins/ca/.claude-plugin/plugin.json `version`.
  2. README commands/skills/agents count badges == actual file counts.
  3. Every README prose echo of the command count ("N commands", "commands/ (N)") == actual.
  4. The canonical catalog (plugins/ca/COMMANDS.md) enumerates exactly the command files.
  5. The README full-catalog table has a row for every command file (the /ca:task bug).

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
    for kind in ("commands", "skills", "agents"):
        m = re.search(r"badge/%s-(\d+)-" % kind, text)
        if m:
            out[kind] = int(m.group(1))
    return out


def parse_prose_command_counts(text):
    """Every place the README states the command count in prose."""
    counts = [int(n) for n in re.findall(r"(\d+)\s+commands\b", text)]
    counts += [int(n) for n in re.findall(r"commands/\s*\((\d+)\)", text)]
    return counts


def parse_ca_slugs(text):
    """`/ca:<slug>` tokens that appear in markdown table rows (lines starting with |)."""
    slugs = set()
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            slugs.update(re.findall(r"/ca:([a-z][a-z0-9-]*)", line))
    return slugs


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


# ---- the consistency rule (pure) ----------------------------------------------

def consistency_errors(readme_version, plugin_version, badge_counts, prose_counts,
                       real_counts, catalog_slugs, cmd_file_slugs, readme_table_slugs):
    errors = []
    if readme_version != plugin_version:
        errors.append("README version badge %r != plugin.json version %r"
                      % (readme_version, plugin_version))
    for kind in ("commands", "skills", "agents"):
        if badge_counts.get(kind) != real_counts.get(kind):
            errors.append("README %s badge %r != actual %r"
                          % (kind, badge_counts.get(kind), real_counts.get(kind)))
    for n in prose_counts:
        if n != real_counts.get("commands"):
            errors.append("README prose command count %r != actual %r"
                          % (n, real_counts.get("commands")))
    if catalog_slugs != cmd_file_slugs:
        miss = cmd_file_slugs - catalog_slugs
        extra = catalog_slugs - cmd_file_slugs
        errors.append("canonical COMMANDS.md catalog drift — missing: %s extra: %s"
                      % (sorted(miss), sorted(extra)))
    missing_rows = cmd_file_slugs - readme_table_slugs
    if missing_rows:
        errors.append("README full-catalog table missing a row for: %s" % sorted(missing_rows))
    return errors


def check(root):
    root = Path(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    catalog = (root / "plugins" / "ca" / "COMMANDS.md").read_text(encoding="utf-8")
    cmd_slugs = command_file_slugs(root)
    real_counts = {"commands": len(cmd_slugs), "skills": count_skills(root), "agents": count_agents(root)}
    return consistency_errors(
        readme_version=parse_version_badge(readme),
        plugin_version=plugin_version(root),
        badge_counts=parse_count_badges(readme),
        prose_counts=parse_prose_command_counts(readme),
        real_counts=real_counts,
        catalog_slugs=parse_ca_slugs(catalog),
        cmd_file_slugs=cmd_slugs,
        readme_table_slugs=parse_ca_slugs(readme),
    )


def main():
    root = Path(__file__).resolve().parents[2]
    errors = check(root)
    if errors:
        print("::error::README badge/count/catalog drift — run the release surface-sync step:")
        for e in errors:
            print("  - " + e)
        return 1
    print("badge/count/catalog consistent with the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
