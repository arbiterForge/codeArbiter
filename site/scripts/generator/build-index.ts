import {
  COMMAND_VISIBILITY_ORDER,
  COMMAND_WORKFLOW_ORDER,
  type CommandCatalog,
  type RenderedPage,
  type IndexResult,
  type SidebarGroup,
  type SidebarEntry,
  type SourceType,
} from "./types";
import { modelTier } from "./model-tier";
import { truncateDescription } from "./truncate-description";

const FIXED_ORDER = ["command", "skill", "agent"] as const;

const VISIBILITY_LABEL: Record<(typeof COMMAND_VISIBILITY_ORDER)[number], string> = {
  core: "Core",
  advanced: "Advanced",
  alias: "Compatibility aliases",
  internal: "Internal",
  deprecated: "Deprecated",
};

function commandRows(pages: RenderedPage[]): string {
  return [
    "| Command | Description |",
    "|---|---|",
    ...pages.map((page) => `| [${page.title}](./commands/${page.slug}/)${page.forgeStatus ? " (preview)" : ""} | ${page.description ?? ""} |`),
  ].join("\n");
}

function standardRows(type: Exclude<SourceType, "command">, items: SidebarEntry[]): string {
  const heading = type === "skill" ? "Skills" : "Agents";
  const header = type === "skill"
    ? "| Skill | Description |\n|---|---|"
    : "| Agent | Model tier | Description |\n|---|---|---|";
  const rows = items.map((item) => type === "skill"
    ? `| [${item.label}](./skills/${item.slug}/) | ${item.description ?? ""} |`
    : `| [${item.label}](./agents/${item.slug}/) | ${item.tier ?? "default"} | ${item.description ?? ""} |`);
  return `## ${heading}\n\n${header}\n${rows.join("\n")}`;
}

/**
 * Build the reference index markdown and the sidebar data structure.
 *
 * Pages are grouped by type in fixed order (`command`, `skill`, `agent`); only
 * groups with at least one page appear. Within a group, items are sorted by
 * title. The `markdown` lists every page; the `sidebar` mirrors the grouping for
 * `astro.config` consumption.
 */
export function buildIndex(pages: RenderedPage[], catalog?: CommandCatalog): IndexResult {
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
        description: p.description ? truncateDescription(p.description) : undefined,
        tier: type === "agent" ? modelTier(p.model) : undefined,
        preview: type === "command" ? p.forgeStatus != null : undefined,
        visibility: type === "command" ? p.commandCatalog?.visibility : undefined,
        workflow: type === "command" ? p.commandCatalog?.workflow : undefined,
      }));
      sidebar.push({ type, label: type, items });
    }
  }

  // 3. Build the discovery index. Commands use metadata-driven visibility then
  // workflow groups; skills and agents retain their existing collection groups.
  const sections: string[] = [];
  const commandPages = grouped.get("command") ?? [];
  if (commandPages.length > 0) {
    if (catalog) {
      if (commandPages.some((page) => page.commandCatalog === undefined)) {
        throw new Error("Every command page needs generated catalog metadata");
      }
      const visibilityOrder = catalog.visibilityOrder ?? [...COMMAND_VISIBILITY_ORDER];
      const workflowOrder = catalog.workflowOrder ?? [...COMMAND_WORKFLOW_ORDER];
      const visibilitySections = visibilityOrder.flatMap((visibility) => {
        const byVisibility = commandPages.filter((page) => page.commandCatalog?.visibility === visibility);
        if (byVisibility.length === 0) return [];
        const workflowSections = workflowOrder.flatMap((workflow) => {
          const matches = byVisibility.filter((page) => page.commandCatalog?.workflow === workflow);
          return matches.length === 0 ? [] : [`#### ${workflow[0].toUpperCase()}${workflow.slice(1)}\n\n${commandRows(matches)}`];
        });
        return [`### ${VISIBILITY_LABEL[visibility]}\n\n${workflowSections.join("\n\n")}`];
      });
      sections.push(`## Commands\n\n${visibilitySections.join("\n\n")}`);
    } else {
      sections.push(`## Commands\n\n${commandRows(commandPages)}`);
    }
  }
  for (const type of ["skill", "agent"] as const) {
    const items = sidebar.find((group) => group.type === type)?.items;
    if (items && items.length > 0) sections.push(standardRows(type, items));
  }
  const markdown = sections.join("\n\n");

  return { markdown, sidebar };
}
