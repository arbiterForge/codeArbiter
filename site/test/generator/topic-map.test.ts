/** topic-map.test.ts: guides and Academy lessons point to each other (AC-08).
 *
 * The negative fixtures each break exactly one rule on an otherwise valid map, so removing
 * the matching check in scripts/topic-map.ts lets that fixture through and fails its test. */
import { afterEach, describe, expect, it } from "vitest";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { loadAcademySource } from "../../scripts/academy-source";
import { generateAcademy } from "../../scripts/generate-academy";
import { lessonIdsForPage, loadTopicMap, parseTopicMap, validateTopicMap } from "../../scripts/topic-map";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const repoRoot = resolve(siteRoot, "..");
const docsRoot = join(siteRoot, "src", "content", "docs");
const realMapPath = join(siteRoot, "src", "data", "topic-map.json");

const lessons = ["F01-one", "F02-two"];
const pages = new Set(["guides/alpha", "concepts/beta"]);

const roots: string[] = [];
function tempRoot(): string {
  const root = mkdtempSync(join(tmpdir(), "topic-map-"));
  roots.push(root);
  return root;
}
function writeFile(path: string, contents: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents);
}
afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { force: true, recursive: true });
});

describe("validateTopicMap", () => {
  it("accepts a map that names real pages and real lessons and maps every lesson", () => {
    expect(() => validateTopicMap({ "guides/alpha": ["F01-one"], "concepts/beta": ["F02-two"] }, lessons, pages))
      .not.toThrow();
  });

  it("fails and names the entry when a lesson ID does not exist", () => {
    const map = { "guides/alpha": ["F01-one", "F99-nope"], "concepts/beta": ["F02-two"] };
    expect(() => validateTopicMap(map, lessons, pages)).toThrow(/"guides\/alpha" names unknown lesson "F99-nope"/);
  });

  it("fails and names the entry when a guide slug does not exist", () => {
    const map = { "guides/alpha": ["F01-one"], "guides/missing": ["F02-two"] };
    expect(() => validateTopicMap(map, lessons, pages)).toThrow(/unknown guide or concept page "guides\/missing"/);
  });

  it("fails and names the lesson when a lesson is mapped to nothing", () => {
    expect(() => validateTopicMap({ "guides/alpha": ["F01-one"] }, lessons, pages))
      .toThrow(/lesson "F02-two" is not mapped to any guide or concept page/);
  });

  it("reports only the rule each fixture breaks", () => {
    const badId = () => validateTopicMap({ "guides/alpha": ["F01-one", "F99-nope"], "concepts/beta": ["F02-two"] }, lessons, pages);
    expect(badId).toThrow(/F99-nope/);
    expect(badId).not.toThrow(/unknown guide or concept page|not mapped to any/);
    const badSlug = () => validateTopicMap({ "guides/alpha": ["F01-one"], "guides/missing": ["F02-two"] }, lessons, pages);
    expect(badSlug).not.toThrow(/unknown lesson|not mapped to any/);
    const unmapped = () => validateTopicMap({ "guides/alpha": ["F01-one"] }, lessons, pages);
    expect(unmapped).not.toThrow(/unknown lesson|unknown guide or concept page/);
  });

  it("names every problem in one failure", () => {
    const map = { "guides/missing": ["F99-nope"] };
    expect(() => validateTopicMap(map, lessons, pages)).toThrow(
      /guides\/missing[\s\S]*F99-nope[\s\S]*"F01-one"[\s\S]*"F02-two"/,
    );
  });

  it("rejects an entry that lists no lessons and a lesson listed twice on one page", () => {
    expect(() => validateTopicMap({ "guides/alpha": ["F01-one", "F02-two"], "concepts/beta": [] }, lessons, pages))
      .toThrow(/"concepts\/beta" lists no lessons/);
    expect(() => validateTopicMap({ "guides/alpha": ["F01-one", "F01-one", "F02-two"] }, lessons, pages))
      .toThrow(/"guides\/alpha" lists lesson "F01-one" twice/);
  });
});

