import { modelTier } from "./model-tier";
import { formatToolsList } from "./format-tools-list";
import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";

/**
 * Render an agent reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line and, when a description is present, a
 * quoted `description:` frontmatter line (used for the page's meta
 * description). Starlight renders the frontmatter `title` as the page's only
 * H1, so the body carries no `# <name>` heading — it opens with the
 * description, followed by a `**Model tier:**` line (via {@link modelTier},
 * so a missing model shows `default`), and a `**Tools:**` line (via
 * {@link formatToolsList}).
 */
export function renderAgentPage(input: PageInput): string {
  const description = input.description ?? "";
  const descriptionLine = yamlDescriptionLine(description);
  const frontMatterFields = descriptionLine
    ? `title: ${input.name}\n${descriptionLine}`
    : `title: ${input.name}`;
  const frontMatter = `---\n${frontMatterFields}\n---`;
  const modelLine = `- **Model tier:** ${modelTier(input.model)}`;
  const toolsLine = `- **Tools:** ${formatToolsList(input.tools)}`;

  return `${frontMatter}\n\n${description}\n\n${modelLine}\n${toolsLine}\n`;
}
