# Telemetry (opt-in, aggregate-only)

Optional feedback for the estimator and review quality, off by default. The
destination is the public codeArbiter repository. Only explicit per-run authorization
permits sending, after a full preview. The run's local evidence is never a payload.

## Hard scrubbing

Use an explicit allowlist of aggregate fields. Do not copy inventory, source.json,
finding, lead, verification or arbitrary event detail objects. Exclude repository
identity, source fingerprints, commit hashes, other source-derived hashes,
paths, code, finding text/titles, command text, receipts and remote URLs.
The public run_id is a fresh random value, never the local scope-bearing run id.

Preserve the existing optional user-entered --tag <label> for cross-run tracking;
never auto-populate it from the repository, source, model output or environment.
This is the only deliberate freeform identity exception and remains visible in
the full preview and covered by per-run consent. --tag itself grants no send
authorization. Do not extend this exception to source fingerprints or code.

## Payload — telemetry.json

Optional additions retain telemetry/v1. Historical payloads remain readable.
This shape illustrates allowed aggregates; omit unavailable optional measurements
or mark them null, never fabricate a zero or derive LOC from file bytes.

```json
{"schema":"telemetry/v1","skill_version":"<installed-version>","run_id":"<fresh-random>","at":"<iso8601>","tag":"<omitted unless user supplied --tag>","loc_total":null,"loc_by_language":{},"files_scanned":0,"primary_language":"unknown","lenses_run":0,"lenses_skipped":0,"model_orchestrator":"inherited","models_by_tier":{},"profiles_used":{"deep":0,"standard":0,"extract":0},"tokens_estimated":0,"tokens_actual":null{{IF:codex}},"tokens_actual_status":"complete|partial|unavailable","tokens_unavailable_reasons":[]{{END}},"lens_exposure":{},"issues_found":0,"severity_breakdown":{"critical":0,"high":0,"medium":0,"low":0},"decision_breakdown":{"keep":0,"combine":0,"duplicate":0,"false_positive":0,"defer":0,"accept_risk":0,"decision_required":0,"verify_required":0,"investigate":0},"verification_candidates":0,"verification_outcomes":{"confirmed":0,"narrowed":0,"refuted":0,"inconclusive":0},"root_cause_groups":0,"corroborations":0,"evidence_packet_band":"unknown","deterministic_probe_count":0,"issues_filed":0,"run_duration_sec":0}
```

Keep actual host settings local if they contain private/custom identifiers.
Public model/tier fields use known public names or inherited/unavailable, never
repository-derived labels. profiles_used is the provider-neutral optional count.
skill_version comes from the installed host's version manifest.

lens_exposure maps each known lens to ran, surface_seen, findings and
false_positives counts from run/triage records. Counts distinguish reviewed
exposure from raw findings; they cannot prove detector precision. Same-run
false-positive decisions are not independent ground truth. Track later
real-world dispositions locally; qualify detectors with the frozen corpus.

issues_found counts kept root-cause groups, not duplicated observations.
verification_outcomes, root_cause_groups, corroborations, applicability skips,
evidence_packet_band (small/medium/large/unknown) and deterministic_probe_count
are optional aggregates. Do not include the underlying ids, keys or evidence.
Document chosen band thresholds locally; no field implies measured recall.
tokens_estimated is the disclosed estimate; retain the full band locally.

`tokens_estimated` vs `tokens_actual` calibrates the cost estimate (a guardrail, not a measure of review quality); `tokens_actual` sums `run.jsonl` `lens-completed` `tokens` when present, and is otherwise optional/best-effort — null when the orchestrator could not observe subagent spend.{{IF:claude}} Claude actuals count fresh input, cache creation, cache reads, and output; the per-lens `token_usage` receipt preserves that split for later cost calibration.{{END}}{{IF:codex}} `tokens_actual_status` is `complete` when every completed lens has numeric usage, `partial` when only some do, and `unavailable` when none do. `tokens_unavailable_reasons` is the sorted, deduplicated enum set from the unobserved lenses, so an unsupported host capability cannot be confused with missing or broken instrumentation and arbitrary log text cannot enter telemetry. Run-level reasons are `no-completed-lenses`, `run-log-unavailable`, `run-log-over-limit`, and `run-log-invalid`; malformed lens reasons become `reason-invalid`.{{END}}

## Send and disposition

{{IF:codex}}- Before writing the payload, resolve the installed plugin root from this routine's loaded SKILL.md path and run `hooks/tribunal-usage.py aggregate --run-log <run-dir>/run.jsonl`. Copy its three output fields exactly; never turn partial into complete.
{{END}}
- Recheck unchanged source through resume-status before follow-ups.
- Write telemetry.json using only the allowed aggregates; show it in full.
- State that these aggregates post publicly to the codeArbiter repo; they contain
  no source identity, paths, code or finding text except the user's explicit tag.
- Default: print the safely quoted command `gh issue create --repo arbiterForge/codeArbiter --label telemetry --title "run-metrics <at>" --body-file telemetry.json`.
- Execute only on explicit approval. On success append telemetry-sent through the
  helper; a failed post leaves the disposition pending and reports the error.
- An explicit decline or chosen hand-off records telemetry-skipped with reason.
  No answer is not consent or a completed disposition.
- After filing and telemetry are both disposed, append run-completed. Retain
  historical payloads/logs; do not rewrite them for the new optional fields.
