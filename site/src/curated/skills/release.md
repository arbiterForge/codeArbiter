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
    when: at the qualifying hosted publication boundary
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
the qualifying commits into the declared changelog, prepares a reviewed release PR and stops. After merge and exact-head CI, the qualifying hosted
publisher composes the tag in its isolated checkout and consumes explicit cohort-specific
publication authority. No interactive local tag fallback is permitted.

## Phases

1. Resolve the declared row and target-scoped history, then derive the version through the
   declared policy. Missing declarations, required notes and ambiguous selections remain stops.
2. Update the declared surfaces, run ordered check-only pre-tag checks, and commit through
   `commit-gate`. Report asset names and the reviewed hosted qualification path, then open the
   release PR and stop this invocation. A local build is not a transferable publication payload.
3. After the PR merges, the qualifying hosted publisher verifies the exact fetched default-branch
   candidate and current green evidence. Qualify the declared inventory, classify existing tag
   state, and compose/verify the annotated tag only in that hosted checkout.
4. Consume explicit one-cohort publication permission, publish the verified identity and assets,
   then read back the remote result. A declared protected publisher can consume the instruction
   given to merge the already-reported release PR; green CI alone supplies no authority.
5. When provenance is declared, retain its original receipt for a separate reviewed closeout PR.
   Publication and a merged provenance record are distinct completion boundaries.

## Exits

Preparation ends at the release PR. A qualified hosted tag report without applicable publication
authority leaves nothing published. After authorized publication, read-back must confirm the exact
non-draft release and declared inventory. A declared provenance receipt remains pending until its
separate PR merges; without a declared manifest, explicitly report the skip. Preserve evidence on
partial failure instead of re-creating published tags or hiding an incomplete result.

A project with no target file uses confirmed back-fill for a real run. A dry run only reports the
proposal and locally evaluable derivation; it never fetches, executes declared checks, writes,
commits, tags or publishes. See [the release guide](/guides/releasing-a-version/) and its
[execution map](/guides/releasing-a-version/#execution-map) for the complete human handoff.

The [workflow comparison](/concepts/workflow-routes/) distinguishes this publication route from feature delivery and initialization.
