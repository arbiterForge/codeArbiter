---
title: Auditability
description: "How ADRs, the sprint log, checkpoints, and the append-only override trail combine to make a codeArbiter repository auditable after the fact for any range of work."
---

Taken together, these concepts make a codeArbiter repository auditable after the fact. ADRs
say *why*. The sprint log says *what was auto-decided and how confidently*. Checkpoints say
*what the sweeps found*. An append-only override trail records every sanctioned bypass. The
governance record can be assembled for any range of work on demand.

For the concrete catalog of what runs in each lane, see the auto-generated
[Reference](/reference/).

## The assembler

[`/ca:audit`](/reference/commands/audit/) is the command that synthesizes the record. It
pulls together, by exact source:

| Source | What it contributes |
|---|---|
| `overrides.log` | every sanctioned bypass |
| `triage.log` | checkpoint findings |
| `decisions/` + `decision-log.md` | ADRs and the decision ledger |
| `sprint-log.md` | autonomous auto-decisions and their confidence |
| `checkpoints/*.md` | dated sweep reports |
| `[CONFIRM-NN]` items | unresolved open questions |
| commits | grouped by Conventional-Commit type |

## Window and output

The range can be given as `<from-ref> <to-ref>`, `--since-checkpoint`, or `--since <date>`;
with no arguments it defaults to the last tag through `HEAD`.

The result is written to `.codearbiter/audits/<YYYY-MM-DD>.md` and is never overwritten: a
second audit on the same day gets a `-2` suffix, a third `-3`. Override lines and
low-confidence sprint entries are quoted verbatim rather than summarized, and a section with
nothing to report says so explicitly instead of being omitted.
