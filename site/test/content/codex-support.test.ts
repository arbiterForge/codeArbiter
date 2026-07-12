import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(__dirname, "../../");
const supportPath = path.join(
  siteRoot,
  "src/content/docs/getting-started/claude-code-and-codex.md",
);

function read(rel: string): string {
  return readFileSync(path.join(siteRoot, rel), "utf8");
}

describe("canonical Claude Code and Codex support evidence", () => {
  it("ships a canonical support page", () => {
    expect(existsSync(supportPath)).toBe(true);
  });

  it("records the dated live evidence and its repository sources", () => {
    const page = readFileSync(supportPath, "utf8");
    expect(page).toContain(
      "Shared enforcement and project-context parity across Claude Code and Codex",
    );
    expect(page).toContain("Codex CLI 0.144.1");
    expect(page).toContain("ca-codex 0.2.4");
    expect(page).toMatch(/9 OK[\s\S]*0 WARN[\s\S]*0 FAIL/);
    expect(page).toContain("[H-03]");
    expect(page).toContain("2026-07-11");
    expect(page).toContain("docs/parity.md");
    expect(page).toContain("docs/codex-parity-testing.md");
  });

  it("labels release availability and intentional differences", () => {
    const page = readFileSync(supportPath, "utf8");
    expect(page).toContain("available after the Codex-support release");
    expect(page).toMatch(/statusline/i);
    expect(page).toMatch(/transcript pruning/i);
    expect(page).toMatch(/Read hook/i);
  });

  it("appears in Getting Started navigation", () => {
    const config = read("astro.config.mjs");
    expect(config).toContain("getting-started/claude-code-and-codex");
  });
});
