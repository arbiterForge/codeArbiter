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
const outDir = join(tmpdir(), "ca-gen-test-out");

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
  });
  afterEach(() => {
    rmSync(outDir, { recursive: true, force: true });
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
});
