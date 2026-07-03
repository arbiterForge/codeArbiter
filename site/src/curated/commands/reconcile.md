---
entity: commands/reconcile
related: [adr, adr-status, conflict, skills/decision-variance]
gates:
  - gate: explicit choice per variance
    when: every variance presented
    effect: "you pick ratify, supersede, or surface as [CONFIRM-NN] — \"you decide\" or \"use your best judgment\" is declined; only your verbatim acceptance of the recommendation counts as a decision"
---

## What it does

Arbitrates variances between the project's three architectural artifacts
(`01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md`) and what the
scaffold or prior ADRs actually show. Every divergent, scaffold-silent, or artifact-silent case
gets a SMARTS analysis of its resolution options and a strength-labeled recommendation — but the
skill never arbitrates on its own. Each variance ends in exactly one of three user-chosen outcomes:
ratify the existing decision, supersede it (appending a new decision log entry and, if warranted, a
replacement ADR via `/ca:adr`), or surface it as an unresolved `[CONFIRM-NN]`. Called bare it runs
the full reconciliation pass; give it a target and it narrows to just that ADR, conflict, or
artifact.

## Usage

```
/ca:reconcile [<ADR-id | artifact | scope>]
```

Leave it bare for a full reconciliation pass; pass an ADR ID, artifact name, or other scope to
narrow it to one variance.

## Example

```text
> /ca:reconcile ADR-0004

Variance: ADR-0004 (fast-forward hotfix branch) vs. scaffold — divergent.
Artifact position: hotfixes may fast-forward directly to main.
Scaffold evidence: git-enforce.py H-01 blocks any direct commit to main, no hotfix carve-out found.

SMARTS analysis... recommendation: supersede (moderate).
Your call — ratify, supersede, or surface as [CONFIRM-NN]?
> supersede

Decision log entry appended, Decided by: dev@example.com.
Route to /ca:adr to author the replacement ADR? (y/n)
```

## When to reach for it

A variance already exists between artifacts, code, or prior decisions and needs a user-attributed
resolution. For a brand-new decision with no prior conflict, use `/ca:adr`; for ADR health alone,
use `/ca:adr-status`.
