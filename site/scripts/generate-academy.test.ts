import { afterEach, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import type { AcademySource } from "./academy-source";
import { generateAcademy } from "./generate-academy";

const fixtureRoots: string[] = [];
const academyOverviewComponent = new URL("../src/components/AcademyOverview.astro", import.meta.url);
const siteRoot = fileURLToPath(new URL("..", import.meta.url));

const publicSource: AcademySource = {
  release: "preview-0.30",
  commit: "f3a645f8022d58fce524886e5a8a6869d04a47d7",
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
  return ["index.mdx", "F01-fork-clone-doctor.mdx", "F02-orient-to-state.mdx", "U99-private.mdx"]
    .filter((path) => existsSync(join(academyRoot, path)))
    .map((path) => relative(docsRoot, join(academyRoot, path)).replaceAll("\\", "/"));
}

afterEach(() => {
  for (const root of fixtureRoots.splice(0)) rmSync(root, { force: true, recursive: true });
});

describe("generateAcademy", () => {
  it("builds one accessible Academy overview from the canonical public inventory", () => {
    const npmCli = process.env.npm_execpath;
    if (!npmCli) throw new Error("npm_execpath is required to run the Academy integration build");

    execFileSync(process.execPath, [npmCli, "run", "build"], {
      cwd: siteRoot,
      stdio: "pipe",
    });

    const academyHtml = readFileSync(join(siteRoot, "dist", "academy", "index.html"), "utf8");
    const generatedContent = readFileSync(
      join(siteRoot, "src", "generated", "academy-content.ts"),
      "utf8",
    );
    const publicLessonIds = [...generatedContent.matchAll(/\n    \{\n      id: "([^"]+)",\n      track:/g)]
      .map((match) => match[1]);

    expect(academyHtml.match(/<h1\b/g)).toHaveLength(1);
    expect(academyHtml.match(/id="complete-these-five-setup-steps-before-f01"/g)).toHaveLength(1);
    expect(academyHtml).not.toContain("ca-page-context");
    expect(publicLessonIds.length).toBeGreaterThan(0);
    for (const lessonId of publicLessonIds) {
      expect(academyHtml.match(new RegExp(`data-academy-lesson="${lessonId}"`, "g")) ?? []).toHaveLength(1);
    }
    expect(academyHtml).toContain('data-academy-show-all aria-controls="track-foundations-more track-practitioner-more track-power-user-more"');
    expect(academyHtml.match(/<details[^>]+id="track-(?:foundations|practitioner|power-user)-more"/g)).toHaveLength(3);
  }, 30_000);

  it("emits one Academy index plus one MDX route for every public lab", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();

    generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(listGeneratedRoutes(docsRoot)).toEqual([
      "academy/index.mdx",
      "academy/F01-fork-clone-doctor.mdx",
      "academy/F02-orient-to-state.mdx",
    ]);
    const indexPage = readFileSync(join(docsRoot, "academy", "index.mdx"), "utf8");
    expect(existsSync(academyOverviewComponent)).toBe(true);
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
    expect(lessonPage).toContain('release: "preview-0.30"');
    expect(lessonPage).toContain('commit: "f3a645f8022d58fce524886e5a8a6869d04a47d7"');
    expect(lessonPage).not.toContain("# F01 - Fork, clone, and Doctor safety");
    expect(lessonPage).toContain('import AcademyCommandPreferences from "../../../components/AcademyCommandPreferences.astro";');
    expect(lessonPage).toContain('<AcademyCommandPreferences labId="F01-fork-clone-doctor" />');
    expect(lessonPage).toContain('<AcademyLesson labId="F01-fork-clone-doctor" actionId="F01-prepare" />');
    expect(lessonPage).toContain("Continue only after the prepared attempt is ready.");
    expect(lessonPage).toContain("[Academy Home](/academy/#setup)");
    expect(lessonPage).toContain("[F02](/academy/f02-orient-to-state/)");
  });

  it("does not emit a route for a lesson absent from the preview manifest", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();
    const academyRoot = join(docsRoot, "academy");
    mkdirSync(academyRoot, { recursive: true });
    writeFileSync(join(academyRoot, "U99-private.mdx"), "private stale route");

    generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(listGeneratedRoutes(docsRoot)).not.toContain("academy/U99-private.mdx");
  });

  it("preserves manifest ordering in typed content and sidebar data", () => {
    const { docsRoot, generatedRoot } = createOutputRoots();

    const result = generateAcademy(publicSource, docsRoot, generatedRoot);

    expect(result.sidebarItems).toEqual([
      { label: "Fork, clone, and doctor safety", slug: "academy/f01-fork-clone-doctor" },
      { label: "Orient to repository state", slug: "academy/f02-orient-to-state" },
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
