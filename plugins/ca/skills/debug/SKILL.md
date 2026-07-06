---
name: debug
description: Investigate-then-decide root-cause analysis for a defect whose cause is unknown (distinct from /fix, which assumes a known bug). Five gated phases: capture, hypothesize, gather, decide, hand off. Investigation only, no code changes; exits to /fix, /adr, or a no-action close.
---

# debug

Find the cause first, fix it never. `debug` investigates and routes; it does not touch code. It drives one closed loop — **reproduce** (Phase 1) → confirm by cited evidence (Phases 2–3) → hand `/fix` a regression test that re-runs the repro and must pass (**verify**). The minimal repro is the anchor that closes the loop; code changes belong to `/fix`.

## Pre-flight

Read these, or STOP and surface the gap — never guess a log path, trace tool, or test runner:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — log paths, trace tooling, test runner conventions. The evidence sources.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — domain vocabulary, system structure, and the `stage:` frontmatter (the maturity value; higher demands more rigorous evidence before exit).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — only when the symptom touches a security boundary (auth, crypto, secrets). Optional; absent on most defects.

The user MUST supply at least a one-sentence symptom. If absent, ask for one — do not guess the symptom.

## Phase 1 — Symptom capture · gate: BLOCK

Record the symptom with enough fidelity that another operator reproduces it without further questions:

- **Observed** — one sentence: what the system did. Not the suspected cause; causes belong to Phase 2.
- **Expected** — one sentence. If the user cannot state expected behavior, that itself may be a design/behavior ambiguity — flag it for Phase 4.
- **Minimal repro** — exact command/request/action, required input and state, environment (local/staging/prod/test) and maturity value, frequency (every time / intermittent / one-time).
- **Evidence in hand** — error messages, stack traces, log excerpts; cite the source of each (log path + timestamp, request ID).

If no minimal repro exists, derive one with the user before continuing. An intermittent issue still has a trigger condition (an input pattern, a load condition, a timing window) — capture that.

Gate: a minimal repro, or a documented intermittent-trigger profile. A symptom without one cannot be debugged, only speculated about. Every piece of evidence MUST cite its source.

## Phase 2 — Hypothesis generation · gate: BLOCK

Produce at least three distinct candidate causes, ranked by likelihood, before gathering any evidence against them. Distinct means different subsystems, mechanisms, or failure modes — not three rewordings of one suspicion.

For each candidate write: a one-sentence hypothesis, the subsystem/boundary involved, and the mechanism by which it produces the observed symptom. Number them H1, H2, H3… for Phase 3.

Rank by recency of relevant changes (recent commits to the suspect subsystem raise rank), symptom specificity (a symptom pointing narrowly at one mechanism raises it), and historical pattern.

Include at least one **boring** hypothesis — environmental drift, dependency version change, config mismatch, stale cache, operator error. List it even if ranked last. Confirmation bias toward exotic causes is the recurring debug failure mode.

Gate: three or more distinct hypotheses, one of them boring. Single-hypothesis lock-in is the single most common cause of misdiagnosis — the gate forces breadth before depth.

## Phase 3 — Evidence gathering · gate: BLOCK

For each hypothesis, identify what would confirm or refute it, then gather that evidence by reading existing artifacts only. No code is modified in this phase.

For each H1…HN write the CONFIRM signal, the REFUTE signal, and the source where each lives (log file, trace tool, commit range, metric dashboard). Then read:

- Application logs and traces at the paths/tools in `tech-stack.md`.
- Recent commits (`git log`, `git diff`) on suspect paths.
- Configuration, environment variables, feature flags (read-only).

Annotate each hypothesis CONFIRMED, REFUTED, or INCONCLUSIVE, with a cited source. Do not collapse INCONCLUSIVE to CONFIRMED or REFUTED by inference — state what additional evidence is needed and where it lives. New hypotheses that emerge are added and gathered against; Phase 2 is a floor, not a ceiling.

Gate: no code change of any kind — no edit, no refactor, no "try a fix." A hypothesis testable only by changing code becomes a Phase 4 finding (exit (a), with a regression test obligation), not a change here. No INCONCLUSIVE evidence promoted to CONFIRMED without a cited source.

