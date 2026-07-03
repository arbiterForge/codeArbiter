---
entity: agents/coverage-auditor
related: [skills/tdd, skills/subagent-driven-development]
---

## Role

Read-only auditor of test coverage against TDD obligations: checks the coverage percentage against the
project's maturity threshold, flags untested source files, and flags logical gaps (missing
boundary/negative-path tests). Dispatched by the `tdd` skill's Phase 4 and by
`subagent-driven-development` as part of fresh-run verification after an author agent finishes.

## Why this model tier

Ships `model: haiku`. Comparing a coverage number against a threshold table and checking for the
presence of a test file is a mechanical, high-volume check rather than novel reasoning.

## What it emits

CRITICAL–LOW findings with the source/test path and the specific gap, a coverage-vs-threshold status
line, and a PASS/BLOCK gate status — HIGH or above blocks the change at the commit gate.
