# Implementation plan — Declarative release version and publication-asset policies

**Status:** APPROVED — faithful decomposition of the user-approved checkpoint-035 spec; no additional product, release, or irreversible decision is introduced.

**Spec:** `.codearbiter/specs/preview-release-contract.md`

## Acceptance-criterion ledger

- **AC-01:** Existing rows without `version-policy` parse and behave exactly as SemVer rows, including current trace and CLI behavior.
- **AC-02:** `numeric-sequence` selects and advances fixed-shape dotted numeric identities, rejecting malformed candidates.
- **AC-03:** Invalid, regressing, shape-changing, unknown, or incompatible version-policy state fails closed.
- **AC-04:** Conventional Commit classification still gates release eligibility; only version arithmetic differs by policy.
- **AC-05:** A declared release build and six templated assets render to the exact expected names.
- **AC-06:** Unsafe, duplicate, malformed, unknown-placeholder, or partial asset declarations fail closed.
- **AC-07:** Exact local inventory accepts only the declared non-empty regular files and rejects missing, extra, symlinked, empty, or non-file entries.
- **AC-08:** The release skill mechanically derives policy, builds and validates assets, preserves authorization, uploads only the verified list, and verifies published names.
- **AC-09:** Canonical sources regenerate byte-identical host and CI copies; focused, trace, generation, and full validation pass.
- **AC-10:** One unchanged declaration advances `0.30` to `0.31` and `0.31` to `0.32`, including versioned assets.
- **AC-11:** No tag, GitHub Release, or Arbiter Academy mutation occurs in this checkpoint.
- **AC-12:** Changelog, notes, manifest-floor, tag-selection, and publish-state seams support the declared numeric shape without relaxing default SemVer.

## Ordered tasks

| id | path(s) | verification | maps-to | covers | depends-on | status |
|---|---|---|---|---|---|---|
| T-01 | `.github/scripts/test_release_lib.py`; `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k NumericSequence` passes after its new tests are first observed failing | TDD obligations AC-01, AC-02, AC-03, AC-04, AC-10 | AC-01, AC-02, AC-03, AC-04, AC-10 | — | ACCEPTED |
| T-02 | `.github/scripts/test_release_lib.py`; `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k DeclaredVersionChangelog` passes after its new tests are first observed failing | TDD obligation AC-12 | AC-12 | T-01 | ACCEPTED |
| T-03 | `.github/scripts/test_release_lib.py`; `core/pysrc/_releaselib.py` | `python .github/scripts/test_release_lib.py -k ReleaseAssetContract` passes after its new tests are first observed failing | TDD obligations AC-05, AC-06, AC-07, AC-10 | AC-05, AC-06, AC-07, AC-10 | T-01 | ACCEPTED |
| T-04 | `.github/scripts/test_release_lib.py`; `core/pysrc/releasehash.py`; `core/surface/skills/release/SKILL.md`; `core/surface/commands/release.md`; `core/surface/skills/INDEX.md`; `.codearbiter/security-controls.md` | `python .github/scripts/test_release_lib.py -k ReleaseSurface` passes and structural assertions prove the declared policy, exact-asset, clean-tree, read-back, and authorization sequence | TDD obligations AC-08 and executable-input security boundary | AC-08 | T-01, T-02, T-03 | ACCEPTED |
| T-05 | `.github/scripts/test_release_trace.py`; `.github/scripts/_releaselib.py`; `plugins/ca/hooks/_releaselib.py`; `plugins/ca-codex/hooks/_releaselib.py`; `plugins/ca-pi/hooks/_releaselib.py`; `plugins/ca/hooks/releasehash.py`; `plugins/ca-codex/hooks/releasehash.py`; `plugins/ca-pi/hooks/releasehash.py`; `plugins/ca/skills/release/SKILL.md`; `plugins/ca-codex/routines/release/SKILL.md`; `plugins/ca-pi/routines/release/SKILL.md`; `plugins/ca-codex/skills/ca-release/SKILL.md`; `plugins/ca-pi/skills/ca-release/SKILL.md` | `python tools/sync-core.py --check; python tools/build-surface.py --check; python .github/scripts/test_release_trace.py; python .github/scripts/test_release_lib.py` all pass after regeneration | TDD obligation AC-09 and default-policy non-regression | AC-01, AC-09 | T-01, T-02, T-03, T-04 | ACCEPTED |
| T-06 | repository diff and refs only | `git diff --check; git status --short; git tag -l 'preview-*'; gh release list --repo arbiterForge/codeArbiter --limit 100` show only scoped source/test/governance changes and no created Preview tag or Release; `git -C C:/Users/brenn/projects/arbiter-academy status --short --branch` remains unchanged | TDD/process obligation AC-11 | AC-11 | T-05 | ACCEPTED |

T-05's declared generated scope also includes every transitive catalog and host index emitted by `tools/build-surface.py` from the changed canonical release command, skill, and index. These generator-owned outputs are reviewed and validated as part of the same task; none is hand-edited.

## Dependency order and MVP slice

Order: T-01 → T-02 and T-03 → T-04 → T-05 → T-06. T-02 and T-03 are independent after T-01, but they land sequentially because both touch the same canonical helper and test file.

**MVP slice:** T-01 through T-05. This is the smallest shippable mechanism: policy arithmetic, scheme-aware changelog handling, exact publication assets, governed release-surface wiring, and generated parity. T-06 is mandatory checkpoint-boundary proof, not extra product scope.

## Bijection and completeness proof

Every AC appears in at least one task's `covers` cell, and every task advances at least one AC. The mechanical `uncovered-intent` check against the approved spec returned empty. Negative completeness question: if every task passed and nothing else changed, the only remaining campaign obligation would be delivery through commit gate, review, PR, exact-head CI, and conditional merge; those are the feature lane's required finishing path rather than omitted implementation criteria.

## Autonomy and review boundary

The user approved the detailed checkpoint and explicitly directed the campaign to continue without inter-task prompts. Therefore this plan executes as one autonomous governed scope through fresh task authors, spec-compliance review, applicable security review, coverage audit, and fresh verification. Hard failures, ambiguity, or irreversible publication still stop. This plan never authorizes an Academy tag or Release.
