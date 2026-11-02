/** guide-examples.test.ts - AC-07: every guide example is captured, labelled, or plainly an input.
 *
 * scripts/capture/guide-examples.json classifies every fenced block in the
 * guides. This test holds the guides to it:
 *  - a block the inventory does not list fails, naming the page and block;
 *  - a capturable block must be a reference to a committed capture, with no
 *    typed output beside it, and the capture must come from the inventory's tool;
 *  - an illustrative block must carry its label in the stated place;
 *  - an input block (a command or file the reader writes) must look like one.
 *
 * Relabelling a capturable block to pass is not possible: its class comes from
 * the tool that produced the text, and the capture reference is checked.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { CAPTURE_TARGETS } from "../../scripts/capture/targets";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const guidesDir = join(siteRoot, "src", "content", "docs", "guides");
const capturesDir = join(siteRoot, "src", "assets", "captures");

interface InventoryEntry {
  page: string;
  match: string;
  occurrence?: number;
  class: "capturable" | "illustrative" | "input";
  capture?: string;
  tool?: string;
  fixture?: string;
  label?: { form: "in-block" | "lead-in"; text: string };
  form?: "slash-command" | "shell-command" | "file-text";
  reason?: string;
}

interface Inventory {
  schema: number;
  blocks: InventoryEntry[];
}

interface Block {
  page: string;
  key: string;
  occurrence: number;
  line: number;
  body: string[];
  /** The paragraph directly above the block, whitespace-collapsed. */
  leadIn: string;
  reference: boolean;
}

const inventory = JSON.parse(readFileSync(join(siteRoot, "scripts", "capture", "guide-examples.json"), "utf8")) as Inventory;

const FENCE_OPEN = /^(\s*)(`{3,}|~{3,})(.*)$/;
const CAPTURE_MARKER = /(?:^|\s)capture="([^"\s]*)"(?=\s|$)/;
const COMPONENT = /<CapturedRun\s+id="([^"]+)"\s*\/>/g;
const SLASH_COMMAND = /^[/$][A-Za-z][\w:-]*(\s|$)/;
const SHELL_COMMAND = /^(git|python|pi|claude|codex|rm)(\s|$)|^CODEARBITER_THEME=|^\$env:/;
/** Phrases that say the text is not a record of something that ran. */
const NON_CLAIM = /\bnot (?:a |an )?(?:newly accepted decision|captured|executed|receipt)\b/i;

function leadInOf(lines: string[], fenceIndex: number): string {
  let end = fenceIndex - 1;
  while (end >= 0 && lines[end].trim() === "") end -= 1;
  let start = end;
  while (start > 0 && lines[start - 1].trim() !== "") start -= 1;
  return end < 0 ? "" : lines.slice(start, end + 1).join(" ").replace(/\s+/g, " ").trim();
}

/** Every fenced block, and every <CapturedRun /> reference, on one page. */
function parseBlocks(page: string, source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Omit<Block, "occurrence">[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const open = FENCE_OPEN.exec(lines[index]);
    if (!open) {
      for (const match of lines[index].matchAll(COMPONENT)) {
        blocks.push({ page, key: `capture=${match[1]}`, line: index + 1, body: [], leadIn: "", reference: true });
      }
      continue;
    }
    const marker = open[2];
    let close = index + 1;
    while (close < lines.length) {
      const candidate = lines[close].trim();
      if (candidate.startsWith(marker[0]) && /^(`+|~+)$/.test(candidate) && candidate.length >= marker.length) break;
      close += 1;
    }
    const body = lines.slice(index + 1, close).map((line) => line.trim()).filter(Boolean);
    const referenced = CAPTURE_MARKER.exec(open[3]);
    blocks.push({
      page,
      key: referenced ? `capture=${referenced[1]}` : (body[0] ?? ""),
      line: index + 1,
      body,
      leadIn: leadInOf(lines, index),
      reference: referenced !== null,
    });
    index = close;
  }
  const seen = new Map<string, number>();
  return blocks.map((block) => {
    const occurrence = (seen.get(block.key) ?? 0) + 1;
    seen.set(block.key, occurrence);
    return { ...block, occurrence };
  });
}

function guidePages(): Record<string, string> {
  const pages: Record<string, string> = {};
  for (const name of readdirSync(guidesDir, { recursive: true }) as string[]) {
    const page = name.replaceAll("\\", "/");
    if (/\.mdx?$/.test(page)) pages[page] = readFileSync(join(guidesDir, name), "utf8");
  }
  return pages;
}

const label = (block: Block) => `${block.page}: block ${JSON.stringify(block.key)} (line ${block.line})`;

