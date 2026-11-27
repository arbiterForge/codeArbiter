import { describe, expect, it } from "vitest";
import { buildGateIndex, loadGateIndex, surfaceOf, type GateSummaries } from "./gate-index";
import type { HookCallSite } from "../generator/extract-hook-gates";

const site = (tag: string, kind: "block" | "remind", file: string, message = "m"): HookCallSite => ({ tag, kind, file, line: 1, message });
const events = new Map([
  ["pre-bash.py", ["PreToolUse (Bash|PowerShell)"]],
  ["pre-write.py", ["PreToolUse (Write)"]],
  ["post-write-edit.py", ["PostToolUse (Write|Edit)"]],
]);

describe("the Hook Gates explorer index", () => {
  it("covers every gate the hooks can print, with a kind that matches its call sites", () => {
    const gates = loadGateIndex();
    expect(gates.length).toBeGreaterThanOrEqual(20);
    for (const gate of gates) {
      expect(gate.summary.length, gate.tag).toBeGreaterThan(20);
      expect(gate.sites.length, gate.tag).toBeGreaterThan(0);
      expect(gate.surfaces.length, gate.tag).toBeGreaterThan(0);
      expect(gate.sites.every((s) => s.kind === gate.kind), gate.tag).toBe(true);
    }
    expect(gates.filter((g) => g.kind === "block").length).toBe(14);
    expect(gates.filter((g) => g.kind === "remind").length).toBe(8);
  });

  it("refuses a gate without a summary, a summary without a gate, and a summary whose kind is wrong", () => {
    const summaries: GateSummaries = { gates: { "H-01": { kind: "block", summary: "No commit to main." }, "H-99": { kind: "block", summary: "Ghost." }, "H-07": { kind: "block", summary: "Dependency changed." } } };
    const { findings } = buildGateIndex([site("H-01", "block", "pre-bash.py"), site("H-07", "remind", "post-write-edit.py"), site("H-03", "block", "pre-bash.py")], events, summaries);
    expect(findings.join("\n")).toMatch(/H-03 has no summary/);
    expect(findings.join("\n")).toMatch(/H-99 has a summary but no call site/);
    expect(findings.join("\n")).toMatch(/H-07 is summarized as block but its call sites remind/);
  });

  it("refuses a gate whose call sites both block and remind, which one summary cannot describe", () => {
    const summaries: GateSummaries = { gates: { "H-01": { kind: "block", summary: "No commit to main." } } };
    const { findings } = buildGateIndex([site("H-01", "block", "pre-bash.py"), site("H-01", "remind", "post-write-edit.py")], events, summaries);
    expect(findings.join("\n")).toMatch(/H-01 both blocks and reminds/);
  });

  it("names where each gate fires from its registered events, and refuses an event it cannot place", () => {
    expect(surfaceOf("PreToolUse (Bash|PowerShell)")).toBe("shell");
    expect(surfaceOf("PreToolUse (Edit|MultiEdit|NotebookEdit)")).toBe("files");
    expect(surfaceOf("PreToolUse (Write)")).toBe("files");
    expect(surfaceOf("PostToolUse (Write|Edit)")).toBe("after-write");
    expect(surfaceOf("git backstop")).toBe("git");
    expect(surfaceOf("SessionStart")).toBeNull();
    const summaries: GateSummaries = { gates: { "H-01": { kind: "block", summary: "No commit to main." } } };
    const { findings } = buildGateIndex([site("H-01", "block", "session-start.py")], new Map([["session-start.py", ["SessionStart"]]]), summaries);
    expect(findings.join("\n")).toMatch(/H-01 fires on SessionStart, which the explorer cannot place/);
  });

  it("orders gates naturally and joins each to the machine parts that enforce it", () => {
    const gates = loadGateIndex();
    const tags = gates.map((g) => g.tag);
    expect(tags.indexOf("H-09")).toBeLessThan(tags.indexOf("H-09b"));
    expect(tags.indexOf("H-09b")).toBeLessThan(tags.indexOf("H-10"));
    const h03 = gates.find((g) => g.tag === "H-03")!;
    expect(h03.enforcers.map((p) => p.id)).toEqual(["guard-bash"]);
    const h20 = gates.find((g) => g.tag === "H-20")!;
    expect(h20.enforcers.map((p) => p.id)).toEqual(["guard-bash"]);
    expect(h20.actsOn.map((p) => p.id)).toContain("git-hooks");
    expect(h03.surfaces).toEqual(["shell"]);
    const h01 = gates.find((g) => g.tag === "H-01")!;
    expect(h01.surfaces).toEqual(["shell", "git"]);
  });
});
