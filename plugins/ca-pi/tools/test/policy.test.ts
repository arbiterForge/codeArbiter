import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import {
  POLICY_ACTION_CLASSES,
  POLICY_CONSEQUENCES,
  POLICY_DECISIONS,
  POLICY_MODES,
  POLICY_TABLE,
  compilePermissionPolicyDescriptor,
  evaluatePolicy,
  type CompiledPermissionPolicyDescriptor,
  type PolicyActionClass,
  type PolicyDecision,
  type PolicyMode,
} from "../src/policy.ts";
import type { ToolCategory } from "../src/contracts.ts";

const rawDescriptor = Object.freeze({
  toolClasses: Object.freeze({
    bash: "EXEC",
    read: "READ",
    write: "WRITE",
    edit: "EDIT",
    codearbiter_background_bash: "EXEC",
  } satisfies Readonly<Record<string, ToolCategory>>),
  actionClasses: Object.freeze({
    "ca-plan": "planning-write",
    codearbiter_background_bash: "background-launch",
  } satisfies Readonly<Record<string, PolicyActionClass>>),
});

const descriptor = compilePermissionPolicyDescriptor(rawDescriptor);
if (descriptor === undefined) throw new Error("valid policy descriptor did not compile");

const toolForAction = Object.freeze({
  read: "read",
  inspection: "bash",
  "source-write": "write",
  "source-edit": "edit",
  "config-write": "write",
  "config-edit": "edit",
  "planning-write": "ca-plan",
  "shell-mutation": "bash",
  "dependency-change": "bash",
  "network-side-effect": "bash",
  "external-side-effect": "bash",
  "background-launch": "codearbiter_background_bash",
  push: "bash",
  release: "bash",
} satisfies Readonly<Record<PolicyActionClass, string>>);

const expected = Object.freeze({
  execute: Object.freeze({
    read: "allow",
    inspection: "allow",
    "source-write": "ask",
    "source-edit": "ask",
    "config-write": "ask",
    "config-edit": "ask",
    "planning-write": "ask",
    "shell-mutation": "ask",
    "dependency-change": "ask",
    "network-side-effect": "ask",
    "external-side-effect": "ask",
    "background-launch": "ask",
    push: "ask",
    release: "ask",
  }),
  plan: Object.freeze({
    read: "allow",
    inspection: "allow",
    "source-write": "deny",
    "source-edit": "deny",
    "config-write": "deny",
    "config-edit": "deny",
    "planning-write": "allow",
    "shell-mutation": "deny",
    "dependency-change": "deny",
    "network-side-effect": "deny",
    "external-side-effect": "deny",
    "background-launch": "deny",
    push: "deny",
    release: "deny",
  }),
} satisfies Readonly<Record<PolicyMode, Readonly<Record<PolicyActionClass, PolicyDecision>>>>);

function decide(
  compiled: CompiledPermissionPolicyDescriptor,
  mode: unknown,
  tool: unknown,
  actions: unknown,
  cwd: unknown = "C:/repo",
) {
  return evaluatePolicy(compiled, { mode, tool, actions, cwd } as never);
}

