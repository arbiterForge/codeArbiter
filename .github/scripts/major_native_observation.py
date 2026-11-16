"""Closed native runtime composition from original same-source CI artifacts.

This owner never runs native code. It authenticates completed original builder
uploads, their unchanged native stamps and exact named outcomes. A producer-time
record is not a successful whole-run consumer verdict.
"""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import tempfile
import zipfile

SCHEMA = "codearbiter-major-readiness/4"
ADMISSION = "codearbiter-native-composite-admission/1"
UPLOAD = "Share the real tested candidate with this workflow run"
# These full recipes preserve the original per-platform clause/observation
# boundaries. New cells need a separate complete semantic mapping; unrelated
# native120 groups and the mixed Python/npm/native eight remain unrouted.
RECIPES = {'disposition:findings:N-F05': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestFreshStoreObservationsReportNoLocalStore',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadOnlyInitializedStoreObservations',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestObservationLockPreservesExclusion'],
                                'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentObservationsShareRepositoryLock',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveExclusiveOperations',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestFreshStoreObservationsReportNoLocalStore',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadOnlyInitializedStoreObservations',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextBoundsWholePacketWithoutPartialDisclosure',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextScopesPrerequisitesAndReportsUnknownLegacyScope',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestObservationLockPreservesExclusion']},
 'disposition:transitions:N08:03': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                    'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                    'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestDraftSourceRefreshPreservesHistoricalEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSChangedSpecRevokesGrant',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestDraftSourceRefreshPreservesHistoricalEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSChangedSpecRevokesGrant',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                    'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade'],
                                    'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveStaleBindingIsVisibleWithoutBlockingProgress',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextSourceChangesRemainVisibleWithoutReviewCascade']},
 'disposition:transitions:N10:02': {'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites']},
 'disposition:transitions:N13:04': {'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage']},
 'disposition:transitions:N18:01': {'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestApprovalDescriptorsCoverActualEffects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairAtomicApprovalAndReplay',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCannotRecycleInitialDelegation'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestApprovalDescriptorsCoverActualEffects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairAtomicApprovalAndReplay',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCannotRecycleInitialDelegation']},
 'disposition:transitions:N18:02': {'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairAtomicApprovalAndReplay',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCannotUseGenericCapture',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCrashRecoveryBlocksPartialAuthority',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairReceiptCannotApproveSingleArtifact',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairStaleMemberCannotPartiallyApprove',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairWrongSourceLeavesBothDraft'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairAtomicApprovalAndReplay',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCannotUseGenericCapture',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairCrashRecoveryBlocksPartialAuthority',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairReceiptCannotApproveSingleArtifact',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairStaleMemberCannotPartiallyApprove',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSprintPairWrongSourceLeavesBothDraft']},
 'disposition:transitions:N19:01': {'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSCannotInventInitialApproval',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSCannotReapproveAnAmendedProtectedPlan',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSChangedSpecRevokesGrant',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSDoesNotClearBlockedMembersOrTheirReason',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSExplicitGrantPreservesScopeAndOriginalProofObligations',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSIndependentStopRequiresCurrentApprovalEpoch',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSInvalidatesAcceptedScopesAndRetainsHistoricalEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRecordsProfile030',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRefusesDecisionCriticalUnknownSelection',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRejectsMalformedOrScopeExpandingChoices',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSUnchangedMethodIsNotAnotherAttempt',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSWithoutExplicitDelegationRefused'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSCannotInventInitialApproval',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSCannotReapproveAnAmendedProtectedPlan',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSChangedSpecRevokesGrant',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSDoesNotClearBlockedMembersOrTheirReason',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSExplicitGrantPreservesScopeAndOriginalProofObligations',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSIndependentStopRequiresCurrentApprovalEpoch',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSInvalidatesAcceptedScopesAndRetainsHistoricalEvidence',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRecordsProfile030',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRefusesDecisionCriticalUnknownSelection',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSRejectsMalformedOrScopeExpandingChoices',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSUnchangedMethodIsNotAnotherAttempt',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestSMARTSWithoutExplicitDelegationRefused']},
 'disposition:transitions:N24:02': {'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestKnowledgeMergeKeepsBothSidesAndRenamesCollidingIDs',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestKnowledgeMergeRewritesIncomingEditReferences',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestKnowledgeMergeRefusesTheSameRecordChangedTwice']}}


