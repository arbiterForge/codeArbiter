// CLI entry for the reference generator. Reads the plugin's own frontmatter and
// emits the reference pages + sidebar data. Wired into `predev`/`prebuild`.
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { generate } from "./generator/generate";
import { extractHookGates } from "./generator/extract-hook-gates";
import { renderHooksReference, buildEventMap, type HooksJson } from "./generator/render-hooks-reference";
import { renderChangelog } from "./generator/render-changelog";
import { renderConfigurationReference } from "./generator/configuration-reference";
import { loadAcademySource } from "./academy-source";
import { generateAcademy } from "./generate-academy";
import { loadTopicMap } from "./topic-map";
import { generateReleaseApplicability } from "./release-applicability";
import { assertCapturesFresh } from "./capture/verify";

const here = dirname(fileURLToPath(import.meta.url)); // site/scripts
const repoRoot = resolve(here, "..", ".."); // -> repo root
const srcDir = join(repoRoot, "plugins", "ca");
const outDir = join(here, "..", "src", "content", "docs", "reference");
const sidebarPath = join(here, "..", "src", "generated", "sidebar.json");
const curatedDir = join(here, "..", "src", "curated");
const releaseApplicabilityPath = join(
  here,
  "..",
  "src",
  "generated",
  "release-applicability.json",
);

// The guides render captured tool output, which is only true while the tool is
// unchanged. A capture records the hash of every source its run executed, so a
// changed source fails here, before anything is generated, with the capture,
// the source and the refresh command named (AC-06).
try {
  const captures = assertCapturesFresh(repoRoot, join(here, "..", "src", "assets", "captures"));
  console.log(`Verified ${captures.length} captured guide examples against the working tree`);
} catch (error) {
  console.error((error as Error).message);
  process.exit(1);
}

const result = generate(srcDir, outDir, sidebarPath, curatedDir, true);
const counts = result.pages.reduce<Record<string, number>>((acc, p) => {
  acc[p.type] = (acc[p.type] ?? 0) + 1;
  return acc;
}, {});
if (result.lensPages.length > 0) {
  counts["tribunal-lens"] = result.lensPages.length;
}
console.log(
  `Generated ${result.pages.length + result.lensPages.length} reference pages ` +
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

const configurationOutPath = join(outDir, "configuration.md");
writeFileSync(configurationOutPath, renderConfigurationReference());
console.log(`Generated configuration reference -> ${configurationOutPath}`);

// On-site changelog (docs-site-overhaul spec, decision f): the repo-root
// CHANGELOG.md is the single source of truth for release history — this emits
// a Starlight-ready copy rather than duplicating it by hand. Gitignored output,
// same discipline as reference/.
const changelogSourcePath = join(repoRoot, "CHANGELOG.md");
const changelogOutPath = join(here, "..", "src", "content", "docs", "changelog.md");
if (existsSync(changelogSourcePath)) {
  const changelogSource = readFileSync(changelogSourcePath, "utf-8");
  writeFileSync(changelogOutPath, renderChangelog(changelogSource));
  console.log(`Generated changelog -> ${changelogOutPath}`);
} else {
  console.log(`Skipped changelog generation: ${changelogSourcePath} not found`);
}

// Academy routes are generated from the pinned submodule's publication
// manifest. Removing the prior generated route directory prevents a lesson
// dropped from the public inventory from remaining reachable as a stale page.
const academySource = loadAcademySource(repoRoot);
const academyDocsRoot = join(here, "..", "src", "content", "docs");
const academyGeneratedRoot = join(here, "..", "src", "generated");
// The topic map is checked before generateAcademy clears the prior Academy routes, so a bad
// entry fails the run with the entry named and leaves the last good output in place.
const topicMap = loadTopicMap(
  join(here, "..", "src", "data", "topic-map.json"),
  academyDocsRoot,
  academySource.lessons.map((lesson) => lesson.id),
);
const academyResult = generateAcademy(academySource, academyDocsRoot, academyGeneratedRoot, topicMap.lessons);
console.log(
  `Generated Academy overview and ${academyResult.sidebarItems.length} public lesson routes ` +
    `from ${academySource.release} (${academySource.commit}), ` +
    `${Object.keys(topicMap.pages).length} guide and concept pages linked to their lessons`,
);

const releaseApplicability = generateReleaseApplicability(
  repoRoot,
  releaseApplicabilityPath,
  process.env,
);
console.log(
  `Generated release applicability for ${releaseApplicability.hosts.length} governance hosts ` +
    `at ${releaseApplicability.build.commit} -> ${releaseApplicabilityPath}`,
);
