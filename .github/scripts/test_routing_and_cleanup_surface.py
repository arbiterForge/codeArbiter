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
                # #586: containment proven against the FETCHED default, not bare
                # `: gone]` state -- and NOT SHA-ancestry alone. This repo
                # squash-merges by default, so ancestry fails for every ordinary
                # landing; the squash case is proven instead via the merged PR
                # record (a MERGED PR whose headRefOid equals local HEAD). Both
                # phrases are pinned together: dropping either one -- reverting
                # to the old ancestry-only gate, or losing the squash-proof
                # instrument -- must fail this test.
                self.assertRegex(text, r"(?i)contained\s+in\s+the\s+fetched\s+default")
                self.assertRegex(text, r"(?i)PR-record\s+squash\s+proof")
                self.assertRegex(text, r"(?i)\bMERGED\b")
                self.assertRegex(text, r"(?i)headRefOid\s*==\s*HEAD")
                # Three-way artifact classification, with uncertainty biased to unique.
                for cls in ("unique", "redundant", "superseded"):
                    self.assertIn(cls, text.lower())
                # Nothing unique discarded without a per-item confirmation.
                self.assertRegex(text, r"(?i)without an explicit\s+confirmation naming that item")
                # Fast-forward only; no merge commit, no rebase, no reset.
                self.assertIn("--ff-only", text)
                # Safety-checked delete by default. `-D` is forbidden everywhere
                # EXCEPT the #586-scoped exception -- this run's PR-record squash
                # proof plus a restated, named confirmation -- never as a blanket
                # allowance alongside `-d`.
                self.assertRegex(text, r"(?i)MUST\s+use\s+`git branch -d`")
                self.assertRegex(text, r"(?i)MAY\s+use\s+`-D`\s+ONLY\s+when")
                self.assertRegex(text, r"(?i)Everywhere\s+else\s+`-D`\s+is\s+forbidden")
                self.assertRegex(text, r"(?i)MUST\s+NOT\s+delete\s+a\s+remote\s+branch")
                # The point of the whole exercise: this never needs an override.
                self.assertRegex(text, r"(?i)MUST NOT route to `.{0,20}override.{0,20}` when blocked")

    def test_the_command_disclaims_the_override_route(self):
        for plugin, _, _, entry in HOSTS:
            rel = f"{plugin}/{entry}"
            with self.subTest(rel=rel):
                self.assertRegex(read(rel), r"(?i)MUST NOT require")




class TestEphemeralToolCarveOut(unittest.TestCase):
    """Issue #346 / ADR-0023 - a one-time tool run is not a dependency.

    `/ca:add-dep` applied to any download-and-execute, so a duplicate-code
    investigation was pushed toward project-dependency review for `jscpd` that
    the operator had explicitly said must never be a dependency - and with no
    owner for the action, the routing loop reached for `/ca:override`.

    This pins the carve-out on every host projection, and pins the constraints
    that keep it from widening into a dependency bypass. It is deliberately a
    section inside `/ca:add-dep` rather than a command, so the assertions are
    about that command's text.
    """

    def add_dep_surfaces(self):
        yield "core/surface/commands/add-dep.md", read("core/surface/commands/add-dep.md")
        for plugin, _, _, _ in HOSTS:
            rel = ("plugins/ca/commands/add-dep.md" if plugin == "plugins/ca"
                   else f"{plugin}/skills/ca-add-dep/SKILL.md")
            yield rel, read(rel)

    def test_the_carve_out_exists_on_every_host(self):
        for rel, text in self.add_dep_surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)ephemeral tool run")

    def test_the_test_is_the_dependency_graph_not_the_download(self):
        # The distinction that makes the carve-out safe. Anything entering a
        # manifest, lockfile, or base image is still the full review.
        for rel, text in self.add_dep_surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)dependency GRAPH, not the download")
                self.assertRegex(text, r"(?i)lockfile")

    def test_it_keeps_the_review_that_still_applies(self):
        # Pinning and the approved registry are the parts of supply-chain review
        # that do not stop mattering just because nothing is adopted.
        for rel, text in self.add_dep_surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)pin the exact version")
                self.assertRegex(text, r"registry\.npmjs\.org")

    def test_it_must_not_touch_a_manifest_or_lockfile_and_verifies_it(self):
        # The load-bearing constraint, and the fact that it is CHECKED rather
        # than taken on trust. A tool that writes a lockfile has adopted itself.
        for rel, text in self.add_dep_surfaces():
            with self.subTest(rel=rel):
                self.assertRegex(text, r"(?i)MUST NOT modify a manifest or a lockfile")
                self.assertRegex(text, r"git status --porcelain")

    def test_it_does_not_become_an_override_route(self):
        # The specific harm #346 recorded. The carve-out exists so the routing
        # loop terminates; it must never point back at the bypass.
        for rel, text in self.add_dep_surfaces():
            with self.subTest(rel=rel):
                section = text[text.lower().index("ephemeral tool run"):]
                # `/ca:override` may be NAMED as the thing that went wrong, but
                # never offered as a route.
                self.assertNotRegex(section, r"(?i)(use|run|route to|reach for) `?[/$]ca[:-]override")

    def test_the_routing_table_distinguishes_the_two_rows(self):
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/includes/routing-table.md"
            with self.subTest(rel=rel):
                rows = [ln for ln in read(rel).splitlines() if "add-dep" in ln]
                self.assertGreaterEqual(len(rows), 2, "the ephemeral row is missing")
                # Keyed on the section name, not on a loose word: "once" also
                # appears inside "c-once-rn" in the dependency row above.
                ephemeral = [ln for ln in rows if "Ephemeral tool run" in ln]
                self.assertEqual(len(ephemeral), 1, "expected exactly one ephemeral-tool row")
                # It must NOT dispatch the dependency reviewer - that is the
                # whole point of the distinction.
                self.assertRegex(ephemeral[0], r"(?i)no `?dependency-reviewer")

    def test_adr_0023_records_the_decision_with_user_attribution(self):
        adr = read(".codearbiter/decisions/0023-ephemeral-tool-runs-are-a-carve-out-inside-add-dep.md")
        self.assertRegex(adr, r"(?m)^decided-by: \S+@\S+")
        self.assertRegex(adr, r"(?m)^status: accepted")
        # The rejected alternative is recorded, because it is the remedy if the
        # carve-out proves too easy to miss.
        self.assertRegex(adr, r"(?i)new command projected to all three hosts")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