describe("parseTopicMap", () => {
  it("rejects a map that is not an object of lesson ID lists", () => {
    expect(() => parseTopicMap([])).toThrow(/object/);
    expect(() => parseTopicMap({ "guides/alpha": "F01-one" })).toThrow(/"guides\/alpha"/);
    expect(() => parseTopicMap({ "guides/alpha": [1] })).toThrow(/"guides\/alpha"/);
    expect(parseTopicMap({ "guides/alpha": ["F01-one"] })).toEqual({ "guides/alpha": ["F01-one"] });
  });

  it("keeps a JSON \"__proto__\" key as an entry so validation names it", () => {
    // JSON.parse makes "__proto__" an own property. On a plain object, assigning it would replace
    // the prototype instead, and an unknown page would pass validation unseen.
    const raw: unknown = JSON.parse(
      '{"__proto__": ["F01-one"], "guides/alpha": ["F01-one"], "concepts/beta": ["F02-two"]}',
    );
    const map = parseTopicMap(raw);
    expect(Object.keys(map)).toContain("__proto__");
    expect(() => validateTopicMap(map, lessons, pages)).toThrow(/unknown guide or concept page "__proto__"/);
  });
});

describe("loadTopicMap", () => {
  function fixtureDocs(): string {
    const docs = tempRoot();
    writeFile(join(docs, "guides", "alpha.md"), "---\ntitle: Alpha Guide\n---\nBody\n");
    writeFile(join(docs, "guides", "index.mdx"), "---\ntitle: Guides\n---\n");
    writeFile(join(docs, "guides", "nested", "gamma.md"), "---\ntitle: 'Gamma: Nested'\n---\n");
    writeFile(join(docs, "concepts", "beta.mdx"), '---\ntitle: "Beta: A Concept"\ndescription: x\n---\n');
    writeFile(join(docs, "getting-started", "install.md"), "---\ntitle: Install\n---\n");
    return docs;
  }
  function writeMap(map: unknown): string {
    const path = join(tempRoot(), "topic-map.json");
    writeFile(path, JSON.stringify(map));
    return path;
  }

  it("resolves titles, hrefs and kinds for every lesson in map order", () => {
    const topics = loadTopicMap(
      writeMap({ "guides/alpha": ["F01-one", "F02-two"], "concepts/beta": ["F02-two"], "guides/nested/gamma": ["F01-one"] }),
      fixtureDocs(),
      lessons,
    );
    expect(topics.lessons.get("F01-one")).toEqual([
      { slug: "guides/alpha", title: "Alpha Guide", href: "/guides/alpha/", kind: "guide" },
      { slug: "guides/nested/gamma", title: "Gamma: Nested", href: "/guides/nested/gamma/", kind: "guide" },
    ]);
    expect(topics.lessons.get("F02-two")).toEqual([
      { slug: "guides/alpha", title: "Alpha Guide", href: "/guides/alpha/", kind: "guide" },
      { slug: "concepts/beta", title: "Beta: A Concept", href: "/concepts/beta/", kind: "concept" },
    ]);
  });

  it("accepts only authored guide and concept pages, not index or Get started pages", () => {
    const docs = fixtureDocs();
    for (const slug of ["guides/index", "guides", "getting-started/install", "guides/gone"]) {
      const map = { "guides/alpha": ["F01-one"], "concepts/beta": ["F02-two"], [slug]: ["F01-one"] };
      expect(() => loadTopicMap(writeMap(map), docs, lessons), slug).toThrow(
        new RegExp(`unknown guide or concept page "${slug}"`),
      );
    }
  });

  it("fails on the file's own entry when its JSON names a missing lesson", () => {
    const map = { "guides/alpha": ["F01-one", "F77-absent"], "concepts/beta": ["F02-two"] };
    expect(() => loadTopicMap(writeMap(map), fixtureDocs(), lessons)).toThrow(/"guides\/alpha" names unknown lesson "F77-absent"/);
  });
});

