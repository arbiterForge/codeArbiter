#!/usr/bin/env python3
"""#437 mode-plane-deterministic-flip — T-71 / T-72 (AC-50, AC-51).

Two guarantees, both prose contracts projected across many files, which is
exactly the shape that regresses silently with a green suite:

  AC-50 — no live `docs/`, `CONTRIBUTING.md`, or site surface states that
  `ORCHESTRATOR.md` is the always-on kernel, or names `/ca:dev`, `/ca:arbiter`,
  or `CODEARBITER_DEV` as current. Known trap on record
  (`curated-site-prose-drifts-silently`): `site/src/curated/` is hand-written
  and merged by the generator with no gate comparing it to the surface it
  documents, so a removed command can live on in published docs indefinitely
  unless something scans the prose directly. This scans the prose directly.

  AC-51 — the historical surfaces the spec names byte-unchanged
  (`gate-events.log`, `decisions/`, `sprint-log.md`, published CHANGELOGs,
  `docs/reports/`) really are, versus this branch's merge-base with `main`.
  "Byte-unchanged" cannot mean zero-diff outright: ADR-0030 itself lands a
  new file under `.codearbiter/decisions/`, appends to `decision-log.md`, and
  every hook call appends to `gate-events.log` throughout this very campaign
  — all legitimate, all pure additions (0 deletions). What must never happen
  is a rewrite or removal of PRE-EXISTING content in one of these paths, the
  same append-only contract this repo already enforces on them at commit
  time (H-05/H-11). This test asserts that contract directly against git
  history instead of trusting it.

R-1: AC-50/AC-51 need an explicit exclusion list (the byte-frozen set) —
`TestFrozenExclusionListIsExplicit` asserts the list IS that set, spelled out
here as literal strings, not synthesized by a glob/regex a future edit could
silently narrow.

Offline and dependency-free except for `git` itself: reads the committed +
working-tree state, writes nothing.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# R-1 -- the byte-frozen historical set, spelled out as an explicit tuple.
# Spec:87-88,202-203 / ADR-0030 position 1: "Historical surfaces (gate-events
# .log, decisions/, sprint-log.md, published CHANGELOGs, the site changelog)
# are byte-unchanged." `docs/reports/` is named in T-72's own verification
# row. The site changelog (`site/src/content/docs/changelog.md`) is
# gitignored/generated -- never tracked -- so a `git diff` against it is
# structurally a no-op and it is intentionally not repeated in this list.
FROZEN_HISTORICAL = (
    ".codearbiter/gate-events.log",
    ".codearbiter/decisions",
    ".codearbiter/sprint-log.md",
    "CHANGELOG.md",
    "plugins/ca-codex/CHANGELOG.md",
    "plugins/ca-pi/CHANGELOG.md",
    "plugins/ca-sandbox/CHANGELOG.md",
    "docs/reports",
)

# The members of FROZEN_HISTORICAL that are directories, not single files.
FROZEN_DIRS = frozenset({".codearbiter/decisions", "docs/reports"})

# The dead surfaces AC-50 forbids a *live* doc from stating as current.
# Literal substrings, matched exactly on the byte -- a paraphrase-to-nothing
# edit is not the failure mode this guards against; the concrete token
# reappearing is.
#
# Deliberately NOT included: "dev-active". AC-50's text names ORCHESTRATOR.md,
# /ca:dev, /ca:arbiter, and CODEARBITER_DEV as current -- it does not name the
# marker string. Lane E ships a live migration (T-47/AC-41: "a pre-existing
# dev-active marker converts to dangerous exactly once and is removed") that a
# doc may need to describe honestly as *historical* migration behavior, not as
# a current entry point. Banning the string here would make an accurate future
# doc fail a check that outlives this campaign once T-78 wires this file into
# ci.yml. If a later task needs "dev-active" banned as a live-current claim,
# that is a new, deliberate addition to this tuple, not an inherited one.
DEAD_TOKENS = (
    "ORCHESTRATOR.md",
    "/ca:dev",
    "/ca:arbiter",
    "$ca-dev",
    "$ca-arbiter",
    "/ca-dev",
    "/ca-arbiter",
    "CODEARBITER_DEV",
)

# Generated/gitignored site surfaces excluded from the live-doc scan: they
# are regenerated deterministically by `npm run gen` and absent from a fresh
# checkout, so scanning them would assert against build output, not authored
# prose. `arbiter.md` itself is explicitly out of AC-50's scope too -- AC-37
# governs its own "(formerly ORCHESTRATOR.md)" header line, a different,
# sanctioned mention -- which is why the scope below is docs/+CONTRIBUTING+
# site/ only, never core/surface/.
_GENERATED_SITE_PREFIXES = (
    "site/node_modules/",
    "site/dist/",
    "site/.astro/",
    "site/src/content/docs/reference/",
)
_GENERATED_SITE_FILES = frozenset({"site/src/content/docs/changelog.md"})


def _is_frozen(relpath: str) -> bool:
    if relpath in FROZEN_HISTORICAL:
        return True
    return any(relpath == d or relpath.startswith(d + "/") for d in FROZEN_DIRS)


def _is_generated_site(relpath: str) -> bool:
    if relpath in _GENERATED_SITE_FILES:
        return True
    return any(relpath.startswith(prefix) for prefix in _GENERATED_SITE_PREFIXES)


def _live_scope_files() -> list[Path]:
    """Every markdown file AC-50 governs, as it exists on disk right now.

    Deliberately a filesystem walk, not `git ls-files`: a lane's working-tree
    deletion (this campaign deletes `site/src/curated/commands/{dev,arbiter}
    .md`) is real compliance the moment the file is gone, even before the
    curator commits it (GR-2) -- `git ls-files` would still list it as
    tracked-but-missing and falsely flag it unreadable.
    """
    candidates: list[Path] = []
    contributing = REPO / "CONTRIBUTING.md"
    if contributing.is_file():
        candidates.append(contributing)
    for root_name in ("docs", "site"):
        root = REPO / root_name
        if not root.is_dir():
            continue
        for pattern in ("*.md", "*.mdx"):
            for path in root.rglob(pattern):
                rel = path.relative_to(REPO).as_posix()
                if _is_frozen(rel) or _is_generated_site(rel):
                    continue
                candidates.append(path)
    return sorted(set(candidates))


def _merge_base() -> str:
    for ref in ("origin/main", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", ref],
            cwd=REPO, capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise RuntimeError("no merge-base found against origin/main or main")


class TestFrozenExclusionListIsExplicit(unittest.TestCase):
    """R-1: the byte-frozen exclusion list is asserted AS a list -- a silent
    drop of one entry from FROZEN_HISTORICAL fails here, by name, rather
    than just narrowing what TestHistoricalSurfacesAreByteFrozen happens to
    check."""

    def test_the_set_is_exactly_the_spec_named_historical_surfaces(self):
        expected = {
            ".codearbiter/gate-events.log",
            ".codearbiter/decisions",
            ".codearbiter/sprint-log.md",
            "CHANGELOG.md",
            "plugins/ca-codex/CHANGELOG.md",
            "plugins/ca-pi/CHANGELOG.md",
            "plugins/ca-sandbox/CHANGELOG.md",
            "docs/reports",
        }
        self.assertEqual(set(FROZEN_HISTORICAL), expected)

    def test_every_frozen_path_exists_in_the_repo(self):
        for rel in FROZEN_HISTORICAL:
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).exists(), f"{rel} is missing")


class TestNoLiveDocStatesTheOldModel(unittest.TestCase):
    """AC-50."""

    def test_no_dead_token_survives_in_the_live_corpus(self):
        files = _live_scope_files()
        # A sanity floor on the walk itself: if this collapses to a handful
        # of files, the scope logic broke and the rest of this test proves
        # nothing.
        self.assertGreater(len(files), 50, "live-doc scope collapsed -- check the walk")
        for path in files:
            rel = path.relative_to(REPO).as_posix()
            text = path.read_text(encoding="utf-8")
            for token in DEAD_TOKENS:
                with self.subTest(rel=rel, token=token):
                    self.assertNotIn(token, text)


class TestHistoricalSurfacesAreByteFrozen(unittest.TestCase):
    """AC-51 / T-72."""

    def test_zero_deletions_against_merge_base_for_every_frozen_path(self):
        base = _merge_base()
        result = subprocess.run(
            ["git", "diff", "--numstat", base, "--", *FROZEN_HISTORICAL],
            cwd=REPO, capture_output=True, text=True, check=True,
        )
        violations = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            added, deleted, filename = line.split("\t", 2)
            if deleted != "0":
                violations.append((filename, added, deleted))
        self.assertEqual(
            violations, [],
            f"pre-existing content changed or removed since merge-base {base}: {violations}",
        )


class TestEveryCitedSectionNumberResolves(unittest.TestCase):
    """Hook block messages cite `§N` at the user; those citations must land.

    The numbering rule used to live only in an HTML comment at the top of
    safety-core.md — invisible in rendered Markdown, and enforced by nothing.
    A renumbering during an ordinary edit would leave ~30 fail-closed block
    messages pointing at a section that no longer exists, and the suite would
    stay green while every one of them dangled.

    Reads the citations out of the enforcement sources rather than hard-coding
    them, so a NEW citation is covered the moment it is written.
    """

    _CITATION = re.compile(r"(?:ORCHESTRATOR|safety-core) §([0-9]+)")
    _HEADING = re.compile(r"^## §([0-9]+)\b", re.M)

    def test_each_section_cited_by_a_hook_exists_in_safety_core(self):
        cited = set()
        for path in sorted((REPO / "core" / "pysrc").glob("*.py")):
            cited |= set(self._CITATION.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(cited, "no §N citations found — this guard would measure nothing")
        present = set(self._HEADING.findall(
            (REPO / "core" / "surface" / "includes" / "safety-core.md").read_text(encoding="utf-8")))
        self.assertEqual(
            sorted(cited - present), [],
            "hook block messages cite section(s) that safety-core.md does not define. "
            "Section numbers are a public interface: renumbering breaks every citation "
            "at once, and only the user sees the dangling reference. "
            "cited={} present={}".format(sorted(cited), sorted(present)))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
