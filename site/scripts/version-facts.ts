/** version-facts.ts — current-state version facts read from the source that enforces them.
 *
 * Hand-authored pages and curated reference text must not type a current
 * version requirement by hand: the number drifts the moment the owning code
 * changes. Instead they write `%%fact=<name>%%`, and the remark plugin below
 * replaces it at build time with the value extracted here.
 *
 * Every extractor demands exactly one match in its owning source and throws
 * otherwise, so a refactor that moves or duplicates a declaration fails the
 * build instead of silently publishing a stale number. An unknown or malformed
 * token also throws; a token never reaches readers as literal text.
 *
 * test/content/version-literal-drift.test.ts is the matching gate: it rejects a
 * version literal in hand-authored site content unless it is a token or an
 * allowlisted historical, illustrative, or external reference.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SEMVER = /^\d+\.\d+\.\d+$/;
const TOKEN = /%%fact=([a-zA-Z][\w.-]*)%%/g;
// Any remnant, including a token a markdown extension split apart, is an error.
const RESIDUE = /%%fact/;

/** One fact and the repository-relative file that owns it. */
export interface VersionFact {
  value: string;
  source: string;
}

export type VersionFacts = Readonly<Record<string, VersionFact>>;

/** Reads a repository-relative path; injectable so extractors can be tested against fixtures. */
export type SourceReader = (path: string) => string;

/** Every repository file a fact is read from; docs.yml must rebuild when any of them changes. */
export const SOURCES = {
  piCompatibility: "plugins/ca-pi/tools/src/compatibility.ts",
  piPackage: "plugins/ca-pi/package.json",
  codexManifest: "plugins/ca-codex/.codex-plugin/plugin.json",
  codexBaseline: ".github/scripts/validate_codex_plugin.py",
  ciWorkflow: ".github/workflows/ci.yml",
  gitPrerequisite: "plugins/ca/hooks/_adrlifecyclegit.py",
  reviewDecision: "plugins/ca/hooks/_artifactauthoritylib.py",
  receiptSchema: "core/artifacts/internal/authority/receipt.go",
  caManifest: "plugins/ca/.claude-plugin/plugin.json",
  releaseRecord: "site/src/generated/release-applicability.json",
} as const;

function exactlyOne(text: string, pattern: RegExp, what: string, source: string): RegExpExecArray {
  const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
  const matches = [...text.matchAll(global)];
  if (matches.length !== 1) {
    throw new Error(
      `Version fact ${what}: expected exactly one declaration in ${source}, found ${matches.length}`,
    );
  }
  return matches[0] as RegExpExecArray;
}

function semver(value: string, what: string, source: string): string {
  if (!SEMVER.test(value)) {
    throw new Error(`Version fact ${what}: ${JSON.stringify(value)} in ${source} is not an exact X.Y.Z version`);
  }
  return value;
}

function compareSemver(left: string, right: string): number {
  const a = left.split(".").map(Number);
  const b = right.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return 0;
}

function quotedList(raw: string, what: string, source: string): string[] {
  const items = raw.split(",").map((item) => item.trim()).filter((item) => item !== "");
  const versions = items.map((item) => {
    const quoted = /^["']([^"']+)["']$/.exec(item);
    if (!quoted) throw new Error(`Version fact ${what}: unparseable list entry ${item} in ${source}`);
    return semver(quoted[1], what, source);
  });
  if (versions.length === 0) throw new Error(`Version fact ${what}: empty version list in ${source}`);
  return versions.sort(compareSemver);
}

function manifestVersion(read: SourceReader, source: string, what: string): string {
  const manifest = JSON.parse(read(source)) as { version?: unknown };
  if (typeof manifest.version !== "string") throw new Error(`Version fact ${what}: ${source} has no version`);
  return semver(manifest.version, what, source);
}

