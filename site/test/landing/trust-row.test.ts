/**
 * Landing trust-row obligation — the stat-tile numbers TrustRow.astro renders
 * must equal an independent filesystem count over plugins/ca/, not drift from
 * it. This guards against the counting helper silently under/over-collecting
 * (e.g. an INDEX.md-exclusion rule that stops matching after a rename).
 */
import { afterEach, describe, it, expect } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { computeLandingStats, DEFAULT_PLUGIN_ROOT } from "../../scripts/generator/landing-stats";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const stats = computeLandingStats();
const trustRowSource = readFileSync(
  join(process.cwd(), "src", "components", "TrustRow.astro"),
  "utf8",
);

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

function independentCatalogVisibilityCount(visibility: string): number {
  const catalog = JSON.parse(readFileSync(
    join(DEFAULT_PLUGIN_ROOT, "generated", "command-catalog.json"),
    "utf8",
  )) as { commands: Record<string, { visibility: string }> };
  return Object.values(catalog.commands).filter((entry) => entry.visibility === visibility).length;
}

describe("computeLandingStats matches an independent filesystem count", () => {
  it("labels the registry-derived count as core lanes", () => {
    expect(trustRowSource).toContain('label: "core lanes"');
    expect(trustRowSource).not.toContain('label: "slash commands"');
  });

  it("gate count matches a literal-tag regex scan of plugins/ca/hooks/*.py", () => {
    expect(stats.gateCount).toBe(independentGateCount());
  });

  it("core lane count matches an independent generated catalog count", () => {
    const expected = independentCatalogVisibilityCount("core");
    expect(stats.coreLaneCount).toBe(expected);
  });

  it("alias count matches an independent generated catalog count", () => {
    expect(stats.aliasCount).toBe(independentCatalogVisibilityCount("alias"));
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
  // Snapshot as of this writing (2026-09-02): 20 distinct gate IDs, 18 core
  // lanes, 5 compatibility aliases, 19 agents (20 files minus INDEX.md), 23
  // skills. Floors, not
  // exact pins, so a legitimate payload addition does not fail this test.
  it("finds at least 15 distinct gate IDs", () => {
    expect(stats.gateCount).toBeGreaterThanOrEqual(15);
  });

  it("finds exactly 18 core lanes", () => {
    expect(stats.coreLaneCount).toBe(18);
  });

  it("finds exactly 5 compatibility aliases", () => {
    expect(stats.aliasCount).toBe(5);
  });

  it("finds at least 15 agents", () => {
    expect(stats.agentCount).toBeGreaterThanOrEqual(15);
  });

  it("finds at least 15 skills", () => {
    expect(stats.skillCount).toBeGreaterThanOrEqual(15);
  });
});

describe("computeLandingStats — canonical command discovery", () => {
  const roots: string[] = [];

  afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

  it("counts core lanes from the generated registry instead of command files", () => {
    const root = mkdtempSync(join(tmpdir(), "ca-landing-catalog-"));
    roots.push(root);
    for (const dir of ["hooks", "commands", "agents", "skills", "generated"]) {
      mkdirSync(join(root, dir), { recursive: true });
    }
    for (const name of ["commit", "audit", "cleanup", "conflict", "btw"]) {
      writeFileSync(join(root, "commands", `${name}.md`), "# command\n");
    }
    writeFileSync(join(root, "generated", "command-catalog.json"), JSON.stringify({
      schemaVersion: 1,
      visibilityOrder: ["core", "advanced", "alias", "internal", "deprecated"],
      workflowOrder: ["evaluate", "initialize", "change", "review", "decide", "ship", "operate", "extend", "help"],
      compatibility: {},
      commands: {
        commit: { description: "commit", commandPath: "commands/commit.md", visibility: "core", workflow: "ship", canonical: "commit", legacyRoutes: ["cleanup"] },
        audit: { description: "audit", commandPath: "commands/audit.md", visibility: "advanced", workflow: "operate", canonical: "audit" },
        cleanup: { description: "cleanup", commandPath: "commands/cleanup.md", visibility: "alias", workflow: "ship", canonical: "commit", replacement: "commit --cleanup" },
        conflict: { description: "conflict", commandPath: "commands/conflict.md", visibility: "internal", workflow: "decide", canonical: "conflict" },
        btw: { description: "btw", commandPath: "commands/btw.md", visibility: "deprecated", workflow: "help", replacement: "ask the question directly" },
      },
    }));

    const stats = computeLandingStats(root);
    expect(stats.coreLaneCount).toBe(1);
    expect(stats.aliasCount).toBe(1);
  });

  it("rejects malformed catalog metadata instead of falling back to file counting", () => {
    const root = mkdtempSync(join(tmpdir(), "ca-landing-catalog-invalid-"));
    roots.push(root);
    for (const dir of ["hooks", "commands", "agents", "skills", "generated"]) {
      mkdirSync(join(root, dir), { recursive: true });
    }
    writeFileSync(join(root, "commands", "commit.md"), "# command\n");
    writeFileSync(join(root, "generated", "command-catalog.json"), "{not json");

    expect(() => computeLandingStats(root)).toThrow(/command-catalog\.json/i);
  });
});
