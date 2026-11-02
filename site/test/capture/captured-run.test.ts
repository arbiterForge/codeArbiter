/** captured-run.test.ts - AC-06/AC-07: a capture renders with the tool and source hash that produced it.
 *
 * `.mdx` guides use the CapturedRun component; plain `.md` guides, which cannot
 * import a component, use a `capture="<id>"` fence that this plugin fills at
 * build time. Both take the same label from scripts/capture/label.ts.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- untyped .mjs config module
import config from "../../astro.config.mjs";
import { capturedRunLabel, entryHash12 } from "../../scripts/capture/label";
import { captureMarker, isCaptureId, readCapture, remarkCapturedRun } from "../../scripts/capture/render";

const siteRoot = resolve(import.meta.dirname, "..", "..");
const capturesDir = join(siteRoot, "src", "assets", "captures");

type Node = { type: string; lang?: string | null; meta?: string | null; value?: string; children?: Node[] };

function fence(meta: string | null, value = ""): Node {
  return { type: "code", lang: "text", meta, value };
}

function transform(children: Node[], dir = capturesDir): Node {
  const tree: Node = { type: "root", children };
  remarkCapturedRun({ capturesDir: dir })()(tree, { path: "guide.md" });
  return tree;
}

describe("capture label", () => {
  const capture = readCapture("override-gate-row", capturesDir);

  it("names the tool path and the first 12 hex characters of the entry script's sha256", () => {
    const entry = capture.sources.find((source) => source.path === capture.tool)!;
    expect(entryHash12(capture)).toBe(entry.sha256.slice(0, 12));
    expect(capturedRunLabel(capture)).toBe(`Captured output of plugins/ca/hooks/append-override.py (sha256 ${entry.sha256.slice(0, 12)})`);
  });

  it("carries no version number, which the site's version-drift gate would reject", () => {
    expect(capturedRunLabel(capture)).not.toMatch(/\d+\.\d+/);
  });

  it("refuses a capture that does not hash its own entry script", () => {
    expect(() => capturedRunLabel({ id: "x", tool: "tools/a.py", sources: [{ path: "tools/b.py", sha256: "0".repeat(64) }] })).toThrow(/entry script/);
  });
});

describe("capture ids", () => {
  it("accept lowercase words joined by hyphens and nothing that could name a path", () => {
    expect(isCaptureId("override-gate-row")).toBe(true);
    for (const bad of ["", "../x", "a/b", "A", "a b", "-a", "a.json"]) expect(isCaptureId(bad)).toBe(false);
    expect(() => readCapture("../x", capturesDir)).toThrow(/Invalid capture id/);
  });

  it("are read from a fence's info string only as a whole word", () => {
    expect(captureMarker('capture="a-b"')).toBe("a-b");
    expect(captureMarker('wrap capture="a-b" extra')).toBe("a-b");
    expect(captureMarker('xcapture="a-b"')).toBeUndefined();
    expect(captureMarker("wrap")).toBeUndefined();
    expect(captureMarker(null)).toBeUndefined();
  });
});

describe("remarkCapturedRun", () => {
  it("fills an empty marker fence with the capture's output and titles the frame with the label", () => {
    const capture = readCapture("override-gate-row", capturesDir);
    const [node] = transform([fence('capture="override-gate-row"')]).children!;
    expect(node.lang).toBe("text");
    expect(node.value).toBe(capture.output);
    expect(node.meta).toBe(`title="${capturedRunLabel(capture)}" wrap`);
  });

  it("reaches a fence nested inside a list item", () => {
    const tree = transform([{ type: "list", children: [{ type: "listItem", children: [fence('capture="override-security-row"')] }] }]);
    const nested = tree.children![0].children![0].children![0];
    expect(nested.value).toContain("SECURITY-OVERRIDE");
  });

  it("leaves ordinary fences untouched", () => {
    const [node] = transform([fence("wrap", "echo hello")]).children!;
    expect(node).toEqual(fence("wrap", "echo hello"));
  });

  it("fails the build when a marker fence also contains hand-written text", () => {
    expect(() => transform([fence('capture="override-gate-row"', "typed by hand")])).toThrow(/must be empty/);
  });

  it("fails the build when the named capture does not exist", () => {
    expect(() => transform([fence('capture="no-such-capture"')])).toThrow(/no-such-capture.*npm run capture/s);
  });

  it("is wired into the site's Markdown processor, so a plain .md guide renders the capture", async () => {
    const renderer = await config.markdown.processor.createRenderer({});
    const { code } = await renderer.render('```text capture="override-security-row"\n```\n');
    expect(code).toContain("SECURITY-OVERRIDE | FINDING: ");
    expect(code).toContain("&#x3C;timestamp>");
    expect(code).not.toContain("capture=");
  });
});

describe("CapturedRun component", () => {
  const source = readFileSync(join(siteRoot, "src", "components", "CapturedRun.astro"), "utf8");

  it("renders the capture's output in a titled code frame using the shared label", () => {
    expect(source).toContain('import { Code } from "@astrojs/starlight/components"');
    expect(source).toContain("capturedRunLabel(capture)");
    expect(source).toContain("code={capture.output}");
    expect(source).toContain("../assets/captures/*.json");
  });

  it("fails the build for an unknown capture instead of rendering an empty block", () => {
    expect(source).toMatch(/if \(!capture\) throw new Error/);
  });
});
