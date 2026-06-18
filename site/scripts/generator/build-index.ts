import type { RenderedPage, IndexResult } from "./types";

/**
 * Build the reference index markdown and the sidebar data structure.
 *
 * Pages are grouped by type in fixed order (`command`, `skill`, `agent`); only
 * groups with at least one page appear. Within a group, items are sorted by
 * title. The `markdown` lists every page; the `sidebar` mirrors the grouping for
 * `astro.config` consumption.
 */
export function buildIndex(pages: RenderedPage[]): IndexResult {
  throw new Error("not implemented");
}
