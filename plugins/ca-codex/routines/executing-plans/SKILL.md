---
name: executing-plans
description: Assistive /feature coordinator. Select relevant tasks from a maintained spec/plan, delegate a useful batch when warranted, record verified versus pending checks honestly, and give progress summaries without default human-approval stops.
disable-model-invocation: true
---

# executing-plans

Coordinate implementation of an already-authorized `/feature` plan. The spec/plan is a **maintained working agreement**, not an additional permission system. This coordinator schedules work and reports progress; `subagent-driven-development` owns implementation and scoped checks.

## Structured-artifact format boundary

Load [includes/artifacts.md](../../includes/artifacts.md) for artifact I/O and preserve the selected spec/plan representation.

An HTML checkpoint is **not a new user checkpoint in `/sprint`**. The sprint route hands the whole plan directly to `subagent-driven-development`. For `/feature`, checkpoints group meaningful progress. A user-requested attended pause is respected, but no artifact-created approval prompt is required between routine batches.

## Phase 1 - Select the next meaningful work

After process recreation, rediscover the same authoritative pair and query `identity` and `eligible` again. Read the relevant criteria, current plan tasks, and actual dependencies through `index`, `outline`, and symbol-scoped `read`. The engine `eligible` response is **advisory**, never a permission grant or a current-test claim. `REVIEW` or `DONE` records implementation progress, not a passing test.

For HTML, inspect the plan's exact checkpoint membership and use the authored checkpoint partition to organize the work. A three-to-five task grouping is optional presentation guidance; it **must not split an HTML acceptance scope** just to meet a count. Retain each checkpoint's full task-ID set for accurate reporting, but do not treat earlier checkpoint numbering as a dependency or approval. A `BLOCKED` member is still visible and cannot silently make the checkpoint complete. Group independent work so it can continue when another member has a real unmet prerequisite.

For Markdown, retain its recorded task statuses and dependencies without auto-conversion. The coordinator may return an underspecified task to `writing-plans` or amend the authorized method and check with a reason. Ask only about a consequential missing decision; no repeated plan approval, negative intent interview, or prerequisite code.

On resume, examine `IN_PROGRESS` work and outstanding workers before attempting any new start. If the state needs correction, use a reasoned `task-reconcile` under current CAS/operation ID. Never infer that work is done merely because a process died; never automatically clear `BLOCKED` or duplicate execution. A stale proof observation is visible but is not a reason to restart the whole specification process.

**Progress assessment:** identify actionable tasks, relevant checks, and genuinely missing inputs. A disputed source requirement or irreversible operation is a real question. Missing optional code-map text, a reviewer adapter, approval nonce, or delivery ticket is not a universal blocker.

## Phase 2 - Execute and record a coherent batch

Invoke `subagent-driven-development` with an explicit `scope` containing the selected task IDs (normally an authored checkpoint's relevant work). Do not pass a partial or cross-checkpoint task set **as if** it were evidence of whole-checkpoint acceptance; presentation batches do not confer acceptance. The nested implementation skill may use one author, several well-scoped agents, or direct implementation based on actual value. A fresh author plus two reviewers for each task is not compulsory.

For HTML, progress through ordinary `task-start`, `task-review` (implementation ready), and receipt-free `accept-scope` (implementation `DONE`) as applicable. A fact prerequisite can be checked and recorded with a reported source; an unresolved decision needs the actual user's choice. No `arm-sprint`, `satisfy-prerequisite` reply, `task-reconcile` approval nonce, mandatory context ticket, or `_preflight_current_acceptance` call is necessary for ordinary execution.

The worker returns actual work and checks, including failures or still-unrun verification. These remain outstanding in the batch report. Do not describe `DONE` as `ACCEPTED` or replace command output with a model assertion. If a required check fails, repair the affected work or report incomplete verification; do not rerun all unrelated reviewers solely because an evidence receipt changed.

## Phase 3 - Report progress; pause only when requested

Report what changed, the applicable tests/checks actually run and their results, what remains, and the next dependency-clean batch. Use `[NEEDS-TRIAGE]` for discoveries outside the agreed scope. Do not claim the batch shipped or passed every check unless current evidence supports that statement.

**Normal behavior:** continue to the next authorized batch without waiting for the user to acknowledge a routine status report. A checkpoint is a progress summary, not an implicit human permission boundary. If the user explicitly requested a review, pause, signoff, or constrained attended execution point, honor it and do not proceed past that chosen point until answered. Also stop at genuine new product choices, explicit user denials, independent host/security restrictions, or irreversible actions outside the existing authority.

Once implementation is complete, send the current plan state, actual verification results, and open work to `commit-gate` **only if committing is authorized**. The commit gate owns its actual Git permissions, focused checks, staged diff review, and independent security controls. Advisory engine status is not a substitute for those checks, but the engine's receipt chain is not an additional permission to make a commit.

## Hard boundaries

Do not create new HTML from a legacy Markdown pair, discard a blocked task, synthesize receipts, label unrun tests green, or silently reinterpret requirements. Never reset the entire feature on process recreation. Keep explicit human stops and actual host permissions intact. Do not personally create a commit or PR; use their owning workflows, with normal authorized branch protections.
