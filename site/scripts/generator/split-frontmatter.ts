import type { SplitResult } from "./types";

/**
 * Split a leading `---`-delimited frontmatter block from a source file.
 *
 * - When the raw text starts with a `---` line and has a matching closing `---`
 *   line, `frontmatter` is the text between them (no surrounding newlines) and
 *   `body` is the remainder with leading newlines stripped.
 * - When there is no leading frontmatter, `frontmatter` is null and `body` is the
 *   input unchanged.
 * - Never throws (empty input → `{ frontmatter: null, body: "" }`).
 */
export function splitFrontmatter(raw: string): SplitResult {
  throw new Error("not implemented");
}
