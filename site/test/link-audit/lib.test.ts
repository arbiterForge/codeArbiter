import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import {
  extractTargets,
  isExternalOrSkippable,
  resolveToDistFile,
  auditDist,
  missingRequiredAssets,
  BASE,
} from "../../scripts/link-audit/lib";

/** Build a throwaway dist/ tree. `assets` controls the chrome the audit pins;
 * `pages` is a map of dist-relative path -> file contents. */
function makeDist(options: {
  favicon?: boolean;
  astroDir?: boolean;
  logoName?: string | null;
  pages?: Record<string, string>;
}): string {
  const { favicon = true, astroDir = true, logoName = "logo.abc123.svg", pages = {} } = options;
  const dist = mkdtempSync(join(tmpdir(), "link-audit-test-"));
  if (favicon) writeFileSync(join(dist, "favicon.svg"), "<svg/>");
  if (astroDir) {
    mkdirSync(join(dist, "_astro"), { recursive: true });
    if (logoName !== null) writeFileSync(join(dist, "_astro", logoName), "<svg/>");
  }
  for (const [rel, contents] of Object.entries(pages)) {
    const full = join(dist, ...rel.split("/"));
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, contents);
  }
  return dist;
}

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

describe("auditDist page-inventory invariant", () => {
  const dists: string[] = [];

  afterAll(() => {
    for (const d of dists) rmSync(d, { recursive: true, force: true });
  });

  function track(dist: string): string {
    dists.push(dist);
    return dist;
  }

  it("fails an existing but HTML-empty dist even when both required assets are present", () => {
    // A generator/build regression that emits no pages must not read as green:
    // "found nothing wrong" and "looked at nothing" are different outcomes.
    const dist = track(makeDist({ pages: {} }));

    const result = auditDist(dist, BASE);

    expect(result.pageCount).toBe(0);
    expect(missingRequiredAssets(dist)).toEqual([]);
    expect(result.failures.length).toBeGreaterThan(0);
    expect(result.failures.some((f) => /zero HTML pages/i.test(f.message))).toBe(true);
  });

  it("fails a dist that contains only non-HTML files", () => {
    const dist = track(makeDist({ pages: { "robots.txt": "User-agent: *" } }));

    const result = auditDist(dist, BASE);

    expect(result.pageCount).toBe(0);
    expect(result.failures.some((f) => /zero HTML pages/i.test(f.message))).toBe(true);
  });

  it("passes a minimal one-page dist, preserving the single-item boundary", () => {
    const dist = track(
      makeDist({
        pages: { "index.html": `<a href="/codeArbiter/favicon.svg">icon</a>` },
      }),
    );

    const result = auditDist(dist, BASE);

    expect(result.pageCount).toBe(1);
    expect(result.checked).toBe(1);
    expect(result.failures).toEqual([]);
    expect(missingRequiredAssets(dist)).toEqual([]);
  });
});

describe("missingRequiredAssets", () => {
  const dists: string[] = [];

  afterAll(() => {
    for (const d of dists) rmSync(d, { recursive: true, force: true });
  });

  const cases: Array<{
    name: string;
    options: Parameters<typeof makeDist>[0];
    expected: string[];
  }> = [
    {
      name: "a complete build reports nothing missing",
      options: {},
      expected: [],
    },
    {
      name: "a missing favicon is reported",
      options: { favicon: false },
      expected: ["dist/favicon.svg"],
    },
    {
      name: "a missing _astro directory is reported as a missing logo",
      options: { astroDir: false },
      expected: ["dist/_astro/logo.*.svg"],
    },
    {
      name: "an _astro directory with no logo asset is reported",
      options: { logoName: null },
      expected: ["dist/_astro/logo.*.svg"],
    },
    {
      name: "an unhashed logo.svg does not satisfy the hashed-logo pin",
      options: { logoName: "logo.svg" },
      expected: ["dist/_astro/logo.*.svg"],
    },
    {
      name: "a differently named hashed svg does not satisfy the hashed-logo pin",
      options: { logoName: "brand.abc123.svg" },
      expected: ["dist/_astro/logo.*.svg"],
    },
    {
      name: "both assets missing are reported together",
      options: { favicon: false, astroDir: false },
      expected: ["dist/favicon.svg", "dist/_astro/logo.*.svg"],
    },
  ];

  for (const { name, options, expected } of cases) {
    it(name, () => {
      const dist = makeDist(options);
      dists.push(dist);
      expect(missingRequiredAssets(dist)).toEqual(expected);
    });
  }
});
