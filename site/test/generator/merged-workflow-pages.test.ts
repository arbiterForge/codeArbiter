import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generate } from "../../scripts/generator/generate";
import type { GenerateResult } from "../../scripts/generator/types";
import { claimedSkill, firstHeading } from "../../scripts/generator/workflow-pairs";
import { buildPlugin, cleanupFixtures, tempDir, writeCurated } from "./plugin-fixture";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const pluginDir = join(repoRoot, "plugins", "ca");

afterEach(cleanupFixtures);

const SOURCE_EMBED = /<details class="ca-source"/g;

/** The single source-embed block of a page, from its opening tag to its closing tag. */
function embedBlock(markdown: string): string {
  const start = markdown.indexOf('<details class="ca-source"');
  const end = markdown.indexOf("</details>", start);
  expect(start, "page has a source embed").toBeGreaterThanOrEqual(0);
  return markdown.slice(start, end);
}

// ---------------------------------------------------------------------------
// Production sources. Curated text is left out on purpose: pairing, page counts
// and the source layer come from the shipped plugin and its catalog alone.
// ---------------------------------------------------------------------------

type CatalogJson = { commands: Record<string, { visibility: string; canonical?: string }> };
const catalog = JSON.parse(
  readFileSync(join(pluginDir, "generated", "command-catalog.json"), "utf8"),
) as CatalogJson;

const commandNames = readdirSync(join(pluginDir, "commands"))
  .filter((file) => file.endsWith(".md"))
  .map((file) => file.replace(/\.md$/, ""))
  .sort();
