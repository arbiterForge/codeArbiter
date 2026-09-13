import { describe, it, expect } from "vitest";
import { buildIndex } from "../../scripts/generator/build-index";
import type { CommandCatalog, RenderedPage } from "../../scripts/generator/types";

const pages: RenderedPage[] = [
  { type: "command", slug: "commit", title: "commit", markdown: "", commandCatalog: { description: "", commandPath: "commands/commit.md", visibility: "core", workflow: "ship" } },
  { type: "agent", slug: "scout", title: "scout", markdown: "" },
  { type: "command", slug: "adr", title: "adr", markdown: "", commandCatalog: { description: "", commandPath: "commands/adr.md", visibility: "core", workflow: "decide" } },
  { type: "skill", slug: "tdd", title: "tdd", markdown: "" },
];

const commandCatalog: CommandCatalog = {
  visibilityOrder: ["core", "advanced", "alias", "internal", "deprecated"],
  workflowOrder: ["evaluate", "initialize", "change", "review", "decide", "ship", "operate", "extend", "help"],
  commands: {},
};

describe("buildIndex", () => {
  it("groups pages by type in fixed order, only non-empty groups", () => {
    const { sidebar } = buildIndex(pages, commandCatalog);
    expect(sidebar.map((g) => g.type)).toEqual(["command", "skill", "agent"]);
  });

  it("sorts items by title within a group", () => {
    const { sidebar } = buildIndex(pages, commandCatalog);
    const commands = sidebar.find((g) => g.type === "command");
    expect((commands?.items[0] as { items: Array<{ slug: string }> }).items.map((i) => i.slug)).toEqual(["adr", "commit"]);
  });

  it("lists every page in the markdown", () => {
    const { markdown } = buildIndex(pages, commandCatalog);
    for (const p of pages) {
      expect(markdown).toContain(p.title);
    }
  });

  it("returns an empty sidebar for no pages", () => {
    expect(buildIndex([]).sidebar).toEqual([]);
  });

  it("refuses to emit a legacy flat Commands group without catalog metadata", () => {
    expect(() => buildIndex([
      { type: "command", slug: "commit", title: "commit", markdown: "" },
    ])).toThrow(/catalog metadata/i);
  });

  it("nests command links under registry-backed visibility groups in canonical order", () => {
    const commandPages: RenderedPage[] = [
      { type: "command", slug: "zeta", title: "zeta", markdown: "", commandCatalog: { description: "", commandPath: "commands/zeta.md", visibility: "core", workflow: "change" } },
      { type: "command", slug: "alpha", title: "alpha", markdown: "", commandCatalog: { description: "", commandPath: "commands/alpha.md", visibility: "core", workflow: "change" } },
      { type: "command", slug: "audit", title: "audit", markdown: "", commandCatalog: { description: "", commandPath: "commands/audit.md", visibility: "advanced", workflow: "operate" } },
      { type: "command", slug: "cleanup", title: "cleanup", markdown: "", commandCatalog: { description: "", commandPath: "commands/cleanup.md", visibility: "alias", workflow: "ship", canonical: "commit", replacement: "commit --cleanup" } },
      { type: "command", slug: "conflict", title: "conflict", markdown: "", commandCatalog: { description: "", commandPath: "commands/conflict.md", visibility: "internal", workflow: "decide" } },
      { type: "command", slug: "btw", title: "btw", markdown: "", commandCatalog: { description: "", commandPath: "commands/btw.md", visibility: "deprecated", workflow: "help", replacement: "ask directly" } },
    ];

    const commands = buildIndex(commandPages, commandCatalog).sidebar[0];
    const groups = commands.items as unknown as Array<{
      label: string;
      visibility: string;
      items: Array<{ label: string; slug: string }>;
    }>;

    expect(commands.label).toBe("Commands");
    expect(groups.map((group) => [group.visibility, group.label])).toEqual([
      ["core", "Core"],
      ["advanced", "Advanced"],
      ["alias", "Compatibility aliases"],
      ["internal", "Internal"],
      ["deprecated", "Deprecated"],
    ]);
    expect(groups.map((group) => group.items.map((item) => item.slug))).toEqual([
      ["alpha", "zeta"],
      ["audit"],
      ["cleanup"],
      ["conflict"],
      ["btw"],
    ]);
  });
});

describe("buildIndex — roster metadata (description/tier/preview)", () => {
  it("truncates a multi-sentence description to its first sentence per item", () => {
    const { sidebar } = buildIndex([
      {
        type: "command",
        slug: "commit",
        title: "commit",
        markdown: "",
        description: "Run the commit gate. Nothing lands without it.",
        commandCatalog: { description: "", commandPath: "commands/commit.md", visibility: "core", workflow: "ship" },
      },
    ], commandCatalog);
    const commands = sidebar.find((g) => g.type === "command");
    expect((commands?.items[0] as { items: Array<{ description?: string }> }).items[0].description).toBe("Run the commit gate.");
  });

  it("attaches a model tier to agent items only", () => {
    const { sidebar } = buildIndex([
      { type: "agent", slug: "scout", title: "scout", markdown: "", model: "haiku" },
      { type: "command", slug: "commit", title: "commit", markdown: "", commandCatalog: { description: "", commandPath: "commands/commit.md", visibility: "core", workflow: "ship" } },
    ], commandCatalog);
    const agents = sidebar.find((g) => g.type === "agent");
    const commands = sidebar.find((g) => g.type === "command");
    expect((agents?.items[0] as { tier?: string }).tier).toBe("Haiku");
    expect((commands?.items[0] as { tier?: string }).tier).toBeUndefined();
  });

  it("defaults an agent with no model field to the 'default' tier", () => {
    const { sidebar } = buildIndex([
      { type: "agent", slug: "scout", title: "scout", markdown: "" },
    ]);
    const agents = sidebar.find((g) => g.type === "agent");
    expect((agents?.items[0] as { tier?: string }).tier).toBe("default");
  });

  it("marks a command with a forgeStatus as preview; leaves others unmarked", () => {
    const { sidebar } = buildIndex([
      {
        type: "command",
        slug: "prune",
        title: "prune",
        markdown: "",
        forgeStatus: { kind: "preview-command" },
        commandCatalog: { description: "", commandPath: "commands/prune.md", visibility: "advanced", workflow: "operate" },
      },
      { type: "command", slug: "commit", title: "commit", markdown: "", commandCatalog: { description: "", commandPath: "commands/commit.md", visibility: "core", workflow: "ship" } },
    ], commandCatalog);
    const commands = sidebar.find((g) => g.type === "command");
    const bySlug = Object.fromEntries(
      (commands!.items as Array<{ items: Array<{ slug: string; preview?: boolean }> }>).flatMap((group) => group.items).map((it) => [it.slug, it]),
    );
    expect(bySlug.prune.preview).toBe(true);
    expect(bySlug.commit.preview).toBe(false);
  });

  it("leaves preview undefined for non-command collections", () => {
    const { sidebar } = buildIndex([
      { type: "skill", slug: "tdd", title: "tdd", markdown: "" },
    ]);
    const skills = sidebar.find((g) => g.type === "skill");
    expect((skills?.items[0] as { preview?: boolean }).preview).toBeUndefined();
  });
});
