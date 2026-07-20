import { mkdirSync, writeFileSync, rmSync, existsSync, readFileSync } from "node:fs";
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
import { loadCurated } from "./load-curated";
import type {
  GenerateResult,
  PageInput,
  RelatedLink,
  RenderedPage,
  SourceType,
} from "./types";

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
 * Read the plugin's version from `<srcDir>/.claude-plugin/plugin.json`.
 *
 * Falls back to `"0.0.0-dev"` when the file is absent or unreadable (e.g. a
 * synthetic test fixture with no plugin manifest) rather than throwing — the
 * version only pins the source-embed's "View in repo" link.
 */
function readPluginVersion(srcDir: string): string {
  const manifestPath = join(srcDir, ".claude-plugin", "plugin.json");
  if (!existsSync(manifestPath)) return "0.0.0-dev";
  try {
    const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
    return typeof manifest.version === "string" ? manifest.version : "0.0.0-dev";
  } catch {
    return "0.0.0-dev";
  }
}

/**
 * Generate the full reference: collect → parse → curate → render → write.
 *
 * Reads plugin sources under `srcDir`, emits one markdown page per source file
 * under `outDir/{commands,skills,agents}/<slug>.md` (slugs deduplicated so there
 * are no collisions), writes an `index.md`, and writes the sidebar JSON to
 * `sidebarPath` (default `outDir/sidebar.json`). Idempotent: running twice over
 * the same sources produces byte-identical output.
 *
 * Every page carries a verbatim source embed (see `render-source-embed.ts`).
 * When `curatedDir` is given and contains a companion file for a source, its
 * curated framing (body, gates, related links) is merged in — see
 * `load-curated.ts` for the divergence-check rules. Before writing, the
 * output's `{commands,skills,agents}` dirs and `index.md` are deleted so a
 * stale file from a prior run (e.g. an old `-2` slug) cannot survive.
 *
 * Returns a summary.
 */
