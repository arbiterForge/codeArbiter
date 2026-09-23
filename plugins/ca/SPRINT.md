<!-- codeArbiter v2 — /sprint: autonomous sprint mode. This is the mode body,
loaded on demand when /ca:sprint (commands/sprint.md) is invoked; the command
file is the thin entry point, this file is the procedure. -->

# /sprint — autonomous sprint

Brainstorm a sprint with the user, then execute it end-to-end — deciding "as the user" on everything
that is not a true hard gate. Every auto-decision is logged. Hard gates are real stops, rare by design.

## Structured-artifact boundary

For new sprint work or an existing `.html` spec/plan match, load
`${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md` before resume classification or artifact
I/O. Call `_select_authoring_route` with the trusted project root, slug,
`workflow: sprint`, and `lane: full`; use only its returned format and paths. For a selected HTML
route it checks the installed capability before writing; a missing or invalid
helper is a STOP and the workflow must not fall back to Markdown.
Its validated identity, authority, binding and task-state operations replace the
`.md` and status-column assumptions below for that pipeline. An existing `.md`
pair remains on the legacy path. Discovery requires a
complete same-extension spec/plan pair: select that exact pair as authoritative. A
mixed-extension or duplicate match is a STOP. A lone spec resumes in its exact format, and the
next plan must use the same extension. The workflow must not create, rename, or
convert its counterpart to repair ambiguity. New full-lane sprint specs use the
installed structured-artifact engine and default to canonical `.html`. The HTML
path must block `--farm` before canary
or dispatch; do not project it into legacy farm JSON.

## Execution backend: premium (default) vs. `--farm`

> **`--farm` is a Feature Forge `preview`** — shipped off by default. Historical runs informed its
> design but count as zero current qualification evidence. The premium subagent path is the blessed
> default. The fresh-evidence promotion bar lives in `${CLAUDE_PLUGIN_ROOT}/includes/farm.md`.

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

**Resume first:** discover this sprint's existing artifacts. Call the private
bridge resolver `_resolve_workflow_pair` with the trusted project root and sprint
slug; its returned paths and format own this resume. Select a complete
same-extension spec/plan pair as authoritative. A lone spec resumes in its exact
format, and the next plan must use the same extension. A mixed-extension or
duplicate match is a STOP. For an HTML pair, obtain state only through the
installed engine `identity`, `index`, and symbol-scoped `read` operations. For a
Markdown pair, use the existing Markdown status ledger. Resume either exact format
without creating or consulting a shadow artifact; the workflow must not create,
rename, or convert its counterpart. Do not re-brainstorm — confirm the resume
with the user and re-enter per `/feature`'s Resume ladder (approved spec + plan with remaining
dependency-clean `PENDING` tasks → straight to Phase 2, executing only those tasks; the legacy
plan's `status` column or the typed engine's execution ledger is authoritative for its own format).
`BLOCKED` tasks remain non-selectable until their owning reconciliation path records a supported
transition. An interrupted sprint is re-entered, never restarted.

Route to `brainstorming` (`${CLAUDE_PLUGIN_ROOT}/skills/brainstorming/SKILL.md`), scoped to a **sprint** — a coherent chunk of work (several features or one
goal), not a single feature. Drive it to a concrete sprint spec at the
route-selected spec path, then to `writing-plans`
(`${CLAUDE_PLUGIN_ROOT}/skills/writing-plans/SKILL.md`) for the task breakdown at the
matching route-selected plan path. New sprint work uses `.html` through the
installed engine.

This is the ONE interactive gate, and it is load-bearing: the thoroughness of the spec is what makes
hard-gate stops rare later. Capture the user's intent, priorities, risk tolerance, and any
explicit "decide it this way" steers here. STOP for explicit user approval of the sprint spec AND the
plan before autonomy begins. A blocking `[CONFIRM-NN]` is resolved here, with the user — never carried
into autonomous execution unresolved.

### Initial HTML approval sequence

The one interactive planning phase is not a new approval protocol. The installed adapter in
`${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md` approves one artifact at a time:

1. Review the sprint scope and findings, then arm the spec at its current identity. Require the
   exact returned reply and verify the spec's `approved` gate after the host observes it.
