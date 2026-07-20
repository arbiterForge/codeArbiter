import { access, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { isEnabled, readCachedUpdateVersion } from "../src/activation.ts";
import { BridgeClient } from "../src/bridge.ts";
import type {
  BridgePort,
  BridgeRequest,
  BridgeResponse,
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
} from "../src/contracts.ts";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as extensionModule from "../src/extension.ts";
import { boundedPiEnvironment, createCodeArbiterPi, installParent, renderPiDoctorReportBlock, resolvePiBackgroundShell } from "../src/extension.ts";
import { collectPiDoctorInput, diagnosePi, formatPiDoctorReport } from "../src/doctor.ts";
import type { NativeBackgroundController } from "../src/commands.ts";

type Handler = (event: Record<string, unknown>, context: ExtensionContextPort) => unknown;

interface ActivationFixture {
  name: string;
  text: string;
  enabled: boolean;
  malformed: boolean;
}

interface ActivationContract {
  version: number;
  canonicalParser: string;
  fixtures: ActivationFixture[];
}

class FakeBridge implements BridgePort {
  readonly calls: BridgeRequest[] = [];
  private readonly contexts = ["stage: implementation\nhost: pi", "stage: verification\nhost: pi"];

  async call(request: BridgeRequest, _signal: AbortSignal): Promise<BridgeResponse> {
    this.calls.push(structuredClone(request));
    return { version: 1, outcome: "notice", context: this.contexts.shift() ?? "host: pi" };
  }
}

class FakePi implements ParentPiPort {
  readonly handlers = new Map<string, Handler[]>();
  readonly registered = new Map<string, { description?: string; handler: (args: string, ctx: ExtensionContextPort) => unknown }>();
  readonly userMessages: string[] = [];
  readonly statusCalls: Array<{ key: string; text: string | undefined }> = [];
  readonly notifications: Array<{ message: string; level?: "info" | "warning" | "error" }> = [];
  readonly extraCommands: ReturnType<ParentPiPort["getCommands"]> = [];

  constructor(private readonly packageRoot: string, private readonly catalog: CommandCatalogEntry[]) {}

  on(event: string, handler: Handler): void {
    const values = this.handlers.get(event) ?? [];
    values.push(handler);
    this.handlers.set(event, values);
  }

  registerCommand(
    name: string,
    options: { description?: string; handler: (args: string, ctx: ExtensionContextPort) => unknown },
  ): void {
    this.registered.set(name, options);
  }

  sendUserMessage(content: string): void {
    this.userMessages.push(content);
  }

  getCommands() {
    const sourceInfo = {
      path: resolve(this.packageRoot, "extensions", "codearbiter.js"),
      source: "fixture",
      scope: "user",
      origin: "package",
      baseDir: this.packageRoot,
    } as const;
    return [
      ...[...this.registered.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
      ...this.catalog.map((entry) => ({
        name: `skill:ca-${entry.name}`,
        source: "skill" as const,
        sourceInfo: {
          ...sourceInfo,
          path: resolve(this.packageRoot, ...entry.skillPath.split("/")),
        },
      })),
      ...this.extraCommands,
    ];
  }

  context(cwd: string, projectTrusted: boolean | null = true): ExtensionContextPort {
    const context: ExtensionContextPort = {
      cwd,
      signal: undefined,
      ui: {
        notify: (message, level) => { this.notifications.push({ message, level }); },
        setStatus: (key, text) => this.statusCalls.push({ key, text }),
      },
    };
    if (projectTrusted !== null) context.isProjectTrusted = () => projectTrusted;
    return context;
  }

  async emit(event: string, payload: Record<string, unknown>, context: ExtensionContextPort): Promise<unknown[]> {
    const results = [];
    for (const handler of this.handlers.get(event) ?? []) results.push(await handler({ type: event, ...payload }, context));
    return results;
  }
}

const roots: string[] = [];
const TRUST_REQUIRED = "codeArbiter host: pi waiting for project trust - run /trust in Pi, approve this project, then start a new session";

async function project(context: string): Promise<string> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-activation-"));
  roots.push(root);
  if (context !== "") {
    await mkdir(resolve(root, ".codearbiter"), { recursive: true });
    await writeFile(resolve(root, ".codearbiter", "CONTEXT.md"), context, "utf8");
  }
  return root;
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("Pi activation", () => {
  test("bounds the OS environment and resolves the configured shell to an absolute identity", async () => {
    expect(boundedPiEnvironment({ SAFE: "1", OMITTED: undefined })).toEqual([["SAFE", "1"], ["OMITTED", undefined]]);
    expect(boundedPiEnvironment(Object.fromEntries(Array.from({ length: 257 }, (_, index) => [`K${index}`, "v"])))).toBeUndefined();
    expect(boundedPiEnvironment(new Proxy({}, {}))).toBeUndefined();
    await expect(resolvePiBackgroundShell(process.execPath, {}, process.platform)).resolves.toBe(await realpath(process.execPath));
    await expect(resolvePiBackgroundShell("definitely-not-a-shell", {}, process.platform)).resolves.toBeUndefined();
  });
  test("installs parent jobs only for trusted interactive sessions and waits for verified shutdown cleanup", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    await mkdir(resolve(packageRoot, "extensions"), { recursive: true });
    await writeFile(resolve(packageRoot, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
    const host = new FakePi(packageRoot, []);
    const stops: string[] = [];
    let currentLifecycle: (() => object | undefined) | undefined;
    let dispatchActivity: (() => { publish(event: never): void } | undefined) | undefined;
    let backgroundActivity: (() => { publish(event: never): void } | undefined) | undefined;
    let releaseStop!: () => void;
    let blockStop = false;
    const stopped = new Promise<void>((resolveStopped) => { releaseStop = resolveStopped; });
    let installedBackgroundFactory = false;
    const controller: NativeBackgroundController = {
      register: (context) => {
        if (context.mode !== "tui" || context.hasUI !== true || context.isProjectTrusted?.() !== true) return false;
        host.registerCommand("ca-jobs", { handler: () => undefined });
        return true;
      },
      activate: () => true,
      toolFactory: () => ({ name: "codearbiter_background_bash", execute: async () => ({}) }),
      stop: async (reason) => {
        expect(currentLifecycle?.()).toBeUndefined();
        stops.push(reason);
        if (blockStop) await stopped;
        return true;
      },
      healthy: () => true,
    };
    installParent(host, {
      bridge: new FakeBridge(), catalog: [], packageRoot,
      loadPersona: async () => "persona",
      readActivation: async () => true,
      installDispatch: (_lifecycle, activity) => { dispatchActivity = activity; },
      installBackground: (lifecycle, activity) => {
        currentLifecycle = lifecycle;
        backgroundActivity = activity;
        return controller;
      },
      installEnforcement: async (_root, _context, _mode, backgroundFactory) => {
        installedBackgroundFactory = backgroundFactory !== undefined;
      },
    });
    const printContext = { ...host.context(cwd), mode: "print" as const, hasUI: false, sessionManager: { getSessionId: () => "print" } };
    await host.emit("session_start", {}, printContext);
    expect(host.registered.has("ca-jobs")).toBe(false);
    expect(installedBackgroundFactory).toBe(false);

    const context = { ...host.context(cwd), mode: "tui" as const, hasUI: true, sessionManager: { getSessionId: () => "session-1" } };
    await host.emit("session_start", {}, context);
    expect(dispatchActivity?.()).toBeDefined();
    expect(backgroundActivity?.()).toBe(dispatchActivity?.());
    expect(host.registered.has("ca-jobs")).toBe(true);
    expect(installedBackgroundFactory).toBe(true);
    const before = stops.length;
    await host.emit("session_before_switch", { reason: "resume" }, context);
    expect(stops).toHaveLength(before);

    blockStop = true;
    const shutdown = host.emit("session_shutdown", { reason: "resume" }, context);
    await Promise.resolve();
    expect(stops.at(-1)).toBe("session-switch");
    expect(backgroundActivity?.()).toBeDefined();
    let complete = false;
    void shutdown.then(() => { complete = true; });
    await Promise.resolve();
    expect(complete).toBe(false);
    releaseStop();
    await shutdown;
    expect(complete).toBe(true);
    expect(backgroundActivity?.()).toBeUndefined();
  });
  test("wires the native plan mode only to the current parent interactive lifecycle", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    await mkdir(resolve(packageRoot, "extensions"), { recursive: true });
    await writeFile(resolve(packageRoot, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
    await writeFile(resolve(packageRoot, "package.json"), JSON.stringify({
      name: "ca-pi", pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
    }), "utf8");
    const ledger = "| Task | Status |\n|---|---|\n| T01 | PENDING |\n";
    const appended: Array<{ customType: string; data: unknown }> = [];
    let getMode: (() => "plan" | "execute") | undefined;
    const bridge: BridgePort = {
      call: async (request) => request.event === "plan_file"
        ? {
          version: 1, outcome: "notice", resultPatch: { planFile: {
            status: "unchanged", exists: true,
            hash: createHash("sha256").update(ledger).digest("hex"),
            contentBase64: Buffer.from(ledger).toString("base64"),
          } },
        }
        : { version: 1, outcome: "notice", context: "host: pi" },
    };
    const host = new FakePi(packageRoot, []);
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "PERSONA",
      planCommandDescriptor: { "ca-plan": "planning-write" },
      appendPlanEntry: (customType, data) => { appended.push({ customType, data }); },
      installEnforcement: (_root, _context, currentMode) => { getMode = currentMode; },
    });
    const context = host.context(cwd);
    context.mode = "tui";
    context.hasUI = true;
    context.sessionManager = { getSessionId: () => "session-1", getEntries: () => [] };

    await host.emit("session_start", {}, context);
    expect(host.registered.has("ca-plan")).toBe(true);
    expect(getMode?.()).toBe("execute");
    await host.registered.get("ca-plan")!.handler("enter sprint-alpha", context);
    expect(getMode?.()).toBe("plan");
    expect(appended).toHaveLength(1);
    const planNotice = host.notifications.at(-1);

    await host.emit("session_before_switch", { reason: "new" }, context);
    expect(getMode?.()).toBe("plan");
    expect(appended).toHaveLength(1);
    expect(host.notifications.at(-1)).toEqual(planNotice);
    await host.registered.get("ca-plan")!.handler("status", context);
    expect(getMode?.()).toBe("plan");
    expect(appended).toHaveLength(1);
    await host.emit("session_shutdown", { reason: "new" }, context);
    expect(getMode?.()).toBe("execute");
  });

  test("reports a truthful native ownership startup collision and blocks invocation before effects", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    await mkdir(resolve(packageRoot, "extensions"), { recursive: true });
    await writeFile(resolve(packageRoot, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
    await writeFile(resolve(packageRoot, "package.json"), JSON.stringify({
      name: "ca-pi", pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
    }), "utf8");
    const bridge = new FakeBridge();
    const appended: unknown[] = [];
    const host = new FakePi(packageRoot, []);
    host.extraCommands.push({
      name: "ca-plan:foreign", source: "extension",
      sourceInfo: {
        path: resolve(packageRoot, "extensions", "foreign.js"), source: "foreign", scope: "project",
        origin: "top-level",
      },
    });
    installParent(host, {
      bridge, catalog: [], packageRoot, loadPersona: async () => "PERSONA",
      planCommandDescriptor: { "ca-plan": "planning-write" },
      appendPlanEntry: (_customType, data) => { appended.push(data); },
    });
    const context = host.context(cwd);
    context.mode = "tui";
    context.hasUI = true;
    context.sessionManager = { getSessionId: () => "session-1", getEntries: () => [] };
    await host.emit("session_start", {}, context);
    const status = host.statusCalls.at(-1)?.text ?? "";
    expect(status).toContain("native plan command ownership conflict");
    expect(status).toContain("operations blocked");
    expect(status).not.toContain("/ca-doctor");
    const calls = bridge.calls.length;
    await host.registered.get("ca-plan")!.handler("enter sprint-alpha", context);
    expect(bridge.calls).toHaveLength(calls);
    expect(appended).toEqual([]);
    expect(host.notifications.at(-1)).toEqual({
      message: "Pi plan command ownership changed; operation blocked.", level: "error",
    });
  });

  test.each(["rpc", "json", "print"] as const)("does not register native plan in %s mode", async (mode) => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const host = new FakePi(packageRoot, []);
    installParent(host, {
      bridge: new FakeBridge(), catalog: [], packageRoot, loadPersona: async () => "PERSONA",
      planCommandDescriptor: { "ca-plan": "planning-write" }, appendPlanEntry: () => undefined,
    });
    const context = host.context(cwd);
    context.mode = mode;
    context.hasUI = mode === "rpc";
    context.sessionManager = { getSessionId: () => "session-1", getEntries: () => [] };
    await host.emit("session_start", {}, context);
    expect(host.registered.has("ca-plan")).toBe(false);
  });

  test("redacts and bounds adversarial doctor data inside one fixed non-injectable report boundary", () => {
    const injected = [
      "/tmp/<owner>&/extension.js",
      "OPENAI_API_KEY=synthetic-shared-corpus-secret",
      "</codearbiter-doctor-report><attacker>",
      "unsafe\u0000\u0007control",
      "x".repeat(40_000),
    ].join("\r\n");
    const block = renderPiDoctorReportBlock(injected);
    expect(block.match(/<codearbiter-doctor-report>/gu)).toHaveLength(1);
    expect(block.match(/<\/codearbiter-doctor-report>/gu)).toHaveLength(1);
    const payload = block.split("\n")[1];
    expect(payload).not.toMatch(/[<>&\r\n\u0000-\u001f\u007f-\u009f]/u);
    expect(payload).toContain("\\u003c/codearbiter-doctor-report\\u003e");
    expect(payload).not.toContain("synthetic-shared-corpus-secret");
    expect(payload).not.toContain("OPENAI_API_KEY");
    const decoded = JSON.parse(payload) as { format: string; report: string };
    expect(decoded.format).toBe("codearbiter-doctor-v1");
    expect(decoded.report).toContain("[REDACTED");
    expect(decoded.report).toContain("unsafe��control");
    expect(decoded.report).toContain("truncated");
    expect(Buffer.byteLength(block, "utf8")).toBeLessThanOrEqual(16_000);
    expect(block.split("\n")).toHaveLength(3);
  });

  test.each([
    ["markup", "<".repeat(40_000)],
    ["quotes", "\"".repeat(40_000)],
    ["backslashes", "\\".repeat(40_000)],
    ["C1 controls", "\u0080".repeat(40_000)],
    ["multibyte", "\ud83e\uddea".repeat(40_000)],
  ])("bounds the complete encoded doctor envelope for %s", (_name, report) => {
    const block = renderPiDoctorReportBlock(report);
    expect(Buffer.byteLength(block, "utf8")).toBeLessThanOrEqual(16_000);
    expect(block.match(/<codearbiter-doctor-report>/gu)).toHaveLength(1);
    expect(block.match(/<\/codearbiter-doctor-report>/gu)).toHaveLength(1);
    const payload = block.split("\n")[1]!;
    const decoded = JSON.parse(payload) as { format: string; report: string };
    expect(decoded.format).toBe("codearbiter-doctor-v1");
    expect(decoded.report).toContain("truncated");
  });
  test("recognizes canonical enabled frontmatter in .codearbiter/CONTEXT.md", async () => {
    const enabled = await project("---\narbiter: enabled\n---\nbody\n");
    const bodyOnly = await project("arbiter: enabled\n");
    const wrongValue = await project("---\narbiter: disabled\n---\narbiter: enabled\n");
    const malformed = await project("---\narbiter: enabled\nbody\n");
    const eofDelimiter = await project("---\narbiter: enabled\n---");
    const duplicate = await project("---\narbiter: enabled\narbiter: enabled\n---\n");
    const bare = await project("");

    await expect(isEnabled(enabled)).resolves.toBe(true);
    await expect(isEnabled(bodyOnly)).resolves.toBe(false);
    await expect(isEnabled(wrongValue)).resolves.toBe(false);
    await expect(isEnabled(malformed)).resolves.toBe(false);
    await expect(isEnabled(eofDelimiter)).resolves.toBe(true);
    await expect(isEnabled(duplicate)).resolves.toBe(true);
    await expect(isEnabled(bare)).resolves.toBe(false);
  });

  test.skipIf(process.platform !== "win32")("reads update availability only from the fixed user-global cache and installed package version", async () => {
    const packageRoot = await project("");
    const fakeHome = await project("");
    const stateRoot = resolve(fakeHome, ".codearbiter");
    await mkdir(stateRoot);
    await writeFile(resolve(packageRoot, "package.json"), '{"name":"ca-pi","version":"1.4.0"}\n', "utf8");
    await writeFile(resolve(stateRoot, "update-state.json"), '{"latest":"1.5.0","checked_at":1}\n', "utf8");
    const previousProfile = process.env.USERPROFILE;
    process.env.USERPROFILE = fakeHome;
    try {
      await expect(readCachedUpdateVersion(packageRoot)).resolves.toBe("1.5.0");
      await writeFile(resolve(stateRoot, "update-state.json"), '{"latest":"1.3.9","checked_at":1}\n', "utf8");
      await expect(readCachedUpdateVersion(packageRoot)).resolves.toBeUndefined();
      await writeFile(resolve(stateRoot, "update-state.json"), "x".repeat(4_097), "utf8");
      await expect(readCachedUpdateVersion(packageRoot)).resolves.toBeUndefined();
      const target = resolve(fakeHome, "update-target.json");
      await writeFile(target, '{"latest":"9.9.9","checked_at":1}\n', "utf8");
      await rm(resolve(stateRoot, "update-state.json"));
      await symlink(target, resolve(stateRoot, "update-state.json"), "file");
      await expect(readCachedUpdateVersion(packageRoot)).resolves.toBeUndefined();
    } finally {
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
    }
  });

  test("matches the canonical shared activation contract", async () => {
    const contractPath = resolve(import.meta.dirname, "../../../..", "core", "activation-contract.json");
    const contract = JSON.parse(await readFile(contractPath, "utf8")) as ActivationContract;
    expect(contract.version).toBe(1);
    expect(contract.canonicalParser).toBe("core/pysrc/_hooklib.py::frontmatter_enabled_text");
    for (const fixture of contract.fixtures) {
      const cwd = await project(fixture.text);
      expect.soft(await isEnabled(cwd), fixture.name).toBe(fixture.enabled);
    }
  });

  test("stays fully dormant without arbiter: enabled", async () => {
    const cwd = await project("");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    let bridgePreparations = 0;
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "GENERATED PERSONA",
      prepareBridge: () => { bridgePreparations += 1; },
    });

    await host.emit("session_start", { reason: "startup" }, host.context(cwd));

    expect(bridgePreparations).toBe(0);
    expect(bridge.calls).toEqual([]);
    expect(host.userMessages).toEqual([]);
    expect(host.statusCalls).toEqual([]);
  });

  test.each([
    ["missing", null],
    ["false", false],
  ] as const)("keeps enabled %s trust before every repository-aware startup operation", async (_name, trusted) => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    const operations: string[] = [];
    const readiness: string[] = [];
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      resetBridge: () => { operations.push("reset"); },
      prepareBridge: () => { operations.push("prepare"); },
      installEnforcement: () => { operations.push("enforce"); },
      loadPersona: async () => { operations.push("persona"); return "PERSONA"; },
      enforcementReadiness: {
        beginActivation: () => { readiness.push("activation"); },
        beginBootstrap: () => { readiness.push("bootstrap"); },
        markReady: () => { readiness.push("ready"); },
        deactivate: () => { readiness.push("inactive"); },
      },
    });
    const context = host.context(cwd, trusted);

    await host.emit("session_start", {}, context);
    const beforeAgent = await host.emit("before_agent_start", { systemPrompt: "base" }, context);

    expect(operations).toEqual(["reset"]);
    expect(bridge.calls).toEqual([]);
    expect(beforeAgent).toEqual([undefined]);
    expect(readiness).toEqual(["inactive", "activation"]);
    expect(host.statusCalls).toEqual([{ key: "codearbiter", text: TRUST_REQUIRED }]);
    expect(host.notifications).toEqual([{ message: TRUST_REQUIRED, level: "warning" }]);

    await host.emit("session_shutdown", {}, context);
    expect(host.statusCalls.at(-1)).toEqual({ key: "codearbiter", text: undefined });
    expect(readiness.at(-1)).toBe("inactive");
  });

  test("refreshes normally when the same process changes from untrusted to trusted", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    const operations: string[] = [];
    let trusted = false;
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      resetBridge: () => { operations.push("reset"); },
      prepareBridge: () => { operations.push("prepare"); },
      installEnforcement: () => { operations.push("enforce"); },
      loadPersona: async () => { operations.push("persona"); return "PERSONA"; },
    });
    const context = host.context(cwd);
    context.isProjectTrusted = () => trusted;

    await host.emit("session_start", {}, context);
    expect(operations).toEqual(["reset"]);
    expect(bridge.calls).toEqual([]);
    trusted = true;
    await host.emit("session_start", {}, context);

    expect(operations).toEqual(["reset", "reset", "prepare", "enforce", "persona"]);
    expect(bridge.calls.map((call) => call.event)).toEqual(["session_start"]);
    expect(host.statusCalls).toContainEqual({ key: "codearbiter", text: undefined });
    expect(host.statusCalls.at(-1)?.text).toBe("codeArbiter host: pi governed");
  });

  test("prepares the bridge only after enabled activation reaches Pi trust context", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    const preparations: Array<{ cwd: string; trusted: boolean }> = [];
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "GENERATED PERSONA",
      prepareBridge: (preparedCwd, context) => {
        preparations.push({ cwd: preparedCwd, trusted: context.isProjectTrusted?.() ?? false });
      },
    });
    const context = host.context(cwd);
    context.isProjectTrusted = () => true;

    await host.emit("session_start", { reason: "startup" }, context);

    expect(preparations).toEqual([{ cwd, trusted: true }]);
    expect(bridge.calls).toHaveLength(1);
  });

  test("keeps the actual dormant doctor command side-effect free while the bridge is unprepared", async () => {
    const cwd = await project("");
    const packageRoot = await project("");
    const stateRoot = resolve(cwd, ".codearbiter");
    const auditPath = resolve(stateRoot, "gate-events.log");
    const sentinel = resolve(cwd, "python-sentinel");
    const extensionPath = resolve(packageRoot, "extensions", "codearbiter.js");
    const childPath = resolve(packageRoot, "extensions", "codearbiter-child.js");
    const bridgeScript = resolve(packageRoot, "hooks", "pi-bridge.py");
    const skillPath = resolve(packageRoot, "skills", "ca-doctor", "SKILL.md");
    await mkdir(stateRoot);
    await mkdir(resolve(packageRoot, "extensions"));
    await mkdir(resolve(packageRoot, "hooks"));
    await mkdir(resolve(packageRoot, "skills", "ca-doctor"), { recursive: true });
    await writeFile(auditPath, "existing-audit\n", "utf8");
    await writeFile(
      resolve(packageRoot, "package.json"),
      '{"name":"ca-pi","version":"0.1.0","pi":{"extensions":["./extensions/codearbiter.js"],"skills":["./skills"]}}\n',
      "utf8",
    );
    await writeFile(extensionPath, "export default () => {};\n", "utf8");
    await writeFile(childPath, "export default () => {};\n", "utf8");
    await writeFile(
      bridgeScript,
      `from pathlib import Path\nPath(${JSON.stringify(sentinel.replaceAll("\\", "/"))}).write_text("executed", encoding="utf-8")\n`,
      "utf8",
    );
    await writeFile(skillPath, "# Doctor\n\nRead-only diagnostics.\n", "utf8");
    const catalog = [{ name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md" }];
    const host = new FakePi(packageRoot, catalog);
    const bridge: BridgePort = {
      call: async (request, signal) => await new BridgeClient({
        bridgeScript,
        packageRoot,
        pythonExecutable: undefined,
        toolClasses: {},
      }).call(request, signal),
    };
    let doctorHealth: unknown;
    installParent(host, {
      bridge,
      catalog,
      packageRoot,
      loadPersona: async () => "GENERATED PERSONA",
      doctorReport: async (context, health) => {
        doctorHealth = health;
        const input = await collectPiDoctorInput({
          packageRoot,
          packageScope: "user",
          extensionPath,
          runtime: {
            piVersion: "0.80.6",
            nodeVersion: process.versions.node,
            pythonMajor: null,
            cliEntry: resolve(packageRoot, "runtime", "cli.js"),
            moduleEntry: resolve(packageRoot, "runtime", "index.js"),
            packageRoot: resolve(packageRoot, "runtime"),
          },
          context,
          commands: host.getCommands(),
          catalog,
          bridge,
          bridgePrepared: false,
          footerExpected: health.footer.expected,
          footerInitialized: health.footer.initialized,
          backgroundExpected: health.background.expected,
          backgroundInitialized: health.background.initialized,
          backgroundHealthy: health.background.healthy,
          projectTrustRequired: false,
          childPath,
          wrapperSourcePath: extensionPath,
          activeTools: [],
          allTools: [],
          expansionFingerprints: {},
          childFingerprint: "0".repeat(64),
        });
        return formatPiDoctorReport(diagnosePi(input));
      },
    });
    const rootEntriesBefore = await readdir(cwd);
    const stateEntriesBefore = await readdir(stateRoot);

    await host.registered.get("ca-doctor")!.handler("", host.context(cwd));

    await expect(access(sentinel)).rejects.toThrow();
    await expect(readFile(auditPath, "utf8")).resolves.toBe("existing-audit\n");
    await expect(readdir(cwd)).resolves.toEqual(rootEntriesBefore);
    await expect(readdir(stateRoot)).resolves.toEqual(stateEntriesBefore);
    expect(host.userMessages).toHaveLength(1);
    expect(doctorHealth).toEqual({
      footer: { expected: false, initialized: false },
      background: { expected: false, initialized: false, healthy: false },
    });
  });

  test("appends generated persona and refreshed state without retaining the raw prompt", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    installParent(host, { bridge, catalog: [], packageRoot, loadPersona: async () => "GENERATED PERSONA" });
    const context = host.context(cwd);

    await host.emit("session_start", { reason: "startup" }, context);
    const results = await host.emit("before_agent_start", {
      prompt: "RAW USER PROMPT MUST NOT BE STORED",
      systemPrompt: "ORIGINAL CHAINED SYSTEM PROMPT",
      systemPromptOptions: {},
    }, context);

    expect(bridge.calls.map((call) => call.event)).toEqual(["session_start", "before_agent_start"]);
    expect(JSON.stringify(bridge.calls)).not.toContain("RAW USER PROMPT MUST NOT BE STORED");
    expect(results).toHaveLength(1);
    expect(results[0]).toEqual({
      systemPrompt: expect.stringContaining("ORIGINAL CHAINED SYSTEM PROMPT\n\nGENERATED PERSONA"),
    });
    expect((results[0] as { systemPrompt: string }).systemPrompt).toContain("stage: verification\nhost: pi");
    expect((results[0] as { systemPrompt: string }).systemPrompt).not.toContain("RAW USER PROMPT MUST NOT BE STORED");
  });

  test("surfaces an advisory session bridge failure as degraded without blocking startup", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const warnings: string[] = [];
    const host = new FakePi(packageRoot, []);
    const bridge: BridgePort = {
      call: async () => ({ version: 1, outcome: "warn", ruleId: "PI-BRIDGE", message: "bridge failed; run /ca-doctor" }),
    };
    installParent(host, { bridge, catalog: [], packageRoot, loadPersona: async () => "PERSONA" });
    const context = host.context(cwd);
    context.ui.notify = (message) => warnings.push(message);

    await host.emit("session_start", {}, context);

    expect(warnings).toEqual(["bridge failed; run /ca-doctor"]);
    expect(host.statusCalls.at(-1)?.text).toContain("degraded");
    expect(host.statusCalls.at(-1)?.text).toContain("/ca-doctor");
  });

  test("hard-stops enabled activation on enforcement failure and retries successfully", async () => {
    const cwd = await project("---\narbiter: enabled\n---\n");
    const packageRoot = await project("");
    const bridge = new FakeBridge();
    const host = new FakePi(packageRoot, []);
    let attempts = 0;
    const readiness: string[] = [];
    installParent(host, {
      bridge,
      catalog: [],
      packageRoot,
      loadPersona: async () => "PERSONA",
      installEnforcement: () => { attempts += 1; if (attempts === 1) throw new Error("guard failed"); },
      enforcementReadiness: {
        beginActivation: () => { readiness.push("activation"); },
        beginBootstrap: () => { readiness.push("begin"); },
        markReady: () => { readiness.push("ready"); },
        deactivate: () => { readiness.push("inactive"); },
      },
    });
    const context = host.context(cwd);
    const firstStart = host.emit("session_start", {}, context);
    expect(readiness).toEqual(["inactive", "activation"]);
    await expect(firstStart).rejects.toThrow("/ca-doctor");
    expect(bridge.calls).toEqual([]);
    // A failed enabled activation stays bootstrap-active and unready so the
    // preinstalled fail-closed handler continues blocking mutations until the
    // next shutdown/start transition explicitly deactivates it.
    expect(readiness).toEqual(["inactive", "activation", "begin"]);
    await host.emit("session_shutdown", {}, context);
    expect(host.statusCalls.at(-1)).toEqual({ key: "codearbiter", text: undefined });
    expect(readiness).toEqual(["inactive", "activation", "begin", "inactive"]);
    const retry = host.emit("session_start", {}, context);
    expect(readiness).toEqual(["inactive", "activation", "begin", "inactive", "inactive", "activation"]);
    await expect(retry).resolves.toHaveLength(1);
    expect(attempts).toBe(2);
    expect(bridge.calls).toHaveLength(1);
    expect(readiness).toEqual(["inactive", "activation", "begin", "inactive", "inactive", "activation", "begin", "ready"]);
  });

  test("removes mutable runtime identity exports and touches no API on incompatibility", () => {
    expect("HOST_PI_VERSION" in extensionModule).toBe(false);
    expect("HOST_RUNTIME_IDENTITY" in extensionModule).toBe(false);
    let apiAccesses = 0;
    const api = new Proxy({}, { get: () => { apiAccesses += 1; return () => undefined; } }) as ExtensionAPI;
    expect(() => createCodeArbiterPi({
      piVersion: "0.80.4",
      nodeVersion: "24.0.0",
      pythonMajor: 3,
    })(api)).toThrow("/ca-doctor");
    expect(apiAccesses).toBe(0);
  });
});
