# Follow-up harvest — promote workflow residue into the durable backlog

Loaded at discovery and at the workflow's existing terminal promotion step so its un-actioned follow-ups reach the
durable backlog instead of languishing in a write-once artifact: gate run → residue →
backlog → surfaced next session → groomed via `/ca-standup`. Legacy board
logic stays in the pure `_taskboardlib` transforms; native projects use stable
work IDs through the installed `hooks/work.py` interface.

Capture and promotion are separate. The local `terminal-harvest` recovery owner
retains only successfully registered, sanitized candidates. It does not recover
unregistered conversation, grant authority, or promote anything at startup.
The existing interactive confirmation or in-scope sprint authority still governs
the terminal effect. Registration failure reports `durable:false`; keep the
candidate and failure visible and continue unrelated authorized work.

## Capture when the candidate is discovered

Use the installed `hooks/workflow-recovery.py` through the same literal helper
resolution as `hooks/work.py` in `includes/helper-invocation.md`. Do not use a
PATH replacement, a copied helper, or a caller-selected storage directory.
The helper authenticates its executing host/package owner and stores local
bookkeeping under Git-common `codearbiter/workflow-recovery/v1/`.

As soon as a qualifying bounded candidate is known, run the existing pure
extractor over its sanitized source text and register its returned exact origin,
including the item suffix. For HTML, read the owning record through the native
API; do not scrape HTML. Use a stable existing workflow/work run ID across restart
and reentry, such as `work:<WORK-ID>`. For ordinary work without one, derive and
retain `origin:<sha256 of the stable source identity>` once. Never derive this
identity only from a timestamp or the current session. Ordinary work may use
`work_ref:"none"`; capture does not require enrolling a new task.

`register` takes bounded JSON stdin, or `--input <bounded-json-file>`:

```json
{"candidates":[{"kind":"terminal-harvest","workflow_run_id":"<stable-run>","origin":"<exact extractor origin>","work_ref":"none","source":{"workflow":"<producer below>","locator":"<relative source file>","fingerprint":"sha256:<current source bytes SHA-256>"},"candidate":{"kind":"work","blocking":"nonblocking","title":"<sanitized title>","description":"<bounded sanitized continuation>","provenance":"<source reference>","boundaries":["<existing scope>"]}}]}
```

The whole batch is at most 64 KiB and 32 candidates; every candidate is validated
without silent truncation. Omit optional description/boundaries when unnecessary.
`source.locator:"candidate"` binds a conversation-only sanitized candidate to the
SHA-256 of its canonical candidate fields, excluding the runtime revision. It
does not pretend that a transcript or other unregistered material was retained.
Never store credentials, raw diagnosis/rejected packets, full transcripts,
arbitrary instructions to execute, or reusable `approved`/`authorized` flags.

| Discovery owner | Exact `source.workflow` |
|---|---|
| TDD findings, when first recognized | `tdd:phase-6` |
| Brainstorming triage | `brainstorming:triage` |
| Planning triage | `writing-plans:triage` |
| Commit-gate set-aside | `commit-gate:set-aside` |
| Checkpoint DEFERRABLE finding | `checkpoint:deferrable` |
| Recorded low-confidence sprint decision | `sprint:low-confidence` |

Retain each returned `obligation_id`, `record_revision`, exact source and observed
`durable` result in the existing work/handoff record. An empty candidate set emits
no obligation and creates no recovery store. Same registration reuses the existing
identity; different content needs an explicit correction, not a fresh implicit
success. A new follow-up after changed facts uses a new stable run/origin and
references the old obligation in provenance; the old terminal history stays intact.

## Inspect, reconcile and resume selected items

`scan [--cursor <opaque>]` and `get --obligation-id <id>` are read-only. One scan
reads at most 32 summaries and 256 KiB, including record verification. `partial`
means this page is only a lower bound; a stale cursor or damaged index is
unavailable, never evidence of an empty queue. Neither automatic startup nor a
status/standup read repairs the ledger or runs a target. Explicit `repair` locks
and reconciles an interrupted record/index transaction, without creating tasks.

