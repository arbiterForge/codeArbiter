---
name: debug
description: Investigate-then-decide root-cause analysis (RCA) workflow for situations where the cause of a defect, anomaly, or unexpected behavior is unknown. Routes to /fix, /ticket, /adr, or no-action close at Phase 4. Distinct from /fix, which assumes a known bug.
---

<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: SKILL.md
-->


# Skill: debug

## Purpose

The `debug` skill encodes a disciplined investigate-then-decide root-cause analysis (RCA) workflow.
It exists for one situation: **the cause of an observed defect, anomaly, or unexpected behavior is
not yet known.** The skill captures the symptom, generates multiple competing hypotheses, gathers
evidence without modifying code, and then forces an explicit exit decision — either a confirmed
bug handed to `/fix`, a design/behavior ambiguity escalated to `/ticket` or `/adr`, or a no-action
close with recorded findings.

The skill is a deliberate counterweight to premature implementation. It MUST NOT modify code. Code
changes belong to `/fix`, and `/fix` is only reached after `debug` has named a confirmed bug and a
regression test obligation.

---

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Conditions that route work to `debug`:

- A user reports an observed defect, anomaly, or unexpected behavior whose cause is unknown.
- A user invokes `/debug` (or a wrapper command that routes to this skill).
- A reviewer agent, a CI gate, or another skill surfaces an unexplained failure that does not yet
  meet the precondition for `/fix` (which requires a known bug and a stated regression test
  obligation).
- The user describes the situation with phrasing such as "I don't know what's wrong yet," "it
  used to work," "something is off but I can't pin it down," or any equivalent ambiguity signal.

Do NOT route to `debug` when:

- The bug is already known and a regression test is already named. Route to `/fix` directly.
- The user wants a design discussion with no failing behavior in hand. Route to `/adr` or
  `/ticket` directly.
