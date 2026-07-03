---
entity: agents/auth-crypto-reviewer
related: [skills/crypto-compliance, skills/secret-handling, skills/security-architecture, skills/subagent-driven-development]
---

## Role

Read-only reviewer of authentication, cryptography, key handling, and secrets, enforcing whatever
`.codearbiter/security-controls.md` specifies as the sole authority — including the approved-primitive
list — rather than a hardcoded compliance framework. It is dispatched by the `crypto-compliance` and
`secret-handling` gates whenever changed code hashes, signs, encrypts, or reads a secret, by
`security-architecture` on a threat-model pass, and by the author agents (`backend-author`,
`frontend-author`, `infra-author`) whenever a diff touches an auth or crypto boundary.

## Why this model tier

Ships `model: inherit`, running at whatever tier dispatched it rather than a pinned floor — the
calling lane (an author agent, or a dedicated crypto/secret gate) already commits the reasoning budget
this review needs.

## What it emits

CRITICAL/HIGH/MEDIUM/LOW findings, each with a file:line, the specific algorithm or value involved,
the `security-controls.md` control it violates, and a remediation. Hard-blocks the PR on any CRITICAL
or HIGH finding — a banned primitive, home-rolled crypto, disabled TLS verification, a secret outside
the approved store, or a shell-injection vector.
