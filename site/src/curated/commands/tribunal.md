---
entity: commands/tribunal
related: [checkpoint, audit, skills/tribunal]
gates:
  - gate: cost acknowledgement
    when: before Phase 0 finishes, every run
    effect: the job is sized, a token-cost band and model recommendation are printed, and nothing dispatches until you explicitly acknowledge the estimate and confirm the model
  - gate: approval before filing
    when: after the report is generated
    effect: findings become GitHub issues only on your explicit selection — silence or "looks good" files nothing
---

## What it does

codeArbiter's deepest, most expensive review, convened rarely and never as a required gate. Eleven
specialist lenses judge the whole codebase in priority waves; each finding is written to its own
file under `.codearbiter/reports/<run-id>/`, so an interrupted run resumes from disk instead of
losing progress. Because this lane routinely costs millions of tokens on a large repo, Phase 0
always stops first: it sizes the codebase, prints the cost band, recommends the highest-reasoning
model, and waits for you to say go. Critical and high findings are blocking-severity in the report
— meaning they're work that should block shipping the affected code — but the tribunal run itself
never halts a merge or commit.

## Usage

```
/ca:tribunal "[scope-path] [--tag <label>]"
```

An optional `scope-path` narrows which subtree gets scrutiny (the full eleven-lens roster still
runs); `--tag <label>` records a freeform label if you opt in to KPI telemetry at the end.

## Example

```text
> /ca:tribunal

Sizing codebase... 340 files, ~2.1M tokens estimated.
Recommended model: highest-reasoning available, high effort.
Estimated cost band: $180-$260.

Proceed with this model and cost? (y/n)
> y

RUN_ID: 2026-07-02-full
Phase 1: mapping... inventory.md written, 11 lenses active.
Phase 2: dispatching lenses (wave 1/3, ≤5 in flight)...
...
Phase 4: report.md regenerated — 3 CRITICAL, 9 HIGH, 21 MEDIUM findings.

Phase 5: file findings as GitHub issues? Select which, or "none".
```

## When to reach for it

Rare, deliberate, whole-codebase depth — not the routine sweep (`/ca:checkpoint`), not a diff review
(`/ca:review`), and never wired into a hot loop or schedule.