# Current progress contracts. Required slash children prevent a parent pass
# from hiding an omitted state/refusal branch. N11:03 uses accepted ADR-0046 /
# D-PROGRESS=B: retained progress, nonempty dependent history and independent
# stops with derived readiness. Its old destructive STALE effect is superseded
# and is never asserted here. The dedicated history control uses real native
# receipt owners with explicitly synthetic inputs, not live user approval.
_PROGRESS_ASSERTIONS = {'disposition:transitions:N09:01': ['TestAssistiveDraftWorkNeedsNoApprovalOrContextTicket',
                                    'TestAssistiveWorkDoesNotSnapshotUnrelatedSource',
                                    'TestN09StartLiveStateCASAndReplayBoundaries',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/ACCEPTED',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/BLOCKED',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/DONE',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/IN_PROGRESS',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/REVIEW',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/STALE',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/absent-and-retired',
                                    'TestN09StartLiveStateCASAndReplayBoundaries/live-pending-cas-replay'],
 'disposition:transitions:N09:02': ['TestAssistiveReportedReviewCannotMasqueradeAsReceiptedReview',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/ACCEPTED',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/BLOCKED',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/DONE',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/PENDING',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/STALE',
                                    'TestN09OrdinaryReviewRepeatHistoryAndSourceStateRefusals/in-progress-and-review-repeat',
                                    'TestNT01BaselineOrdinaryWorkKeepsReportedFailuresExplicit'],
 'disposition:transitions:N09:03': ['TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent',
                                    'TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent/BLOCKED',
                                    'TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent/PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/ACCEPTED-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/ACCEPTED-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/ACCEPTED-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/BLOCKED-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/BLOCKED-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/BLOCKED-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/DONE-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/DONE-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/DONE-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/IN_PROGRESS-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/IN_PROGRESS-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/IN_PROGRESS-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/PENDING-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/PENDING-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/PENDING-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/REVIEW-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/REVIEW-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/REVIEW-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/STALE-to-BLOCKED',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/STALE-to-PENDING',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/STALE-to-REVIEW',
                                    'TestN09OrdinaryReconcileAllLabelsTargetsAndHistory/closed-target-and-reason'],
 'disposition:transitions:N09:05': ['TestAssistiveScopeCanFinishWithoutReviewPermissionOrTestClaim',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation/BLOCKED',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation/PENDING',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation/STALE',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation/done-with-new-operation-id',
                                    'TestN09OrdinaryScopeGuardsAndRepeatedDoneOperation/missing-empty-retired-reason',
                                    'TestNT01TaskLabelBasesAreDistinct',
                                    'TestNT01TaskLabelBasesAreDistinct/ordinary',
                                    'TestNT01TaskLabelBasesAreDistinct/receipted'],
 'disposition:transitions:N11:03': ['TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent',
                                    'TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent/BLOCKED',
                                    'TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent/PENDING',
                                    'TestDependencyInvalidationPreservesIndependentStops',
                                    'TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops',
                                    'TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops/ancestor-block',
                                    'TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops/receipted-blocked',
                                    'TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops/receipted-pending',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/ACCEPTED',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/BLOCKED',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/DONE',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/IN_PROGRESS',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/PENDING',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/REVIEW',
                                    'TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel/STALE',
                                    'TestNT09LegacyStaleIsUnresolvedAndRetainsRawReason',
                                    'TestNT09PreservedProgressKeepsDependencyReadinessIndependent',
                                    'TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence',
                                    'TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/BLOCKED',
                                    'TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/PENDING',
                                    'TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/REVIEW',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/capture-input-binding',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/capture-task-binding',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/definition',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/input',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/review-stale-evidence',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/review-without-evidence',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/subject',
                                    'TestNT09ReceiptedReconcileRejectsWrongBindingsWithoutWrites/target',
                                    'TestNT09TaskBlockPreservesDependentRecordedProgress']}
_PROGRESS_PLATFORMS = ('darwin/amd64', 'darwin/arm64', 'linux/amd64', 'linux/arm64',
                       'windows/amd64', 'windows/arm64')
