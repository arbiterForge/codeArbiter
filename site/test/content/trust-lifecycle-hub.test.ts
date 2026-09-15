import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = process.cwd();
const hubPath = join(siteRoot, "src", "content", "docs", "trust.md");
const hub = existsSync(hubPath) ? readFileSync(hubPath, "utf8") : "";
const sidebar = readFileSync(join(siteRoot, "astro.config.mjs"), "utf8");

describe("trust and lifecycle hub", () => {
  it("OBL-TRUST-01 routes prospects to each canonical trust owner", () => {
    expect(existsSync(hubPath)).toBe(true);
    expect(hub).toContain("## Before installation");
    expect(hub).toContain("/enforcement/");
    expect(hub).toContain("/getting-started/compatibility/#network-calls");
    expect(hub).toContain("/getting-started/compatibility/#release-applicability-heading");
    expect(hub).toContain("/release-applicability.json");
    expect(hub).toContain("https://github.com/arbiterForge/codeArbiter/blob/main/PRIVACY.md");
    expect(hub).toContain("https://github.com/arbiterForge/codeArbiter/blob/main/LICENSE");
  });

  it("OBL-TRUST-02 routes operators to safe removal without restating policy", () => {
    expect(hub).toContain("## While operating or removing codeArbiter");
    expect(hub).toContain("/guides/uninstalling/");
    expect(hub).toContain("canonical owners");
    expect(hub).toContain("documentation website");
    expect(hub).toContain("installed product");
  });

  it("OBL-TRUST-03 exposes the hub directly in Start navigation", () => {
    expect(sidebar).toContain('{ label: "Trust & Lifecycle", slug: "trust" }');
    expect(sidebar.indexOf('slug: "trust"')).toBeLessThan(sidebar.indexOf('slug: "faq"'));
  });
});
