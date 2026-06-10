---
description: Review the current diff with the reviewer fleet, funneled to one triaged verdict.
argument-hint: "[path]" (defaults to the current diff)
---

# /ca:review — diff review

Read-only review of the current change. Routes to `dispatching-parallel-agents`: dispatches the reviewer fleet by path matrix, dedupes, then funnels through `finding-triage` → `checkpoint-aggregator` to a single verdict. No code is modified.

## Flow

1. Resolve scope — `$ARGUMENTS` if a path is given, else the current diff.
2. Build the unit list by path matrix; each matched reviewer is one read-only unit:

   | Reviewer | Dispatched when scope touches |
   |---|---|
   | `security-reviewer` | auth, middleware, secrets, deploy/CI, any security-sensitive path |
   | `auth-crypto-reviewer` | authn, crypto, key handling, secrets |
   | `dependency-reviewer` | `package.json`, lockfiles, base images, dependency manifests |
   | `migration-reviewer` | DB migration file add/modify |
   | `coverage-auditor` | any source change (test coverage vs. obligations) |
   | `architecture-drift-reviewer` | code that may diverge from accepted ADRs in `.codearbiter/decisions/` |

3. Route to `dispatching-parallel-agents` with that unit list (read-only batch — no collision check).
   It dedupes overlapping findings, then funnels through `finding-triage` (severity + inline
   `[NEEDS-TRIAGE]` on out-of-scope items) → `checkpoint-aggregator` (single verdict).
4. Surface the aggregated verdict: findings by severity, file:line, remediation, and the applicable
   control from `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` for security findings.

## Severity

- **CRITICAL** — exploitable vuln, secret exposure, banned primitive, data-integrity breach.
- **HIGH** — significant compliance gap or unsafe pattern.
- **MEDIUM** — standards deviation or coverage gap.
- **LOW** — informational or style.

## Hard gate

Read-only — MUST NOT modify a file. BLOCK on any CRITICAL or HIGH finding: it must be resolved before
`/ca:pr`. MUST NOT consume raw reviewer output — only the `finding-triage` → `checkpoint-aggregator`
verdict. MUST NOT resolve a `[CONFIRM-NN]` surfaced during review by guessing.

## When NOT to use

- Opening a PR (reviews dispatch automatically) → `/ca:pr`.
- A periodic full-codebase sweep → `/ca:checkpoint`.
- A pre-implementation threat model → `/ca:threat-model`.
- A question about the code → `/ca:btw`.
