import { describe, it, expect } from "vitest";
import { renderAgentPage } from "../../scripts/generator/render-agent-page";

describe("renderAgentPage", () => {
  it("renders title, description, model tier, and tools, with no body H1", () => {
    const md = renderAgentPage({
      name: "myagent",
      description: "reviews a thing",
      model: "sonnet",
      tools: "Read, Grep",
    });
    expect(md).toContain("title: myagent");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("reviews a thing");
    expect(md).toContain("Sonnet");
    expect(md).toContain("`Read`, `Grep`");
  });

  it("shows the default tier when model is missing", () => {
    const md = renderAgentPage({
      name: "nomodel",
      description: "no model here",
      tools: "Read",
    });
    expect(md).toContain("default");
    expect(md).toContain("`Read`");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderAgentPage({
      name: "myagent",
      description: "reviews a thing",
      tools: "Read",
    });
    expect(md).toContain('description: "reviews a thing"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderAgentPage({
      name: "myagent",
      description: 'Reviews "the" thing: end-to-end — nothing skipped.',
      tools: "Read",
    });
    expect(md).toContain(
      'description: "Reviews \\"the\\" thing: end-to-end — nothing skipped."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderAgentPage({ name: "myagent", description: "", tools: "Read" });
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderAgentPage({ name: "myagent", tools: "Read" });
    expect(md).not.toContain("description:");
  });
});
