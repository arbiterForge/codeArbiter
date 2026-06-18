import type { PageInput } from "./types";

/**
 * Render a command reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line, an `# <name>` heading, and the
 * description. Commands have no model or tools, so the page renders neither a
 * `Model tier` nor a `Tools` section.
 */
export function renderCommandPage(input: PageInput): string {
  const { name, description } = input;
  const desc = description ?? "";

  return `---
title: ${name}
---

# ${name}

${desc}
`;
}
