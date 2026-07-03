---
entity: commands/preview
related: [doctor, review]
---

## What it does

A zero-onboarding, read-only dry-run of the reviewer fleet against whatever is currently
uncommitted — no `/ca:init`, no `.codearbiter/` directory, no decompose or create-context
interview required first. It exists so someone evaluating codeArbiter can see it react to their
real, in-progress code before paying any setup cost. `git status` is unchanged by a run: nothing
is written, not the worktree, not the index, not `.codearbiter/`.

It does three things: collects the current diff (unstaged, staged, and untracked changes,
unioned); predicts which reviewers *would* dispatch by matching changed paths against the same
reviewer-to-path matrix `/ca:review` uses; and actually runs the one check that needs no project
rules at all — a state-free secret scan — reporting any finding by `path:line_no` with the
credential value already redacted to `****`. The reviewer predictions are exactly that,
predictions; only the secret scan is a real result.

## Usage

```
/ca:preview
```

Takes no arguments — it always inspects the current uncommitted diff.

## Example

```text
> /ca:preview

Changed files
  src/auth/session.ts     (unstaged)
  src/auth/login.test.ts  (untracked)

Predicted reviewers
  security-reviewer       -> src/auth/session.ts (auth path)
  auth-crypto-reviewer    -> src/auth/session.ts (crypto/key handling path)
  coverage-auditor        -> src/auth/login.test.ts (source change)

Secret findings
  none found

Full gated review needs /ca:init, then /ca:review.
```

## When to reach for it

An onboarded repo wanting the full gated verdict wants `/ca:init` then `/ca:review`; proving the
install's hooks actually fire (not just predicting reviewers) is `/ca:doctor`'s job, not this
one's — the two make distinct claims and are never blended.
