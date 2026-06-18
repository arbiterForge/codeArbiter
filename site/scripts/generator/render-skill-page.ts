import type { PageInput } from "./types";

/**
 * Render a skill reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line, an `# <name>` heading, and the
 * description. Skills render neither a `Model tier` nor a `Tools` section.
 */
export function renderSkillPage(input: PageInput): string {
  throw new Error("not implemented");
}
