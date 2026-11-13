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
  it("reserves every emitted slug, including suffixed forms (HW-24)", () => {
    const out = assignSlugs(["foo", "foo", "foo-2"]);
    expect(new Set(out).size).toBe(3);
    expect(out).toEqual(["foo", "foo-2", "foo-2-2"]);
  });

  it("never emits a duplicate for names already ending in numeric suffixes", () => {
    const inputs = [
      ["foo-2", "foo", "foo"],
      ["a", "a-2", "a", "a-3", "a"],
      ["Foo Bar", "foo-bar", "foo bar-2", "FOO BAR"],
      ["x-2", "x-2", "x", "x"],
    ];
    for (const names of inputs) {
      const out = assignSlugs(names);
      expect(out).toHaveLength(names.length);
      expect(new Set(out).size).toBe(names.length);
      expect(assignSlugs(names)).toEqual(out);
    }
    expect(assignSlugs(["foo-2", "foo", "foo"])).toEqual(["foo-2", "foo", "foo-3"]);
  });
});
