import { describe, expect, it } from "vitest";
import { frameSvg, renderText, spellCommand } from "./machine-render";

describe("renderText", () => {
  const options = { base: "/docs", form: "/ca:{name}" };

  it("escapes markup and renders code spans", () => {
    expect(renderText("Use `git add <path>` & <b>stop</b>", options)).toBe(
      "Use <code>git add &lt;path&gt;</code> &amp; &lt;b&gt;stop&lt;/b&gt;",
    );
  });

  it("spells command placeholders for the chosen host and keeps the command for later re-spelling", () => {
    expect(renderText("Run {{init --check}} first.", options)).toBe(
      'Run <code class="ca-machine__cmd" data-cmd="init" data-args="--check">/ca:init --check</code> first.',
    );
    expect(renderText("Run {{init}}.", { ...options, form: "$ca-{name}" })).toContain(">$ca-init</code>");
  });

  it("links gate IDs to the generated Hook Gates reference, but not inside code", () => {
    expect(renderText("Force-push is blocked (H-02), see `H-02`.", options)).toBe(
      'Force-push is blocked (<a href="/docs/reference/hooks-gates/#h-02">H-02</a>), see <code>H-02</code>.',
    );
    expect(renderText("H-09b and H-10b", { ...options, base: "" })).toBe(
      '<a href="/reference/hooks-gates/#h-09b">H-09b</a> and <a href="/reference/hooks-gates/#h-10b">H-10b</a>',
    );
  });
});

describe("spellCommand and frameSvg", () => {
  it("spells a command with each host's form", () => {
    expect(spellCommand("/ca:{name}", "pr", "--watch")).toBe("/ca:pr --watch");
    expect(spellCommand("/ca-{name}", "pr")).toBe("/ca-pr");
  });

  it("draws a decorative frame and falls back to the square for an unknown shape", () => {
    expect(frameSvg("shield")).toMatch(/^<svg class="ca-machine__frame" viewBox="0 0 16 16" aria-hidden="true"/);
    expect(frameSvg("unknown")).toBe(frameSvg("square"));
  });
});
