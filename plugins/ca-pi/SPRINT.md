<!-- codeArbiter /sprint body. Loaded by the existing sprint command. -->

# /sprint - autonomous, assistive execution

The user's sprint request authorizes the agreed work. Build and maintain its spec and plan, then execute **without a second artifact approval system**. Make ordinary in-scope method decisions, record meaningful deviations, verify outcomes, and report real blockers. Do not make the user repeatedly certify prerequisites or evidence identities.

Keep one `WORK-ID` per actionable deliverable through restarts. Select an
existing exact ID or stable origin before creating another item through the
installed `hooks/work.py` facade. A cycle key groups multiple member IDs via
`set-cycle`; `cycle-view` is derived, with no second writable task ledger.
Single-outcome sprints may keep one work item. Attach only real spec and plan
identities to their owning work item and report the selected work or cycle view
as the human entry point. Local completion never certifies checks, PR delivery
or provider synchronization.

## Representation and resume

For new full sprint work or an existing HTML spec/plan, load `<plugin-root>/includes/artifacts.md` and use `_select_authoring_route` with the trusted root, slug, `workflow: sprint`, `lane: full`. New complete sprint artifacts default to canonical HTML through the pinned native writer. An existing Markdown pair remains Markdown; a complete same-extension spec/plan pair is authoritative. A mixed-extension or duplicate match is a STOP. A lone spec resumes in its exact format, and the next plan must use the same extension. Do not create, rename, or convert a counterpart to repair ambiguity.

**Resume first.** Resolve `_resolve_workflow_pair`. For an HTML pair, read state only through the installed engine `identity`, `index`, and symbol-scoped `read`. For a Markdown pair, use the existing Markdown status ledger. Resume either exact format without creating or consulting a shadow artifact. A task marked `IN_PROGRESS` requires inspection of running workers and partial work, not automatic redispatch. Do not demand a new approval because a session was restarted.

The HTML writer may refuse a genuinely invalid/missing payload; that means an artifact was not saved, not permission to invent a Markdown fallback. Ordinary safe investigation may continue. HTML `--farm` dispatch remains disabled.

## Backend

Default is the normal agent-assisted implementation engine. Delegate when it helps; **one fresh premium subagent and two reviewers per task are not mandatory**. `/sprint --farm` remains a separately requested legacy Markdown preview backend governed by `<plugin-root>/includes/farm.md` and `subagent-driven-development/references/farm-dispatch.md`: do not run without real provider configuration and budget, bypass its circuit breaker, or silently switch to premium on a failure. No model is selected, charged, or invoked by the artifact writer alone.

## Recorded intent before drafting

Perform the **recorded-intent read — BEFORE first material spec shaping, fail-soft**.
Read only relevant plan/decision index entries and expand cited records as needed.
Absent `plans/` or `decisions/` is never a STOP; it is
**intent: silent — no decomposition record**, not invented prior consent.

Do not silently contradict an accepted ADR or a recorded deferral when choosing
a different outcome. If the named re-evaluation trigger has occurred, the
decision is reopened; a current explicit owner direction also supersedes lower
priority history. Ask one consequential question when ownership is genuinely
unresolved: **one stop per record per sprint**, not repeated approval codes.
In the sprint log `intent:` goes AFTER the `confidence:` token for
the existing reader. When a conflict repeats, consider whether the planned
outcome is wrong **or the record itself is stale** before questioning the user
again. None of this is an approval prerequisite for routine work.

## Phase 1 - Establish a useful working agreement

Use `brainstorming` for a missing spec and `writing-plans` for a missing plan. Bound the sprint goal, requirements, relevant acceptance criteria, real dependencies, and genuinely consequential decisions. Prefer source evidence and existing project decisions; read applicable ADR titles/index first, and only relevant full bodies. A missing planning index is not another user STOP. Avoid bulk context loads and repeated interviews about answered requirements.

For HTML create the spec and plan as typed drafts. A `draft_preview` binding identifies the current source and can be maintained under the existing authorization. Use `validate` for structural/ready diagnostics. **Do not arm `arm-sprint`, `sprint-approve`, `delegate-methods`, or `smarts-apply` to obtain permission to make ordinary plans or choose methods.** Those are historical attestation operations, not prerequisites to this default workflow. An explicit requested human approval checkpoint remains real; do not infer one from an artifact state.

