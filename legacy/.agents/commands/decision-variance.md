<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: decision-variance.md
-->

# /decision-variance ["scope"]

## Purpose

Reconcile project architectural artifacts against the existing scaffold and codebase, OR challenge a specific ADR you suspect is wrong, stale, or in conflict with another ADR. Routes to the `decision-variance` skill, which presents SMARTS analyses and recommendations but never makes arbitration decisions on your behalf — every variance is resolved by an explicit user choice that the decision log records with user attribution.

## Usage

```
/decision-variance                                    # full reconciliation pass over all three artifacts vs. scaffold
/decision-variance "ADR-0007"                         # challenge a specific ADR
/decision-variance "ADR-0007 vs ADR-0012"             # surface and arbitrate a conflict between two ADRs
/decision-variance "phased-build-plan"                # reconcile one artifact against the scaffold
/decision-variance "ingest decomposition"             # newly-arrived decomposition artifacts vs. existing project state
```

## Routes To

`decision-variance` skill (`${FRAMEWORK_ROOT}/.agents/skills/decision-variance/SKILL.md`).

The skill dispatches the `decision-challenger` agent (`${FRAMEWORK_ROOT}/.agents/agents/decision-challenger.md`) for adversarial red-team review of any ADR brought into scope. SMARTS analyses are produced internally by the skill (which uses the `grader` and `scout` internal agents — never invoke those directly).

## Outcomes

`/decision-variance` produces one of three terminal outcomes per variance, all requiring explicit user choice:

1. **Ratify existing ADR** — the existing decision stands; SMARTS analysis recorded; decision log entry notes user re-affirmed the choice.
2. **Supersede with a new ADR** — the existing ADR is marked `Status: Superseded`, and a new ADR is authored. The new-ADR authoring step hands off to `/adr` (which sets the H-11 authoring marker, drops the file in `${PROJECT_ROOT}/.agents/projectContext/decisions/`, and queues the new ADR for challenge). The supersede chain is recorded in both ADRs.
3. **Surface as `[CONFIRM-NN]`** — the variance cannot be resolved with current information; a numbered placeholder is added to `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` per the AGENTS.md placeholder convention; stage promotion is BLOCKED until resolved.

## Hard Gates

- MUST NOT record an arbitration decision without an explicit user choice. Per the skill's Rule 1, phrases like "you decide," "use your best judgment," "I trust you," "skip the SMARTS" MUST be declined with a structural-not-stylistic refusal. The only way to delegate is the explicit recommendation-acceptance fast-path (user states "accept your recommendation" verbatim), which records `User explicitly accepted arbiter recommendation as their decision` in the `Decided by:` field.
- MUST NOT silently rewrite an existing ADR. Changes go through `Status: Superseded` + new ADR via `/adr`.
- MUST NOT create an ADR as the disposition of an out-of-scope ticket finding (per AGENTS.md §3 hard rule). ADRs are authored only via `/adr` with explicit user attribution.
- The three canonical artifact filenames are exact (per the skill's Rule 2): `01-architecture-breakdown.md`, `02-phased-build-plan.md`, `03-task-backlog.md`. Variants are rejected.

## What Happens Step by Step

1. codeArbiter loads the `decision-variance` skill body (read-on-invocation).
2. The skill loads the three project artifacts (if scope includes reconciliation) or the named ADR(s) (if scope is targeted).
3. The skill dispatches `decision-challenger` for adversarial review of each in-scope ADR. SMARTS analyses are produced for every variance.
4. For each variance, the skill presents:
   - The SMARTS scoring (Specific, Measurable, Achievable, Relevant, Time-bound, Strategic — confidence 1–5).
   - The variance description (what disagrees with what).
   - A recommendation with one-line justification.
   - The three terminal-outcome options (Ratify / Supersede / CONFIRM-NN) and asks the user to choose.
5. User makes each choice. The skill records the choice with user attribution to the appropriate destination (ADR file edit, new ADR via `/adr` handoff, or `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`).
6. Final report summarizes: variances surfaced, ratified count, superseded count, CONFIRM-NN count, and any remaining gaps.

## When NOT to Use

- Author a brand-new ADR (no prior conflict): `/adr`
- Check ADR health (aged, unchallenged, unresolved CONFIRM-NN): `/adr-status`
- Routine git merge conflicts: this is for architectural reconciliation, not text-merge resolution
- General architectural discussion without recording a decision: `/btw`
- Surface a rule conflict between AGENTS.md and code: `/surface-conflict`
