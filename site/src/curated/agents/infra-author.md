---
entity: agents/infra-author
related: [skills/subagent-driven-development, backend-author]
---

## Role

Writes infrastructure-as-code, containers, CI/CD manifests, and deployment configuration, mirroring
`backend-author` and `frontend-author` for the infra surface. It reads tech stack and security
boundaries from `.codearbiter/` before writing, and dispatches `security-reviewer` (mandatory before
staging) whenever a change touches network policy, IAM, or a container security context. Dispatched by
`subagent-driven-development` once the relevant planning phase has completed.

## Why this model tier

Ships `model: sonnet`. IaC idempotency, least-privilege IAM, and network-policy correctness are
implementation-grade judgment calls, the same tier rationale as the other author agents.

## What it emits

Not findings — it writes IaC, container, and CI/CD configuration files directly, plus the mandatory
`security-reviewer` dispatch its own rules require before anything with elevated permissions ships.
