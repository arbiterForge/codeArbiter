/** runtime-resolver.test.ts - direct exercise of resolvePiRuntimeIdentity's fail-closed branches
 * against real temp-directory fixtures, with no mock of the module under test.
 *
 * IMPORTANT: `resolvePiRuntimeIdentity` computes its own "extension package root" via
 * `owningPackageRoot(shippedModule, "ca-pi")`, where `shippedModule` is derived from
 * `import.meta.url` of runtime-resolver.ts itself (see src/runtime-resolver.ts:113-114). If we
 * import the module directly from its real location (plugins/ca-pi/tools/src/runtime-resolver.ts),
 * `owningPackageRoot` walks up and finds plugins/ca-pi/tools/package.json first, whose "name" is
 * "ca-pi-tools" - NOT "ca-pi" - and `owningPackageRoot` fails closed on the FIRST package.json it
 * finds with a mismatched name rather than continuing to walk up to plugins/ca-pi/package.json
 * (which *is* named "ca-pi"). See the documented defect below ("owningPackageRoot name-mismatch
 * short-circuit"). Consequently `resolvePiRuntimeIdentity` can never succeed when the real module
 * is imported directly from source in this repo layout - every call fails closed regardless of the
 * CLI package fixture under test.
 *
 * To exercise real success paths (and to keep failure-path tests anchored on the *exact* branch
 * they intend to cover rather than always failing at the extension-root check), this suite loads
 * an unmodified byte-for-byte COPY of src/runtime-resolver.ts into a throwaway temp directory whose
 * immediate package.json IS named "ca-pi", then dynamically imports that copy. This is still the
 * real, unmodified `resolvePiRuntimeIdentity` implementation under test - only its on-disk location
 * (and therefore its self-referential extension-root anchor) differs from the checked-in path.
 */
import { readFile, mkdir, mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { afterAll, afterEach, beforeAll, describe, expect, test } from "vitest";

type RuntimeResolverModule = typeof import("../src/runtime-resolver.ts");

const temporaryRoots: string[] = [];
let resolverHomeRoot: string;
let resolvePiRuntimeIdentity: RuntimeResolverModule["resolvePiRuntimeIdentity"];
let PI_RUNTIME_DIAGNOSIS: RuntimeResolverModule["PI_RUNTIME_DIAGNOSIS"];

beforeAll(async () => {
  // Build a fixture "ca-pi" package whose src/runtime-resolver.ts is an unmodified copy of the
  // real module, so `owningPackageRoot(shippedModule, "ca-pi")` finds a package.json literally
  // named "ca-pi" at the first ancestor, matching the intended (production-bundle) layout.
  resolverHomeRoot = await realpath(await mkdtemp(resolve(tmpdir(), "ca-pi-runtime-resolver-home-")));
  const srcDir = resolve(resolverHomeRoot, "src");
  await mkdir(srcDir, { recursive: true });
  const realSourcePath = resolve(import.meta.dirname, "..", "src", "runtime-resolver.ts");
  const realSource = await readFile(realSourcePath, "utf8");
  await writeFile(resolve(srcDir, "runtime-resolver.ts"), realSource, "utf8");
  await writeFile(resolve(resolverHomeRoot, "package.json"), JSON.stringify({ name: "ca-pi", version: "0.1.0", type: "module" }), "utf8");
  const module = await import(pathToFileURL(resolve(srcDir, "runtime-resolver.ts")).href) as RuntimeResolverModule;
  resolvePiRuntimeIdentity = module.resolvePiRuntimeIdentity;
  PI_RUNTIME_DIAGNOSIS = module.PI_RUNTIME_DIAGNOSIS;
});

afterAll(async () => {
  await rm(resolverHomeRoot, { recursive: true, force: true });
});

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

async function makeRoot(prefix = "ca-pi-runtime-resolver-"): Promise<string> {
  const root = await realpath(await mkdtemp(resolve(tmpdir(), prefix)));
  temporaryRoots.push(root);
  return root;
}

interface FixtureOptions {
  name?: unknown;
  version?: unknown;
  bin?: unknown;
  exports?: unknown;
  manifestJson?: string; // raw override, wins over name/version/bin/exports
  omitManifest?: boolean;
  cliRelative?: string; // path (relative to package root) that will actually hold the CLI file
  moduleRelative?: string; // path (relative to package root) that will actually hold the module file
  omitCli?: boolean;
  omitModule?: boolean;
  cliIsDirectory?: boolean;
  moduleIsDirectory?: boolean;
}

/**
 * Builds a fake, well-formed (unless overridden) Pi CLI package tree:
 *   <root>/pi-runtime/package.json
 *   <root>/pi-runtime/dist/cli.js       (bin target)
 *   <root>/pi-runtime/dist/index.js     (module/export target)
 * Returns the package root, the absolute cli path (the "activeAnchor"), and the module entry path.
 */
async function buildPiPackage(root: string, options: FixtureOptions = {}): Promise<{ packageRoot: string; cliPath: string; moduleEntry: string }> {
  const packageRoot = resolve(root, "pi-runtime");
  await mkdir(resolve(packageRoot, "dist"), { recursive: true });

  const cliRelative = options.cliRelative ?? "dist/cli.js";
  const moduleRelative = options.moduleRelative ?? "dist/index.js";
  const cliPath = resolve(packageRoot, cliRelative);
  const moduleEntry = resolve(packageRoot, moduleRelative);

  if (!options.omitCli) {
    await mkdir(dirname(cliPath), { recursive: true });
    if (options.cliIsDirectory) await mkdir(cliPath, { recursive: true });
    else await writeFile(cliPath, "// fixture Pi CLI\n", "utf8");
  }
  if (!options.omitModule) {
    await mkdir(dirname(moduleEntry), { recursive: true });
    if (options.moduleIsDirectory) await mkdir(moduleEntry, { recursive: true });
    else await writeFile(moduleEntry, "export const VERSION = \"1.2.3\";\n", "utf8");
  }

  if (!options.omitManifest) {
    const manifestJson = options.manifestJson ?? JSON.stringify({
      name: options.name ?? "@earendil-works/pi-coding-agent",
      version: options.version ?? "1.2.3",
      bin: options.bin ?? { pi: "./" + cliRelative },
      exports: options.exports ?? { ".": { import: "./" + moduleRelative } },
    });
    await writeFile(resolve(packageRoot, "package.json"), manifestJson, "utf8");
  }

  return { packageRoot, cliPath, moduleEntry };
}

/** Runs resolvePiRuntimeIdentity with process.argv[1] pointed at the given CLI path. */
async function resolveWithAnchor(cliPath: string, cliCandidate?: string) {
  const originalArgv1 = process.argv[1];
  process.argv[1] = cliPath;
  try {
    return await resolvePiRuntimeIdentity(cliCandidate);
  } finally {
    process.argv[1] = originalArgv1;
  }
}

describe("resolvePiRuntimeIdentity - happy path", () => {
  test("resolves a well-formed Pi package tree with the correct identity fields", async () => {
    const root = await makeRoot();
    const { packageRoot, cliPath, moduleEntry } = await buildPiPackage(root);
    const identity = await resolveWithAnchor(cliPath);
    expect(identity.cliEntry).toBe(await realpath(cliPath));
    expect(identity.packageRoot).toBe(await realpath(packageRoot));
    expect(identity.version).toBe("1.2.3");
    expect(identity.manifestPath).toBe(await realpath(resolve(packageRoot, "package.json")));
    expect(identity.moduleEntry).toBe(await realpath(moduleEntry));
  });

  test("accepts a matching absolute cliCandidate that resolves to the same anchor", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root);
    const identity = await resolveWithAnchor(cliPath, cliPath);
    expect(identity.cliEntry).toBe(await realpath(cliPath));
  });
});

