---
name: tribunal
description: The deep, rarely-convened whole-codebase audit lane. Routed to when the user invokes /ca:tribunal. Seven gated phases — cost/model, map, roster dispatch, triage, report, approval+filing, telemetry. Costs on the order of millions of tokens; proceeds only after the user acknowledges the estimate; never a required gate; nothing filed or sent without explicit authorization.
---

# tribunal

The deepest, most expensive review codeArbiter offers — convened rarely, on demand, never as a gate. Routed to when the user invokes `/ca:tribunal`. Ten specialist lenses judge the codebase; every finding persists to its own file (plus append-only triage/run logs) under a run dir that survives compaction and disconnects, so the run resumes from disk.

## Pre-flight

Read these, or STOP and surface the gap — never guess a command or a path:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — stack, async model, concurrency primitives, test/lint/secrets commands, and, when documented, the tracker command. Stop if the test/lint/secrets commands are missing; do not guess.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` maturity value and domain vocabulary.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/coding-standards.md` — the conventions lenses judge against.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — trust boundaries, approved crypto/secret stores; feeds the appsec and secrets lenses. Absent on some repos — proceed without the security lenses' control-file checks if so.
- A git repository must be present.
- The reference set under `${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/` — each is cited at its phase, loaded on demand. Do not preload them.

## Phase 0 — Cost, model & resume · gate: STOP

This lane is expensive. Orient and get explicit go-ahead before dispatching anything.

- **Resume check.** If `.codearbiter/reports/<run-id>/` exists for today's scope, recover position with the cheap cursor scan in `references/schemas.md` (grep the last `wave-triaged`, do not read finding bodies) and offer to resume at the first un-triaged wave instead of restarting. On resume, skip the estimate.
- **Size the job.** Count LOC, file count, and language breakdown with the commands in `references/cost-and-models.md`.
- **Estimate cost.** Compute the token band from the v0 heuristic in `references/cost-and-models.md`. Present it plainly: the band, the inputs it came from, and that it is a rough estimate this run will help calibrate.
- **Recommend the model.** State that this lane should be driven by the highest-reasoning model available at high effort — a cheap model inflates false positives, and these findings file real issues. Name the concrete recommendation from the roster.
- **Offer cost control.** If the band is large, offer to narrow scope to a subtree, trim the Tier-2 lenses, or lower concurrency (`references/cost-and-models.md`).
- Establish `RUN_ID` = `<UTC-date>-<scope-slug>`; create `.codearbiter/reports/<run-id>/`; open `run.jsonl`.

Gate: the user has acknowledged the estimated cost and confirmed the model. An unacknowledged run does not pass.

## Phase 1 — Map + judgment overlay · gate: BLOCK

Map before reviewing; the map decides what gets scrutiny.

- Produce the inventory (inline, or on a large repo dispatch the optional cheap mappers per `references/cost-and-models.md`): file tree, language breakdown, entry points/routes, core-logic and shared-utility locations, dependency and integration surface. Write `inventory.md`.
- Apply the judgment overlay in `references/ai-markers.md`: risk-rank directories (untrusted input, money, auth, PII, churn = highest), mark trust boundaries, record AI-authorship markers and an iteration-depth estimate. High-marker / high-iteration areas carry a scrutiny boost and a small severity prior.
- Choose the active lenses — the full roster minus any whose concern is absent from scope (no migrations → drop the migration lens). Record launched/skipped as `run.jsonl` events.
- Choose the wave partition — the default in `references/cost-and-models.md`, or a repartition for cause — and record it in the `run-started` event (`references/schemas.md`); resume reads this recorded partition, never re-derives it.

Gate: `inventory.md` written with the risk/boundary/marker overlay, and the active-lens set recorded.

## Phase 2 — Roster dispatch (dual output: finding files + summary) · gate: BLOCK

Dispatch the active lenses in the wave partition recorded at Phase 1 (default in `references/cost-and-models.md`) at the concurrency from `references/cost-and-models.md` (≤5 in flight). Give each agent only its scope slice, on the model/effort from `references/cost-and-models.md`; the agent itself reads its own mandate (`references/lenses/<lens>.md`) and the finding contract (`references/finding-record.md`), and loads neither the other lenses' mandates nor the orchestrator schemas. The orchestrator reads `references/finding-record.md` to read findings at triage, and consults a lens mandate only to adjudicate that lens's finding.

- Each `tribunal-*` agent writes each finding to its own file `findings/<lens>/<finding-id>.json` the moment it is found — one file per finding, never a batched write at the end (write contract: `references/finding-record.md`).
- **Evidence-or-drop.** Every finding cites a concrete `path:line` and the minimal snippet. An absence claim — "no handler", "no teardown", "missing validation" — requires reading the whole unit, never a truncated window.
- Specialists never dispatch further subagents. Update each wave's status in `run.jsonl` as it flushes.
- When a lens's summary returns, record a `lens-completed` event in `run.jsonl` with `surface_seen`/`findings`/`model` taken from the agent's summary, plus `tokens` when the orchestrator can observe that lens's spend.

Gate: every active lens has flushed its `findings/<lens>/` files, and each wave's status is recorded.

## Phase 3 — Triage & per-wave planning · gate: BLOCK

Triage per wave from disk as soon as it flushes; do not wait for the whole run. Follow `references/triage.md`.

