---
description: Start a feature the only sanctioned way — brainstorm a spec, get it approved, then drive it test-first through the pipeline.
argument-hint: "<what you want to build>"
---

# /ca:feature — spec-driven feature

The single permitted entry to implementation work. No feature code is written before a spec is
approved and the `tdd` skill's Phase 1 clears. A one-line idea is not a spec — `brainstorming` makes
it one.

## Flow

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

The autonomous counterpart (`/sprint`) runs the same spec→plan but passes the full plan to
`subagent-driven-development` directly, without per-batch checkpoints. That path is its own (hidden)
entry, not `/feature`.

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

MUST NOT write feature code before the spec is approved AND `tdd` Phase 1 clears. MUST NOT skip
`writing-plans` for anything beyond a trivial single-file change. MUST NOT resolve a `[CONFIRM-NN]`
in the spec by guessing — surface it.
