# Orchestrator schemas and helper operations

The coordinator invokes the trusted bundle's `hooks/tribunal.py`; candidate
repository helpers are evidence, never a substitute executable. All operations
take `--root` before the subcommand. JSON goes in a structured argv argument;
never interpolate evidence into executable shell text. Resolve the interpreter
once by presence, not by retrying a failed operation with another interpreter.
On Codex/Pi derive the bundle root from the loaded routine path.

```sh
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" inventory --scope "$SCOPE"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" inventory --scope "$SCOPE" --format markdown
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" profile deep --capabilities "$CAPABILITIES_JSON"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" estimate --packet-bytes 4096 --profiles '{"deep":2,"standard":1}' --verification-candidates 1 --concurrency 3 --extraction-bytes 256
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" start --scope "$SCOPE" --target-digest "$TARGET_DIGEST" --evidence-path contract.txt --detail "$DETAIL_JSON"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" resume-status "$RUN" --scope "$SCOPE" --target-digest "$TARGET_DIGEST" --evidence-path contract.txt
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" read-run "$RUN"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" lead "$RUN" --record "$LEAD_JSON"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" lead "$RUN" --id reliability-lead-001 --disposition promoted --rationale "Owned by reliability-001"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" lead "$RUN"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" eligibility --finding "$FINDING_JSON" --record "$TRIAGE_JSON" --verification "$VERIFICATION_JSON"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" triage "$RUN" --finding "$FINDING_JSON" --record "$TRIAGE_JSON" --verification "$VERIFICATION_JSON"
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" event "$RUN" wave-triaged --data '{"wave":1}'
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" event "$RUN" report-written
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" event "$RUN" filing-skipped --data '{"detail":"No filing selected; commands handed off."}'
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" event "$RUN" telemetry-skipped --data '{"detail":"No transmission authorized."}'
"$PY" "<plugin-root>/hooks/tribunal.py" --root "$ROOT" event "$RUN" run-completed
```

These are invocation shapes, not authorization to execute project commands or to
assert a phase completed. Set ROOT/SCOPE from the caller, RUN from `start.run_dir`,
and JSON arguments from validated records. The example evidence file must exist
and belong to the declared inputs; use actual bounded filenames. Omit optional
`--verification` when no attempt exists. Emit wave/report events only after their
projections exist. Disposition events record actual user choices/actions.

Use the caller's current declarations for both `start` and `resume-status`:
recompute `TARGET_DIGEST` and repeat `--evidence-path` for every declared file.
Omit `--target-digest` from both commands when there is no explicit target.
If a previously declared target or evidence path has been removed, start a fresh
run. Omitted resume options reuse the saved values; they do not prove that the
caller still intends those inputs.

Run operations return `ok` and fixed refusal reasons. Inventory instead returns
`status: ok|partial|unavailable`; partial is usable only with its unavailable
fields disclosed. Profiles return ok/limited/unavailable; estimates return
estimated/unavailable. CLI exit 0 means a supported result, 1 a refusal, 2 invalid
arguments. No helper sends issues or telemetry, grants execution or runs project
scripts. Inventory JSON uses canonical key ordering; its Markdown is a mechanical
projection. Limits are `--max-file-bytes`, `--max-total-bytes`, `--history-limit`.

## Source binding and layout

`start` exclusively allocates a timestamp/scope/random run directory; never make
a date-only name or reuse an existing directory. The helper writes immutable
`source.json` (tribunal-run/v1 with a tribunal-source/v1 fingerprint) and the
first run/v1 event. Fingerprint fields cover repository identity, HEAD, normalized
scope, HEAD/index/worktree digests, selected untracked bytes, clean state,
evidence_paths and optional target_digest. Only this run's output is excluded;
historical reports used as evidence remain inputs.

Default untracked policy is all nonignored untracked inputs inside the declared
scope/evidence set. Repeat `--untracked path` for an explicit selection, or use
`--no-untracked` to exclude them. Repeat `--evidence-path` for concrete represented
tracked files/gitlinks or included nonignored untracked files outside the subtree.
Directories, ignored/missing files and excluded untracked evidence refuse with
`evidence-input-unavailable`. Freeze that complete intended evidence set before
dispatch. Expanding it requires a fresh binding/run, never rewriting source.json
or reusing completed work under a changed scope. An explicit review target uses
`--target-digest` with its exact SHA-256; recompute/pass it on resume.

One populated submodule level is bound, including dirty/untracked bytes; a nested
populated submodule requires a separate audit. Unpopulated gitlinks bind the
recorded object, not unseen file content. Inventory itself covers tracked facts
and reports unsupported parsing; it does not silently inventory reviewed
untracked files or claim a complete import graph.

```
.codearbiter/reports/<allocated-run-id>/
  source.json                         # immutable helper-owned binding
  run.jsonl                           # append-only lifecycle events
  inventory.json, inventory.md        # deterministic facts and projection
  risk-map.json                       # judgments, applicability, bounded packets
  findings/<lens>/<id>.json           # immutable individual findings
  pending-leads/<lens>/<id>.json      # durable reviewer handoff
  leads/<lens>/<id>.json              # validated immutable lead records
  lead-dispositions.jsonl             # append-only lead resolutions
  verification/<attempt-id>/<id>.json # immutable verification attempts
  triage.jsonl                        # append-only decisions and embedded verification
  plans/phase-<n>.md, report.md        # projections, never authority
  manifest.yaml                       # regenerable lifecycle snapshot
  bodies/<id>.md, issue-commands.sh    # selected eligible work only
  telemetry.json                      # optional public aggregate payload
```

