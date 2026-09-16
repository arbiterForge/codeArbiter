---
status: accepted
date: 2026-09-16
title: Adopt bounded authorization for routine cleanup, gated on a proven backend
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/includes/safety-core.md, core/surface/arbiter.md, core/surface/includes/routing-table.md, core/surface/commands/pr.md
---

# ADR-0036 — Adopt bounded authorization for routine cleanup, gated on a proven backend

## Status
Accepted — explicitly approved for authoring and acceptance by SUaDtL@users.noreply.github.com on 2026-09-16.

## Context

`core/surface/includes/safety-core.md` §6 currently requires a confirmation "even when intent is obvious" for every branch or worktree deletion, unconditionally, with no other backstop: no hook anywhere blocks `git branch -d` or `git worktree remove`, so that per-item confirmation is the entire safety control today. This was verified independently in-session by an adversarial (opus) review dispatched specifically to stress-test a commissioned proposal package ("Lifecycle cleanup & bounded authorization", spec.html/plan.html, 26 acceptance criteria and 12 tasks across two delivery slices) that argues for replacing unconditional per-item confirmation with a "bounded authorization" model: one explicit user instruction or accepted work-lifecycle scope authorizes an entire proven-safe batch (for example, "delete all proven-merged local branches") without re-confirming each item, backed by a new internal proof/mutation backend (fetched-target ancestry plus repository-qualified PR-record squash proof, and a guarded expected-OID conditional ref mutation) and a durable resource-ownership ledger that survives context compaction.

The same review found the proposal's factual claims about this repository accurate, and its direction sound, but under-priced: loosening confirmation before that proof/mutation backend exists and is independently trusted would flip a fail-safe control to fail-open with nothing mechanical underneath it — `core/pysrc/_standuplib.py`'s own docstring already justifies one of its broad worktree-candidate rules by name, saying it is safe specifically because per-item confirmation still backstops it. The review also found the proposal's own scope claims incomplete: `tools/sync-core.py` vendoring means "one internal helper" is really three files across four trees and three separate plugin version-bump surfaces; `core/surface/commands/pr.md`'s own body still requires per-item confirmation and was missing from the proposal's file list; `.worktrees.json` is prose-only with no code reading or writing it, so a proposed migration task would migrate nothing; and dropping tree-equality-only merge proof is a real capability loss when `gh` is unavailable that the proposal does not name.

## Decision

Bounded authorization is endorsed as the target direction for routine local cleanup. This decision supersedes no existing ADR and changes no confirmation behavior today. It authorizes future work to proceed on the proposal's inventory-hardening and proof/backend tasks without asking again, under one precondition: safety-core.md §6's unconditional per-item confirmation clause for branch or worktree deletion is not weakened, removed, or reworded by any change that cites this ADR as authority, unless and until a later ADR explicitly supersedes this clause after an authoritative inventory, an integration-proof evaluator, and a guarded mutation backend exist and have been independently reviewed. Until that later ADR is accepted, `core/surface/includes/safety-core.md`, `core/surface/arbiter.md`, `core/surface/includes/routing-table.md`, and `core/surface/commands/pr.md` remain governed exactly as they read today.

## Alternatives considered

- **Implement the full 12-task proposal now** — rejected: the in-session opus adversarial review returned NO-GO on implementing the full plan, or even its first delivery slice, in one sitting; this is a genuine multi-session campaign.
- **Reword the confirmation policy now and build the backend later** — rejected: this is precisely the fail-open path the review warned against, since the per-item confirmation is currently the only mechanical control and nothing today replaces it.
- **Decline the proposal outright** — rejected in favor of recording the direction, so that safety-positive, ADR-free groundwork (an authoritative branch/worktree inventory) has a clear destination and does not need to re-litigate this question later.

## Consequences

Inventory-hardening and proof/backend work can proceed without asking again, evaluated on its own merits and without needing a fresh ADR for each task. No wording in safety-core.md §6 or its dependents changes until a later ADR explicitly supersedes this one's gating clause with the named evidence in hand. `/ca:adr-status` will show this ADR as Accepted/Planned, not Implemented — recording the decision is not a claim that any part of the proposal has shipped.

## Risks

`status: accepted` under ADR-0033 means Accepted/Planned, not Implemented or Verified — so this decision could sit indefinitely as an "endorsed direction" while no concrete work proceeds, creating an appearance of momentum without any. Proven wrong if a future change cites this ADR to justify loosening safety-core.md §6's confirmation wording before the named backend exists and has been independently reviewed — that is exactly the fail-open regression this decision exists to prevent, and would mean this ADR's gating clause failed to hold.
