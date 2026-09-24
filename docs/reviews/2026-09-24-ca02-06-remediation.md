# September 24 audit remediation

## Source boundary

Prepared from `arbiterForge/codeArbiter@48c32f3516320469957ed0bd387534a6a76d3594`.
This is a review candidate, not a release, package qualification or approval
receipt. The September 24 CA findings are distinct from the August RA findings.
CA-01 is not part of this change.

## Disposition

| Finding | Change and remaining evidence |
| --- | --- |
| CA-02 | Claude production authority is owned by open PR #860, inspected at `22a100e10d47823b742c382ee2a3c2a53b4781bb`. Do not duplicate it or treat it as released. Early host-workflow admission remains unimplemented here. Pi's unsupported boundaries and production consumer-journey qualification remain open. |
| CA-03 | Sync owning LICENSE and Go runtime notices into each installable subtree. Exact-source archive assembly independently requires complete matching bytes. Pi's package allowlist includes its nested LICENSE. Hosted candidate packages and normal installed channels still need read-back after release. |
| CA-04 | Companion review branches in `arbiterForge/arbiterforge-site` and `arbiterForge/.github` replace stale copied installation, version and broad policy claims with product-owned links. Historical proof assets remain unchanged. |
| CA-05 | SECURITY discloses the native helper and separates engine capability from host qualification. CLA is a status notice, not an active agreement. LICENSE is unchanged; legal approval remains a maintainer responsibility. |
| CA-06 | README names explicit statusline uninstall. Reinstall still refreshes the path and preserves the prior backup. A fixture exercises install, reinstall and restoration without touching real user settings. |

## Integration and verification

PR #860 and the separate farm work may advance adapter versions. Rebase the
second-to-merge change and derive fresh candidate versions from main; do not
retarget tags or reuse published package identities. Regenerate host projections
and recheck the exact integration head.

Package tests must inspect the actual archive and Codex npm projection, not only
the checkout. Source-contract tests for public wording do not establish live
network behavior, legal interpretation or deployed-site state.

For CA-02, the remaining acceptance evidence is a fresh supported consumer
installation followed by approval, prerequisite satisfaction, verification,
independent review, acceptance and interruption recovery. Missing host authority
must be detected before new full-lane authoring, while existing Markdown pairs
and the inline small lane retain their existing behavior. No fallback artifact,
fabricated receipt, relaxed validation or automatic maturity promotion is allowed.

## Rollback

Revert this candidate through a reviewed change if its contracts regress.
Preserve original LICENSE bytes, published tags, old package bytes and all
historical evidence. Reverting the wording does not qualify an unsupported host;
retain explicit limitations until an independently verified correction ships.
