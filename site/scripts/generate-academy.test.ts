import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import type { AcademySource } from "./academy-source";
import { generateAcademy } from "./generate-academy";

const fixtureRoots: string[] = [];
const academyOverviewComponent = new URL("../src/components/AcademyOverview.astro", import.meta.url);
const siteRoot = fileURLToPath(new URL("..", import.meta.url));
const requiredTracks = [
  ["foundations", "Foundation"],
  ["practitioner", "Practitioner"],
  ["power-user", "Power user"],
] as const;

function extractEmittedScripts(html: string): string[] {
  const normalizedHtml = html.toLowerCase();
  const scripts: string[] = [];
  let cursor = 0;

  while (cursor < html.length) {
    const openingTagStart = normalizedHtml.indexOf("<script", cursor);
    if (openingTagStart < 0) return scripts;
    const openingTagEnd = normalizedHtml.indexOf(">", openingTagStart);
    const closingTagStart = normalizedHtml.indexOf("</script", openingTagEnd + 1);
    const closingTagEnd = normalizedHtml.indexOf(">", closingTagStart);
    if (openingTagEnd < 0 || closingTagStart < 0 || closingTagEnd < 0) return scripts;

    scripts.push(html.slice(openingTagEnd + 1, closingTagStart));
    cursor = closingTagEnd + 1;
  }

  return scripts;
}

const publicSource: AcademySource = {
  release: "preview-0.32",
  commit: "dcdc1b0ab023cd8f346e89d41a1bcb6f8a027acf",
  home: {
    title: "Start here",
    anchor: "complete-these-five-setup-steps-before-f01",
    steps: [],
  },
  lessons: [
    {
      id: "F01-fork-clone-doctor",
      track: "foundations",
      guide: [
        "---",
        "id: F01-fork-clone-doctor",
        "track: foundations",
        "order: 1",
        "title: Fork, clone, and doctor safety",
        "outcome: Prove the repository has safe fetch and push boundaries.",
        "prerequisites: none",
        "estimated_minutes: 30",
        "scenario_command: {{action:F01-prepare}}",
        "checkpoint_command: {{action:F01-check}}",
        "next_lab: none",
        "---",
        "",
        "# F01 - Fork, clone, and Doctor safety",
        "",
        "{{action:F01-prepare}}",
        "",
        "Continue only after the prepared attempt is ready.",
        "",
        "See [Academy Home](../../index.html#setup) and [F02](../F02-orient-to-state/index.html).",
      ].join("\n"),
      actions: {
        schema_version: 1,
        lesson_contract_version: 1,
        document_id: "F01-fork-clone-doctor",
        actions: [{ id: "F01-prepare" }],
      },
    },
    {
      id: "F02-orient-to-state",
      track: "foundations",
      guide: [
        "---",
        "id: F02-orient-to-state",
        "track: foundations",
        "order: 2",
        "title: Orient to repository state",
        "outcome: Read the current governance state.",
        "prerequisites: F01-fork-clone-doctor",
        "estimated_minutes: 15",
        "scenario_command: {{action:F02-prepare}}",
        "checkpoint_command: {{action:F02-check}}",
        "next_lab: none",
        "---",
        "",
        "# F02 - Orient to repository state",
        "",
        "{{action:F02-prepare}}",
      ].join("\n"),
      actions: {
        schema_version: 1,
        lesson_contract_version: 1,
        document_id: "F02-orient-to-state",
        actions: [{ id: "F02-prepare" }],
      },
    },
    {
      id: "P01-practice",
      track: "practitioner",
      guide: [
        "---",
        "id: P01-practice",
        "track: practitioner",
        "order: 1",
        "title: Practice governed delivery",
        "outcome: Complete a realistic governed workflow.",
        "prerequisites: F02-orient-to-state",
        "estimated_minutes: 20",
        "scenario_command: {{action:P01-prepare}}",
        "checkpoint_command: {{action:P01-check}}",
        "next_lab: none",
        "---",
        "",
        "# P01 - Practice governed delivery",
        "",
        "{{action:P01-prepare}}",
      ].join("\n"),
      actions: {
        schema_version: 1,
        lesson_contract_version: 1,
        document_id: "P01-practice",
        actions: [{ id: "P01-prepare" }],
      },
    },
    {
      id: "U01-operate",
      track: "power-user",
      guide: [
        "---",
        "id: U01-operate",
        "track: power-user",
        "order: 1",
        "title: Operate advanced delivery",
        "outcome: Diagnose an advanced delivery boundary.",
        "prerequisites: P01-practice",
        "estimated_minutes: 25",
        "scenario_command: {{action:U01-prepare}}",
        "checkpoint_command: {{action:U01-check}}",
        "next_lab: none",
        "---",
        "",
        "# U01 - Operate advanced delivery",
        "",
        "{{action:U01-prepare}}",
      ].join("\n"),
      actions: {
        schema_version: 1,
        lesson_contract_version: 1,
        document_id: "U01-operate",
        actions: [{ id: "U01-prepare" }],
      },
    },
  ],
};

