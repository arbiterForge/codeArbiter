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

  it("does not split at vs. abbreviations", () => {
    expect(
      truncateDescription("Surface persona vs. docs vs. code. Present both sides."),
    ).toBe("Surface persona vs. docs vs. code.");
  });

  it("does not split at e.g. or i.e. abbreviations", () => {
    expect(
      truncateDescription("Use a source, e.g. the manifest. Then verify it."),
    ).toBe("Use a source, e.g. the manifest.");
  });
});
