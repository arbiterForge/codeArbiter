/** yaml-quote.ts — codeArbiter's shared YAML double-quoted-scalar helper. */

/**
 * Escape a string for use inside a YAML double-quoted scalar.
 *
 * Backslashes are escaped first (so a later `"` escape doesn't double-escape
 * an already-inserted backslash), then double quotes are escaped as `\"`.
 * Source descriptions routinely contain colons, em-dashes, and double quotes,
 * all of which are safe inside a double-quoted scalar once escaped this way.
 */
export function yamlQuoteEscape(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

/**
 * Render a YAML frontmatter `description:` line for the given value.
 *
 * Returns an empty string when `value` is empty or absent, so callers can
 * omit the line entirely (Starlight then falls back to the site default
 * meta description) rather than emitting `description: ""`.
 */
export function yamlDescriptionLine(value: string | undefined): string {
  if (!value) return "";
  return `description: "${yamlQuoteEscape(value)}"`;
}
