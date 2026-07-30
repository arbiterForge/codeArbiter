import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const docsRoot = join(process.cwd(), "src", "content", "docs");

function contentFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return contentFiles(path);
    return [".md", ".mdx"].includes(extname(entry.name)) ? [path] : [];
  });
}

function frontmatter(source: string): string {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  return match?.[1] ?? "";
}

describe("hand-authored learning contract", () => {
  const handPages = contentFiles(docsRoot).filter((path) => {
    const route = relative(docsRoot, path).replaceAll("\\", "/");
    return !route.startsWith("reference/")
      && route !== "index.mdx"
      && route !== "changelog.md";
  });

  it("gives every hand-authored page an outcome, prerequisite context, and proof", () => {
    const failures = handPages.flatMap((path) => {
      const metadata = frontmatter(readFileSync(path, "utf8"));
      const missing = ["journey:", "level:", "time:", "outcome:", "prerequisites:", "proof:"]
        .filter((field) => !metadata.includes(field));
      return missing.length
        ? [`${relative(docsRoot, path)}: ${missing.join(", ")}`]
        : [];
    });
    expect(failures).toEqual([]);
  });

  it("keeps hand-authored page descriptions specific enough to orient search results", () => {
    const failures = handPages.flatMap((path) => {
      const metadata = frontmatter(readFileSync(path, "utf8"));
      const description = metadata.match(/^description:\s*["']?(.+?)["']?\s*$/m)?.[1] ?? "";
      return description.length >= 45
        ? []
        : [`${relative(docsRoot, path)}: ${description.length} characters`];
    });
    expect(failures).toEqual([]);
  });
});