const skillNames = readdirSync(join(pluginDir, "skills"), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

/** Independent oracle: a command pairs with a skill when its first heading names a shipped skill. */
function pairsFromDisk(): Array<{ command: string; skill: string; mode: string }> {
  const pairs: Array<{ command: string; skill: string; mode: string }> = [];
  for (const command of commandNames) {
    const raw = readFileSync(join(pluginDir, "commands", `${command}.md`), "utf8").replace(/\r\n/g, "\n");
    const heading = raw.match(/^# (.+)$/m)?.[1].trim();
    if (heading && skillNames.includes(heading)) {
      pairs.push({
        command,
        skill: heading,
        mode: catalog.commands[command].visibility === "alias" ? "alias" : "merge",
      });
    }
  }
  return pairs;
}

describe("one reference page per paired workflow (production sources)", () => {
  // One generation shared by the whole block; the per-test fixture cleanup must not delete it.
  const outDir = mkdtempSync(join(tmpdir(), "ca-merged-pages-"));
  let result: GenerateResult;
  beforeAll(() => {
    result = generate(pluginDir, outDir, undefined, undefined, true);
  });
  afterAll(() => rmSync(outDir, { recursive: true, force: true }));

  const pairs = pairsFromDisk();
  const merged = pairs.filter((pair) => pair.mode === "merge");
  const aliases = pairs.filter((pair) => pair.mode === "alias");
  const commandPage = (name: string) => result.pages.find((p) => p.type === "command" && p.slug === name)!;

  it("derives the pairs from the shipped sources: 9 merged and 4 alias", () => {
    expect(result.workflowPairs.map(({ command, skill, mode }) => ({ command, skill, mode })))
      .toEqual(pairs);
    // A derivation that finds nothing would pass every per-pair loop below.
    expect(merged).toHaveLength(9);
    expect(aliases).toHaveLength(4);
    expect(merged.every((pair) => ["core", "advanced"].includes(catalog.commands[pair.command].visibility)))
      .toBe(true);
    expect(aliases.map((pair) => pair.command).sort())
      .toEqual(["cleanup", "context-check", "create-context", "decompose"]);
  });

  it("emits one page per command", () => {
    const commandPages = result.pages.filter((page) => page.type === "command");
    expect(commandPages).toHaveLength(commandNames.length);
    expect(readdirSync(join(outDir, "commands"))).toHaveLength(commandNames.length);
  });

  it.each(merged)("gives merged command $command exactly one source embed holding both shipped files", ({ command, skill }) => {
    const markdown = commandPage(command).markdown;
    expect(markdown.match(SOURCE_EMBED)).toHaveLength(1);

    const commandRel = `plugins/ca/commands/${command}.md`;
    const skillRel = `plugins/ca/skills/${skill}/SKILL.md`;
    const block = embedBlock(markdown);
    expect(block).toContain(`<code>${commandRel}</code>`);
    expect(block).toContain(`<code>${skillRel}</code>`);
    expect(block.indexOf(commandRel)).toBeLessThan(block.indexOf(skillRel));
    // Both shipped files appear verbatim, command first.
    const commandRaw = readFileSync(join(pluginDir, "commands", `${command}.md`), "utf8");
    const skillRaw = readFileSync(join(pluginDir, "skills", skill, "SKILL.md"), "utf8");
    expect(block).toContain(commandRaw);
    expect(block).toContain(skillRaw);
    expect(block.indexOf(commandRaw)).toBeLessThan(block.indexOf(skillRaw));
    expect(block).toContain("data-pagefind-ignore");
  });

  it("emits no page for the skills merged into a command", () => {
    const skillSlugs = result.pages.filter((page) => page.type === "skill").map((page) => page.slug);
    for (const { skill } of merged) {
      expect(skillSlugs, skill).not.toContain(skill);
      expect(existsSync(join(outDir, "skills", `${skill}.md`)), skill).toBe(false);
    }
    expect(skillSlugs).toHaveLength(skillNames.length - merged.length);
    expect(readdirSync(join(outDir, "skills"))).toHaveLength(skillNames.length - merged.length);
  });

  it("keeps a page for every alias-owning and internal-only skill", () => {
    const mergedSkills = new Set(merged.map((pair) => pair.skill));
    for (const skill of skillNames.filter((name) => !mergedSkills.has(name))) {
      expect(existsSync(join(outDir, "skills", `${skill}.md`)), skill).toBe(true);
    }
    for (const { skill } of aliases) {
      expect(existsSync(join(outDir, "skills", `${skill}.md`)), skill).toBe(true);
    }
  });

  it.each(aliases)("points alias $command at its replacement command and its skill page", ({ command, skill }) => {
    const markdown = commandPage(command).markdown;
    const canonical = catalog.commands[command].canonical!;
    expect(markdown).toContain("## Compatibility");
    expect(markdown).toContain(`](/reference/commands/${canonical}/)`);
    expect(markdown).toContain(`](/reference/skills/${skill}/)`);
    // The alias keeps its own source layer, and only its own file.
    expect(markdown.match(SOURCE_EMBED)).toHaveLength(1);
    const block = embedBlock(markdown);
    expect(block).toContain(`plugins/ca/commands/${command}.md`);
    expect(block).not.toContain(`plugins/ca/skills/${skill}/SKILL.md`);
  });

  it("leaves the unpaired watch alias and non-paired commands untouched", () => {
    const watch = commandPage("watch").markdown;
    expect(watch).toContain("## Compatibility");
    expect(watch).not.toContain("](/reference/skills/");
    expect(commandPage("sprint").markdown.match(SOURCE_EMBED)).toHaveLength(1);
    expect(commandPage("sprint").markdown).not.toContain("How it runs");
  });

  it("gives every skill page exactly one source embed", () => {
    for (const page of result.pages.filter((p) => p.type === "skill")) {
      expect(page.markdown.match(SOURCE_EMBED), page.slug).toHaveLength(1);
    }
  });
});

// ---------------------------------------------------------------------------
// Synthetic plugin trees: reader text, related links, and the two failures.
// ---------------------------------------------------------------------------

// Core commands must carry the reader fields and an Example (see load-curated.ts).
const READER_FRONTMATTER = ["use_when: u", "avoid_when: a", "asks: q", "produces: p"];
const EXAMPLE_SECTION = ["## Example", "", "```text", "/ca:ship", "```", ""];

describe("workflow pairing on synthetic plugins", () => {
  function pairedPlugin(): string {
    return buildPlugin(
      [
        { name: "ship", heading: "release-flow", visibility: "core", legacyRoutes: ["tidy"] },
        { name: "tidy", heading: "tidy-up", visibility: "alias", canonical: "ship", replacement: "ship --tidy" },
        { name: "other", heading: "/ca:other — an unpaired command", visibility: "core" },
      ],
      ["release-flow", "tidy-up", "loner"],
    );
  }

  it("merges the skill's curated text, gates, related links and source into the command page", () => {
    const plugin = pairedPlugin();
    const curated = tempDir("ca-merged-curated-");
    writeCurated(curated, "commands/ship.md", [
      "---",
      "entity: commands/ship",
      "related: [skills/release-flow, other]",
      ...READER_FRONTMATTER,
      "gates:",
      "  - gate: command gate",
      "    when: the command starts",
      "    effect: it asks first",
      "---",
      "",
      "## What it does",
      "",
      "Command text.",
      "",
      ...EXAMPLE_SECTION,
    ].join("\n"));
    writeCurated(curated, "skills/release-flow.md", [
      "---",
      "entity: skills/release-flow",
      "related: [loner, commands/other]",
      "gates:",
      "  - gate: skill gate",
      "    when: the skill runs",
      "    effect: it stops",
      "---",
      "",
      "## What it does",
      "",
      "Skill text.",
      "",
      "```sh",
      "# a comment, not a heading",
      "```",
      "",
    ].join("\n"));
    writeCurated(curated, "commands/other.md", [
      "---",
      "entity: commands/other",
      "related: [skills/release-flow]",
      ...READER_FRONTMATTER,
      "---",
      "",
      "Other text.",
      "",
      ...EXAMPLE_SECTION,
    ].join("\n"));

    const outDir = tempDir("ca-merged-out-");
    const result = generate(plugin, outDir, undefined, curated);
    const ship = result.pages.find((p) => p.type === "command" && p.slug === "ship")!.markdown;

    // Command text, then "How it runs" with the skill's headings nested one level down.
    expect(ship.indexOf("Command text.")).toBeLessThan(ship.indexOf("## How it runs"));
    expect(ship.indexOf("## How it runs")).toBeLessThan(ship.indexOf("Skill text."));
    expect(ship).toContain("### What it does");
    expect(ship).toContain("\n# a comment, not a heading\n");
    expect(ship).not.toContain("## a comment, not a heading");

    // One gates table, command gate first.
    expect(ship.match(/^## Gates$/gm)).toHaveLength(1);
    expect(ship.indexOf("command gate")).toBeLessThan(ship.indexOf("skill gate"));

    // Related: both halves, no link to itself, none to the unpublished skill URL.
    const related = ship.slice(ship.indexOf("## Related"), ship.indexOf("## Route context"));
    expect(related).toContain("](/reference/commands/other/)");
    expect(related).toContain("](/reference/skills/loner/)");
    expect(related).not.toContain("/reference/commands/ship/");
    expect(related).not.toContain("/reference/skills/release-flow/");
    expect(related.match(/\(\/reference\/commands\/other\/\)/g)).toHaveLength(1);

    // One embed, both files, command first.
    expect(ship.match(SOURCE_EMBED)).toHaveLength(1);
    const block = embedBlock(ship);
    expect(block.indexOf("plugins/ca/commands/ship.md")).toBeGreaterThanOrEqual(0);
    expect(block.indexOf("plugins/ca/commands/ship.md")).toBeLessThan(
      block.indexOf("plugins/ca/skills/release-flow/SKILL.md"),
    );

    // No page for the merged skill, and a page that related to it now lands on the command.
    expect(existsSync(join(outDir, "skills", "release-flow.md"))).toBe(false);
    expect(existsSync(join(outDir, "skills", "loner.md"))).toBe(true);
    const other = result.pages.find((p) => p.type === "command" && p.slug === "other")!.markdown;
    expect(other).toContain("](/reference/commands/ship/)");
    expect(other).not.toContain("/reference/skills/release-flow/");
  });

  it("renders a merged page without a How it runs section when the skill has no curated text", () => {
    const plugin = pairedPlugin();
    const outDir = tempDir("ca-merged-out-");
    const result = generate(plugin, outDir);
    const ship = result.pages.find((p) => p.type === "command" && p.slug === "ship")!.markdown;
    expect(ship).not.toContain("## How it runs");
    expect(ship.match(SOURCE_EMBED)).toHaveLength(1);
    expect(embedBlock(ship)).toContain("plugins/ca/skills/release-flow/SKILL.md");
  });

  it("keeps the skill page as the workflow page for an alias and points the alias at it", () => {
    const plugin = pairedPlugin();
    const outDir = tempDir("ca-merged-out-");
    const result = generate(plugin, outDir);
    expect(result.workflowPairs.map((pair) => [pair.command, pair.skill, pair.mode])).toEqual([
      ["ship", "release-flow", "merge"],
      ["tidy", "tidy-up", "alias"],
    ]);
    const tidy = result.pages.find((p) => p.type === "command" && p.slug === "tidy")!.markdown;
    expect(tidy).toContain("Use `ship --tidy` for new work.");
    expect(tidy).toContain("[ship command page](/reference/commands/ship/)");
    expect(tidy).toContain("[tidy-up skill page](/reference/skills/tidy-up/)");
    expect(existsSync(join(outDir, "skills", "tidy-up.md"))).toBe(true);
    expect(existsSync(join(outDir, "skills", "release-flow.md"))).toBe(false);
    // A `/ca:` heading is not a claim on a skill.
    expect(result.pages.find((p) => p.type === "command" && p.slug === "other")!.markdown)
      .not.toContain("How it runs");
  });

  it("fails generation when a command source names a skill that is not shipped", () => {
    const plugin = buildPlugin(
      [{ name: "ship", heading: "ghost-skill" }],
      ["release-flow"],
    );
    expect(() => generate(plugin, tempDir("ca-merged-out-"))).toThrow(
      /commands\/ship\.md names owning skill "ghost-skill".*no skills\/ghost-skill\/ is shipped/,
    );
  });

  it("fails generation when two commands name the same skill, listing both", () => {
    const plugin = buildPlugin(
      [
        { name: "ship", heading: "release-flow" },
        { name: "send", heading: "release-flow" },
      ],
      ["release-flow"],
    );
    expect(() => generate(plugin, tempDir("ca-merged-out-"))).toThrow(
      /skill "release-flow" is named as owner by 2 commands: commands\/send\.md, commands\/ship\.md/,
    );
  });

  it("reports every unknown and duplicated owner in one error", () => {
    const plugin = buildPlugin(
      [
        { name: "a", heading: "ghost-one" },
        { name: "b", heading: "ghost-two" },
        { name: "c", heading: "release-flow" },
        { name: "d", heading: "release-flow" },
      ],
      ["release-flow"],
    );
    let message = "";
    try {
      generate(plugin, tempDir("ca-merged-out-"));
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("ghost-one");
    expect(message).toContain("ghost-two");
    expect(message).toContain("named as owner by 2 commands");
  });

  it("fails generation when a command names a skill but no catalog supplies its visibility", () => {
    const plugin = buildPlugin([{ name: "ship", heading: "release-flow" }], ["release-flow"], false);
    expect(() => generate(plugin, tempDir("ca-merged-out-"))).toThrow(/no generated command catalog/);
  });

  it("pairs nothing when no command names a skill", () => {
    const plugin = buildPlugin(
      [{ name: "ship", heading: "/ca:ship — ship it" }],
      ["release-flow"],
    );
    const outDir = tempDir("ca-merged-out-");
    const result = generate(plugin, outDir);
    expect(result.workflowPairs).toEqual([]);
    expect(existsSync(join(outDir, "skills", "release-flow.md"))).toBe(true);
  });
});

describe("owning-skill claim", () => {
  it("reads a bare identifier heading as a claim and a /ca: heading as none", () => {
    expect(claimedSkill("---\ndescription: x\n---\n\n# decision-lifecycle\n\nBody\n")).toBe("decision-lifecycle");
    expect(claimedSkill("# /ca:adr-status — read-only mode adapter\n")).toBeUndefined();
    expect(claimedSkill("# Release Flow\n")).toBeUndefined();
    expect(claimedSkill("no heading at all\n")).toBeUndefined();
  });

  it("skips frontmatter and fenced code when looking for the first heading", () => {
    const raw = "---\n# not-a-heading: frontmatter\n---\n\n```sh\n# a-shell-comment\n```\n\n# real-heading\n";
    expect(firstHeading(raw)).toBe("real-heading");
    expect(claimedSkill(raw)).toBe("real-heading");
  });

  it("ignores deeper headings", () => {
    expect(firstHeading("## second-level\n\n# first-level\n")).toBe("first-level");
  });
});
