# Spec — task-board lifecycle for `open-tasks.md`

**Slug:** `task-board-lifecycle` · **Lane:** full · **Status:** approved 2026-06-21 by brennonhuff@gmail.com

## Problem

`open-tasks.md` has no schema. The only machine contract is "column-0 `- ` bullet =
one task," counted blindly by `session-start.py:478` and `statusline.py:381`. The live
file has drifted into an informal `## In-flight` / `## Done` kanban that no code
understands, so every `- ` bullet under `## Done` still counts as in-flight — the
startup "in-flight tasks: N" is wrong. There is no in-progress state, so work started
in a session that then crashes/compacts leaves no durable trace for the next session.

This feature gives the backlog a parseable, crash-safe lifecycle (queued → in-progress
→ done), fixes the count, surfaces abandoned in-progress work at startup, and gives each
task a content-bearing ID + minimum fields — without becoming a second execution ledger
that fights `plans/`.

## Scope

**In:**

- A structured task entry: top-level lifecycle line + indented content sub-bullets.
  - Lifecycle marker `[ ]` queued · `[~]` in-progress · `[x]` done, with dated
    `(started YYYY-MM-DD)` / `(done YYYY-MM-DD)` parentheticals.
  - Content-bearing ID `‹group›.‹type›.‹seq›` (e.g. `poc.auth.0001`): `group` = build
    phase (reused from decompose's `02-phased-build-plan.md`), `type` = domain/area
    token, `seq` = a `>=4`-digit zero-padded number (growth past 9999 allowed),
    numbered within each `group.type` namespace.
  - Sub-fields `Desc`, `Done when`, `Boundaries`. `ID + title + marker` are mandatory;
    the three sub-fields are expected but may read `TBD` until refined.
  - `Boundaries` uses the project's live vocabulary ("security boundary" / "trust
    boundary", NOT the cut "trust zones"); values are a security-routing hint that
    foreshadows a downstream `security-reviewer` / `crypto-compliance` /
    `secret-handling` gate — it never replaces those gates.
- A pure, fixture-testable helper (`_taskboardlib.py`) shared by both readers:
  `parse_board`, `validate_id`, `duplicate_ids`, `count_in_flight`,
  `stale_in_progress`, `undated_in_progress`, `lint_board`, `startup_summary`.
- Count fix consumed by both `session-start.py` and `statusline.py` (lockstep).
- A SessionStart stale-in-progress nudge, plus an undated-in-progress notice and a
  `lint_board` pass that SURFACES a task at risk of dropping off the map — a marker
  not at column 0 (indented / no-space / wrong-bullet), or an invalid/duplicate ID.
  This is the live surface for `validate_id` / `duplicate_ids` (without it they are
  dead code and a one-character slip hides a real task silently).
- Oversize-board degradation (`>65536B` not body-parsed).
- Scaffold-template documentation of the schema; migration of this repo's own
  `open-tasks.md`.

**Out (the honest boundary):**

- No second source of truth for execution. `plans/<slug>.md` (the `PENDING→ACCEPTED`
  ledger `/sprint`, `/feature`, `executing-plans` drive) is untouched and unbridged. The
  board stays a coarse, durable, advisory backlog. `Done when` stays one coarse
  sentence; per-step paths + verification commands belong to `plans/`, testable criteria
  to a spec.
- No live cross-file move to `done-tasks.md` — done is an in-place `[x]` flip; archival
  is a separate, deliberate, confirmed, append-only sweep (deferred — see D-2 in
  `open-questions.md`).
- No automated transition writer in the MVP: flipping a marker `[ ]`→`[~]`→`[x]` (and
  adding the `(started ...)` date) is HAND-EDITED. A command to do it is deferred — see
  D-1. This is the main residual drop-off risk: a task started but never flipped to
  `[~]` (with a date) is invisible to the stale nudge.
- No router+core+leaves bundle for a mutable task list.
- Not a UI/TUI kanban; the artifact is a markdown file.

Consistent with `CONTEXT.md` — extends an existing state file, contradicts nothing on
the NOT-building list, redefines no domain vocabulary (uses the live boundary term).

## Acceptance criteria

1. **AC-01 — Count excludes done.** A board with 2 `- [ ]`, 1 `- [~]`, 3 `- [x]`, and 1
   legacy bare `- ` → `count_in_flight` returns **4**, not 7.
2. **AC-02 — Both readers use the helper.** `session-start.py` "in-flight tasks" and the
   `statusline.py` `tasks` segment both reflect the AC-01 count against the same fixture
   — no done inflation in either.
3. **AC-03 — Stale detection.** `- [~] … (started 2026-06-18)` with injected
   today=2026-06-21 and threshold=3 → `stale_in_progress` reports 1 stale, oldest age 3;
   with started=today → reports 0.
4. **AC-04 — Nudge gating.** SessionStart emits the stale line only when ≥1 stale;
   otherwise the line is absent.
5. **AC-05 — Oversize degrades.** A board file `>65536` bytes is not body-parsed; the
   reader emits a "board too large — open directly" summary and never stalls.
6. **AC-06 — Schema documented in scaffold.** The `init-codearbiter.py` `OPEN_TASKS`
   template documents the lifecycle markers, the `‹group›.‹type›.‹seq4›` ID grammar, the
   `Desc`/`Done when`/`Boundaries` sub-fields (with the required-vs-`TBD` rule), and the
   count rule.
7. **AC-07 — Malformed dates never crash.** A `- [~]` entry with a missing/garbage
   `(started …)` is treated as age-unknown (counted in-progress, not stale, no throw).
8. **AC-08 — Repo self-migration.** This repo's `open-tasks.md` is migrated to the schema
   (Done bullets → `- [x] … (done <date>)`, in-flight → `- [ ]`/`- [~]`, ad-hoc IDs
   mapped to the dotted grammar); `count_in_flight` on the migrated file returns the true
   hand-counted in-flight number.
9. **AC-09 — ID grammar validated.** `validate_id` accepts `poc.auth.0001` /
   `mvp1.api.0042` and rejects malformed IDs (missing component, non-numeric or
   non-padded seq); a duplicate `group.type.seq` within the board is reported.
10. **AC-10 — Fields parse, partial allowed.** `parse_board` parses an entry's
    `Desc`/`Done when`/`Boundaries` sub-bullets into a structured record; a `TBD` or
    absent field yields an empty/`TBD` value, never a throw; `Boundaries` splits into
    tokens.

**Incremental (post-MVP, gated by deferred decision D-1):**

11. **AC-11 — Decompose seeding.** `decompose` Phase 5 and `context-creation` seed
    backlog items as `- [ ]` with dotted IDs sourced from the phase plan + role/domain.

## Open questions

These are **feature-internal deferred decisions — non-blocking**. They do not gate stage
promotion, so per house convention they are recorded under "Deferred decisions" in
`.codearbiter/open-questions.md` (NOT as `[CONFIRM-NN]`, which the hook counts as
stage-blocking). MVP ships without any of them.

- **D-1 — Transition writer surface.** New `/ca:task` (add/start/done) vs. extend
  `/ca:standup`/`/ca:status` vs. manual edit. MVP ships with the schema + counters +
  nudge; transitions are hand-edited until decided. Gates AC-11. **Resolved
  post-MVP:** `/ca:task` now enforces `[ ]`→`[~]`→`[x]`; `done` rejects a queued task
  and tells the caller to `start` it first (see `task-writer-harvest.md`).
- **D-2 — Archival sweep owner + cutoff.** Which command runs the confirmed
  done→`done-tasks.md` sweep, and the "long-settled" age (done >N days). Archival is
  post-MVP.
- **D-3 — Stale threshold value.** Default 3 days ships as a named constant; this tunes
  the number. Mechanism is tested with an injected date regardless.

Recorded under Deferred decisions in `.codearbiter/open-questions.md`.