- **Dedup** against all findings already on disk by `dedup_key` and overlapping locations.
- **Calibrate independently.** Set `final_severity`/`final_confidence` from the evidence yourself — the lens's values are provisional input. Every critical/high carries a `counter_argument` (the strongest case it is lower or false); if compelling, downgrade. Promote under-rated findings too.
- **Low-severity discipline.** A `low` is kept only above the confidence gate (defined in `triage.md`) with a concrete fix; beyond ~5 lows per lens, roll the remainder into one finding that still lists each `path:line`.
- **Decide** each finding via the vocabulary; append one line to `triage.jsonl`. Below the confidence gate after calibration → `investigate` (medium/low) or `decision-required` (critical/high) — never dropped silently.
- **Plan** the wave: write `plans/phase-<n>.md` covering `keep`/`combine` findings grouped by type — shared approach, ordered sequence, cross-group `depends_on`, rolled-up acceptance criteria. Roadmap level, no per-finding code steps. A `decision-required` item gets a one-line "ADR-candidate — resolve via `/adr`" pointer, never an authored ADR.

Gate: every wave's findings triaged into `triage.jsonl` and a `plans/phase-<n>.md` written for its kept work.

## Phase 4 — Report · gate: BLOCK

Regenerate `report.md` and `manifest.yaml` from the two logs per `references/report.md` — projections, never hand-authored. Task-list-structured (not prose): findings grouped by **calibrated** severity then type, each with id, `path:line`, one-line description, remediation shape, triage decision, and a link to its phase plan; `decision-required` in its own section; a launched/skipped-lens summary; an investigate appendix. Apply `${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/` (`core` + `medium-documents`) to the prose.

State plainly that critical/high are blocking-severity findings — work that should block shipping the affected code — but that this lane is not itself a gate and blocks nothing.

Gate: `report.md` regenerated from the logs and presented. No issues created.

## Phase 5 — Approval & issue filing · gate: BLOCK

Findings become GitHub issues only on explicit selection and authorization. Follow `references/issue-filing.md`.

- **Select.** Ask which findings to file ("all keep+combine critical/high", or specific ids). Silence or ambiguity → file nothing. "Looks good" is not authorization. Offer `decision-required` findings as a **separate** opt-in (discussion issues), so design questions don't masquerade as fix tickets.
- **Dedup first.** Skip any finding already carrying an `issue_ref` in `triage.jsonl`; then search the tracker for an open issue matching each remaining finding's `dedup_key`/title and skip matches — this lane reruns over time and will re-find the same issues.
- **Bodies.** Generate `bodies/<finding-id>.md` lazily for selected `keep`/`combine` findings above the gate — approved-only. `decision-required` bodies are framed as question + options + evidence, not a fix.
- **File.** Default: write `issue-commands.sh` with a ready-to-run `gh issue create` per issue (tracker command from `tech-stack.md`) and print them. On explicit approval: execute; capture URLs; write `issue_ref` back into `triage.jsonl`.
- **Report.** A table: finding/group id → created URL, or skipped (duplicate), or failed (with the error). Never silently drop a failure.
- Findings file as GitHub issues, never `open-tasks.md` — a periodic-review finding must survive PR abandonment.

Gate: either `issue-commands.sh` written and printed, or — on approval — issues filed with the id→result table and `issue_ref` recorded. Nothing filed without explicit selection; no duplicates against the tracker.

## Phase 6 — Telemetry · gate: STOP

Optional, opt-in KPI feedback to refine the skill and the estimator. Follow `references/telemetry.md`.

- Assemble the KPI-only payload — aggregates and per-lens exposure counts only, scrubbed of code, paths, and finding text; no repo identity unless the user adds `--tag`.
- Write it to the run dir and show it in full. State plainly that the target is the public codeArbiter repo, so these aggregates post publicly.
- **Default:** print the ready `gh issue create --repo arbiterforge/codearbiter --label telemetry` command for the user to run. **On explicit approval:** post it.

Gate: the payload is shown, and it is either handed to the user as a command or — on approval — posted. No telemetry leaves without per-run authorization.

## Hard rules

- MUST NOT proceed past Phase 0 without the user acknowledging the estimated token cost — this lane can cost millions of tokens.
- MUST NOT edit, refactor, format, or commit project code — writes are confined to `.codearbiter/reports/<run-id>/` until the filing gate.
- MUST NOT act as a required gate or block a merge, commit, or other workflow — critical/high are blocking-severity findings, not a pipeline halt.
- MUST NOT record a finding without a concrete `path:line` and a minimal evidence snippet.
- MUST NOT assert an absence without reading the whole relevant unit — partial-window absence claims do not pass.
- MUST NOT let a lens's provisional severity/confidence stand as final — calibrate at triage; every critical/high carries a `counter_argument`.
- MUST NOT mutate the append-only logs — `manifest.yaml`, `report.md`, and `plans/` are regenerated from them, never hand-edited.
- MUST NOT file an issue below the confidence gate or without explicit selection and authorization; findings file as GitHub issues, never `open-tasks.md`.
- MUST NOT create a duplicate issue — skip findings carrying an `issue_ref`, and dedup against the tracker by `dedup_key`/title before filing.
- MUST NOT author or scaffold an ADR — `decision-required` findings file as a discussion issue; ADRs are authored only via `/adr` with user attribution.
- MUST NOT send telemetry without explicit per-run authorization, and MUST NOT include code, file paths, finding text, or repo identity (absent an explicit `--tag`) in the payload — KPI aggregates only.
- MUST NOT guess the test, lint, or secrets-scan command — read `tech-stack.md` or STOP. For the tracker: use `tech-stack.md` if it documents one; else default to `gh issue create` on a GitHub origin; else STOP.
- MUST NOT dispatch a subagent from within a dispatched specialist — only the orchestrator dispatches.
