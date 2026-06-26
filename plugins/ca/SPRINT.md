<!-- codeArbiter v2 — /sprint: autonomous sprint mode. This is the mode body,
loaded on demand when /ca:sprint (commands/sprint.md) is invoked; the command
file is the thin entry point, this file is the procedure. -->

# /sprint — autonomous sprint

Brainstorm a sprint with the user, then execute it end-to-end — deciding "as the user" on everything
that is not a true hard gate. Every auto-decision is logged. Hard gates are real stops, rare by design.

## Execution backend: premium (default) vs. `--farm`

> **`--farm` is a Feature Forge `preview`** — shipped off by default and not yet validated on real
> runs. The premium subagent path is the blessed default. The promotion bar lives in
> `${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md` (CONFIRM-05).

`/sprint` runs the normal premium-subagent path unless invoked as `/sprint --farm`. The `--farm` flag
selects the pluggable execution backend: Claude still authors the spec, the failing tests, and the plan,
but a worker (not a premium subagent) implements each task behind the same hard gates. Thread the flag
into Phase 1 (`writing-plans --farm`) and Phase 2 (the farm dispatch path in
`subagent-driven-development`); if `--farm` is set, pre-flight `FARM_API_KEY` and BLOCK if absent,
citing `${CLAUDE_PLUGIN_ROOT}/includes/farm.md`, before brainstorming begins. Everything else about
`/sprint` (the one interactive gate, deciding-as-the-user, hard gates, logging) is identical between
backends. The worker-seam design (the cheap/premium/agentic policies the seam admits) lives in
`farm.md`; do not restate it here.

## Phase 1 — Sprint spec · gate: STOP

**Resume first:** if `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<sprint-slug>.md` and
`plans/<sprint-slug>.md` already exist for this sprint, do not re-brainstorm — confirm the resume
with the user and re-enter per `/feature`'s Resume ladder (approved spec + plan with non-`ACCEPTED`
tasks → straight to Phase 2, executing only the remaining tasks; the plan's `status` column is the
ledger). An interrupted sprint is re-entered, never restarted.

Route to `brainstorming`, scoped to a **sprint** — a coherent chunk of work (several features or one
goal), not a single feature. Drive it to a concrete sprint spec at
`${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<sprint-slug>.md`, then to `writing-plans` for the task
breakdown at `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<sprint-slug>.md`.

This is the ONE interactive gate, and it is load-bearing: the thoroughness of the spec is what makes
hard-gate stops rare later. Capture the user's intent, priorities, risk tolerance, and any
explicit "decide it this way" steers here. STOP for explicit user approval of the sprint spec AND the
plan before autonomy begins. A blocking `[CONFIRM-NN]` is resolved here, with the user — never carried
into autonomous execution unresolved.

**`--farm` mode:** route the plan step through `writing-plans --farm`, which additionally writes each
task's failing test and co-emits `plans/<sprint-slug>.plan.json`. To preserve the MVP-slice philosophy
(and to cap the blast radius of a bad model), drive the farm **one MVP slice at a time**: emit and
dispatch the plan.json for the current slice, review/merge it, then plan the next slice with the merged
code in hand — rather than authoring every failing test in the sprint up front. The user approves the
sprint spec and the first slice's plan at this gate; subsequent slices proceed under the same autonomy.

## Phase 2 — Autonomous execution · gate: BLOCK

Hand the approved plan to `subagent-driven-development` and run it to completion WITHOUT per-batch
human checkpoints — that is the difference from `/feature`'s `executing-plans`. Each task is
test-first via `tdd`, two-pass reviewed, and proven on a fresh run.

**`--farm` mode:** `subagent-driven-development` detects `plan.json` and takes its farm path —
selecting a model (a canary probe over candidate Zen models, falling back to websearch), dispatching
`farm.js`, then routing every green task through the SAME spec-compliance + quality + fresh-verification
gates the premium path runs (Phases 3–5). Swapping the worker only changes who *writes* the code, never
whether it is *reviewed* — every farm-produced green task still routes through the full review chain. A farm escalation is handled per `subagent-driven-development`'s Phase 2.5
(re-dispatch via premium Phase 2, or `[CONFIRM-NN]` on a genuine spec gap), and a circuit-breaker abort
from `farm.js` (too many escalations) is itself a hard-gate surface: stop and tell the user the model
isn't capable of the slice rather than grinding through.

### Deciding "as the user"

At every point the framework would normally surface for the user's decision — a design choice, an
ambiguity, a trade-off, a non-obvious option — DECIDE rather than stop:

- Run the SMARTS 6-lens evaluation (the scoring in
  `${CLAUDE_PLUGIN_ROOT}/includes/smarts/core.md`) plus a project-correctness
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

Emit the sprint **Receipt** — the same win-summary shape `finishing-a-development-branch` Phase 4 uses,
widened to the whole sprint: what shipped; obligations covered and the gates that fired with what each
caught; secrets/regressions prevented; suite time; the auto-decision count with every `low`-confidence
call listed for review (cite `sprint-log.md`); any hard gates that tripped, each with the
planning/confidence signal; and any open `[NEEDS-TRIAGE]` items. Drawn from in-hand state, not a fresh
crawl. Close with exactly one warm, synthesizing sentence (per the orchestrator register) — earned,
never on a no-op run.

## Hard rules

- MUST log every auto-decision to `.codearbiter/sprint-log.md` — append-only, never edited, committed as a permanent audit artifact.
- MUST NOT auto-decide a hard gate: `security-controls`, crypto/secrets/auth, irreversible ops, `/override`/hotfix, or an unresolvable `[CONFIRM-NN]`. Halt and surface.
- MUST NOT merge to the default branch or discard autonomously — auto-select open-PR only.
- MUST NOT inherit `decision-variance`'s Rule 1 — `/sprint` decides as the user, reusing only the SMARTS scoring.
- MUST surface a repeated hard-gate-trip pattern as a planning/confidence signal, not grind past it.
- MUST, at sprint close, run the follow-up harvest (`${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`) in autonomous mode — auto-promote `confidence: low` `sprint-log.md` decisions and any open `[NEEDS-TRIAGE]` to `open-tasks.md` (work) / `open-questions.md` (decisions), each promotion SMARTS-scored and logged. A blocking decision is never auto-promoted — it escalates.
