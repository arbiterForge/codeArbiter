import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const search = readFileSync(resolve(siteRoot, "src/components/Search.astro"), "utf8");
const config = readFileSync(resolve(siteRoot, "astro.config.mjs"), "utf8");
const theme = readFileSync(resolve(siteRoot, "src/styles/theme.css"), "utf8");

describe("inline Pagefind search", () => {
  it("remains registered as the Starlight search override", () => {
    expect(config).toMatch(/Search:\s*["']\.\/src\/components\/Search\.astro["']/);
  });

  it("implements the labelled WAI-ARIA combobox contract", () => {
    expect(search).toContain('role="search"');
    expect(search).toContain('type="search"');
    expect(search).toContain('role="combobox"');
    expect(search).toContain('aria-autocomplete="list"');
    expect(search).toContain('aria-controls="ca-search-listbox"');
    expect(search).toContain('aria-activedescendant');
    expect(search).toContain('id="ca-search-listbox"');
    expect(search).toContain('role="listbox"');
    expect(search).toMatch(/setAttribute\("role",\s*"option"\)/);
    expect(search).toMatch(/aria-label="[^"]+"/);
    expect(search).toContain('aria-expanded="false"');
    expect(search).toContain('aria-live="polite"');
  });

  it("supports arrow navigation, activation, and dismissal", () => {
    expect(search).toContain('"ArrowDown"');
    expect(search).toContain('"ArrowUp"');
    expect(search).toContain('"Enter"');
    expect(search).toContain('"Escape"');
    expect(search).toMatch(/setAttribute\("aria-activedescendant"/);
  });

  it("loads Pagefind from the deployment base and visibly marks virtual focus", () => {
    expect(search).toContain("import.meta.env.BASE_URL");
    expect(search).toMatch(/\/pagefind\/pagefind\.js/);
    expect(theme).toMatch(
      /\.ca-search__result-link\[aria-selected="true"\]\s*\{[^}]*outline:\s*2px solid var\(--ca-gold\)/,
    );
  });
});
