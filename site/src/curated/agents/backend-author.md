---
entity: agents/backend-author
related: [skills/subagent-driven-development, skills/tdd, frontend-author, infra-author]
---

## Role

Writes backend and server-side code using the caller's selected verification approach: regression
RED/GREEN for confirmed fixes, criterion-focused feature checks, and passing characterization
baselines for refactors. It receives a bounded scope when delegation is useful and returns actual
results and pending checks. It may stage only when assigned and authorized.

Required security, authentication/crypto, migration and dependency reviewers still run when the
diff crosses their triggers. Input validation, error handling and project coverage requirements
apply regardless of the verification approach.

## Why this model tier

Ships `model: sonnet`. Writing correct server-side code — input validation, ORM usage,
framework conventions — needs implementation-grade reasoning, not just fact-gathering, which is why it
sits above the haiku-tier read-only reviewers.

## What it emits

Not findings — it writes source and test files directly (`Edit`/`Write`), plus the security-boundary
dispatch calls its own rules require. It hands the result back for the review chain that follows it.
