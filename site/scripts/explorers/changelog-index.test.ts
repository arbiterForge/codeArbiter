import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { loadChangelogIndex, parseChangelogPage } from "./changelog-index";

describe("the changelog index", () => {
  it("reads versioned and date-grouped releases with their entry counts by type", () => {
    const releases = parseChangelogPage([
      "Intro.",
      "",
      "## [Unreleased]",
      "",
      "## [3.8.9] - 2026-11-12",
      "",
      "### Fixed",
      "",
      "- One.",
      "- Two, which",
      "  wraps.",
      "",
      "### Added",
      "",
      "- Three.",
      "",
      "## [2.0.0] — 2026-06-10 — Native Claude Code plugin",
      "",
      "### Fixed",
      "- Four.",
      "",
      "```",
      "## [9.9.9] - not a heading",
      "- not an entry",
      "```",
      "",
      "## [2026-05-13] — copyright standards, /decompose, H-08 hook fix",
      "",
      "### Added",
      "- Five.",
      "",
      "## Maintenance notes",
      "",
      "- Not a release entry.",
    ].join("\n"));
    expect(releases.map((r) => [r.label, r.version, r.date, r.total])).toEqual([
      ["3.8.9", "3.8.9", "2026-11-12", 3],
      ["2.0.0", "2.0.0", "2026-06-10", 1],
      ["2026-05-13", null, "2026-05-13", 1],
    ]);
    expect(releases[0].counts).toEqual({ Fixed: 2, Added: 1 });
    expect(releases[1].title).toBe("Native Claude Code plugin");
    expect(releases[2].title).toBe("copyright standards, /decompose, H-08 hook fix");
  });

  it("gives each release the id Starlight gives its heading, counting every heading before it", () => {
    const [first, second] = parseChangelogPage("## [1.0.1] - 2026-06-11\n\n### Fixed\n\n- a\n\n## [1.0.0] — 2026-06-10 — First\n\n### Fixed\n\n- b\n");
    expect(first.id).toBe("101---2026-06-11");
    expect(second.id).toBe("100--2026-06-10--first");
  });

  it("covers every release in the shipped changelog", () => {
    const releases = loadChangelogIndex();
    expect(releases.length).toBeGreaterThan(150);
    expect(releases.every((r) => r.date !== null)).toBe(true);
    expect(releases.reduce((sum, r) => sum + r.total, 0)).toBeGreaterThan(500);
  });

  const built = resolve(import.meta.dirname, "..", "..", "dist", "changelog", "index.html");
  it.skipIf(!existsSync(built))("links only to release headings that exist on the built page", () => {
    const ids = new Set([...readFileSync(built, "utf8").matchAll(/<h2 id="([^"]+)"/g)].map(([, id]) => id));
    const missing = loadChangelogIndex().filter((r) => !ids.has(r.id)).map((r) => `${r.label} -> ${r.id}`);
    expect(missing).toEqual([]);
  });
});
