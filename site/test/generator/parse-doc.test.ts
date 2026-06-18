import { describe, it, expect } from "vitest";
import { parseDoc } from "../../scripts/generator/parse-doc";

describe("parseDoc", () => {
  it("parses fields and body from a full document", () => {
    const r = parseDoc("---\nname: tdd\ndescription: test-first\n---\nBody here");
    expect(r.fields).toEqual({ name: "tdd", description: "test-first" });
    expect(r.body).toBe("Body here");
  });

  it("returns empty fields for a body-only document", () => {
    const r = parseDoc("# Heading\nprose");
    expect(r.fields).toEqual({});
    expect(r.body).toBe("# Heading\nprose");
  });

  it("never throws on empty input", () => {
    expect(parseDoc("")).toEqual({ fields: {}, body: "" });
  });
});
