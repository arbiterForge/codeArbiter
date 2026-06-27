# Plan — context-drift-provenance

**Slug:** `context-drift-provenance` · **Spec:** `.codearbiter/specs/context-drift-provenance.md` (approved 2026-06-26)
**Branch:** `feat/context-drift-provenance` (off `main`) · **Stage:** 2

One engine (`_provenancelib.py`, stdlib-only, injectable hasher), three outputs: drift detection,
a coarse code map, and passive freshness via commit-gate. House pattern = `_taskboardlib.py` +
`.github/scripts/test_taskboardlib.py` (lib unit tests) and `test_board_sync.py` (structural
SKILL.md/hook assertions). All hashing through `git hash-object --stdin-paths` (honors
`.gitattributes` EOL → no CRLF false-drift). `drift_trigger` split is the anti-noise guarantee.

## Acceptance-criteria ledger (verbatim from spec)

| AC | Criterion |
|----|-----------|
| AC-01 | `write_provenance` then `read_provenance` round-trips an equal record; on-disk file is valid JSON with `schema/doc/created/interview_derived/entries[]`. |
| AC-02 | `batch_hash(paths, runner)` issues a **single** `git hash-object --stdin-paths` call (asserted via injected `runner`) and returns `{path: oid}` preserving order. |
| AC-03 | An entry hashed by `git hash-object` vs a working-tree file differing **only** by LF↔CRLF under `eol=lf` is reported **unchanged** by `compute_drift`. |
| AC-04 | Given an injected current-hash map with one diverged path, `compute_drift` returns that path under its doc, and only it. |
| AC-05 | An entry whose path is absent from current hashes is reported as drift kind `missing`; `compute_drift` does not raise. |
| AC-06 | No diverged entry → `startup_drift_line` returns `""` (SessionStart silent). |
| AC-07 | Drift > 0 → `startup_drift_line` returns exactly one line naming stale-source and doc counts and pointing to `/ca:context-check`. |
| AC-08 | Missing/corrupt `.provenance/` → `compute_drift` empty, `startup_drift_line` `""`, hook never crashes (degrade-not-fail). |
| AC-09 | `compute_drift` considers **only** entries with `drift_trigger: true`; entries with `drift_trigger: false` are stored but never reported as drift. |
| AC-10 | `classify_source(path)` returns `drift_trigger: true` for config/manifest/schema/security-entry patterns and `false` for general source, over a fixture path set. |
| AC-11 | `changed_scope(doc_provenance, drift)` returns **only** the changed/missing paths of that doc — never the full repo, never another doc's paths. |
| AC-12 | `rebaseline(provenance, current_hashes)` updates each entry's `hash`, leaves `claims`/`doc` untouched; a subsequent `compute_drift` returns empty. |
| AC-13 | `heal_worklist(staged_paths, provenance, current_hashes)` returns only staged paths that are `drift_trigger` entries with diverged hashes — **empty** when no staged file is tracked. |
| AC-14 | (structural) `commit-gate/SKILL.md` gains a conditional phase: on a non-empty heal worklist, dispatch an incremental re-scout scoped to those paths only; claim-holds → silent re-baseline; claim-changed → doc/map edit proposed in the existing diff-review phase. |
| AC-15 | `lint_code_map` rejects/flags a map exceeding the entry cap or carrying a multi-line role — enforcing module/concern granularity. |
| AC-16 | (structural) task-authoring skills (`tdd`, `feature`, `fix`) read `code-map.md` in pre-flight; the SessionStart hook does **not** read or inject it (read-on-demand only). |
| AC-17 | (structural) `context-creation` Phase 2 scouts emit a `git hash-object` per cited file; Phase 5 writes one provenance file per derived doc **and** `code-map.md`; `agents/scout.md`'s output template carries the hash field. |
| AC-18 | (structural) `decompose` writes provenance stubs (`interview_derived: true`, empty `entries`) per derived doc + a code-map stub; `write_stub` produces exactly that shape. |
| AC-19 | (structural) `/ca:context-check` skill + command exist with the minimal flow (report → per-doc re-scout / re-baseline / defer), and routing-table + reference-map + command-catalog entries resolve under `check-plugin-refs.py`. |

## Task table

