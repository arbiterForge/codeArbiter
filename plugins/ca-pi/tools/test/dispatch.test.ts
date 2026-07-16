import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { afterEach, describe, expect, test, vi } from "vitest";

import {
  DISPATCH_MODES,
  DISPATCH_POLICY,
  DISPATCH_TERMINALS,
  createDispatchTool,
  createDispatcher,
} from "../src/dispatch.ts";
import type {
  DispatchRequest,
  DispatchRuntime,
  DispatchTerminal,
} from "../src/dispatch.ts";
import type { PiChildRequest, ChildResult } from "../src/runner.ts";
import type { PiRole } from "../src/roles.ts";
import { installParent, installPiDispatch } from "../src/extension.ts";
import type {
  BridgePort,
  ExtensionContextPort,
  ParentPiPort,
  ToolDefinitionPort,
} from "../src/contracts.ts";

const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

async function project(enabled: boolean): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-dispatch-"));
  temporaryRoots.push(root);
  if (enabled) {
    await mkdir(resolve(root, ".codearbiter"), { recursive: true });
    await writeFile(resolve(root, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
  }
  return root;
}

const packageRoot = resolve("C:/codearbiter/plugins/ca-pi");
const runtime: DispatchRuntime = Object.freeze({
  nodePath: resolve("C:/runtime/node.exe"),
  piCliPath: resolve("C:/runtime/pi.js"),
  provider: "openai",
  model: "gpt-5",
  cwd: resolve("C:/work/project"),
  packageRoot,
  childExtensionPath: resolve(packageRoot, "extensions/codearbiter-child.js"),
});

const roles = new Map<string, PiRole>([
  ["backend-author", Object.freeze({
    name: "backend-author",
    classification: "author",
    charterPath: "agents/backend-author.md",
    skillPaths: ["routines/tdd/SKILL.md"],
    tools: ["read", "bash", "edit", "write"],
  }) as PiRole],
  ["coverage-auditor", Object.freeze({
    name: "coverage-auditor",
    classification: "reviewer",
    charterPath: "agents/coverage-auditor.md",
    skillPaths: ["routines/tdd/SKILL.md"],
    tools: ["read", "bash"],
  }) as PiRole],
  ["security-reviewer", Object.freeze({
    name: "security-reviewer",
    classification: "reviewer",
    charterPath: "agents/security-reviewer.md",
    skillPaths: [],
    tools: ["read", "bash"],
  }) as PiRole],
  ["auth-crypto-reviewer", Object.freeze({
    name: "auth-crypto-reviewer",
    classification: "reviewer",
    charterPath: "agents/auth-crypto-reviewer.md",
    skillPaths: [],
    tools: ["read", "bash"],
  }) as PiRole],
]);

const neverAbort = new AbortController();

function request(overrides: Partial<DispatchRequest> = {}): DispatchRequest {
  return {
    mode: "single",
    roles: ["security-reviewer"],
    task: "Review the bounded change.",
    depth: 0,
    runtime,
    ...overrides,
  };
}

function completed(state: "accepted" | "changes_requested" | "blocked", summary = `${state} summary`): ChildResult {
  return {
    terminal: "completed",
    pid: 1234,
    correlationId: "corr-1",
    output: JSON.stringify({ state, summary }),
  };
}

function dispatcher(runChild: (input: PiChildRequest, signal: AbortSignal) => Promise<ChildResult>) {
  return createDispatcher({
    runChild,
    loadRoles: async () => roles,
  });
}

describe("Pi dispatch contract", () => {
  test("exports one frozen bounded policy and exact closed mode and terminal sets", () => {
    expect(DISPATCH_MODES).toEqual(["single", "chain", "parallel"]);
    expect(DISPATCH_TERMINALS).toEqual([
      "accepted",
      "changes_requested",
      "blocked",
      "cancelled",
      "timeout",
      "depth_exceeded",
      "oversized",
      "protocol_error",
      "crashed",
      "degraded",
    ]);
    expect(Object.isFrozen(DISPATCH_POLICY)).toBe(true);
    expect(Object.values(DISPATCH_POLICY).every((value) => Number.isSafeInteger(value) && value > 0)).toBe(true);
  });

  test.each([
    ["single", ["security-reviewer"]],
    ["chain", ["backend-author", "coverage-auditor"]],
    ["parallel", ["security-reviewer", "auth-crypto-reviewer"]],
  ] as const)("dispatches %s with deterministic requested role ordering", async (mode, selectedRoles) => {
    const runChild = vi.fn(async () => completed("accepted"));
    const result = await dispatcher(runChild)(request({ mode, roles: [...selectedRoles] }), neverAbort.signal);

    expect(result.state).toBe("accepted");
    expect(result.children.map((child) => child.role)).toEqual(selectedRoles);
    expect(runChild).toHaveBeenCalledTimes(selectedRoles.length);
  });

  test("chain forwards only the bounded parsed prior result", async () => {
    const inputs: PiChildRequest[] = [];
    const runChild = vi.fn(async (input: PiChildRequest) => {
      inputs.push(input);
      return completed("accepted", inputs.length === 1 ? "author summary" : "review summary");
    });

    const result = await dispatcher(runChild)(request({
      mode: "chain",
      roles: ["backend-author", "coverage-auditor"],
    }), neverAbort.signal);

    expect(result.state).toBe("accepted");
    const first = JSON.parse(inputs[0]!.task) as Record<string, unknown>;
    expect(first).toEqual({
      protocol: "codearbiter-dispatch-v1",
      task: "Review the bounded change.",
      response: {
        exactKeys: ["state", "summary"],
        states: ["accepted", "changes_requested", "blocked"],
        summary: "Put the complete Markdown report required by your role charter in this JSON string. Emit only the JSON object.",
      },
    });
    const forwarded = JSON.parse(inputs[1]!.task) as Record<string, unknown>;
    expect(forwarded).toEqual({
      protocol: "codearbiter-dispatch-v1",
      task: "Review the bounded change.",
      prior: { role: "backend-author", state: "accepted", summary: "author summary" },
      response: {
        exactKeys: ["state", "summary"],
        states: ["accepted", "changes_requested", "blocked"],
        summary: "Put the complete Markdown report required by your role charter in this JSON string. Emit only the JSON object.",
      },
    });
    expect(inputs[1]!.task).not.toContain("correlationId");
    expect(inputs[1]!.task).not.toContain("pid");
    expect(inputs[1]!.task).not.toContain("provider");
  });

  test.each([
    ["unknown role", { roles: ["missing-reviewer"] }, "protocol_error"],
    ["duplicate role", { roles: ["security-reviewer", "security-reviewer"], mode: "parallel" }, "protocol_error"],
    ["duplicate author", { roles: ["backend-author", "backend-author"], mode: "chain" }, "protocol_error"],
    ["single role count", { roles: ["security-reviewer", "coverage-auditor"] }, "protocol_error"],
    ["depth", { depth: DISPATCH_POLICY.maxDepth + 1 }, "depth_exceeded"],
    ["zero concurrency", { limits: { concurrency: 0 } }, "protocol_error"],
    ["negative timeout", { limits: { timeoutMs: -1 } }, "protocol_error"],
    ["over-policy output limit", { limits: { maxAggregateOutputBytes: DISPATCH_POLICY.maxAggregateOutputBytes + 1 } }, "protocol_error"],
  ] as const)("validates %s before spawning", async (_label, overrides, terminal) => {
    const runChild = vi.fn(async () => completed("accepted"));
    const result = await dispatcher(runChild)(request(overrides as Partial<DispatchRequest>), neverAbort.signal);

    expect(result).toMatchObject({ state: terminal, children: [] });
    expect(runChild).not.toHaveBeenCalled();
  });

  test("validates every role before spawning any child", async () => {
    const runChild = vi.fn(async () => completed("accepted"));
    const result = await dispatcher(runChild)(request({
      mode: "parallel",
      roles: ["security-reviewer", "missing-reviewer"],
    }), neverAbort.signal);

    expect(result.state).toBe("protocol_error");
    expect(runChild).not.toHaveBeenCalled();
  });

  test("parallel scheduling is FIFO, bounded, and returns requested ordering", async () => {
    const started: string[] = [];
    const releases: Array<() => void> = [];
    let active = 0;
    let peak = 0;
    const runChild = vi.fn(async (input: PiChildRequest) => {
      const role = input.charterPath.split(/[\\/]/u).at(-1)!.replace(/\.md$/u, "");
      started.push(role);
      active += 1;
      peak = Math.max(peak, active);
      await new Promise<void>((resolvePromise) => releases.push(resolvePromise));
      active -= 1;
      return completed("accepted", role);
    });
    const run = dispatcher(runChild)(request({
      mode: "parallel",
      roles: ["security-reviewer", "auth-crypto-reviewer", "coverage-auditor"],
      limits: { concurrency: 2 },
    }), neverAbort.signal);

    await vi.waitFor(() => expect(started).toEqual(["security-reviewer", "auth-crypto-reviewer"]));
    releases.shift()!();
    await vi.waitFor(() => expect(started).toEqual([
      "security-reviewer",
      "auth-crypto-reviewer",
      "coverage-auditor",
    ]));
    releases.splice(0).forEach((release) => release());
    const result = await run;

    expect(peak).toBe(2);
    expect(result.children.map((child) => child.role)).toEqual([
      "security-reviewer",
      "auth-crypto-reviewer",
      "coverage-auditor",
    ]);
  });

  test("parent cancellation aborts active siblings and never starts queued work", async () => {
    const parent = new AbortController();
    const started: string[] = [];
    const runChild = vi.fn(async (input: PiChildRequest, signal: AbortSignal) => {
      started.push(input.charterPath);
      await new Promise<void>((resolvePromise) => signal.addEventListener("abort", () => resolvePromise(), { once: true }));
      return { terminal: "degraded" as const };
    });
    const run = dispatcher(runChild)(request({
      mode: "parallel",
      roles: ["security-reviewer", "auth-crypto-reviewer", "coverage-auditor"],
      limits: { concurrency: 2 },
    }), parent.signal);

    await vi.waitFor(() => expect(started).toHaveLength(2));
    parent.abort();
    const result = await run;

    expect(result.state).toBe("cancelled");
    expect(started).toHaveLength(2);
    expect(result.children.map((child) => child.state)).toEqual(["cancelled", "cancelled", "cancelled"]);
  });

  test.each([
    ["changes_requested", async () => completed("changes_requested")],
    ["blocked", async () => completed("blocked")],
    ["protocol_error", async () => ({ terminal: "completed", output: "not-json" } as ChildResult)],
    ["crashed", async () => { throw new Error("synthetic child crash"); }],
    ["degraded", async () => ({ terminal: "degraded" } as ChildResult)],
  ] as const)("maps child outcome to terminal state %s without rejection", async (state, runChild) => {
    await expect(dispatcher(runChild)(request(), neverAbort.signal)).resolves.toMatchObject({ state });
  });

  test("maps the dispatcher deadline to timeout after aborting the child", async () => {
    vi.useFakeTimers();
    try {
      const runChild = vi.fn(async (_input: PiChildRequest, signal: AbortSignal) => {
        await new Promise<void>((resolvePromise) => signal.addEventListener("abort", () => resolvePromise(), { once: true }));
        return { terminal: "degraded" as const };
      });
      const run = dispatcher(runChild)(request({ limits: { timeoutMs: 10 } }), neverAbort.signal);
      await vi.advanceTimersByTimeAsync(10);
      await expect(run).resolves.toMatchObject({ state: "timeout" });
    } finally {
      vi.useRealTimers();
    }
  });

  test("rejects per-child and deterministic aggregate output overflow", async () => {
    const largeSummary = "x".repeat(120);
    const runChild = vi.fn(async () => completed("accepted", largeSummary));
    const result = await dispatcher(runChild)(request({
      mode: "parallel",
      roles: ["security-reviewer", "auth-crypto-reviewer"],
      limits: { maxChildOutputBytes: 180, maxAggregateOutputBytes: 200 },
    }), neverAbort.signal);

    expect(result.state).toBe("oversized");
    expect(result.children.map((child) => child.state)).toEqual(["accepted", "oversized"]);
  });

  test("registers one codearbiter_dispatch tool without exposing trusted launch paths as parameters", async () => {
    const run = vi.fn(async () => ({ state: "accepted" as DispatchTerminal, children: [] }));
    const tool = createDispatchTool({
      authorize: async () => true,
      resolveRuntime: () => runtime,
      dispatch: run,
    });
    const signal = new AbortController().signal;
    const result = await tool.execute("call-1", {
      mode: "single",
      roles: ["security-reviewer"],
      task: "Review this.",
    }, signal, undefined, {
      cwd: runtime.cwd,
      signal,
      model: { provider: runtime.provider, id: runtime.model },
    });

    expect(tool.name).toBe("codearbiter_dispatch");
    expect(JSON.stringify(tool.parameters)).not.toMatch(/nodePath|piCliPath|packageRoot|childExtensionPath/u);
    expect(run).toHaveBeenCalledWith(expect.objectContaining({
      mode: "single",
      roles: ["security-reviewer"],
      task: "Review this.",
      runtime,
    }), signal);
    expect(result).toMatchObject({ details: { state: "accepted", children: [] } });
  });

  test("tool input is exact and fails closed before dispatch", async () => {
    const run = vi.fn(async () => ({ state: "accepted" as DispatchTerminal, children: [] }));
    const tool = createDispatchTool({ authorize: async () => true, resolveRuntime: () => runtime, dispatch: run });
    const result = await tool.execute("call-1", {
      mode: "single",
      roles: ["security-reviewer"],
      task: "Review this.",
      nodePath: "C:/attacker/node.exe",
    }, undefined, undefined, {
      cwd: runtime.cwd,
      signal: undefined,
      model: { provider: runtime.provider, id: runtime.model },
    });

    expect(run).not.toHaveBeenCalled();
    expect(result).toMatchObject({ details: { state: "protocol_error", children: [] } });
  });

  test("production registration authorizes only enabled, currently trusted, lifecycle-ready sessions", async () => {
    const enabled = await project(true);
    const dormant = await project(false);
    let lifecycleReady = true;
    const run = vi.fn(async () => ({ state: "accepted" as DispatchTerminal, children: [] }));
    let tool: ToolDefinitionPort | undefined;
    installPiDispatch({
      registerTool: (definition) => { tool = definition; },
    }, {
      packageRoot,
      piCliPath: runtime.piCliPath,
      isLifecycleReady: () => lifecycleReady,
      dispatch: run,
    });
    expect(tool?.name).toBe("codearbiter_dispatch");

    const context = (
      cwd: string,
      trust: "true" | "false" | "missing" | "throw",
    ): ExtensionContextPort => ({
      cwd,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: () => undefined },
      ...(trust === "missing" ? {} : {
        isProjectTrusted: () => {
          if (trust === "throw") throw new Error("synthetic trust failure");
          return trust === "true";
        },
      }),
      model: { provider: runtime.provider, id: runtime.model },
    });

    for (const blockedContext of [
      context(dormant, "true"),
      context(enabled, "false"),
      context(enabled, "missing"),
      context(enabled, "throw"),
    ]) {
      const result = await tool!.execute("blocked", {
        mode: "single", roles: ["security-reviewer"], task: "Review.",
      }, undefined, undefined, blockedContext);
      expect(result).toMatchObject({ details: { state: "degraded", children: [] } });
    }
    lifecycleReady = false;
    const stale = await tool!.execute("stale", {
      mode: "single", roles: ["security-reviewer"], task: "Review.",
    }, undefined, undefined, context(enabled, "true"));
    expect(stale).toMatchObject({ details: { state: "degraded", children: [] } });
    expect(run).not.toHaveBeenCalled();

    lifecycleReady = true;
    const accepted = await tool!.execute("ready", {
      mode: "single", roles: ["security-reviewer"], task: "Review.",
    }, undefined, undefined, context(enabled, "true"));
    expect(accepted).toMatchObject({ details: { state: "accepted", children: [] } });
    expect(run).toHaveBeenCalledTimes(1);
  });

  test("installParent owns dispatch readiness and invalidates it on shutdown", async () => {
    const cwd = await project(true);
    const handlers = new Map<string, Array<(event: Record<string, unknown>, context: ExtensionContextPort) => unknown>>();
    let lifecycleReady: (() => object | undefined) | undefined;
    const host: ParentPiPort = {
      on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
      registerCommand: () => undefined,
      sendUserMessage: () => undefined,
      getCommands: () => [],
    };
    const bridge: BridgePort = {
      call: async () => ({ version: 1, outcome: "allow", context: "host: pi" }),
    };
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot: cwd,
      loadPersona: async () => "persona",
      installEnforcement: async () => undefined,
      installDispatch: (ready) => { lifecycleReady = ready; },
      enforcementReadiness: {
        beginActivation: () => undefined,
        beginBootstrap: () => undefined,
        markReady: () => undefined,
        deactivate: () => undefined,
      },
    });
    const context: ExtensionContextPort = {
      cwd,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: () => undefined },
      isProjectTrusted: () => true,
    };
    const emit = async (event: string) => {
      for (const handler of handlers.get(event) ?? []) await handler({ type: event }, context);
    };

    expect(lifecycleReady?.()).toBeUndefined();
    await emit("session_start");
    expect(lifecycleReady?.()).toEqual(expect.any(Object));
    await emit("session_shutdown");
    expect(lifecycleReady?.()).toBeUndefined();
  });
});
