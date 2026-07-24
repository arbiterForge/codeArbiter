import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import type { BridgePort, BridgeRequest, BridgeResponse, ExtensionContextPort, ToolCategory } from "../src/contracts.ts";
import {
  EnforcementInstaller,
  appendBackgroundJobAudit,
  bridgeToolResults,
  classifyPermissionActions,
  compileBuiltinPermissionPolicy,
  guardUnknownTools,
  wrapBuiltins,
} from "../src/tool-guard.ts";

type Execute = (
  id: string,
  params: Record<string, unknown>,
  signal?: AbortSignal,
  onUpdate?: unknown,
  context?: unknown,
) => Promise<Record<string, unknown>>;

class FakeBridge implements BridgePort {
  readonly requests: BridgeRequest[] = [];
  constructor(private readonly response: BridgeResponse) {}
  async call(request: BridgeRequest): Promise<BridgeResponse> {
    this.requests.push(structuredClone(request));
    return this.response;
  }
}

class DelayedBridge implements BridgePort {
  readonly requests: BridgeRequest[] = [];
  private release!: () => void;
  readonly entered = new Promise<void>((resolveEntered) => { this.release = resolveEntered; });
  private continue!: () => void;
  private readonly continued = new Promise<void>((resolveContinued) => { this.continue = resolveContinued; });
  constructor(private readonly response: BridgeResponse = { version: 1, outcome: "allow" }) {}
  async call(request: BridgeRequest): Promise<BridgeResponse> {
    this.requests.push(request);
    this.release();
    await this.continued;
    return this.response;
  }
  resume(): void { this.continue(); }
}

class RejectingDelayedBridge implements BridgePort {
  readonly requests: BridgeRequest[] = [];
  private first = true;
  private releaseEntered!: () => void;
  readonly entered = new Promise<void>((resolveEntered) => { this.releaseEntered = resolveEntered; });
  private continueFirst!: () => void;
  private readonly firstContinued = new Promise<void>((resolveContinued) => { this.continueFirst = resolveContinued; });
  constructor(
    private readonly rejection: unknown,
    private readonly laterResponse: BridgeResponse = { version: 1, outcome: "allow" },
  ) {}
  async call(request: BridgeRequest): Promise<BridgeResponse> {
    this.requests.push(structuredClone(request));
    if (!this.first) return this.laterResponse;
    this.first = false;
    this.releaseEntered();
    await this.firstContinued;
    throw this.rejection;
  }
  reject(): void { this.continueFirst(); }
}

class FakePi {
  readonly definitions = new Map<string, { name: string; execute: Execute; [key: string]: unknown }>();
  readonly handlers = new Map<string, Array<(event: Record<string, unknown>, context: ExtensionContextPort) => unknown>>();
  readonly sources = new Map<string, string>();

  registerTool(tool: { name: string; execute: Execute }): void {
    this.definitions.set(tool.name, tool);
    this.sources.set(tool.name, "C:/package/extensions/codearbiter.js");
  }
  on(event: "tool_call" | "tool_result", handler: (event: Record<string, unknown>, context: ExtensionContextPort) => unknown): void {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
  getActiveTools(): string[] { return [...this.sources.keys()]; }
  getAllTools() {
    return [...this.sources].map(([name, path]) => ({ name, sourceInfo: { path } }));
  }
  async emit(event: string, payload: Record<string, unknown>) {
    let result: unknown;
    const context: ExtensionContextPort = {
      cwd: "C:/repo",
      signal: undefined,
      ui: { notify: () => undefined, setStatus: () => undefined },
    };
    for (const handler of this.handlers.get(event) ?? []) result = await handler(payload, context);
    return result;
  }
}

function factories(executions: Array<{ tool: string; params: Record<string, unknown> }>) {
  const create = (name: string) => (_cwd: string) => ({
    name,
    label: name,
    description: name,
    parameters: {},
    execute: async (_id: string, params: Record<string, unknown>) => {
      executions.push({ tool: name, params: structuredClone(params) });
      return { content: [{ type: "text", text: `${name} executed` }], details: undefined, isError: false };
    },
  });
  return { bash: create("bash"), edit: create("edit"), read: create("read"), write: create("write") };
}

const descriptor: Readonly<Record<string, ToolCategory>> = {
  bash: "EXEC",
  edit: "EDIT",
  read: "READ",
  write: "WRITE",
  safe_extension_read: "READ",
};

const permissionPolicy = compileBuiltinPermissionPolicy(descriptor, {});
if (permissionPolicy === undefined) throw new Error("test permission policy did not compile");

function interactiveContext(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    cwd: "C:/repo",
    mode: "tui",
    hasUI: true,
    ui: {
      confirm: async () => true,
    },
    ...overrides,
  };
}

