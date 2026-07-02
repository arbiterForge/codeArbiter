# Orchestrator schemas & artifact layout

The finding record (what agents emit) is in `finding-record.md`. This file holds the orchestrator-only logs and the run layout. Source of truth = the per-finding files (`findings/<lens>/<finding-id>.json`) plus the two append-only logs (`triage.jsonl`, `run.jsonl`); everything else is a projection regenerable from them. Write each record as it is produced — never batch.

## Artifact tree

```
.codearbiter/reports/<run-id>/        # run-id = <UTC-date>-<scope-slug>
  run.jsonl              # APPEND-ONLY run-state events; resume source of truth
  manifest.yaml          # projection of run.jsonl (regenerable snapshot)
  inventory.md           # map + risk/boundary/marker overlay
  findings/<lens>/<finding-id>.json  # one finding per file, written on discovery
                         # (crash-durable: a kill risks only the in-flight file;
                         # per-lens dirs, so no write contention)
  triage.jsonl           # APPEND-ONLY, one decision/line
  bodies/<finding-id>.md # issue body, lazy, approved-only
  plans/phase-<n>.md     # per-wave path plan (projection)
  report.md              # final human-readable (projection)
  issue-commands.sh      # ready-to-run gh issue create commands
  telemetry.json         # KPI payload, opt-in
```

## triage/v1 — one object per line in `triage.jsonl`

```json
{"schema":"triage/v1","id":"<finding-id>","decision":"keep|combine|duplicate|false-positive|defer|accept-risk|decision-required|investigate","final_severity":"critical|high|medium|low","final_confidence":0.0,"counter_argument":"<steelman; required for critical+high>","rationale":"<why>","group_id":"<when combine>","duplicate_of":"<finding-id, when duplicate>","issue_ref":"<filled after filing>","decided_at":"<iso8601>"}
```

`final_*` override the provisional self-scores everywhere downstream. `issue_ref` closes the finding→issue loop and makes re-runs idempotent.

## run/v1 — one state event per line in `run.jsonl`

```json
{"schema":"run/v1","event":"run-started|lens-launched|lens-skipped|wave-flushed|wave-triaged|report-written|issues-filed|telemetry-sent","wave":1,"lens":"<lens>","detail":"<optional>","at":"<iso8601>"}
```

## Resume — read the cursor, never the finding bodies

`run.jsonl` is the coarse state log — one line per wave/lens transition, tens of lines even across retries, not the per-finding logs. Resume reads the cursor, not the whole run, and never re-hydrates completed work:

1. **Position.** The resume point is fixed by the last triaged wave: `grep '"event":"wave-triaged"' run.jsonl | tail -1` returns it while reading only matching lines. If none, resume at wave 1.
2. **Plan.** Read the active-lens/wave set from `manifest.yaml` (a small projection) or, if it is missing or stale, from the `run-started`/`lens-launched`/`lens-skipped` block at the head of `run.jsonl`. Both are bounded reads — never a full-file scan for the plan.
3. **Re-enter** Phase 2/3 for waves after the last triaged one only.
4. **Do not load** already-triaged waves' `findings/<lens>/` files or `triage.jsonl` into context — they are authoritative on disk. A later wave's dedup that needs a specific prior id fetches it by targeted `grep` across `findings/`, never a full read.

`manifest.yaml` is a convenience snapshot regenerated from `run.jsonl`; it accelerates the plan read but is never authoritative — a corrupt or stale manifest falls back to the append-only log.

## dedup_key & ids

`id`: `<lens>-NNN`, sequential per lens. `dedup_key`: `<lens>:<path-normalized-to-repo-root>:<short-slug-of-title>`. Dedup matches on `dedup_key` and overlapping `locations`.
