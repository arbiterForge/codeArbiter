---
entity: skills/release
related: [commands/release, commit-gate]
gates:
  - gate: version derivation
    when: before tagging
    effect: the version bump is derived mechanically from the commit log, not guessed, and must match the manifest's version field before anything is tagged
  - gate: publication authorization
    when: after the local tag is composed
    effect: pushing the tag and creating the public release both wait for your explicit go-ahead — nothing about the tag composition authorizes publishing it
---

## What it does

This is the only sanctioned path to a version tag, invoked by the release command on a
non-default branch with a green suite. It derives the version bump from the Conventional Commits
history since the last tag, rolls the relevant commits into the changelog, composes an annotated
tag locally, and — only once you authorize it — pushes the tag and publishes it as a public
release using that same changelog section as its notes.

## Phases

1. Derive the version bump mechanically from the commit log, confirm it against the manifest, and
   roll the qualifying commits into a new changelog section.
2. Compose the annotated tag locally from that changelog section and report the version, the
   bump rationale, and the tag — without publishing anything yet.
3. On your explicit authorization, push the tag, create the public release from the same
   changelog section, and read the result back to confirm it actually published.

## Exits

A completed run leaves a pushed tag and a confirmed, non-draft public release whose notes are
exactly the changelog section composed in the first phase. Without your authorization, the tag
and changelog stay staged locally and nothing leaves the repository.
