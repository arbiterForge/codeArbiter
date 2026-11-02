/** curated-drift.test.ts — hand-written reference text cannot name what the source dropped (AC-04).
 *
 * Curated pages are prose about shipped commands. When a command loses a flag, or
 * a command is renamed, the prose keeps saying the old thing unless something
 * compares them. The drift check attributes every `--flag` in curated text to a
 * codeArbiter command and looks for it in that command's shipped source, and it
 * looks up every `/ca:<name>` in the command catalog. These cases use fixture
 * sources, so each rule is pinned on its own; the last block runs the real set.
 */
import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generate } from "../../scripts/generator/generate";
import {
  assertNoCuratedDrift,
  findCuratedDrift,
  ownCommandOf,
  type CuratedDriftFile,
  type DriftMiss,
} from "../../scripts/generator/curated-drift";
import { buildPlugin, cleanupFixtures, tempDir, writeCurated } from "./plugin-fixture";

afterEach(cleanupFixtures);

const here = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(here, "../..");
const repoRoot = resolve(siteRoot, "..");

/** The catalog: every command a curated page may name. */
const commands = new Set(["commit", "pr", "init", "status", "cleanup", "adr", "adr-status"]);

/** What each command's shipped source says (command file plus its paired skill). */
const sources = new Map<string, string>([
  ["commit", "# commit-gate\nRuns the gate. Accepts --scope and --no-edit.\n"],
  ["pr", 'argument-hint: ["title"] | --watch [PR] | --cleanup\n'],
  ["init", "/ca:init [--stage N | --check | --format markdown]\n"],
  ["status", "argument-hint: (none) | drift\nAlso --since-checkpoint.\n"],
  ["cleanup", "# post-merge-cleanup\nTakes no arguments. Prefer /ca:pr --cleanup.\n"],
  ["adr", "# decision-lifecycle\nRecords a decision. --yes skips nothing.\n"],
  ["adr-status", "Read-only. --adr N narrows the scan.\n"],
]);

const text = (...lines: string[]) => lines.join("\n") + "\n";
const file = (path: string, raw: string, ownCommand?: string): CuratedDriftFile => ({ path, raw, ownCommand });
const drift = (...files: CuratedDriftFile[]): DriftMiss[] => findCuratedDrift({ files, commands, sources });
const flagMiss = (path: string, line: number, token: string, command: string): DriftMiss =>
  ({ file: path, line, kind: "flag", token, command });
const commandMiss = (path: string, line: number, token: string): DriftMiss =>
  ({ file: path, line, kind: "command", token });

describe("flags are checked against the command's shipped source", () => {
  it("reports a /ca: flag that the command source does not have", () => {
    const page = file("commands/commit.md", text("---", "entity: commands/commit", "---", "", "Run `/ca:commit --amend` to rewrite."));
    expect(drift(page)).toEqual([flagMiss("commands/commit.md", 5, "--amend", "commit")]);
  });

  it("accepts a flag the command source has, in prose and in a code block", () => {
    const page = file("commands/commit.md", text(
      "Use `/ca:commit --scope api` for one area.",
      "",
      "```",
      "/ca:commit --no-edit",
      "```",
    ));
    expect(drift(page)).toEqual([]);
  });

  it("does not take a flag whose name merely starts like a source flag", () => {
    const page = file("commands/status.md", text("`/ca:status --since` shows recent changes."));
    expect(drift(page)).toEqual([flagMiss("commands/status.md", 1, "--since", "status")]);
  });

  it("does not take a flag that merely contains a source flag", () => {
    const page = file("commands/status.md", text("`/ca:status --since-checkpoint-extra` is not a flag."));
    expect(drift(page)).toEqual([flagMiss("commands/status.md", 1, "--since-checkpoint-extra", "status")]);
  });

  it("reads the flag name when it carries a value", () => {
    const page = file("commands/commit.md", text("`/ca:commit --scope=api` and `/ca:commit --nope=1`."));
    expect(drift(page)).toEqual([flagMiss("commands/commit.md", 1, "--nope", "commit")]);
  });

  it("checks frontmatter text, because reader fields are shown on the page", () => {
    const page = file("commands/commit.md", text(
      "---",
      "entity: commands/commit",
      'avoid_when: "Instead use `/ca:commit --force`."',
      "---",
    ));
    expect(drift(page)).toEqual([flagMiss("commands/commit.md", 3, "--force", "commit")]);
  });

  it("gives the same answer for CRLF text and LF text", () => {
    const lf = "Run `/ca:commit --amend`.\nThen `/ca:nothing`.\n";
    expect(drift(file("a.md", lf.replace(/\n/g, "\r\n")))).toEqual(drift(file("a.md", lf)));
    expect(drift(file("a.md", lf))).toHaveLength(2);
  });
});

