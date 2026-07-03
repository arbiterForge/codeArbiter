---
entity: agents/design-quality-reviewer
related: [frontend-author, skills/subagent-driven-development]
---

## Role

Read-only reviewer of generated, user-facing output — UI, reports, slides, charts, diagrams, CLI
output — against the `anti-slop-design` reference. It checks that a deliverable made deliberate,
brief-driven design choices instead of defaulting to the statistical center; it never reviews
codeArbiter's own internal framework docs. `frontend-author` dispatches it on any change that produces
or alters user-facing UI, the same way it dispatches `security-reviewer` for a security-sensitive one.

## Why this model tier

Ships `model: sonnet`. Judging whether a design choice was deliberate versus a reflex default (a
generic three-card layout, a fabricated chart number) is a nuanced call against a reference document,
not a fixed-pattern scan.

## What it emits

CRITICAL/HIGH/MEDIUM/LOW findings, each naming the artifact location, the violated `anti-slop-design`
rule, and a concrete fix. Blocks only on a data-integrity violation (a fabricated or unmarked number)
or a prose em-dash used as a sentence separator; everything else surfaces without blocking.
