---
entity: commands/commit
related: [sprint, pr, skills/commit-gate]
gates:
  - gate: verification
    when: every invocation
    effect: test, lint, and secret-scan results must all come back clean before anything else runs
  - gate: behavioral proof + diff review
    when: after verification passes
    effect: the change must demonstrate the behavior it claims, and the diff is reviewed line by line before staging
---

## What it does

This is the single entry point for turning staged work into a commit — nothing in codeArbiter
calls `git commit` any other way. Invoking it hands control to a multi-phase check that reads the
repository's current state itself (what's staged, what changed, whether the test suite is green)
rather than taking your word for it, then walks through verification, a behavioral check, and a
diff review before anything is written to history.

## Usage

```
/ca:commit
```

Takes no arguments — everything it needs comes from the current git state.

## Example

```text
> commit this

Branch: feat/export-csv (not protected — OK).
Classification: feat, scope export.
Running tests... 214 passed. Running lint... clean. Scanning staged files for secrets... clean.
Behavioral proof: re-running the export endpoint against the spec's acceptance criterion — a saved
search with zero results returns a header-only CSV. Confirmed by fresh output.
Reviewing the staged diff... no unexpected files, no TODO markers, nothing out of scope.
Staged set matches intended files exactly.
Commit message drafted:

  feat(export): add CSV export for saved searches

  CHANGELOG: Saved searches can now be exported as CSV from the search list.

Committed a1b2c3d. git status: clean.
```

## When to reach for it

Reach for `/ca:commit` once staged work is ready to persist. `/ca:pr` builds on the same gate to
check PR readiness, dispatching additional reviewers the diff's path demands.