describe("attribution", () => {
  it("attributes a flag to the nearest preceding command on its line", () => {
    // --cleanup belongs to pr (it has it); --check belongs to init (it has it).
    expect(drift(file("a.md", text("`/ca:pr --cleanup`, then `/ca:init --check`.")))).toEqual([]);
    // Reversed, each flag lands on a command that lacks it.
    expect(drift(file("a.md", text("`/ca:init --cleanup`, then `/ca:pr --check`.")))).toEqual([
      flagMiss("a.md", 1, "--cleanup", "init"),
      flagMiss("a.md", 1, "--check", "pr"),
    ]);
  });

  it("follows a compatibility route to its replacement: /ca:pr --cleanup on the cleanup page", () => {
    // The cleanup source has no such flag of its own; the replacement command does.
    const page = file("skills/post-merge-cleanup.md", text("Prefer `/ca:pr --cleanup` for new use."), "cleanup");
    expect(drift(page)).toEqual([]);
    const bad = file("skills/post-merge-cleanup.md", text("Prefer `/ca:pr --cleaning` for new use."), "cleanup");
    expect(drift(bad)).toEqual([flagMiss("skills/post-merge-cleanup.md", 1, "--cleaning", "pr")]);
  });

  it("carries a command down its code block to flags on later lines", () => {
    const page = file("a.md", text("```", "/ca:commit", "  --scope api", "  --amend", "```"));
    expect(drift(page)).toEqual([flagMiss("a.md", 4, "--amend", "commit")]);
  });

  it("ends the carry at the end of the block", () => {
    const page = file("a.md", text("```", "/ca:commit", "```", "", "```", "--amend", "```", "", "plain --amend text"));
    expect(drift(page)).toEqual([]);
  });

  it("does not carry a command across prose lines", () => {
    const page = file("a.md", text("Run `/ca:commit`.", "It also accepts --amend somewhere else."));
    expect(drift(page)).toEqual([]);
  });

  it("does not read a flag out of a word joined by dashes, or out of a rule", () => {
    expect(drift(file("a.md", text("`/ca:commit` is a--amend-free zone", "---")))).toEqual([]);
  });

  it("leaves a flag with no command in reach alone", () => {
    expect(drift(file("a.md", text("Pass `--whatever` to the hook.", "```", "--also-this", "```")))).toEqual([]);
  });
});

describe("the Usage block", () => {
  const usage = (...body: string[]) => text("## Usage", "", "```", ...body, "```");

  it("attributes a flag in the Usage block to the page's own command", () => {
    const page = file("commands/commit.md", usage("[--scope X] [--amend]"), "commit");
    expect(drift(page)).toEqual([flagMiss("commands/commit.md", 4, "--amend", "commit")]);
  });

  it("does not attribute a flag in a code block outside Usage to the page's command", () => {
    const page = file("commands/commit.md", text("## Example", "", "```", "[--amend]", "```"), "commit");
    expect(drift(page)).toEqual([]);
  });

  it("prefers a command named on the same line over the page's own command", () => {
    const page = file("commands/commit.md", usage("/ca:pr --watch"), "commit");
    expect(drift(page)).toEqual([]);
  });

  it("does not check prose in the Usage section, so a correct negation can say what is absent", () => {
    const page = file("commands/commit.md", text(
      "## Usage",
      "",
      "```",
      "/ca:commit --scope api",
      "```",
      "",
      "There is no `--auto`.",
    ), "commit");
    expect(drift(page)).toEqual([]);
  });

  it("applies to a skill page through its paired command", () => {
    const page = file("skills/commit-gate.md", usage("--amend"), ownCommandOf("skills/commit-gate", new Map([["commit-gate", "commit"]])));
    expect(drift(page)).toEqual([flagMiss("skills/commit-gate.md", 4, "--amend", "commit")]);
  });

  it("checks nothing for a page that has no command of its own", () => {
    expect(drift(file("skills/tdd.md", usage("--amend")))).toEqual([]);
  });

  it("ends at the next heading of the same level", () => {
    const page = file("commands/commit.md", text("## Usage", "", "```", "--scope", "```", "", "## Example", "", "```", "--amend", "```"), "commit");
    expect(drift(page)).toEqual([]);
  });
});

