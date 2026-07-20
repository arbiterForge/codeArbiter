import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import type {
  BridgePort,
  BridgeRequest,
  BridgeResponse,
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
} from "../src/contracts.ts";
import { installParent } from "../src/extension.ts";
import { setArbiterStatus } from "../src/status.ts";

type Handler = (event: Record<string, unknown>, context: ExtensionContextPort) => unknown;

class StatusHost implements ParentPiPort {
  readonly handlers = new Map<string, Handler[]>();
  readonly calls: Array<{ key: string; text: string | undefined }> = [];
  readonly footerCalls: unknown[] = [];
  private readonly registered = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
  lateCollision = false;

  constructor(private readonly packageRoot: string, private readonly catalog: CommandCatalogEntry[]) {}

  on(event: string, handler: Handler): void {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
  registerCommand(name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }): void {
    this.registered.set(name, options);
  }
  sendUserMessage(): void {}
  getCommands() {
    const sourceInfo = {
      path: resolve(this.packageRoot, "extensions", "codearbiter.js"),
      source: "fixture",
      scope: "user",
      origin: "package",
      baseDir: this.packageRoot,
    } as const;
    return [
      ...[...this.registered.keys()].flatMap((name) => this.lateCollision
        ? [
          { name: `${name}:1`, source: "extension" as const, sourceInfo },
          { name: `${name}:2`, source: "extension" as const, sourceInfo },
        ]
        : [{ name, source: "extension" as const, sourceInfo }]),
      ...this.catalog.map((entry) => ({
        name: `skill:ca-${entry.name}`,
        source: "skill" as const,
        sourceInfo: { ...sourceInfo, path: resolve(this.packageRoot, ...entry.skillPath.split("/")) },
      })),
    ];
  }
  context(
    cwd: string,
    projectTrusted = true,
    options: { interactive?: boolean; mode?: ExtensionContextPort["mode"] } = {},
  ): ExtensionContextPort {
    const interactive = options.interactive ?? false;
    return {
      cwd,
      signal: undefined,
      hasUI: interactive,
      mode: options.mode ?? (interactive ? "tui" : "json"),
      isProjectTrusted: () => projectTrusted,
      ui: {
        notify: () => undefined,
        setStatus: (key, text) => this.calls.push({ key, text }),
        setFooter: (factory) => this.footerCalls.push(factory),
      },
    };
  }
  async emit(event: string, context: ExtensionContextPort): Promise<void> {
    for (const handler of this.handlers.get(event) ?? []) await handler({ type: event }, context);
  }
  async invoke(name: string, args: string, context: ExtensionContextPort): Promise<void> {
    await this.registered.get(name)!.handler(args, context);
  }
  last(): string | undefined { return this.calls.at(-1)?.text; }
}

class StatusBridge implements BridgePort {
  async call(_request: BridgeRequest, _signal: AbortSignal): Promise<BridgeResponse> {
    return { version: 1, outcome: "notice", context: "host: pi" };
  }
}

