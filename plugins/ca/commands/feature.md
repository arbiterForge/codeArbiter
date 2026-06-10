---
description: Start a feature the only sanctioned way — brainstorm a spec, get it approved, then drive it test-first through the pipeline.
argument-hint: "<what you want to build>"
---

# /ca:feature — spec-driven feature

The single permitted entry to implementation work. No feature code is written before a spec is approved and `tdd` Phase 1 clears. A one-line idea is not a spec — `brainstorming` makes it one.

## Step 0 — change-class triage (logged)

Before routing, classify the request. The **small lane** applies only when ALL of these hold —
judged against `$ARGUMENTS` and a quick look at the code, never assumed:

- the change touches ≤ 2 implementation files (plus their tests);
- no §4 reference-map scope-touch: auth/crypto/secrets, dependencies, migrations/schema, telemetry,
  public API surface, domain vocabulary;
- no new dependency, endpoint, command, or configuration surface;
- the behavior change is expressible as 1–3 concrete, individually testable acceptance criteria.

**Small lane:** state the mini-spec inline (the 1–3 criteria) and STOP for the user's one-reply
confirmation. On confirmation, append one line to `${CLAUDE_PROJECT_DIR}/.codearbiter/triage.log`
(append-only, `>>`):

```
[ISO-8601 timestamp] | BY: <git user.email> | LANE: small | SCOPE: <one-line> | BASIS: <criteria met>
```

Then route directly to `tdd` — the confirmed criteria are its Phase 1 obligations; Phases 2–6 run
unchanged — and exit through the full `commit-gate` and `finishing-a-development-branch` exactly as
the full lane does. The lane trims ceremony, never gates.

Any criterion violated, or uncertain → **full lane** (below). Uncertainty is full-lane; the triage
never guesses.

## Flow — full lane

Route through the pipeline in order; each step gates the next:

1. **`brainstorming`** — refine `$ARGUMENTS` into a concrete spec by Socratic questioning: challenge
   vague language, surface hidden complexity, force trade-offs. Writes the spec to
   `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md`. **Hard gate: no plan and no code until the
   user approves the spec.** Genuinely-unresolved unknowns become `[CONFIRM-NN]` in
   `open-questions.md`, never guesses.
2. **`writing-plans`** — decompose the approved spec into small tasks, each with an exact path and a
   verification that maps to a `tdd` obligation (it does not replace one). Writes
   `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.md` with bijective criterion↔task coverage.
3. **`executing-plans`** — coordinates the plan in small batches with human checkpoints. Each batch is
   delegated to `subagent-driven-development` (fresh author agent per task, spec-compliance review,
   quality review, fresh verification). The user acknowledges between batches; nothing advances until
   they do.
4. **`commit-gate`** — the only path to a commit; nine gates, including behavioral proof.
5. **`finishing-a-development-branch`** — terminal step: open-PR / merge-via-PR / discard. Every
   change lands through a PR; never a direct write to the default branch.

The autonomous counterpart (`/ca:sprint`) runs the same spec→plan but passes the full plan to
`subagent-driven-development` directly, without per-batch checkpoints. That path is its own entry,
not `/feature`.

## Scope routing

Scope determines which author agent `subagent-driven-development` dispatches per task:
`backend-author`, `frontend-author`, or `infra-author` — per the mapping in `tech-stack.md`. A
multi-area feature runs the appropriate agent per task; the full suite must be green before
transitioning between scope areas.

## When NOT to use

- A known defect with a reproduction → `/fix`.
- A behavior-preserving restructure → `/refactor`.
- A question or quick discussion → `/btw`.
- Persisting work already written → `/commit`.

## Hard gate

MUST NOT write feature code before a spec is approved AND `tdd` Phase 1 clears — the brainstormed
spec in the full lane, the user-confirmed mini-spec in the small lane. MUST NOT take the small lane
unless every Step 0 criterion holds, and MUST log the classification to
`.codearbiter/triage.log` before `tdd` begins. MUST NOT skip `writing-plans` in the full lane.
MUST NOT resolve a `[CONFIRM-NN]` in the spec by guessing — surface it.
