# Sprint spec: checkpoint-remediation-2026-06-12

**Approved:** 2026-06-12  
**Goal:** Close all actionable findings from the 2026-06-12 checkpoint. 4 workstreams, one PR.

---

## Workstream 1 — Security code fixes

| Finding | Change |
|---------|--------|
| B-1 `farm.ts:720` | Replace `git add -A` with `git add <worker.filesWritten>` |
| B-2 `farm.ts:626-627` | Add `t.id` character-set validation (`[A-Za-z0-9._-]`, max 64) in `validate()` |
| D-2 `farm.ts:845` | Add plan.json schema validation (gate.commands, test.path, filesInScope, apiBaseUrl) |
| D-3 `farm.ts:299-300` | Strip raw API response body from `priorFailure` before injecting into prompt |
| D-4 `_hooklib.py:108-116` | Emit `warn()` on every parse failure; document as explicit exception to fail-loud; do NOT change fail-open behavior (intentional resilience) |
| D-6 `farm.test.ts:75` | Refactor `runFarm()` from `exec()` to `spawn()` with explicit args array |
| N-1 `_prunelib.py:1082-1083` | Add `transcript_path` containment check (must resolve under `~/.claude/`) in `hook_run()` |
| N-3 `pre-bash.py:56` | Add comment on `LOG_TRUNC_RE` known shell-spelling gaps |
| D-7 `tmp/extracted/` | Delete stale artifact directory |

## Workstream 2 — Governance document

**D-1.** Create `.codearbiter/security-controls.md` with:
- Approved primitives: SHA-256 (SHA-2 family). Forbidden: MD5, SHA-1, DES, RC4.
- Secret store: `process.env` in CI context (`FARM_API_KEY`); this is the approved method for this project.
- Approved registries: `registry.npmjs.org`.
- Approved licenses: MIT, ISC, Apache-2.0, BSD-3-Clause.
- TLS: default Node.js; no `rejectUnauthorized: false` permitted.

**D-5 resolves via D-1** — `process.env` declared as approved store; no code change needed.

## Workstream 3 — Test coverage

New test files:

| File | Covers |
|------|--------|
| `tests/test_statusline.py` | `vlen`/`clip`/`pad`, `fmt_tok`, `_tx_accumulate` dedup, `ledger_update`, `seg_ctx_lines` pct thresholds, `sparkline` edge cases, `render()` no-crash |
| `tests/test_doctor.py` | `check_payload` (missing script, bad JSON, stale sibling), `check_repo` (enabled/dormant), FAIL/WARN/OK format |
| `tests/test_wire_statusline.py` | Fresh install, backup/restore on uninstall, idempotent refresh, corrupted JSON abort, `status` output |
| `tests/test_init_codearbiter.py` | Fresh scaffold, re-run guard, `--check` on scaffolded dir, sentinel invariant, `--stage` override |

Coverage additions to existing test files:

| Gap | Target |
|-----|--------|
| D-15 `prune-transcript.py` | `cmd_audit`, `cmd_report`, `resolve`, `is_live`, argparse flow |
| D-16 `post-write-edit.py` | `governs_index` cache-hit, cache-miss, fnmatch, GOVERNS_RE/STATUS_RE |
| D-17 `session-start.py` | `has_source` walk, CONFIRM count, task count, malformed-frontmatter path |
| D-18 `_prunelib.py` | `tail_is_settled` queue-op branch, `Config.from_env` all env vars |
| D-19 `_hooklib.py` | `frontmatter_enabled` BOM, unclosed, mixed case, no-frontmatter |
| N-9 `farm.test.ts` | Unit tests: `parseFileBlocks`, `antiGamingCheck`, `mutationScore`, `circuitBreaker` |
| N-10 `test_write.py` | Fix partial assertion (`verdict` captured from result) |
| N-11 `test_validators.py` | Clarify assertion with explicit comment |

## Workstream 4 — Documentation

| Finding | Change |
|---------|--------|
| D-20 + full README | Full audit of `README.md` against current state: version badge `2.0.1` → `2.1.0-beta.2`, feature descriptions, install instructions, command catalog, links — all updated to reflect v2.1.0-beta.2 reality |
| N-12 | `tech-stack.md:52` — clarify `marketplace.json` refers to `.claude-plugin/marketplace.json` |

## Acceptance criteria

1. All security code fixes pass existing test suite with no regressions
2. `security-controls.md` exists and is complete per the content above
3. `tests/test_statusline.py`, `tests/test_doctor.py`, `tests/test_wire_statusline.py`, `tests/test_init_codearbiter.py` all exist and pass
4. All coverage additions (D-15–D-19, N-9) pass
5. N-10, N-11 assertions strengthened
6. README fully updated; version badge reads `2.1.0-beta.2`
7. `tmp/extracted/` deleted
8. `tech-stack.md` marketplace.json reference clarified
9. Full test suite green (both Python and TypeScript where tools changed)
