---
name: ca-review
description: Review a diff with the reviewer fleet, funneled to one triaged verdict. Targets the current working diff, a path, or an inbound GitHub PR.
argument-hint: "[path | #<pr> | <pr-url>] (defaults to the current diff)"
---

# /ca-review — diff review

Read-only review of a change. Routes to `dispatching-parallel-agents` (`<plugin-root>/routines/dispatching-parallel-agents/SKILL.md`): dispatches the reviewer fleet by path matrix, dedupes, then funnels through `finding-triage` → `verdict-aggregator` to a single in-memory verdict. No code is modified.

**The change under review does not have to be yours.** `/ca-review #123` reviews an inbound pull request through the same fleet, the same matrix, and the same triage. That is the point of issue #80: a tool that only reviews the diff you just wrote is a linter for authors, not a gate for a team, and reviewing code you did NOT write is where a governance gate earns its keep.

It is an ARGUMENT, not a second command. The scope resolver already took one, the fleet is scope-agnostic, and every phase downstream operates on a diff regardless of where it came from — so a `/ca-review-pr` would be a whole public surface (catalog, three host projections, README counts, sidebar) whose only distinguishing feature is where the diff was fetched from.

## Flow

1. Resolve scope from `$ARGUMENTS`:
   - **empty** → the current working diff (unchanged default).
   - **a path** → that path (unchanged).
   - **`#<number>`, a bare number, or a GitHub PR URL** → an INBOUND PR. Fetch its diff with
     `gh pr diff <number>` and review that. If `gh` is missing or unauthenticated, STOP and say so —
     do NOT silently fall back to the working diff, which would report a verdict on the wrong change
     under the PR's name.

   For a PR target, resolve the diff ONCE and review that text. Do not re-fetch per reviewer: the
   fleet runs in parallel, and a PR updated mid-review would otherwise have different reviewers
   reading different code and a triage that reconciles findings from two versions.
2. Before any substantive verdict, deliver task context to each actual reviewer.
   Use the changed paths from the resolved diff to select the current bounded
   packet with `_contextselectlib.select_task_context`; preserve the owning
   host's effective root/nested instruction order and the original source
   owner, scope/cwd, authority, and evidence epoch for each record. Identify
   task-critical source refs from the review obligation. Pass the packet and
   those refs to `_contextselectlib.prepare_review_input` for each reviewer,
   then include its `reviewer_input` in that reviewer's actual input. The
   returned `ready` state is a local preflight, not evidence that the host
   delivered the input; check that boundary before using the review result.
   For each actual reviewer, call `_contextselectlib.prepare_actor_delivery`
   with that selected packet, reviewer/task, absolute worktree and current
   source/host epochs. Send its bounded `delivery_text` with the review input
   on `deliver`, retain the counted attempt, and stop the substantive verdict
   on `blocked`. Re-select after resume, compaction, scope or worktree change;
   a parent session marker or author receipt cannot stand for reviewer delivery.
   Preserve applicable native instruction precedence. Source-scoped records,
   imported instruction text, map prose, and accepted ADR labels do not gain
   local normative authority by being copied into the packet.

   Bounded read-only source orientation and prerequisite inspection may happen
   before this preflight, including inspecting missing context. If a critical
   ref is missing or an applicable constraint conflicts, stop the substantive
   verdict and report the gap; do not block the bounded read-only inspection
   needed to resolve it. A stale or incomplete optional map, or a legacy
   provenance warning, remains visible and advisory unless it hides a named
   critical source. Review must not write context/native artifacts or any
   tracked or preexisting untracked file. Inventory only exact allowed
   transient host state, if the host creates any.
3. Build the unit list by path matrix; each matched reviewer is one read-only unit:

   | Reviewer | Dispatched when scope touches |
   |---|---|
   | `security-reviewer` | auth, middleware, secrets, deploy/CI, any security-sensitive path |
   | `auth-crypto-reviewer` | authn, crypto, key handling, secrets |
   | `dependency-reviewer` | `package.json`, lockfiles, base images, dependency manifests |
   | `migration-reviewer` | DB migration file add/modify |
   | `coverage-auditor` | any source change (test coverage vs. obligations) |
   | `architecture-drift-reviewer` | code that may diverge from accepted ADRs in `.codearbiter/decisions/` |

4. Route to `dispatching-parallel-agents` with that unit list (read-only batch — no collision check).
   It dedupes overlapping findings, then funnels through `finding-triage` (severity + inline
   `[NEEDS-TRIAGE]` on out-of-scope items) → `verdict-aggregator` (single read-only verdict).
5. Surface the aggregated verdict: findings by severity, file:line, remediation, and the applicable
   control from `<project-root>/.codearbiter/security-controls.md` for security findings.
6. **For a PR target, posting the verdict is a separate, confirmed step.** Report locally first; post only on explicit instruction, with `gh pr review <number> --comment --body-file <file>`. A review comment on someone else's PR is outward-facing and effectively public the moment it lands — it notifies subscribers and cannot be un-sent. Never `--request-changes` or `--approve` from here: those carry merge authority, and this command produces a finding list, not a maintainer's decision.

## Severity

- **CRITICAL** — exploitable vuln, secret exposure, banned primitive, data-integrity breach.
- **HIGH** — significant compliance gap or unsafe pattern.
- **MEDIUM** — standards deviation or coverage gap.
- **LOW** — informational or style.

## Hard gate

Read-only — MUST NOT modify a file, and MUST NOT check out, merge, or otherwise move the repository to the PR's branch: reviewing an inbound PR means reading its DIFF, not adopting its code, and a checkout would run its content through hooks that trust the working tree. BLOCK on any CRITICAL or HIGH finding on your OWN change: it must be resolved before `/ca-pr`. On an inbound PR there is nothing local to block — the verdict is the deliverable. MUST NOT consume raw reviewer output — only the `finding-triage` → `verdict-aggregator` verdict. MUST NOT resolve a `[CONFIRM-NN]` surfaced during review by guessing.

## When NOT to use

- Opening a PR (reviews dispatch automatically) → `/ca-pr`.
- A periodic full-codebase sweep → `/ca-checkpoint`.
- A pre-implementation threat model → `/ca-threat-model`.
- A question about the code → `/ca-btw`.