RECIPES.update({cell: {platform: [
    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:' + name
    for name in required] for platform in _PROGRESS_PLATFORMS}
    for cell, required in _PROGRESS_ASSERTIONS.items()})

# Complete source/assertion contracts for two existing native findings.
RECIPES.update({'disposition:findings:N-F02': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed'],
                                'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed'],
                                'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed'],
                                'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed'],
                                'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed'],
                                'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorTraitsAreClosedAndHonest',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationRegistryReverseClosure',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRepairIsDiscoverableAppliedAndReplayed',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed']},
 'disposition:findings:N-F07': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects'],
                                'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects'],
                                'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects'],
                                'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects'],
                                'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects'],
                                'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckExactAndBatchReadDoNotClaimCurrentWorktree',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskContextAvoidsWholeSourceSnapshots',
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects']}})


# Admission, advisory reporting and retained journal boundary controls.
RECIPES.update({'disposition:transitions:N01:01': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract'],
                                    'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract'],
                                    'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract'],
                                    'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract'],
                                    'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/capabilities',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/schema',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-operation',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/unknown-field',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects/wrong-protocol',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAllOperationSchemasClosed',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCapabilitiesAdvertiseVersionedOperationContract']},
 'disposition:transitions:N13:01': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295'],
                                    'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295'],
                                    'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295'],
                                    'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295'],
                                    'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/pass',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/fail',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/skip',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13CallerReportBindsOperationTimeAndSubjects/unknown',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckNativeExitBoundsAndOutcomeSemantics',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-2147483648',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/-15',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/256',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/3221225477',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckPreservesNativeFailureExitCodes/4294967295']},
 'disposition:transitions:N13:02': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits'],
                                    'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits'],
                                    'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits'],
                                    'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits'],
                                    'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCASReplaySourceChangesAndPresentationEdits']},
 'disposition:transitions:N13:03': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability'],
                                    'darwin/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                     'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability'],
                                    'linux/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability'],
                                    'linux/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability'],
                                    'windows/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability'],
                                    'windows/arm64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/missing',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/oversized',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13UnavailableScopesRemainReportableWithoutReadMutation/unsafe',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConfigAdditionsAndDirectoryMembershipInvalidateScopedResult',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckCriterionScopeDoesNotInvalidateUnrelatedSpecEdits',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckConstraintScopeFollowsRelevantBodiesAfterRebinding',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckLegacyCriterionDigestDoesNotGainConstraintCoverage',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed',
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability']}})


def selected_recipes(cells):
    import major_readiness as owner
    owner.require(isinstance(cells, list) and len(cells) <= len(RECIPES)
                  and all(isinstance(cell, str) and cell in RECIPES for cell in cells)
                  and cells == sorted(set(cells)), 'invalid native composition selection')
    return {cell: copy.deepcopy(RECIPES[cell]) for cell in cells}


def runtime_requirements(req):
    import major_readiness as owner
    recipes = req.get('native_compositions')
    owner.require(isinstance(recipes, dict) and recipes
                  and recipes == selected_recipes(sorted(recipes)), 'native composition recipe differs')
    cells, jobs = req.get('cells'), req.get('cell_jobs')
    owner.require(isinstance(cells, list) and all(isinstance(cell, str) for cell in cells)
                  and len(cells) == len(set(cells)) and isinstance(jobs, dict)
                  and set(jobs) == set(cells) and set(recipes) < set(cells)
                  and not set(recipes).intersection(req.get('source_dispositions', {})),
                  'native/runtime cell partition differs')
    modules = req.get('native_module_sha256')
    owner.require(isinstance(modules, dict) and set(modules) == {'posix', 'windows'}
                  and all(isinstance(v, str) and owner.DIGEST.fullmatch(v) for v in modules.values()),
                  'native composition lacks immutable module identity')
    return {**{key: value for key, value in req.items()
               if key not in ('native_compositions', 'native_module_sha256')},
            'cells': [cell for cell in cells if cell not in recipes],
            'cell_jobs': {cell: job for cell, job in jobs.items() if cell not in recipes}}


