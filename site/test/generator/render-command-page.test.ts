import { describe, it, expect } from "vitest";
import { renderCommandPage } from "../../scripts/generator/render-command-page";

describe("renderCommandPage", () => {
  it("renders title and description, and no body H1", () => {
    const md = renderCommandPage({
      name: "commit",
      description: "the only path to a commit",
    });
    expect(md).toContain("title: commit");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("the only path to a commit");
  });

  it("omits model and tools sections", () => {
    const md = renderCommandPage({ name: "commit", description: "d" });
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderCommandPage({
      name: "commit",
      description: "the only path to a commit",
    });
    expect(md).toContain('description: "the only path to a commit"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderCommandPage({
      name: "commit",
      description: 'The "only" path: a commit — never a direct write.',
    });
    expect(md).toContain(
      'description: "The \\"only\\" path: a commit — never a direct write."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderCommandPage({ name: "commit", description: "" });
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderCommandPage({ name: "commit" });
    expect(md).not.toContain("description:");
  });
});
