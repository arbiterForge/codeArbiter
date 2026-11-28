import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildGateIndex, loadGateIndex, surfaceOf, type GateSummaries } from "./gate-index";
import { REPO_ROOT } from "../machine/machine-model";
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

/** The hand-written sentences say what a gate refuses or reminds, bound to the facts in the hook
 * source that a reader is most likely to act on. */
describe("gate summaries against the hooks they describe", () => {
  const hooks = join(REPO_ROOT, "plugins", "ca", "hooks");
  const read = (file: string) => readFileSync(join(hooks, file), "utf8");
  const summary = (tag: string) => loadGateIndex().find((gate) => gate.tag === tag)!.summary;
  const literals = (list: string) => [...list.matchAll(/["']([^"']+)["']/g)].map((match) => match[1]);

  it("H-01 names each branch the hook protects, and no branch it does not", () => {
    const shell = /def is_protected_branch\(branch\):[\s\S]*?\.lower\(\) in \(([^)]*)\)/.exec(read("_bashguardlib.py"));
    const git = /def is_protected_branch\(branch\):[\s\S]*?\.lower\(\) in \(([^)]*)\)/.exec(read("git-enforce.py"));
    expect(shell && git).toBeTruthy();
    const names = literals(shell![1]);
    expect(literals(git![1])).toEqual(names);
    for (const name of names) expect(summary("H-01")).toContain(name);
    expect(summary("H-01")).not.toMatch(/default branch/i);
  });

  it("H-12 names the ADR statuses the reminder skips, and keeps the hook's condition", () => {
    const skipped = /status not in \(([^)]*)\)/.exec(read("post-write-edit.py"));
    expect(skipped).toBeTruthy();
    for (const status of literals(skipped![1])) expect(summary("H-12")).toContain(status);
    expect(read("post-write-edit.py")).toContain("If this change contradicts it");
    expect(summary("H-12")).toMatch(/if your change contradicts it/i);
  });

  it("H-09b sends binary content to an audited override, as the hook does", () => {
    const recovery = /def binary_security_recovery\(\):[\s\S]*?\n\n/.exec(read("_hooklib.py"));
    expect(recovery?.[0]).toContain("cmd_ref('override')");
    expect(recovery?.[0]).toContain("the PASS producer cannot approve");
    expect(summary("H-09b")).toMatch(/binary[^.]*override/);
  });

  it("no summary promises that a gate cannot be skipped, bypassed or switched off", () => {
    const promise = /\b(?:cannot|can't|can not) be (?:skipped|bypassed|evaded|fooled|turned off|switched off|disabled|damaged)\b|\bin any spelling\b|\bnever be skipped\b/i;
    for (const gate of loadGateIndex()) expect(gate.summary, gate.tag).not.toMatch(promise);
  });
});
