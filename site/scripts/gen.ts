// CLI entry for the reference generator. Reads the plugin's own frontmatter and
// emits the reference pages + sidebar data. Wired into `predev`/`prebuild`.
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { generate } from "./generator/generate";
import { extractHookGates } from "./generator/extract-hook-gates";
import { renderHooksReference, buildEventMap, type HooksJson } from "./generator/render-hooks-reference";

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

// Hooks are code, not prose (docs-site-overhaul spec, decision d): the hooks
// gate-ID reference is generated separately from `plugins/ca/hooks/*.py` call
// sites rather than joining the command/skill/agent frontmatter pipeline above
// — it has no source frontmatter and isn't one of `generate()`'s three
// SourceTypes, so it is emitted here as a standalone page in the same output
// directory instead of extending the SourceType union for a single page.
const hooksDir = join(srcDir, "hooks");
const hooksJsonPath = join(hooksDir, "hooks.json");
const pluginManifestPath = join(srcDir, ".claude-plugin", "plugin.json");
const pluginVersion = existsSync(pluginManifestPath)
  ? (JSON.parse(readFileSync(pluginManifestPath, "utf-8")).version ?? "0.0.0-dev")
  : "0.0.0-dev";

const { callSites, skipped } = extractHookGates(hooksDir);
const hooksJson: HooksJson = existsSync(hooksJsonPath)
  ? JSON.parse(readFileSync(hooksJsonPath, "utf-8"))
  : { hooks: {} };
const eventMap = buildEventMap(hooksJson);
const hooksGatesPage = renderHooksReference(callSites, eventMap, pluginVersion);
writeFileSync(join(outDir, "hooks-gates.md"), hooksGatesPage);

console.log(
  `Generated hooks-gates reference (${callSites.length} call sites, ` +
    `${new Set(callSites.map((c) => c.tag)).size} tags, ${skipped.length} skipped) -> ` +
    join(outDir, "hooks-gates.md"),
);
if (skipped.length > 0) {
  for (const s of skipped) {
    console.log(`  skipped (non-literal tag): ${s.file}:${s.line}`);
  }
}
