---
entity: agents/backend-author
related: [skills/subagent-driven-development, skills/tdd, frontend-author, infra-author]
---

## Role

Writes backend and server-side code — the implementation executor for the `tdd` skill's Phase 1 test
obligations. It never writes implementation code before a failing-test checklist exists, and it
dispatches `security-reviewer`, `auth-crypto-reviewer`, `migration-reviewer`, or `dependency-reviewer`
itself when the diff crosses their triggers. Dispatched fresh per task by `subagent-driven-development`
(and by `dispatching-parallel-agents` for a batch of independent backend tasks).

## Why this model tier

Ships `model: sonnet`. Writing correct server-side code test-first — input validation, ORM usage,
framework conventions — needs implementation-grade reasoning, not just fact-gathering, which is why it
sits above the haiku-tier read-only reviewers.

## What it emits

Not findings — it writes source and test files directly (`Edit`/`Write`), plus the security-boundary
dispatch calls its own rules require. It hands the result back for the review chain that follows it.
