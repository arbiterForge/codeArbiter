import { describe, it, expect } from "vitest";
import { slugify } from "../../scripts/generator/slugify";

describe("slugify", () => {
  it("lowercases and hyphenates spaces", () => {
    expect(slugify("Hello World")).toBe("hello-world");
  });

  it("collapses runs of non-alphanumeric characters to a single hyphen", () => {
    expect(slugify("Foo__Bar!!Baz")).toBe("foo-bar-baz");
  });

  it("strips leading and trailing separators (e.g. /ca:commit)", () => {
    expect(slugify("/ca:commit")).toBe("ca-commit");
  });

  it("is idempotent", () => {
    const once = slugify("Some Mixed: Name!");
    expect(slugify(once)).toBe(once);
    expect(slugify("already-slug")).toBe("already-slug");
  });
});
