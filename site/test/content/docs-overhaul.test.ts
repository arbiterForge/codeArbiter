/** docs-overhaul.test.ts — the reader-facing contract from DOCS-OVERHAUL.md (M1-M6). */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildJourneySidebar } from "../../scripts/journey-navigation";
import type { ReferenceSidebarGroup, ReferenceSidebarLink } from "../../scripts/reference-sidebar";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const docsRoot = join(siteRoot, "src", "content", "docs");
const read = (path: string) => readFileSync(join(siteRoot, path), "utf8");
const doc = (path: string) => readFileSync(join(docsRoot, path), "utf8");

/** Body text a reader meets by default: frontmatter, imports and evidence disclosures removed. */
function readerLayer(source: string): string {
  return source
    .replace(/^---\n[\s\S]*?\n---\n/, "")
    .replace(/^import .*$/gm, "")
    .replace(/<LimitsAndEvidence[\s\S]*?<\/LimitsAndEvidence>/g, "")
    .replace(/<details class="ca-evidence"[\s\S]*?<\/details>/g, "");
}

const EVIDENCE_REGISTER = [
  /\bnot (?:proof|evidence|a (?:claim|guarantee|certification))\b/i,
  /\bdoes not (?:prove|establish|certify|imply|grant)\b/i,
  /\bis not (?:proof|evidence|approval|verification)\b/i,
  /\bdo not (?:infer|treat|confuse)\b/i,
  /\b(?:bounded|receipts?|charters?|route-closure)\b/i,
];

const START_PATH = [
  "index.mdx",
  "overview.md",
  "getting-started/choose-your-host.md",
  "getting-started/install.md",
  "getting-started/quickstart.md",
  "guides/first-feature.mdx",
];

function slugs(items: Array<ReferenceSidebarGroup | ReferenceSidebarLink>): string[] {
  return items.flatMap((item) => ("slug" in item ? [item.slug] : slugs(item.items)));
}

describe("M1 reader layer over an evidence layer", () => {
  it.each(START_PATH)("%s states behavior plainly outside its evidence disclosure", (path) => {
    const body = readerLayer(doc(path));
    const hits = EVIDENCE_REGISTER.flatMap((pattern) => body.match(pattern) ?? []);
    expect(hits).toEqual([]);
  });

  it("keeps the evidence disclosure native, printable and visible in forced colors", () => {
    const component = read("src/components/LimitsAndEvidence.astro");
    expect(component).toContain('<details class="ca-evidence"');
    expect(component).toContain("<summary");
    const css = read("src/styles/callouts.css");
    expect(css).toMatch(/@media print[\s\S]*\.ca-evidence/);
    expect(css).toMatch(/@media \(forced-colors: active\)[\s\S]*\.ca-evidence/);
  });

  it("keeps the required reviewer-charter disclosure in the evidence layer outside its home page", () => {
    const homes = [
      "src/content/docs/overview.md",
      "src/content/docs/glossary.md",
      "src/content/docs/getting-started/compatibility.mdx",
      "src/curated/commands/checkpoint.md",
      "src/curated/commands/pr.md",
      "src/curated/commands/review.md",
      "src/curated/commands/tribunal.md",
    ];
    // test_public_codex_docs.py requires the scoped claim on each page; it stays, one click down.
    for (const path of homes) expect(readerLayer(read(path)), path).not.toContain("Published releases from 0.7.5");
    expect(doc("getting-started/claude-code-and-codex.md")).toContain("0.7.5");
  });

  it("tells authors where caveats belong", () => {
    expect(read("VOICE.md")).toContain("LimitsAndEvidence");
  });
});

describe("M2 one front door", () => {
  const sidebar = buildJourneySidebar([], []);

  it("lists no destination twice", () => {
    const all = slugs(sidebar);
    expect(all.filter((slug, index) => all.indexOf(slug) !== index)).toEqual([]);
  });

  it("keeps command reference out of the Guides group", () => {
    const guides = sidebar.find((group) => group.label === "Guides")!;
    expect(slugs(guides.items).filter((slug) => slug.startsWith("reference/"))).toEqual([]);
  });

  it("sends lost readers to the one start path and keeps the self-guided path with the Academy", () => {
    const notFound = read("src/pages/404.astro");
    expect(notFound).toContain("/overview/");
    expect(notFound).not.toContain("/learn/");
    expect(read("src/components/AcademyOverview.astro")).toContain("/learn/");
  });
});

