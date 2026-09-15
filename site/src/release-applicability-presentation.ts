/**
 * release-applicability-presentation.ts — pure presentation decisions for release evidence.
 */

export interface ProofApplicabilityInput {
  applicable: boolean;
  publishedSource: { matchesReplay: boolean };
  currentSource: { matchesReplay: boolean };
}

export interface ProofApplicabilityPresentation {
  isMismatch: boolean;
  message: string;
}

export function presentProofApplicability(
  proof: ProofApplicabilityInput,
): ProofApplicabilityPresentation {
  const publishedMatchesReplay = proof.publishedSource.matchesReplay;
  const currentMatchesReplay = proof.currentSource.matchesReplay;
  if (proof.applicable !== (publishedMatchesReplay && currentMatchesReplay)) {
    throw new Error("Generated proof applicability is internally inconsistent");
  }

  if (proof.applicable) {
    return {
      isMismatch: false,
      message: "Replay source applies to the exact latest published ca artifact",
    };
  }

  return {
    isMismatch: true,
    message: publishedMatchesReplay
      ? "Replay source matches the exact latest published ca artifact, but differs from the current hook source"
      : "Digest mismatch: the exact latest published ca artifact does not match the replay source",
  };
}
