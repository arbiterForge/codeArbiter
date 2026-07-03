---
entity: commands/spike
related: [feature, debug, skills/using-git-worktrees]
gates:
  - gate: named question
    when: before the branch is created
    effect: a spike must restate the request as a falsifiable question plus a timebox, and you confirm it before any code is written
  - gate: no merge, ever
    when: for the lifetime of the spike branch
    effect: the branch can only end in a findings file and deletion — it is never PR'd or merged
  - gate: security floor
    when: throughout exploration
    effect: no secret leaves the approved store and no irreversible operation runs, even on disposable code
---

## What it does

This is the outlet for "I need to write code to find out" rather than "I know what to build." The
work happens on a disposable branch with none of the usual process overhead — no plan, no test-first
discipline, no review fleet — because the code itself is never meant to survive. What survives is the
answer: once the question is settled (or the timebox runs out without one), the finding gets written
down as a short note and the branch is deleted. If the answer turns out to justify building the real
thing, that's a fresh `/ca:feature` request that treats the spike as reference material, not as a
starting diff.

## Usage

```
/ca:spike <question to answer> [timebox]
```

State the question the exploration needs to answer; an optional timebox overrides the one-session
default.

## Example

```text
> /ca:spike can we stream large CSV exports without loading the whole file into memory? 2 hours

Question: can a 500MB export stream to the client without a full in-memory buffer?
Timebox: 2 hours. Confirm? (y/n)
> y

Branch spike/streaming-csv-export created.
[exploration — no plan, no tdd, no review]

Timebox reached. Answer: yes, a Node stream + res.write() loop holds memory flat at ~40MB regardless
of file size; the current buffer-then-send path is the only blocker.
Findings written to .codearbiter/spikes/streaming-csv-export.md.
Branch spike/streaming-csv-export deleted.
```

## When to reach for it

Reach for `/ca:spike` when you don't yet know if an approach works. Once you do, hand the findings to
`/ca:feature` — the implementation is written fresh, test-first, never copied from the spike branch.