describe("resolvePiRuntimeIdentity - fail-closed branches (105-159)", () => {
  test("fails when process.argv[1] is missing, empty, or relative", async () => {
    const originalArgv1 = process.argv[1];
    try {
      process.argv[1] = undefined as unknown as string;
      await expect(resolvePiRuntimeIdentity()).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
      process.argv[1] = "";
      await expect(resolvePiRuntimeIdentity()).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
      process.argv[1] = "relative/cli.js";
      await expect(resolvePiRuntimeIdentity()).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
    } finally {
      process.argv[1] = originalArgv1;
    }
  });

  test("fails when cliCandidate is relative or resolves to a different anchor", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root);
    await expect(resolveWithAnchor(cliPath, "relative/cli.js")).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
    const other = await buildPiPackage(await makeRoot(), { name: "other-pkg" });
    await expect(resolveWithAnchor(cliPath, other.cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when no package.json is found walking up from the anchor", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { omitManifest: true });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when package.json contains malformed JSON (non-ENOENT read error)", async () => {
    const root = await makeRoot();
    const { packageRoot, cliPath } = await buildPiPackage(root);
    await writeFile(resolve(packageRoot, "package.json"), "{ not valid json", "utf8");
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the manifest name does not match the expected Pi package name", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { name: "not-the-right-package" });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when version is missing or not a string", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { version: 123 });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);

    const root2 = await makeRoot();
    const manifestJson = JSON.stringify({
      name: "@earendil-works/pi-coding-agent",
      bin: { pi: "./dist/cli.js" },
      exports: { ".": { import: "./dist/index.js" } },
    });
    const { cliPath: cliPath2 } = await buildPiPackage(root2, { manifestJson });
    await expect(resolveWithAnchor(cliPath2)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when bin is missing, not a string/object, or lacks a `pi` key", async () => {
    for (const bin of [undefined, 42, {}, { notPi: "./dist/cli.js" }]) {
      const root = await makeRoot();
      const options: FixtureOptions = bin === undefined ? { manifestJson: JSON.stringify({
        name: "@earendil-works/pi-coding-agent",
        version: "1.2.3",
        exports: { ".": { import: "./dist/index.js" } },
      }) } : { bin };
      const { cliPath } = await buildPiPackage(root, options);
      await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
    }
  });

  test("fails when the declared bin target does not resolve to the running anchor", async () => {
    const root = await makeRoot();
    // Declared bin points elsewhere in the package, but argv[1] anchors at dist/cli.js.
    const { cliPath } = await buildPiPackage(root, { bin: { pi: "./dist/other-cli.js" } });
    await writeFile(resolve(dirname(cliPath), "other-cli.js"), "// mismatched bin target\n", "utf8");
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the declared bin target escapes the package root (containment)", async () => {
    const root = await makeRoot();
    const outsideFile = resolve(root, "outside-cli.js");
    await writeFile(outsideFile, "// outside the package root\n", "utf8");
    // bin points outside the package root via traversal; the running anchor is still the in-tree
    // cli file, so realpath(declaredBin) !== canonicalAnchor is what actually trips here (the
    // resolver never reaches a pure containment-only failure for `declaredBin` because the
    // anchor-equality check runs first) - this documents that observed failure mode.
    const { cliPath } = await buildPiPackage(root, { bin: { pi: "../outside-cli.js" } });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when exports is missing, not an object, or the root export is malformed", async () => {
    for (const exports_ of [undefined, "./dist/index.js", {}, { ".": {} }, { ".": { import: 42 } }]) {
      const root = await makeRoot();
      const options: FixtureOptions = exports_ === undefined ? { manifestJson: JSON.stringify({
        name: "@earendil-works/pi-coding-agent",
        version: "1.2.3",
        bin: { pi: "./dist/cli.js" },
      }) } : { exports: exports_ };
      const { cliPath } = await buildPiPackage(root, options);
      await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
    }
  });

  test("fails when the root export does not start with './'", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { exports: { ".": { import: "dist/index.js" } } });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the module export target cannot be resolved (missing file)", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { omitModule: true });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the resolved module export escapes the package root (containment)", async () => {
    const root = await makeRoot();
    const outsideModule = resolve(root, "outside-index.js");
    await writeFile(outsideModule, "export const VERSION = \"1.2.3\";\n", "utf8");
    const { cliPath } = await buildPiPackage(root, { exports: { ".": { import: "../outside-index.js" } } });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the resolved package root is inside the ca-pi extension's own package root", async () => {
    // The fixture module lives at resolverHomeRoot ("ca-pi") - build the Pi package tree nested
    // beneath it so `inside(packageRoot, extensionPackageRoot)` trips.
    const nestedRoot = resolve(resolverHomeRoot, "nested-pi-fixture");
    await mkdir(nestedRoot, { recursive: true });
    const { cliPath } = await buildPiPackage(nestedRoot);
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
    await rm(nestedRoot, { recursive: true, force: true });
  });
});

