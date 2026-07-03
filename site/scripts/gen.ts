// CLI entry for the reference generator. Reads the plugin's own frontmatter and
// emits the reference pages + sidebar data. Wired into `predev`/`prebuild`.
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { generate } from "./generator/generate";

const here = dirname(fileURLToPath(import.meta.url)); // site/scripts
const repoRoot = resolve(here, "..", ".."); // -> repo root
const srcDir = join(repoRoot, "plugins", "ca");
const outDir = join(here, "..", "src", "content", "docs", "reference");
const sidebarPath = join(here, "..", "src", "generated", "sidebar.json");
const curatedDir = join(here, "..", "src", "curated");

const result = generate(srcDir, outDir, sidebarPath, curatedDir);
const counts = result.pages.reduce<Record<string, number>>((acc, p) => {
  acc[p.type] = (acc[p.type] ?? 0) + 1;
  return acc;
}, {});
console.log(
  `Generated ${result.pages.length} reference pages ` +
    `(${Object.entries(counts).map(([t, n]) => `${n} ${t}`).join(", ")}) -> ${outDir}`,
);
