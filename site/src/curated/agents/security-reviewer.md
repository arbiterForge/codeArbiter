---
entity: agents/security-reviewer
related: [commands/review, commands/checkpoint, skills/commit-gate, skills/subagent-driven-development]
---

## Role

Read-only reviewer of authentication, authorization, secrets, deployment manifests, network policy, and
CI workflows against `.codearbiter/security-controls.md`. It is the broadest of the security reviewers
— dispatched proactively whenever a diff touches any of those surfaces, by `/ca:review`,
`/ca:checkpoint`, the `commit-gate` skill, and every author agent (`backend-author`, `frontend-author`,
`infra-author`) that crosses a security boundary.

## Why this model tier

Ships `model: inherit`, running at whatever tier the calling lane already committed. Because it is
dispatched from so many different contexts — a fast checkpoint sweep or a careful pre-commit gate — a
pinned tier would either overpay on the common case or underpower the sensitive one.

## What it emits

CRITICAL/HIGH/MEDIUM/LOW findings, each with a file:line, description, the violated `security-controls.md`
control, and a remediation. Blocks the PR on any CRITICAL or HIGH finding — an exploitable
vulnerability, an exposed secret, a banned primitive, or an undeclared security-boundary crossing.
