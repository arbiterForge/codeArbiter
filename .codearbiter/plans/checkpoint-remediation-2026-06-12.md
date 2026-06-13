# Plan: checkpoint-remediation-2026-06-12

**Spec:** `.codearbiter/specs/checkpoint-remediation-2026-06-12.md`  
**Branch:** `checkpoint-remediation-2026-06-12` (new branch off current HEAD)

MVP slice: tasks 1–10 (all security fixes + governance doc). Test coverage in tasks 11–22. Docs in 23–24.

---

## Tasks

| # | Title | File(s) | Verification | Deps | Status |
|---|-------|---------|--------------|------|--------|
| 1 | B-2: Add t.id character-set validation | `plugins/ca/tools/farm.ts:750` (validate fn) | New vitest test: plan with `id: "../escape"` throws; plan with `id: "valid-id_1"` passes | — | TODO |
| 2 | B-1: Replace git add -A with explicit file list | `plugins/ca/tools/farm.ts:720` | New vitest test: task commit stages only filesWritten; no `git add -A` in source | 1 | TODO |
| 3 | D-2: Add plan.json schema validation for gate fields | `plugins/ca/tools/farm.ts:750` (validate fn) | New vitest test: plan with http apiBaseUrl rejected; plan with no filesInScope entries passes | 1 | TODO |
| 4 | D-3: Strip API error body from priorFailure | `plugins/ca/tools/farm.ts:299-300` | New vitest test: error with 500-char body produces priorFailure with generic code only, not body text | — | TODO |
| 5 | D-6: Refactor runFarm() exec() → spawn() | `plugins/ca/tools/farm.test.ts:69` | `npm run typecheck` passes; existing 10 vitest tests still pass | — | TODO |
| 6 | N-1: Add transcript_path containment check | `plugins/ca/hooks/_prunelib.py:1064` (hook_run) | New Python test: hook_run with path outside ~/.claude/ is rejected; path inside passes | — | TODO |
| 7 | D-18: Tests for tail_is_settled queue-op branch + Config.from_env | `plugins/ca/hooks/tests/test_hook.py` | New tests pass: tail_is_settled returns False when last line is queue-operation; Config.from_env validates all env vars | 6 | TODO |
| 8 | D-4: Emit warn() on read_input parse failure | `plugins/ca/hooks/_hooklib.py:108-116` | `python -m py_compile plugins/ca/hooks/_hooklib.py` passes; existing guard tests pass | — | TODO |
| 9 | N-3: Document LOG_TRUNC_RE limitations | `plugins/ca/hooks/pre-bash.py:56` | `python -m py_compile plugins/ca/hooks/pre-bash.py` passes; guard test suite passes | — | TODO |
| 10 | D-1: Create security-controls.md | `.codearbiter/security-controls.md` | File exists with all 5 required sections (primitives, secret store, registries, licenses, TLS) | — | TODO |
| 11 | D-7: Delete tmp/extracted/ | `tmp/extracted/` | Directory absent from `git status` / filesystem | — | TODO |
| 12 | D-19: frontmatter_enabled edge case tests | `plugins/ca/hooks/tests/` (new or existing test file) | New tests pass: no-frontmatter→(False,False); enabled→(True,False); unclosed→(False,True); BOM→parsed; mixed-case→(True,False) | 8 | TODO |
| 13 | D-15: prune-transcript.py CLI tests | `plugins/ca/hooks/tests/` (new test file) | New tests pass: cmd_audit/cmd_report on tempdir transcript; is_live threshold; resolve glob; argparse subcommand dispatch | — | TODO |
| 14 | D-16: governs_index cache tests | `plugins/ca/hooks/tests/` (new or existing test file) | New tests pass: cache-miss builds and writes cache; cache-hit returns data without rescan; superseded ADRs excluded; H-12 fires on matching path | — | TODO |
| 15 | D-17: session-start.py startup-state tests | `plugins/ca/hooks/tests/` (new test file) | New tests pass: has_source walk finds source vs not; CONFIRM count from open-questions.md; task count from open-tasks.md; malformed frontmatter → stderr breadcrumb | — | TODO |
| 16 | N-10: Fix test_write.py partial assertion | `plugins/ca/hooks/tests/test_write.py` | `python -m pytest` (or unittest discover) passes; test_rollback asserts `res["executed"] == False` and `"rolled-back" in res["verdict"]` | — | TODO |
| 17 | N-11: Clarify test_validators.py assertion | `plugins/ca/hooks/tests/test_validators.py` | Test still passes; comment clarifies what is and isn't being asserted | — | TODO |
| 18 | tests/test_statusline.py — pure-function layer | `plugins/ca/hooks/tests/test_statusline.py` (new) | New tests pass: vlen/clip/pad with ANSI codes; fmt_tok/usd_fine/human_dur; _tx_accumulate dedup; ledger_update two-session; seg_ctx_lines pct thresholds; sparkline edge cases; render() no-crash | — | TODO |
| 19 | tests/test_doctor.py | `plugins/ca/hooks/tests/test_doctor.py` (new) | New tests pass: check_payload missing script/bad JSON/stale sibling; check_repo enabled/dormant; FAIL/WARN/OK output format | — | TODO |
| 20 | tests/test_wire_statusline.py | `plugins/ca/hooks/tests/test_wire_statusline.py` (new) | New tests pass: fresh install; backup+restore on uninstall; idempotent refresh; corrupted JSON abort; status output | — | TODO |
| 21 | tests/test_init_codearbiter.py | `plugins/ca/hooks/tests/test_init_codearbiter.py` (new) | New tests pass: fresh scaffold creates all files; re-run without --check raises SystemExit; --check on scaffolded dir reports; CONTEXT.md lacks sentinel; --stage 3 writes stage:3 | — | TODO |
| 22 | N-9: farm.ts pure-function unit tests | `plugins/ca/tools/farm.test.ts` | New vitest tests pass: parseFileBlocks multi-block/path-traversal/test.path guard; antiGamingCheck literal vs computed; mutationScore 0/all-survive/all-killed; circuitBreaker escalation-rate | 1,2,3,4 | TODO |
| 23 | README full audit and update | `README.md` | Version badge reads 2.1.0-beta.2; command/skill/agent counts match current repo state; all stale content corrected | — | TODO |
| 24 | tech-stack.md marketplace.json clarification | `.codearbiter/tech-stack.md:52` | Line unambiguously refers to `.claude-plugin/marketplace.json`; no broken reference | — | TODO |
