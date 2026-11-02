import { mkdirSync, writeFileSync, rmSync, existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { collectSources } from "./collect-sources";
import { collectLenses } from "./collect-lenses";
import { renderLensPage } from "./render-lens-page";
import { truncateDescription } from "./truncate-description";
import { parseDoc } from "./parse-doc";
import { normalizeSource } from "./normalize-source";
import { deriveName } from "./derive-name";
import { assignSlugs } from "./assign-slugs";
import { renderAgentPage } from "./render-agent-page";
import { renderCommandPage } from "./render-command-page";
import { renderSkillPage } from "./render-skill-page";
import { buildIndex } from "./build-index";
import { getCommandForgeStatus } from "./forge-status";
import { loadCurated } from "./load-curated";
import {
  assertNoCuratedDrift,
  ownCommandOf,
  readCuratedDriftSources,
} from "./curated-drift";
import { classifySkills, deriveWorkflowPairs } from "./workflow-pairs";
import { publicReferenceDescription } from "./render-reference-lead";
import { loadCommandCatalog } from "./landing-stats";
import {
  commandHostAvailability,
  loadHostCommandCatalogs,
} from "./host-command-catalog";
import type {
  AliasWorkflowPointer,
  GenerateResult,
  MergedWorkflowSkill,
  PageInput,
  RelatedLink,
  ReaderShape,
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
  requireCommandCatalog = false,
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
    doc: parseDoc(normalizeSource(source.raw)),
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

  const pluginVersion = readPluginVersion(srcDir);
  const commandNames = parsed
    .filter(({ source }) => source.type === "command")
    .map(({ source }) => deriveName(source.path, {}));
  const hostCatalogs = loadHostCommandCatalogs(srcDir, commandNames);
  const commandCatalogPath = join(srcDir, "generated", "command-catalog.json");
  const commandCatalog = commandNames.length > 0 &&
    (requireCommandCatalog || existsSync(commandCatalogPath))
    ? loadCommandCatalog(srcDir, commandNames)
    : undefined;

  // Pair each command with the skill that owns its procedure (see
  // workflow-pairs.ts). A merged skill keeps its place in `parsed`, `slugs`,
  // `entityKeys` and the curated loader, so no slug shifts and its curated
  // companion is not an orphan; it is only left out of the emitted pages.
  const skillBasenames = parsed
    .map((p, i) => ({ type: p.source.type, basename: basenameKeys[i] }))
    .filter((entry) => entry.type === "skill")
    .map((entry) => entry.basename);
  const workflowPairs = deriveWorkflowPairs(
    parsed.flatMap(({ source }, i) =>
      source.type === "command"
        ? [{ name: basenameKeys[i], raw: normalizeSource(source.raw) }]
        : [],
    ),
    skillBasenames,
    commandCatalog,
  );
  const pairByCommand = new Map(workflowPairs.map((pair) => [pair.command, pair]));
  const mergedSkillToCommand = new Map(
    workflowPairs
      .filter((pair) => pair.mode === "merge")
      .map((pair) => [`skills/${pair.skill}`, `commands/${pair.command}`]),
  );
  const isMergedSkill = (index: number): boolean => mergedSkillToCommand.has(entityKeys[index]);
  /** The page a reader lands on for an entity: a merged skill lands on its command. */
  const landingIndex = (index: number): number => {
    const commandKey = mergedSkillToCommand.get(entityKeys[index]);
    return commandKey === undefined ? index : entityKeyToIndex.get(commandKey)!;
  };
  const hrefOf = (index: number): string =>
    `/reference/${TYPE_DIR[parsed[index].source.type]}/${slugs[index]}/`;
  /** Resolve curated `related:` refs written for `ownerType`, following merged skills to their command. */
  const resolveRelated = (
    refs: readonly string[],
    ownerType: SourceType,
    ownerKey: string,
  ): RelatedLink[] =>
    refs.map((ref) => {
      const resolvedKey = ref.includes("/") ? ref : `${TYPE_DIR[ownerType]}/${ref}`;
      const targetIndex = entityKeyToIndex.get(resolvedKey);
      if (targetIndex === undefined) {
        throw new Error(
          `Curated file for "${ownerKey}" has an unresolvable related ref "${ref}"`,
        );
      }
      const landing = landingIndex(targetIndex);
      return { label: names[landing], href: hrefOf(landing) };
    });

  // Which reader fields each entity's curated page must carry. A command needs
  // them unless it is a compatibility route; a skill needs the workflow fields
  // when it is the workflow page for an alias, the two internal-only fields
  // when no command owns it, and none when it is merged into a command page.
  // Without a catalog no command has a known visibility, so nothing is shaped.
  const readerShapes = new Map<string, ReaderShape>();
  if (commandCatalog) {
    parsed.forEach(({ source }, i) => {
      if (source.type !== "command") return;
      const visibility = commandCatalog.commands[basenameKeys[i]]?.visibility;
      if (visibility === "core" || visibility === "advanced" || visibility === "internal") {
        readerShapes.set(entityKeys[i], "workflow");
      }
    });
    const roles = classifySkills(skillBasenames, workflowPairs);
    parsed.forEach(({ source }, i) => {
      if (source.type !== "skill") return;
      const role = roles.get(basenameKeys[i]);
      if (role === "alias-owner") readerShapes.set(entityKeys[i], "workflow");
      if (role === "internal-only") readerShapes.set(entityKeys[i], "internal-skill");
    });
  }

  const curatedMap = curatedDir
    ? loadCurated(curatedDir, collectedKeys, readerShapes)
    : new Map();

  // Hand-written text must not name a flag its command's shipped source lacks, or
  // a command the catalog lacks. A command's source is its command file plus, when
  // paired, its skill (see curated-drift.ts). Every miss is reported in one error.
  if (curatedDir) {
    const commandSources = new Map<string, string>();
    parsed.forEach(({ source }, i) => {
      if (source.type !== "command") return;
      const pair = pairByCommand.get(basenameKeys[i]);
      const skillIndex = pair ? entityKeyToIndex.get(`skills/${pair.skill}`) : undefined;
      commandSources.set(
        basenameKeys[i],
        [source.raw, ...(skillIndex === undefined ? [] : [parsed[skillIndex].source.raw])]
          .map(normalizeSource)
          .join("\n"),
      );
    });
    const skillCommand = new Map(workflowPairs.map((pair) => [pair.skill, pair.command]));
    assertNoCuratedDrift({
      files: readCuratedDriftSources(curatedDir).map(({ path, raw, entity }) => ({
        path,
        raw,
        ownCommand: ownCommandOf(entity, skillCommand),
      })),
      commands: new Set(commandCatalog ? Object.keys(commandCatalog.commands) : commandNames),
      sources: commandSources,
    });
  }

  const pages: RenderedPage[] = parsed.flatMap(({ source, doc }, i) => {
    if (isMergedSkill(i)) return [];
    const name = names[i];
    // Derive forge status for command pages only. The slug at this point is the
    // raw file-basename (e.g. "prune", "sprint") — use that as the lookup key
    // so the allowlist stays filename-stable regardless of display name.
    const forgeStatus =
      source.type === "command"
        ? getCommandForgeStatus(slugs[i])
        : null;
    const curated = curatedMap.get(entityKeys[i]);

    // Pair state for a command page: a merged skill's reader text and source
    // join this page; an alias points at its replacement and its skill page.
    const pair = source.type === "command" ? pairByCommand.get(basenameKeys[i]) : undefined;
    let workflowSkill: MergedWorkflowSkill | undefined;
    let aliasPointer: AliasWorkflowPointer | undefined;
    const skillIndex = pair ? entityKeyToIndex.get(`skills/${pair.skill}`)! : undefined;
    if (pair && skillIndex !== undefined) {
      if (pair.mode === "merge") {
        workflowSkill = {
          name: pair.skill,
          curated: curatedMap.get(entityKeys[skillIndex]),
          sourceRaw: parsed[skillIndex].source.raw,
          sourceRelPath: `plugins/ca/${parsed[skillIndex].source.path}`,
        };
      } else {
        const canonicalIndex = pair.canonical
          ? entityKeyToIndex.get(`commands/${pair.canonical}`)
          : undefined;
        if (canonicalIndex === undefined || !pair.replacement) {
          throw new Error(
            `Alias command "${pair.command}" needs a replacement that names an existing command, got canonical "${pair.canonical}" and replacement "${pair.replacement}"`,
          );
        }
        aliasPointer = {
          skill: pair.skill,
          skillHref: hrefOf(skillIndex),
          replacement: pair.replacement,
          replacementHref: hrefOf(canonicalIndex),
          replacementCommand: pair.canonical!,
        };
      }
    }

    // A merged page lists the related pages of both halves. A merged skill's
    // URL is not published, so any ref to it lands on its command page; a page
    // never lists itself, and each target is listed once.
    const relatedRefs = [
      ...resolveRelated(curated?.related ?? [], source.type, entityKeys[i]),
      ...(workflowSkill && skillIndex !== undefined
        ? resolveRelated(
            curatedMap.get(entityKeys[skillIndex])?.related ?? [],
            "skill",
            entityKeys[skillIndex],
          )
        : []),
    ];
    const seenHrefs = new Set([hrefOf(i)]);
    const resolvedRelated = relatedRefs.filter((link) => {
      if (seenHrefs.has(link.href)) return false;
      seenHrefs.add(link.href);
      return true;
    });
    const relatedLinks: RelatedLink[] | undefined =
      resolvedRelated.length > 0 ? resolvedRelated : undefined;

    const commandName = source.type === "command" ? deriveName(source.path, {}) : undefined;
    const catalogEntry = commandName ? commandCatalog?.commands[commandName] : undefined;
    const input: PageInput = {
      name,
      description: doc.fields.description ?? "",
      model: doc.fields.model,
      tools: doc.fields.tools,
      forgeStatus,
      curated,
      readerShape: readerShapes.get(entityKeys[i]),
      relatedLinks,
      commandHosts:
        source.type === "command"
          ? commandHostAvailability(commandName!, hostCatalogs)
          : undefined,
      commandCatalog: catalogEntry,
      workflowSkill,
      aliasPointer,
      sourceRaw: source.raw,
      sourceRelPath: `plugins/ca/${source.path}`,
      pluginVersion,
    };
    return [
      {
        type: source.type,
        slug: slugs[i],
        title: name,
        markdown: renderPage(source.type, input),
        description: publicReferenceDescription(doc.fields.description ?? ""),
        model: doc.fields.model,
        forgeStatus,
        commandCatalog: catalogEntry,
      },
    ];
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
  const { sidebar, markdown: indexBody } = buildIndex(pages, commandCatalog);
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
    const itemCount = group.items.reduce(
      (count, item) => count + ("items" in item ? item.items.length : 1),
      0,
    );
    const purpose = group.type === "command"
      ? "Public entry points you invoke for an outcome."
      : group.type === "skill"
        ? "Gated workflows the orchestrator routes into."
        : "Focused author and reviewer roles a skill may dispatch.";
    return `<a href="#${group.type}s"><span>${itemCount}</span><strong>${plural}</strong><small>${purpose}</small></a>`;
  }).join("\n");
  const indexContent = `---\ntitle: Reference\ndescription: Source-backed command, skill, and agent catalogs with host syntax, operating context, gates, relationships, and exact shipped source.\n---\n\nEntity identities, frontmatter, host availability, and exact source embeds regenerate from the shipped payload on every build. Curated operating guidance is hand-reviewed and contract-tested, but it can still lag a source change; when the two disagree, the exact source embed is authoritative. See how the three catalogs cooperate in [How a Request Flows](/overview/#how-a-request-flows): a command routes to an owning skill, which may dispatch specialist agents.\n\n<div class="ca-reference-map">\n${catalogCards}\n</div>\n\n<div class="ca-reference-guide">\n<strong>Use the catalog from left to right.</strong>\n<ol>\n<li>Choose the public <strong>command</strong> that matches the outcome you need.</li>\n<li>Read how it runs: a core or advanced command's page carries its owning skill's phases, stops, and durable artifacts; a compatibility entry points to its <strong>skill</strong> page, and internal-only skills have pages of their own.</li>\n<li>Open an <strong>agent</strong> only to inspect a dispatched role's tools and constraints; agents are not a second command surface.</li>\n</ol>\n<p>Every entity page begins with host-native syntax or dispatch context, then curated operating guidance, gates, related routes, and the exact source used to generate it.</p>\n</div>\n\n${hostNote}\n\n${indexBody}${lensSection}\n`;

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

  return { pages, workflowPairs, lensPages, outDir, sidebarPath: resolvedSidebarPath };
}
