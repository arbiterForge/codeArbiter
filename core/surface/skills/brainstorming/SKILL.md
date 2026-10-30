---
name: brainstorming
description: Refine feature and sprint intent into a useful specification. Capture scope, observable criteria and material choices without repeated artifact approval ceremonies.
disable-model-invocation: true
---

# brainstorming

Refine the agreed outcome before implementation. This is intent clarification and specification authoring, not a second permission system. The feature or sprint request is the initial authorization; ask about consequential choices not already answered, not whether an artifact may exist.

## Format and caller

For artifact I/O, load `{{PLUGIN_ROOT}}/includes/artifacts.md` and select the source with `_select_authoring_route`. Retain that source identity through specification authoring.

The calling feature or sprint owns scope and the next step. A sprint may include several related features under one coherent goal. A small inline feature remains the caller's mini-spec lane. Specification authoring itself does not grant commit, publication, override, provider spending, or irreversible-operation authority.

Use relevant CONTEXT.md, tech-stack.md and security-controls.md when present; in an HTML-knowledge repository use `knowledge.py relevant <paths>` and the greenfield decomposition records instead (see `{{PLUGIN_ROOT}}/includes/knowledge.md`). Read an existing open-questions document and relevant ADR/plan headings index-first. Missing optional historical indices are not blockers. Preserve real decisions while distinguishing an accepted decision from implemented or released behavior.

When the request selects an existing work ID, first read it through the
selected owner with `work.py context <work_id>` as described in the knowledge
include. Reuse its exact spec/plan bindings and stated intent; inspect the
current source and ask only about consequential gaps. A same-title item is not
an identity match, and a work context is not evidence that attached checks ran.

## Recorded intent and consequential conflicts

Use an index-first recorded-intent read to avoid asking about settled choices.
This pre-flight is exempt from the read-or-STOP rule when optional project
history is absent: **intent: silent — no decomposition record**. Do not
manufacture a plan or an approval to fill that gap.

If a proposed solution resurrects a capability `plans/02` records as deferred,
identify the original reason and any stated re-evaluation trigger, then fork to ask
only when the *outcome* would materially change. An explicit current owner steer
can settle that fork; an ordinary implementation detail cannot silently reverse
a recorded deferral.

A candidate that contradicts an accepted ADR must be **surfaced WITH the ADR
citation, never silently dropped**. A recommended outcome change is paired with
a supersession fork via `/adr` instead of pretending the old decision never
existed. If the contradiction is the only sane approach, that IS the fork:
show the choice and consequence to the owner once, respecting an already
recorded superseding instruction. A referenced ADR is not a new permission
token for safe, in-scope investigation or implementation.

## Phase 1 - Frame

State the problem, observable result, intended scope and explicit exclusions. Respect what the user already requested. If a record conflicts with new intent, identify the material decision and which work it affects; do not automatically create another approval round for ordinary method choices.

## Phase 2 - Select a viable approach

Consider genuine trade-offs where they matter, recommend a suitable approach and explain why. Do not manufacture straw alternatives. Reversible implementation methods remain agent-owned within the agreed outcome. Ask for a user ruling on an unresolved, consequential product choice, not on every viable implementation detail.

**Never manufacture alternatives.** When only one sane approach exists, say so in one line and say why; that path runs no SMARTS comparison and adds no SMARTS table.

**SMARTS on a material choice.** Only when two or more materially plausible approaches exist, run a SMARTS comparison per `{{PLUGIN_ROOT}}/includes/smarts/core.md` inline before recommending one. Bound it to the context-envelope dimensions that could differentiate the approaches, mark missing evidence `Unknown` with its missing observation, and surface a decision-critical `Unknown` before selecting. If every candidate carries one, pause the selection until the missing observation is resolved or the user rules. The comparison dispatches no grader or scout, performs no bulk read of `plans/` or `decisions/`, and loads `{{PLUGIN_ROOT}}/includes/smarts/lenses.md` only when a verdict turns on a consideration the core summaries do not settle. Name cost, schedule, team-skill, vendor or stakeholder constraints alongside the result; they never become a seventh lens. Apply the core's priority order when lenses conflict; a tie without explicit priority evidence goes to the user. An explicit request for a full SMARTS read changes only the presentation depth — the full option-by-option table — with no new command and no change to decision authority.

**Record the rationale.** When the comparison ran, write the decisive lenses, any `Unknown` with its missing observation, the non-SMARTS constraints and the selection reason into the spec's `SEC-SMARTS` section, or the `## SMARTS design rationale` section of a Markdown spec. A single-approach choice records only its one-line statement there.

Review applicable ADRs and explicit exclusions. A real conflicting architecture decision goes to its owner. Mentioning a protected file does not by itself restart the entire feature interview.

## Phase 3 - Make acceptance observable

Turn intended scope into specific criteria: input or trigger, expected behavior, and relevant failure/boundary condition. Check integration risks and ask: **if every criterion passed, what would still be broken?** For meaningful behavior changes, plan one or more focused tests against the actual obligation; do not create tests solely to clear an artifact gate. For complex or issue-backed work, a bounded `_intentlib.py uncovered-intent` inspection can catch uncited requirements. It is not a mandatory permission gate for every small change.

Choose sensible defaults and record material parameters. Do not create CONFIRM placeholders for normal method choices. A consequential unresolved requirement warrants one clear user question; independent work may proceed if that decision affects only part of the plan. Do not repeatedly ask the same question merely because an artifact was revised.

## Phase 4 - Write the spec

Create or update the route-selected spec with: problem, chosen approach and rationale, included/excluded scope, meaningful parameters, observable acceptance criteria, and actual open decisions. For HTML use typed `create` and `apply`, stable criterion IDs, current CAS, and symbol-scoped readback; never edit embedded HTML/JSON directly. Existing Markdown remains on the legacy path without automatic conversion. Do not invent a command, test, source, approval or result.

Drafts may be incomplete. `validate` with `gate: ready` identifies missing coverage and structure. Diagnostics help complete the plan; they are not a reason to prohibit independent authorized investigation. A conflicting write or structural failure still prevents claiming the artifact was saved. A ready spec is not proof of implementation.

## Phase 5 - Self-review and handoff

Read back the saved specification. Check consistency, alignment with the user's request, exclusions, and ability to verify: no criterion that contradicts an accepted ADR without an explicitly resolved, source-visible owner decision. Identify a plausible failure mode or say none was found. Proportion the review to risk rather than mandating an adversarial committee.

For full-lane feature or sprint work, return the selected spec identity, normative digest, criteria, and genuinely open decisions directly to `writing-plans` (`{{PLUGIN_ROOT}}/skills/writing-plans/SKILL.md`). The caller maintains its ordering; do not skip a useful plan to reach implementation. An existing spec should resume at its actual unfinished step, not restart an interview.

**Do not demand separate spec approval or `arm-sprint`/`sprint-approve` merely to progress.** An explicitly requested human review pause and real user-owned decisions still apply. Historical paired approval, producer capture or SMARTS grant remains historical; do not fabricate a receipt. In-scope method updates during work are typed plan maintenance, not another permission interview.

## Hard boundaries

Never broaden the requested outcome, ignore a genuine host denial or user stop, manufacture verification evidence, silently change representation, or claim a saved/verified state without observing it. Preserve source integrity and independently applicable security controls. Avoid interviews for already-answered or agent-owned choices.
