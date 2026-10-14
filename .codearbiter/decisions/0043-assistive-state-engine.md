---
status: accepted
date: 2026-10-14
title: Make the state engine assistive rather than a second permission system
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0037-extensible-structured-artifact-engine (artifact-origin permission policy only)
governs: core/artifacts/**, core/pysrc/_artifact*.py, core/pysrc/_approvallib.py, core/pysrc/_prerequisitelib.py, core/pysrc/_reconciliationlib.py, core/surface/includes/artifacts.md, core/surface/skills/**
---

# ADR-0043 - Make the state engine assistive rather than a second permission system

## Status

Accepted - product direction approved by the product owner on October 14, 2026. The owner requested the streamlined overhaul as one implementation PR and then explicitly requested that the handoff be committed and implementation started. This records that decision, not a claim of complete implementation, independent review, installed-host qualification, or release.

## Context

The desired engine keeps the agent aligned with its plan, maintains honest progress and evidence, supports orchestration, produces human-readable HTML, and supplies compact symbol-bound context. Its artifact approval codes, per-prerequisite certification, context-ticket admission, reconciliation codes, and verification-receipt-dependent reviewer restarts instead became a second always-ask workflow.

The owning implementation baseline is `arbiterForge/codeArbiter@045c0812888f20f4c843677cfb37b802e2084770:core/artifacts/internal/operations/lifecycle.go`, with the caller contract in `core/surface/includes/artifacts.md`. This is current-source evidence for the decision, not proof of the owner's installed package.

ADR-0037's shared, file-backed engine and integrity/recovery kernel remain the architecture. This decision supersedes only the interpretation that artifact-owned approval, review, and freshness machinery must independently authorize ordinary work. It does not weaken actual host permissions or independently applicable repository and publication controls. ADR-0042's ship-set snapshot definition remains a valid observation mechanism; taking or refreshing that snapshot is not itself a prerequisite to recording ordinary progress.

## Decision

The engine records intent, progress, changes, and supporting evidence; it does not independently authorize already-authorized work.

Normal task selection, progress updates, in-scope plan maintenance, and resume do not require artifact approval receipts, prerequisite reply codes, or context-delivery tickets.

Observable prerequisites are checked and recorded through ordinary authorized tools. Only affected work waits for a real dependency or consequential unresolved decision; unrelated work may continue.

Work progress and evidence assessment are separate. Implementation may be reported complete while verification is pending, failed, or unknown. No progress label may fabricate a test result, reviewer event, approval, or release claim.

New verification receipts, presentation edits, and routine bookkeeping do not automatically invalidate code review or dispatch reviewers. Reassessment follows changes to the relevant subject, requirements, findings, or verification inputs, with uncertainty disclosed.

Preserve typed state, stable symbols and references, bounded retrieval, safe HTML rendering, compare-and-swap writes, transaction recovery, and historical evidence. Preserve actual host permissions, explicit user stops and denials, sandbox protections, and independently applicable repository and publication controls.

Replace the default artifact permission workflow rather than adding a relaxed mode, synthetic auto-approval, blanket hook bypass, new permission broker, daemon, database, or general rule language.

Implement the compatible engine, callers, migration, generated adapters, documentation, and release preparation in one PR. Partial development slices stay draft; source tests, installed-candidate verification, publication, and distributed-artifact readback remain distinct states.

## Alternatives considered

- Shorter approval codes or automated answers: rejected because the extra permission dependency remains.
- Faster validation with identical refusal semantics: rejected as the primary correction; it preserves the wrong boundary.
- Disable all checks or treat every outcome as success: rejected because it destroys data integrity, real permissions, and honest reporting.
- Optional relaxed mode alongside the old default: rejected because it preserves two workflows and leaves the owner maintaining the unwanted behavior.
- Replace checked-in artifacts with a service or database: unnecessary for this correction and outside this PR.

## Consequences

The agent maintains a working agreement instead of a frozen implementation script. It may revise its method within the agreed outcome while preserving references and reasons. Material outcome changes and actual authorization boundaries remain consequential decisions, not opaque artifact codes.

Historical evidence stays available without being relabeled as current. Existing readers and unfinished work require explicit compatibility handling. Old instructions can recreate the problem even after native changes, so caller and generated-surface conversion are part of the same PR, not an optional follow-up.

The implementation handoff is `docs/plans/assistive-state-engine-overhaul.md`; actual slice completion and verification belong in `docs/plans/assistive-state-engine-progress.md`. No broad product maturity or release claim follows from acceptance of this ADR.

## Risks and verification

A scheduler could accidentally promote recorded progress to verified completion; explicit evidence consumers must not derive proof from advisory task selection. A partial conversion could leave old callers demanding removed fields; the draft must not ship before compatible callers and upgrade handling are complete. Removing duplicate ceremony must not silently clear a user stop, duplicate active work, overwrite concurrent edits, discard history, or bypass host permissions.

Use focused successful-work, negative-result, concurrency, interruption, and migration scenarios from the handoff. Preserve legitimate integrity checks; rewrite tests that exist solely to enforce the removed artifact ceremony. Verification is proportionate to the changed behavior rather than a new mandatory reviewer cascade.
