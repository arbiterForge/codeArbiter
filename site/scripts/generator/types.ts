// Shared type contract for the codeArbiter reference generator.
// Authored as the harness API; individual modules implement against it.
import type { ForgeStatus } from "./forge-status";
import type { CommandHostAvailability } from "./host-command-catalog";

/** The three kinds of plugin source documents the generator reads. */
export type SourceType = "command" | "skill" | "agent";

export const COMMAND_VISIBILITY_ORDER = [
  "core", "advanced", "alias", "internal", "deprecated",
] as const;
export type CommandVisibility = (typeof COMMAND_VISIBILITY_ORDER)[number];

export const COMMAND_WORKFLOW_ORDER = [
  "evaluate", "initialize", "change", "review", "decide", "ship", "operate", "extend", "help",
] as const;
export type CommandWorkflow = (typeof COMMAND_WORKFLOW_ORDER)[number];

/** Catalog metadata projected by each host's generated command sidecar. */
export interface CommandCatalogEntry {
  description: string;
  commandPath: string;
  visibility: CommandVisibility;
  workflow: CommandWorkflow;
  canonical?: string;
  replacement?: string;
  legacyRoutes?: string[];
}

/** Validated envelope for a host's generated command sidecar. */
export interface CommandCatalog {
  visibilityOrder: CommandVisibility[];
  workflowOrder: CommandWorkflow[];
  commands: Record<string, CommandCatalogEntry>;
}

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
 * Which reader fields a curated page carries.
 *
 * `workflow`: a core, advanced or internal command, and a skill that owns an
 * alias route; four fields and an `Example` heading in the body.
 * `internal-skill`: a skill with no command; two fields.
 * Alias commands and skills merged into a command have no shape.
 */
export type ReaderShape = "workflow" | "internal-skill";

/** Reader fields as written in curated frontmatter, one line each. */
export interface ReaderFields {
  use_when?: string;
  avoid_when?: string;
  asks?: string;
  produces?: string;
  runs_inside?: string;
}

/**
 * The required fields of each shape, in the order the page renders them, with
 * the heading each renders under. The loader validates against this table and
 * the renderer reads it, so the two cannot disagree on the set or the order.
 */
export const READER_FIELD_SPEC: Record<
  ReaderShape,
  ReadonlyArray<{ key: keyof ReaderFields; label: string }>
> = {
  workflow: [
    { key: "use_when", label: "Use it when" },
    { key: "avoid_when", label: "Don't use it for" },
    { key: "asks", label: "What it asks you" },
    { key: "produces", label: "What it produces" },
  ],
  "internal-skill": [
    { key: "runs_inside", label: "Runs inside" },
    { key: "produces", label: "What it produces" },
  ],
};

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
  /** Reader fields from frontmatter; keys present in the file, empty values included. */
  reader?: ReaderFields;
  body: string;
}

/** A related-entity link, already resolved to its collection + slug by `generate.ts`. */
export interface RelatedLink {
  label: string;
  href: string;
}

/** A skill folded into its command's page; see {@link PageInput.workflowSkill}. */
export interface MergedWorkflowSkill {
  /** The skill's directory name, e.g. `decision-lifecycle`. */
  name: string;
  /** The skill's curated companion, when one exists. */
  curated?: CuratedDoc;
  /** Verbatim raw contents of the skill's `SKILL.md`. */
  sourceRaw: string;
  /** Repo-relative path, e.g. `plugins/ca/skills/decision-lifecycle/SKILL.md`. */
  sourceRelPath: string;
}

/** Where an alias command sends the reader; see {@link PageInput.aliasPointer}. */
export interface AliasWorkflowPointer {
  /** The skill directory name whose page is the workflow page. */
  skill: string;
  skillHref: string;
  /** Replacement text from the catalog, e.g. `pr --cleanup`. */
  replacement: string;
  /** Page of the canonical command the replacement belongs to. */
  replacementHref: string;
  /** Canonical command name, e.g. `pr`. */
  replacementCommand: string;
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
  /** Which reader fields this page renders above its body; undefined renders none. */
  readerShape?: ReaderShape;
  /** Resolved `related:` links, or undefined when there are none. */
  relatedLinks?: RelatedLink[];
  /** Command availability derived from each shipped host adapter's catalog. */
  commandHosts?: CommandHostAvailability;
  /** Visibility/workflow metadata from the generated host command catalog. */
  commandCatalog?: CommandCatalogEntry;
  /**
   * The skill merged into this command page (core and advanced commands that
   * name an owning skill). Its curated text renders under "How it runs" and its
   * shipped source joins the command's in the page's single source embed.
   */
  workflowSkill?: MergedWorkflowSkill;
  /** For an alias command whose owning skill page is the workflow page. */
  aliasPointer?: AliasWorkflowPointer;
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
  /** Generated command-catalog metadata, preserved for discovery grouping. */
  commandCatalog?: CommandCatalogEntry;
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
  /** Command visibility, present only for command entries. */
  visibility?: CommandVisibility;
  /** Command workflow, present only for command entries. */
  workflow?: CommandWorkflow;
}

/** One registry-backed visibility section nested beneath the Commands group. */
export interface CommandSidebarGroup {
  visibility: CommandVisibility;
  label: string;
  items: SidebarEntry[];
}

/** A direct collection link or a nested command-visibility section. */
export type SidebarItem = SidebarEntry | CommandSidebarGroup;

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
  items: SidebarItem[];
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

/**
 * A command paired with the skill that owns its procedure. The pair is derived
 * from the shipped command source (its first heading names the skill) and the
 * command catalog (its visibility), never from a hand-kept list.
 *
 * `merge`: a core or advanced command, whose page also carries the skill's
 * reader text and source, so the skill gets no page of its own.
 * `alias`: a compatibility route; the skill page stays the workflow page and
 * the alias command page points at it.
 */
export interface WorkflowPair {
  command: string;
  skill: string;
  mode: "merge" | "alias";
  visibility: CommandVisibility;
  /** Alias only: the command that replaces the route, e.g. `pr`. */
  canonical?: string;
  /** Alias only: the replacement spelling, e.g. `pr --cleanup`. */
  replacement?: string;
}

/** Summary returned by a full generator run. */
export interface GenerateResult {
  pages: RenderedPage[];
  /** Command/skill pairs derived from the shipped sources (empty without a catalog). */
  workflowPairs: WorkflowPair[];
  /** Tribunal-lens pages, rendered from lens cards (empty when the source tree has none). */
  lensPages: LensPage[];
  outDir: string;
  sidebarPath: string;
}
