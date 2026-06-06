<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: debug.md
-->

# /debug "symptom description"

## Purpose

Investigate an observed defect, anomaly, or unexpected behavior whose **cause is not yet known**. `/debug` is the disciplined investigate-then-decide root-cause analysis (RCA) workflow. It deliberately separates **investigation** from **implementation**: no code is modified while debugging. The session terminates only at an explicit Phase 4 disposition — confirmed bug routed to `/fix`, ambiguity routed to `/ticket` or `/adr`, or a recorded no-action close.

## Usage

```
/debug "clear description of the observed symptom"
```

The argument must describe the symptom with enough fidelity that a different operator could reproduce the situation: observed behavior, reproduction steps (or intermittent-trigger profile), and environment / stage. Vague descriptions ("it's flaky", "something's off") will be rejected — codeArbiter will ask for clarification before routing.

## Routes To

`debug` skill (`${FRAMEWORK_ROOT}/.agents/skills/debug/SKILL.md`) — all five phases:

1. **Symptom Capture** — record observed vs. expected behavior, minimal repro, environment, evidence in hand.
2. **Hypothesis Generation** — produce at least three distinct ranked candidate causes, including at least one "boring" environmental / configuration / dependency hypothesis.
3. **Evidence Gathering** — read logs, traces, audit events, commits, configuration. No code modification.
4. **Root Cause Decision** — exit to exactly one of:
   - **(a) Confirmed bug** → emit `/fix` invocation carrying the confirmed bug statement, cited evidence, and a named regression test obligation.
   - **(b) Behavior / design ambiguity** → emit `/ticket` (open work item) or `/adr` (architectural decision, with user attribution) with the symptom record and evidence ledger attached.
   - **(c) No-action close** → record symptom and rationale to `${PROJECT_ROOT}/.agents/projectContext/debug-log.md`.
5. **Handoff** — emit summary block and route the chosen exit.

## Phase Gates (hard stops)

- **Phase 1** BLOCKs on no minimal repro (or no documented intermittent-trigger profile).
- **Phase 2** BLOCKs on fewer than three distinct hypotheses, or single-hypothesis lock-in.
- **Phase 3** BLOCKs on **any code modification** — code changes belong to `/fix`, not `/debug`. Also BLOCKs on collapsing INCONCLUSIVE evidence to CONFIRMED without a cited source.
- **Phase 4** BLOCKs on no-decision. MUST exit with one of (a), (b), or (c).
- **Phase 5** BLOCKs if exit (a) is selected but no regression test obligation is named — `/fix` refuses to proceed without one.

## Distinction from /fix

- `/fix` requires a **known bug** with a regression test obligation stated up front. It writes code.
- `/debug` is for **"I don't know what's wrong yet."** It writes no code. Its job is to produce the payload that `/fix` (or `/ticket` / `/adr`) needs in order to begin.

If the cause is already known and a regression test is already named, skip `/debug` and invoke `/fix` directly. If you start in `/debug` and Phase 4 lands on exit (a), `/debug` will emit the `/fix` invocation for you.

## Example invocations

- `/debug "intermittent 502 on /api/users during peak hours, started ~3 days ago"`
- `/debug "test suite passes locally but fails on CI runner — auth fixture test only"`
- `/debug "memory usage on the worker pod climbs without bound after ~6h uptime"`
- `/debug "users report stale data after profile update — only on staging, not production"`

## When NOT to Use

- **Known bug with named regression test:** use `/fix` directly.
- **Design discussion with no failing behavior in hand:** use `/adr` or `/ticket`.
- **New feature implementation:** use `/feature`.
- **General questions about why something behaves a certain way (no defect):** use `/btw`.
- **Re-entry from inside `/fix`, `/ticket`, or `/adr`:** exit that command first, then re-enter via `/debug`. `debug` MUST NOT be invoked from inside those commands (routing-cycle prevention).

## See Also

- `/fix` — once root cause is confirmed and a regression test obligation is named (Phase 4 exit (a)).
- `/ticket` — for behavior / design ambiguity needing triage (Phase 4 exit (b)).
- `/adr` — for architectural ambiguity requiring a decision (Phase 4 exit (b), with user attribution).
