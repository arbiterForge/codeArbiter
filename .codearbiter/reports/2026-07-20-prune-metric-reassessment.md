# Prune metric reassessment — 2026-07-20

Scope: aggregate-only recalculation of the local
`~/.codearbiter/metrics/prune-dry.jsonl` evidence. No transcript content,
repository identity, paths, or session identifiers were read into this report.

## Evidence

- Rows: 9 total; 9 `dry-run` with zero validation errors.
- Legacy whole-file estimate: 4,545,576 bytes, approximately 1,136,394 tokens.
- File-only `sidecar-collapse`: 2,860,049 bytes.
- Model-visible strategies: 1,611,362 bytes, approximately 402,840 tokens.
- Individual rows clearing the default 80,000 context-token nudge floor: 0.

Strategy deltas do not sum exactly to the serialized file delta because JSON
container punctuation and reserialization overhead are outside the replaced
payloads. The context estimate deliberately counts only strategy deltas whose
targets live in model-visible message content.

## Decision

The safety evidence remains clean, but the earlier benefit headline was about
64.5% too high because it treated file-only bookkeeping as model context. This
sample does not justify arming the cold-cache nudge at its default threshold and
does not support graduating pruning from preview on benefit evidence alone.
Keep the feature off by default, collect new dry records with the corrected
schema, and base any later `dry` to `on` decision on
`context_est_tokens_freed`, not the legacy whole-file estimate.