describe("M3 landing in five sections", () => {
  const landing = doc("index.mdx");

  it("has exactly five top-level sections and one eyebrow", () => {
    expect(landing.match(/^<section\b/gm)).toHaveLength(5);
    expect(landing.match(/class="ca-eyebrow"/g)).toHaveLength(1);
  });

  it("drops the inventory sections from the front page", () => {
    for (const removed of ["<ArtifactWorkbench", "<TrustRow", "ca-journey-preview", "ca-proof-strip"]) {
      expect(landing).not.toContain(removed);
    }
    expect(landing).not.toContain("./learn/#stage-");
  });

  it("keeps digests and publication identity inside the replay's disclosure", () => {
    const proof = read("src/components/HookProof.astro");
    const caption = proof.match(/<figcaption>[\s\S]*?<\/figcaption>/)?.[0] ?? "";
    expect(caption).not.toContain("shortDigest");
    expect(caption).not.toContain("shortPublicationCommit");
    const disclosure = proof.match(/<details>[\s\S]*?<\/details>/)?.[0] ?? "";
    expect(disclosure).toContain("publishedCa.publicationCommit");
    expect(disclosure).toContain("proof.sourceSha256");
  });
});

describe("M4 lighter page furniture", () => {
  it("renders the journey card as one line with a disclosure for prerequisites and proof", () => {
    const context = read("src/components/PageContext.astro");
    expect(context).toContain('<details class="ca-page-context__more"');
    expect(context).toMatch(/<details[\s\S]*Before you start[\s\S]*Proof of completion[\s\S]*<\/details>/);
  });

  it("turns the splash docs rail into a compact control on narrow screens", () => {
    const rail = read("src/components/SplashDocsRail.astro");
    expect(rail).toMatch(/@media \(max-width: 50rem\)/);
  });
});

describe("M5 quieter visual style", () => {
  it("renders outcomes as a plain list, not panels", () => {
    const outcomes = doc("index.mdx").match(/<section class="ca-section ca-guarantees"[\s\S]*?<\/section>/)?.[0] ?? "";
    expect(outcomes).not.toContain("ca-panel");
    expect(read("DESIGN-SYSTEM.md")).toContain("Cards only where the reader chooses");
  });
});

describe("M6 task pages split from reference pages", () => {
  const pairs = [
    ["codearbiter-directory.md", "codearbiter-directory/files.md", "/codearbiter-directory/files/", "/codearbiter-directory/"],
    ["hooks.md", "hooks/scripts.md", "/hooks/scripts/", "/hooks/"],
    ["getting-started/compatibility.mdx", "getting-started/compatibility/runtime.md", "/getting-started/compatibility/runtime/", "/getting-started/compatibility/"],
    ["guides/uninstalling.md", "guides/uninstalling/details.md", "/guides/uninstalling/details/", "/guides/uninstalling/"],
  ] as const;

  it.each(pairs)("%s links its reference page %s and back", (task, reference, referenceUrl, taskUrl) => {
    expect(existsSync(join(docsRoot, reference)), reference).toBe(true);
    expect(doc(task)).toContain(referenceUrl);
    expect(doc(reference)).toContain(taskUrl);
  });

  it("puts every reference page in the sidebar", () => {
    const all = slugs(buildJourneySidebar([], []));
    for (const [, reference] of pairs) expect(all).toContain(reference.replace(/\.mdx?$/, ""));
  });

  // link-audit checks routes, not #fragments, so a moved section would break inbound anchors silently.
  it("resolves every inbound fragment link to a heading on the page that now holds it", () => {
    const anchorsByUrl = new Map<string, Set<string>>();
    for (const [task, reference, referenceUrl, taskUrl] of pairs) {
      anchorsByUrl.set(taskUrl, anchors(join(docsRoot, task)));
      anchorsByUrl.set(referenceUrl, anchors(join(docsRoot, reference)));
    }
    const sources = [
      ...walk(join(siteRoot, "src", "content", "docs")),
      ...walk(join(siteRoot, "src", "curated")),
      ...walk(join(siteRoot, "scripts", "generator")),
    ];
    const target = /(\/(?:codearbiter-directory|hooks|getting-started\/compatibility|guides\/uninstalling)\/(?:[a-z]+\/)?)#([a-z0-9-]+)/g;
    const broken = sources.flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(target)]
        .filter(([, url, fragment]) => !anchorsByUrl.get(url)?.has(fragment))
        .map(([link]) => `${file.slice(siteRoot.length + 1)}: ${link}`),
    );
    expect(broken).toEqual([]);
  });
});

/** Heading slugs (github-slugger rules for these headings) plus explicit ids, including imported components'. */
function anchors(file: string): Set<string> {
  const source = readFileSync(file, "utf8");
  const ids = new Set<string>();
  for (const [, heading] of source.matchAll(/^#{2,6} (.+)$/gm)) {
    ids.add(heading.replace(/`/g, "").toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, "").replace(/ /g, "-"));
  }
  const components = [...source.matchAll(/^import \w+ from ["'](.+\.astro)["'];?$/gm)]
    .map(([, path]) => readFileSync(resolve(file, "..", path), "utf8"));
  for (const text of [source, ...components]) {
    for (const [, id] of text.matchAll(/\bid="([^"{}]+)"/g)) ids.add(id);
  }
  return ids;
}

function walk(directory: string): string[] {
  return readdirSync(directory, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(?:mdx?|ts)$/.test(entry.name))
    .map((entry) => join(entry.parentPath, entry.name));
}
