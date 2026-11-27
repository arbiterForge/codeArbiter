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

  // The build that `npm test` makes first: each mapped page must render exactly its parts as
  // chips, in order, so a page that stopped rendering the orientation strip fails here.
  const dist = join(siteRoot, "dist");
  const built = (id: string) => join(dist, id === "index" ? "" : id, "index.html");
  it.skipIf(!existsSync(join(dist, "index.html")))("renders each mapped page's parts as chips in the built site", () => {
    const wrong: string[] = [];
    for (const [id, list] of Object.entries(map.pages)) {
      const file = built(id);
      if (!existsSync(file)) {
        wrong.push(`${id}: not built`);
        continue;
      }
      const html = readFileSync(file, "utf8");
      const chips = [...html.matchAll(/class="ca-machine-chip"[^>]*href="[^"]*\/concepts\/machine\/#part-([^"]+)"/g)].map(([, part]) => part);
      if (JSON.stringify(chips) !== JSON.stringify(list)) wrong.push(`${id}: ${chips.join(",") || "none"} != ${list.join(",")}`);
    }
    expect(wrong).toEqual([]);
  });
});
