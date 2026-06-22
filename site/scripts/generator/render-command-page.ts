/** render-command-page.ts — codeArbiter's command reference page renderer. */
import type { PageInput } from "./types";

/**
 * Render a command reference page as Starlight-compatible markdown.
 *
 * Includes a `title:` frontmatter line, an `# <name>` heading, and the
 * description. Commands have no model or tools, so the page renders neither a
 * `Model tier` nor a `Tools` section.
 *
 * When `forgeStatus` is provided on the input the renderer decorates the page:
 * - `preview-command` — a preview badge (`<span class="ca-badge" data-kind="preview">`)
 *   is injected immediately after the H1 heading.
 * - `preview-flag` — a preview callout (`<div class="ca-callout ca-callout--preview">`)
 *   naming the preview flag is injected immediately after the H1 heading.
 * - null / undefined — no decoration; stable command renders unchanged.
 */
export function renderCommandPage(input: PageInput): string {
  const { name, description, forgeStatus } = input;
  const desc = description ?? "";

  let decoration = "";
  if (forgeStatus?.kind === "preview-command") {
    decoration =
      '\n\n<span class="ca-badge" data-kind="preview">preview</span>';
  } else if (forgeStatus?.kind === "preview-flag") {
    const flag = forgeStatus.flag;
    decoration =
      `\n\n<div class="ca-callout ca-callout--preview">` +
      `<p class="ca-callout__label">Feature Forge — preview</p>` +
      `<p><code>${flag}</code> — preview. This flag is part of the Feature Forge and ships dormant by default. Promotion to stable is driven by real-world evidence.</p>` +
      `</div>`;
  }

  return `---
title: ${name}
---

# ${name}${decoration}

${desc}
`;
}
