/** feature-forge-content.test.ts — Feature Forge section content guard.
 *
 * The Feature Forge moved out of the home page (the old ForgeShowcase) and out
 * of Concepts into its own top-level section: an overview, the live "what's in
 * the forge" catalog, and a how-to. These guards consolidate what used to live
 * in concepts-content.test.ts and the landing test's AC-12/AC-15:
 *   - the load-bearing forge story survives (preview -> stable, evidence-promoted);
 *   - the catalog is data-driven from forge-status.ts, so it cannot drift from
 *     the reference preview badges;
 *   - --farm is documented in context, not free-floating.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FORGE_FEATURES } from "../../scripts/generator/forge-status";

const DOCS = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "src",
  "content",
  "docs",
);
const FORGE = join(DOCS, "feature-forge");

const overview = readFileSync(join(FORGE, "overview.md"), "utf8");
const whatsIn = readFileSync(join(FORGE, "whats-in-the-forge.mdx"), "utf8");
const usingPreview = readFileSync(join(FORGE, "using-preview-features.md"), "utf8");
const concepts = readFileSync(join(DOCS, "concepts.md"), "utf8");

describe("Feature Forge section (its own top-level group)", () => {
  it("overview is titled 'What Is the Feature Forge'", () => {
    expect(overview).toMatch(/^title:\s*What Is the Feature Forge\s*$/m);
  });

  it("overview describes evidence-driven promotion to stable", () => {
    expect(overview).toMatch(/promoted to\b/);
    expect(overview).toContain("stable");
    expect(overview.toLowerCase()).toContain("evidence");
  });

  it("overview embeds the two-axis-model diagram", () => {
    expect(overview).toContain("two-axis-model");
  });

  it("the concepts index no longer routes to a feature-forge concept page", () => {
    expect(concepts).not.toContain("/concepts/feature-forge/");
  });

  it("the catalog is data-driven from forge-status.ts (cannot drift from the badges)", () => {
    expect(whatsIn).toContain("FORGE_FEATURES");
    expect(whatsIn).toMatch(/from\s+['"][^'"]*forge-status['"]/);
  });

  it("--farm is documented in context within the Feature Forge section", () => {
    expect(usingPreview).toContain("--farm");
  });

  it("the how-to covers opt-in and dormant behavior", () => {
    expect(usingPreview.toLowerCase()).toContain("opt-in");
    expect(usingPreview.toLowerCase()).toContain("dormant");
  });
});

describe("Feature Forge catalog explains each feature, not just lists it", () => {
  it("each catalog card renders the feature's summary", () => {
    // The summary field is required on ForgeFeature and rendered in the card,
    // so the at-a-glance list is self-explanatory rather than a bare lookup.
    expect(whatsIn).toContain("{f.summary}");
    for (const f of FORGE_FEATURES) {
      expect(f.summary.length).toBeGreaterThan(0);
    }
  });

  it("every field the card renders is present (no 'undefined' leaks into the UI)", () => {
    // The card renders optIn and helpGraduate for every feature, and falls back
    // to href for a feature with no /ca: command (e.g. ca-sandbox). Guard them
    // so an emptied field is caught here, not seen as "Opt in: undefined" live.
    for (const f of FORGE_FEATURES) {
      expect(f.optIn.length).toBeGreaterThan(0);
      expect(f.helpGraduate.length).toBeGreaterThan(0);
      if (!f.command) {
        expect(f.href && f.href.length > 0).toBeTruthy();
      }
    }
  });

  it("has a hand-authored 'How Each Preview Works' deep-dive section", () => {
    expect(whatsIn).toContain("## How Each Preview Works");
  });

  it("every Forge feature has a matching deep-dive subsection (prose cannot silently drift)", () => {
    for (const f of FORGE_FEATURES) {
      expect(whatsIn).toContain(`### ${f.name}`);
    }
  });
});
