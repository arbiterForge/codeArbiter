import { describe, it, expect } from "vitest";
import { parseFields } from "../../scripts/generator/parse-fields";

describe("parseFields", () => {
  it("parses a flat key: value block", () => {
    expect(parseFields("description: Hello world\nname: foo")).toEqual({
      description: "Hello world",
      name: "foo",
    });
  });

  it("leaves missing fields absent (does not invent them)", () => {
    const r = parseFields("description: only this");
    expect(r.description).toBe("only this");
    expect(r.model).toBeUndefined();
    expect(r.name).toBeUndefined();
  });

  it("preserves extra fields and strips surrounding quotes", () => {
    const r = parseFields('description: cmd\nargument-hint: "[note]"');
    expect(r["argument-hint"]).toBe("[note]");
    expect(r.description).toBe("cmd");
  });

  it("splits only on the first colon (values may contain colons)", () => {
    expect(parseFields("description: a: b")).toEqual({ description: "a: b" });
  });

  it("skips malformed lines without throwing", () => {
    expect(parseFields("description: ok\nbadline\nname: x")).toEqual({
      description: "ok",
      name: "x",
    });
  });

  it("returns an empty record for empty input", () => {
    expect(parseFields("")).toEqual({});
  });
});
