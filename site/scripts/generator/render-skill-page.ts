import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";
import { renderSourceEmbed } from "./render-source-embed";
import { renderGatesTable } from "./render-gates-table";
import { renderRelatedLinks } from "./render-related-links";

/**
 * Render a skill reference page as Starlight-compatible markdown.
 *
 * Anatomy, in order: frontmatter (`title` + quoted `description`) →
 * description paragraph → curated body (verbatim, when `curated` is
 * present) → gates table (when `curated.gates` is present) → `## Related`
 * (when `relatedLinks` is present) → `## Source` verbatim embed (always).
 *
 * Starlight renders the frontmatter `title` as the page's only H1, so the
 * body carries no `# <name>` heading.
 */
export function renderSkillPage(input: PageInput): string {
  const { curated, relatedLinks } = input;
  const description = input.description ?? "";
  const descriptionLine = yamlDescriptionLine(description);
  const frontMatterFields = descriptionLine
    ? `title: ${input.name}\n${descriptionLine}`
    : `title: ${input.name}`;

  const sections: string[] = [description];

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
${frontMatterFields}
---

${sections.join("\n\n")}
`;
}
