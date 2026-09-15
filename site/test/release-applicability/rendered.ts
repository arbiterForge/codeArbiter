/**
 * rendered.ts — behavior checks against Astro's built release-applicability surfaces.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { presentProofApplicability } from "../../src/release-applicability-presentation";

interface HostRelease {
  target: string;
  version: string;
  tag: string;
  publicationCommit: string;
}

interface ApplicabilityRecord {
  build: { commit: string };
  hosts: HostRelease[];
  proof: {
    applicable: boolean;
    publishedSource: { matchesReplay: boolean };
    currentSource: { matchesReplay: boolean };
  };
}

const siteRoot = fileURLToPath(new URL("../..", import.meta.url));
const generated = JSON.parse(
  readFileSync(join(siteRoot, "src/generated/release-applicability.json"), "utf8"),
) as ApplicabilityRecord;
const compatibilityHtml = readFileSync(
  join(siteRoot, "dist/getting-started/compatibility/index.html"),
  "utf8",
);
const homeHtml = readFileSync(join(siteRoot, "dist/index.html"), "utf8");

function requireBuiltValue(value: string, description: string): void {
  if (!compatibilityHtml.includes(value)) {
    throw new Error(`Built Compatibility output is missing ${description}: ${value}`);
  }
}

requireBuiltValue(
  "Published governance host releases described by this documentation",
  "the release table caption",
);
for (const host of generated.hosts) {
  requireBuiltValue(`>${host.target}</code>`, `${host.target}'s visible target row`);
  requireBuiltValue(`>${host.version}</td>`, `${host.target}'s exact visible version`);
  requireBuiltValue(
    `aria-label="${host.target} ${host.version} tag ${host.tag} publication commit ${host.publicationCommit}"`,
    `${host.target}'s full accessible release identity`,
  );
  requireBuiltValue(
    `href="https://github.com/arbiterForge/codeArbiter/releases/tag/${encodeURIComponent(host.tag)}"`,
    `${host.target}'s exact release link`,
  );
  requireBuiltValue(`>${host.tag}</code>`, `${host.target}'s exact visible tag`);
  requireBuiltValue(
    `href="https://github.com/arbiterForge/codeArbiter/commit/${host.publicationCommit}"`,
    `${host.target}'s full publication-commit link`,
  );
}

requireBuiltValue(
  `aria-label="View full documentation build commit ${generated.build.commit}"`,
  "the full accessible documentation-build identity",
);
requireBuiltValue(
  `href="https://github.com/arbiterForge/codeArbiter/commit/${generated.build.commit}"`,
  "the exact documentation-build link",
);
requireBuiltValue("release-and-build-identity", "the evidence boundary");
requireBuiltValue(
  "does not certify runtime compatibility, installation success, or universal host support",
  "the non-certification boundary",
);
requireBuiltValue('href="/release-applicability.json"', "the machine-readable record link");

const builtEndpoint = JSON.parse(
  readFileSync(join(siteRoot, "dist/release-applicability.json"), "utf8"),
);
if (JSON.stringify(builtEndpoint) !== JSON.stringify(generated)) {
  throw new Error("Built /release-applicability.json differs from the generated canonical record");
}

const publishedCa = generated.hosts.find((host) => host.target === "ca");
if (!publishedCa) {
  throw new Error("Generated release applicability is missing the ca host row");
}
const proofPresentation = presentProofApplicability(generated.proof);
const expectedApplicableMessage = "Replay source applies to the exact latest published ca artifact";
if (proofPresentation.message !== expectedApplicableMessage) {
  throw new Error(`Unexpected proof applicability message: ${proofPresentation.message}`);
}
for (const [value, description] of [
  [expectedApplicableMessage, "the exact HookProof applicability message"],
  [`href="https://github.com/arbiterForge/codeArbiter/releases/tag/${encodeURIComponent(publishedCa.tag)}"`, "the exact published ca release link"],
  [`>${publishedCa.tag}</code>`, "the exact visible published ca tag"],
  [`href="https://github.com/arbiterForge/codeArbiter/commit/${publishedCa.publicationCommit}"`, "the full ca publication-commit link"],
  [`aria-label="View full ca publication commit ${publishedCa.publicationCommit}"`, "the full accessible ca publication-commit identity"],
  ['href="/release-applicability.json"', "the complete applicability-record link"],
  ["It does not prove a host discovered or registered that hook.", "the HookProof evidence boundary"],
] as const) {
  if (!homeHtml.includes(value)) {
    throw new Error(`Built homepage is missing ${description}: ${value}`);
  }
}

process.stdout.write("rendered release applicability: OK\n");
