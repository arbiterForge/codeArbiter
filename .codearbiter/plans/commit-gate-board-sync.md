# Plan — commit-gate board-sync chokepoint

Spec: `.codearbiter/specs/commit-gate-board-sync.md` (approved 2026-06-26). ADR-0008.
Branch: `feat/commit-gate-board-sync`.

## AC ledger (verbatim from spec)

- **AC-01** Classifier — done-flip positive: only change is `[~]`+started → `[x]`+done → *is-transition*.
- **AC-02** Classifier — start-flip and add positive: clean `[ ]`→`[~]`+date, and an appended queued
  `- [ ] <desc>`, each with no other change → *is-transition*.
- **AC-03** Classifier — arbitrary-edit negative: any change beyond a state-cell flip, its stamped
  date, or a single appended queued entry → *not-transition*.
- **AC-04** commit-gate `SKILL.md` Phase 6 retains a classified transition (not scope creep); other
  board edits still flag; names the classifier.
- **AC-05** commit-gate `SKILL.md` Phase 7 explicitly stages the classified board edit by path (no
  wildcard).
- **AC-06** commit-gate `SKILL.md` + `harvest.md`: raise-new harvest runs pre-commit (Phase 6→7),
  staged into the work commit, contingent default; must-survive follow-up → GitHub issue.
- **AC-07** `/ca:task` doc states transitions ride the work commit via commit-gate; `check-plugin-refs`
  stays green.
- **AC-08** `find_board_drift(board, merged_ids, today)` returns a `[~]`/`[ ]` task whose id ∈ merged_ids.
- **AC-09** `find_board_drift`: empty when the task is `[x]`; a merged_id absent from the board is
  surfaced as info (or ignored), never a board write or false done.
- **AC-10** `extract_task_ids(text)` yields dotted task-ids from merged-commit text; ignores non-id tokens.
- **AC-11** `/ca:standup` command runs the sweep as an advisory step that surfaces drift and never
  auto-flips — the fix routes through `/ca:task`.
- **AC-12** The reconcile entrypoint writes nothing to `open-tasks.md` — board byte-identical before/after.

## Tasks

