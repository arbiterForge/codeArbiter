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
import importlib.util
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
    assert match, "arbiter.md has no §6 section"
    return match.group(1)


def load_destructive_registry_checker():
    path = REPO / ".github/scripts/check_destructive_registry.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("check_destructive_registry", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DESTRUCTIVE_OPERATIONS = (
    "Logged bypass (`/override`)",
    "Merge to the default branch",
    "Branch or worktree deletion",
    "Release and tag publication",
)


class TestDestructiveOperationRegistry(unittest.TestCase):
    """ADR-0026/0030/0033: registry authority and resident-copy parity."""

    def checker(self):
        checker = load_destructive_registry_checker()
        self.assertIsNotNone(
            checker,
            "missing .github/scripts/check_destructive_registry.py",
        )
        return checker

    def test_current_registry_and_resident_copy_match_exactly_four_operations(self):
        checker = self.checker()
        registry = checker.extract_operations(read("core/surface/includes/routing-table.md"))
        resident = checker.extract_operations(orchestrator_section_six(read("core/surface/arbiter.md")))
        self.assertEqual(registry, DESTRUCTIVE_OPERATIONS)
        self.assertEqual(resident, DESTRUCTIVE_OPERATIONS)
        for rel, text in self._arbiter_surfaces():
            with self.subTest(rel=rel):
                section = orchestrator_section_six(text)
                self.assertIn("compared item-for-item in CI", section)
                self.assertNotIn("byte-compared", section)

    def _arbiter_surfaces(self):
        yield "core/surface/arbiter.md", read("core/surface/arbiter.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/arbiter.md"
            yield rel, read(rel)

    def test_seeded_resident_mismatch_is_rejected(self):
        checker = self.checker()
        registry = checker.render_block(DESTRUCTIVE_OPERATIONS, heading_level=2)
        seeded_resident = checker.render_block(
            DESTRUCTIVE_OPERATIONS[:-1] + ("Publish a package",),
            heading_level=3,
        )
        errors = checker.compare_surfaces(registry, seeded_resident)
        self.assertEqual(len(errors), 1)
        self.assertIn("item-for-item mismatch", errors[0])

    def test_blank_line_cannot_hide_an_additional_destructive_operation(self):
        checker = self.checker()
        registry = checker.render_block(DESTRUCTIVE_OPERATIONS, heading_level=2)
        with_extra = registry.replace(
            "- Release and tag publication\n",
            "- Release and tag publication\n\n- Publish a package\n",
        )
        self.assertEqual(
            checker.extract_operations(with_extra),
            DESTRUCTIVE_OPERATIONS + ("Publish a package",),
        )
        errors = checker.compare_surfaces(registry, with_extra)
        self.assertEqual(len(errors), 1)
        self.assertIn("item-for-item mismatch", errors[0])


class TestSectionSixRoutesRatherThanRedirects(unittest.TestCase):
    """ADR-0022: route on understood intent, in three tiers."""

    def surfaces(self):
        yield "core/surface/arbiter.md", read("core/surface/arbiter.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/arbiter.md"
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
        #
        # ADR-0030 supersedes ADR-0022:46-49 for dangerous-mode entry ONLY: a
        # deterministic `mode --dangerous` token flip is friction, not the gate
        # itself, so dev/dangerous entry no longer belongs to this destructive
        # set (see #437, mode-plane-deterministic-flip). The other four members
        # are untouched by that supersession and MUST stay asserted here:
        # ADR-0022's three-tier decision and its tier-1 dual requirement remain
        # in force for `/ca:override`, a default-branch merge, branch/worktree
        # deletion, and release/tag publication.
        for rel, text in self.surfaces():
            with self.subTest(rel=rel):
                section = orchestrator_section_six(text)
                self.assertRegex(section, r"(?i)separate axes")
                for irreversible in (
                    r"override",                       # the logged bypass
                    r"merge to\s+the default branch",  # irreversible on the shared history
                    r"branch or worktree deletion",    # local data loss
                    r"release and tag publication",    # published, immutable (issue #386)
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


class TestIntentRoutingAndDelegatedMethods(unittest.TestCase):
    """Routing refinement without extra public surface or weaker authority.

    These are cross-host prose-contract checks, not proof of live model routing
    or token savings. Existing ADR, cleanup and destructive-registry tests above
    remain intact; a method choice is not a new user goal or authorization.
    """

    def surfaces(self, relative):
        for prefix in ("core/surface", *(host[0] for host in HOSTS)):
            rel = f"{prefix}/{relative}"
            yield rel, " ".join(read(rel).split())

    def test_explicit_commands_are_optional_not_required_input(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn("Explicit commands are optional entry points", text)
                self.assertNotIn("Every user intent flows through", text)
                self.assertNotIn("All intent flows through", text)
                self.assertIn("not prerequisites for understanding a request", text)

    def test_methods_do_not_create_another_approval_question(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn("Multiple reasonable internal methods are not ambiguous user intent", text)
                self.assertIn("A second plausible route alone is not a reason to ask", text)
                self.assertIn("requested outcome or required authority is missing", text)
                self.assertNotIn("an argument you would have to invent, or a second plausible command", text)

    def test_question_and_draft_only_boundaries_are_resident(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn("Questions are not mutation authority", text)
                self.assertIn("Explain a commit without creating one", text)
                self.assertIn("without staging or committing when asked to draft only", text)
                self.assertIn("read-only evidence gathering", text)
                self.assertIn("do not select a procedure's writing close", text)

    def test_action_questions_are_not_classified_by_punctuation(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn('"can you commit these changes?" can request an action', text)
                self.assertIn("classify the intended outcome and explicit restrictions, not punctuation alone", text)

    def test_direct_handoffs_preserve_wrapper_owned_behavior(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn("arguments, modes, prerequisites, and gates are preserved", text)
                self.assertIn("If the wrapper owns distinct behavior, load it too", text)
                self.assertIn("A description is a discovery hint, never the complete procedure", text)
                self.assertIn("Keep private procedures path-loaded and avoid bulk context reads", text)

    def test_continuation_respects_the_active_call_extent(self):
        for rel, text in self.surfaces("arbiter.md"):
            with self.subTest(rel=rel):
                self.assertIn("return a scoped result, forward a completed authorized stage", text)
                self.assertIn("branch for an allowed prerequisite", text)
                self.assertIn("Neither universal return-to-caller nor unconditional commit-to-PR is correct", text)

    def test_reversible_choice_cannot_grant_its_own_authority(self):
        for rel, text in self.surfaces("includes/safety-core.md"):
            with self.subTest(rel=rel):
                self.assertIn("Within already-authorized scope, choose reversible implementation parameters", text)
                self.assertIn("record material choices where the workflow requires", text)
                self.assertNotIn("has one sensible answer", text)
                self.assertIn("does not grant initial scope approval", text)
                self.assertIn("`[CONFIRM-NN]`", text)
                self.assertIn("expand provider, spending, data-disclosure, or publication authority", text)
                self.assertIn("irreversible-action confirmations above remain mandatory", text)

    def test_redirect_is_not_a_repeat_menu_or_bypass_offer(self):
        for rel, text in self.surfaces("includes/redirect.md"):
            with self.subTest(rel=rel):
                self.assertIn("Do not repeat a command catalog", text)
                self.assertIn("lack of slash syntax is not itself uncertainty", text)
                self.assertIn("A generic approval of a route is not authority", text)
                self.assertIn("never steer the user toward", text)
                self.assertNotIn("Or pick a channel", text)
                self.assertNotIn("Still need a channel", text)
                self.assertNotIn("to proceed anyway", text)
                self.assertIn("this clarification card does not select or activate another mode", text)

    def test_routing_cues_are_not_syntax_or_permission(self):
        for rel, text in self.surfaces("includes/routing-table.md"):
            with self.subTest(rel=rel):
                self.assertIn("Invocation cues are examples, not required user syntax", text)
                self.assertIn("routing never authorizes a bypass", text)
                self.assertIn("Informational requests use read-only behavior, not a writing close", text)

    def test_safety_section_numbers_and_surviving_controls(self):
        for rel, text in self.surfaces("includes/safety-core.md"):
            with self.subTest(rel=rel):
                self.assertEqual(re.findall(r"## §(\d+) —", text), ["2", "3", "5", "6", "7"])
                self.assertIn("MUST NOT store a raw secret", text)
                self.assertIn("MUST NOT write directly to the default branch or force-push", text)
                self.assertIn("MUST NOT author an ADR except via", text)
                self.assertIn("audit logs", text)
                self.assertIn("are append-only", text)
                self.assertIn("A gate that looks wrong is diagnosed, not bypassed", text)
                self.assertIn("--match-head-commit", text)



class TestSprintRecoveryAndLimits(unittest.TestCase):
    """PR843: repair permission is not acceptance, scope, or publication authority."""

    def sprint_surfaces(self):
        yield "core/surface/SPRINT.md", read("core/surface/SPRINT.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/SPRINT.md"
            yield rel, read(rel)

    def engine_surfaces(self):
        yield "core/surface/skills/subagent-driven-development/SKILL.md", read("core/surface/skills/subagent-driven-development/SKILL.md")
        for plugin, skilldir, _, _ in HOSTS:
            rel = f"{plugin}/{skilldir}/subagent-driven-development/SKILL.md"
            yield rel, read(rel)

    def test_failed_quality_blocks_acceptance_not_authorized_repair(self):
        for host, text in self.sprint_surfaces():
            with self.subTest(host=host):
                self.assertIn('A failing unit test', text)
                self.assertIn('another permission question', text)
                self.assertIn('Do not weaken tests', text)


    def test_recovery_reuses_current_typed_authority(self):
        for host, text in self.sprint_surfaces():
            with self.subTest(host=host):
                self.assertIn('task-reconcile', text)
                self.assertIn('same journaled operation ID', text)
                self.assertIn('not rearmed', text)


    def test_identical_failure_changes_strategy_not_user_interview(self):
        for host, text in self.sprint_surfaces():
            with self.subTest(host=host):
                self.assertIn('strategy fails twice', text)
                self.assertIn('continue unrelated eligible work', text)
                self.assertIn('Do not weaken tests', text)


    def test_stopped_strategy_is_persisted_and_excluded_from_selection(self):
        for host, text in self.sprint_surfaces():
            with self.subTest(host=host):
                self.assertIn('mark that task blocked', text)
                self.assertIn('Never erase a user', text)
                self.assertIn('independent', text)


    def test_real_hard_stops_and_commit_permission_survive(self):
        for host, text in self.sprint_surfaces():
            with self.subTest(host=host):
                self.assertIn('explicit user denial', text)
                self.assertIn('host/tool sandbox denial', text)
                self.assertIn('merge to the default branch', text)


    def test_child_calls_parent_recovery_without_auto_passing_gate(self):
        for host, text in self.engine_surfaces():
            with self.subTest(host=host):
                self.assertIn('failing check', text)
                self.assertIn('not permission to claim it passed', text)
                self.assertIn('real `commit-gate` owner', text)
                self.assertIn("not fresh verification", text)


    def test_legacy_dependency_sentence_does_not_override_typed_eligibility(self):
        for host, text in self.engine_surfaces():
            with self.subTest(host=host):
                self.assertIn('actual task dependencies', text)
                self.assertIn('advisory scheduling', text)
                self.assertIn('For Markdown', text)


    def test_scoped_continuation_and_full_plan_proof_remain(self):
        for host, text in self.engine_surfaces():
            with self.subTest(host=host):
                self.assertIn('Scoped invocation', text)
                self.assertIn('Do not call `commit-gate`', text)
                self.assertIn('not release-ready', text)

    def test_scope_continuity_does_not_reask_or_hide_remaining_work(self):
        sprint = read('core/surface/SPRINT.md')
        commit = read('core/surface/skills/commit-gate/SKILL.md')
        finish = read('core/surface/skills/finishing-a-development-branch/SKILL.md')
        self.assertIn('outcome, scope and duration', commit)
        self.assertIn('unrelated preexisting paths', commit)
        self.assertIn('covered delivery actions', sprint)
        self.assertIn('remaining obligations', sprint)
        self.assertIn('explicit earlier merge authority', finish)
        self.assertIn('per-item confirmation', finish)



class TestCallerAwareSpecAndCheckpointContract(unittest.TestCase):
    """PR843: child prose must preserve the caller's scope and delegation.

    These are instruction-contract regressions, not a live-model evaluation.
    Test the operative phase and hard rules, not an unrelated review document.
    """

    def skills(self, name):
        yield "core", read(f"core/surface/skills/{name}/SKILL.md")
        for plugin, routine_dir, _, _ in HOSTS:
            yield plugin, read(f"{plugin}/{routine_dir}/{name}/SKILL.md")

    @staticmethod
    def section(text, heading, next_heading):
        if text.count(heading) != 1 or text.count(next_heading) != 1:
            raise AssertionError(f"Expected one operative section: {heading} -> {next_heading}")
        return text.split(heading, 1)[1].split(next_heading, 1)[0]

    def test_initial_sprint_is_not_its_own_delegation(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('not a second permission system', text)
                self.assertIn('does not grant commit', text)
                self.assertIn('ask about consequential', text)


    def test_sprint_scope_is_not_forced_into_repeated_feature_interviews(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('several related features', text)
                self.assertIn('without repeated', text)
                self.assertIn('the actual', text)


    def test_method_choice_does_not_reintroduce_the_retired_single_answer_rule(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('Reversible implementation', text)
                self.assertIn('Do not manufacture straw', text)
                self.assertIn('consequential', text)


    def test_only_user_owned_unknowns_become_confirmation_requests(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('Do not create CONFIRM placeholders', text)
                self.assertIn('consequential unresolved', text)
                self.assertIn('already-answered', text)


    def test_initial_approval_and_delegated_proof_remain_distinct(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('Do not demand separate spec approval', text)
                self.assertIn('Historical paired approval', text)
                self.assertIn('do not fabricate a receipt', text)


    def test_full_lane_handoff_preserves_plan_before_execution(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('writing-plans', text)
                self.assertIn('do not skip a useful plan', text)
                self.assertIn('return the selected spec identity', text)


    def test_harvest_uses_active_authority_instead_of_an_unconditional_prompt(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('Never broaden', text)
                self.assertIn('independently applicable', text)
                self.assertIn('already-answered', text)


    def test_html_acceptance_partition_is_not_a_task_count_heuristic(self):
        for host, text in self.skills('executing-plans'):
            with self.subTest(host=host):
                self.assertIn('authored checkpoint partition', text)
                self.assertIn('must not split an HTML acceptance scope', text)
                self.assertIn('three-to-five', text)
                self.assertIn('full task-ID set', text)


    def test_checkpoint_meaning_does_not_add_sprint_user_stops(self):
        for host, text in self.skills('executing-plans'):
            with self.subTest(host=host):
                self.assertIn('not a new user checkpoint in `/sprint`', text)
                self.assertIn('directly to `subagent-driven-development`', text)
                self.assertIn('pause is respected', text)



    def test_initial_html_approval_sequence_uses_the_existing_host_adapter(self):
        sources = [('core', read('core/surface/SPRINT.md'))]
        sources.extend((plugin, read(f'{plugin}/SPRINT.md')) for plugin, *_ in HOSTS)
        for host, text in sources:
            with self.subTest(host=host):
                self.assertIn('Do not arm', text)
                self.assertIn('arm-sprint', text)
                self.assertIn('sprint-approve', text)
                self.assertIn('initial request bounds', text)



    def test_missing_typed_approval_producer_is_not_filled_by_scoring(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('A ready spec is not proof', text)
                self.assertIn('do not fabricate a receipt', text)
                self.assertIn('genuine host denial', text)


    def test_write_step_honors_the_selected_format_not_a_new_html_shadow(self):
        for host, text in self.skills('brainstorming'):
            with self.subTest(host=host):
                self.assertIn('HTML', text)
                self.assertIn('includes/artifacts.md', text)
                include = ('core/surface/includes/artifacts.md' if host == 'core'
                           else f'{host}/includes/artifacts.md')
                self.assertIn('silently convert it or create a shadow ledger', read(include))
                self.assertIn('Retain that source identity', text)
                self.assertIn('typed `create`', text)


    def test_blocked_members_cannot_be_dropped_from_an_html_checkpoint(self):
        for host, text in self.skills('executing-plans'):
            with self.subTest(host=host):
                self.assertIn('`BLOCKED` member is still visible', text)
                self.assertIn('cannot silently make the checkpoint complete', text)
                self.assertIn('reasoned `task-reconcile`', text)



if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
