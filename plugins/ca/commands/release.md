---
description: Cut a release for one of the four independently-versioned plugins. Selects the target's tag series, payload, manifests, changelog, and built artifacts; derives SemVer from that payload's commit window; publishes only on explicit authorization.
argument-hint: "[ca | ca-codex | ca-sandbox | ca-pi]"
---

# /ca:release — target-aware tagged release

The only permitted path to a version tag. A release is a deployment-readiness assertion for one
specific plugin payload at one commit. `/ca:release` routes to the `release` skill; it does not
duplicate the release gates here.

## Target

The optional argument selects one independently-versioned plugin. A bare command defaults to `ca`.

| Target | Tag series | Manifest | Changelog |
|---|---|---|---|
| `ca` | `vX.Y.Z` | `plugins/ca/.claude-plugin/plugin.json` | `CHANGELOG.md` |
| `ca-codex` | `ca-codex-vX.Y.Z` | `plugins/ca-codex/.codex-plugin/plugin.json` | `plugins/ca-codex/CHANGELOG.md` |
| `ca-sandbox` | `ca-sandbox-vX.Y.Z` | `plugins/ca-sandbox/.claude-plugin/plugin.json` | `plugins/ca-sandbox/CHANGELOG.md` |
| `ca-pi` | `ca-pi-vX.Y.Z` | `plugins/ca-pi/package.json` plus generated root `package.json` | `plugins/ca-pi/CHANGELOG.md` |

An unknown target STOPs. It is never guessed from the current branch or changed files.

## Flow

1. **Resolve the target row.** The shared release helper supplies the tag prefix. The last tag and
   commit window are scoped to that tag series and payload only.
2. **Prove readiness.** The tree is clean, HEAD is not the default branch, the target has a
   bump-earning commit window, its manifests agree, and every shipped bundle rebuilds cleanly.
3. **Derive version and changelog.** Conventional Commits determine the bump. Every `feat` and
   `fix` requires a `CHANGELOG:` footer; `perf` footers are rolled when present, while `refactor`
   earns a patch without inventing a user-facing entry.
4. **Sync release surfaces.** The selected manifest and target-specific generated or README
   surfaces move together through the normal commit gate.
5. **Compose and report.** An annotated tag is created locally and the target, classification,
   changelog section, and tag SHA are reported.
6. **Publish on authorization.** The tag and GitHub Release publish together only after the user
   explicitly approves publication. The release is read back and the tag provenance is recorded.

Only `ca` may hold GitHub's repo-wide Latest badge. Every sibling release explicitly declines it.

## Usage

```text
/ca:release
/ca:release ca
/ca:release ca-codex
/ca:release ca-sandbox
/ca:release ca-pi
```

Codex uses `$ca-release <target>`; Pi uses `/ca-release <target>`.

## When not to use it

- Work is still in progress: land it through the owning feature, fix, or chore lane.
- The tree is dirty or HEAD is the default branch: prepare a release branch first.
- You only want readiness information: inspect the target's release workflow and commit window
  without invoking the mutating release lane.
- A published release is wrong: fix forward and publish a new version. Never move or delete the
  published tag.

## Hard gate

MUST resolve exactly one supported target before release work begins. MUST scope the tag series,
commit window, manifest, changelog, payload, and built artifacts to that target. MUST derive SemVer
from the target's Conventional-Commit history and MUST NOT tag a non-bumping window. MUST NOT
auto-fill a missing required `feat`/`fix` changelog footer. MUST NOT publish a tag or GitHub Release without explicit
authorization. MUST NOT give the Latest badge to a sibling series. MUST NOT move, retarget, or
delete a published tag; correction is a new version.
