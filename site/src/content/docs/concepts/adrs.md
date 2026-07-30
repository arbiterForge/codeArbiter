---
title: ADRs and the Decision Log
description: "How architecturally significant choices are captured as numbered, dated, user-attributed Architecture Decision Records with supersede chains and decision-health reporting."
journey:
  level: Power user
  time: 8 min
  outcome: "the ability to distinguish ADR files from the append-only decision ledger, trace active governs globs, and follow a forward-only supersession chain."
  prerequisites:
    - Know why the decision matters to later work
  proof: "You can find the active ADR for a path and explain why the prior record was not rewritten."
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

## Use the Records in Practice

When a write reminder says a path is governed by an ADR, open that numbered record and verify three
things before continuing: its status is `accepted`, the edited path matches a `governs:` glob, and no
later ADR supersedes it. Use `/ca:adr-status --adr N` (Codex: `$ca-adr-status --adr N`) when the
chain is not obvious.

Use an ADR for a durable architectural choice future work must obey. Do not use one for a temporary
task, a debugging hypothesis, or an option you have not decided. Record a decision through the
[ADR workflow](/guides/recording-adrs/); use reconcile when competing artifacts still need SMARTS
arbitration.