/** Extract every published fact from its owning source. */
export function loadVersionFacts(read: SourceReader): VersionFacts {
  const facts: Record<string, VersionFact> = {};
  const add = (name: string, value: string, source: string) => {
    facts[name] = { value, source };
  };

  const piSource = read(SOURCES.piCompatibility);
  const piSet = exactlyOne(piSource, /const SUPPORTED_PI_VERSIONS = new Set\(\[([^\]]*)\]\)/, "pi.supported", SOURCES.piCompatibility);
  add("pi.supported", quotedList(piSet[1], "pi.supported", SOURCES.piCompatibility).join(" or "), SOURCES.piCompatibility);

  const piPackage = JSON.parse(read(SOURCES.piPackage)) as { engines?: { node?: unknown } };
  const nodeRange = piPackage.engines?.node;
  const nodeMinimum = typeof nodeRange === "string" ? /^>=(\d+\.\d+\.\d+)$/.exec(nodeRange) : null;
  if (!nodeMinimum) {
    throw new Error(`Version fact node.minimum: ${SOURCES.piPackage} engines.node must be ">=X.Y.Z"`);
  }
  add("node.minimum", nodeMinimum[1], SOURCES.piPackage);

  const ciSource = read(SOURCES.ciWorkflow);
  const ciMatrix = exactlyOne(ciSource, /^\s*codex-version: \[([^\]]*)\]\s*$/m, "codex.ci", SOURCES.ciWorkflow);
  const ciVersions = quotedList(ciMatrix[1], "codex.ci", SOURCES.ciWorkflow);
  add("codex.ci", ciVersions.join(" and "), SOURCES.ciWorkflow);

  const codexManifest = JSON.parse(read(SOURCES.codexManifest)) as { description?: unknown };
  const description = typeof codexManifest.description === "string" ? codexManifest.description : "";
  const codexMinimum = semver(
    exactlyOne(description, /Codex >= (\d+\.\d+\.\d+)\./, "codex.minimum", SOURCES.codexManifest)[1],
    "codex.minimum",
    SOURCES.codexManifest,
  );
  if (codexMinimum !== ciVersions[0]) {
    throw new Error(
      `Version fact codex.minimum: ${SOURCES.codexManifest} declares Codex >= ${codexMinimum} `
      + `but the lowest CI-verified version in ${SOURCES.ciWorkflow} is ${ciVersions[0]}`,
    );
  }
  add("codex.minimum", codexMinimum, SOURCES.codexManifest);

  const baseline = exactlyOne(read(SOURCES.codexBaseline), /^BASELINE = "([^"]+)"$/m, "codex.schemaBaseline", SOURCES.codexBaseline);
  add("codex.schemaBaseline", semver(baseline[1], "codex.schemaBaseline", SOURCES.codexBaseline), SOURCES.codexBaseline);

  const gitMinimum = exactlyOne(
    read(SOURCES.gitPrerequisite),
    /requires Git (\d+\.\d+\.\d+)\+ with --no-lazy-fetch/,
    "git.adrMinimum",
    SOURCES.gitPrerequisite,
  );
  add("git.adrMinimum", semver(gitMinimum[1], "git.adrMinimum", SOURCES.gitPrerequisite), SOURCES.gitPrerequisite);

  const decision = exactlyOne(
    read(SOURCES.reviewDecision),
    /^DECISION_FORMAT = "(codearbiter\.review-decision\/\d+\.\d+\.\d+)"$/m,
    "reviewDecision.format",
    SOURCES.reviewDecision,
  );
  add("reviewDecision.format", decision[1], SOURCES.reviewDecision);

  const receiptSource = read(SOURCES.receiptSchema);
  const currentReceipt = exactlyOne(
    receiptSource,
    /^func ReceiptSchema\(\)[^\n]*\n[^\n]*?"const": "(codearbiter\.receipt\/\d+\.\d+\.\d+)"/m,
    "receipt.current",
    SOURCES.receiptSchema,
  );
  const legacyReceipt = exactlyOne(
    receiptSource,
    /^func legacyReceiptSchema\(\)[^\n]*\n[^\n]*?"const": "(codearbiter\.receipt\/\d+\.\d+\.\d+)"/m,
    "receipt.legacy",
    SOURCES.receiptSchema,
  );
  add("receipt.current", currentReceipt[1], SOURCES.receiptSchema);
  add("receipt.legacy", legacyReceipt[1], SOURCES.receiptSchema);

  add("ca.version", manifestVersion(read, SOURCES.caManifest, "ca.version"), SOURCES.caManifest);

  // Latest published releases come from the generated release-applicability
  // record (highest stable release tag per host). `npm run gen` writes it before
  // any build; before generation it is absent, and a `release.*` token then
  // fails as unknown. A present but unreadable record is an error, never absent.
  let record: string | undefined;
  try {
    record = read(SOURCES.releaseRecord);
  } catch (error) {
    if (!(error && typeof error === "object" && "code" in error && error.code === "ENOENT")) throw error;
  }
  if (record !== undefined) {
    const parsed = JSON.parse(record) as { hosts?: Array<{ target?: unknown; version?: unknown }> };
    if (!Array.isArray(parsed.hosts)) {
      throw new Error(`Version fact release.*: ${SOURCES.releaseRecord} has no hosts array`);
    }
    for (const host of parsed.hosts) {
      if (typeof host.target !== "string" || typeof host.version !== "string") {
        throw new Error(`Version fact release.*: ${SOURCES.releaseRecord} has a malformed host row`);
      }
      add(`release.${host.target}`, semver(host.version, `release.${host.target}`, SOURCES.releaseRecord), SOURCES.releaseRecord);
    }
  }

  return facts;
}

