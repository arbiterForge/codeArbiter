---
title: Cut a Release
description: "Release one codeArbiter plugin through its own tag series, manifests, changelog, built artifacts, and verified GitHub Release."
journey:
  level: "Power user"
  time: "15 minutes"
  outcome: "Cut one target-specific release with consistent versions, artifacts, tag, and hosted checks."
  prerequisites:
    - "Maintainer access"
    - "A clean release branch with the target's changes committed"
  proof: "Manifest, changelog, tag, release artifacts, and hosted verification all name the same target version."
---

codeArbiter ships four independently-versioned plugins. The release lane selects one target and
keeps every version input and output inside that plugin's row. Use it only when the target's work is
already landed on a clean release branch and its verification is green.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/lane-release.svg"
    alt="The release lane from selecting one plugin target through derived semantic version, changelog and manifest updates, verification, annotated tag, and explicitly authorized publication."
    loading="lazy"
  />
  <figcaption>Each release is scoped to one plugin target; publication remains a separate explicit decision.</figcaption>
</figure>

<div class="ca-host-syntax">
  <strong>Host syntax:</strong> Claude Code uses <code>/ca:release</code>; Codex uses
  <code>$ca-release</code>; Pi uses <code>/ca-release</code>. Examples below use Claude Code syntax.
</div>

## Where the targets come from

The release lane holds no knowledge of any particular project. Every fact it
needs (the tag prefix, which manifests carry the version, which changelog to
roll into, what the payload scope is, and any checks to run before tagging) is
read from a file the project declares at `.codearbiter/release-targets.md`.

That means **the table below is codeArbiter's own configuration, not the lane's
behaviour.** Your project's table is whatever its own declared file says: one
row for a single-artifact repository, several for a monorepo. If you have no
declared file yet, the first `/ca:release` proposes one from what it can detect
and writes nothing until you confirm it.

Read the rest of this guide with that split in mind: the steps are general, the
four rows are ours.

## codeArbiter's own declared targets

| Target | Tag | Manifest(s) | Changelog | Built artifacts |
|---|---|---|---|---|
| `ca` | `vX.Y.Z` | `plugins/ca/.claude-plugin/plugin.json` | `CHANGELOG.md` | `plugins/ca/tools/farm.js` |
| `ca-codex` | `ca-codex-vX.Y.Z` | `plugins/ca-codex/.codex-plugin/plugin.json` | `plugins/ca-codex/CHANGELOG.md` | none |
| `ca-sandbox` | `ca-sandbox-vX.Y.Z` | `plugins/ca-sandbox/.claude-plugin/plugin.json` | `plugins/ca-sandbox/CHANGELOG.md` | sandbox and Claude-inside bundles |
| `ca-pi` | `ca-pi-vX.Y.Z` | `plugins/ca-pi/package.json` and generated root `package.json` | `plugins/ca-pi/CHANGELOG.md` | parent and child extension bundles |

A bare `/ca:release` means `ca`. Prefer the explicit target in maintainer work:

```text
/ca:release ca-codex
```

The command accepts a target, not a version. SemVer is derived from the selected payload's commit
history.

## Prerequisites

Before invoking the lane:

- check out a non-default release branch;
- leave the working tree clean;
- confirm the target has new commits in its payload since its own latest stable tag;
- confirm the last applicable suite was green;
- make sure every `feat` and `fix` commit carries a `CHANGELOG:` footer; add one to `perf` when the
  performance change should appear in user-facing release notes; and
- authenticate `gh` if you expect to authorize publication later.

Do not run release as a readiness query. It is a mutating lane that may update manifests, changelog,
generated surfaces, and a local tag.

## 1. Target-scoped pre-flight

The release skill resolves the target through the shared release register. It does not use bare
`git describe`, because the nearest tag in a multi-plugin repository may belong to a sibling.

It then verifies:

1. the last tag belongs to the target's tag series;
2. the commit window contains only changes under the target payload;
3. the window contains a SemVer-earning change;
4. the target manifest version can move to the derived version;
5. every committed bundle rebuilds without a diff; and
6. target-specific generated surfaces agree.

For `ca-pi`, the root `package.json` is generated install metadata and must equal the plugin
manifest. For `ca`, README badges, catalog counts, and command tables are synchronized from the
repository rather than incremented by hand.

## 2. Derive the version and changelog

The highest-precedence change in the target payload decides the bump:

| Commit evidence | Bump |
|---|---|
| `BREAKING CHANGE:` or a Conventional-Commit `!` | major |
| `feat` | minor |
| `fix`, `perf`, or `refactor` | patch |
| only `test`, `docs`, `chore`, or `ci` | no release; stop |

The same window supplies the changelog entries. Every `feat` and `fix` requires a `CHANGELOG:`
footer because release notes must not omit a user-visible change or invent one after the fact.
A `perf` footer is rolled when present. A `refactor` earns a patch version but does not require or
synthesize a user-facing changelog entry.

The selected changelog receives:

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added

- ...
```

Any manifest, changelog, or generated-surface update lands through the normal commit gate before
tagging.

## 3. Compose the local tag

The skill writes a multi-line annotated tag in the selected namespace and reports:

- target and payload window;
- previous and next version;
- per-commit classification;
- changelog section;
- rebuilt artifact status; and
- local tag SHA.

If the tag already exists at HEAD with the matching manifest version but has no GitHub Release, the
lane classifies that as a resumable publish rather than composing another tag.

## 4. Review and authorize publication

Nothing leaves the repository until you explicitly authorize publishing. On authorization, the
lane:

1. pushes the selected tag;
2. verifies the release-notes heading matches that tag;
3. creates the GitHub Release from the exact changelog section;
4. passes `--latest=false` for every sibling series;
5. reads the release back and requires a non-draft result on the expected tag; and
6. records the remote tag SHA and dereferenced commit in `.github/published-tags.json`.

Only a `ca` release may take GitHub's single repo-wide Latest badge, and only when it is actually
the newest release across all four series.

## Common stops

| Stop | Meaning | Recovery |
|---|---|---|
| Unknown target | No release row exists | Invoke one of the four exact target names |
| Empty or non-bumping window | This payload has nothing releasable | Land a bump-earning change or do not release |
| Manifest mismatch | The tag would advertise a version the payload does not report | Update the target surfaces through commit-gate |
| Bundle diff after rebuild | The repository would ship stale generated code | Commit the rebuilt artifact, verify, then re-run |
| Missing required `CHANGELOG:` footer on `feat` or `fix` | Release notes would silently omit a user-visible change | Correct the commit history through the governed path |
| Publish read-back fails | Tag/Release may be partially published | Keep the exact state and resume the missing step |

## Recover from a bad published release

Never move, retarget, or delete a published tag. Consumers can pin exact tags; changing the object
behind a published version makes verification history describe different code.

Fix the defect through a normal PR, invoke `/ca:release <target>` again, and publish the next
version. Mark the bad GitHub Release as a prerelease and add a note naming the superseding version.
The old tag remains the immutable identity of what shipped.

For the exact target register and every hard rule, read the
[`release` command](/reference/commands/release/) and [`release` skill](/reference/skills/release/).
