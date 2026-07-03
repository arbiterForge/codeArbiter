/** landing-stats.ts — build-time counters for the landing page's trust row.
 *
 * The landing page's stat tiles (gate IDs, commands, agents, skills) are
 * computed here from the plugin source, never hand-typed, so they cannot
 * drift from what actually ships. `TrustRow.astro` calls
 * `computeLandingStats()` at build time; `test/landing/trust-row.test.ts`
 * asserts the result against an independent filesystem count.
 */
import { readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { extractHookGates } from "./extract-hook-gates";

// Deliberately NOT `import.meta.url`-relative: this module is imported by
// TrustRow.astro, which Vite bundles for the static build into
// dist/.prerender/chunks/ at a different relative depth than the source
// tree, so an import.meta.url-derived path resolves to the wrong directory
// once bundled (it works fine unbundled, e.g. under vitest or tsx, which is
// what made this easy to miss). `process.cwd()` is stable across every entry
// point that matters here (`npm test`, `npm run build`, `astro dev`), all of
// which run from `site/`.
/** Repo root — one level up from the `site/` working directory every build
 *  and test entry point runs from. */
export const REPO_ROOT = resolve(process.cwd(), "..");

/** `plugins/ca/` — the payload directory the counts are drawn from. */
export const DEFAULT_PLUGIN_ROOT = join(REPO_ROOT, "plugins", "ca");

export interface LandingStats {
  /** Distinct `H-xx` gate IDs found across `block()`/`remind()` call sites. */
  gateCount: number;
  /** Slash-command markdown files under `commands/`. */
  commandCount: number;
  /** Specialist agent markdown files under `agents/`, excluding `INDEX.md`
   *  (the internal catalog is not a published roster entry). */
  agentCount: number;
  /** Skill directories under `skills/` (each a published skill). */
  skillCount: number;
}

/** Counts `.md` files directly under `dir`, optionally excluding `INDEX.md`
 *  (the generator's own published-roster rule; see `generate.ts`). */
function countMarkdownFiles(dir: string, excludeIndex: boolean): number {
  return readdirSync(dir, { withFileTypes: true }).filter((entry) => {
    if (!entry.isFile() || !entry.name.endsWith(".md")) return false;
    if (excludeIndex && /^index\.md$/i.test(entry.name)) return false;
    return true;
  }).length;
}

/** Counts directories directly under `dir`. */
function countDirectories(dir: string): number {
  return readdirSync(dir, { withFileTypes: true }).filter((entry) => entry.isDirectory()).length;
}

/** Computes the landing page's trust-row numbers from the plugin source at
 *  `pluginRoot` (defaults to the real `plugins/ca/`). */
export function computeLandingStats(pluginRoot: string = DEFAULT_PLUGIN_ROOT): LandingStats {
  const { callSites } = extractHookGates(join(pluginRoot, "hooks"));
  const gateCount = new Set(callSites.map((site) => site.tag)).size;
  const commandCount = countMarkdownFiles(join(pluginRoot, "commands"), false);
  const agentCount = countMarkdownFiles(join(pluginRoot, "agents"), true);
  const skillCount = countDirectories(join(pluginRoot, "skills"));
  return { gateCount, commandCount, agentCount, skillCount };
}
