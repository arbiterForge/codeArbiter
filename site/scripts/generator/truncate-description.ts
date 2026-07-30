/**
 * Truncate a description to its first sentence for a compact table cell.
 *
 * Cuts at the first sentence-ending period while skipping common abbreviations
 * such as "vs.", "e.g.", and "i.e.". This avoids visibly broken roster text
 * like "persona vs." while keeping the index compact.
 */
export function truncateDescription(text: string): string {
  const abbreviations = new Set([
    "vs.",
    "e.g.",
    "i.e.",
    "etc.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
  ]);

  for (let idx = text.indexOf(". "); idx !== -1; idx = text.indexOf(". ", idx + 2)) {
    const prefix = text.slice(0, idx + 1);
    const token = prefix.match(/(?:^|\s)(\S+)$/)?.[1]?.toLowerCase() ?? "";
    if (!abbreviations.has(token)) return prefix;
  }

  return text;
}
