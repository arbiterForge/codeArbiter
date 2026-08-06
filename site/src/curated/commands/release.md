---
entity: commands/release
related: [commit, pr, skills/release]
gates:
  - gate: target resolution
    when: before anything is read or written
    effect: the target is looked up in the project's declared release-targets file; an unrecognised or ambiguous name stops rather than being resolved to a guess
  - gate: version derivation
    when: before a tag is composed
    effect: the SemVer bump is computed mechanically from Conventional Commits in the target's own payload — there is no way to supply a version by hand
  - gate: changelog completeness
    when: same phase as version derivation
    effect: every feat/fix/perf commit in the release window must carry its own changelog note; a missing one blocks rather than being auto-filled
  - gate: publish authorization
    when: after the tag is composed locally
    effect: the tag and the GitHub Release publish together, and only once you explicitly say to
---

## What it does

This is the only sanctioned way a version tag gets created, and it holds no knowledge of any
particular project. Everything it needs — the tag prefix, which manifests carry the version, which
changelog to roll into, what counts as the payload, and any checks to run before tagging — is read
from a file the project declares at `.codearbiter/release-targets.md`. One row means a
single-artifact repository; several rows mean a monorepo where each artifact versions on its own.

It never invents a version number. It walks the commits in the selected target's payload,
classifies each by its Conventional Commits type, and applies whichever bump that history actually
earns (a breaking change beats a feature, a feature beats a fix). The window is scoped to that
target, so a sibling's commit can never bump this one or land in its changelog. The changelog
section is assembled the same mechanical way, pulled from commit footers rather than freehand
summary, and a commit that should have carried one but didn't is a hard stop rather than a gap
silently papered over. Composing the tag locally and publishing it are two separate moments:
nothing pushes to the remote or shows up as a GitHub Release until you explicitly authorize that
second step.

## Usage

```
/ca:release [target] | --dry-run
```

The main argument is the name of a row in the declared target file. It is optional when the file
declares exactly one target and required when it declares more — with several declared, a bare
invocation stops rather than guessing which one you meant.

`--dry-run` previews a release with nothing written: it resolves the row, derives the version, and
verifies changelog-footer completeness, then reports exactly what a real run would do and stops
before anything is edited, committed, or tagged. It combines with `[target]` exactly as a real run
does.

There is no version argument and no `--auto`. A number you type is a number nobody checked, and
preventing exactly that is the reason this lane exists — so the version comes from the commit history
and the declared manifests, every time, with no override. A project with no declared file yet enters
the skill's back-fill lane, which proposes a row from what it can detect and writes nothing without
your confirmation.

## Example

```text
> /ca:release ca-codex

Resolved target `ca-codex` from .codearbiter/release-targets.md.
  tag series: ca-codex-v*   payload: plugins/ca-codex/
Working tree clean. Branch: release/prep (not the default branch — OK).
Last tag in this series: ca-codex-v0.2.4 (a sibling's v2.8.13 is ignored).
Scanning 9 commits in the payload...
Classification: 2 feat, 4 fix, 3 chore -> minor bump.
Derived version: 0.3.0. Declared manifest plugins/ca-codex/.codex-plugin/plugin.json reads 0.2.4 — will update.
Changelog: all 6 feat/fix commits carry a CHANGELOG: footer.
Declared pre-tag checks: 2 ran, both clean, tree unchanged.
Composed annotated tag ca-codex-v0.3.0 locally. Nothing pushed — authorize to publish.
```

## When to reach for it

Reach for `/ca:release` once the target's branch is clean and its suite is green and you're ready to
cut a version. Work still in progress lands through `/ca:feature` or `/ca:fix` first — a release
aggregates what already passed, it doesn't chase down anything new.
