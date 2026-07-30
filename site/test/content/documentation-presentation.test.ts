import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const siteRoot = process.cwd();
const docsRoot = join(siteRoot, "src", "content", "docs");
const styles = readFileSync(join(siteRoot, "src", "styles", "design-system.css"), "utf8");
const themeStyles = readFileSync(join(siteRoot, "src", "styles", "theme.css"), "utf8");
const calloutStyles = readFileSync(join(siteRoot, "src", "styles", "callouts.css"), "utf8");
const config = readFileSync(join(siteRoot, "astro.config.mjs"), "utf8");

function readIfPresent(path: string): string {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function finalTableDisplay(source: string): string | undefined {
  const rules = [...source.matchAll(/\.sl-markdown-content table\s*\{([^}]+)\}/g)];
  return rules
    .flatMap((rule) => [...rule[1].matchAll(/display:\s*([^;]+);/g)])
    .at(-1)?.[1]
    .trim();
}

describe("documentation presentation regressions", () => {
  it("OBL-PRES-01 renders the concept index as navigation rather than a raw table", () => {
    const markdownPath = existsSync(join(docsRoot, "concepts.mdx"))
      ? join(docsRoot, "concepts.mdx")
      : join(docsRoot, "concepts.md");
    const source = readFileSync(markdownPath, "utf8");
    const component = readIfPresent(join(siteRoot, "src", "components", "ConceptNavigator.astro"));

    expect(source).toContain("<ConceptNavigator");
    expect(source).not.toMatch(/^\| Question \| Read \|$/m);
    expect(component).toContain("<nav");
    expect(component).toContain('aria-label="Concept map"');
    expect(component.match(/^\s{4}href:/gm)).toHaveLength(10);
  });

  it("OBL-PRES-02 keeps table layout semantic and moves overflow to a shared shell", () => {
    expect(finalTableDisplay(styles)).toBe("table");
    expect(styles).toContain(".ca-table-shell");
    expect(styles).toMatch(/\.ca-table-shell\s*\{[^}]*overflow-x:\s*auto;/s);
    expect(config).toContain("rehypeTableShell");
  });

  it("OBL-PRES-03 preserves Checkpoints as a real reviewer data grid", () => {
    const checkpoints = readFileSync(join(docsRoot, "concepts", "checkpoints.md"), "utf8");
    const fleetTable = checkpoints.match(/\| Reviewer \| Checks \|[\s\S]+?(?=\n\n## The funnel)/)?.[0] ?? "";

    expect(fleetTable).toContain("| Reviewer | Checks |");
    expect(fleetTable.match(/reference\/agents\//g)).toHaveLength(6);
  });

  it("OBL-PRES-04 gives Start a trailhead icon instead of a pause-shaped glyph", () => {
    const icons = readFileSync(join(siteRoot, "src", "components", "ArbiterIcon.astro"), "utf8");

    expect(icons).not.toContain("M4 18.5V5.5h4.5v13H4");
    expect(icons).toContain("M6 21V4.5");
  });

  it("OBL-PRES-05 uses a crisp, ownable header lockup instead of a glow-filtered utility mark", () => {
    const logo = readFileSync(join(siteRoot, "src", "assets", "logo.svg"), "utf8");

    expect(logo).toContain('viewBox="0 0 188 36"');
    expect(logo).toContain('id="mark-gold"');
    expect(logo).not.toContain("<filter");
    expect(styles).toMatch(/@media \(max-width: 34rem\)[\s\S]*?\.site-title\s*\{[^}]*overflow:\s*hidden;/);
  });

  it("OBL-PRES-06 normalizes the deployment base before building learning-path links", () => {
    const learningPath = readFileSync(join(docsRoot, "learn", "index.mdx"), "utf8");

    expect(learningPath).toContain('import.meta.env.BASE_URL.replace(/\\/$/, "")');
    expect(learningPath).not.toContain("`${import.meta.env.BASE_URL}/`");
  });

  it("OBL-PRES-07 uses rendered art for Feature Forge atmosphere and retains SVG for its model", () => {
    const forge = readFileSync(join(docsRoot, "feature-forge", "overview.md"), "utf8");
    const artwork = join(siteRoot, "public", "art", "feature-forge.webp");

    expect(forge).toContain('class="ca-art-banner');
    expect(forge).toContain('/codeArbiter/art/feature-forge.webp');
    expect(forge).toContain('/codeArbiter/diagrams/two-axis-model.svg');
    expect(existsSync(artwork)).toBe(true);
    expect(themeStyles).toContain(".ca-art-banner");
  });

  it("OBL-PRES-08 gives the landing page a real skip-link target", () => {
    const landing = readFileSync(join(docsRoot, "index.mdx"), "utf8");

    expect(landing).toMatch(/id=["']_top["']/);
    expect(landing).toMatch(/tabindex=["']-1["']/);
  });

  it("OBL-PRES-09 keeps labeled diagrams readable through horizontal exploration on phones", () => {
    expect(themeStyles).toMatch(
      /@media\s*\(max-width:\s*48rem\)[\s\S]*?\.ca-diagram\s*>\s*(?:svg|img)[\s\S]*?max-width:\s*none;/,
    );
    expect(themeStyles).toMatch(
      /@media\s*\(max-width:\s*48rem\)[\s\S]*?\.ca-statusline-map\s*\{[^}]*min-width:/,
    );
    expect(calloutStyles).not.toMatch(
      /\.ca-diagram\s+(?:img|svg)[\s\S]*?width:\s*100%;/,
    );
  });

  it("OBL-PRES-10 labels lookup, recovery, and walkthrough page orientation honestly", () => {
    const pageContext = readFileSync(
      join(siteRoot, "src", "components", "PageContext.astro"),
      "utf8",
    );

    expect(pageContext).toContain('time === "Lookup"');
    expect(pageContext).toContain('"Reference lookup"');
    expect(pageContext).toContain('time === "Symptom-driven"');
    expect(pageContext).toContain("Read / walkthrough / ${time}");
  });

  it("OBL-CONTENT-01 states the honest learning-path duration and governing scope", () => {
    const learningPath = readFileSync(join(docsRoot, "learn", "index.mdx"), "utf8");

    expect(learningPath).toContain("3–4 hours total");
    expect(learningPath).not.toContain(
      "configuration reference for migration, CI, and deployment scope",
    );
    expect(learningPath).toContain("security controls");
  });

  it("OBL-CONTENT-02 gives Pi exact supported hosts and a mechanical tag lookup", () => {
    const pi = readFileSync(join(docsRoot, "getting-started", "pi.md"), "utf8");

    expect(pi).toContain("Pi 0.80.5 or Pi 0.80.10");
    expect(pi).not.toContain("Pi 0.80.10 or newer");
    expect(pi).toContain("git ls-remote --tags --refs");
    expect(pi).toContain('"ca-pi-v*"');
  });

  it("OBL-CONTENT-03 documents hook registration and marker trust honestly across hosts", () => {
    const hooks = readFileSync(join(docsRoot, "hooks.md"), "utf8");

    expect(hooks).not.toContain("Every hook is registered **twice**");
    expect(hooks).not.toContain("unforgeable by hand");
    expect(hooks).toContain("Claude Code registrations");
    expect(hooks).toContain("Codex adapter registrations");
    expect(hooks).toContain("Pi wrapper events");
    expect(hooks).toContain("cooperative attestation");
  });

  it("OBL-CONTENT-04 defines every terminology-locked term and the H-18 exception", () => {
    const glossary = readFileSync(join(docsRoot, "glossary.md"), "utf8");

    for (const term of ["Agent", "Command", "Layer", "Phase", "Severity", "Skill"]) {
      expect(glossary).toMatch(new RegExp(`^## ${term}$`, "m"));
    }
    expect(glossary).toContain("H-18");
    expect(glossary).toContain("project-maturity");
    expect(glossary).not.toContain("It scales how strict a gate behaves");
  });

  it("OBL-CONTENT-05 keeps uninstall and sandbox setup actionable on every host", () => {
    const uninstall = readFileSync(join(docsRoot, "guides", "uninstalling.md"), "utf8");
    const sandbox = readFileSync(join(docsRoot, "guides", "ca-sandbox.md"), "utf8");

    expect(uninstall).toContain("Claude Code, Codex, and Pi");
    expect(uninstall).toContain("git ls-remote --tags --refs");
    expect(uninstall).toContain("Claude Code removes");
    expect(uninstall).toContain("Codex removes");
    expect(uninstall).toContain("Pi removes");
    expect(uninstall).not.toContain("This removes the plugin payload");
    expect(uninstall).toContain("runs **every live registered enforcer**");
    expect(uninstall).toContain("removes only that host's registry");
    expect(uninstall).toContain("deliberately leaves the shared shims");
    expect(uninstall).toContain("git rev-parse --git-common-dir");
    expect(uninstall).toContain("git config --get core.hooksPath");
    expect(uninstall.indexOf("### 1. Remove the Claude Code Statusline")).toBeLessThan(
      uninstall.indexOf("### 3. Uninstall the Host Packages"),
    );
    expect(uninstall.indexOf("### 2. Remove Each Host's Git-Backstop Registration")).toBeLessThan(
      uninstall.indexOf("### 3. Uninstall the Host Packages"),
    );
    expect(sandbox).toContain("/plugin marketplace add arbiterForge/codeArbiter");
  });

  it("OBL-CONTENT-06 avoids duplicate narration for decorative Feature Forge art", () => {
    const forge = readFileSync(join(docsRoot, "feature-forge", "overview.md"), "utf8");

    expect(forge).toMatch(/feature-forge\.webp"\s+alt=""/);
  });

  it("OBL-CONTENT-07 presents repository opt-in as a three-host contract", () => {
    const optIn = readFileSync(join(docsRoot, "guides", "opt-in-a-repo.md"), "utf8");

    expect(optIn).toMatch(/shared by Claude Code, Codex, and Pi/);
    expect(optIn).toContain("/ca-init");
  });

  it("OBL-CONTENT-08 explains host-specific role execution without overgeneralizing dispatch", () => {
    const overview = readFileSync(join(docsRoot, "overview.md"), "utf8");

    expect(overview).not.toContain("The owning skill calls the agents");
    expect(overview).toContain("Claude Code dispatches plugin agents");
    expect(overview).toContain("host-provided agent threads");
    expect(overview).toContain("inline");
    expect(overview).toMatch(/Pi launches\s+hardened child processes/);
  });

  it("OBL-CONTENT-09 labels platform-aggregate setup as maintainer-only verification", () => {
    const compatibility = readFileSync(
      join(docsRoot, "getting-started", "compatibility.md"),
      "utf8",
    );

    expect(compatibility).toContain("Maintainer verification only");
    expect(compatibility).toContain("npm --prefix plugins/ca-pi/tools ci --ignore-scripts");
  });

  it("OBL-REF-01 suppresses inferred journey cards on generated entity pages", () => {
    const pageTitle = readFileSync(join(siteRoot, "src", "components", "PageTitle.astro"), "utf8");

    expect(pageTitle).toContain("isGeneratedEntity");
    expect(pageTitle).toMatch(/!isGeneratedEntity\s*&&\s*<PageContext/);
    expect(pageTitle).toContain("id === 'changelog'");
  });

  it("OBL-REF-02 compacts generated reference orientation on narrow viewports", () => {
    expect(styles).toMatch(
      /@media \(max-width: 42rem\)[\s\S]*?\.ca-reference-lead\s*\{[^}]*padding:\s*var\(--ca-space-4\);/,
    );
    expect(styles).toMatch(
      /@media \(max-width: 42rem\)[\s\S]*?\.ca-reference-lead__usage p\s*\{[^}]*max-width:\s*none;/,
    );
    expect(styles).toContain(".ca-reference-lead + ul + h2");
  });
});
