#!/usr/bin/env python3
"""Issue #308 / ADR-0022 — the §6 routing contract and the post-merge cleanup owner.

Both halves of #308 are *prose contracts* projected into three host surfaces, so
the thing that can silently regress is not a function's return value — it is a
paragraph quietly reverting, or landing on one host and not the others. These
tests pin what the ADR actually decided, on every generated projection:

  1. §6 states the three routing tiers and no longer requires the user to retype
     a command the orchestrator has already named.
  2. Tier 1 is bounded by BOTH axes — unambiguous AND non-destructive — and the
     destructive set is enumerated where the orchestrator can see it.
  3. The invariant §6 protects is preserved: the orchestrator still routes rather
     than performing the work itself.
  4. A missing owner is a routing gap, never a reason to reach for /ca:override.
     That substitution is the concrete harm #308 recorded.
  5. `cleanup` / `post-merge-cleanup` exists as a real owner on every host, is
     reachable from the routing table, and carries the safety gates the issue's
     acceptance criteria name: proven ancestry, per-item confirmation, --ff-only,
     and `branch -d` rather than `-D`.

Offline and dependency-free: reads the committed surfaces, nothing else.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Each host projects the same core surface under its own layout: Claude Code
# gets `commands/<name>.md` + `skills/<skill>/`, while Codex and Pi expose the
# command as a `ca-`-prefixed skill and keep the routine under `routines/`.
# (plugin dir, skill dir, routine dir for post-merge-cleanup, command entry point)
HOSTS = (
    ("plugins/ca", "skills", "skills/post-merge-cleanup", "commands/cleanup.md"),
    ("plugins/ca-codex", "routines", "routines/post-merge-cleanup", "skills/ca-cleanup/SKILL.md"),
    ("plugins/ca-pi", "routines", "routines/post-merge-cleanup", "skills/ca-cleanup/SKILL.md"),
)


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def orchestrator_section_six(text: str) -> str:
    """§6's body, from its heading to the next section heading."""
    match = re.search(r"^## §6 .*?$(.*?)^## §7 ", text, re.MULTILINE | re.DOTALL)
    assert match, "ORCHESTRATOR.md has no §6 section"
    return match.group(1)


class TestSectionSixRoutesRatherThanRedirects(unittest.TestCase):
    """ADR-0022: route on understood intent, in three tiers."""

    def surfaces(self):
        yield "core/surface/ORCHESTRATOR.md", read("core/surface/ORCHESTRATOR.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/ORCHESTRATOR.md"
            yield rel, read(rel)

    def test_section_six_names_all_three_tiers(self):
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                section = orchestrator_section_six(text)
                self.assertRegex(section, r"(?i)unambiguous and non-destructive")
                self.assertRegex(section, r"(?i)\bprobable\b")
                self.assertRegex(section, r"(?i)genuinely unclear")

    def test_section_six_no_longer_demands_the_user_retype_the_command(self):
        # The exact sentence the ADR retired. Its return is the regression.
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                self.assertNotIn("nothing routes without their", orchestrator_section_six(text))

    def test_tier_one_requires_both_axes_and_enumerates_the_destructive_set(self):
        # Clarity and risk are separate axes: an obvious /override is still tier 2.
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                section = orchestrator_section_six(text)
                self.assertRegex(section, r"(?i)separate axes")
                for irreversible in (
                    r"override",                       # the logged bypass
                    r"merge to\s+the default branch",  # irreversible on the shared history
                    r"branch or worktree deletion",    # local data loss
                    r"release and tag publication",    # published, immutable (issue #386)
                    # Gates-off maintainer mode, in every host's rendering of the
                    # {{CMD:dev}} token: /ca:dev (Claude Code), /ca-dev (Pi),
                    # $ca-dev (Codex), and the unrendered core template.
                    r"\{\{CMD:dev\}\}|[/$]ca[:-]dev",
                ):
                    self.assertRegex(section, rf"(?i){irreversible}")

    def test_the_invariant_section_six_protects_is_still_stated(self):
        # §6 exists so nothing happens outside a gated command path. Auto-routing
        # INTO the command satisfies it; improvising the operation does not.
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                section = orchestrator_section_six(text)
                self.assertRegex(section, r"(?i)routes the command.{0,80}not improvise|does not improvise")

    def test_a_missing_owner_is_a_routing_gap_not_an_override(self):
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(orchestrator_section_six(text), r"(?i)routing gap")


class TestRedirectIsNowTierTwoAndThreeOnly(unittest.TestCase):
    def surfaces(self):
        yield "core/surface/includes/redirect.md", read("core/surface/includes/redirect.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/includes/redirect.md"
            yield rel, read(rel)

    def test_redirect_declares_it_is_not_used_for_tier_one(self):
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)tier 1 does not use this file")

    def test_redirect_forbids_steering_to_override_over_a_coverage_hole(self):
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)routing gap")
                self.assertRegex(text, r"(?i)never steer the user toward")


class TestPostMergeCleanupOwnerExistsOnEveryHost(unittest.TestCase):
    def test_the_command_entry_point_ships_on_every_host(self):
        for plugin, _, _, entry in HOSTS:
            rel = f"{plugin}/{entry}"
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).is_file(), f"missing {rel}")

    def test_the_routine_ships_on_every_host(self):
        for plugin, _, routine, _ in HOSTS:
            rel = f"{plugin}/{routine}/SKILL.md"
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).is_file(), f"missing {rel}")

    def test_the_routing_table_points_the_trigger_at_the_owner(self):
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/includes/routing-table.md"
            with self.subTest(rel=rel):
                rows = [ln for ln in read(rel).splitlines() if "post-merge-cleanup" in ln]
                self.assertEqual(len(rows), 1, f"{rel}: expected exactly one cleanup route")
                self.assertRegex(rows[0], r"(?i)merged")

    def test_the_skill_carries_the_issue_308_acceptance_gates(self):
        # Each assertion is one acceptance criterion from the issue, not prose taste.
        for plugin, _, routine, _ in HOSTS:
            rel = f"{plugin}/{routine}/SKILL.md"
            with self.subTest(rel=rel):
                text = read(rel)
                # Ancestry proven against the FETCHED default, not `: gone]` state.
                self.assertRegex(text, r"(?i)ancestor of the fetched default")
                # Three-way artifact classification, with uncertainty biased to unique.
                for cls in ("unique", "redundant", "superseded"):
                    self.assertIn(cls, text.lower())
                # Nothing unique discarded without a per-item confirmation.
                self.assertRegex(text, r"(?i)without an explicit\s+confirmation naming that item")
                # Fast-forward only; no merge commit, no rebase, no reset.
                self.assertIn("--ff-only", text)
                # Safety-checked delete only, and never the remote branch.
                self.assertRegex(text, r"(?i)MUST use `git branch -d`, never `-D`")
                self.assertRegex(text, r"(?i)MUST NOT delete a remote branch")
                # The point of the whole exercise: this never needs an override.
                self.assertRegex(text, r"(?i)MUST NOT route to `.{0,20}override.{0,20}` when blocked")

    def test_the_command_disclaims_the_override_route(self):
        for plugin, _, _, entry in HOSTS:
            rel = f"{plugin}/{entry}"
            with self.subTest(rel=rel):
                self.assertRegex(read(rel), r"(?i)MUST NOT require")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