- The user wants implementation of a new feature. Route to the `tdd` skill via `/feature`.

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` is readable — stop if missing. The skill needs to know
   the project's log paths, trace tooling, and test runner conventions before it can gather
   evidence.
2. `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` is readable — stop if missing. Audit events are a primary
   evidence source for RCA on auditable actions.
3. Current stage is known — read `cat ${PROJECT_ROOT}/.agents/projectContext/stage`. Stage influences how much
   evidence the skill requires before exiting (higher stages demand more rigorous evidence).
4. The invoking user has provided at least a one-sentence symptom statement. If not, ask for one
   before proceeding. Do not guess at the symptom.

If any file is missing or any check fails, surface the gap and stop. Do not guess at log paths,
trace tooling, or audit event field names.

---

## Phase 1: Symptom Capture

**Goal:** Record the observed symptom with enough fidelity that a different operator could
reproduce the situation without further questions.

**Inputs:**
- The user's symptom description
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — environment and runtime conventions
- Current stage (from Pre-Flight)

**Actions:**

1. Record the observed symptom in one sentence. State what the system did, not what the user
   thinks caused it. Causes belong to Phase 2.
2. Record the expected behavior in one sentence. If the user cannot state expected behavior, this
   may itself be a sign that the issue is a design/behavior ambiguity (flag for Phase 4).
3. Record the minimal reproduction steps:
   - Exact command, request, or user action
   - Input data, parameters, or state required
   - Environment (local, staging, production, test) and stage (1–4)
   - Frequency (every time / intermittent / one-time observation)
4. Record observable evidence already in hand: error messages, stack traces, screenshots, log
   excerpts. Cite source (log path, timestamp, request ID) for each.
5. If no minimal reproduction exists, attempt to derive one with the user before proceeding. An
   intermittent issue may have a minimal repro that triggers it reliably (e.g., a specific input
   pattern, a load condition, a timing window). Capture that.

**Output:** Symptom record with: observed behavior, expected behavior, minimal repro steps,
environment, stage, and cited evidence in hand.

**Gate:** BLOCK on no minimal repro. A symptom without a reproduction (or at least a reliable
trigger condition for intermittent issues) cannot be debugged — it can only be speculated about.
MUST NOT proceed to Phase 2 without a minimal repro or a documented intermittent-trigger profile.
MUST cite the source of every piece of evidence captured.

---

## Phase 2: Hypothesis Generation

**Goal:** Produce at least three candidate causes ranked by likelihood, before any evidence is
gathered against them.

**Inputs:**
- Symptom record from Phase 1
- `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` — domain vocabulary and system structure
- Recent commit log (read-only) — surface candidate recent changes

**Actions:**

1. Generate at least three distinct candidate causes for the symptom. Distinctness means the
   hypotheses point at different subsystems, mechanisms, or failure modes — not three rewordings
   of the same suspicion.
2. For each candidate, write:
   - A one-sentence hypothesis statement
   - The subsystem, component, or boundary involved
   - The mechanism by which the hypothesis would produce the observed symptom
3. Rank the candidates by likelihood (most likely first). Use:
   - Recency of relevant changes (recent commits to the suspect subsystem raise rank)
   - Specificity of the symptom (a symptom that points narrowly at one mechanism raises that rank)
   - Historical pattern (recurring issue types in this project raise rank)
4. Explicitly include at least one "boring" hypothesis — environmental drift, dependency version
   change, configuration mismatch, stale cache, or operator error. The boring hypothesis MUST be
   listed even if it is ranked last. Confirmation bias toward exotic causes is a recurring debug
   failure mode.
5. Number the hypotheses H1, H2, H3, … for reference in Phase 3.

**Output:** Ranked hypothesis list, three or more entries, each with statement, subsystem,
mechanism, and rank rationale.

**Gate:** BLOCK on single-hypothesis lock-in. MUST NOT proceed to Phase 3 with fewer than three
distinct hypotheses. MUST NOT proceed with three hypotheses that are reworded versions of one
suspicion. Single-hypothesis lock-in is the single most common cause of misdiagnosis; the gate
exists to force breadth before depth.

---

## Phase 3: Evidence Gathering

**Goal:** For each hypothesis, identify what evidence would confirm or refute it, then gather that
evidence by reading existing artifacts only. No code is modified in this phase.

**Inputs:**
- Hypothesis list from Phase 2
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` — audit event field definitions and sink paths
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — log paths, trace tooling, test runner conventions
- Git history (read-only)
- Application logs, traces, audit event records, metrics dashboards

**Actions:**

1. For each hypothesis H1…HN, write:
   - The evidence that would CONFIRM it (positive signal)
   - The evidence that would REFUTE it (negative signal)
   - The source where that evidence lives (log file, trace tool, audit sink, commit range, metric
     dashboard)
2. Gather the evidence by reading:
   - Application logs at the paths defined in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`
   - Traces from the trace tool defined in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`
   - Audit events from the sink defined in `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`
   - Recent commits (`git log`, `git diff`) on suspect paths
   - Configuration files, environment variables, and feature flags (read-only)
3. Record evidence findings against each hypothesis: CONFIRMED, REFUTED, or INCONCLUSIVE.
4. If evidence is INCONCLUSIVE for a hypothesis, state what additional evidence would be needed
   and where it would live. Do not collapse INCONCLUSIVE to CONFIRMED or REFUTED by inference.
5. If new hypotheses emerge during evidence gathering, add them to the list and gather evidence
   for them too. Phase 2 is a floor, not a ceiling.

**Output:** Evidence ledger: each hypothesis annotated with CONFIRMED, REFUTED, or INCONCLUSIVE,
with cited evidence source for each annotation.

**Gate:** BLOCK on any code change. MUST NOT modify, refactor, "try a fix," or otherwise alter
production or test code during this phase. Code changes belong to `/fix`, not `/debug`. If a
hypothesis can only be tested by changing code, that becomes a finding for Phase 4 disposition
(typically Phase 4 exit (a) with a stated regression test obligation). BLOCK on collapsing
INCONCLUSIVE evidence to CONFIRMED without a cited source.

---

## Phase 4: Root Cause Decision

**Goal:** Pick exactly one exit. No "we'll figure it out later." The skill does not end without a
named disposition.

**Inputs:**
- Symptom record from Phase 1
- Hypothesis list from Phase 2
- Evidence ledger from Phase 3

