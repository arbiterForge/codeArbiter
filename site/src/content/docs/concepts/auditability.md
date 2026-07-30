---
title: Auditability
description: "How ADRs, the sprint log, checkpoints, and the append-only override trail combine to make a codeArbiter repository auditable after the fact for any range of work."
journey:
  level: "Power user"
  time: "8 minutes"
  outcome: "Assemble and validate the governance record for a release or handoff."
  prerequisites:
    - "An initialized repository with at least one governed commit"
  proof: "A dated audit packet whose range and verbatim records match their source files."
---

Taken together, these concepts make a codeArbiter repository auditable after the fact. ADRs
say *why*. The sprint log says *what was auto-decided and how confidently*. Checkpoints say
*what the sweeps found*. An append-only override trail records every sanctioned bypass. The
governance record can be assembled for any range of work on demand.

For the concrete catalog of what runs in each lane, see the auto-generated
[Reference](/reference/).

## When to use it

Assemble an audit when you need to explain a release, hand work to another maintainer, review a
security-sensitive range, or establish whether an override or low-confidence autonomous choice
affected a result. The audit command is read-only: it projects existing evidence into a new report;
it does not repair missing records or rewrite the sources it reads.

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

## Example

```text
/ca:audit v2.8.12 HEAD
```

| Host | Invocation |
|---|---|
| Claude Code | `/ca:audit v2.8.12 HEAD` |
| Codex | `$ca-audit v2.8.12 HEAD` |
| Pi | `/ca-audit v2.8.12 HEAD` |

Open the path printed by the command and verify that its range, commit list, unresolved questions,
and verbatim override lines match the source files. An empty section is evidence that the source
had nothing in that category, not proof that an expected record was created elsewhere.

## Validate the packet

Do not treat file creation as success. Check the packet in this order:

1. Confirm the requested `from` and `to` refs resolved to the commits you intended.
2. Pick one commit and trace it back to `git log`.
3. If the range contains an override, compare the packet's line byte-for-byte with
   `.codearbiter/overrides.log`.
4. If it contains an ADR, open the named file and verify its status and decision-log entry.
5. Review the unresolved questions section before handing the packet to someone else.

Your proof is not “the command exited zero.” It is a packet whose selected evidence can be traced
back to the checked-in source of record.

If evidence is missing, stop and trace the owning workflow. Do not hand-edit the assembled report
to make the record look complete.
