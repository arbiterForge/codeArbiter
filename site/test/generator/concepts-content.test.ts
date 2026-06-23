/** concepts-content.test.ts — AC-13 content guard.
 *
 * Guards that concepts.md keeps the "The Feature Forge" section and its
 * evidence-promotion language. The forge story (preview -> stable, promoted by
 * real-world evidence) is a load-bearing claim of the docs; a silent deletion
 * or reword that drops it should fail.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const CONCEPTS = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "src",
  "content",
  "docs",
  "concepts.md",
);

const concepts = readFileSync(CONCEPTS, "utf8");

describe("concepts.md content (AC-13)", () => {
  it("contains the '## The Feature Forge' section heading", () => {
    expect(concepts).toContain("## The Feature Forge");
  });

  it("describes evidence-driven promotion to stable", () => {
    expect(concepts).toMatch(/promoted to\b/);
    expect(concepts).toContain("stable");
    expect(concepts.toLowerCase()).toContain("evidence");
  });
});