/** Every way the guides, the inventory and the captures can disagree. Empty means they agree. */
function audit(
  pages: Record<string, string>,
  entries: readonly InventoryEntry[],
  captures: ReadonlyMap<string, { tool: string }>,
): string[] {
  const problems: string[] = [];
  const claimed = new Set<InventoryEntry>();
  const allBlocks = Object.entries(pages).flatMap(([page, source]) => parseBlocks(page, source));

  for (const block of allBlocks) {
    const entry = entries.find(
      (candidate) => candidate.page === block.page && candidate.match === block.key && (candidate.occurrence ?? 1) === block.occurrence,
    );
    if (!entry) {
      problems.push(`${label(block)} is not in the inventory; classify it as capturable, illustrative or input`);
      continue;
    }
    claimed.add(entry);

    if (entry.class === "capturable") {
      const capture = entry.capture ?? "";
      if (block.key !== `capture=${capture}`) {
        problems.push(`${label(block)} is classed capturable but is hand-written; render it from capture "${capture}"`);
      } else if (!block.reference || block.body.length > 0) {
        problems.push(`${label(block)} sits beside typed text; a captured block must hold only the capture reference`);
      }
      if (block.page.endsWith(".md") && !block.reference) {
        problems.push(`${label(block)} is a plain .md guide, which can only use a capture="${capture}" fence`);
      }
      const known = captures.get(capture);
      if (!known) problems.push(`${label(block)} names capture "${capture}", which has no target and asset`);
      else if (known.tool !== entry.tool) problems.push(`${label(block)} says tool ${entry.tool} but capture "${capture}" ran ${known.tool}`);
    } else if (block.key.startsWith("capture=")) {
      problems.push(`${label(block)} references a capture but is classed ${entry.class}`);
    } else if (entry.class === "illustrative") {
      const text = entry.label?.text ?? "";
      if (!/\billustrative\b/i.test(text) || !NON_CLAIM.test(text)) {
        problems.push(`${label(block)} has a label that does not say illustrative and not captured: ${JSON.stringify(text)}`);
      } else if (entry.label?.form === "in-block" && block.body[0] !== text) {
        problems.push(`${label(block)} should open with its label ${JSON.stringify(text)}`);
      } else if (entry.label?.form === "lead-in" && !block.leadIn.includes(text)) {
        problems.push(`${label(block)} should be introduced by ${JSON.stringify(text)}`);
      } else if (entry.label?.form !== "in-block" && entry.label?.form !== "lead-in") {
        problems.push(`${label(block)} has an unknown label form`);
      }
    } else if (entry.class === "input") {
      const pattern = entry.form === "slash-command" ? SLASH_COMMAND : entry.form === "shell-command" ? SHELL_COMMAND : undefined;
      if (pattern) {
        const odd = block.body.find((line) => !pattern.test(line));
        if (odd !== undefined) problems.push(`${label(block)} is classed ${entry.form} but contains ${JSON.stringify(odd)}`);
      } else if (entry.form === "file-text") {
        if (!entry.reason) problems.push(`${label(block)} is file-text input without a stated reason`);
      } else {
        problems.push(`${label(block)} has an unknown input form`);
      }
    }
  }

  for (const entry of entries) {
    if (!claimed.has(entry)) problems.push(`${entry.page}: inventory entry ${JSON.stringify(entry.match)} matches no block`);
  }

  // No guide may keep typing out what a capture already holds.
  for (const [id] of captures) {
    const output = JSON.parse(readFileSync(join(capturesDir, `${id}.json`), "utf8")).output as string;
    for (const line of output.split("\n").filter((text) => text.length > 24)) {
      for (const page of Object.keys(pages)) {
        if (pages[page].includes(line)) problems.push(`${page}: still types out line of capture "${id}": ${JSON.stringify(line.slice(0, 60))}`);
      }
    }
  }
  return problems;
}

const captureTools = new Map(
  CAPTURE_TARGETS.filter((target) => existsSync(join(capturesDir, `${target.id}.json`))).map((target) => [target.id, { tool: target.tool }]),
);

describe("guide example inventory (T-07)", () => {
  it("parses, is versioned, and classifies every entry", () => {
    expect(inventory.schema).toBe(1);
    expect(inventory.blocks.length).toBeGreaterThan(40);
    for (const entry of inventory.blocks) expect(["capturable", "illustrative", "input"]).toContain(entry.class);
  });

  it("has unique entries and names pages that exist", () => {
    const keys = inventory.blocks.map((entry) => `${entry.page}|${entry.match}|${entry.occurrence ?? 1}`);
    expect(new Set(keys).size).toBe(keys.length);
    for (const entry of inventory.blocks) expect(existsSync(join(guidesDir, entry.page)), entry.page).toBe(true);
  });

  it("counts what the inventory claims", () => {
    const count = (kind: string) => inventory.blocks.filter((entry) => entry.class === kind).length;
    expect(count("capturable") + count("illustrative") + count("input")).toBe(inventory.blocks.length);
    expect(count("capturable")).toBe(5);
  });
});

