import { describe, it, expect } from "vitest";
import { renderCommandPage } from "../../scripts/generator/render-command-page";

describe("renderCommandPage", () => {
  it("renders title, heading, and description", () => {
    const md = renderCommandPage({
      name: "commit",
      description: "the only path to a commit",
    });
    expect(md).toContain("title: commit");
    expect(md).toContain("# commit");
    expect(md).toContain("the only path to a commit");
  });

  it("omits model and tools sections", () => {
    const md = renderCommandPage({ name: "commit", description: "d" });
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });
});
