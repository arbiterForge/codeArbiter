---
title: "Record an architecture decision"
description: "How to author, supersede, and monitor Architecture Decision Records with /ca:adr and /ca:adr-status."
---

Record an Architecture Decision Record (ADR) when a choice is significant enough to constrain future work: a data-store selection, a dependency commitment, a structural boundary, or a security posture. This guide walks through authoring, superseding, and monitoring ADRs.

## Before you start

Confirm codeArbiter is active. The first three lines of `.codearbiter/CONTEXT.md` must include `arbiter: enabled` inside a closed frontmatter block. If it does not, run `/ca:init` first.

## Run /ca:adr

Invoke the command with a short description of the decision:

```text
/ca:adr "Use PostgreSQL as the primary datastore"
```

The `decision-lifecycle` skill opens an interview. It asks for the context that made this decision necessary, the options you considered, the rationale behind the choice, and any consequences or constraints it carries. The skill writes nothing until you have supplied that information. Every field in the record is your input, not a generated judgment.

## What the skill produces

`/ca:adr` writes a numbered, dated, user-attributed file to `.codearbiter/decisions/`. Files follow the sequence already in that directory: `ADR-0001.md`, `ADR-0002.md`, and so on. The `author:` field names you. codeArbiter never fills in that field with its own identity.

H-11 makes that requirement durable. Shell operations that write directly to `decisions/` are blocked at the tool-call boundary: redirects, `cp`, `rm`, and `sed -i` targeting that directory all exit non-zero. Direct `Write` and `Edit` calls to files there are blocked the same way. The skill drops a fresh authoring marker before it writes; any write attempt without that marker is rejected. There is no path to create or modify an ADR outside of `/ca:adr`.

## Supersede an outdated decision

When a new decision replaces an earlier one, run `/ca:adr` again and tell the skill which ADR the new one supersedes. The skill marks the earlier ADR's status as superseded and links the two records in both directions. The original file stays intact; the chain shows which decision is current.

## Check decision health

```text
/ca:adr-status
```

This command sweeps `.codearbiter/decisions/` and reports:

- ADRs that are aging without challenge
- records with unresolved `CONFIRM-NN` markers
- decisions that are candidates for supersession

`/ca:adr-status` is read-only. It surfaces information and never writes. Act on its output by running `/ca:adr`.

## Related pages

- [adr](/reference/commands/adr/) command reference
- [adr-status](/reference/commands/adr-status/) command reference
- [decision-lifecycle](/reference/skills/decision-lifecycle/) skill reference
- [Enforcement](/enforcement/) (H-11: ADR authoring gate)
