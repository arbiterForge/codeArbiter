import { modelTier } from "./model-tier";
import { formatToolsList } from "./format-tools-list";
import type { PageInput } from "./types";

/**
 * Render an agent reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line, an `# <name>` heading, the description,
 * a `**Model tier:**` line (via {@link modelTier}, so a missing model shows
 * `default`), and a `**Tools:**` line (via {@link formatToolsList}).
 */
export function renderAgentPage(input: PageInput): string {
  throw new Error("not implemented");
}
