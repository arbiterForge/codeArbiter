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


# Exact main.run CLI contract: all required terminal children on all platforms.
RECIPES.update({'disposition:transitions:N37:01': {platform: [
    'go:github.com/arbiterForge/codeArbiter/core/artifacts/cmd/ca-artifact:' + name for name in ('TestN37CLIValidDecodeOnceAndCommittedOutputFailure',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/valid-create-and-exact-replay',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-malformed-json',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-duplicate-key',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-trailing-json',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-non-object',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-oversized-json',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-unknown-key',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-wrong-protocol',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/refuse-unknown-operation',
 'TestN37CLIValidDecodeOnceAndCommittedOutputFailure/committed-before-output-failure',
 'TestCLIEmitsJSONFaultAndMatchingExitClass')
] for platform in ('darwin/amd64','darwin/arm64','linux/amd64','linux/arm64','windows/amd64','windows/arm64')}})


# Full journal clauses: all required original parent/slash outcomes on all six
# native platforms. Later journal/schema recipes retain their own complete
# complements; incomplete replay/recovery effects remain unrouted.
_JOURNAL_ASSERTIONS = {'disposition:transitions:N02:01': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02AcknowledgementWriteFailureRetainsRecoverableOutcome',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/ancestor-case-folded',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/ancestor-overlap',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/ancestor-reversed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/before-mismatch',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/case-alias',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/duplicate',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/exact-512',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/invalid-id',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/nil-before-after',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/oversized-after',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/prepublication-cleanup',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/too-many',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/unsafe-path',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/valid-prefix-lookalike',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02CommitAdmissionAndPrepublicationCleanup/zero-edits',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPartialJournalStageRequiresManualReconciliation',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/EACCES',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/EIO',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/ENOSPC',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/EPERM',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/EROFS',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPreJournalIOFailureHasBoundedPublicDiagnostic/permission_sentinel',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestTransactionalCAS'],
 'disposition:transitions:N02:02': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/after-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/before-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/during-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback'],
 'disposition:transitions:N02:03': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestMigrationPairAndRollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestWorkAdoptJournalsBoardCutoverAndReplays',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/after-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/before-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/during-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02PreparedTargetCASRefusesConcurrentBytes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestTransactionalCAS'],
 'disposition:transitions:N02:04': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN13TrimRetainsActualJournalBeforeImage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReviewRetryPreservesMutationResult',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02AcknowledgementWriteFailureRetainsRecoverableOutcome',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback'],
 'disposition:transitions:N03:03': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/rollback']}
RECIPES.update({cell: {platform: list(required) for platform in _PROGRESS_PLATFORMS}
    for cell, required in _JOURNAL_ASSERTIONS.items()})


# N03:04 preserves baseline distinct conflict/corruption diagnostics under the
# accepted kernel/wire contract; frozen inventory wording is not rewritten.
# N03:05 requires actual unreadable parent/children PASS, including Unix.
# Current0.3.4 retirement/progress is included alongside historical0.3.2/.3.
_KERNEL_SCHEMA_ASSERTIONS = {'disposition:transitions:N03:04': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-backup',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-stage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/third-digest',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestRecoveryConflictPreservesExternalEdit'],
 'disposition:transitions:N03:05': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestInvalidJournalFilenameNamesEntry',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/after_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/before_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.1.0/request_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/after_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/before_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/long',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/newline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/nonhex',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/short',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/uppercase',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalDigestGrammar/codearbiter.transaction/0.2.0/request_sha256/wrong_type',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalRemovedBetweenListAndReadBlocksWithPath',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-case-folded',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-case-folded/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-case-folded/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-case-folded/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-first',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-first/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-first/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-first/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-reversed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-reversed/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-reversed/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03LegacyAncestorOverlapJournalRefusesEveryAdmission/ancestor-reversed/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnreadableFinalJournalNeverBecomesClean',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnreadableFinalJournalNeverBecomesClean/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnreadableFinalJournalNeverBecomesClean/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnreadableFinalJournalNeverBecomesClean/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/backup-parent-traversal',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/backup-parent-traversal/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/backup-parent-traversal/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/backup-parent-traversal/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/stage-parent-traversal',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/stage-parent-traversal/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/stage-parent-traversal/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/stage-parent-traversal/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/target-parent-backslash',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/target-parent-backslash/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/target-parent-backslash/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03UnsafeEmbeddedJournalPathsRefuseEveryAdmission/target-parent-backslash/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestObstructedTransactionNamesOffendingEntry',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestObstructedTransactionNamesOffendingEntry/foreign-directory',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestObstructedTransactionNamesOffendingEntry/foreign-file',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestOversizedFinalJournalReportsCorruptionAndBlocksWrites',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestOversizedFinalJournalReportsCorruptionAndBlocksWrites/new-write',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestOversizedFinalJournalReportsCorruptionAndBlocksWrites/pending',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestOversizedFinalJournalReportsCorruptionAndBlocksWrites/recover',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPendingRejectsCorruptCompletedDigest',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPendingRejectsCorruptCompletedDigest/after_sha256',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPendingRejectsCorruptCompletedDigest/before_sha256',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestPendingRejectsCorruptCompletedDigest/request_sha256',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestUnparseableFinalJournalNamesPathAndBlocksRecovery'],
 'disposition:transitions:N04:02': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveLegacyReadPreservesBytesAndNewFieldsRequireNewSchema',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestLegacyReceiptIsInspectableButCannotConferAuthority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOldSchemaCannotSilentlyContainNewObservations',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestUnknownVersionFailsClosed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestUntypedTombstoneDoesNotOwnHistory',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestObjectPathTablesKeepHistoricalGrammar',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestObjectPathTablesKeepHistoricalGrammar/0.3.0',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestObjectPathTablesKeepHistoricalGrammar/0.3.1',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestReviewReadPriorSchemaPreservesBytes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestReviewReadPriorSchemaPreservesBytes/plan',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/render:TestReviewReadPriorSchemaPreservesBytes/spec'],
 'disposition:transitions:N04:03': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveDraftBindingPreservesProgressAndEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveLegacyReadPreservesBytesAndNewFieldsRequireNewSchema',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/BLOCKED',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/PENDING',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09ReceiptedReconcilePreservesProgressAndSelectedEvidence/REVIEW',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRetiringCheckedTaskKeepsTypedHistory',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckOldSchemaCannotSilentlyContainNewObservations',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTrackerCoordinationT02OneTransitionStagesBoundIssue',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestUnknownVersionFailsClosed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestUntypedTombstoneDoesNotOwnHistory',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestWorkRetryPreservesLaterEdit']}
