# Local and hosted verification boundary

Use **impact-bounded local verification** for the contributor loop. Before a
commit or pull request, run the smallest fresh set that directly proves the
changed obligations and affected contracts, plus applicable lint/type-check,
coverage, generated-artifact parity, staged secret scanning, and specialized
security, dependency, migration, release, ADR, or deployment gates. A failing
local check blocks. Do not require a repository-wide or cross-platform suite on
the contributor's machine merely to create a commit or open a pull request.

GitHub's public-repository **hosted CI** owns exhaustive and cross-platform
validation. Before merge, bind the pull request's current exact-head commit and
require its repository merge-readiness aggregate, including every job selected
by the impact planner. Missing, stale, cancelled, or mismatched hosted evidence
does not count: **MUST NOT merge** until the exact-head required checks pass.

Hosted CI is not a substitute for evidence that cannot be exercised safely or
faithfully on a hosted runner, such as a user-authorized live device, private
environment, or local integration boundary. Run that proof locally when the
acceptance criterion requires it, record the environment and result, and still
require hosted CI for the repository checks it owns.

This allocation changes where exhaustive compute runs, not the strength of the
gates. It never waives focused regression proof, coverage thresholds, lint or
type-check failures, security and secret controls, dependency review, migration
review, release invariants, ADR lifecycle proof, deployment review, or exact-head
merge protection.
