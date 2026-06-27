// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { readFileSync } from "node:fs";

// Build the reference sidebar groups from the generator's output. `predev` and
// `prebuild` run `npm run gen` first, so sidebar.json exists before this loads.
// The try/catch keeps `astro check`/tooling from hard-failing on a fresh clone
// where the generator has not run yet.
/** @type {Array<{label: string, items: Array<{label: string, slug: string}>}>} */
let referenceGroups = [];
try {
  /** @type {Array<{type: string, label: string, items: Array<{label: string, slug: string}>}>} */
  const sidebarData = JSON.parse(
    readFileSync(new URL("./src/generated/sidebar.json", import.meta.url), "utf8"),
  );
  referenceGroups = sidebarData.map((g) => ({
    label: `${g.type.charAt(0).toUpperCase()}${g.type.slice(1)}s`,
    collapsed: true,
    items: g.items.map((it) => ({
      label: it.label,
      slug: `reference/${g.type}s/${it.slug}`,
    })),
  }));
} catch {
  // sidebar.json not generated yet — reference groups stay empty.
}

export default defineConfig({
  // GitHub Pages project site: served from https://arbiterforge.github.io/codeArbiter/.
  // `base` also applies in local dev — the dev server serves at /codeArbiter/.
  //
  // BASE-PATH-SAFE LINK PATTERN for downstream authors:
  //   - In Starlight MDX/Markdown, use root-relative slugs (no leading slash):
  //       [Overview](/overview)  →  Starlight maps slugs through the base automatically.
  //   - In Astro component href props, use import.meta.env.BASE_URL:
  //       href={`${import.meta.env.BASE_URL}overview/`}
  //   - Never hardcode "/codeArbiter/" in href strings. That value desynchs
  //     when the Astro base is changed and is invisible to linting.
  site: "https://arbiterforge.github.io",
  base: "/codeArbiter",
  integrations: [
    starlight({
      title: "codeArbiter",
      description: "Gated software-engineering workflows for Claude Code.",
      logo: {
        src: "./src/assets/logo.svg",
        replacesTitle: true,
        alt: "codeArbiter",
      },
      favicon: "/favicon.svg",
      customCss: [
        "./src/styles/theme.css",
        "./src/styles/callouts.css",
        "./src/styles/landing.css",
      ],
      // Starlight 0.33+ takes an array of link items, not an object.
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/arbiterForge/codeArbiter",
        },
      ],
      sidebar: [
        {
          label: "Getting started",
          items: [
            { label: "Install", slug: "getting-started/install" },
            { label: "Quickstart", slug: "getting-started/quickstart" },
            { label: "What is codeArbiter", slug: "overview" },
          ],
        },
        {
          label: "Guides",
          items: [
            { label: "Opt a repository in", slug: "guides/opt-in-a-repo" },
            { label: "Build a feature end to end", slug: "guides/feature-lane" },
            { label: "Run an autonomous sprint", slug: "guides/autonomous-sprints" },
            { label: "Override a gate safely", slug: "guides/overriding-a-gate" },
            { label: "Record an architecture decision", slug: "guides/recording-adrs" },
            { label: "Add a dependency safely", slug: "guides/adding-a-dependency" },
            { label: "Cut a release", slug: "guides/releasing-a-version" },
            { label: "Set up the statusline", slug: "guides/the-statusline" },
            { label: "Troubleshooting", slug: "guides/troubleshooting" },
          ],
        },
        {
          label: "Concepts",
          items: [
            { label: "Overview", slug: "concepts" },
            { label: "The gated-lane model", slug: "concepts/gated-lanes" },
            { label: "The Feature Forge", slug: "concepts/feature-forge" },
            { label: "SMARTS", slug: "concepts/smarts" },
            { label: "ADRs and the decision log", slug: "concepts/adrs" },
            { label: "Checkpoints", slug: "concepts/checkpoints" },
            { label: "The persona-register split", slug: "concepts/persona-and-context" },
            { label: "Provenance and context drift", slug: "concepts/provenance-drift" },
            { label: "Just-in-time context injection", slug: "concepts/jit-context-injection" },
            { label: "Auditability", slug: "concepts/auditability" },
          ],
        },
        {
          label: "Security",
          items: [
            { label: "Enforcement & Security", slug: "enforcement" },
            { label: "Hooks reference", slug: "hooks" },
          ],
        },
        {
          label: "Reference",
          items: [{ label: "All reference", slug: "reference" }, ...referenceGroups],
        },
      ],
    }),
  ],
});
