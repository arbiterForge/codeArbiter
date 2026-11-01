/** Topic map: which guide or concept page each Academy lesson practices (AC-08).
 *
 * `site/src/data/topic-map.json` is keyed by page slug (`guides/<name>` or `concepts/<name>`),
 * and each value lists the Academy lesson IDs that practice that page. Generation loads the map,
 * checks it against the pinned Academy source and the authored pages, and hands each lesson its
 * pages. A page slug that does not exist, a lesson ID that does not exist, or a lesson that no
 * page lists fails generation with the entry named.
 *
 * This module is pure and filesystem-light on purpose: it never imports `src/generated/*`, which
 * does not exist until generation has run. Components read the JSON map and the generated lesson
 * titles themselves and call `lessonIdsForPage`. */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** Page slug to the Academy lesson IDs that practice it. */
export type TopicMap = Record<string, string[]>;

export type TopicPage = {
  slug: string;
  title: string;
  /** Root-absolute route, trailing slash. Markdown links are base-prefixed by rehype-base-links. */
  href: string;
  kind: "guide" | "concept";
};

export type LoadedTopicMap = {
  pages: TopicMap;
  /** Every Academy lesson ID to its pages, in the order the map file lists them. */
  lessons: Map<string, TopicPage[]>;
};

/** Sections a lesson may point to. Get started pages are deliberately not eligible. */
const SECTIONS = ["guides", "concepts"] as const;

/** Check the JSON's shape and return it typed. Names the offending entry. */
export function parseTopicMap(raw: unknown): TopicMap {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("Topic map must be an object of page slugs to lesson ID lists");
  }
  const map: TopicMap = {};
  for (const [slug, ids] of Object.entries(raw)) {
    if (!Array.isArray(ids) || ids.some((id) => typeof id !== "string")) {
      throw new Error(`Topic map entry "${slug}" must be a list of lesson ID strings`);
    }
    map[slug] = ids as string[];
  }
  return map;
}

/** Throw one error naming every bad entry: unknown page, unknown lesson, empty or repeated list,
 * and any lesson no page lists. */
export function validateTopicMap(map: TopicMap, lessonIds: readonly string[], pageSlugs: ReadonlySet<string>): void {
  const problems: string[] = [];
  const known = new Set(lessonIds);
  const mapped = new Set<string>();
  for (const [slug, ids] of Object.entries(map)) {
    if (!pageSlugs.has(slug)) problems.push(`unknown guide or concept page "${slug}"`);
    if (ids.length === 0) problems.push(`"${slug}" lists no lessons`);
    const seen = new Set<string>();
    for (const id of ids) {
      if (!known.has(id)) problems.push(`"${slug}" names unknown lesson "${id}"`);
      if (seen.has(id)) problems.push(`"${slug}" lists lesson "${id}" twice`);
      seen.add(id);
      mapped.add(id);
    }
  }
  for (const id of lessonIds) {
    if (!mapped.has(id)) problems.push(`lesson "${id}" is not mapped to any guide or concept page`);
  }
  if (problems.length > 0) {
    throw new Error(`Topic map is invalid:\n${problems.map((problem) => `  - ${problem}`).join("\n")}`);
  }
}

/** The lesson IDs that practice one page, in map order. Empty when the page is not mapped. */
export function lessonIdsForPage(map: TopicMap, slug: string): string[] {
  return Object.hasOwn(map, slug) ? map[slug] : [];
}

/** Read a page's `title` from its frontmatter. Titles are single-line scalars, quoted or plain. */
function readTitle(source: string, slug: string): string {
  const frontmatter = /^---\r?\n([\s\S]*?)\r?\n---/.exec(source)?.[1] ?? "";
  const raw = /^title:[ \t]*(.+?)[ \t]*$/m.exec(frontmatter)?.[1];
  if (!raw) throw new Error(`Page "${slug}" has no frontmatter title`);
  if (raw.startsWith('"')) return JSON.parse(raw) as string;
  if (raw.startsWith("'") && raw.endsWith("'")) return raw.slice(1, -1).replaceAll("''", "'");
  return raw;
}

/** Every authored guide and concept page (index pages excluded) with its title, keyed by slug. */
function topicPages(docsRoot: string): Map<string, TopicPage> {
  const pages = new Map<string, TopicPage>();
  const walk = (directory: string, slugPrefix: string, section: typeof SECTIONS[number]): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        walk(join(directory, entry.name), `${slugPrefix}/${entry.name}`, section);
        continue;
      }
      const match = /^(.+)\.mdx?$/.exec(entry.name);
      if (!match || match[1] === "index") continue;
      const slug = `${slugPrefix}/${match[1]}`;
      pages.set(slug, {
        slug,
        title: readTitle(readFileSync(join(directory, entry.name), "utf8"), slug),
        href: `/${slug}/`,
        kind: section === "guides" ? "guide" : "concept",
      });
    }
  };
  for (const section of SECTIONS) {
    const directory = join(docsRoot, section);
    if (existsSync(directory)) walk(directory, section, section);
  }
  return pages;
}

/** Load the map file, validate it against the Academy lessons and the authored pages, and resolve
 * each lesson to its pages. Throws, naming the entry, on any invalid entry. */
export function loadTopicMap(mapPath: string, docsRoot: string, lessonIds: readonly string[]): LoadedTopicMap {
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(mapPath, "utf8"));
  } catch (error) {
    throw new Error(`Topic map could not be read: ${mapPath}`, { cause: error });
  }
  const pages = parseTopicMap(raw);
  const available = topicPages(docsRoot);
  validateTopicMap(pages, lessonIds, new Set(available.keys()));

  const lessons = new Map<string, TopicPage[]>(lessonIds.map((id) => [id, []]));
  for (const [slug, ids] of Object.entries(pages)) {
    for (const id of ids) lessons.get(id)!.push(available.get(slug)!);
  }
  return { pages, lessons };
}
