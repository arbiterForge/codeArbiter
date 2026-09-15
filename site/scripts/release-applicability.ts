/** release-applicability.ts — codeArbiter's release applicability derivation. */

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { lstatSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

const GOVERNANCE_TARGETS = ["ca", "ca-codex", "ca-pi"] as const;
const DECLARED_TARGETS = new Set([...GOVERNANCE_TARGETS, "ca-sandbox"]);
const TARGET_BLOCK = /<!-- release-targets -->([\s\S]*?)<!-- \/release-targets -->/;
const TARGET_HEADER = /^\[([^\]]+)]$/;
const PREFIX = /^(?:v|[a-z][a-z0-9-]*-v)$/;
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const COMMIT_SHA = /^[0-9a-f]{40}$/i;
const NONZERO_LOWER_COMMIT_SHA = /^(?!0{40}$)[0-9a-f]{40}$/;
const DIRECT_HOOK_SOURCE = "plugins/ca/hooks/pre-bash.py";
const DIRECT_HOOK_EVIDENCE_KIND = "direct-hook-invocation-rendered-replay";
const ORIGINAL_LEDGER_PATH = ".github/published-tags.json";
const LEDGER_NAMESPACES = ["v*", "ca-sandbox-v*", "ca-codex-v*", "ca-pi-v*"] as const;

type GovernanceTarget = (typeof GOVERNANCE_TARGETS)[number];

export interface CurrentGovernanceRelease {
  target: GovernanceTarget;
  version: string;
  tag: string;
  publicationCommit: string;
}

export interface VerifiedGovernanceRelease extends CurrentGovernanceRelease {
  manifestPath: string;
  manifestPaths: string[];
}

export interface ReleaseApplicabilityGit {
  readAtCommit(commit: string, path: string): string;
  head(): string;
  isDirty(): boolean;
}

export interface DocumentationBuildIdentity {
  mode: "github-actions" | "local";
  commit: string;
  dirty: boolean;
}

export interface DirectHookReplayEvidence {
  evidenceKind: typeof DIRECT_HOOK_EVIDENCE_KIND;
  hostDiscoveryProven: false;
  source: string;
  sourceSha256: string;
}

export interface ReleaseApplicabilityRecord {
  schemaVersion: 1;
  evidenceBoundary: {
    claim: "release-and-build-identity";
    doesNotCertify: [
      "runtime compatibility",
      "installation success",
      "universal host certification",
      "host discovery or registration",
    ];
  };
  build: DocumentationBuildIdentity;
  hosts: VerifiedGovernanceRelease[];
  proof: {
    claim: "direct-hook-replay-source-applicability";
    evidenceKind: string;
    hostDiscoveryProven: boolean;
    replayDigest: string;
    applicable: boolean;
    statement: string;
    currentSource: {
      path: string;
      digest: string;
      matchesReplay: boolean;
    };
    publishedSource: {
      path: string;
      publicationCommit: string;
      digest: string;
      matchesReplay: boolean;
    };
  };
  evidenceSources: Array<{
    kind: string;
    path?: string;
    commit?: string;
  }>;
}

export interface CreateReleaseApplicabilityRecordInput {
  build: DocumentationBuildIdentity;
  releases: readonly VerifiedGovernanceRelease[];
  proof: DirectHookReplayEvidence;
  currentHookSource: string | Uint8Array;
  git: ReleaseApplicabilityGit;
}

interface ReleaseTarget {
  prefix: string;
  manifests: string[];
  provenanceManifests: string[];
}

interface Receipt {
  object_sha: string;
  object_type: "tag" | "commit";
  commit_sha: string;
}

interface ParsedVersion {
  major: bigint;
  minor: bigint;
  patch: bigint;
  prerelease?: string;
}

