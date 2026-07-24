import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import {
  rmSync,
  existsSync,
  readFileSync,
  readdirSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { generate } from "../../scripts/generator/generate";

const here = dirname(fileURLToPath(import.meta.url));
const pluginDir = join(here, "..", "fixtures", "plugin");
const collisionsPluginDir = join(here, "..", "fixtures", "plugin-collisions");
const outDir = join(tmpdir(), "ca-gen-test-out");
const collisionsOutDir = join(tmpdir(), "ca-gen-test-out-collisions");

/** Recursively read every file under a dir into a path->contents map. */
function snapshot(dir: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (d: string, prefix: string) => {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      const full = join(d, entry.name);
      if (entry.isDirectory()) walk(full, rel);
      else out[rel] = readFileSync(full, "utf8");
    }
  };
  walk(dir, "");
  return out;
}

describe("generate", () => {
  beforeEach(() => {
    rmSync(outDir, { recursive: true, force: true });
    mkdirSync(outDir, { recursive: true });
    rmSync(collisionsOutDir, { recursive: true, force: true });
    mkdirSync(collisionsOutDir, { recursive: true });
  });
  afterEach(() => {
    rmSync(outDir, { recursive: true, force: true });
    rmSync(collisionsOutDir, { recursive: true, force: true });
  });

  it("emits exactly one page per source file", () => {
    const result = generate(pluginDir, outDir);
    expect(result.pages).toHaveLength(5);
    const mdFiles = Object.keys(snapshot(outDir)).filter(
      (p) => p.endsWith(".md") && !p.endsWith("index.md"),
    );
    expect(mdFiles).toHaveLength(5);
  });

  it("writes a sidebar JSON listing every page", () => {
    const result = generate(pluginDir, outDir);
    expect(existsSync(result.sidebarPath)).toBe(true);
    const sidebar = JSON.parse(readFileSync(result.sidebarPath, "utf8"));
    const total = sidebar.reduce(
      (n: number, g: { items: unknown[] }) => n + g.items.length,
      0,
    );
    expect(total).toBe(5);
  });

  it("is idempotent: running twice produces byte-identical output", () => {
    generate(pluginDir, outDir);
    const first = snapshot(outDir);
    generate(pluginDir, outDir);
    const second = snapshot(outDir);
    expect(second).toEqual(first);
  });

  describe("per-collection slug dedup", () => {
    it("gives a same-named command, skill, and agent all the clean slug in their own collection — no -2 anywhere", () => {
      const result = generate(collisionsPluginDir, collisionsOutDir);
      const debugPages = result.pages.filter((p) => p.title === "debug");
      expect(debugPages).toHaveLength(3);
      const byType = Object.fromEntries(debugPages.map((p) => [p.type, p.slug]));
      expect(byType.command).toBe("debug");
      expect(byType.skill).toBe("debug");
      expect(byType.agent).toBe("debug");
      // None of the three "debug" pages themselves got pushed to a -2 slug.
      // (A separate, deliberately-colliding "dup" skill pair in this fixture
      // set is expected to produce a -2 — that's covered by the next test.)
      expect(debugPages.some((p) => p.slug.endsWith("-2"))).toBe(false);
      expect(existsSync(join(collisionsOutDir, "commands", "debug.md"))).toBe(true);
      expect(existsSync(join(collisionsOutDir, "skills", "debug.md"))).toBe(true);
      expect(existsSync(join(collisionsOutDir, "agents", "debug.md"))).toBe(true);
    });

    it("still dedupes two same-named files WITHIN one collection to a -2 slug", () => {
      const result = generate(collisionsPluginDir, collisionsOutDir);
      const dupPages = result.pages.filter((p) => p.type === "skill" && p.title === "dup");
      expect(dupPages).toHaveLength(2);
      const slugs = dupPages.map((p) => p.slug).sort();
      expect(slugs).toEqual(["dup", "dup-2"]);
    });

    it("resolves the forge preview badge for a command after per-collection slugging (regression)", () => {
      const result = generate(collisionsPluginDir, collisionsOutDir);
      const prunePage = result.pages.find(
        (p) => p.type === "command" && p.slug === "prune",
      );
      expect(prunePage).toBeDefined();
      // prune is a preview-command in the forge allowlist (forge-status.ts) —
      // its rendered page must still carry the preview badge/markup after
      // switching slug assignment to per-collection.
      expect(prunePage!.markdown).toMatch(/preview/i);
    });
  });

  describe("source embed + output-dir cleaning", () => {
    it("always renders a source embed, even with no curated dir", () => {
      const result = generate(pluginDir, outDir);
      const anyPage = result.pages[0];
      expect(anyPage.markdown).toContain("## Source");
      expect(anyPage.markdown).toContain('<details class="ca-source">');
    });

    it("cleans stale files out of outDir before writing", () => {
      mkdirSync(join(outDir, "commands"), { recursive: true });
      writeFileSync(join(outDir, "commands", "stale-2.md"), "stale content");
      writeFileSync(join(outDir, "index.md"), "stale index");
      generate(pluginDir, outDir);
      expect(existsSync(join(outDir, "commands", "stale-2.md"))).toBe(false);
      const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
      expect(indexContent).not.toBe("stale index");
    });
  });

  describe("curated merge", () => {
    const curatedOutDir = join(tmpdir(), "ca-gen-test-out-curated");
    const curatedDir = join(tmpdir(), "ca-gen-test-curated-src");

    beforeEach(() => {
      rmSync(curatedOutDir, { recursive: true, force: true });
      rmSync(curatedDir, { recursive: true, force: true });
      mkdirSync(curatedOutDir, { recursive: true });
    });
    afterEach(() => {
      rmSync(curatedOutDir, { recursive: true, force: true });
      rmSync(curatedDir, { recursive: true, force: true });
    });

    it("merges a curated body/gates/related for a matching source", () => {
      mkdirSync(join(curatedDir, "commands"), { recursive: true });
      writeFileSync(
        join(curatedDir, "commands", "sample.md"),
        `---\nentity: commands/sample\nrelated: [another]\ngates:\n  - gate: g1\n    when: w1\n    effect: e1\n---\n\nCurated prose for sample.\n`,
      );
      const result = generate(pluginDir, curatedOutDir, undefined, curatedDir);
      const samplePage = result.pages.find(
        (p) => p.type === "command" && p.slug === "sample",
      );
      expect(samplePage).toBeDefined();
      expect(samplePage!.markdown).toContain("Curated prose for sample.");
      expect(samplePage!.markdown).toContain("| g1 | w1 | e1 |");
      expect(samplePage!.markdown).toContain("## Related");
    });

    it("throws when a curated file's entity has no matching collected source (orphan)", () => {
      mkdirSync(join(curatedDir, "commands"), { recursive: true });
      writeFileSync(
        join(curatedDir, "commands", "ghost.md"),
        `---\nentity: commands/ghost\n---\n\nBody.\n`,
      );
      expect(() => generate(pluginDir, curatedOutDir, undefined, curatedDir)).toThrow(
        /ghost/,
      );
    });

    it("throws when a curated related ref cannot be resolved", () => {
      mkdirSync(join(curatedDir, "commands"), { recursive: true });
      writeFileSync(
        join(curatedDir, "commands", "sample.md"),
        `---\nentity: commands/sample\nrelated: [does-not-exist]\n---\n\nBody.\n`,
      );
      expect(() => generate(pluginDir, curatedOutDir, undefined, curatedDir)).toThrow(
        /unresolvable/,
      );
    });
  });

  describe("reference index — roster tables", () => {
    it("links the three catalogs to the request-flow explanation", () => {
      generate(pluginDir, outDir);
      const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
      expect(indexContent).toContain(
        "[How a Request Flows](/overview/#how-a-request-flows)",
      );
      expect(indexContent).toMatch(/command routes to an owning skill.*specialist agents/);
    });

    it("renders one markdown table per non-empty collection, headers matching the collection", () => {
      generate(pluginDir, outDir);
      const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
      expect(indexContent).toContain("| Command | Description |");
      expect(indexContent).toContain("| Skill | Description |");
      expect(indexContent).toContain("| Agent | Model tier | Description |");
    });

    it("links the name cell to the entity's page", () => {
      const result = generate(pluginDir, outDir);
      const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
      const anyCommand = result.pages.find((p) => p.type === "command");
      expect(anyCommand).toBeDefined();
      expect(indexContent).toContain(
        `[${anyCommand!.title}](./commands/${anyCommand!.slug}/)`,
      );
    });

    it("marks a preview command with a (preview) suffix after its name", () => {
      const result = generate(collisionsPluginDir, collisionsOutDir);
      const indexContent = readFileSync(join(collisionsOutDir, "index.md"), "utf8");
      const prunePage = result.pages.find(
        (p) => p.type === "command" && p.slug === "prune",
      );
      expect(prunePage).toBeDefined();
      expect(indexContent).toContain(
        `[${prunePage!.title}](./commands/${prunePage!.slug}/) (preview)`,
      );
    });

    it("carries a model-tier column value for an agent row", () => {
      const result = generate(pluginDir, outDir);
      const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
      const anyAgent = result.pages.find((p) => p.type === "agent");
      expect(anyAgent).toBeDefined();
      const rowRegex = new RegExp(
        `\\[${anyAgent!.title}\\]\\(\\./agents/${anyAgent!.slug}/\\) \\| \\S+ \\|`,
      );
      expect(indexContent).toMatch(rowRegex);
    });
  });
});
