/** diagram-href-convention.test.ts — Task 21 convention guard.
 *
 * Centralises the diagram-image href convention so the five references can't
 * drift back into four bespoke forms. The sanctioned forms are:
 *
 *   - In .md / .mdx pages (which cannot import an Astro component or read
 *     import.meta.env): the root-absolute, base-safe literal
 *       src="/codeArbiter/diagrams/<name>.svg"
 *     The base /codeArbiter is already owned by astro.config.mjs, so this adds
 *     no coupling the config doesn't already carry.
 *
 *   - In .astro components: import.meta.env.BASE_URL, the base-safe form for
 *     that context, e.g. src={`${baseUrl}/diagrams/<name>.svg`} — the config's
 *     documented pattern for component href props.
 *
 * Any other diagram <img src=...> form (bare "diagrams/x.svg", relative
 * "../diagrams/x.svg", a different hardcoded base) fails the guard.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, extname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "src");

/** Every page-ish source file under src/. */
function pageFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...pageFiles(full));
    else if (/\.(md|mdx|astro)$/.test(entry)) out.push(full);
  }
  return out;
}

// Matches any <img ... src=VALUE ...> where VALUE points at a /diagrams/*.svg,
// across both quoted ("...") and expression ({`...`}) attribute forms.
const DIAGRAM_IMG_SRC =
  /<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*diagrams\/[^"]*\.svg)"|\{`([^`]*diagrams\/[^`]*\.svg)`\})/gi;

/** Sanctioned forms, keyed by file extension. */
function isSanctioned(value: string, ext: string): boolean {
  if (ext === ".astro") {
    // import.meta.env.BASE_URL form: `${baseUrl}/diagrams/<name>.svg`
    return /^\$\{baseUrl\}\/diagrams\/[\w.-]+\.svg$/.test(value);
  }
  // .md / .mdx: the root-absolute base-safe literal.
  return /^\/codeArbiter\/diagrams\/[\w.-]+\.svg$/.test(value);
}

describe("diagram <img src> convention (Task 21)", () => {
  const files = pageFiles(SRC_DIR);
  const offenders: string[] = [];

  for (const file of files) {
    const ext = extname(file);
    const src = readFileSync(file, "utf8");
    let m: RegExpExecArray | null;
    DIAGRAM_IMG_SRC.lastIndex = 0;
    while ((m = DIAGRAM_IMG_SRC.exec(src)) !== null) {
      const value = m[1] ?? m[2] ?? "";
      if (!isSanctioned(value, ext)) {
        offenders.push(`${file.replace(SRC_DIR, "src")}  ->  src=${JSON.stringify(value)}`);
      }
    }
  }

  it("every diagram <img src> uses the sanctioned base-safe form", () => {
    expect(offenders).toEqual([]);
  });
});
