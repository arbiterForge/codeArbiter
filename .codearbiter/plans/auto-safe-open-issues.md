# Auto-Safe Open Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development. Each task is reviewed for specification compliance and code quality before integration.

**Goal:** Clear the approved auto-safe issue set on one unmerged feature branch.

**Architecture:** Canonical shared Python changes live in `core/pysrc/` and are generated into both host payloads. Each task is implemented test-first in isolation, reviewed, and then integrated serially where shared statusline files overlap.

**Tech stack:** Python 3 stdlib hooks and unittest; TypeScript/Vitest/Astro docs site; Git worktrees.

## Global constraints

Use the exact constraints in `.codearbiter/specs/auto-safe-open-issues.md`. Never hand-edit generated hook copies, add Python dependencies, change default violet output, weaken a gate, merge to `main`, or overwrite the main checkout's audit-log modification.

## Task ledger

| Task | Deliverable | Focused verification | Status |
|---|---|---|---|
| 1 | #296 lossless concurrent ledger persistence and totals | `python -m unittest plugins.ca.hooks.tests.test_ledgerlib` plus deterministic collision tests | ACCEPTED |
| 2 | #297 linked-worktree branch resolution | focused `_gitlib`/statusline tests with realistic gitdir pointer | ACCEPTED |
| 3 | #299 exact statusline ownership | `test_wire_statusline.py` third-party/current/stale/restore cases | ACCEPTED |
| 4 | #298 bounded dirty-check latency | focused `_gitlib` tests with deterministic slow/failing runner | ACCEPTED |
| 5 | #278 deterministic prune timing | `python .github/scripts/test_prune_nudge.py` | ACCEPTED |
| 6 | #293 structural gate fixtures and #283 gate-event docs | targeted site Vitest, then site test/typecheck/build | ACCEPTED |
| 7 | #259 Codex bootstrap/payload audit and minimum remediation if needed | generated-surface checks, plugin refs, relevant adapter tests | ACCEPTED — closed with evidence |
| 8 | #300 immutable palette resolver and custom JSON | focused color/statusline tests across built-ins, malformed files, gradients, and `NO_COLOR` | ACCEPTED |
| 9 | #300 bounded subagent model display | focused subagent/statusline tests for one/mixed/absent/long IDs and narrow widths | ACCEPTED |
| 9a | User-approved emergent audit regressions | deterministic same-process and 3×24-process dual-host append tests | ACCEPTED |
| 10 | generation, full verification, commit gate, ready PR | sync/build checks, complete Python/site gates, branch review | ACCEPTED |

## Per-task protocol

For every behavior change: write the regression/feature test, run it and capture the expected failure, implement the minimum production change, rerun focused tests, refactor only while green, sync canonical outputs, and rerun focused tests. Sol then performs specification and quality review before marking the task accepted. Shared-core tasks are serialized; only disjoint site/test work may overlap.

## Landing

Integrate accepted commits onto `feat/auto-safe-open-issues`, run the complete gate from `.codearbiter/tech-stack.md` plus site tests/typecheck/build/link-audit and generated-source checks, push the branch, and open a ready PR to `main`. Preserve the integration worktree for user follow-up.