## Phase 4 — Root-cause decision · gate: BLOCK

Walk the evidence ledger and pick exactly one exit. "We'll figure it out later" is not an exit.

- **(a) Confirmed bug → `/fix`.** One hypothesis is CONFIRMED by cited evidence and the disposition is a code change. Carry: the hypothesis ID and statement, the cited confirming evidence, and a named **regression test obligation** — a one-sentence description of the test `/fix` MUST write (and watch fail) before any fix code. It MUST encode the Phase 1 minimal repro, so the exact condition that reproduced the defect becomes the test that proves it fixed — this is what closes the reproduce→fix→verify loop. `/fix` refuses to proceed without it.
- **(b) Behavior/design ambiguity → `/adr`.** The system behaves as currently specified, but the specification itself is in question. Carry: the hypothesis ID and statement, a one-sentence statement of the ambiguity, and the symptom record plus evidence ledger as context. An ADR is authored only via `/adr` with explicit user attribution — surface the question to the user and obtain attribution; never author the ADR autonomously as the disposition of a debug session.
- **(c) No-action close.** The symptom is non-reproducible, was a one-time environmental event, or was already resolved by an unrelated commit. Carry: a one-sentence rationale, the cited evidence supporting "no action," and a note appended to the symptom record.

If a finding is real but out of scope for any of the three exits, mark it inline with `[NEEDS-TRIAGE]` and continue — do not stall on it.

If no exit can be chosen — all hypotheses INCONCLUSIVE — loop back to Phase 3 for more evidence, or take exit (b) and surface the open question. "No decision" is not a valid exit.

Gate: exactly one of (a) / (b) / (c) is named, with its full carry set. No exit closes on "more investigation needed" without either looping to Phase 3 or selecting (b).

## Phase 5 — Handoff · gate: BLOCK

Emit a summary downstream skills can consume without re-reading the session, then route:

- **Summary block:** symptom (one sentence), reproduction profile, hypotheses considered (count + one-line list), evidence ledger summary (CONFIRMED / REFUTED / INCONCLUSIVE per hypothesis), the Phase 4 exit and rationale, and the handoff target.
- **Exit (a):** route to `/fix` with the Phase 4 carry set. The orchestrator routes `/fix` to the `tdd` skill in bug-fix variant, where the carried test obligation becomes the Phase 1 obligation that must fail before fix code. `debug` does not pre-write the test.
- **Exit (b):** route to `/adr` with the Phase 4 carry set attached as context.
- **Exit (c):** append a schema-conformant queued entry to `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md` (the format the SessionStart hook and statusline parse — see the `OPEN_TASKS` scaffold note): a top-level `- [ ] <symptom> (logged YYYY-MM-DD)` line, with the "no action" rationale as an indented `- Desc:` sub-bullet. A dotted ID is optional for a debug note. This keeps the note in the in-flight count as an open item to revisit, rather than a bare bullet that drifts from the schema. No further handoff.

Surface the summary and the handoff to the user before the skill exits.

Gate: the handoff is routed. Exit (c) is recorded before close.

## Hard rules

- MUST NOT modify, refactor, or "try a fix" on any code during Phases 1–5. Code changes belong to `/fix`.
- MUST NOT proceed past Phase 1 without a minimal repro or a documented intermittent-trigger profile.
- MUST NOT promote INCONCLUSIVE evidence to CONFIRMED or REFUTED without a cited source.
- MUST cite the source of every piece of evidence — log path + timestamp, commit SHA, trace ID.
- MUST NOT route to `/fix` for a bug not yet confirmed by cited evidence — `/fix` is for known bugs.
- MUST NOT exit (a) without a named regression test obligation tied to the Phase 1 minimal repro — the repro-encoding test is what closes the loop.
- MUST NOT author an ADR autonomously — exit (b) routes through `/adr` with user attribution.
- MUST NOT guess a log path, trace tool, or test command — read `tech-stack.md` or STOP.
