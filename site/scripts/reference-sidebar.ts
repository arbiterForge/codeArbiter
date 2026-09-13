import type {
  CommandSidebarGroup,
  SidebarEntry,
  SidebarGroup,
  SidebarItem,
} from "./generator/types";

const COMMAND_VISIBILITY_GROUPS = [
  ["core", "Core"],
  ["advanced", "Advanced"],
  ["alias", "Compatibility aliases"],
  ["internal", "Internal"],
  ["deprecated", "Deprecated"],
] as const;

export interface ReferenceSidebarLink {
  label: string;
  slug: string;
}

export interface ReferenceSidebarGroup {
  label: string;
  collapsed: boolean;
  items: Array<ReferenceSidebarLink | ReferenceSidebarGroup>;
}

function isNestedGroup(item: SidebarItem): item is CommandSidebarGroup {
  return "items" in item;
}

function isSidebarEntry(item: SidebarItem): item is SidebarEntry {
  return !isNestedGroup(item);
}

function projectLink(item: SidebarEntry, path: string): ReferenceSidebarLink {
  return {
    label: item.label,
    slug: `reference/${path}/${item.slug}`,
  };
}

/** Project generated reference metadata into Starlight's nested sidebar shape. */
export function buildReferenceSidebar(groups: SidebarGroup[]): ReferenceSidebarGroup[] {
  const commandGroups = groups.filter((group) => group.type === "command");
  if (commandGroups.length !== 1) {
    throw new Error("Generated sidebar must contain exactly one Commands group");
  }
  if (commandGroups[0].label !== "Commands") {
    throw new Error("Generated command group must be labeled Commands");
  }

  return groups.map((group) => {
    const isLens = group.type === "tribunal-lens";
    if (group.type === "command") {
      if (!group.items.every(isNestedGroup)) {
        throw new Error("Commands sidebar entries must be visibility groups");
      }
      const hasCanonicalGroups = group.items.length === COMMAND_VISIBILITY_GROUPS.length
        && group.items.every((item, index) => {
          const expected = COMMAND_VISIBILITY_GROUPS[index];
          return item.visibility === expected[0] && item.label === expected[1];
        });
      if (!hasCanonicalGroups) {
        throw new Error("Commands sidebar must contain the canonical visibility groups");
      }

      const commandSlugs = new Set<string>();
      for (const visibilityGroup of group.items) {
        for (const item of visibilityGroup.items) {
          if (item.visibility !== visibilityGroup.visibility) {
            throw new Error(`Command visibility must agree with its ${visibilityGroup.label} group`);
          }
          if (commandSlugs.has(item.slug)) {
            throw new Error(`Duplicate command membership: ${item.slug}`);
          }
          commandSlugs.add(item.slug);
        }
      }
      return {
        label: group.label,
        collapsed: true,
        items: group.items.map((item) => ({
          label: item.label,
          collapsed: item.visibility !== "core",
          items: item.items.map((entry) => projectLink(entry, "commands")),
        })),
      };
    }

    if (!group.items.every(isSidebarEntry)) {
      throw new Error(`${group.type} sidebar entries must be direct links`);
    }
    const path = isLens ? "tribunal-lenses" : `${group.type}s`;
    return {
      label: isLens
        ? "Tribunal lenses"
        : `${group.type.charAt(0).toUpperCase()}${group.type.slice(1)}s`,
      collapsed: true,
      items: group.items.map((item) => projectLink(item, path)),
    };
  });
}
