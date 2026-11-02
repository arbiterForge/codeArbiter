---
entity: commands/release
related: [commit, pr, skills/release]
use_when: "A declared release target's branch is clean, its suite is green, and you are ready to cut a version."
avoid_when: "Work still in progress, which lands through `/ca:feature` or `/ca:fix` first, because a release only aggregates what has already passed."
asks: "Which target to release when more than one is declared, and your confirmation of a proposed target declaration if none exists yet. It never accepts a version number from you, and publishing waits for your explicit go-ahead."
produces: "A release pull request with the derived version, the rolled-up changelog and updated manifests; `--dry-run` previews it with nothing written. Nothing is published without your authorization."
gates:
  - gate: changelog completeness
    when: same phase as version derivation
    effect: every bumping commit in the release window must carry its own changelog note; a missing one blocks rather than being auto-filled
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
silently papered over. Preparation stops at a release PR. Only after that PR merges and its exact merged commit passes
required checks can a qualifying hosted publisher compose the tag. Publication consumes explicit
one-cohort permission, not CI success alone. A declared protected automatic publisher can consume
the merge instruction given after the release-PR report and before merge; it must not ask twice
for the same cohort or reuse that authority for a different candidate.

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
Illustrative report, not a captured release:
Target: the selected project declaration.
Derived identity and declared surfaces: reported.
Release changes: committed through commit-gate.
Asset names and hosted qualification path: reported.
Next: release PR, owner decision, exact merged-head CI.
No interactive tag composition or publication occurred.
```

The [workflow comparison](/concepts/workflow-routes/) distinguishes this publication route from feature delivery and initialization.
