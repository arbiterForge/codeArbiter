# Brownfield preparation fixtures

These are test-owned synthetic repositories for the exercise-ready brownfield campaign in PR #872. They are not generated consumer instructions, an onboarding implementation, or a second execution plan.

Run `python .github/scripts/test_context_fixtures.py` from the repository root. Explicit class selectors are supported; an unknown selector or zero selected tests fails. CI runs this suite through the existing native hook-contract cells, including fixture-only changes.

The eleven fixed cases cover a tiny project, preexisting root/nested/override instructions, independent packages, infrastructure without a database, conflicting command declarations, partial onboarding, separate staged/working/untracked content, a linked detached worktree, an unborn repository, sparse checkout, and ignored input. A standalone detached recipe is also tested.

The catalog contains bounded UTF-8 file content and identity hashes, a declared task, and proposed evaluator checks. Materialization creates only an absent test-owned directory. It uses fixed Git operations; declared application/test/deploy commands are inert. Existing destinations, unsafe paths, malformed inputs, and symlink/reparse ancestors are rejected before writing. Concurrent hostile filesystem behavior is not qualified by this test helper.

Each instance separates `solver/` from `evaluator/` and `control/`. For linked worktrees, `primary/` is also outside the solver. Evaluator expectations never enter the solver tree or its Git history. This layout is NOT a security boundary: a future host runner must independently prevent the solving agent from reading the sibling directories, this source catalog, or evaluator-side oracles. No agent/model run or containment qualification has occurred here.

Evaluator identity records bind the whole case, declared task, initial file snapshot, oracle, and materialized working files. A content identity is not semantic approval. Proposed checks still require independent review before a scored experiment. The catalog's zero-new-instructions expectations describe the unselected default-off pilot, not approval to create files in any consumer repository.

The helper and catalog remain repository test infrastructure and are not packaged into host plugins. Production report decoding, lifecycle recovery, context mutation, host loading, and task correctness require separate implementation and qualification. Preserve this distinction when reconciling preparation evidence into the canonical campaign plan.
