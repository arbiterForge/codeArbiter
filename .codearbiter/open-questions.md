# Open questions

Unresolved `[CONFIRM-NN]` items. Each blocks stage promotion until resolved.
The SessionStart hook and statusline count `CONFIRM-NN` occurrences here.

## [CONFIRM-05] Feature Forge promotion bar for the `--farm` (OpenCode Zen) backend

What evidence promotes `--farm` from `preview` to stable? Define the bar before promoting. Candidate
signals to choose among, with thresholds to set: number of successful `/ca:sprint --farm` runs across
how many distinct repos; per-task pass-rate and average attempts; measured cost saving vs. the premium
backend; zero gate escapes (no farm-produced code reaching a commit without clearing the full review
chain); no security or supply-chain incident from the third-party Zen API. The owner decides the metric
set and thresholds; until then the farm stays `preview`.

_Previously resolved: the four Phase 1 gate decisions, 2026-06-04 (see `legacy/ASSESSMENT.md` §10)._
