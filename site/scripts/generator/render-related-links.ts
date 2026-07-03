/** render-related-links.ts — codeArbiter's `## Related` section renderer. */
import type { RelatedLink } from "./types";

/**
 * Render the `## Related` section for a page's resolved related links.
 *
 * Returns an empty string for an empty/absent list. Links are rendered in
 * the order given (the order `curated.related` was written in).
 */
export function renderRelatedLinks(related: RelatedLink[] | undefined): string {
  if (!related || related.length === 0) return "";

  const links = related.map((r) => `- [${r.label}](${r.href})`).join("\n");
  return `## Related\n\n${links}`;
}
