import type { RenderedPage, IndexResult, SidebarGroup, SidebarEntry } from "./types";

const FIXED_ORDER = ["command", "skill", "agent"] as const;

/**
 * Build the reference index markdown and the sidebar data structure.
 *
 * Pages are grouped by type in fixed order (`command`, `skill`, `agent`); only
 * groups with at least one page appear. Within a group, items are sorted by
 * title. The `markdown` lists every page; the `sidebar` mirrors the grouping for
 * `astro.config` consumption.
 */
export function buildIndex(pages: RenderedPage[]): IndexResult {
  // 1. Group pages by type
  const grouped = new Map<string, RenderedPage[]>();
  for (const page of pages) {
    const list = grouped.get(page.type);
    if (list) {
      list.push(page);
    } else {
      grouped.set(page.type, [page]);
    }
  }

  // 2. Build sidebar in fixed order, skipping empty groups
  const sidebar: SidebarGroup[] = [];
  for (const type of FIXED_ORDER) {
    const groupPages = grouped.get(type);
    if (groupPages && groupPages.length > 0) {
      // Sort by title within the group
      const sorted = [...groupPages].sort((a, b) =>
        a.title.localeCompare(b.title)
      );
      const items: SidebarEntry[] = sorted.map((p) => ({
        label: p.title,
        slug: p.slug,
      }));
      sidebar.push({ type, label: type, items });
    }
  }

  // 3. Build markdown – simply concatenate all titles
  const markdown = pages.map((p) => p.title).join("\n");

  return { markdown, sidebar };
}
