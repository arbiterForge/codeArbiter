---
title: Checkpoints
description: "Periodic, read-only sweeps of the whole codebase by the reviewer fleet, consolidated into dated reports to catch drift and latent issues between feature work."
journey:
  level: Power user
  time: 10–30 min
  outcome: "a repeatable whole-tree review cadence, a dated triaged report, and a clear boundary between checkpoint findings and required change gates."
  prerequisites:
    - An initialized repository
    - Enough time for six read-only review lenses
  proof: "A dated checkpoint report exists, every finding has severity and location, and follow-up work is routed separately."
---

A **checkpoint** is a periodic, read-only sweep of the whole codebase by the reviewer fleet.
The findings are consolidated, classified by severity, and triaged into a single dated
report. Checkpoints are how drift and latent issues get caught between feature work, without
blocking any single change.

## The fleet

A checkpoint dispatches six named reviewers, read-only and in parallel. This is the same
fleet [`/ca:review`](/reference/commands/review/) runs per-diff; a checkpoint scopes it to the
whole tree instead of one change.

| Reviewer | Checks |
|---|---|
| [`security-reviewer`](/reference/agents/security-reviewer/) | Security posture against `security-controls.md` |
| [`auth-crypto-reviewer`](/reference/agents/auth-crypto-reviewer/) | Authentication, cryptography, key, and secret paths |
| [`dependency-reviewer`](/reference/agents/dependency-reviewer/) | License and supply-chain posture of manifests |
| [`migration-reviewer`](/reference/agents/migration-reviewer/) | Migration safety and data classification |
| [`coverage-auditor`](/reference/agents/coverage-auditor/) | Test coverage against TDD obligations |
| [`architecture-drift-reviewer`](/reference/agents/architecture-drift-reviewer/) | Drift between code and accepted ADRs in `decisions/` |

## The funnel

The orchestrator never reads raw reviewer output. Each reviewer's findings go to
[`finding-triage`](/reference/agents/finding-triage/), which classifies every finding by
severity and by whether it blocks the current change. The triaged result goes to
[`checkpoint-aggregator`](/reference/agents/checkpoint-aggregator/), which composes the dated
report.

## What gets written

- `.codearbiter/checkpoints/YYYY-MM-DD.md`: findings grouped by severity with `file:line`;
  anything out of scope for the sweep is marked `[NEEDS-TRIAGE]` inline.
- `.codearbiter/last-checkpoint`: the current override count, re-zeroing the statusline's
  `over:N` counter until the next `/ca:override`.

A checkpoint is a report, not a promotion gate. It enforces no sign-off and blocks nothing by
itself.

## Run and Act on a Checkpoint

Invoke `/ca:checkpoint` in Claude Code, `$ca-checkpoint` in Codex, or `/ca-checkpoint` in Pi. Let the
read-only fleet finish; do not edit in parallel and then mistake moving source for a stable review
target.

Review `.codearbiter/checkpoints/YYYY-MM-DD.md` from highest severity down:

1. Confirm each finding still points to the named file and line.
2. Route a confirmed defect through the fix lane, a structural change through refactor, and new
   behavior through feature. A checkpoint does not implement its own findings.
3. Triage `[NEEDS-TRIAGE]` items into a scoped follow-up or an explicit defer condition.
4. Run status and confirm the override counter reset captured by `.codearbiter/last-checkpoint`.

If a reviewer fails or its evidence is incomplete, the report must say so. A partially populated
file is not equivalent to a clean sweep.

## The deep counterpart

[`/ca:tribunal`](/reference/commands/tribunal/) convenes the rare, on-demand version of this
same idea, at far greater depth. Where a checkpoint runs six reviewers against the current
tree, tribunal dispatches eleven specialist lens reviewers (roster on the
[tribunal command](/reference/commands/tribunal/) and [tribunal skill](/reference/skills/tribunal/)
pages) across seven gated phases. Phase 0 is a hard STOP: the user must acknowledge a
token-cost estimate, routinely in the millions, before anything runs. Each finding is written
to its own file the moment it's found, alongside append-only `run.jsonl` and `triage.jsonl`
logs under `.codearbiter/reports/<run-id>/`, so an interrupted run resumes from disk instead
of restarting. A triage pass independently recalibrates every lens's severity; every
critical or high finding carries a counter-argument. Findings become GitHub issues only on
explicit per-finding selection. "Looks good" files nothing.

Like the checkpoint, tribunal is read-only review and never a required gate.
