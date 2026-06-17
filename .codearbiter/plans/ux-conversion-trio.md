# Plan — UX conversion trio (#82 + #84 + #83)

Spec: `.codearbiter/specs/ux-conversion-trio.md` (pending approval). Stage 2. Effort M.

**Architecture (resolved this session):**
- **Executable obligations via one structural test.** `.github/scripts/test_ux_conversion.py`
  (stdlib-only per ADR-0004) reads each touched framework file and asserts durable marker phrases are
  present (Receipt fields, register-split clause, stakes lines) and forbidden tokens are absent
  (saves-ledger / statusline segment / per-gate counter; stakes phrasing on mechanical-gate blocks).
  Each prose task pairs its own assertion (red) with its edit (green), mirroring how
  `test_preview_lib.py` was grown task-by-task. Coarse markers, not exact wording — avoids brittleness.
- **Two surfaces, six files.** The *close* surface = `finishing-a-development-branch/SKILL.md` +
  `SPRINT.md` + the register permission in `ORCHESTRATOR.md`. The *caught-finding* surface =
  `tdd/SKILL.md` + `secret-handling/SKILL.md` + `commit-gate/SKILL.md` + the same register permission.
- **Copy only.** No gate logic, no `security-controls.md`, no crypto/secret/auth enforcement changes.

## AC ledger (verbatim from spec)

| ID | Acceptance criterion |
|---|---|
| AC-01 | Receipt close lists all five fields (obligations, gates+catches, SMARTS decisions, secrets/regressions prevented, suite time). |
| AC-02 | Receipt draws only from Phase-1 state + `last-checkpoint`; skill forbids a fresh audit crawl. |
| AC-03 | `SPRINT.md` Phase 3 summary aligned to the Receipt field shape. |
| AC-04 | No saves-ledger / per-gate counter / new statusline segment in any touched file. |
| AC-05 | Stakes line on each finding block: tdd coverage/MISSING (Phase 4 & 5), secret caught, commit-gate Phase 5 + Phase 6. |
| AC-06 | Mechanical gates stay terse — no stakes line on protected-branch / missing tech-stack / wildcard-stage / subject>72. |
| AC-07 | `ORCHESTRATOR.md` register split: terse default + exactly one warm sentence at closes and genuine caught findings. |
| AC-08 | Register forbids warmth on routine green commits; no emojis/flattery. |
| AC-09 | Warm-sentence permission wired at real close points (Receipt, /sprint summary) + caught-finding points (tdd/secret/commit-gate). |
| AC-10 | `check-plugin-refs.py` passes; no broken refs. |
| AC-11 | `test_ux_conversion.py` runs in CI, listed in `tech-stack.md`, encodes AC 1–9 as assertions. |

## Tasks

| ID | Path(s) | Verification | maps-to (tdd obligation) | covers | depends-on | status |
|---|---|---|---|---|---|---|
| T-01 | `plugins/ca/ORCHESTRATOR.md`; `.github/scripts/test_ux_conversion.py` (new) | `python .github/scripts/test_ux_conversion.py` passes: asserts register-split clause present (terse-for-gating + one-warm-sentence-at-close/catch) and "routine green"/no-emoji prohibition present | "register split exists; warmth bounded; test harness created" | AC-07, AC-08 | — | ACCEPTED |
| T-02 | `plugins/ca/skills/finishing-a-development-branch/SKILL.md`; `test_ux_conversion.py` | test passes: Receipt section present with all 5 field markers + "no fresh audit-trail crawl" clause + one-warm-sentence reference | "Receipt close from Phase-1 state only; warm sentence wired" | AC-01, AC-02, AC-09 | T-01 | ACCEPTED |
| T-03 | `plugins/ca/SPRINT.md`; `test_ux_conversion.py` | test passes: Phase 3 summary carries the Receipt field markers + one warm closing sentence | "sprint summary aligned to Receipt shape" | AC-03, AC-09 | T-01 | ACCEPTED |
| T-04 | `plugins/ca/skills/tdd/SKILL.md`; `test_ux_conversion.py` | test passes: stakes marker on Phase 4 & Phase 5 coverage/MISSING blocks; assert mechanical obligation-scan/threshold blocks carry NO stakes phrasing | "stakes on coverage finding blocks; mechanical terse" | AC-05, AC-06 | T-01 | ACCEPTED |
| T-05 | `plugins/ca/skills/secret-handling/SKILL.md`; `test_ux_conversion.py` | test passes: stakes marker on the caught-secret block + one-warm-sentence reference on a genuine catch | "stakes on caught-secret; warm sentence wired" | AC-05, AC-09 | T-01 | ACCEPTED |
| T-06 | `plugins/ca/skills/commit-gate/SKILL.md`; `test_ux_conversion.py` | test passes: stakes marker on Phase 5 behavioral-proof + Phase 6 diff-review finding blocks; assert branch/wildcard-stage/subject>72 blocks carry NO stakes phrasing | "stakes on commit-gate findings; mechanical terse" | AC-05, AC-06 | T-01 | ACCEPTED |
| T-07 | `.github/scripts/test_ux_conversion.py`; `.github/workflows/ci.yml`; `.codearbiter/tech-stack.md` | test passes incl. global negative assertions (no `saves-ledger`/`statusline` segment/per-gate counter added across the six files); `test_ux_conversion.py` invoked in CI; tech-stack Test section lists it | "negative constraints enforced; test wired into CI + tech-stack" | AC-04, AC-11 | T-01..T-06 | ACCEPTED |
| T-08 | (no edit — verification) `python .github/scripts/check-plugin-refs.py` | reference graph passes; `git diff` confirms `security-controls.md` + all crypto/secret/auth enforcement logic untouched (copy-only) | "reference graph green; no logic/security drift" | AC-10 | T-01..T-07 | ACCEPTED |

## Order & MVP slice

Dependency order: T-01 (root: register split + test harness) → T-02, T-03, T-04, T-05, T-06 (independent, each appends one assertion to the shared test) → T-07 (negatives + CI wiring, after all edits) → T-08 (final graph/security verification). No cycle.

**MVP slice (the close experience — the demo):** `T-01, T-02, T-03`. Register split + Receipt close +
aligned `/sprint` summary. On its own this delivers the "end every loop on its most rewarding beat"
payoff and the warm close. The stakes layer (T-04..T-06) and the negatives/CI wiring (T-07) are the
incremental past the slice; T-08 is the final guard.

## Coverage proof

Every AC has ≥1 task: AC-01→T-02 · AC-02→T-02 · AC-03→T-03 · AC-04→T-07 · AC-05→T-04,T-05,T-06 ·
AC-06→T-04,T-06 · AC-07→T-01 · AC-08→T-01 · AC-09→T-02,T-03,T-05 · AC-10→T-08 · AC-11→T-07. Every task
covers ≥1 AC (table column). ✓

`[NEEDS-TRIAGE]` Structural prose-marker assertions are coarse by design; they prove the required copy
is present, not that it reads well. Copy quality is carried by the two-pass review (spec-compliance +
quality) in `subagent-driven-development`, not by the test.
