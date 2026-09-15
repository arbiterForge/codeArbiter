/** generation.test.ts — real-input wiring for the release applicability record. */
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  generateReleaseApplicability,
  loadDirectHookReplayEvidence,
  resolveHookSourcePath,
  serializeReleaseApplicabilityRecord,
  type ReleaseApplicabilityRecord,
} from "../../scripts/release-applicability";

const repoRoot = resolve(import.meta.dirname, "..", "..", "..");
const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("release applicability generation", () => {
  function writeProof(overrides: Record<string, unknown> = {}): string {
    const directory = mkdtempSync(join(tmpdir(), "release-applicability-proof-"));
    temporaryDirectories.push(directory);
    const path = join(directory, "hook-proof.json");
    writeFileSync(path, JSON.stringify({
      schema: 1,
      evidenceKind: "direct-hook-invocation-rendered-replay",
      hostDiscoveryProven: false,
      source: "plugins/ca/hooks/pre-bash.py",
      sourceSha256: "a".repeat(64),
      fixture: { retained: true },
      invocation: { retained: true },
      ...overrides,
    }), "utf8");
    return path;
  }

  it("loads the exact supported direct-hook replay claim while allowing fixture detail (O-10)", () => {
    expect(loadDirectHookReplayEvidence(writeProof())).toEqual({
      evidenceKind: "direct-hook-invocation-rendered-replay",
      hostDiscoveryProven: false,
      source: "plugins/ca/hooks/pre-bash.py",
      sourceSha256: "a".repeat(64),
    });
  });

  it.each([
    ["missing schema", { schema: undefined }],
    ["unsupported schema", { schema: 2 }],
    ["relabeled evidence kind", { evidenceKind: "direct-hook-registration-proof" }],
    ["host discovery promoted to true", { hostDiscoveryProven: true }],
  ])("rejects %s before proof metadata enters the generated record (O-10)", (_case, overrides) => {
    expect(() => loadDirectHookReplayEvidence(writeProof(overrides))).toThrow(/direct-hook|schema|discovery/i);
  });

  it.each(["missing", "invalid JSON"])(
    "rejects %s proof evidence before generation (O-10)",
    (evidenceCase) => {
      const directory = mkdtempSync(join(tmpdir(), "release-applicability-proof-"));
      temporaryDirectories.push(directory);
      const path = evidenceCase === "missing"
        ? join(directory, "does-not-exist.json")
        : join(directory, "hook-proof.json");
      if (evidenceCase === "invalid JSON") writeFileSync(path, "{not-json", "utf8");

    expect(() => loadDirectHookReplayEvidence(path)).toThrow(/missing or invalid JSON/i);
    },
  );

  it.each([
    "../outside.py",
    "plugins/ca/hooks/../pre-bash.py",
    "plugins\\ca\\hooks\\pre-bash.py",
    "/plugins/ca/hooks/pre-bash.py",
    "C:/plugins/ca/hooks/pre-bash.py",
    "./plugins/ca/hooks/pre-bash.py",
  ])("rejects a non-canonical or unconfined hook evidence path %s (O-10)", (source) => {
    expect(() => resolveHookSourcePath(repoRoot, source)).toThrow(/hook source path/i);
  });

  it("rejects a canonical hook path whose parent symlink escapes the repository (O-10)", () => {
    const fixtureRoot = mkdtempSync(join(tmpdir(), "release-applicability-root-"));
    const outside = mkdtempSync(join(tmpdir(), "release-applicability-outside-"));
    temporaryDirectories.push(fixtureRoot, outside);
    mkdirSync(join(fixtureRoot, "plugins", "ca"), { recursive: true });
    writeFileSync(join(outside, "pre-bash.py"), "outside\n", "utf8");
    symlinkSync(outside, join(fixtureRoot, "plugins", "ca", "hooks"), "junction");

    expect(() => resolveHookSourcePath(
      fixtureRoot, "plugins/ca/hooks/pre-bash.py",
    )).toThrow(/confined|regular|symbolic/i);
  });

  it("rejects a canonical hook path that resolves to a directory (O-10)", () => {
    const fixtureRoot = mkdtempSync(join(tmpdir(), "release-applicability-root-"));
    temporaryDirectories.push(fixtureRoot);
    mkdirSync(join(fixtureRoot, "plugins", "ca", "hooks", "pre-bash.py"), { recursive: true });

    expect(() => resolveHookSourcePath(
      fixtureRoot, "plugins/ca/hooks/pre-bash.py",
    )).toThrow(/regular/i);
  });

  it("writes the strict deterministic record from the repository's real evidence (O-10)", () => {
    const directory = mkdtempSync(join(tmpdir(), "release-applicability-"));
    temporaryDirectories.push(directory);
    const outputPath = join(directory, "release-applicability.json");

    const record = generateReleaseApplicability(repoRoot, outputPath, {});
    const bytes = readFileSync(outputPath, "utf8");
    const parsed = JSON.parse(bytes) as ReleaseApplicabilityRecord;

    expect(bytes).toBe(serializeReleaseApplicabilityRecord(record));
    expect(parsed).toEqual(record);
    expect(record.hosts.map(({ target }) => target)).toEqual([
      "ca",
      "ca-codex",
      "ca-pi",
    ]);
    expect(record.hosts.map(({ target, tag, version }) => [target, tag])).toEqual(
      record.hosts.map(({ target, version }) => [
        target,
        target === "ca" ? `v${version}` : `${target}-v${version}`,
      ]),
    );
    expect(record.proof.applicable).toBe(
      record.proof.currentSource.matchesReplay &&
        record.proof.publishedSource.matchesReplay,
    );
    expect(record.evidenceBoundary.claim).toBe("release-and-build-identity");
  });

  it("fails closed without writing output when build identity evidence is inconsistent (O-10)", () => {
    const directory = mkdtempSync(join(tmpdir(), "release-applicability-"));
    temporaryDirectories.push(directory);
    const outputPath = join(directory, "release-applicability.json");

    expect(() =>
      generateReleaseApplicability(repoRoot, outputPath, {
        GITHUB_ACTIONS: "true",
        GITHUB_SHA: "0000000000000000000000000000000000000000",
      }),
    ).toThrow(/GITHUB_SHA.*HEAD/i);
    expect(existsSync(outputPath)).toBe(false);
  });
});
