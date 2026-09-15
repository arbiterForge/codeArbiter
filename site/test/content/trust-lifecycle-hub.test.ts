import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = process.cwd();
const hubPath = join(siteRoot, "src", "content", "docs", "trust.md");
const hub = existsSync(hubPath) ? readFileSync(hubPath, "utf8") : "";
const sidebar = readFileSync(join(siteRoot, "astro.config.mjs"), "utf8");

function section(source: string, heading: string): string {
  const start = source.indexOf(`## ${heading}`);
  const end = source.indexOf("\n## ", start + heading.length + 3);
  return start < 0 ? "" : source.slice(start, end < 0 ? source.length : end);
}

describe("trust and lifecycle hub", () => {
  it("OBL-TRUST-01 routes prospects to each canonical trust owner", () => {
    expect(existsSync(hubPath)).toBe(true);
    const prospect = section(hub, "Before installation");
    const mappings = [
      ["What can codeArbiter block, and where are its limits?", "/enforcement/"],
      ["Which activity uses the network, and what stays on disk?", "/getting-started/compatibility/#network-calls"],
      ["Which activity uses the network, and what stays on disk?", "https://github.com/arbiterForge/codeArbiter/blob/main/PRIVACY.md"],
      ["Which published versions and documentation build does the site currently support with evidence?", "/getting-started/compatibility/#release-applicability-heading"],
      ["Which published versions and documentation build does the site currently support with evidence?", "/release-applicability.json"],
      ["What license governs the repository?", "https://github.com/arbiterForge/codeArbiter/blob/main/LICENSE"],
    ] as const;
    for (const [question, target] of mappings) {
      const row = prospect.split("\n").find((line) => line.includes(`| ${question} |`)) ?? "";
      expect(row, `${question} should link to ${target}`).toContain(`](${target})`);
    }
  });

  it("OBL-TRUST-02 routes operators to safe removal without restating policy", () => {
    const operator = section(hub, "While operating or removing codeArbiter");
    expect(operator).toContain("/guides/uninstalling/");
    expect(hub).toContain("canonical owners");
    expect(hub).toContain("documentation website");
    expect(hub).toContain("installed product");
    expect(hub.match(/^## .+$/gm)).toEqual([
      "## Before installation",
      "## While operating or removing codeArbiter",
    ]);
    expect(hub).not.toMatch(/```|\bH-\d+\b|arbiter_active\(|(?:claude|codex) plugin (?:add|install|uninstall)/i);
  });

  it("OBL-TRUST-03 exposes the hub directly in Start navigation", () => {
    expect(sidebar).toContain('{ label: "Trust & Lifecycle", slug: "trust" }');
    expect(sidebar.indexOf('slug: "trust"')).toBeLessThan(sidebar.indexOf('slug: "faq"'));
  });
});