RECIPES.update({cell: {platform: list(required) for platform in _PROGRESS_PLATFORMS}
    for cell, required in _KERNEL_SCHEMA_ASSERTIONS.items()})


# Complete caller-replay/recovery effects retain their original complements.
_KERNEL_REMAINDER_ASSERTIONS = {'disposition:transitions:N02:05': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestConcurrentReadersPreserveWriterRetry',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN02ResultlessReplayRequiresRefreshWithoutInventingIdentity',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN02ResultlessReplayRequiresRefreshWithoutInventingIdentity/codearbiter.transaction/0.1.0',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN02ResultlessReplayRequiresRefreshWithoutInventingIdentity/codearbiter.transaction/0.2.0',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReviewRetryPreservesMutationResult',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestWorkRetryPreservesLaterEdit',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN02AcknowledgementWriteFailureRetainsRecoverableOutcome'],
 'disposition:transitions:N03:01': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestWorkAdoptRecoveryPreservesLaterBoardEdit',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/after-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/before-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/during-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryOwnAcknowledgementFailureAndSameModeRetry',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryOwnAcknowledgementFailureAndSameModeRetry/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-backup',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-stage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/third-digest',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained/complete-changed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained/complete-verified',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestRecoveryConflictPreservesExternalEdit',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback'],
 'disposition:transitions:N03:02': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT01JournalOutcomeCodesStayDistinct/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestWorkAdoptRecoveryPreservesLaterBoardEdit',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/after-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/before-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestJournalPublicationCrash/during-journal-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryOwnAcknowledgementFailureAndSameModeRetry',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryOwnAcknowledgementFailureAndSameModeRetry/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-backup',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/missing-stage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03RecoveryPreflightPreservesAllTargetsAndEvidence/third-digest',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03TerminalRecoveryReplayPreservesBytes/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained/rollback-changed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestN03VerifiedUnusedStagesCleanedAndChangedStagesRetained/rollback-verified',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestProcessDeathRecovery/after-stage-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestRecoveryConflictPreservesExternalEdit',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-complete/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-journal/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-0/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-replace-1/rollback',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/complete',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReplaceRecovery/after-stage-0/rollback']}
RECIPES.update({cell: {platform: sorted(set(required) |
    ({'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/store:TestReviewLegacyJournalRemainsReadable'} if cell == 'disposition:transitions:N02:05' and platform.startswith('linux/') else set()))
    for platform in _PROGRESS_PLATFORMS} for cell, required in _KERNEL_REMAINDER_ASSERTIONS.items()})


# Full readiness and receipt rows: exact original named complements remain required.
_READINESS_RECEIPT_ASSERTIONS = {'disposition:transitions:N07:01': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07DecisionResolutionChangesReadinessWithoutApproving',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07DecisionResolutionChangesReadinessWithoutApproving/blank-resolution',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07DecisionResolutionChangesReadinessWithoutApproving/dangling-reference',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07DecisionResolutionChangesReadinessWithoutApproving/resolved',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestRoleBoundReferences',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecReadiness'],
 'disposition:transitions:N07:03': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/invalid-partition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/missing-statement',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/ready-positive',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/uncovered-criterion',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/uncovered-input',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing/uncovered-scope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestDraftIncompleteRecords',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestPlanGraphAndCoverage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestReadyRefusesGitDirectoryTaskPaths',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestReadyRefusesRuntimeMarkerInputs',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestReadyRejectsRepositoryRelativeExcludesOutsideRoots',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestReviewNamedTestRequirementAtReadiness',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestRoleBoundReferences',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecBinding',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecReadiness'],
 'disposition:transitions:N07:04': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ActiveNotApplicableAndMandatoryDispositionRefuse',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ActiveNotApplicableAndMandatoryDispositionRefuse/active-not-applicable',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ActiveNotApplicableAndMandatoryDispositionRefuse/mandatory-disposition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN07ActiveNotApplicableAndMandatoryDispositionRefuse/optional-disposition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestRetiringCriterionKeepsNestedCollectionKinds',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecBinding'],
 'disposition:transitions:N10:03': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestLegacyReceiptIsInspectableButCannotConferAuthority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/authority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/changed-source',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/definition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/empty-assessment',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/input',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites/subject',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileUpdatesBaselineAndPreservesEveryMemberHistory',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileUpdatesBaselineAndPreservesEveryMemberHistory/missing',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ScopeReconcileUpdatesBaselineAndPreservesEveryMemberHistory/stale'],
 'disposition:transitions:N12:04': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistivePrerequisiteNewFailureAndUnknownReplaceOldSuccess',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistivePrerequisiteObservationCASReplayAndClosedShapes',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistivePrerequisiteReferencesHistoryAndInertHTML',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestAssistiveScopedFactsKeepIndependentWorkMoving',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/authority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/changed-source',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/definition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/missing-receipt-structural-refusal',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/stale-consumer-receipt',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteRejectsWrongAuthorityAndStaleDefinitions/subject',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN12ReceiptedPrerequisiteReplacesObservationWithoutLosingHistory']}