describe("Pi final-wrapper permission decision", () => {
  test("registers the core-descriptor background tool through the enforcement installer", async () => {
    const hosts = JSON.parse(
      await readFile(fileURLToPath(new URL("../../../../core/hosts.json", import.meta.url)), "utf8"),
    ) as { hosts: Array<{ name: string; tool_classes: Record<string, ToolCategory> }> };
    const piDescriptor = hosts.hosts.find((host) => host.name === "pi")!.tool_classes;
    expect(piDescriptor.codearbiter_background_bash).toBe("EXEC");
    const policy = compileBuiltinPermissionPolicy(piDescriptor, {
      codearbiter_background_bash: "background-launch",
    });
    expect(policy).toBeDefined();
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();

    installer.ensureCustomTool(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo",
      name: "codearbiter_background_bash",
      descriptor: piDescriptor,
      factory: () => ({
        name: "codearbiter_background_bash",
        execute: async () => ({ content: [{ type: "text", text: "started" }], isError: false }),
      }),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy: policy!,
    });

    expect([...pi.definitions]).toEqual([
      ["codearbiter_background_bash", expect.objectContaining({ name: "codearbiter_background_bash" })],
    ]);
  });

  test("appends only closed bounded background job facts through the hardened audit sink", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-job-audit-"));
    try {
      await mkdir(resolve(root, ".codearbiter"));
      const row = {
        timestamp: new Date().toISOString(),
        lifecycleId: "b".repeat(64),
        correlation: "a".repeat(64),
        event: "launch" as const,
        id: 1,
        state: "active" as const,
        timeoutMs: null,
      };
      await expect(appendBackgroundJobAudit(root, row)).resolves.toBe(true);
      const text = await readFile(resolve(root, ".codearbiter", "gate-events.log"), "utf8");
      expect(text).toContain("RULE: PI-BACKGROUND-JOB");
      expect(text).toContain("EVENT: launch");
      expect(text).toContain(`LIFECYCLE: ${"b".repeat(64)}`);
      expect(text).toContain("JOB_ID: 1");
      expect(text).not.toContain("command");
      await expect(appendBackgroundJobAudit(root, {
        timestamp: new Date().toISOString(), lifecycleId: row.lifecycleId, correlation: row.correlation,
        event: "terminal", id: 1, state: "completed", exitClass: "success", durationMs: 42, outputBytes: 7,
      })).resolves.toBe(true);
      const terminal = await readFile(resolve(root, ".codearbiter", "gate-events.log"), "utf8");
      expect(terminal).toContain("DURATION_MS: 42");
      expect(terminal).toContain("EXIT_CLASS: success");
      expect(terminal.match(new RegExp(`CORRELATION: ${row.correlation}`, "gu"))).toHaveLength(2);
      await expect(appendBackgroundJobAudit(root, {
        timestamp: new Date().toISOString(), lifecycleId: row.lifecycleId, correlation: row.correlation,
        event: "terminal", id: 1, state: "failed", exitClass: "success", durationMs: 42, outputBytes: 7,
      })).resolves.toBe(false);
      await expect(appendBackgroundJobAudit(root, { ...row, command: "secret" } as never)).resolves.toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
  test("custom background definitions use the same hard-rule, ask, audit, and lifecycle gate", async () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    const bridge = new DelayedBridge();
    const executions: Record<string, unknown>[] = [];
    const audits: unknown[] = [];
    const confirmations: unknown[][] = [];
    const backgroundDescriptor = {
      ...descriptor,
      codearbiter_background_bash: "EXEC" as const,
    };
    const backgroundPolicy = compileBuiltinPermissionPolicy(backgroundDescriptor, {
      codearbiter_background_bash: "background-launch",
    });
    expect(backgroundPolicy).toBeDefined();
    installer.beginBootstrap();
    installer.ensureCustomTool(pi, bridge, {
      cwd: "C:/repo",
      name: "codearbiter_background_bash",
      bridgeToolName: "bash",
      descriptor: backgroundDescriptor,
      factory: () => ({
        name: "codearbiter_background_bash",
        execute: async (_id, params) => {
          executions.push(params);
          return { content: [{ type: "text", text: "started" }], isError: false };
        },
      }),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy: backgroundPolicy!,
      permissionAudit: async (_cwd, row) => { audits.push(row); return true; },
    });
    installer.markReady();
    const raw = { command: "npm install secret-package", label: "fixture" };
    const pending = pi.definitions.get("codearbiter_background_bash")!.execute(
      "background-1",
      raw,
      undefined,
      undefined,
      interactiveContext({
        ui: { confirm: async (...args: unknown[]) => { confirmations.push(args); return true; } },
      }),
    );
    await bridge.entered;
    expect(executions).toEqual([]);
    expect(confirmations).toEqual([]);
    expect(audits).toEqual([]);
    bridge.resume();
    await pending;
    expect(bridge.requests).toHaveLength(1);
    expect(bridge.requests[0]).toMatchObject({ tool: "bash" });
    expect(confirmations).toHaveLength(1);
    expect(audits).toHaveLength(1);
    expect(audits[0]).toMatchObject({
      toolClass: "EXEC",
      actionClasses: ["shell-mutation", "dependency-change", "network-side-effect", "external-side-effect", "background-launch"],
      decision: "approved",
    });
    expect(executions).toEqual([raw]);
    expect(Object.isFrozen(executions[0])).toBe(true);

    installer.deactivate();
    await expect(pi.definitions.get("codearbiter_background_bash")!.execute(
      "background-stale",
      { command: "never" },
      undefined,
      undefined,
      interactiveContext(),
    )).rejects.toThrow("/ca-doctor");
    expect(executions).toEqual([raw]);
  });

  test("rejects a custom bridge alias with a different tool category", () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();

    expect(() => installer.ensureCustomTool(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo",
      name: "codearbiter_background_bash",
      bridgeToolName: "read",
      descriptor: { ...descriptor, codearbiter_background_bash: "EXEC" },
      factory: () => ({
        name: "codearbiter_background_bash",
        execute: async () => ({ content: [], isError: false }),
      }),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    })).toThrow("bridge alias");
  });
  test("classifies frozen built-in facts conservatively and deterministically", () => {
    expect(classifyPermissionActions(permissionPolicy, "read", { path: "src/main.ts" })).toEqual(["read"]);
    expect(classifyPermissionActions(permissionPolicy, "write", { path: "src/main.ts", content: "x" })).toEqual(["source-write"]);
    expect(classifyPermissionActions(permissionPolicy, "edit", { path: ".github/workflows/ci.yml" })).toEqual(["config-edit"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git status --short" })).toEqual(["inspection"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git diff --no-ext-diff --no-textconv HEAD" })).toEqual(["inspection"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git log --no-ext-diff --no-textconv -5" })).toEqual(["inspection"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git show --no-ext-diff --no-textconv HEAD" })).toEqual(["inspection"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git diff --no-ext-diff HEAD" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git log -5" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git show HEAD" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "npm install example" })).toEqual([
      "shell-mutation", "dependency-change", "network-side-effect", "external-side-effect",
    ]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git push origin main" })).toEqual([
      "shell-mutation", "network-side-effect", "external-side-effect", "push",
    ]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "Get-Content (Remove-Item victim.txt)" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git show --ext-diff HEAD" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: "git diff --no-ext-diff --output=patch.txt" })).toEqual(["shell-mutation"]);
    expect(classifyPermissionActions(permissionPolicy, "mystery", {})).toBeUndefined();
    expect(classifyPermissionActions(permissionPolicy, "bash", { command: 7 })).toBeUndefined();
    const background = compileBuiltinPermissionPolicy(
      { ...descriptor, codearbiter_background_bash: "EXEC" },
      { codearbiter_background_bash: "background-launch" },
    );
    expect(background).toBeDefined();
    expect(classifyPermissionActions(background!, "codearbiter_background_bash", { command: "git status" })).toEqual([
      "shell-mutation", "background-launch",
    ]);
    expect(classifyPermissionActions(background!, "codearbiter_background_bash", { command: "npm install example" })).toEqual([
      "shell-mutation", "dependency-change", "network-side-effect", "external-side-effect", "background-launch",
    ]);
  });

  test("hard bridge blocks precede UI and policy classification", async () => {
    const pi = new FakePi();
    const confirmations: unknown[] = [];
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "block", ruleId: "H-20", message: "blocked" }), {
      cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
    });

    await expect(pi.definitions.get("bash")!.execute("blocked", { command: "git push origin main" }, undefined, undefined, interactiveContext({
      ui: { confirm: async (...args: unknown[]) => { confirmations.push(args); return true; } },
    }))).rejects.toThrow("blocked");
    expect(confirmations).toEqual([]);
    expect(executions).toEqual([]);
  });

  test("asks exactly once with bounded closed text and executes the frozen request after durable audit", async () => {
    const pi = new FakePi();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    let executedReference: Record<string, unknown> | undefined;
    const confirmations: unknown[][] = [];
    const audits: unknown[] = [];
    const permissionFactories = factories(executions);
    permissionFactories.bash = () => ({
      name: "bash",
      label: "bash",
      description: "bash",
      parameters: {},
      execute: async (_id, params) => {
        executedReference = params;
        executions.push({ tool: "bash", params: structuredClone(params) });
        return { content: [], details: undefined, isError: false };
      },
    });
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: permissionFactories, wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async (_cwd, row) => { audits.push(row); return true; },
    });
    const raw = { command: "git push https://user:secret@example.invalid/repo main", env: { TOKEN: "secret" } };
    await pi.definitions.get("bash")!.execute("opaque-secret-call", raw, undefined, undefined, interactiveContext({
      ui: { confirm: async (...args: unknown[]) => { confirmations.push(args); return true; } },
    }));

    expect(confirmations).toHaveLength(1);
    expect(confirmations[0]).toEqual([
      "Allow governed operation?",
      expect.stringContaining("shell-mutation, network-side-effect, external-side-effect, push"),
      { timeout: 60_000, signal: undefined },
    ]);
    expect(JSON.stringify(confirmations)).not.toContain("secret");
    expect(executions).toEqual([{ tool: "bash", params: raw }]);
    expect(Object.isFrozen(executedReference)).toBe(true);
    expect(audits).toHaveLength(1);
    expect(audits[0]).toMatchObject({ toolClass: "EXEC", actionClasses: ["shell-mutation", "network-side-effect", "external-side-effect", "push"], decision: "approved" });
    expect(JSON.stringify(audits)).not.toContain("secret");
    expect(JSON.stringify(audits)).not.toContain("C:/repo");
  });

  test("binds confirmation and audit to the wrapper working directory", async () => {
    const pi = new FakePi();
    const auditCwds: string[] = [];
    let message = "";
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: factories([]), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      permissionAudit: async (cwd) => { auditCwds.push(cwd); return true; },
    });
    await pi.definitions.get("write")!.execute("cwd-bound", { path: "src/x.ts", content: "x" }, undefined, undefined, interactiveContext({
      cwd: "C:/attacker-controlled",
      ui: { confirm: async (_title: string, value: string) => { message = value; return true; } },
    }));
    expect(message).toContain("Working directory: C:/repo");
    expect(message).not.toContain("attacker-controlled");
    expect(auditCwds).toEqual(["C:/repo"]);
  });

  test("denies missing or noninteractive UI and fails closed when an approved mutation cannot be audited", async () => {
    for (const context of [undefined, interactiveContext({ mode: "rpc" }), interactiveContext({ hasUI: false })]) {
      const pi = new FakePi();
      const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
      wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
        cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      });
      await expect(pi.definitions.get("write")!.execute("missing-ui", { path: "src/x.ts", content: "x" }, undefined, undefined, context)).rejects.toThrow();
      expect(executions).toEqual([]);
    }

    const pi = new FakePi();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      permissionAudit: async () => false,
    });
    await expect(pi.definitions.get("write")!.execute("audit-failure", { path: "src/x.ts", content: "x" }, undefined, undefined, interactiveContext())).rejects.toThrow("audit");
    expect(executions).toEqual([]);
  });

  test("cancellation, timeout-false, UI errors, and plan-mode mutation execute nothing", async () => {
    for (const confirm of [async () => false, async () => { throw new Error("UI detail"); }]) {
      const pi = new FakePi();
      const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
      const audits: unknown[] = [];
      wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
        cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
        permissionAudit: async (_cwd, row) => { audits.push(row); return true; },
      });
      await expect(pi.definitions.get("write")!.execute("cancelled", { path: "src/x.ts", content: "x" }, undefined, undefined, interactiveContext({
        ui: { confirm },
      }))).rejects.toThrow("cancelled");
      expect(executions).toEqual([]);
      expect(audits).toEqual([expect.objectContaining({ decision: "cancelled" })]);
    }

    const pi = new FakePi();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    let confirmations = 0;
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      getMode: () => "plan",
      permissionAudit: async () => true,
    });
    await expect(pi.definitions.get("edit")!.execute("plan-edit", { path: "src/x.ts" }, undefined, undefined, interactiveContext({
      ui: { confirm: async () => { confirmations += 1; return true; } },
    }))).rejects.toThrow("policy denied");
    expect(confirmations).toBe(0);
    expect(executions).toEqual([]);
  });

  test("a throwing UI accessor denies without leaking its detail", async () => {
    const pi = new FakePi();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      permissionAudit: async () => true,
    });
    const context = {
      cwd: "C:/repo", mode: "tui", hasUI: true,
      get ui(): never { throw new Error("OPENAI_API_KEY=synthetic-secret"); },
    };
    const execution = pi.definitions.get("write")!.execute("ui-accessor", { path: "src/x.ts", content: "x" }, undefined, undefined, context);
    await expect(execution).rejects.toThrow("UI is unavailable");
    await expect(execution).rejects.not.toThrow("synthetic-secret");
    expect(executions).toEqual([]);
  });

  test("revalidates raw arguments, lifecycle, mode, owner, and registry after confirmation", async () => {
    for (const drift of ["args", "lifecycle", "mode", "owner", "inactive"] as const) {
      const pi = new FakePi();
      const bridge = new FakeBridge({ version: 1, outcome: "allow" });
      const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
      const installer = new EnforcementInstaller();
      installer.ensureBootstrap(pi, descriptor);
      installer.beginBootstrap();
      let mode: "execute" | "plan" = "execute";
      installer.ensureBuiltins(pi, bridge, {
        cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
        getMode: () => mode,
        permissionAudit: async () => true,
      });
      installer.markReady();
      const raw = { path: "src/x.ts", content: "x" };
      const confirmation = async () => {
        if (drift === "args") raw.content = "changed";
        if (drift === "lifecycle") installer.deactivate();
        if (drift === "mode") mode = "plan";
        if (drift === "owner") pi.sources.set("write", "C:/foreign/replacement.js");
        if (drift === "inactive") pi.sources.delete("write");
        return true;
      };
      await expect(pi.definitions.get("write")!.execute(`drift-${drift}`, raw, undefined, undefined, interactiveContext({ ui: { confirm: confirmation } }))).rejects.toThrow();
      expect(executions, drift).toEqual([]);
    }
  });

  test("revalidates native execute identity and registry again after the audit await", async () => {
    const pi = new FakePi();
    let originalWrite: { execute: Execute } | undefined;
    let originalCalls = 0;
    let replacementCalls = 0;
    const base = factories([]);
    const guardedFactories = {
      ...base,
      write: () => {
        originalWrite = {
          execute: async () => { originalCalls += 1; return { content: [] }; },
        };
        return { name: "write", execute: originalWrite.execute };
      },
    };
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: guardedFactories, wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      permissionAudit: async () => { pi.sources.delete("write"); return true; },
    });
    await expect(pi.definitions.get("write")!.execute("identity", { path: "src/x.ts", content: "x" }, undefined, undefined, interactiveContext({
      ui: { confirm: async () => {
        originalWrite!.execute = async () => { replacementCalls += 1; return { content: [] }; };
        return true;
      } },
    }))).rejects.toThrow("stale");
    expect(originalCalls).toBe(0);
    expect(replacementCalls).toBe(0);
  });

  test("passes the tool signal to confirmation and never executes an aborted approval", async () => {
    const pi = new FakePi();
    const controller = new AbortController();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    let received: AbortSignal | undefined;
    wrapBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
      cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
      permissionAudit: async () => true,
    });
    await expect(pi.definitions.get("write")!.execute("aborted-confirm", { path: "src/x.ts", content: "x" }, controller.signal, undefined, interactiveContext({
      ui: { confirm: async (_title: string, _message: string, options: { signal?: AbortSignal }) => {
        received = options.signal;
        controller.abort();
        return true;
      } },
    }))).rejects.toThrow("stale");
    expect(received).toBe(controller.signal);
    expect(executions).toEqual([]);
  });

  test("revalidates allow paths after best-effort audit and delegates only stale reads natively", async () => {
    for (const drift of ["lifecycle-read", "lifecycle-abort-read", "lifecycle-exec", "abort", "owner", "native", "args"] as const) {
      const pi = new FakePi();
      const installer = new EnforcementInstaller();
      const controller = new AbortController();
      const trusted: string[] = [];
      const native: string[] = [];
      let bashDefinition: { execute: Execute } | undefined;
      const make = (target: string[], capture = false) => (name: string) => (_cwd: string) => {
        const definition = {
          name,
          execute: async () => { target.push(name); return { content: [] }; },
        };
        if (capture) bashDefinition = definition;
        return definition;
      };
      const trustedFactories = {
        bash: make(trusted, true)("bash"), write: make(trusted)("write"), edit: make(trusted)("edit"), read: make(trusted)("read"),
      };
      const nativeFactories = {
        bash: make(native)("bash"), write: make(native)("write"), edit: make(native)("edit"), read: make(native)("read"),
      };
      installer.beginBootstrap();
      installer.ensureBuiltins(pi, new FakeBridge({ version: 1, outcome: "allow" }), {
        cwd: "C:/repo", descriptor, factories: trustedFactories, nativeFactories,
        wrapperSourcePath: "C:/package/extensions/codearbiter.js", permissionPolicy,
        permissionAudit: async () => {
          if (drift.startsWith("lifecycle")) installer.deactivate();
          if (drift.includes("abort")) controller.abort();
          if (drift === "owner") pi.sources.set("bash", "C:/foreign/replacement.js");
          if (drift === "native") bashDefinition!.execute = async () => { trusted.push("replacement"); return { content: [] }; };
          return true;
        },
      });
      installer.markReady();
      const tool = drift.endsWith("read") ? "read" : "bash";
      const raw = tool === "read" ? { path: "README.md" } : { command: "git status", nested: { value: "stable" } };
      const auditStarted = new Promise<void>((resolveAudit) => {
        const current = pi.definitions.get(tool)!;
        const previous = current.execute;
        current.execute = async (...args) => {
          const result = previous(...args);
          queueMicrotask(() => {
            if (drift === "args") (raw.nested as { value: string }).value = "changed";
            resolveAudit();
          });
          return await result;
        };
      });
      const execution = pi.definitions.get(tool)!.execute(`allow-${drift}`, raw, controller.signal, undefined, interactiveContext());
      await auditStarted;
      if (drift === "lifecycle-read") {
        await expect(execution).resolves.toBeDefined();
        expect(trusted).toEqual([]);
        expect(native).toEqual(["read"]);
      } else {
        await expect(execution).rejects.toThrow();
        expect(trusted).toEqual([]);
        expect(native).toEqual([]);
      }
    }
  });
});

