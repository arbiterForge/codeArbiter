import { existsSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const repoRoot = resolve(process.cwd(), "..");
const readme = readFileSync(join(repoRoot, "README.md"), "utf8");

describe("professional repository README", () => {
  it("leads with the rendered product artwork instead of the legacy SVG banner", () => {
    const hero = join(repoRoot, "docs", "readme-hero.webp");

    expect(readme).toContain('src="docs/readme-hero.webp"');
    expect(readme).not.toContain('src="docs/banner.svg"');
    expect(existsSync(hero)).toBe(true);
    expect(statSync(hero).size).toBeGreaterThan(50_000);
  });

  it("routes a newcomer into the same novice-to-power-user journey as the site", () => {
    for (const href of [
      "getting-started/choose-your-host/",
      "getting-started/install/",
      "getting-started/quickstart/",
      "learn/",
      "concepts/",
      "reference/",
    ]) {
      expect(readme).toContain(href);
    }

    expect(readme.indexOf("## Get running")).toBeLessThan(readme.indexOf("## How governance works"));
  });

  it("uses rendered Feature Forge atmosphere while linking the source-backed live catalog", () => {
    expect(readme).toContain('src="docs/feature-forge.webp"');
    expect(readme).not.toContain('src="docs/feature-forge.svg"');
    expect(readme).toContain("feature-forge/whats-in-the-forge/");
  });

  it("keeps detailed catalogs collapsible so the README remains an adoption surface", () => {
    expect(readme).toContain("<summary><strong>All 40 Claude Code commands</strong></summary>");
    expect(readme).toContain("The docs are the operating manual");
  });

  it("keeps Pi tag selection and override authority honest at the repository entry point", () => {
    expect(readme).toContain("git ls-remote --tags --refs");
    expect(readme).toContain('"ca-pi-v*"');
    expect(readme).toContain("H-18");
    expect(readme).not.toContain("bypass of one gate or hard rule");
  });
});
