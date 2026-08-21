import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = join(import.meta.dirname, "..");
const component = readFileSync(join(siteRoot, "src", "components", "AcademyCommandPreferences.astro"), "utf8");
const styles = readFileSync(join(siteRoot, "src", "styles", "academy.css"), "utf8");
const preferenceRule = styles.match(/\.academy-command-preferences \{([^}]*)\}/)?.[1] ?? "";

describe("Academy command preference presentation", () => {
  it("keeps the selector as a compact lesson toolbar instead of a raised form panel", () => {
    expect(component).toContain("Show command examples for");
    expect(preferenceRule).toContain("border-block: 1px solid var(--ca-line);");
    expect(preferenceRule).not.toContain("background: var(--ca-bg-raised);");
  });

  it("keeps each setup group label and its choices on the same compact row when space allows", () => {
    expect(component).toContain('role="group" aria-labelledby="academy-operating-system-label"');
    expect(component).toContain('role="group" aria-labelledby="academy-codearbiter-host-label"');
    expect(styles).toMatch(/\.academy-command-preferences__group \{[\s\S]*align-items: center;/);
    expect(styles).toMatch(/\.academy-command-preferences__label \{[\s\S]*width: auto;/);
  });

  it("gives every operating-system and host choice the same stable control width", () => {
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*inline-size: 7rem;/);
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*block-size: 2\.35rem;/);
    expect(styles).toMatch(/\.academy-command-preferences button \{[\s\S]*justify-content: center;/);
  });
});
