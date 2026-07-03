import { describe, it, expect } from "vitest";
import { renderCommandPage } from "../../scripts/generator/render-command-page";
import type { PageInput } from "../../scripts/generator/types";

/** Minimal required fields every PageInput now carries. */
const sourceFields = {
  sourceRaw: "Plain command body, no frontmatter markers.\n",
  sourceRelPath: "plugins/ca/commands/commit.md",
  pluginVersion: "2.8.11",
};

function input(overrides: Partial<PageInput> & { name: string }): PageInput {
  return { ...sourceFields, ...overrides };
}

describe("renderCommandPage", () => {
  it("renders title and description, and no body H1", () => {
    const md = renderCommandPage(
      input({ name: "commit", description: "the only path to a commit" }),
    );
    expect(md).toContain("title: commit");
    expect(md).not.toMatch(/^# /m);
    expect(md).toContain("the only path to a commit");
  });

  it("omits model and tools sections", () => {
    const md = renderCommandPage(input({ name: "commit", description: "d" }));
    expect(md).not.toContain("Model tier");
    expect(md).not.toContain("Tools");
  });

  it("emits a quoted description frontmatter line", () => {
    const md = renderCommandPage(
      input({ name: "commit", description: "the only path to a commit" }),
    );
    expect(md).toContain('description: "the only path to a commit"');
  });

  it("escapes double quotes and colons in the description frontmatter line", () => {
    const md = renderCommandPage(
      input({
        name: "commit",
        description: 'The "only" path: a commit — never a direct write.',
      }),
    );
    expect(md).toContain(
      'description: "The \\"only\\" path: a commit — never a direct write."',
    );
  });

  it("omits the description frontmatter line when description is empty", () => {
    const md = renderCommandPage(input({ name: "commit", description: "" }));
    expect(md).not.toContain("description:");
  });

  it("omits the description frontmatter line when description is absent", () => {
    const md = renderCommandPage(input({ name: "commit" }));
    expect(md).not.toContain("description:");
  });

  it("always renders a source embed, even with no curated content", () => {
    const md = renderCommandPage(input({ name: "commit", description: "d" }));
    expect(md).toContain("## Source");
    expect(md).toContain('<details class="ca-source">');
    expect(md).toContain("plugins/ca/commands/commit.md");
    expect(md).toContain("v2.8.11");
  });

  it("merges curated body verbatim after the description", () => {
    const md = renderCommandPage(
      input({
        name: "commit",
        description: "d",
        curated: { entity: "commands/commit", body: "## What it does\n\nCurated prose." },
      }),
    );
    expect(md).toContain("## What it does");
    expect(md).toContain("Curated prose.");
    // curated body must land before the source embed
    expect(md.indexOf("Curated prose.")).toBeLessThan(md.indexOf("## Source"));
  });

  it("renders a gates table when curated.gates is present", () => {
    const md = renderCommandPage(
      input({
        name: "commit",
        description: "d",
        curated: {
          entity: "commands/commit",
          body: "",
          gates: [{ gate: "verification", when: "every run", effect: "must be clean" }],
        },
      }),
    );
    expect(md).toContain("## Gates");
    expect(md).toContain("| Gate | When | Effect |");
    expect(md).toContain("| verification | every run | must be clean |");
  });

  it("renders a Related section when relatedLinks is present", () => {
    const md = renderCommandPage(
      input({
        name: "commit",
        description: "d",
        relatedLinks: [{ label: "sprint", href: "/reference/commands/sprint/" }],
      }),
    );
    expect(md).toContain("## Related");
    expect(md).toContain("[sprint](/reference/commands/sprint/)");
  });

  it("omits Gates and Related sections when absent", () => {
    const md = renderCommandPage(input({ name: "commit", description: "d" }));
    expect(md).not.toContain("## Gates");
    expect(md).not.toContain("## Related");
  });
});
