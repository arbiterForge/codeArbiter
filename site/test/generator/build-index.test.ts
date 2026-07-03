import { describe, it, expect } from "vitest";
import { buildIndex } from "../../scripts/generator/build-index";
import type { RenderedPage } from "../../scripts/generator/types";

const pages: RenderedPage[] = [
  { type: "command", slug: "commit", title: "commit", markdown: "" },
  { type: "agent", slug: "scout", title: "scout", markdown: "" },
  { type: "command", slug: "adr", title: "adr", markdown: "" },
  { type: "skill", slug: "tdd", title: "tdd", markdown: "" },
];

describe("buildIndex", () => {
  it("groups pages by type in fixed order, only non-empty groups", () => {
    const { sidebar } = buildIndex(pages);
    expect(sidebar.map((g) => g.type)).toEqual(["command", "skill", "agent"]);
  });

  it("sorts items by title within a group", () => {
    const { sidebar } = buildIndex(pages);
    const commands = sidebar.find((g) => g.type === "command");
    expect(commands?.items.map((i) => i.slug)).toEqual(["adr", "commit"]);
  });

  it("lists every page in the markdown", () => {
    const { markdown } = buildIndex(pages);
    for (const p of pages) {
      expect(markdown).toContain(p.title);
    }
  });

  it("returns an empty sidebar for no pages", () => {
    expect(buildIndex([]).sidebar).toEqual([]);
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
      },
    ]);
    const commands = sidebar.find((g) => g.type === "command");
    expect(commands?.items[0].description).toBe("Run the commit gate.");
  });

  it("attaches a model tier to agent items only", () => {
    const { sidebar } = buildIndex([
      { type: "agent", slug: "scout", title: "scout", markdown: "", model: "haiku" },
      { type: "command", slug: "commit", title: "commit", markdown: "" },
    ]);
    const agents = sidebar.find((g) => g.type === "agent");
    const commands = sidebar.find((g) => g.type === "command");
    expect(agents?.items[0].tier).toBe("Haiku");
    expect(commands?.items[0].tier).toBeUndefined();
  });

  it("defaults an agent with no model field to the 'default' tier", () => {
    const { sidebar } = buildIndex([
      { type: "agent", slug: "scout", title: "scout", markdown: "" },
    ]);
    const agents = sidebar.find((g) => g.type === "agent");
    expect(agents?.items[0].tier).toBe("default");
  });

  it("marks a command with a forgeStatus as preview; leaves others unmarked", () => {
    const { sidebar } = buildIndex([
      {
        type: "command",
        slug: "prune",
        title: "prune",
        markdown: "",
        forgeStatus: { kind: "preview-command" },
      },
      { type: "command", slug: "commit", title: "commit", markdown: "" },
    ]);
    const commands = sidebar.find((g) => g.type === "command");
    const bySlug = Object.fromEntries(commands!.items.map((it) => [it.slug, it]));
    expect(bySlug.prune.preview).toBe(true);
    expect(bySlug.commit.preview).toBe(false);
  });

  it("leaves preview undefined for non-command collections", () => {
    const { sidebar } = buildIndex([
      { type: "skill", slug: "tdd", title: "tdd", markdown: "" },
    ]);
    const skills = sidebar.find((g) => g.type === "skill");
    expect(skills?.items[0].preview).toBeUndefined();
  });
});
