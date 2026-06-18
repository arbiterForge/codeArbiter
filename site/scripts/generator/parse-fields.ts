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
  throw new Error("not implemented");
}
