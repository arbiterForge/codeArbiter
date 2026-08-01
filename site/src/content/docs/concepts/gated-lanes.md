---
title: The Gated-Lane Model
description: "How codeArbiter assigns every kind of work to a sanctioned path with gates scaled to its risk, and what distinguishes soft gates from hard gates."
journey:
  level: "Foundation"
  time: "8 minutes"
  outcome: "Choose the correct lane for a change and recognize who can clear its next gate."
  prerequisites:
    - "Read What Is codeArbiter"
  proof: "You can classify a real repository task without reaching for override or implementation first."
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
  <img src="/diagrams/gate-model.svg" alt="Gate model. A soft gate surfaces a decision bubble and waits for the user. A hard gate is a closed cross-bar that is never auto-decided." loading="lazy" />
  <figcaption>Soft gates surface and wait. Hard gates stop, and only the user can clear them.</figcaption>
</figure>

## Choose a lane from the work, not its size

| Situation | Start here | Why |
|---|---|---|
| Add user-visible behavior | `/ca:feature` | A spec and failing test establish the new contract. |
| Repair a defect with a confirmed cause | `/ca:fix` | A regression test must fail before the minimal repair. |
| Find the cause of an unexplained failure | `/ca:debug` | Investigation comes before selecting a change lane. |
| Restructure without changing behavior | `/ca:refactor` | Existing tests must remain unmodified and prove parity. |
| Change docs, bump a dependency, or revert | `/ca:chore` | The lighter lane scales evidence to non-feature work. |
| Explore a disposable idea | `/ca:spike` | The branch cannot merge or become a PR. |
| Run a governed multi-task campaign | `/ca:sprint` | One approved spec and plan drive logged autonomous decisions. |

The number of changed lines does not choose the lane. A one-line behavior change is still a feature
or fix; a 500-line generated reference refresh can still be a chore.

## How many gates, concretely

Lane depth is scaled to risk. The [`tdd` skill](/reference/skills/tdd/) runs 6 gated phases:
obligation scan, red, green, obligation verify, coverage, lint. The
[`commit-gate` skill](/reference/skills/commit-gate/) runs 9: permission, branch,
classification, verification, behavioral proof, diff review, selective stage, message,
commit. It's the only path to a commit. [`refactor`](/reference/skills/refactor/) runs 6
phases, all built around proving behavioral parity through unmodified pre-existing tests.

<figure class="ca-diagram">
  <img src="/diagrams/commit-gate-phases.svg" alt="Commit-gate's nine phases as a left-to-right gated pipeline: permission, branch, classification, verification, behavioral proof, diff review, selective stage, message, commit. Each phase is a hard BLOCK gate. Phase 5.5, provenance auto-heal, is a conditional side-lane that only runs on drift, then rejoins before diff review." loading="lazy" />
  <figcaption>Nine phases, permission through commit. 5.5 is a conditional side-lane, not a tenth gate.</figcaption>
</figure>

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

Where a gate permits bypass, the one sanctioned path is
[`/ca:override`](/reference/commands/override/): a deliberate, immediate-action exception that
appends one line to `overrides.log`. It is logged, not silent. H-18 activation protection is the
important exception: it has no in-session override path.

## Check your understanding

Take the next item from your issue tracker and write down three things before invoking a command:

1. the lane that owns it;
2. the first evidence that lane must produce;
3. whether the next stop is a soft decision or a hard gate.

Then compare your choice with the command's [generated reference page](/reference/). A correct
classification is the proof for this module; invoking an override because the wrong lane stopped
you is not.
