import { describe, it, expect } from "vitest";
import { renderAgentPage } from "../../scripts/generator/render-agent-page";
import type { PageInput } from "../../scripts/generator/types";

const sourceFields = {
  sourceRaw: "---\nname: myagent\n---\n\nBody.\n",
  sourceRelPath: "plugins/ca/agents/myagent.md",
  pluginVersion: "2.8.11",
};

function input(overrides: Partial<PageInput> & { name: string }): PageInput {
  return { ...sourceFields, ...overrides };
}

describe("renderAgentPage", () => {
  it("renders title, description, model tier, and tools, with no body H1", () => {
    const md = renderAgentPage(
      input({
        name: "myagent",
        description: "reviews a thing",
        model: "sonnet",
        tools: "Read, Grep",
      }),
    );
    expect(md).toContain("title: myagent");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("reviews a thing");
    expect(md).toContain("Sonnet");
    expect(md).toContain("`Read`, `Grep`");
  });

  it("shows the default tier when model is missing", () => {
    const md = renderAgentPage(
      input({ name: "nomodel", description: "no model here", tools: "Read" }),
    );
    expect(md).toContain("default");
    expect(md).toContain("`Read`");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderAgentPage(
      input({ name: "myagent", description: "reviews a thing", tools: "Read" }),
    );
    expect(md).toContain('description: "reviews a thing"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderAgentPage(
      input({
        name: "myagent",
        description: 'Reviews "the" thing: end-to-end — nothing skipped.',
        tools: "Read",
      }),
    );
    expect(md).toContain(
      'description: "Reviews \\"the\\" thing: end-to-end — nothing skipped."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderAgentPage(input({ name: "myagent", description: "", tools: "Read" }));
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderAgentPage(input({ name: "myagent", tools: "Read" }));
    expect(md).not.toContain("description:");
  });

  it("always renders a source embed, even with no curated content", () => {
    const md = renderAgentPage(input({ name: "myagent", tools: "Read" }));
    expect(md).toContain("## Source");
    expect(md).toContain('<details class="ca-source">');
  });

  it("places Model tier / Tools before the curated body", () => {
    const md = renderAgentPage(
      input({
        name: "myagent",
        description: "d",
        tools: "Read",
        curated: { entity: "agents/myagent", body: "## What it does\n\nCurated prose." },
      }),
    );
    expect(md.indexOf("Tools")).toBeLessThan(md.indexOf("Curated prose."));
    expect(md.indexOf("Curated prose.")).toBeLessThan(md.indexOf("## Source"));
  });

  it("renders a gates table when curated.gates is present", () => {
    const md = renderAgentPage(
      input({
        name: "myagent",
        description: "d",
        tools: "Read",
        curated: {
          entity: "agents/myagent",
          body: "",
          gates: [{ gate: "review", when: "dispatched", effect: "blocks on findings" }],
        },
      }),
    );
    expect(md).toContain("## Gates");
    expect(md).toContain("| review | dispatched | blocks on findings |");
  });

  it("renders a Related section when relatedLinks is present", () => {
    const md = renderAgentPage(
      input({
        name: "myagent",
        description: "d",
        tools: "Read",
        relatedLinks: [{ label: "commit", href: "/reference/commands/commit/" }],
      }),
    );
    expect(md).toContain("## Related");
    expect(md).toContain("[commit](/reference/commands/commit/)");
  });
});
