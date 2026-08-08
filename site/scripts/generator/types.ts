// Shared type contract for the codeArbiter reference generator.
// Authored as the harness API; individual modules implement against it.
import type { ForgeStatus } from "./forge-status";
import type { CommandHostAvailability } from "./host-command-catalog";

/** The three kinds of plugin source documents the generator reads. */
export type SourceType = "command" | "skill" | "agent";

/** A frontmatter block split from a source file. `frontmatter` is null when absent. */
export interface SplitResult {
  frontmatter: string | null;
  body: string;
}

/** A parsed document: flat frontmatter fields plus the remaining body. */
export interface ParsedDoc {
  fields: Record<string, string>;
  body: string;
}

/** A raw source file discovered under the plugin tree. */
export interface SourceFile {
  /** Absolute or root-relative path to the file. */
  path: string;
  /** Raw file contents. */
  raw: string;
  /** Which kind of source this is, by location. */
  type: SourceType;
}

/** One row of a curated `gates:` table — a gate the entity participates in. */
export interface GateSpec {
  gate: string;
  when: string;
  effect: string;
}

/**
 * A parsed curated companion file (`site/src/curated/{commands,agents,skills}/<basename>.md`).
 *
 * `entity` is the `<type-dir>/<basename>` key the file declares itself under (must match its
 * location and a collected source — validated by `load-curated.ts`). `related` holds raw entity
 * refs as written in frontmatter (bare basename or `type/basename`); resolution to a slug/link
 * happens at generation time. `body` is the verbatim markdown body, inserted as-is.
 */
export interface CuratedDoc {
  entity: string;
  related?: string[];
  gates?: GateSpec[];
  body: string;
}

/** A related-entity link, already resolved to its collection + slug by `generate.ts`. */
export interface RelatedLink {
  label: string;
  href: string;
}

/** Input to a page renderer. Fields are optional because source frontmatter is heterogeneous. */
export interface PageInput {
  name: string;
  description?: string;
  model?: string;
  tools?: string;
  /** Feature Forge preview status for this page, or null/undefined for stable features. */
  forgeStatus?: ForgeStatus | null;
  /** The curated framing layer for this entity, or undefined when uncurated. */
  curated?: CuratedDoc;
  /** Resolved `related:` links, or undefined when there are none. */
  relatedLinks?: RelatedLink[];
  /** Command availability derived from each shipped host adapter's catalog. */
  commandHosts?: CommandHostAvailability;
  /** Verbatim raw contents of the plugin source file, for the source embed. */
  sourceRaw: string;
  /** Repo-relative path to the plugin source file, e.g. `plugins/ca/commands/sprint.md`. */
  sourceRelPath: string;
  /** The plugin's version (from `plugin.json`), for the tag-pinned view-in-repo link. */
  pluginVersion: string;
}

/** A rendered reference page ready to write to disk. */
export interface RenderedPage {
  type: SourceType;
  slug: string;
  title: string;
  markdown: string;
  /** First-sentence-truncated description, for the reference index table. */
  description?: string;
  /** Raw `model:` frontmatter value (agents only), for the index's tier column. */
  model?: string;
  /** Feature Forge preview status (commands only), for the index's preview marker. */
  forgeStatus?: ForgeStatus | null;
}

/** One entry in a sidebar group. */
export interface SidebarEntry {
  label: string;
  slug: string;
  /** First-sentence-truncated description, for the reference index table. */
  description?: string;
  /** Model tier display label (agents only), via {@link modelTier}. */
  tier?: string;
  /** Whether this entry carries a Feature Forge preview badge (commands only). */
  preview?: boolean;
}

/**
 * The collection key of a sidebar group: one of the three plugin source types,
 * or the tribunal-lens documentation collection (lens cards are skill reference
 * data, not a fourth plugin source type — see `collect-lenses.ts`).
 */
export type SidebarGroupType = SourceType | "tribunal-lens";

/** A sidebar group (one per collection). */
export interface SidebarGroup {
  type: SidebarGroupType;
  label: string;
  items: SidebarEntry[];
}

/** The output of the index/sidebar builder. */
export interface IndexResult {
  markdown: string;
  sidebar: SidebarGroup[];
}

/** A raw tribunal lens card discovered under `skills/tribunal/references/lenses/`. */
export interface LensCard {
  /** The lens slug — the card's file basename (e.g. `appsec`, `secrets-supply`). */
  slug: string;
  /** Raw file contents. */
  raw: string;
}

/** A rendered tribunal-lens reference page ready to write to disk. */
export interface LensPage {
  slug: string;
  title: string;
  markdown: string;
  /** One-sentence description, for the reference index table and sidebar. */
  description: string;
}

/** Summary returned by a full generator run. */
export interface GenerateResult {
  pages: RenderedPage[];
  /** Tribunal-lens pages, rendered from lens cards (empty when the source tree has none). */
  lensPages: LensPage[];
  outDir: string;
  sidebarPath: string;
}
