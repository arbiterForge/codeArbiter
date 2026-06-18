import { describe, it, expect } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { collectSources } from "../../scripts/generator/collect-sources";

const here = dirname(fileURLToPath(import.meta.url));
const pluginDir = join(here, "..", "fixtures", "plugin");
const emptyDir = join(here, "..", "fixtures", "empty-plugin");

describe("collectSources", () => {
  it("collects commands, skills, and agents from a plugin tree", () => {
    const found = collectSources(pluginDir);
    expect(found).toHaveLength(5);
    const types = found.map((f) => f.type).sort();
    expect(types).toEqual(["agent", "agent", "command", "command", "skill"]);
  });

  it("reads raw contents for each source", () => {
    const found = collectSources(pluginDir);
    for (const f of found) {
      expect(typeof f.raw).toBe("string");
      expect(f.raw.length).toBeGreaterThan(0);
    }
  });

  it("returns results sorted by path for stable order", () => {
    const found = collectSources(pluginDir);
    const paths = found.map((f) => f.path);
    expect(paths).toEqual([...paths].sort());
  });

  it("returns an empty list for an empty plugin tree", () => {
    expect(collectSources(emptyDir)).toEqual([]);
  });

  it("returns an empty list (no throw) for a missing directory", () => {
    expect(collectSources(join(here, "does-not-exist-xyz"))).toEqual([]);
  });
});
