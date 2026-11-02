---
entity: commands/checkpoint
related: [tribunal, audit, status]
use_when: "You want the routine whole-codebase review sweep, with a triaged report of findings by severity."
avoid_when: "Reviewing only the current change, which is `/ca:review`; a rare deep audit, which is `/ca:tribunal`; or ADR health alone, which is `/ca:adr-status`."
asks: "Nothing. It takes no arguments and sweeps the whole codebase every time."
produces: "A dated report under `.codearbiter/checkpoints/` with findings by severity, and an updated `.codearbiter/last-checkpoint` baseline. No code is changed."
gates:
  - gate: reviewer fleet, funneled
    when: every invocation
    effect: security-reviewer, auth-crypto-reviewer, dependency-reviewer, migration-reviewer, coverage-auditor, and architecture-drift-reviewer run read-only over the whole codebase, then return a finding-triage and verdict-aggregator verdict before the caller separately dispatches the checkpoint writer
---

## What it does

A periodic whole-repository review. The caller supplies the reviewer unit list to
`dispatching-parallel-agents`; the read-only results pass through `finding-triage` and
`verdict-aggregator`. Only after that verdict returns does the caller separately dispatch
`checkpoint-aggregator` to persist every finding and incomplete-unit result.

The report uses `.codearbiter/checkpoints/YYYY-MM-DD.md`, with `-2`, `-3` suffixes when necessary.
Existing reports are never overwritten. The command then writes the nonblank, noncomment override
count to `.codearbiter/last-checkpoint`, re-zeroing the overrides-since-checkpoint display. That
integer is neither a timestamp nor a commit-gate receipt. A periodic report provides no promotion
sign-off and does not satisfy typed task acceptance.

The caller captures the reviewed commit, UTC review-start time and whether the worktree was dirty
before dispatch. The report retains these as `source_commit`, `recorded_at` and `worktree_dirty`;
missing observations remain unknown. Audit windows use these report anchors, not the counter.

[Checkpoints in context](/concepts/checkpoints/) explains the complete handoff and how to inspect
missing review evidence before routing follow-up work.

<details class="ca-evidence">
<summary>Limits and evidence: reviewers on Codex</summary>

Published releases from 0.7.5 include each packaged reviewer resource charter for Codex
host-provided agent threads. Exact static-package and route-closure checks gate release. A bounded
0.9.4 receipt proves one exact installed-charter review. The inline fallback applies only where the
canonical workflow explicitly permits it and isolation is not mandatory. See
[Claude Code + Codex → Intentional host
differences](/getting-started/claude-code-and-codex/#intentional-host-differences).

</details>

## Usage

```
/ca:checkpoint
```

Takes no arguments — it sweeps the whole codebase every time.

## Example

```text
Illustrative output, not captured execution:
> /ca:checkpoint

Read-only reviewer batch -> triage -> verdict.
Separate checkpoint writer retains the complete verdict.
Selected report: .codearbiter/checkpoints/2026-09-24-2.md
last-checkpoint: 12 (override-count baseline)
No code repair or delivery sign-off performed.
```
