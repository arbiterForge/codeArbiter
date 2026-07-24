# AI-authorship markers & judgment overlay

The orchestrator's Phase 1 overlay on the raw inventory. These signals risk-rank scope and set severity priors; they are not findings themselves.

## Structural map

For each module, record what it exports, imports, and is called by. Flag modules importing from >5 sources (likely god module) and modules imported by >10 consumers (critical shared dependency — highest audit priority).

## AI-authorship markers

Signals that raise scrutiny on a file or directory:

- Excessive inline comments narrating trivial logic.
- Stale `TODO:`/`FIXME:` never resolved.
- Near-duplicate functions separated by 100+ lines (lost-context duplication).
- Convention switches mid-file — camelCase to snake_case, a pattern used then abandoned.
- Naming-convention drift within a unit.

## Iteration-depth estimate

Inspect git history. A large surface with few commits, or long runs of AI commits without human edits, indicates high AI-generation ratio and a higher feedback-loop-degradation prior — code more secure at step 1 than at the final state. Identify AI commits via `Co-Authored-By: Claude` / AI-tool trailers and characteristic generated message shapes (uniform conventional-commit bodies with bullet lists) — a heuristic signal, not proof. Raise scrutiny on the highest-iteration areas.

## Risk ranking & trust boundaries

Rank directories: highest = untrusted input, money movement, auth, PII, high churn. Mark trust boundaries explicitly — these feed the appsec lens directly.

## Effect on triage

A finding in a high-marker or high-iteration area carries a small upward severity prior at calibration. The prior never manufactures a finding — it only adjusts one that already cleared evidence-or-drop.
