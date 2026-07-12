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

  it("makes the primary getting-started journey host-aware", () => {
    for (const rel of [
      "src/content/docs/overview.md",
      "src/content/docs/getting-started/install.md",
      "src/content/docs/getting-started/quickstart.md",
      "src/content/docs/getting-started/compatibility.md",
    ]) {
      const content = read(rel);
      expect(content, rel).toContain("Claude Code");
      expect(content, rel).toContain("Codex");
      expect(content, rel).toContain(".codearbiter/");
      expect(content, rel).toContain("getting-started/claude-code-and-codex");
    }
    const install = read("src/content/docs/getting-started/install.md");
    expect(install).toContain("/ca:doctor");
    expect(install).toContain("$ca-doctor");
  });

  it("keeps operational guidance host-correct", () => {
    const enforcement = read("src/content/docs/enforcement.md");
    const hooks = read("src/content/docs/hooks.md");
    const optIn = read("src/content/docs/guides/opt-in-a-repo.md");
    const faq = read("src/content/docs/faq.md");
    const troubleshooting = read("src/content/docs/guides/troubleshooting.md");
    const uninstalling = read("src/content/docs/guides/uninstalling.md");
    const statusline = read("src/content/docs/guides/the-statusline.md");
    const support = read("src/content/docs/getting-started/claude-code-and-codex.md");

    expect(enforcement).toContain("structured deny");
    expect(hooks).toContain("pre-tool-adapter.py");
    expect(optIn).toContain("/ca:init");
    expect(optIn).toContain("$ca-init");
    expect(faq).toMatch(/two users|mixed-host/i);
    expect(troubleshooting).toContain("/ca:doctor");
    expect(troubleshooting).toContain("$ca-doctor");
    expect(troubleshooting).toContain("/hooks");
    expect(uninstalling).toContain("codex plugin remove ca-codex@codearbiter");
    expect(uninstalling).toContain(".codearbiter/");
    expect(statusline).toMatch(/Claude Code only/i);
    expect(support).toContain("Documentation launch: 2026-07-12");
  });
});
