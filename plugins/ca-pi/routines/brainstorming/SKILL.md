---
name: brainstorming
description: Refine feature and sprint intent into a useful specification. Capture scope, observable criteria and material choices without repeated artifact approval ceremonies.
disable-model-invocation: true
---

# brainstorming

Refine the agreed outcome before implementation. This is intent clarification and specification authoring, not a second permission system. The feature or sprint request is the initial authorization; ask about consequential choices not already answered, not whether an artifact may exist.

## Format and caller

For new full-lane work or an existing HTML pair, load `<plugin-root>/includes/artifacts.md` and select the actual source via `_select_authoring_route`. New full-lane specs use the pinned native engine and canonical HTML; existing Markdown keeps its representation. Do not write or regex-edit HTML, create a Markdown shadow, or claim a failed artifact write succeeded. HTML farm remains disabled.

The calling feature or sprint owns scope and the next step. A sprint may include several related features under one coherent goal. A small inline feature remains the caller's mini-spec lane. Specification authoring itself does not grant commit, publication, override, provider spending, or irreversible-operation authority.

Use relevant CONTEXT.md, tech-stack.md and security-controls.md when present. Read an existing open-questions document and relevant ADR/plan headings index-first. Missing optional historical indices are not blockers. Preserve real decisions while distinguishing an accepted decision from implemented or released behavior.

## Phase 1 - Frame

State the problem, observable result, intended scope and explicit exclusions. Respect what the user already requested. If a record conflicts with new intent, identify the material decision and which work it affects; do not automatically create another approval round for ordinary method choices.

## Phase 2 - Select a viable approach

Consider genuine trade-offs where they matter, recommend a suitable approach and explain why. Do not manufacture straw alternatives. Reversible implementation methods remain agent-owned within the agreed outcome. Ask for a user ruling on an unresolved, consequential product choice, not on every viable implementation detail.

Review applicable ADRs and explicit exclusions. A real conflicting architecture decision goes to its owner. Mentioning a protected file does not by itself restart the entire feature interview.

## Phase 3 - Make acceptance observable

Turn intended scope into specific criteria: input or trigger, expected behavior, and relevant failure/boundary condition. Check integration risks and ask: **if every criterion passed, what would still be broken?** For complex or issue-backed work, a bounded `_intentlib.py uncovered-intent` inspection can catch uncited requirements. It is not a mandatory permission gate for every small change.

Choose sensible defaults and record material parameters. Do not create CONFIRM placeholders for normal method choices. A consequential unresolved requirement warrants one clear user question; independent work may proceed if that decision affects only part of the plan. Do not repeatedly ask the same question merely because an artifact was revised.

## Phase 4 - Write the spec

Create or update the route-selected spec with: problem, chosen approach and rationale, included/excluded scope, meaningful parameters, observable acceptance criteria, and actual open decisions. For HTML use typed `create` and `apply`, stable criterion IDs, current CAS, and symbol-scoped readback; never edit embedded HTML/JSON directly. Existing Markdown remains on the legacy path without automatic conversion. Do not invent a command, test, source, approval or result.

Drafts may be incomplete. `validate` with `gate: ready` identifies missing coverage and structure. Diagnostics help complete the plan; they are not a reason to prohibit independent authorized investigation. A conflicting write or structural failure still prevents claiming the artifact was saved. A ready spec is not proof of implementation.

## Phase 5 - Self-review and handoff

Read back the saved specification. Check consistency, alignment with the user's request, exclusions, and ability to verify. Identify a plausible failure mode or say none was found. Proportion the review to risk rather than mandating an adversarial committee.

For full-lane feature or sprint work, return the selected spec identity, normative digest, criteria, and genuinely open decisions directly to `writing-plans` (`<plugin-root>/routines/writing-plans/SKILL.md`). The caller maintains its ordering; do not skip a useful plan to reach implementation. An existing spec should resume at its actual unfinished step, not restart an interview.

**Do not demand separate spec approval or `arm-sprint`/`sprint-approve` merely to progress.** An explicitly requested human review pause and real user-owned decisions still apply. Historical paired approval, producer capture or SMARTS grant remains historical; do not fabricate a receipt. In-scope method updates during work are typed plan maintenance, not another permission interview.

## Hard boundaries

Never broaden the requested outcome, ignore a genuine host denial or user stop, manufacture verification evidence, silently change representation, or claim a saved/verified state without observing it. Preserve source integrity and independently applicable security controls. Avoid interviews for already-answered or agent-owned choices.