function createOutputRoots(): { docsRoot: string; generatedRoot: string } {
  const root = mkdtempSync(join(tmpdir(), "academy-generation-"));
  fixtureRoots.push(root);
  return {
    docsRoot: join(root, "content", "docs"),
    generatedRoot: join(root, "generated"),
  };
}

function listGeneratedRoutes(docsRoot: string): string[] {
  const academyRoot = join(docsRoot, "academy");
  return (readdirSync(academyRoot, { recursive: true }) as string[])
    .filter(path => path.endsWith(".mdx"))
    .map(path => relative(docsRoot, join(academyRoot, path)).replaceAll("\\", "/"))
    .sort();
}

class InteractiveElement extends EventTarget {
  open: boolean;
  textContent: string;
  readonly attributes: Map<string, string>;
  readonly children: InteractiveElement[];

  constructor(
    textContent = "",
    attributes = new Map<string, string>(),
    children: InteractiveElement[] = [],
  ) {
    super();
    this.open = attributes.has("open");
    this.textContent = textContent;
    this.attributes = attributes;
    this.children = children;
  }

  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }

  getAttribute(name: string): string | null {
    return this.attributes.get(name) ?? null;
  }

  querySelector(selector: string): InteractiveElement | null {
    return this.children.find((element) => element.matches(selector)) ?? null;
  }

  matches(selector: string): boolean {
    const attributeSelector = selector.match(/^\[([a-z0-9-]+)\]$/i);
    if (attributeSelector) return this.attributes.has(attributeSelector[1]);
    if (selector.startsWith(".")) {
      return (this.attributes.get("class") ?? "").split(/\s+/).includes(selector.slice(1));
    }
    return false;
  }
}

