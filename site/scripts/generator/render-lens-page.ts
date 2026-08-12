/** render-lens-page.ts — renders one tribunal lens card as a reference page.
 *
 * Each lens card (see `collect-lenses.ts`) becomes a Starlight page at
 * `/reference/tribunal-lenses/<lens>/`. The page keeps the card's own
 * sections (mandate opener, Scope emphasis, Required reading, Checklist,
 * Exposure, Out of scope) and adds a short generated lead tying the card to
 * the generic `tribunal-lens-reviewer` agent that executes it.
 */
import { yamlDescriptionLine } from "./yaml-quote";
import { publicReferenceDescription } from "./render-reference-lead";
import type { LensCard, LensPage } from "./types";

/** URL path of the generic executor agent's reference page. */
const REVIEWER_HREF = "/reference/agents/tribunal-lens-reviewer/";

/** Strip a leading BOM and normalize CRLF to LF, matching generate.ts's read boundary. */
function normalize(raw: string): string {
  const noBom = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
  return noBom.replace(/\r\n/g, "\n");
}

/** One-sentence page description, shared by the frontmatter, index table, and sidebar. */
export function lensDescription(slug: string): string {
  return (
    `The ${slug} tribunal lens: the per-lens mandate the tribunal-lens-reviewer ` +
    `agent executes when a /ca:tribunal deep audit activates this lens.`
  );
}

/**
 * Render a lens card as a Starlight-compatible markdown page.
 *
 * Anatomy, in order: frontmatter (`title` + quoted `description`) → generated
 * lead naming the executing agent → the card body verbatim minus its `# <lens>
 * — lens mandate` H1 (Starlight renders the frontmatter title as the page's
 * only H1). Claude-specific environment placeholders in the body are
 * translated for readers via {@link publicReferenceDescription} — unlike the
 * source embeds on entity pages, a lens page's body *is* the reader-facing
 * copy.
 */
export function renderLensPage(card: LensCard): LensPage {
  const { slug } = card;
  const title = `${slug} lens`;
  const description = lensDescription(slug);
  const descriptionLine = yamlDescriptionLine(description);
  const frontMatterFields = descriptionLine
    ? `title: ${title}\n${descriptionLine}`
    : `title: ${title}`;

  // Drop the card's own H1 (`# <lens> — lens mandate`): the frontmatter title
  // already renders as the page H1. Everything after it — the mandate opener
  // paragraph and every `##` section — is kept. Placeholders that sit inside a
  // code span get the translated prose moved OUTSIDE the backticks (so the
  // span stays a real path); any remaining bare placeholders go through the
  // shared {@link publicReferenceDescription} translation.
  const body = publicReferenceDescription(
    normalize(card.raw)
      .replace(/^#[^\n]*\n/, "")
      .trim()
      .replace(/`\$\{CLAUDE_PROJECT_DIR\}\/([^`]+)`/g, "the repository's `$1`")
      .replace(/`\$\{CLAUDE_PLUGIN_ROOT\}\/([^`]+)`/g, "the installed plugin's `$1`"),
  );

  const lead =
    `**Tribunal lens card.** This is not a standalone agent: when the ` +
    `[\`/ca:tribunal\`](/reference/commands/tribunal/) deep audit activates the ` +
    `\`${slug}\` lens, the generic ` +
    `[\`tribunal-lens-reviewer\`](${REVIEWER_HREF}) agent is dispatched once under the ` +
    `\`${slug}\` assignment and executes this card as its mandate.`;

  const markdown = `---\n${frontMatterFields}\n---\n\n${lead}\n\n${body}\n`;

  return { slug, title, markdown, description };
}
