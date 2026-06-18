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
  site: "https://arbiterforge.github.io",
  base: "/codeArbiter",
  integrations: [
    starlight({
      title: "codeArbiter",
      description: "Gated software-engineering workflows for Claude Code.",
      customCss: ["./src/styles/theme.css"],
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
