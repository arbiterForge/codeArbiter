import { describe, it, expect } from "vitest";
import { renderGatesTable } from "../../scripts/generator/render-gates-table";

describe("renderGatesTable", () => {
  it("returns an empty string for an empty list", () => {
    expect(renderGatesTable([])).toBe("");
  });

  it("returns an empty string for undefined", () => {
    expect(renderGatesTable(undefined)).toBe("");
  });

  it("renders a markdown table with the fixed header", () => {
    const md = renderGatesTable([
      { gate: "verification", when: "every run", effect: "must be clean" },
    ]);
    expect(md).toContain("| Gate | When | Effect |");
    expect(md).toContain("| --- | --- | --- |");
    expect(md).toContain("| verification | every run | must be clean |");
  });

  it("renders one row per gate, in order", () => {
    const md = renderGatesTable([
      { gate: "a", when: "w1", effect: "e1" },
      { gate: "b", when: "w2", effect: "e2" },
    ]);
    const rows = md.split("\n");
    expect(rows[2]).toBe("| a | w1 | e1 |");
    expect(rows[3]).toBe("| b | w2 | e2 |");
  });
});
