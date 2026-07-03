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
): string {
  const fence = chooseFence(sourceRaw);
  const tag = `v${pluginVersion}`;
  const repoUrl = `https://github.com/arbiterForge/codeArbiter/blob/${tag}/${sourceRelPath}`;

  return `<details class="ca-source">
<summary>Source — <code>${sourceRelPath}</code> (${tag})</summary>

${fence}md
${sourceRaw}
${fence}

<a href="${repoUrl}">View in repo</a>
</details>`;
}
