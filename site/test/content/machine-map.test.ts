/** machine-map.test.ts - every hand-authored page's "In the machine" line names real pages and parts. */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const docs = join(siteRoot, "src", "content", "docs");
const map = JSON.parse(readFileSync(join(siteRoot, "src", "data", "machine-map.json"), "utf8")) as { pages: Record<string, string[]> };
const parts = JSON.parse(readFileSync(join(siteRoot, "scripts", "machine", "machine-data", "parts.json"), "utf8")) as Record<string, unknown>;

const pageExists = (id: string) => [".md", ".mdx"].some((ext) => existsSync(join(docs, `${id}${ext}`)));

describe("machine map", () => {
  it("maps only pages that exist, and only hand-authored ones", () => {
    const ids = Object.keys(map.pages);
    expect(ids.length).toBeGreaterThan(20);
    expect(ids.filter((id) => !pageExists(id))).toEqual([]);
    expect(ids.filter((id) => /^reference\/(?:commands|skills|agents)\//.test(id) || id.startsWith("academy/"))).toEqual([]);
    expect(ids).not.toContain("concepts/machine");
  });

  it("names only machine parts that exist, a few per page, without repeats", () => {
    for (const [id, list] of Object.entries(map.pages)) {
      expect(list.filter((part) => !(part in parts)), id).toEqual([]);
      expect(list.length, id).toBeGreaterThan(0);
      expect(list.length, id).toBeLessThanOrEqual(4);
      expect(new Set(list).size, id).toBe(list.length);
    }
  });

  it("is rendered by the page orientation strip with machine frames and part links", () => {
    const context = readFileSync(join(siteRoot, "src", "components", "PageContext.astro"), "utf8");
    expect(context).toContain("machine-map.json");
    expect(context).toContain("ca-page-context__machine");
    expect(context).toContain("partById(id)");
    expect(context).toContain("framePath(part.shape)");
  });
});