def _document(zipped, path, limit):
    import major_readiness as owner
    import major_qualification_report as reports
    info = zipped.getinfo(path)
    owner.require(info.file_size <= limit, 'native input document exceeds bound')
    return json.loads(zipped.read(info), object_pairs_hook=reports.unique)


def _component(req, run, artifacts, jobs, platform):
    import major_readiness as owner
    import major_qualification_report as reports
    import ci20_native_binding as binding_owner
    runners = {value: key for key, value in binding_owner.RUNNERS.items()}
    name = 'ci20-native-tested-' + runners[platform]
    matching = [item for item in artifacts if item.get('name') == name]
    selected = [job for job in jobs if job.get('name') ==
                '[CHECK] | [CORE] | Tested native candidate build <' + platform + '>']
    owner.require(len(matching) == len(selected) == 1, 'native component original archive/job missing or repeated')
    artifact, job = matching[0], selected[0]
    owner.require(type(job.get('id')) is int and job['id'] > 0
                  and job.get('run_id') == req['ci_run_id'] and job.get('run_attempt') == run['run_attempt']
                  and job.get('status') == 'completed' and job.get('conclusion') == 'success',
                  'native component original job is not successful for this attempt')
    owner.validate_upload(job, artifact, UPLOAD)
    archive = owner.artifact_bytes(artifact, req)
    members = owner.members(archive)
    binary = 'ca-artifact-' + platform.replace('/', '-') + ('.exe' if platform.startswith('windows/') else '')
    expected = {'artifact-candidate/release.json', 'artifact-candidate/' + binary,
                'ci20-native-tested.json', 'native-tests.json', 'native-observation.json'}
    owner.require({item['path'] for item in members} == expected, 'native component archive members differ')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        binding = _document(zipped, 'ci20-native-tested.json', 65536)
        raw = _document(zipped, 'native-tests.json', 8 * 1024 * 1024)
        retained = _document(zipped, 'native-observation.json', 8 * 1024 * 1024)
        owner.require(isinstance(binding, dict) and binding.get('source_commit') == req['source_commit']
                      and binding.get('run_id') == str(req['ci_run_id'])
                      and binding.get('run_attempt') == str(run['run_attempt']) and binding.get('platform') == platform
                      and binding.get('module_sha256') == req['native_module_sha256'][
                          'windows' if platform.startswith('windows/') else 'posix'],
                      'native component source/run/platform/module differs')
        owner.require(isinstance(raw, dict) and 'subtests' in raw,
                      'native composite requires original child terminal observations')
        observed = reports.admit_go(raw, binding, req['source_tree'])
        owner.require(len(observed['tests']) == len(raw['observed']) + len(raw['subtests']),
                      'native admission omitted original terminal outcomes')
        owner.require(retained == observed, 'native component retained observation differs from original raw outcomes')
        # Reuse the maintained candidate manifest/native_tested/binary owner.
        # Only two exact bounded archive members enter a fresh private directory;
        # no archive path extraction, process launch or native execution occurs.
        with tempfile.TemporaryDirectory(prefix='major-native-admit-') as directory:
            root = Path(directory).resolve(strict=True)
            for filename in ('release.json', binary):
                data = zipped.read('artifact-candidate/' + filename)
                with (root / filename).open('xb') as stream:
                    stream.write(data)
            identity = binding_owner.candidate_identity(root, platform)
        owner.require(all(binding[key] == value for key, value in identity.items()),
                      'native component stamp differs from original candidate bytes')
    return {'platform': platform, 'job_id': job['id'], 'artifact_id': artifact['id'],
            'archive_sha256': owner.digest(archive), 'members': members,
            'native_binding': binding, 'argv': observed['argv'], 'tests': observed['tests']}


def authenticate_component(req, run, artifacts, jobs, platform):
    """Original archive authority for a same-run source consumer's producer phase.

    This is not a final-readiness verdict. The independent final owner must still
    require whole trusted main success. Module pins must come from the immutable
    Git owner, never from a caller's source-consumer report.
    """
    import major_readiness as owner
    import ci20_native_binding as binding_owner
    owner.validate_run(run, req, producing=True, allow_program_branch=True)
    owner.require(platform in binding_owner.PLATFORMS and type(run.get('run_attempt')) is int
                  and run['run_attempt'] > 0, 'invalid native component platform or attempt')
    modules = req.get('native_module_sha256')
    owner.require(isinstance(modules, dict) and set(modules) == {'posix', 'windows'}
                  and all(isinstance(value, str) and owner.DIGEST.fullmatch(value) for value in modules.values()),
                  'native component requires immutable module pins')
    return _component(req, run, artifacts, jobs, platform)


