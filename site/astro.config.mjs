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
      // codeArbiter is dark-only: ThemeProvider forces data-theme="dark" and
      // ThemeSelect renders nothing (the switcher is removed). See theme.css.
      components: {
        // dark-only: force the theme, remove the switcher
        ThemeProvider: "./src/components/ThemeProvider.astro",
        ThemeSelect: "./src/components/ThemeSelect.astro",
        // SPA-like navigation via Astro view transitions
        Head: "./src/components/Head.astro",
        // suppress the duplicate auto-<h1> on the bespoke landing hero
        PageTitle: "./src/components/PageTitle.astro",
        // position-based scroll-spy so the last "On this page" item highlights
        // when scrolled to the bottom (the stock observer misses it)
        TableOfContents: "./src/components/TableOfContents.astro",
        // inline search (live as you type, results drop below the box)
        // replacing Starlight's stock modal-on-click search
        Search: "./src/components/Search.astro",
      },
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
          label: "Getting Started",
          collapsed: true,
          items: [
            { label: "Install", slug: "getting-started/install" },
            { label: "Quickstart", slug: "getting-started/quickstart" },
            { label: "What Is codeArbiter", slug: "overview" },
          ],
        },
        {
          label: "Guides",
          collapsed: true,
          items: [
            { label: "Opt a Repository In", slug: "guides/opt-in-a-repo" },
            { label: "Record an Architecture Decision", slug: "guides/recording-adrs" },
            { label: "Add a Dependency Safely", slug: "guides/adding-a-dependency" },
            { label: "Set Up the Statusline", slug: "guides/the-statusline" },
            { label: "Build a Feature End to End", slug: "guides/feature-lane" },
            { label: "Run an Autonomous Sprint", slug: "guides/autonomous-sprints" },
            { label: "Override a Gate Safely", slug: "guides/overriding-a-gate" },
            { label: "Cut a Release", slug: "guides/releasing-a-version" },
            { label: "Troubleshooting", slug: "guides/troubleshooting" },
          ],
        },
        {
          label: "Feature Forge",
          collapsed: true,
          items: [
            { label: "What Is the Feature Forge", slug: "feature-forge/overview" },
            { label: "What's in the Forge", slug: "feature-forge/whats-in-the-forge" },
            { label: "Using Features Still in the Forge", slug: "feature-forge/using-preview-features" },
          ],
        },
        {
          label: "Concepts",
          collapsed: true,
          items: [
            { label: "Overview", slug: "concepts" },
            { label: "SMARTS", slug: "concepts/smarts" },
            { label: "Provenance and Context Drift", slug: "concepts/provenance-drift" },
            { label: "ADRs and the Decision Log", slug: "concepts/adrs" },
            { label: "Just-in-Time Context Injection", slug: "concepts/jit-context-injection" },
            { label: "The Gated-Lane Model", slug: "concepts/gated-lanes" },
            { label: "Checkpoints", slug: "concepts/checkpoints" },
            { label: "The Persona-Register Split", slug: "concepts/persona-and-context" },
            { label: "Auditability", slug: "concepts/auditability" },
          ],
        },
        {
          label: "Security",
          collapsed: true,
          items: [
            { label: "Enforcement & Security", slug: "enforcement" },
            { label: "Hooks Reference", slug: "hooks" },
          ],
        },
        {
          label: "Reference",
          collapsed: true,
          items: [{ label: "All Reference", slug: "reference" }, ...referenceGroups],
        },
      ],
    }),
  ],
});
