import { afterEach, describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { generate } from "../../scripts/generator/generate";
import { loadCurated } from "../../scripts/generator/load-curated";
import { renderReaderFields } from "../../scripts/generator/render-reader-fields";
import type { ReaderShape } from "../../scripts/generator/types";
import { buildPlugin, cleanupFixtures, tempDir, writeCurated } from "./plugin-fixture";

afterEach(cleanupFixtures);

const WORKFLOW = {
  use_when: "you want a release cut from a clean main",
  avoid_when: "the tree has uncommitted work",
  asks: "which version to cut and whether to publish",
  produces: "a tagged release and its notes",
} as const;
const WORKFLOW_KEYS = Object.keys(WORKFLOW) as Array<keyof typeof WORKFLOW>;
const INTERNAL = {
  runs_inside: "the sprint lane, after the plan is approved",
  produces: "a spec the lane can execute",
} as const;

const EXAMPLE = "## Example\n\n```text\n/ca:ship 1.2.0\n```\n";

/** A curated companion file: reader fields in frontmatter, then a body. */
function curated(
  entity: string,
  fields: Record<string, string | undefined>,
  body = `## What it does\n\nProse.\n\n${EXAMPLE}`,
  extraFrontmatter = "",
): string {
  const lines = Object.entries(fields)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${key}: ${value}`);
  return `---\nentity: ${entity}\n${extraFrontmatter}${lines.join("\n")}${lines.length > 0 ? "\n" : ""}---\n\n${body}`;
}

function without<T extends object>(fields: T, key: keyof T): Record<string, string> {
  const copy = { ...fields } as Record<string, string>;
  delete copy[key as string];
  return copy;
}

const WORKFLOW_SHAPE = new Map<string, ReaderShape>([["commands/ship", "workflow"]]);
const INTERNAL_SHAPE = new Map<string, ReaderShape>([["skills/loner", "internal-skill"]]);

function loadShip(content: string, shape = WORKFLOW_SHAPE) {
  const dir = tempDir("ca-reader-fields-");
  writeCurated(dir, "commands/ship.md", content);
  return loadCurated(dir, new Set(["commands/ship"]), shape);
}

describe("loadCurated reader fields", () => {
  it("accepts a workflow command file with the four fields and an Example", () => {
    const doc = loadShip(curated("commands/ship", WORKFLOW)).get("commands/ship")!;
    expect(doc.reader).toEqual(WORKFLOW);
    expect(doc.body).toContain("## Example");
  });

  it.each(WORKFLOW_KEYS)("fails naming the file and the field when %s is missing", (key) => {
    expect(() => loadShip(curated("commands/ship", without(WORKFLOW, key)))).toThrow(
      new RegExp(`ship\\.md[^\\n]*missing required field "${key}"`),
    );
  });

  it.each(WORKFLOW_KEYS)("fails when %s is present but empty", (key) => {
    for (const empty of ["", '""', "''", "   "]) {
      expect(() => loadShip(curated("commands/ship", { ...WORKFLOW, [key]: empty })), `value ${JSON.stringify(empty)}`)
        .toThrow(new RegExp(`ship\\.md[^\\n]*field "${key}" is empty`));
    }
  });

  it("fails naming the file and the Example heading when the body has none", () => {
    const body = "## What it does\n\nProse only.\n";
    expect(() => loadShip(curated("commands/ship", WORKFLOW, body))).toThrow(
      /ship\.md[^\n]*missing an "Example" heading/,
    );
  });

  it("fails when the Example heading has no content before the next heading", () => {
    const body = "## Example\n\n## Usage\n\n```text\n/ca:ship\n```\n";
    expect(() => loadShip(curated("commands/ship", WORKFLOW, body))).toThrow(
      /ship\.md[^\n]*"Example" heading has no content/,
    );
  });

  it("does not count an Example heading inside a code fence", () => {
    const body = "## What it does\n\n```md\n## Example\n\nnot a heading\n```\n";
    expect(() => loadShip(curated("commands/ship", WORKFLOW, body))).toThrow(/missing an "Example" heading/);
  });

  it("does not count a heading that only starts with Example", () => {
    const body = "## Examples of use\n\nProse.\n\n## Worked example\n\nProse.\n";
    expect(() => loadShip(curated("commands/ship", WORKFLOW, body))).toThrow(/missing an "Example" heading/);
  });

  it("accepts Example at a deeper level, and with a code block as its only content", () => {
    expect(() => loadShip(curated("commands/ship", WORKFLOW, "## Usage\n\nProse.\n\n### Example\n\n```text\n/ca:ship\n```\n")))
      .not.toThrow();
  });

  it("counts content under a subheading of Example", () => {
    expect(() => loadShip(curated("commands/ship", WORKFLOW, "## Example\n\n### Release\n\nRun it.\n"))).not.toThrow();
  });

  it("requires only runs_inside and produces for an internal-only skill, and no Example", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "skills/loner.md", curated("skills/loner", INTERNAL, "## What it does\n\nProse only.\n"));
    const doc = loadCurated(dir, new Set(["skills/loner"]), INTERNAL_SHAPE).get("skills/loner")!;
    expect(doc.reader).toEqual(INTERNAL);
  });

  it.each(["runs_inside", "produces"] as const)("fails an internal-only skill missing %s", (key) => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "skills/loner.md", curated("skills/loner", without(INTERNAL, key)));
    expect(() => loadCurated(dir, new Set(["skills/loner"]), INTERNAL_SHAPE)).toThrow(
      new RegExp(`loner\\.md[^\\n]*missing required field "${key}"`),
    );
  });

  it("does not require the workflow fields of an internal-only skill, or runs_inside of a workflow file", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "skills/loner.md", curated("skills/loner", INTERNAL));
    expect(() => loadCurated(dir, new Set(["skills/loner"]), INTERNAL_SHAPE)).not.toThrow();
    expect(() => loadShip(curated("commands/ship", WORKFLOW))).not.toThrow();
  });

  it("requires nothing of an entity with no reader shape (alias command, merged skill)", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "commands/tidy.md", curated("commands/tidy", {}, "Points elsewhere.\n"));
    writeCurated(dir, "skills/merged.md", curated("skills/merged", {}, "Skill prose.\n"));
    const loaded = loadCurated(dir, new Set(["commands/tidy", "skills/merged"]), new Map());
    expect(loaded.size).toBe(2);
    expect(loaded.get("commands/tidy")!.reader).toBeUndefined();
  });

  it("reports every missing field and Example across all files in one error", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "commands/ship.md", curated("commands/ship", without(WORKFLOW, "asks"), "Prose.\n"));
    writeCurated(dir, "skills/loner.md", curated("skills/loner", {}));
    const shapes = new Map<string, ReaderShape>([
      ["commands/ship", "workflow"],
      ["skills/loner", "internal-skill"],
    ]);
    let message = "";
    try {
      loadCurated(dir, new Set(["commands/ship", "skills/loner"]), shapes);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("4 problems");
    expect(message).toMatch(/ship\.md[^\n]*"asks"/);
    expect(message).toMatch(/ship\.md[^\n]*"Example"/);
    expect(message).toMatch(/loner\.md[^\n]*"runs_inside"/);
    expect(message).toMatch(/loner\.md[^\n]*"produces"/);
  });

  it("reads reader fields only from top-level frontmatter keys", () => {
    const nested = "gates:\n  - gate: g\n    when: now\n    effect: stop\n    use_when: nested lookalike\n";
    expect(() => loadShip(curated("commands/ship", without(WORKFLOW, "use_when"), undefined, nested))).toThrow(
      /missing required field "use_when"/,
    );
  });

  it("strips matching quotes and keeps a colon inside the value", () => {
    const doc = loadShip(
      curated("commands/ship", { ...WORKFLOW, use_when: '"you need one thing: a release"', asks: "'which version?'" }),
    ).get("commands/ship")!;
    expect(doc.reader!.use_when).toBe("you need one thing: a release");
    expect(doc.reader!.asks).toBe("which version?");
  });

  it("rejects a block scalar, which the one-line frontmatter subset cannot read", () => {
    expect(() => loadShip(curated("commands/ship", { ...WORKFLOW, use_when: "|" }))).toThrow(
      /ship\.md[^\n]*"use_when"[^\n]*single line/,
    );
  });

  it("validates nothing when no reader shapes are supplied (plain loader)", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "commands/ship.md", curated("commands/ship", {}, "Prose only.\n"));
    expect(loadCurated(dir, new Set(["commands/ship"])).size).toBe(1);
  });
});

