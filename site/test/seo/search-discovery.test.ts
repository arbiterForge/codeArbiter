import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = resolve(process.cwd());
const repoRoot = resolve(siteRoot, "..");
const readSite = (path: string) => readFileSync(resolve(siteRoot, path), "utf8");
const readRepo = (path: string) => readFileSync(resolve(repoRoot, path), "utf8");

describe("search discovery foundation", () => {
  it("makes the homepage the explicit codeArbiter category/entity page", () => {
    const homepage = readSite("src/content/docs/index.mdx");
    expect(homepage).toContain("title: Agentic Coding Governance for Claude Code, Codex, and Pi");
    expect(homepage).toContain("codeArbiter: hard gates for agentic coding.");
    expect(homepage).toContain("codeArbiter is an open-source governance layer for AI coding agents.");
    expect(homepage).toContain('href="./overview/">What is codeArbiter?</a>');
  });

  it("publishes one homepage site-name graph and the Open Graph site name", () => {
    const head = readSite("src/components/Head.astro");
    expect(head).toContain('<meta property="og:site_name" content="codeArbiter" />');
    expect(head).toContain('"@type": "WebSite"');
    expect(head).toContain('name: "codeArbiter"');
    expect(head).toContain('alternateName: ["Code Arbiter", "codearbiter.dev"]');
    expect(head).toContain('"@type": "SoftwareApplication"');
    expect(head).toContain("isHomepage &&");
    expect(head).toContain('type="application/ld+json"');
    expect(head).toContain("AGPL-3.0-only");
  });

  it("advertises the Starlight sitemap without blocking normal crawling", () => {
    const robots = readSite("public/robots.txt");
    const config = readSite("astro.config.mjs");
    expect(config).toContain('site: "https://codearbiter.dev"');
    expect(robots).toBe(
      "User-agent: *\nAllow: /\n\nSitemap: https://codearbiter.dev/sitemap-index.xml\n",
    );
  });

  it("uses the custom domain directly from the repository and generated public links", () => {
    const readme = readRepo("README.md");
    const forgeStatus = readSite("scripts/generator/forge-status.ts");
    expect(readme).toContain("https://codearbiter.dev/");
    expect(readme).not.toContain("https://arbiterforge.github.io/codeArbiter");
    expect(forgeStatus).not.toContain("https://arbiterforge.github.io/codeArbiter");
  });

  it("maps common sector vocabulary onto existing authoritative pages", () => {
    expect(readSite("src/content/docs/enforcement.md")).toContain(
      "deterministic AI coding agent guardrails",
    );
    expect(readSite("src/content/docs/concepts/auditability.mdx")).toContain(
      "AI coding agent audit trail",
    );
    expect(readSite("src/content/docs/overview.md")).toContain(
      "agentic coding governance",
    );
  });
});
