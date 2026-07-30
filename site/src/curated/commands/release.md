---
entity: commands/release
related: [commit, pr, skills/release]
gates:
  - gate: version derivation
    when: before a tag is composed
    effect: the SemVer bump is computed mechanically from Conventional Commits since the last tag — an explicit version that disagrees with that classification blocks rather than being silently adjusted
  - gate: changelog completeness
    when: same phase as version derivation
    effect: every feat/fix/perf commit in the release window must carry its own changelog note; a missing one blocks rather than being auto-filled
  - gate: publish authorization
    when: after the tag is composed locally
    effect: the tag and the GitHub Release publish together, and only once you explicitly say to
---

## What it does

This is the only sanctioned way a version tag gets created. It never invents a version number — it
walks every commit since the last tag, classifies each by its Conventional Commits type, and applies
whichever bump that history actually earns (a breaking change beats a feature, a feature beats a
fix). The changelog section is assembled the same mechanical way, pulled from the commit footers
rather than freehand summary, and a commit that should have carried one but didn't is a hard stop
rather than a gap silently papered over. Composing the tag locally and publishing it are two separate
moments: nothing pushes to the remote or shows up as a GitHub Release until you explicitly authorize
that second step.

## Usage

```
/ca:release ["<version>"] | --auto | --dry-run
```

An explicit version still gets checked against the derived classification; `--auto` derives it
outright (the default when no version is given); `--dry-run` runs every check and reports readiness
without composing anything.

## Example

```text
> /ca:release --dry-run

Working tree clean. Branch: release/prep (not the default branch — OK).
Last tag: v2.4.1. Scanning 14 commits since...
Classification: 3 feat, 6 fix, 5 chore -> minor bump.
Derived version: v2.5.0. Matches plugin manifest? no — manifest still reads 2.4.1, would need updating.
Changelog: all 9 feat/fix commits carry a CHANGELOG: footer.
Dry run complete — no tag composed. Update the manifest version, then re-run without --dry-run.
```

## When to reach for it

Reach for `/ca:release` once the target branch is clean and its suite is green and you're ready to
cut a version. Work still in progress lands through `/ca:feature` or `/ca:fix` first — a release
aggregates what already passed, it doesn't chase down anything new.
