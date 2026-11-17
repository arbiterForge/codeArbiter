import { afterEach, describe, expect, it } from "vitest";
import { existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, rmSync, rmdirSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { primaryNamedResults, ORIGINAL_COVERAGE_SCRIPT } from "./docs-vitest-results";

const roots: string[] = [];
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }); });
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "ca-docs-report-config-")); roots.push(root);
  const output = join(root, "primary-vitest.json");
  return { root, output, env: { CODEARBITER_DOCS_NAMED_RESULTS: output,
    npm_lifecycle_event: "coverage", npm_lifecycle_script: ORIGINAL_COVERAGE_SCRIPT } };
}

describe("original Docs primary-only named reporting", () => {
  it("keeps default config unchanged without the owning opt-in", () => {
    expect(primaryNamedResults({}, ["run", "--coverage"])).toEqual({});
  });
  it("retains default and JSON reporters only for the exact primary lifecycle", () => {
    const f = fixture();
    expect(primaryNamedResults(f.env, ["run", "--coverage"])).toEqual({ reporters: ["default", "json"], outputFile: { json: f.output } });
    expect(existsSync(f.output)).toBe(false);
    writeFileSync(f.output, "");
    expect(primaryNamedResults(f.env, ["run", "--coverage"]).outputFile).toEqual({ json: f.output });
  });
  it("does not let precoverage, nested followups, filtered runs or workers overwrite primary results", () => {
    const f = fixture(); writeFileSync(f.output, "completed primary sentinel");
    for (const event of ["precoverage", "test:academy-base", "test:release-applicability-rendered"])
      expect(primaryNamedResults({ ...f.env, npm_lifecycle_event: event }, ["run", "--coverage"])).toEqual({});
    for (const argv of [["run"], ["run", "--coverage", "selected.test.ts"], ["worker"], ["run", "--reporter=json"]])
      expect(primaryNamedResults(f.env, argv)).toEqual({});
    expect(readFileSync(f.output, "utf8")).toBe("completed primary sentinel");
  });
  it("refuses a changed compound lifecycle rather than attaching flags to its final command", () => {
    const f = fixture();
    for (const script of ["vitest run --coverage", ORIGINAL_COVERAGE_SCRIPT + " --reporter=json", "vitest run selected.test.ts --coverage"])
      expect(() => primaryNamedResults({ ...f.env, npm_lifecycle_script: script }, ["run", "--coverage"])).toThrow(/role or output/);
  });
  it("refuses malformed, reused, linked and nonregular result targets", () => {
    const f = fixture();
    for (const output of ["primary-vitest.json", join(f.root, "foreign.json"), join(f.root, "\nprimary-vitest.json")])
      expect(() => primaryNamedResults({ ...f.env, CODEARBITER_DOCS_NAMED_RESULTS: output }, ["run", "--coverage"])).toThrow();
    writeFileSync(f.output, "already completed");
    expect(() => primaryNamedResults(f.env, ["run", "--coverage"])).toThrow(/fresh/);
    rmSync(f.output); mkdirSync(f.output);
    expect(() => primaryNamedResults(f.env, ["run", "--coverage"])).toThrow(/fresh/);
    rmdirSync(f.output); writeFileSync(f.output, ""); linkSync(f.output, join(f.root, "second-link"));
    expect(() => primaryNamedResults(f.env, ["run", "--coverage"])).toThrow(/fresh/);
  });
  it("refuses a linked parent without touching its target", () => {
    const f = fixture(); const parent = join(f.root, "real"); mkdirSync(parent);
    const linked = join(f.root, "alias"); symlinkSync(parent, linked, "junction");
    expect(() => primaryNamedResults({ ...f.env, CODEARBITER_DOCS_NAMED_RESULTS: join(linked, "primary-vitest.json") }, ["run", "--coverage"])).toThrow();
    expect(existsSync(join(parent, "primary-vitest.json"))).toBe(false);
  });
  it("refuses unavailable ownership without echoing the source path", () => {
    const f = fixture(); const canary = "PRIVATE_PATH_CANARY";
    let error: unknown;
    try { primaryNamedResults({ ...f.env, CODEARBITER_DOCS_NAMED_RESULTS: join(f.root, canary, "primary-vitest.json") }, ["run", "--coverage"]); }
    catch (caught) { error = caught; }
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).not.toContain(canary);
  });
});