describe("the published topic map", () => {
  /** Loaded inside each test so a bad entry fails the test that reads it, with the entry named.
   * A successful load is reused because reading the Academy source starts several processes;
   * a failed load is never cached. */
  let loaded: ReturnType<typeof loadPublished> | undefined;
  function loadPublished() {
    const source = loadAcademySource(repoRoot);
    const lessonIds = source.lessons.map((lesson) => lesson.id);
    return { source, lessonIds, topics: loadTopicMap(realMapPath, docsRoot, lessonIds) };
  }
  function published() {
    loaded ??= loadPublished();
    return loaded;
  }

  it("validates against the pinned Academy lessons and the authored guide and concept pages", () => {
    expect(() => published()).not.toThrow();
  });

  it("maps every Academy lesson to at least one existing guide or concept page", () => {
    const { lessonIds, topics } = published();
    expect(lessonIds.length).toBeGreaterThan(0);
    for (const id of lessonIds) expect(topics.lessons.get(id)?.length ?? 0, id).toBeGreaterThan(0);
  });

  it("names a guide or concept page for each practice link, never a Get started page", () => {
    const { topics } = published();
    for (const slug of Object.keys(topics.pages)) {
      expect(slug, slug).toMatch(/^(guides|concepts)\/./);
      // guides/first-feature sits on the Get started path, which carries no evidence-register phrasing.
      expect(slug).not.toBe("guides/first-feature");
    }
  });

  it("gives each mapped page its lessons and each lesson its pages from the same entries", () => {
    const { topics } = published();
    for (const [slug, ids] of Object.entries(topics.pages)) {
      expect(lessonIdsForPage(topics.pages, slug)).toEqual(ids);
      for (const id of ids) expect(topics.lessons.get(id)?.map((page) => page.slug), id).toContain(slug);
    }
    expect(lessonIdsForPage(topics.pages, "guides/not-in-the-map")).toEqual([]);
  });

  it("renders a guide link on every generated lesson page", () => {
    const { source, lessonIds, topics } = published();
    const out = tempRoot();
    generateAcademy(source, join(out, "docs"), join(out, "generated"), topics.lessons);
    for (const id of lessonIds) {
      const page = readFileSync(join(out, "docs", "academy", `${id}.mdx`), "utf8");
      for (const topic of topics.lessons.get(id)!) {
        expect(page, `${id} -> ${topic.slug}`).toContain(`](${topic.href})`);
      }
    }
  });

  it("leaves lesson pages without guide links when no topic map is supplied", () => {
    const { source, lessonIds } = published();
    const out = tempRoot();
    generateAcademy(source, join(out, "docs"), join(out, "generated"));
    const page = readFileSync(join(out, "docs", "academy", `${lessonIds[0]}.mdx`), "utf8");
    expect(page).not.toContain("Read alongside");
  });

  it("refuses to generate a lesson page for a lesson the supplied map leaves out", () => {
    const { source, lessonIds, topics } = published();
    const out = tempRoot();
    const partial = new Map([...topics.lessons].slice(1));
    expect(() => generateAcademy(source, join(out, "docs"), join(out, "generated"), partial))
      .toThrow(new RegExp(`"${lessonIds[0]}"`));
  });

  it("shows the practice link from PageContext using the same map and the site base path", () => {
    const component = readFileSync(join(siteRoot, "src", "components", "PageContext.astro"), "utf8");
    expect(component).toMatch(/^import topicMap from "\.\.\/data\/topic-map\.json";$/m);
    expect(component).toMatch(/^import \{ lessonIdsForPage \} from "\.\.\/\.\.\/scripts\/topic-map";$/m);
    expect(component).toMatch(/lessonIdsForPage\(topicMap, pageId\)/);
    expect(component).toMatch(/<a href=\{lesson\.href\}>/);
    expect(component).toContain("import.meta.env.BASE_URL");
  });
});