describe("guide examples are captured, labelled or inputs (AC-07)", () => {
  const pages = guidePages();

  it("finds the guide pages", () => {
    expect(Object.keys(pages).length).toBeGreaterThan(15);
  });

  it("holds for every block in every guide", () => {
    expect(audit(pages, inventory.blocks, captureTools)).toEqual([]);
  });

  it("renders each capturable block from a committed capture of the inventory's tool", () => {
    const capturable = inventory.blocks.filter((entry) => entry.class === "capturable");
    for (const entry of capturable) {
      const capture = JSON.parse(readFileSync(join(capturesDir, `${entry.capture}.json`), "utf8"));
      expect(capture.tool, entry.capture).toBe(entry.tool);
      expect(capture.exitCode, entry.capture).toBe(CAPTURE_TARGETS.find((target) => target.id === entry.capture)!.expectExitCode);
    }
  });

  it("leaves no capture target without a guide block that uses it", () => {
    const used = new Set(inventory.blocks.filter((entry) => entry.class === "capturable").map((entry) => entry.capture));
    expect([...used].sort()).toEqual(CAPTURE_TARGETS.map((target) => target.id).sort());
  });

  // The scenarios below are the negative controls: each breaks a copy of the real guides.
  it("names the page and block when an unlabelled output block is added (SCN-AC-07)", () => {
    const broken = { ...pages, "feature-lane.mdx": `${pages["feature-lane.mdx"]}\n\`\`\`text\nBLOCKED [H-03]: made-up tool output\n\`\`\`\n` };
    const problems = audit(broken, inventory.blocks, captureTools);
    expect(problems).toEqual([expect.stringMatching(/^feature-lane\.mdx: block "BLOCKED \[H-03\]: made-up tool output" \(line \d+\) is not in the inventory/)]);
  });

  it("fails a capturable block that is hand-written again instead of referencing its capture", () => {
    const page = "overriding-a-gate.md";
    const handWritten = pages[page].replace(/```text capture="override-gate-row"[^\n]*\n\s*```/, "```text\n[2026-06-27T14:30:00Z] | BY: you@example.com | GATE: design-review | REASON: typed\n```");
    expect(handWritten).not.toBe(pages[page]);
    const problems = audit({ ...pages, [page]: handWritten }, inventory.blocks, captureTools);
    expect(problems.join("\n")).toMatch(/overriding-a-gate\.md/);
    expect(problems.join("\n")).toMatch(/is not in the inventory|inventory entry "capture=override-gate-row" matches no block/);
  });

  it("fails a capture reference with typed text inside it", () => {
    const page = "troubleshooting.md";
    const typed = pages[page].replace(/(```text capture="context-scaffold-frontmatter"[^\n]*\n)(\s*```)/, "$1arbiter: enabled\n$2");
    expect(typed).not.toBe(pages[page]);
    expect(audit({ ...pages, [page]: typed }, inventory.blocks, captureTools).join("\n")).toMatch(/holds only the capture reference|only the capture reference/);
  });

  it("fails an illustrative block whose label has been removed", () => {
    const page = "adding-a-dependency.mdx";
    const unlabelled = pages[page].replace("Illustrative request, not a captured review:\n", "");
    expect(unlabelled).not.toBe(pages[page]);
    expect(audit({ ...pages, [page]: unlabelled }, inventory.blocks, captureTools).join("\n")).toMatch(/adding-a-dependency\.mdx/);
  });

  it("fails an illustrative record whose lead-in label has been removed", () => {
    const page = "recording-adrs.mdx";
    const unlabelled = pages[page].replace("This is an illustrative record, not a newly accepted decision or a receipt from your repository.\n", "");
    expect(unlabelled).not.toBe(pages[page]);
    expect(audit({ ...pages, [page]: unlabelled }, inventory.blocks, captureTools).join("\n")).toMatch(/should be introduced by/);
  });

  it("fails an input block that has become output", () => {
    const page = "ca-sandbox.md";
    const output = pages[page].replace('/ca-sandbox:sandbox-destroy "<id>"', "container removed: 3 volumes");
    expect(output).not.toBe(pages[page]);
    expect(audit({ ...pages, [page]: output }, inventory.blocks, captureTools).join("\n")).toMatch(/ca-sandbox\.md/);
  });

  it("fails a guide that types out a line a capture already holds", () => {
    const page = "troubleshooting.md";
    const duplicate = `${pages[page]}\nThe helper wrote: [<timestamp>] | BY: you@example.com | GATE: design-review | REASON: design review: retain the deprecated v2 compatibility selector until the documented v3 removal release; supported v2 clients still depend on it, this commit only\n`;
    expect(audit({ ...pages, [page]: duplicate }, inventory.blocks, captureTools).join("\n")).toMatch(/still types out line of capture "override-gate-row"/);
  });
});
