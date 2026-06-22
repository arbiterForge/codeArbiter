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
          label: "Start here",
          items: [
            { label: "Overview", slug: "overview" },
            { label: "Concepts", slug: "concepts" },
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
