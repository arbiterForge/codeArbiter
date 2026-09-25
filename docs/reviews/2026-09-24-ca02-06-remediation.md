# September 24 audit remediation

## Source boundary

Integrated `arbiterForge/codeArbiter@28f14f59f1a5e7231ee21d5f75d161ad1c51939a`,
which merged #860, into the existing #861 branch without rewriting its history.
This is a source review candidate, not a published release or host qualification.
CA-01 and the August RA findings are not this change's scope.

## Implementation disposition

| Finding | Change | Remaining release evidence |
| --- | --- | --- |
| CA-02 | Preserve #860's Claude authority producers. Before HTML authoring, inspect the installed host identity, required resources and OS-specific hook registrations. Pi and incomplete installations fail early with `HOST_WORKFLOW_UNAVAILABLE`. Recheck before plan authoring; preserve existing Markdown and the inline small lane. | Normal supported-channel installation and live host lifecycle qualification are separate from resource presence. No Pi authority or new maturity claim is implied. |
| CA-03 | Synchronize complete owning LICENSE and Go runtime notices into each installable subtree. Exact-source archive and Codex npm assembly require matching bytes; the Pi allowlist includes its nested LICENSE. | Inspect corrected published archives and installed channels after an authorized release. |
| CA-04 | Companion PRs `arbiterForge/arbiterforge-site#2` and `arbiterForge/.github#2` replace stale copied installation and trust claims with product-owned links. | Rendered review and authorized deployment read-back. |
| CA-05 | SECURITY discloses the native helper and host qualification boundary. CLA becomes a non-operative status notice; LICENSE remains unchanged. | Maintainer policy review and qualified legal advice where needed. |
| CA-06 | README names explicit statusline uninstall. Reinstallation still refreshes its path and preserves the prior backup. | Publication and operator-facing read-back. |

## Verification boundaries

`ArtifactClient.workflow_preflight()` is a read-only installed-resource inventory.
It cannot grant authority, authenticate the user, prove hook trust or turn a
fixture into live host evidence. Existing native digest checks, approval,
prerequisite, verification, review and acceptance gates remain unchanged.

Admission regressions cover current Claude and Codex registrations, Pi refusal,
missing and nonregular helpers, linked ancestors, malformed/duplicate/oversized
registries, redirected and asynchronous hooks, OS-specific handler selection,
ambiguous host identities, repeated checks, and unchanged small/legacy routes.
Fixtures provide actual installed source resources rather than a production
bypass flag. The cold Pi test first proves that normal authoring is refused,
then separately exercises the explicitly synthetic engine lifecycle.

Package tests inspect the actual archives and Codex npm projection. Public claim
checks validate source text and links, not deployed behavior or legal meaning.
The exact-head hosted merge-readiness gate and independent review must complete
before merge. Record actual run identities and outcomes in the PR, not invented
verification receipts in this document.

## Integration and rollback

Recompute candidate versions from the integrated main; never reuse a published
identity. A later main advance requires a preserving merge and fresh exact-head
checks. Regenerate all host surfaces together.

Rollback is a reviewed revert. Preserve published tags, package bytes, LICENSE,
and historical authority evidence. Do not relax validation, manufacture receipts,
substitute a different runtime package or create fallback artifacts to proceed.
