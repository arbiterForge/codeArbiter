/**
 * Truncate a description to its first sentence for a compact table cell.
 *
 * Cuts at the first ". " (period + space) and keeps the leading period, so a
 * multi-sentence frontmatter `description` collapses to one line in the
 * roster tables. A description with no ". " (already one sentence, or ending
 * in a bare period with nothing after it) is returned unchanged.
 */
export function truncateDescription(text: string): string {
  const idx = text.indexOf(". ");
  if (idx === -1) return text;
  return text.slice(0, idx + 1);
}