**Actions:**

1. Walk the evidence ledger. Identify whether the evidence supports one of three exits:

   - **(a) Confirmed bug.** One hypothesis is CONFIRMED by cited evidence and the disposition is
     a code change. Required output:
     - The hypothesis ID and statement (e.g., "H2: stale cache returns prior tenant's record")
     - The cited confirming evidence
     - A named regression test obligation: a one-sentence description of the test that MUST be
       written by `/fix` before the fix code is written. This is a hard requirement — `/fix`
       refuses to proceed without it.
     - The `/fix` invocation handoff payload (see Phase 5)

   - **(b) Behavior/design ambiguity.** The evidence shows the system behaves as currently
     specified, but the specified behavior is itself in question. Required output:
     - The hypothesis ID and statement
     - Whether the disposition is `/ticket` (open work item, no decision yet) or `/adr`
       (architectural decision required)
     - A one-sentence statement of the ambiguity to be resolved
     - Routing choice rationale (why ticket vs. ADR)

   - **(c) No-action close.** The evidence shows the symptom is not reproducible, was a one-time
     environmental event, has already been fixed by an unrelated commit, or otherwise requires no
     follow-up. Required output:
     - A one-sentence statement of why no action is needed
     - The cited evidence supporting "no action"
     - A note added to the symptom record for future reference

2. If no exit can be chosen — e.g., all hypotheses are INCONCLUSIVE — the correct response is to
   loop back to Phase 3 and gather more evidence, or to escalate to Phase 4 exit (b) (`/ticket`)
   with the symptom recorded for later revisit. "No decision" is not a valid Phase 4 exit.

3. Record the chosen exit (a / b / c) and the rationale.

**Output:** A single named Phase 4 exit — (a), (b), or (c) — with the required payload for that
exit.

**Gate:** BLOCK on no-decision. Phase 4 MUST exit with one of (a) / (b) / (c). MUST NOT exit with
"more investigation needed" without either (i) looping back to Phase 3 for additional evidence, or
(ii) selecting exit (b) and opening a `/ticket` to track the open question. MUST NOT exit with (a)
without a named regression test obligation. MUST NOT exit with (b) without choosing between
`/ticket` and `/adr` and stating the rationale.

---

## Phase 5: Handoff

**Goal:** Route the chosen exit and emit a summary that downstream skills and commands can consume
without re-reading the entire debug session.

**Inputs:**
- Phase 4 exit selection and payload

**Actions:**

1. Emit a debug summary block with:
   - Symptom (one sentence from Phase 1)
   - Reproduction profile (minimal repro or intermittent-trigger profile)
   - Hypotheses considered (count and one-line list)
   - Evidence ledger summary (which hypothesis was CONFIRMED / REFUTED / INCONCLUSIVE)
   - Phase 4 exit selection and rationale
   - Handoff target (`/fix`, `/ticket`, `/adr`, or no-action close)

2. Execute the handoff:
   - **Exit (a) — `/fix`:** Emit a `/fix` invocation that includes the confirmed bug statement,
     the cited evidence, and the named regression test obligation. The orchestrator routes the
     `/fix` invocation to the `tdd` skill in bug-fix variant.
   - **Exit (b) — `/ticket` or `/adr`:** Emit the chosen invocation with the ambiguity statement,
     the symptom record, and the evidence ledger attached as context. The orchestrator routes
     accordingly.
   - **Exit (c) — no-action close:** Append the symptom record and "no action" rationale to
     `${PROJECT_ROOT}/.agents/projectContext/debug-log.md` (create if missing) for future reference. No further
     handoff.

3. Surface the summary block and handoff to the user. Confirm the handoff before the skill exits.

**Output:** Debug summary block emitted; handoff routed; skill exits.

**Gate:** BLOCK if exit is (a) and no regression test obligation is named. The `/fix` invocation
MUST carry an explicit regression test obligation — `/fix` refuses to proceed without one, so
omitting it here would simply stall downstream. MUST NOT bypass the handoff. MUST NOT close the
skill in exit (c) without recording the symptom and rationale to the debug log.