describe("resolvePiRuntimeIdentity - tampering", () => {
  // Hardened: resolvePiRuntimeIdentity now stat()s the cli entry after the realpath/anchor
  // equality check and requires isFile(). Replacing the declared bin target with a directory of
  // the same path is rejected.
  test("fails when the cli entry path is a directory instead of a file", async () => {
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { cliIsDirectory: true });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when the module entry file is replaced by a directory", async () => {
    // require.resolve() already rejects a bare directory with no package.json/index.js
    // (MODULE_NOT_FOUND) before the explicit isFile() guard is even reached, so this exercises
    // the pre-existing require.resolve failure mode.
    const root = await makeRoot();
    const { cliPath } = await buildPiPackage(root, { moduleIsDirectory: true });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("fails when package.json's bin points at an absolute path outside the tree", async () => {
    const root = await makeRoot();
    const outsideFile = resolve(root, "absolute-outside-cli.js");
    await writeFile(outsideFile, "// absolute outside target\n", "utf8");
    // resolve() with an absolute path input ignores packageRoot, so the resulting
    // declaredBin lands outside packageRoot and fails containment/anchor-equality.
    const { cliPath } = await buildPiPackage(root, { bin: { pi: outsideFile } });
    await expect(resolveWithAnchor(cliPath)).rejects.toThrow(PI_RUNTIME_DIAGNOSIS);
  });

  test("resolves through a symlinked package root once realpath is applied uniformly", async () => {
    const root = await makeRoot();
    const { packageRoot, cliPath: realCliPath } = await buildPiPackage(root);
    const outsideRoot = await makeRoot("ca-pi-runtime-resolver-outside-");
    const linkedPackageRoot = resolve(outsideRoot, "linked-pi-runtime");
    let linked = true;
    try {
      await symlink(packageRoot, linkedPackageRoot, process.platform === "win32" ? "junction" : "dir");
    } catch {
      linked = false;
    }
    if (!linked) return; // Platform/permission cannot create symlinks (e.g. unprivileged Windows); skip.
    const linkedCliPath = resolve(linkedPackageRoot, "dist", "cli.js");
    // The anchor resolves through the symlink; canonicalAnchor collapses to the real cli file via
    // realpath(), and every containment check downstream is performed against realpath'd values,
    // so this resolves successfully rather than failing - documenting that symlinked *access* to
    // an otherwise legitimate package is tolerated once realpath is applied uniformly.
    const identity = await resolveWithAnchor(linkedCliPath);
    expect(identity.cliEntry).toBe(await realpath(realCliPath));
    expect(identity.packageRoot).toBe(await realpath(packageRoot));
  });
});
