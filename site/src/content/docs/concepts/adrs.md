---
title: ADRs and the Decision Log
description: "How architecturally significant choices are captured as numbered, dated, user-attributed Architecture Decision Records with supersede chains and decision-health reporting."
---

Architecturally significant choices are written down as **Architecture Decision Records**:
numbered, dated, and attributed to the user who made them, stored under the project's
decision log. codeArbiter never authors an ADR as its own judgment; every record carries
explicit user attribution. The decision-lifecycle skill maintains supersede chains, so a
newer ADR can replace an older one, and it can report decision health: which records are
aging, unchallenged, or in conflict.

## Where a decision lives

Each ADR is a file at `.codearbiter/decisions/NNNN-<slug>.md`, numbered gap-free. The two
entry points are [`/ca:adr "<title>"`](/reference/commands/adr/) to write one and
[`/ca:adr-status [--adr N]`](/reference/commands/adr-status/) to report on the set. Both
route through the [decision-lifecycle skill](/reference/skills/decision-lifecycle/).

An ADR's status follows a fixed vocabulary: `proposed → accepted → superseded | rejected`.
A status change happens only on explicit user instruction, never inferred. A supersede
chain runs forward-only through a `supersedes:` field on the newer record; the prior ADR
file itself is never edited.

Every ADR shares its directory with an append-only companion, `decision-log.md`, that
records the same decisions as a running ledger.

## What makes a decision live

An ADR's `governs:` field is a set of path globs. Once a decision is accepted, those globs
do two things: the post-write hook surfaces "governed by ADR-NNNN" on a matching edit, and
an accepted ADR's globs feed tier 2 of the JIT read-injection priority map (see
[Just-in-Time Context Injection](/concepts/jit-context-injection/)).

Some questions in a draft ADR can only be answered by the user. Those are marked with a
`[CONFIRM-NN]` placeholder and never resolved by guessing.

## Enforcement, not convention

"ADRs only get written through `/ca:adr`" is not a house rule that relies on discipline.
Pre-write and pre-edit hooks block any write to `decisions/NNNN-*.md` unless a fresh
`.codearbiter/.markers/adr-authoring-active` marker exists, minted by the command and
valid for a 30-minute window. See the [hooks and gates reference](/reference/hooks-gates/)
for the full gate catalog.

`/ca:adr-status` MAY additionally dispatch
[`decision-challenger`](/reference/agents/decision-challenger/), an optional adversarial
reviewer that red-teams each decision and assigns it a confidence score from 1 to 5.
