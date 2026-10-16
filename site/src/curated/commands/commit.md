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
calls `git commit` any other way. This entry contains the complete procedure generated
from the `commit-gate` owner, not a separately maintained wrapper. The check reads the
repository's current state itself (what's staged, what changed, whether the applicable local checks
are green) rather than taking your word for it. It runs impact-bounded local verification, a
behavioral check, and a diff review before anything is written to history. Exhaustive exact-head
hosted CI remains a merge gate.

The explicit command name is preserved. Claude keeps the owning skill available to
natural-language routing while suppressing the redundant command description. Codex and
Pi use their generated entry skill for discovery. Explaining history or drafting a
message does not authorize creating a commit, pushing, or opening a PR.

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
Behavioral proof: inspected the existing export regression output and unchanged source binding.
The criterion is covered: a saved search with zero results returns a header-only CSV.
Reviewing the staged diff... no unexpected files, no TODO markers, nothing out of scope.
Staged set matches intended files exactly.
Commit message drafted:

  feat(export): add CSV export for saved searches

  CHANGELOG: Saved searches can now be exported as CSV from the search list.

Committed a1b2c3d. git status: clean.
```

## When to reach for it

Reach for `/ca:commit` once selected work is ready to persist and committing is authorized.
Ordinary commits do not require artifact acceptance receipts. `/ca:pr` verifies an already
committed branch against its base-to-HEAD diff and dispatches the required reviewers; it uses
the commit owner when authorized uncommitted work still needs recording.
