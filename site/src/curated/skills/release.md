---
entity: skills/release
related: [commands/release, skills/commit-gate]
gates:
  - gate: target isolation
    when: pre-flight resolves the release row
    effect: one plugin's tag or commit cannot influence another plugin's version, changelog, or payload
  - gate: version and artifact proof
    when: before tagging
    effect: the derived version must match every target manifest and all shipped bundles must rebuild without a diff
  - gate: publication authorization
    when: after the local tag and report exist
    effect: pushing the tag and creating the public release wait for explicit approval
  - gate: publication read-back
    when: GitHub operations return
    effect: the release is not accepted until a non-draft release on the expected tag is read back
---

## What it does

The release command routes here with one of four plugin targets. The skill resolves that target's
registered tag prefix, payload path, manifests, changelog, built artifacts, and Latest-badge policy;
then it derives the release from that isolated row.

## Phases

1. Prove the branch, tree, target-specific tag baseline, payload window, manifests, and built
   artifacts are ready.
2. Derive SemVer from the selected payload's commits, update its changelog and release surfaces, and
   route any required commit through the commit gate. Every `feat` and `fix` must already carry a
   `CHANGELOG:` footer; `perf` footers roll when present and `refactor` does not synthesize one.
3. Compose an annotated tag locally and report the classification, notes, and tag SHA.
4. After explicit authorization, publish the tag and GitHub Release, read the release back, and
   record the published tag's provenance.

## Target-specific state

`ca-pi` has two manifests and generated extension bundles. `ca` owns README version/count surfaces
and may receive the repo-wide Latest badge. Every sibling explicitly publishes with
`--latest=false`. The helper register, not prose memory, supplies each tag prefix.

## Exits and recovery

Without publish authorization, the local release state remains unpushed. A partial publish is named
and resumed rather than repeated blindly. A bad published release is superseded with a new version;
the original tag is immutable.
