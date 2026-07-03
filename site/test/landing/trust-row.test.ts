/**
 * Landing trust-row obligation — the stat-tile numbers TrustRow.astro renders
 * must equal an independent filesystem count over plugins/ca/, not drift from
 * it. This guards against the counting helper silently under/over-collecting
 * (e.g. an INDEX.md-exclusion rule that stops matching after a rename).
 */
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { computeLandingStats, DEFAULT_PLUGIN_ROOT } from "../../scripts/generator/landing-stats";

const stats = computeLandingStats();

function independentGateCount(): number {
  // Scans every quoted "H-xx" literal in the hooks source (not just calls
  // whose first argument is the literal) — some tags (e.g. H-10b) only ever
  // appear as a literal inside a conditional variable assignment
  // (`tag = "H-09b" if touches_crypto else "H-10b"`), resolved to a call site
  // by extractHookGates's variable-tag logic rather than matched directly at
  // the call. A literal-anywhere scan still finds every tag that exists,
  // without re-implementing that resolution logic here.
  const hooksDir = join(DEFAULT_PLUGIN_ROOT, "hooks");
  const files = readdirSync(hooksDir).filter((f) => f.endsWith(".py"));
  const tags = new Set<string>();
  for (const file of files) {
    const content = readFileSync(join(hooksDir, file), "utf8");
    const matches = content.matchAll(/"(H-\d+[a-z]?)"/g);
    for (const m of matches) tags.add(m[1]);
  }
  return tags.size;
}

function independentMarkdownCount(dir: string, excludeIndex: boolean): number {
  return readdirSync(dir, { withFileTypes: true }).filter((entry) => {
    if (!entry.isFile() || !entry.name.endsWith(".md")) return false;
    if (excludeIndex && /^index\.md$/i.test(entry.name)) return false;
    return true;
  }).length;
}

function independentDirCount(dir: string): number {
  return readdirSync(dir, { withFileTypes: true }).filter((e) => e.isDirectory()).length;
}

describe("computeLandingStats matches an independent filesystem count", () => {
  it("gate count matches a literal-tag regex scan of plugins/ca/hooks/*.py", () => {
    expect(stats.gateCount).toBe(independentGateCount());
  });

  it("command count matches the .md file count in plugins/ca/commands/", () => {
    const expected = independentMarkdownCount(join(DEFAULT_PLUGIN_ROOT, "commands"), false);
    expect(stats.commandCount).toBe(expected);
  });

  it("agent count matches the .md file count in plugins/ca/agents/, excluding INDEX.md", () => {
    const expected = independentMarkdownCount(join(DEFAULT_PLUGIN_ROOT, "agents"), true);
    expect(stats.agentCount).toBe(expected);
  });

  it("skill count matches the directory count in plugins/ca/skills/", () => {
    const expected = independentDirCount(join(DEFAULT_PLUGIN_ROOT, "skills"));
    expect(stats.skillCount).toBe(expected);
  });
});

describe("computeLandingStats — floor guard (catches silent under-collection)", () => {
  // Snapshot as of this writing (2026-07-03): 20 distinct gate IDs, 39
  // commands, 28 agents (29 files minus INDEX.md), 22 skills. Floors, not
  // exact pins, so a legitimate payload addition does not fail this test.
  it("finds at least 15 distinct gate IDs", () => {
    expect(stats.gateCount).toBeGreaterThanOrEqual(15);
  });

  it("finds at least 30 commands", () => {
    expect(stats.commandCount).toBeGreaterThanOrEqual(30);
  });

  it("finds at least 20 agents", () => {
    expect(stats.agentCount).toBeGreaterThanOrEqual(20);
  });

  it("finds at least 15 skills", () => {
    expect(stats.skillCount).toBeGreaterThanOrEqual(15);
  });
});
