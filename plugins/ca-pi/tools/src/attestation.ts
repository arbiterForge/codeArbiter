/** attestation.ts - digest-only binding for one isolated Pi child launch. */
import { createHash } from "node:crypto";

const CHILD_ATTESTATION_DOMAIN = "ca-pi-child-attestation-v1";
export const CHILD_ATTESTATION_TITLE = "codeArbiter isolated child readiness";
export const CHILD_ATTESTATION_TIMEOUT_MS = 5_000;

export interface ChildAttestationInput {
  nonce: string;
  challenge: string;
  cwd: string;
  provider: string;
  model: string;
  tools: readonly string[];
  projectTrusted: false;
  mode: "rpc";
}

export function childAttestationDigest(input: ChildAttestationInput): string {
  return createHash("sha256").update(JSON.stringify([
    CHILD_ATTESTATION_DOMAIN,
    input.nonce,
    input.challenge,
    input.cwd,
    input.provider,
    input.model,
    [...input.tools].sort(),
    input.projectTrusted,
    input.mode,
  ]), "utf8").digest("hex");
}