function parseReleaseTargets(markdown: string): Map<string, ReleaseTarget> {
  const block = TARGET_BLOCK.exec(markdown)?.[1];
  if (block === undefined) {
    throw new Error("Release target declarations are missing their bounded block");
  }

  const targets = new Map<string, ReleaseTarget>();
  let currentTarget: string | undefined;
  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;

    const header = TARGET_HEADER.exec(line);
    if (header) {
      currentTarget = header[1];
      if (!DECLARED_TARGETS.has(currentTarget)) {
        throw new Error(`Unsupported release target: ${currentTarget}`);
      }
      if (targets.has(currentTarget)) {
        throw new Error(`Duplicate release target: ${currentTarget}`);
      }
      targets.set(currentTarget, { prefix: "", manifests: [], provenanceManifests: [] });
      continue;
    }

    if (!currentTarget) {
      throw new Error(`Malformed release target line: ${line}`);
    }
    const separator = line.indexOf(":");
    if (separator <= 0 || line.slice(separator + 1).trim() === "") {
      throw new Error(`Malformed release target line: ${line}`);
    }
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (key === "prefix") {
      const target = targets.get(currentTarget)!;
      if (target.prefix !== "") {
        throw new Error(`Duplicate prefix for release target: ${currentTarget}`);
      }
      target.prefix = value;
    } else if (key === "manifest") {
      const target = targets.get(currentTarget)!;
      if (target.manifests.includes(value)) {
        throw new Error(`Duplicate manifest for release target: ${currentTarget}`);
      }
      target.manifests.push(value);
    } else if (key === "provenance-manifest") {
      targets.get(currentTarget)!.provenanceManifests.push(value);
    }
  }

  for (const targetName of GOVERNANCE_TARGETS) {
    const target = targets.get(targetName);
    if (!target) throw new Error(`Missing release target: ${targetName}`);
    if (!PREFIX.test(target.prefix)) {
      throw new Error(`Malformed prefix for release target ${targetName}: ${target.prefix}`);
    }
    if (target.manifests.length === 0) {
      throw new Error(`Missing manifest for release target: ${targetName}`);
    }
    if (target.provenanceManifests.length !== 1) {
      throw new Error(
        `Release target ${targetName} must declare exactly one provenance-manifest`,
      );
    }
    if (target.provenanceManifests[0] !== ORIGINAL_LEDGER_PATH) {
      throw new Error(
        `Release target ${targetName} provenance-manifest must be ${ORIGINAL_LEDGER_PATH}`,
      );
    }
  }
  return targets;
}

function parseJsonWithUniqueKeys(json: string): unknown {
  let position = 0;
  const whitespace = /\s/;

  function skipWhitespace() {
    while (position < json.length && whitespace.test(json[position])) position += 1;
  }

  function parseStringToken(): string {
    if (json[position] !== '"') throw new Error("expected JSON string");
    const start = position;
    position += 1;
    let escaped = false;
    while (position < json.length) {
      const character = json[position++];
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === '"') {
        return JSON.parse(json.slice(start, position)) as string;
      }
    }
    throw new Error("unterminated JSON string");
  }

  function parseValue(): void {
    skipWhitespace();
    if (json[position] === "{") {
      position += 1;
      const keys = new Set<string>();
      skipWhitespace();
      if (json[position] === "}") {
        position += 1;
        return;
      }
      while (position < json.length) {
        skipWhitespace();
        const key = parseStringToken();
        if (keys.has(key)) throw new Error(`duplicate JSON key: ${key}`);
        keys.add(key);
        skipWhitespace();
        if (json[position++] !== ":") throw new Error("expected JSON object separator");
        parseValue();
        skipWhitespace();
        const delimiter = json[position++];
        if (delimiter === "}") return;
        if (delimiter !== ",") throw new Error("expected JSON object delimiter");
      }
      throw new Error("unterminated JSON object");
    }
    if (json[position] === "[") {
      position += 1;
      skipWhitespace();
      if (json[position] === "]") {
        position += 1;
        return;
      }
      while (position < json.length) {
        parseValue();
        skipWhitespace();
        const delimiter = json[position++];
        if (delimiter === "]") return;
        if (delimiter !== ",") throw new Error("expected JSON array delimiter");
      }
      throw new Error("unterminated JSON array");
    }
    if (json[position] === '"') {
      parseStringToken();
      return;
    }
    const primitive = /(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/y;
    primitive.lastIndex = position;
    const match = primitive.exec(json);
    if (!match) throw new Error("invalid JSON value");
    position = primitive.lastIndex;
  }

  parseValue();
  skipWhitespace();
  if (position !== json.length) throw new Error("trailing JSON content");
  return JSON.parse(json) as unknown;
}

