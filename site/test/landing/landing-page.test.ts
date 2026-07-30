import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(__dirname, "../../");

function readSrc(rel: string): string {
  return readFileSync(path.join(siteRoot, rel), "utf8");
}

const indexMdx = readSrc("src/content/docs/index.mdx");
const proofCmp = readSrc("src/components/HookProof.astro");
const astroConfig = readSrc("astro.config.mjs");
const landingCss = readSrc("src/styles/landing.css");
const designCss = readSrc("src/styles/design-system.css");

describe("first-class product splash", () => {
  it("uses the sidebar-free Starlight splash shell", () => {
    expect(indexMdx).toMatch(/^template:\s*splash$/m);
    expect(indexMdx).toContain('class="ca-splash"');
    expect(landingCss).toContain(":root:has(.ca-landing) .main-pane");
  });

  it("leads with the reader outcome and supported hosts", () => {
    expect(indexMdx).toContain("Hard gates for agentic coding.");
    expect(indexMdx).toContain("You decide. codeArbiter enforces.");
    expect(indexMdx).toContain("Claude Code");
    expect(indexMdx).toContain("Codex");
    expect(indexMdx).toContain("Pi preview");
  });

  it("has one primary action above the fold", () => {
    const primaryMatches = indexMdx.match(/ca-button--primary/g) ?? [];
    expect(primaryMatches).toHaveLength(2);
    const splash = indexMdx.match(/<section class="ca-splash"[\s\S]*?<\/section>/)?.[0] ?? "";
    expect(splash.match(/ca-button--primary/g)).toHaveLength(1);
    expect(splash).toContain("Protect a repository");
  });

  it("shows a faithful direct-hook replay, not a fictional terminal sequence", () => {
    expect(indexMdx).toContain("<HookProof />");
    expect(indexMdx).toContain("rendered as a faithful replay");
    expect(indexMdx).toContain("not host discovery or registration");
    expect(indexMdx).not.toContain("<CardGrid>");
    expect(indexMdx).not.toContain("GateCatchTerminal");
    expect(indexMdx).not.toContain("ca-source-map");
  });

  it("follows the adopter story through proof, guarantees, flow, hosts, fit, and final CTA", () => {
    for (const className of [
      "ca-proof-strip",
      "ca-guarantees",
      "ca-flow",
      "ca-hosts",
      "ca-fit",
      "ca-final-cta",
    ]) {
      expect(indexMdx).toContain(className);
    }
  });

  it("links lifecycle and trust claims to their owning docs", () => {
    expect(indexMdx).toContain("./enforcement/");
    expect(indexMdx).toContain("./codearbiter-directory/");
    expect(indexMdx).toContain("./concepts/auditability/");
    expect(indexMdx).toContain("./getting-started/compatibility/");
    expect(indexMdx).toContain("./guides/uninstalling/");
  });

  it("uses page-relative internal links instead of a hardcoded deployment base", () => {
    expect(indexMdx).not.toMatch(/href="\/codeArbiter/);
    expect(indexMdx).toMatch(/href="\.\/getting-started\/install\//);
  });

  it("keeps raw HTML paragraphs on one line to avoid nested MDX paragraphs", () => {
    expect(indexMdx).not.toMatch(/<p(?:\s+class="[^"]+")?>\s*\n/);
  });
});

describe("captured gate proof", () => {
  it("ships accessible video controls and an exact text transcript", () => {
    expect(proofCmp).toContain("<video");
    expect(proofCmp).toContain("controls");
    expect(proofCmp).toContain("playsinline");
    expect(proofCmp).toMatch(/aria-label="[^"]+"/);
    expect(proofCmp).toContain('type="video/webm"');
    expect(proofCmp).toContain('type="video/mp4"');
    expect(proofCmp).toContain("Read the exact invocation result");
    expect(proofCmp).toContain("proof.invocation.stderr");
    expect(proofCmp).not.toContain("autoplay");
    expect(proofCmp).not.toContain("loop");
  });

  it("is traceable to the current shipped hook and proves the denied command stayed unstaged", () => {
    const proofPath = path.join(siteRoot, "src/assets/proof/hook-proof.json");
    const proof = JSON.parse(readFileSync(proofPath, "utf8"));
    const hookPath = path.resolve(siteRoot, "..", proof.source);
    const digest = createHash("sha256").update(readFileSync(hookPath)).digest("hex");

    expect(proof.sourceSha256).toBe(digest);
    expect(proof.invocation.exitCode).toBe(2);
    expect(proof.invocation.commandExecuted).toBe(false);
    expect(proof.evidenceKind).toBe("direct-hook-invocation-rendered-replay");
    expect(proof.hostDiscoveryProven).toBe(false);
    expect(proof.invocation.stderr).toContain("BLOCKED [H-03]");
    expect(proof.fixture.stagedAfter).toBe("");
    expect(proof.fixture.statusAfter).toContain("?? note.txt");
    expect(proof.fixture.gateEvent).toContain("BLOCK [H-03]");
  });

  it("keeps both efficient video formats and a poster in the repository", () => {
    for (const asset of ["hook-proof.mp4", "hook-proof.webm", "hook-proof-poster.webp"]) {
      expect(statSync(path.join(siteRoot, "src/assets/proof", asset)).size).toBeGreaterThan(10_000);
    }
  });

  it("does not overuse em dashes in adopter-facing copy", () => {
    const prose = indexMdx
      .replace(/^---[\s\S]*?---\n/, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/^import\s+.*$/gm, "");
    expect((prose.match(/—/g) ?? []).length).toBeLessThanOrEqual(3);
  });
});

describe("shared docs design system", () => {
  it("is registered before page-specific styles", () => {
    const designAt = astroConfig.indexOf("./src/styles/design-system.css");
    const landingAt = astroConfig.indexOf("./src/styles/landing.css");
    expect(designAt).toBeGreaterThan(-1);
    expect(landingAt).toBeGreaterThan(designAt);
  });

  it("bundles local variable fonts and exposes shared tokens", () => {
    expect(designCss).toContain('font-family: "Manrope Variable"');
    expect(designCss).toContain("../assets/fonts/manrope-latin-wght-normal.woff2");
    expect(designCss).toContain('font-family: "JetBrains Mono Variable"');
    expect(designCss).toContain("../assets/fonts/jetbrains-mono-latin-wght-normal.woff2");
    expect(designCss).toContain("--ca-space-9");
    expect(designCss).toContain("--ca-bg-panel");
    expect(designCss).toContain(".ca-reference-lead");
  });

  it("pins the reviewed font assets beside their complete OFL texts", () => {
    const fonts = [
      ["manrope-latin-wght-normal.woff2", "a30ddcd349703aff7464c34bef3fffdff405ee50c113440d7c8693c02d210972"],
      ["jetbrains-mono-latin-wght-normal.woff2", "18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e"],
    ] as const;
    for (const [file, expected] of fonts) {
      const bytes = readFileSync(path.join(siteRoot, "src/assets/fonts", file));
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(expected);
    }
    expect(readSrc("src/assets/fonts/LICENSE-Manrope.txt")).toContain(
      "SIL OPEN FONT LICENSE Version 1.1",
    );
    expect(readSrc("src/assets/fonts/LICENSE-JetBrains-Mono.txt")).toContain(
      "SIL OPEN FONT LICENSE Version 1.1",
    );
  });

  it("keeps the canonical gate diagram asset available to inner docs", () => {
    expect(existsSync(path.join(siteRoot, "public/diagrams/lane-flow.svg"))).toBe(true);
  });
});
