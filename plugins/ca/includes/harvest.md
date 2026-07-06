# Follow-up harvest — promote workflow residue into the durable backlog

Loaded by a gated workflow's TERMINAL step so its un-actioned follow-ups reach the
durable backlog instead of languishing in a write-once artifact: gate run → residue →
backlog → surfaced next session → groomed via `/ca:standup`. The board LOGIC is the
pure `_taskboardlib` transforms; this is the procedure that wires each terminal step.

**Scope caveat (v1):** harvest fires only AT a terminal step. A step that is skipped,
interrupted, or crashes before this runs still loses its residue — the standup backstop
that would re-scan for un-harvested residue is **D-4, not yet built**. So v1 makes
residue languish far *less*, not "never"; do not rely on it as a guarantee until D-4.

## When each step harvests

| Terminal step | Residue source | Extractor (`_taskboardlib`) |
|---|---|---|
| `tdd` (Phase 6 exit), `brainstorming`, `writing-plans` | `[NEEDS-TRIAGE]` markers | `extract_needs_triage(text, origin)` |
| `commit-gate` (Phase 7 set-aside) | the out-of-scope `[NEEDS-TRIAGE]` file/change | `extract_needs_triage` |
| `checkpoint` | the `### DEFERRABLE` section | `extract_deferrable(text, origin)` |
| `sprint` (completion) | `confidence: low` auto-decisions in `sprint-log.md` | `extract_low_confidence(text, origin)` |

**commit-gate Phase 8 — pre-commit harvest (ADR-0008):** When commit-gate invokes harvest it
does so at **Phase 8, before staging** — not after the commit. The promoted `open-tasks.md`
additions are staged into and **ride the work commit** as part of the same payload. This is a
contingent default: an abandoned branch or PR abandons the board additions with it
(self-correcting per ADR-0008). A follow-up that **must survive** abandonment should be filed
as a **GitHub issue**, not the board.

`origin` is the artifact's identity (e.g. `checkpoint-2026-06-13`, `spec:<slug>`,
`sprint:<slug>`) so each promoted entry carries a `(from <origin>)` back-ref.

## Procedure

1. **Detect.** Run the matching extractor over the residue to get candidates
   `(kind, desc, origin, boundaries)`. `kind` defaults to `work`; re-tag an item to
   `decision` at step 2 if it is really an open question, not a work item.
2. **Dedup + preview.** Call `promote(board, questions, candidates, mode="interactive",
   today=...)`. It drops any candidate already promoted (`(from <origin>)` already open)
   and returns the fresh list — it writes NOTHING yet.
3. **Confirm.**
   - **Interactive (`/feature`, manual):** present the fresh list as ONE batch — promote
     these N? The user may edit/drop/re-tag before yes. On **decline**, write nothing to
     the board BUT record one audit line (`harvest declined: N candidates from <origin>`)
     to `triage.log` (append-only — use Edit/`>>`, never Write) so the decline is
     recoverable, not invisible.
   - **Autonomous (`/sprint`):** SMARTS-score the batch, auto-promote, and append each
     promotion (id + `(from origin)`) to `sprint-log.md` — append-only, so use Edit/`>>`,
     never Write (H-05 blocks a Write to it). A blocking decision is never auto-promoted
     — it escalates and STOPs.
4. **Apply.** On confirm, route each:
   - **work → `open-tasks.md`** — a queued, ID-less `- [ ] <desc>  (from <origin>)` via
     `/ca:task add -- "<desc>" --from <origin>` (the `--` lets a desc start with `-`;
     add `--boundaries a,b` when the extractor supplied them).
   - **non-blocking decision → `open-questions.md`** "Deferred decisions" (a
     non-`CONFIRM-NN` bullet with the back-ref).
   - **blocking decision → ESCALATE**, never the Deferred-decisions section: `promote`
     emits an escalation audit entry instead of filing it. Route it to the user /
     `brainstorming` to author a real `[CONFIRM-NN]`. (The auto-`[CONFIRM-NN]` writer is
     not implemented — a blocking decision must NOT be silently demoted to non-gating.)

## Hard rules

- MUST harvest only at the terminal step, and only when residue exists — emit nothing
  when there is none.
- MUST dedup by `(from <origin>)`: re-running a workflow never double-promotes.
- MUST NOT auto-promote interactively — batch-confirm; `/sprint` auto is the only
  unattended path and it is logged.
- A harvested item is the ACTIONABLE copy; the origin artifact keeps its historical
  record. Do not delete the origin entry.
