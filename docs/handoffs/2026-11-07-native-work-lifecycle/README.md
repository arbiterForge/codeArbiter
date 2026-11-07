# codeArbiter: Native work lifecycle closure
Agent handoff packet | 2026-11-07 | Execution target: `arbiterForge/codeArbiter`

## Mission

Deliver a single cohesive codeArbiter implementation PR that makes the native work system usable by existing projects. Repair legacy board adoption (#1084 and #1087), accept legitimate selected-item lifecycle changes through commit-gate (#1089), and leave truthful, evidence-based progress records.

**This is an implementation handoff, not implementation proof.** The handoff branch contains documentation only. Nothing in it has been merged to `main`, installed, published, or tested as a code change.

## Source and authority boundary

The review baseline is `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c` (the inspected `main` on 2026-11-07). Re-fetch and record the actual `main` head and issue/PR states before implementation. Code at the new head overrides this packet when changed. Do not treat a historical issue reproduction as current without re-running it.

The product-owner direction is ADR-0043: the state engine assists already-authorized work, preserves honest progress, bounded context, human-readable HTML, transaction safety, actual host permissions and explicit user stops. Do not build another approval system, fabricate authorizations, or turn normal progress into a verification receipt prerequisite.

## Files to read, in order

1. `01-EXECUTION-CONTRACT.md` - scope, dependencies, implementation sequence and work boundaries.
2. `02-ACCEPTANCE-AND-TEST-MATRIX.md` - discriminating tests, negative controls and evidence requirements.
3. `03-EVIDENCE-AND-SOURCE-MAP.md` - baseline facts, code owners, release distinctions and contradictions.
4. `04-MIGRATION-AND-ROLLBACK.md` - recovery, source preservation, rollout and cross-host requirements.
5. `05-FOLLOW-ON-AND-REPORTING.md` - excluded follow-ons, PR report template and owner decisions.
6. `handoff-manifest.json` - content hashes and packet identity.

## Deliverable

**One implementation PR** against `arbiterForge/codeArbiter` from a new feature branch based on *fresh* `main`, with red-before-green regressions, bounded code changes, generated derivatives, exact-head CI, and an evidence summary. A draft PR is acceptable if hosted/installed-host requirements remain incomplete; report limitations, do not call it finished. Do not merge, publish a release, modify remote Projects, or migrate any real consumer repository on the owner's behalf.

The handoff branch is a **read-only reference**: fetch it, inspect its documents using `git show`, then create a separate implementation branch from fresh `main`. **Do not merge the handoff branch into the implementation branch.**

## Expected result

A normal existing project can be inventoried, migrated explicitly and safely, resumed, and represented by stable native work IDs. A feature/fix/sprint can attach the correct spec/plan and update an in-scope work item in its own governed commit without a spurious scope-creep verdict. Work state, reported checks, actual verification and release/delivery observations remain separately truthful.

## Operator shorthand

Reproduction targets: [#1084](https://github.com/arbiterForge/codeArbiter/issues/1084), [#1087](https://github.com/arbiterForge/codeArbiter/issues/1087), [#1089](https://github.com/arbiterForge/codeArbiter/issues/1089).

Follow-on, separate security/gate issue: [#1088](https://github.com/arbiterForge/codeArbiter/issues/1088). Do not use the accidental git-variable evasion described in that issue. Apply approved repository governance and genuine host authorization.

The scope is strictly the personal `arbiterForge` organization. Exclude all downstream, employer and unrelated repositories or sessions.
