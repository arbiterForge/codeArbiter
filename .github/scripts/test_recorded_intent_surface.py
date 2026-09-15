#!/usr/bin/env python3
"""ADR-0025 — recorded intent precedes autonomous scoring and spec shaping.

The decision is a *prose contract* projected into three host surfaces, so the
regression mode is a paragraph quietly reverting — or landing on one host and
not the others. These tests pin what ADR-0025 actually decided, on every
generated projection that carries the surface:

  1. smarts/core.md Step 0 exists, is SCOPED (applies to /sprint scoring and
     brainstorming; decision-variance, grader, and decision-challenger exempt
     BY NAME), ranks "answered" by the Phase 4 authority order, states the
     three outcomes, the index-first loading rule, and the fail-soft sentence.
     The scoping is the load-bearing half: an unscoped Step 0 would let a
     rank-4 artifact defeat a rank-1 user steer inside the arbitration lanes
     (the CRITICAL defect the 2026-08-07 adversarial review killed).
  2. SPRINT.md runs the recorded-intent read BEFORE Phase 1 spec approval
     (fail-soft), lists the ADR/deferral contradiction as a NEVER-auto-decided
     hard gate WITH the stale-record valve, pins the `intent:` field's
     position AFTER the `confidence:` token (the harvest parser is
     positional), and names stale-record in the repeated-trip diagnostic.
  3. grader.md carries the informational ADR-citation line AND its explicit
     Step-0 exemption. Codex ships it as a packaged Markdown resource charter,
     never a native agent registration, so the grader surface is pinned on all
     four generated projections.
  4. brainstorming carries all four touches: the fail-soft pre-flight block
     (explicitly exempt from the read-or-STOP contract), the Phase 1
     deferral-resurrection fork, the Phase 2 accepted-ADR conformance check
     with the supersession-fork pairing, and the Phase 5 review bullet.

Offline and dependency-free: reads the committed surfaces, nothing else.
Every assertion has been proven to die to a mutant (passage deleted -> red);
the transcript rides in the introducing PR.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from codex_agent_routes import validate_agent_routes

REPO = Path(__file__).resolve().parents[2]

# Host layouts (same projection map as test_routing_and_cleanup_surface.py):
# Claude Code keeps skills/ and agents/; Codex and Pi keep routines/, and all
# three host packages ship canonical agent Markdown resources.
SMARTS_COPIES = (
    "core/surface/includes/smarts/core.md",
    "plugins/ca/includes/smarts/core.md",
    "plugins/ca-codex/includes/smarts/core.md",
    "plugins/ca-pi/includes/smarts/core.md",
)
SPRINT_COPIES = (
    "core/surface/SPRINT.md",
    "plugins/ca/SPRINT.md",
    "plugins/ca-codex/SPRINT.md",
    "plugins/ca-pi/SPRINT.md",
)
GRADER_COPIES = (
    "core/surface/agents/grader.md",
    "plugins/ca/agents/grader.md",
    "plugins/ca-codex/agents/grader.md",
    "plugins/ca-pi/agents/grader.md",
)
BRAINSTORMING_COPIES = (
    "core/surface/skills/brainstorming/SKILL.md",
    "plugins/ca/skills/brainstorming/SKILL.md",
    "plugins/ca-codex/routines/brainstorming/SKILL.md",
    "plugins/ca-pi/routines/brainstorming/SKILL.md",
)


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


class SurfaceCase(unittest.TestCase):
    """Assert a regex on every copy of a surface, naming the copy on failure."""

    def assert_on(self, copies, pattern: str, why: str) -> None:
        for rel in copies:
            with self.subTest(copy=rel):
                text = read(rel)
                self.assertRegex(text, pattern, f"{rel}: {why}")


class TestSmartsStepZero(SurfaceCase):
    def test_step_zero_exists_and_precedes_the_lenses(self):
        for rel in SMARTS_COPIES:
            with self.subTest(copy=rel):
                text = read(rel)
                step0 = text.find("## Step 0")
                lenses = text.find("## The six lenses")
                self.assertGreater(step0, -1, f"{rel}: no Step 0 section")
                self.assertGreater(lenses, step0,
                                   f"{rel}: Step 0 must precede the lenses")

    def test_scope_names_the_two_appliers_and_three_exemptions(self):
        self.assert_on(SMARTS_COPIES,
                       r"(?i)applies to `/sprint`.*and\s+`brainstorming`",
                       "Step 0 must be scoped to /sprint scoring + brainstorming")
        for name in ("decision-variance", "grader", "decision-challenger"):
            self.assert_on(SMARTS_COPIES,
                           rf"(?is)exempt by name.{{0,200}}{name}",
                           f"Step 0 must exempt {name} BY NAME")

    def test_answered_is_ranked_by_the_authority_order(self):
        self.assert_on(SMARTS_COPIES,
                       r"(?is)explicit user decision this session.{0,120}>"
                       r".{0,120}decision-log\.md.{0,200}>.{0,120}accepted ADR",
                       "the authority-order chain (user > log > ADR) must be stated")
        self.assert_on(SMARTS_COPIES,
                       r"(?i)never\s+silently conform downward",
                       "a lower-ranked record must not defeat a higher-ranked steer")

    def test_three_outcomes_present(self):
        for outcome in (r"\*\*Answered\*\*", r"\*\*Constrains\*\*", r"\*\*Silent\*\*"):
            self.assert_on(SMARTS_COPIES, outcome,
                           "all three Step-0 outcomes must be stated")

    def test_sprint_contradiction_is_the_hard_gate_not_a_reconcile_dispatch(self):
        self.assert_on(SMARTS_COPIES,
                       r"(?i)IS the contradiction hard gate",
                       "under /sprint an answered-contradiction is the hard gate")
        self.assert_on(SMARTS_COPIES,
                       r"(?i)never a mid-sprint reconcile dispatch",
                       "no mid-sprint reconcile dispatch (SPRINT Rule-1 override)")

    def test_index_first_loading_rule(self):
        self.assert_on(SMARTS_COPIES,
                       r"(?i)never bulk-read `?plans/`? or `?decisions/`?",
                       "the index-first loading rule is normative (consumer cost bound)")

    def test_fail_soft_sentence(self):
        self.assert_on(SMARTS_COPIES,
                       r"(?i)intent: silent — no decomposition record",
                       "fail-soft: absent record proceeds, never STOPs")


class TestSprintIntentRead(SurfaceCase):
    def test_read_runs_before_spec_approval_and_is_fail_soft(self):
        self.assert_on(SPRINT_COPIES,
                       r"(?i)recorded-intent read — BEFORE spec approval, fail-soft",
                       "the intent read precedes Phase 1 approval")
        self.assert_on(SPRINT_COPIES,
                       r"(?is)absent\s+`plans/` or `decisions/`.{0,120}never a STOP",
                       "sprint-surface fail-soft must be explicit (AC-04)")

    def test_contradiction_is_a_hard_gate_with_the_valve(self):
        self.assert_on(SPRINT_COPIES,
                       r"(?i)contradict an accepted ADR or a recorded deferral",
                       "the contradiction hard gate must be in the NEVER list")
        self.assert_on(SPRINT_COPIES,
                       r"(?i)re-evaluation trigger has occurred is reopened",
                       "valve: an occurred trigger reopens, it is not a contradiction")
        self.assert_on(SPRINT_COPIES,
                       r"(?i)one stop per record per sprint",
                       "valve: dedup — later identical collisions cite the first ruling")

    def test_intent_field_position_is_pinned_after_confidence(self):
        self.assert_on(SPRINT_COPIES,
                       r"(?i)`intent:` goes AFTER the `confidence:` token",
                       "position pin: the harvest title parser is positional")

    def test_stale_record_named_in_the_diagnostic(self):
        self.assert_on(SPRINT_COPIES,
                       r"(?i)or the record itself is stale",
                       "repeated trips must implicate the record, not only the spec")


class TestGraderInformationalCitation(SurfaceCase):
    def test_codex_recorded_intent_charter_routes_close_over_the_shipped_inventory(self):
        """The grader is a packaged charter, so all advertised Codex agent
        routes must resolve in the exact package that carries it."""
        errors, stats = validate_agent_routes(REPO / "plugins" / "ca-codex")
        self.assertEqual(errors, [])
        self.assertGreater(stats["agents_indexed"], 0)
        self.assertGreater(stats["literal_route_occurrences"], 0)
        self.assertGreater(stats["generic_route_occurrences"], 0)

    def test_grader_cites_but_never_conforms(self):
        self.assert_on(GRADER_COPIES,
                       r"(?i)Recorded prior decisions \(informational\)",
                       "the assignment format carries the ADR-citation line")
        self.assert_on(GRADER_COPIES,
                       r"(?i)exempt by name from smarts/core\.md Step 0",
                       "the grader's Step-0 exemption is stated where the grader reads")

    def test_codex_grader_is_a_packaged_resource_not_native_registration(self):
        text = read("plugins/ca-codex/agents/grader.md")
        self.assertNotIn("\ntools:", text)
        self.assertNotIn("\nmodel:", text)
        self.assertNotIn("\npi-skills:", text)
        self.assertIn("classification: reviewer", text)


class TestBrainstormingTouches(SurfaceCase):
    def test_preflight_fail_soft_block_is_exempt_from_read_or_stop(self):
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)exempt from the read-or-STOP rule",
                       "the recorded-intent pre-flight block must not inherit STOP")
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)intent: silent — no decomposition record",
                       "brainstorming fail-soft: absent record proceeds")

    def test_phase1_resurrection_is_a_fork(self):
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?is)resurrects a capability `plans/02` records as deferred"
                       r".{0,200}fork to ask",
                       "a deferral resurrection is asked, never silently proceeded on")

    def test_phase2_ADR_conformance_with_supersession_pairing(self):
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)surfaced WITH the ADR citation, never silently dropped",
                       "a contradicting candidate surfaces with its citation")
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)paired with a supersession fork via `/adr`",
                       "recommending a contradiction requires the supersession fork")
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)only sane approach, that IS the fork",
                       "the only-sane-approach case presents rather than dead-ends")

    def test_phase5_review_bullet(self):
        self.assert_on(BRAINSTORMING_COPIES,
                       r"(?i)no criterion that contradicts an accepted ADR",
                       "the Phase 5 mechanical self-review backstops the spec file")


if __name__ == "__main__":
    unittest.main(verbosity=2)
