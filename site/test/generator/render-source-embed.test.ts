import { describe, it, expect } from "vitest";
import { renderSourceEmbed } from "../../scripts/generator/render-source-embed";

describe("renderSourceEmbed", () => {
  it("wraps content with no backticks in a minimum 4-backtick fence", () => {
    const md = renderSourceEmbed("plain content, no fences", "plugins/ca/commands/x.md", "2.8.11");
    expect(md).toContain("````md");
    expect(md).toContain("plain content, no fences");
  });

  it("escalates the fence past a 3-backtick run in the content", () => {
    const content = "Some prose.\n```\ncode block\n```\nMore prose.";
    const md = renderSourceEmbed(content, "plugins/ca/commands/x.md", "2.8.11");
    // longest run in content is 3, so fence must be 4.
    expect(md).toContain("````md");
    expect(md).toContain(content);
    // The fence appears exactly twice: opening (with "md") and closing.
    const lines = md.split("\n");
    const fenceLines = lines.filter((l) => l === "````md" || l === "````");
    expect(fenceLines).toHaveLength(2);
  });

  it("escalates past a 4-backtick run in the content to a 5-backtick fence", () => {
    const content = "Nested example:\n````\nsome fenced text\n````\nend.";
    const md = renderSourceEmbed(content, "plugins/ca/commands/x.md", "2.8.11");
    expect(md).toContain("`````md");
  });

  it("pins the View in repo link to the given version tag", () => {
    const md = renderSourceEmbed("x", "plugins/ca/commands/sprint.md", "2.8.11");
    expect(md).toContain(
      '<a href="https://github.com/arbiterForge/codeArbiter/blob/v2.8.11/plugins/ca/commands/sprint.md">View in repo</a>',
    );
  });

  it("renders the details/summary structure with the repo-relative path and version", () => {
    const md = renderSourceEmbed("x", "plugins/ca/commands/sprint.md", "2.8.11");
    expect(md).toContain('<details class="ca-source">');
    expect(md).toContain(
      "<summary>Source — <code>plugins/ca/commands/sprint.md</code> (v2.8.11)</summary>",
    );
    expect(md).toContain("</details>");
  });
});
