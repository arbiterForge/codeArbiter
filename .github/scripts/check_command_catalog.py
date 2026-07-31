#!/usr/bin/env python3
"""Fail when the canonical command catalog drifts from the repo (T-34, AC-2.8).

A dedicated, non-mutating pre-tag check for the `ca` release target
(`.codearbiter/release-targets.md`), declared alongside
`check_badge_consistency.py` — that script already asserts this same pair of
invariants as part of a broader README-badge check, but the release skill
(`core/surface/skills/release/SKILL.md`) delegates ALL of a target's extra
release-surface consistency to whatever its row's declared `pre-tag`
commands assert (DECISION-0034), and this repo's own `ca` row declares this
script as its own, separate line — so it must exist on its own, not only as
a side effect of the badge check.

Invariants enforced (both derived from the repo, never hand-asserted):
  1. The canonical catalog (plugins/ca/COMMANDS.md) enumerates exactly the
     command files under plugins/ca/commands/ (excluding INDEX).
  2. The README full-catalog table has a row for every command file (the
     historical /ca:task omission this whole check family exists to catch).

Mutates nothing — reads three files, prints a report, and exits 0 or 1.

Run: python .github/scripts/check_command_catalog.py   (exit 1 on any drift)
"""
import re
import sys
from pathlib import Path


def command_file_slugs(root):
    d = root / "plugins" / "ca" / "commands"
    return {p.stem for p in d.glob("*.md") if p.stem.upper() != "INDEX"}


def parse_ca_slugs(text):
    """`/ca:<slug>` tokens that appear in markdown table rows (lines starting
    with `|`) — the same extraction `check_badge_consistency.py` uses, so the
    two checks can never disagree about what counts as a catalog row."""
    slugs = set()
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            slugs.update(re.findall(r"/ca:([a-z][a-z0-9-]*)", line))
    return slugs


def consistency_errors(cmd_file_slugs, catalog_slugs, readme_table_slugs):
    errors = []
    if catalog_slugs != cmd_file_slugs:
        missing = cmd_file_slugs - catalog_slugs
        extra = catalog_slugs - cmd_file_slugs
        errors.append(
            "canonical COMMANDS.md catalog drift — missing: %s extra: %s"
            % (sorted(missing), sorted(extra))
        )
    missing_rows = cmd_file_slugs - readme_table_slugs
    if missing_rows:
        errors.append(
            "README full-catalog table missing a row for: %s" % sorted(missing_rows)
        )
    return errors


def check(root):
    root = Path(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    catalog = (root / "plugins" / "ca" / "COMMANDS.md").read_text(encoding="utf-8")
    cmd_slugs = command_file_slugs(root)
    return consistency_errors(
        cmd_file_slugs=cmd_slugs,
        catalog_slugs=parse_ca_slugs(catalog),
        readme_table_slugs=parse_ca_slugs(readme),
    )


def main():
    root = Path(__file__).resolve().parents[2]
    errors = check(root)
    if errors:
        print("::error::command catalog drift — reconcile before tagging:")
        for e in errors:
            print("  - " + e)
        return 1
    print("command catalog consistent with the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
