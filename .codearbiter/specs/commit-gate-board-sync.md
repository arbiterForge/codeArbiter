# Spec — commit-gate board-sync chokepoint (ADR-0008)

Implements ADR-0008 (`accepted` 2026-06-26): commit-gate is the single board-sync chokepoint;
task-board transitions ride the work commit, with a `/ca:standup` reconciliation backstop.

## Problem

Task-board transitions (`[x]` done-flip, `[~]` start-flip, new `[ ]` queued task) do not ride the
work commit today. commit-gate Phase 6 ejects an `open-tasks.md` edit as scope creep, and the
raise-new harvest runs *after* the commit lands — so flips drift into lagging `chore(board)` PRs or
post-commit edits that depend on cross-session memory (e.g. #138, #140/#141). The board edit only goes
live at merge, so co-locating it with the work commit is self-correcting; the fix is to make
commit-gate expect and stage the flip, and to add a backstop sweep for any flip still forgotten.

## Scope

**In:**
- A pure `_taskboardlib` classifier that recognizes a clean `open-tasks.md` *transition* diff
  (done-flip, start-flip, or queued add) versus an arbitrary board edit.
- commit-gate prose: Phase 6 exempts a classified transition from scope creep; Phase 7 stages it; the
  raise-new harvest runs **pre-commit** so raised tasks ride the work commit.
- harvest.md, `/ca:task` doc, and `task-board-lifecycle.md` updated in lockstep.
- A pure `_taskboardlib` reconciliation transform + a thin stdlib entrypoint that, from merged-commit
  task-id references, surfaces tasks whose work merged but whose board state is not `[x]`.
- `/ca:standup` wiring: an advisory reconciliation step that surfaces drift and never auto-flips.

**Out of scope (boundary):**
- No post-merge GitHub Action and no CI write to `main` (ADR-0008 declined it).
- No task→commit *inference* engine and no required `Closes <task-id>` footer convention (ADR-0008
  declined the linkage; the sweep signal is best-effort grep, SMARTS-selected).
- No crypto/secret/migration surface; no new runtime dependency (hooks stay Python-3 stdlib-only).
- The sweep is read-only/advisory — it never writes the board; a real flip still routes through
  `/ca:task` (`taskwrite.py`).

## Atomicity rules (from ADR-0008, for reference)

- **done-flip** `[~]`→`[x]` rides the **completing** commit; reverts on abandonment (self-correcting).
- **start-flip** `[ ]`→`[~]` rides the **first** work commit; reverts on abandonment.
- **raise-new** add `[ ]` rides the work commit (harvest pre-commit), **contingent default**; a
  follow-up that must survive abandonment is filed as a **GitHub issue**, not a board-only side commit.

## Acceptance criteria

Each is verifiable by a single test; structural-prose criteria assert anchored SKILL/command copy, the
pattern already used by `test_ux_conversion.py`.

1. **Classifier — done-flip positive.** Given the prior and new `open-tasks.md` text where the only
   change is one entry flipping `[~]`+started-date → `[x]`+done-date, the `_taskboardlib` transition
   classifier returns *is-transition*.
2. **Classifier — start-flip and add positive.** It returns *is-transition* for (a) a clean start-flip
   `[ ]`→`[~]` with a stamped started-date and no other change, and (b) an appended queued
   `- [ ] <desc>` entry with no other change.
3. **Classifier — arbitrary-edit negative.** It returns *not-transition* when the diff includes any
   change beyond a state-cell flip, its stamped date, or a single appended queued entry — e.g. a
   reworded description, a deleted entry, or an edit to a non-target line.
4. **Phase 6 exemption (prose).** commit-gate `SKILL.md` Phase 6 states that an `open-tasks.md` edit the
   classifier marks *is-transition* is retained (not flagged as scope creep), while any other board edit
   still flags — and names the classifier as the test.
5. **Phase 7 stage (prose).** commit-gate `SKILL.md` Phase 7 explicitly includes the classified board
   edit in the selective stage by path (no wildcard — the existing Phase 7 rule stands).
6. **Harvest pre-commit (prose).** commit-gate `SKILL.md` and `harvest.md` state the raise-new harvest
   runs before the commit (between Phase 6 and Phase 7), staging raised tasks into the work commit as a
   contingent default, and route a must-survive follow-up to a GitHub issue rather than the board.
7. **Doc lockstep (prose).** The `/ca:task` command doc and `task-board-lifecycle.md` state that
   transitions ride the work commit via commit-gate; `check-plugin-refs.py` stays green (every reference
   resolves).
8. **Sweep transform — drift detected.** `find_board_drift(board_text, merged_ids, today)` returns a
   task that is `[~]` or `[ ]` on the board but whose id appears in `merged_ids`.
9. **Sweep transform — clean and unknown-id safety.** It returns empty when the referenced task is
   already `[x]`; and a `merged_id` absent from the board is surfaced as an informational note (or
   ignored), never reported as a board write or a false done.
10. **Sweep id-extraction.** A `_taskboardlib` helper extracts dotted task-ids (the existing grammar,
    e.g. `v2.rev.0020`) from merged-commit text — yields the id when present, ignores non-id tokens.
11. **/ca:standup wiring (prose).** `/ca:standup` `SKILL.md` runs the reconciliation sweep as an
    advisory step that surfaces drift and never auto-flips a task — the fix routes through `/ca:task`.
12. **Read-only safety.** The reconciliation entrypoint performs no write to `open-tasks.md`; a test
    asserts the board file is byte-identical before and after a reconcile run.

## Open questions

None blocking. The three design forks (both-in-one-feature; tested classifier helper; `/ca:standup`
owner) were resolved by the user, and the drift-detection signal (best-effort task-id grep, advisory)
was resolved by SMARTS (moderate; A over B), consistent with ADR-0008's declined-linkage decision.

## Notes

- New pure logic lands in `_taskboardlib` (the pure-transform home); the thin reconcile entrypoint
  mirrors `taskwrite.py` (stdlib-only, shells `git log` for merged-commit text, calls the transform,
  prints drift). Exact paths are assigned by `writing-plans`.
- This change is `plugins/ca/**`-scoped → it bumps `plugins/ca/.claude-plugin/plugin.json` version with
  the README badge + dated CHANGELOG section (release invariant), folded into the work, not a trailing
  chore.
