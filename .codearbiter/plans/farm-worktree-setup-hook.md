# Plan — farm per-worktree dependency setup hook (#92)

Spec: `.codearbiter/specs/farm-worktree-setup-hook.md`. Test-first. One branch `feat/farm-worktree-setup-hook`, one PR closing #92.
**Status:** COMPLETE — reconciled 2026-07-12 against shipped PR #96 and subsequent farm hardening.
Tools cwd = `plugins/ca/tools/`. Status: `PENDING` → `RED` → `GREEN` → `ACCEPTED`.

- **T1** `[ACCEPTED]` — RED: unit tests in `farm.unit.test.ts` (via `RunTaskDeps`, stubbing `runGate`):
  (a) a task with `setup: [...]` runs setup before the worker (runGate called with the setup commands prior to worker.apply);
  (b) a failing setup command → `status:"escalate"`, note matches `/setup failed/`, worker NOT called;
  (c) a task with no setup → worker called, runGate invoked only for the gate (unchanged).
  Plus `validate()` tests: `meta.setup`/`task.setup` with an empty or >1024-char entry throws; valid arrays pass.
  Files: `farm.unit.test.ts`. Verify: fails (setup unsupported). Maps: AC-1,2,3,4.
- **T2** `[ACCEPTED]` — GREEN: add `setup?: string[]` to `Task` and `Plan["meta"]`; in `runTask`, after the reset at the top of the attempt loop, run effective setup via `deps.runGate(wt, t.setup)` and escalate on failure before the worker. Files: `farm.ts`. Verify: T1 (a)(b)(c) green. Maps: AC-2,3,4.
- **T3** `[ACCEPTED]` — GREEN: `validate()` checks `plan.meta.setup` and each `task.setup` like `gate.commands` (non-empty strings, ≤1024). Files: `farm.ts`. Verify: T1 validate cases green. Maps: AC-1.
- **T4** `[ACCEPTED]` — GREEN: propagate `plan.meta.setup` → `task.setup` (fallback, not override) at dispatch in `main()` and `runCanary()`. Files: `farm.ts`. Verify: unit test for the fallback precedence (task.setup wins; meta.setup fills the gap). Maps: AC-5.
- **T5** `[ACCEPTED]` — schema: add `setup` (array of strings) to `meta` and `task` in `plan.schema.json` (both are `additionalProperties:false`). Files: `plan.schema.json`. Verify: schema parses; a plan with `meta.setup` validates. Maps: AC-1.
- **T6** `[ACCEPTED]` — docs: document the hook in `farm.md` — what it is, the gitignore/drift contract, per-worktree cost, and that JS up-tree resolution may make it unnecessary. Files: `plugins/ca/includes/farm.md`. Maps: AC-6.
- **T7** `[ACCEPTED]` — land: normalize touched files to LF (avoid the CRLF diff-bloat), `npm run typecheck && npm test && npm run build`, `git diff --quiet -- farm.js`, commit-gate, open PR closing #92. Maps: AC-7.

## Coverage

AC-1→T1/T3/T5, AC-2→T1/T2, AC-3→T1/T2, AC-4→T1/T2, AC-5→T1/T4, AC-6→T6, AC-7→T7. ✔

## Execution

One branch off `main`. T1 (RED) → T2/T3/T4 (GREEN) → T5/T6 (schema+docs) → T7 (land). No hard gate expected (no auth/crypto/secret surface). Autonomous: every non-gate decision SMARTS-scored and logged to sprint-log.md; surface anything `low` confidence in the morning summary.
