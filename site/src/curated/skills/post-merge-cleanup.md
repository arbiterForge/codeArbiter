---
entity: skills/post-merge-cleanup
related: [commands/cleanup, commands/pr, commands/standup]
use_when: "A pull request has merged and your local checkout is still on the topic branch."
avoid_when: "A pull request that has not merged, which is `/ca:pr`; work that still needs committing, which is `/ca:commit`; a read-only summary, which is `/ca:status`; or branch and worktree cleanup across the whole repository, which is `/ca:standup`."
asks: "A separate yes or no for every file, artifact or local branch offered for removal. Declining any deletion is a valid result, and a stash is reported but never dropped."
produces: "A clean, current default-branch checkout, the removals you approved, and a receipt of what was removed and kept."
gates:
  - gate: merge proof
    when: phase 1 compares the topic HEAD with the fetched default ref
    effect: work stops unless HEAD is proven contained in the fetched default branch, by ancestry or, for a squash merge, by the merged PR record matching HEAD
  - gate: item classification
    when: phase 2 inventories tracked changes, untracked files, and stashes
    effect: every item receives a reasoned class and any uncertainty receives the most conservative class
  - gate: explicit removal
    when: phases 3 and 5 offer local cleanup
    effect: each artifact and the local branch require their own named confirmation
  - gate: safe transition
    when: phase 4 returns to the default branch
    effect: verifies the checkout and permits only a fast-forward update
---

## What it does

The `cleanup` command routes here after a pull request lands. The skill separates merge proof from
local tidying so no generated file, scratch note, stash, or branch is discarded merely because it
looks obsolete. It proves that the branch's work reached the fetched default branch before anything
local is touched, and it never treats an upstream marked `gone` as proof. A squash merge leaves no
commit ancestry back to the branch, so when the ancestry check fails it falls back to the merged PR
record, where the PR's `headRefOid` must equal local HEAD, and it reports whichever proof held.

## Usage

```text
/ca:cleanup
```

The command takes no arguments. Prefer `/ca:pr --cleanup` or request cleanup directly; the retained
entry uses the same owner. Start from the merged topic branch. A cleanup request does not approve
any discard.

## Example

Illustrative output, not captured execution:

```text
> /ca:cleanup

Fetched origin/main. HEAD is not an ancestor of origin/main, so checking the PR record.
PR #482 is MERGED and its head commit equals local HEAD: containment proven by the PR record.
Leftover items:
  notes/session.md  unique (no copy on main). Keep it, commit it, or discard it by name?
  dist/bundle.js    redundant (rebuilt by a committed script). Remove it?
> Keep notes/session.md. Remove dist/bundle.js.
Stash stash@{0} reported, not dropped.
Fast-forwarded local main, checked it out, confirmed the branch is main.
Delete fix/session-rotation? git branch -d refused because the remote branch is gone; -D is
offered only because the PR-record proof above held.
> Yes.
Receipt: proof = PR #482 head match; removed dist/bundle.js and fix/session-rotation;
kept notes/session.md and the stash; now on main.
```

## What you decide

codeArbiter explains whether each leftover file is reproducible, replaced by landed work, or the
only remaining copy. You approve or decline each removal by name. A stash is reported but never
dropped. Before the checkout, a stale local default ref is fast-forwarded from the fetched one so it
cannot be mistaken for a conflicting kept artifact; then the default branch is checked out and
fast-forwarded, and the merged local branch is offered for deletion with `git branch -d`. If `-d`
refuses because the remote branch is already gone, `-D` is offered instead, but only when the
squash-merge PR-record proof held, and that proof is restated in the confirmation next to the
branch name.

## Phases

1. Fetch the remote default branch and prove the topic commit is contained in it.
2. Inventory the working tree and stashes, then explain the evidence for each classification.
3. Ask about every possible removal separately, preserving anything declined or uncertain.
4. Check out the default branch, verify the checkout, and update it only by fast-forward.
5. Offer deletion of the merged local branch with Git's non-forcing safety check.
6. Report the final checkout and every keep/remove decision.

## Exits

A complete run leaves you on a clean, current default branch and may remove the merged local branch.
The receipt names the fetched default ref used for proof, what was removed, what was kept, the
current checkout, and whether the local topic branch remains.
A safe early exit leaves the checkout unchanged and names the evidence or retained item that stopped
the transition. Remote branches and stashes are outside this skill's deletion authority.
