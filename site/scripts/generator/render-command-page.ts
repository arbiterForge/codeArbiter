/** render-command-page.ts — codeArbiter's command reference page renderer. */
import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";

/**
 * Render a command reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line and, when a description is present, a
 * quoted `description:` frontmatter line (used for the page's meta
 * description). Starlight renders the frontmatter `title` as the page's only
 * H1, so the body carries no `# <name>` heading. Commands have no model or
 * tools, so the page renders neither a `Model tier` nor a `Tools` section.
 *
 * When `forgeStatus` is provided on the input the renderer decorates the page:
 * - `preview-command` — a preview badge (`<span class="ca-badge" data-kind="preview">`)
 *   is injected as the first body element, before the description paragraph.
 * - `preview-flag` — a preview callout (`<div class="ca-callout ca-callout--preview">`)
 *   naming the preview flag is injected as the first body element, before the
 *   description paragraph.
 * - null / undefined — no decoration; the description paragraph is the only
 *   body content.
 */
export function renderCommandPage(input: PageInput): string {
  const { name, description, forgeStatus } = input;
  const desc = description ?? "";

  let decoration = "";
  if (forgeStatus?.kind === "preview-command") {
    decoration =
      '<span class="ca-badge" data-kind="preview">preview</span>\n\n';
  } else if (forgeStatus?.kind === "preview-flag") {
    const flag = forgeStatus.flag;
    decoration =
      `<div class="ca-callout ca-callout--preview">` +
      `<p class="ca-callout__label">Feature Forge — preview</p>` +
      `<p><code>${flag}</code> — preview. This flag is part of the Feature Forge and ships dormant by default. Promotion to stable is driven by real-world evidence.</p>` +
      `</div>\n\n`;
  }

  const descriptionLine = yamlDescriptionLine(desc);
  const frontMatter = descriptionLine
    ? `title: ${name}\n${descriptionLine}`
    : `title: ${name}`;

  return `---
${frontMatter}
---

${decoration}${desc}
`;
}
