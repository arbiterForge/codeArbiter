---
entity: commands/debug
related: [fix, adr, skills/debug]
gates:
  - gate: minimal repro
    when: before a hypothesis is formed
    effect: a defect with no reliable reproduction (or a documented intermittent-trigger profile) cannot proceed
  - gate: three hypotheses, one boring
    when: before evidence is gathered
    effect: at least three distinct candidate causes are required, including one environmental or configuration explanation, before anything is checked against evidence
  - gate: no code changes
    when: for the entire investigation
    effect: investigation never edits application code; the no-action exit records a queued note through the task helper
  - gate: single named exit
    when: at the end of the investigation
    effect: the session must close as exactly one of a confirmed bug, a design ambiguity, or a no-action close — never left open
---

## What it does

This is where an unexplained defect goes before anyone touches code. The investigation is
deliberately separated from the fix: describing the symptom, forming multiple candidate causes, and
checking each against logs, traces, and recent commits happen without editing application code. The
requirement for at least three distinct hypotheses — with one of them a boring explanation like a
stale cache or a config mismatch — exists because locking onto the first plausible story is the most
common way a diagnosis goes wrong. Whatever the investigation lands on, it has to close as exactly one
outcome: a confirmed bug handed to `/ca:fix` with a named regression-test obligation, a design
ambiguity handed to `/ca:adr`, or a documented decision that no action is needed.

## Usage

A plain-language request for root-cause investigation selects the same owning
skill. `/ca:debug` remains an explicit entry generated from that skill, not a
second independently maintained procedure. The gates below still apply.

```
/ca:debug <observed symptom>
```

Describe what happened with enough detail that someone else could reproduce it — a vague description
like "it's flaky" gets a request for more detail before routing begins.

## Example

```text
Illustrative investigation entry, not a captured run:
> /ca:debug export returns no CSV for one saved search

Observed: no CSV for name Open, query state:open.
Expected: a header and one data row.
Reproduction: repeats in the identified checkout.
Candidates: serializer path; empty input reaching
that path; stale installed or running code.
Evidence: still required before confirming a cause.
```

A symptom record needs an exact reproduction or intermittent-trigger profile. A plausible
hypothesis is not a confirmed diagnosis. The returned summary names the evidence, result and
chosen exit. See [Investigate and fix a defect](/guides/investigate-and-fix/) for the complete
operator procedure and the regression-test handoff.

A no-action close records a queued note through the task helper. Application code stays
unchanged, but this board write means the complete command is not universally zero-write.
The investigation does not promise a separate fixed-path report file.

## When to reach for it

Reach for `/ca:debug` when the cause isn't known yet. If the cause and a reproduction are already
in hand, go straight to `/ca:fix`.
