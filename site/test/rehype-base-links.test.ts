import { describe, it, expect } from "vitest";
import { rehypeBaseLinks } from "../scripts/rehype-base-links";

/** Minimal HAST-shaped fixture builder. */
function elementTree(children: Array<Record<string, unknown>>) {
  return {
    type: "root",
    children: children.map((c) => ({ type: "element", ...c })),
  };
}

function run(tree: unknown, base = "/codeArbiter") {
  const plugin = rehypeBaseLinks(base);
  const transformer = plugin();
  // @ts-expect-error — test-only loose call, tree shape matches our HastNode
  transformer(tree);
  return tree;
}

describe("rehypeBaseLinks", () => {
  it("prefixes a bare-root href", () => {
    const tree = elementTree([{ tagName: "a", properties: { href: "/overview" }, children: [] }]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("/codeArbiter/overview");
  });

  it("prefixes a bare-root src", () => {
    const tree = elementTree([{ tagName: "img", properties: { src: "/diagrams/x.svg" }, children: [] }]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.src).toBe("/codeArbiter/diagrams/x.svg");
  });

  it("leaves an already-prefixed href untouched, and is idempotent across repeated runs", () => {
    const tree = elementTree([{ tagName: "a", properties: { href: "/codeArbiter/overview" }, children: [] }]);
    run(tree);
    run(tree); // run again — must not double-prefix
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("/codeArbiter/overview");
  });

  it("leaves the bare base path itself untouched", () => {
    const tree = elementTree([{ tagName: "a", properties: { href: "/codeArbiter" }, children: [] }]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("/codeArbiter");
  });

  it("leaves external URLs untouched", () => {
    const tree = elementTree([
      { tagName: "a", properties: { href: "https://example.com/x" }, children: [] },
    ]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("https://example.com/x");
  });

  it("leaves protocol-relative URLs untouched", () => {
    const tree = elementTree([{ tagName: "a", properties: { href: "//host/x" }, children: [] }]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("//host/x");
  });

  it("leaves fragment-only anchors untouched", () => {
    const tree = elementTree([{ tagName: "a", properties: { href: "#section" }, children: [] }]);
    run(tree);
    // @ts-expect-error loose test access
    expect(tree.children[0].properties.href).toBe("#section");
  });

  it("recurses into nested children", () => {
    const tree = {
      type: "root",
      children: [
        {
          type: "element",
          tagName: "div",
          properties: {},
          children: [{ type: "element", tagName: "a", properties: { href: "/overview" }, children: [] }],
        },
      ],
    };
    run(tree);
    expect(tree.children[0].children[0].properties.href).toBe("/codeArbiter/overview");
  });
});
