// Shared type contract for the codeArbiter reference generator.
// Authored as the harness API; individual modules implement against it.

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

/** Input to a page renderer. Fields are optional because source frontmatter is heterogeneous. */
export interface PageInput {
  name: string;
  description?: string;
  model?: string;
  tools?: string;
}

/** A rendered reference page ready to write to disk. */
export interface RenderedPage {
  type: SourceType;
  slug: string;
  title: string;
  markdown: string;
}

/** One entry in a sidebar group. */
export interface SidebarEntry {
  label: string;
  slug: string;
}

/** A sidebar group (one per source type). */
export interface SidebarGroup {
  type: SourceType;
  label: string;
  items: SidebarEntry[];
}

/** The output of the index/sidebar builder. */
export interface IndexResult {
  markdown: string;
  sidebar: SidebarGroup[];
}

/** Summary returned by a full generator run. */
export interface GenerateResult {
  pages: RenderedPage[];
  outDir: string;
  sidebarPath: string;
}
