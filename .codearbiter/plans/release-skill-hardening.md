# Plan — release-skill hardening

Spec: `.codearbiter/specs/release-skill-hardening.md` (APPROVED 2026-06-26).
Branch: `feat/release-skill-hardening`.
Stage: 2. No `--farm`. Stdlib-only Python + prose edits.

## AC ledger (verbatim from the approved spec)

- **AC-1 (0006)** — `last_tag_select(tags)` returns the highest ca SemVer tag, excluding pre-releases
  (`-beta`/`-rc`/`-alpha`) and every `ca-sandbox-v*` tag; `<none>` sentinel when no ca tag matches.
  Skill Pre-flight uses it as the single `LAST_TAG` source.
- **AC-2 (0005)** — `notes_heading_matches(notes_text, tag)` True iff the notes' first `## vX.Y.Z`
  heading equals `tag`. Skill Phase 3 calls it before `gh release create`, STOPs on False.
- **AC-3 (0004)** — `release_dates_consistent(changelog_section, tag_message)` True iff the
  `## vX.Y.Z — YYYY-MM-DD` date equals the `Released-at:` footer date. Skill derives the date once
  (`date +%F`), reuses it; structural assert it no longer instructs a second hand-typed date.
- **AC-4 (0003)** — `classify_publish_state(...)` returns exactly one of
  `{publish_fresh, resume_publish, already_published, abort_mismatch}` per the branch table. Skill
  Phase 2/3 branches on it instead of the flat "tag exists → STOP".
- **AC-5 (0002)** — Skill Pre-flight rebuilds `farm.js` and `git diff --quiet`s it **unconditionally**,
  ca-only (no `sandbox.js`), and **names the CI `tools` job as the mechanical backstop**. Structural
  test: unconditional rebuild present, no `farm.ts`-conditional guarding it, CI job referenced.
- **AC-6 (wiring)** — `test_release_lib.py` registered in `tech-stack.md` (Test section) and the
  `ci.yml` `hooks` job, suite green.

## Tasks

All helper functions land in `.github/scripts/_releaselib.py` (stdlib-only, `# codeArbiter — …`
header + `name(args) -> type` public-API block, never-raise-on-bad-input, pure/synthetic-testable —
mirrors `_taskboardlib`/`_metricslib`). All unit tests land in `.github/scripts/test_release_lib.py`.
Per `tdd`, each task writes its failing test FIRST, then the implementation.

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|----|---------|--------------|--------------------------|--------|------------|--------|
| T-01 | `.github/scripts/_releaselib.py`, `.github/scripts/test_release_lib.py` | `python .github/scripts/test_release_lib.py` — `last_tag_select(["v2.5.0","v2.5.1","v2.6.0-beta.1","ca-sandbox-v0.1.0"])=="v2.5.1"`; `(["ca-sandbox-v0.1.0","v2.7.0-rc.1"])=="<none>"` | AC-1 obligation: highest ca SemVer, pre-release + ca-sandbox excluded, sentinel on none | AC-1 | — | ACCEPTED |
| T-02 | `.github/scripts/_releaselib.py`, `.github/scripts/test_release_lib.py` | `python …test_release_lib.py` — matching `## v2.6.0` notes vs tag `v2.6.0` → True; `## v2.5.0` vs `v2.6.0` → False; missing heading → False | AC-2 obligation: first-heading↔tag equality | AC-2 | T-01 (shared file exists) | ACCEPTED |
| T-03 | `.github/scripts/_releaselib.py`, `.github/scripts/test_release_lib.py` | `python …test_release_lib.py` — equal dates → True; differing → False; either missing → False | AC-3 obligation: changelog-date↔`Released-at`-date equality | AC-3 | T-01 | ACCEPTED |
| T-04 | `.github/scripts/_releaselib.py`, `.github/scripts/test_release_lib.py` | `python …test_release_lib.py` — one case per branch returns the right label of `{publish_fresh,resume_publish,already_published,abort_mismatch}` | AC-4 obligation: publish-state classifier branch table | AC-4 | T-01 | ACCEPTED |
| T-05 | `plugins/ca/skills/release/SKILL.md`, `.github/scripts/test_release_lib.py` | `python …test_release_lib.py` structural checks: Pre-flight has unconditional `farm.js` rebuild+diff, NO `farm.ts`-conditional around it, references the CI `tools` job; Pre-flight invokes `last_tag_select`; Phase 3 invokes `notes_heading_matches`; date derived once; Phase 2/3 branch on `classify_publish_state` | AC-5 obligation (structural) + prose-wiring of AC-1..4 into the skill | AC-5 (+ wires AC-1,2,3,4) | T-01, T-02, T-03, T-04 | ACCEPTED |
| T-06 | `.codearbiter/tech-stack.md`, `.github/workflows/ci.yml` | registration strings present (tech-stack Test block lists `test_release_lib.py`; `ci.yml` `hooks` job has a step running it) AND `python .github/scripts/test_release_lib.py` exits 0 | AC-6 obligation: the new suite runs in CI parity and is green | AC-6 | T-01..T-05 | ACCEPTED |

## Order & MVP slice

Order: **T-01 → T-02 → T-03 → T-04 → T-05 → T-06** (T-02..T-04 each only need T-01's file to exist;
no cycle).

- **MVP slice — T-01..T-05:** the four tested helpers plus their wiring into the release skill. At
  T-05 the skill mechanically enforces tag-baseline, notes-heading, date-consistency, and
  publish-state, with the `farm.js` prose corrected — the spec's core is satisfied and shippable.
- **Incremental — T-06:** registers the suite in `tech-stack.md` + CI so the guards run on every
  future PR. Defense-in-depth completing AC-6; small, lands in the same PR.

## Coverage proof (bijective)

- AC-1→T-01 · AC-2→T-02 · AC-3→T-03 · AC-4→T-04 · AC-5→T-05 · AC-6→T-06. Every AC covered.
- Every task covers ≥1 AC (T-05 also wires AC-1..4 into the skill prose; that is the skill-side half
  of those criteria, not scope creep). No task covers nothing.

## Execution batches (executing-plans, checkpointed)

- **Batch 1:** T-01, T-02, T-03, T-04 (the helpers + unit tests; one new file, RED→GREEN each).
- **Batch 2:** T-05 (skill wiring + structural tests).
- **Batch 3:** T-06 (CI + tech-stack registration; full suite green).

No `[NEEDS-TRIAGE]` items raised (the `sandbox.js` boundary is routed to the existing
`casandbox.release.0001` task, recorded in the spec).
