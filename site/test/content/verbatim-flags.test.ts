/** verbatim-flags.test.ts - no command-line flag in the built site is printed as a dash.
 *
 * Smart typography once turned `--no-verify`, `--ff-only` and `--dry-run` into dashes in prose
 * and in the hook-gates reference, so a reader copying them got the wrong flag. The markdown
 * processor no longer converts dashes (astro.config.mjs), and hook messages render as escaped
 * HTML. This scans the build that `npm test` makes first.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const dist = resolve(import.meta.dirname, "..", "..", "dist");

function pages(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === "pagefind" || entry.name === "workflow-atlas" ? [] : pages(path);
    return entry.name === "index.html" ? [path] : [];
  });
}

describe("verbatim flags in the built site", () => {
  it.skipIf(!existsSync(dist))("prints no flag as a dash", () => {
    const mangled = pages(dist).flatMap((file) => {
      const text = readFileSync(file, "utf8")
        .replace(/<(script|style|pre|code)\b[\s\S]*?<\/\1>/g, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/&#x2014;|&mdash;/g, "—")
        .replace(/&#x2013;|&ndash;/g, "–");
      return [...text.matchAll(/(?<![\w—–-])[—–](?=[a-z][a-z-]{1,20}\b)/g)].map(
        (match) => `${relative(dist, file)}: ${text.slice(Math.max(0, match.index - 20), match.index + 20)}`,
      );
    });
    expect(mangled).toEqual([]);
  });

  it("keeps dash conversion off in the markdown processor", () => {
    const config = readFileSync(resolve(import.meta.dirname, "..", "..", "astro.config.mjs"), "utf8");
    expect(config).toContain("smartypants: { dashes: false }");
  });
});