---

## Hard Rules

- MUST NOT modify code during Phases 1–3. Code changes belong to `/fix`, not `/debug`.
- MUST NOT proceed past Phase 1 without a minimal reproduction (or a documented intermittent-
  trigger profile for non-reproducible cases).
- MUST NOT proceed past Phase 2 with fewer than three distinct hypotheses. Single-hypothesis lock-
  in is a blocking violation.
- MUST NOT collapse INCONCLUSIVE evidence to CONFIRMED or REFUTED without a cited source.
- MUST NOT exit Phase 4 without selecting one of (a) confirmed bug → `/fix`, (b) ambiguity →
  `/ticket` or `/adr`, or (c) no-action close.
- MUST NOT exit with (a) without naming a regression test obligation that `/fix` will carry into
  its TDD Phase 1.
- MUST NOT route to `/fix` for situations where the bug is not yet confirmed by cited evidence —
  `/fix` is for known bugs.
- MUST NOT guess at log paths, trace tooling, or audit field names — always read
  `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` and `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`.
- MUST cite the source of every piece of evidence (log path + timestamp, commit SHA, audit event
  ID, trace ID).
- MUST include at least one "boring" environmental / configuration / dependency hypothesis in
  Phase 2 to counter confirmation bias toward exotic causes.

---

## Decision Gates Summary

| Gate         | Condition                                                              | Action if blocked                                               |
|--------------|------------------------------------------------------------------------|-----------------------------------------------------------------|
| Phase 1 exit | No minimal repro (or no intermittent-trigger profile)                  | Stop; derive a repro with the user before continuing            |
| Phase 2 exit | Fewer than three distinct hypotheses, or single-hypothesis lock-in     | Stop; generate additional distinct hypotheses                   |
| Phase 3 exit | Any code modification attempted, or INCONCLUSIVE collapsed to CONFIRMED | Stop; revert any change; re-gather cited evidence              |
| Phase 4 exit | No exit chosen, or exit (a) without regression test obligation         | Stop; loop back to Phase 3 or select (b); name regression test  |
| Phase 5 exit | Handoff not routed, or exit (c) not recorded to debug log              | Stop; complete the handoff or record the no-action close        |

---

## Interactions with other skills

The `debug` skill is a router-into-other-skills by design. Phase 4 exits compose with downstream
commands as follows:

- **Exit (a) → `/fix`.** The `/fix` command requires a known bug and a stated regression test
  obligation. `debug` Phase 4 exit (a) produces exactly that payload: confirmed bug statement,
  cited evidence, named regression test. The `/fix` command then routes to the `tdd` skill in
  bug-fix variant, where the named regression test becomes the Phase 1 obligation that must fail
  before any fix code is written. `debug` does NOT pre-implement the regression test — `/fix`'s
  TDD Phase 2 owns that.

- **Exit (b) → `/ticket`.** When the evidence shows correct-as-specified behavior with an
  ambiguous specification, the work is to clarify the specification, not to change code. `/ticket`
  opens an item for triage. The full symptom record and evidence ledger are attached as ticket
  context so the triage agent does not re-debug from scratch.

- **Exit (b) → `/adr`.** When the ambiguity is architectural — a trade-off between competing
  designs, a trust-boundary question, a cross-component contract — the disposition is an ADR, not
  a ticket. `/adr` is authored only with explicit user attribution (per AGENTS.md §3). `debug`
  Phase 4 surfaces the question to the user and obtains attribution before routing to `/adr`.
  `debug` MUST NOT author an ADR autonomously as the disposition of a debug session.

- **Exit (c) → no-action close.** No downstream skill is invoked. The symptom record and rationale
  are appended to `${PROJECT_ROOT}/.agents/projectContext/debug-log.md`. Future debug sessions that encounter a
  similar symptom may reference the prior close as evidence (cited in Phase 3).

`debug` MUST NOT be invoked from inside `/fix`, `/ticket`, or `/adr` — that would create a routing
cycle. If those skills surface an unknown cause mid-flow, the correct response is to exit them and
re-enter via `/debug`.