RECIPES.update({cell: {platform: list(required) for platform in _PROGRESS_PLATFORMS}
    for cell, required in _READINESS_RECEIPT_ASSERTIONS.items()})


# Full creation/review/acceptance clauses; original completion and legacy guards stay mandatory.
_CREATION_REVIEW_ACCEPT_ASSERTIONS = {'disposition:transitions:N04:01': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCreateDoesNotShadowLegacy',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestDuplicateCanonicalAuthoritiesFailClosed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateCatalogBoundsRefuseBeforeWriting',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateCatalogBoundsRefuseBeforeWriting/public-count',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateCatalogBoundsRefuseBeforeWriting/save-byte-bound',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateInitialTypedStateAndDuplicateRefusals',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateInitialTypedStateAndDuplicateRefusals/decomposition',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateInitialTypedStateAndDuplicateRefusals/knowledge',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateInitialTypedStateAndDuplicateRefusals/plan',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN04CreateInitialTypedStateAndDuplicateRefusals/spec',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository:TestContextRepresentationBoundary',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestClosedSchema'],
 'disposition:transitions:N10:01': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV1CaptureAndPublication',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV2CaptureAndPublication',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV2CompletionCapturePublicationAndScope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewCanSupersedeStaleCompletedRun',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewNativeCapturePublicationAndScope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsDefinitionOnlyReceipt',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/mapped-after-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/mapped-before-capture',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/mapped-before-consume',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/material-after-publish',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/material-before-capture',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewRejectsSelectedEvidenceDrift/material-before-consume',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewReplayRetainsExplicitSelectedReceipt',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/definition-only',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/duplicate-obligation',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/duplicate-reference',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/missing-fact',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/missing-obligation',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/unselected-reference',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewSelectionAndDecisionAreExact/whitespace-assessment',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestLegacyReceiptIsInspectableButCannotConferAuthority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestMissingOrSkippedNamedTests',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence/baseline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence/failed-named-test',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence/missing-named-test',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence/ordinary-prerequisite',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRefusesStaleBaselineAndEvidence/source-input',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline/ACCEPTED',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline/DONE',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline/IN_PROGRESS',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline/REVIEW',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10ReceiptedReviewRetainsRefsAndScopeBaseline/STALE',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestPlanGraphAndCoverage',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecBinding',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate:TestSpecReadiness'],
 'disposition:transitions:N10:04': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV1CaptureAndPublication',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV2CaptureAndPublication',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCodexNativeV2CompletionCapturePublicationAndScope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionRerunCannotReuseReviewAfterItsSubjectChanges',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionRerunReusesTaskReviewWithoutRelabellingItsEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewNativeCapturePublicationAndScope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestCompletionReviewQualityPreservesExactTaskEvidence',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestLegacyReceiptIsInspectableButCannotConferAuthority',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope/later-member-blocked',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope/later-member-stale',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope/prior-stale',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRefusesFailedMemberOrPriorScope/prior-unaccepted',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRetainsEveryMemberReceipt',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRetainsEveryMemberReceipt/later-scope',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRetainsEveryMemberReceipt/mixed',
                                    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN10StrictScopeAcceptanceRetainsEveryMemberReceipt/review']}
RECIPES.update({cell: {platform: list(required) for platform in _PROGRESS_PLATFORMS}
    for cell, required in _CREATION_REVIEW_ACCEPT_ASSERTIONS.items()})


# Exact named progress-preservation tests on the Windows native suite.
RECIPES["disposition:findings:N-F03"] = {"windows/amd64": [
    "go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
    for name in (
        "TestAssistiveReconcileKeepsTransitiveDependencyAdviceCurrent",
        "TestAssistiveScopedFactsKeepIndependentWorkMoving",
        "TestCheckConflictsRespectDefinitionAndSourceScope",
        "TestDependencyInvalidationPreservesIndependentStops",
        "TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel",
        "TestNT09OrdinaryReviewAndDoneDoNotClaimIndependentProof",
        "TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
        "TestTaskCheckCASReplaySourceChangesAndPresentationEdits",
        "TestTaskCheckLatestFailureOverridesPriorPassAndSkipsUnknown",
        "TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability",
    )
]}


