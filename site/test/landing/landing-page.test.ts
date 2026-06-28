/**
 * TDD Phase 1 obligations — bespoke landing page (AC 6, 7, 8, 12, 15, 16, 19).
 *
 * These tests read the landing source files because the full Astro build is not
 * run inside vitest.  The "landing source" is the union of:
 *   - src/content/docs/index.mdx   (frontmatter + MDX body)
 *   - src/components/GateCatchTerminal.astro
 *   - src/components/ForgeShowcase.astro
 *   - src/styles/landing.css
 *
 * Source-level assertions are reliable here because:
 *   - AC 6/7/8/12/15/16: structural/markup obligations are authored in the above
 *     files and render directly to the built HTML without transformation.
 *   - AC 19: em-dash cap is a source-level prose check by spec definition.
 *
 * The design-quality-reviewer (AC-11) is dispatched separately as a visual gate.
 */

import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(__dirname, "../../");

function readSrc(rel: string): string {
  return readFileSync(path.join(siteRoot, rel), "utf8");
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const indexMdx = readSrc("src/content/docs/index.mdx");
const terminalCmp = readSrc("src/components/GateCatchTerminal.astro");
const installCmp = readSrc("src/components/InstallTerminal.astro");
const landingCss = readSrc("src/styles/landing.css");

/** Combined source of the landing page artifacts. The Feature Forge showcase
 *  moved off the home page into its own section — see feature-forge-content.test.ts. */
const landingSrc = indexMdx + "\n" + terminalCmp + "\n" + installCmp;

// ---------------------------------------------------------------------------
// AC-6: Bespoke landing — stock CardGrid replaced
// ---------------------------------------------------------------------------

describe("AC-6: bespoke landing replaces stock CardGrid", () => {
  it("index.mdx does not contain the stock <CardGrid> component from Starlight", () => {
    expect(indexMdx).not.toMatch(/<CardGrid>/);
  });

  it("landing source contains the gate-catch terminal (ca-terminal)", () => {
    expect(landingSrc).toContain("ca-terminal");
  });

  it("index.mdx contains the bespoke hero section (ca-hero)", () => {
    expect(indexMdx).toContain("ca-hero");
  });
});

// ---------------------------------------------------------------------------
// AC-7: prefers-reduced-motion honored for terminal animation
// ---------------------------------------------------------------------------

describe("AC-7: terminal honors prefers-reduced-motion", () => {
  it("theme.css contains a prefers-reduced-motion media query that collapses animation", () => {
    const themeCss = readSrc("src/styles/theme.css");
    expect(themeCss).toContain("prefers-reduced-motion");
    expect(themeCss).toContain("animation: none");
  });

  it("terminal lines carry the ca-terminal__line class (so the reduced-motion rule applies)", () => {
    expect(terminalCmp).toContain("ca-terminal__line");
  });

  it("theme.css reduced-motion block sets opacity: 1 so all lines are visible statically", () => {
    const themeCss = readSrc("src/styles/theme.css");
    expect(themeCss).toMatch(/prefers-reduced-motion[\s\S]*?opacity:\s*1/);
  });
});

// ---------------------------------------------------------------------------
// AC-8: Terminal transcript is real DOM text
// ---------------------------------------------------------------------------

describe("AC-8: terminal transcript is real DOM text, not canvas/image", () => {
  it("terminal component does not use <canvas> elements", () => {
    expect(terminalCmp).not.toContain("<canvas");
  });

  it("terminal component does not use <img> elements for the transcript", () => {
    // The terminal transcript itself must not be an image
    // (img is allowed in diagrams but not inside the terminal body)
    const bodySection = terminalCmp.match(/ca-terminal__body[\s\S]*/)?.[0] ?? "";
    expect(bodySection).not.toContain("<img");
  });

  it("terminal contains visible command text as plain DOM text", () => {
    expect(terminalCmp).toMatch(/git commit|ca:commit/i);
  });

  it("terminal body has role=list for screen-reader grouping", () => {
    expect(terminalCmp).toContain('role="list"');
  });

  it("terminal lines have role=listitem", () => {
    expect(terminalCmp).toContain('role="listitem"');
  });

  it("terminal region has an aria-label", () => {
    expect(terminalCmp).toMatch(/aria-label="[^"]+"/);
  });
});

// ---------------------------------------------------------------------------
// AC-16: Above-the-fold: what / why / first command + single primary CTA
// ---------------------------------------------------------------------------

describe("AC-16: above-fold hero answers what/why/first command + one primary CTA", () => {
  it("hero tagline (the 'why') is present in the bespoke hero body", () => {
    // The landing moved off Starlight's splash `hero:` frontmatter to a bespoke
    // two-column hero in the MDX body (doc template + sidebar). The tagline now
    // lives in a .ca-landing__tagline element, not frontmatter.
    expect(indexMdx).toContain("ca-landing__tagline");
    expect(indexMdx).toMatch(/real stops/i);
  });

  it("exactly one primary CTA exists in the hero", () => {
    const primaryMatches = indexMdx.match(/ca-landing__cta--primary/g);
    expect(primaryMatches).not.toBeNull();
    expect(primaryMatches!.length).toBe(1);
  });

  it("primary CTA uses a base-safe page-relative link (no hardcoded base, no leading slash)", () => {
    // The hero CTAs are raw <a href> in the MDX body. A page-relative `./…`
    // link resolves against the page URL (served at /codeArbiter/) and
    // auto-corrects if the base changes — unlike a leading-slash `/…` link,
    // which would 404 under the /codeArbiter base on GH Pages, or a hardcoded
    // `/codeArbiter/…`, which silently desyncs if the base ever changes.
    expect(indexMdx).toMatch(/href="\.\/getting-started\/install\//);
    expect(indexMdx).not.toMatch(/href="\/codeArbiter/);
  });

  it("first command is shown in the hero section", () => {
    // The hero now leads with the install commands (the new user's actual first
    // commands), rendered in the animated install terminal. The old
    // /ca:feature|/ca:fix|/ca:commit sample box was removed in favor of this
    // get-it-running demo.
    expect(landingSrc).toMatch(/\/plugin install/);
  });

  it("hero body answers 'what' (the orchestrator description)", () => {
    expect(indexMdx).toMatch(/orchestrat|gated|lane/i);
  });
});

// ---------------------------------------------------------------------------
// Install demo: the get-it-running terminal replaced the sample-command box
// ---------------------------------------------------------------------------

describe("install demo terminal (get-it-running below the fold)", () => {
  it("index.mdx imports and renders the InstallTerminal component", () => {
    expect(indexMdx).toContain("InstallTerminal");
  });

  it("the install title and statusline subtext are present above the demo", () => {
    expect(indexMdx).toMatch(/Get the Arbiter on Your Case/);
    expect(indexMdx).toMatch(/wires in the statusline/i);
  });

  it("the old sample-command box was removed", () => {
    expect(indexMdx).not.toContain("ca-hero__first-command");
  });

  it("the install terminal shows both install commands", () => {
    expect(installCmp).toContain("/plugin marketplace add arbiterForge/codeArbiter");
    expect(installCmp).toContain("/plugin install ca@codearbiter");
  });

  it("the install terminal runs /ca:statusline as the third command", () => {
    expect(installCmp).toContain("/ca:statusline");
  });

  it("the real rendered statusline sits below the terminal (single-source asset)", () => {
    // The bar is shown below the terminal in index.mdx, using the canonical
    // statusline.png — the same asset the statusline guide and README serve —
    // via the base-safe root-absolute literal sanctioned for .mdx pages.
    expect(indexMdx).toContain("ca-hero__statusline");
    expect(indexMdx).toContain("/codeArbiter/diagrams/statusline.png");
  });

  it("the install terminal reuses the animated terminal contract (ca-terminal lines)", () => {
    expect(installCmp).toContain("ca-terminal__line");
    expect(installCmp).toContain('role="list"');
    expect(installCmp).toMatch(/aria-label="[^"]+"/);
  });
});

// ---------------------------------------------------------------------------
// AC-19: Em-dash cap (≤3 per page, ≤1 per paragraph) on prose
// ---------------------------------------------------------------------------

describe("AC-19: em-dash cap on landing prose", () => {
  /**
   * Strips frontmatter, code blocks, HTML/JSX tags, and import statements
   * so the cap applies only to hand-written prose, per spec.
   */
  function extractProse(src: string): string {
    let text = src.replace(/^---[\s\S]*?---\n/, "");
    text = text.replace(/```[\s\S]*?```/g, "");
    text = text.replace(/`[^`\n]*`/g, "");
    text = text.replace(/<[^>]+>/g, " ");
    text = text.replace(/^import\s+.*$/gm, "");
    return text;
  }

  it("index.mdx contains ≤3 em-dashes in hand-written prose", () => {
    const prose = extractProse(indexMdx);
    const emDashes = (prose.match(/—/g) ?? []).length;
    expect(emDashes).toBeLessThanOrEqual(3);
  });

  it("no paragraph in index.mdx prose has more than one em-dash", () => {
    const prose = extractProse(indexMdx);
    const paragraphs = prose.split(/\n{2,}/);
    for (const para of paragraphs) {
      const count = (para.match(/—/g) ?? []).length;
      expect(count).toBeLessThanOrEqual(1);
    }
  });

  it("GateCatchTerminal.astro prose contains ≤3 em-dashes", () => {
    const prose = extractProse(terminalCmp);
    const emDashes = (prose.match(/—/g) ?? []).length;
    expect(emDashes).toBeLessThanOrEqual(3);
  });

  it("InstallTerminal.astro prose contains ≤3 em-dashes", () => {
    const prose = extractProse(installCmp);
    const emDashes = (prose.match(/—/g) ?? []).length;
    expect(emDashes).toBeLessThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// Lane-flow diagram embedded in landing
// ---------------------------------------------------------------------------

describe("lane-flow diagram embedded in landing", () => {
  it("lane-flow.svg asset exists", () => {
    const svgPath = path.join(siteRoot, "public/diagrams/lane-flow.svg");
    expect(existsSync(svgPath)).toBe(true);
  });

  it("index.mdx references the lane-flow diagram", () => {
    expect(indexMdx).toContain("lane-flow");
  });
});
