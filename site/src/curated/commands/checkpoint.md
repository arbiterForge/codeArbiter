---
entity: commands/checkpoint
related: [tribunal, audit, status]
gates:
  - gate: reviewer fleet, funneled
    when: every invocation
    effect: security-reviewer, auth-crypto-reviewer, dependency-reviewer, migration-reviewer, coverage-auditor, and architecture-drift-reviewer run read-only over the whole codebase, then funnel through finding-triage and checkpoint-aggregator — the orchestrator never consumes raw reviewer output directly
---

## What it does

A periodic sweep of the entire codebase with the same reviewer fleet `/ca:review` uses per-diff,
scoped instead to everything against the `.codearbiter/` docs. Every reviewer's output passes
through `finding-triage` then `checkpoint-aggregator`, which writes a dated report to
`.codearbiter/checkpoints/YYYY-MM-DD.md` with findings grouped by severity and file:line. It also
re-zeros the `over:N` overrides-since-checkpoint counter the statusline shows, by writing the
current `overrides.log` line count to `.codearbiter/last-checkpoint`. This is a report, not a
promotion gate — it surfaces findings and enforces no sign-off.

## Usage

```
/ca:checkpoint
```

Takes no arguments — it sweeps the whole codebase every time.

## Example

```text
> /ca:checkpoint

Dispatching reviewer fleet (6 reviewers, read-only)...
Triaging findings...

Checkpoint document written to .codearbiter/checkpoints/2026-07-02.md.

| Reviewer | CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| security-reviewer | 0 | 1 | 2 | 0 |
| coverage-auditor | 0 | 0 | 3 | 1 |
| architecture-drift-reviewer | 0 | 0 | 1 | 0 |
| **Total** | **0** | **1** | **6** | **1** |

1 DEFERRABLE finding surfaced for follow-up harvest.
last-checkpoint updated: 4 (override count reset)
```

## When to reach for it

The routine, cheap, whole-codebase sweep — not the current diff (`/ca:review`), not the rare
expensive deep audit (`/ca:tribunal`), and not ADR health alone (`/ca:adr-status`).