Identify factual prerequisites and scope them to the tasks they really affect. The agent can check a fact through an ordinary authorized tool and record a `prerequisite` observation; a tool result is not a decision made by the user. Ask the actual user about a consequential unresolved product choice. Do not ask to certify a hash, approve a nonce, or reapprove a plan because tests or steps changed.

The initial request bounds the work; it does **not** grant arbitrary future scope expansion, third-party spending, credential access, irreversible changes, merge, publication, or an override. Keep actual authorizations and explicit user limits intact.

## Phase 2 - Execute autonomously within the scope

Send the selected plan to `subagent-driven-development` with no artificial per-batch human pause. It reads compact task records, selects actual dependency-clean work, and implements or delegates coherent units. Use TDD where behavior changes benefit from test-first work. Tests, review, and evidence belong to their actual subject and risk; do not require a fixed number of reviewers or rerun them because a receipt ID changed.

**Deciding on behalf of the sprint:** use the user's intent and priorities to choose reversible implementation methods. Use SMARTS when a genuinely difficult trade-off warrants it, not as a six-lens tax on every step. Record material decisions in `.codearbiter/sprint-log.md` with reason and any meaningful uncertainty. A changed method, verification runner, or task decomposition within the agreed outcome is ordinary typed plan maintenance with a short reason, not a new user grant. A materially different product outcome is a question for the actual owner.
Per `<plugin-root>/includes/smarts/core.md`, an `Unknown` cell names its missing observation and whether it is decision-critical; an `Unknown` cannot bypass a hard gate or manufacture authority, and never stands in for user approval, a prerequisite or security authority.

For HTML, use receipt-free `task-start`, `task-review` (implementation reported ready), `task-reconcile` (reasoned progress correction), and `accept-scope` (reported implementation `DONE`) as appropriate. These labels **never certify a passing check, independent review, or released artifact**. Preserve applicable test output and state the exact outstanding checks. `eligible` is advisory scheduling; use `verification-status` only when an explicit historical attestation claim is actually needed, never to decide whether ordinary code editing may proceed.

## Actual stops

Stop affected work for an explicit user denial/stop, an unauthorized irreversible or destructive operation, a host/tool sandbox denial, a genuinely consequential missing product decision, or an independently applicable security, secrets, migration, or publication control. A security-critical finding requires resolving its risk, not faking a reviewer pass. Not every change mentioning authentication or an ADR automatically asks the user again when it is already within the agreed task; assess the actual risk and authorization.

A failing unit test, lint error, mismatched criterion, missing optional context map, changed receipt, or unsupported named-test parser is **not** another permission question. Record the failure and work on a correction or independent task. Do not equate a reported passing command exit with named-test-level proof it does not provide.

## Recovery without an approval ritual

Investigate the failed obligation and actual output. Fix the affected work, rerun the appropriate checks, and revisit only findings affected by the changed source or result. Do not spawn a full reviewer fleet or restart planning for routine implementation learning.

After process recreation, inspect workers and worktree state before changing an `IN_PROGRESS` record. Use `identity` and `eligible` for current advisory state, then a reasoned `task-reconcile` when needed. Never erase a user `BLOCKED` stop or rerun an uncertain attempt merely because its previous response was lost. Use the same journaled operation ID for an uncertain write and the engine's actual recovery operation. Old armed prompt/receipt history remains historical; it is not rearmed to permit progress.

If the same corrective strategy fails twice with no new diagnosis or evidence, change the approach or mark that task blocked with its actual cause; continue unrelated eligible work. Do not weaken tests, invent exceptions, or claim unrun verification passed.

## Phase 3 - Return an honest result

Summarize implemented changes, tests and checks **actually run**, unresolved defects/decisions, risk findings, and what still requires verification. Attribute meaningful autonomous decisions from the sprint log without requiring the user to read a long transcript.

If an authorized commit is requested, route through `commit-gate`, then `finishing-a-development-branch` for the chosen PR action. `/sprint` may open a PR under the existing authorized workflow; it must not merge to the default branch, publish a release, discard work, or bypass Git permissions without the appropriate separate authority. A local `DONE` batch is not a shipped release.

Harvest applicable follow-up tasks and decisions through `<plugin-root>/includes/harvest.md` without silently broadening this sprint or promoting an unresolved decision into authority. The requested work, not procedural gate count, determines when the sprint is finished.
