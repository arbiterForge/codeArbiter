---
entity: agents/grader
related: [skills/decision-variance, decision-challenger]
---

## Role

Internal SMARTS analyst dispatched only by the `decision-variance` skill: takes one
artifact-position-versus-scaffold-evidence pair and produces a scored SMARTS analysis (Scalable,
Maintainable, Available, Reliable, Testable, Securable) with a recommendation strength. It never
decides — `decision-variance` dispatches a grader for a variance detailed or borderline enough to
warrant a structured second-pass evaluation, and analyzes obvious cases inline instead.

## Why this model tier

Ships `model: inherit`, matching whatever tier `decision-variance` is running at. A SMARTS analysis
quality-caps at the reasoning available, so inheriting keeps the grader as capable as the arbitration
it's supporting.

## What it emits

A structured SMARTS table (one row per lens, verdict-first, ≤25 words per cell), a preferred option
with a strong/moderate/tied recommendation strength, and a self-conformance checklist against the
format's hard constraints — never the arbitration decision itself.
