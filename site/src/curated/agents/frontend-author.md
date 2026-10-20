---
entity: agents/frontend-author
related: [skills/subagent-driven-development, skills/tdd, backend-author, design-quality-reviewer]
---

## Role

Writes frontend and UI code using the caller's selected verification approach: regression RED/GREEN
for confirmed fixes, criterion-focused feature checks, and passing characterization baselines for
refactors. It receives a bounded scope when delegation is useful and returns actual results and
pending checks. It may stage only when assigned and authorized.

Security and authentication/crypto reviewers still run for applicable changes. User-facing UI
changes require design-quality review against rendered output. Component, interaction, error-state
and applicable accessibility checks remain part of the task's evidence.

## Why this model tier

Ships `model: sonnet`. Component logic, state management, and accessibility all need
implementation-grade reasoning under TDD, the same rationale that puts `backend-author` at this tier.

## What it emits

Not findings — it writes component and test files directly, plus the security- and design-review
dispatch calls its own rules require, before handing the result to the review chain that follows it.
