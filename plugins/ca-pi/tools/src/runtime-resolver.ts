/** Resolve Pi runtime exports exclusively from the canonical CLI package anchor. */
import { lstat, readFile, realpath } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import type { ToolDefinitionPort } from "./contracts.ts";

export const PI_RUNTIME_DIAGNOSIS =
  "codeArbiter could not validate the active Pi CLI runtime; start from the Pi CLI and run /ca-doctor.";

export interface ResolvedPiRuntime {
  cliEntry: string;
  moduleEntry: string;
  packageRoot: string;
  version: string;
  ModelRegistry: abstract new (...args: never[]) => unknown;
  SettingsManager: {
    create(cwd: string, agentDir?: string, options?: { projectTrusted?: boolean }): {
      getShellCommandPrefix(): string | undefined;
      getShellPath(): string | undefined;
      getImageAutoResize(): boolean;
    };
  };
  getAgentDir(): string;
  createBashToolDefinition(cwd: string, options?: Record<string, unknown>): ToolDefinitionPort;
  createWriteToolDefinition(cwd: string, options?: Record<string, unknown>): ToolDefinitionPort;
  createEditToolDefinition(cwd: string, options?: Record<string, unknown>): ToolDefinitionPort;
  createReadToolDefinition(cwd: string, options?: Record<string, unknown>): ToolDefinitionPort;
}

export interface ResolvedPiRuntimeIdentity {
  readonly cliEntry: string;
  readonly manifestPath: string;
  readonly moduleEntry: string;
  readonly packageRoot: string;
  readonly version: string;
}

interface PiManifest {
  name?: unknown;
  version?: unknown;
  bin?: unknown;
  exports?: unknown;
}

const trustedIdentities = new WeakSet<object>();

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function fail(cause?: unknown): never {
  throw new Error(PI_RUNTIME_DIAGNOSIS, cause === undefined ? undefined : { cause });
}

async function owningPackageRoot(file: string, expectedName: string): Promise<string> {
  let cursor = dirname(file);
  while (true) {
    const candidate = resolve(cursor, "package.json");
    try {
      const manifest = JSON.parse(await readFile(candidate, "utf8")) as { name?: unknown };
      // By design: resolution is anchored to the shipped bundle layout (extensions/ under the
      // ca-pi package root), so the first package.json found is expected to already be "ca-pi";
      // a dev-tree src/ import walking up to an intermediate workspace package.json (e.g.
      // tools/package.json) is not a supported runtime path and fails closed here rather than
      // continuing to search further ancestors.
      if (manifest.name !== expectedName) return fail();
      const canonicalRoot = await realpath(cursor);
      if (!inside(file, canonicalRoot) || !inside(await realpath(candidate), canonicalRoot)) return fail();
      return canonicalRoot;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") return fail(error);
    }
    const parent = dirname(cursor);
    if (parent === cursor) return fail();
    cursor = parent;
  }
}

function binTarget(manifest: PiManifest): string {
  if (typeof manifest.bin === "string") return manifest.bin;
  if (manifest.bin !== null && typeof manifest.bin === "object") {
    const value = (manifest.bin as Record<string, unknown>).pi;
    if (typeof value === "string") return value;
  }
  return fail();
}

function importTarget(manifest: PiManifest): string {
  if (manifest.exports === null || typeof manifest.exports !== "object") return fail();
  const rootExport = (manifest.exports as Record<string, unknown>)["."];
  if (typeof rootExport === "string") return rootExport;
  if (rootExport !== null && typeof rootExport === "object") {
    const value = (rootExport as Record<string, unknown>).import;
    if (typeof value === "string") return value;
  }
  return fail();
}

function identitiesMatch(left: ResolvedPiRuntimeIdentity, right: ResolvedPiRuntimeIdentity): boolean {
  return left.cliEntry === right.cliEntry
    && left.manifestPath === right.manifestPath
    && left.moduleEntry === right.moduleEntry
    && left.packageRoot === right.packageRoot
    && left.version === right.version;
}