function parseAttributes(tag: string): Map<string, string> {
  return new Map(
    [...tag.matchAll(/\s([a-z][a-z0-9-]*)(?:="([^"]*)")?/gi)]
      .map((match) => [match[1], match[2] ?? ""]),
  );
}

afterEach(() => {
  for (const root of fixtureRoots.splice(0)) rmSync(root, { force: true, recursive: true });
});

describe("generateAcademy", () => {
  let integrationAcademyHtml = "";
  const integrationLessonHtml = new Map<string, string>();

  beforeAll(() => {
    const npmCli = process.env.npm_execpath;
    if (!npmCli) throw new Error("npm_execpath is required to run the Academy integration build");

    execFileSync(process.execPath, [npmCli, "run", "build"], {
      cwd: siteRoot,
      stdio: "pipe",
    });

    integrationAcademyHtml = readFileSync(join(siteRoot, "dist", "academy", "index.html"), "utf8");
    for (const lessonSlug of ["p01-feature-through-plan", "u01-autonomous-sprint"]) {
      integrationLessonHtml.set(
        lessonSlug,
        readFileSync(join(siteRoot, "dist", "academy", lessonSlug, "index.html"), "utf8"),
      );
    }
  }, 30_000);

  it("builds one accessible Academy overview from the canonical public inventory", () => {
    const academyHtml = integrationAcademyHtml;
    const generatedContent = readFileSync(
      join(siteRoot, "src", "generated", "academy-content.ts"),
      "utf8",
    );
    const generatedSidebar = JSON.parse(
      readFileSync(join(siteRoot, "src", "generated", "academy-sidebar.json"), "utf8"),
    ) as Array<{ label: string; items: Array<{ slug: string }> }>;
    const publicLessonIds = [...generatedContent.matchAll(/\n    \{\n      id: "([^"]+)",\n      track:/g)]
      .map((match) => match[1]);

    expect(academyHtml.match(/<h1\b/g)).toHaveLength(1);
    expect(academyHtml.match(/id="complete-these-five-setup-steps-before-f01"/g)).toHaveLength(1);
    expect(academyHtml.match(/id="setup"/g)).toHaveLength(1);
    expect(academyHtml).toContain("Open the Academy fork page, choose your GitHub account as the owner");
    expect(academyHtml).toContain('href="https://github.com/arbiterForge/arbiter-academy/fork"');
    expect(academyHtml).toContain("git clone https://github.com/&lt;your-account&gt;/arbiter-academy.git");
    expect(academyHtml).toContain('href="/learn/"');
    expect(academyHtml).toContain("Academy provides verifier-backed practice");
    expect(academyHtml).toMatch(/The Learning Path provides\s+guided documentation/);
    expect(academyHtml).toContain("does not create an account, import progress, or store completion state");
    expect(academyHtml).not.toContain("ca-page-context");
    expect(publicLessonIds.length).toBeGreaterThan(0);
    for (const lessonId of publicLessonIds) {
      expect(academyHtml.match(new RegExp(`data-academy-lesson="${lessonId}"`, "g")) ?? []).toHaveLength(1);
    }
    expect(academyHtml).toContain('data-academy-show-all aria-controls="track-foundations-more track-practitioner-more track-power-user-more"');
    expect(academyHtml.match(/<details[^>]+id="track-(?:foundations|practitioner|power-user)-more"/g)).toHaveLength(3);
    const mainNavigation = academyHtml.match(/<nav[^>]*aria-label="Main"[\s\S]*?<\/nav>/)?.[0];
    expect(mainNavigation).toBeDefined();
    expect(
      [...(mainNavigation?.matchAll(/<span class="large[^"]*">(Foundation|Practitioner|Power user)<\/span>/g) ?? [])]
        .map((match) => match[1]),
    ).toEqual(["Foundation", "Practitioner", "Power user"]);
    expect(generatedSidebar.map((group) => [group.label, group.items.length])).toEqual([
      ["Foundation", 5],
      ["Practitioner", 9],
      ["Power user", 8],
    ]);
    expect(generatedSidebar.flatMap((group) => group.items.map((item) => item.slug)).filter(slug => !slug.startsWith("academy/tracks/"))).toEqual(
      publicLessonIds.map((lessonId) => `academy/${lessonId.toLowerCase()}`),
    );
    for (const lessonId of publicLessonIds) {
      expect(mainNavigation?.match(new RegExp(`href="/academy/${lessonId.toLowerCase()}/"`, "g")) ?? []).toHaveLength(1);
    }
    const trackBoundaryPages = [
      ["p01-feature-through-plan", "Practitioner", "f04-fix-with-evidence", "p02-commit-review-pr"],
      ["u01-autonomous-sprint", "Power user", "p08-repository-hygiene", "u02-override-audit-metrics"],
    ] as const;
    for (const [lessonSlug, trackLabel, previousSlug, nextSlug] of trackBoundaryPages) {
      const lessonHtml = integrationLessonHtml.get(lessonSlug) ?? "";
      expect(lessonHtml).not.toBe("");
      const lessonNavigation = lessonHtml.match(/<nav[^>]*aria-label="Main"[\s\S]*?<\/nav>/)?.[0];
      expect(lessonNavigation).toBeDefined();
      const currentLinks = [...(lessonNavigation?.matchAll(/<a\b[^>]*\baria-current="page"[^>]*>/g) ?? [])];
      expect(currentLinks).toHaveLength(1);
      expect(parseAttributes(currentLinks[0][0]).get("href")).toBe(`/academy/${lessonSlug}/`);
      const currentLinkIndex = currentLinks[0].index ?? -1;
      const disclosureStack: Array<{ label?: string; open: boolean }> = [];
      const disclosureTokens = /<details\b([^>]*)>|<\/details>|<summary[^>]*>[\s\S]*?<span class="large[^"]*">([^<]+)<\/span>[\s\S]*?<\/summary>/g;
      for (const token of lessonNavigation?.slice(0, currentLinkIndex).matchAll(disclosureTokens) ?? []) {
        if (token[0].startsWith("<details")) disclosureStack.push({ open: /\bopen\b/.test(token[1]) });
        else if (token[0] === "</details>") disclosureStack.pop();
        else if (disclosureStack.length > 0) disclosureStack.at(-1)!.label = token[2];
      }
      expect(disclosureStack).toEqual([
        { label: "Academy", open: true },
        { label: trackLabel, open: true },
      ]);
      expect(lessonHtml).toContain(`href="../${previousSlug}/" rel="prev"`);
      expect(lessonHtml).toContain(`href="../${nextSlug}/" rel="next"`);
    }
  }, 30_000);

  it("distinguishes the Pi skill fallback from the ordinary Pi command", () => {
    const lessonHtml = integrationLessonHtml.get("p01-feature-through-plan") ?? "";
    const commandCards = [...lessonHtml.matchAll(
      /<section class="academy-command" data-academy-command-variant[\s\S]*?<\/section>/g,
    )].map((match) => match[0]);
    const direct = commandCards.find((card) => card.includes("/ca-feature"));
    const fallback = commandCards.find((card) => card.includes("/skill:ca-feature"));

    expect(direct).toContain('<p class="academy-command__label" id="academy-command-P01-draft-spec-pi-direct-label">Any OS · Pi</p>');
    expect(fallback).toContain('<p class="academy-command__label" id="academy-command-P01-draft-spec-pi-fallback-label">Any OS · Pi · Fallback</p>');
    expect(fallback).toContain('aria-label="Copy Any OS · Pi · Fallback command"');
  });

  it("executes the emitted View all lessons script and keeps its disclosure state synchronized", () => {
    expect(integrationAcademyHtml).not.toBe("");
    const academyHtml = integrationAcademyHtml;
    const disclosureTags = [...academyHtml.matchAll(
      /<details\b(?=[^>]*class="[^"]*\bacademy-overview__more\b[^"]*")[^>]*>/g,
    )].map((match) => match[0]);
    const revealControlMarkup = academyHtml.match(
      /(<a\b(?=[^>]*class="[^"]*\bacademy-overview__all-lessons\b[^"]*")[^>]*>)([\s\S]*?)<\/a>/,
    );
    const revealLabelMarkup = revealControlMarkup?.[2].match(/(<span\b[^>]*>)([^<]*)<\/span>/);
    const pageScript = extractEmittedScripts(academyHtml)
      .find((script) => script.includes("data-academy-show-all"));
    expect(revealControlMarkup).not.toBeNull();
    expect(revealLabelMarkup).not.toBeNull();

    const label = new InteractiveElement(
      revealLabelMarkup![2],
      parseAttributes(revealLabelMarkup![1]),
    );
    const showAll = new InteractiveElement(
      "",
      parseAttributes(revealControlMarkup![1]),
      [label],
    );
    const disclosures = disclosureTags.map((tag) => new InteractiveElement("", parseAttributes(tag)));
    const documentHarness = {
      addEventListener: () => {},
      querySelector: (selector: string) => showAll.matches(selector) ? showAll : null,
      querySelectorAll: (selector: string) => disclosures.filter((element) => element.matches(selector)),
    };

    expect(disclosures).toHaveLength(3);
    expect(showAll.attributes.has("data-academy-show-all")).toBe(true);
    expect(showAll.getAttribute("aria-controls")).toBe(
      disclosures.map((details) => details.getAttribute("id")).join(" "),
    );
    expect(showAll.getAttribute("aria-expanded")).toBe("false");
    expect(label.attributes.has("data-academy-show-all-label")).toBe(true);
    expect(label.textContent).toBe("View all lessons");
    expect(disclosures.every((details) => !details.open)).toBe(true);
    expect(pageScript).toBeDefined();
    Function("document", pageScript!)(documentHarness);

    showAll.dispatchEvent(new Event("click"));
    expect(disclosures.every((details) => details.open)).toBe(true);
    expect(showAll.getAttribute("aria-expanded")).toBe("true");
    expect(label.textContent).toBe("All lessons shown");

    for (const details of disclosures) {
      details.open = false;
      details.dispatchEvent(new Event("toggle"));
      expect(showAll.getAttribute("aria-expanded")).toBe("false");
      expect(label.textContent).toBe("View all lessons");

      details.open = true;
      details.dispatchEvent(new Event("toggle"));
      expect(showAll.getAttribute("aria-expanded")).toBe("true");
      expect(label.textContent).toBe("All lessons shown");
    }
  }, 30_000);

  it("emits the index, three source-bound tracks and one route for every public lab", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();

    generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(listGeneratedRoutes(docsRoot)).toEqual([
      "academy/F01-fork-clone-doctor.mdx",
      "academy/F02-orient-to-state.mdx",
      "academy/P01-practice.mdx",
      "academy/U01-operate.mdx",
      "academy/index.mdx",
      "academy/tracks/foundations.mdx",
      "academy/tracks/power-user.mdx",
      "academy/tracks/practitioner.mdx",
    ]);
    const indexPage = readFileSync(join(docsRoot, "academy", "index.mdx"), "utf8");
    expect(existsSync(academyOverviewComponent)).toBe(true);
    expect(indexPage).toContain('description: "Guided, evidence-based practice for the codeArbiter workflow."');
    expect(indexPage).toContain('import AcademyOverview from "../../../components/AcademyOverview.astro";');
    expect(indexPage).toContain("<AcademyOverview />");
    expect(indexPage).not.toMatch(/<h1\b/i);
    expect(indexPage).not.toContain("## Published lessons");
    const lessonPage = readFileSync(
      join(docsRoot, "academy", "F01-fork-clone-doctor.mdx"),
      "utf8",
    );
    expect(lessonPage).toContain('title: "Fork, clone, and doctor safety"');
    expect(lessonPage).toContain('description: "Prove the repository has safe fetch and push boundaries."');
    expect(lessonPage).toContain('release: "preview-0.32"');
    expect(lessonPage).toContain('commit: "dcdc1b0ab023cd8f346e89d41a1bcb6f8a027acf"');
    expect(lessonPage).not.toContain("# F01 - Fork, clone, and Doctor safety");
    expect(lessonPage).toContain('import AcademyCommandPreferences from "../../../components/AcademyCommandPreferences.astro";');
    expect(lessonPage).toContain('<AcademyCommandPreferences labId="F01-fork-clone-doctor" />');
    expect(lessonPage).toContain('<AcademyLesson labId="F01-fork-clone-doctor" actionId="F01-prepare" />');
    expect(lessonPage).toContain("Continue only after the prepared attempt is ready.");
    expect(lessonPage).toContain("[Academy Home](/academy/#setup)");
    expect(lessonPage).toContain("[F02](/academy/f02-orient-to-state/)");
    expect(lessonPage).toContain('<AcademyWayfinding labId="F01-fork-clone-doctor" />');
    expect(lessonPage).toContain('prev: false');
    expect(lessonPage).toContain('next: false');
    for (const [track] of requiredTracks) {
      const trackPage = readFileSync(join(docsRoot, "academy", "tracks", `${track}.mdx`), "utf8");
      expect(trackPage).toContain(`release: "${publicSource.release}"`);
      expect(trackPage).toContain(`commit: "${publicSource.commit}"`);
      expect(trackPage).toContain(`<AcademyTrack track="${track}" />`);
    }
  });

  it("extracts scripts with uppercase tags and whitespace before the closing bracket", () => {
    const uppercaseScript = "<SCRIPT>document.body.dataset.ready = \"true\";</SCRIPT >";

    expect(extractEmittedScripts(uppercaseScript)).toEqual([
      'document.body.dataset.ready = "true";',
    ]);
  });

  it("only exposes View all lessons when a track has hidden lessons", () => {
    const component = readFileSync(academyOverviewComponent, "utf8");

    expect(component).toContain(
      "const tracksWithHiddenLessons = tracks.filter((track) => track.lessons.length > 1);",
    );
    expect(component).toContain("{tracksWithHiddenLessons.length > 0 && (");
  });

  it("does not emit a route for a lesson absent from the preview manifest", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();
    const academyRoot = join(docsRoot, "academy");
    mkdirSync(academyRoot, { recursive: true });
    writeFileSync(join(academyRoot, "U99-private.mdx"), "private stale route");

    generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(listGeneratedRoutes(docsRoot)).not.toContain("academy/U99-private.mdx");
  });

  it.each(requiredTracks)("rejects landing data missing the %s Academy track", (track, label) => {
    const { docsRoot, generatedRoot } = createOutputRoots();
    const withoutRequiredTrack: AcademySource = {
      ...publicSource,
      lessons: publicSource.lessons.filter((lesson) => lesson.track !== track),
    };

    expect(() => generateAcademy(withoutRequiredTrack, docsRoot, generatedRoot)).toThrow(new RegExp(label));
  });

  it("preserves manifest ordering in typed content and sidebar data", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();

    const result = generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(result.sidebarItems).toEqual([
      { label: "Fork, clone, and doctor safety", slug: "academy/f01-fork-clone-doctor" },
      { label: "Orient to repository state", slug: "academy/f02-orient-to-state" },
      { label: "Practice governed delivery", slug: "academy/p01-practice" },
      { label: "Operate advanced delivery", slug: "academy/u01-operate" },
    ]);
    expect(JSON.parse(readFileSync(join(generatedRoot, "academy-sidebar.json"), "utf8"))).toEqual([
      {
        label: "Foundation",
        collapsed: true,
        items: [
          { label: "Track overview", slug: "academy/tracks/foundations" },
          { label: "Fork, clone, and doctor safety", slug: "academy/f01-fork-clone-doctor" },
          { label: "Orient to repository state", slug: "academy/f02-orient-to-state" },
        ],
      },
      {
        label: "Practitioner",
        collapsed: true,
        items: [
          { label: "Track overview", slug: "academy/tracks/practitioner" },
          { label: "Practice governed delivery", slug: "academy/p01-practice" },
        ],
      },
      {
        label: "Power user",
        collapsed: true,
        items: [
          { label: "Track overview", slug: "academy/tracks/power-user" },
          { label: "Operate advanced delivery", slug: "academy/u01-operate" },
        ],
      },
    ]);
    const generatedContent = readFileSync(join(generatedRoot, "academy-content.ts"), "utf8");
    expect(generatedContent).toContain('home: {\n    title: "Start here",\n    anchor: "complete-these-five-setup-steps-before-f01",\n    steps: []\n  }');
    expect(generatedContent.match(/\n    \{\n      id: "/g)).toHaveLength(publicSource.lessons.length);
    for (const lesson of publicSource.lessons) {
      const canonicalRecord = `\n    {\n      id: "${lesson.id}",\n      track: "${lesson.track}",`;
      expect(generatedContent.split(canonicalRecord)).toHaveLength(2);
    }
    expect(generatedContent.indexOf('id: "F01-fork-clone-doctor"')).toBeLessThan(
      generatedContent.indexOf('id: "F02-orient-to-state"'),
    );
    expect(generatedContent).toContain('markdown: "# F01 - Fork, clone, and Doctor safety\\n\\n{{action:F01-prepare}}\\n\\nContinue only after the prepared attempt is ready.\\n\\nSee [Academy Home](../../index.html#setup) and [F02](../F02-orient-to-state/index.html)."');
  });
});
