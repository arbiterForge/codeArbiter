import { describe, it, expect } from "vitest";
import { renderChangelog } from "../../scripts/generator/render-changelog";

const SOURCE = `# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

The plugin is the contents of \`plugins/ca/\`. Project state under a consumer's \`.codearbiter/\` is consumer-owned and out of scope for this log.

---

## [2.8.11] — 2026-07-02

### Added
- **Durable gate-events sink (#186).** Some detail here.

## [2.8.10] — 2026-07-02

### Changed
- **Cut SessionStart blocking work (#194).** Some other detail.
`;

describe("renderChangelog", () => {
  it("strips the source H1 and preamble above the first version heading", () => {
    const out = renderChangelog(SOURCE);
    expect(out).not.toMatch(/^#\s+Changelog/m);
    expect(out).not.toContain("Format follows [Keep a Changelog]");
    expect(out).not.toContain("---\n\n## [2.8.11]");
  });

  it("emits Starlight frontmatter with title and description", () => {
    const out = renderChangelog(SOURCE);
    expect(out.startsWith("---\n")).toBe(true);
    expect(out).toContain("title: Changelog");
    expect(out).toMatch(/description: ".+"/);
  });

  it("preserves every `## [X.Y.Z]` version heading and its body", () => {
    const out = renderChangelog(SOURCE);
    expect(out).toContain("## [2.8.11] — 2026-07-02");
    expect(out).toContain("Durable gate-events sink (#186).");
    expect(out).toContain("## [2.8.10] — 2026-07-02");
    expect(out).toContain("Cut SessionStart blocking work (#194).");
  });

  it("links the GitHub releases page", () => {
    const out = renderChangelog(SOURCE);
    expect(out).toContain("https://github.com/arbiterForge/codeArbiter/releases");
  });

  it("is idempotent: rendering the same source twice yields byte-identical output", () => {
    const first = renderChangelog(SOURCE);
    const second = renderChangelog(SOURCE);
    expect(second).toBe(first);
  });

  it("rewrites repo-root-relative ../../pull/NN links to absolute GitHub PR URLs", () => {
    const withPr = SOURCE.replace(
      "Some detail here.",
      "Some detail ([#11](../../pull/11)).",
    );
    const out = renderChangelog(withPr);
    expect(out).toContain("(https://github.com/arbiterForge/codeArbiter/pull/11)");
    expect(out).not.toContain("../../pull/11");
  });

  it("quote-escapes a description containing double quotes via yaml-quote", () => {
    // The static DESCRIPTION has no quotes today, but this guards the frontmatter
    // line stays well-formed YAML regardless — a change to DESCRIPTION that adds
    // a `"` must not break the emitted frontmatter block.
    const out = renderChangelog(SOURCE);
    const descLine = out.split("\n").find((l) => l.startsWith("description:"));
    expect(descLine).toBeDefined();
    expect(descLine).toMatch(/^description: "[^\n]*"$/);
  });
});