describe("final-execution Pi tool enforcement", () => {
  test("bootstrap guard leaves dormant repositories ungoverned", async () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);

    await expect(pi.emit("tool_call", { toolName: "write", input: {} })).resolves.toBeUndefined();
    await expect(pi.emit("tool_call", { toolName: "mystery", input: {} })).resolves.toBeUndefined();
  });

  test("bootstrap guard blocks every potentially mutating tool until enforcement is ready", async () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);
    installer.beginBootstrap();

    await expect(pi.emit("tool_call", { toolName: "read", input: {} })).resolves.toBeUndefined();
    for (const name of ["bash", "write", "edit", "mystery"]) {
      const refusal = await pi.emit("tool_call", { toolName: name, input: {} });
      expect(refusal).toMatchObject({ block: true, reason: expect.stringContaining("/ca-doctor") });
    }
  });

  test("bootstrap refusal serialization omits an opaque secret-shaped control-bearing tool name", async () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);
    installer.beginBootstrap();
    const opaqueName = "OPENAI_API_KEY=synthetic-secret\r\n\u0000attacker-control";

    const refusal = await pi.emit("tool_call", { toolName: opaqueName, input: {} });
    const serialized = JSON.stringify(refusal);

    expect(refusal).toMatchObject({ block: true, reason: expect.stringContaining("/ca-doctor") });
    expect(serialized).not.toContain("synthetic-secret");
    expect(serialized).not.toContain("attacker-control");
    expect(serialized).not.toContain("OPENAI_API_KEY");
    expect(serialized).not.toContain("\\r");
    expect(serialized).not.toContain("\\n");
    expect(serialized).not.toContain("\\u0000");
  });

  test("bootstrap readiness resets for retry and releases only after explicit completion", async () => {
    const pi = new FakePi();
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);
    installer.beginBootstrap();
    await expect(pi.emit("tool_call", { toolName: "write", input: {} })).resolves.toMatchObject({ block: true });

    installer.markReady();
    await expect(pi.emit("tool_call", { toolName: "write", input: {} })).resolves.toBeUndefined();

    installer.beginBootstrap();
    await expect(pi.emit("tool_call", { toolName: "write", input: {} })).resolves.toMatchObject({ block: true });
    installer.deactivate();
    await expect(pi.emit("tool_call", { toolName: "write", input: {} })).resolves.toBeUndefined();
  });

  test("deactivation makes every partially installed final stage dormant without stale cwd or bridge activity", async () => {
    const partialStages = ["guard", "results", "bash", "write", "edit", "read"] as const;
    for (const stage of partialStages) {
      const pi = new FakePi();
      const bridge = new FakeBridge({ version: 1, outcome: "allow" });
      const executions: Array<{ tool: string; cwd: string }> = [];
      const create = (name: string) => (cwd: string) => ({
        name,
        label: name,
        description: name,
        parameters: {},
        execute: async () => {
          executions.push({ tool: name, cwd });
          return { content: [], details: undefined, isError: false };
        },
      });
      const base = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
      const failureAfter = { guard: "bash", results: "bash", bash: "write", write: "edit", edit: "read", read: undefined } as const;
      const factoriesWithStop = Object.fromEntries(Object.entries(base).map(([name, factory]) => [name, (cwd: string) => {
        if (name === failureAfter[stage]) throw new Error(`${name} partial stop`);
        return factory(cwd);
      }])) as typeof base;
      const installer = new EnforcementInstaller();
      installer.ensureBootstrap(pi, descriptor);
      installer.beginBootstrap();
      installer.ensureGuard(pi, descriptor, "C:/package/extensions/codearbiter.js");
      if (stage !== "guard") installer.ensureResults(pi, bridge, descriptor);
      if (stage !== "guard" && stage !== "results") {
        const install = () => installer.ensureBuiltins(pi, bridge, {
          cwd: "C:/enabled",
          descriptor,
          factories: factoriesWithStop,
          wrapperSourcePath: "C:/package/extensions/codearbiter.js",
        });
        if (stage === "read") install();
        else expect(install).toThrow("partial stop");
      }

      installer.deactivate();
      bridge.requests.length = 0;
      await expect(pi.emit("tool_call", { toolName: "mystery", input: {} })).resolves.toBeUndefined();
      await expect(pi.emit("tool_result", {
        toolName: "write",
        input: { path: "x" },
        content: [],
        isError: false,
      })).resolves.toBeUndefined();
      for (const definition of pi.definitions.values()) {
        await definition.execute("dormant", {}, undefined, undefined, { cwd: "C:/dormant" });
      }
      expect(bridge.requests, stage).toEqual([]);
      expect(executions, stage).toEqual([...pi.definitions.keys()].map((tool) => ({ tool, cwd: "C:/dormant" })));
    }
  });

  test("reactivation cannot reuse an earlier cwd while bootstrap is incomplete or after readiness", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    const executions: Array<{ tool: string; cwd: string }> = [];
    const create = (name: string) => (cwd: string) => ({
      name,
      label: name,
      description: name,
      parameters: {},
      execute: async () => {
        executions.push({ tool: name, cwd });
        return { content: [], details: undefined, isError: false };
      },
    });
    const cwdFactories = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);
    installer.beginBootstrap();
    installer.ensureGuard(pi, descriptor, "C:/package/extensions/codearbiter.js");
    installer.ensureResults(pi, bridge, descriptor);
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/first-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    installer.deactivate();
    installer.beginBootstrap();

    await pi.definitions.get("read")!.execute("bootstrap-read", {}, undefined, undefined, { cwd: "C:/second-enabled" });
    expect(bridge.requests).toEqual([]);
    expect(executions).toEqual([{ tool: "read", cwd: "C:/second-enabled" }]);
    await expect(
      pi.definitions.get("write")!.execute("bootstrap-write", {}, undefined, undefined, { cwd: "C:/second-enabled" }),
    ).rejects.toThrow("/ca-doctor");
    expect(executions).toEqual([{ tool: "read", cwd: "C:/second-enabled" }]);

    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/second-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    executions.length = 0;
    await pi.definitions.get("bash")!.execute("ready-bash", { command: "git status" }, undefined, undefined, { cwd: "C:/second-enabled" });
    expect(bridge.requests.at(-1)).toMatchObject({ cwd: "C:/second-enabled", tool: "bash" });
    expect(executions).toEqual([{ tool: "bash", cwd: "C:/second-enabled" }]);
  });

  test("new-start deactivation immediately blocks retained mutators and delegates retained reads with current untrusted settings", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    const executions: Array<{ mode: string; cwd: string; tool: string }> = [];
    const makeFactories = (mode: string) => {
      const create = (tool: string) => (cwd: string) => ({
        name: tool,
        execute: async () => {
          executions.push({ mode, cwd, tool });
          return { content: [], isError: false };
        },
      });
      return { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
    };
    let nativeMode = "untrusted-first";
    const nativeFactories = {
      bash: (cwd: string) => makeFactories(nativeMode).bash(cwd),
      write: (cwd: string) => makeFactories(nativeMode).write(cwd),
      edit: (cwd: string) => makeFactories(nativeMode).edit(cwd),
      read: (cwd: string) => makeFactories(nativeMode).read(cwd),
    };
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/same",
      descriptor,
      factories: makeFactories("trusted-first"),
      nativeFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    const retainedRead = pi.definitions.get("read")!;
    const retainedWrite = pi.definitions.get("write")!;

    installer.deactivate();
    installer.beginActivation();
    nativeMode = "untrusted-activation-await";
    await retainedRead.execute("activation-await", {}, undefined, undefined, { cwd: "C:/same" });
    expect(executions.at(-1)).toEqual({ mode: "untrusted-activation-await", cwd: "C:/same", tool: "read" });
    await expect(retainedWrite.execute("activation-await", {}, undefined, undefined, { cwd: "C:/same" })).rejects.toThrow("/ca-doctor");
    expect(bridge.requests).toHaveLength(0);

    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/same",
      descriptor,
      factories: makeFactories("trusted-second"),
      nativeFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    await pi.definitions.get("read")!.execute("current", {}, undefined, undefined, { cwd: "C:/same" });
    expect(executions.at(-1)).toEqual({ mode: "trusted-second", cwd: "C:/same", tool: "read" });

    nativeMode = "untrusted-stale-handle";
    const requestCount = bridge.requests.length;
    await retainedRead.execute("stale-read", {}, undefined, undefined, { cwd: "C:/other" });
    expect(executions.at(-1)).toEqual({ mode: "untrusted-stale-handle", cwd: "C:/other", tool: "read" });
    expect(bridge.requests).toHaveLength(requestCount);
    await expect(retainedWrite.execute("stale-write", {}, undefined, undefined, { cwd: "C:/other" })).rejects.toThrow("/ca-doctor");
  });

  test("blocks an old mutator approval after deactivate-reactivate and keeps the new lifecycle operational", async () => {
    const pi = new FakePi();
    const bridge = new DelayedBridge();
    const executions: Array<{ tool: string; cwd: string }> = [];
    const create = (name: string) => (cwd: string) => ({
      name,
      execute: async () => {
        executions.push({ tool: name, cwd });
        return { content: [{ type: "text", text: `${name} native` }], isError: false };
      },
    });
    const cwdFactories = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/old-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async () => true,
    });
    installer.markReady();
    const oldWrite = pi.definitions.get("write")!;
    const pendingOldWrite = oldWrite.execute(
      "old-write",
      { path: "old.txt", content: "old" },
      undefined,
      undefined,
      { cwd: "C:/old-enabled" },
    );
    await bridge.entered;

    installer.deactivate();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/new-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async () => true,
    });
    installer.markReady();
    bridge.resume();

    await expect(pendingOldWrite).rejects.toThrow(/lifecycle|\/ca-doctor/u);
    expect(executions).toEqual([]);
    await pi.definitions.get("write")!.execute(
      "new-write",
      { path: "new.txt", content: "new" },
      undefined,
      undefined,
      interactiveContext({ cwd: "C:/new-enabled" }),
    );
    expect(bridge.requests.map((request) => request.cwd)).toEqual(["C:/old-enabled", "C:/new-enabled"]);
    expect(executions).toEqual([{ tool: "write", cwd: "C:/new-enabled" }]);
  });

  test("delegates a stale read natively from the execution context without bridge decoration after deactivate", async () => {
    const pi = new FakePi();
    const bridge = new DelayedBridge({
      version: 1,
      outcome: "notice",
      context: "STALE GOVERNANCE NOTICE",
    });
    const executions: Array<{ tool: string; cwd: string }> = [];
    const create = (name: string) => (cwd: string) => ({
      name,
      execute: async () => {
        executions.push({ tool: name, cwd });
        return { content: [{ type: "text", text: `${name} native` }], isError: false };
      },
    });
    const cwdFactories = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/old-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async () => true,
    });
    installer.markReady();
    const pendingRead = pi.definitions.get("read")!.execute(
      "old-read",
      { path: "README.md" },
      undefined,
      undefined,
      { cwd: "C:/current-dormant" },
    );
    await bridge.entered;

    installer.deactivate();
    bridge.resume();

    const result = await pendingRead;
    expect(executions).toEqual([{ tool: "read", cwd: "C:/current-dormant" }]);
    expect(JSON.stringify(result)).not.toContain("STALE GOVERNANCE NOTICE");
  });

  test("suppresses stale bridge decoration when deactivation happens during native execution", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({
      version: 1,
      outcome: "notice",
      context: "STALE POST-NATIVE NOTICE",
    });
    let nativeEntered!: () => void;
    const enteredNative = new Promise<void>((resolveEntered) => { nativeEntered = resolveEntered; });
    let resumeNative!: () => void;
    const nativeContinued = new Promise<void>((resolveContinued) => { resumeNative = resolveContinued; });
    const baseFactories = factories([]);
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/enabled",
      descriptor,
      factories: {
        ...baseFactories,
        read: () => ({
          name: "read",
          execute: async () => {
            nativeEntered();
            await nativeContinued;
            return { content: [{ type: "text", text: "native read" }], isError: false };
          },
        }),
      },
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    const pendingRead = pi.definitions.get("read")!.execute("read", { path: "README.md" });
    await enteredNative;

    installer.deactivate();
    resumeNative();

    const result = await pendingRead;
    expect(result).toMatchObject({ content: [{ type: "text", text: "native read" }] });
    expect(JSON.stringify(result)).not.toContain("STALE POST-NATIVE NOTICE");
  });

  test("suppresses a stale post-result notice across deactivate-reactivate and handles the new lifecycle", async () => {
    const pi = new FakePi();
    const bridge = new DelayedBridge({
      version: 1,
      outcome: "warn",
      message: "post bridge warning",
    });
    const warnings: string[] = [];
    const context: ExtensionContextPort = {
      cwd: "C:/old-enabled",
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => warnings.push(message) },
    };
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureResults(pi, bridge, descriptor);
    installer.markReady();
    const resultHandler = pi.handlers.get("tool_result")![0]!;
    const event = {
      toolName: "write",
      input: { path: "old.txt" },
      content: [{ type: "text", text: "native write detail" }],
      isError: false,
    };
    const pendingOldResult = resultHandler(event, context);
    await bridge.entered;

    installer.deactivate();
    installer.beginBootstrap();
    installer.markReady();
    bridge.resume();

    await expect(pendingOldResult).resolves.toBeUndefined();
    expect(warnings).toEqual([]);
    const newResult = await resultHandler({ ...event, input: { path: "new.txt" } }, { ...context, cwd: "C:/new-enabled" });
    expect(newResult).toMatchObject({ content: [
      { type: "text", text: "native write detail" },
      { type: "text", text: expect.stringMatching(/codearbiter:pi-tool-result:[a-f0-9]{64}/u) },
    ] });
    expect(warnings).toEqual(["post bridge warning"]);
  });

  test("turns an old mutator bridge rejection into a fixed lifecycle block after deactivate-reactivate", async () => {
    const rawBridgeError = new Error("raw old-lifecycle bridge detail");
    const bridge = new RejectingDelayedBridge(rawBridgeError);
    const pi = new FakePi();
    const executions: Array<{ tool: string; cwd: string }> = [];
    const create = (name: string) => (cwd: string) => ({
      name,
      execute: async () => {
        executions.push({ tool: name, cwd });
        return { content: [{ type: "text", text: `${name} native` }], isError: false };
      },
    });
    const cwdFactories = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
    const installer = new EnforcementInstaller();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/old-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    const pendingOldWrite = pi.definitions.get("write")!.execute(
      "old-write",
      { path: "old.txt", content: "old" },
      undefined,
      undefined,
      { cwd: "C:/old-enabled" },
    );
    await bridge.entered;

    installer.deactivate();
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/new-enabled",
      descriptor,
      factories: cwdFactories,
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async () => true,
    });
    installer.markReady();
    bridge.reject();

    let oldFailure: unknown;
    try { await pendingOldWrite; } catch (error) { oldFailure = error; }
    expect(oldFailure).toBeInstanceOf(Error);
    expect((oldFailure as Error).message).toContain("lifecycle changed");
    expect((oldFailure as Error).message).toContain("/ca-doctor");
    expect((oldFailure as Error).message).not.toContain("raw old-lifecycle bridge detail");
    expect(executions).toEqual([]);

    await pi.definitions.get("write")!.execute(
      "new-write",
      { path: "new.txt", content: "new" },
      undefined,
      undefined,
      interactiveContext({ cwd: "C:/new-enabled" }),
    );
    expect(executions).toEqual([{ tool: "write", cwd: "C:/new-enabled" }]);
  });

  test("delegates a stale rejected read once from current cwd after deactivate or reactivation", async () => {
    for (const transition of ["deactivate", "reactivate"] as const) {
      const rawCancellation = new DOMException(`raw stale ${transition} cancellation`, "AbortError");
      const bridge = new RejectingDelayedBridge(rawCancellation);
      const pi = new FakePi();
      const executions: Array<{ tool: string; cwd: string }> = [];
      const delegatedSignals: Array<AbortSignal | undefined> = [];
      const create = (name: string) => (cwd: string) => ({
        name,
        execute: async (_id: string, _params: Record<string, unknown>, signal?: AbortSignal) => {
          executions.push({ tool: name, cwd });
          delegatedSignals.push(signal);
          return { content: [{ type: "text", text: `${name} native` }], isError: false };
        },
      });
      const cwdFactories = { bash: create("bash"), write: create("write"), edit: create("edit"), read: create("read") };
      const installer = new EnforcementInstaller();
      installer.beginBootstrap();
      installer.ensureBuiltins(pi, bridge, {
        cwd: "C:/old-enabled",
        descriptor,
        factories: cwdFactories,
        wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      });
      installer.markReady();
      const originalSignal = new AbortController().signal;
      const pendingOldRead = pi.definitions.get("read")!.execute(
        "old-read",
        { path: "README.md" },
        originalSignal,
        undefined,
        { cwd: `C:/current-${transition}` },
      );
      await bridge.entered;

      installer.deactivate();
      if (transition === "reactivate") {
        installer.beginBootstrap();
        installer.ensureBuiltins(pi, bridge, {
          cwd: "C:/new-enabled",
          descriptor,
          factories: cwdFactories,
          wrapperSourcePath: "C:/package/extensions/codearbiter.js",
        });
        installer.markReady();
      }
      bridge.reject();

      const result = await pendingOldRead;
      expect(executions).toEqual([{ tool: "read", cwd: `C:/current-${transition}` }]);
      expect(delegatedSignals).toEqual([originalSignal]);
      expect(JSON.stringify(result)).not.toContain(`raw stale ${transition} cancellation`);
      if (transition === "reactivate") {
        await pi.definitions.get("read")!.execute(
          "new-read",
          { path: "README.md" },
          undefined,
          undefined,
          { cwd: "C:/new-enabled" },
        );
        expect(executions.at(-1)).toEqual({ tool: "read", cwd: "C:/new-enabled" });
      }
    }
  });

  test("suppresses stale rejected result effects after deactivate or reactivation", async () => {
    for (const transition of ["deactivate", "reactivate"] as const) {
      for (const toolName of ["write", "edit"] as const) {
      const bridge = new RejectingDelayedBridge(
        new Error(`raw stale ${transition} ${toolName} result detail`),
        { version: 1, outcome: "warn", message: "new lifecycle warning" },
      );
      const pi = new FakePi();
      const warnings: string[] = [];
      const context: ExtensionContextPort = {
        cwd: "C:/old-enabled",
        signal: undefined,
        ui: { setStatus: () => undefined, notify: (message) => warnings.push(message) },
      };
      const installer = new EnforcementInstaller();
      installer.beginBootstrap();
      installer.ensureResults(pi, bridge, descriptor);
      installer.markReady();
      const resultHandler = pi.handlers.get("tool_result")![0]!;
      const event = {
        toolName,
        input: { path: "old.txt" },
        content: [{ type: "text", text: "native write detail" }],
        isError: false,
      };
      const pendingOldResult = resultHandler(event, context);
      await bridge.entered;

      installer.deactivate();
      if (transition === "reactivate") {
        installer.beginBootstrap();
        installer.markReady();
      }
      bridge.reject();

      await expect(pendingOldResult).resolves.toBeUndefined();
      expect(warnings).toEqual([]);
      if (transition === "reactivate") {
        const newResult = await resultHandler(
          { ...event, input: { path: "new.txt" } },
          { ...context, cwd: "C:/new-enabled" },
        );
        expect(newResult).toMatchObject({ content: [
          { type: "text", text: "native write detail" },
          { type: "text", text: expect.stringMatching(/codearbiter:pi-tool-result:[a-f0-9]{64}/u) },
        ] });
        expect(warnings).toEqual(["new lifecycle warning"]);
      }
      }
    }
  });

  test("propagates same-generation wrapper and result-handler bridge rejections unchanged", async () => {
    const wrapperFailure = new Error("current wrapper bridge failure");
    const wrapperBridge = new RejectingDelayedBridge(wrapperFailure);
    const wrapperPi = new FakePi();
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    const wrapperInstaller = new EnforcementInstaller();
    wrapperInstaller.beginBootstrap();
    wrapperInstaller.ensureBuiltins(wrapperPi, wrapperBridge, {
      cwd: "C:/enabled",
      descriptor,
      factories: factories(executions),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    wrapperInstaller.markReady();
    const pendingWrite = wrapperPi.definitions.get("write")!.execute("write", { path: "x", content: "x" });
    await wrapperBridge.entered;
    wrapperBridge.reject();
    await expect(pendingWrite).rejects.toBe(wrapperFailure);
    expect(executions).toEqual([]);

    const resultFailure = new Error("current result bridge failure");
    const resultBridge = new RejectingDelayedBridge(resultFailure);
    const resultPi = new FakePi();
    const warnings: string[] = [];
    const resultInstaller = new EnforcementInstaller();
    resultInstaller.beginBootstrap();
    resultInstaller.ensureResults(resultPi, resultBridge, descriptor);
    resultInstaller.markReady();
    const resultHandler = resultPi.handlers.get("tool_result")![0]!;
    const pendingResult = resultHandler({
      toolName: "edit",
      input: { path: "x" },
      content: [{ type: "text", text: "native edit detail" }],
      isError: false,
    }, {
      cwd: "C:/enabled",
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => warnings.push(message) },
    });
    await resultBridge.entered;
    resultBridge.reject();
    await expect(pendingResult).rejects.toBe(resultFailure);
    expect(warnings).toEqual([]);
  });

  for (const [tool, input] of [
    ["bash", { command: "git status", metadata: { value: "judged" } }],
    ["write", { path: "x", content: "judged", metadata: { value: "judged" } }],
    ["edit", { path: "x", edits: [{ oldText: "a", newText: "judged" }] }],
  ] as const) {
    test(`${tool} blocks when raw final arguments drift after bridge judgment`, async () => {
      const pi = new FakePi();
      const bridge = new DelayedBridge();
      const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
      wrapBuiltins(pi, bridge, {
        cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js",
        permissionPolicy, permissionAudit: async () => true,
      });
      const mutable = structuredClone(input) as Record<string, unknown>;
      const pending = pi.definitions.get(tool)!.execute("delayed", mutable, undefined, undefined, interactiveContext());
      await bridge.entered;
      if (tool === "edit") (mutable.edits as Array<Record<string, unknown>>)[0]!.newText = "mutated";
      else (mutable.metadata as Record<string, unknown>).value = "mutated";
      bridge.resume();
      await expect(pending).rejects.toThrow("stale");
      expect(executions).toEqual([]);
    });
  }

  test("cyclic mutating parameters fail closed before bridge or executor", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, bridge, { cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js" });
    const cyclic: Record<string, unknown> = { command: "true" };
    cyclic.secret = "OPENAI_API_KEY=synthetic-secret";
    cyclic.self = cyclic;
    const execution = pi.definitions.get("bash")!.execute("cycle", cyclic);
    await expect(execution).rejects.toThrow("/ca-doctor");
    await expect(execution).rejects.not.toThrow("synthetic-secret");
    expect(bridge.requests).toEqual([]);
    expect(executions).toEqual([]);
  });

  test("approved snapshots preserve ordinary builtin object and array prototypes", async () => {
    const pi = new FakePi();
    let judged: BridgeRequest | undefined;
    const bridge: BridgePort = {
      call: async (request) => { judged = request; return { version: 1, outcome: "allow" }; },
    };
    let executed: Record<string, unknown> | undefined;
    const base = factories([]);
    const snapshotFactories = {
      ...base,
      bash: (_cwd: string) => ({
        name: "bash", label: "bash", description: "bash", parameters: {},
        execute: async (_id: string, params: Record<string, unknown>) => {
          executed = params;
          return { content: [], details: undefined, isError: false };
        },
      }),
    };
    wrapBuiltins(pi, bridge, {
      cwd: "C:/repo", descriptor, factories: snapshotFactories, wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy, permissionAudit: async () => true,
    });
    await pi.definitions.get("bash")!.execute("plain", { command: "true", nested: { values: [1, { ok: true }] }, }, undefined, undefined, interactiveContext());
    const approved = judged!.input as Record<string, unknown>;
    expect(executed).toBe(approved);
    expect(Object.getPrototypeOf(approved)).toBe(Object.prototype);
    expect(Object.getPrototypeOf(approved.nested as object)).toBe(Object.prototype);
    expect(Array.isArray((approved.nested as { values: unknown }).values)).toBe(true);
    expect(Object.getPrototypeOf(((approved.nested as { values: unknown[] }).values)[1] as object)).toBe(Object.prototype);
  });

  test("bridge blocks become sanitized failed Pi tool calls without executing", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "block", ruleId: "H-19", message: "OPENAI_API_KEY=synthetic-secret" });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, bridge, { cwd: "C:/repo", descriptor, factories: factories(executions), wrapperSourcePath: "C:/package/extensions/codearbiter.js" });
    const execution = pi.definitions.get("write")!.execute("blocked", { path: "x", content: "x" });
    await expect(execution).rejects.toThrow();
    await expect(execution).rejects.not.toThrow("synthetic-secret");
    expect(executions).toEqual([]);
  });

  test("enforcement installation is retry-safe across guard and every builtin factory stage", () => {
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    for (const failure of ["guard", "bash", "write", "edit", "read"] as const) {
      const pi = new FakePi();
      const originalOn = pi.on.bind(pi);
      let guardFailed = false;
      if (failure === "guard") {
        pi.on = ((event, handler) => {
          if (event === "tool_call" && !guardFailed) { guardFailed = true; throw new Error("guard failure"); }
          originalOn(event, handler);
        }) as typeof pi.on;
      }
      const counts = new Map<string, number>();
      let failed = false;
      const base = factories([]);
      const staged = Object.fromEntries(Object.entries(base).map(([name, factory]) => [name, (cwd: string) => {
        counts.set(name, (counts.get(name) ?? 0) + 1);
        if (name === failure && !failed) { failed = true; throw new Error(`${name} failure`); }
        return factory(cwd);
      }])) as ReturnType<typeof factories>;
      const installer = new EnforcementInstaller();
      const options = { cwd: "C:/repo", descriptor, factories: staged, wrapperSourcePath: "C:/package/extensions/codearbiter.js" };
      expect(() => { installer.ensureGuard(pi, descriptor, options.wrapperSourcePath); installer.ensureResults(pi, bridge, descriptor); installer.ensureBuiltins(pi, bridge, options); }).toThrow();
      installer.ensureGuard(pi, descriptor, options.wrapperSourcePath);
      installer.ensureResults(pi, bridge, descriptor);
      installer.ensureBuiltins(pi, bridge, options);
      expect(pi.handlers.get("tool_call")).toHaveLength(1);
      expect(pi.handlers.get("tool_result")).toHaveLength(1);
      expect(pi.definitions.size).toBe(4);
      for (const name of ["bash", "write", "edit", "read"]) {
        expect(counts.get(name)).toBe(name === failure ? 2 : 1);
      }
    }
  });

  test("enforcement installation retries each failed builtin registration without duplicates", () => {
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    for (const failure of ["bash", "write", "edit", "read"] as const) {
      const pi = new FakePi();
      const originalRegister = pi.registerTool.bind(pi);
      let failed = false;
      pi.registerTool = ((tool) => {
        if (tool.name === failure && !failed) { failed = true; throw new Error(`${failure} registration failure`); }
        originalRegister(tool);
      }) as typeof pi.registerTool;
      const installer = new EnforcementInstaller();
      const options = { cwd: "C:/repo", descriptor, factories: factories([]), wrapperSourcePath: "C:/package/extensions/codearbiter.js" };
      installer.ensureGuard(pi, descriptor, options.wrapperSourcePath);
      installer.ensureResults(pi, bridge, descriptor);
      expect(() => installer.ensureBuiltins(pi, bridge, options)).toThrow();
      installer.ensureBuiltins(pi, bridge, options);
      expect(pi.handlers.get("tool_call")).toHaveLength(1);
      expect(pi.handlers.get("tool_result")).toHaveLength(1);
      expect([...pi.definitions.keys()]).toEqual(["bash", "write", "edit", "read"]);
    }
  });

  test("judges final args inside the execution override", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "block", ruleId: "H-19", message: "blocked" });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories(executions),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    const finalInput = { command: "git commit --no-verify" };
    await expect(pi.definitions.get("bash")!.execute("call-1", finalInput)).rejects.toThrow("blocked");
    expect(bridge.requests.at(-1)?.input).toEqual(finalInput);
    expect(executions).toEqual([]);
  });

  test("read bridge warnings delegate once and append one visible warning", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "warn", ruleId: "PI-BRIDGE", message: "run /ca-doctor" });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories(executions),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    const result = await pi.definitions.get("read")!.execute("call-2", { path: "README.md" });
    expect(executions).toEqual([{ tool: "read", params: { path: "README.md" } }]);
    expect(JSON.stringify(result).match(/run \/ca-doctor/gu)).toHaveLength(1);
  });

  test("appends governed pre-read context to the native result without changing native execution", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({
      version: 1,
      outcome: "notice",
      context: "ADR-0015 (Model-visible read contract) governs this file",
    });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    const nativeFactories = factories(executions);
    wrapBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: {
        ...nativeFactories,
        read: () => ({
          name: "read",
          execute: async (_id: string, params: Record<string, unknown>) => {
            executions.push({ tool: "read", params: structuredClone(params) });
            return {
              content: [{ type: "text", text: "native read content" }],
              details: { path: "README.md", truncated: false },
              isError: false,
            };
          },
        }),
      },
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });

    const result = await pi.definitions.get("read")!.execute(
      "governed-read",
      { path: "README.md" },
      undefined,
      undefined,
      { sessionManager: { getSessionId: () => "pi-session-123" } },
    );

    expect(bridge.requests).toEqual([expect.objectContaining({
      event: "tool_call",
      sessionId: "pi-session-123",
      tool: "read",
      input: { path: "README.md" },
    })]);
    expect(executions).toEqual([{ tool: "read", params: { path: "README.md" } }]);
    expect(result).toMatchObject({
      details: { path: "README.md", truncated: false },
      isError: false,
      content: [
        { type: "text", text: "native read content" },
        {
          type: "text",
          text: expect.stringContaining("ADR-0015 (Model-visible read contract) governs this file"),
          codearbiter: { kind: "codearbiter-notice", version: 1 },
        },
      ],
    });
    expect(JSON.stringify(result).match(/ADR-0015/gu)).toHaveLength(1);
  });

  test("uses a stable private fallback for malformed Pi session identities and rotates it with the lifecycle", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "allow" });
    const installer = new EnforcementInstaller();
    installer.ensureBootstrap(pi, descriptor);
    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories([]),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();

    const read = pi.definitions.get("read")!;
    await read.execute("missing-id", { path: "README.md" });
    await read.execute("blank-id", { path: "README.md" }, undefined, undefined, {
      sessionManager: { getSessionId: () => "   " },
    });
    await read.execute("oversized-id", { path: "README.md" }, undefined, undefined, {
      sessionManager: { getSessionId: () => "x".repeat(1_025) },
    });
    const firstLifecycle = bridge.requests.map((request) => request.sessionId);
    expect(firstLifecycle[0]).toEqual(expect.any(String));
    expect(firstLifecycle[0]).not.toBe("");
    expect(firstLifecycle[0]!.length).toBeLessThanOrEqual(1_024);
    expect(firstLifecycle).toEqual([firstLifecycle[0], firstLifecycle[0], firstLifecycle[0]]);

    installer.deactivate();
    let dormantGetterCalls = 0;
    await read.execute("dormant-id", { path: "README.md" }, undefined, undefined, {
      sessionManager: { getSessionId: () => { dormantGetterCalls += 1; return "dormant-session"; } },
    });
    expect(dormantGetterCalls).toBe(0);
    expect(bridge.requests).toHaveLength(3);

    installer.beginBootstrap();
    installer.ensureBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories([]),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
    });
    installer.markReady();
    const refreshedRead = pi.definitions.get("read")!;
    await refreshedRead.execute("throwing-id", { path: "README.md" }, undefined, undefined, {
      sessionManager: { getSessionId: () => { throw new Error("unavailable"); } },
    });
    const secondLifecycle = bridge.requests.at(-1)!.sessionId;
    expect(secondLifecycle).toEqual(expect.any(String));
    expect(secondLifecycle).not.toBe(firstLifecycle[0]);

    await refreshedRead.execute("native-id", { path: "README.md" }, undefined, undefined, {
      sessionManager: { getSessionId: () => "pi-native-session" },
    });
    expect(bridge.requests.at(-1)!.sessionId).toBe("pi-native-session");
  });

  test("mutating bridge warnings remain advisory and proceed through confirmation", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "warn", ruleId: "PI-BRIDGE", message: "degraded" });
    const executions: Array<{ tool: string; params: Record<string, unknown> }> = [];
    wrapBuiltins(pi, bridge, {
      cwd: "C:/repo",
      descriptor,
      factories: factories(executions),
      wrapperSourcePath: "C:/package/extensions/codearbiter.js",
      permissionPolicy,
      permissionAudit: async () => true,
    });
    const result = await pi.definitions.get("write")!.execute("call-3", { path: "x", content: "x" }, undefined, undefined, interactiveContext());
    expect(executions).toEqual([{ tool: "write", params: { path: "x", content: "x" } }]);
    expect(JSON.stringify(result)).toContain("degraded");
  });

  test("blocks an unknown active tool until the descriptor classifies it", async () => {
    const pi = new FakePi();
    pi.sources.set("mystery", "C:/foreign/extension.js");
    guardUnknownTools(pi, descriptor, "C:/package/extensions/codearbiter.js");
    const result = await pi.emit("tool_call", { toolName: "mystery", input: {} });
    expect(result).toMatchObject({ block: true });
    expect(JSON.stringify(result)).toContain("/ca-doctor");
  });

  test("ready-state unknown refusal serialization omits an opaque secret-shaped control-bearing tool name", async () => {
    const pi = new FakePi();
    const opaqueName = "OPENAI_API_KEY=synthetic-secret\r\n\u0000ready-attacker-control";
    pi.sources.set(opaqueName, "C:/foreign/extension.js");
    guardUnknownTools(pi, descriptor, "C:/package/extensions/codearbiter.js");

    const refusal = await pi.emit("tool_call", { toolName: opaqueName, input: {} });
    const serialized = JSON.stringify(refusal);

    expect(refusal).toMatchObject({ block: true, reason: expect.stringContaining("/ca-doctor") });
    expect(serialized).not.toContain("synthetic-secret");
    expect(serialized).not.toContain("ready-attacker-control");
    expect(serialized).not.toContain("OPENAI_API_KEY");
    expect(serialized).not.toContain("\\r");
    expect(serialized).not.toContain("\\n");
    expect(serialized).not.toContain("\\u0000");
  });

  test("blocks an earlier-loaded competing definition that wins Pi's first-registration order", async () => {
    const pi = new FakePi();
    pi.sources.set("write", "C:/foreign/override.js");
    guardUnknownTools(pi, descriptor, "C:/package/extensions/codearbiter.js");
    const result = await pi.emit("tool_call", { toolName: "write", input: { path: "x", content: "x" } });
    expect(result).toMatchObject({ block: true });
    expect(JSON.stringify(result)).toContain("source drift");
  });

  test("allows a descriptor-declared external read without a mutation wrapper", async () => {
    const pi = new FakePi();
    pi.sources.set("safe_extension_read", "C:/foreign/reader.js");
    guardUnknownTools(pi, descriptor, "C:/package/extensions/codearbiter.js");
    await expect(pi.emit("tool_call", { toolName: "safe_extension_read", input: {} })).resolves.toBeUndefined();
  });

  test("routes post-write results through the bridge and appends a bounded warning without replacing native content", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "warn", ruleId: "PI-BRIDGE", message: "post bridge failed; run /ca-doctor" });
    const warnings: string[] = [];
    bridgeToolResults(pi, bridge, descriptor);
    const context: ExtensionContextPort = {
      cwd: "C:/repo",
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => warnings.push(message) },
    };
    let result: unknown;
    for (const handler of pi.handlers.get("tool_result") ?? []) {
      result = await handler({
        toolName: "write",
        input: { path: "x" },
        content: [{ type: "text", text: "native write detail" }],
        isError: false,
      }, context);
    }
    expect(result).toMatchObject({ content: [
      { type: "text", text: "native write detail" },
      { type: "text", text: expect.stringMatching(/codearbiter:pi-tool-result:[a-f0-9]{64}/u) },
    ] });
    expect(bridge.requests.at(-1)).toMatchObject({
      event: "tool_result",
      tool: "write",
      result: { content: [{ type: "text", text: "native write detail" }], isError: false },
    });
    expect(warnings).toEqual(["post bridge failed; run /ca-doctor"]);
  });

  test("does not fabricate a post-result READ bridge route", async () => {
    const pi = new FakePi();
    const bridge = new FakeBridge({ version: 1, outcome: "notice", context: "generated read context" });
    bridgeToolResults(pi, bridge, descriptor);
    const context: ExtensionContextPort = {
      cwd: "C:/repo",
      signal: undefined,
      ui: { setStatus: () => undefined, notify: () => undefined },
    };
    let result: unknown;
    for (const handler of pi.handlers.get("tool_result") ?? []) {
      result = await handler({
        toolName: "read",
        input: { path: "README.md" },
        content: [{ type: "text", text: "native read detail" }],
        isError: false,
      }, context);
    }
    expect(bridge.requests).toEqual([]);
    expect(result).toBeUndefined();
  });

  test("consumes Pi tool classes directly from the generated host descriptor", async () => {
    const hosts = JSON.parse(await readFile(fileURLToPath(new URL("../../../../core/hosts.json", import.meta.url)), "utf8")) as {
      hosts: Array<{ name: string; tool_classes: Record<string, ToolCategory> }>;
    };
    const piDescriptor = hosts.hosts.find((host) => host.name === "pi")!.tool_classes;
    const pi = new FakePi();
    pi.sources.set("descriptor_rogue", "C:/foreign/tool.js");
    guardUnknownTools(pi, piDescriptor, "C:/package/extensions/codearbiter.js");
    const result = await pi.emit("tool_call", { toolName: "descriptor_rogue", input: {} });
    expect(result).toMatchObject({ block: true });
  });

  test("allows only the parent-extension-owned Pi dispatch executable", async () => {
    const hosts = JSON.parse(await readFile(fileURLToPath(new URL("../../../../core/hosts.json", import.meta.url)), "utf8")) as {
      hosts: Array<{ name: string; tool_classes: Record<string, ToolCategory> }>;
    };
    const piDescriptor = hosts.hosts.find((host) => host.name === "pi")!.tool_classes;
    expect(piDescriptor.codearbiter_dispatch).toBe("EXEC");

    const pi = new FakePi();
    pi.sources.set("codearbiter_dispatch", "C:/package/extensions/codearbiter.js");
    guardUnknownTools(pi, piDescriptor, "C:/package/extensions/codearbiter.js");
    await expect(pi.emit("tool_call", { toolName: "codearbiter_dispatch", input: {} })).resolves.toBeUndefined();

    pi.sources.set("codearbiter_dispatch", "C:/foreign/replacement.js");
    const replaced = await pi.emit("tool_call", { toolName: "codearbiter_dispatch", input: {} });
    expect(replaced).toMatchObject({ block: true, reason: expect.stringContaining("source drift") });
  });

  test("allows only the parent-extension-owned farm preview executable", async () => {
    const hosts = JSON.parse(await readFile(fileURLToPath(new URL("../../../../core/hosts.json", import.meta.url)), "utf8")) as {
      hosts: Array<{ name: string; tool_classes: Record<string, ToolCategory> }>;
    };
    const piDescriptor = hosts.hosts.find((host) => host.name === "pi")!.tool_classes;
    expect(piDescriptor.codearbiter_farm_preview).toBe("EXEC");

    const pi = new FakePi();
    pi.sources.set("codearbiter_farm_preview", "C:/package/extensions/codearbiter.js");
    guardUnknownTools(pi, piDescriptor, "C:/package/extensions/codearbiter.js");
    await expect(pi.emit("tool_call", { toolName: "codearbiter_farm_preview", input: {} })).resolves.toBeUndefined();

    pi.sources.set("codearbiter_farm_preview", "C:/foreign/replacement.js");
    const replaced = await pi.emit("tool_call", { toolName: "codearbiter_farm_preview", input: {} });
    expect(replaced).toMatchObject({ block: true, reason: expect.stringContaining("source drift") });
  });
});