export function generate(
  srcDir: string,
  outDir: string,
  sidebarPath?: string,
  curatedDir?: string,
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

  // Slugs are deduplicated per collection (command/skill/agent), not across the
  // whole combined set — each collection writes to its own output directory, so
  // a skill sharing a name with a command must not be pushed to a `-2` slug.
  // Group indices by type (preserving relative order), assign slugs within each
  // group, then scatter the results back into a single array aligned with
  // `parsed`/`names` so the rest of generation is unaffected.
  const slugs: string[] = new Array(parsed.length);
  const indicesByType = new Map<SourceType, number[]>();
  parsed.forEach(({ source }, i) => {
    const list = indicesByType.get(source.type) ?? [];
    list.push(i);
    indicesByType.set(source.type, list);
  });
  for (const indices of indicesByType.values()) {
    const groupSlugs = assignSlugs(indices.map((i) => names[i]));
    indices.forEach((i, j) => {
      slugs[i] = groupSlugs[j];
    });
  }

  // Curated companion files key off the plugin source file's basename (a
  // skill's basename is its directory name), not the display name — the same
  // filename-stable discipline forge-status.ts uses. Compute it by calling
  // deriveName with no frontmatter fields, so a `name:` override in the
  // source can never change the curated lookup key.
  const basenameKeys = parsed.map((p) => deriveName(p.source.path, {}));
  const entityKeys = parsed.map(
    (p, i) => `${TYPE_DIR[p.source.type]}/${basenameKeys[i]}`,
  );
  const entityKeyToIndex = new Map<string, number>(
    entityKeys.map((key, i) => [key, i]),
  );
  const collectedKeys = new Set(entityKeys);
  const curatedMap = curatedDir
    ? loadCurated(curatedDir, collectedKeys)
    : new Map();

  const pluginVersion = readPluginVersion(srcDir);

  const pages: RenderedPage[] = parsed.map(({ source, doc }, i) => {
    const name = names[i];
    // Derive forge status for command pages only. The slug at this point is the
    // raw file-basename (e.g. "prune", "sprint") — use that as the lookup key
    // so the allowlist stays filename-stable regardless of display name.
    const forgeStatus =
      source.type === "command"
        ? getCommandForgeStatus(slugs[i])
        : null;
    const curated = curatedMap.get(entityKeys[i]);

    let relatedLinks: RelatedLink[] | undefined;
    if (curated?.related && curated.related.length > 0) {
      relatedLinks = curated.related.map((ref: string) => {
        const resolvedKey = ref.includes("/")
          ? ref
          : `${TYPE_DIR[source.type]}/${ref}`;
        const targetIndex = entityKeyToIndex.get(resolvedKey);
        if (targetIndex === undefined) {
          throw new Error(
            `Curated file for "${entityKeys[i]}" has an unresolvable related ref "${ref}"`,
          );
        }
        const targetType = parsed[targetIndex].source.type;
        return {
          label: names[targetIndex],
          href: `/reference/${TYPE_DIR[targetType]}/${slugs[targetIndex]}/`,
        };
      });
    }

    const input: PageInput = {
      name,
      description: doc.fields.description ?? "",
      model: doc.fields.model,
      tools: doc.fields.tools,
      forgeStatus,
      curated,
      relatedLinks,
      sourceRaw: source.raw,
      sourceRelPath: `plugins/ca/${source.path}`,
      pluginVersion,
    };
    return {
      type: source.type,
      slug: slugs[i],
      title: name,
      markdown: renderPage(source.type, input),
      description: doc.fields.description,
      model: doc.fields.model,
      forgeStatus,
    };
  });

  // Clean prior output before writing: a stale file from a previous run (an
  // old `-2` slug, a since-removed entity) must not survive a re-generate.
  // Only the generated subtrees + index are removed — never the whole
  // outDir, which may hold other content-collection files.
  for (const typeDir of Object.values(TYPE_DIR)) {
    rmSync(join(outDir, typeDir), { recursive: true, force: true });
  }
  rmSync(join(outDir, "index.md"), { force: true });

  // Write one page per source under its type directory.
  for (const page of pages) {
    const dir = join(outDir, TYPE_DIR[page.type]);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, `${page.slug}.md`), page.markdown);
  }

  // Index + sidebar. buildIndex gives the grouped, sorted structure (each item
  // already carrying its truncated description, and — per collection — a
  // model tier or preview flag); we render a Starlight-valid index page
  // (frontmatter title + one table per collection) from it.
  const { sidebar } = buildIndex(pages);
  // Column headers per collection: agents carry a model-tier column the other
  // two collections don't have.
  const TABLE_HEADER: Record<SourceType, string> = {
    command: "| Command | Description |\n|---|---|",
    skill: "| Skill | Description |\n|---|---|",
    agent: "| Agent | Model tier | Description |\n|---|---|---|",
  };
  // Host-scope note (docs-codex findings 01/02): every page below is generated
  // from the `ca` (Claude Code) plugin payload — its command syntax and its
  // 27-agent `Task`-dispatch catalog describe Claude Code specifically. Codex
  // uses `ca-codex` (same command names, `$ca-<name>` instead of `/ca:<name>`)
  // and runs the same reviewer/author roles inline in the current thread
  // rather than dispatching them as isolated subagents. Stated once here,
  // generator-side, so it can't drift out of sync across 65+ per-page edits;
  // see docs/parity.md's "Role charters" row for the canonical wording.
  const hostNote =
    "Commands, skills, and agents below are generated from the `ca` (Claude Code) plugin " +
    "payload. Codex CLI (`ca-codex`) uses the same names with `$ca-<name>` in place of " +
    "`/ca:<name>`; Pi (`ca-pi`) uses `/ca-<name>`. The Agents catalog below describes Claude " +
    "Code's isolated `Task`-tool dispatch — Codex executes the same reviewer and author roles " +
    "inline in the current thread instead, until packaged agent dispatch lands for that host. " +
    "See [Compatibility → Host Differences](/getting-started/compatibility/#host-differences) " +
    "for the full per-surface breakdown across all three hosts.";
  const indexBody = sidebar
    .map((group) => {
      const heading = `## ${group.type.charAt(0).toUpperCase()}${group.type.slice(1)}s`;
      const rows = group.items.map((it) => {
        const nameCell =
          `[${it.label}](./${TYPE_DIR[group.type]}/${it.slug}/)` +
          (it.preview ? " (preview)" : "");
        const description = it.description ?? "";
        return group.type === "agent"
          ? `| ${nameCell} | ${it.tier ?? "default"} | ${description} |`
          : `| ${nameCell} | ${description} |`;
      });
      return `${heading}\n\n${TABLE_HEADER[group.type]}\n${rows.join("\n")}`;
    })
    .join("\n\n");
  const indexContent = `---\ntitle: Reference\ndescription: Auto-generated reference for codeArbiter commands, skills, and agents.\n---\n\nThis section is generated from the plugin's own frontmatter and regenerates on every build, so it can never drift from the source. See how the three catalogs cooperate in [How a Request Flows](/overview/#how-a-request-flows): a command routes to an owning skill, which may dispatch specialist agents.\n\n${hostNote}\n\n${indexBody}\n`;

  mkdirSync(outDir, { recursive: true });
  mkdirSync(dirname(resolvedSidebarPath), { recursive: true });
  writeFileSync(join(outDir, "index.md"), indexContent);
  writeFileSync(resolvedSidebarPath, JSON.stringify(sidebar, null, 2));

  return { pages, outDir, sidebarPath: resolvedSidebarPath };
}
