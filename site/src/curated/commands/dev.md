---
entity: commands/dev
related: [arbiter, override]
gates:
  - gate: env gate
    when: CODEARBITER_DEV is not set to 1
    effect: refuses in one line and orchestration stays in force — dev mode is never a casual bypass
  - gate: append-only audit
    when: entering dev mode
    effect: an entry line is appended to overrides.log before orchestration is suspended, and the statusline turns alarm-red for the duration
---

## What it does

Suspends codeArbiter's orchestration so you can edit codeArbiter itself — skill, agent, command,
and hook bodies, `ORCHESTRATOR.md`, settings. It is not for project work; `/ca:override` covers a
single-gate bypass on ordinary project code, and this command declines that use.

Entry is gated behind the `CODEARBITER_DEV=1` environment variable specifically so it's a
deliberate maintainer posture, never a one-line accidental bypass. Once entered, an append-only
log line records who and when in `.codearbiter/overrides.log`, a gitignored marker file turns the
statusline alarm-red so the mode is unmistakable, and the session becomes a plain, direct coding
assistant — no routing, no skills, no gates, no `[CONFIRM-NN]` surfacing — until `/ca:arbiter` or a
new session.

## Usage

```
/ca:dev [note]
```

An optional free-text note is recorded alongside the entry log line.

## Example

```text
$ export CODEARBITER_DEV=1
> /ca:dev "fixing pre-bash H-03 regex"

[2026-07-02T14:02:11Z] | BY: dev@example.com | DEV: enter | NOTE: fixing pre-bash H-03 regex
dev-active marker written; statusline is now red.
Orchestration suspended — plain coding assistant mode until /ca:arbiter.
```

## When to reach for it

A single gate bypass on ordinary project work is `/ca:override "reason"`'s job, not this one's;
a plain question is `/ca:btw`'s.
