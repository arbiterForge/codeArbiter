import { describe, it, expect } from "vitest";
import { assignSlugs } from "../../scripts/generator/assign-slugs";

describe("assignSlugs", () => {
  it("slugifies names with no collisions", () => {
    expect(assignSlugs(["Foo", "Bar"])).toEqual(["foo", "bar"]);
  });

  it("suffixes colliding slugs in order of appearance", () => {
    expect(assignSlugs(["Foo", "foo", "Bar"])).toEqual(["foo", "foo-2", "bar"]);
  });

  it("suffixes triple collisions deterministically", () => {
    expect(assignSlugs(["a", "a", "a"])).toEqual(["a", "a-2", "a-3"]);
  });

  it("preserves input length and order", () => {
    const out = assignSlugs(["One", "Two", "Three"]);
    expect(out).toHaveLength(3);
    expect(out).toEqual(["one", "two", "three"]);
  });
});
