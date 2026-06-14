# Plan — farm: pluggable execution backend (v1)

slug: farm-pluggable-backend
spec: `.codearbiter/specs/farm-pluggable-backend.md` (APPROVED 2026-06-14)
created: 2026-06-14
mode: normal /ca:feature (premium subagents, sequential per-task; NOT a --farm sprint)

> Pre-flight note: `.codearbiter/coding-standards.md` does not exist. Not blocking — all paths are
> concrete from the spec and `tech-stack.md`. Canonical commands (from `tech-stack.md`, CI-authoritative):
> in `plugins/ca/tools`: `npm run typecheck`, `npm test`, `npm run build`; refs: `python
> .github/scripts/check-plugin-refs.py`.

## Acceptance-criterion ledger (from the approved spec, verbatim intent)

- **AC-01** — `Worker` interface extracted; HTTP-chat author becomes one impl; `runTask` depends on the interface, not `callApi`. Behavior-preserving: full existing suite passes unchanged.
- **AC-02** — interface receives resolved model/config; optional `task.model` added to schema + `Task` type, resolved `task.model ?? meta.model`; `additionalProperties:false` honored; SAFE_TASK_ID/schema-id divergence reconciled-or-noted, not silently widened.
- **AC-03** — outgoing worker request includes the read-only source of `task.test.path`.
- **AC-04** — outgoing worker request includes current contents of existing in-scope files (imports best-effort); test asserts test source AND a sibling's contents in the request body.
- **AC-05** — injected context byte-capped (configurable; default mindful of `FARM_REQUEST_TIMEOUT_MS`) and run through a NEW redaction over the `tech-stack.md` secret-pattern set; planted secret NOT transmitted (test).
- **AC-06** — task overlapping an unfinished sibling's `filesInScope` is removed from readiness (not just merge-serialized) until that sibling is green+merged; derived ordering (no `deps` cycle), id-tiebroken; test: two overlapping tasks green, second's worktree has first's change.
- **AC-07** — merge conflict → reset to new integration HEAD + re-run worker (one retry per D4) before escalating; post-loop merge moved into the attempt loop; test: forced conflict yields regeneration, not instant escalate.
- **AC-08** — `farm.js` appends each settled task to `.farm/farm-results.jsonl` (plus the final `farm-report.json`); test: two-task run → both results in completion order.
- **AC-09** — `farm-dispatch.md` + `subagent-driven-development` document completion-order consumption, Phase 3+5 per green, Phase 4 once-per-scope barrier, abort-reconcile via report (D7), temporal overlap = roadmap; `check-plugin-refs.py` passes.
- **AC-10** — `farm.md`, ORCHESTRATOR.md `/sprint --farm` section, `SPRINT.md`, `farm-dispatch.md` reframed to "pluggable backend (cheap/premium/agentic)"; name `farm` + `preview` status preserved; refs pass.
- **AC-11** — `farm.js` rebuilt with no stale build; typecheck + full test green; `plugin.json` version bumped and synced across `plugin.json`, README badge, dated `CHANGELOG.md` section.
- **AC-12** *(added mid-execution at user request, 2026-06-14)* — README "Feature Forge" section restructured for parallel form/function (an index table + consistent per-feature subsections), and the farm entry rewritten from the stale "cost-arbitrage / cheap Zen" framing to this feature's pluggable-backend reality; the intro's over-broad "each feature ships a dry mode" claim corrected; `#feature-forge` anchor and all internal links still resolve.

