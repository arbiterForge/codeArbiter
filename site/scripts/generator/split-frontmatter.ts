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
  const lines = raw.split("\n");

  // Check for a leading frontmatter delimiter: first line must be exactly "---".
  if (lines.length > 0 && lines[0] === "---") {
    // Look for the closing delimiter (the next line that is exactly "---").
    for (let i = 1; i < lines.length; i++) {
      if (lines[i] === "---") {
        // Extract the content between delimiters.
        const frontmatterLines = lines.slice(1, i);
        const frontmatter = frontmatterLines.join("\n");

        // Build the body, stripping leading empty (blank) lines.
        let bodyStartIndex = i + 1;
        while (bodyStartIndex < lines.length && lines[bodyStartIndex] === "") {
          bodyStartIndex++;
        }
        const bodyLines = lines.slice(bodyStartIndex);
        const body = bodyLines.join("\n");

        return { frontmatter, body };
      }
    }
    // No matching closing delimiter → treat as if no frontmatter exists.
  }

  // No valid leading frontmatter block.
  return { frontmatter: null, body: raw };
}