describe("flags of other tools", () => {
  it("ignores a git flag and an npm flag after a command on the same line", () => {
    const page = file("a.md", text(
      "Run `/ca:commit`, then `git push --force-with-lease` and `npm run build --silent`.",
    ));
    expect(drift(page)).toEqual([]);
  });

  it("ignores them on later lines of the command's code block", () => {
    const page = file("a.md", text(
      "```",
      "/ca:commit --scope api",
      "git push --force-with-lease",
      "npm run build --silent",
      "```",
    ));
    expect(drift(page)).toEqual([]);
  });

  it("ignores them inside the Usage block", () => {
    const page = file("commands/commit.md", text("## Usage", "", "```", "git log --oneline", "npm test --coverage", "```"), "commit");
    expect(drift(page)).toEqual([]);
  });

  it("still checks a codeArbiter flag that follows a foreign one", () => {
    const page = file("a.md", text("```", "git push --force-with-lease && /ca:commit --amend", "```"));
    expect(drift(page)).toEqual([flagMiss("a.md", 2, "--amend", "commit")]);
  });

  it("still checks a codeArbiter flag on a line where a foreign tool is only mentioned earlier", () => {
    const page = file("a.md", text("After `git status`, run `/ca:commit --amend`."));
    expect(drift(page)).toEqual([flagMiss("a.md", 1, "--amend", "commit")]);
  });
});

describe("commands are checked against the catalog", () => {
  it("reports a /ca: command that is not in the catalog", () => {
    const page = file("a.md", text("", "Use `/ca:frobnicate` for that."));
    expect(drift(page)).toEqual([commandMiss("a.md", 2, "frobnicate")]);
  });

  it("does not confuse a command with a longer one that starts with its name", () => {
    expect(drift(file("a.md", text("`/ca:adr` and `/ca:adr-status`.")))).toEqual([]);
    expect(drift(file("a.md", text("`/ca:adr-statuz`.")))).toEqual([commandMiss("a.md", 1, "adr-statuz")]);
  });

  it("does not check the flags of an unknown command", () => {
    expect(drift(file("a.md", text("`/ca:frobnicate --anything`.")))).toEqual([commandMiss("a.md", 1, "frobnicate")]);
  });

  it("ignores a placeholder or a bare prefix that names no command", () => {
    expect(drift(file("a.md", text("`/ca:<command>` and the `/ca:` prefix.")))).toEqual([]);
  });

  it("finds a command named in frontmatter", () => {
    const page = file("a.md", text("---", 'avoid_when: "Use `/ca:gone` instead."', "---"));
    expect(drift(page)).toEqual([commandMiss("a.md", 2, "gone")]);
  });
});

describe("ownCommandOf", () => {
  const skillCommand = new Map([["commit-gate", "commit"], ["post-merge-cleanup", "cleanup"]]);
  it("is the command itself for a command page", () => {
    expect(ownCommandOf("commands/pr", skillCommand)).toBe("pr");
  });
  it("is the paired command for a skill page that has one", () => {
    expect(ownCommandOf("skills/commit-gate", skillCommand)).toBe("commit");
    expect(ownCommandOf("skills/post-merge-cleanup", skillCommand)).toBe("cleanup");
  });
  it("is nothing for an internal-only skill or an agent", () => {
    expect(ownCommandOf("skills/tdd", skillCommand)).toBeUndefined();
    expect(ownCommandOf("agents/scout", skillCommand)).toBeUndefined();
  });
});

