# Telemetry (opt-in, KPI-only)

Optional feedback that refines the skill and calibrates the estimator, pooled across contributors. The target is the public codeArbiter repo, so a shared corpus needs a shared destination — which is safe only because the payload is boring by construction: aggregates and per-lens exposure counts, never anything that identifies a codebase or exposes a weakness. Off by default; sent only on explicit per-run authorization.

## Hard scrubbing

The payload carries integers and enums only. It MUST NOT contain code, file paths, finding titles or text, commit hashes, or remote URLs. Repo identity is omitted by default; a contributor who wants to self-tag their submission for their own cross-run tracking may add `--tag <label>`, and only then does `tag` appear. `run_id` is a fresh random value, not derived from the repo.

## Why exposure counts, not raw findings

A raw finding count is uninterpretable alone: it is base-rate x detector-sensitivity x exposure, and you cannot invert the product from one number. "0 SQL-injection findings" reads as both "nobody concatenates SQL" and "our appsec lens is blind" — and those resolve oppositely. The per-lens `surface_seen` denominator disambiguates: 0 against a large surface is a blind-spot alarm; 0 against no surface is correctly uninformative. `false_positives` (from the decision log) separates a silent lens from a noisy one. These fields let the corpus *flag* blind-vs-rare; they cannot *confirm* it — that needs ground truth (a seeded-vulnerability canary or a semgrep/CodeQL cross-check), which is a separate self-test, not a payload field.

Reading the corpus is the maintainer's judgment, not skill behavior — and a suspicious zero in a security lens defaults to suspecting the detector, never to dialing the lens back, because those costs are asymmetric.

## Payload — `telemetry.json`

```json
{"schema":"telemetry/v1","skill_version":"<x.y.z>","run_id":"<random>","at":"<iso8601>","tag":"<omitted unless --tag>","loc_total":0,"loc_by_language":{"<lang>":0},"files_scanned":0,"primary_language":"<lang>","lenses_run":0,"lenses_skipped":0,"model_orchestrator":"<api-string>","models_by_tier":{"opus":0,"sonnet":0,"haiku":0},"tokens_estimated":0,"tokens_actual":0,"lens_exposure":{"<lens>":{"ran":true,"surface_seen":0,"findings":0,"false_positives":0}},"issues_found":0,"severity_breakdown":{"critical":0,"high":0,"medium":0,"low":0},"decision_breakdown":{"keep":0,"combine":0,"duplicate":0,"false_positive":0,"defer":0,"accept_risk":0,"decision_required":0,"investigate":0},"issues_filed":0,"run_duration_sec":0}
```

`lens_exposure` is the field that makes the corpus interpretable. `tokens_estimated` vs `tokens_actual` calibrates the cost estimate (a guardrail, not a measure of review quality).

## Send procedure

- Write `telemetry.json`; show it in full.
- State plainly, in one line: these aggregates post publicly to the codeArbiter repo; they carry no code, paths, or finding text, and no repo identity unless you added `--tag`.
- **Default:** print `gh issue create --repo arbiterforge/codearbiter --label telemetry --title "run-metrics <at>" --body-file telemetry.json`. Stop.
- **On explicit approval:** run it; record a `telemetry-sent` event in `run.jsonl`.
