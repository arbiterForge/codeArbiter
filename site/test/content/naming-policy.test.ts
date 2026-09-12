import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = join(import.meta.dirname, "..", "..");
const readSiteFile = (path: string): string => readFileSync(join(siteRoot, path), "utf8");

describe("approved naming policy", () => {
  it("uses codeArbiter in mutable codeArbiter-owned Academy framing", () => {
    const overview = readSiteFile("src/components/AcademyOverview.astro");
    const preferences = readSiteFile("src/components/AcademyCommandPreferences.astro");
    const generator = readSiteFile("scripts/generate-academy.ts");

    expect(overview).toContain("Build codeArbiter habits");
    expect(overview).not.toContain("Build CodeArbiter habits");
    expect(preferences).toContain("codeArbiter host");
    expect(preferences).not.toContain("CodeArbiter host");
    expect(generator).toContain("practice for the codeArbiter workflow");
    expect(generator).not.toContain("practice for the CodeArbiter workflow");
  });

  it("defines Feature Forge as the public navigation label without changing preview maturity", () => {
    const voice = readSiteFile("VOICE.md");
    const astroConfig = readSiteFile("astro.config.mjs");

    expect(voice).toMatch(/In navigation and\s+reader-facing copy it is labeled "Feature Forge"/);
    expect(voice).toMatch(/"preview" and "stable" are maturity\s+labels/);
    expect(voice).not.toContain('reader-facing copy it is labeled "Preview Features"');
    expect(astroConfig).toContain('label: "Feature Forge"');
  });
});