## Tasks

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|---|---|---|---|---|---|---|
| T-01 | `plugins/ca/tools/farm.ts` | `cd plugins/ca/tools && npm test` green — full existing suite unchanged; `runWorker`/HTTP call now invoked via a `Worker` interface, not directly | existing farm suite stays green (refactor parity); `runTask` depends on the interface | AC-01 | — | ACCEPTED |
| T-02 | `plugins/ca/tools/farm.ts` | `npm test` green — containment (`isInside`) + read-only-test guard relocated to a post-apply sweep in `runTask`; HTTP impl owns `extractFileBlocks`+write internally (D6); escape/test-protect/drift smoke tests still pass | apply step owned by the worker seam; containment runs post-apply for any worker type | AC-01 | T-01 | ACCEPTED |
| T-03 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/plan.schema.json` | `npm test` green incl. new unit test: a plan with `task.model` validates (schema, `additionalProperties:false` respected) and resolution picks `task.model` over `meta.model`; SAFE_TASK_ID vs schema-id divergence reconciled or explicitly commented | optional per-task model resolves `task.model ?? meta.model`; schema accepts the field | AC-02 | T-02 | ACCEPTED |
| T-04 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/farm.test.ts` | `npm test` green incl. new mock-server test asserting the request body contains the `test.path` source AND an existing in-scope sibling's contents; shared file-read helper reused by anti-gaming/mutation, not duplicated | `buildPrompt` injects test source + in-scope file contents via a shared reader | AC-03, AC-04 | T-01 | ACCEPTED |
| T-05 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/farm.test.ts` | `npm test` green incl. test: planted secret-pattern string in an in-scope file is NOT in the outgoing request body; total injected context respects the configurable byte cap | enrichment byte-capped + secret-redacted over the `tech-stack.md` pattern set | AC-05 | T-04 | ACCEPTED |
| T-06 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/farm.test.ts` | `npm test` green incl. smoke test: two scope-overlapping tasks both reach green with no merge conflict and the second's worktree contains the first's merged change | `ready()` excludes a task overlapping an unfinished sibling's `filesInScope`; id-tiebroken | AC-06 | T-02 | ACCEPTED |
| T-07 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/farm.test.ts` | `npm test` green incl. smoke test: a forced same-file conflict produces a regeneration attempt (reset to integration HEAD + re-run worker, one retry) rather than an instant `escalate` | post-loop merge moved into the attempt loop; conflict → regenerate-then-escalate | AC-07 | T-02, T-06 | ACCEPTED |
| T-08 | `plugins/ca/tools/farm.ts`, `plugins/ca/tools/farm.test.ts` | `npm test` green incl. test: after a two-task run `.farm/farm-results.jsonl` holds both task results in completion order; `farm-report.json` still written | each settled task appended to the JSONL stream as it settles | AC-08 | T-02 | ACCEPTED |
| T-09 | `plugins/ca/skills/subagent-driven-development/references/farm-dispatch.md`, `plugins/ca/skills/subagent-driven-development/SKILL.md` | `python .github/scripts/check-plugin-refs.py` passes; both docs describe completion-order consumption of the JSONL, Phase 3+5 per green, Phase 4 once-per-scope barrier, abort-reconcile via `farm-report.json` (D7), and temporal overlap as roadmap | documented dispatch contract matches the streaming rail | AC-09 | T-08 | ACCEPTED |
| T-10 | `plugins/ca/includes/farm.md`, `plugins/ca/ORCHESTRATOR.md`, `plugins/ca/SPRINT.md`, `plugins/ca/skills/subagent-driven-development/references/farm-dispatch.md` | `check-plugin-refs.py` passes; "pluggable backend (cheap/premium/agentic)" framing present, "cost arbitrage / cheap Zen workers" framing removed/softened; term `farm` and `preview`/Feature-Forge status intact | reframed positioning, name + preview status preserved | AC-10 | T-09 | ACCEPTED |
| T-11 | `plugins/ca/tools/farm.js`, `plugins/ca/.claude-plugin/plugin.json`, `README.md`, `CHANGELOG.md` | `cd plugins/ca/tools && npm run typecheck && npm test` green; `npm run build` then `git diff --quiet -- farm.js` (no stale build); `plugin.json` version bumped **2.3.1 → 2.4.0** (feat → minor) and identical in `plugin.json` + README badge (NB: badge is pre-existingly stale at `2.1.0-beta.6` — correct it to `2.4.0`) + a new dated `CHANGELOG.md` section | shipped build matches source; version synced across three places | AC-11 | T-01,T-02,T-03,T-04,T-05,T-06,T-07,T-08,T-09,T-10 | ACCEPTED |
| T-12 | `README.md` | `python .github/scripts/check-plugin-refs.py` passes; README renders; `#feature-forge` + internal anchors resolve; both forge features share a parallel structure (index table + per-feature subsections); farm entry reflects the pluggable-backend reframe, no "cost-arbitrage/cheap Zen" framing remains | README Feature Forge section has parallel form/function; farm entry accurate to shipped reality | AC-12 | T-10, T-11 | ACCEPTED |

## Order & MVP slice

Dependency order is linear with two short branches; no cycle. Build order:

`T-01 → T-02 → { T-03, T-04→T-05, T-06→T-07, T-08 } → T-09 → T-10 → T-11`

- **MVP slice (batch 1): T-01, T-02, T-03, T-04, T-05** — the Worker seam (incl. D6 apply ownership) + the per-task-model design hook + prompt enrichment. This is the escalation-rate win and the cross-model-ready spine; the highest-value, independently reviewable core.
- **Batch 2: T-06, T-07, T-08** — scheduling, regenerate-on-conflict, streaming rail (harness robustness + the pipeline primitive).
- **Batch 3: T-09, T-10** — dispatch-contract docs + positioning reframe (prose).
- **Finalize: T-11** — rebuild `farm.js` + version bump; depends on every prior task. Closes the single PR.

## Coverage proof (bijective)

- Every AC has ≥1 task: AC-01→T-01,T-02 · AC-02→T-03 · AC-03→T-04 · AC-04→T-04 · AC-05→T-05 · AC-06→T-06 · AC-07→T-07 · AC-08→T-08 · AC-09→T-09 · AC-10→T-10 · AC-11→T-11. ✓
- Every task advances ≥1 AC (see `covers` column). ✓

## Deferred (roadmap, from spec Non-goals — not in this plan)

- [NEEDS-TRIAGE] `farm.js` backgrounding for true temporal review overlap.
- [NEEDS-TRIAGE] cross-model second provider + cheap→premium ladder + cost telemetry (item 3 build).
- [NEEDS-TRIAGE] item-6 grab-bag: schema-validated output, adversarial second-model verify, budget-scaled depth, per-task journaling, live progress.

## Security / review note for execution

T-04/T-05 change what leaves the trust boundary to the third-party endpoint — `subagent-driven-development`
Phase 4 MUST dispatch `security-reviewer` over the combined diff of this feature.
