---
entity: agents/authority-reviewer
related: [commands/feature, commands/sprint, skills/executing-plans, skills/subagent-driven-development]
---

## Role

Read-only independent reviewer for typed HTML plans on Claude Code. It performs the spec review of
one task, or the quality review of one checkpoint scope, against a target the artifact engine has
frozen. It is never dispatched by name: the authority adapter arms a request and returns an exact
launch envelope, and the orchestrator passes that envelope to the Agent tool unchanged. It has
Read, Grep and Glob only, so it can inspect the target but cannot change it.

## Why this model tier

The frontmatter pins no model. The armed launch envelope carries it instead (`opus` by default,
`sonnet` or `haiku` when the request asks for one), so the tier is part of the reviewed request
rather than a property of whichever lane dispatched it.

## What it emits

Exactly one `codearbiter.review-decision/0.1.0` JSON object: the request ID, the frozen target and
contract digests, a `pass` or `changes_requested` decision, the covered criteria, any findings,
and an assessment. The host hooks bind that answer to the exact launch call, the
reviewer's own child ID and its first stop, so a pasted or coordinator-written decision confers no
authority. Arming refuses when a project, session, user or managed agent could shadow the
reviewer's name.