Test homes: lib unit tests → `.github/scripts/test_provenancelib.py` (unittest, mirrors
`test_taskboardlib.py`); structural wiring → `.github/scripts/test_provenance_wiring.py` (new,
mirrors `test_board_sync.py`); hook surface → `plugins/ca/hooks/tests/test_session_start.py`.
T-01 also registers `test_provenancelib.py` and T-17 also registers `test_provenance_wiring.py`
in `.github/workflows/ci.yml` + `.codearbiter/tech-stack.md` (registration rides the file-creating
task — no orphan registration task).

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|----|---------|--------------|--------------------------|--------|------------|--------|
| T-01 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py`, `.github/workflows/ci.yml`, `.codearbiter/tech-stack.md` | `python .github/scripts/test_provenancelib.py -k round_trip` passes; `ci.yml`+`tech-stack.md` list the test | `write_provenance`/`read_provenance` round-trip an equal record; on-disk JSON carries `schema/doc/created/interview_derived/entries[]` | AC-01 | — | ACCEPTED |
| T-02 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k batch_hash` passes | `batch_hash(paths, runner)` issues exactly one `git hash-object --stdin-paths` (injected `runner` asserts call count) and returns order-preserving `{path: oid}` | AC-02 | T-01 | ACCEPTED |
| T-03 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k classify_source` passes | `classify_source(path)` → `True` for config/manifest/schema/security-entry patterns, `False` for general source, over a fixture path set | AC-10 | T-01 | ACCEPTED |
| T-04 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k drift_diverged` passes | `compute_drift` with one diverged path in the injected current-hash map returns that path under its doc, and only it | AC-04 | T-01 | ACCEPTED |
| T-05 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k drift_trigger_only` passes | `compute_drift` ignores `drift_trigger:false` entries (stored, never reported); only `drift_trigger:true` can drift | AC-09 | T-04 | ACCEPTED |
| T-06 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k drift_missing` passes | an entry path absent from current hashes is reported as kind `missing`; `compute_drift` does not raise | AC-05 | T-04 | ACCEPTED |
| T-07 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k eol_normalization` passes (temp git repo + `.gitattributes eol=lf`, CRLF-only variant) | an entry whose only change is LF↔CRLF under `eol=lf` produces the same `git hash-object` oid → `compute_drift` reports it unchanged | AC-03 | T-04 | ACCEPTED |
| T-08 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k degrade` passes | missing/corrupt `.provenance/` → `compute_drift` empty, `startup_drift_line` `""`, no raise | AC-08 | T-04, T-10 | ACCEPTED |
| T-09 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k drift_line_silent` passes | `startup_drift_line` returns `""` when no entry diverged | AC-06 | T-04 | ACCEPTED |
| T-10 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k drift_line_emit` passes | drift>0 → `startup_drift_line` returns exactly one line naming stale-source + doc counts and pointing to `/ca:context-check` | AC-07 | T-09 | ACCEPTED |
| T-11 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k changed_scope` passes | `changed_scope(doc_provenance, drift)` returns only that doc's changed/missing paths — never repo-wide, never another doc's | AC-11 | T-04 | ACCEPTED |
| T-12 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k rebaseline` passes | `rebaseline(provenance, current_hashes)` updates each entry's `hash`, leaves `claims`/`doc` intact; subsequent `compute_drift` empty | AC-12 | T-04 | ACCEPTED |
| T-13 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k heal_worklist` passes | `heal_worklist(staged_paths, provenance, current_hashes)` returns only staged `drift_trigger` entries with diverged hashes; empty when no staged file is tracked | AC-13 | T-04, T-03 | ACCEPTED |
| T-14 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k lint_code_map` passes | `lint_code_map(text)` flags an over-cap entry count or a multi-line role; clean map passes | AC-15 | T-01 | ACCEPTED |
| T-15 | `plugins/ca/hooks/_provenancelib.py`, `.github/scripts/test_provenancelib.py` | `python .github/scripts/test_provenancelib.py -k write_stub` passes | `write_stub(...)` produces `interview_derived:true`, empty `entries`, valid schema | AC-18 | T-01 | ACCEPTED (lib half — structural T-19 pending) |
| T-16 | `plugins/ca/hooks/session-start.py`, `plugins/ca/hooks/tests/test_session_start.py` | `python plugins/ca/hooks/tests/test_session_start.py` passes (emits the drift line when diverged; nothing when clean; degrades on missing `.provenance/`) | session-start.py computes drift via one `git hash-object --stdin-paths` and prints `startup_drift_line` only when drift>0; never crashes | AC-06, AC-07, AC-08 | T-10, T-08 | ACCEPTED |
| T-17 | `plugins/ca/skills/commit-gate/SKILL.md`, `.github/scripts/test_provenance_wiring.py`, `.github/workflows/ci.yml`, `.codearbiter/tech-stack.md` | `python .github/scripts/test_provenance_wiring.py -k commit_gate_heal` passes; `ci.yml`+`tech-stack.md` list the test | commit-gate gains a conditional auto-heal phase: non-empty `heal_worklist` → incremental re-scout of those paths only; claim-holds → silent re-baseline; claim-changed → edit proposed in the existing diff-review phase | AC-14 | T-13 | ACCEPTED |
| T-18 | `plugins/ca/skills/context-creation/SKILL.md`, `plugins/ca/agents/scout.md`, `.github/scripts/test_provenance_wiring.py` | `python .github/scripts/test_provenance_wiring.py -k context_creation` passes | context-creation Phase 2 scouts emit a `git hash-object` per cited file; Phase 5 writes one provenance file per derived doc + `code-map.md`; scout.md output template carries the hash field | AC-17 | T-01 | ACCEPTED |
| T-19 | `plugins/ca/skills/decompose/SKILL.md`, `.github/scripts/test_provenance_wiring.py` | `python .github/scripts/test_provenance_wiring.py -k decompose_stub` passes | decompose writes provenance stubs (`interview_derived:true`, empty `entries`) per derived doc + a code-map stub | AC-18 | T-15 | ACCEPTED |
| T-20 | `plugins/ca/skills/tdd/SKILL.md`, `plugins/ca/commands/feature.md`, `plugins/ca/commands/fix.md`, `.github/scripts/test_provenance_wiring.py` | `python .github/scripts/test_provenance_wiring.py -k code_map_read` passes (asserts each pre-flight reads `code-map.md`; session-start.py source has no code-map read) | tdd/feature/fix pre-flight read `.codearbiter/code-map.md` (read-on-demand); SessionStart hook does not read or inject it | AC-16 | T-16 | ACCEPTED |
| T-21 | `plugins/ca/skills/context-check/SKILL.md`, `plugins/ca/commands/context-check.md`, `plugins/ca/COMMANDS.md`, `plugins/ca/skills/INDEX.md`, `plugins/ca/includes/routing-table.md`, `plugins/ca/includes/reference-map.md`, `.github/scripts/test_provenance_wiring.py` | `python .github/scripts/test_provenance_wiring.py -k context_check` passes AND `python .github/scripts/check-plugin-refs.py` exits 0 | `/ca:context-check` skill+command exist with the minimal flow (report → re-scout / re-baseline / defer); catalog/routing/refmap entries all resolve | AC-19 | T-13 | ACCEPTED |

