---
entity: skills/debug
related: [commands/debug, tdd]
gates:
  - gate: symptom capture
    when: at the start of an investigation
    effect: a minimal reproduction, or a documented intermittent trigger, must exist before anything else proceeds
  - gate: hypothesis breadth
    when: before evidence gathering begins
    effect: at least three distinct candidate causes are required, one of them a boring environmental or configuration explanation
  - gate: root-cause decision
    when: after evidence is gathered
    effect: exactly one exit must be chosen — a confirmed bug, a design ambiguity, or a no-action close; "needs more investigation" alone is not an exit
---

## What it does

This is where an unknown defect gets investigated before anyone touches code. Invoked as its own
command, it runs one closed loop: capture a reproducible symptom, generate several distinct
candidate causes, gather cited evidence against each one, then commit to exactly one disposition.
No code changes here — a confirmed cause routes to the fix path, a design ambiguity routes to a
decision record, and a resolved-elsewhere symptom closes with a rationale on file.

## Phases

1. Capture the symptom with a minimal reproduction or a documented intermittent-trigger profile.
2. Generate at least three distinct hypotheses, including one boring, non-exotic explanation.
3. Gather cited evidence for and against each hypothesis without touching any code.
4. Choose exactly one root-cause exit: a confirmed bug carrying a named regression-test
   obligation, a behavior/design ambiguity headed for a decision record, or a no-action close.
5. Emit a summary and route to the chosen exit.

## Exits

A confirmed bug hands the fix path a regression-test obligation tied to the reproduction, so the
fix must first prove it fails before it can prove it's fixed. A design ambiguity surfaces the
question for a decision record with your attribution. A no-action close is logged as a queued
item rather than silently dropped.
