/**
 * Parse a flat `key: value` frontmatter block into a record.
 *
 * - Splits on the first `:` of each line; key and value are trimmed.
 * - Matching surrounding single or double quotes are stripped from the value.
 * - Lines without a `:` and blank lines are skipped (never throws).
 * - Missing fields are simply absent from the record; extra fields are preserved.
 * - Empty input → `{}`.
 */
export function parseFields(text: string): Record<string, string> {
  const result: Record<string, string> = {};

  if (text === "") return result;

  const lines = text.split("\n");

  for (const line of lines) {
    const trimmedLine = line.trim();

    // Skip blank lines
    if (trimmedLine === "") continue;

    // Find the first colon
    const colonIndex = trimmedLine.indexOf(":");
    if (colonIndex === -1) continue; // no colon, skip line

    const key = trimmedLine.slice(0, colonIndex).trim();
    let value = trimmedLine.slice(colonIndex + 1).trim();

    // Strip a single pair of matching surrounding single or double quotes from the value
    if (
      value.length >= 2 &&
      ((value.startsWith("'") && value.endsWith("'")) ||
        (value.startsWith('"') && value.endsWith('"')))
    ) {
      value = value.slice(1, -1);
    }

    result[key] = value;
  }

  return result;
}
