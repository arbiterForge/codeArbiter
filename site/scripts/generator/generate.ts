import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { collectSources } from "./collect-sources";
import { parseDoc } from "./parse-doc";
import { deriveName } from "./derive-name";
import { assignSlugs } from "./assign-slugs";
import { renderAgentPage } from "./render-agent-page";
import { renderCommandPage } from "./render-command-page";
import { renderSkillPage } from "./render-skill-page";
import { buildIndex } from "./build-index";
import { getCommandForgeStatus } from "./forge-status";
import type { GenerateResult, PageInput, RenderedPage, SourceType } from "./types";

/** Output subdirectory for each source type. */
const TYPE_DIR: Record<SourceType, string> = {
  command: "commands",
  skill: "skills",
  agent: "agents",
};

function renderPage(type: SourceType, input: PageInput): string {
  switch (type) {
    case "agent":
      return renderAgentPage(input);
    case "command":
      return renderCommandPage(input);
    case "skill":
      return renderSkillPage(input);
  }
}

/**
 * Normalize a raw file at the read boundary: strip a leading BOM and convert
 * CRLF to LF. The frontmatter parser is specified against `\n`, so real-world
 * CRLF files (e.g. a Windows checkout of the plugin) must be normalized here
 * before parsing — otherwise the leading `---` line carries a trailing `\r` and
 * no frontmatter is detected.
 */
function normalize(raw: string): string {
  const noBom = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
  return noBom.replace(/\r\n/g, "\n");
}

/**
 * Generate the full reference: collect → parse → render → write.
 *
 * Reads plugin sources under `srcDir`, emits one markdown page per source file
 * under `outDir/{commands,skills,agents}/<slug>.md` (slugs deduplicated so there
 * are no collisions), writes an `index.md`, and writes the sidebar JSON to
 * `sidebarPath` (default `outDir/sidebar.json`). Idempotent: running twice over
 * the same sources produces byte-identical output. Returns a summary.
 */
export function generate(
  srcDir: string,
  outDir: string,
  sidebarPath?: string,
): GenerateResult {
  const resolvedSidebarPath = sidebarPath ?? join(outDir, "sidebar.json");
  // `INDEX.md` files are the plugin's internal catalog / surface-scan tables
  // (no frontmatter, not a documentable command/skill/agent). Skip them — they
  // would also collide with Starlight's reserved `index` route slug.
  const sources = collectSources(srcDir).filter(
    (s) => !/(^|\/)INDEX\.md$/i.test(s.path),
  );

  // Parse each source once (normalized). Names are derived first so slugs can be
  // de-duplicated across the whole, already path-sorted set (stable output).
  const parsed = sources.map((source) => ({
    source,
    doc: parseDoc(normalize(source.raw)),
  }));
  const names = parsed.map((p) => deriveName(p.source.path, p.doc.fields));
  const slugs = assignSlugs(names);

  const pages: RenderedPage[] = parsed.map(({ source, doc }, i) => {
    const name = names[i];
    // Derive forge status for command pages only. The slug at this point is the
    // raw file-basename (e.g. "prune", "sprint") — use that as the lookup key
    // so the allowlist stays filename-stable regardless of display name.
    const forgeStatus =
      source.type === "command"
        ? getCommandForgeStatus(slugs[i])
        : null;
    const input: PageInput = {
      name,
      description: doc.fields.description ?? "",
      model: doc.fields.model,
      tools: doc.fields.tools,
      forgeStatus,
    };
    return {
      type: source.type,
      slug: slugs[i],
      title: name,
      markdown: renderPage(source.type, input),
    };
  });

  // Write one page per source under its type directory.
  for (const page of pages) {
    const dir = join(outDir, TYPE_DIR[page.type]);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, `${page.slug}.md`), page.markdown);
  }

  // Index + sidebar. buildIndex gives the grouped, sorted structure; we render a
  // Starlight-valid index page (frontmatter title + linked groups) from it.
  const { sidebar } = buildIndex(pages);
  const indexBody = sidebar
    .map((group) => {
      const heading = `## ${group.type.charAt(0).toUpperCase()}${group.type.slice(1)}s`;
      const links = group.items
        .map((it) => `- [${it.label}](./${TYPE_DIR[group.type]}/${it.slug}/)`)
        .join("\n");
      return `${heading}\n\n${links}`;
    })
    .join("\n\n");
  const indexContent = `---\ntitle: Reference\ndescription: Auto-generated reference for codeArbiter commands, skills, and agents.\n---\n\nThis section is generated from the plugin's own frontmatter and regenerates on every build, so it can never drift from the source.\n\n${indexBody}\n`;

  mkdirSync(outDir, { recursive: true });
  mkdirSync(dirname(resolvedSidebarPath), { recursive: true });
  writeFileSync(join(outDir, "index.md"), indexContent);
  writeFileSync(resolvedSidebarPath, JSON.stringify(sidebar, null, 2));

  return { pages, outDir, sidebarPath: resolvedSidebarPath };
}
