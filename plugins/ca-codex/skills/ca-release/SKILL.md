---
name: ca-release
description: Cut a release the only sanctioned way — derive the target's declared version policy from the commit log, roll its changelog, compose an annotated tag, and optionally publish its exact declared assets. Takes the declared target's name as its only argument, or --dry-run to preview one with no write. The only path to a version tag.
argument-hint: "[target] | --dry-run"
---

# $ca-release — tagged release

The only permitted path to a version tag. A release is a deployment-readiness assertion: the codebase at this SHA satisfies the bar for shipping. `$ca-release` aggregates existing compliance — it does not duplicate it.

## Flow

Routes to the `release` skill, which resolves everything about the release from the project's **declared target file**, `<project-root>/.codearbiter/release-targets.md` — the tag prefix, declared version policy, manifests, changelog, payload scope, optional checks, and optional exact release-asset inventory. Nothing about any target is written here.

`$ca-release` takes the target's name as its only argument. When the declared file names exactly one target, a bare `$ca-release` uses it; when it names more, the argument is required and the skill STOPs rather than guessing. A project with no declared file at all enters the skill's own back-fill lane, which proposes a row and writes nothing without explicit confirmation.

1. **Pre-flight** — declared row resolved, working tree clean, not on the default branch, suite green, no blocking `[CONFIRM-NN]` open. Resolve `LAST_TAG` within that target's own tag series and scope the commit window to the row's declared payload, so a sibling target's commit never bumps this one or lands in its changelog.
2. **Version** — classify the window by Conventional Commits type and derive the next identity through the row's declared `version-policy` (`semver` by default). The base accounts for both the last compatible tag and every declared manifest. Every bumping commit must carry a `CHANGELOG:` footer; a missing one BLOCKs and is never auto-filled.
3. **Surfaces** — roll the section into the declared changelog, update every declared manifest, and run the row's declared `pre-tag` checks. After those edits are committed, an optional `release-build` produces the declared exact release-asset inventory in an empty temporary directory; tracked-tree mutation or inventory drift BLOCKs before the tag.
4. **Tag** — compose the annotated tag and report any verified asset inventory. Never push it or publish a Release without explicit user authorization. On authorization, upload only the verified inventory and require the published names to match exactly.

## Dry run

`$ca-release --dry-run [target]` runs Flow steps 1 and 2 above — Pre-flight in full, then Version's
read-only derivation: resolving the row, deriving the bump, classifying the window, and verifying
`CHANGELOG:` footer completeness — then stops before step 3 and reports exactly what a real run would
do: the target, the derived version and its rationale, the per-commit classification, and any blocker
Pre-flight or Version would itself have hit. Steps 3 (Surfaces) and 4 (Tag) never run: no changelog
edit, no manifest bump, no commit, no declared `pre-tag` check execution, no tag. The report also
prints the resolved row's fields verbatim, which doubles as a way to validate a freshly authored
`<project-root>/.codearbiter/release-targets.md` without tagging anything. Declared `pre-tag` checks
are listed, not run — they assert against the manifests AFTER the bump this mode never performs, so
running them early would report false failures against files `--dry-run` deliberately leaves
untouched, not a preview of anything real. A declared `release-build` and its asset templates are also
listed but never executed or rendered into files. `release`'s own SKILL.md is authoritative for the exact
stopping point.

## Arguments

- **`[target]`** — the name of a row in the declared target file (e.g. the name in `[ca]`). Optional only when exactly one target is declared. An unrecognised name STOPs; it is never resolved to a guess.
- **`--dry-run`** — preview a release with no write; see "Dry run" above. Combines with `[target]` exactly as a real run does — required only when more than one target is declared.

There is no version or `--auto` argument. The version is always derived from the commit log and the declared manifests — supplying one by hand is the thing this lane exists to prevent.

## Routes to

`release` ([routines/release/SKILL.md](../../routines/release/SKILL.md)), which is authoritative for the phase contents and gates summarized above.

## When NOT to use

- Tagging an in-progress branch → land work first via `$ca-feature` / `$ca-fix`.
- Pushing an already-composed tag → that is a separate user-authorized step.
- A changelog only → it is a phase output, not a standalone deliverable.
- Creating a declared target file ahead of a release → that is `context-creation`'s job, or the skill's back-fill lane at release time.

## Hard gate

MUST NOT compose a tag on a red suite. MUST NOT guess the version — it is derived from the commit log and the declared manifests. MUST NOT auto-fill a missing `CHANGELOG:` footer. MUST NOT resolve an unrecognised or ambiguous target to a guess. MUST NOT write to the default branch or force-push. MUST NOT push the tag or publish a Release without explicit user authorization. MUST NOT write, commit, or tag anything under `--dry-run` — it stops before Version step 3's writes even reach the working tree. Any BLOCK may be bypassed only via `$ca-override`.
