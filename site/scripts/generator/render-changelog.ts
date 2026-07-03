/** render-changelog.ts — renders the repo-root `CHANGELOG.md` into the
 * gitignored `site/src/content/docs/changelog.md` at gen time (docs-site-overhaul
 * spec, decision f).
 *
 * The source file carries its own `# Changelog` H1 and a short preamble above
 * the first version heading; Starlight pages get their title from frontmatter,
 * so both are stripped here to avoid a duplicate `<h1>`. Every `## [X.Y.Z]`
 * version heading and its body is passed through unchanged — this is a
 * generated verbatim layer, not a rewrite.
 */
import { yamlDescriptionLine } from "./yaml-quote";

const DESCRIPTION =
  "Every released version of codeArbiter, generated from the repository's own CHANGELOG.md.";

const REPO_URL = "https://github.com/arbiterForge/codeArbiter";

/** CHANGELOG.md links to PRs with a repo-root-relative `../../pull/NN` path — correct
 * when GitHub renders the file at the repo root, but meaningless once the same
 * markdown is rendered as a site page at `/changelog/` (it resolves relative to
 * the page URL, lands outside the site's base path, and fails the link audit).
 * Rewrite every such link to the absolute GitHub PR URL. */
function absolutizePullLinks(source: string): string {
  return source.replace(/\]\(\.\.\/\.\.\/pull\/(\d+)\)/g, `](${REPO_URL}/pull/$1)`);
}

/** The first `## [` version heading marks the start of real changelog content;
 * everything above it (the `# Changelog` H1 and any preamble prose) is
 * Starlight-page scaffolding this renderer replaces with frontmatter, so it is
 * dropped. Returns the H1/preamble-free remainder unchanged. */
function stripHeadingAndPreamble(source: string): string {
  const match = /^##\s*\[/m.exec(source);
  if (!match) return source.trim();
  return source.slice(match.index).trimEnd();
}

/**
 * Render `site/src/content/docs/changelog.md` from the raw contents of the
 * repo-root `CHANGELOG.md`.
 *
 * Idempotent: rendering the same `changelogSource` twice produces byte-identical
 * output, since this is a pure function of its input with no mutable state.
 */
export function renderChangelog(changelogSource: string): string {
  const body = absolutizePullLinks(stripHeadingAndPreamble(changelogSource));
  const frontmatterLines = [
    "---",
    "title: Changelog",
    yamlDescriptionLine(DESCRIPTION),
    "---",
  ].filter((line) => line !== "");

  return (
    frontmatterLines.join("\n") +
    "\n\n" +
    "Every released version of codeArbiter. See the " +
    "[GitHub Releases page](https://github.com/arbiterForge/codeArbiter/releases) " +
    "for the same history with release assets.\n\n" +
    body +
    "\n"
  );
}
