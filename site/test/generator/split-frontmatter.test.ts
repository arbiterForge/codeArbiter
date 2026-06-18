import { describe, it, expect } from "vitest";
import { splitFrontmatter } from "../../scripts/generator/split-frontmatter";

describe("splitFrontmatter", () => {
  it("splits a single-field frontmatter block from the body", () => {
    const r = splitFrontmatter("---\ndescription: x\n---\nHello");
    expect(r.frontmatter).toBe("description: x");
    expect(r.body).toBe("Hello");
  });

  it("splits a multi-line frontmatter block and strips leading body newlines", () => {
    const r = splitFrontmatter("---\na: 1\nb: 2\n---\n\nBody");
    expect(r.frontmatter).toBe("a: 1\nb: 2");
    expect(r.body).toBe("Body");
  });

  it("returns a null block when there is no leading frontmatter", () => {
    expect(splitFrontmatter("# nope\ntext")).toEqual({
      frontmatter: null,
      body: "# nope\ntext",
    });
  });

  it("does not treat a non-leading --- as frontmatter", () => {
    const r = splitFrontmatter("intro\n---\nlater");
    expect(r.frontmatter).toBeNull();
    expect(r.body).toBe("intro\n---\nlater");
  });

  it("never throws on empty input", () => {
    expect(splitFrontmatter("")).toEqual({ frontmatter: null, body: "" });
  });
});