2. Pass that identity through `writing-plans`' approved-spec preflight, create and bind the plan,
   and review its task breakdown within this same planning phase.
3. Separately arm the plan, require its exact returned reply, and verify current spec and plan
   approval and binding. No execution before both approvals; one generic reply does not approve both.

Use the existing qualified host producer, never a model-authored event or SMARTS score in its place.
Keep this one scope review with no per-feature interviews, and do not add attended execution checkpoints.
Existing Markdown approval remains on its legacy path. Within a previously approved sprint, only a
supported producer can authorize a typed amendment; the delegation does not create an absent adapter.

**Recorded-intent read — BEFORE spec approval, fail-soft (ADR-0025):** consult
`decisions/decision-log.md`, the accepted-ADR index, the `plans/` artifacts' section headings, and
`open-questions.md`'s deferred sections — index-first, bodies only when the index names them
relevant. Surface AT THIS GATE every accepted ADR and open deferral the planned scope plausibly
touches, and capture the user's ruling on each in the approved spec ("conform" / "supersede via
`/adr` first" / "scoped exception, cite the ADR"). A ruling recorded here is a user decision: a
later in-flight collision with a pre-ruled record cites the ruling and proceeds. An absent
`plans/` or `decisions/` records `intent: silent — no decomposition record` in the sprint log and
proceeds — never a STOP.

**`--farm` mode:** route the plan step through `writing-plans --farm`, which additionally writes each
task's failing test and co-emits `plans/<sprint-slug>.plan.json`. To preserve the MVP-slice philosophy
(and to cap the blast radius of a bad model), drive the farm **one MVP slice at a time**: emit and
dispatch the plan.json for the current slice, review/merge it, then plan the next slice with the merged
code in hand — rather than authoring every failing test in the sprint up front. The user approves the
sprint spec and the first slice's plan at this gate; subsequent slices proceed under the same autonomy.

## Phase 2 — Autonomous execution · gate: BLOCK

Hand the approved plan to `subagent-driven-development` (`${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/SKILL.md`) and run it to completion WITHOUT per-batch
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
  `${CLAUDE_PLUGIN_ROOT}/includes/smarts/core.md`), beginning with its Step 0 recorded-intent check
  (ADR-0025 — in scope here by name), plus a project-correctness read against `CONTEXT.md` and the
  sprint spec. Reuse SMARTS *scoring* only — NOT `decision-variance`'s
  Rule 1 ("never decide alone"), which `/sprint` explicitly overrides.
- Choose the option the analysis favors. Decide on EVERY non-hard-gate point **regardless of SMARTS
  strength** — `strong`, `moderate`, or `tied`. Break a `tied` toward the sprint spec's stated
  priorities; failing that, the §2 conflict hierarchy.
- LOG every auto-decision to `${CLAUDE_PROJECT_DIR}/.codearbiter/sprint-log.md` (append-only): the
  decision point, the options weighed, the SMARTS verdict, the chosen option, the strength, a
  **confidence flag** — `low` for any `tied` or `moderate`, `high` for `strong` — and an
  **intent field**: `intent: per <source>` when Step 0 answered or constrained (an answered
  decision logs `confidence: high`, with the citation written in the verdict slot), `intent:
  silent` otherwise. On a heading line `intent:` goes AFTER the `confidence:` token, or on a body
  line — never before it: the harvest's positional parser takes the promoted title as everything
  before `· confidence:`. The `low`-confidence
  entries are exactly what the user reviews in the morning; nothing is hidden behind autonomy.

### Hard gates — true stops, even mid-sprint

NEVER auto-decided. Halt and surface to the user:

- Anything in `security-controls.md`; auth, crypto, secrets, or a trust-boundary change.
- An irreversible operation — data loss, a destructive migration, anything that cannot be rolled back.
- `/override` or hotfix territory — a gate bypass is never taken autonomously.
- A security CRITICAL finding, or a `[CONFIRM-NN]` that requires a missing user decision.
  An ordinary failing TDD/verification result instead takes Recovery within the approved sprint;
  it remains blocked from acceptance until the original gate and required reviews pass.
