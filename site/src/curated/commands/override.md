---
entity: commands/override
related: [conflict, audit]
gates:
  - gate: single-confirm log
    when: a routine gate is bypassed (lint, style, a non-security review finding)
    effect: one append-only line is written to overrides.log — timestamp, operator identity, gate name, reason — before the action proceeds
  - gate: security ceiling
    when: a security CRITICAL finding, the crypto/secret commit gate (H-09b/H-10b), or an irreversible operation is at stake
    effect: the single-confirm path is refused; the finding must be surfaced verbatim, acknowledged in your own words, and logged as a heavier SECURITY-OVERRIDE line before anything proceeds
---

## What it does

The sanctioned, logged escape hatch. A routine gate — a lint rule, a style check, a non-security
review finding — can be bypassed with a one-line confirm: the reason is validated, your identity is
read from `git config user.email`, and a permanent line is appended to
`.codearbiter/overrides.log` before the action proceeds. A security-critical stop takes a heavier
path instead: the specific finding is named verbatim, you acknowledge that finding in your own
words (a bare "yes" is declined), and a `SECURITY-OVERRIDE`-tagged line is logged before the bypass
is recorded. Under `/ca:sprint`, a security-critical override is always a hard-gate stop — never
auto-decided, even in autonomous mode.

## Usage

```
/ca:override "<reason>"
```

The reason must name the gate being bypassed and a real justification — a vague reason like
"just skip it" is rejected.

## Example

```text
> /ca:override "skip the coverage-auditor finding on the new formatter, it's test-only tooling"

Identity: dev@example.com (from git config user.email)
Logged:
  [2026-07-02T14:03:11Z] | BY: dev@example.com | GATE: coverage-auditor | REASON: skip the coverage-auditor finding on the new formatter, it's test-only tooling
Proceeding — override recorded in .codearbiter/overrides.log.
```

## When to reach for it

Only when a gate is actually standing in the way of a change you've decided is correct. Never
needed for work that clears every gate on its own. For a rule conflict between two sources rather
than a gate to bypass, that's `/ca:conflict`.
