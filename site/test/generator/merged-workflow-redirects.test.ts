/** merged-workflow-redirects.test.ts — the old skill URLs of merged workflows keep working (AC-02).
 *
 * A command whose shipped source names its owning skill is one page, so that
 * skill's own `/reference/skills/<name>/` page is gone. Every one of those URLs
 * must still land on the command page, in one hop, with the site base applied
 * the way the older `-2` redirects apply it. The redirect map is derived from
 * the shipped sources; nothing here, and nothing in the config, lists a pair.
 *
 * The expected pairs come from an oracle that does not use the derivation
 * under test: the first heading of each shipped command source, read from disk.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generate } from "../../scripts/generator/generate";
import type { GenerateResult, WorkflowPair } from "../../scripts/generator/types";
import {
  LEGACY_SECOND_SLUG_SKILLS,
  legacySecondSlugRedirects,
  mergedSkillRedirects,
} from "../../scripts/generator/workflow-pairs";
// astro.config.mjs is plain JS outside the tsconfig program; the shape asserted
// on here is checked at runtime instead.
// @ts-expect-error -- untyped .mjs config module
import config, { BASE } from "../../astro.config.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(here, "../..");
const pluginDir = resolve(siteRoot, "..", "plugins", "ca");

type CatalogJson = { commands: Record<string, { visibility: string }> };
const catalog = JSON.parse(
  readFileSync(join(pluginDir, "generated", "command-catalog.json"), "utf8"),
) as CatalogJson;
const skillNames = readdirSync(join(pluginDir, "skills"), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);

/** Oracle: a non-alias command whose first heading is a shipped skill's name is a merged pair. */
function mergedPairsFromDisk(): Array<{ command: string; skill: string }> {
  const pairs: Array<{ command: string; skill: string }> = [];
  for (const file of readdirSync(join(pluginDir, "commands")).filter((f) => f.endsWith(".md")).sort()) {
    const command = file.replace(/\.md$/, "");
    const heading = readFileSync(join(pluginDir, "commands", file), "utf8")
      .replace(/\r\n/g, "\n")
      .match(/^# (.+)$/m)?.[1]
      .trim();
    if (heading && skillNames.includes(heading) && catalog.commands[command].visibility !== "alias") {
      pairs.push({ command, skill: heading });
    }
  }
  return pairs;
}

const merged = mergedPairsFromDisk();
const redirects = config.redirects as Record<string, string>;
const skillUrl = (skill: string) => `/reference/skills/${skill}`;
const commandUrl = (command: string) => `/reference/commands/${command}`;
const LEGACY_SECOND_SLUG_KEYS = ["context-check", "debug", "decompose", "refactor", "release", "tribunal"]
  .map((skill) => skillUrl(`${skill}-2`));

describe("redirects for merged workflow skills (astro.config.mjs)", () => {
  it("finds the 9 merged workflows the oracle expects, so no loop below runs empty", () => {
    expect(merged.map(({ command }) => command)).toEqual([
      "adr", "commit", "debug", "pr", "reconcile", "refactor", "release", "threat-model", "tribunal",
    ]);
  });

  it("redirects exactly the merged skills, plus the historical -2 URLs, under /reference/skills", () => {
    const expected = [...merged.map(({ skill }) => skillUrl(skill)), ...LEGACY_SECOND_SLUG_KEYS].sort();
    const actual = Object.keys(redirects).filter((key) => key.startsWith("/reference/skills/")).sort();
    expect(actual).toEqual(expected);
  });

  it("sends each merged skill URL to its command page with the base applied", () => {
    for (const { command, skill } of merged) {
      expect(redirects[skillUrl(skill)], skillUrl(skill)).toBe(`${BASE}${commandUrl(command)}`);
    }
    expect(redirects["/reference/skills/commit-gate"]).toBe(`${BASE}/reference/commands/commit`);
  });

  it("keeps skill pages that still exist out of the map: alias-owning and internal-only skills", () => {
    for (const keep of ["decompose", "context-check", "context-creation", "post-merge-cleanup", "tdd", "brainstorming"]) {
      expect(redirects[skillUrl(keep)], skillUrl(keep)).toBeUndefined();
    }
  });

  it("points the -2 URLs of merged skills straight at their command pages", () => {
    for (const skill of ["debug", "refactor", "release", "tribunal"]) {
      expect(redirects[skillUrl(`${skill}-2`)], skillUrl(`${skill}-2`)).toBe(`${BASE}${commandUrl(skill)}`);
    }
  });

  it("leaves the -2 URLs of alias-owning skills on their skill pages", () => {
    expect(redirects[skillUrl("context-check-2")]).toBe(`${BASE}${skillUrl("context-check")}`);
    expect(redirects[skillUrl("decompose-2")]).toBe(`${BASE}${skillUrl("decompose")}`);
  });

  it("never sends a redirect to another redirect", () => {
    const sources = new Set(Object.keys(redirects));
    for (const [source, destination] of Object.entries(redirects)) {
      const path = destination.slice(BASE.length).replace(/\/$/, "");
      expect(sources.has(path), `${source} -> ${destination} is a second hop`).toBe(false);
    }
  });

  it("does not hand-list a merged skill in the config source", () => {
    const configSource = readFileSync(join(siteRoot, "astro.config.mjs"), "utf8");
    for (const { skill } of merged) {
      expect(configSource.includes(skillUrl(skill)), `astro.config.mjs spells ${skillUrl(skill)}`).toBe(false);
    }
  });
});

describe("redirect destinations against the generated pages", () => {
  const outDir = mkdtempSync(join(tmpdir(), "ca-merged-redirects-"));
  let result: GenerateResult;
  beforeAll(() => {
    result = generate(pluginDir, outDir, undefined, undefined, true);
  });
  afterAll(() => rmSync(outDir, { recursive: true, force: true }));

  const pageUrls = () => new Set(result.pages.map((page) => `/reference/${page.type}s/${page.slug}`));

  it("redirects from URLs that have no page and to URLs that do", () => {
    const urls = pageUrls();
    expect(urls.size).toBeGreaterThan(50);
    for (const [source, destination] of Object.entries(redirects)) {
      if (!source.startsWith("/reference/skills/")) continue;
      expect(urls.has(source), `${source} still has a generated page`).toBe(false);
      expect(urls.has(destination.slice(BASE.length)), `${source} -> ${destination} has no page`).toBe(true);
    }
  });

  it("derives the same merged pairs as the page generator", () => {
    const fromGenerator = result.workflowPairs
      .filter((pair) => pair.mode === "merge")
      .map(({ command, skill }) => ({ command, skill }));
    expect(fromGenerator).toEqual(merged);
    expect(Object.keys(mergedSkillRedirects(result.workflowPairs, BASE)).sort())
      .toEqual(merged.map(({ skill }) => skillUrl(skill)).sort());
  });
});

describe("redirect builders", () => {
  const pairs: WorkflowPair[] = [
    { command: "ship", skill: "ship-flow", mode: "merge", visibility: "core" },
    { command: "tidy", skill: "tidy-flow", mode: "alias", visibility: "alias", canonical: "ship", replacement: "ship --tidy" },
  ];

  it("prefixes only the destination with the base, as the older entries do", () => {
    expect(mergedSkillRedirects(pairs, "/sub")).toEqual({
      "/reference/skills/ship-flow": "/sub/reference/commands/ship",
    });
    expect(mergedSkillRedirects(pairs, "")).toEqual({
      "/reference/skills/ship-flow": "/reference/commands/ship",
    });
  });

  it("builds an empty map for no pairs and ignores alias pairs", () => {
    expect(mergedSkillRedirects([], "/sub")).toEqual({});
    expect(mergedSkillRedirects(pairs.slice(1), "/sub")).toEqual({});
  });

  it("resolves a -2 URL to the command page when merged and to the skill page otherwise", () => {
    const redirectsFor = legacySecondSlugRedirects(
      ["ship-flow", "tidy-flow"],
      pairs,
      "/sub",
    );
    expect(redirectsFor).toEqual({
      "/reference/skills/ship-flow-2": "/sub/reference/commands/ship",
      "/reference/skills/tidy-flow-2": "/sub/reference/skills/tidy-flow",
    });
  });

  it("names the six skills that once shared a name with a command", () => {
    expect([...LEGACY_SECOND_SLUG_SKILLS]).toEqual([
      "context-check", "debug", "decompose", "refactor", "release", "tribunal",
    ]);
  });
});
