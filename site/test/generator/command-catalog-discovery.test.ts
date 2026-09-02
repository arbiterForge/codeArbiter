import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generate } from "../../scripts/generator/generate";

const roots: string[] = [];

function writeCommand(root: string, name: string): void {
  writeFileSync(
    join(root, "ca", "commands", `${name}.md`),
    `---\ndescription: ${name} command.\n---\n\n# /ca:${name}\n\nBody.\n`,
  );
}

function writeCatalog(root: string, mutate?: (catalog: Record<string, unknown>) => void): void {
  const catalog: Record<string, unknown> = {
    schemaVersion: 1,
    visibilityOrder: ["core", "advanced", "alias", "internal", "deprecated"],
    workflowOrder: ["evaluate", "initialize", "change", "review", "decide", "ship", "operate", "extend", "help"],
    compatibility: {},
    commands: {
      commit: {
        description: "commit command.", commandPath: "commands/commit.md",
        visibility: "core", workflow: "ship", canonical: "commit", legacyRoutes: ["cleanup"],
      },
      audit: {
        description: "audit command.", commandPath: "commands/audit.md",
        visibility: "advanced", workflow: "operate", canonical: "audit",
      },
      cleanup: {
        description: "cleanup command.", commandPath: "commands/cleanup.md",
        visibility: "alias", workflow: "ship", canonical: "commit", replacement: "commit --cleanup",
      },
      conflict: {
        description: "conflict command.", commandPath: "commands/conflict.md",
        visibility: "internal", workflow: "decide", canonical: "conflict",
      },
      btw: {
        description: "btw command.", commandPath: "commands/btw.md",
        visibility: "deprecated", workflow: "help", replacement: "ask the question directly",
      },
    },
  };
  mutate?.(catalog);
  writeFileSync(join(root, "ca", "generated", "command-catalog.json"), JSON.stringify(catalog));
}

function makePlugin(mutate?: (catalog: Record<string, unknown>) => void): { srcDir: string; outDir: string } {
  const root = mkdtempSync(join(tmpdir(), "ca-catalog-discovery-"));
  roots.push(root);
  for (const path of ["ca/commands", "ca/generated", "ca-codex", "ca-pi"]) {
    mkdirSync(join(root, path), { recursive: true });
  }
  for (const name of ["commit", "audit", "cleanup", "conflict", "btw"]) writeCommand(root, name);
  writeCatalog(root, mutate);
  writeFileSync(join(root, "ca", "COMMANDS.md"), ["commit", "audit", "cleanup", "conflict", "btw"].map((name) => `| \`/ca:${name}\` |`).join("\n"));
  writeFileSync(join(root, "ca-codex", "COMMANDS.md"), ["commit", "audit", "conflict"].map((name) => `| \`$ca-${name}\` |`).join("\n"));
  writeFileSync(join(root, "ca-pi", "COMMANDS.md"), ["commit", "audit", "cleanup", "conflict", "btw"].map((name) => `| \`/ca-${name}\` |`).join("\n"));
  return { srcDir: join(root, "ca"), outDir: join(root, "out") };
}

beforeEach(() => roots.splice(0));
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

describe("generated command catalog discovery", () => {
  it("groups every command exactly once by visibility then workflow while preserving host badges", () => {
    const { srcDir, outDir } = makePlugin();

    generate(srcDir, outDir);

    const index = readFileSync(join(outDir, "index.md"), "utf8");
    expect(index).toContain("## Commands");
    expect(index).toContain("### Core\n\n#### Ship");
    expect(index).toContain("### Advanced\n\n#### Operate");
    expect(index).toContain("### Compatibility aliases\n\n#### Ship");
    expect(index).toContain("### Internal\n\n#### Decide");
    expect(index).toContain("### Deprecated\n\n#### Help");
    for (const name of ["commit", "audit", "cleanup", "conflict", "btw"]) {
      expect(index.match(new RegExp(`\\[${name}\\]\\(\\./commands/${name}/\\)`, "g"))).toHaveLength(1);
    }
    const cleanup = readFileSync(join(outDir, "commands", "cleanup.md"), "utf8");
    expect(cleanup).toContain("## Compatibility");
    expect(cleanup).toContain("`commit --cleanup`");
    expect(cleanup).toContain("<code>/ca:cleanup</code>");
    expect(cleanup).not.toContain("<code>$ca-cleanup</code>");
  });

  it("fails closed when a collected command has no catalog assignment", () => {
    const { srcDir, outDir } = makePlugin((catalog) => {
      delete (catalog.commands as Record<string, unknown>).cleanup;
    });

    expect(() => generate(srcDir, outDir)).toThrow(/cleanup.*catalog/i);
  });

  it("fails closed when reverse alias assignment is duplicated", () => {
    const { srcDir, outDir } = makePlugin((catalog) => {
      ((catalog.commands as Record<string, { legacyRoutes: string[] }>).commit).legacyRoutes = ["cleanup", "cleanup"];
    });

    expect(() => generate(srcDir, outDir)).toThrow(/legacyRoutes.*duplicate/i);
  });

  it("fails closed when production generation has commands but no sidecar", () => {
    const { srcDir, outDir } = makePlugin();
    rmSync(join(srcDir, "generated", "command-catalog.json"));

    expect(() => generate(srcDir, outDir, undefined, undefined, true)).toThrow(
      /missing generated command catalog/i,
    );
  });
});
