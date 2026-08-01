---
entity: skills/release
related: [commands/release, commit-gate]
gates:
  - gate: declared-target resolution
    when: before any read or write
    effect: every fact about the release comes from the project's declared release-targets file; an unrecognised or ambiguous target name stops rather than resolving to a guess
  - gate: version derivation
    when: before tagging
    effect: the version bump is derived mechanically from the target's own payload commits, not guessed, and must agree with every declared manifest before anything is tagged
  - gate: check-only pre-tag commands
    when: after surfaces are updated, before the tag
    effect: the row's declared checks run in order and stop at the first failure; a check that mutates the working tree blocks, because a check is not allowed to be a fixer
  - gate: publication authorization
    when: after the local tag is composed
    effect: pushing the tag and creating the public release both wait for your explicit go-ahead — nothing about the tag composition authorizes publishing it
---

## What it does

This is the only sanctioned path to a version tag, invoked by the release command on a
non-default branch with a green suite. It carries no knowledge of any particular project: the tag
prefix, the manifests, the changelog, the payload scope, and any pre-tag checks are all read from
the project's declared `.codearbiter/release-targets.md`, so the same skill serves a
single-artifact repository and a monorepo without a repo-local variant.

It resolves the last tag *within the selected target's own series* rather than using a bare
`git describe`, because in a multi-artifact repository the nearest tag may belong to a sibling. It
then derives the version bump from the Conventional Commits history in that target's payload, rolls
the qualifying commits into the declared changelog, composes an annotated tag locally, and — only
once you authorize it — pushes the tag and publishes it as a public release using that same
changelog section as its notes.

## Phases

1. Resolve the declared row for the target, scope the commit window to its payload, and confirm
   the last tag belongs to its own series.
2. Derive the version bump mechanically from that window, confirm it against every declared
   manifest, and roll the qualifying commits into a new changelog section.
3. Update the declared surfaces and run the row's declared pre-tag checks in order — check-only,
   so one that mutates the tree stops the release.
4. Compose the annotated tag locally and report the target, the version, the bump rationale, and
   the tag — without publishing anything yet.
5. On your explicit authorization, push the tag, create the public release from the same
   changelog section, and read the result back to confirm it actually published.

## Exits

A completed run leaves a pushed tag and a confirmed, non-draft public release whose notes are
exactly the changelog section composed earlier. Without your authorization, the tag and changelog
stay staged locally and nothing leaves the repository. A project with no declared target file
enters the back-fill lane instead, which proposes a row and writes nothing unconfirmed.
