---
description: Lightweight Q&A about the project — answer from context and return, no routing, no state change.
argument-hint: "<question>"
---

# {{CMD:btw}} — quick Q&A

The one exception to the slash-command pipeline. Answer the question and return. No skill is routed
to, no agent dispatched, no file written. Always safe to invoke.

## Flow

1. Read `{{PROJECT_DIR}}/.codearbiter/` docs as needed to answer accurately — `CONTEXT.md`,
   `tech-stack.md`, `coding-standards.md`, `security-controls.md`, `decisions/`, `specs/`, `plans/`.
2. Answer directly and conversationally — not a formatted report.
3. If the answer is not in context, say so plainly. Never guess.

## Hard gate

Read-only. MUST NOT write or modify any file, route to a skill, dispatch an agent, run tests, or
resolve a `[CONFIRM-NN]`. If the question is really a request to build or fix something, say so and
point to `{{CMD:feature}}` or `{{CMD:fix}}` — do not start implementation from `{{CMD:btw}}`.
