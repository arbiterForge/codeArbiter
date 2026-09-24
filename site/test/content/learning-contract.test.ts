import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const docsRoot = join(process.cwd(), "src", "content", "docs");
const academyOverview = join(process.cwd(), "src", "components", "AcademyOverview.astro");

function contentFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return contentFiles(path);
    return [".md", ".mdx"].includes(extname(entry.name)) ? [path] : [];
  });
}

function frontmatter(source: string): string {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  return match?.[1] ?? "";
}

describe("hand-authored learning contract", () => {
  const handPages = contentFiles(docsRoot).filter((path) => {
    const route = relative(docsRoot, path).replaceAll("\\", "/");
    return !route.startsWith("reference/")
      && !route.startsWith("academy/")
      && route !== "index.mdx"
      && route !== "changelog.md";
  });

  it("gives every hand-authored page an outcome, prerequisite context, and proof", () => {
    const failures = handPages.flatMap((path) => {
      const metadata = frontmatter(readFileSync(path, "utf8"));
      const missing = ["journey:", "level:", "time:", "outcome:", "prerequisites:", "proof:"]
        .filter((field) => !metadata.includes(field));
      return missing.length
        ? [`${relative(docsRoot, path)}: ${missing.join(", ")}`]
        : [];
    });
    expect(failures).toEqual([]);
  });

  it("keeps hand-authored page descriptions specific enough to orient search results", () => {
    const failures = handPages.flatMap((path) => {
      const metadata = frontmatter(readFileSync(path, "utf8"));
      const description = metadata.match(/^description:\s*["']?(.+?)["']?\s*$/m)?.[1] ?? "";
      return description.length >= 45
        ? []
        : [`${relative(docsRoot, path)}: ${description.length} characters`];
    });
    expect(failures).toEqual([]);
  });

  it("keeps every authored page substantial, structured, and connected to a next step", () => {
    const failures = handPages.flatMap((path) => {
      const source = readFileSync(path, "utf8");
      const route = relative(docsRoot, path).replaceAll("\\", "/");
      // This one index renders its substantive sections from the content collection.
      // Its complete H2/card/outcome structure is asserted against the actual /docs/ build
      // by test-academy-non-root-base.mjs, not measured from an MDX component tag.
      if (route === "guides/index.mdx") {
        expect(source).toContain("import GuideDirectory from '../../../components/GuideDirectory.astro'");
        expect(source).toContain("<GuideDirectory />");
        expect(source).toContain("/guides/review-and-ship/");
        return [];
      }
      const body = source.replace(/^---\r?\n[\s\S]*?\r?\n---/, "");
      const wordCount = body.match(/\b[\p{L}\p{N}][\p{L}\p{N}'-]*\b/gu)?.length ?? 0;
      const h2Count = body.match(/^## /gm)?.length ?? 0;
      const hasInternalPath =
        /(?:href=|]\()["']?\/?(?:getting-started|guides|concepts|reference|feature-forge|overview|learn|enforcement|hooks|faq|glossary|codearbiter-directory)/.test(body)
        || body.includes("href={`${base}");
      const gaps = [
        wordCount < 250 ? `${wordCount} words` : "",
        h2Count < 2 ? `${h2Count} H2 sections` : "",
        !hasInternalPath ? "no internal next-step link" : "",
      ].filter(Boolean);
      return gaps.length ? [`${route}: ${gaps.join(", ")}`] : [];
    });
    expect(failures).toEqual([]);
  });

  it("gives every operational walkthrough a verification or recovery path", () => {
    const operationalRoutes = [
      "getting-started/install.md",
      "getting-started/pi.md",
      "getting-started/quickstart.md",
      "feature-forge/using-preview-features.md",
      "guides/adding-a-dependency.md",
      "guides/autonomous-sprints.mdx",
      "guides/ca-sandbox.md",
      "guides/feature-lane.mdx",
      "guides/opt-in-a-repo.mdx",
      "guides/overriding-a-gate.md",
      "guides/recording-adrs.md",
      "guides/review-and-ship.mdx",
      "guides/releasing-a-version.md",
      "guides/the-statusline.md",
      "guides/troubleshooting.md",
      "guides/uninstalling.md",
    ];
    const failures = operationalRoutes.flatMap((route) => {
      const body = readFileSync(join(docsRoot, route), "utf8");
      const hasVerification = /verify|proof|healthy|completion/i.test(body);
      const hasRecovery = /common stops|failure|fails|recovery|troubleshoot|clean up|turn it back off|unparseable|symptom|resume|interrupted|absent|malformed/i.test(body);
      return hasVerification && hasRecovery ? [] : [
        `${route}: ${!hasVerification ? "missing verification" : "missing recovery"}`,
      ];
    });
    expect(failures).toEqual([]);
  });

  it("keeps the Learning Path and Academy reciprocal without inventing progress state", () => {
    const learningPath = readFileSync(join(docsRoot, "learn", "index.mdx"), "utf8");
    const academy = readFileSync(academyOverview, "utf8");

    expect(learningPath).toContain('href={`${base}academy/`}');
    expect(learningPath).toContain("guided documentation");
    expect(learningPath).toContain("verifier-backed practice");
    expect(academy).toContain('href={`${basePath}/learn/`}');
    expect(academy).toContain("guided documentation");
    expect(academy).toContain("verifier-backed practice");
    for (const source of [learningPath, academy]) {
      expect(source).toContain("does not create an account, import progress, or store completion state");
    }
  });
});