/**
 * The repository root, found by walking up from this module. Astro bundles
 * importers of this file into `site/dist/.prerender/chunks/`, so a fixed
 * relative hop would land inside the build output instead of the checkout.
 */
function findRepositoryRoot(): string {
  let directory = dirname(fileURLToPath(import.meta.url));
  for (;;) {
    if (existsSync(join(directory, ".codearbiter", "release-targets.md")) && existsSync(join(directory, "site", "package.json"))) {
      return directory;
    }
    const parent = dirname(directory);
    if (parent === directory) throw new Error("Version facts: cannot locate the codeArbiter repository root");
    directory = parent;
  }
}

let cachedRepositoryFacts: VersionFacts | undefined;

/** Facts for this checkout, read once per process. */
export function repositoryVersionFacts(): VersionFacts {
  if (!cachedRepositoryFacts) {
    const root = findRepositoryRoot();
    cachedRepositoryFacts = loadVersionFacts((path) => readFileSync(join(root, path), "utf8"));
  }
  return cachedRepositoryFacts;
}

/** Replace every `%%fact=<name>%%` token; throw on an unknown name or malformed residue. */
export function resolveFactTokens(text: string, facts: VersionFacts, where: string): string {
  const resolved = text.replace(TOKEN, (_token, name: string) => {
    const fact = facts[name];
    if (!fact) throw new Error(`Unknown version fact "${name}" in ${where}`);
    return fact.value;
  });
  if (RESIDUE.test(resolved)) {
    throw new Error(`Malformed version fact token in ${where}: write %%fact=<name>%%`);
  }
  return resolved;
}

interface MarkdownNode {
  type: string;
  value?: unknown;
  children?: MarkdownNode[];
}

interface MarkdownFile {
  path?: string;
}

/** Remark plugin: resolve fact tokens in prose, inline code, and fenced code before rendering. */
export function remarkVersionFacts(facts: VersionFacts = repositoryVersionFacts()) {
  return () => (tree: MarkdownNode, file: MarkdownFile) => {
    const where = file.path ?? "markdown";
    const visit = (node: MarkdownNode) => {
      if (typeof node.value === "string" && (node.type === "text" || node.type === "inlineCode" || node.type === "code" || node.type === "html")) {
        node.value = resolveFactTokens(node.value, facts, where);
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}
