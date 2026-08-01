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
} from "../../scripts/link-audit/lib";

/** A fixed subpath base for the algorithm cases below.
 *
 * Deliberately NOT the site's live BASE. These cases exercise prefix stripping
 * and the outside-base classification, which only exist when the base is
 * non-empty; binding them to the live value made all nine disappear the moment
 * the site moved to an apex domain. The apex case (base "") is covered by its
 * own describe block at the end of this file. */
const TEST_BASE = "/codeArbiter";

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
    const result = resolveToDistFile("/codeArbiter/overview/", "/codeArbiter/x", distRoot, TEST_BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "overview", "index.html"),
    });
  });

  it("classifies a base-less root-absolute target as outside-base (regression: previously silently skipped)", () => {
    const result = resolveToDistFile("/overview/", "/codeArbiter/x", distRoot, TEST_BASE);
    expect(result).toEqual({ kind: "outside-base", normalizedPath: "/overview/" });
  });

  it("resolves a page-relative target against the page's URL directory", () => {
    const result = resolveToDistFile(
      "../concepts/",
      "/codeArbiter/guides/troubleshooting",
      distRoot,
      TEST_BASE,
    );
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "guides", "concepts", "index.html"),
    });
  });

  it("classifies a page-relative target that normalizes outside the base as outside-base", () => {
    const result = resolveToDistFile("../../overview/", "/codeArbiter/x", distRoot, TEST_BASE);
    expect(result?.kind).toBe("outside-base");
  });

  it("maps an extensionless route to its directory index", () => {
    const result = resolveToDistFile("/codeArbiter/overview", "/codeArbiter/x", distRoot, TEST_BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "overview", "index.html"),
    });
  });

  it("maps a file-like target (has an extension) verbatim", () => {
    const result = resolveToDistFile("/codeArbiter/favicon.svg", "/codeArbiter/x", distRoot, TEST_BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "favicon.svg"),
    });
  });

  it("returns null for an empty target", () => {
    expect(resolveToDistFile("", "/codeArbiter/x", distRoot, TEST_BASE)).toBeNull();
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
    const result = auditDist(dist, TEST_BASE);
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

    const result = auditDist(dist, TEST_BASE);

    expect(result.pageCount).toBe(0);
    expect(missingRequiredAssets(dist)).toEqual([]);
    expect(result.failures.length).toBeGreaterThan(0);
    expect(result.failures.some((f) => /zero HTML pages/i.test(f.message))).toBe(true);
  });

  it("fails a dist that contains only non-HTML files", () => {
    const dist = track(makeDist({ pages: { "robots.txt": "User-agent: *" } }));

    const result = auditDist(dist, TEST_BASE);

    expect(result.pageCount).toBe(0);
    expect(result.failures.some((f) => /zero HTML pages/i.test(f.message))).toBe(true);
  });

  it("passes a minimal one-page dist, preserving the single-item boundary", () => {
    const dist = track(
      makeDist({
        pages: { "index.html": `<a href="/codeArbiter/favicon.svg">icon</a>` },
      }),
    );

    const result = auditDist(dist, TEST_BASE);

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

describe("resolveToDistFile on an apex domain (base '')", () => {
  const distRoot = "/fake/dist";
  const APEX_BASE = "";

  // The site's live configuration. With an empty base every root-absolute
  // target is inside the base by definition, so the outside-base classification
  // that the subpath cases above exercise cannot fire here — that is the
  // behaviour change the apex move introduced, pinned rather than assumed.
  it("resolves a root-absolute target with no prefix to strip", () => {
    const result = resolveToDistFile("/overview/", "/x", distRoot, APEX_BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "overview", "index.html"),
    });
  });

  it("treats every root-absolute target as inside the base", () => {
    const result = resolveToDistFile("/anything/", "/x", distRoot, APEX_BASE);
    expect(result?.kind).toBe("resolved");
  });

  it("maps a file-like target verbatim", () => {
    const result = resolveToDistFile("/diagrams/x.svg", "/x", distRoot, APEX_BASE);
    expect(result).toEqual({ kind: "resolved", distFile: join(distRoot, "diagrams", "x.svg") });
  });

  it("cannot classify anything as outside-base, so escapes fall to the missing-file check", () => {
    // posix.normalize clamps at the root, so "../../../etc/passwd" from "/x"
    // becomes "/etc/passwd" — which is inside a base of "". The outside-base
    // classification is therefore INERT on an apex domain; what still catches a
    // bad target is auditDist's dangling-file check, not this guard. Pinned so
    // the next reader does not assume a protection that is no longer load-bearing.
    // "passwd" is extensionless, so it maps to a directory index like any route.
    const result = resolveToDistFile("../../../etc/passwd", "/x", distRoot, APEX_BASE);
    expect(result).toEqual({
      kind: "resolved",
      distFile: join(distRoot, "etc", "passwd", "index.html"),
    });
  });
});