export async function resolvePiRuntimeIdentity(cliCandidate?: string): Promise<ResolvedPiRuntimeIdentity> {
  try {
    const activeAnchor = process.argv[1];
    if (typeof activeAnchor !== "string" || activeAnchor.length === 0 || !isAbsolute(activeAnchor)) return fail();
    const canonicalAnchor = await realpath(activeAnchor);
    if (cliCandidate !== undefined) {
      if (!isAbsolute(cliCandidate) || await realpath(cliCandidate) !== canonicalAnchor) return fail();
    }
    const shippedModule = await realpath(fileURLToPath(import.meta.url));
    const extensionPackageRoot = await owningPackageRoot(shippedModule, "ca-pi");
    let cursor = dirname(canonicalAnchor);
    let manifest: PiManifest | undefined;
    let manifestPath = "";
    while (true) {
      const candidate = resolve(cursor, "package.json");
      try {
        manifest = JSON.parse(await readFile(candidate, "utf8")) as PiManifest;
        manifestPath = candidate;
        break;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") return fail(error);
      }
      const parent = dirname(cursor);
      if (parent === cursor) return fail();
      cursor = parent;
    }
    if (manifest.name !== "@earendil-works/pi-coding-agent" || typeof manifest.version !== "string") return fail();
    const packageRoot = await realpath(cursor);
    const canonicalManifest = await realpath(manifestPath);
    if (!inside(canonicalAnchor, packageRoot) || !inside(canonicalManifest, packageRoot)) return fail();
    if (inside(packageRoot, extensionPackageRoot)) return fail();

    const declaredBin = resolve(packageRoot, binTarget(manifest));
    if (!inside(declaredBin, packageRoot) || await realpath(declaredBin) !== canonicalAnchor) return fail();
    if (!(await lstat(canonicalAnchor)).isFile()) return fail();

    const declaredExport = importTarget(manifest);
    if (!declaredExport.startsWith("./")) return fail();
    const requireFromPi = createRequire(resolve(packageRoot, "package.json"));
    const moduleEntry = await realpath(requireFromPi.resolve(declaredExport));
    if (!inside(moduleEntry, packageRoot)) return fail();
    if (!(await lstat(moduleEntry)).isFile()) return fail();

    const identity = Object.freeze({
      cliEntry: canonicalAnchor,
      manifestPath: canonicalManifest,
      moduleEntry,
      packageRoot,
      version: manifest.version,
    });
    trustedIdentities.add(identity);
    return identity;
  } catch (error) {
    if (error instanceof Error && error.message === PI_RUNTIME_DIAGNOSIS) throw error;
    return fail(error);
  }
}

export async function loadPiRuntime(identity: ResolvedPiRuntimeIdentity): Promise<ResolvedPiRuntime> {
  try {
    if (!trustedIdentities.has(identity)) return fail();
    const beforeImport = await resolvePiRuntimeIdentity(identity.cliEntry);
    if (!identitiesMatch(identity, beforeImport)) return fail();

    const runtime = await import(pathToFileURL(identity.moduleEntry).href) as Record<string, unknown>;
    const requiredFunctions = [
      "getAgentDir",
      "createBashToolDefinition",
      "createWriteToolDefinition",
      "createEditToolDefinition",
      "createReadToolDefinition",
    ];
    if (
      runtime.VERSION !== identity.version
      || typeof runtime.ModelRegistry !== "function"
      || typeof runtime.SettingsManager !== "function"
      || requiredFunctions.some((name) => typeof runtime[name] !== "function")
    ) return fail();
    const afterImport = await resolvePiRuntimeIdentity(identity.cliEntry);
    if (!identitiesMatch(identity, afterImport)) return fail();
    return {
      cliEntry: identity.cliEntry,
      moduleEntry: identity.moduleEntry,
      packageRoot: identity.packageRoot,
      version: identity.version,
      ModelRegistry: runtime.ModelRegistry as ResolvedPiRuntime["ModelRegistry"],
      SettingsManager: runtime.SettingsManager as unknown as ResolvedPiRuntime["SettingsManager"],
      getAgentDir: runtime.getAgentDir as ResolvedPiRuntime["getAgentDir"],
      createBashToolDefinition: runtime.createBashToolDefinition as ResolvedPiRuntime["createBashToolDefinition"],
      createWriteToolDefinition: runtime.createWriteToolDefinition as ResolvedPiRuntime["createWriteToolDefinition"],
      createEditToolDefinition: runtime.createEditToolDefinition as ResolvedPiRuntime["createEditToolDefinition"],
      createReadToolDefinition: runtime.createReadToolDefinition as ResolvedPiRuntime["createReadToolDefinition"],
    };
  } catch (error) {
    if (error instanceof Error && error.message === PI_RUNTIME_DIAGNOSIS) throw error;
    return fail(error);
  }
}

export async function resolvePiRuntime(cliCandidate?: string): Promise<ResolvedPiRuntime> {
  const identity = await resolvePiRuntimeIdentity(cliCandidate);
  return await loadPiRuntime(identity);
}
