---
entity: skills/post-merge-cleanup
related: [commands/cleanup, commands/pr, commands/standup]
gates:
  - gate: merge proof
    when: phase 1 compares the topic HEAD with the fetched default ref
    effect: work stops if containment cannot be proven from current remote state
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
looks obsolete.

## Phases

1. Fetch the remote default branch and prove the topic commit is contained in it.
2. Inventory the working tree and stashes, then explain the evidence for each classification.
3. Ask about every possible removal separately, preserving anything declined or uncertain.
4. Check out the default branch, verify the checkout, and update it only by fast-forward.
5. Offer deletion of the merged local branch with Git's non-forcing safety check.
6. Report the final checkout and every keep/remove decision.

## Exits

A complete run leaves you on a clean, current default branch and may remove the merged local branch.
A safe early exit leaves the checkout unchanged and names the evidence or retained item that stopped
the transition. Remote branches and stashes are outside this skill's deletion authority.
