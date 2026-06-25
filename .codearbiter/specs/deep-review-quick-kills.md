# Spec — deep-review quick-kills (v2.rev.0001–0014)

**Slug:** `deep-review-quick-kills` · **Lane:** sprint · **Status:** APPROVED 2026-06-24 by brennonhuff@gmail.com (run T-01–T-12 autonomously; PAUSE and wait for the user at T-13/T-14) · **Date:** 2026-06-24
**Origin:** the `deep-review-2026-06-24-root` audit (`docs/reports/2026-06-24-root/`). This sprint
implements only the **`[AUTO]` + `[AUTO-CAUTION]`** findings — the ones with no security-enforcement
surface. The `[HARD-GATE]` (0015–0025) and `[DECISION]` (0026–0027) tasks are explicitly OUT OF SCOPE.

## Goal

Land the 14 safe, mechanical hardening fixes from the deep review as a single reviewed PR — improving
farm/ca-sandbox robustness & diagnosability, statusline render cost, task-board/lib input safety, and
test coverage of existing behavior — **without changing any enforcement behavior**.

## Scope (in)

Two stacks. Each task carries its finding id(s), file:line, and a testable acceptance criterion.

### A. Python — task-board / lib safety & docs (no enforcement surface)
- **AC-01 (0001, migration-001):** `taskwrite.py` writes `open-tasks.md` atomically (`.tmp` + `os.replace`). A simulated crash after open leaves the prior board intact.
- **AC-08 (0008, dx-004/005):** `_taskboardlib.set_state` no longer raises `KeyError` on an unknown `state`; `promote` no longer silently auto-applies on an unknown `mode` (degrades or raises with a clear message). Valid value sets documented in docstrings.
- **AC-09 (0009, dx-007):** `_hooklib.py` and `_sloplib.py` headers carry the `name(args) -> type` public-API block (comment-only; zero behavior change).

### B. Python — additive tests of EXISTING behavior
- **AC-11 (0011, coverage-004):** `test_hooklib.py` covers `is_ci_path`/`is_deploy_path` custom extend+exclude via a temp `security-controls.md` (mirrors migration OB-02/03).
- **AC-12 (0012, coverage-005):** an integration test drives `post-write-edit.py` and asserts `[H-12]` for a governed path, none for an ungoverned path, exit 0.

### C. TypeScript — farm.ts robustness/diagnosability (rebuild farm.js)
- **AC-02 (0002, reliability-001):** a configurable per-command timeout (`FARM_GATE_TIMEOUT_MS`) kills a hung gate/setup/mutation child (tree-kill on Windows) and resolves a tagged timeout; the scheduler still finalizes `farm-report.*`.
- **AC-03 (0003, reliability-004/migration-004/observability-003):** the `finally` no longer passes an undefined worktree to spawn; `validate()` emits named errors for missing required plan fields; `farm-results.jsonl` lines + report header carry a run-id, and the crash note includes a truncated stack.
- **AC-04 (0004, dx-001/002/003):** `parseChatCompletion` returns `ok:false` (actionable) on a response with no `choices` array; `mutationCheck` guards `typeof`-object before `parsed.score`; the `originals.get(c.file)!` non-null assertion is replaced with a guard that preserves the file on a miss.

### D. TypeScript — ca-sandbox failure surfacing (rebuild sandbox.js)
- **AC-05 (0005, reliability-002/observability-004):** `defaultBuildImage` checks the `docker create`/`cp` exit codes and aborts with stderr; `spawnAsync`/`defaultCloneRepo` capture a bounded slice of git stderr into the thrown error.
- **AC-10 (0010, coverage-003):** `create.test.ts` pins that `git@github.com::evil` (double-colon) is rejected and single-colon scp forms accepted (EXISTING behavior).

### E. Python — statusline (display-only; refactor)
- **AC-06 (0006, performance-004/005):** `session_start` uses a PID fast-path (or ledger-cached start) and `arbiter_state` is mtime/per-render cached — typical re-renders do no full session scan and re-read state only on change.
- **AC-07 (0007, architecture-005/007):** statusline derives arbiter-enabled state from `_hooklib` (local parser dropped); the ~290-LOC cost ledger is extracted to `_ledgerlib.py` with its own test. Behavior-preserving (`/ca:refactor` discipline — unmodified statusline tests are the parity proof).

### F. Python — AUTO-CAUTION (highest attention; done last, parity-proven)
- **AC-13 (0013, performance-001/002):** `_hooklib` mtime-keys the `security-controls.md` read and pre-compiles the constant default glob sets at import. **Parity:** a stale-cache cannot feed a guard an old scope (invalidated on mtime); glob-match results are byte-identical to today across the guard test-matrix.
- **AC-14 (0014, performance-003):** `project_root()` resolves via a `.git`-walk in the common case (no subprocess), falling back to `git rev-parse` on any ambiguity. **Parity:** the resolved root is byte-identical to `git rev-parse --show-toplevel` across the guard matrix incl. worktree/bare; on any doubt it falls back.

## Scope (out) — hard rule

- NO `[HARD-GATE]` task (0015–0025): nothing touches the H-09b/H-10b/H-14 commit gates, CRYPTO_RE/
  SECRET_RE, the H-05 audit guards, the marker writers, or the container-isolation argv/mount/egress.
- NO `[DECISION]` task (0026–0027): CONFIRM-08/09 are the operator's.
- If any task is discovered mid-sprint to actually require an enforcement change, it is a **hard-gate
  stop** — halt, log, surface; do not auto-decide it into scope.

## Non-negotiable invariants (verification floor — all must hold at land)

- `python -m py_compile` clean on every touched hook; full hooks suite green
  (`python -m unittest discover -s plugins/ca/hooks/tests` + the `.github/scripts/test_*.py` set);
  cold-install + guard matrix unchanged-green (proves no enforcement regression).
- `plugins/ca/tools`: `npm run typecheck` + `npm test` green; `npm run build` → `farm.js` in sync.
- `plugins/ca-sandbox/tools`: `npm run typecheck` + `npm test` green; `npm run build` → `sandbox.js` in sync.
- `check-plugin-refs.py` (both plugins) + JSON-manifest parse + badge-consistency green.
- LF preserved on all `*.py`/`*.md`/`*.yml`/`*.json` (Windows Edit-tool CRLF-flip watch).
- Version bump: this touches `plugins/ca/**` (and `plugins/ca-sandbox/**`) on a published version →
  bump `plugin.json` (and the ca-sandbox `plugin.json`) + README badge + CHANGELOG, per the CI guards.

## Risk register (steers captured at the gate)

1. **AC-13/AC-14 are the real risk.** Both alter how the *guards* resolve their scope/root. Done LAST,
   test-first with explicit parity tests against current behavior; if parity can't be cleanly proven,
   that task is dropped to a hard-gate surface rather than shipped.
2. **AC-07 is a refactor**, not a feature — proven by *unmodified* pre-existing statusline tests
   (`/ca:refactor` discipline). A new `_ledgerlib.py` gets its own fresh test.
3. **Commit gate on hook files:** edits to `_hooklib.py` etc. may surface the H-09b/H-10b gate if the
   diff context touches a CRYPTO_RE/SECRET_RE line. That is a recordable security-pass (test-only/
   non-crypto, gate genuinely passes — AD-008 precedent), NOT a hard-gate stop, *provided* no actual
   crypto/secret line is changed.
