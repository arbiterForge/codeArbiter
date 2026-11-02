/** plugin-workflow-pairs.ts — derive the command/skill pairs straight from a plugin tree.
 *
 * `generate()` derives the same pairs while it builds pages. The site config
 * needs them earlier, to emit redirects for the skills that no longer have a
 * page, and it loads before any page is generated. Reading the shipped sources
 * here, on every config load, means the redirect map can never be stale and
 * never silently empty: a missing catalog or a broken claim throws and stops
 * the build. test/generator/merged-workflow-redirects.test.ts pins this result
 * to the one `generate()` returns.
 */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { collectSources } from "./collect-sources";
import { deriveName } from "./derive-name";
import { loadCommandCatalog } from "./landing-stats";
import { normalizeSource } from "./normalize-source";
import { deriveWorkflowPairs } from "./workflow-pairs";
import type { WorkflowPair } from "./types";

/**
 * The command/skill pairs of the plugin tree at `pluginDir`. Names follow the
 * same file-basename rule `generate()` uses, so `INDEX.md` catalogs are skipped
 * and a frontmatter `name:` cannot change a pairing.
 */
export function loadWorkflowPairs(pluginDir: string): WorkflowPair[] {
  const sources = collectSources(pluginDir).filter((source) => !/(^|\/)INDEX\.md$/i.test(source.path));
  const commands = sources
    .filter((source) => source.type === "command")
    .map((source) => ({ name: deriveName(source.path, {}), raw: normalizeSource(source.raw) }));
  const skills = sources
    .filter((source) => source.type === "skill")
    .map((source) => deriveName(source.path, {}));
  const hasCatalog = existsSync(join(pluginDir, "generated", "command-catalog.json"));
  const catalog = commands.length > 0 && hasCatalog
    ? loadCommandCatalog(pluginDir, commands.map((command) => command.name))
    : undefined;
  return deriveWorkflowPairs(commands, skills, catalog);
}