# Exact Windows context vectors from the retained pure native owner evidence.
# Each vector belongs to the original unfiltered Windows candidate run.
_WINDOWS_CONTEXT_ASSERTIONS = (
    (
        (
            "disposition:findings:N-F01",
            "disposition:transitions:N16:04",
            "disposition:transitions:N21:01",
            "scenario:SEQ-03",
            "task:NT-02",
        ),
        (
            "contextdocument:TestStoredPreviewContractRejectsMalformedRecords",
            "evidence:TestRecognizedOutputsCoverEveryDerivedKind",
            "operations:TestContextPreviewComposesWithStrictConsumers",
            "operations:TestReservedPreviewOutputsFailClosed",
            "operations:TestStaleContextPreviewRemainsRecognizedButCannotApply",
        ),
    ),
    (
        ("disposition:machines:N16",),
        (
            "contextdocument:TestStoredPreviewContractRejectsMalformedRecords",
            "evidence:TestRecognizedOutputsCoverEveryDerivedKind",
            "evidence:TestSnapshotExecutableFromIndexMode",
            "evidence:TestSnapshotGitProbeFailureFailsClosed",
            "evidence:TestSnapshotProgressOnlyUpdateKeepsIdentity",
            "evidence:TestSnapshotRejectsDifferingScans",
            "evidence:TestSnapshotShipSetMembership",
            "evidence:TestSnapshotTrackedSymlinkIsUnsafePath",
            "evidence:TestSnapshotUnreadableDotGitFailsClosed",
            "operations:TestContextPreviewComposesWithStrictConsumers",
            "operations:TestReservedPreviewOutputsFailClosed",
            "operations:TestStaleContextPreviewRemainsRecognizedButCannotApply",
        ),
    ),
    (
        (
            "disposition:machines:N21",
            "disposition:transitions:N21:04",
            "disposition:transitions:N21:05",
        ),
        (
            "contextdocument:TestOrdinaryContextAdoptionRecoveryPreservesHistory",
            "contextdocument:TestStoredPreviewContractRejectsMalformedRecords",
            "evidence:TestRecognizedOutputsCoverEveryDerivedKind",
            "operations:TestContextApplyRequestShapes",
            "operations:TestContextAuthorityExactPreviewFixture",
            "operations:TestContextOrdinaryAdoptsMissingAndLegacyProvenance",
            "operations:TestContextOrdinaryCreateReplayAndIntegrity",
            "operations:TestContextOrdinaryRejectsAmbiguousUnsafeOrForgedRequests",
            "operations:TestContextPreviewComposesWithStrictConsumers",
            "operations:TestContextWholeDocumentCreateAdoptUpdate",
            "operations:TestContextWholeDocumentSelectionPreservesControls",
            "operations:TestReservedPreviewOutputsFailClosed",
            "operations:TestStaleContextPreviewRemainsRecognizedButCannotApply",
        ),
    ),
    (
        (
            "disposition:machines:N22",
            "disposition:transitions:N22:01",
            "disposition:transitions:N22:02",
            "disposition:transitions:N22:03",
        ),
        (
            "contextdocument:TestContextFinalizationNegativeControls",
            "contextdocument:TestContextFinalizationPositiveControls",
            "operations:TestContextOrdinaryFinalization",
            "operations:TestContextWholeDocumentOnboardingFinalization",
        ),
    ),
    (
        (
            "disposition:transitions:N16:01",
            "disposition:transitions:N16:02",
            "disposition:transitions:N16:03",
        ),
        (
            "evidence:TestSnapshotExecutableFromIndexMode",
            "evidence:TestSnapshotGitProbeFailureFailsClosed",
            "evidence:TestSnapshotProgressOnlyUpdateKeepsIdentity",
            "evidence:TestSnapshotRejectsDifferingScans",
            "evidence:TestSnapshotShipSetMembership",
            "evidence:TestSnapshotTrackedSymlinkIsUnsafePath",
            "evidence:TestSnapshotUnreadableDotGitFailsClosed",
        ),
    ),
    (
        (
            "disposition:transitions:N21:02",
            "disposition:transitions:N21:03",
            "disposition:transitions:N21:06",
        ),
        (
            "contextdocument:TestOrdinaryContextAdoptionRecoveryPreservesHistory",
            "operations:TestContextApplyRequestShapes",
            "operations:TestContextAuthorityExactPreviewFixture",
            "operations:TestContextOrdinaryAdoptsMissingAndLegacyProvenance",
            "operations:TestContextOrdinaryCreateReplayAndIntegrity",
            "operations:TestContextOrdinaryRejectsAmbiguousUnsafeOrForgedRequests",
            "operations:TestContextWholeDocumentCreateAdoptUpdate",
            "operations:TestContextWholeDocumentSelectionPreservesControls",
        ),
    ),
    (
        ("disposition:transitions:N38:01",),
        (
            "contextdocument:TestContextDocumentContract",
        ),
    ),
    (
        ("disposition:transitions:N38:04",),
        (
            "contextdocument:TestContentEvidencePathRejectsSensitiveComponents",
            "contextdocument:TestContextMutationAdmission",
        ),
    ),
    (
        ("disposition:transitions:N38:05",),
        (
            "contextdocument:TestContextMutationAdmission",
            "contextdocument:TestMembershipDigestDoesNotTraverseExcludedBoundaries",
            "contextdocument:TestMembershipDigestFileLimitIncludesNonmatchingFiles",
            "contextdocument:TestMembershipDigestNestedRegularEntries",
            "contextdocument:TestMembershipDigestScopeOrderAndOwnershipBoundaries",
            "contextdocument:TestMembershipDigestTracksNamesSeparatelyFromContent",
        ),
    ),
)
# Ordinary work admission, progress, checks and retirement share this Windows owner.
_WINDOWS_WORK_ASSERTIONS = (
    (
        ("disposition:findings:N-F04",),
        (
            "operations:TestAssistiveDraftWorkNeedsNoApprovalOrContextTicket",
            "operations:TestAssistiveReportedReviewCannotMasqueradeAsReceiptedReview",
            "operations:TestAssistiveResumePreservesStopsAndRejectsDuplicateStart",
            "operations:TestAssistiveScopedFactsKeepIndependentWorkMoving",
            "operations:TestAssistiveSelectionUsesDependenciesNotCheckpointOrder",
            "operations:TestNT01BaselineOrdinaryWorkKeepsReportedFailuresExplicit",
            "operations:TestNT01TaskLabelBasesAreDistinct",
            "operations:TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
            "operations:TestTaskContextShowsStopsAndUnfinishedDependencies",
        ),
    ),
    (
        (
            "disposition:findings:N-F10",
            "disposition:transitions:N06:03",
            "scenario:SEQ-06",
        ),
        (
            "operations:TestInterruptedRetirementRecoversExactly",
            "operations:TestRetirementKindMustNameAnActualCollection",
            "operations:TestRetiringCheckedTaskKeepsTypedHistory",
            "operations:TestRetiringCheckpointKeepsScopeBaseline",
            "operations:TestRetiringCriterionKeepsNestedCollectionKinds",
            "operations:TestUntypedTombstoneDoesNotOwnHistory",
        ),
    ),
    (
        ("disposition:machines:N09",),
        (
            "operations:TestAssistiveDraftWorkNeedsNoApprovalOrContextTicket",
            "operations:TestAssistiveReportedReviewCannotMasqueradeAsReceiptedReview",
            "operations:TestAssistiveResumePreservesStopsAndRejectsDuplicateStart",
            "operations:TestDependencyInvalidationPreservesIndependentStops",
            "operations:TestNT01BaselineOrdinaryWorkKeepsReportedFailuresExplicit",
            "operations:TestNT01TaskLabelBasesAreDistinct",
            "operations:TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel",
            "operations:TestNT09TaskBlockPreservesDependentRecordedProgress",
        ),
    ),
    (
        ("disposition:machines:N11",),
        (
            "operations:TestAssistiveScopedFactsKeepIndependentWorkMoving",
            "operations:TestAssistiveSelectionUsesDependenciesNotCheckpointOrder",
            "operations:TestDependencyInvalidationPreservesIndependentStops",
            "operations:TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel",
            "operations:TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
            "operations:TestNT09TaskBlockPreservesDependentRecordedProgress",
            "operations:TestTaskContextShowsStopsAndUnfinishedDependencies",
        ),
    ),
    (
        ("disposition:machines:N13",),
        (
            "operations:TestInterruptedRetirementRecoversExactly",
            "operations:TestRetirementKindMustNameAnActualCollection",
            "operations:TestRetiringCheckedTaskKeepsTypedHistory",
            "operations:TestRetiringCheckpointKeepsScopeBaseline",
            "operations:TestRetiringCriterionKeepsNestedCollectionKinds",
            "operations:TestTaskCheckBoundedRecentViewKeepsHistoryInJournal",
            "operations:TestTaskCheckHistoricalRecordIsNotGivenNewSourceIdentity",
            "operations:TestTaskCheckNeverExecutesItsSourceAndEscapesHTML",
            "operations:TestTaskCheckOutOfBoundsOrUnsafeInputsRemainUnassessed",
            "operations:TestTaskCheckRecordsCommandOutcomeWithoutNewAuthority",
            "operations:TestTaskCheckRejectsInventedPassesAndMismatchedNamedCommands",
            "operations:TestTaskCheckScopedSourceChangesDoNotRestartUnrelatedWork",
            "operations:TestUntypedTombstoneDoesNotOwnHistory",
        ),
    ),
    (
        (
            "disposition:machines:N14",
            "disposition:transitions:N14:02",
            "disposition:transitions:N14:04",
            "disposition:transitions:N14:05",
        ),
        (
            "operations:TestCheckConflictsDoNotPromoteUnboundOrTrimmedHistory",
            "operations:TestCheckConflictsMatchEveryUnindexedCommandWithoutBindingIt",
            "operations:TestCheckConflictsRespectDefinitionAndSourceScope",
            "operations:TestCheckReportBoundaryCannotCoverARepeatedLaterReport",
        ),
    ),
    (
        ("disposition:transitions:N01:03",),
        (
            "operations:TestConcurrentObservationsShareRepositoryLock",
            "operations:TestFreshStoreObservationsReportNoLocalStore",
            "operations:TestPlanVerificationSharedClassification",
            "operations:TestPlanVerificationWriterExclusion",
        ),
    ),
    (
        ("disposition:transitions:N01:04",),
        (
            "operations:TestConcurrentReadersPreserveExclusiveOperations",
            "operations:TestConcurrentReadersPreserveWriterRetry",
            "operations:TestIndexObservationUsesExclusiveEngineLock",
        ),
    ),
    (
        ("disposition:transitions:N01:05",),
        (
            "operations:TestInitStoreCreatesOnlyLockMetadata",
            "operations:TestInitStoreIsIdempotent",
        ),
    ),
    (
        ("disposition:transitions:N06:02",),
        (
            "operations:TestRecordReorderRejectsInvalidCheckpointDependencyOrder",
            "operations:TestRecordReorderRejectsMalformedOrStaleRequestsAtomically",
            "operations:TestTypedRecordReorder",
        ),
    ),
    (
        ("disposition:transitions:N06:04",),
        (
            "operations:TestRetiringCheckedTaskKeepsTypedHistory",
        ),
    ),
    (
        (
            "disposition:transitions:N11:01",
            "disposition:transitions:N11:02",
            "disposition:transitions:N11:04",
        ),
        (
            "operations:TestAssistiveScopedFactsKeepIndependentWorkMoving",
            "operations:TestAssistiveSelectionUsesDependenciesNotCheckpointOrder",
            "operations:TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
            "operations:TestTaskContextShowsStopsAndUnfinishedDependencies",
        ),
    ),
    (
        ("disposition:transitions:N12:01",),
        (
            "operations:TestAssistiveDecisionRemainsAUserChoiceNotAToolResult",
            "operations:TestAssistivePrerequisiteNewFailureAndUnknownReplaceOldSuccess",
            "operations:TestAssistivePrerequisiteObservationCASReplayAndClosedShapes",
            "operations:TestAssistivePrerequisiteReferencesHistoryAndInertHTML",
            "operations:TestAssistiveScopedFactsKeepIndependentWorkMoving",
        ),
    ),
)

