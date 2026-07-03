import { describe, it, expect } from "vitest";
import { renderSkillPage } from "../../scripts/generator/render-skill-page";

describe("renderSkillPage", () => {
  it("renders title and description, and no body H1", () => {
    const md = renderSkillPage({
      name: "tdd",
      description: "the test-first gate",
    });
    expect(md).toContain("title: tdd");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("the test-first gate");
  });

  it("omits model and tools sections", () => {
    const md = renderSkillPage({ name: "tdd", description: "d" });
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderSkillPage({
      name: "tdd",
      description: "the test-first gate",
    });
    expect(md).toContain('description: "the test-first gate"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderSkillPage({
      name: "tdd",
      description: 'The "test-first" gate: red, green — refactor.',
    });
    expect(md).toContain(
      'description: "The \\"test-first\\" gate: red, green — refactor."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderSkillPage({ name: "tdd", description: "" });
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderSkillPage({ name: "tdd" });
    expect(md).not.toContain("description:");
  });
});
