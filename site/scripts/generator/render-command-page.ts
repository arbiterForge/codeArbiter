/** render-command-page.ts — codeArbiter's command reference page renderer. */
import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";
import { renderSourceEmbed } from "./render-source-embed";
import { renderGatesTable } from "./render-gates-table";
import { renderRelatedLinks } from "./render-related-links";

/**
 * Render a command reference page as Starlight-compatible markdown.
 *
 * Anatomy, in order: frontmatter (`title` + quoted `description`) → forge
 * preview badge/callout (when `forgeStatus` is set) → description paragraph
 * → curated body (verbatim, when `curated` is present) → gates table (when
 * `curated.gates` is present) → `## Related` (when `relatedLinks` is
 * present) → `## Source` verbatim embed (always).
 *
 * Starlight renders the frontmatter `title` as the page's only H1, so the
 * body carries no `# <name>` heading. Commands have no model or tools, so
 * the page renders neither a `Model tier` nor a `Tools` line.
 */
export function renderCommandPage(input: PageInput): string {
  const { name, description, forgeStatus, curated, relatedLinks } = input;
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

  const sections: string[] = [`${decoration}${desc}`.trimEnd()];

  if (curated?.body) {
    sections.push(curated.body.trim());
  }

  const gatesTable = renderGatesTable(curated?.gates);
  if (gatesTable) {
    sections.push(`## Gates\n\n${gatesTable}`);
  }

  const related = renderRelatedLinks(relatedLinks);
  if (related) {
    sections.push(related);
  }

  sections.push(
    `## Source\n\n${renderSourceEmbed(
      input.sourceRaw,
      input.sourceRelPath,
      input.pluginVersion,
    )}`,
  );

  return `---
${frontMatter}
---

${sections.join("\n\n")}
`;
}