# Store, knowledge, tracker and project view assertions from the Windows candidate.
_WINDOWS_STORE_AND_PROJECT_ASSERTIONS = (
    (
        ("disposition:findings:N-F08",),
        (
            "store:TestSupportedBackendDeclarationMatchesBuiltBackend",
            "store:TestUnsupportedPlatformDiagnosticIsTruthful",
        ),
    ),
    (
        (
            "disposition:machines:N23",
            "disposition:transitions:N23:01",
            "disposition:transitions:N23:02",
            "disposition:transitions:N23:03",
        ),
        (
            "operations:TestKnowledgeCutoverPreservesSettingsAndScopeBlocks",
            "operations:TestKnowledgeCutoverRefusesUnmappedSections",
            "operations:TestKnowledgeCutoverRefusesUnrecordedContent",
            "operations:TestKnowledgeCutoverRetryKeepsLaterWorkAndStaleApplyFails",
            "operations:TestKnowledgeInitializeBootstrapsPortableProjectBeforeFirstWork",
            "operations:TestKnowledgeInitializeRejectsOrphanAndKeepsLegacyOwner",
            "operations:TestReadsNeverMigrate",
        ),
    ),
    (
        (
            "disposition:machines:N24",
            "disposition:transitions:N24:01",
            "disposition:transitions:N24:03",
        ),
        (
            "operations:TestKnowledgeMergeKeepsBothSidesAndRenamesCollidingIDs",
            "operations:TestKnowledgeMergeRefusesTheSameRecordChangedTwice",
            "operations:TestKnowledgeMergeRewritesIncomingEditReferences",
        ),
    ),
    (
        (
            "disposition:machines:N28",
            "disposition:transitions:N28:01",
            "disposition:transitions:N28:02",
            "disposition:transitions:N28:03",
            "disposition:transitions:N28:04",
        ),
        (
            "operations:TestKnowledgeInitializeBootstrapsPortableProjectBeforeFirstWork",
            "operations:TestWorkAdoptJournalsBoardCutoverAndReplays",
            "operations:TestWorkAdoptRecoveryPreservesLaterBoardEdit",
            "operations:TestWorkAdoptRefusesStaleBoardAndUncoveredRows",
            "operations:TestWorkAdoptRefusesTamperedSourceMeaning",
            "operations:TestWorkOriginRetryFindsArchivedIdentity",
            "operations:TestWorkOriginRetryRepairsMissingAttachmentAfterArchive",
        ),
    ),
    (
        (
            "disposition:machines:N30",
            "disposition:machines:N31",
            "disposition:transitions:N30:01",
            "disposition:transitions:N30:02",
            "disposition:transitions:N30:03",
            "disposition:transitions:N30:04",
            "disposition:transitions:N31:01",
            "disposition:transitions:N31:02",
            "disposition:transitions:N31:03",
            "disposition:transitions:N31:04",
            "disposition:transitions:N31:05",
            "disposition:transitions:N31:06",
        ),
        (
            "operations:TestTrackerCoordinationT01FiniteOptInMap",
            "operations:TestWorkEffectBindingChangeDoesNotSend",
            "operations:TestWorkEffectConcurrentSyncHasOneClaim",
            "operations:TestWorkEffectDeferredClaimRequiresMergeObservation",
            "operations:TestWorkEffectLostCreateResponseRemainsUnknown",
            "operations:TestWorkIssueAdoptionRequiresUnboundIdentityAndExactRepository",
            "operations:TestWorkStatusEffectPreservesBindingAndRecordsRemoteConflict",
        ),
    ),
    (
        (
            "disposition:machines:N34",
            "disposition:transitions:N34:01",
            "disposition:transitions:N34:02",
            "disposition:transitions:N34:03",
            "disposition:transitions:N34:04",
            "disposition:transitions:N34:05",
        ),
        (
            "operations:TestAuthorizedFarmEnrichment",
            "operations:TestCanaryPreflightRequiresExactBaseBytes",
            "operations:TestFarmAuthorizationRejectsLegacyObservationLaundering",
            "operations:TestFarmProjectionBinding",
            "operations:TestFarmProjectionBindingIncludesOrderedPendingDependencies",
            "operations:TestFarmProjectionRefreshSelectsCurrentBinding",
            "operations:TestFarmSealRejectsMatchingOpenShapeForgery",
        ),
    ),
    (
        (
            "disposition:machines:N35",
            "disposition:transitions:N35:01",
            "disposition:transitions:N35:02",
            "disposition:transitions:N35:03",
        ),
        (
            "operations:TestCycleViewGroupsCanonicalWorkWithoutCopyingIt",
            "operations:TestGeneratedWorkViewIsNotCanonical",
            "operations:TestProjectViewPresentsBoundedCanonicalWork",
            "operations:TestProjectViewShowsBoundedRecordedArchitecture",
            "operations:TestWorkContextShowsBlockedPlanTaskAndUnresolvedReportWithoutChangingIt",
            "operations:TestWorkListPagesArchiveAndRejectsChangedMembership",
            "operations:TestWorkViewSelectsActualPlanTaskWithoutPromotingChecks",
        ),
    ),
    (
        ("disposition:transitions:N20:03",),
        (
            "read:TestExactBatchPinsContinuationAndKeepsRenderValidation",
            "read:TestExactBatchRejectsInvalidWholeSelection",
            "read:TestExactBatchRejectsOversizedLaterRecordBeforeDelivery",
            "read:TestExactBatchWholeRecordParityAndPages",
            "read:TestOutlineDirectPageParity",
            "read:TestPlanVerificationEmptyPlan",
            "read:TestPlanVerificationPinsContinuationAndRender",
            "read:TestPlanVerificationRejectsIncompleteOrOversizedSelection",
            "read:TestPlanVerificationRejectsInvalidRequests",
            "read:TestPlanVerificationWholeArraysAndPages",
        ),
    ),
    (
        (
            "disposition:transitions:N27:01",
            "disposition:transitions:N27:02",
        ),
        (
            "operations:TestRepairIsDiscoverableAppliedAndReplayed",
        ),
    ),
    (
        ("disposition:transitions:N27:03",),
        (
            "store:TestCreateRaceDoesNotOverwrite",
            "store:TestTransactionalCAS",
        ),
    ),
)
RECIPES.update({
    cell: {"windows/amd64": ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/" + name for name in selectors]}
    for cells, selectors in (
        *_WINDOWS_CONTEXT_ASSERTIONS, *_WINDOWS_WORK_ASSERTIONS, *_WINDOWS_STORE_AND_PROJECT_ASSERTIONS
    )
    for cell in cells
})


# The discovery suite is joined to terminal dispatch witnesses for all 80
# operations. Standalone export is observed on the original Linux suite.
RECIPES["scenario:SEQ-04"] = {
    "linux/amd64": ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
                    for name in ("TestLegacyCaptureRefusalMatchesDiscoveryDescriptor",
                                 "TestRebrandAndStandaloneExport")],
    "windows/amd64": ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
                      for name in (
                          "TestAllOperationSchemasClosed",
                          "TestApprovalDescriptorsCoverActualEffects",
                          "TestAuthorizedFarmEnrichment",
                          "TestBrownfieldCandidatesAreNotPublished",
                          "TestCapabilitiesAdvertiseVersionedOperationContract",
                          "TestConcurrentReadersPreserveAdmission",
                          "TestConcurrentReadersPreserveWriterRetry",
                          "TestContextAuthorityExactPreviewFixture",
                          "TestContextFinalizationReceiptOnlyApply",
                          "TestContextWholeDocumentOnboardingFinalization",
                          "TestCycleViewGroupsCanonicalWorkWithoutCopyingIt",
                          "TestKnowledgeContextBoundsOmissionMetadata",
                          "TestKnowledgeCutoverPagesLargeSectionInventory",
                          "TestKnowledgeMergeKeepsBothSidesAndRenamesCollidingIDs",
                          "TestMigrationPairAndRollback",
                          "TestN01AdmissionHasNoRepositoryEffects",
                          "TestN07ActiveNotApplicableAndMandatoryDispositionRefuse",
                          "TestN10ReceiptedReviewRetainsRefsAndScopeBaseline",
                          "TestN10ScopeReconcileRejectsWrongBindingsWithoutWrites",
                          "TestNT01BaselineOrdinaryWorkKeepsReportedFailuresExplicit",
                          "TestOperationDescriptorTraitsAreClosedAndHonest",
                          "TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply",
                          "TestOperationRegistryReverseClosure",
                          "TestProjectViewPresentsBoundedCanonicalWork",
                          "TestProtocolDocumentListsEveryOperation",
                          "TestReadOnlyInitializedStoreObservations",
                          "TestRepairIsDiscoverableAppliedAndReplayed",
                          "TestTrackerCoordinationT01FiniteOptInMap",
                          "TestTrackerCoordinationT04ProjectObservationAndMergeFence",
                          "TestTypedRecordReorder",
                          "TestWorkAdoptSharedOriginDistinctRows",
                          "TestWorkOriginsFindsArchivedIdentityInOneBoundedRead",
                          "TestWorkProjectEffectPreservesIssueAndScopesRetry",
                          "TestWorkStatusEffectPreservesBindingAndRecordsRemoteConflict",
                      )],
}


