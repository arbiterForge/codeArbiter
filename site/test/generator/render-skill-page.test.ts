import { describe, it, expect } from "vitest";
import { renderSkillPage } from "../../scripts/generator/render-skill-page";

describe("renderSkillPage", () => {
  it("renders title, heading, and description", () => {
    const md = renderSkillPage({
      name: "tdd",
      description: "the test-first gate",
    });
    expect(md).toContain("title: tdd");
    expect(md).toContain("# tdd");
    expect(md).toContain("the test-first gate");
  });

  it("omits model and tools sections", () => {
    const md = renderSkillPage({ name: "tdd", description: "d" });
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });
});
