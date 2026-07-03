/** paraphrase-lint.test.ts — structural enforcement of the spec's paraphrase ban.
 *
 * For every curated companion file under `site/src/curated/`, assert that no
 * 12-word shingle (whitespace/case normalized) appears verbatim in both the
 * curated body and its entity's plugin source body. The embed already carries
 * the source verbatim — curated prose must describe it, not restate it.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { splitFrontmatter } from "../../scripts/generator/split-frontmatter";
import { parseFields } from "../../scripts/generator/parse-fields";

const here = dirname(fileURLToPath(import.meta.url));
const siteRoot = join(here, "..", ".."); // site/
const repoRoot = join(siteRoot, ".."); // repo root
const curatedRoot = join(siteRoot, "src", "curated");

const TYPE_DIRS = ["commands", "skills", "agents"] as const;
const SHINGLE_SIZE = 12;

function normalizeWords(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[`*_#>|[\](){}]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function shingles(words: string[], n: number): Set<string> {
  const set = new Set<string>();
  for (let i = 0; i + n <= words.length; i++) {
    set.add(words.slice(i, i + n).join(" "));
  }
  return set;
}

/** Resolve a curated `entity` (`<type-dir>/<basename>`) to its plugin source path. */
function resolveSourcePath(entity: string): string {
  const [typeDir, basename] = entity.split("/");
  if (typeDir === "skills") {
    return join(repoRoot, "plugins", "ca", "skills", basename, "SKILL.md");
  }
  return join(repoRoot, "plugins", "ca", typeDir, `${basename}.md`);
}

function findCuratedFiles(): string[] {
  const files: string[] = [];
  for (const dir of TYPE_DIRS) {
    const full = join(curatedRoot, dir);
    if (!existsSync(full)) continue;
    for (const entry of readdirSync(full)) {
      if (entry.endsWith(".md")) files.push(join(full, entry));
    }
  }
  return files;
}

describe("paraphrase lint — curated content never quotes its own source verbatim", () => {
  const files = findCuratedFiles();

  it("found at least one curated file to check", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  for (const filePath of files) {
    it(`${filePath} carries no ${SHINGLE_SIZE}-word shingle from its source`, () => {
      const raw = readFileSync(filePath, "utf-8").replace(/\r\n/g, "\n");
      const { frontmatter, body } = splitFrontmatter(raw);
      expect(frontmatter).not.toBeNull();
      const fields = parseFields(frontmatter as string);
      const entity = fields.entity;
      expect(entity).toBeTruthy();

      const sourcePath = resolveSourcePath(entity);
      expect(existsSync(sourcePath)).toBe(true);
      const sourceRaw = readFileSync(sourcePath, "utf-8").replace(/\r\n/g, "\n");
      const { body: sourceBody } = splitFrontmatter(sourceRaw);

      const sourceShingles = shingles(normalizeWords(sourceBody), SHINGLE_SIZE);
      const curatedShingles = shingles(normalizeWords(body), SHINGLE_SIZE);

      const overlap = [...curatedShingles].filter((s) => sourceShingles.has(s));
      expect(overlap).toEqual([]);
    });
  }
});