function parseLedger(json: string): Record<string, Receipt> {
  let parsed: unknown;
  try {
    parsed = parseJsonWithUniqueKeys(json);
  } catch (error) {
    const detail = error instanceof Error && /duplicate JSON key/i.test(error.message)
      ? `: ${error.message}`
      : "";
    throw new Error(`Published tag ledger is not valid JSON${detail}`);
  }
  if (!isRecord(parsed) || !hasExactKeys(parsed, ["$comment", "namespaces", "verified_at", "tags"])) {
    throw new Error("Published tag ledger has an invalid top-level schema");
  }
  if (
    !Array.isArray(parsed.$comment)
    || !parsed.$comment.every((line) => typeof line === "string")
    || !Array.isArray(parsed.namespaces)
    || parsed.namespaces.length !== LEDGER_NAMESPACES.length
    || !parsed.namespaces.every((value, index) => value === LEDGER_NAMESPACES[index])
    || typeof parsed.verified_at !== "string"
    || !/^\d{4}-\d{2}-\d{2}$/.test(parsed.verified_at)
    || !isRecord(parsed.tags)
  ) {
    throw new Error("Published tag ledger has invalid metadata");
  }

  const receipts: Record<string, Receipt> = {};
  for (const [tag, receipt] of Object.entries(parsed.tags)) {
    const prefix = LEDGER_NAMESPACES.map((namespace) => namespace.slice(0, -1))
      .find((candidate) => tag.startsWith(candidate));
    const version = prefix === undefined ? "" : tag.slice(prefix.length);
    if (prefix === undefined || !parseVersion(version)) {
      throw new Error(`Published tag ledger has an invalid governed tag: ${tag}`);
    }
    if (!isRecord(receipt) || !hasExactKeys(receipt, ["object_sha", "object_type", "commit_sha"])) {
      throw new Error(`Published tag ledger has a malformed receipt for ${tag}`);
    }
    const objectSha = receipt.object_sha;
    const commitSha = receipt.commit_sha;
    const objectType = receipt.object_type;
    if (
      typeof objectSha !== "string"
      || !NONZERO_LOWER_COMMIT_SHA.test(objectSha)
      || typeof commitSha !== "string"
      || !NONZERO_LOWER_COMMIT_SHA.test(commitSha)
      || (objectType !== "tag" && objectType !== "commit")
      || (objectType === "commit" && objectSha !== commitSha)
    ) {
      throw new Error(
        `Published tag ledger receipt for ${tag} has an invalid identity; `
        + "object and commit SHA values must be nonzero lowercase 40-hex identities",
      );
    }
    receipts[tag] = { object_sha: objectSha, object_type: objectType, commit_sha: commitSha };
  }
  return receipts;
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === [...expected].sort()[index]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha256(bytes: string | Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function parseVersion(version: string): ParsedVersion | undefined {
  const match = SEMVER.exec(version);
  if (!match) return undefined;
  if (match[4]?.split(".").some(
    (identifier) => /^\d+$/.test(identifier) && identifier.length > 1 && identifier.startsWith("0"),
  )) return undefined;
  return {
    major: BigInt(match[1]),
    minor: BigInt(match[2]),
    patch: BigInt(match[3]),
    prerelease: match[4],
  };
}

function compareVersions(left: ParsedVersion, right: ParsedVersion): number {
  for (const key of ["major", "minor", "patch"] as const) {
    if (left[key] < right[key]) return -1;
    if (left[key] > right[key]) return 1;
  }
  return 0;
}

export function selectCurrentGovernanceReleases(
  releaseTargetsMarkdown: string,
  publishedTagsJson: string,
): CurrentGovernanceRelease[] {
  const targets = parseReleaseTargets(releaseTargetsMarkdown);
  const receipts = parseLedger(publishedTagsJson);

  return GOVERNANCE_TARGETS.map((targetName) => {
    const prefix = targets.get(targetName)!.prefix;
    let selected:
      | { tag: string; version: string; parsed: ParsedVersion; receipt: Receipt }
      | undefined;
    let matchingReceiptCount = 0;

    for (const [tag, receipt] of Object.entries(receipts)) {
      if (!tag.startsWith(prefix)) continue;
      matchingReceiptCount += 1;
      const version = tag.slice(prefix.length);
      const parsed = parseVersion(version);
      if (!parsed) throw new Error(`Malformed release tag for ${targetName}: ${tag}`);
      if (parsed.prerelease !== undefined) continue;
      if (!selected || compareVersions(parsed, selected.parsed) > 0) {
        selected = { tag, version, parsed, receipt };
      }
    }

    if (!selected) {
      const reason = matchingReceiptCount === 0 ? "No receipts exist" : "No stable receipt exists";
      throw new Error(`${reason} for release target ${targetName}`);
    }
    return {
      target: targetName,
      version: selected.version,
      tag: selected.tag,
      publicationCommit: selected.receipt.commit_sha,
    };
  });
}

export function deriveVerifiedGovernanceReleases(
  releaseTargetsMarkdown: string,
  publishedTagsJson: string,
  git: ReleaseApplicabilityGit,
): VerifiedGovernanceRelease[] {
  const targets = parseReleaseTargets(releaseTargetsMarkdown);
  const selected = selectCurrentGovernanceReleases(releaseTargetsMarkdown, publishedTagsJson);

  return selected.map((release) => {
    if (!COMMIT_SHA.test(release.publicationCommit)) {
      throw new Error(
        `Publication commit for ${release.tag} must be an exact 40-hex Git commit SHA`,
      );
    }
    const publicationCommit = release.publicationCommit.toLowerCase();
    const manifestPaths = targets.get(release.target)!.manifests;
    for (const manifestPath of manifestPaths) {
      let rawManifest: string;
      try {
        rawManifest = git.readAtCommit(publicationCommit, manifestPath);
      } catch {
        throw new Error(
          `Cannot read historical manifest for ${release.tag} at ${manifestPath} from ${publicationCommit}`,
        );
      }

      let manifest: unknown;
      try {
        manifest = JSON.parse(rawManifest);
      } catch {
        throw new Error(`Historical manifest for ${release.tag} at ${manifestPath} is not valid JSON`);
      }
      if (!isRecord(manifest) || typeof manifest.version !== "string") {
        throw new Error(`Historical manifest for ${release.tag} at ${manifestPath} has no version`);
      }
      if (manifest.version !== release.version) {
        throw new Error(
          `Release tag ${release.tag} does not match historical manifest version ${manifest.version}`,
        );
      }
    }

    return {
      ...release,
      publicationCommit,
      manifestPath: manifestPaths[0],
      manifestPaths: [...manifestPaths],
    };
  });
}

export function resolveDocumentationBuildIdentity(
  git: ReleaseApplicabilityGit,
  environment: Readonly<Record<string, string | undefined>>,
): DocumentationBuildIdentity {
  const rawHead = git.head();
  if (!COMMIT_SHA.test(rawHead)) {
    throw new Error("Git HEAD must resolve to an exact 40-hex commit SHA");
  }
  const commit = rawHead.toLowerCase();

  if (environment.GITHUB_ACTIONS === "true") {
    const githubSha = environment.GITHUB_SHA;
    if (!githubSha || !COMMIT_SHA.test(githubSha)) {
      throw new Error("GITHUB_SHA must be an exact 40-hex commit SHA in GitHub Actions");
    }
    if (githubSha.toLowerCase() !== commit) {
      throw new Error(`GITHUB_SHA ${githubSha} does not equal checked-out HEAD ${commit}`);
    }
    return { mode: "github-actions", commit, dirty: false };
  }

  return { mode: "local", commit, dirty: git.isDirty() };
}

export function createReleaseApplicabilityRecord({
  build,
  releases,
  proof,
  currentHookSource,
  git,
}: CreateReleaseApplicabilityRecordInput): ReleaseApplicabilityRecord {
  if (proof.evidenceKind !== DIRECT_HOOK_EVIDENCE_KIND) {
    throw new Error(`Direct-hook replay evidenceKind must be ${DIRECT_HOOK_EVIDENCE_KIND}`);
  }
  if (proof.hostDiscoveryProven !== false) {
    throw new Error("Direct-hook replay cannot claim host discovery proof");
  }
  if (!/^[0-9a-f]{64}$/i.test(proof.sourceSha256)) {
    throw new Error("Direct-hook replay sourceSha256 must be an exact 64-hex SHA-256 digest");
  }
  if (proof.source !== DIRECT_HOOK_SOURCE) {
    throw new Error(`Direct-hook replay source must be ${DIRECT_HOOK_SOURCE}`);
  }

  const byTarget = new Map<GovernanceTarget, VerifiedGovernanceRelease>();
  for (const release of releases) {
    if (byTarget.has(release.target)) {
      throw new Error(`Duplicate verified release row for ${release.target}`);
    }
    byTarget.set(release.target, release);
  }
  const hosts = GOVERNANCE_TARGETS.map((target) => {
    const release = byTarget.get(target);
    if (!release) throw new Error(`Missing verified release row for ${target}`);
    return {
      target: release.target,
      version: release.version,
      tag: release.tag,
      publicationCommit: release.publicationCommit,
      manifestPath: release.manifestPath,
      manifestPaths: [...release.manifestPaths],
    };
  });
  if (byTarget.size !== GOVERNANCE_TARGETS.length) {
    throw new Error("Applicability record contains an unsupported verified release row");
  }

  const publishedCa = hosts[0];
  let publishedHookSource: string;
  try {
    publishedHookSource = git.readAtCommit(publishedCa.publicationCommit, proof.source);
  } catch {
    throw new Error(
      `Cannot read published hook source ${proof.source} from ${publishedCa.publicationCommit}`,
    );
  }

  const replayDigest = proof.sourceSha256.toLowerCase();
  const currentDigest = sha256(currentHookSource);
  const publishedDigest = sha256(publishedHookSource);
  const currentMatches = currentDigest === replayDigest;
  const publishedMatches = publishedDigest === replayDigest;
  const applicable = currentMatches && publishedMatches;
  const statement = applicable
    ? "Replay digest applies to both the current hook source and the exact latest published ca artifact source."
    : `Replay digest mismatch: current hook source ${currentMatches ? "matches" : "does not match"}; `
      + `latest published ca artifact source ${publishedMatches ? "matches" : "does not match"}.`;

  return {
    schemaVersion: 1,
    evidenceBoundary: {
      claim: "release-and-build-identity",
      doesNotCertify: [
        "runtime compatibility",
        "installation success",
        "universal host certification",
        "host discovery or registration",
      ],
    },
    build: {
      mode: build.mode,
      commit: build.commit,
      dirty: build.dirty,
    },
    hosts,
    proof: {
      claim: "direct-hook-replay-source-applicability",
      evidenceKind: proof.evidenceKind,
      hostDiscoveryProven: proof.hostDiscoveryProven,
      replayDigest,
      applicable,
      statement,
      currentSource: {
        path: proof.source,
        digest: currentDigest,
        matchesReplay: currentMatches,
      },
      publishedSource: {
        path: proof.source,
        publicationCommit: publishedCa.publicationCommit,
        digest: publishedDigest,
        matchesReplay: publishedMatches,
      },
    },
    evidenceSources: [
      { kind: "release-declarations", path: ".codearbiter/release-targets.md" },
      { kind: "original-publication-receipts", path: ".github/published-tags.json" },
      ...hosts.flatMap((release) => release.manifestPaths.map((manifestPath) => ({
        kind: "historical-manifest",
        path: manifestPath,
        commit: release.publicationCommit,
      }))),
      { kind: "documentation-build", commit: build.commit },
      { kind: "direct-hook-replay", path: "site/src/assets/proof/hook-proof.json" },
      { kind: "current-hook-source", path: proof.source },
      {
        kind: "published-hook-source",
        path: proof.source,
        commit: publishedCa.publicationCommit,
      },
    ],
  };
}

export function serializeReleaseApplicabilityRecord(record: ReleaseApplicabilityRecord): string {
  return `${JSON.stringify(record, null, 2)}\n`;
}

const GIT_MAX_BUFFER = 4 * 1024 * 1024;

function runGit(repoRoot: string, args: readonly string[]): string {
  return execFileSync("git", [...args], {
    cwd: repoRoot,
    encoding: "utf8",
    maxBuffer: GIT_MAX_BUFFER,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

export type GitCommandRunner = (repoRoot: string, args: readonly string[]) => string;

export function repositoryGit(
  repoRoot: string,
  runner: GitCommandRunner = runGit,
): ReleaseApplicabilityGit {
  return {
    readAtCommit(commit, path) {
      if (!COMMIT_SHA.test(commit)) {
        throw new Error("Historical lookup requires an exact 40-hex Git commit SHA");
      }
      return runner(repoRoot, ["--no-lazy-fetch", "show", `${commit.toLowerCase()}:${path}`]);
    },
    head() {
      return runner(repoRoot, ["rev-parse", "--verify", "HEAD"]).trim();
    },
    isDirty() {
      return runner(repoRoot, ["status", "--porcelain=v1", "--untracked-files=normal"]).length > 0;
    },
  };
}

export function loadDirectHookReplayEvidence(path: string): DirectHookReplayEvidence {
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    throw new Error(`Direct-hook replay evidence is missing or invalid JSON: ${path}`);
  }
  if (
    !isRecord(parsed)
    || parsed.schema !== 1
    || parsed.evidenceKind !== DIRECT_HOOK_EVIDENCE_KIND
    || parsed.hostDiscoveryProven !== false
    || typeof parsed.source !== "string"
    || parsed.source === ""
    || typeof parsed.sourceSha256 !== "string"
  ) {
    throw new Error(`Direct-hook replay evidence is malformed: ${path}`);
  }
  return {
    evidenceKind: DIRECT_HOOK_EVIDENCE_KIND,
    hostDiscoveryProven: false,
    source: parsed.source,
    sourceSha256: parsed.sourceSha256,
  };
}

export function resolveHookSourcePath(repoRoot: string, source: string): string {
  const segments = source.split("/");
  if (
    source !== DIRECT_HOOK_SOURCE
    || source.includes("\\")
    || isAbsolute(source)
    || segments.some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new Error(
      `Direct-hook source path must be the canonical repository path ${DIRECT_HOOK_SOURCE}`,
    );
  }

  let canonicalRoot: string;
  try {
    canonicalRoot = realpathSync(resolve(repoRoot));
  } catch {
    throw new Error("Direct-hook source repository root is unavailable");
  }
  const resolvedSource = resolve(canonicalRoot, ...segments);
  let cursor = canonicalRoot;
  try {
    for (const segment of segments) {
      cursor = join(cursor, segment);
      if (lstatSync(cursor).isSymbolicLink()) {
        throw new Error("symbolic link");
      }
    }
    if (!lstatSync(resolvedSource).isFile()) {
      throw new Error("not a regular file");
    }
  } catch {
    throw new Error("Direct-hook source must resolve through regular files without symbolic links");
  }
  const realSource = realpathSync(resolvedSource);
  const confined = relative(canonicalRoot, realSource);
  if (confined === ".." || confined.startsWith(`..${sep}`) || isAbsolute(confined)) {
    throw new Error("Direct-hook source path must remain confined to the repository root");
  }
  return realSource;
}

export function generateReleaseApplicability(
  repoRoot: string,
  outputPath: string,
  environment: Readonly<Record<string, string | undefined>> = process.env,
): ReleaseApplicabilityRecord {
  const releaseTargetsPath = join(repoRoot, ".codearbiter", "release-targets.md");
  const publishedTagsPath = join(repoRoot, ".github", "published-tags.json");
  const proofPath = join(repoRoot, "site", "src", "assets", "proof", "hook-proof.json");
  const releaseTargetsMarkdown = readFileSync(releaseTargetsPath, "utf8");
  const publishedTagsJson = readFileSync(publishedTagsPath, "utf8");
  const proof = loadDirectHookReplayEvidence(proofPath);
  const currentHookPath = resolveHookSourcePath(repoRoot, proof.source);
  const git = repositoryGit(repoRoot);
  const releases = deriveVerifiedGovernanceReleases(
    releaseTargetsMarkdown,
    publishedTagsJson,
    git,
  );
  const build = resolveDocumentationBuildIdentity(git, environment);
  const currentHookSource = readFileSync(currentHookPath);
  const record = createReleaseApplicabilityRecord({
    build,
    releases,
    proof,
    currentHookSource,
    git,
  });

  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, serializeReleaseApplicabilityRecord(record), "utf8");
  return record;
}
