import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const siteRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const projectorPath = join(siteRoot, "scripts", "reference-sidebar.ts");

type Projector = (groups: unknown[]) => Array<{
  label: string;
  collapsed: boolean;
  items: Array<{
    label: string;
    slug?: string;
    collapsed?: boolean;
    items?: Array<{ label: string; slug: string }>;
  }>;
}>;

async function loadProjector(): Promise<Projector | undefined> {
  if (!existsSync(projectorPath)) return undefined;
  const module = await import(pathToFileURL(projectorPath).href);
  return module.buildReferenceSidebar;
}

type GeneratedGroupsFixture = [
  {
    type: string;
    label: string;
    items: Array<{
      visibility: string;
      label: string;
      items: Array<{ label: string; slug: string; visibility: string; workflow: string }>;
    }>;
  },
  { type: string; label: string; items: Array<{ label: string; slug: string }> },
  { type: string; label: string; items: Array<{ label: string; slug: string }> },
];

const generatedGroups: GeneratedGroupsFixture = [
  {
    type: "command",
    label: "Commands",
    items: [
      { visibility: "core", label: "Core", items: [{ label: "commit", slug: "commit", visibility: "core", workflow: "ship" }] },
      { visibility: "advanced", label: "Advanced", items: [{ label: "audit", slug: "audit", visibility: "advanced", workflow: "operate" }] },
      { visibility: "alias", label: "Compatibility aliases", items: [{ label: "cleanup", slug: "cleanup", visibility: "alias", workflow: "ship" }] },
      { visibility: "internal", label: "Internal", items: [{ label: "conflict", slug: "conflict", visibility: "internal", workflow: "decide" }] },
      { visibility: "deprecated", label: "Deprecated", items: [{ label: "btw", slug: "btw", visibility: "deprecated", workflow: "help" }] },
    ],
  },
  { type: "skill", label: "skill", items: [{ label: "tdd", slug: "tdd" }] },
  { type: "tribunal-lens", label: "tribunal-lens", items: [{ label: "appsec", slug: "appsec" }] },
];

function commandGroups(): GeneratedGroupsFixture {
  return structuredClone(generatedGroups);
}

describe("reference sidebar projection", () => {
  it("projects command visibility as one nested level with canonical collapse and routes", async () => {
    const project = await loadProjector();
    expect(project).toBeTypeOf("function");

    const referenceGroups = project!(generatedGroups);
    const commands = referenceGroups[0];
    expect(commands.label).toBe("Commands");
    expect(commands.collapsed).toBe(true);
    expect(commands.items.map((group) => [group.label, group.collapsed])).toEqual([
      ["Core", false],
      ["Advanced", true],
      ["Compatibility aliases", true],
      ["Internal", true],
      ["Deprecated", true],
    ]);
    expect(commands.items.map((group) => group.items?.map((item) => item.slug))).toEqual([
      ["reference/commands/commit"],
      ["reference/commands/audit"],
      ["reference/commands/cleanup"],
      ["reference/commands/conflict"],
      ["reference/commands/btw"],
    ]);

    const serialized = JSON.stringify(commands);
    expect(serialized).not.toContain("workflow");
    expect(serialized).not.toContain("localStorage");
    expect(serialized).not.toContain("sessionStorage");
    expect(referenceGroups[1].items[0].slug).toBe("reference/skills/tdd");
    expect(referenceGroups[2].items[0].slug).toBe("reference/tribunal-lenses/appsec");
  });

  it("fails closed rather than flattening a command group without visibility children", async () => {
    const project = await loadProjector();
    expect(project).toBeTypeOf("function");
    expect(() => project!([
      { type: "command", label: "Commands", items: [{ label: "commit", slug: "commit" }] },
    ])).toThrow(/visibility group/i);
  });

  it("rejects generated sidebar data with no Commands collection", async () => {
    const project = await loadProjector();
    expect(() => project!(commandGroups().slice(1))).toThrow(/exactly one Commands group/i);
  });

  it("rejects generated sidebar data with duplicate Commands collections", async () => {
    const project = await loadProjector();
    const groups = commandGroups();
    groups.push(structuredClone(groups[0]));
    expect(() => project!(groups)).toThrow(/exactly one Commands group/i);
  });

  it("rejects a sole command collection whose label is not exactly Commands", async () => {
    const project = await loadProjector();
    const groups = commandGroups();
    groups[0].label = "Command reference";
    expect(() => project!(groups)).toThrow(/labeled Commands/i);
  });

  it.each([
    ["unknown", (groups: GeneratedGroupsFixture) => {
      groups[0].items[0].visibility = "public";
    }],
    ["misordered", (groups: GeneratedGroupsFixture) => {
      [groups[0].items[0], groups[0].items[1]] = [groups[0].items[1], groups[0].items[0]];
    }],
    ["duplicated", (groups: GeneratedGroupsFixture) => {
      groups[0].items[1] = structuredClone(groups[0].items[0]);
    }],
    ["mislabeled", (groups: GeneratedGroupsFixture) => {
      groups[0].items[0].label = "Everyday";
    }],
  ])("rejects %s command visibility groups", async (_case, mutate) => {
    const project = await loadProjector();
    const groups = commandGroups();
    mutate(groups);
    expect(() => project!(groups)).toThrow(/canonical visibility groups/i);
  });

  it("rejects command entries whose visibility disagrees with their group", async () => {
    const project = await loadProjector();
    const groups = commandGroups();
    groups[0].items[0].items[0].visibility = "advanced";
    expect(() => project!(groups)).toThrow(/visibility.*group/i);
  });

  it("rejects duplicate command membership across visibility groups", async () => {
    const project = await loadProjector();
    const groups = commandGroups();
    const duplicate = structuredClone(groups[0].items[0].items[0]);
    duplicate.visibility = "advanced";
    groups[0].items[1].items.push(duplicate);
    expect(() => project!(groups)).toThrow(/duplicate command/i);
  });

  it.each([
    ["command", (groups: GeneratedGroupsFixture) => groups[0].items[0].items[0]],
    ["direct", (groups: GeneratedGroupsFixture) => groups[1].items[0]],
  ])("rejects a malformed %s leaf before projecting its route", async (_case, selectLeaf) => {
    const project = await loadProjector();
    const groups = commandGroups();
    const leaf = selectLeaf(groups) as Partial<{ label: string; slug: string }>;
    delete leaf.slug;
    expect(() => project!(groups)).toThrow(/label and slug/i);
  });

  it.each(["skill", "agent", "tribunal-lens"])(
    "fails closed when a %s collection contains a nested group",
    async (type) => {
      const project = await loadProjector();
      expect(project).toBeTypeOf("function");
      expect(() => project!([
        commandGroups()[0],
        {
          type,
          label: type,
          items: [{ visibility: "core", label: "Unexpected", items: [] }],
        },
      ])).toThrow(/direct links/i);
    },
  );
});
