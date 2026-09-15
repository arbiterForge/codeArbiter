---
entity: commands/chore
related: [feature, add-dep, skills/commit-gate]
gates:
  - gate: type classification
    when: before any gate runs
    effect: the request must sort cleanly into docs, deps, or revert; a behavioral change beyond that scope redirects to feature or fix
  - gate: type-scaled checks
    when: after classification
    effect: docs gets a copy pass and a secrets scan; deps gets dependency review plus affected tests; revert gets a clean git revert plus affected regression tests; exhaustive exact-head proof runs in hosted CI
  - gate: commit-gate
    when: after the type's checks pass
    effect: the change still exits through the standard commit gate and lands via branch and PR
---

## What it does

This is the lane for changes with no behavior to test-drive — prose edits, a version bump on an
existing dependency, or backing out a named commit. Each of the three types gets exactly the checks
it needs and nothing more: a docs edit gets a secrets scan and a copy pass instead of a demand for
failing tests that would never exist for prose; a dependency bump gets the same vetting `/ca:add-dep`
applies plus impact-bounded local tests; a revert has to be a real `git revert`, never a hand-edited
backout, and also needs the affected regression tests green afterward. Exhaustive cross-platform
proof remains mandatory in exact-head hosted CI before merge. Anything that smuggles in a behavioral code change gets
redirected — this lane exists precisely to keep TDD ceremony off changes that have nothing to test.

## Usage

```
/ca:chore <docs|deps|revert> <description or SHA>
```

Name the type first, then the docs description, the dependency to bump, or the commit SHA to revert.

## Example

```text
> /ca:chore deps bump lodash to 4.17.21

Classified: deps.
Dispatching dependency-reviewer... license MIT (unchanged), no new transitive risk, changelog reviewed.
Manifest and lockfile updated together.
Running affected dependency and contract tests... 42 passed, 0 failed.
Exhaustive exact-head GitHub Actions checks remain required before merge.
Routing to commit-gate (classification: chore)...
```

## When to reach for it

Reach for `/ca:chore` for docs-only edits, an existing dependency's version bump, or reverting a
named commit. A brand-new dependency goes through `/ca:add-dep` first; any behavioral change goes
through `/ca:feature` or `/ca:fix`.