describe("loadCurated retired When to reach for it section", () => {
  const RETIRED = "## When to reach for it\n\nUse it for releases.\n";

  it("fails naming the file when a workflow command keeps the section beside the fields", () => {
    expect(() => loadShip(curated("commands/ship", WORKFLOW, `Prose.\n\n${EXAMPLE}\n${RETIRED}`))).toThrow(
      /ship\.md[^\n]*"When to reach for it"[^\n]*"use_when"/,
    );
  });

  it("fails for an entity with no reader shape too (alias command, merged skill)", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "commands/tidy.md", curated("commands/tidy", {}, `Alias text.\n\n${RETIRED}`));
    writeCurated(dir, "skills/merged.md", curated("skills/merged", {}, `Skill text.\n\n${RETIRED}`));
    let message = "";
    try {
      loadCurated(dir, new Set(["commands/tidy", "skills/merged"]), new Map());
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toMatch(/tidy\.md[^\n]*"When to reach for it"/);
    expect(message).toMatch(/merged\.md[^\n]*"When to reach for it"/);
  });

  it("fails when no reader shapes are supplied at all (plain loader)", () => {
    const dir = tempDir("ca-reader-fields-");
    writeCurated(dir, "commands/ship.md", curated("commands/ship", {}, `Prose.\n\n${RETIRED}`));
    expect(() => loadCurated(dir, new Set(["commands/ship"]))).toThrow(/ship\.md[^\n]*"When to reach for it"/);
  });

  it("matches the heading at any level and in any letter case", () => {
    for (const heading of ["### When to reach for it", "# when to reach for IT", "## When to reach for it ##"]) {
      expect(() => loadShip(curated("commands/ship", WORKFLOW, `${EXAMPLE}\n${heading}\n\nText.\n`)), heading)
        .toThrow(/"When to reach for it"/);
    }
  });

  it("reports it together with a missing field in one error", () => {
    let message = "";
    try {
      loadShip(curated("commands/ship", without(WORKFLOW, "asks"), `${EXAMPLE}\n${RETIRED}`));
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("2 problems");
    expect(message).toMatch(/ship\.md[^\n]*"asks"/);
    expect(message).toMatch(/ship\.md[^\n]*"When to reach for it"/);
  });

  it("ignores the words inside a code fence, in a longer heading and in prose", () => {
    const body = [
      EXAMPLE,
      "## When to reach for it again",
      "",
      "Prose that says When to reach for it in a sentence.",
      "",
      "```md",
      "## When to reach for it",
      "```",
      "",
    ].join("\n");
    expect(() => loadShip(curated("commands/ship", WORKFLOW, body))).not.toThrow();
  });
});

