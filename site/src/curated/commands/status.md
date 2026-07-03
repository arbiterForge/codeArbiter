---
entity: commands/status
related: [metrics, audit, task]
---

## What it does

A read-only snapshot of `.codearbiter/` state: the project's `stage:` maturity value, every
in-flight pipeline under `specs/` and `plans/` with how far each got (spec awaiting approval, spec
approved with no plan, a plan in progress with its `ACCEPTED` task count, or complete), the open
task and open-question counts, overrides logged since the last checkpoint, and the current git
branch. No skill is routed to and no file is modified — if `[CONFIRM-NN]` placeholders are open, it
surfaces them without resolving them.

## Usage

```
/ca:status
```

Takes no arguments.

## Example

```text
> /ca:status

## Project status — 2026-07-02

Stage:            3
Branch:           docs/site-curated-commands-b
Pipelines:
  docs-site-overhaul   plan 4/12 ACCEPTED — resume with /ca:feature "docs-site-overhaul"
Open tasks:       2
Open questions:   1 ([CONFIRM-11] unresolved)
Overrides since last checkpoint: 2
```

## When to reach for it

A quick glance at where things stand right now. For a full cross-cutting review, use
`/ca:checkpoint`; for a specific question about the project, use `/ca:btw`.
