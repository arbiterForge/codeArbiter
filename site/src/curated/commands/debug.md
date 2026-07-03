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
    effect: every phase is read-only; a fix is never attempted mid-investigation
  - gate: single named exit
    when: at the end of the investigation
    effect: the session must close as exactly one of a confirmed bug, a design ambiguity, or a no-action close — never left open
---

## What it does

This is where an unexplained defect goes before anyone touches code. The investigation is
deliberately separated from the fix: describing the symptom, forming multiple candidate causes, and
checking each against logs, traces, and recent commits all happen without editing anything. The
requirement for at least three distinct hypotheses — with one of them a boring explanation like a
stale cache or a config mismatch — exists because locking onto the first plausible story is the most
common way a diagnosis goes wrong. Whatever the investigation lands on, it has to close as exactly one
outcome: a confirmed bug handed to `/ca:fix` with a named regression-test obligation, a design
ambiguity handed to `/ca:adr`, or a documented decision that no action is needed.

## Usage

```
/ca:debug <observed symptom>
```

Describe what happened with enough detail that someone else could reproduce it — a vague description
like "it's flaky" gets a request for more detail before routing begins.

## Example

```text
> /ca:debug the nightly export job sometimes finishes with a zero-byte file, maybe once a week

Symptom captured. Repro: intermittent, ~1-in-7 nightly runs, no clear trigger yet identified.
Hypotheses:
  H1 (likely): export writer is not flushed before the process exits
  H2: source query times out silently under load and returns nothing
  H3 (boring): the export volume mount is occasionally unmounted before the job starts
Gathering evidence... H1 CONFIRMED (log shows process exit 0.2s after last write, no flush call in
the writer's shutdown path). H2 and H3 REFUTED (query duration and mount logs are clean on affected runs).

Exit: (a) confirmed bug. Regression test obligation: kill the writer immediately after the last write
call and assert the output file is complete. Routing to /ca:fix.
```

## When to reach for it

Reach for `/ca:debug` when the cause isn't known yet. If the cause and a reproduction are already
in hand, go straight to `/ca:fix`.
