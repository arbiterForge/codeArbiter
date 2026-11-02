/** stale-capture.test.ts - AC-06: a stale capture fails the build.
 *
 * A capture records the sha256 of every repository source its tool executed.
 * `npm run gen` compares those hashes with the working tree and fails, naming
 * the capture, the changed source and the refresh command, when one differs.
 * The docs workflow must also trigger on every captured source, or a change to
 * it could merge without this check running.
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { sha256Lf } from "../../scripts/capture/normalize";
import { assertCapturesFresh, verifyCaptures } from "../../scripts/capture/verify";
import { matchesPathFilter, readWorkflowPathFilters, uncoveredSources } from "./path-filters";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const repoRoot = resolve(siteRoot, "..");
const capturesDir = join(siteRoot, "src", "assets", "captures");
const workflowText = readFileSync(join(repoRoot, ".github", "workflows", "docs.yml"), "utf8");

const require_ = createRequire(import.meta.url);
const tsxPackage = require_.resolve("tsx/package.json");
const tsxBin = require_("tsx/package.json").bin;
const TSX_CLI = resolve(dirname(tsxPackage), typeof tsxBin === "string" ? tsxBin : tsxBin.tsx);

const scratch: string[] = [];
afterAll(() => {
  for (const dir of scratch) rmSync(dir, { recursive: true, force: true });
});

interface MiniRepo {
  repo: string;
  captures: string;
}

/** A throwaway repository with two sources and one capture of them, hashed correctly. */
function miniRepo(overrides: { recordedLib?: string; extra?: Record<string, unknown> } = {}): MiniRepo {
  const repo = mkdtempSync(join(tmpdir(), "stale-capture-test-"));
  scratch.push(repo);
  mkdirSync(join(repo, "tools"), { recursive: true });
  const entry = "def main():\n    return 0\n";
  const lib = "VALUE = 1\n";
  writeFileSync(join(repo, "tools", "entry.py"), entry);
  writeFileSync(join(repo, "tools", "lib.py"), lib);
  const captures = join(repo, "captures");
  mkdirSync(captures, { recursive: true });
  const record = {
    schema: 1,
    id: "demo-run",
    title: "Demo",
    tool: "tools/entry.py",
    argv: ["python", "tools/entry.py"],
    exitCode: 0,
    shown: "stdout",
    output: "ok",
    hashing: "sha256 over file bytes with CRLF collapsed to LF",
    sources: [
      { path: "tools/entry.py", sha256: sha256Lf(Buffer.from(entry)) },
      { path: "tools/lib.py", sha256: overrides.recordedLib ?? sha256Lf(Buffer.from(lib)) },
    ],
    ...overrides.extra,
  };
  writeFileSync(join(captures, "demo-run.json"), `${JSON.stringify(record, null, 2)}\n`);
  return { repo, captures };
}

describe("stale-capture check (AC-06)", () => {
  it("passes when every recorded hash matches the working tree", () => {
    const { repo, captures } = miniRepo();
    expect(verifyCaptures(repo, captures).findings).toEqual([]);
    expect(() => assertCapturesFresh(repo, captures)).not.toThrow();
  });

  it("fails a capture whose recorded source hash is wrong, naming the capture, the source and the refresh command", () => {
    const { repo, captures } = miniRepo({ recordedLib: "0".repeat(64) });
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/demo-run/);
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/tools\/lib\.py/);
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/npm run capture/);
    const [finding] = verifyCaptures(repo, captures).findings;
    expect(finding).toMatchObject({ capture: "demo-run", source: "tools/lib.py", problem: "changed" });
  });

  it("does not blame an unchanged source", () => {
    const { repo, captures } = miniRepo({ recordedLib: "0".repeat(64) });
    const sources = verifyCaptures(repo, captures).findings.map((finding) => finding.source);
    expect(sources).toEqual(["tools/lib.py"]);
  });

  it("fails when a captured source changes after the capture was recorded", () => {
    const { repo, captures } = miniRepo();
    writeFileSync(join(repo, "tools", "entry.py"), "def main():\n    return 1\n");
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/demo-run.*tools\/entry\.py.*npm run capture/s);
  });

  it("fails when a captured source no longer exists", () => {
    const { repo, captures } = miniRepo();
    rmSync(join(repo, "tools", "lib.py"));
    const [finding] = verifyCaptures(repo, captures).findings;
    expect(finding).toMatchObject({ capture: "demo-run", source: "tools/lib.py", problem: "missing" });
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/tools\/lib\.py.*npm run capture/s);
  });

  it("accepts an unchanged source checked out with CRLF line endings", () => {
    const { repo, captures } = miniRepo();
    writeFileSync(join(repo, "tools", "lib.py"), "VALUE = 1\r\n");
    expect(verifyCaptures(repo, captures).findings).toEqual([]);
  });

  it("reports every stale capture, not only the first", () => {
    const { repo, captures } = miniRepo({ recordedLib: "0".repeat(64) });
    const second = JSON.parse(readFileSync(join(captures, "demo-run.json"), "utf8"));
    second.id = "second-run";
    writeFileSync(join(captures, "second-run.json"), JSON.stringify(second));
    const names = verifyCaptures(repo, captures).findings.map((finding) => finding.capture).sort();
    expect(names).toEqual(["demo-run", "second-run"]);
  });

  it("fails a capture that is malformed, naming its file", () => {
    const { repo, captures } = miniRepo();
    writeFileSync(join(captures, "broken.json"), "{ not json");
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/broken\.json/);

    const noEntry = miniRepo({ extra: { tool: "tools/other.py" } });
    expect(() => assertCapturesFresh(noEntry.repo, noEntry.captures)).toThrow(/demo-run.*entry script/s);

    const badHash = miniRepo({ recordedLib: "not-a-hash" });
    expect(() => assertCapturesFresh(badHash.repo, badHash.captures)).toThrow(/demo-run.*sha256/s);

    const badId = miniRepo({ extra: { id: "other-name" } });
    expect(() => assertCapturesFresh(badId.repo, badId.captures)).toThrow(/demo-run\.json.*id/s);
  });

  it("refuses a source path that escapes the repository", () => {
    const { repo, captures } = miniRepo();
    const record = JSON.parse(readFileSync(join(captures, "demo-run.json"), "utf8"));
    record.sources.push({ path: "../outside.py", sha256: "0".repeat(64) });
    writeFileSync(join(captures, "demo-run.json"), JSON.stringify(record));
    expect(() => assertCapturesFresh(repo, captures)).toThrow(/demo-run.*outside the repository/s);
  });

  it("fails when there are no captures at all, so deleting them cannot disable the check", () => {
    const { repo } = miniRepo();
    const empty = join(repo, "no-captures");
    mkdirSync(empty);
    expect(() => assertCapturesFresh(repo, empty)).toThrow(/no captures/i);
    expect(() => assertCapturesFresh(repo, join(repo, "missing-directory"))).toThrow(/no captures/i);
  });

  it("is what the command line runs: exit 1 and the message on stderr when stale, exit 0 when fresh", () => {
    const fresh = miniRepo();
    const ok = spawnSync(process.execPath, [TSX_CLI, "scripts/capture/verify.ts", "--repo", fresh.repo, "--captures", fresh.captures], {
      cwd: siteRoot,
      encoding: "utf8",
    });
    expect(ok.status).toBe(0);

    const stale = miniRepo({ recordedLib: "0".repeat(64) });
    const failed = spawnSync(process.execPath, [TSX_CLI, "scripts/capture/verify.ts", "--repo", stale.repo, "--captures", stale.captures], {
      cwd: siteRoot,
      encoding: "utf8",
    });
    expect(failed.status).toBe(1);
    expect(failed.stderr).toMatch(/demo-run.*tools\/lib\.py.*npm run capture/s);
  }, 60_000);

  it("runs from the generator before any page is generated", () => {
    const gen = readFileSync(join(siteRoot, "scripts", "gen.ts"), "utf8");
    const call = gen.indexOf("assertCapturesFresh(");
    expect(gen).toMatch(/from "\.\/capture\/verify"/);
    expect(call).toBeGreaterThan(-1);
    expect(call).toBeLessThan(gen.indexOf("generate(srcDir"));
  });

  it("holds for the committed captures against the working tree", () => {
    const names = readdirSync(capturesDir).filter((name) => name.endsWith(".json"));
    expect(names.length).toBeGreaterThanOrEqual(4);
    expect(verifyCaptures(repoRoot, capturesDir).findings).toEqual([]);
  });
});

