import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { collectSources } from "./collect-sources";
import { parseDoc } from "./parse-doc";
import { deriveName } from "./derive-name";
import { assignSlugs } from "./assign-slugs";
import { renderAgentPage } from "./render-agent-page";
import { renderCommandPage } from "./render-command-page";
import { renderSkillPage } from "./render-skill-page";
import { buildIndex } from "./build-index";
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
  const sources = collectSources(srcDir);

  // Derive a display name per source, then assign collision-free slugs across
  // the whole set (stable: collectSources is already sorted by path).
  const names = sources.map((s) => deriveName(s.path, parseDoc(s.raw).fields));
  const slugs = assignSlugs(names);

  const pages: RenderedPage[] = sources.map((source, i) => {
    const { fields } = parseDoc(source.raw);
    const name = names[i];
    const input: PageInput = {
      name,
      description: fields.description,
      model: fields.model,
      tools: fields.tools,
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

  // Index + sidebar.
  const { markdown, sidebar } = buildIndex(pages);
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, "index.md"), markdown);
  writeFileSync(resolvedSidebarPath, JSON.stringify(sidebar, null, 2));

  return { pages, outDir, sidebarPath: resolvedSidebarPath };
}
