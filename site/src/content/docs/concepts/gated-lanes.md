---
title: The Gated-Lane Model
description: "How codeArbiter assigns every kind of work to a sanctioned path with gates scaled to its risk, and what distinguishes soft gates from hard gates."
---

Every kind of work has a **lane**: a sanctioned path with gates scaled to its risk, and the
only way that kind of change ships. `/ca:fix` and `/ca:feature` run test-first through the
`tdd` gate. `/ca:refactor` must prove behavioral parity through *unmodified* pre-existing
tests. `/ca:chore` carries lighter gates, because prose edits and dependency bumps don't
demand TDD.

Gates come in two strengths. **Soft gates** surface a decision and wait for the user.
**Hard gates** are true stops, never auto-decided, even under autonomous execution:
anything in the security controls, auth/crypto/secret changes, irreversible operations, a
gate bypass, an unresolved decision, or a merge to the default branch. Hard gates are rare
by design; a hard gate that trips often is a signal the spec was too thin, and worth fixing
at the spec rather than working around at the gate.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/gate-model.svg" alt="Gate model. A soft gate surfaces a decision bubble and waits for the user. A hard gate is a closed cross-bar that is never auto-decided." loading="lazy" />
  <figcaption>Soft gates surface and wait. Hard gates stop, and only the user can clear them.</figcaption>
</figure>

## How many gates, concretely

Lane depth is scaled to risk. The [`tdd` skill](/reference/skills/tdd/) runs 6 gated phases:
obligation scan, red, green, obligation verify, coverage, lint. The
[`commit-gate` skill](/reference/skills/commit-gate/) runs 9: permission, branch,
classification, verification, behavioral proof, diff review, selective stage, message,
commit. It's the only path to a commit. [`refactor`](/reference/skills/refactor/) runs 6
phases, all built around proving behavioral parity through unmodified pre-existing tests.

## Mandatory routing at commit time

A change that touches certain surfaces pulls a specialist reviewer into the lane
automatically, not by request:

- Crypto-compliance and secret-handling changes must mint a digest-bound
  `security-gate-passed` marker before commit-gate lets the commit through; hooks H-09b and
  H-10b block it otherwise.
- A database migration must mint `migration-gate-passed`, enforced by H-14.
- A CI or deploy-path change dispatches `security-reviewer`, enforced by H-15/H-16, though
  advisory rather than blocking.

See the [hooks and gates reference](/reference/hooks-gates/) for the full gate catalog.

## The terminal lane

Every change lands through a PR, via
[finishing-a-development-branch](/reference/skills/finishing-a-development-branch/). Direct
merge to the default branch is forbidden.

The one sanctioned way around any of this is [`/ca:override`](/reference/commands/override/):
a deliberate bypass that appends one line to `overrides.log` and proceeds. It is logged, not
silent.
