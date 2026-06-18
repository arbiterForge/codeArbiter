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
