---
title: "Cut a Release"
description: "Tag and publish a codeArbiter version with /ca:release: SemVer derivation from Conventional Commits, CHANGELOG.md update, and authorized GitHub Release publication."
---

`/ca:release` is the only permitted path to a version tag. It derives the SemVer bump from Conventional Commits history since the last `ca` tag, updates `CHANGELOG.md`, composes an annotated tag locally, and publishes a GitHub Release only after you explicitly authorize it.

## Prerequisites

Four conditions must hold before `/ca:release` will proceed:

- **On a feature branch.** The current branch must not be the default branch (`main`, `master`, or equivalent). Releases land through the normal branch-and-PR path; if HEAD is the default branch, the release stops immediately.
- **Clean working tree.** No uncommitted changes. Commit or stash through `/ca:commit` first.
- **Green suite.** The last suite run must have passed. A red suite blocks tagging.
- **No open CONFIRM blocks.** Any unresolved `[CONFIRM-NN]` block stops the release.

Every `feat` and `fix` commit in the release window must carry a `CHANGELOG:` footer. A commit missing that footer is a hard block. The skill never auto-fills one.

### CHANGELOG: Footer Format

The `CHANGELOG:` footer is part of the commit body, following the Conventional Commits trailer convention:

```
feat(release): resolve baseline tag through tested helper

CHANGELOG: Tag derivation now resolves the ca baseline tag through the tested helper, excluding pre-releases and ca-sandbox tags.
```

`/ca:release` rolls these footers into the new changelog section. If a `feat` or `fix` commit has no footer, it surfaces the commit and stops.

## Check Readiness Without Tagging

Before running the full release, use `--dry-run` to see the bump classification and the commit window:

```text
/ca:release --dry-run
```

This runs every gate and surfaces a readiness report. It stops before composing the tag. Use it to confirm the derived version and the commit set look correct before proceeding.

`--dry-run` combines with an explicit version:

```text
/ca:release "X.Y.Z" --dry-run
```

## Run the Release

```text
/ca:release
```

No version argument means `--auto`: the version is derived from the commit log. Supply it explicitly when you need a specific version:

```text
/ca:release "X.Y.Z"
```

An explicit version that disagrees with what the commit log requires is a hard block. The bump is never silently adjusted. An explicit version and `--auto` are mutually exclusive.

### Phase 1: Version and CHANGELOG

The skill reads every `plugins/ca/`-scoped commit since the last `ca` SemVer tag. Commits under `plugins/ca-sandbox/` do not affect the bump or the changelog. The highest-precedence type in the window determines the bump:

| Highest-precedence type in the window | Bump |
|---|---|
| `BREAKING CHANGE:` footer or `!` after type/scope | major |
| `feat` | minor |
| `fix`, `perf`, or `refactor` | patch |
| `test`, `docs`, `chore`, or `ci` only | no bump; nothing to release |

The `CHANGELOG:` footers from `feat`, `fix`, and `perf` commits are appended to `CHANGELOG.md` under a new Keep-a-Changelog heading:

```
## [X.Y.Z] — YYYY-MM-DD

### Added
- ...

### Fixed
- ...
```

Prior sections stay intact. If `CHANGELOG.md` does not exist, the skill creates it. The README version badge, command/skill/agent count badges, and the `COMMANDS.md` catalog are also updated to match the repo. If those changes require a commit before tagging, it routes through commit-gate.

### Phase 2: Tag

The annotated tag is composed locally from the Phase 1 changelog section. The tag is never pushed without authorization. Phase 2 ends with a report: version, bump rationale, per-commit classification, the new changelog section, and the tag SHA.

### Phase 3: Publish (Requires Authorization)

The tag and GitHub Release publish together, and only after you authorize them. Without authorization, nothing leaves the local repository.

## Review and Authorize

Read the Phase 2 report. When the version, classification, and changelog section look correct, authorize publication.

On authorization:

1. The tag is pushed to the remote.
2. A GitHub Release is created. The notes are the Phase 1 changelog section verbatim; they are never re-derived or hand-written.
3. The Release is read back via `gh release view` to confirm it is non-draft and on the correct tag. If `gh` is unavailable or the call fails, the skill surfaces the exact manual command so you can finish publication by hand rather than leave it in an incomplete state.

The Release URL is reported only after the read-back confirms a non-draft Release on the correct tag.

## Common Blocks

| Situation | Effect | Resolution |
|---|---|---|
| A `feat` or `fix` commit has no `CHANGELOG:` footer | Phase 1 stops; the commit is surfaced | Add the footer to the commit; re-run |
| Explicit version disagrees with the commit log | Hard block | Use `--auto` or supply the correct version |
| Suite is not green | Pre-flight stops | Fix the failing tests; re-run |
| Window is non-bumping (`test`/`docs`/`chore`/`ci` only) | Phase 1 stops | Nothing user-visible to release |
| Dirty working tree | Pre-flight stops | Commit or stash via `/ca:commit` |
| HEAD is on the default branch | Pre-flight stops | Switch to a feature branch |

Any block may be bypassed only through `/ca:override`.

## See Also

- [release command reference](/reference/commands/release/): arguments and hard gates
- [release skill reference](/reference/skills/release-2/): full phase-by-phase specification
