---
entity: commands/cleanup
related: [commands/pr, commands/standup, commands/status, skills/post-merge-cleanup]
gates:
  - gate: fetched ancestry proof
    when: before any local artifact or branch can be removed
    effect: fetches the default branch and stops unless the current HEAD is proven contained in that fetched ref
  - gate: residue classification
    when: the working tree or stash list contains leftover material
    effect: every item is classified with evidence; uncertainty is treated as unique rather than disposable
  - gate: per-item consent
    when: any file, artifact, or local branch is offered for removal
    effect: each target is named and confirmed separately; there is no batch approval
---

## What it does

Use this after a pull request has merged but your local checkout is still on the topic branch.
`cleanup` proves that the branch's work reached the fetched default branch, inventories everything
left locally, and walks back to a clean default checkout without treating an upstream marked
`gone` as proof.

## Usage

```text
/ca:cleanup
```

The command takes no arguments. Run it from the merged topic branch. Codex uses `$ca-cleanup`; Pi
uses `/ca-cleanup`.

## What you decide

codeArbiter explains whether each leftover file is reproducible, replaced by landed work, or the
only remaining copy. You approve or decline each removal by name. A stash is reported but never
dropped. After the tree is safe, the default branch is checked out and fast-forwarded, and the
merged local branch is offered for deletion with `git branch -d`.

## Successful exit

The receipt names the fetched default ref used for proof, what was removed, what was kept, the
current checkout, and whether the local topic branch remains. Declining any deletion is a valid
result.

## When to use another command

- The PR has not merged: use `/ca:pr`.
- The current work needs committing: use `/ca:commit`.
- You want a read-only repository summary: use `/ca:status`.
- You want broad daily hygiene across other branches and worktrees: use `/ca:standup`.