- An auto-decision that would contradict an accepted ADR or a recorded deferral rationale
  (ADR-0025). The valve, none of it auto-decided: a collision pre-ruled at the Phase 1 gate cites
  the ruling and proceeds (that ruling was a user decision); a deferral whose recorded
  re-evaluation trigger has occurred is reopened and surfaced, not treated as a contradiction;
  one stop per record per sprint — the first stop's answer is logged, later identical collisions
  cite it.
- Merge to the default branch (see Phase 3).

Hard gates are rare BY DESIGN. If they trip repeatedly in one sprint, that is a signal the spec was
too thin, confidence was misplaced, or the record itself is stale — route a repeatedly-tripping
ADR to supersession in the summary; surface it, do not silently grind through.

## Recovery within the approved sprint

A failed TDD, coverage, lint, or fresh-verification result blocks acceptance, not authorized repair.
This section applies only after initial spec-and-plan approval and only inside that approved scope.
Classify the failure before acting: an implementation defect or stale proof takes the owning repair
or reconciliation path; a real authority or security block takes the named Hard gates path.

Read the diagnostics and current state, give the author a corrective brief containing the failed
obligation and relevant evidence, and rerun the original gate plus every invalidated review.
Never redispatch merely to evade a failing gate. Do not weaken tests, invent an exemption, broaden
scope, or accept a self-reported pass to continue. Use SMARTS and the existing sprint log for material
method choices, not another approval interview for an already-authorized correction.

For HTML, load `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md` and use the exact current identity,
`eligible`, and applicable `task-reconcile` or `scope-reconcile` operations before redispatch.
Obtain a fresh complete context ticket and capture real policy events for every required receipt.
Never manufacture an approval or a receipt, edit execution cells, or create a shadow ledger.
An invalidated proof needs the appropriate fresh verification/review, not automatic reimplementation.

Unchanged failure plus unchanged inputs is not progress. After two consecutive corrective attempts
with the same failure and no new evidence, stop that retry strategy. Choose a different authorized
approach supported by a new diagnosis, or persist the stop before continuing independently eligible work.
For HTML, apply `task-block` with the exact current revision and model hash, then rerun `eligible`;
the blocked task and invalidated dependents must not be redispatched. For Markdown,
record the bounded blocked-task report in the authoritative plan and change that task's status to `BLOCKED`;
select only dependency-clean `PENDING` tasks whose dependencies are `ACCEPTED`.
`BLOCKED` tasks must not be redispatched until the owning plan/reconciliation workflow records a
supported transition. This is not automatically another user checkpoint. Ask only for the specific
missing fact or authority when that is the blocker; do not report the incomplete plan as accepted.

A `commit-gate` refusal returns to its named repair/reconciliation prerequisite. Recovery does not grant commit, provider, spending, disclosure, or publication authority. Security CRITICAL findings,
unresolved `[CONFIRM-NN]` decisions, irreversible operations, and all named Hard gates remain stops.
HTML farm remains disabled. This recovery path does not change farm-only intent or authorize a
silent premium fallback, another provider, or more spending after a farm circuit-breaker abort.

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
- MUST NOT auto-decide a hard gate: `security-controls`, crypto/secrets/auth, irreversible ops, `/override`/hotfix, an unresolvable `[CONFIRM-NN]`, or a contradiction with an accepted ADR / recorded deferral outside the ADR-0025 valve. Halt and surface.
- MUST run the recorded-intent read before Phase 1 spec approval — index-first and fail-soft: an absent `plans/` or `decisions/` logs `intent: silent` and never stops the sprint.
- MUST NOT merge to the default branch or discard autonomously — auto-select open-PR only.
- MUST NOT inherit `decision-variance`'s Rule 1 — `/sprint` decides as the user, reusing only the SMARTS scoring.
- MUST surface a repeated hard-gate-trip pattern as a planning/confidence signal, not grind past it.
- MUST diagnose and repair ordinary in-scope quality failures through Recovery within the approved sprint;
  never auto-pass a gate or treat recovery as additional authority.
- MUST, at sprint close, run the follow-up harvest (`${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`) in autonomous mode — auto-promote `confidence: low` `sprint-log.md` decisions and any open `[NEEDS-TRIAGE]` to `open-tasks.md` (work) / `open-questions.md` (decisions), each promotion SMARTS-scored and logged. A blocking decision is never auto-promoted — it escalates.
