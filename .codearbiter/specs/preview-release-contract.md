# Feature spec — Declarative release version and publication-asset policies

**Status:** APPROVED — the user explicitly approved this narrow governance extension on 2026-09-13; this file transcribes the approved checkpoint-035 boundaries without adding a new product choice.

**Governs:** core/pysrc/_releaselib.py, core/surface/skills/release/SKILL.md, core/surface/commands/release.md, core/surface/skills/INDEX.md, .github/scripts/test_release_lib.py, .github/scripts/test_release_trace.py, .codearbiter/security-controls.md

## Problem

The portable release lane assumes every declared target uses three-component SemVer and publishes no generated release assets, so it cannot govern a caller whose existing releases use monotonically increasing two-component Preview identities and an exact generated asset inventory.

The caller is a repository maintainer declaring a release target. Done means the same generic target row keeps producing the next valid identity and exact asset set as the series advances, while all existing SemVer targets behave exactly as before.

This feature is one concern: making version derivation and publication assets explicit properties of a declared release target. It does not declare or publish an Arbiter Academy release.

## Approach

Extend the existing protected `release-targets.md` row grammar with two optional, orthogonal policy seams. A `version-policy` defaults to `semver`; the added `numeric-sequence` policy uses a declared `initial-version` to fix the dotted numeric shape and increments only the final component. An optional `release-build` command and repeated `release-asset` filename templates let the lane build into an empty temporary directory and prove the directory and published Release contain exactly the rendered inventory.

This is preferable to hard-coding a Preview prefix or version because the row remains the source of repository-specific facts. It is also preferable to accepting arbitrary regex and arithmetic expressions because those would turn validation and ordering into unbounded executable policy. The trade-off is a deliberately narrow second built-in policy rather than a general version-language interpreter.

## Scope

- Add one declarative version-policy seam to the existing release-target row grammar. Existing rows remain SemVer by default; a numeric-sequence row derives the next fixed-shape dotted numeric identity by incrementing its final component.
- Add a separate declarative publication-asset contract: an optional build command plus an exact list of safe filename templates rendered from the derived version and tag.
- Extend the shared release helper, generated host copies, public release surfaces, security-boundary description, and focused/full tests so the policy is enforced rather than remembered.
- Preserve existing target resolution, Conventional Commit window classification, SemVer arithmetic, changelog, manifest equality, immutable-tag classification, pre-tag, committed-artifact freshness, provenance, publication authorization, and generated parity.
- Prove a generic Preview-like row advances `0.30` to `0.31` and later `0.31` to `0.32` without changing its declaration, and requires exactly six declared assets.
- Do not add an Academy-specific row, name, release, tag, workflow, or hard-coded single future version in shared release logic.

## Decided parameters

- The grammar key is `version-policy`; omission means `semver`, preserving every existing row without migration.
- The only new policy is `numeric-sequence`; it requires `initial-version`, whose two or more dot-separated numeric components fix the component count for the whole series.
- Numeric components use canonical decimal spelling: zero is `0`, positive values have no leading zero, and derivation increments only the final component.
- Conventional Commit classification remains the release-eligibility and changelog grouping source. Under `numeric-sequence`, `patch`, `minor`, and `major` all advance the sequence exactly once; `none` still refuses a release.
- Scheme-aware helper commands own tag selection, comparison, next-version derivation, changelog section extraction, and notes-heading matching. Existing SemVer helper commands and signatures remain supported.
- Publication assets use an optional `release-build` scalar plus one or more repeated `release-asset` values; either both are declared or neither is.
- Each `release-asset` is a flat safe filename template. Only `{version}` and `{tag}` placeholders are allowed; absolute paths, separators, traversal, duplicate rendered names, control characters, shell metacharacters, and unknown placeholders are rejected.
- The release lane exports `VERSION`, `RELEASE_TAG`, and `RELEASE_ASSET_DIR` to `release-build`. The command inherits the protected, length-capped operator-authored executable-input boundary and must leave the tracked tree clean.
- The output directory starts empty. Every rendered asset must be one non-symlink regular non-empty file, and no undeclared entry may exist.
- Publication uploads only the helper-verified file list and reads the Release back to prove the published asset names equal the declared set. Publication still requires the existing explicit authorization.
- This extension reuses ADR-0024's accepted protected executable-input class and the existing release row mechanism; it does not create an ADR that freezes a repository to one version.

## Acceptance criteria

1. Existing rows without `version-policy` parse and behave exactly as SemVer rows, including their current resolution trace and helper CLI behavior.
2. A `numeric-sequence` row with an initial two-component identity selects the highest same-shape tag in its prefix, rejects malformed or leading-zero candidates, and derives the next identity by incrementing the final component.
3. Numeric-sequence derivation refuses a regressing or shape-changing manifest floor, an invalid initial identity, an unknown policy, or a policy-incompatible field instead of silently defaulting.
4. Conventional Commit classification still determines whether a release window is bumping; a numeric-sequence policy changes only version arithmetic, while SemVer preserves patch/minor/major arithmetic.
5. A release row can declare `release-build` and repeated `release-asset` filename templates using only the derived version and tag placeholders; rendering a generic Preview-like row produces exactly six expected names.
6. Release-asset declarations reject duplicate, absolute, escaping, nested, empty, unsafe, or unknown-placeholder names and reject build/list fields that are only partially declared.
7. Exact inventory verification accepts only a clean directory containing each rendered regular, non-symlink, non-empty asset exactly once and rejects missing, extra, symlinked, empty, or non-file entries.
8. The release skill resolves the row policy mechanically, derives versions through the helper, executes release-asset generation only after the existing release edits and checks, verifies exact local inventory before publication, uploads exactly that list after explicit authorization, and verifies the published asset-name inventory.
9. Canonical shared helper and release-surface sources regenerate byte-identical Claude, Codex, Pi, and CI copies; focused tests, trace tests, generation checks, and the repository's full required validation remain green.
10. The same unchanged generic declaration proves consecutive `0.30` to `0.31` and `0.31` to `0.32` derivations and corresponding versioned asset names, so future releases cannot require a single-version policy edit.
11. This checkpoint creates no tag or GitHub Release and makes no Arbiter Academy repository mutation.
12. Changelog section extraction, notes-heading validation, manifest-floor comparison, tag selection, and publish-state inputs accept the declared numeric-sequence shape while retaining the current strict SemVer grammar for default rows.

## Open questions

None. The approved campaign checkpoint fixes the user-visible and irreversible boundaries; the remaining choices are implementation parameters recorded above.

## Review and approval evidence

Mechanical self-review found no placeholder, scope contradiction, NOT-building conflict, accepted-ADR conflict, or untestable criterion. The `uncovered-intent` backstop returned empty before this file was written.

Adversarial review identified three credible failure modes. First, a permissive version regex could weaken current SemVer targets; the default is therefore unchanged and separately regression-tested. Second, generated assets could smuggle undeclared files or path traversal into a Release; templates are flat, narrowly tokenized filenames and both local and published inventories must match exactly. Third, numeric sequencing could bypass changelog and release-eligibility rules; only arithmetic changes, while the existing window classification, footer gate, changelog, clean-tree, tag, and authorization gates remain mandatory.

Negative completeness question: if every criterion above passed and nothing else changed, the remaining failure would have been SemVer-only changelog and notes helpers rejecting a valid numeric-sequence release. Criterion 12 adds that previously missing obligation. No other in-scope behavior would remain broken.

Approval is the user's explicit 2026-09-13 “yes” to the proposed narrow reusable governance/release-tool extension, as durably recorded in campaign revision 463. This spec does not expand that approval.
