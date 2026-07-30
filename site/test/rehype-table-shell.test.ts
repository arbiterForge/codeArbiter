import { describe, expect, it } from "vitest";
import { rehypeTableShell } from "../scripts/rehype-table-shell";

type Node = {
  type?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: Node[];
};

function run(tree: Node): Node {
  const transformer = rehypeTableShell()();
  transformer(tree);
  return tree;
}

function table(): Node {
  return { type: "element", tagName: "table", properties: {}, children: [] };
}

describe("rehypeTableShell", () => {
  it("wraps a rendered table without changing the table element", () => {
    const original = table();
    const tree = run({ type: "root", children: [original] });
    const shell = tree.children?.[0];

    expect(shell?.tagName).toBe("div");
    expect(shell?.properties?.className).toEqual(["ca-table-shell"]);
    expect(shell?.children?.[0]).toBe(original);
  });

  it("finds tables nested inside other rendered content", () => {
    const tree = run({
      type: "root",
      children: [{ type: "element", tagName: "section", properties: {}, children: [table()] }],
    });

    expect(tree.children?.[0].children?.[0].properties?.className).toEqual(["ca-table-shell"]);
  });

  it("is idempotent when a table is already inside the shared shell", () => {
    const tree: Node = {
      type: "root",
      children: [{
        type: "element",
        tagName: "div",
        properties: { className: ["ca-table-shell"] },
        children: [table()],
      }],
    };

    run(tree);
    expect(tree.children?.[0].children?.[0].tagName).toBe("table");
  });
});
