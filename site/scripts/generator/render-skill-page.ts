import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";

/**
 * Render a skill reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line and, when a description is present, a
 * quoted `description:` frontmatter line (used for the page's meta
 * description). Starlight renders the frontmatter `title` as the page's only
 * H1, so the body carries no `# <name>` heading — it opens with the
 * description.
 */
export function renderSkillPage(input: PageInput): string {
  const description = input.description ?? "";
  const descriptionLine = yamlDescriptionLine(description);
  const frontMatterFields = descriptionLine
    ? `title: ${input.name}\n${descriptionLine}`
    : `title: ${input.name}`;

  return `---
${frontMatterFields}
---
${description}
`;
}
