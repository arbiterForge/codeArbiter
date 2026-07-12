# Plan — /ca:preview (#81)

Spec: `.codearbiter/specs/ca-preview.md` (approved). Stage 2. Effort M.

**Status:** COMPLETE — reconciled 2026-07-12 against shipped PR #87 and subsequent preview fixes/refactors.

**Architecture (resolved this session):**
- **[CONFIRM-06] → single prose include.** Extract the reviewer-to-path matrix to
  `plugins/ca/includes/review-matrix.md`; `review.md`, `pr.md`, `checkpoint.md`, and the new
  `preview.md` all cite it. Verified by `check-plugin-refs.py`. Kills the existing triplication.
- **Deterministic checks in a testable helper.** `plugins/ca/hooks/_previewlib.py` (stdlib-only per
  ADR-0004; imports `SECRET_RE` from `_hooklib.py`) does diff collection, the secret scan, and the
  test-gap check. The command prose orchestrates and does the matrix *prediction* by reading the
  include. No subagent dispatch; runs locally.

## AC ledger (verbatim from spec)

| ID | Acceptance criterion |
|---|---|
| AC-01 | Runs without onboarding (no `.codearbiter/`, no `arbiter: enabled`); does not require/trigger init/decompose/create-context or error on missing state. |
| AC-02 | Read-only: no file under `.codearbiter/` or elsewhere created/modified; `git status` unchanged. |
| AC-03 | Diff source = `git diff HEAD` + staged + untracked; all three change kinds appear in the reviewed-file set. |
| AC-04 | Graceful empty/no-repo: non-git dir and clean repo print "nothing to preview" and exit 0. |
| AC-05 | Matrix prediction by path (auth/crypto → security + auth-crypto; migration → migration-reviewer; dep manifest → dependency-reviewer; coverage-auditor for all). |
| AC-06 | Single source of truth: preview's predicted reviewer set equals review's dispatch set; mapping shared, not duplicated. |
| AC-07 | Real secret finding: a credential matching `SECRET_RE` in the diff reported as BLOCK-level, marked found/ran. |
| AC-08 | Real test-gap finding: a changed source file with no corresponding test reported, marked found/ran. |
| AC-09 | State-dependent honesty: the four rule-dependent reviewers shown "would run — sharper after onboarding," no fabricated findings. |
| AC-10 | Distinct from doctor: report describes reviewer/gate behavior on the diff, no hook-probe claims; `/ca:doctor` unchanged. |
| AC-11 | Onboarding nudge: report ends with the `/ca:init` → `/ca:review` upgrade path. |

## Tasks

| ID | Path(s) | Verification | maps-to (tdd obligation) | covers | depends-on | status |
|---|---|---|---|---|---|---|
| T-01 | `plugins/ca/includes/review-matrix.md` (new) | `python .github/scripts/check-plugin-refs.py` passes; file holds all 5 reviewer rows | "matrix include exists with the full reviewer-to-path table" | AC-05, AC-06 | — | ACCEPTED |
| T-02 | `plugins/ca/commands/review.md`, `pr.md`, `checkpoint.md` | check-plugin-refs passes; `grep` finds no inline matrix table left in the three commands | "the three existing commands cite the include, no duplicated table" | AC-06 | T-01 | ACCEPTED |
| T-03 | `plugins/ca/hooks/_previewlib.py` (new), `.github/scripts/test_preview_lib.py` (new) | `python .github/scripts/test_preview_lib.py` passes: collect_diff returns tracked+staged+untracked; non-git → empty sentinel | "collect_diff gathers HEAD+staged+untracked; empty/no-repo handled" | AC-03, AC-04 | — | ACCEPTED |
| T-04 | `plugins/ca/hooks/_previewlib.py`, `.github/scripts/test_preview_lib.py` | `test_preview_lib.py` passes: a fake key → secret finding; clean diff → none; uses `_hooklib.SECRET_RE` | "scan_secrets reuses SECRET_RE, flags credential lines" | AC-07 | T-03 | ACCEPTED |
| T-05 | `plugins/ca/hooks/_previewlib.py`, `.github/scripts/test_preview_lib.py` | `test_preview_lib.py` passes: changed source w/o adjacent test → finding; with test → none | "find_test_gaps flags changed source lacking a test" | AC-08 | T-03 | ACCEPTED |
| T-06 | `.github/scripts/test_preview_lib.py` | `test_preview_lib.py` includes a read-only assertion: running the lib against a temp repo creates no `.codearbiter/` | "preview lib writes nothing" | AC-02 | T-03 | ACCEPTED |
| T-07 | `plugins/ca/commands/preview.md` (new) | check-plugin-refs passes (cites `review-matrix.md` + `_previewlib.py`); manual: `/ca:preview` in a fresh non-init repo prints a report with prediction + found findings + nudge | "command orchestrates lib + matrix include, emits report + nudge, requires no init" | AC-01, AC-05, AC-11 | T-01, T-03, T-04 | ACCEPTED |
| T-08 | `plugins/ca/commands/preview.md` | manual: state-dependent reviewers render as "would run — sharper after onboarding"; report makes no hook-probe claim; `git diff` shows `doctor.md`/`doctor.py` untouched | "honesty marking for rule-dependent reviewers; doctor untouched" | AC-09, AC-10 | T-07 | ACCEPTED |
| T-09 | `plugins/ca/COMMANDS.md`, `plugins/ca/commands/commands.md`, `includes/routing-table.md`, `includes/reference-map.md`, `README.md` (badge 34→35), `docs/architecture.md` | check-plugin-refs passes; command count consistent across catalog + badge + chart | "preview registered everywhere registration lives (lazy-load invariant #4)" | AC-01 | T-07 | ACCEPTED |
| T-10 | `.codearbiter/tech-stack.md`, `.github/workflows/ci.yml` | `test_preview_lib.py` runs in CI; tech-stack Test section lists it | "new test wired into the suite + CI parity" | AC-02, AC-07, AC-08 | T-03 | ACCEPTED |

## Order & MVP slice

Dependency order: T-01, T-03 (independent roots) → T-04, T-05, T-06 (after T-03), T-02 (after T-01) → T-07 (after T-01, T-03, T-04) → T-08, T-09 (after T-07), T-10 (after T-03). No cycle.

**MVP slice (shippable):** `T-01, T-03, T-04, T-07, T-09`. This gives a working `/ca:preview` that runs cold (AC-01), is read-only by construction (AC-02 partial, fully proven by T-06), shows the matrix prediction from the shared include (AC-05), produces a real secret finding (AC-07), ends with the nudge (AC-11), and is discoverable (AC-09 registration). It is the adoption demo on its own.

**Incremental past the slice:** T-02 (finish AC-06 dedup of the other three commands), T-05 (AC-08 test-gap), T-06 (AC-02 proof), T-08 (AC-09/AC-10 honesty + doctor-distinct), T-10 (CI wiring).

## Coverage proof

Every AC has ≥1 task: AC-01→T-07,T-09 · AC-02→T-06,T-10 · AC-03→T-03 · AC-04→T-03 · AC-05→T-01,T-07 · AC-06→T-01,T-02 · AC-07→T-04,T-10 · AC-08→T-05,T-10 · AC-09→T-08 · AC-10→T-08 · AC-11→T-07. Every task covers ≥1 AC (table column). Bijective. ✓

`[NEEDS-TRIAGE]` Future expansion of the run-locally check set (e.g., a generic banned-primitive scan) is deliberately deferred — not in this plan.
