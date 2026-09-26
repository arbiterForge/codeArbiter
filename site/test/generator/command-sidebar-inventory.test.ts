import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generate } from "../../scripts/generator/generate";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const pluginDir = join(repoRoot, "plugins", "ca");
const curatedDir = join(repoRoot, "site", "src", "curated");
const roots: string[] = [];

afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

describe("production command sidebar inventory", () => {
  it("groups all 37 retained commands exactly once by validated visibility with alphabetical links", () => {
    const outDir = mkdtempSync(join(tmpdir(), "ca-command-sidebar-"));
    roots.push(outDir);

    const result = generate(pluginDir, outDir, undefined, curatedDir, true);
    const sidebar = JSON.parse(readFileSync(result.sidebarPath, "utf8"));
    const referenceIndex = readFileSync(join(outDir, "index.md"), "utf8");
    const commands = sidebar.find((group: { type: string }) => group.type === "command");
    const groups = commands.items as Array<{
      visibility: string;
      label: string;
      items: Array<{ label: string; slug: string }>;
    }>;

    expect(commands.label).toBe("Commands");
    expect(referenceIndex).toContain("<span>37</span><strong>Commands</strong>");
    expect(referenceIndex).not.toContain("<span>5</span><strong>Commands</strong>");
    expect(groups.map((group) => group.label)).toEqual([
      "Core",
      "Advanced",
      "Compatibility aliases",
      "Internal",
      "Deprecated",
    ]);
    expect(groups.map((group) => group.items.length)).toEqual([18, 12, 5, 1, 1]);

    for (const group of groups) {
      expect(group.items.map((item) => item.label)).toEqual(
        group.items.map((item) => item.label).sort((a, b) => a.localeCompare(b)),
      );
    }

    const commandPages = result.pages.filter((page) => page.type === "command");
    // This is an explicitly retired capability, not a hidden or aliased page.
    expect(commandPages.map((page) => page.slug)).not.toContain("new-skill");
    expect(result.pages.filter((page) => page.type === "skill").map((page) => page.slug))
      .not.toContain("skill-author");
    const expectedVisibility = new Map(
      commandPages.map((page) => [page.slug, page.commandCatalog?.visibility]),
    );
    const groupedItems = groups.flatMap((group) =>
      group.items.map((item) => ({ ...item, visibility: group.visibility })),
    );
    expect(groupedItems).toHaveLength(37);
    expect(new Set(groupedItems.map((item) => item.slug)).size).toBe(37);
    expect(groupedItems.map((item) => item.slug).sort()).toEqual(
      commandPages.map((page) => page.slug).sort(),
    );
    for (const item of groupedItems) {
      expect(item.visibility).toBe(expectedVisibility.get(item.slug));
    }
  });
});
