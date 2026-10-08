#!/usr/bin/env python3
"""SMARTS design-quality integration — structural pins on every SMARTS surface.

SMARTS is a prose contract: the regression mode is a paragraph quietly
reverting to the variance-only framing, a verdict losing its rule, a
scoring shortcut creeping back in, or a workflow applying SMARTS where it
must not. These tests pin order and required text, never the mere presence
of the word SMARTS.

The canonical core (`core/surface/includes/smarts/core.md`):

  1. the role: the six-lens design-quality rubric for material engineering
     solution choices; workflow owners pick the depth; SMARTS grants no
     authority; architectural variance is a consumer, not the definition;
  2. exactly the six acronym lenses, in acronym order;
  3. the five-verdict vocabulary, with Unknown carrying `missing_observation`
     and `decision_critical`, never neutral, never mapped to Indifferent;
  4. single-option Indifferent means "not material", never "no evidence";
  5. the context envelope, every dimension conditional on relevance, no new
     project or configuration file;
  6. the four-step priority order, ending in a tie that stays tied;
  7. the three evaluation depths: scan, comparison, delegated decision;
  8. no aggregate scoring: no counts, weights, sums or percentages.

The consuming surfaces, one class each: the lazy lens reference and its
load condition; brainstorming Phase 2 order and the full-read route form;
the spec rationale convention; the writing-plans design-drift guard; the
`/feature` small-lane scan; `/debug` (no SMARTS in diagnosis) and `/fix`
(remediation strategy only after root cause); refactor's conditional
strategy step; SDD and the authority reviewer's material-invalidation
check; the decision-variance and grader five-verdict vocabulary; and
SPRINT's typed Unknown fields. The host-parity class pins the generated
Claude Code, Codex and Pi projections.

Offline and dependency-free; every test has been proven to die to a mutant
that removes the rule it pins.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = "core/surface/includes/smarts/core.md"
LENSES = ("Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable")
VERDICTS = ("Strong", "Adequate", "Weak", "Indifferent", "Unknown")


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """Body of the `## <heading>` section, up to the next level-2 heading."""
    match = re.search(rf"(?m)^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S)
    if match is None:
        raise AssertionError(f"{CORE}: no '## {heading}' section")
    return match.group(1)


def bullets(body: str) -> list[tuple[str, str]]:
    """(bold name, rest of line) for each top-level `- **Name** ...` bullet."""
    return re.findall(r"(?m)^- \*\*([^*]+)\*\*(.*)$", body)


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TestSmartsCore(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(CORE)

    def test_core_defines_design_quality_role(self):
        intro = flat(self.text[: self.text.index("\n## ")])
        self.assertIn("six-lens design-quality rubric for material engineering solution choices",
                      intro, "the role must be the design-quality rubric")
        self.assertRegex(intro, r"Workflow owners decide when a choice needs a scan, a full "
                                r"comparison, or delegated autonomous handling",
                         "workflow owners, not SMARTS, pick the depth")
        self.assertIn("SMARTS itself does not grant authority", intro)
        self.assertRegex(intro, r"(?i)architectural variance[^.]*\bconsumer\b[^.]*not the definition",
                         "variance must stay a consumer, not the framework's definition")
        self.assertNotRegex(self.text, r"(?i)standardized evaluation for architectural variances",
                            "the variance-only definition must not return")
        self.assertLess(self.text.index("design-quality rubric"), self.text.index("## Step 0"),
                        "the role is stated before Step 0")

    def test_core_keeps_six_lenses_exactly(self):
        names = tuple(name for name, _ in bullets(section(self.text, "The six lenses")))
        self.assertEqual(names, LENSES, "exactly the six acronym lenses, in acronym order")
        self.assertRegex(flat(self.text), r"\*\*non-SMARTS considerations\*\*[^.]*never become a "
                                          r"seventh lens", "business factors never become a lens")

    def test_core_vocabulary_has_unknown_with_fields(self):
        body = section(self.text, "Verdicts")
        self.assertEqual(tuple(name for name, _ in bullets(body)), VERDICTS,
                         "exactly five verdicts, in order")
        unknown = flat(dict(bullets(body))["Unknown"])
        self.assertRegex(unknown, r"missing, contradictory or not yet established")
        self.assertIn("`missing_observation`", unknown)
        self.assertIn("`decision_critical`", unknown)
        self.assertRegex(unknown, r"no other verdict carries (those|these) fields")
        prose = flat(body)
        self.assertRegex(prose, r"`Unknown` is not neutral: never treat it as `Indifferent`, "
                                r"`Adequate` or a pass")
        self.assertRegex(prose, r"decision-critical Unknown blocks a `strong` recommendation, "
                                r"blocks selecting the option that carries it")
        self.assertRegex(prose, r"non-critical Unknown never shields a dominated option")
        self.assertRegex(prose, r"no better than the other option's verdict on that lens, and strictly worse "
                                r"than a compared `Strong`")
        rules = flat(section(self.text, "Cell rules"))
        self.assertRegex(rules, r"`Strong`.*`Adequate`.*`Weak`.*`Indifferent`.*`Unknown`",
                         "verdict-first must admit all five verdict words")
        self.assertRegex(rules, r"If genuinely uncertain, the verdict is `Unknown`",
                         "uncertainty routes to Unknown")
        self.assertNotRegex(rules, r"If genuinely uncertain, the verdict is `Indifferent`",
                            "uncertainty must never route to Indifferent")
        strength = flat(section(self.text, "Strength of recommendation"))
        self.assertRegex(strength, r"\*\*strong\*\*[^\n]*no option carries a decision-critical Unknown")

    def test_core_defines_single_option_indifferent(self):
        indifferent = flat(dict(bullets(section(self.text, "Verdicts")))["Indifferent"])
        self.assertRegex(indifferent, r"If any option marks a lens `Indifferent`, every option marks it "
                                      r"`Indifferent`", "Indifferent is uniform across options")
        self.assertRegex(indifferent, r"In a single-option scan[^.]*nothing to differentiate[^.]*"
                                      r"not material to this choice")
        self.assertRegex(indifferent, r"a lens that matters but lacks evidence is `Unknown`, "
                                      r"never `Indifferent`")

    def test_core_context_envelope_is_conditional(self):
        body = section(self.text, "Context envelope")
        dims = bullets(body)
        self.assertEqual([name for name, _ in dims],
                         ["decision", "scope/horizon", "scale expectation",
                          "failure/availability expectation", "security/trust boundary",
                          "non-SMARTS constraints"], "the six envelope dimensions, in order")
        for name, rest in dims:
            with self.subTest(dimension=name):
                self.assertRegex(rest, r"\b(only )?when\b",
                                 f"envelope dimension '{name}' must be conditional on relevance")
                self.assertNotRegex(rest, r"(?i)\b(always|required|mandatory|must|every choice)\b",
                                    f"envelope dimension '{name}' must never be made unconditional")
        prose = flat(body)
        self.assertIn("No dimension is required for every choice", prose)
        self.assertRegex(prose, r"creates no new project or configuration file")
        self.assertNotRegex(body, r"\.(json|ya?ml|toml|ini)\b|\bconfig(uration)?/",
                            "the envelope must not reference a configuration file")
        self.assertLess(self.text.index("## Step 0"), self.text.index("## Context envelope"))
        self.assertLess(self.text.index("## Context envelope"), self.text.index("## The six lenses"),
                        "the envelope is established before any lens is judged")

    def test_core_priority_order_and_tie(self):
        body = section(self.text, "Conflicting lenses")
        steps = re.findall(r"(?m)^\d\. (.+)$", body)
        self.assertEqual(len(steps), 4, "exactly four priority steps")
        self.assertRegex(steps[0], r"explicit current user or approved-spec priority")
        self.assertRegex(steps[1], r"explicit project priority already recorded")
        self.assertRegex(steps[2], r"prior-decision precedent, labelled as precedent, not authority")
        self.assertRegex(steps[3], r"no assumed priority")
        tie = flat(body).find("Absent explicit priority evidence, a tied comparison stays tied")
        self.assertGreater(tie, -1, "a tie without explicit priority evidence stays tied")
        self.assertGreater(tie, flat(body).find("no assumed priority"), "the tie rule closes the order")

    def test_core_names_three_depths(self):
        body = section(self.text, "Evaluation depths")
        steps = re.findall(r"(?m)^\d\. \*\*([^*]+)\*\*(.+)$", body)
        self.assertEqual([name for name, _ in steps], ["Scan", "Comparison", "Delegated decision"])
        self.assertRegex(steps[0][1], r"lightweight six-lens fitness pass")
        self.assertRegex(steps[1][1], r"two or more materially plausible approaches")
        self.assertRegex(steps[1][1], r"explicitly asks for a full SMARTS read")
        self.assertRegex(steps[2][1], r"approved `/sprint`")
        self.assertRegex(flat(body), r"differ in presentation, persistence and decision authority, "
                                     r"not in what the acronym means")
        self.assertLess(self.text.index("## Evaluation depths"), self.text.index("## Step 0"))

    def test_core_has_no_aggregate_scoring(self):
        body = section(self.text, "Conflicting lenses")
        rule = re.search(r"SMARTS stays qualitative:[^\n]*\n?", body)
        self.assertIsNotNone(rule, "the qualitative rule must be stated")
        self.assertRegex(rule.group(0), r"never count `?Strong`? cells, assign weights, sum,? or "
                                        r"compute percentages")
        self.assertRegex(flat(body), r"ordinal comparison, not a score")
        rest = self.text.replace(rule.group(0), "")
        for pattern in (r"\d+\s*(%|percent|points?\b)", r"(?i)\bweight(s|ed|ing)?\b",
                        r"(?i)\b(sum|tally|tallies|total)\b", r"(?i)\bcount(s|ed|ing)?\b",
                        r"(?i)\b(most|more|fewer)\s+(`?Strong`?|`?Weak`?)\s+(cells|verdicts)\b",
                        r"(?i)\bmajority\b", r"(?i)\b(most|more|fewer)\s+(of the\s+)?lenses\b",
                        r"(?i)\bwins?\s+(on\s+)?(the\s+)?(most|majority)\b"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(rest, pattern, "no winner arithmetic outside the prohibition")


LENS_REFERENCE = "core/surface/includes/smarts/lenses.md"
# Surfaces injected at every session start or prompt: the safety core, each
# mode body, and the hooks that inject them.
STARTUP_SURFACES = (
    "core/surface/includes/safety-core.md",
    "core/surface/arbiter.md",
    "core/surface/includes/dangerous-mode.md",
    "core/surface/includes/ops-mode.md",
    "core/pysrc/session-start.py",
    "core/pysrc/prompt-submit.py",
)


class TestSmartsLensReference(unittest.TestCase):
    def test_lens_reference_carries_historical_detail(self):
        text = read(LENS_REFERENCE)
        names = re.findall(r"(?m)^## (\w+)$", text)
        self.assertEqual(tuple(names), LENSES, "one section per lens, in acronym order")
        for name in LENSES:
            with self.subTest(lens=name):
                body = section(text, name)
                for label in ("**Question:**", "**Considerations:**", "**Traps:**", "**Settles an Unknown:**"):
                    self.assertIn(label, body, f"{name} lacks {label}")
                considerations = body[body.index("**Considerations:**"):body.index("**Traps:**")]
                self.assertGreaterEqual(len(re.findall(r"(?m)^- ", considerations)), 4,
                                        f"{name} must carry the original framework's considerations")
        prose = flat(text)
        for trap in ("confusing performance (one request is fast) with scalability",
                     "conflating availability with high availability",
                     "bolting security on after the architecture is set",
                     "assuming the database or framework handles it without checking"):
            self.assertIn(trap, prose, "the historical traps are retained")
        self.assertNotRegex(prose, r"(?i)uncertain[^.]*`?Indifferent`?",
                            "the reference must not route uncertainty to Indifferent")

    def test_lens_reference_is_loaded_only_on_condition(self):
        core = read(CORE)
        sentences = [s for s in re.split(r"(?<=[.;])\s+", flat(core)) if "lenses.md" in s]
        self.assertTrue(sentences, "core.md must point to the lazy lens reference")
        for sentence in sentences:
            with self.subTest(sentence=sentence[:80]):
                self.assertRegex(sentence, r"\bonly when\b",
                                 "every lens-reference pointer must state its load condition")
        self.assertRegex(flat(core), r"never for a routine scan",
                         "a routine scan must not load the lens reference")
        self.assertRegex(flat(read(LENS_REFERENCE)), r"Load it only under the condition `core\.md` states")

    def test_no_startup_surface_references_lens_reference(self):
        for rel in STARTUP_SURFACES:
            with self.subTest(surface=rel):
                self.assertTrue((REPO / rel).is_file(), f"{rel}: startup surface moved; update this list")
                self.assertNotRegex(read(rel), r"lenses\.md|smarts/lenses",
                                    f"{rel} is loaded at startup and must not pull the lens reference")


BRAINSTORMING = "core/surface/skills/brainstorming/SKILL.md"


def phase_two(text: str) -> str:
    match = re.search(r"(?ms)^## Phase 2 — Shape the approach[^\n]*\n(.*?)(?=^## )", text)
    if match is None:
        raise AssertionError(f"{BRAINSTORMING}: no Phase 2 section")
    return match.group(1)


def smarts_step(text: str) -> str:
    """The Phase 2 bullet that runs the SMARTS pass."""
    match = re.search(r"(?m)^\d\. \*\*Run the SMARTS pass\.\*\*.*$", phase_two(text))
    if match is None:
        raise AssertionError(f"{BRAINSTORMING}: Phase 2 has no SMARTS pass bullet")
    return match.group(0)


class TestSmartsBrainstorming(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(BRAINSTORMING)
        self.phase = phase_two(self.text)

    def test_brainstorming_orders_smarts_before_selection(self):
        steps = re.findall(r"(?m)^(\d)\. \*\*([^*]+)\*\*", self.phase)
        self.assertEqual([name for _, name in steps],
                         ["Bound the context.", "Run the SMARTS pass.", "Surface non-SMARTS constraints.",
                          "Select under existing authority.", "Record the rationale."],
                         "Phase 2 orders context, SMARTS, constraints, selection, rationale")
        self.assertEqual([n for n, _ in steps], ["1", "2", "3", "4", "5"])
        prose = flat(self.phase)
        self.assertRegex(prose, r"Run the SMARTS pass\.\*\*[^.]*`\{\{PLUGIN_ROOT\}\}/includes/smarts/core\.md`",
                         "the SMARTS step cites the canonical core")
        self.assertRegex(prose, r"comparison when two or more materially plausible approaches exist")
        self.assertRegex(prose, r"Record the rationale\.\*\*[^.]*running notes[^.]*`SEC-SMARTS`",
                         "the rationale seeds the spec's SMARTS section")
        self.assertLess(prose.index("Run the SMARTS pass."), prose.index("Select under existing authority."))

    def test_brainstorming_allows_single_option_scan(self):
        prose = flat(self.phase)
        self.assertRegex(prose, r"one-option fitness scan[^.]*states why no alternative was credible",
                         "a single credible approach still gets a stated-reason scan")
        self.assertRegex(prose, r"\*\*Never manufacture alternatives\.\*\*",
                         "manufactured alternatives stay forbidden")

    def test_full_read_changes_presentation_only(self):
        prose = flat(self.phase)
        self.assertRegex(prose, r"explicit request for a full SMARTS read changes only the presentation depth[^.]*"
                                r"no new command[^.]*no change to decision authority")
        for rel in (BRAINSTORMING, CORE, "core/surface/command-routes.json", "core/surface/COMMANDS.md"):
            with self.subTest(surface=rel):
                self.assertNotRegex(read(rel), r"(?<![\w/])/smarts\b(?!/)", f"{rel}: no SMARTS command route")
        # The registry and catalog spell routes as bare keys and `{{CMD:name}}`,
        # not as slash text, so pin those forms too.
        import json
        registry = json.loads(read("core/surface/command-routes.json"))["commands"]
        self.assertEqual([name for name in registry if "smarts" in name.lower()], [],
                         "no SMARTS key in the route registry")
        self.assertNotRegex(read("core/surface/COMMANDS.md"), r"(?i)\{\{CMD:[^}]*smarts[^}]*\}\}",
                            "no SMARTS row in the command catalog")
        commands = sorted((REPO / "core/surface/commands").glob("*"))
        self.assertTrue(commands, "the command directory moved; update this check")
        self.assertEqual([p.name for p in commands if "smarts" in p.name.lower()], [],
                         "no SMARTS command file")

    def test_brainstorming_smarts_step_dispatches_nothing(self):
        step = flat(smarts_step(self.text))
        self.assertRegex(step, r"inline", "the SMARTS pass runs inline")
        self.assertRegex(step, r"dispatches no grader or scout")
        self.assertRegex(step, r"no bulk read of `plans/` or `decisions/`")
        self.assertRegex(step, r"`\{\{PLUGIN_ROOT\}\}/includes/smarts/lenses\.md` only when",
                         "the lens reference loads only on a stated condition")
        self.assertNotRegex(re.sub(r"dispatches no grader or scout", "", step),
                            r"(?i)\b(dispatch|grader|scout|subagent)\b", "the step names no dispatch")


ARTIFACTS = "core/surface/includes/artifacts.md"
RATIONALE_PARTS = ("alternatives considered or the single-option statement", "decisive lenses",
                   "material Weak and Unknown observations", "load-bearing assumptions",
                   "non-SMARTS considerations", "priority evidence")


class TestSmartsRationaleConvention(unittest.TestCase):
    def test_rationale_convention_documented_once(self):
        body = flat(section(read(CORE), "Design rationale record"))
        self.assertRegex(body, r"`approach` record \(`choice`, `tradeoff`\)")
        self.assertRegex(body, r"`decisions` record[^.]*`approach\.binding_decision_refs` cites it")
        self.assertRegex(body, r"one `sections` record with the fixed id `SEC-SMARTS` \(title \"SMARTS design rationale\"\)")
        positions = [body.find(part) for part in RATIONALE_PARTS]
        self.assertNotIn(-1, positions, "every rationale part is named")
        self.assertEqual(positions, sorted(positions), "rationale parts appear in the documented order")
        self.assertRegex(body, r"existing mutation operations[^.]*no spec-schema change")
        self.assertRegex(body, r"never hand-edit or parse rendered HTML")
        self.assertRegex(body, r"design evidence, not a source of execution authority")
        pointer = flat(read(ARTIFACTS))
        self.assertRegex(pointer, r"SMARTS design rationale[^.]*`approach`[^.]*`decisions`[^.]*`SEC-SMARTS`[^.]*"
                                  r"`\{\{PLUGIN_ROOT\}\}/includes/smarts/core\.md`",
                         "artifacts.md points at the one definition")
        for rel in (ARTIFACTS, BRAINSTORMING):
            with self.subTest(copy=rel):
                text = flat(read(rel))
                self.assertLess(sum(part in text for part in RATIONALE_PARTS), 3,
                                f"{rel} must point at the convention, not restate it")

    def test_markdown_rationale_section_documented(self):
        body = flat(section(read(CORE), "Design rationale record"))
        self.assertRegex(body, r"legacy Markdown spec[^.]*one stable `## SMARTS design rationale` section")
        self.assertRegex(body, r"`## SMARTS design rationale` section[^.]*same parts")
        self.assertRegex(flat(read(ARTIFACTS)), r"Markdown spec[^.]*`## SMARTS design rationale`")


WRITING_PLANS = "core/surface/skills/writing-plans/SKILL.md"


def phase(text: str, number: int, rel: str) -> str:
    """Body of the `## Phase <number>` section, up to the next level-2 heading."""
    match = re.search(rf"(?ms)^## Phase {number} [^\n]*\n(.*?)(?=^## )", text)
    if match is None:
        raise AssertionError(f"{rel}: no Phase {number} section")
    return match.group(1)


def drift_guard(text: str) -> str:
    match = re.search(r"(?m)^\*\*Design-drift guard\.\*\*.*(?:\n(?!\n).*)*", text)
    if match is None:
        raise AssertionError(f"{WRITING_PLANS}: no design-drift guard paragraph")
    return match.group(0)


class TestSmartsWritingPlans(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(WRITING_PLANS)

    def test_writing_plans_has_no_smarts_scoring(self):
        guard = drift_guard(self.text)
        self.assertRegex(flat(guard), r"never pick, score or SMARTS-evaluate it here",
                         "the guard forbids scoring inside planning")
        rule = re.search(r"(?m)^- MUST NOT score[^\n]*", self.text)
        self.assertIsNotNone(rule, "a hard rule forbids SMARTS scoring in planning")
        rest = self.text.replace(guard, "").replace(rule.group(0), "")
        for pattern in (r"SMARTS", r"`(Strong|Adequate|Weak|Indifferent|Unknown)`",
                        r"(?i)\blens(es)?\b", r"(?i)\b(score|grade|rate)s? (each|the|every) "
                                              r"(task|approach|option)"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(rest, pattern, "writing-plans runs no SMARTS scoring step")

    def test_writing_plans_drift_guard_routes_back(self):
        decomposition = phase(self.text, 2, WRITING_PLANS)
        guard = drift_guard(self.text)
        self.assertIn(guard, decomposition, "the guard sits in task decomposition")
        self.assertLess(decomposition.index(guard), decomposition.index("Gate:"),
                        "the guard runs before the decomposition gate closes")
        prose = flat(guard)
        self.assertRegex(prose, r"material solution choice the approved spec does not decide")
        self.assertRegex(prose, r"STOP[^.]*never pick")
        self.assertRegex(prose, r"[Rr]oute the undecided choice back to the owning design workflow[^.]*"
                                r"`brainstorming`")
        self.assertRegex(prose, r"resume planning only once the spec records the decision")
        self.assertRegex(prose, r"not drift", "decided or trivial choices are not drift")


FEATURE = "core/surface/commands/feature.md"


def small_lane_smarts(text: str) -> str:
    match = re.search(r"(?m)^\*\*Small-lane SMARTS\.\*\*.*(?:\n(?!\n).*)*", text)
    if match is None:
        raise AssertionError(f"{FEATURE}: no small-lane SMARTS paragraph")
    return match.group(0)


class TestSmartsSmallLane(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(FEATURE)
        self.step = small_lane_smarts(self.text)
        self.prose = flat(self.step)

    def test_small_lane_scans_only_material_choice(self):
        criteria = self.text.index("- the behavior change is expressible as 1–3 concrete")
        confirm = self.text.index("**Small lane:** state the mini-spec inline")
        position = self.text.index(self.step)
        self.assertLess(criteria, position, "the scan follows the small-lane criteria")
        self.assertLess(position, confirm, "the scan result is stated before the mini-spec confirmation")
        self.assertRegex(self.prose, r"Only when the change involves a material solution choice[^.]*"
                                     r"run a SMARTS scan[^.]*`\{\{PLUGIN_ROOT\}\}/includes/smarts/core\.md`",
                         "the scan is conditional on a material choice")
        self.assertRegex(self.prose, r"inline[^.]*no grader or scout",
                         "the small-lane scan dispatches nothing")
        self.assertRegex(self.prose, r"If the scan shows that the better approach would violate any small-lane "
                                     r"criterion above, route to the \*\*full lane\*\*",
                         "a criterion-breaking approach routes to the full lane")
        self.assertNotRegex(self.prose, r"(?i)\b(always|every small-lane change) (runs?|gets?) a SMARTS",
                            "the scan is never unconditional")

    def test_small_lane_no_choice_adds_no_table(self):
        self.assertRegex(self.prose, r"[Oo]therwise state `SMARTS: no material solution choice`")
        self.assertRegex(self.prose, r"`SMARTS: no material solution choice`[^.]*no SMARTS table and no extra "
                                     r"artifact", "the no-choice path adds nothing")
        lane = self.text[self.text.index("**Small lane:**"):self.text.index("## Flow — full lane")]
        self.assertNotRegex(lane, r"\| *Lens *\|", "the small lane carries no SMARTS table")


DEBUG = "core/surface/skills/debug/SKILL.md"
FIX = "core/surface/commands/fix.md"
SMARTS_TERMS = (r"SMARTS", r"`(Strong|Adequate|Weak|Indifferent|Unknown)`", r"(?i)\blens(es)?\b")


class TestSmartsDebugFix(unittest.TestCase):
    def test_debug_has_no_smarts_in_diagnosis(self):
        text = read(DEBUG)
        for number in (2, 3, 4):
            body = phase(text, number, DEBUG)
            for pattern in SMARTS_TERMS:
                with self.subTest(phase=number, pattern=pattern):
                    self.assertNotRegex(body, pattern, "hypothesis ranking and root-cause confirmation stay "
                                                       "evidence-led")
        rule = re.search(r"(?m)^- MUST NOT apply SMARTS[^\n]*", text)
        self.assertIsNotNone(rule, "a hard rule keeps SMARTS out of diagnosis")
        self.assertRegex(rule.group(0), r"hypothesis ranking or root-cause confirmation[^.]*evidence-led[^.]*"
                                        r"remediation strategy[^.]*`/fix` after root cause")

    def test_fix_applies_smarts_after_root_cause_only(self):
        text = read(FIX)
        match = re.search(r"(?m)^\*\*Remediation strategy \(conditional\)\.\*\*.*(?:\n(?!\n).*)*", text)
        self.assertIsNotNone(match, "fix.md has a conditional remediation-strategy step")
        step = flat(match.group(0))
        self.assertLess(text.index("2. **Locate the root cause**"), text.index(match.group(0)),
                        "SMARTS runs only after the root cause is located")
        self.assertLess(text.index(match.group(0)), text.index("minimal fix to green"),
                        "the strategy is chosen before fix code")
        self.assertRegex(step, r"Only after step 2 has confirmed the root cause, and only when materially "
                               r"distinct remediation strategies exist")
        self.assertRegex(step, r"SMARTS comparison[^.]*`\{\{PLUGIN_ROOT\}\}/includes/smarts/core\.md`[^.]*inline")
        self.assertRegex(step, r"single obvious fix gets no SMARTS table")
        self.assertRegex(step, r"never ranks hypotheses or confirms the cause")
        before = text[:text.index(match.group(0))]
        self.assertNotRegex(before, r"SMARTS", "no SMARTS before root cause")


REFACTOR = "core/surface/skills/refactor/SKILL.md"
# The parity and coverage gate sentences, pinned verbatim: the refactor trigger
# must add a strategy step without weakening any of them.
REFACTOR_GATES = (
    "Gate: surface coverage at or above the maturity threshold on every required metric in the declared "
    "coverage profile, the shared critical-path evidence present, AND every public method backed by a direct "
    "test. Otherwise backfill via `tdd` Phase 1 before retrying.",
    "Gate: scoped parity tests green with zero pre-existing tests modified. BLOCK if any pre-existing test was "
    "modified to pass, or if any applicable test fails; the branch still MUST NOT merge until exhaustive "
    "exact-head hosted CI passes.",
    "Gate: clean lint and type-check, zero errors, and no coverage regression on the named surface.",
    "Every public method in the surface table MUST have at least one direct test",
    "Each MUST pass with NO modification to its source",
)


class TestSmartsRefactor(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(REFACTOR)

    def test_refactor_smarts_only_for_distinct_strategies(self):
        match = re.search(r"(?m)^\*\*Strategy choice \(conditional\)\.\*\*.*(?:\n(?!\n).*)*", self.text)
        self.assertIsNotNone(match, "refactor has a conditional strategy step")
        step = flat(match.group(0))
        implementation = phase(self.text, 4, REFACTOR)
        self.assertIn(match.group(0), implementation, "the strategy step sits in implementation")
        self.assertLess(implementation.index(match.group(0)), implementation.index("Apply the restructure"),
                        "the strategy is chosen before any edit")
        self.assertRegex(step, r"Only when materially distinct restructuring strategies exist")
        self.assertRegex(step, r"after the Phase 1 surface table and the Phase 2 parity proof are settled")
        self.assertRegex(step, r"SMARTS comparison[^.]*`\{\{PLUGIN_ROOT\}\}/includes/smarts/core\.md`[^.]*inline")
        self.assertRegex(step, r"never widens the surface table or relaxes a parity or coverage gate")
        self.assertRegex(step, r"One evident strategy gets no SMARTS table")
        before = self.text[:self.text.index(match.group(0))]
        self.assertNotRegex(before, r"SMARTS", "no SMARTS before surface and parity are known")

    def test_refactor_parity_gate_text_unchanged(self):
        prose = flat(self.text)
        for gate in REFACTOR_GATES:
            with self.subTest(gate=gate[:50]):
                self.assertIn(gate, prose, "the refactor parity and coverage gates are unchanged")


SDD = "core/surface/skills/subagent-driven-development/SKILL.md"
AUTHORITY_REVIEWER = "core/surface/agents/authority-reviewer.md"
INVALIDATION = (r"a load-bearing assumption the change contradicts",
                r"a `Weak` or `Unknown` the rationale chose to avoid that the change newly introduces",
                r"a materially different approach than the one selected")


class TestSmartsImplementationDrift(unittest.TestCase):
    def test_spec_compliance_checks_material_invalidation_only(self):
        body = phase(read(SDD), 3, SDD)
        match = re.search(r"(?m)^- \*\*Design-rationale drift\.\*\*.*(?:\n  .*)*", body)
        self.assertIsNotNone(match, "Phase 3 checks the recorded SMARTS rationale")
        step = flat(match.group(0))
        self.assertLess(body.index(match.group(0)), body.index("Gate:"), "the check runs before the gate")
        self.assertRegex(step, r"`SEC-SMARTS`[^.]*`## SMARTS design rationale`")
        self.assertRegex(step, r"material invalidation only")
        for clause in INVALIDATION:
            with self.subTest(clause=clause):
                self.assertRegex(step, clause)
        self.assertRegex(step, r"[Dd]o not re-run SMARTS or grade the implementation")
        self.assertRegex(step, r"returns the task to Phase 2[^.]*or routes the design question back to "
                               r"`brainstorming`", "a mismatch routes back")
        self.assertRegex(step, r"never pick a replacement approach inside review")

    def test_authority_reviewer_reads_smarts_rationale(self):
        text = read(AUTHORITY_REVIEWER)
        match = re.search(r"(?m)^- When the frozen context includes an approved spec's SMARTS design "
                          r"rationale.*(?:\n  .*)*", text)
        self.assertIsNotNone(match, "the reviewer checks recorded rationale")
        rule = flat(match.group(0))
        self.assertRegex(rule, r"material invalidation only")
        for clause in INVALIDATION:
            with self.subTest(clause=clause):
                self.assertRegex(rule, clause.replace("the change", "the target"))
        self.assertRegex(rule, r"`BLOCK` finding that routes the task back")
        self.assertRegex(rule, r"never propose or choose a replacement approach")
        self.assertRegex(text.split("---")[1], r"(?m)^tools: Read, Grep, Glob$", "the reviewer stays read-only")
        agents = sorted((REPO / "core/surface/agents").glob("*.md"))
        self.assertTrue(agents, "the agents directory moved; update this check")
        self.assertEqual([p.name for p in agents if "smarts" in p.name.lower()], [], "no new SMARTS agent")


ANALYSIS = "core/surface/skills/decision-variance/references/analysis.md"
GRADER = "core/surface/agents/grader.md"


class TestSmartsArbitrationVocabulary(unittest.TestCase):
    def test_arbitration_surfaces_use_five_state_vocabulary(self):
        four = r"Strong\W+Adequate\W+Weak\W+(or\W+)?Indifferent(?!\W+(or\W+)?Unknown)"
        five = r"Strong\W+Adequate\W+Weak\W+Indifferent\W+(or\W+)?Unknown"
        for rel in (ANALYSIS, GRADER):
            text = read(rel)
            with self.subTest(surface=rel):
                self.assertNotRegex(text, four, f"{rel}: no four-verdict list remains")
                self.assertRegex(text, five, f"{rel}: the five verdicts are listed in order")
                prose = flat(text)
                self.assertRegex(prose, r"`Unknown` cell names its `missing_observation` and states whether it "
                                        r"is `decision_critical`", f"{rel}: the missing-observation rule")
                self.assertRegex(prose, r"never `Indifferent` for missing evidence",
                                 f"{rel}: missing evidence is never Indifferent")
        grader = flat(read(GRADER))
        self.assertRegex(grader, r"\*\*strong\*\* — [^.]*no option carries a decision-critical `Unknown`",
                         "a decision-critical Unknown blocks a strong recommendation")
        self.assertRegex(grader, r"Every cell starts with verdict word \(Strong/Adequate/Weak/Indifferent/Unknown\)")


SPRINT = "core/surface/SPRINT.md"


def typed_authority(text: str) -> str:
    match = re.search(r"(?ms)^### Typed SMARTS method authority\n(.*?)(?=^### )", text)
    if match is None:
        raise AssertionError(f"{SPRINT}: no typed SMARTS method authority section")
    return match.group(1)


class TestSmartsSprint(unittest.TestCase):
    def setUp(self) -> None:
        self.section = flat(typed_authority(read(SPRINT)))

    def test_sprint_teaches_unknown_fields(self):
        self.assertRegex(self.section, r"Each six-lens cell carries one of the five verdicts")
        self.assertRegex(self.section, r"An `Unknown` cell must carry `missing_observation`[^.]*and "
                                       r"`decision_critical`")
        self.assertRegex(self.section, r"those two fields appear on no other verdict")
        self.assertRegex(self.section, r"refuses a selected option that carries a decision-critical `Unknown`[^.]*"
                                       r"`strong` strength while any option carries one")

    def test_sprint_unknown_cannot_bypass_hard_gate(self):
        self.assertRegex(self.section, r"An `Unknown` cannot bypass a hard gate or manufacture authority")
        self.assertRegex(self.section, r"never stands in for user approval, a prerequisite or security authority")
        self.assertRegex(self.section, r"named Hard gates below stay true stops")


# Canonical surface -> its generated projection on each host. Claude Code keeps
# skills/, commands/ and agents/; Codex and Pi project skills to routines/ and
# commands to skills/ca-<name>/. The authority reviewer is Claude Code only.
HOST_COPIES = {
    CORE: ("plugins/ca/includes/smarts/core.md", "plugins/ca-codex/includes/smarts/core.md",
           "plugins/ca-pi/includes/smarts/core.md"),
    LENS_REFERENCE: ("plugins/ca/includes/smarts/lenses.md", "plugins/ca-codex/includes/smarts/lenses.md",
                     "plugins/ca-pi/includes/smarts/lenses.md"),
    BRAINSTORMING: ("plugins/ca/skills/brainstorming/SKILL.md", "plugins/ca-codex/routines/brainstorming/SKILL.md",
                    "plugins/ca-pi/routines/brainstorming/SKILL.md"),
    WRITING_PLANS: ("plugins/ca/skills/writing-plans/SKILL.md", "plugins/ca-codex/routines/writing-plans/SKILL.md",
                    "plugins/ca-pi/routines/writing-plans/SKILL.md"),
    FEATURE: ("plugins/ca/commands/feature.md", "plugins/ca-codex/skills/ca-feature/SKILL.md",
              "plugins/ca-pi/skills/ca-feature/SKILL.md"),
    FIX: ("plugins/ca/commands/fix.md", "plugins/ca-codex/skills/ca-fix/SKILL.md",
          "plugins/ca-pi/skills/ca-fix/SKILL.md"),
    DEBUG: ("plugins/ca/skills/debug/SKILL.md", "plugins/ca-codex/routines/debug/SKILL.md",
            "plugins/ca-pi/routines/debug/SKILL.md"),
    REFACTOR: ("plugins/ca/skills/refactor/SKILL.md", "plugins/ca-codex/routines/refactor/SKILL.md",
               "plugins/ca-pi/routines/refactor/SKILL.md"),
    SDD: ("plugins/ca/skills/subagent-driven-development/SKILL.md",
          "plugins/ca-codex/routines/subagent-driven-development/SKILL.md",
          "plugins/ca-pi/routines/subagent-driven-development/SKILL.md"),
    AUTHORITY_REVIEWER: ("plugins/ca/agents/authority-reviewer.md",),
    ANALYSIS: ("plugins/ca/skills/decision-variance/references/analysis.md",
               "plugins/ca-codex/routines/decision-variance/references/analysis.md",
               "plugins/ca-pi/routines/decision-variance/references/analysis.md"),
    GRADER: ("plugins/ca/agents/grader.md", "plugins/ca-codex/agents/grader.md", "plugins/ca-pi/agents/grader.md"),
    SPRINT: ("plugins/ca/SPRINT.md", "plugins/ca-codex/SPRINT.md", "plugins/ca-pi/SPRINT.md"),
}

# One load-bearing trigger or vocabulary sentence per surface, chosen free of
# host placeholders so the canonical and generated text must agree verbatim.
HOST_PINS = {
    CORE: ("SMARTS is codeArbiter's six-lens design-quality rubric for material engineering solution choices.",
           "**Unknown** — the evidence needed to judge the lens is missing, contradictory or not yet established.",
           "and strictly worse than a compared `Strong`."),
    LENS_REFERENCE: ("**Settles an Unknown:**",),
    BRAINSTORMING: ("2. **Run the SMARTS pass.**",),
    WRITING_PLANS: ("**Design-drift guard.**",),
    FEATURE: ("**Small-lane SMARTS.**", "SMARTS: no material solution choice"),
    FIX: ("**Remediation strategy (conditional).**",),
    DEBUG: ("MUST NOT apply SMARTS to hypothesis ranking or root-cause confirmation",),
    REFACTOR: ("**Strategy choice (conditional).**", "One evident strategy gets no SMARTS table."),
    SDD: ("**Design-rationale drift.**",),
    AUTHORITY_REVIEWER: ("never propose or choose a replacement approach, and never re-grade the lenses",),
    ANALYSIS: ("never `Indifferent` for missing evidence",),
    GRADER: ("never `Indifferent` for missing evidence",),
    SPRINT: ("An `Unknown` cannot bypass a hard gate or manufacture authority",),
}


class TestSmartsHostParity(unittest.TestCase):
    def test_all_hosts_carry_trigger_and_vocabulary(self):
        self.assertEqual(set(HOST_COPIES), set(HOST_PINS), "every pinned surface has a host map")
        for canonical, pins in HOST_PINS.items():
            for rel in (canonical, *HOST_COPIES[canonical]):
                with self.subTest(copy=rel):
                    self.assertTrue((REPO / rel).is_file(), f"{rel}: projection missing")
                    text = flat(read(rel))
                    for pin in pins:
                        self.assertIn(flat(pin), text, f"{rel}: lost {pin[:60]!r}")

    def test_generated_writing_plans_runs_no_rescore(self):
        # T-17 pins the canonical writing-plans; the projections must not
        # reintroduce a recorded-intent rescore either.
        for rel in HOST_COPIES[WRITING_PLANS]:
            text = read(rel)
            for pattern in (r"Step 0", r"(?i)recorded[- ]intent", r"intent: (per|silent)", r"ADR-0025",
                            r"(?i)re-?scor"):
                with self.subTest(copy=rel, pattern=pattern):
                    self.assertNotRegex(text, pattern, f"{rel} runs no recorded-intent rescore")


if __name__ == "__main__":
    unittest.main()
