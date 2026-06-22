/** generate-forge.test.ts — codeArbiter's end-to-end forge badge injection tests. */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import {
  rmSync,
  readFileSync,
  mkdirSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { generate } from "../../scripts/generator/generate";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(tmpdir(), "ca-gen-forge-test-out");

/** Build a minimal in-memory plugin tree under a temp srcDir. */
function makeSrcDir(base: string): string {
  const commandsDir = join(base, "commands");
  mkdirSync(commandsDir, { recursive: true });

  // prune — whole command is preview
  writeFileSync(
    join(commandsDir, "prune.md"),
    `---\ndescription: Trim transcript clutter.\nargument-hint: status | dry\n---\n\n# /ca:prune\n\nBody.\n`,
  );

  // sprint — --farm flag is preview
  writeFileSync(
    join(commandsDir, "sprint.md"),
    `---\ndescription: Autonomous sprint.\nargument-hint: "[goal] [--farm]"\n---\n\n# /ca:sprint\n\nBody.\n`,
  );

  // commit — stable; no badge expected
  writeFileSync(
    join(commandsDir, "commit.md"),
    `---\ndescription: Run the full commit gate.\n---\n\n# /ca:commit\n\nBody.\n`,
  );

  return base;
}

describe("generate — forge badge injection", () => {
  let srcDir: string;

  beforeEach(() => {
    rmSync(outDir, { recursive: true, force: true });
    mkdirSync(outDir, { recursive: true });
    srcDir = join(tmpdir(), "ca-gen-forge-src-" + Date.now());
    mkdirSync(srcDir, { recursive: true });
    makeSrcDir(srcDir);
  });

  afterEach(() => {
    rmSync(outDir, { recursive: true, force: true });
    rmSync(srcDir, { recursive: true, force: true });
  });

  it("stamps a preview badge onto the prune page", () => {
    generate(srcDir, outDir);
    const prunePage = join(outDir, "commands", "prune.md");
    expect(existsSync(prunePage)).toBe(true);
    const content = readFileSync(prunePage, "utf8");
    expect(content).toContain('data-kind="preview"');
    expect(content).toContain("ca-badge");
  });

  it("stamps a --farm preview callout onto the sprint page", () => {
    generate(srcDir, outDir);
    const sprintPage = join(outDir, "commands", "sprint.md");
    expect(existsSync(sprintPage)).toBe(true);
    const content = readFileSync(sprintPage, "utf8");
    expect(content).toContain("ca-callout--preview");
    expect(content).toContain("--farm");
  });

  it("does NOT add any badge or preview callout to the stable commit page", () => {
    generate(srcDir, outDir);
    const commitPage = join(outDir, "commands", "commit.md");
    expect(existsSync(commitPage)).toBe(true);
    const content = readFileSync(commitPage, "utf8");
    expect(content).not.toContain("ca-badge");
    expect(content).not.toContain("ca-callout--preview");
  });
});