const roots: string[] = [];
const footerMetrics = {
  visibleWidth: (text: string) => Array.from(text.replace(/\x1b\[[0-9;]*m/gu, "")).length,
  truncateToWidth: (text: string, width: number) => Array.from(text).slice(0, Math.max(0, width)).join(""),
};

async function enabledProject(): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-status-"));
  roots.push(root);
  await mkdir(resolve(root, ".codearbiter"), { recursive: true });
  await writeFile(resolve(root, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
  return root;
}

async function bareProject(): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-status-bare-"));
  roots.push(root);
  return root;
}

async function preparePackage(root: string, catalog: CommandCatalogEntry[]): Promise<void> {
  await mkdir(resolve(root, "extensions"), { recursive: true });
  await mkdir(resolve(root, "skills"), { recursive: true });
  await writeFile(resolve(root, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
  await writeFile(resolve(root, "package.json"), JSON.stringify({
    name: "ca-pi",
    pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
  }) + "\n", "utf8");
  for (const entry of catalog) {
    const path = resolve(root, ...entry.skillPath.split("/"));
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, `---\nname: ca-${entry.name}\ndescription: ${entry.description}\n---\nbody\n`, "utf8");
  }
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("Pi keyed status lifecycle", () => {
  test("reports only bounded live footer and background health across session modes", async () => {
    const enabled = await enabledProject();
    const dormant = await bareProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md",
    }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    let backgroundHealthy = true;
    const facts: unknown[] = [];
    installParent(host, {
      bridge: new StatusBridge(), catalog, packageRoot, loadPersona: async () => "persona", footerMetrics,
      installEnforcement: () => undefined,
      installBackground: () => ({
        register: (context) => {
          if (context.mode !== "tui" || context.hasUI !== true) return false;
          host.registerCommand("ca-jobs", { handler: () => undefined });
          return true;
        },
        activate: () => true,
        toolFactory: () => ({ name: "codearbiter_background_bash", execute: async () => ({}) }),
        stop: async () => true,
        healthy: () => backgroundHealthy,
      }),
      doctorReport: async (_context, health) => { facts.push(health); return "doctor"; },
    });

    let liveTrust = true;
    const trusted = host.context(enabled, true, { interactive: true });
    trusted.isProjectTrusted = () => liveTrust;
    trusted.sessionManager = { getSessionId: () => "trusted" };
    await host.emit("session_start", trusted);
    await host.invoke("ca-doctor", "", trusted);
    expect(facts.at(-1)).toEqual({
      footer: { expected: true, initialized: true },
      background: { expected: true, initialized: true, healthy: true },
    });
    liveTrust = false;
    await host.invoke("ca-doctor", "", trusted);
    expect(facts.at(-1)).toEqual({
      footer: { expected: true, initialized: true },
      background: { expected: true, initialized: true, healthy: true },
    });
    liveTrust = true;
    backgroundHealthy = false;
    await host.invoke("ca-doctor", "", trusted);
    expect(facts.at(-1)).toEqual({
      footer: { expected: true, initialized: true },
      background: { expected: true, initialized: true, healthy: false },
    });
    await host.emit("session_shutdown", trusted);
    await host.invoke("ca-doctor", "", trusted);
    expect(facts.at(-1)).toEqual({
      footer: { expected: false, initialized: false },
      background: { expected: false, initialized: false, healthy: false },
    });

    const dormantContext = host.context(dormant, true, { interactive: true });
    await host.emit("session_start", dormantContext);
    await host.invoke("ca-doctor", "", dormantContext);
    expect(facts.at(-1)).toEqual({
      footer: { expected: true, initialized: true },
      background: { expected: false, initialized: false, healthy: false },
    });
    await host.emit("session_shutdown", dormantContext);

    const json = host.context(dormant, true, { interactive: false, mode: "json" });
    await host.emit("session_start", json);
    await host.invoke("ca-doctor", "", json);
    expect(facts.at(-1)).toEqual({
      footer: { expected: false, initialized: false },
      background: { expected: false, initialized: false, healthy: false },
    });
  });

  test.each([
    ["plain", false, true],
    ["dormant", false, true],
    ["untrusted enabled", true, false],
    ["trusted enabled", true, true],
  ] as const)("installs the rich footer globally for an interactive %s repository", async (_name, marker, trusted) => {
    const cwd = marker ? await enabledProject() : await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });

    await host.emit("session_start", host.context(cwd, trusted, { interactive: true }));

    expect(host.footerCalls).toHaveLength(1);
    expect(host.footerCalls[0]).toBeTypeOf("function");
  });

  test("renders current session activity immediately and clears the registry on shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let currentActivity: (() => { publish(event: {
      kind: "child" | "job"; id: string; label: string; state: "active" | "completed";
    }): void } | undefined) | undefined;
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
      installDispatch: (_lifecycle, activity) => { currentActivity = activity; },
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = { getEntries: () => [] };
    await host.emit("session_start", context);

    let renders = 0;
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = factory({ requestRender: () => { renders += 1; } }, {}, { getGitBranch: () => "main" });
    currentActivity?.()?.publish({ kind: "job", id: "1", label: "focused tests", state: "active" });
    currentActivity?.()?.publish({ kind: "job", id: "1", label: "focused tests", state: "completed" });

    expect(renders).toBe(2);
    expect(component.render(120).join("\n").replace(/\x1b\[[0-9;]*m/gu, ""))
      .toContain("job:focused tests");
    await host.emit("session_shutdown", context);
    expect(currentActivity?.()).toBeUndefined();
  });

  test.each([
    ["JSON", "json"],
    ["RPC", "rpc"],
    ["print", "print"],
  ] as const)("does not install footer UI in %s mode", async (_name, mode) => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let metricLoads = 0;
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      loadFooterMetrics: async () => { metricLoads += 1; return footerMetrics; },
    });

    await host.emit("session_start", host.context(cwd, true, { interactive: false, mode }));

    expect(host.footerCalls).toEqual([]);
    expect(metricLoads).toBe(0);
  });

  test("a production metrics-loader failure restores native UI without aborting adapter activation", async () => {
    const cwd = await enabledProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{ name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md" }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    const notifications: string[] = [];
    let health: unknown;
    const context = host.context(cwd, true, { interactive: true });
    context.ui.notify = (message) => notifications.push(message);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
      loadFooterMetrics: async () => { throw new Error("runtime module unavailable"); },
      doctorReport: async (_context, facts) => { health = facts; return "doctor"; },
    });

    await expect(host.emit("session_start", context)).resolves.toBeUndefined();
    expect(host.footerCalls).toEqual([undefined]);
    expect(notifications).toContain("codeArbiter footer unavailable; native Pi footer restored; run /ca-doctor");
    expect(host.last()).toBe("codeArbiter host: pi governed");
    await host.invoke("ca-doctor", "", context);
    expect(health).toEqual({
      footer: { expected: true, initialized: false },
      background: { expected: true, initialized: false, healthy: false },
    });
  });

  test("shutdown during a deferred metrics load prevents every later activation and footer side effect", async () => {
    const cwd = await enabledProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let releaseMetrics!: () => void;
    let metricsEntered!: () => void;
    const gate = new Promise<void>((resolveGate) => { releaseMetrics = resolveGate; });
    const entered = new Promise<void>((resolveEntered) => { metricsEntered = resolveEntered; });
    const operations: string[] = [];
    const bridge: BridgePort = {
      call: async () => { operations.push("bridge"); return { version: 1, outcome: "notice" }; },
    };
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => { operations.push("persona"); return "persona"; },
      loadFooterMetrics: async () => {
        metricsEntered();
        await gate;
        return footerMetrics;
      },
      readActivation: async () => { operations.push("activation"); return true; },
      prepareBridge: () => { operations.push("prepare"); },
      prepareFooterBridge: () => { operations.push("footer-prepare"); },
      installEnforcement: () => { operations.push("enforcement"); },
    });
    const context = host.context(cwd, true, { interactive: true });

    const start = host.emit("session_start", context);
    await entered;
    await host.emit("session_shutdown", context);
    releaseMetrics();
    await start;

    expect(operations).toEqual([]);
    expect(host.footerCalls).toEqual([]);
    expect(host.calls).toEqual([]);
  });

  test("a replacement session wins while the prior deferred metrics load cannot resurrect", async () => {
    const firstCwd = await enabledProject();
    const secondCwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let releaseFirst!: () => void;
    let firstEntered!: () => void;
    const gate = new Promise<void>((resolveGate) => { releaseFirst = resolveGate; });
    const entered = new Promise<void>((resolveEntered) => { firstEntered = resolveEntered; });
    let loads = 0;
    const activationCwds: string[] = [];
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      loadFooterMetrics: async () => {
        loads += 1;
        if (loads === 1) {
          firstEntered();
          await gate;
        }
        return footerMetrics;
      },
      readActivation: async (cwd) => { activationCwds.push(cwd); return false; },
    });
    const firstContext = host.context(firstCwd, true, { interactive: true });
    const secondContext = host.context(secondCwd, true, { interactive: true });

    const firstStart = host.emit("session_start", firstContext);
    await entered;
    await host.emit("session_start", secondContext);
    expect(host.footerCalls).toHaveLength(1);
    expect(host.footerCalls[0]).toBeTypeOf("function");
    expect(activationCwds).toEqual([secondCwd]);
    releaseFirst();
    await firstStart;

    expect(host.footerCalls).toHaveLength(1);
    expect(activationCwds).toEqual([secondCwd]);
    expect(host.calls).toEqual([]);
  });

  test("restores Pi's native footer on session shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });

    await host.emit("session_start", context);
    await host.emit("session_shutdown", context);

    expect(host.footerCalls).toHaveLength(2);
    expect(host.footerCalls.at(-1)).toBeUndefined();
  });

  test("renders through Pi's authoritative width primitives and unsubscribes branch updates", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = {
      getSessionId: () => "footer-session",
      getSessionName: () => "status",
      getEntries: () => [],
    };

    await host.emit("session_start", context);
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
      onBranchChange(callback: () => void): () => void;
    }) => { render(width: number): string[]; dispose?(): void };
    let branchCallback: (() => void) | undefined;
    let renders = 0;
    let unsubscribed = false;
    const component = factory(
      { requestRender: () => { renders += 1; } },
      {},
      {
        getGitBranch: () => "feat/footer",
        onBranchChange: (callback) => {
          branchCallback = callback;
          return () => { unsubscribed = true; };
        },
      },
    );

    const lines = component.render(31);
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.every((line) => footerMetrics.visibleWidth(line) <= 31)).toBe(true);
    branchCallback?.();
    expect(renders).toBe(1);
    component.dispose?.();
    expect(unsubscribed).toBe(true);
  });

  test("fatal factory registration restores native state and publishes a bounded diagnosis", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd, true, { interactive: true });
    const notifications: string[] = [];
    context.ui.notify = (message) => notifications.push(message);
    context.ui.setFooter = (() => { throw new Error("host footer failure"); });
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });

    await expect(host.emit("session_start", context)).resolves.toBeUndefined();
    expect(notifications).toEqual([
      "codeArbiter footer unavailable; native Pi footer restored; run /ca-doctor",
    ]);
  });

  test("missing interactive footer UI fails soft with the bounded doctor direction", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd, true, { interactive: true });
    const notifications: string[] = [];
    context.ui.notify = (message) => notifications.push(message);
    delete context.ui.setFooter;
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });

    await expect(host.emit("session_start", context)).resolves.toBeUndefined();
    expect(notifications).toEqual([
      "codeArbiter footer unavailable; native Pi footer restored; run /ca-doctor",
    ]);
  });

  test.each([
    ["plain", false, true, 0],
    ["untrusted enabled", true, false, 0],
    ["trusted enabled", true, true, 1],
  ] as const)("keeps governance bridge reads trust-gated in %s repositories", async (
    _name,
    marker,
    trusted,
    expectedStatusCalls,
  ) => {
    const cwd = marker ? await enabledProject() : await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const calls: BridgeRequest[] = [];
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => {
        calls.push(request);
        if (request.event === "footer_usage_update") {
          return {
            version: 1,
            outcome: "notice",
            resultPatch: { footerUsage: {
              status: "ok",
              session: totals,
              today: totals,
              acceptedThrough: 0,
              highWater: 0,
            } },
          };
        }
        if (request.event === "footer_status_snapshot") {
          return {
            version: 1,
            outcome: "notice",
            resultPatch: { footerStatus: {
              status: "ok",
              stage: "implementation",
              tasks: 1,
              questions: 0,
              overrides: 0,
              sprint: true,
              dev: false,
              prune: null,
            } },
          };
        }
        return { version: 1, outcome: "notice", context: "host: pi" };
      },
    };
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });
    const context = host.context(cwd, trusted, { interactive: true });
    context.sessionManager = {
      getSessionId: () => "trust-gate",
      getEntries: () => [{ type: "message", message: { role: "user" } }],
    };

    await host.emit("session_start", context);

    expect(calls.filter((call) => call.event === "footer_usage_update")).toHaveLength(1);
    expect(calls.filter((call) => call.event === "footer_status_snapshot")).toHaveLength(expectedStatusCalls);
  });

  test("retains the last valid usage snapshot while retrying the exact first unacknowledged range", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let entries: unknown[] = [{ type: "message", message: { role: "user" } }];
    let failSecond = true;
    const scanStarts: number[] = [];
    const bridge: BridgePort = {
      call: async (request) => {
        const input = request.input as { scanStart: number; scanEnd: number };
        scanStarts.push(input.scanStart);
        const failed = input.scanStart === 1 && failSecond;
        const tokens = input.scanStart === 0 ? 10 : 20;
        const totals = {
          inputTokens: tokens,
          outputTokens: 0,
          cacheReadTokens: 0,
          cacheWriteTokens: 0,
          costUsd: 0,
        };
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: {
            status: failed ? "write_failed" : "ok",
            session: totals,
            today: totals,
            acceptedThrough: failed ? -1 : input.scanEnd,
            highWater: failed ? 0 : input.scanEnd,
          } },
        };
      },
    };
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = {
      getSessionId: () => "usage-retry",
      getEntries: () => entries,
    };

    await host.emit("session_start", context);
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = factory({ requestRender: () => undefined }, {}, { getGitBranch: () => "main" });
    expect(component.render(100).join("\n").replace(/\x1b\[[0-9;]*m/gu, "")).toContain("10");

    entries = [...entries, { type: "message", message: { role: "user" } }];
    await host.emit("agent_settled", context);
    expect(component.render(100).join("\n").replace(/\x1b\[[0-9;]*m/gu, "")).toContain("10");

    failSecond = false;
    await host.emit("agent_settled", context);
    expect(component.render(100).join("\n").replace(/\x1b\[[0-9;]*m/gu, "")).toContain("20");
    expect(scanStarts).toEqual([0, 1, 1]);
  });

  test("limits startup accounting to one 256-entry bridge range", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const calls: Array<{ scanStart: number; scanEnd: number }> = [];
    const entries = Array.from({ length: 600 }, () => ({ type: "message", message: { role: "user" } }));
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => {
        const input = request.input as { scanStart: number; scanEnd: number };
        calls.push({ scanStart: input.scanStart, scanEnd: input.scanEnd });
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: {
            status: "ok", session: totals, today: totals,
            acceptedThrough: input.scanEnd, highWater: input.scanEnd,
          } },
        };
      },
    };
    installParent(host, {
      bridge, catalog: [], packageRoot, loadPersona: async () => "persona", footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = { getSessionId: () => "large-start", getEntries: () => entries };

    await host.emit("session_start", context);

    expect(calls).toEqual([{ scanStart: 0, scanEnd: 255 }]);
  });

  test("serializes same-session refreshes so overlapping events neither duplicate nor roll back cursor work", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const entries = Array.from({ length: 300 }, () => ({ type: "message", message: { role: "user" } }));
    const scans: number[] = [];
    let releaseFirst!: () => void;
    let firstEntered!: () => void;
    const firstGate = new Promise<void>((resolveGate) => { releaseFirst = resolveGate; });
    const entered = new Promise<void>((resolveEntered) => { firstEntered = resolveEntered; });
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => {
        const input = request.input as { scanStart: number; scanEnd: number };
        scans.push(input.scanStart);
        if (scans.length === 1) {
          firstEntered();
          await firstGate;
        }
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: {
            status: "ok", session: totals, today: totals,
            acceptedThrough: input.scanEnd, highWater: input.scanEnd,
          } },
        };
      },
    };
    installParent(host, {
      bridge, catalog: [], packageRoot, loadPersona: async () => "persona", footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = { getSessionId: () => "serialized", getEntries: () => entries };

    const start = host.emit("session_start", context);
    await entered;
    const settled = host.emit("agent_settled", context);
    await Promise.resolve();
    const beforeRelease = [...scans];
    releaseFirst();
    await Promise.all([start, settled]);
    expect(beforeRelease).toEqual([0]);
    expect(scans).toEqual([0, 256]);
  });

  test("lets a replacement session refresh immediately while stale completion remains unable to mutate it", async () => {
    const firstCwd = await bareProject();
    const secondCwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let releaseFirst!: () => void;
    let firstEntered!: () => void;
    const firstGate = new Promise<void>((resolveGate) => { releaseFirst = resolveGate; });
    const entered = new Promise<void>((resolveEntered) => { firstEntered = resolveEntered; });
    let calls = 0;
    const bridge: BridgePort = {
      call: async (request) => {
        calls += 1;
        if (calls === 1) {
          firstEntered();
          await firstGate;
        }
        const input = request.input as { scanEnd: number };
        const totals = {
          inputTokens: request.cwd === secondCwd ? 20 : 10,
          outputTokens: 0,
          cacheReadTokens: 0,
          cacheWriteTokens: 0,
          costUsd: 0,
        };
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: {
            status: "ok", session: totals, today: totals,
            acceptedThrough: input.scanEnd, highWater: input.scanEnd,
          } },
        };
      },
    };
    installParent(host, {
      bridge, catalog: [], packageRoot, loadPersona: async () => "persona", footerMetrics,
    });
    const makeContext = (cwd: string, id: string) => {
      const context = host.context(cwd, true, { interactive: true });
      context.sessionManager = {
        getSessionId: () => id,
        getEntries: () => [{ type: "message", message: { role: "user" } }],
      };
      return context;
    };
    const firstContext = makeContext(firstCwd, "first");
    const secondContext = makeContext(secondCwd, "second");

    const firstStart = host.emit("session_start", firstContext);
    await entered;
    const secondStart = host.emit("session_start", secondContext);
    await secondStart;
    expect(calls).toBe(2);
    const secondFactory = host.footerCalls.at(-1) as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = secondFactory({ requestRender: () => undefined }, {}, { getGitBranch: () => "main" });
    const render = () => component.render(100).join("\n").replace(/\x1b\[[0-9;]*m/gu, "");
    expect(render()).toContain("20");
    releaseFirst();
    await firstStart;
    expect(render()).toContain("20");
    expect(render()).not.toContain("10");
  });

  test("returns a nonempty bounded ASCII fallback even when both injected width functions throw", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const throwingMetrics = {
      visibleWidth: () => { throw new Error("width failure"); },
      truncateToWidth: () => { throw new Error("truncate failure"); },
    };
    installParent(host, {
      bridge: new StatusBridge(), catalog: [], packageRoot, loadPersona: async () => "persona",
      footerMetrics: throwingMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    await host.emit("session_start", context);
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = factory({ requestRender: () => undefined }, {}, { getGitBranch: () => "main" });

    const lines = component.render(8);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/^[\x20-\x7e]+$/u);
    expect(lines[0]!.length).toBeLessThanOrEqual(8);
  });

  test("retains a valid cached update fact across later usage-only refreshes", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      readFooterUpdateVersion: async () => "2.0.0",
      footerMetrics,
    });
    const context = host.context(cwd, true, { interactive: true });
    context.sessionManager = { getSessionId: () => "update", getEntries: () => [] };

    await host.emit("session_start", context);
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = factory({ requestRender: () => undefined }, {}, { getGitBranch: () => "main" });
    const render = () => component.render(120).join("\n").replace(/\x1b\[[0-9;]*m/gu, "");
    expect(render()).toContain("update 2.0.0");
    await host.emit("agent_settled", context);
    expect(render()).toContain("update 2.0.0");
  });

  test("hides an already-read governance snapshot immediately when Pi trust is withdrawn", async () => {
    const cwd = await enabledProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => request.event === "footer_status_snapshot"
        ? {
          version: 1,
          outcome: "notice",
          resultPatch: { footerStatus: {
            status: "ok", stage: "implementation", tasks: 1, questions: 0, overrides: 0,
            sprint: false, dev: false, prune: "next checkpoint",
          } },
        }
        : request.event === "footer_usage_update"
          ? {
            version: 1,
            outcome: "notice",
            resultPatch: { footerUsage: {
              status: "ok", session: totals, today: totals, acceptedThrough: 0, highWater: 0,
            } },
          }
          : { version: 1, outcome: "notice", context: "host: pi" },
    };
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      footerMetrics,
    });
    let trusted = true;
    const context = host.context(cwd, true, { interactive: true });
    context.isProjectTrusted = () => trusted;
    context.sessionManager = {
      getSessionId: () => "trust-withdrawal",
      getEntries: () => [{ type: "message", message: { role: "user" } }],
    };

    await host.emit("session_start", context);
    const factory = host.footerCalls[0] as (tui: { requestRender(): void }, theme: unknown, data: {
      getGitBranch(): string;
    }) => { render(width: number): string[] };
    const component = factory({ requestRender: () => undefined }, {}, { getGitBranch: () => "main" });
    const render = () => component.render(120).join("\n").replace(/\x1b\[[0-9;]*m/gu, "");
    expect(render()).toContain("stage:implementation");
    expect(render()).toContain("prune:next checkpoint");
    trusted = false;
    expect(render()).not.toContain("stage:implementation");
    expect(render()).not.toContain("prune:next checkpoint");
  });

  test("setArbiterStatus composes through only the codearbiter key", () => {
    const calls: Array<[string, string | undefined]> = [];
    setArbiterStatus({ ui: { setStatus: (key, text) => calls.push([key, text]), notify: () => undefined } }, "working");
    expect(calls).toEqual([["codearbiter", "working"]]);
  });

  test("retains status through end, retry, and compaction and clears only when settled", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    await host.emit("agent_start", context);
    const active = host.last();
    expect(active).toContain("host: pi");
    await host.emit("agent_end", context);
    expect(host.last()).toBe(active);
    await host.emit("session_before_compact", context);
    await host.emit("session_compact", context);
    await host.emit("agent_start", context);
    expect(host.last()).toBe(active);
    await host.emit("agent_settled", context);
    expect(host.last()).toBeUndefined();
    expect(new Set(host.calls.map((call) => call.key))).toEqual(new Set(["codearbiter"]));
  });

  test("session shutdown is the only non-settled lifecycle clear", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    expect(host.last()).toBeDefined();
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });

  test("a never-published dormant lifecycle remains status-silent through shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    await host.emit("session_shutdown", context);
    expect(host.calls).toEqual([]);
  });

  test("failed activation clears its unhealthy status on a dormant start and on shutdown", async () => {
    const enabled = await enabledProject();
    const dormant = await bareProject();
    const packageRoot = await bareProject();
    const host = new StatusHost(packageRoot, []);
    let attempts = 0;
    installParent(host, {
      bridge: new StatusBridge(),
      catalog: [],
      packageRoot,
      loadPersona: async () => "persona",
      installEnforcement: () => {
        attempts += 1;
        throw new Error("fixture install failure");
      },
    });

    const failedContext = host.context(enabled);
    await expect(host.emit("session_start", failedContext)).rejects.toThrow("/ca-doctor");
    expect(host.last()).toContain("unhealthy");
    const callCount = host.calls.length;
    await host.emit("session_start", host.context(dormant));
    expect(host.calls).toHaveLength(callCount + 1);
    expect(host.calls.at(-1)).toEqual({ key: "codearbiter", text: undefined });

    await expect(host.emit("session_start", failedContext)).rejects.toThrow("/ca-doctor");
    expect(host.last()).toContain("unhealthy");
    await host.emit("session_shutdown", failedContext);
    expect(host.calls.at(-1)).toEqual({ key: "codearbiter", text: undefined });
    expect(attempts).toBe(2);
  });

  test("agent work and settling never erase a persistent command-ownership degradation", async () => {
    const cwd = await enabledProject();
    const packageRoot = await enabledProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });

    await host.emit("session_start", context);
    const baseline = host.last();
    expect(baseline).toContain("command ownership conflict");
    await host.emit("agent_start", context);
    expect(host.last()).toBe(baseline);
    await host.emit("agent_settled", context);
    expect(host.last()).toBe(baseline);
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });

  test("a late alias collision becomes the persistent baseline through agent_settled", async () => {
    const cwd = await enabledProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    host.lateCollision = true;
    await host.invoke("ca-feature", "args", context);
    const baseline = host.last();
    expect(baseline).toContain("command surface");
    await host.emit("agent_settled", context);
    expect(host.last()).toBe(baseline);
  });

  test("an explicit alias degradation in a bare repo clears on session shutdown", async () => {
    const cwd = await bareProject();
    const packageRoot = await bareProject();
    const catalog: CommandCatalogEntry[] = [{
      name: "feature",
      description: "Build a feature.",
      skillPath: "skills/ca-feature/SKILL.md",
    }];
    await preparePackage(packageRoot, catalog);
    const host = new StatusHost(packageRoot, catalog);
    const context = host.context(cwd);
    installParent(host, {
      bridge: new StatusBridge(),
      catalog,
      packageRoot,
      loadPersona: async () => "persona",
    });
    await host.emit("session_start", context);
    expect(host.calls).toEqual([]);
    host.lateCollision = true;
    await host.invoke("ca-feature", "args", context);
    expect(host.last()).toContain("command surface");
    await host.emit("session_shutdown", context);
    expect(host.last()).toBeUndefined();
  });
});
