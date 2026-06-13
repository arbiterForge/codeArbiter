---
status: proposed
date: 2026-06-13
title: Treat plan.json gate commands and FARM_MUTATION_CMD as trusted operator-authored shell input
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/tools/farm.ts
---

# ADR-0002 — Treat plan.json gate commands and FARM_MUTATION_CMD as trusted operator-authored shell input

## Status
Proposed

## Context
`farm.ts` executes `plan.json` `gate.commands` / `test.command` and the `FARM_MUTATION_CMD`
environment variable verbatim via `cmd.exe /c` / `bash -c`. The 2026-06-13 security review
flagged this as an undeclared executable-input trust boundary: `plan.json` is effectively
executable input, and nothing recorded the trust model. SMARTS this session scored
*document the boundary* over *impose a content allowlist*.

## Decision
`plan.json` gate/test commands and `FARM_MUTATION_CMD` are trusted, operator-authored,
PR-reviewed shell input. They are length-capped (≤1024 chars) and run by design as the
deterministic gate; no content allowlist is imposed on them. The trust boundary is declared
in the `security-controls.md` boundary-crossings table.

## Alternatives considered
- **Content allowlist on gate commands** — over-engineers a trusted-operator input, fights the
  deterministic-arbitrary-gate design, and risks rejecting legitimate operator commands.
- **Leave the boundary undeclared** — a hidden executable-input boundary that confuses later
  readers and reviewers; Securable-weak.

## Consequences
Easier: an explicit trust model — reviewers know `plan.json` is executable input and review it
as such. Harder: correctness depends on PR-review discipline for `plan.json` content.

## Risks
A malicious or mistaken `plan.json` runs arbitrary shell on the dispatcher host. Accepted
because `plan.json` is operator-authored and PR-reviewed. **Revisit immediately if `plan.json`
ever ingests untrusted or third-party source** — that would invalidate the trust premise and
require a real allowlist or sandbox.
