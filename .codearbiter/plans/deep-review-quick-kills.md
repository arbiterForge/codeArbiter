# Plan — deep-review-quick-kills

Spec: `.codearbiter/specs/deep-review-quick-kills.md`. Backend: **premium** (no `--farm`).
Branch: `sprint/deep-review-quick-kills` off `main`. Lands as type-homogeneous commits → one PR (not merged).

**Status ledger** (the resume column): `QUEUED` → `IN-PROGRESS` → `ACCEPTED` / `DROPPED`.
Each task is test-first via `tdd` (or `/ca:refactor` parity for T-09), two-pass reviewed, fresh-verified.

Ordered for fast safe value first; the two AUTO-CAUTION guard-resolution tasks are LAST.

## Slice 1 — Python task-board/lib safety & docs (commit: `fix(hooks)` + `docs(hooks)`)
- **T-01** (AC-01 / 0001) — `taskwrite.py`: atomic `open-tasks.md` write (`.tmp` + `os.replace`).
  *Verify:* new unittest injects a failure after open → original board intact; existing taskboard tests green. `QUEUED`
- **T-02** (AC-08 / 0008) — `_taskboardlib.py`: guard `set_state` (unknown `state`) + `promote` (unknown `mode`); document valid sets.
  *Verify:* unittests for bad state/mode (no KeyError, no silent auto-apply); `test_taskboardlib.py`/`test_taskwriter.py` green. `QUEUED`
- **T-03** (AC-09 / 0009) — `_hooklib.py` + `_sloplib.py`: add `name(args) -> type` API header block (comment-only).
  *Verify:* `py_compile` clean; no behavior diff; full hooks suite green. `QUEUED`

## Slice 2 — Python additive tests of existing behavior (commit: `test(hooks)`)
- **T-04** (AC-11 / 0011) — `test_hooklib.py`: custom `is_ci_path`/`is_deploy_path` extend+exclude via temp `security-controls.md`.
  *Verify:* new cases pass; mirror migration OB-02/03 shape. `QUEUED`
- **T-05** (AC-12 / 0012) — `test_post_write_edit_scope.py`: H-12 governed-path reminder integration (seed `governs:` ADR → assert `[H-12]`).
  *Verify:* `[H-12]` for governed path, none for ungoverned, exit 0. `QUEUED`

## Slice 3 — farm.ts robustness/diagnosability (commit: `fix(farm)`; rebuild farm.js)
- **T-06** (AC-02 / 0002) — `farm.ts`: per-command timeout (`FARM_GATE_TIMEOUT_MS`) on `run()`/gate/setup/mutation; tagged-timeout result; Windows tree-kill.
  *Verify:* vitest — a never-exiting command is killed, scheduler finalizes; typecheck. `QUEUED`
- **T-07** (AC-03 / 0003) — `farm.ts`: guard the `finally` worktree-remove; named `validate()` field errors; run-id + truncated crash stack in `farm-results.jsonl`/report.
  *Verify:* vitest for each (undefined-worktree path, null plan field, run-id present). `QUEUED`
- **T-08** (AC-04 / 0004) — `farm.ts`: `parseChatCompletion` outer-shape guard; `mutationCheck` object guard; replace `originals.get(c.file)!`.
  *Verify:* vitest — no-`choices` body → `ok:false`; string/number `score` → null; Map-miss preserves file. Then `npm run build`; `git diff --quiet farm.js`. `QUEUED`

## Slice 4 — ca-sandbox failure surfacing (commit: `fix(ca-sandbox)`; rebuild sandbox.js)
- **T-09** (AC-05 / 0005) — `create.ts`: check `docker create`/`cp` exit codes (abort w/ stderr); capture git stderr in `spawnAsync`/`defaultCloneRepo`.
  *Verify:* vitest (injected runner) — non-zero create/clone surfaces stderr, not a bare code. `QUEUED`
- **T-10** (AC-10 / 0010) — `create.test.ts`: pin `git@github.com::evil` rejected + single-colon scp accepted (existing behavior).
  *Verify:* vitest green. Then `npm run build`; `git diff --quiet sandbox.js`. `QUEUED`

## Slice 5 — statusline (commit: `perf(statusline)` + `refactor(statusline)`)
- **T-11** (AC-06 / 0006) — `statusline.py`: PID/ledger fast-path for `session_start`; mtime/per-render cache for `arbiter_state`.
  *Verify:* `test_statusline.py` — cached on unchanged inputs, re-read on change; output identical. `QUEUED`
- **T-12** (AC-07 / 0007, `/ca:refactor`) — reuse `_hooklib.frontmatter_enabled`/`arbiter_active` (drop local parser); extract cost ledger → `_ledgerlib.py` + test.
  *Verify:* UNMODIFIED `test_statusline.py` passes (parity); new `_ledgerlib` test; render identical. `QUEUED`

## Slice 6 — AUTO-CAUTION guard-resolution (commit: `perf(hooks)`; LAST, parity-gated)
- **T-13** (AC-13 / 0013) — `_hooklib.py`: mtime-keyed `security-controls.md` cache; import-time pre-compiled default globs.
  *Verify:* PARITY test — same `is_*_path` verdicts as today across the matrix; stale-cache impossible (mtime); cold-install + guard matrix green. If parity not cleanly proven → **DROP to hard-gate surface**. `QUEUED`
- **T-14** (AC-14 / 0014) — `_hooklib.py`: `project_root()` `.git`-walk with subprocess fallback.
  *Verify:* PARITY test — root byte-identical to `git rev-parse --show-toplevel` incl. worktree/bare; falls back on ambiguity; guard matrix green. If parity not cleanly proven → **DROP**. `QUEUED`

## Landing (Phase 3)
- Version bump: `plugins/ca/.claude-plugin/plugin.json` (+ `plugins/ca-sandbox/.claude-plugin/plugin.json` since Slice 4 touches it) + README badge + dated CHANGELOG. Re-derive counts (no command/skill/agent count change expected).
- Full CI-parity sweep locally (hooks suites, cold-install, guard matrix, both `npm` toolchains incl. build-freshness, ref-graph, badge-consistency, JSON parse).
- `commit-gate` → `finishing-a-development-branch` auto-selects **open-PR** (NOT merged). Sprint Receipt + low-confidence harvest.

## Dependencies / notes
- Slices are independent except: T-08 build-freshness depends on T-06/T-07 (same file) → build farm.js once after Slice 3. T-10 build after Slice 4.
- T-12 depends on T-11 (same file, do perf-cache first, then refactor).
- T-13/T-14 are independent of each other; both LAST so a parity failure drops cleanly without blocking the rest.
- MVP slice (if scope must shrink): Slices 1–4 (the highest-value robustness + test wins, zero guard-resolution risk).