describe("reporting", () => {
  const bad = [
    file("curated/commands/commit.md", text("Run `/ca:commit --amend`.")),
    file("curated/commands/pr.md", text("", "Run `/ca:pr --draft`, then `/ca:gone`.")),
  ];

  it("lists every miss in one error, naming each file, line and flag", () => {
    let message = "";
    try {
      assertNoCuratedDrift({ files: bad, commands, sources });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("3 problems");
    expect(message).toContain("curated/commands/commit.md:1");
    expect(message).toContain("--amend");
    expect(message).toContain("curated/commands/pr.md:2");
    expect(message).toContain("--draft");
    expect(message).toContain("/ca:gone");
  });

  it("passes silently when nothing drifted", () => {
    expect(() => assertNoCuratedDrift({ files: [], commands, sources })).not.toThrow();
    expect(() =>
      assertNoCuratedDrift({ files: [file("a.md", text("`/ca:commit --scope x`"))], commands, sources }),
    ).not.toThrow();
  });

  it("reports in file order, then line order", () => {
    const misses = drift(...bad);
    expect(misses.map((miss) => `${miss.file}:${miss.line}:${miss.token}`)).toEqual([
      "curated/commands/commit.md:1:--amend",
      "curated/commands/pr.md:2:--draft",
      "curated/commands/pr.md:2:gone",
    ]);
  });
});

describe("generate() runs the check", () => {
  const shipPage = (line: string) =>
    text(
      "---",
      "entity: commands/ship",
      'use_when: "you ship"',
      'avoid_when: "never"',
      'asks: "nothing"',
      'produces: "a shipment"',
      "---",
      "",
      line,
      "",
      "## Example",
      "",
      "```text",
      "/ca:ship",
      "```",
    );
  const unpairedPlugin = () => buildPlugin([{ name: "ship", heading: "/ca:ship — ship it" }], [], true);

  it("fails generation, listing every miss with its file and flag", () => {
    const curated = tempDir("ca-drift-curated-");
    writeCurated(curated, "commands/ship.md", shipPage("Run `/ca:ship --turbo`, or `/ca:launch`."));
    let message = "";
    try {
      generate(unpairedPlugin(), tempDir("ca-drift-out-"), undefined, curated);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("ship.md");
    expect(message).toContain("--turbo");
    expect(message).toContain("/ca:launch");
  });

  it("generates when the curated text agrees with the source", () => {
    const curated = tempDir("ca-drift-curated-");
    writeCurated(curated, "commands/ship.md", shipPage("Run `/ca:ship`."));
    expect(() => generate(unpairedPlugin(), tempDir("ca-drift-out-"), undefined, curated)).not.toThrow();
  });

  /** A paired plugin whose skill source, and only it, carries the flag `--turbo`. */
  function pairedPlugin(): string {
    const plugin = buildPlugin([{ name: "ship", heading: "ship-flow" }], ["ship-flow"], true);
    writeCurated(
      plugin,
      "skills/ship-flow/SKILL.md",
      text("---", "name: ship-flow", 'description: "Fixture."', "---", "", "# ship-flow", "", "Accepts --turbo."),
    );
    return plugin;
  }
  it("checks a flag against the paired skill source as well as the command source", () => {
    const curated = tempDir("ca-drift-curated-");
    writeCurated(curated, "commands/ship.md", shipPage("Run `/ca:ship --turbo`."));
    expect(() => generate(pairedPlugin(), tempDir("ca-drift-out-"), undefined, curated)).not.toThrow();
  });

  it("still reports a flag that neither the command nor the paired skill has", () => {
    const curated = tempDir("ca-drift-curated-");
    writeCurated(curated, "commands/ship.md", shipPage("Run `/ca:ship --warp`."));
    expect(() => generate(pairedPlugin(), tempDir("ca-drift-out-"), undefined, curated)).toThrow(/--warp/);
  });
});

describe("the real curated set", () => {
  it("has no drift from the shipped sources", () => {
    const out = mkdtempSync(join(tmpdir(), "ca-drift-real-"));
    try {
      expect(() =>
        generate(join(repoRoot, "plugins", "ca"), out, undefined, join(siteRoot, "src", "curated"), true),
      ).not.toThrow();
    } finally {
      rmSync(out, { recursive: true, force: true });
    }
  });
});
