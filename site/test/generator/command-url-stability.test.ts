import { afterEach, describe, expect, it } from "vitest";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generate } from "../../scripts/generator/generate";

/**
 * Command URLs are a published contract (spec CON-01 / AC-10): the pairing of
 * commands with skills may move reader text between pages, but it must never
 * rename, drop or regroup a command page.
 *
 * `BEFORE_THE_SPRINT` is a literal snapshot of the 33 command pages that the
 * generator emitted before commands and skills were paired, with each page's
 * sidebar visibility group. It is deliberately NOT derived from the current
 * sources: a derived list would follow a rename instead of catching it.
 */
const BEFORE_THE_SPRINT: Record<string, string> = {
  "add-dep": "core",
  adr: "core",
  "adr-status": "advanced",
  audit: "advanced",
  checkpoint: "advanced",
  chore: "core",
  cleanup: "alias",
  commit: "core",
  conflict: "internal",
  "context-check": "alias",
  "create-context": "alias",
  debug: "advanced",
  decompose: "alias",
  doctor: "core",
  feature: "core",
  fix: "core",
  init: "core",
  override: "core",
  pr: "core",
  prune: "advanced",
  reconcile: "advanced",
  refactor: "core",
  release: "core",
  review: "core",
  spike: "core",
  sprint: "core",
  standup: "advanced",
  status: "core",
  statusline: "advanced",
  task: "core",
  "threat-model": "advanced",
  tribunal: "advanced",
  watch: "alias",
};

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const pluginDir = join(repoRoot, "plugins", "ca");
const roots: string[] = [];

afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function generateProduction() {
  const outDir = mkdtempSync(join(tmpdir(), "ca-command-urls-"));
  roots.push(outDir);
  // No curated dir: URLs and visibility come from the shipped sources and the
  // catalog alone, so this contract does not move with curated prose.
  return { outDir, result: generate(pluginDir, outDir, undefined, undefined, true) };
}

const urlOf = (slug: string) => `/reference/commands/${slug}/`;

describe("command URL stability", () => {
  it("snapshots exactly 33 command URLs", () => {
    expect(Object.keys(BEFORE_THE_SPRINT)).toHaveLength(33);
  });

  it("emits every command URL from before the sprint and no other command URL", () => {
    const { result } = generateProduction();
    const emitted = result.pages
      .filter((page) => page.type === "command")
      .map((page) => urlOf(page.slug))
      .sort();
    expect(emitted).toEqual(Object.keys(BEFORE_THE_SPRINT).map(urlOf).sort());
  });

  it("writes a page file at every command URL", () => {
    const { outDir } = generateProduction();
    const onDisk = readdirSync(join(outDir, "commands")).sort();
    expect(onDisk).toEqual(Object.keys(BEFORE_THE_SPRINT).map((slug) => `${slug}.md`).sort());
    for (const slug of Object.keys(BEFORE_THE_SPRINT)) {
      expect(existsSync(join(outDir, "commands", `${slug}.md`)), slug).toBe(true);
    }
  });

  it("keeps every command in its sidebar visibility group", () => {
    const { result } = generateProduction();
    // The sidebar JSON is the artifact the Starlight config consumes.
    const sidebar = JSON.parse(readFileSync(result.sidebarPath, "utf8")) as Array<{
      type: string;
      items: Array<{ visibility: string; items: Array<{ slug: string }> }>;
    }>;
    const commands = sidebar.find((group) => group.type === "command")!;
    const grouped: Record<string, string> = {};
    for (const group of commands.items) {
      for (const item of group.items) grouped[item.slug] = group.visibility;
    }
    expect(grouped).toEqual(BEFORE_THE_SPRINT);
    expect(commands.items.map((group) => group.visibility)).toEqual([
      "core",
      "advanced",
      "alias",
      "internal",
    ]);
  });
});
