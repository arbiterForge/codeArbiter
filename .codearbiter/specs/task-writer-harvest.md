# Spec — task-board writer + workflow follow-up harvest

**Slug:** `task-writer-harvest` · **Lane:** full · **Status:** SHIPPED — reconciled 2026-07-12 against PR #118
**Builds on:** `task-board-lifecycle` (the schema + `_taskboardlib`). **Resolves:** D-1.

## Problem

Follow-up work the gated workflows generate — `[NEEDS-TRIAGE]` items (tdd /
brainstorming / writing-plans / commit-gate), checkpoint DEFERRABLE findings, and
low-confidence sprint decisions — is written into write-once artifacts (plan files,
checkpoint docs, `sprint-log.md`) that nobody re-reads, so it silently languishes
instead of reaching the durable backlog. And there is still no sanctioned *writer*
for the board (D-1): every transition is hand-edited, so a task can be started but
never marked `[~]` with a date — invisible to the stale nudge forever.

This feature closes the loop: a single sanctioned mutator (`/ca:task` + a shared
writer) makes `[ ]`→`[~]`→`[x]` transitions safe and dated, and each workflow's
terminal step promotes its un-actioned residue into the right durable store —
**work → `open-tasks.md`**, **decision → `open-questions.md`** — with a back-ref to
its origin, under confirmation.

## Scope

**In:**

- **Pure text-transform writer logic in `_taskboardlib`** (text in → new text out, no
  I/O; the existing pure-then-thin house style):
  - `next_seq(text, group, type) -> int` — next free 4-digit seq in the
    `group.type` namespace (1 when none). Used only when an ID is minted (add with
    an explicit group/type, or start of an ID-less item) — NOT at harvest time.
  - `add_entry(text, *, desc, origin=None, group=None, type=None, boundaries=None,
    section="## In-flight") -> str` — append a queued entry. ID-LESS by default:
    `- [ ] <desc>  (from <origin>)`. When `group`+`type` are given, mints
    `<group>.<type>.<NNNN>` via `next_seq`. Result is lint-clean; creates `section`
    if absent. The description must be nonblank and single-line; the section must
    be one canonical level-two heading; origin and boundary values must be
    single-line. Invalid input returns the original text unchanged.
  - `set_state(text, target, state, today, *, assign=None) -> str` — flip a task's
    marker (`target` = a dotted id, or the title of an ID-less item). `in_progress`
    accepts a queued task and ALWAYS stamps `(started <today>)`; `done` accepts an
    in-progress task and stamps `(done <today>)`. A direct queued-to-done transition
    is rejected unchanged. When `assign` = `group.type` and the target is ID-less,
    mints its dotted ID at the same time (the "ID on pick-up" path).
  - `already_promoted(text, origin) -> bool` — True iff an open (non-done) entry
    carries `(from <origin>)`.
- **Three pure extractors** (artifact text + origin → candidate list):
  `extract_needs_triage(text, origin)`, `extract_deferrable(text, origin)`
  (parses the checkpoint `### DEFERRABLE` markdown TABLE, bullet list also accepted),
  `extract_low_confidence(text, origin)`. A candidate carries
  `(kind, desc, origin, boundaries, blocking)` where `kind ∈ {work, decision}` and
  `blocking` (default False) marks a decision that must gate.
- **A `/ca:task` command** (`add` | `start` | `done`) — the human-facing, sanctioned
  board mutator, backed by the writer logic. Registered in the catalog + routing.
- **Harvest wiring in all five terminal steps** (tdd, brainstorming/writing-plans,
  commit-gate, checkpoint, sprint): detect residue via the extractors, then —
  - interactive (`/feature`): **batch-confirm** (show the list, write only on an
    explicit yes; decline writes nothing);
  - autonomous (`/sprint`): **auto-promote, SMARTS-logged** to the audit trail /
    `sprint-log.md`.
  - **Routing:** `kind=work` → `open-tasks.md`; `kind=decision` → `open-questions.md`
    "Deferred decisions" (non-CONFIRM) with the back-ref; a decision flagged
    blocking → a new `[CONFIRM-NN]`.
  - **Dedup:** skip any candidate whose `origin` is already promoted.
- **Harvested items are ID-less** (`- [ ] <desc>  (from <origin>)`) — counted,
  surfaced, back-ref'd, but no dotted ID until a human picks one up. `/ca:task start`
  mints the dotted ID at that point (the human supplies `group.type`; `next_seq`
  allocates) and stamps the started date — so the harvest never guesses a phase/domain
  and a picked-up item is immediately conformant with no dateless window.

**Out (the honest boundary):**

- NOT auto-syncing plan-task *status* (`PENDING→ACCEPTED`) into the board — that role
  separation stands. This harvests *residue*, not status.
- NOT an external issue tracker / ticketing integration.
- Does NOT replace the origin artifact's record — checkpoint docs / `sprint-log.md`
  keep their history; the board holds the actionable copy + a back-ref.