describe("Pi mode permission policy", () => {
  test("exports only the approved immutable modes, decisions, actions, and fixed consequences", () => {
    expect(POLICY_MODES).toEqual(["plan", "execute"]);
    expect(POLICY_DECISIONS).toEqual(["allow", "ask", "deny"]);
    expect(POLICY_ACTION_CLASSES).toEqual([
      "read", "inspection", "source-write", "source-edit", "config-write", "config-edit",
      "planning-write", "shell-mutation", "dependency-change", "network-side-effect",
      "external-side-effect", "background-launch", "push", "release",
    ]);
    expect(Object.keys(POLICY_CONSEQUENCES)).toEqual(POLICY_ACTION_CLASSES);
    expect(Object.values(POLICY_CONSEQUENCES).every((value) => typeof value === "string" && value.length > 0)).toBe(true);
    expect(Object.values(POLICY_CONSEQUENCES).every((value) => (
      Buffer.byteLength(value, "utf8") <= 160 && Array.from(value).length <= 120
    ))).toBe(true);
    expect(Object.isFrozen(POLICY_CONSEQUENCES)).toBe(true);
  });

  test("evaluates the exhaustive single-action plan and execute matrix", () => {
    expect(POLICY_TABLE).toEqual(expected);
    for (const mode of POLICY_MODES) {
      for (const actionClass of POLICY_ACTION_CLASSES) {
        expect(decide(descriptor, mode, toolForAction[actionClass], [actionClass]).decision,
          `${mode}/${actionClass}`).toBe(expected[mode][actionClass]);
      }
    }
  });

  test("resolves every valid label conservatively with deny before ask before allow", () => {
    expect(decide(descriptor, "execute", "bash", ["inspection", "shell-mutation"])).toEqual({
      decision: "ask",
      confirmation: {
        actionClasses: ["inspection", "shell-mutation"],
        cwd: "C:/repo",
        consequence: POLICY_CONSEQUENCES["shell-mutation"],
      },
    });
    expect(decide(descriptor, "plan", "bash", ["inspection", "shell-mutation"])).toEqual({ decision: "deny" });
    expect(decide(descriptor, "execute", "bash", ["dependency-change", "network-side-effect"])).toEqual({
      decision: "ask",
      confirmation: {
        actionClasses: ["dependency-change", "network-side-effect"],
        cwd: "C:/repo",
        consequence: POLICY_CONSEQUENCES["network-side-effect"],
      },
    });
    expect(decide(descriptor, "plan", "bash", ["dependency-change", "network-side-effect"])).toEqual({ decision: "deny" });
  });

  test("deduplicates in canonical order and rejects empty, unknown, or oversized label lists", () => {
    expect(decide(descriptor, "execute", "bash", ["shell-mutation", "inspection", "shell-mutation"])).toEqual({
      decision: "ask",
      confirmation: {
        actionClasses: ["inspection", "shell-mutation"],
        cwd: "C:/repo",
        consequence: POLICY_CONSEQUENCES["shell-mutation"],
      },
    });
    for (const actions of [
      [],
      ["inspection", "unknown"],
      ["inspection\u0000"],
      new Set(["inspection"]),
      Array.from({ length: 33 }, () => "inspection"),
      null,
    ]) {
      expect(decide(descriptor, "execute", "bash", actions)).toEqual({ decision: "deny" });
    }
  });

  test("admits planning-write only through descriptor-owned ca-plan", () => {
    for (const tool of ["write", "edit", "bash", "codearbiter_background_bash"]) {
      expect(decide(descriptor, "plan", tool, ["planning-write"]), tool).toEqual({ decision: "deny" });
      expect(decide(descriptor, "execute", tool, ["planning-write"]), tool).toEqual({ decision: "deny" });
    }
    expect(decide(descriptor, "plan", "ca-plan", ["planning-write"])).toEqual({ decision: "allow" });
    expect(decide(descriptor, "execute", "ca-plan", ["planning-write"]).decision).toBe("ask");
  });

  test("requires every exact surface to carry its owned action and prevents broad borrowing", () => {
    for (const incomplete of [
      ["inspection"],
      ["release"],
      ["inspection", "network-side-effect", "dependency-change"],
    ]) {
      expect(decide(descriptor, "execute", "codearbiter_background_bash", incomplete), incomplete.join("+")).toEqual({
        decision: "deny",
      });
    }

    expect(decide(descriptor, "execute", "codearbiter_background_bash", [
      "inspection", "shell-mutation", "dependency-change", "network-side-effect", "background-launch",
    ])).toEqual({
      decision: "ask",
      confirmation: {
        actionClasses: ["inspection", "shell-mutation", "dependency-change", "network-side-effect", "background-launch"],
        cwd: "C:/repo",
        consequence: POLICY_CONSEQUENCES["background-launch"],
      },
    });
    expect(decide(descriptor, "plan", "codearbiter_background_bash", [
      "inspection", "background-launch",
    ])).toEqual({ decision: "deny" });

    for (const borrowed of [
      ["background-launch"],
      ["inspection", "background-launch"],
    ]) {
      expect(decide(descriptor, "execute", "bash", borrowed), borrowed.join("+")).toEqual({ decision: "deny" });
    }
    expect(decide(descriptor, "execute", "ca-plan", ["read"])).toEqual({ decision: "deny" });
    expect(decide(descriptor, "execute", "ca-plan", ["planning-write"]).decision).toBe("ask");
  });

  test("derives confirmation consequences and reflects no caller-controlled consequence data", () => {
    const request = {
      mode: "execute",
      tool: "bash",
      actions: ["shell-mutation"],
      cwd: ` C:/repo\u001b[31m\u061c\u202e\u2066\u200b\r\n${"x".repeat(900)} `,
    } as const;
    const verdict = evaluatePolicy(descriptor, request);
    expect(verdict.decision).toBe("ask");
    if (verdict.decision !== "ask") throw new Error("expected ask verdict");
    expect(Object.keys(verdict)).toEqual(["decision", "confirmation"]);
    expect(Object.keys(verdict.confirmation)).toEqual(["actionClasses", "cwd", "consequence"]);
    expect(verdict.confirmation.consequence).toBe(POLICY_CONSEQUENCES["shell-mutation"]);
    expect(Buffer.byteLength(verdict.confirmation.cwd, "utf8")).toBeLessThanOrEqual(512);
    expect(Array.from(verdict.confirmation.cwd).length).toBeLessThanOrEqual(256);
    expect(verdict.confirmation.cwd).not.toMatch(/[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u);
    expect(JSON.stringify(verdict)).not.toMatch(/command|params|environment|output|prompt|always|grant|caller consequence/iu);
    expect(() => (verdict.confirmation.actionClasses as string[]).push("release")).toThrow(TypeError);
  });

  test("bounds astral cwd facts by UTF-8 bytes and code points without splitting", () => {
    const verdict = decide(descriptor, "execute", "bash", ["shell-mutation"], "😀".repeat(600));
    if (verdict.decision !== "ask") throw new Error("expected ask verdict");
    expect(Buffer.byteLength(verdict.confirmation.cwd, "utf8")).toBeLessThanOrEqual(512);
    expect(Array.from(verdict.confirmation.cwd).length).toBeLessThanOrEqual(256);
    expect(verdict.confirmation.cwd).not.toMatch(/[\ud800-\udbff]$/u);
  });

  test("normalizes a descriptor once into deeply frozen null-prototype data", () => {
    const mutable = {
      toolClasses: { read: "READ" },
      actionClasses: { "ca-plan": "planning-write" },
    };
    const compiled = compilePermissionPolicyDescriptor(mutable);
    expect(compiled).toBeDefined();
    if (compiled === undefined) throw new Error("descriptor did not compile");
    mutable.toolClasses.read = "OTHER";
    mutable.actionClasses["ca-plan"] = "release";
    expect(decide(compiled, "execute", "read", ["read"])).toEqual({ decision: "allow" });
    expect(Object.isFrozen(compiled)).toBe(true);
    expect(Object.isFrozen(compiled.toolClasses)).toBe(true);
    expect(Object.isFrozen(compiled.actionClasses)).toBe(true);
    expect(Object.getPrototypeOf(compiled.toolClasses)).toBeNull();
    expect(Object.getPrototypeOf(compiled.actionClasses)).toBeNull();
  });

  test("descriptor compilation rejects non-exact data, accessors, proxies, inheritance, and bad bounds", () => {
    class DescriptorClass {
      toolClasses = { read: "READ" };
      actionClasses = {};
    }
    const inherited = Object.create({ toolClasses: { read: "READ" } });
    inherited.actionClasses = {};
    const accessor = Object.defineProperty({ actionClasses: {} }, "toolClasses", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    const nestedAccessor = {
      toolClasses: Object.defineProperty({}, "read", {
        enumerable: true,
        get: () => { throw new Error("must not execute"); },
      }),
      actionClasses: {},
    };
    const cases: unknown[] = [
      null,
      [],
      new DescriptorClass(),
      inherited,
      accessor,
      nestedAccessor,
      new Proxy(rawDescriptor, {}),
      { toolClasses: new Proxy({ read: "READ" }, {}), actionClasses: {} },
      { toolClasses: { read: "READ" }, actionClasses: new Proxy({}, {}) },
      { toolClasses: Object.create({ read: "READ" }), actionClasses: {} },
      { toolClasses: { read: "READ" }, actionClasses: Object.create({ "ca-plan": "planning-write" }) },
      { toolClasses: { read: "READ" }, actionClasses: null },
      { toolClasses: { read: "READ" }, actionClasses: {}, unknown: true },
      { toolClasses: { read: "SHELL" }, actionClasses: {} },
      { toolClasses: { "read\u0000": "READ" }, actionClasses: {} },
      { toolClasses: { ["r".repeat(129)]: "READ" }, actionClasses: {} },
      { toolClasses: { read: "READ" }, actionClasses: { "ca-plan": "always-allow" } },
      { toolClasses: { read: "READ" }, actionClasses: { "ca-plan\u061c": "planning-write" } },
      { toolClasses: Object.fromEntries(Array.from({ length: 129 }, (_, index) => [`t${index}`, "READ"])), actionClasses: {} },
    ];
    for (const candidate of cases) expect(compilePermissionPolicyDescriptor(candidate)).toBeUndefined();
  });

  test("descriptor compilation rejects exact actions incompatible with the same tool's broad class", () => {
    expect(compilePermissionPolicyDescriptor({
      toolClasses: { codearbiter_background_bash: "EXEC" },
      actionClasses: { codearbiter_background_bash: "background-launch" },
    })).toBeDefined();
    expect(compilePermissionPolicyDescriptor({
      toolClasses: {},
      actionClasses: { "ca-plan": "planning-write" },
    })).toBeDefined();

    for (const candidate of [
      {
        toolClasses: { codearbiter_background_bash: "READ" },
        actionClasses: { codearbiter_background_bash: "background-launch" },
      },
      {
        toolClasses: { "ca-plan": "EXEC" },
        actionClasses: { "ca-plan": "planning-write" },
      },
      {
        toolClasses: { exact_read: "WRITE" },
        actionClasses: { exact_read: "read" },
      },
    ]) {
      expect(compilePermissionPolicyDescriptor(candidate)).toBeUndefined();
    }
  });

  test("evaluation accepts only exact plain requests and compiled descriptors and never throws", () => {
    const valid = { mode: "execute", tool: "read", actions: ["read"], cwd: "C:/repo" } as const;
    const inherited = Object.create(valid);
    const accessor = Object.defineProperty({ tool: "read", actions: ["read"], cwd: "C:/repo" }, "mode", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    const hostile = [
      null,
      [],
      inherited,
      accessor,
      new Proxy(valid, { ownKeys: () => { throw new Error("proxy"); } }),
      { ...valid, unknown: true },
      ...["consequence", "command", "params", "env", "output", "prompt", "grant"].map((key) => ({
        ...valid,
        [key]: "caller-controlled",
      })),
      { ...valid, mode: "admin" },
      { ...valid, tool: "rogue" },
      { ...valid, tool: "read\u001b[2J" },
      { ...valid, cwd: { toString: () => { throw new Error("cwd"); } } },
      { ...valid, actions: Object.defineProperty([], "0", { get: () => { throw new Error("action"); } }) },
    ];
    for (const request of hostile) {
      expect(() => evaluatePolicy(descriptor, request as never)).not.toThrow();
      expect(evaluatePolicy(descriptor, request as never)).toEqual({ decision: "deny" });
    }
    expect(evaluatePolicy(rawDescriptor as never, valid)).toEqual({ decision: "deny" });
    expect(Object.isFrozen(evaluatePolicy(descriptor, null as never))).toBe(true);
  });

  test("deep-freezes the data-driven policy tables", () => {
    expect(Object.isFrozen(POLICY_MODES)).toBe(true);
    expect(Object.isFrozen(POLICY_DECISIONS)).toBe(true);
    expect(Object.isFrozen(POLICY_ACTION_CLASSES)).toBe(true);
    expect(Object.isFrozen(POLICY_TABLE)).toBe(true);
    expect(Object.isFrozen(POLICY_TABLE.plan)).toBe(true);
    expect(Object.isFrozen(POLICY_TABLE.execute)).toBe(true);
    expect(() => {
      (POLICY_TABLE as unknown as { plan: Record<string, string> }).plan.read = "ask";
    }).toThrow(TypeError);
    expect(POLICY_TABLE.plan.read).toBe("allow");
  });

  test("keeps exact descriptor ownership and embeds it as a declared build global", async () => {
    const [hostsText, buildSource, declarations] = await Promise.all([
      readFile(resolve(import.meta.dirname, "../../../../core/hosts.json"), "utf8"),
      readFile(resolve(import.meta.dirname, "../build.mjs"), "utf8"),
      readFile(resolve(import.meta.dirname, "../src/pi-api.d.ts"), "utf8"),
    ]);
    const document = JSON.parse(hostsText) as { hosts: Array<{
      name: string;
      tool_classes: Record<string, string>;
      permission_policy?: { surfaces: Record<string, string> };
    }> };
    const pi = document.hosts.find((host) => host.name === "pi");
    expect(pi?.permission_policy?.surfaces).toEqual({
      "ca-plan": "planning-write",
      codearbiter_background_bash: "background-launch",
    });
    expect(pi?.tool_classes.codearbiter_background_bash).toBe("EXEC");
    expect(pi?.tool_classes).not.toHaveProperty("ca-plan");
    expect(buildSource).toContain("const permissionPolicySurfaces = piHost?.permission_policy?.surfaces;");
    expect(buildSource).toContain("__CODEARBITER_PI_PERMISSION_POLICY_SURFACES__: JSON.stringify(permissionPolicySurfaces)");
    expect(buildSource).toContain('throw new Error("core/hosts.json has no valid Pi permission_policy.surfaces descriptor")');
    expect(declarations).toContain("declare const __CODEARBITER_PI_PERMISSION_POLICY_SURFACES__: unknown;");
  });
});