RECIPES["scenario:SEQ-07"] = {
    "windows/amd64": sorted(set(RECIPES["disposition:findings:N-F03"]["windows/amd64"]) |
                            set(RECIPES["disposition:findings:N-F04"]["windows/amd64"]))
}
RECIPES["scenario:SEQ-08"] = {
    platform: ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:"
               "TestScopedConflictPreservesIndependentWorkAfterJournalRecovery"]
    for platform in _PROGRESS_PLATFORMS
}
RECIPES["task:NT-03"] = copy.deepcopy(RECIPES["scenario:SEQ-04"])
RECIPES["task:NT-05"] = {
    platform: ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
               for name in (
                   "TestInterruptedRetirementRecoversExactly",
                   "TestLegacyNativeRetirementPreviewBindsPreimageAndRefusesDrift",
                   "TestLegacyNativeRetirementPreviewBindsPreimageAndRefusesDrift/old-tombstone",
                   "TestLegacyNativeRetirementPreviewBindsPreimageAndRefusesDrift/retained-unclassified-history",
                   "TestLegacyRetirementAmbiguityDoesNotBlockIndependentWork",
                   "TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory",
                   "TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory/complete",
                   "TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory/independent-edit",
                   "TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory/rollback",
                   "TestReceiptedCheckpointRetirementRecoversWithoutLosingHistory/staging",
                   "TestRetirementKindMustNameAnActualCollection",
                   "TestRetiringCheckedTaskKeepsTypedHistory",
                   "TestRetiringCheckpointKeepsScopeBaseline",
                   "TestRetiringCriterionKeepsNestedCollectionKinds",
               )]
    for platform in _PROGRESS_PLATFORMS
}
RECIPES["task:NT-06"] = {
    platform: sorted(set(RECIPES["disposition:findings:N-F05"][platform]) |
                     set(RECIPES["disposition:findings:N-F07"][platform]))
    for platform in _PROGRESS_PLATFORMS
}
RECIPES["task:NT-07"] = {
    "windows/amd64": ["go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
                      for name in (
                          "TestHistoricalWorkCheckStatusRemainsReadableWithoutEvidence",
                          "TestHistoricalWorkCheckStatusRemainsReadableWithoutEvidence/failed",
                          "TestHistoricalWorkCheckStatusRemainsReadableWithoutEvidence/passed",
                          "TestNoOperationRequestCanSetWorkCheckStatus",
                          "TestWorkAdoptJournalsBoardCutoverAndReplays",
                          "TestWorkLifecycleNeverManufacturesCheckStatus",
                          "TestWorkViewRetainsObservedPullSeparatelyFromChecksAndIssue",
                      )],
}