## Order & MVP slice

Dependency order (topological): T-01 → T-02 → T-03 → T-04 → {T-05, T-06, T-07, T-09, T-11, T-12} →
T-10 → T-08 → T-13 → T-14, T-15 → T-16 → {T-17, T-18, T-19, T-20, T-21}.

**MVP slice — passive drift detection, end-to-end (shippable on its own):**
**T-01 → T-02 → T-03 → T-04 → T-05 → T-07 → T-09 → T-10 → T-08 → T-16.**
That is: provenance store + single-call `git hash-object` + `drift_trigger` classification +
drift compute (with the LF↔CRLF anti-false-drift guarantee and `drift_trigger` discipline) +
the one passive SessionStart drift line + degrade-not-fail. Covers AC-01,02,03,04,05*,06,07,08,09,10.
(*AC-05 missing-kind, T-06, can fold into the slice or the first increment — non-blocking either way.)

**Increment 1 — incremental scope & the maintenance engine:** T-06, T-11, T-12, T-13, T-17
(`changed_scope` / `rebaseline` / `heal_worklist` → commit-gate auto-heal, pillar 3). Covers AC-11,12,13,14.

**Increment 2 — code map + creation + manual surface:** T-14, T-15, T-18, T-19, T-20, T-21
(`lint_code_map`, `write_stub`, context-creation/decompose ride-alongs, read-on-demand wiring,
`/ca:context-check`). Covers AC-15,16,17,18,19.

## Coverage proof

- **Every AC covered:** AC-01→T-01, AC-02→T-02, AC-03→T-07, AC-04→T-04, AC-05→T-06, AC-06→T-09/T-16,
  AC-07→T-10/T-16, AC-08→T-08/T-16, AC-09→T-05, AC-10→T-03, AC-11→T-11, AC-12→T-12, AC-13→T-13,
  AC-14→T-17, AC-15→T-14, AC-16→T-20, AC-17→T-18, AC-18→T-15/T-19, AC-19→T-21. No gaps.
- **Every task covers ≥1 AC:** yes (see `covers` column). Test-registration is folded into T-01/T-17,
  not a coverage-free task.

## Notes / boundaries (from spec — do not violate)

- Per-file hash (not line-anchors) for v1; line ranges are **stored** in `claims[].lines` (free, feeds
  the JIT-injection follow-up) but drift is per-file (D-1).
- No vector DB / embeddings / daemon / transcript-JSONL parsing / call-graph DB. Net-new-file coverage
  is out of scope (D-2 — full `/ca:create-context` re-run owns it).
- Enforcement soft-spot (provenance/code-map *writes* are prompt-discipline + structural ACs, not a
  runtime gate) is named, not solved in v1 — same class as CONFIRM-09.
- Spec follow-ups already harvested to `open-tasks.md` this session: `v2.feature.0001` (file-scoped JIT
  injection — committed next feature) and `v2.docs.0004` (scout-agent dispatch doc reconcile). No new
  `[NEEDS-TRIAGE]` in this plan.