## Lead, verification and triage examples

These illustrative records match the example finding in
finding-record (`<plugin-root>/routines/tribunal/references/finding-record.md`).
Use actual observations in a real run.

```json
{"schema":"lead/v1","id":"reliability-lead-001","source_lens":"reliability","target_lens":"architecture","locations":[{"path":"src/app.py","lines":"2-4"}],"observation":"Two callers may share the queue owner.","reason":"Ownership needs a caller trace.","created_at":"2026-10-05T12:00:00Z","disposition":"open"}
```

`lead --record` validates and exclusively writes the lead. Import pending records
before lens completion; on retry compare an existing id's bytes, never overwrite.
`lead --id --disposition --rationale` appends lead-disposition/v1, with disposition
routed/promoted/dismissed/deferred. Routed is not final resolution: close with a
finding id, refutation or explicit deferred reason before the report. Read merged
dispositions with `lead RUN`. Original leads and disposition history remain.

```json
{"schema":"verification/v1","id":"reliability-001","outcome":"confirmed","verification_independence":"independent","evidence":"A fresh reviewer traced both callers to the same unsynchronized queue owner.","surviving_claim":"Concurrent enqueue can discard a queued write.","commands":[]}
```

Outcomes are confirmed/narrowed/refuted/inconclusive. Independence is independent
only for a fresh reviewer given a bounded candidate packet; shared-context review
is limited. Executed command receipts include the exact argv, cwd, source binding,
independent caller authorization reference and result status. These are local
evidence, never telemetry. Narrowed results state the surviving claim.

```json
{"schema":"triage/v1","id":"reliability-001","decision":"keep","final_severity":"high","final_confidence":0.9,"counter_argument":"A caller might serialize access; both caller paths were traced and neither does.","rationale":"The independently checked owner loses a queued write.","decided_at":"2026-10-05T12:05:00Z"}
```

The helper adds root_cause_key, related_lenses, corroborates and verification to
the persisted triage row. Decisions: keep/combine/duplicate/false-positive/defer/
accept-risk/decision-required/verify-required/investigate. Optional group_id and
duplicate_of describe grouping; issue_ref is added only after eligible defect
filing. Preserve all earlier references when folding later rows. The helper
enforces serious-finding verification; the coordinator additionally enforces the
confidence thresholds and evidence/scope contract in
triage (`<plugin-root>/routines/tribunal/references/triage.md`).

## Lifecycle and resume

Call `resume-status` before reusing work, before dispatch and before any follow-up
action. Pass current scope/target/evidence declarations; elapsed age is advisory.
Never infer current evidence from a manifest or the last timestamp.

| state | action |
|---|---|
| audit | Use detail's recorded waves and last_triaged_wave; review only unfinished work. |
| follow-up | Report exists. Resume unresolved filing/telemetry dispositions only, without lenses. |
| source-drift | Preserve history; start a fresh binding/run before current-source work. |
| legacy-unbound | Read as history only; never resume as current evidence. |
| invalid | Surface the malformed/incomplete records; never guess or rewrite them. |
| terminal | Run completed/aborted. Read history; a new audit needs exclusive allocation. |

`read-run` returns historical events and triage without migration. A missing or
invalid binding cannot be repaired by editing old records. `manifest.yaml` is a
convenience snapshot only. Bounded helper reads can refuse oversized logs or a
stranded write lock; report that condition, never force unlock or truncate.

Allowed audit events are lens-launched, lens-skipped, lens-completed, wave-flushed,
wave-triaged, report-written. `start` alone creates run-started; its detail records
waves, applicability, profile/capabilities, packets and acknowledged budget.
Lens events retain lens/wave, applicability or skip reason, model/settings,
execution/independence limits, packet size, and completion counts. Only append
lens-completed after durable findings and pending leads are accounted for.

Usage field vocabulary below preserves the host receipt contract. Supply actual
counts/identifiers and one status value; omit tokens/components when unavailable.
These placeholders are a schema guide, not a measured completion event.

```json
{"schema":"run/v1","event":"lens-completed","wave":1,"lens":"reliability","surface_seen":0,"findings":0,"model":"inherited","tokens":0,"at":"<iso8601>"}
```

A `lens-completed` event carries `surface_seen` (int — the lens's Exposure denominator), `findings` (int — count the lens emitted), and `model` (the model the lens ran on, as dispatched); `model` also appears on `lens-launched`. `tokens` (int, optional) records the lens's observed token spend when the orchestrator can see it; null/omitted when unobserved.



`report-written` switches to follow-up; it is not terminal. Follow-up events are
issues-filed/filing-skipped and telemetry-sent/telemetry-skipped, then run-completed.
Both dispositions are required for completion. Handed-off commands or declined
actions use skipped with the actual reason; an unanswered choice remains pending.
Failures remain pending for retry after another source check. `run-aborted` is
terminal and records a deliberate abandonment; nothing resumes an aborted run.

For separately authorized design-discussion issues, `issues-filed.detail` carries
`discussion_refs`: a list of {id, url, root_cause_key, dedup_key}. They are not
confirmed-defect issue_ref records. Resume, reports and duplicate suppression
read this mapping alongside every historical triage issue_ref. If filing is
already disposed, skip it on follow-up resume. If a crash happened after tracker
creation but before the receipt, search the tracker for all identities before
retrying. Store each returned discussion receipt immediately in a new local
`bodies/<id>.filing.json`, reconcile those receipts into the single issues-filed
event when the selected batch finishes, and retain partial failures visibly.
Neither a stored command nor this receipt grants permission to create an issue.
