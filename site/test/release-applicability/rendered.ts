/**
 * rendered.ts — behavior checks against Astro's built release-applicability surfaces.
 */

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { presentProofApplicability } from "../../src/release-applicability-presentation";
import { repositoryVersionFacts } from "../../scripts/version-facts";

interface HostRelease {
  target: string;
  version: string;
  tag: string;
  publicationCommit: string;
  originalPublicationReceipt: "recorded" | "not-recorded";
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

const compatibilityText = compatibilityHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
for (const boundary of ["Python hook core", "installation-pinned", "ca-artifact", "native-platform qualification", "binary digest"]) {
  if (!compatibilityText.includes(boundary)) {
    throw new Error(`Built Compatibility output is missing the runtime boundary: ${boundary}`);
  }
}
if (compatibilityText.includes("no compiled binaries") || compatibilityText.includes("Zero, for the plugin itself")) {
  throw new Error("Built Compatibility output still denies the packaged native runtime");
}
const farmRow = compatibilityHtml.match(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)
  ?.find((row) => row.match(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/)?.[1]
    .replace(/<[^>]+>/g, " ").trim() === "/ca:sprint --farm");
const codexFarmCell = farmRow?.match(/<t[dh]\b[^>]*>[\s\S]*?<\/t[dh]>/g)?.[2]
  .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
for (const boundary of [
  "backend is not packaged",
  "Reports the unavailable backend",
  "no silent provider/model switch",
  "another backend only within existing authorization",
]) {
  if (!codexFarmCell?.includes(boundary)) {
    throw new Error(`Built Compatibility output is missing the Codex farm boundary: ${boundary}`);
  }
}
if (/premium-subagent path|falls back|degraded/i.test(codexFarmCell!)) {
  throw new Error("Built Compatibility output still promises an automatic Codex farm fallback");
}

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

// Receipt status is its own column, never folded into the selected tag.
requireBuiltValue("Original-publication receipt", "the receipt-status column");
const receiptCells = [...compatibilityHtml.matchAll(/<td\b[^>]*>(Recorded|Not yet reconciled)<\/td>/g)]
  .map((match) => match[1]);
const expectedReceiptCells = generated.hosts.map((host) =>
  host.originalPublicationReceipt === "recorded" ? "Recorded" : "Not yet reconciled");
if (JSON.stringify(receiptCells) !== JSON.stringify(expectedReceiptCells)) {
  throw new Error(
    `Built receipt-status cells ${JSON.stringify(receiptCells)} differ from the record ${JSON.stringify(expectedReceiptCells)}`,
  );
}

// Version fact tokens must never reach readers, including through frontmatter or curated text.
function builtHtml(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return builtHtml(path);
    return entry.name.endsWith(".html") ? [path] : [];
  });
}
const pages = builtHtml(join(siteRoot, "dist"));
if (pages.length < 50) throw new Error(`Expected the built site, found ${pages.length} HTML pages`);
const leaked = pages.filter((path) => readFileSync(path, "utf8").includes("%%fact="));
if (leaked.length > 0) {
  throw new Error(`Unresolved version fact tokens in built pages: ${leaked.join(", ")}`);
}
const facts = repositoryVersionFacts();
for (const [name, page] of [
  ["pi.supported", "getting-started/pi"],
  ["codex.minimum", "getting-started/compatibility"],
  ["git.adrMinimum", "getting-started/compatibility"],
  ["release.ca-pi", "getting-started/pi"],
  ["release.ca", "reference/commands/doctor"],
] as const) {
  const html = readFileSync(join(siteRoot, "dist", page, "index.html"), "utf8");
  if (!html.includes(facts[name].value)) {
    throw new Error(`Built ${page} is missing version fact ${name}: ${facts[name].value}`);
  }
}

process.stdout.write("rendered release applicability: OK\n");
