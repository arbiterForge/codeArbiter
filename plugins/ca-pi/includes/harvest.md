# Follow-up harvest — promote workflow residue into the durable backlog

Loaded by a gated workflow's TERMINAL step so its un-actioned follow-ups reach the
durable backlog instead of languishing in a write-once artifact: gate run → residue →
backlog → surfaced next session → groomed via `/ca-standup`. Legacy board
logic stays in the pure `_taskboardlib` transforms; native projects use stable
work IDs through the installed `hooks/work.py` interface.

**Scope caveat (v1):** harvest fires only AT a terminal step. A step that is skipped,
interrupted, or crashes before this runs still loses its residue — the standup backstop
that would re-scan for un-harvested residue is **D-4, not yet built**. So v1 makes
residue languish far *less*, not "never"; do not rely on it as a guarantee until D-4.

## When each step harvests

| Terminal step | Residue source | Extractor (`_taskboardlib`) |
|---|---|---|
| `tdd` (Phase 6 exit), `brainstorming`, `writing-plans` | `[NEEDS-TRIAGE]` markers | `extract_needs_triage(text, origin)` |
| `commit-gate` (Phase 6 set-aside) | the out-of-scope `[NEEDS-TRIAGE]` file/change | `extract_needs_triage` |
| `checkpoint` | the `### DEFERRABLE` section | `extract_deferrable(text, origin)` |
| `sprint` (completion) | `confidence: low` auto-decisions in `sprint-log.md` | `extract_low_confidence(text, origin)` |

**commit-gate Phase 7 — pre-commit harvest (ADR-0008):** When commit-gate invokes harvest it
does so at **Phase 7, before staging** — not after the commit. Promoted work
changes are staged from the selected owner and **ride the work commit** as part of the same payload. This is a
contingent default: an abandoned branch or PR abandons the board additions with it
(self-correcting per ADR-0008). A follow-up that **must survive** abandonment should be filed
as a **GitHub issue**, not the board.

`origin` is the artifact's identity (e.g. `checkpoint-2026-06-13`, `spec:<slug>`,
`sprint:<slug>`) so each promoted entry carries a `(from <origin>)` back-ref.

## Procedure

1. **Detect.** Run the matching extractor over the residue to get candidates
   `(kind, desc, origin, boundaries)`. `kind` defaults to `work`; re-tag an item to
   `decision` at step 2 if it is really an open question, not a work item.
2. **Dedup + preview.** If `open-tasks.md` exists, call
   `promote(board, questions, candidates, mode="interactive", today=..., archive=...)`.
   It drops an origin already present on the board or in the archive. Before
   applying any result, run the installed `work.py list --limit 1` owner check
   used by `/ca-task`; a dual owner refuses the write. If the board is absent,
   page `work.py list` through `next_offset` and `membership_sha256`, collecting
   the returned origins across active and archived work. Drop candidates whose
   exact origin is already present. A stale page or failed read stops this
   harvest without a partial preview. Neither path writes during preview.
3. **Confirm.**
   - **Interactive (`/feature`, manual):** present the fresh list as ONE batch — promote
     these N? The user may edit/drop/re-tag before yes. On **decline**, write nothing to
     the board BUT record one audit line (`harvest declined: N candidates from <origin>`)
     to `triage.log` (append-only — use Edit/`>>`, never Write) so the decline is
     recoverable, not invisible.
   - **Autonomous (`/sprint`):** promote in-scope follow-ups and append each
     promotion (id + `(from origin)`) to `sprint-log.md` — append-only, so use Edit/`>>`,
     never Write (H-05 blocks a Write to it). A blocking decision is never auto-promoted
     — it escalates and STOPs.
4. **Apply.** On confirm, route each:
   - **work → selected owner** — on a legacy board, add a queued, ID-less
     `- [ ] <desc>  (from <origin>)` via `/ca-task add --from <origin> -- "<desc>"`.
     Put optional `--boundaries a,b` before `--`. On native work, call the
     installed `work.py create` with `--title=<desc>`, `--intent=<desc>`,
     `--type unknown`, the exact `--origin=<origin>`, and one caller-stable
     `--operation-id`. Include any boundaries in the intent text. Retain the
     returned `work_id`; a concurrent origin match returns that identity as
     reused rather than creating another item. Do not create a board.
   - **non-blocking decision → `open-questions.md`** "Deferred decisions" (a
     non-`CONFIRM-NN` bullet with the back-ref).
   - **blocking decision → ESCALATE**, never the Deferred-decisions section: `promote`
     emits an escalation audit entry instead of filing it. Route it to the user /
     `brainstorming` to author a real `[CONFIRM-NN]`. (The auto-`[CONFIRM-NN]` writer is
     not implemented — a blocking decision must NOT be silently demoted to non-gating.)

## Hard rules

- MUST harvest only at the terminal step, and only when residue exists — emit nothing
  when there is none.
- MUST dedup by exact source origin across active and archived work: re-running
  a workflow never double-promotes.
- MUST NOT auto-promote interactively — batch-confirm; `/sprint` auto is the only
  unattended path and it is logged.
- A harvested item is the ACTIONABLE copy; the origin artifact keeps its historical
  record. Do not delete the origin entry.