def admit(req, artifacts, jobs, *, run=None, producing=False):
    import major_readiness as owner
    runtime_requirements(req)
    run = owner.api('actions/runs/' + str(req['ci_run_id'])) if run is None else run
    owner.validate_run(run, req, producing=producing)
    owner.require(type(run.get('run_attempt')) is int and run['run_attempt'] > 0,
                  'native composition original run attempt missing')
    platforms = sorted({platform for recipe in req['native_compositions'].values() for platform in recipe})
    components = {platform: _component(req, run, artifacts, jobs, platform) for platform in platforms}
    owner.require(len({c['job_id'] for c in components.values()}) == len(platforms)
                  and len({c['artifact_id'] for c in components.values()}) == len(platforms),
                  'native component jobs or archives alias multiple platforms')
    results, used = [], {platform: set() for platform in platforms}
    for cell, recipe in sorted(req['native_compositions'].items()):
        requirements = []
        for platform, selectors in sorted(recipe.items()):
            component = components[platform]
            index = {}
            for test in component['tests']:
                index.setdefault(test['id'], []).append(test['result'])
            for selector in selectors:
                owner.require(index.get(selector) == ['passed'],
                              'native composite selected assertion missing/skipped/repeated/failed')
                # A parent pass never hides a skip/failure below that required
                # parent. The original collector records all terminal children.
                descendants = {name: outcomes for name, outcomes in index.items() if name.startswith(selector + '/')}
                owner.require(all(outcomes == ['passed'] for outcomes in descendants.values()),
                              'native composite required child skipped/repeated/failed')
                used[platform].add(selector)
                used[platform].update(descendants)
            requirements.append({'platform': platform, 'job_id': component['job_id'],
                                 'artifact_id': component['artifact_id'], 'selectors': selectors})
        results.append({'cell': cell, 'result': 'PASSED', 'components': requirements})
    retained = []
    for platform, component in sorted(components.items()):
        retained.append({**component, 'tests': sorted(
            [test for test in component['tests'] if test['id'] in used[platform]], key=lambda t: t['id'])})
    return {'schema': ADMISSION, 'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
            'ci_run_id': req['ci_run_id'], 'run_attempt': run['run_attempt'],
            'results': results, 'components': retained}


def produce(req, artifacts, jobs):
    import major_readiness as owner
    runtime = runtime_requirements(req)
    native = admit(req, artifacts, jobs, producing=True)
    return {'schema': SCHEMA, 'program_id': owner.PROGRAM, 'state': 'PREPUBLICATION_READY',
            **req, 'native': native, 'runtime': owner.produce(runtime, artifacts, jobs)}


def verify(*, record, requirements, run, artifact, archive_digest, jobs, build_artifacts, payload_members=None):
    import major_readiness as owner
    req = requirements
    owner.validate_run(run, req)  # Whole trusted main success before any admission.
    runtime = runtime_requirements(req)
    owner.require(isinstance(record, dict) and set(record) == {'schema', 'program_id', 'state', 'native', 'runtime', *req}
                  and record.get('schema') == SCHEMA and record.get('program_id') == owner.PROGRAM
                  and record.get('state') == 'PREPUBLICATION_READY'
                  and all(record.get(key) == value for key, value in req.items()),
                  'native composite readiness differs from original requirements')
    expected = admit(req, build_artifacts, jobs, run=run)
    owner.require(record.get('native') == expected, 'native composite differs from authenticated original components')
    inner = record.get('runtime')
    owner.require(isinstance(inner, dict) and inner.get('schema') in
                  (owner.SCHEMA, 'codearbiter-major-readiness/2'),
                  'native composition runtime schema is invalid')
    return owner.verify(record=inner, requirements=runtime, run=run, artifact=artifact,
                        archive_digest=archive_digest, jobs=jobs, build_artifacts=build_artifacts,
                        payload_members=payload_members)
