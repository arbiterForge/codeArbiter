import { repositorySourceRef } from "./source-ref";

/** render-source-embed.ts — codeArbiter's verbatim source-embed renderer.
 *
 * The "source-visible" half of every reference page: a collapsible `<details>`
 * wrapping the plugin source file's raw contents, unmodified, plus a
 * tag-pinned link to view the exact file in the repo at the version it was
 * generated from.
 */

/**
 * Choose a fenced-code-block delimiter long enough to safely wrap `content`.
 *
 * Plugin sources routinely contain triple-backtick fences of their own (code
 * examples inside a command/skill body), so a fixed 3-backtick fence would
 * terminate early. The fence is the longest run of backticks found in
 * `content`, plus one, with a floor of 4 (so short/fence-free content still
 * gets a visually distinct fence from an ordinary ``` block).
 */
function chooseFence(content: string): string {
  const runs = content.match(/`+/g) ?? [];
  const longest = runs.reduce((max, run) => Math.max(max, run.length), 0);
  const length = Math.max(longest + 1, 4);
  return "`".repeat(length);
}

/**
 * Render a verbatim source embed for one plugin source file.
 *
 * Produces a `<details class="ca-source">` block: a summary line naming the
 * repo-relative path and the pinned plugin version, a dynamically-fenced
 * ```` ```md ```` block containing `sourceRaw` unmodified (see
 * {@link chooseFence}), and a "View in repo" link pinned to the `v<version>`
 * tag. `pluginVersion` is passed without a leading `v` — the `v` is added
 * here, once, for both the summary and the URL.
 */
export function renderSourceEmbed(
  sourceRaw: string,
  sourceRelPath: string,
  pluginVersion: string,
  sourceRef: string = repositorySourceRef(),
): string {
  const fence = chooseFence(sourceRaw);
  const tag = `v${pluginVersion}`;
  const repoUrl = `https://github.com/arbiterForge/codeArbiter/blob/${sourceRef}/${sourceRelPath}`;

  return `<details class="ca-source" data-pagefind-ignore>
<summary>Source — <code>${sourceRelPath}</code> (${tag})</summary>

${fence}md
${sourceRaw}
${fence}

<a href="${repoUrl}">View in repo</a>
</details>`;
}

/** One shipped file inside a combined workflow source embed. */
export interface WorkflowSourceFile {
  /** Verbatim raw contents of the shipped file. */
  sourceRaw: string;
  /** Repo-relative path, e.g. `plugins/ca/commands/adr.md`. */
  sourceRelPath: string;
}

/**
 * Render ONE source embed holding several shipped files, for a page that
 * documents a command together with the skill that owns its procedure.
 *
 * Same wrapper as {@link renderSourceEmbed} (a single collapsed,
 * search-excluded `<details class="ca-source">`), so the page still has exactly
 * one source layer and every shipped source stays visible. Each file is
 * labelled with its path, fenced on its own (see {@link chooseFence}) and given
 * its own tag-pinned "View in repo" link, in the order given.
 */
export function renderWorkflowSourceEmbed(
  files: readonly WorkflowSourceFile[],
  pluginVersion: string,
  sourceRef: string = repositorySourceRef(),
): string {
  const tag = `v${pluginVersion}`;
  const paths = files.map((file) => `<code>${file.sourceRelPath}</code>`).join(" and ");
  const blocks = files.map((file) => {
    const fence = chooseFence(file.sourceRaw);
    const repoUrl = `https://github.com/arbiterForge/codeArbiter/blob/${sourceRef}/${file.sourceRelPath}`;
    return `<p class="ca-source__file"><code>${file.sourceRelPath}</code></p>

${fence}md
${file.sourceRaw}
${fence}

<a href="${repoUrl}" aria-label="View ${file.sourceRelPath} in repo">View in repo</a>`;
  });

  return `<details class="ca-source" data-pagefind-ignore>
<summary>Source — ${paths} (${tag})</summary>

${blocks.join("\n\n")}
</details>`;
}
