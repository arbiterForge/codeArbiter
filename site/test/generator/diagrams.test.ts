/** diagrams.test.ts — AC-9 diagram-asset guards.
 *
 * Asserts the concept diagrams exist, each carries an in-SVG <title> element
 * (accessibility), and each is referenced by at least one page file under
 * site/src/. Guards against a deleted asset, a stripped title, or an orphaned
 * diagram that no page shows.
 *
 * Diagrams have a single source of truth: site/public/diagrams. Pages serve
 * them from there via the base-safe /codeArbiter/diagrams/<name>.svg literal
 * (see diagram-href-convention.test.ts); md/mdx can't import an asset, so there
 * is no src/assets copy to keep in sync.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SITE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DIAGRAM_DIR = join(SITE_ROOT, "public", "diagrams");
const SRC_DIR = join(SITE_ROOT, "src");

const DIAGRAMS = ["lane-flow.svg", "two-axis-model.svg", "gate-model.svg", "four-tier-map.svg", "provenance-drift-flow.svg"];

/** Recursively read every page-ish source file under src/ as one big string. */
function readAllPageSources(dir: string): string {
  let buf = "";
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      buf += readAllPageSources(full);
    } else if (/\.(md|mdx|astro)$/.test(entry)) {
      buf += readFileSync(full, "utf8");
    }
  }
  return buf;
}

const allPageSources = readAllPageSources(SRC_DIR);

describe("concept diagrams (AC-9)", () => {
  for (const name of DIAGRAMS) {
    describe(name, () => {
      const path = join(DIAGRAM_DIR, name);

      it("source SVG exists", () => {
        expect(existsSync(path)).toBe(true);
      });

      it("contains an in-SVG <title> element (accessibility)", () => {
        const svg = readFileSync(path, "utf8");
        expect(svg).toMatch(/<title\b[^>]*>[^<]+<\/title>/);
      });

      it("is referenced by at least one page under src/", () => {
        // Pages reference the diagram by file name (any href/src form).
        expect(allPageSources).toContain(name);
      });
    });
  }
});
