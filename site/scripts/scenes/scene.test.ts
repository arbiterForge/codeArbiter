import { describe, expect, it } from "vitest";
import { pathLength, validateScene, wrapMono, type Scene } from "./scene";
import { renderSceneSvg } from "./render-scene";

/** The smallest scene that satisfies every rule: two parts, one handoff, one note, two steps. */
function minimal(): Scene {
  return {
    id: "mini",
    title: "Mini",
    summary: "A request reaches a guard.",
    size: { wide: { w: 500, h: 200 }, tall: { w: 200, h: 300 } },
    nodes: [
      { id: "a", part: "operator", label: "You", zone: "You", shape: "diamond", tone: "brand", at: { wide: { x: 10, y: 60, w: 170, h: 56 }, tall: { x: 25, y: 10, w: 150, h: 56 } } },
      { id: "b", part: "guard-bash", label: "Shell gate", sub: "pre-bash.py", zone: "Guard ring", shape: "shield", tone: "danger", at: { wide: { x: 300, y: 60, w: 170, h: 56 }, tall: { x: 25, y: 200, w: 150, h: 56 } } },
    ],
    edges: [{ id: "ab", from: "a", to: "b", path: { wide: "M180,88 H300", tall: "M100,66 V200" } }],
    notes: [{ id: "n", tone: "danger", lines: ["BLOCKED [H-03]"], at: { x: 200, y: 10, w: 190 } }],
    steps: [
      { id: "ask", title: "You ask", caption: "You describe the change.", reveal: ["a", "b", "ab"], focus: "a", travel: ["ab"], verdict: "run" },
      { id: "block", title: "Blocked", caption: "The gate refuses.", reveal: ["n"], focus: "b", verdict: "block", terminal: "BLOCKED [H-03]" },
    ],
    evidence: "Illustrative.",
  };
}

describe("pathLength", () => {
  it("sums straight segments in absolute M, H, V and L commands", () => {
    expect(pathLength("M0,0 H30 V40")).toBe(70);
    expect(pathLength("M0 0 L30 40")).toBe(50);
    expect(pathLength("M10,10 H20 M0,0 V5")).toBe(15);
  });

  it("refuses curves and relative commands rather than guessing their length", () => {
    expect(() => pathLength("M0,0 C10,10 20,20 30,30")).toThrow(/unsupported/);
    expect(() => pathLength("M0,0 h10")).toThrow(/unsupported/);
  });
});

describe("wrapMono", () => {
  it("never exceeds the column budget and loses no characters", () => {
    const text = "BLOCKED [H-03]: 'git add -A' / 'git add .' / 'git add --all' / 'git add -u' are prohibited.";
    for (const cols of [12, 25, 40, 73]) {
      const lines = wrapMono(text, cols);
      for (const line of lines) expect(line.length).toBeLessThanOrEqual(cols);
      expect(lines.join(" ")).toBe(text);
    }
  });

  it("breaks a word longer than the budget instead of overflowing", () => {
    expect(wrapMono("[2026-07-30T13:34:06Z]", 10)).toEqual(["[2026-07-3", "0T13:34:06", "Z]"]);
  });
});

describe("validateScene", () => {
  it("accepts a well-formed scene", () => {
    expect(validateScene(minimal())).toEqual([]);
  });

  it("names duplicate ids and unknown edge endpoints", () => {
    const scene = minimal();
    scene.notes[0].id = "a";
    scene.edges[0].to = "ghost";
    const findings = validateScene(scene).join("\n");
    expect(findings).toMatch(/duplicate id a/);
    expect(findings).toMatch(/edge ab ends at unknown node ghost/);
  });

  it("requires every element to be revealed exactly once", () => {
    const twice = minimal();
    twice.steps[1].reveal.push("ab");
    expect(validateScene(twice).join("\n")).toMatch(/ab is revealed more than once/);
    const never = minimal();
    never.steps[1].reveal = [];
    expect(validateScene(never).join("\n")).toMatch(/n is never revealed/);
  });

  it("only focuses or travels what the reader can already see", () => {
    const scene = minimal();
    scene.steps[0].focus = "n";
    scene.steps[0].reveal = ["a", "ab"];
    scene.steps[1].reveal = ["n", "b"];
    const findings = validateScene(scene).join("\n");
    expect(findings).toMatch(/step ask focuses n before it is revealed/);
    expect(findings).toMatch(/step ask travels ab before its end b is revealed/);
  });

  it("keeps geometry inside its composition and terminal text inside its box", () => {
    const scene = minimal();
    scene.nodes[1].at.wide.x = 390;
    scene.notes[0].lines = ["x".repeat(40)];
    const findings = validateScene(scene).join("\n");
    expect(findings).toMatch(/node b leaves the wide composition/);
    expect(findings).toMatch(/note n line 1 is wider than its box/);
  });

  it("rejects an empty caption or a title too long for the step rail", () => {
    const scene = minimal();
    scene.steps[0].caption = " ";
    scene.steps[1].title = "A title far too long to sit on the step rail beside six others";
    const findings = validateScene(scene).join("\n");
    expect(findings).toMatch(/step ask has no caption/);
    expect(findings).toMatch(/step block title is longer than 40 characters/);
  });
});

describe("renderSceneSvg", () => {
  it("draws each composition as a decorative, step-annotated vector", () => {
    const svg = renderSceneSvg(minimal(), "wide");
    expect(svg).toMatch(/^<svg [^>]*viewBox="0 0 500 200"/);
    expect(svg).toContain('aria-hidden="true"');
    expect(svg).toContain('data-el="ab" data-from-step="0"');
    expect(svg).toContain('data-el="n" data-from-step="1"');
    expect(svg).toContain("Shell gate");
    expect(svg).toContain("pre-bash.py");
    expect(svg).toContain("style=\"--len:120\"");
  });

  it("escapes every model string it draws", () => {
    const scene = minimal();
    scene.nodes[0].label = "<you & me>";
    expect(renderSceneSvg(scene, "tall")).toContain("&lt;you &amp; me&gt;");
  });

  it("omits terminal notes from the tall composition, where the step text carries them", () => {
    expect(renderSceneSvg(minimal(), "tall")).not.toContain('data-el="n"');
  });
});