At the existing authorized terminal step, run `resume --obligation-id <id>
--expected-revision <revision>` for each selected item. This calls only its
selected work owner or the narrow nonblocking-decision adapter and records exact
target readback. An uncertain prior effect is looked up by exact operation/origin
before retry, including active/archive legacy work. A live OS lock returns busy;
timestamps cannot steal it. Do not substitute a title match or a second writer.
After a lost response, use `get` and `reconcile --obligation-id <id>
--expected-revision <revision>` before any new effect. Reconciliation observes
an existing effect or proves absence; it does not replay one.

Interactive decline uses the explicit `decline` operation only after the user
declines; its audit append and readback settle once. Blocking decisions remain
unavailable for dependent-only user resolution, never Deferred decisions or an
invented `[CONFIRM-NN]`. `correct` takes a new bounded candidate/source and CAS
revision, preserving old history. It cannot overwrite an unknown effect or clear
an actual denial/stop. `restore` rechecks a restored non-authority condition;
real denial/stop lifting stays with the actual host/user owner. Only after that
same owner actually lifts it, the current actor may invoke `restore-authority`
with a sanitized `--authority-source user:<actual message reference>` or
`host:<actual event reference>`. This records context in preserved history; it
does not authenticate or grant authority from the reference, and effect actors
must still check live scope and bindings. Validation, correction, age or a new
grant cannot prove an unknown earlier effect absent; reconcile that effect first.
A new session
gets no old Pi child grant merely by inspecting or reconciling the record.
Pi children cannot directly mutate the shared ledger. They send bounded sanitized
candidates to their current parent, which checks the actual delegation's work,
run and origin scope before registration. An unavailable parent capture is
`durable:false`, not permission to write an unconstrained recovery record.

`cancel` and `supersede` are explicit scoped dispositions and refuse an
unreconciled effect. `compact` retains a terminal record and its exact origin,
candidate, target and receipt while retaining prior versions separately; it
never deletes pending state or a target. Rollback disables new feature calls
while retaining readable records/history and all independently edited targets.
CLI success, bookkeeping settlement, work progress, passing review, merge and
publication remain distinct.

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

Pass the artifact identity (e.g. `checkpoint-2026-06-13`, `spec:<slug>`,
`sprint:<slug>`) to the extractor. Each returned candidate's `origin` is the
exact source key with its item suffix (for example `spec:<slug>#triage-1`);
use that returned key unchanged for deduplication, promotion, and the
`(from <origin>)` back-ref.

## Procedure

1. **Detect.** Reuse the successfully registered exact candidates; capture any
   newly discovered candidate immediately using the section above. Run the matching extractor over the residue to get candidates
   `(kind, desc, origin, boundaries)`. `kind` defaults to `work`; re-tag an item to
   `decision` at step 2 if it is really an open question, not a work item.
2. **Dedup + preview.** If `open-tasks.md` exists, call
   `promote(board, questions, candidates, mode="interactive", today=..., archive=...)`.
   It drops an origin already present on the board or in the archive. Before
   applying any result, run the installed `work.py list --limit 1` owner check
   used by `/ca-task`; a dual owner refuses the write. If the board is absent,
   first call `promote("", questions, candidates, mode="interactive", today=...)`
   to omit decisions already filed in `open-questions.md`. Query the remaining
   work origins in batches of at most 32 with the installed `work.py origins`
   (`--origin=<source-key>` for each exact key). It checks active and archived
   work in one bounded native read per batch. Omit matched work origins from
   the preview; a failed query stops this harvest without a partial preview.
   Neither path writes during preview.
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
4. **Apply.** On confirm, use the selected obligation's `resume` operation and
   retain its exact per-item target/readback result. The closed adapter routes each:
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

- MUST register qualifying candidates at discovery; promote only at the existing
  authorized terminal step or explicit selected resume. Emit no obligation when
  there is no candidate, and never call an unregistered candidate recovered.
- MUST dedup by exact source origin across active and archived work: re-running
  a workflow never double-promotes.
- MUST NOT auto-promote interactively — batch-confirm; `/sprint` auto is the only
  unattended path and it is logged.
- A harvested item is the ACTIONABLE copy; the origin artifact keeps its historical
  record. Do not delete the origin entry.
