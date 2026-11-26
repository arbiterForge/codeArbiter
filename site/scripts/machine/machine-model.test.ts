import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import {
  REPO_ROOT,
  loadMachine,
  readMachineData,
  readMachineSources,
  validateMachine,
  type MachineData,
  type MachineSources,
} from "./machine-model";

let pristineData: MachineData;
let pristineSources: MachineSources;
beforeAll(() => {
  pristineData = readMachineData();
  pristineSources = readMachineSources(REPO_ROOT);
});

const data = (): MachineData => structuredClone(pristineData);
const sources = (): MachineSources => ({ ...pristineSources, commands: new Map(pristineSources.commands), gates: [...pristineSources.gates] });

describe("the committed machine model", () => {
  it("validates against the current plugin sources with no findings", () => {
    expect(validateMachine(pristineData, pristineSources)).toEqual([]);
  });

  it("loads with the shipped plugin version, every part, and source-derived gate messages", () => {
    const machine = loadMachine();
    const manifest = JSON.parse(readFileSync(join(REPO_ROOT, "plugins/ca/.claude-plugin/plugin.json"), "utf8"));
    expect(machine.version).toBe(manifest.version);
    expect(Object.keys(machine.parts)).toHaveLength(Object.keys(pristineData.parts).length);
    expect(machine.gates["H-02"].kind).toBe("block");
    expect(machine.gates["H-02"].sites.some((site) => site.message.startsWith("Force-push is prohibited"))).toBe(true);
    expect(machine.gates["H-10"].kind).toBe("remind");
    expect(machine.hosts.map((host) => host.name)).toEqual(["claude", "codex", "pi"]);
  });
});

describe("validateMachine refuses drift", () => {
  it("names a hook gate the plugin does not define", () => {
    const d = data();
    d.parts["guard-bash"].what += " It also enforces H-99.";
    expect(validateMachine(d, sources()).join("\n")).toMatch(/guard-bash names gate H-99, which no hook in plugins\/ca\/hooks defines/);
  });

  it("shows a reminder-only gate as a block", () => {
    const d = data();
    d.tours[0].steps.push({ title: "t", text: "x", fx: "call:write;block;H-10;src/app.ts" });
    expect(validateMachine(d, sources()).join("\n")).toMatch(/shows H-10 as a block, but every H-10 call site only reminds/);
  });

  it("keeps a lane for a command that no longer exists", () => {
    const s = sources();
    s.commands.delete("spike");
    expect(validateMachine(data(), s).join("\n")).toMatch(/lane ca-spike names command spike, which core\/surface\/command-routes.json does not define/);
  });

  it("misses a lane for a new core or advanced command", () => {
    const s = sources();
    s.commands.set("newcmd", { visibility: "core", workflow: "change" });
    expect(validateMachine(data(), s).join("\n")).toMatch(/command newcmd \(core, change\) has no lane/);
  });

  it("files a lane under the wrong family or tier", () => {
    const d = data();
    d.parts["ca-fix"].family = "ship";
    d.parts["ca-fix"].tier = "advanced";
    const findings = validateMachine(d, sources()).join("\n");
    expect(findings).toMatch(/lane ca-fix is filed under ship, but fix belongs to change/);
    expect(findings).toMatch(/lane ca-fix is marked advanced, but fix is core/);
  });

  it("links a part, tour stop or scenario that does not exist", () => {
    const d = data();
    d.parts.router.related.push("no-such-part");
    d.tours[0].steps.push({ at: "nowhere", title: "t", text: "x" });
    const findings = validateMachine(d, sources()).join("\n");
    expect(findings).toMatch(/router relates to unknown part no-such-part/);
    expect(findings).toMatch(/stops at unknown part nowhere/);
  });

  it("spells a command the plugin does not ship", () => {
    const d = data();
    d.parts.operator.what += " Run {{frobnicate --now}}.";
    expect(validateMachine(d, sources()).join("\n")).toMatch(/operator spells \{\{frobnicate --now\}\}, but frobnicate is not a command/);
  });

  it("omits a different set of commands for a host than its capabilities say", () => {
    const d = data();
    d.layout.hostOmissions.codex = ["statusline"];
    expect(validateMachine(d, sources()).join("\n")).toMatch(/codex omits statusline, but core\/hosts.json leaves out prune, statusline/);
  });

  it("cites a repository path that does not exist and uses an unknown kind or zone", () => {
    const d = data();
    d.parts.operator.source = ["plugins/ca/no-such-file.md (§1)"];
    d.parts.tokenizer.kind = "Gizmo";
    d.parts.sampler.zone = "attic";
    const findings = validateMachine(d, sources()).join("\n");
    expect(findings).toMatch(/operator cites plugins\/ca\/no-such-file.md, which does not exist/);
    expect(findings).toMatch(/tokenizer has kind Gizmo, which the key does not draw/);
    expect(findings).toMatch(/sampler sits in zone attic, which the layout does not define/);
  });

  it("names an unknown gate in a scenario's catcher tag", () => {
    const d = data();
    const scenario = d.faults.find((fault) => fault.ref)!;
    scenario.tag = "Blocked by H-99";
    expect(validateMachine(d, sources()).join("\n")).toMatch(new RegExp(`scenario ${scenario.id} names gate H-99`));
  });

  it("reports a behavior claim that stopped holding", () => {
    const s = sources();
    const read = s.read;
    s.read = (path) => (path === "plugins/ca/hooks/git-enforce.py"
      ? read(path).replace(/def block\(tag, msg\):\n/, 'def block(tag, msg):\n    _log_gate_event("BLOCK", tag, msg)\n')
      : read(path));
    expect(validateMachine(data(), s).join("\n")).toMatch(/claim git-backstop-not-logged no longer holds/);
  });
});
