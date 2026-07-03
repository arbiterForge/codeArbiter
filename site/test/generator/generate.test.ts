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
});
