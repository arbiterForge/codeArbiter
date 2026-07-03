---
entity: agents/frontend-author
related: [skills/subagent-driven-development, skills/tdd, backend-author, design-quality-reviewer]
---

## Role

Writes frontend and UI code — the implementation executor for the `tdd` skill's Phase 1 test
obligations, mirroring `backend-author` on the client side. It never writes implementation code before
a failing-test checklist exists, and it dispatches `security-reviewer`, `auth-crypto-reviewer`, or
`design-quality-reviewer` itself when the diff crosses their triggers. Dispatched fresh per task by
`subagent-driven-development`.

## Why this model tier

Ships `model: sonnet`. Component logic, state management, and accessibility all need
implementation-grade reasoning under TDD, the same rationale that puts `backend-author` at this tier.

## What it emits

Not findings — it writes component and test files directly, plus the security- and design-review
dispatch calls its own rules require, before handing the result to the review chain that follows it.