def selected_recipes(cells):
    import major_readiness as owner
    owner.require(isinstance(cells, list) and len(cells) <= len(RECIPES)
                  and all(isinstance(cell, str) and cell in RECIPES for cell in cells)
                  and cells == sorted(set(cells)), 'invalid native composition selection')
    return {cell: copy.deepcopy(RECIPES[cell]) for cell in cells}


def launch_finding_selection(value):
    """Finite finding on the existing HW04 identity/count/consumer transport."""
    import major_readiness as owner
    owner.require(isinstance(value, list) and value == ['disposition:findings:HOOK-F04'],
                  'invalid launch binding finding selection')
    return value


def launch_scenario_selection(value):
    """SEQ-05 uses the complete original Python/npm/native launch carrier."""
    import major_readiness as owner
    owner.require(isinstance(value, list) and value == ['scenario:SEQ-05'],
                  'invalid launch binding scenario selection')
    return value


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
    launch_cells = set()
    if 'launch_binding_tasks' in req or 'launch_binding_inputs' in req:
        import npm_binding_observation as launch
        launch.tasks(req.get('launch_binding_tasks'))
        owner.require(isinstance(req.get('launch_binding_inputs'), dict) and req['launch_binding_inputs'],
                      'npm binding source inputs missing')
        launch_cells = {'task:' + task for task in req['launch_binding_tasks']}
        owner.require(launch_cells < set(cells) and not launch_cells.intersection(recipes),
                      'npm binding task/runtime population differs')
    launch_findings = set()
    if 'launch_binding_findings' in req:
        launch_findings = set(launch_finding_selection(req['launch_binding_findings']))
        owner.require('task:HW-04' in launch_cells
                      and launch_findings < set(cells)
                      and not launch_findings.intersection(recipes)
                      and not launch_findings.intersection(req.get('source_dispositions', {}))
                      and all(jobs[cell] == 'major qualification / native' for cell in launch_findings),
                      'launch finding requires the original HW04 source and native authority')
    launch_scenarios = set()
    if 'launch_binding_scenarios' in req:
        launch_scenarios = set(launch_scenario_selection(req['launch_binding_scenarios']))
        owner.require('task:HW-04' in launch_cells
                      and launch_scenarios < set(cells)
                      and not launch_scenarios.intersection(recipes)
                      and not launch_scenarios.intersection(req.get('source_dispositions', {}))
                      and all(jobs[cell] == 'major qualification / native' for cell in launch_scenarios),
                      'launch scenario requires the original HW04 source and native authority')
    consumed = set(recipes) | launch_cells | launch_findings | launch_scenarios
    return {**{key: value for key, value in req.items()
               if key not in ('native_compositions', 'native_module_sha256',
                              'launch_binding_tasks', 'launch_binding_inputs', 'launch_binding_findings',
                              'launch_binding_scenarios')},
            'cells': [cell for cell in cells if cell not in consumed],
            'cell_jobs': {cell: job for cell, job in jobs.items() if cell not in consumed}}


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
    recipes = copy.deepcopy(req['native_compositions'])
    if req.get('launch_binding_tasks'):
        import npm_binding_observation as launch
        import ci20_native_binding as binding_owner
        for task in launch.tasks(req['launch_binding_tasks']):
            recipes['task:' + task] = {platform: launch.selectors(platform) for platform in sorted(binding_owner.PLATFORMS)}
        # A finding reuses the same complete original native consumers and the
        # same mandatory sidecars below; it never adds another test execution.
        for cell in req.get('launch_binding_findings', []) + req.get('launch_binding_scenarios', []):
            recipes[cell] = {platform: launch.selectors(platform) for platform in sorted(binding_owner.PLATFORMS)}
    platforms = sorted({platform for recipe in recipes.values() for platform in recipe})
    components = {platform: _component(req, run, artifacts, jobs, platform) for platform in platforms}
    owner.require(len({c['job_id'] for c in components.values()}) == len(platforms)
                  and len({c['artifact_id'] for c in components.values()}) == len(platforms),
                  'native component jobs or archives alias multiple platforms')
    results, used = [], {platform: set() for platform in platforms}
    for cell, recipe in sorted(recipes.items()):
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
    launch_components = {}
    if req.get('launch_binding_tasks'):
        import npm_binding_observation as launch
        import ci20_native_binding as binding_owner
        for platform in sorted(binding_owner.PLATFORMS):
            component = components[platform]
            runner = next(name for name, target in binding_owner.RUNNERS.items() if target == platform)
            matches = [item for item in artifacts if item.get('name') == launch.ARTIFACT + runner]
            owner.require(len(matches) == 1, 'original npm binding archive missing or repeated')
            artifact = matches[0]
            job = next(job for job in jobs if job['id'] == component['job_id'])
            owner.validate_upload(job, artifact, launch.UPLOAD)
            archive = owner.artifact_bytes(artifact, req)
            members = owner.members(archive)
            owner.require({m['path'] for m in members} == {f'workspaces-{n}.json' for n in launch.COUNTS},
                          'npm binding archive membership differs')
            observed = []
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                for count in launch.COUNTS:
                    raw = _document(zipped, f'workspaces-{count}.json', launch.SIDECAR_JSON_LIMIT)
                    launch.validate(raw, {**req, 'run_attempt': run['run_attempt']}, platform, count)
                    observed.append({'workspace_count': count,
                        'record_sha256': owner.digest(zipped.read(f'workspaces-{count}.json')),
                        'runtime_sha256': owner.digest(json.dumps(raw['runtime_before'],sort_keys=True,separators=(',',':')).encode()),
                        'bindings_sha256': raw['bindings_sha256'], 'launch_files': raw['launch_files']})
            launch_components[platform] = {'platform':platform,'job_id':job['id'],'artifact_id':artifact['id'],
                'archive_sha256':owner.digest(archive),'members':members,'observations':observed}
    return {**({'launch_components':launch_components} if launch_components else {}),
            'schema': ADMISSION, 'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
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
                  (owner.SCHEMA, 'codearbiter-major-readiness/2', 'codearbiter-major-site-source-readiness/1'),
                  'native composition runtime schema is invalid')
    return owner.verify(record=inner, requirements=runtime, run=run, artifact=artifact,
                        archive_digest=archive_digest, jobs=jobs, build_artifacts=build_artifacts,
                        payload_members=payload_members)
