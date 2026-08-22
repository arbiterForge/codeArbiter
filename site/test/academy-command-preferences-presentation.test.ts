import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = join(import.meta.dirname, "..");
const component = readFileSync(join(siteRoot, "src", "components", "AcademyCommandPreferences.astro"), "utf8");
const styles = readFileSync(join(siteRoot, "src", "styles", "academy.css"), "utf8");
const preferenceRule = styles.match(/\.academy-command-preferences \{([^}]*)\}/)?.[1] ?? "";

describe("Academy command preference presentation", () => {
  it("keeps the setup explanation and choice groups in the original stacked hierarchy", () => {
    expect(component).toContain("Use your setup");
    expect(component).toContain("Choose an operating system or CodeArbiter host to focus every command example in this lesson. Your choices stay on this device.");
    expect(preferenceRule).toContain("display: grid;");
    expect(preferenceRule).toContain("background: var(--ca-bg-raised);");
  });

  it("uses native legends above each choice row", () => {
    expect(component).toContain('<fieldset class="academy-command-preferences__group">');
    expect(component).toContain("<legend>Operating system</legend>");
    expect(component).toContain("<legend>CodeArbiter host</legend>");
  });

  it("gives every operating-system and host choice the same stable control size", () => {
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*inline-size: 100%;/);
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*block-size: 2\.75rem;/);
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*justify-content: center;/);
  });

  it("keeps each legend above one aligned responsive control grid", () => {
    expect(styles).toMatch(/\.academy-command-preferences__group \{[^}]*display: grid;/);
    expect(styles).toMatch(/\.academy-command-preferences__group div \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(auto-fit, minmax\(7rem, 1fr\)\);/);
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*inline-size: 100%;/);
    expect(styles).toMatch(/\.academy-command-preferences__group div button \+ button \{ margin-block-start: 0; \}/);
  });
});
