import { describe, it, expect } from "vitest";
import { truncateDescription } from "../../scripts/generator/truncate-description";

describe("truncateDescription", () => {
  it("cuts a multi-sentence description at the first '. '", () => {
    expect(truncateDescription("Foo bar. Baz qux.")).toBe("Foo bar.");
  });

  it("returns a single-sentence description unchanged", () => {
    expect(truncateDescription("Foo bar")).toBe("Foo bar");
  });

  it("returns an already-short description ending in a period unchanged", () => {
    expect(truncateDescription("Foo bar.")).toBe("Foo bar.");
  });

  it("cuts at the first occurrence when there are several", () => {
    expect(truncateDescription("One. Two. Three.")).toBe("One.");
  });

  it("returns an empty string unchanged", () => {
    expect(truncateDescription("")).toBe("");
  });
});
