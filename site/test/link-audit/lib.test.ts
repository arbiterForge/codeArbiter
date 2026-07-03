import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  extractTargets,
  isExternalOrSkippable,
  resolveToDistFile,
  auditDist,
  BASE,
} from "../../scripts/link-audit/lib";

describe("extractTargets", () => {
  it("pulls href and src attribute values out of raw HTML", () => {
    const html = `<a href="/codeArbiter/overview/">x</a><img src="foo.svg">`;
    expect(extractTargets(html)).toEqual(["/codeArbiter/overview/", "foo.svg"]);
  });
});

describe("isExternalOrSkippable", () => {
  it("skips protocol-relative URLs", () => {
    expect(isExternalOrSkippable("//host/x")).toBe(true);
  });

  it("skips URLs with a scheme", () => {
    expect(isExternalOrSkippable("https://example.com")).toBe(true);
    expect(isExternalOrSkippable("mailto:a@b.com")).toBe(true);
  });

  it("skips pure fragments", () => {
    expect(isExternalOrSkippable("#frag")).toBe(true);
  });

  it("skips empty targets", () => {
    expect(isExternalOrSkippable("")).toBe(true);
  });

  it("does not skip root-absolute or page-relative internal-looking targets", () => {
    expect(isExternalOrSkippable("/overview/")).toBe(false);
    expect(isExternalOrSkippable("../concepts/")).toBe(false);
  });
});

describe("resolveToDistFile", () => {
  const distRoot = "/fake/dist";

  it("resolves a base-prefixed root-absolute target to a dist file", () => {
    const result = resolveToDistFile("/codeArbiter/overview/", "/codeArbiter/x", distRoot, BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "overview", "index.html"),
    });
  });

  it("classifies a base-less root-absolute target as outside-base (regression: previously silently skipped)", () => {
    const result = resolveToDistFile("/overview/", "/codeArbiter/x", distRoot, BASE);
    expect(result).toEqual({ kind: "outside-base", normalizedPath: "/overview/" });
  });

  it("resolves a page-relative target against the page's URL directory", () => {
    const result = resolveToDistFile(
      "../concepts/",
      "/codeArbiter/guides/troubleshooting",
      distRoot,
      BASE,
    );
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "guides", "concepts", "index.html"),
    });
  });

  it("classifies a page-relative target that normalizes outside the base as outside-base", () => {
    const result = resolveToDistFile("../../overview/", "/codeArbiter/x", distRoot, BASE);
    expect(result?.kind).toBe("outside-base");
  });

  it("maps an extensionless route to its directory index", () => {
    const result = resolveToDistFile("/codeArbiter/overview", "/codeArbiter/x", distRoot, BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "overview", "index.html"),
    });
  });

  it("maps a file-like target (has an extension) verbatim", () => {
    const result = resolveToDistFile("/codeArbiter/favicon.svg", "/codeArbiter/x", distRoot, BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "favicon.svg"),
    });
  });

  it("returns null for an empty target", () => {
    expect(resolveToDistFile("", "/codeArbiter/x", distRoot, BASE)).toBeNull();
  });
});

describe("auditDist", () => {
  let dist: string;

  beforeAll(() => {
    dist = mkdtempSync(join(tmpdir(), "link-audit-test-"));
    mkdirSync(join(dist, "overview"), { recursive: true });
    writeFileSync(join(dist, "overview", "index.html"), "<html><body>overview</body></html>");
    writeFileSync(
      join(dist, "index.html"),
      [
        `<a href="/codeArbiter/overview/">good link</a>`,
        `<a href="/overview/">base-less link</a>`,
        `<a href="https://example.com">external</a>`,
        `<a href="//host/x">protocol-relative</a>`,
        `<a href="#frag">fragment</a>`,
        `<a href="/codeArbiter/missing/">dangling</a>`,
      ].join("\n"),
    );
  });

  afterAll(() => {
    rmSync(dist, { recursive: true, force: true });
  });

  it("resolves base-prefixed internal links and reports base-less ones and dangling ones as failures", () => {
    const result = auditDist(dist, BASE);
    const messages = result.failures.map((f) => f.message);

    expect(messages.some((m) => m.includes("outside base path"))).toBe(true);
    expect(messages.some((m) => m.includes("missing"))).toBe(true);
    // The good, external, protocol-relative, and fragment links must not fail.
    expect(messages.some((m) => m.includes("good link"))).toBe(false);
    expect(result.failures.length).toBe(2);
  });
});
