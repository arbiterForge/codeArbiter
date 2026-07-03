/** rehype-base-links.ts — base-path-safe link rewriting at build time.
 *
 * Starlight does NOT map root-absolute markdown links (`](/overview)`) through
 * the configured `base` — that was a false claim in a prior astro.config.mjs
 * comment. Left alone, such links render as literal `/overview` in the built
 * HTML and 404 once the site is served from a subpath (GitHub Pages:
 * `/codeArbiter/`).
 *
 * This rehype plugin walks the rendered HAST tree for every markdown/MDX page
 * and, for each element `href`/`src` value that is root-absolute (starts with
 * "/", not "//") and not already base-prefixed, prefixes it with the
 * configured base. It is idempotent: running it twice never double-prefixes.
 *
 * Deliberately dependency-free: a plain recursive walk over `node.children`
 * instead of pulling in `unist-util-visit`.
 */

/** Minimal shape of the HAST nodes we care about — element nodes with
 * string-valued properties, and a `children` array for recursion. */
interface HastNode {
  type?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const REWRITTEN_ATTRS = ["href", "src"] as const;

/** True if `value` should be left alone: empty, a fragment-only link,
 * protocol-relative, or carrying a URL scheme (http:, mailto:, data:, ...). */
function isSkippable(value: string): boolean {
  if (value === "") return true;
  if (value.startsWith("#")) return true;
  if (value.startsWith("//")) return true;
  if (!value.startsWith("/")) return true; // not root-absolute — nothing to do
  return false;
}

/** True if `value` is already prefixed with `base` (exactly, or as a
 * directory prefix), so re-prefixing would double it up. */
function isAlreadyBasePrefixed(value: string, base: string): boolean {
  return value === base || value.startsWith(`${base}/`);
}

/** Prefix one attribute value with `base` if it needs it; otherwise return
 * it unchanged. */
function rewriteValue(value: string, base: string): string {
  if (isSkippable(value)) return value;
  if (isAlreadyBasePrefixed(value, base)) return value;
  return `${base}${value}`;
}

function walk(node: HastNode, base: string): void {
  if (node.type === "element" && node.properties) {
    for (const attr of REWRITTEN_ATTRS) {
      const value = node.properties[attr];
      if (typeof value === "string") {
        node.properties[attr] = rewriteValue(value, base);
      }
    }
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) walk(child, base);
  }
}

/**
 * Factory: returns a rehype plugin (a function returning a tree transformer)
 * that base-prefixes root-absolute `href`/`src` values throughout the tree.
 *
 * Usage: `rehypeBaseLinks("/codeArbiter")` in `markdown.rehypePlugins`.
 */
export function rehypeBaseLinks(base: string) {
  return () => (tree: HastNode) => {
    walk(tree, base);
  };
}
