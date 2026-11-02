---
entity: commands/status
related: [audit, task]
use_when: "You want a quick read-only glance at where the project stands right now."
avoid_when: "A full cross-cutting review, which is `/ca:checkpoint`; for a specific question, ask it directly."
asks: "Nothing. With no argument it shows the snapshot, and `/ca:status drift` routes to the context drift audit instead."
produces: "A snapshot of maturity, pipeline progress, open tasks and questions, override count and Git branch. It changes no files."
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
