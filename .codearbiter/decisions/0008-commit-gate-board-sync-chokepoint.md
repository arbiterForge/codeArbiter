---
status: accepted
date: 2026-06-26
title: commit-gate is the board-sync chokepoint — task-board transitions ride the work commit
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/skills/commit-gate/*, plugins/ca/includes/harvest.md, plugins/ca/commands/task.md, plugins/ca/skills/finishing-a-development-branch/*
---

# ADR-0008 — commit-gate is the board-sync chokepoint — task-board transitions ride the work commit

## Status
Accepted — ratified 2026-06-26 by SUaDtL@users.noreply.github.com.

## Context
Issue #142. A task is not truly done until its PR merges, but `.codearbiter/open-tasks.md` is itself
versioned, so a `[x]` done-flip only goes live when **its own** change merges to `main`. That created
an order-of-operations trap with no good side under the prior flow: marking done inside the work PR
risked the board edit being dropped as out-of-scope, while marking done after merge required a
**separate** `chore(board)` PR with its own merge lag. Both paths depended on human memory across a
context boundary — exactly where it broke. Concrete instances: #138 merged release-skill work but
never flipped `v2.release.0002-0006` (drift sat unnoticed for days); #140's `v2.rev.0020` flip needed
a third PR (#141) to land, which also swept up the stale `v2.release.0002-0006`.

Two facts about the existing machinery shaped the decision:

- **The flips are human-declared, not inferred.** `/ca:task done|start|add` runs `taskwrite.py` (the
  blessed `open-tasks.md` writer, D-1) and the human supplies the dotted task-id. There is no
  task→commit inference to build — the issue's "task-to-commit linkage" open question dissolves. The
  only thing wrong was the **timing/locus** of when that already-declared board edit gets committed.
- **commit-gate already ejects the flip.** Phase 6 (diff review) classifies an `open-tasks.md` edit as
  scope creep ("changes outside the agreed feature boundary") and unstages it. That ejection is *why*
  the flip was exiled to a separate `chore(board)` PR. Separately, raising a new follow-up task already
  exists as the **post-commit harvest** (Phase 6 `[NEEDS-TRIAGE]` → `harvest.md`, hard-rule line 133),
  which runs *after* the commit lands, so newly-raised tasks land in a separate edit — the board
  equivalent of burying a follow-up in the PR description.

The key insight (#142) resolves the paradox: because the board edit is invisible on `main` until merge,
co-locating the `[x]` flip with the work commit is **self-correcting** — it becomes live at exactly the
moment the work does (one atomic merge), and if the PR is abandoned the flip is abandoned with it, so
the board never wrongly shows done. The "don't mark done before merge" rule and the "don't lose the
board update" rule are the same problem; co-location satisfies both.

## Decision
**commit-gate is the single board-sync chokepoint.** All three task-board transitions co-locate with
the work commit rather than landing in a separate `chore(board)` PR or a PR-description note. The human
still declares each transition via `/ca:task` (`taskwrite.py`); commit-gate stops treating the
resulting `open-tasks.md` edit as scope creep and stages it into the same commit as the work.

Per-transition atomicity rules:

| Transition | Rides which commit | On PR abandonment | Rationale |
|---|---|---|---|
| **done-flip** `[~]`→`[x]` | the **completing** commit (the one whose work finishes the task) | reverts to `[~]` | self-correcting — board never wrongly shows done |
| **start-flip** `[ ]`→`[~]` | the **first** work commit of the task | reverts to `[ ]` | in-progress signal lands early; an un-landed start is no landed progress |
| **raise-new** add `[ ]` | the work commit (the harvest runs **pre-commit** instead of post-commit) | vanishes — **contingent default** | most discovered follow-ups depend on this work and are moot if it never lands |

**Raise-new survival rule:** a newly-raised task rides the work commit by default (contingent) and
vanishes with an abandoned PR. A follow-up that **must survive abandonment** (an independent discovery
unrelated to this work) is filed as a **GitHub issue** instead — the durable, PR-independent capture
surface — never as a board-only side commit. This keeps every `open-tasks.md` edit co-located with work
and routes truly-independent survivors to the right tool.

**Mechanism (to be implemented under a follow-on `/ca:feature`):**
1. commit-gate **Phase 6** no longer flags an `open-tasks.md` board edit as scope creep when it is a
   schema-valid `taskwrite.py` transition; it is expected and retained.
2. commit-gate **Phase 7** explicitly includes the board edit in the selective stage (by explicit path,
   never a wildcard — the existing Phase 7 rule stands).
3. The follow-up **harvest moves from post-commit to pre-commit** (Phase 6→7) so raised tasks are staged
   into the work commit; must-survive items are split out to GitHub issues at that point.
4. A **reconciliation backstop** in `/ca:standup` (and/or `/ca:doctor`) diffs the board against merged
   PRs and surfaces any merged-but-not-flipped task — the safety net for a done-flip that still drifts.

## Alternatives considered
- **finishing-a-development-branch / `/ca:pr` stages the flip at branch-finish** — declined as the
  *primary* hook. Same atomicity, but a slightly later and coarser point; commit-gate is where the
  staged set and scope are already adjudicated, so the flip belongs there. `/ca:pr` may still surface a
  reminder, but the chokepoint is the commit.
- **Post-merge GitHub Action flips the board** — declined. Removes human memory entirely but introduces
  a CI-writes-to-`main` concern (against the no-direct-writes posture) and standing machinery to
  maintain, for a solo-dev board.
- **Reconciliation sweep alone** — declined as a *fix*; kept as a *backstop*. A sweep can detect a
  merged-but-not-flipped task, but cannot recover a contingent task lost to an abandoned PR (there is no
  merged PR to diff against), so it cannot be the primary mechanism.
- **Build a task→commit linkage convention (`Closes <id>` footer / branch parse / `/ca:commit` arg)** —
  declined as unnecessary. The human already declares the task-id via `/ca:task`; commit-gate co-locates
  the already-declared edit rather than inferring which task a commit closes. The "which commit in a
  multi-commit branch carries the flip" question is answered by *when the human runs `/ca:task`*: the
  start-flip rides the first commit after `/ca:task start`, the done-flip rides the commit after
  `/ca:task done`.

## Consequences
Easier: one atomic merge lands the work and its board state together; no separate `chore(board)` PR, no
cross-session memory, no PR-description follow-ups that no tool reads. Abandoned work cleans up its own
board state for free. Harder: commit-gate Phase 6/7 and the harvest ordering must learn the board edit
as a first-class, expected part of the staged set without weakening the genuine scope-creep check (the
exemption is narrow — only schema-valid `taskwrite.py` transitions to `open-tasks.md`, not arbitrary
edits to it). Doc lockstep is required: the commit-gate SKILL, the `/ca:task` command doc, `harvest.md`,
and `task-board-lifecycle.md` update in the same change. This decision also resolves deferral D-1's
sibling concern (the start-flip-with-date drop-off hole) by giving the start-flip a committed home.

## Risks
- **Scope-creep check erosion.** If the Phase 6 board-edit exemption is too broad, a real out-of-scope
  change to `open-tasks.md` (e.g. an unrelated hand-edit) could ride through. Mitigation: exempt only
  edits that match a `taskwrite.py`-shaped transition diff; anything else stays flagged.
- **Wrong-commit flip on a multi-commit branch.** If the human runs `/ca:task done` before the
  truly-completing commit, the flip rides an earlier commit. Low stakes (still invisible until merge,
  still atomic with the branch), but the convention "flip when the work is actually complete" must be
  documented.
- **Contingent-default data loss.** A genuinely-independent follow-up mistakenly left as a contingent
  board task vanishes with an abandoned PR. Mitigation: the GitHub-issue escape hatch for must-survive
  items, plus the `/ca:standup` reconciliation backstop.
- **Proven wrong if** board drift persists after this ships (showing the chokepoint is still bypassable),
  or if the Phase 6 exemption causes a real scope-creep escape — at which point the post-merge-Action or
  a stricter linkage convention reopens.