describe("docs workflow covers every captured source (AC-06)", () => {
  const filters = readWorkflowPathFilters(workflowText);
  const capturedSources = [
    ...new Set(
      readdirSync(capturesDir)
        .filter((name) => name.endsWith(".json"))
        .flatMap((name) => JSON.parse(readFileSync(join(capturesDir, name), "utf8")).sources.map((source: { path: string }) => source.path)),
    ),
  ];

  it("reads both the push and the pull_request path filters", () => {
    expect(filters.push.length).toBeGreaterThan(3);
    expect(filters.pull_request.length).toBeGreaterThan(3);
    expect(filters.push).toContain("site/**");
    expect(filters.pull_request).toContain("site/**");
  });

  it("matches every captured source on both triggers", () => {
    expect(capturedSources.length).toBeGreaterThan(5);
    expect(uncoveredSources(capturedSources, filters)).toEqual([]);
  });

  it("reports a source outside the filters, by trigger", () => {
    const outside = uncoveredSources(["tools/unrelated/script.py", "plugins/ca/hooks/_hooklib.py"], filters);
    expect(outside).toEqual([
      { source: "tools/unrelated/script.py", event: "push" },
      { source: "tools/unrelated/script.py", event: "pull_request" },
    ]);
  });

  it("notices when only one trigger loses its filter", () => {
    const pushOnly = { push: filters.push, pull_request: filters.pull_request.filter((pattern) => pattern !== "plugins/ca/**") };
    expect(uncoveredSources(["plugins/ca/hooks/_hooklib.py"], pushOnly)).toEqual([
      { source: "plugins/ca/hooks/_hooklib.py", event: "pull_request" },
    ]);
  });

  it("refuses a workflow whose filter lists are missing or empty instead of passing vacuously", () => {
    expect(() => readWorkflowPathFilters("name: x\njobs: {}\n")).toThrow(/`on:`/);
    expect(() => readWorkflowPathFilters("on:\n  push:\n    branches: [main]\n")).toThrow(/on\.push has no paths/);
    expect(() => readWorkflowPathFilters("on:\n  push:\n    paths:\n      - 'a/**'\n")).toThrow(/pull_request/);
    expect(() => readWorkflowPathFilters("on:\n  push:\n    paths:\n  pull_request:\n    paths:\n      - 'a'\n")).toThrow(/empty/);
  });

  it("matches filter globs the way GitHub does", () => {
    expect(matchesPathFilter("plugins/ca/hooks/_hooklib.py", "plugins/ca/**")).toBe(true);
    expect(matchesPathFilter("plugins/ca-pi/x.ts", "plugins/ca/**")).toBe(false);
    expect(matchesPathFilter("site/a/b.ts", "site/*")).toBe(false);
    expect(matchesPathFilter("site/a.ts", "site/*")).toBe(true);
    expect(matchesPathFilter("academy-source", "academy-source")).toBe(true);
    expect(matchesPathFilter("academy-source/x", "academy-source")).toBe(false);
  });
});
