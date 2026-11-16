"""Closed native composition unit fixtures: no Go/helper/provider execution."""
import copy, io, json, unittest, zipfile
from pathlib import Path
from unittest import mock
import major_readiness as readiness
import major_qualification_report as reports
import ci20_native_binding as binding_owner

# Exact current source-backed recipe; synthetic observations below are unit
# transport fixtures, never historical/current runtime qualification.
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


# Independent exact expected scope for the five supported current-contract cells.
# The original eight-cell fixture below remains intact.
PROGRESS_ASSERTION_NAMES = {'disposition:transitions:N09:01': ['TestAssistiveDraftWorkNeedsNoApprovalOrContextTicket',
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
PROGRESS_EXPECTED = {cell: {platform: [
    'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:' + name
    for name in required] for platform in (
        'darwin/amd64', 'darwin/arm64', 'linux/amd64', 'linux/arm64', 'windows/amd64', 'windows/arm64')}
    for cell, required in PROGRESS_ASSERTION_NAMES.items()}

FINDING_EXPECTED = {'disposition:findings:N-F02': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply',
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
                                                  'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestReadModeMetadataEffects']}}


BOUNDARY_EXPECTED = {'disposition:transitions:N01:01': {'darwin/amd64': ['go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN01AdmissionHasNoRepositoryEffects',
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
                                                      'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestTaskCheckSubjectPathChangeInvalidatesOnlyReportedCheckApplicability']}}


CLI_EXPECTED = {'disposition:transitions:N37:01': {platform: [
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
] for platform in ('darwin/amd64','darwin/arm64','linux/amd64','linux/arm64','windows/amd64','windows/arm64')}}


class NativeCompositeAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.source='a'*40;self.tree='b'*40;self.module='c'*64
        self.cell='disposition:findings:N-F05';self.runtime='installed:fixture:package'
        self.req={'source_commit':self.source,'source_tree':self.tree,'ci_run_id':7,'task_ids':['Q-02'],
            'cells':[self.cell,self.runtime], 'cell_jobs':{self.cell:'major qualification / native',self.runtime:'Runtime fixture'},
            'native_compositions':{self.cell:copy.deepcopy(RECIPES[self.cell])},
            'native_module_sha256':{'posix':self.module,'windows':self.module},
            'required_artifact_names':['qualified-payload'],'targets':[]}
        self.run={'id':7,'run_attempt':1,'head_sha':self.source,'head_branch':'main','event':'push',
            'path':'.github/workflows/ci.yml','conclusion':'success','repository':{'full_name':readiness.REPOSITORY}}
        self.data={};self.artifacts=[];self.jobs=[];self.raw={};self.stamps={}
        self.job_artifacts={}
        for index,(runner,platform) in enumerate(sorted(binding_owner.RUNNERS.items())):
            binary=('ca-artifact-'+platform.replace('/','-')+('.exe' if platform.startswith('windows/') else ''))
            inert=('inert binary fixture '+platform).encode()
            manifest={'format':'codearbiter.artifact-release/0.1.0','version':'0.1.0',
                'protocol':'codearbiter.artifact-api/0.1.0','schema_version':'0.3.2',
                'binaries':{platform:{'file':binary,'sha256':readiness.digest(inert),'native_tested':True}}}
            encoded=json.dumps(manifest).encode()
            stamp={'format':binding_owner.FORMAT,'source_commit':self.source,'run_id':'7','run_attempt':'1',
                'workflow':binding_owner.WORKFLOW,'producer_job':binding_owner.PRODUCER,'platform':platform,
                'toolchain':binding_owner.TOOLCHAIN,'module_sha256':self.module,'go_sha256':'d'*64,
                'manifest_sha256':readiness.digest(encoded),'binary_sha256':readiness.digest(inert)}
            selectors=sorted(set(RECIPES[self.cell][platform]))
            selected=[{'package':s.split(':',2)[1],'test':s.split(':',2)[2]} for s in selectors]
            raw={'format':'codearbiter.go-test-observation/1','complete':True,
                'module_sha256_before':self.module,'module_sha256_after':self.module,
                'argv':['python','tools/go_test_parallel.py','--module','core/artifacts'],
                'selected':selected,'observed':[{**r,'result':'pass'} for r in selected],
                'subtests':[{'package':selected[0]['package'],'test':selected[0]['test']+'/owned-case','result':'pass'}]}
            self.raw[platform]=raw;self.stamps[platform]=stamp
            files={'artifact-candidate/release.json':encoded,'artifact-candidate/'+binary:inert,
                'ci20-native-tested.json':json.dumps(stamp).encode(),'native-tests.json':json.dumps(raw).encode(),
                'native-observation.json':json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()}
            job=self.job(200+index,'[CHECK] | [CORE] | Tested native candidate build <'+platform+'>',
                         'Share the real tested candidate with this workflow run')
            self.add_archive(100+index,'ci20-native-tested-'+runner,files,job)
        package=self.zip({'package.txt':b'inert runtime package'})
        payload=self.metadata(12,'qualified-payload',package)
        self.artifacts.append(payload);self.data[12]=package
        self.report={'schema':'codearbiter-major-qualification/1','source_commit':self.source,'source_tree':self.tree,
            'ci_run_id':7,'job_id':20,'results':[{'cell':self.runtime,'result':'PASSED',
                'commands':[{'argv':['inert-unit-fixture'],'exit_code':0}],'selected_population':1,'executed_population':1,
                'payload_artifact_id':12,'payload_archive_sha256':readiness.digest(package),'payload_members':readiness.members(package)}]}
        self.add_archive(30,'major-qualification-20',{'qualification.json':json.dumps(self.report).encode()},
                         self.job(20,'Runtime fixture','Upload major qualification report'))
        self.producer=self.job(99,'major readiness producer','Upload major readiness record')
        self.jobs.append(self.producer)

    @staticmethod
    def zip(files):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as zipped:
            for name,data in files.items():zipped.writestr(name,data)
        return stream.getvalue()

    def job(self,identity,name,step):
        return {'id':identity,'name':name,'run_id':7,'run_attempt':1,'status':'completed','conclusion':'success',
            'steps':[{'name':step,'status':'completed','conclusion':'success',
                'started_at':'2026-11-13T15:00:00Z','completed_at':'2026-11-13T15:00:03Z'}]}

    def metadata(self,identity,name,data):
        return {'id':identity,'name':name,'expired':False,'size_in_bytes':len(data),
            'digest':'sha256:'+readiness.digest(data),'created_at':'2026-11-13T15:00:01Z',
            'workflow_run':{'id':7,'head_sha':self.source}}

    def add_archive(self,identity,name,files,job):
        data=self.zip(files);self.data[identity]=data;self.artifacts.append(self.metadata(identity,name,data))
        self.jobs.append(job);self.job_artifacts[job['id']]=identity

    def api(self,path,binary=False):
        if path=='actions/runs/7':return self.run
        if path.startswith('actions/artifacts/') and path.endswith('/zip'):
            return self.data[int(path.split('/')[2])]
        if path.startswith('actions/jobs/') and path.endswith('/logs'):
            identity=int(path.split('/')[2]);item=(self.latest_readiness_metadata if identity==99
                else next(a for a in self.artifacts if a['id']==self.job_artifacts[identity]))
            return ('2026-11-13T15:00:00Z ##[group]Run '+readiness.UPLOAD_ACTION+'\n'
                '2026-11-13T15:00:01Z SHA256 digest of uploaded artifact is '+item['digest'][7:]+'\n'
                '2026-11-13T15:00:02Z Artifact '+item['name']+' successfully finalized. Artifact ID '+str(item['id'])+'\n').encode()
        raise AssertionError('unexpected fixture API operation')

    def produce(self):
        with mock.patch.object(readiness,'api',side_effect=self.api):
            return readiness.produce(self.req,self.artifacts,self.jobs)

    def test_six_original_archives_form_one_complete_cell_without_fictional_job(self):
        record=self.produce()
        self.assertEqual(record['schema'],'codearbiter-major-readiness/4')
        self.assertEqual(record['native']['results'][0]['cell'],self.cell)
        self.assertEqual(record['native']['results'][0]['result'],'PASSED')
        self.assertEqual(len(record['native']['components']),6)
        self.assertNotIn('job_id',record['native']['results'][0])
        self.assertEqual([x['cell'] for x in record['runtime']['results']],[self.runtime])

    def rewrite(self, platform, mutate):
        runner={v:k for k,v in binding_owner.RUNNERS.items()}[platform]
        item=next(a for a in self.artifacts if a['name']=='ci20-native-tested-'+runner)
        with zipfile.ZipFile(io.BytesIO(self.data[item['id']])) as zipped:
            files={name:zipped.read(name) for name in zipped.namelist()}
        mutate(files)
        data=self.zip(files);self.data[item['id']]=data
        item.update(digest='sha256:'+readiness.digest(data),size_in_bytes=len(data))

    @staticmethod
    def json_edit(files, path, mutate):
        value=json.loads(files[path]);mutate(value);files[path]=json.dumps(value).encode()

    def test_original_platform_archive_job_or_upload_omissions_never_pass(self):
        initial=(copy.deepcopy(self.artifacts),copy.deepcopy(self.jobs))
        for reason in ('missing archive','duplicate archive','missing job','wrong platform name',
                       'failed job','wrong job run','wrong job attempt','failed upload','wrong artifact run',
                       'forged uploader log'):
            self.artifacts,self.jobs=copy.deepcopy(initial)
            target=next(a for a in self.artifacts if a['name']=='ci20-native-tested-windows-2025')
            job=next(j for j in self.jobs if j['name'].endswith('<windows/amd64>'))
            if reason=='missing archive':self.artifacts.remove(target)
            elif reason=='duplicate archive':self.artifacts.append(dict(target))
            elif reason=='missing job':self.jobs.remove(job)
            elif reason=='wrong platform name':job['name']=job['name'].replace('windows/amd64','windows/unknown')
            elif reason=='failed job':job['conclusion']='failure'
            elif reason=='wrong job run':job['run_id']=8
            elif reason=='wrong job attempt':job['run_attempt']=2
            elif reason=='failed upload':job['steps'][0]['conclusion']='skipped'
            elif reason=='wrong artifact run':target['workflow_run']['id']=8
            elif reason=='forged uploader log':self.job_artifacts[job['id']]=30
            with self.subTest(reason=reason),self.assertRaises((readiness.ReadinessError,ValueError)):
                self.produce()
            self.job_artifacts[job['id']]=target['id']

    def test_source_stamp_original_raw_candidate_and_child_refusals_are_independent(self):
        initial=(copy.deepcopy(self.artifacts),dict(self.data))
        for reason in ('source','run','attempt','platform','module','missing children','duplicate child',
                       'child skip','retained observation','extra member','binary bytes','native_tested'):
            self.artifacts,self.data=copy.deepcopy(initial)
            def mutate(files):
                if reason in ('source','run','attempt','platform','module'):
                    field,value={'source':('source_commit','e'*40),'run':('run_id','8'),
                        'attempt':('run_attempt','2'),'platform':('platform','windows/arm64'),
                        'module':('module_sha256','e'*64)}[reason]
                    self.json_edit(files,'ci20-native-tested.json',lambda d:d.update(**{field:value}))
                elif reason=='missing children':self.json_edit(files,'native-tests.json',lambda d:d.pop('subtests'))
                elif reason in ('duplicate child','child skip'):
                    raw=json.loads(files['native-tests.json'])
                    if reason=='duplicate child':raw['subtests'].append(dict(raw['subtests'][0]))
                    else:raw['subtests'][0]['result']='skip'
                    files['native-tests.json']=json.dumps(raw).encode()
                    if reason=='child skip':
                        stamp=json.loads(files['ci20-native-tested.json'])
                        files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
                elif reason=='retained observation':
                    self.json_edit(files,'native-observation.json',lambda d:d.update(source_tree='e'*40))
                elif reason=='extra member':files['foreign.txt']=b'unexpected'
                elif reason=='binary bytes':files['artifact-candidate/ca-artifact-windows-amd64.exe']+=b'changed'
                elif reason=='native_tested':
                    self.json_edit(files,'artifact-candidate/release.json',
                        lambda d:d['binaries']['windows/amd64'].update(native_tested=False))
            self.rewrite('windows/amd64',mutate)
            with self.subTest(reason=reason),self.assertRaises((readiness.ReadinessError,ValueError)):
                self.produce()

    def test_recipe_cannot_drop_a_platform_selector_or_claim_an_unmapped_cell(self):
        for change in ('platform','selector','unmapped','source substitute'):
            req=copy.deepcopy(self.req)
            if change=='platform':req['native_compositions'][self.cell].pop('darwin/arm64')
            elif change=='selector':req['native_compositions'][self.cell]['windows/amd64'].pop()
            elif change=='unmapped':
                req['native_compositions']['disposition:machines:N14']=req['native_compositions'].pop(self.cell)
            else:req['source_dispositions']={self.cell:{'result':'PRESERVED'}}
            with self.subTest(change=change),mock.patch.object(readiness,'api',side_effect=self.api), \
                 self.assertRaises(readiness.ReadinessError):
                readiness.produce(req,self.artifacts,self.jobs)

    def readiness_artifact(self, record):
        archive=self.zip({'major-readiness.json':json.dumps(record).encode()})
        metadata=self.metadata(11,'major-readiness-'+self.source,archive)
        self.data[11]=archive;self.job_artifacts[99]=11;self.latest_readiness_metadata=metadata
        return metadata,archive

    def verify(self, record, **changes):
        artifact,archive=self.readiness_artifact(record)
        args=dict(record=record,requirements=self.req,run=self.run,artifact=artifact,
            archive_digest=readiness.digest(archive),jobs=self.jobs,build_artifacts=self.artifacts,
            payload_members={12:readiness.members(self.data[12])})
        args.update(changes)
        with mock.patch.object(readiness,'api',side_effect=self.api):return readiness.verify(**args)

    def test_final_reader_authenticates_again_and_requires_whole_success_and_runtime(self):
        record=self.produce()
        self.assertEqual(self.verify(record)['state'],'PREPUBLICATION_READY')
        for field,value in [('conclusion','failure'),('conclusion',None),('head_branch','major/state-contracts'),
                            ('event','pull_request'),('head_sha','e'*40)]:
            with self.subTest(field=field,value=value),self.assertRaises(readiness.ReadinessError):
                self.verify(record,run={**self.run,field:value})
        for change in ('native result','missing component','runtime result','recursive','unknown'):
            wrong=copy.deepcopy(record)
            if change=='native result':wrong['native']['results'][0]['result']='SKIPPED'
            elif change=='missing component':wrong['native']['components'].pop()
            elif change=='runtime result':wrong['runtime']['results'].clear()
            elif change=='recursive':wrong['runtime']['schema']='codearbiter-major-readiness/4'
            else:wrong['runtime']['schema']='unknown'
            with self.subTest(change=change),self.assertRaises(readiness.ReadinessError):self.verify(wrong)

    def test_producer_phase_does_not_require_its_own_completion_or_upload_log(self):
        self.run['conclusion']=None
        self.producer.update(status='in_progress',conclusion=None)
        record=self.produce()
        self.assertEqual(record['schema'],'codearbiter-major-readiness/4')
        with self.assertRaises(readiness.ReadinessError):self.verify(record)

    def test_load_reconstructs_exact_components_and_walks_only_runtime_package_archives(self):
        record=self.produce();metadata,archive=self.readiness_artifact(record)
        with mock.patch.object(readiness,'collect',return_value=(self.req,self.run,self.artifacts+[metadata],self.jobs)), \
             mock.patch.object(readiness,'api',side_effect=self.api):
            actual,result=readiness.load_verified_receipt(None,self.source,7)
            self.assertEqual(actual,record);self.assertEqual(result['source'],self.source)
        wrong=copy.deepcopy(record);wrong['native']['components'][0]['archive_sha256']='e'*64
        metadata,archive=self.readiness_artifact(wrong)
        with mock.patch.object(readiness,'collect',return_value=(self.req,self.run,self.artifacts+[metadata],self.jobs)), \
             mock.patch.object(readiness,'api',side_effect=self.api),self.assertRaisesRegex(
                readiness.ReadinessError,'original qualification evidence'):
            readiness.load_verified_receipt(None,self.source,7)

    def test_source3_native4_core1_layer_keeps_separate_typed_source_truth(self):
        source_cell='disposition:transitions:inert-source'
        self.req['cells'].append(source_cell);self.req['cell_jobs'][source_cell]='major qualification / source'
        self.req['source_dispositions']={source_cell:{'result':'PRESERVED','proofs':[{
            'ref':'inert-proof.json','ref_commit':self.source,'sha256':'e'*64,'source_commit':self.source,
            'kind':'conformance-check','result':'PRESERVED','producer':{'class':'source-conformance',
                'identity':'inert schema-composition unit fixture, not proof'},'current_at':self.source}]}}
        record=self.produce()
        self.assertEqual(record['schema'],'codearbiter-major-readiness/3')
        self.assertEqual(record['runtime']['schema'],'codearbiter-major-readiness/4')
        self.assertEqual(readiness.runtime_record(record)['schema'],readiness.SCHEMA)
        self.assertEqual(record['source_dispositions'][source_cell]['result'],'PRESERVED')
        self.assertEqual(self.verify(record)['state'],'PREPUBLICATION_READY')
        wrong=copy.deepcopy(record);wrong['runtime']['native']['results'][0]['result']='SKIPPED'
        with self.assertRaises(readiness.ReadinessError):self.verify(wrong)

    def test_all_eight_exact_routes_keep_platforms_and_other_native_holds(self):
        self.req['native_compositions']=copy.deepcopy(RECIPES)
        self.req['cells']=[self.runtime,*sorted(RECIPES)]
        self.req['cell_jobs']={self.runtime:'Runtime fixture',**dict.fromkeys(RECIPES,'major qualification / native')}
        for platform in self.raw:
            selectors=sorted({s for recipe in RECIPES.values() for s in recipe.get(platform,[])})
            def extend(files):
                raw=json.loads(files['native-tests.json'])
                raw['selected']=[{'package':s.split(':',2)[1],'test':s.split(':',2)[2]} for s in selectors]
                raw['observed']=[{**row,'result':'pass'} for row in raw['selected']]
                raw['subtests']=[]
                files['native-tests.json']=json.dumps(raw).encode()
                stamp=json.loads(files['ci20-native-tested.json'])
                files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
            self.rewrite(platform,extend)
        record=self.produce()
        self.assertEqual({r['cell'] for r in record['native']['results']},set(RECIPES))
        for row in record['native']['results']:
            self.assertEqual({c['platform'] for c in row['components']},set(RECIPES[row['cell']]))
        for cell in ('disposition:machines:N14','disposition:transitions:N27:03','disposition:findings:N-F09'):
            self.assertNotIn(cell,RECIPES)
        self.assertEqual(self.verify(record)['state'],'PREPUBLICATION_READY')

    def test_source3_native4_docs2_core1_load_verifies_both_original_runs(self):
        import test_site_playwright_observation as fixture
        docs_case=fixture.DocsAuthorityTests();docs_case.setUp()
        self.req['cells']+=fixture.CELLS
        self.req['cell_jobs'].update(dict.fromkeys(fixture.CELLS,fixture.JOB))
        source_cell='disposition:transitions:inert-source'
        self.req['cells'].append(source_cell);self.req['cell_jobs'][source_cell]='major qualification / source'
        self.req['source_dispositions']={source_cell:{'result':'PRESERVED','proofs':[{
            'ref':'inert-proof.json','ref_commit':self.source,'sha256':'e'*64,'source_commit':self.source,
            'kind':'conformance-check','result':'PRESERVED','producer':{'class':'source-conformance',
                'identity':'inert schema unit fixture'},'current_at':self.source}]}}
        original=self.api
        def api(path,binary=False):
            if ('docs.yml/runs?' in path or path.startswith('actions/runs/17')
                    or path=='actions/jobs/29/logs' or path in ('actions/artifacts/31/zip','actions/artifacts/32/zip')):
                return docs_case.api(path,binary)
            return original(path,binary)
        with mock.patch.object(readiness,'api',side_effect=api):
            record=readiness.produce(self.req,self.artifacts,self.jobs)
        self.assertEqual(record['schema'],'codearbiter-major-readiness/3')
        self.assertEqual(record['runtime']['schema'],'codearbiter-major-readiness/4')
        self.assertEqual(record['runtime']['runtime']['schema'],'codearbiter-major-readiness/2')
        self.assertEqual(readiness.runtime_record(record)['schema'],'codearbiter-major-readiness/2')
        metadata,archive=self.readiness_artifact(record)
        with mock.patch.object(readiness,'collect',return_value=(self.req,self.run,self.artifacts+[metadata],self.jobs)), \
             mock.patch.object(readiness,'api',side_effect=api):
            actual,result=readiness.load_verified_receipt(None,self.source,7)
            self.assertEqual(actual,record);self.assertEqual(result['docs_run_id'],17)
            docs_case.run['conclusion']='failure'
            with self.assertRaises(readiness.ReadinessError):readiness.load_verified_receipt(None,self.source,7)
        for bad in ({'schema':'codearbiter-major-readiness/3','runtime':record},
                    {'schema':'codearbiter-major-readiness/4','runtime':record},
                    {'schema':'codearbiter-major-readiness/4','runtime':{'schema':'unknown'}}):
            with self.assertRaises(readiness.ReadinessError):readiness.runtime_record(bad)

    def _select_progress_contracts(self):
        self.req['native_compositions']=copy.deepcopy(PROGRESS_EXPECTED)
        self.req['cells']=[self.runtime,*sorted(PROGRESS_EXPECTED)]
        self.req['cell_jobs']={self.runtime:'Runtime fixture',
            **dict.fromkeys(PROGRESS_EXPECTED,'major qualification / native')}
        for platform in self.raw:
            selectors=sorted({name for recipe in PROGRESS_EXPECTED.values() for name in recipe[platform]})
            def extend(files):
                raw=json.loads(files['native-tests.json'])
                identities=[name.split(':',2)[1:] for name in selectors]
                parents=sorted({(package,test.split('/',1)[0]) for package,test in identities})
                raw['selected']=[{'package':package,'test':test} for package,test in parents]
                raw['observed']=[{**row,'result':'pass'} for row in raw['selected']]
                raw['subtests']=[{'package':package,'test':test,'result':'pass'}
                    for package,test in identities if '/' in test]
                files['native-tests.json']=json.dumps(raw).encode()
                stamp=json.loads(files['ci20-native-tested.json'])
                files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
            self.rewrite(platform,extend)

    def test_current_progress_recipes_keep_all_original_routes_and_complete_required_children(self):
        import major_native_observation as native
        self.assertEqual(native.selected_recipes(sorted(PROGRESS_EXPECTED)),PROGRESS_EXPECTED)
        self.assertEqual({cell:native.RECIPES[cell] for cell in RECIPES},RECIPES)
        self.assertEqual(set(native.RECIPES),set(RECIPES)|set(PROGRESS_EXPECTED)|set(FINDING_EXPECTED)|set(BOUNDARY_EXPECTED)|set(CLI_EXPECTED))
        self._select_progress_contracts()
        record=self.produce()
        self.assertEqual({row['cell'] for row in record['native']['results']},set(PROGRESS_EXPECTED))
        for row in record['native']['results']:
            self.assertEqual({c['platform']:c['selectors'] for c in row['components']},PROGRESS_EXPECTED[row['cell']])
        self.assertEqual(self.verify(record)['state'],'PREPUBLICATION_READY')

    def test_progress_parent_pass_cannot_replace_required_child_or_platform_observations(self):
        import major_native_observation as native
        self._select_progress_contracts()
        initial=(copy.deepcopy(self.artifacts),dict(self.data))
        for cell,recipe in PROGRESS_EXPECTED.items():
            changed=copy.deepcopy(self.req)
            changed['native_compositions'][cell].pop('darwin/arm64')
            with self.subTest(cell=cell,missing='required platform'), self.assertRaises(readiness.ReadinessError):
                native.runtime_requirements(changed)
            # Each of the five recipes has actual named matrix children. Keep
            # every parent PASS and all archive/stamp/source metadata coherent.
            selected=next(name for name in recipe['windows/amd64'] if '/' in name.split(':',2)[2])
            package,test=selected.split(':',2)[1:]
            for mode in ('missing','skip'):
                self.artifacts,self.data=copy.deepcopy(initial)
                def change(files):
                    raw=json.loads(files['native-tests.json'])
                    match=lambda row:row['package']==package and row['test']==test
                    self.assertEqual(sum(map(match,raw['subtests'])),1)
                    if mode=='missing':raw['subtests']=[row for row in raw['subtests'] if not match(row)]
                    else:
                        next(row for row in raw['subtests'] if match(row))['result']='skip'
                    files['native-tests.json']=json.dumps(raw).encode()
                    stamp=json.loads(files['ci20-native-tested.json'])
                    files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
                self.rewrite('windows/amd64',change)
                with self.subTest(cell=cell,child=mode), self.assertRaises(readiness.ReadinessError):self.produce()

    def test_n11_current_contract_requires_nonempty_history_control_and_every_event_child(self):
        import major_native_observation as native
        cell='disposition:transitions:N11:03'
        try:
            selected=native.selected_recipes([cell])
        except readiness.ReadinessError as error:
            self.fail('Current accepted N11 history contract has no complete canonical route: '+str(error))
        self.assertEqual(selected,{cell:PROGRESS_EXPECTED[cell]})
        policy=json.loads((Path(__file__).resolve().parents[2]/'.github/major-qualification-policy.json').read_text())
        self.assertEqual(set(policy['native_composite_cells']),set(RECIPES)|set(PROGRESS_EXPECTED)|set(FINDING_EXPECTED)|set(BOUNDARY_EXPECTED)|set(CLI_EXPECTED))
        parent='go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestN11AncestorChangesPreserveDependentHistoryAndIndependentStops'
        children=[parent+'/'+name for name in ('ancestor-block','receipted-pending','receipted-blocked')]
        for platform,required in selected[cell].items():
            self.assertIn(parent,required)
            self.assertIn('go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:TestNT09LegacyStaleIsUnresolvedAndRetainsRawReason',required)
            for child in children:self.assertIn(child,required)
        self._select_progress_contracts()
        record=self.produce()
        result=next(row for row in record['native']['results'] if row['cell']==cell)
        self.assertEqual({row['platform']:row['selectors'] for row in result['components']},PROGRESS_EXPECTED[cell])
        self.assertEqual(self.verify(record)['state'],'PREPUBLICATION_READY')
        initial=(copy.deepcopy(self.artifacts),dict(self.data))
        for child in children:
            package,test=child.split(':',2)[1:]
            for mode in ('missing','skip'):
                self.artifacts,self.data=copy.deepcopy(initial)
                def change(files):
                    raw=json.loads(files['native-tests.json'])
                    match=lambda row:row['package']==package and row['test']==test
                    self.assertEqual(sum(map(match,raw['subtests'])),1)
                    if mode=='missing':raw['subtests']=[row for row in raw['subtests'] if not match(row)]
                    else:next(row for row in raw['subtests'] if match(row))['result']='skip'
                    files['native-tests.json']=json.dumps(raw).encode()
                    stamp=json.loads(files['ci20-native-tested.json'])
                    files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
                self.rewrite('windows/amd64',change)
                with self.subTest(child=child,mode=mode),self.assertRaisesRegex(readiness.ReadinessError,
                    'native composite (selected assertion missing|required child skipped)'):
                    self.produce()

    def test_same_run_source_consumer_alias_requires_original_component_authority(self):
        import major_native_observation as native
        with mock.patch.object(readiness,'api',side_effect=self.api):
            component=native.authenticate_component(self.req,self.run,self.artifacts,self.jobs,'windows/amd64')
            self.assertEqual(component['native_binding']['platform'],'windows/amd64')
            self.assertEqual(component['archive_sha256'],next(a for a in self.artifacts
                if a['id']==component['artifact_id'])['digest'][7:])
            for change in ('source','attempt','event','missing module pin','unknown platform'):
                run=copy.deepcopy(self.run);req=copy.deepcopy(self.req);platform='windows/amd64'
                if change=='source':run['head_sha']='e'*40
                elif change=='attempt':run['run_attempt']=2
                elif change=='event':run['event']='pull_request'
                elif change=='missing module pin':req.pop('native_module_sha256')
                else:platform='windows/unknown'
                with self.subTest(change=change),self.assertRaises(readiness.ReadinessError):
                    native.authenticate_component(req,run,self.artifacts,self.jobs,platform)

    def test_internally_consistent_foreign_stamp_cannot_rebind_current_source_run_or_module(self):
        initial=(copy.deepcopy(self.artifacts),dict(self.data))
        for field,value in [('source_commit','e'*40),('run_id','8'),('run_attempt','2'),
                            ('platform','windows/arm64'),('module_sha256','e'*64)]:
            self.artifacts,self.data=copy.deepcopy(initial)
            def mutate(files):
                stamp=json.loads(files['ci20-native-tested.json']);stamp[field]=value
                raw=json.loads(files['native-tests.json'])
                if field=='module_sha256':raw.update(module_sha256_before=value,module_sha256_after=value)
                files['ci20-native-tested.json']=json.dumps(stamp).encode()
                files['native-tests.json']=json.dumps(raw).encode()
                files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
            self.rewrite('windows/amd64',mutate)
            with self.subTest(field=field),self.assertRaisesRegex(readiness.ReadinessError,'source/run/platform/module'):
                self.produce()

    def test_consistent_unexecuted_candidate_manifest_still_refuses_native_tested_false(self):
        def mutate(files):
            manifest=json.loads(files['artifact-candidate/release.json'])
            manifest['binaries']['windows/amd64']['native_tested']=False
            encoded=json.dumps(manifest).encode();files['artifact-candidate/release.json']=encoded
            stamp=json.loads(files['ci20-native-tested.json']);stamp['manifest_sha256']=readiness.digest(encoded)
            files['ci20-native-tested.json']=json.dumps(stamp).encode()
            raw=json.loads(files['native-tests.json'])
            files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
        self.rewrite('windows/amd64',mutate)
        with self.assertRaisesRegex(ValueError,'native and module-tested'):self.produce()

    def test_complete_finding_routes_require_actual_named_results_on_every_platform(self):
        import major_native_observation as native
        self.assertEqual(native.selected_recipes(sorted(FINDING_EXPECTED)), FINDING_EXPECTED)
        with mock.patch.dict(globals(), PROGRESS_EXPECTED=FINDING_EXPECTED):
            self._select_progress_contracts()
        record=self.produce()
        self.assertEqual({row['cell'] for row in record['native']['results']}, set(FINDING_EXPECTED))
        self.assertEqual(self.verify(record)['state'], 'PREPUBLICATION_READY')
        initial=(copy.deepcopy(self.artifacts), dict(self.data))
        for cell, recipe in FINDING_EXPECTED.items():
            for platform, names in recipe.items():
                self.assertEqual(set(recipe), set(self.raw))
                package,test=names[-1].split(':',2)[1:]
                self.artifacts,self.data=copy.deepcopy(initial)
                def change(files):
                    raw=json.loads(files['native-tests.json'])
                    found=[row for row in raw['observed'] if row['package']==package and row['test']==test]
                    self.assertEqual(len(found),1)
                    found[0]['result']='skip'
                    files['native-tests.json']=json.dumps(raw).encode()
                    stamp=json.loads(files['ci20-native-tested.json'])
                    files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
                self.rewrite(platform,change)
                with self.subTest(cell=cell,platform=platform), self.assertRaises(readiness.ReadinessError):
                    self.produce()

    def test_boundary_contracts_require_named_effect_controls_on_every_platform(self):
        import major_native_observation as native
        self.assertEqual(native.selected_recipes(sorted(BOUNDARY_EXPECTED)), BOUNDARY_EXPECTED)
        with mock.patch.dict(globals(), PROGRESS_EXPECTED=BOUNDARY_EXPECTED):
            self._select_progress_contracts()
        record=self.produce()
        self.assertEqual({row['cell'] for row in record['native']['results']}, set(BOUNDARY_EXPECTED))
        self.assertEqual(self.verify(record)['state'], 'PREPUBLICATION_READY')
        initial=(copy.deepcopy(self.artifacts), dict(self.data))
        for cell,recipe in BOUNDARY_EXPECTED.items():
            for platform,names in recipe.items():
                self.assertEqual(set(recipe), set(self.raw))
                selected=next((name for name in names if '/' in name.split(':',2)[2]), names[0])
                package,test=selected.split(':',2)[1:]
                self.artifacts,self.data=copy.deepcopy(initial)
                def change(files):
                    raw=json.loads(files['native-tests.json'])
                    population=raw['subtests'] if '/' in test else raw['observed']
                    found=[row for row in population if row['package']==package and row['test']==test]
                    self.assertEqual(len(found), 1)
                    found[0]['result']='skip'
                    files['native-tests.json']=json.dumps(raw).encode()
                    stamp=json.loads(files['ci20-native-tested.json'])
                    files['native-observation.json']=json.dumps(reports.admit_go(raw,stamp,self.tree)).encode()
                self.rewrite(platform,change)
                with self.subTest(cell=cell,platform=platform), self.assertRaises(readiness.ReadinessError):
                    self.produce()

    def _select_cli_contracts(self, recipes):
        self.req['native_compositions'] = copy.deepcopy(recipes)
        self.req['cells'] = [self.runtime, *sorted(recipes)]
        self.req['cell_jobs'] = {self.runtime: 'Runtime fixture',
            **dict.fromkeys(recipes, 'major qualification / native')}
        for platform in self.raw:
            selectors = sorted({name for recipe in recipes.values() for name in recipe.get(platform, [])})
            def extend(files):
                raw = json.loads(files['native-tests.json'])
                identities = [name.split(':', 2)[1:] for name in selectors]
                parents = sorted({(package, test.split('/', 1)[0]) for package, test in identities})
                raw['selected'] = [{'package': package, 'test': test} for package, test in parents]
                raw['observed'] = [{**row, 'result': 'pass'} for row in raw['selected']]
                raw['subtests'] = [{'package': package, 'test': test, 'result': 'pass'}
                    for package, test in identities if '/' in test]
                files['native-tests.json'] = json.dumps(raw).encode()
                stamp = json.loads(files['ci20-native-tested.json'])
                files['native-observation.json'] = json.dumps(reports.admit_go(raw, stamp, self.tree)).encode()
            self.rewrite(platform, extend)

    def test_cli_route_joins_sorted_twenty_policy_and_all_original_components(self):
        import major_native_observation as native
        cell = 'disposition:transitions:N37:01'
        try:
            selected = native.selected_recipes([cell])
        except readiness.ReadinessError as error:
            self.fail('Complete CLI boundary has no canonical composition route: ' + str(error))
        self.assertEqual(selected, CLI_EXPECTED)
        expected = {**RECIPES, **PROGRESS_EXPECTED, **FINDING_EXPECTED, **BOUNDARY_EXPECTED, **CLI_EXPECTED}
        self.assertEqual(len(expected), 20)
        self.assertEqual(native.RECIPES, expected)
        policy = json.loads((Path(__file__).resolve().parents[1] / 'major-qualification-policy.json').read_text(encoding='utf-8'))
        cells = policy['native_composite_cells']
        self.assertEqual(cells, sorted(set(cells)))
        self.assertEqual(native.selected_recipes(cells), expected)
        for invalid in (list(reversed(cells)), cells + [cell], sorted([*cells, 'disposition:transitions:N27:03'])):
            with self.subTest(selection='noncanonical-or-unmapped'), self.assertRaises(readiness.ReadinessError):
                native.selected_recipes(invalid)
        self._select_cli_contracts(expected)
        record = self.produce()
        self.assertEqual({row['cell'] for row in record['native']['results']}, set(expected))
        self.assertEqual(len(record['native']['components']), 6)
        for row in record['native']['results']:
            self.assertEqual({component['platform']: component['selectors'] for component in row['components']}, expected[row['cell']])
        self.assertEqual(self.verify(record)['state'], 'PREPUBLICATION_READY')
        for field, value in (('conclusion', 'failure'), ('event', 'pull_request')):
            with self.subTest(final_gate=field), self.assertRaises(readiness.ReadinessError):
                self.verify(record, run={**self.run, field: value})

    def test_cli_parent_pass_never_substitutes_for_required_child_or_platform(self):
        import major_native_observation as native
        cell = 'disposition:transitions:N37:01'
        self.assertEqual(native.selected_recipes([cell]), CLI_EXPECTED)
        self._select_cli_contracts(CLI_EXPECTED)
        initial = (copy.deepcopy(self.artifacts), dict(self.data))
        names = CLI_EXPECTED[cell]['windows/amd64']
        parent = next(name for name in names if name.endswith(':TestN37CLIValidDecodeOnceAndCommittedOutputFailure'))
        # All ten mandatory terminal children and the original CLI error
        # complement remain independent of the passing new parent.
        required = [name for name in names if '/' in name.split(':', 2)[2]
                    or name.endswith(':TestCLIEmitsJSONFaultAndMatchingExitClass')]
        self.assertEqual(len(required), 11)
        for name in required:
            package, test = name.split(':', 2)[1:]
            for mode in ('missing', 'skip'):
                self.artifacts, self.data = copy.deepcopy(initial)
                def change(files):
                    raw = json.loads(files['native-tests.json'])
                    ppackage, ptest = parent.split(':', 2)[1:]
                    self.assertEqual([row['result'] for row in raw['observed'] if row['package'] == ppackage and row['test'] == ptest], ['pass'])
                    population = raw['subtests'] if '/' in test else raw['observed']
                    found = [row for row in population if row['package'] == package and row['test'] == test]
                    self.assertEqual(len(found), 1)
                    if mode == 'missing':
                        population.remove(found[0])
                        if '/' not in test:
                            raw['selected'] = [row for row in raw['selected']
                                if not (row['package'] == package and row['test'] == test)]
                    else: found[0]['result'] = 'skip'
                    files['native-tests.json'] = json.dumps(raw).encode()
                    stamp = json.loads(files['ci20-native-tested.json'])
                    files['native-observation.json'] = json.dumps(reports.admit_go(raw, stamp, self.tree)).encode()
                self.rewrite('windows/amd64', change)
                with self.subTest(required=test, outcome=mode), self.assertRaisesRegex(readiness.ReadinessError, 'selected assertion|child'):
                    self.produce()
        for platform in CLI_EXPECTED[cell]:
            self.artifacts, self.data = copy.deepcopy(initial)
            runner = {value: key for key, value in binding_owner.RUNNERS.items()}[platform]
            self.artifacts = [item for item in self.artifacts if item['name'] != 'ci20-native-tested-' + runner]
            with self.subTest(platform=platform, missing='original archive'), self.assertRaisesRegex(readiness.ReadinessError, 'archive/job'):
                self.produce()
            changed = copy.deepcopy(self.req)
            changed['native_compositions'][cell].pop(platform)
            with self.subTest(platform=platform, missing='recipe platform'), self.assertRaisesRegex(readiness.ReadinessError, 'recipe differs'):
                native.runtime_requirements(changed)
