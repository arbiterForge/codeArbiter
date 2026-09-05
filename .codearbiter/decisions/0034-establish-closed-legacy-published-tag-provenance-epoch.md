---
status: accepted
date: 2026-09-05
title: Establish a closed legacy provenance epoch for unrecoverable published tags
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .github/published-tags.json, .github/legacy-published-tags.json, .github/scripts/check_tag_immutability.py, .github/scripts/tag_publication_receipt.py, .github/scripts/reconcile_tag_receipt.py, .github/scripts/test_tag_immutability.py, .github/scripts/test_tag_publication_receipt.py, .github/scripts/test_reconcile_tag_receipt.py, .github/actions/publish-release/action.yml, .github/RELEASE-PROVENANCE.md, .github/workflows/release.yml, .github/workflows/ci.yml, .codearbiter/security-controls.md
---

# ADR-0034 — Establish a closed legacy provenance epoch for unrecoverable published tags

## Status
Accepted — explicitly approved for authoring and acceptance by
SUaDtL@users.noreply.github.com on 2026-09-05.

## Context

The release guard treats `.github/published-tags.json` as original-publication evidence and refuses
a new release while any governed historical tag is absent. After PR #744 repaired the live tag
inventory reader, exact-main release run 33917217688 correctly exposed 44 absent tags and skipped
every publisher.

Bounded recovery across every accessible inspected source proved no original tag-ref object identity
for any of the 44 tags. Fifteen tags have surviving publisher logs that corroborate the tag name,
publication time, and peeled commit but omit the tag-ref object SHA. Twenty-eight have associated run
metadata whose logs are unavailable, and one has mutable GitHub Release metadata only. All current
ref identities were observed at
2026-09-04T20:45:43Z, but tag protection began later than some publications and cannot prove that a
ref never moved before observation.

Recording those current identities as original-publication receipts would fabricate provenance.
Keeping them permanently absent would preserve that semantic purity by making every future governed
release impossible, even though no accessible inspected retained source satisfies the missing proof.

## Decision

`.github/published-tags.json` remains exclusively the original-publication receipt ledger. Its
entries continue to mean that the recorded object identity was captured by the trusted publication
path; no legacy observation enters that file.

A separate, closed `.github/legacy-published-tags.json` records exactly the 44 approved historical
baselines observed at 2026-09-04T20:45:43Z. Each entry records tag name, object SHA, object type,
peeled commit, observation time, evidence source, and one evidence grade preserving the recovered
distinction: 15 `publisher-log-corroborated`, 28 `associated-run-metadata-only`, and one
`current-release-metadata-only`.

The approved identity-and-grade set is the tag-sorted JSON array of objects containing exactly
`tag`, `evidence_grade`, `source_id`, `object_sha`, `object_type`, and `commit_sha`, encoded as UTF-8
with lexicographically sorted object keys and compact JSON separators. Its SHA-256 is
`26f2d1b06b494dbcc721367e09af52f32ca1a50a71dddb457557af2a48cd8c48`. The inspected recovery
matrix SHA-256 is `cfb3f66e933edb6b1f075f3e089103115c95837b944d56e2c7338d0d3519e8a6`.
The ledger identifies this ADR, the observation time, its closed 44-record set, and both digests.
Adding or replacing a legacy identity or evidence grade requires a new accepted, user-attributed
ADR; release automation and receipt tooling never append to or rewrite the legacy ledger.

The immutability guard validates both ledgers strictly, rejects overlap, malformed evidence classes,
an altered closed-set identity, or an incomplete live inventory, and compares every recorded object
SHA with the live ref. Diagnostics and summaries distinguish original-publication receipts from
legacy baselines. A legacy mismatch states only that the tag moved after its recorded observation;
it never claims where the tag was originally published.

Strict release preflight accepts complete coverage across the disjoint union of the two ledgers only
when every recorded ref matches live state. Every tag outside the closed legacy set must have an
original-publication receipt before a later release proceeds. The existing prohibition on moving,
retargeting, or deleting published tags remains absolute, with no break-glass path.

The accepted residual risk is explicit: a historical tag moved before 2026-09-04T20:45:43Z could be
frozen at its later identity. Available evidence neither proves nor disproves such drift. The legacy
ledger establishes a forward immutability guarantee from the recorded observation; it does not
retroactively prove original publication identity.

## Alternatives considered

- **Permanent fail-closed quarantine** — rejected because the accessible inspected sources do not
  satisfy the historical proof precondition and that unsatisfied condition would block every future
  release.
- **Mix evidence classes inside `published-tags.json`** — rejected because it would change the
  established meaning of that file and invite consumers to treat observations as receipts.
- **Start a new release lineage** — rejected because it strands existing pinned consumers, splits
  documentation and support across eras, and leaves the historical identities unresolved.
- **Reissue or retarget historical tags** — prohibited because published tags are immutable and a
  correction must use a new version.

## Consequences

The release lane can resume after the ADR, separate ledger, guard, documentation, and tests pass the
governed PR and exact-head CI path. Original-publication claims remain uncontaminated. All 44 legacy
refs gain durable forward drift detection, and future tags remain receipt-gated.

The guard and manifest tooling must now validate two schemas and render evidence-class-aware
diagnostics. Reviewers must treat changes to the closed legacy set as an architectural change, not a
routine receipt reconciliation. Public documentation must state the epoch and residual risk without
implying historical proof.

## Risks

The baseline can preserve an undetected pre-epoch retarget. A parser or diagnostic that collapses the
two provenance classes can recreate the false provenance claim this decision forbids. A future change
could try to admit a new tag into the closed legacy set to avoid receipt requirements; schema checks,
tests, governed-path notices, and review must reject that drift.

This decision is proven wrong if a legacy record is presented as original-publication evidence, a
post-epoch tag passes strict preflight without a publication receipt, the closed 44-tag set changes
without a new accepted ADR, or a recorded object can move without the guard failing.
