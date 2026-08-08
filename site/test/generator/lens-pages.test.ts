/** lens-pages.test.ts — the tribunal-lens reference collection.
 *
 * Covers collect-lenses.ts + render-lens-page.ts and their wiring into
 * generate.ts: one page per lens card under `tribunal-lenses/`, a sidebar
 * group appended after the entity groups, an index table, and clean behavior
 * on source trees (like the shared fixtures) that carry no lens cards.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import {
  rmSync,
  existsSync,
  readFileSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { collectLenses } from "../../scripts/generator/collect-lenses";
import { renderLensPage } from "../../scripts/generator/render-lens-page";
import { generate } from "../../scripts/generator/generate";

const here = dirname(fileURLToPath(import.meta.url));
const realPluginDir = join(here, "..", "..", "..", "plugins", "ca");
const fixturePluginDir = join(here, "..", "fixtures", "plugin");

const LENS_ROSTER = [
  "appsec",
  "architecture",
  "coverage",
  "infra",
  "migration",
  "observability",
  "performance",
  "reliability",
  "secrets-supply",
  "test-fidelity",
  "typesafety",
];

describe("collectLenses", () => {
  it("returns every shipped lens card, sorted by slug", () => {
    const cards = collectLenses(realPluginDir);
    expect(cards.map((c) => c.slug)).toEqual(LENS_ROSTER);
    for (const card of cards) {
      expect(card.raw.length).toBeGreaterThan(0);
    }
  });

  it("returns [] for a source tree without a lenses directory", () => {
    expect(collectLenses(fixturePluginDir)).toEqual([]);
  });
});

describe("renderLensPage", () => {
  const card = {
    slug: "appsec",
    raw: [
      "# appsec — lens mandate",
      "",
      "Executed under the `appsec` assignment.",
      "",
      "## Required reading",
      "- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — boundaries.",
      "",
      "## Checklist",
      "- Injection surface.",
    ].join("\n"),
  };

  it("titles the page after the lens and strips the card's own H1", () => {
    const page = renderLensPage(card);
    expect(page.title).toBe("appsec lens");
    expect(page.markdown).toMatch(/^---\ntitle: appsec lens\n/);
    expect(page.markdown).not.toContain("# appsec — lens mandate");
  });

  it("leads with the executing agent and links its page and the tribunal command", () => {
    const page = renderLensPage(card);
    expect(page.markdown).toContain("(/reference/agents/tribunal-lens-reviewer/)");
    expect(page.markdown).toContain("(/reference/commands/tribunal/)");
    // The lead comes before the card body's first section.
    expect(page.markdown.indexOf("tribunal-lens-reviewer")).toBeLessThan(
      page.markdown.indexOf("## Required reading"),
    );
  });

  it("keeps the card's sections and translates environment placeholders", () => {
    const page = renderLensPage(card);
    expect(page.markdown).toContain("Executed under the `appsec` assignment.");
    expect(page.markdown).toContain("## Required reading");
    expect(page.markdown).toContain("## Checklist");
    expect(page.markdown).not.toContain("${CLAUDE_PROJECT_DIR}");
    // The translated prose sits outside the code span, keeping the span a real path.
    expect(page.markdown).toContain("the repository's `.codearbiter/security-controls.md`");
  });

  it("carries a per-lens description into the frontmatter", () => {
    const page = renderLensPage(card);
    expect(page.description).toContain("appsec");
    expect(page.markdown).toContain("description:");
  });
});

describe("generate — tribunal-lens collection wiring", () => {
  const srcDir = join(tmpdir(), "ca-lens-test-src");
  const outDir = join(tmpdir(), "ca-lens-test-out");
  const noLensOutDir = join(tmpdir(), "ca-lens-test-out-nolens");

  beforeEach(() => {
    rmSync(srcDir, { recursive: true, force: true });
    rmSync(outDir, { recursive: true, force: true });
    rmSync(noLensOutDir, { recursive: true, force: true });
    mkdirSync(join(srcDir, "commands"), { recursive: true });
    writeFileSync(
      join(srcDir, "commands", "sample.md"),
      "---\ndescription: A sample command.\n---\n\nBody.\n",
    );
    const lensesDir = join(srcDir, "skills", "tribunal", "references", "lenses");
    mkdirSync(lensesDir, { recursive: true });
    writeFileSync(
      join(lensesDir, "appsec.md"),
      "# appsec — lens mandate\n\nOpener.\n\n## Checklist\n- Item.\n",
    );
  });
  afterEach(() => {
    rmSync(srcDir, { recursive: true, force: true });
    rmSync(outDir, { recursive: true, force: true });
    rmSync(noLensOutDir, { recursive: true, force: true });
  });

  it("writes one page per lens card under tribunal-lenses/ and reports them", () => {
    const result = generate(srcDir, outDir);
    expect(result.lensPages.map((p) => p.slug)).toEqual(["appsec"]);
    const pagePath = join(outDir, "tribunal-lenses", "appsec.md");
    expect(existsSync(pagePath)).toBe(true);
    expect(readFileSync(pagePath, "utf8")).toContain("## Checklist");
  });

  it("appends a tribunal-lens sidebar group after the entity groups", () => {
    const result = generate(srcDir, outDir);
    const sidebar = JSON.parse(readFileSync(result.sidebarPath, "utf8"));
    const last = sidebar[sidebar.length - 1];
    expect(last.type).toBe("tribunal-lens");
    expect(last.items.map((it: { slug: string }) => it.slug)).toEqual(["appsec"]);
    // Entity groups keep their own pages only — the lens page joins no entity group.
    const total = sidebar
      .slice(0, -1)
      .reduce((n: number, g: { items: unknown[] }) => n + g.items.length, 0);
    expect(total).toBe(result.pages.length);
  });

  it("adds a Tribunal lenses table to the reference index, linking each lens page", () => {
    generate(srcDir, outDir);
    const indexContent = readFileSync(join(outDir, "index.md"), "utf8");
    expect(indexContent).toContain("## Tribunal lenses");
    expect(indexContent).toContain("[appsec](./tribunal-lenses/appsec/)");
  });

  it("cleans stale lens pages out of outDir before writing", () => {
    mkdirSync(join(outDir, "tribunal-lenses"), { recursive: true });
    writeFileSync(join(outDir, "tribunal-lenses", "ghost.md"), "stale");
    generate(srcDir, outDir);
    expect(existsSync(join(outDir, "tribunal-lenses", "ghost.md"))).toBe(false);
  });

  it("emits no lens dir, sidebar group, or index section for a lens-free source tree", () => {
    const result = generate(fixturePluginDir, noLensOutDir);
    expect(result.lensPages).toEqual([]);
    expect(existsSync(join(noLensOutDir, "tribunal-lenses"))).toBe(false);
    const sidebar = JSON.parse(readFileSync(result.sidebarPath, "utf8"));
    expect(sidebar.some((g: { type: string }) => g.type === "tribunal-lens")).toBe(false);
    const indexContent = readFileSync(join(noLensOutDir, "index.md"), "utf8");
    expect(indexContent).not.toContain("## Tribunal lenses");
  });
});
