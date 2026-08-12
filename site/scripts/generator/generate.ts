import { mkdirSync, writeFileSync, rmSync, existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { collectSources } from "./collect-sources";
import { collectLenses } from "./collect-lenses";
import { renderLensPage } from "./render-lens-page";
import { truncateDescription } from "./truncate-description";
import { parseDoc } from "./parse-doc";
import { deriveName } from "./derive-name";
import { assignSlugs } from "./assign-slugs";
import { renderAgentPage } from "./render-agent-page";
import { renderCommandPage } from "./render-command-page";
import { renderSkillPage } from "./render-skill-page";
import { buildIndex } from "./build-index";
import { getCommandForgeStatus } from "./forge-status";
import { loadCurated } from "./load-curated";
import { publicReferenceDescription } from "./render-reference-lead";
import {
  commandHostAvailability,
  loadHostCommandCatalogs,
} from "./host-command-catalog";
import type {
  GenerateResult,
  PageInput,
  RelatedLink,
  RenderedPage,
  SidebarGroup,
  SourceType,
} from "./types";

/** Output subdirectory for each source type. */
const TYPE_DIR: Record<SourceType, string> = {
  command: "commands",
  skill: "skills",
  agent: "agents",
};

/** Output subdirectory for the tribunal-lens collection (see collect-lenses.ts). */
const LENS_DIR = "tribunal-lenses";

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
  const hostCatalogs = loadHostCommandCatalogs(
    srcDir,
    parsed
      .filter(({ source }) => source.type === "command")
      .map(({ source }) => deriveName(source.path, {})),
  );

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
      commandHosts:
        source.type === "command"
          ? commandHostAvailability(slugs[i], hostCatalogs)
          : undefined,
      sourceRaw: source.raw,
      sourceRelPath: `plugins/ca/${source.path}`,
      pluginVersion,
    };
    return {
      type: source.type,
      slug: slugs[i],
      title: name,
      markdown: renderPage(source.type, input),
      description: publicReferenceDescription(doc.fields.description ?? ""),
      model: doc.fields.model,
      forgeStatus,
    };
  });

  // Tribunal lens cards are a fourth, self-contained collection: one page per
  // card under `tribunal-lenses/`, no curated companion (the card body is the
  // documentation), no slug dedup needed (slugs are unique file basenames).
  const lensPages = collectLenses(srcDir).map(renderLensPage);

  // Clean prior output before writing: a stale file from a previous run (an
  // old `-2` slug, a since-removed entity) must not survive a re-generate.
  // Only the generated subtrees + index are removed — never the whole
  // outDir, which may hold other content-collection files.
  for (const typeDir of [...Object.values(TYPE_DIR), LENS_DIR]) {
    rmSync(join(outDir, typeDir), { recursive: true, force: true });
  }
  rmSync(join(outDir, "index.md"), { force: true });

  // Write one page per source under its type directory.
  for (const page of pages) {
    const dir = join(outDir, TYPE_DIR[page.type]);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, `${page.slug}.md`), page.markdown);
  }

  // Write one page per tribunal lens card.
  if (lensPages.length > 0) {
    const dir = join(outDir, LENS_DIR);
    mkdirSync(dir, { recursive: true });
    for (const page of lensPages) {
      writeFileSync(join(dir, `${page.slug}.md`), page.markdown);
    }
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
  // The entities come from the Claude Code payload, while each command page
  // derives its host availability from all three shipped COMMANDS.md catalogs.
  // Agent identities remain a Claude-specific catalog boundary even though
  // current Codex hosts can execute the same charter in host-provided threads.
  const hostNote =
    "Commands, skills, and agents below are generated from the `ca` (Claude Code) plugin " +
    "payload. Each command page checks the shipped Claude Code, Codex, and Pi catalogs and marks " +
    "adapters where that command is not shipped. The Agents catalog below describes Claude " +
    "Code's packaged agent charters. Current Codex releases load those charters into host-provided " +
    "agent threads and retain thread receipts; older hosts may fall back to inline execution except " +
    "where isolated scouts are mandatory. Pi dispatches hardened children through the parent-only " +
    "`codearbiter_dispatch` tool. " +
    "See [Compatibility → Host Differences](/getting-started/compatibility/#host-differences) " +
    "for the full per-surface breakdown across all three hosts.";
  // At this point `sidebar` holds only the three entity groups (the
  // tribunal-lens group is appended below, after the index is rendered); the
  // filter narrows the type for `TYPE_DIR`/`TABLE_HEADER` indexing.
  const entityGroups = sidebar.filter(
    (g): g is SidebarGroup & { type: SourceType } => g.type !== "tribunal-lens",
  );
  const indexBody = entityGroups
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
  // The tribunal-lens collection gets its own index table, after the three
  // entity catalogs (the group renders adjacent to Agents in the sidebar too).
  const lensSection =
    lensPages.length > 0
      ? `\n\n## Tribunal lenses\n\nEach lens card is the per-lens mandate the ` +
        `[tribunal-lens-reviewer](./agents/tribunal-lens-reviewer/) agent executes when ` +
        `[/ca:tribunal](./commands/tribunal/) dispatches it under that lens's assignment.\n\n` +
        `| Lens | Description |\n|---|---|\n` +
        lensPages
          .map(
            (p) =>
              `| [${p.slug}](./${LENS_DIR}/${p.slug}/) | ${truncateDescription(p.description)} |`,
          )
          .join("\n")
      : "";
  const catalogCards = entityGroups.map((group) => {
    const plural = `${group.type.charAt(0).toUpperCase()}${group.type.slice(1)}s`;
    const purpose = group.type === "command"
      ? "Public entry points you invoke for an outcome."
      : group.type === "skill"
        ? "Gated workflows the orchestrator routes into."
        : "Focused author and reviewer roles a skill may dispatch.";
    return `<a href="#${group.type}s"><span>${group.items.length}</span><strong>${plural}</strong><small>${purpose}</small></a>`;
  }).join("\n");
  const indexContent = `---\ntitle: Reference\ndescription: Source-backed command, skill, and agent catalogs with host syntax, operating context, gates, relationships, and exact shipped source.\n---\n\nEntity identities, frontmatter, host availability, and exact source embeds regenerate from the shipped payload on every build. Curated operating guidance is hand-reviewed and contract-tested, but it can still lag a source change; when the two disagree, the exact source embed is authoritative. See how the three catalogs cooperate in [How a Request Flows](/overview/#how-a-request-flows): a command routes to an owning skill, which may dispatch specialist agents.\n\n<div class="ca-reference-map">\n${catalogCards}\n</div>\n\n<div class="ca-reference-guide">\n<strong>Use the catalog from left to right.</strong>\n<ol>\n<li>Choose the public <strong>command</strong> that matches the outcome you need.</li>\n<li>Follow its owning <strong>skill</strong> to understand phases, stops, and durable artifacts.</li>\n<li>Open an <strong>agent</strong> only to inspect a dispatched role's tools and constraints; agents are not a second command surface.</li>\n</ol>\n<p>Every entity page begins with host-native syntax or dispatch context, then curated operating guidance, gates, related routes, and the exact source used to generate it.</p>\n</div>\n\n${hostNote}\n\n${indexBody}${lensSection}\n`;

  // Append the tribunal-lens sidebar group after the three entity groups so it
  // renders directly under Agents. Appended AFTER the index tables/cards above
  // are built from `sidebar` — those iterate only the entity collections.
  if (lensPages.length > 0) {
    sidebar.push({
      type: "tribunal-lens",
      label: "tribunal-lens",
      items: lensPages.map((p) => ({
        label: p.slug,
        slug: p.slug,
        description: truncateDescription(p.description),
      })),
    });
  }

  mkdirSync(outDir, { recursive: true });
  mkdirSync(dirname(resolvedSidebarPath), { recursive: true });
  writeFileSync(join(outDir, "index.md"), indexContent);
  writeFileSync(resolvedSidebarPath, JSON.stringify(sidebar, null, 2));

  return { pages, lensPages, outDir, sidebarPath: resolvedSidebarPath };
}
