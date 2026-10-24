---
entity: commands/status
related: [audit, task]
---

## What it does

A read-only snapshot of project maturity, pipeline progress, open tasks and questions,
override count and Git branch. `DONE` and historical `ACCEPTED` contribute to implementation
completion, with their labels retained. Verification is reported separately: a completed task
does not establish a passing check, review or release. Missing state remains unknown.

Drafts do not create a permission wait. The snapshot shows genuine decisions and blocked tasks
with their actual reasons, without resolving them or changing files.

## Usage

```
/ca:status
```

With no arguments, show the snapshot. `/ca:status drift` routes to the context audit;
refreshing documents requires an explicit scoped selection after its report.

## Example

```text
> /ca:status

## Project status — YYYY-MM-DD

Stage:            3
Branch:           feature/export
Pipelines:
  export   implementation 4/12 complete (4 DONE); verification pending — resume with /ca:feature "export"
Open tasks:       2
Open questions:   1 ([CONFIRM-11] unresolved)
Overrides since last checkpoint: 2
```

## When to reach for it

A quick glance at where things stand right now. For a full cross-cutting review, use
`/ca:checkpoint`; for a specific question about the project, ask it directly.
