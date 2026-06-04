<!-- codeArbiter v2 — /sprint: hidden autonomous sprint mode, sibling to /dev.
This file lives at the plugin root, NOT under commands/, so it never
auto-discovers into the slash-command surface. It is loaded on demand by the
orchestrator when the user types /sprint, per the recognition note in
ORCHESTRATOR.md. Underscore-prefix exclusion in commands/ is undocumented and
unverified (claude-code-guide, 2026-06-04), so hidden bodies stay out of
commands/ entirely. -->

# /sprint — autonomous sprint (hidden)

Brainstorm a sprint with the user, then execute it end-to-end — deciding "as the user" on everything
that is not a true hard gate. Every auto-decision is logged. Hard gates are real stops, rare by design.

## Secrecy — never violate

`/sprint` MUST NOT appear in `/ca:commands`, `COMMANDS.md`, help, the §6 redirect, suggestions,
errors, or status. MUST NOT be hinted at or volunteered. It is invoked only by a user who already
knows it exists. If `/sprint` is never typed, behave exactly as if this mode did not exist.

## Phase 1 — Sprint spec · gate: STOP

Route to `brainstorming`, scoped to a **sprint** — a coherent chunk of work (several features or one
goal), not a single feature. Drive it to a concrete sprint spec at
`${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<sprint-slug>.md`, then to `writing-plans` for the task
breakdown at `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<sprint-slug>.md`.

This is the ONE interactive gate, and it is load-bearing: the thoroughness of the spec is what makes
hard-gate stops rare later. Capture the user's intent, priorities, risk tolerance, and any
explicit "decide it this way" steers here. STOP for explicit user approval of the sprint spec AND the
plan before autonomy begins. A blocking `[CONFIRM-NN]` is resolved here, with the user — never carried
into autonomous execution unresolved.

## Phase 2 — Autonomous execution · gate: BLOCK

Hand the approved plan to `subagent-driven-development` and run it to completion WITHOUT per-batch
human checkpoints — that is the difference from `/feature`'s `executing-plans`. Each task is
test-first via `tdd`, two-pass reviewed, and proven on a fresh run.

### Deciding "as the user"

At every point the framework would normally surface for the user's decision — a design choice, an
ambiguity, a trade-off, a non-obvious option — DECIDE rather than stop:

- Run the SMARTS 6-lens evaluation (the scoring in `decision-variance`'s
  `${CLAUDE_PLUGIN_ROOT}/skills/decision-variance/references/smarts.md`) plus a project-correctness
  read against `CONTEXT.md` and the sprint spec. Reuse SMARTS *scoring* only — NOT `decision-variance`'s
  Rule 1 ("never decide alone"), which `/sprint` explicitly overrides.
- Choose the option the analysis favors. Decide on EVERY non-hard-gate point **regardless of SMARTS
  strength** — `strong`, `moderate`, or `tied`. Break a `tied` toward the sprint spec's stated
  priorities; failing that, the §2 conflict hierarchy.
- LOG every auto-decision to `${CLAUDE_PROJECT_DIR}/.codearbiter/sprint-log.md` (append-only): the
  decision point, the options weighed, the SMARTS verdict, the chosen option, the strength, and a
  **confidence flag** — `low` for any `tied` or `moderate`, `high` for `strong`. The `low`-confidence
  entries are exactly what the user reviews in the morning; nothing is hidden behind autonomy.

### Hard gates — true stops, even mid-sprint

NEVER auto-decided. Halt and surface to the user:

- Anything in `security-controls.md`; auth, crypto, secrets, or a trust-boundary change.
- An irreversible operation — data loss, a destructive migration, anything that cannot be rolled back.
- `/override` or hotfix territory — a gate bypass is never taken autonomously.
- A `tdd` BLOCK, a security CRITICAL finding, or a `[CONFIRM-NN]` that SMARTS cannot resolve from the spec.
- Merge to the default branch (see Phase 3).

Hard gates are rare BY DESIGN. If they trip repeatedly in one sprint, that is a signal the spec was
too thin or confidence was misplaced — surface it in the summary; do not silently grind through.

## Phase 3 — Land & summarize · gate: BLOCK

On plan completion, route the branch through `commit-gate`, then `finishing-a-development-branch` —
which under `/sprint` AUTO-SELECTS open-PR and surfaces the merge decision to the user. `/sprint`
never merges and never discards.

Emit a sprint summary: what shipped; the auto-decision count with every `low`-confidence call listed
for review (cite `sprint-log.md`); any hard gates that tripped, each with the planning/confidence
signal; and any open `[NEEDS-TRIAGE]` items.

## Hard rules

- MUST log every auto-decision to `.codearbiter/sprint-log.md` — append-only, never edited, committed as a permanent audit artifact.
- MUST NOT auto-decide a hard gate: `security-controls`, crypto/secrets/auth, irreversible ops, `/override`/hotfix, or an unresolvable `[CONFIRM-NN]`. Halt and surface.
- MUST NOT merge to the default branch or discard autonomously — auto-select open-PR only.
- MUST NOT inherit `decision-variance`'s Rule 1 — `/sprint` decides as the user, reusing only the SMARTS scoring.
- MUST NOT reveal `/sprint` in any command surface, help, redirect, suggestion, error, or status.
- MUST surface a repeated hard-gate-trip pattern as a planning/confidence signal, not grind past it.