- NOT a re-classification engine for already-promoted items.
- Does NOT overlap `/ca:audit`: audit *reports* point-in-time (read-only); this makes
  items *durable + actionable*. They compose.

Consistent with `CONTEXT.md` — kernel backlog hygiene, not an enterprise compliance
suite; reuses existing vocab (`NEEDS-TRIAGE`, DEFERRABLE, `[CONFIRM-NN]`).

## Acceptance criteria

1. **AC-01 — seq allocation.** `next_seq("", "v2", "followup")` → 1; on a board
   already holding `v2.followup.0001` and `v2.followup.0003` → 4; a different
   namespace is independent.
2. **AC-02 — add_entry: ID-less default + mint-on-request.** `add_entry(board,
   desc="X", origin="checkpoint-2026-06-13#H-2")` appends
   `- [ ] X  (from checkpoint-2026-06-13#H-2)` under `## In-flight`; `count_in_flight`
   +1 and `lint_board` clean. Given `group="v2", type="followup"` it instead appends
   `- [ ] v2.followup.0001 - X  (from …)`. Blank or multiline descriptions,
   non-heading/multiline sections, multiline origins, and multiline boundary values
   are rejected unchanged; the CLI reports the invalid field before writing.
3. **AC-03 — start/done transitions are ordered and dated.** `set_state(board,
   "v2.api.0001", "in_progress", date(2026,6,21))` flips `[ ]`→`[~]` and adds
   `(started 2026-06-21)`; applying `"done"` to that in-progress result flips
   `[~]`→`[x]` and adds `(done 2026-06-21)`. Applying `done` directly to a queued
   task is rejected unchanged, and the writer tells the caller to `start` it first.
   A re-`done` is a safe no-op.
4. **AC-04 — start of an ID-less item mints + dates** (the pick-up path, D-1 hole
   closed): `set_state(board, "<title>", "in_progress", date(2026,6,21),
   assign="v2.api")` assigns the next `v2.api.NNNN` dotted ID AND stamps
   `(started 2026-06-21)`; `undated_in_progress` on the result is empty and the item
   validates. A malformed `assign`/`--as` namespace (extra or empty component,
   whitespace, or a character outside the ID grammar) is rejected before write.
5. **AC-05 — set_state on a missing target** returns the text unchanged and signals
   not-found (no silent partial write, no raise).
6. **AC-06 — dedup by origin.** `already_promoted(board, origin)` is True once an open
   entry carries `(from <origin>)`; a promote pass given a candidate with that origin
   adds nothing (idempotent re-run).
7. **AC-07 — extract_needs_triage.** Given artifact text with two `[NEEDS-TRIAGE]`
   lines, returns two candidates with the captured descriptions; none → empty.
8. **AC-08 — extract_deferrable.** Given a checkpoint doc whose `### DEFERRABLE`
   section is a markdown table of N findings, returns N candidates (column-1 desc)
   tagged `kind=work`, each with a checkpoint-dated origin. A prose `###` mentioning
   "deferrable" does not trigger; nested sub-rows are ignored. (Re-tag to `decision`
   at the confirm step — the extractor does not auto-detect decision phrasing.)
9. **AC-09 — extract_low_confidence.** Given `sprint-log.md` text, returns one
   candidate per `confidence: low` heading, origin = sprint slug + index; a prose line
   containing "confidence: low" is not harvested.
10. **AC-10 — work/decision routing.** A `kind=work` candidate renders into the
    `open-tasks.md` transform; a non-blocking `kind=decision` renders into the
    `open-questions.md` "Deferred decisions" transform with the back-ref; a
    `blocking=True` decision is NOT filed there — it is escalated (audit entry) for a
    `[CONFIRM-NN]`, never silently demoted to the non-gating section.
11. **AC-11 — confirmation modes.** `promote(board, questions, candidates,
    mode="interactive", today=…)` returns the fresh candidate list and produces NO
    mutation (the caller writes only after confirm); `mode="auto"` returns the new
    board + questions text PLUS an audit record naming each promotion/escalation.
12. **AC-12 — `/ca:task` command registered.** The command file exists, `/ca:task`
    `add`/`start`/`done` route to the writer, and `check-plugin-refs.py ca` passes
    with the new command in the catalog + routing table.

## Open questions (feature-internal, non-blocking — recorded as Deferred decisions)

- **D-4 — `/ca:standup` harvest offer.** Whether the daily standup should also offer to
  promote any residue not caught at a workflow's terminal step (a backstop sweep).
  Deferred; v1 harvests only at the terminal steps.
- **D-5 — sprint low-confidence threshold.** v1 harvests `confidence: low` only;
  whether `moderate` should also harvest is a tuning decision left open.

Cross-referenced in `.codearbiter/open-questions.md`.
