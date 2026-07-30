/** rehype-table-shell.ts — preserve table semantics while containing overflow.
 *
 * `overflow-x: auto` only works when a table is changed to `display: block`,
 * which breaks the table formatting context and produces the partial-width
 * headers and dead strips seen on the Concept Map and Checkpoints pages.
 *
 * This dependency-free rehype pass wraps every rendered Markdown table in a
 * shared scroll shell. The table remains `display: table`; the shell owns
 * overflow, focus-independent touch scrolling, border, and radius.
 */

interface HastNode {
  type?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function classNames(node: HastNode): string[] {
  const value = node.properties?.className;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  return typeof value === "string" ? value.split(/\s+/) : [];
}

function wrapTables(node: HastNode): void {
  if (!Array.isArray(node.children)) return;

  for (let index = 0; index < node.children.length; index += 1) {
    const child = node.children[index];
    const alreadyWrapped = classNames(node).includes("ca-table-shell");

    if (child.type === "element" && child.tagName === "table" && !alreadyWrapped) {
      node.children[index] = {
        type: "element",
        tagName: "div",
        properties: { className: ["ca-table-shell"] },
        children: [child],
      };
      continue;
    }

    wrapTables(child);
  }
}

/** Rehype plugin factory used by Astro's unified Markdown processor. */
export function rehypeTableShell() {
  return () => (tree: HastNode) => {
    wrapTables(tree);
  };
}
