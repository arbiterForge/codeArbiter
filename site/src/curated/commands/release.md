---
entity: commands/release
related: [commands/commit, commands/pr, skills/release]
gates:
  - gate: target resolution
    when: before release state is inspected
    effect: selects exactly one plugin row and stops on an unknown target rather than inferring one
  - gate: target-scoped version derivation
    when: before a tag is composed
    effect: only commits in the selected payload and tag series influence the SemVer bump and changelog
  - gate: changelog completeness
    when: version and release notes are assembled
    effect: every feat and fix must carry its own changelog note; perf notes roll when present and refactor notes are never invented
  - gate: publish authorization
    when: after the annotated tag and report exist locally
    effect: the tag and GitHub Release publish together only after explicit approval
---

## What it does

codeArbiter contains four plugins with independent versions. This command selects the release target
and routes the matching tag namespace, payload, manifests, changelog, and built artifacts through
one release skill. A bare invocation preserves the default `ca` release path.

## Usage

```text
/ca:release [ca | ca-codex | ca-sandbox | ca-pi]
```

Codex uses `$ca-release`; Pi uses `/ca-release`. The target defaults to `ca`. There is no
user-supplied version: the selected payload's Conventional-Commit history determines it.

## Example

```text
> /ca:release ca-pi

Target: ca-pi
Tag series: ca-pi-v*
Payload window: plugins/ca-pi/ (tools/ excluded)
Manifest parity: plugins/ca-pi/package.json = generated root package.json
Derived bump: patch
Next version: ca-pi-v0.1.33
Built extensions: clean
```

The command continues through changelog and local tag composition. It stops again before pushing
the tag or creating the GitHub Release.

## Choose the target deliberately

- `ca`: Claude Code governance plugin and the only series eligible for the repo-wide Latest badge.
- `ca-codex`: Codex adapter.
- `ca-sandbox`: isolated exploration plugin.
- `ca-pi`: Git-installed Pi adapter with two manifests and committed extension bundles.

Use the [release guide](/guides/releasing-a-version/) for the per-target verification checklist and
bad-release recovery procedure.
