# Sprint spec — farm per-worktree dependency setup hook (#92)

**Status:** autonomous (`/ca:sprint` fully autonomous — user delegated the design decision; no interactive gate)
**Author attribution:** user (brennonhuff@gmail.com) delegated; design decided-as-the-user via SMARTS, logged in sprint-log.md (D-01…D-04).
**Surface:** `plugins/ca/tools/farm.ts`, `plugins/ca/tools/plan.schema.json`, `plugins/ca/tools/farm.unit.test.ts`, `plugins/ca/includes/farm.md` (+ rebuilt `farm.js`).
**Landing:** one PR closing #92.

## Problem

The farm cuts an isolated git worktree per task off the integration HEAD. `node_modules` (and other
dependency dirs) are gitignored, so a fresh worktree has none. Today this only works because the
prior sprint installed the toolchain at the repo-root `node_modules` and Node's resolution walks
**up-tree** from `.farm/worktrees/<id>/…` to the repo root. That is fragile and JS-only: a language
without up-tree resolution (Python venv, Cargo, Go modules in a subdir) gets no deps in the worktree,
so its gate (`pytest`, `cargo test`, …) fails for environmental reasons, not worker quality.

## Design decision (SMARTS, decided-as-the-user — D-01)

Three options weighed:

- **(A) Declarative setup hook — CHOSEN.** A list of shell commands (`meta.setup`, optional per-task
  `task.setup`) the dispatcher runs **in each worktree before the worker**. The command is the policy
  (`npm ci`, `pip install -r requirements.txt`, a symlink, …). Language-agnostic, deterministic, fits
  the existing `plan.json` contract, and is exactly the "setup hook" the issue names. Reuses the gate
  execution + validation machinery already in place.
- (B) Auto-symlink/copy `node_modules` into each worktree. Fast, but JS-only, and Windows symlink/junction
  permissions are brittle. Rejected — narrow and fragile.
- (C) Document up-tree resolution only. Zero code, but does not generalize beyond Node and leaves the
  real gap open. Rejected — non-fix.

**Sub-decisions:** setup runs at the **top of each attempt (after `resetWorktree`)** because the
inter-attempt `git clean -fd` wipes untracked deps — cost is bounded (happy-path tasks run it once)
(D-02). A failing setup command **escalates immediately** (environmental, not worker-fixable) rather
than consuming a worker retry (D-03). Setup is executed through the existing `runGate` mechanism (same
shell + exit-code semantics) rather than a new dependency seam — DRY, zero churn to existing test deps
(D-04).

## Acceptance criteria

- **AC-1** — `plan.meta.setup` and per-task `task.setup` (both `string[]`) are accepted by `plan.schema.json` (added to the `additionalProperties:false` objects) and by `validate()`, which rejects non-string / empty / >1024-char entries with a clear message (mirroring `gate.commands`).
- **AC-2** — When effective setup is non-empty, its commands run **in the task worktree, before the worker, on every attempt** (after any inter-attempt reset), via the gate execution path.
- **AC-3** — A setup command that exits non-zero **escalates the task immediately** with a `setup failed: <cmd>` note (redacted tail), and the worker is NOT invoked that attempt.
- **AC-4** — With no `meta.setup` and no `task.setup`, behavior is **byte-identical to today** (no setup invocation, no extra shell call).
- **AC-5** — `task.setup` overrides `meta.setup`; `meta.setup` propagates to every task lacking its own. Resolution happens once at dispatch (main and canary).
- **AC-6** — `farm.md` documents the hook, the contract that **setup artifacts must be gitignored** (else they trip drift detection), and the per-worktree cost / when up-tree resolution makes it unnecessary.
- **AC-7** — `farm.js` rebuilt; full tools gate green (`npm run typecheck && npm test && npm run build`, `git diff --quiet -- farm.js`).

## Hard rules / scope

- No auth/crypto/secrets/TLS surface touched. Setup commands are author-supplied (same trust level as `gate.commands`), executed by the same redacting `runGate`.
- Drift contract: setup-produced files must be gitignored or they surface as drift — documented, not worked around (a setup that writes tracked files outside scope is correctly an escalation).
- Out of scope: auto-detecting WHEN to emit `setup` (a `writing-plans --farm` concern) — this PR ships the **dispatcher support + contract**; the plan author (or a future writing-plans step) populates it.