/** The panel's `<dl>` block, which must be one contiguous raw HTML block. */
function panel(markdown: string): string {
  const match = /<dl class="ca-reader-fields">\n[\s\S]*?\n<\/dl>/.exec(markdown);
  expect(match, 'a <dl class="ca-reader-fields"> block').not.toBeNull();
  return match![0];
}
const labelsOf = (markdown: string) => [...panel(markdown).matchAll(/<dt>(.*?)<\/dt>/g)].map((m) => m[1]);
const valuesOf = (markdown: string) => [...panel(markdown).matchAll(/<dd>(.*?)<\/dd>/g)].map((m) => m[1]);
const glanceHeadings = (markdown: string) => (markdown.match(/^## At a glance$/gm) ?? []).length;

const WORKFLOW_LABELS = ["Use it when", "Don't use it for", "What it asks you", "What it produces"];

describe("renderReaderFields", () => {
  it("renders the four workflow fields as one At a glance panel, labels and values in the fixed order", () => {
    const markdown = renderReaderFields(WORKFLOW, "workflow");
    expect(glanceHeadings(markdown)).toBe(1);
    expect(markdown.match(/^## /gm)).toHaveLength(1);
    expect(markdown.startsWith('## At a glance\n\n<dl class="ca-reader-fields">\n')).toBe(true);
    expect(labelsOf(markdown)).toEqual(WORKFLOW_LABELS);
    expect(valuesOf(markdown)).toEqual([WORKFLOW.use_when, WORKFLOW.avoid_when, WORKFLOW.asks, WORKFLOW.produces]);
  });

  it("keeps the list one raw HTML block, because a blank line would end it", () => {
    expect(panel(renderReaderFields(WORKFLOW, "workflow"))).not.toContain("\n\n");
    const spaced = renderReaderFields({ ...WORKFLOW, asks: "a first line\n\nand a second" }, "workflow");
    expect(panel(spaced)).not.toContain("\n\n");
    expect(valuesOf(spaced)[2]).toBe("a first line and a second");
  });

  it("renders Runs inside and What it produces for an internal-only skill, and nothing else", () => {
    const markdown = renderReaderFields({ ...INTERNAL, use_when: "ignored" }, "internal-skill");
    expect(glanceHeadings(markdown)).toBe(1);
    expect(labelsOf(markdown)).toEqual(["Runs inside", "What it produces"]);
    expect(valuesOf(markdown)).toEqual([INTERNAL.runs_inside, INTERNAL.produces]);
    expect(markdown).not.toContain("Use it when");
    expect(markdown).not.toContain("ignored");
  });

  it("skips a field with no value, and renders nothing when none has one", () => {
    expect(labelsOf(renderReaderFields({ ...WORKFLOW, avoid_when: "" }, "workflow"))).toEqual([
      "Use it when",
      "What it asks you",
      "What it produces",
    ]);
    expect(renderReaderFields({ ...WORKFLOW, use_when: "", avoid_when: "", asks: "", produces: "" }, "workflow")).toBe("");
  });

  it("renders inline code, links and emphasis in a value as HTML, not literal markdown", () => {
    const markdown = renderReaderFields(
      {
        ...WORKFLOW,
        avoid_when: "Opening a pull request, which is `/ca:pr`, or the [PR page](/reference/commands/pr/).",
        asks: "A **clear** go-ahead, *once*, and _only_ then.",
      },
      "workflow",
    );
    const [, avoid, asks] = valuesOf(markdown);
    expect(avoid).toBe(
      'Opening a pull request, which is <code>/ca:pr</code>, or the <a href="/reference/commands/pr/">PR page</a>.',
    );
    expect(asks).toBe("A <strong>clear</strong> go-ahead, <em>once</em>, and <em>only</em> then.");
    expect(panel(markdown)).not.toContain("`");
    expect(panel(markdown)).not.toContain("**");
  });

  it("escapes angle brackets inside a code span instead of emitting them as tags", () => {
    const markdown = renderReaderFields(
      { ...WORKFLOW, produces: "A packet at `.codearbiter/audits/<YYYY-MM-DD>.md` and `a && b`." },
      "workflow",
    );
    expect(valuesOf(markdown)[3]).toBe(
      "A packet at <code>.codearbiter/audits/&lt;YYYY-MM-DD&gt;.md</code> and <code>a &amp;&amp; b</code>.",
    );
    expect(markdown).not.toContain("<YYYY");
  });

  it("escapes HTML in a value, and does not let a value open a tag or an attribute", () => {
    const markdown = renderReaderFields(
      {
        ...WORKFLOW,
        use_when: 'you see <b>bold</b> & <script>alert("x")</script>',
        asks: 'a [link](/a"onmouseover="y) and a [bad](javascript:alert(1)) one',
      },
      "workflow",
    );
    const [useWhen, , asks] = valuesOf(markdown);
    expect(useWhen).toBe("you see &lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;");
    expect(asks).toBe('a <a href="/a&quot;onmouseover=&quot;y">link</a> and a [bad](javascript:alert(1)) one');
    expect(markdown).not.toContain("<script");
    expect(markdown).not.toContain("<b>");
    expect(markdown).not.toContain('href="javascript');
  });

  it("does not read identifiers with underscores as emphasis", () => {
    const markdown = renderReaderFields({ ...WORKFLOW, produces: "one of confirmed_code_defect or no_action" }, "workflow");
    expect(valuesOf(markdown)[3]).toBe("one of confirmed_code_defect or no_action");
  });

  it("renders nothing without a reader shape or without fields", () => {
    expect(renderReaderFields(WORKFLOW, undefined)).toBe("");
    expect(renderReaderFields(undefined, "workflow")).toBe("");
  });
});

describe("reader fields through generate()", () => {
  function plugin(): string {
    return buildPlugin(
      [
        { name: "ship", heading: "release-flow", visibility: "core", legacyRoutes: ["tidy"] },
        { name: "tidy", heading: "tidy-up", visibility: "alias", canonical: "ship", replacement: "ship --tidy" },
        { name: "helper", heading: "/ca:helper — internal", visibility: "internal" },
      ],
      ["release-flow", "tidy-up", "loner"],
    );
  }

  /** A curated set where every entity that needs fields has them. */
  function completeCurated(overrides: Record<string, string> = {}): string {
    const dir = tempDir("ca-reader-curated-");
    const files: Record<string, string> = {
      "commands/ship.md": curated("commands/ship", WORKFLOW, `Command text.\n\n${EXAMPLE}`),
      "commands/helper.md": curated("commands/helper", WORKFLOW, `Helper text.\n\n${EXAMPLE}`),
      "commands/tidy.md": curated("commands/tidy", {}, "Alias text.\n"),
      "skills/release-flow.md": curated("skills/release-flow", {}, "Merged skill text.\n"),
      "skills/tidy-up.md": curated("skills/tidy-up", WORKFLOW, `Skill text.\n\n${EXAMPLE}`),
      "skills/loner.md": curated("skills/loner", INTERNAL, "Loner text.\n"),
      ...overrides,
    };
    for (const [path, content] of Object.entries(files)) writeCurated(dir, path, content);
    return dir;
  }

  const page = (result: ReturnType<typeof generate>, type: string, slug: string) =>
    result.pages.find((p) => p.type === type && p.slug === slug)!.markdown;

  it("renders one At a glance panel above the body of a core command, a merged page and an alias-owning skill", () => {
    const result = generate(plugin(), tempDir("ca-reader-out-"), undefined, completeCurated());
    for (const [type, slug, bodyMarker] of [
      ["command", "ship", "Command text."],
      ["command", "helper", "Helper text."],
      ["skill", "tidy-up", "Skill text."],
    ] as const) {
      const markdown = page(result, type, slug);
      const label = `${type}/${slug}`;
      expect(glanceHeadings(markdown), label).toBe(1);
      expect(labelsOf(markdown), label).toEqual(WORKFLOW_LABELS);
      expect(valuesOf(markdown), label).toEqual(Object.values(WORKFLOW));
      const order = ["ca-reference-lead", "## At a glance", '<dl class="ca-reader-fields">', "</dl>", bodyMarker]
        .map((text) => markdown.indexOf(text));
      expect(order.every((index) => index >= 0), label).toBe(true);
      expect([...order].sort((a, b) => a - b), label).toEqual(order);
      expect(markdown, label).not.toContain("<dt>Runs inside</dt>");
      for (const old of WORKFLOW_LABELS) expect(markdown, `${label} ${old}`).not.toContain(`## ${old}`);
    }
  });

  it("renders a code span in a curated field as <code> inside the page's panel", () => {
    const dir = completeCurated({
      "commands/ship.md": curated(
        "commands/ship",
        { ...WORKFLOW, avoid_when: '"cutting a release, which is `/ca:ship`"' },
        `Command text.\n\n${EXAMPLE}`,
      ),
    });
    const markdown = page(generate(plugin(), tempDir("ca-reader-out-"), undefined, dir), "command", "ship");
    expect(valuesOf(markdown)[1]).toBe("cutting a release, which is <code>/ca:ship</code>");
    expect(panel(markdown)).not.toContain("`");
  });

  it("renders Runs inside and What it produces for an internal-only skill", () => {
    const markdown = page(generate(plugin(), tempDir("ca-reader-out-"), undefined, completeCurated()), "skill", "loner");
    expect(glanceHeadings(markdown)).toBe(1);
    expect(labelsOf(markdown)).toEqual(["Runs inside", "What it produces"]);
    expect(valuesOf(markdown)).toEqual([INTERNAL.runs_inside, INTERNAL.produces]);
    const order = ["## At a glance", "</dl>", "Loner text."].map((text) => markdown.indexOf(text));
    expect(order.every((index) => index >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(markdown).not.toContain("<dt>Use it when</dt>");
  });

  it("renders no reader fields on an alias command page", () => {
    const result = generate(
      plugin(),
      tempDir("ca-reader-out-"),
      undefined,
      completeCurated({ "commands/tidy.md": curated("commands/tidy", WORKFLOW, "Alias text.\n") }),
    );
    const markdown = page(result, "command", "tidy");
    expect(markdown).toContain("Alias text.");
    expect(markdown).not.toContain("At a glance");
    expect(markdown).not.toContain("ca-reader-fields");
    for (const label of [...WORKFLOW_LABELS, "Runs inside"]) {
      expect(markdown).not.toContain(`<dt>${label}</dt>`);
      expect(markdown).not.toContain(`## ${label}`);
    }
  });

  it("emits no page for the merged skill even though its curated file carries no fields", () => {
    const outDir = tempDir("ca-reader-out-");
    generate(plugin(), outDir, undefined, completeCurated());
    expect(existsSync(join(outDir, "skills", "release-flow.md"))).toBe(false);
  });

  it.each(WORKFLOW_KEYS)("fails generation naming the core command file and %s", (key) => {
    const dir = completeCurated({ "commands/ship.md": curated("commands/ship", without(WORKFLOW, key), `Text.\n\n${EXAMPLE}`) });
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, dir)).toThrow(
      new RegExp(`ship\\.md[^\\n]*"${key}"`),
    );
  });

  it("fails generation naming the file and the Example heading", () => {
    const dir = completeCurated({ "commands/ship.md": curated("commands/ship", WORKFLOW, "Text only.\n") });
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, dir)).toThrow(
      /ship\.md[^\n]*"Example"/,
    );
  });

  it("requires the fields of an internal command", () => {
    const dir = completeCurated({ "commands/helper.md": curated("commands/helper", {}, `Text.\n\n${EXAMPLE}`) });
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, dir)).toThrow(/helper\.md[^\n]*"use_when"/);
  });

  it("requires the fields of a skill that owns an alias route", () => {
    const dir = completeCurated({
      "skills/tidy-up.md": curated("skills/tidy-up", without(WORKFLOW, "avoid_when"), `Text.\n\n${EXAMPLE}`),
    });
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, dir)).toThrow(
      /tidy-up\.md[^\n]*"avoid_when"/,
    );
  });

  it("requires runs_inside and produces of an internal-only skill", () => {
    const dir = completeCurated({ "skills/loner.md": curated("skills/loner", without(INTERNAL, "runs_inside")) });
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, dir)).toThrow(
      /loner\.md[^\n]*"runs_inside"/,
    );
  });

  it("does not require fields of an alias command or a merged skill", () => {
    expect(() => generate(plugin(), tempDir("ca-reader-out-"), undefined, completeCurated())).not.toThrow();
  });
});
