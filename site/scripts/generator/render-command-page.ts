/** render-command-page.ts — codeArbiter's command reference page renderer. */
import type { PageInput } from "./types";
import { yamlDescriptionLine } from "./yaml-quote";
import { renderSourceEmbed, renderWorkflowSourceEmbed } from "./render-source-embed";
import { demoteHeadings } from "./markdown-fences";
import { renderGatesTable } from "./render-gates-table";
import { renderReaderFields } from "./render-reader-fields";
import { renderRelatedLinks } from "./render-related-links";
import { publicReferenceDescription, renderReferenceLead } from "./render-reference-lead";

/**
 * Render a command reference page as Starlight-compatible markdown.
 *
 * Anatomy, in order: frontmatter (`title` + quoted `description`) → forge
 * preview badge/callout (when `forgeStatus` is set) → description paragraph
 * → `## At a glance` reader fields (when `readerShape` is set)
 * → curated body (verbatim, when `curated` is present) → `## How it runs`
 * (the owning skill's curated text, when `workflowSkill` is merged in) → gates
 * table (the command's gates, then the skill's) → `## Related` (when
 * `relatedLinks` is present) → `## Compatibility` (alias and deprecated
 * routes, with a pointer to the replacement and the skill page when
 * `aliasPointer` is set) → `## Route context` → `## Source` verbatim embed
 * (always, and always exactly one: a merged page carries the command source
 * then the skill source inside that one embed).
 *
 * Starlight renders the frontmatter `title` as the page's only H1, so the
 * body carries no `# <name>` heading. Commands have no model or tools, so
 * the page renders neither a `Model tier` nor a `Tools` line.
 */
export function renderCommandPage(input: PageInput): string {
  const {
    name,
    description,
    forgeStatus,
    curated,
    relatedLinks,
    commandCatalog,
    workflowSkill,
    aliasPointer,
  } = input;
  const desc = publicReferenceDescription(description ?? "");

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
    ? `title: ${name} command\n${descriptionLine}`
    : `title: ${name} command`;

  const sections: string[] = [
    `${decoration}${renderReferenceLead("command", name, desc, input.commandHosts)}`.trimEnd(),
  ];

  const readerFields = renderReaderFields(curated?.reader, input.readerShape);
  if (readerFields) {
    sections.push(readerFields);
  }

  if (curated?.body) {
    sections.push(curated.body.trim());
  }

  // A merged page reads the command text first, then how the skill runs it. The
  // skill's headings drop one level so they nest under "How it runs".
  const skillBody = workflowSkill?.curated?.body.trim();
  if (skillBody) {
    sections.push(`## How it runs\n\n${demoteHeadings(skillBody)}`);
  }

  const gatesTable = renderGatesTable([
    ...(curated?.gates ?? []),
    ...(workflowSkill?.curated?.gates ?? []),
  ]);
  if (gatesTable) {
    sections.push(`## Gates\n\n${gatesTable}`);
  }

  const related = renderRelatedLinks(relatedLinks);
  if (related) {
    sections.push(related);
  }

  if ((commandCatalog?.visibility === "alias" || commandCatalog?.visibility === "deprecated") &&
      commandCatalog.replacement) {
    const lifecycle = commandCatalog.visibility === "alias"
      ? "This compatibility route remains available for existing workflows."
      : "This route is deprecated but remains listed for compatibility.";
    const pointer = aliasPointer
      ? `\n\nThe replacement is documented on the [${aliasPointer.replacementCommand} command page](${aliasPointer.replacementHref}), ` +
        `and the workflow this route runs is documented on the [${aliasPointer.skill} skill page](${aliasPointer.skillHref}).`
      : "";
    sections.push(`## Compatibility\n\n${lifecycle} Use \`${commandCatalog.replacement}\` for new work.${pointer}`);
  }

  // The source catalog supplies membership. Unknown synthetic entities must not
  // acquire broken links, and this remains generated rather than hand-copied.
  if (commandCatalog && /^[a-z][a-z0-9-]*$/.test(name)) {
    sections.push(`## Route context\n\n[Find this entry in the workflow atlas](/concepts/workflow-routes/#atlas-${name}). Compare its related teaching maps, host spelling and context inputs. The exact procedure below remains the owner.`);
  }

  const sourceEmbed = workflowSkill
    ? renderWorkflowSourceEmbed(
        [
          { sourceRaw: input.sourceRaw, sourceRelPath: input.sourceRelPath },
          { sourceRaw: workflowSkill.sourceRaw, sourceRelPath: workflowSkill.sourceRelPath },
        ],
        input.pluginVersion,
      )
    : renderSourceEmbed(input.sourceRaw, input.sourceRelPath, input.pluginVersion);
  sections.push(`## Source\n\n${sourceEmbed}`);

  return `---
${frontMatter}
---

${sections.join("\n\n")}
`;
}
