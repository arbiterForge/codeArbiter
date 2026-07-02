# Report projection

`report.md` is a projection of the logs, regenerated in Phase 4 — never hand-authored, never a source of truth. Rebuild it fully from `findings/*/*.json` + `triage.jsonl` on every run and on resume; it is deterministic from the logs. Task-list-structured, not prose.

## Structure

- **Header** — run-id, scope, date, models used (from `run.jsonl`), the token estimate from Phase 0 vs. actuals (summed from `lens-completed` `tokens` in `run.jsonl` when present; best-effort, since the orchestrator cannot always observe subagent spend), and a launched/skipped-lens summary with the skip reason per lens.
- **Findings** — grouped by **calibrated** `final_severity` (critical to low), then by lens/type within each severity. Each entry on one line: `id` · `path:line(s)` · one-line description · remediation shape · triage `decision` · link to `plans/phase-<n>.md`. Only `keep`/`combine` findings appear here.
- **Decisions needed** — a separate section for `decision-required` findings, each as its question + options. These need a decision, not a fix; do not fold them into the severity list.
- **Investigate appendix** — medium/low findings below the confidence gate after calibration (defined in `triage.md`; below-gate critical/high land in Decisions needed instead); `id` + `path:line` + one terse line each. Preserved, not filed.
- **Blocking-severity note** — one line: critical/high should block shipping the affected code, but this lane is not a gate and blocks nothing.

## Anti-slop

Apply `core` (no em-dash sentence separators, no filler/AI cadence, no fabricated precision) and `medium-documents`. Every count comes from the logs — never invent a number to make the report "feel precise."

## Relationship to `manifest.yaml`

`manifest.yaml` is the machine-readable run snapshot (a projection of `run.jsonl`); `report.md` is the human view. Both regenerate from the logs; neither is edited by hand.