Each task is implemented test-first via `tdd` (its verification *maps to* a tdd obligation; it does not
replace tdd's red/green/coverage gates). Status is the resume ledger.

| id | path(s) | verification | maps-to | covers | depends-on | status |
|---|---|---|---|---|---|---|
| **T-01** | `plugins/ca/hooks/_taskboardlib.py`, `.github/scripts/test_taskboardlib.py` | `python .github/scripts/test_taskboardlib.py` passes new `classify_board_diff` cases: done-flip+start-flip+add positive, arbitrary-edit negative | tdd obligations for AC-01/02/03 | AC-01, AC-02, AC-03 | — | ACCEPTED |
| **T-02** | `plugins/ca/hooks/_taskboardlib.py`, `.github/scripts/test_taskboardlib.py` | `python .github/scripts/test_taskboardlib.py` passes `extract_task_ids`: yields `v2.rev.0020` from sample log text, ignores non-id tokens | tdd obligation for AC-10 | AC-10 | — | ACCEPTED |
| **T-03** | `plugins/ca/hooks/_taskboardlib.py`, `.github/scripts/test_taskboardlib.py` | `python .github/scripts/test_taskboardlib.py` passes `find_board_drift`: drift-detected, clean-when-`[x]`, unknown-id-safety (no write/no false done) | tdd obligations for AC-08/09 | AC-08, AC-09 | T-02 | ACCEPTED |
| **T-04** | `plugins/ca/hooks/boardsync.py` (new), `plugins/ca/hooks/tests/test_boardsync.py` (new) | `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` — `reconcile` reads board read-only + merged-commit text from stdin, prints drift, and a temp board file is byte-identical after the run | tdd obligation for AC-12 | AC-12 | T-02, T-03 | ACCEPTED |
| **T-05** | `plugins/ca/commands/standup.md`, `.github/scripts/test_board_sync.py` (new) | `python .github/scripts/test_board_sync.py` asserts standup.md wires the advisory `boardsync.py reconcile` step with "never auto-flip"/"`/ca:task`" language; `python .github/scripts/check-plugin-refs.py` green | tdd obligation for AC-11 | AC-11 | T-04 | ACCEPTED |
| **T-06** | `plugins/ca/skills/commit-gate/SKILL.md`, `.github/scripts/test_board_sync.py`, `.codearbiter/tech-stack.md`, `.github/workflows/ci.yml` | `python .github/scripts/test_board_sync.py` asserts Phase 6 exemption clause (classified transition retained, arbitrary board edit still flags, names classifier); test registered in tech-stack.md + CI | tdd obligation for AC-04 | AC-04 | T-01 | ACCEPTED |
| **T-07** | `plugins/ca/skills/commit-gate/SKILL.md`, `.github/scripts/test_board_sync.py` | `python .github/scripts/test_board_sync.py` asserts Phase 7 explicitly stages the classified board edit by path (no wildcard) | tdd obligation for AC-05 | AC-05 | T-06 | ACCEPTED |
| **T-08** | `plugins/ca/skills/commit-gate/SKILL.md`, `.github/scripts/test_board_sync.py` | `python .github/scripts/test_board_sync.py` asserts harvest runs pre-commit (Phase 6→7, staged into the work commit, contingent default) and must-survive → GitHub issue; hard-rule line 133 updated | tdd obligation for AC-06 | AC-06 | T-07 | ACCEPTED |
| **T-09** | `plugins/ca/includes/harvest.md`, `.github/scripts/test_board_sync.py` | `python .github/scripts/test_board_sync.py` asserts harvest.md documents the commit-gate pre-commit harvest + contingent/must-survive rule; `check-plugin-refs` green | tdd obligation for AC-06 | AC-06 | T-08 | ACCEPTED |
| **T-10** | `plugins/ca/commands/task.md`, `.github/scripts/test_board_sync.py` | `python .github/scripts/test_board_sync.py` asserts task.md states transitions ride the work commit via commit-gate; `check-plugin-refs` green | tdd obligation for AC-07 | AC-07 | — | ACCEPTED |

## Shared-file ownership (sequential execution invariant)

Several tasks edit the same file; `subagent-driven-development` runs them sequentially so each author
sees the prior's working-tree edits. Rules to keep it collision-free:

- `plugins/ca/hooks/_taskboardlib.py` (T-01/02/03) and `commit-gate/SKILL.md` (T-06/07/08): each task
  **adds** its function/clause additively; never rewrite a prior task's addition.
- `.github/scripts/test_board_sync.py`: **created by the first prose task to run** (expected T-06);
  every later prose task (T-05/07/08/09/10) **appends** its assertions — create-if-absent, never clobber.
- Registration of `test_board_sync.py` in `.codearbiter/tech-stack.md` and `.github/workflows/ci.yml`
  is **idempotent** (add the line if absent) and owned by T-06.

## Order & MVP slice

Dependency order: T-01 → T-06 → T-07 → T-08 → T-09 (commit-gate chain, same file then harvest);
T-10 independent; T-02 → T-03 → T-04 → T-05 (reconciliation chain). No cycles.

- **MVP slice (the #142 fix — co-location, shippable alone): T-01, T-06, T-07, T-08, T-09, T-10.**
  Satisfies AC-01..07 — the primary mechanism that lands board flips with the work.
- **Increment (the backstop): T-02, T-03, T-04, T-05.** AC-08..12, the `/ca:standup` reconciliation
  sweep. In scope this feature (user chose both-in-one); ordered after the MVP slice.

## Coverage proof

Every AC covered: AC-01/02/03→T-01; AC-04→T-06; AC-05→T-07; AC-06→T-08+T-09; AC-07→T-10; AC-08/09→T-03;
AC-10→T-02; AC-11→T-05; AC-12→T-04. Every task covers ≥1 AC. Bijective. ✓

## Release invariants (executed at commit-gate / finishing, not a feature task)

`plugins/ca/**` changed → MUST bump `plugins/ca/.claude-plugin/plugin.json` `version`, the README
version badge, and add a dated `CHANGELOG.md` section (CI `version-bump` job enforces). Folded into the
work, not a trailing `chore(board)` — per ADR-0008's own thesis and `ca-version-bump-is-payload-scoped`.

## Out-of-scope / triage

- `[NEEDS-TRIAGE]` Docs-site mirrors under `site/src/content/docs/reference/commands/` (task.md,
  standup.md) drift from the plugin source after T-05/T-10. Sync as a fast-follow `docs(site)` change;
  not gated here (the plugin source is the governing surface).
