/** concepts-content.test.ts — Feature Forge content guard.
 *
 * Guards the forge story (preview -> stable, promoted by real-world evidence) —
 * a load-bearing claim of the docs. After the Concepts split (AC-08) it lives in
 * concepts/feature-forge.md, with concepts.md as a router index. These guard that
 * the story survives in its own page and that the index still links to it; a
 * silent deletion or reword that drops it should fail.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const DOCS = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "src",
  "content",
  "docs",
);

const forge = readFileSync(join(DOCS, "concepts", "feature-forge.md"), "utf8");
const index = readFileSync(join(DOCS, "concepts.md"), "utf8");

describe("Feature Forge content (concepts split)", () => {
  it("the feature-forge page is titled 'The Feature Forge'", () => {
    expect(forge).toMatch(/^title:\s*The Feature Forge\s*$/m);
  });

  it("describes evidence-driven promotion to stable", () => {
    expect(forge).toMatch(/promoted to\b/);
    expect(forge).toContain("stable");
    expect(forge.toLowerCase()).toContain("evidence");
  });

  it("the concepts index routes to the feature-forge page", () => {
    expect(index).toContain("/concepts/feature-forge/");
  });
});
