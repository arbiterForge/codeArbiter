import { existsSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const repoRoot = resolve(process.cwd(), "..");
const readme = readFileSync(join(repoRoot, "README.md"), "utf8");
const packageJson = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8"));
const codexManifest = JSON.parse(
  readFileSync(join(repoRoot, "plugins", "ca-codex", ".codex-plugin", "plugin.json"), "utf8"),
);

describe("professional repository README", () => {
  it("leads with the rendered product artwork instead of the legacy SVG banner", () => {
    const hero = join(repoRoot, "docs", "readme-hero.webp");
    const generator = join(process.cwd(), "scripts", "generate-readme-hero.ts");

    expect(readme).toContain('src="docs/readme-hero.webp"');
    expect(readme).not.toContain('src="docs/banner.svg"');
    expect(existsSync(hero)).toBe(true);
    expect(statSync(hero).size).toBeGreaterThan(50_000);
    expect(existsSync(generator)).toBe(true);
    const generatorSource = readFileSync(generator, "utf8");
    expect(generatorSource).toContain("hero-gates.webp");
    expect(generatorSource).toContain("gate-mark.svg");
    expect(packageJson.scripts["gen:readme-hero"]).toBe(
      "tsx scripts/generate-readme-hero.ts",
    );
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
    expect(readme).toContain("https://arbiterforge.github.io/codeArbiter/#proof");
    expect(readme).not.toContain("#direct-hook-proof");
  });

  it("uses rendered Feature Forge atmosphere while linking the source-backed live catalog", () => {
    expect(readme).toContain('src="docs/feature-forge.webp"');
    expect(readme).not.toContain('src="docs/feature-forge.svg"');
    expect(readme).toContain("feature-forge/whats-in-the-forge/");
  });

  it("keeps detailed catalogs collapsible so the README remains an adoption surface", () => {
    expect(readme).toContain("<summary><strong>All 38 Claude Code commands</strong></summary>");
    expect(readme).toContain("The docs are the operating manual");
  });

  it("keeps Pi tag selection and override authority honest at the repository entry point", () => {
    expect(readme).toContain("git ls-remote --tags --refs");
    expect(readme).toContain('"ca-pi-v*"');
    expect(readme).toContain("H-18");
    expect(readme).not.toContain("bypass of one gate or hard rule");
  });

  it("separates the current Codex adapter from the dated live-install evidence", () => {
    expect(readme).toContain(`currently ships \`ca-codex ${codexManifest.version}\``);
    expect(readme).toContain("dated end-to-end public-install record");
    expect(readme).toContain("`ca-codex 0.2.4` from release `v2.8.13`");
  });
});
