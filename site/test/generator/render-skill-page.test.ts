import { describe, it, expect } from "vitest";
import { renderSkillPage } from "../../scripts/generator/render-skill-page";
import type { PageInput } from "../../scripts/generator/types";

const sourceFields = {
  sourceRaw: "---\nname: tdd\n---\n\nBody.\n",
  sourceRelPath: "plugins/ca/skills/tdd/SKILL.md",
  pluginVersion: "2.8.11",
};

function input(overrides: Partial<PageInput> & { name: string }): PageInput {
  return { ...sourceFields, ...overrides };
}

describe("renderSkillPage", () => {
  it("renders title and description, and no body H1", () => {
    const md = renderSkillPage(input({ name: "tdd", description: "the test-first gate" }));
    expect(md).toContain("title: tdd");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("the test-first gate");
  });

  it("omits model and tools sections", () => {
    const md = renderSkillPage(input({ name: "tdd", description: "d" }));
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderSkillPage(input({ name: "tdd", description: "the test-first gate" }));
    expect(md).toContain('description: "the test-first gate"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderSkillPage(
      input({ name: "tdd", description: 'The "test-first" gate: red, green — refactor.' }),
    );
    expect(md).toContain(
      'description: "The \\"test-first\\" gate: red, green — refactor."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderSkillPage(input({ name: "tdd", description: "" }));
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderSkillPage(input({ name: "tdd" }));
    expect(md).not.toContain("description:");
  });

  it("always renders a source embed, even with no curated content", () => {
    const md = renderSkillPage(input({ name: "tdd", description: "d" }));
    expect(md).toContain("## Source");
    expect(md).toContain('<details class="ca-source">');
  });

  it("merges curated body, gates table, and related links", () => {
    const md = renderSkillPage(
      input({
        name: "tdd",
        description: "d",
        curated: {
          entity: "skills/tdd",
          body: "## What it does\n\nCurated prose.",
          gates: [{ gate: "red", when: "phase 2", effect: "test must fail first" }],
        },
        relatedLinks: [{ label: "sprint", href: "/reference/commands/sprint/" }],
      }),
    );
    expect(md).toContain("Curated prose.");
    expect(md).toContain("## Gates");
    expect(md).toContain("## Related");
    expect(md.indexOf("Curated prose.")).toBeLessThan(md.indexOf("## Gates"));
    expect(md.indexOf("## Gates")).toBeLessThan(md.indexOf("## Related"));
    expect(md.indexOf("## Related")).toBeLessThan(md.indexOf("## Source"));
  });
});
