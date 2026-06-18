import { describe, it, expect } from "vitest";
import { renderAgentPage } from "../../scripts/generator/render-agent-page";

describe("renderAgentPage", () => {
  it("renders title, heading, description, model tier, and tools", () => {
    const md = renderAgentPage({
      name: "myagent",
      description: "reviews a thing",
      model: "sonnet",
      tools: "Read, Grep",
    });
    expect(md).toContain("title: myagent");
    expect(md).toContain("# myagent");
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
});
