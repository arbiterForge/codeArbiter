/** landing-stats.ts — build-time counters for the landing page's trust row.
 *
 * The landing page's stat tiles (gate IDs, core lanes, agents, skills) are
 * computed here from the plugin source, never hand-typed, so they cannot
 * drift from what actually ships. `TrustRow.astro` calls
 * `computeLandingStats()` at build time; `test/landing/trust-row.test.ts`
 * asserts the result against an independent filesystem count.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { extractHookGates } from "./extract-hook-gates";
import {
  COMMAND_VISIBILITY_ORDER,
  COMMAND_WORKFLOW_ORDER,
  type CommandCatalog,
  type CommandCatalogEntry,
  type CommandVisibility,
  type CommandWorkflow,
} from "./types";

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
  /** Canonical core lanes from the generated command registry. */
  coreLaneCount: number;
  /** Installed compatibility aliases from the generated command registry. */
  aliasCount: number;
  /** Specialist agent markdown files under `agents/`, excluding `INDEX.md`
   *  (the internal catalog is not a published roster entry). */
  agentCount: number;
  /** Skill directories under `skills/` (each a published skill). */
  skillCount: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sameOrder<T extends string>(actual: unknown, expected: readonly T[]): actual is T[] {
  return Array.isArray(actual) && actual.length === expected.length && actual.every(
    (value, index) => value === expected[index],
  );
}

function catalogError(path: string, message: string): Error {
  return new Error(`${path}: ${message}`);
}

/**
 * Load the generated host catalog and validate the closed discovery graph the
 * site depends on. The surface generator owns broader cross-host validation;
 * this consumer still rejects missing, stale, duplicate, or malformed local
 * metadata rather than silently rediscovering commands from filenames.
 */
export function loadCommandCatalog(pluginRoot: string, routeNames: readonly string[]): CommandCatalog {
  const path = join(pluginRoot, "generated", "command-catalog.json");
  if (!existsSync(path)) throw catalogError(path, "missing generated command catalog");
  let document: unknown;
  try {
    document = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    const detail = error instanceof Error ? `: ${error.message}` : "";
    throw catalogError(path, `invalid JSON${detail}`);
  }
  if (!isRecord(document) || document.schemaVersion !== 1) {
    throw catalogError(path, "schemaVersion must be 1");
  }
  if (!sameOrder(document.visibilityOrder, COMMAND_VISIBILITY_ORDER)) {
    throw catalogError(path, "visibilityOrder must match the canonical taxonomy");
  }
  if (!sameOrder(document.workflowOrder, COMMAND_WORKFLOW_ORDER)) {
    throw catalogError(path, "workflowOrder must match the canonical taxonomy");
  }
  if (!isRecord(document.compatibility) || !isRecord(document.commands)) {
    throw catalogError(path, "compatibility and commands must be objects");
  }

  const commands: Record<string, CommandCatalogEntry> = {};
  const expectedRoutes = new Set(routeNames);
  for (const [route, raw] of Object.entries(document.commands)) {
    if (!expectedRoutes.has(route)) throw catalogError(path, `catalog route ${route} is not installed`);
    if (!isRecord(raw)) throw catalogError(path, `commands.${route} must be an object`);
    const visibility = raw.visibility;
    const workflow = raw.workflow;
    if (!COMMAND_VISIBILITY_ORDER.includes(visibility as CommandVisibility)) {
      throw catalogError(path, `commands.${route}.visibility is invalid`);
    }
    if (!COMMAND_WORKFLOW_ORDER.includes(workflow as CommandWorkflow)) {
      throw catalogError(path, `commands.${route}.workflow is invalid`);
    }
    if (typeof raw.description !== "string" || raw.description.length === 0 ||
        typeof raw.commandPath !== "string" || raw.commandPath.length === 0) {
      throw catalogError(path, `commands.${route} needs description and commandPath`);
    }
    if (raw.legacyRoutes !== undefined &&
        (!Array.isArray(raw.legacyRoutes) || raw.legacyRoutes.some((item) => typeof item !== "string") ||
          new Set(raw.legacyRoutes).size !== raw.legacyRoutes.length)) {
      throw catalogError(path, `commands.${route}.legacyRoutes has duplicate or invalid entries`);
    }
    const canonical = raw.canonical;
    const replacement = raw.replacement;
    if (visibility === "alias") {
      if (typeof canonical !== "string" || typeof replacement !== "string" || replacement.length === 0) {
        throw catalogError(path, `commands.${route} alias needs canonical and replacement`);
      }
    } else if (visibility === "deprecated") {
      if (typeof replacement !== "string" || replacement.length === 0) {
        throw catalogError(path, `commands.${route} deprecated route needs replacement`);
      }
    } else if (canonical !== route) {
      throw catalogError(path, `commands.${route}.canonical must equal its route`);
    }
    commands[route] = {
      description: raw.description,
      commandPath: raw.commandPath,
      visibility: visibility as CommandVisibility,
      workflow: workflow as CommandWorkflow,
      ...(typeof canonical === "string" ? { canonical } : {}),
      ...(typeof replacement === "string" ? { replacement } : {}),
      ...(Array.isArray(raw.legacyRoutes) ? { legacyRoutes: [...raw.legacyRoutes] as string[] } : {}),
    };
  }
  for (const route of expectedRoutes) {
    if (!commands[route]) throw catalogError(path, `installed route ${route} has no catalog assignment`);
  }
  for (const [route, entry] of Object.entries(commands)) {
    if (entry.visibility === "alias") {
      const target = entry.canonical && commands[entry.canonical];
      if (!target || target.visibility === "alias" || target.visibility === "deprecated") {
        throw catalogError(path, `commands.${route}.canonical is not an installed canonical route`);
      }
    }
    if (entry.legacyRoutes) {
      for (const legacy of entry.legacyRoutes) {
        if (commands[legacy]?.visibility !== "alias" || commands[legacy].canonical !== route) {
          throw catalogError(path, `commands.${route}.legacyRoutes does not close alias mapping`);
        }
      }
    }
  }
  for (const [route, entry] of Object.entries(commands)) {
    if (entry.visibility !== "alias") continue;
    if (!commands[entry.canonical!].legacyRoutes?.includes(route)) {
      throw catalogError(path, `commands.${entry.canonical}.legacyRoutes omits alias ${route}`);
    }
  }

  return {
    visibilityOrder: [...COMMAND_VISIBILITY_ORDER],
    workflowOrder: [...COMMAND_WORKFLOW_ORDER],
    commands,
  };
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
  const routeNames = readdirSync(join(pluginRoot, "commands"), { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => entry.name.slice(0, -".md".length));
  const catalog = loadCommandCatalog(pluginRoot, routeNames);
  const coreLaneCount = Object.values(catalog.commands).filter((entry) => entry.visibility === "core").length;
  const aliasCount = Object.values(catalog.commands).filter((entry) => entry.visibility === "alias").length;
  const agentCount = countMarkdownFiles(join(pluginRoot, "agents"), true);
  const skillCount = countDirectories(join(pluginRoot, "skills"));
  return { gateCount, coreLaneCount, aliasCount, agentCount, skillCount };
}
