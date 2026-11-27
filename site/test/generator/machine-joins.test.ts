import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { extractHookGates } from "../../scripts/generator/extract-hook-gates";
import { gateJoin, lanePartFor, markdownText, partsCiting, routeLineHtml, routeStops } from "../../scripts/generator/machine-joins";

const repo = resolve(import.meta.dirname, "../../..");
const catalog = JSON.parse(readFileSync(join(repo, "core/surface/command-routes.json"), "utf8")).commands as Record<string, { visibility: string }>;

describe("machine joins", () => {
  it("joins a command to the lane the machine model routes for it", () => {
    const lane = lanePartFor("feature");
    expect(lane?.id).toBe("ca-feature");
    expect(lane?.href).toBe("/concepts/machine/#part-ca-feature");
    expect(routeStops("ca-feature")).toHaveLength(12);
    expect(lanePartFor("not-a-command")).toBeNull();
  });

  it("finds a lane for every core, advanced and internal command", () => {
    const missing = Object.entries(catalog)
      .filter(([, command]) => ["core", "advanced", "internal"].includes(command.visibility))
      .map(([name]) => name)
      .filter((name) => !lanePartFor(name));
    expect(missing).toEqual([]);
  });

  it("joins a skill or agent only where the machine model cites its own file", () => {
    expect(partsCiting("plugins/ca/skills/tdd/SKILL.md").map((part) => part.id)).toEqual(expect.arrayContaining(["skill-tdd", "ca-fix"]));
    expect(partsCiting("plugins/ca/agents/backend-author.md").map((part) => part.id)).toEqual(["authors"]);
    expect(partsCiting("plugins/ca/agents/scout.md")).toEqual([]);
    expect(partsCiting("plugins/ca/commands/not-real.md")).toEqual([]);
    expect(partsCiting("plugins/ca/skills/tdd-extra/SKILL.md")).toEqual([]);
  });

  it("names lane parts by their command, never by a missing name", () => {
    const lane = partsCiting("plugins/ca/skills/tdd/SKILL.md").find((part) => part.id === "ca-fix");
    expect(lane?.name).toBe("/ca:fix lane");
    for (const part of partsCiting("plugins/ca/skills/brainstorming/SKILL.md")) expect(part.name).not.toMatch(/undefined/);
  });

  it("gives every hook gate an owning machine part", () => {
    const tags = [...new Set(extractHookGates(join(repo, "plugins/ca/hooks")).callSites.map((site) => site.tag))];
    expect(tags.length).toBeGreaterThan(10);
    expect(tags.filter((tag) => gateJoin(tag).parts.length === 0)).toEqual([]);
  });

  it("links a gate to the failure scenario that shows it firing", () => {
    const h03 = gateJoin("H-03");
    expect(h03.parts.map((part) => part.id)).toContain("guard-bash");
    expect(h03.scenarios.map((scenario) => scenario.href)).toContain("/concepts/machine/#fault-add-all");
    expect(gateJoin("H-10b").scenarios.map((scenario) => scenario.id)).toContain("fault-hardcoded-key");
    expect(gateJoin("H-10").scenarios.map((scenario) => scenario.id)).toContain("fault-hardcoded-key");
    expect(gateJoin("H-1").parts).toEqual([]);
  });

  it("keeps machine titles intact in Markdown: flags become code, punctuation is escaped", () => {
    expect(markdownText("Skips the git hooks with --no-verify")).toBe("Skips the git hooks with `--no-verify`");
    expect(markdownText("pre-bash and -n")).toBe("pre-bash and `-n`");
    expect(markdownText("a [b] *c* <d>")).toBe("a \\[b\\] \\*c\\* \\<d\\>");
    const h20 = gateJoin("H-20").scenarios.find((scenario) => scenario.id === "fault-no-verify");
    expect(h20?.title).toContain("--no-verify");
  });

  it("draws a route as decorative frames coloured by what happens at each stop", () => {
    const stops = routeStops("ca-fix");
    const html = routeLineHtml(stops);
    expect(html).toMatch(/^<div class="ca-route" aria-hidden="true"/);
    expect(html.match(/class="ca-route__stop"/g)).toHaveLength(stops.length);
    expect(stops.some((stop) => stop.verdict === "fail")).toBe(true);
    expect(html).toContain('data-tone="danger"');
    expect(html).not.toContain("undefined");
  });
});

describe("generated pages carry their machine joins", async () => {
  const { renderCommandPage } = await import("../../scripts/generator/render-command-page");
  const { renderSkillPage } = await import("../../scripts/generator/render-skill-page");
  const { renderAgentPage } = await import("../../scripts/generator/render-agent-page");
  const { renderHooksReference } = await import("../../scripts/generator/render-hooks-reference");
  const base = { sourceRaw: "body\n", pluginVersion: "9.9.9" };

  it("puts a command's lane route and machine link in its route context", () => {
    const md = renderCommandPage({
      ...base,
      name: "feature",
      description: "d",
      sourceRelPath: "plugins/ca/commands/feature.md",
      commandCatalog: { description: "d", commandPath: "commands/feature.md", visibility: "core", workflow: "change", canonical: "feature" },
    });
    const context = md.slice(md.indexOf("## Route context"), md.indexOf("## Source"));
    expect(context).toContain('<div class="ca-route" aria-hidden="true"');
    expect(context).toContain("[/ca:feature lane](/concepts/machine/#part-ca-feature)");
    expect(context).toMatch(/: 12 stops, waiting at \d+ of them on a gate or on you\./);
    expect(context).toContain("(/concepts/workflow-routes/#atlas-feature)");
  });

  it("adds an In the machine section to a skill or agent the model cites, and none otherwise", () => {
    const tdd = renderSkillPage({ ...base, name: "tdd", description: "d", sourceRelPath: "plugins/ca/skills/tdd/SKILL.md" });
    expect(tdd).toContain("## In the machine");
    expect(tdd).toContain("(/concepts/machine/#part-skill-tdd)");
    const author = renderAgentPage({ ...base, name: "backend-author", description: "d", sourceRelPath: "plugins/ca/agents/backend-author.md" });
    expect(author).toContain("cites this agent in [Author agents](/concepts/machine/#part-authors)");
    const scout = renderAgentPage({ ...base, name: "scout", description: "d", sourceRelPath: "plugins/ca/agents/scout.md" });
    expect(scout).not.toContain("## In the machine");
  });

  it("names each hook gate's machine owner and the scenario that shows it", () => {
    const md = renderHooksReference(
      [{ tag: "H-03", kind: "block", file: "pre-bash.py", line: 10, message: "no broad staging" }],
      new Map([["pre-bash.py", ["PreToolUse (Bash)"]]]),
      "9.9.9",
      "main",
    );
    expect(md).toContain("**In the machine:** [Shell gate (pre-bash)](/concepts/machine/#part-guard-bash).");
    expect(md).toContain("Watch it catch a mistake: [Stages everything, including a .env file](/concepts/machine/#fault-add-all).");
  });

  it("keeps the generator's own prose free of separator dashes and literal backticks", () => {
    const md = renderHooksReference([], new Map(), "9.9.9", "main");
    const prose = md.replace(/^>.*$/gm, "");
    expect(prose).not.toMatch(/\s[—–]\s/);
    expect(prose).toContain("A `{placeholder}` shown in a message");
    expect(prose).not.toContain("`` `{placeholder}` ``");
  });
});
