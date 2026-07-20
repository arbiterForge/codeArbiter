import { mkdir, mkdtemp, readFile, rm, symlink, unlink, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { existsSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  assertCommandOwnership,
  assertNativeJobsCommandOwnership,
  assertNativePlanCommandOwnership,
  createNativeBackgroundController,
  createNativePlanController,
  registerAliases,
} from "../src/commands.ts";
import type { CommandCatalogEntry, ExtensionContextPort, ParentPiPort, SlashCommand } from "../src/contracts.ts";
import type { BackgroundJobRuntime, BackgroundJobSnapshot, BackgroundJobStopReason } from "../src/background-jobs.ts";

const pluginRoot = resolve(import.meta.dirname, "..", "..");
const catalogPath = resolve(pluginRoot, "generated", "command-catalog.json");
const roots: string[] = [];
const links: string[] = [];

async function tempPlugin(): Promise<{ root: string; catalog: CommandCatalogEntry[] }> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-command-"));
  roots.push(root);
  const skillPath = "skills/ca-feature/SKILL.md";
  await mkdir(resolve(root, "extensions"), { recursive: true });
  await mkdir(dirname(resolve(root, skillPath)), { recursive: true });
  await writeFile(resolve(root, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
  await writeFile(resolve(root, "package.json"), JSON.stringify({
    name: "ca-pi",
    pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
  }) + "\n", "utf8");
  await writeFile(
    resolve(root, skillPath),
    "---\nname: ca-feature\ndescription: Build a feature.\n---\n\n# Feature body\n\nKeep this body.\n",
    "utf8",
  );
  return { root, catalog: [{ name: "feature", description: "Build a feature.", skillPath }] };
}

afterEach(async () => {
  await Promise.all(links.splice(0).map((link) => unlink(link).catch(() => undefined)));
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("generated Pi command aliases", () => {
  test("cancels without publishing or auditing when the tool signal aborts during runtime launch", async () => {
    const fixture = await tempPlugin();
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
      sendUserMessage: () => undefined,
      getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
    } satisfies ParentPiPort;
    const lease = Object.freeze({});
    const abort = new AbortController();
    const authorizationChecks: boolean[] = [];
    let cancels = 0;
    let job: BackgroundJobSnapshot = Object.freeze({ id: 1, label: "launch-abort", state: "active", status: "running", timeoutMs: null, outputBytes: 0 });
    const runtime: BackgroundJobRuntime = {
      launch: async (input) => {
        authorizationChecks.push(input.authorization.isCurrent(input.authorization.lease));
        abort.abort();
        authorizationChecks.push(input.authorization.isCurrent(input.authorization.lease));
        return job;
      },
      cancel: async () => {
        cancels += 1;
        job = Object.freeze({ ...job, state: "cancelled", status: "cancelled" });
        return true;
      },
      stop: async () => true, settled: async () => undefined, health: () => ({ healthy: true }),
      getJob: () => job, listJobs: () => [job], activeJobIds: () => job.state === "active" ? [1] : [],
      tail: () => "", dispose: async () => true,
    };
    const audits: Array<Record<string, unknown>> = [];
    const controller = createNativeBackgroundController(pi, {
      packageRoot: fixture.root, currentLifecycle: () => lease, toolOwnershipValid: () => true,
      createRuntime: () => runtime, createAuditLifecycleId: () => "a".repeat(64),
      resolveLaunch: async () => ({ shellPath: process.execPath, env: [] }),
      audit: async (_cwd, facts) => { audits.push({ ...facts }); return true; },
    });
    const notifications: string[] = [];
    const context: ExtensionContextPort = {
      cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
      isProjectTrusted: () => true, sessionManager: { getSessionId: () => "session" },
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    controller.register(context); expect(controller.activate(context)).toBe(true);

    const result = await controller.toolFactory(fixture.root).execute(
      "launch-abort", { command: "work", label: "launch-abort" }, abort.signal, undefined, context,
    );

    expect(authorizationChecks).toEqual([true, false]);
    expect(cancels).toBe(1);
    expect(runtime.activeJobIds()).toEqual([]);
    expect(audits).toEqual([]);
    expect(result.isError).toBe(true);
    expect(JSON.stringify(result)).not.toContain("started");
    expect(notifications.some((message) => message.includes("Background job completed:"))).toBe(false);
  });

  test("cancels and terminal-audits without publishing when the tool signal aborts during launch audit", async () => {
    const fixture = await tempPlugin();
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
      sendUserMessage: () => undefined,
      getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
    } satisfies ParentPiPort;
    const lease = Object.freeze({});
    const abort = new AbortController();
    let releaseSettled!: () => void;
    const settled = new Promise<void>((resolveSettled) => { releaseSettled = resolveSettled; });
    let cancels = 0;
    let job: BackgroundJobSnapshot = Object.freeze({ id: 1, label: "audit-abort", state: "active", status: "running", timeoutMs: null, outputBytes: 0 });
    const runtime: BackgroundJobRuntime = {
      launch: async () => job,
      cancel: async () => {
        cancels += 1;
        job = Object.freeze({ ...job, state: "cancelled", status: "cancelled" });
        releaseSettled();
        return true;
      },
      stop: async () => true, settled: async () => await settled, health: () => ({ healthy: true }),
      getJob: () => job, listJobs: () => [job], activeJobIds: () => job.state === "active" ? [1] : [],
      tail: () => "", dispose: async () => true,
    };
    const audits: Array<Record<string, unknown>> = [];
    const controller = createNativeBackgroundController(pi, {
      packageRoot: fixture.root, currentLifecycle: () => lease, toolOwnershipValid: () => true,
      createRuntime: () => runtime, createAuditLifecycleId: () => "b".repeat(64), now: () => 100,
      resolveLaunch: async () => ({ shellPath: process.execPath, env: [] }),
      audit: async (_cwd, facts) => {
        audits.push({ ...facts });
        if (facts.event === "launch") abort.abort();
        return true;
      },
    });
    const notifications: string[] = [];
    const context: ExtensionContextPort = {
      cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
      isProjectTrusted: () => true, sessionManager: { getSessionId: () => "session" },
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    controller.register(context); expect(controller.activate(context)).toBe(true);

    const result = await controller.toolFactory(fixture.root).execute(
      "audit-abort", { command: "work", label: "audit-abort" }, abort.signal, undefined, context,
    );
    await new Promise<void>((resolveTick) => setImmediate(resolveTick));

    expect(cancels).toBe(1);
    expect(runtime.activeJobIds()).toEqual([]);
    expect(result.isError).toBe(true);
    expect(JSON.stringify(result)).not.toContain("started");
    expect(notifications.some((message) => message.includes("Background job completed:"))).toBe(false);
    expect(audits.map((row) => row.event)).toEqual(["launch", "terminal"]);
    expect(audits[1]).toMatchObject({
      lifecycleId: audits[0]!.lifecycleId, correlation: audits[0]!.correlation,
      state: "cancelled", exitClass: "cancelled",
    });
  });

  test("blocks background publication when trust or exact tool registry authority changes across awaits", async () => {
    for (const phase of ["resolve", "launch-active", "audit-source"] as const) {
      const fixture = await tempPlugin();
      const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
      const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
      const pi = {
        on: () => undefined,
        registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
        sendUserMessage: () => undefined,
        getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
      } satisfies ParentPiPort;
      const lease = Object.freeze({});
      let trusted = true;
      let toolActive = true;
      let toolSourceOwned = true;
      let launchCalls = 0;
      let spawns = 0;
      let cancels = 0;
      let releaseSettled!: () => void;
      const settled = new Promise<void>((resolveSettled) => { releaseSettled = resolveSettled; });
      let job: BackgroundJobSnapshot = Object.freeze({ id: 1, label: phase, state: "active", status: "running", timeoutMs: null, outputBytes: 0 });
      const runtime: BackgroundJobRuntime = {
        launch: async (input) => {
          launchCalls += 1;
          if (phase === "launch-active") toolActive = false;
          if (!input.authorization.isCurrent(input.authorization.lease)) return undefined;
          spawns += 1;
          return job;
        },
        cancel: async () => {
          cancels += 1;
          job = Object.freeze({ ...job, state: "cancelled", status: "cancelled" });
          releaseSettled();
          return true;
        },
        stop: async () => true,
        settled: async () => await settled,
        health: () => ({ healthy: true }),
        getJob: () => job,
        listJobs: () => [job],
        activeJobIds: () => [1],
        tail: () => "",
        dispose: async () => true,
      };
      const audits: Array<Record<string, unknown>> = [];
      const controller = createNativeBackgroundController(pi, {
        packageRoot: fixture.root,
        currentLifecycle: () => lease,
        toolOwnershipValid: () => toolActive && toolSourceOwned,
        createRuntime: () => runtime,
        createAuditLifecycleId: () => "e".repeat(64),
        resolveLaunch: async () => {
          if (phase === "resolve") trusted = false;
          return { shellPath: process.execPath, env: [] };
        },
        audit: async (_cwd, facts) => {
          audits.push({ ...facts });
          if (phase === "audit-source" && facts.event === "launch") toolSourceOwned = false;
          return true;
        },
      });
      const notifications: string[] = [];
      const context: ExtensionContextPort = {
        cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
        isProjectTrusted: () => trusted,
        sessionManager: { getSessionId: () => "session" },
        ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
      };
      expect(controller.register(context)).toBe(true);
      expect(controller.activate(context)).toBe(true);
      const result = await controller.toolFactory(fixture.root).execute("call", { command: "never publish", label: phase }, undefined, undefined, context);
      expect(result.isError, phase).toBe(true);
      expect(JSON.stringify(result), phase).not.toContain("started");
      expect(notifications.some((message) => message.includes("started")), phase).toBe(false);
      expect({ launchCalls, spawns, cancels }, phase).toEqual(phase === "resolve"
        ? { launchCalls: 0, spawns: 0, cancels: 0 }
        : phase === "launch-active" ? { launchCalls: 1, spawns: 0, cancels: 0 }
          : { launchCalls: 1, spawns: 1, cancels: 1 });
      if (phase === "audit-source") {
        await new Promise<void>((resolveTick) => setImmediate(resolveTick));
        expect(audits.map((row) => row.event)).toEqual(["launch", "terminal"]);
        expect(audits[1]).toMatchObject({ correlation: audits[0]!.correlation, state: "cancelled", exitClass: "cancelled" });
      }
    }
  });
  test("latches unhealthy on unproven settlement or terminal-audit failure and never announces completion", async () => {
    for (const failure of ["nonterminal", "runtime-unhealthy", "audit-failure"] as const) {
      const fixture = await tempPlugin();
      const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
      const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
      const pi = {
        on: () => undefined,
        registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
        sendUserMessage: () => undefined,
        getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
      } satisfies ParentPiPort;
      const lease = Object.freeze({});
      let release!: () => void;
      const settled = new Promise<void>((resolveSettled) => { release = resolveSettled; });
      let healthy = true;
      let launches = 0;
      let job: BackgroundJobSnapshot = Object.freeze({ id: 1, label: failure, state: "active", status: "running", timeoutMs: null, outputBytes: 4 });
      const runtime: BackgroundJobRuntime = {
        launch: async () => { launches += 1; return job; }, cancel: async () => true,
        stop: async () => true, settled: async () => await settled,
        health: () => healthy ? { healthy: true } : { healthy: false, diagnostic: "run /ca-doctor" },
        getJob: () => job, listJobs: () => [job], activeJobIds: () => [1], tail: () => "data", dispose: async () => true,
      };
      const audits: Array<Record<string, unknown>> = [];
      const controller = createNativeBackgroundController(pi, {
        packageRoot: fixture.root, currentLifecycle: () => lease, toolOwnershipValid: () => true,
        createRuntime: () => runtime, createAuditLifecycleId: () => "f".repeat(64), now: () => 10,
        resolveLaunch: async () => ({ shellPath: process.execPath, env: [] }),
        audit: async (_cwd, facts) => {
          audits.push({ ...facts });
          return !(failure === "audit-failure" && facts.event === "terminal");
        },
      });
      const notifications: string[] = [];
      const context: ExtensionContextPort = {
        cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
        isProjectTrusted: () => true, sessionManager: { getSessionId: () => "session" },
        ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
      };
      controller.register(context); expect(controller.activate(context)).toBe(true);
      const tool = controller.toolFactory(fixture.root);
      expect((await tool.execute("one", { command: "work", label: failure }, undefined, undefined, context)).isError).toBe(false);
      if (failure !== "nonterminal") job = Object.freeze({ ...job, state: "completed", status: "completed" });
      if (failure === "runtime-unhealthy") healthy = false;
      release();
      await new Promise<void>((resolveTick) => setImmediate(resolveTick));
      expect(controller.healthy(), failure).toBe(false);
      expect(notifications.filter((message) => message.includes("run /ca-doctor")), failure).toHaveLength(1);
      expect(notifications.some((message) => message.startsWith("Background job completed:")), failure).toBe(false);
      expect(audits.filter((row) => row.event === "terminal"), failure).toHaveLength(failure === "audit-failure" ? 1 : 0);
      expect((await tool.execute("two", { command: "blocked", label: failure }, undefined, undefined, context)).isError).toBe(true);
      expect(launches, failure).toBe(1);
      expect(notifications.filter((message) => message.includes("run /ca-doctor")), failure).toHaveLength(1);
    }
  });
  test("durably terminal-audits a valid launch after authority drift without a completion notification", async () => {
    const fixture = await tempPlugin();
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
      sendUserMessage: () => undefined,
      getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
    } satisfies ParentPiPort;
    const lease = Object.freeze({});
    let sourceOwned = true;
    let release!: () => void;
    const settled = new Promise<void>((resolveSettled) => { release = resolveSettled; });
    let job: BackgroundJobSnapshot = Object.freeze({ id: 1, label: "drift", state: "active", status: "running", timeoutMs: null, outputBytes: 9 });
    const runtime: BackgroundJobRuntime = {
      launch: async () => job, cancel: async () => true, stop: async () => true,
      settled: async () => await settled, health: () => ({ healthy: true }), getJob: () => job,
      listJobs: () => [job], activeJobIds: () => [1], tail: () => "", dispose: async () => true,
    };
    const audits: Array<Record<string, unknown>> = [];
    const controller = createNativeBackgroundController(pi, {
      packageRoot: fixture.root, currentLifecycle: () => lease, toolOwnershipValid: () => sourceOwned,
      createRuntime: () => runtime, createAuditLifecycleId: () => "1".repeat(64), now: () => 100,
      resolveLaunch: async () => ({ shellPath: process.execPath, env: [] }),
      audit: async (_cwd, facts) => { audits.push({ ...facts }); return true; },
    });
    const notifications: string[] = [];
    const context: ExtensionContextPort = {
      cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
      isProjectTrusted: () => true, sessionManager: { getSessionId: () => "session" },
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    controller.register(context); expect(controller.activate(context)).toBe(true);
    const result = await controller.toolFactory(fixture.root).execute("launch", { command: "work", label: "drift" }, undefined, undefined, context);
    expect(result.isError).toBe(false);
    const launchAudit = audits[0]!;
    sourceOwned = false;
    job = Object.freeze({ ...job, state: "completed", status: "completed" });
    release();
    await new Promise<void>((resolveTick) => setImmediate(resolveTick));
    expect(audits.at(-1)).toMatchObject({
      event: "terminal", lifecycleId: launchAudit.lifecycleId, correlation: launchAudit.correlation,
      state: "completed", exitClass: "success", outputBytes: 9,
    });
    expect(notifications.some((message) => message.startsWith("Background job completed:"))).toBe(false);
  });
  test("bounds in-flight audit metadata and completion watchers to the active-job limit", async () => {
    const fixture = await tempPlugin();
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
      sendUserMessage: () => undefined,
      getCommands: () => [...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
    } satisfies ParentPiPort;
    let launches = 0;
    let resolveCalls = 0;
    let launchAudits = 0;
    let releaseResolve!: () => void;
    const resolveGate = new Promise<void>((resolveHeld) => { releaseResolve = resolveHeld; });
    let releaseAudit!: () => void;
    const auditGate = new Promise<void>((resolveHeld) => { releaseAudit = resolveHeld; });
    const jobs = new Map<number, BackgroundJobSnapshot>();
    const settlements = new Map<number, Promise<void>>();
    const settle = new Map<number, () => void>();
    const runtime: BackgroundJobRuntime = {
      launch: async (input) => {
        launches += 1;
        const job = Object.freeze({ id: launches, label: input.label, state: "active" as const, status: "running", timeoutMs: null, outputBytes: 0 });
        jobs.set(job.id, job);
        settlements.set(job.id, new Promise<void>((resolveSettled) => { settle.set(job.id, resolveSettled); }));
        return job;
      },
      cancel: async () => true, stop: async () => true,
      settled: async (id) => await settlements.get(Number(id)), health: () => ({ healthy: true }),
      getJob: (id) => jobs.get(Number(id)), listJobs: () => [...jobs.values()], activeJobIds: () => [...jobs.keys()],
      tail: () => "", dispose: async () => true,
    };
    const lease = Object.freeze({});
    const controller = createNativeBackgroundController(pi, {
      packageRoot: fixture.root, currentLifecycle: () => lease, toolOwnershipValid: () => true,
      createRuntime: () => runtime, createAuditLifecycleId: () => "2".repeat(64),
      resolveLaunch: async () => { resolveCalls += 1; await resolveGate; return { shellPath: process.execPath, env: [] }; },
      audit: async (_cwd, facts) => {
        if (facts.event === "launch") { launchAudits += 1; await auditGate; }
        return true;
      },
    });
    const context: ExtensionContextPort = {
      cwd: fixture.root, signal: undefined, mode: "tui", hasUI: true,
      isProjectTrusted: () => true, sessionManager: { getSessionId: () => "session" },
      ui: { setStatus: () => undefined, notify: () => undefined },
    };
    controller.register(context); expect(controller.activate(context)).toBe(true);
    const tool = controller.toolFactory(fixture.root);
    const first = Array.from({ length: 5 }, async (_, index) => await tool.execute(
      String(index + 1), { command: "work", label: `job-${index + 1}` }, undefined, undefined, context,
    ));
    await Promise.resolve();
    expect(resolveCalls).toBe(4);
    expect((await first[4]!).isError).toBe(true);
    releaseResolve();
    await new Promise<void>((resolveTick) => setImmediate(resolveTick));
    expect({ launches, launchAudits }).toEqual({ launches: 4, launchAudits: 4 });
    expect((await tool.execute("6", { command: "blocked", label: "job-6" }, undefined, undefined, context)).isError).toBe(true);
    releaseAudit();
    expect((await Promise.all(first.slice(0, 4))).every((result) => result.isError === false)).toBe(true);
    expect(launches).toBe(4);
    for (const [id, job] of jobs) {
      jobs.set(id, Object.freeze({ ...job, state: "completed", status: "completed" }));
      settle.get(id)?.();
    }
    await new Promise<void>((resolveTick) => setImmediate(resolveTick));
    expect((await tool.execute("7", { command: "recovered", label: "job-7" }, undefined, undefined, context)).isError).toBe(false);
    expect(launches).toBe(5);
  });
  test("owns bounded session jobs without persistence and rechecks lifecycle across awaited operations", async () => {
    const fixture = await tempPlugin();
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const extra: SlashCommand[] = [];
    const notifications: string[] = [];
    const sourceInfo = { path: resolve(fixture.root, "extensions", "codearbiter.js"), source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => { commands.set(name, options); },
      sendUserMessage: () => undefined,
      getCommands: () => [
        ...[...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
        ...extra,
      ],
    } satisfies ParentPiPort;
    let lease: object | undefined = Object.freeze({});
    let releaseSettled: () => void = () => undefined;
    let settled = Promise.resolve();
    const jobs = new Map<number, BackgroundJobSnapshot>();
    const stops: BackgroundJobStopReason[] = [];
    let cancelWaitsForSettlement = false;
    const runtime: BackgroundJobRuntime = {
      launch: async (input) => {
        settled = new Promise<void>((resolveSettled) => { releaseSettled = resolveSettled; });
        expect(JSON.stringify(input)).not.toContain("TOKEN");
        const job = Object.freeze({ id: 1, label: input.label, state: "active" as const, status: "running", timeoutMs: input.timeoutMs ?? null, outputBytes: 0 });
        jobs.set(1, job); return job;
      },
      cancel: async (id) => {
        if (cancelWaitsForSettlement) await settled;
        return jobs.has(Number(id));
      },
      stop: async (reason) => {
        stops.push(reason);
        const current = jobs.get(1);
        if (current !== undefined && (current.state === "active" || current.state === "queued")) {
          jobs.set(1, Object.freeze({ ...current, state: "cancelled", status: "cancelled" }));
          releaseSettled();
        }
        return true;
      },
      settled: async () => await settled,
      health: () => Object.freeze({ healthy: true }),
      getJob: (id) => jobs.get(Number(id)),
      listJobs: () => [...jobs.values()],
      activeJobIds: () => [...jobs.keys()],
      tail: (id) => jobs.has(Number(id)) ? "bounded\routput\r\nnext" : undefined,
      dispose: async () => true,
    };
    const audits: unknown[] = [];
    let blockTerminalAudit = false;
    let releaseTerminalAudit!: () => void;
    const terminalAuditGate = new Promise<void>((resolveAudit) => { releaseTerminalAudit = resolveAudit; });
    const lifecycleIds = ["c".repeat(64), "d".repeat(64)];
    const clock = [100, 150, 200, 250];
    const controller = createNativeBackgroundController(pi, {
      packageRoot: fixture.root,
      currentLifecycle: () => lease,
      toolOwnershipValid: () => true,
      createAuditLifecycleId: () => lifecycleIds.shift()!,
      now: () => clock.shift() ?? 250,
      createRuntime: () => runtime,
      resolveLaunch: async () => ({ shellPath: process.execPath, env: [["SAFE", "1"]] }),
      audit: async (_cwd, facts) => {
        audits.push(facts);
        if (blockTerminalAudit && facts.event === "terminal") await terminalAuditGate;
        return true;
      },
    });
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      mode: "tui",
      hasUI: true,
      isProjectTrusted: () => true,
      sessionManager: { getSessionId: () => "session-1", getEntries: () => [{ type: "custom", customType: "unrelated" }] },
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    expect(controller.register(context)).toBe(true);
    expect(controller.activate(context)).toBe(true);
    expect(assertNativeJobsCommandOwnership(pi, fixture.root)).toEqual([]);
    const tool = controller.toolFactory(fixture.root);
    const result = await tool.execute("opaque", { command: "echo secret", label: "fixture" }, undefined, undefined, context);
    expect(result).toMatchObject({ isError: false, details: { id: 1, label: "fixture", state: "active" } });
    expect(JSON.stringify(result)).not.toContain("echo secret");
    expect(audits).toEqual([expect.objectContaining({
      lifecycleId: "c".repeat(64), event: "launch", id: 1, state: "active", timeoutMs: null,
    })]);
    await commands.get("ca-jobs")!.handler("list", context);
    await commands.get("ca-jobs")!.handler("tail 1", context);
    expect(notifications.slice(-2)).toEqual([expect.stringContaining("#1 fixture"), "bounded\noutput\nnext"]);
    blockTerminalAudit = true;
    const stopping = controller.stop("session-switch");
    let stopCompleted = false;
    void stopping.then(() => { stopCompleted = true; });
    await Promise.resolve(); await Promise.resolve();
    expect(stopCompleted).toBe(false);
    releaseTerminalAudit();
    expect(await stopping).toBe(true);
    expect(stopCompleted).toBe(true);
    lease = Object.freeze({});
    expect(controller.activate(context)).toBe(true);
    await tool.execute("opaque-new", { command: "echo new", label: "new fixture" }, undefined, undefined, context);
    cancelWaitsForSettlement = true;
    const cancelling = commands.get("ca-jobs")!.handler("cancel 1", context);
    const current = jobs.get(1)!;
    jobs.set(1, Object.freeze({ ...current, state: "completed", status: "completed" }));
    releaseSettled();
    await cancelling;
    await new Promise<void>((resolveTick) => setImmediate(resolveTick));
    expect(notifications.filter((message) => message.startsWith("Background job completed:"))).toHaveLength(1);
    expect(notifications.find((message) => message.startsWith("Background job completed:"))).toContain("new fixture");
    const secondLaunch = audits.find((row) => (row as { lifecycleId?: string }).lifecycleId === "d".repeat(64)
      && (row as { event?: string }).event === "launch") as { correlation: string };
    const terminal = audits.find((row) => (row as { event?: string; lifecycleId?: string }).event === "terminal"
      && (row as { lifecycleId?: string }).lifecycleId === "d".repeat(64)) as {
      lifecycleId: string; correlation: string; durationMs: number; exitClass: string;
    };
    expect(terminal).toMatchObject({ lifecycleId: "d".repeat(64), correlation: secondLaunch.correlation, durationMs: 50, exitClass: "success" });
    expect(audits.find((row) => (row as { event?: string }).event === "cancel")).toMatchObject({ correlation: secondLaunch.correlation });
    expect(context.sessionManager!.getEntries!()).toEqual([{ type: "custom", customType: "unrelated" }]);

    lease = undefined;
    expect(await controller.stop("shutdown")).toBe(true);
    expect(stops).toEqual(["session-switch", "shutdown"]);
    expect(controller.activate(context)).toBe(false);
  });
  test("catalog is generated one-to-one from shipped ca skills", async () => {
    expect(existsSync(catalogPath)).toBe(true);
    const catalog = existsSync(catalogPath)
      ? JSON.parse(await readFile(catalogPath, "utf8")) as CommandCatalogEntry[]
      : [];
    expect(catalog.length).toBeGreaterThan(0);
    expect(catalog).toEqual([...catalog].sort((left, right) => left.name.localeCompare(right.name)));
    for (const entry of catalog) {
      expect(Object.keys(entry).sort()).toEqual(["description", "name", "skillPath"]);
      expect(entry.skillPath).toBe(`skills/ca-${entry.name}/SKILL.md`);
      expect(existsSync(resolve(pluginRoot, ...entry.skillPath.split("/")))).toBe(true);
    }
  });

  test("expands only the generated in-package skill through the public API and preserves args", async () => {
    const fixture = await tempPlugin();
    const registered = new Map<string, { handler: (args: string, ctx: ExtensionContextPort) => unknown }>();
    const userMessages: string[] = [];
    const delivery: Array<{ deliverAs?: "steer" | "followUp" } | undefined> = [];
    const notifications: string[] = [];
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      getCommands: () => [
        ...[...registered.keys()].map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")),
        })),
        {
          name: "skill:ca-feature",
          source: "skill" as const,
          sourceInfo: source(resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"))),
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, ctx: ExtensionContextPort) => unknown }) => {
        registered.set(name, options);
      },
      sendUserMessage: (content: string, options?: { deliverAs?: "steer" | "followUp" }) => {
        userMessages.push(content);
        delivery.push(options);
      },
    } satisfies ParentPiPort;
    registerAliases(pi, fixture.catalog, fixture.root);

    expect([...registered.keys()]).toEqual(["ca-feature"]);
    await registered.get("ca-feature")!.handler("  add caching  ", {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    });

    const expectedPath = realpathSync(resolve(fixture.root, "skills", "ca-feature", "SKILL.md"));
    expect(userMessages).toEqual([
      `<skill name="ca-feature" location="${expectedPath}">\n` +
      `References are relative to ${dirname(expectedPath)}.\n\n` +
      "# Feature body\n\nKeep this body.\n</skill>\n\n  add caching  ",
    ]);
    expect(userMessages[0]).not.toContain("/skill:ca-feature");
    expect(userMessages[0]).not.toContain("description: Build a feature.");
    expect(delivery).toEqual([{ deliverAs: "followUp" }]);
    expect(notifications).toEqual([]);
  });

  test("strips frontmatter only when both delimiter lines are exact", async () => {
    const fixture = await tempPlugin();
    let handler: ((args: string, context: ExtensionContextPort) => unknown) | undefined;
    const sent: string[] = [];
    const skill = resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"));
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      registerCommand: (_name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        handler = options.handler;
      },
      sendUserMessage: (content: string) => sent.push(content),
      getCommands: () => [
        { name: "ca-feature", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "skill:ca-feature", source: "skill" as const, sourceInfo: source(skill) },
      ],
    } satisfies ParentPiPort;
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: () => undefined },
    };
    registerAliases(pi, fixture.catalog, fixture.root);

    await writeFile(skill, "---not-frontmatter\nname: ca-feature\n---\nBODY\n", "utf8");
    await handler!("", context);
    expect(sent.at(-1)).toContain("---not-frontmatter\nname: ca-feature\n---\nBODY");
    await writeFile(skill, "---\nname: ca-feature\n---not-a-close\nBODY\n", "utf8");
    await handler!("", context);
    expect(sent.at(-1)).toContain("---\nname: ca-feature\n---not-a-close\nBODY");
  });

  test("fails visibly instead of reading a missing or out-of-package skill", async () => {
    const fixture = await tempPlugin();
    const sent: string[] = [];
    const notifications: string[] = [];
    const handlers: Array<(args: string, ctx: ExtensionContextPort) => unknown> = [];
    const registeredNames: string[] = [];
    let activeEntry: CommandCatalogEntry | undefined;
    const pi = {
      on: () => undefined,
      getCommands: () => activeEntry === undefined ? [] : [
        ...registeredNames.map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: {
            path: resolve(fixture.root, "extensions", "codearbiter.js"),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        })),
        {
          name: `skill:ca-${activeEntry.name}`,
          source: "skill" as const,
          sourceInfo: {
            path: resolve(fixture.root, ...activeEntry.skillPath.split("/")),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, ctx: ExtensionContextPort) => unknown }) => {
        registeredNames.push(name);
        handlers.push(options.handler);
      },
      sendUserMessage: (content: string) => sent.push(content),
    } satisfies ParentPiPort;
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };

    activeEntry = { name: "missing", description: fixture.catalog[0].description, skillPath: "skills/ca-missing/SKILL.md" };
    registerAliases(pi, [activeEntry], fixture.root);
    await handlers.shift()!("args", context);
    expect(sent).toEqual([]);
    expect(notifications.at(-1)).toContain("/ca-doctor");

    activeEntry = fixture.catalog[0];
    await writeFile(
      resolve(fixture.root, ...activeEntry.skillPath.split("/")),
      "---\nname: ca-feature\ndescription: x\n---\nbody\n</skill>\nattacker tail\n",
      "utf8",
    );
    registerAliases(pi, [activeEntry], fixture.root);
    await handlers.shift()!("args", context);
    expect(sent).toEqual([]);
    expect(notifications.at(-1)).toContain("/ca-doctor");

    expect(() => registerAliases(pi, [{
      ...fixture.catalog[0],
      skillPath: "../outside/SKILL.md",
    }], fixture.root)).toThrow("/ca-doctor");
  });

  test("rejects noncanonical catalog names, absolute paths, invalid UTF-8, directories, and symlink escapes", async () => {
    const fixture = await tempPlugin();
    const outside = await mkdtemp(resolve(tmpdir(), "ca-pi-command-outside-"));
    roots.push(outside);
    await writeFile(resolve(outside, "SKILL.md"), "---\nname: ca-feature\ndescription: x\n---\noutside\n", "utf8");
    const link = resolve(fixture.root, "skills", "ca-linked");
    const internalTarget = resolve(fixture.root, "skills", "internal-target");
    const internalLink = resolve(fixture.root, "skills", "ca-internal");
    await mkdir(internalTarget, { recursive: true });
    await writeFile(
      resolve(internalTarget, "SKILL.md"),
      "---\nname: ca-internal\ndescription: x\n---\ninside package\n",
      "utf8",
    );
    let linked = true;
    let internalLinked = true;
    try {
      await symlink(outside, link, process.platform === "win32" ? "junction" : "dir");
    } catch {
      linked = false;
    }
    try {
      await symlink(internalTarget, internalLink, process.platform === "win32" ? "junction" : "dir");
    } catch {
      internalLinked = false;
    }
    const invalidPath = resolve(fixture.root, "skills", "ca-invalid", "SKILL.md");
    await mkdir(dirname(invalidPath), { recursive: true });
    await writeFile(invalidPath, Buffer.from([0xff, 0xfe, 0xfd]));
    const directoryPath = resolve(fixture.root, "skills", "ca-directory", "SKILL.md");
    await mkdir(directoryPath, { recursive: true });
    const handlers: Array<(args: string, context: ExtensionContextPort) => unknown> = [];
    const registeredNames: string[] = [];
    const notifications: string[] = [];
    let activeEntry: CommandCatalogEntry | undefined;
    const pi = {
      on: () => undefined,
      getCommands: () => activeEntry === undefined ? [] : [
        ...registeredNames.map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: {
            path: resolve(fixture.root, "extensions", "codearbiter.js"),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        })),
        {
          name: `skill:ca-${activeEntry.name}`,
          source: "skill" as const,
          sourceInfo: {
            path: resolve(fixture.root, ...activeEntry.skillPath.split("/")),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        registeredNames.push(name);
        handlers.push(options.handler);
      },
      sendUserMessage: () => undefined,
    } satisfies ParentPiPort;
    const syntacticallyBad: CommandCatalogEntry[] = [
      { name: "bad\nname", description: "x", skillPath: "skills/ca-bad\nname/SKILL.md" },
      { name: 'bad"name', description: "x", skillPath: 'skills/ca-bad"name/SKILL.md' },
      { name: "bad<name", description: "x", skillPath: "skills/ca-bad<name/SKILL.md" },
      { name: "feature", description: "x", skillPath: resolve(fixture.root, "skills", "ca-feature", "SKILL.md") },
    ];
    for (const entry of syntacticallyBad) {
      expect(() => registerAliases(pi, [entry], fixture.root), JSON.stringify(entry)).toThrow("/ca-doctor");
    }
    const fileBad: CommandCatalogEntry[] = [
      { name: "invalid", description: "x", skillPath: "skills/ca-invalid/SKILL.md" },
      { name: "directory", description: "x", skillPath: "skills/ca-directory/SKILL.md" },
    ];
    if (linked) fileBad.push({ name: "linked", description: "x", skillPath: "skills/ca-linked/SKILL.md" });
    if (internalLinked) fileBad.push({ name: "internal", description: "x", skillPath: "skills/ca-internal/SKILL.md" });
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    for (const entry of fileBad) {
      activeEntry = entry;
      registerAliases(pi, [entry], fixture.root);
      const notificationCount = notifications.length;
      await handlers.shift()!("args", context);
      expect(notifications, JSON.stringify(entry)).toHaveLength(notificationCount + 1);
      expect(notifications.at(-1), JSON.stringify(entry)).toContain("/ca-doctor");
    }
  });

  test("accepts exactly one canonical package alias and matching native fallback", async () => {
    const fixture = await tempPlugin();
    const extension = resolve(fixture.root, "extensions", "codearbiter.js");
    const skill = resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"));
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const commands: SlashCommand[] = [
      { name: "ca-feature", source: "extension", sourceInfo: source(extension) },
      { name: "skill:ca-feature", source: "skill", sourceInfo: source(skill) },
    ];
    expect(assertCommandOwnership({ getCommands: () => commands } as ParentPiPort, fixture.root, fixture.catalog)).toEqual([]);
    const mismatchedSource = structuredClone(commands);
    mismatchedSource[1].sourceInfo.source = "different-package-source";
    expect(assertCommandOwnership(
      { getCommands: () => mismatchedSource } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    ).map((collision) => collision.reason)).toContain("foreign-owner");
  });

  test("accepts a harmless ancestor alias but rejects a symlinked package root", async () => {
    const fixture = await tempPlugin();
    const ancestorAlias = resolve(dirname(fixture.root), `ca-pi-ancestor-${basename(fixture.root)}`);
    const rootAlias = resolve(dirname(fixture.root), `ca-pi-root-${basename(fixture.root)}`);
    try {
      await symlink(dirname(fixture.root), ancestorAlias, process.platform === "win32" ? "junction" : "dir");
      await symlink(fixture.root, rootAlias, process.platform === "win32" ? "junction" : "dir");
    } catch {
      await unlink(ancestorAlias).catch(() => undefined);
      await unlink(rootAlias).catch(() => undefined);
      return;
    }
    links.push(ancestorAlias, rootAlias);
    const packageThroughAncestor = resolve(ancestorAlias, basename(fixture.root));
    const commandsFor = (baseDir: string): SlashCommand[] => [{
      name: "ca-feature",
      source: "extension",
      sourceInfo: {
        path: resolve(baseDir, "extensions", "codearbiter.js"),
        source: "fixture",
        scope: "user",
        origin: "package",
        baseDir,
      },
    }, {
      name: "skill:ca-feature",
      source: "skill",
      sourceInfo: {
        path: resolve(baseDir, ...fixture.catalog[0].skillPath.split("/")),
        source: "fixture",
        scope: "user",
        origin: "package",
        baseDir,
      },
    }];

    expect(assertCommandOwnership(
      { getCommands: () => commandsFor(packageThroughAncestor) } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    )).toEqual([]);
    expect(assertCommandOwnership(
      { getCommands: () => commandsFor(rootAlias) } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    ).map((collision) => collision.reason)).toContain("foreign-owner");
  });

  test("rechecks complete ownership inside an alias and sends nothing after a late collision", async () => {
    const fixture = await tempPlugin();
    let handler: ((args: string, context: ExtensionContextPort) => unknown) | undefined;
    const sent: string[] = [];
    const notifications: string[] = [];
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      registerCommand: (_name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        handler = options.handler;
      },
      sendUserMessage: (content: string) => sent.push(content),
      getCommands: () => [
        { name: "ca-feature:1", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "ca-feature:2", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "skill:ca-feature", source: "skill" as const, sourceInfo: source(resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"))) },
      ],
    } satisfies ParentPiPort;
    registerAliases(pi, fixture.catalog, fixture.root);

    await handler!("args", {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    });

    expect(sent).toEqual([]);
    expect(notifications).toEqual([expect.stringContaining("/ca-doctor")]);
  });

  test("reports suffixed, duplicate, foreign, and missing-fallback ownership", async () => {
    const fixture = await tempPlugin();
    const inside = resolve(fixture.root, "extensions", "codearbiter.js");
    const outside = resolve(dirname(fixture.root), "project-extension.js");
    const source = (path: string, scope: "user" | "project" = "user") => ({
      path,
      source: "fixture",
      scope,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const commands: SlashCommand[] = [
      { name: "ca-feature:1", source: "extension", sourceInfo: source(inside) },
      { name: "ca-feature:2", source: "extension", sourceInfo: source(outside, "project") },
      { name: "ca-feature", source: "skill", sourceInfo: source(outside, "project") },
    ];
    const pi = { getCommands: () => commands } as ParentPiPort;

    const collisions = assertCommandOwnership(pi, fixture.root, fixture.catalog);

    expect(new Set(collisions.map((collision) => collision.reason))).toEqual(new Set([
      "missing-alias",
      "suffixed-alias",
      "foreign-owner",
      "missing-fallback",
    ]));
  });
});

describe("descriptor-backed native /ca-plan command", () => {
  const ledger = [
    "| Task | Status |",
    "|---|---|",
    "| T01 | PENDING |",
    "| T02 | IN-PROGRESS |",
    "",
  ].join("\n");
  const planResponse = {
    version: 1 as const,
    outcome: "notice" as const,
    resultPatch: {
      planFile: {
        status: "unchanged",
        exists: true,
        hash: "54a087e369aff67a57ebc899de6840042058e68fe542dea48f939b172730376f",
        contentBase64: Buffer.from(ledger, "utf8").toString("base64"),
      },
    },
  };

  function planFixture() {
    const commands = new Map<string, { handler: (args: string, context: ExtensionContextPort) => unknown }>();
    const notifications: string[] = [];
    const entries: Array<{ customType: string; data: unknown }> = [];
    const sessionEntries: unknown[] = [];
    const bridgeCalls: unknown[] = [];
    const lease = Object.freeze({ lease: 1 });
    let current: object | undefined = lease;
    let appendFails = false;
    let currentLedger = ledger;
    let bridgeHook: (() => void) | undefined;
    const lateCommands: SlashCommand[] = [];
    const sourceInfo = {
      path: resolve(pluginRoot, "extensions", "codearbiter.js"),
      source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: pluginRoot,
    };
    const pi = {
      on: () => undefined,
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        commands.set(name, options);
      },
      sendUserMessage: () => undefined,
      getCommands: () => [
        ...[...commands.keys()].map((name) => ({ name, source: "extension" as const, sourceInfo })),
        ...lateCommands,
      ],
    } satisfies ParentPiPort;
    const context: ExtensionContextPort = {
      cwd: "C:/repo",
      signal: undefined,
      mode: "tui",
      hasUI: true,
      isProjectTrusted: () => true,
      sessionManager: { getSessionId: () => "session-1", getEntries: () => sessionEntries },
      ui: {
        setStatus: () => undefined,
        notify: (message) => notifications.push(message),
        confirm: async () => true,
      },
    };
    const controller = createNativePlanController(pi, {
      descriptor: { "ca-plan": "planning-write" },
      packageRoot: pluginRoot,
      bridge: {
        call: async (request) => {
          bridgeCalls.push(structuredClone(request));
          bridgeHook?.();
          return {
            version: 1, outcome: "notice", resultPatch: { planFile: {
              status: "unchanged", exists: true,
              hash: createHash("sha256").update(currentLedger).digest("hex"),
              contentBase64: Buffer.from(currentLedger).toString("base64"),
            } },
          } as const;
        },
      },
      currentLifecycle: () => current,
      appendEntry(customType, data) {
        if (appendFails) throw new Error("append failed");
        entries.push({ customType, data: structuredClone(data) });
      },
      confirmationTimeoutMs: 20,
    });
    return {
      commands, notifications, entries, sessionEntries, bridgeCalls, context, controller,
      setCurrent(value: object | undefined) { current = value; },
      setAppendFails(value: boolean) { appendFails = value; },
      setLedger(value: string) { currentLedger = value; },
      setBridgeHook(value: (() => void) | undefined) { bridgeHook = value; },
      addCollision() {
        lateCommands.push({
          name: "ca-plan:foreign", source: "extension",
          sourceInfo: { ...sourceInfo, path: resolve(pluginRoot, "extensions", "foreign.js") },
        });
      },
      clearCollisions() { lateCommands.length = 0; },
    };
  }

  test("registers only from the exact planning-write descriptor in parent interactive mode", () => {
    const fixture = planFixture();
    expect(fixture.controller.register({ ...fixture.context, mode: "rpc" })).toBe(false);
    expect(fixture.commands.size).toBe(0);
    expect(fixture.controller.register(fixture.context)).toBe(true);
    expect([...fixture.commands.keys()]).toEqual(["ca-plan"]);
    expect(() => createNativePlanController({} as ParentPiPort, {
      descriptor: { "ca-plan": "release" }, bridge: { call: async () => planResponse },
      packageRoot: pluginRoot, currentLifecycle: () => undefined, appendEntry: () => undefined,
    })).toThrow("/ca-doctor");
    expect(() => createNativePlanController({} as ParentPiPort, {
      descriptor: Object.defineProperty({}, "ca-plan", { get: () => "planning-write" }),
      packageRoot: pluginRoot, bridge: { call: async () => planResponse }, currentLifecycle: () => undefined,
      appendEntry: () => undefined,
    })).toThrow("/ca-doctor");
  });

  test("owns exactly one native extension command and rejects generated or foreign fallbacks", async () => {
    const fixture = await tempPlugin();
    const extension = resolve(fixture.root, "extensions", "codearbiter.js");
    const source = (path: string) => ({
      path, source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: fixture.root,
    });
    const exact: SlashCommand[] = [{ name: "ca-plan", source: "extension", sourceInfo: source(extension) }];
    expect(assertNativePlanCommandOwnership(
      { getCommands: () => exact } as ParentPiPort, fixture.root,
    )).toEqual([]);
    const collisions = assertNativePlanCommandOwnership({ getCommands: () => [
      ...exact,
      { name: "skill:ca-plan", source: "skill", sourceInfo: source(resolve(fixture.root, fixture.catalog[0]!.skillPath)) },
      { name: "ca-plan:2", source: "extension", sourceInfo: source(extension) },
    ] } as ParentPiPort, fixture.root);
    expect(new Set(collisions.map((collision) => collision.reason))).toEqual(new Set(["foreign-owner", "suffixed-alias"]));
  });

  test("enters, reports, approves after confirmation, and cancels without exposing the slug", async () => {
    const fixture = planFixture();
    fixture.controller.register(fixture.context);
    const handler = fixture.commands.get("ca-plan")!.handler;
    await handler("enter sprint-alpha", fixture.context);
    expect(fixture.controller.mode()).toBe("plan");
    expect(fixture.entries).toHaveLength(1);
    expect(fixture.entries[0]?.customType).toBe("codearbiter.plan-mode.v1");
    expect(JSON.stringify(fixture.bridgeCalls)).toContain('"slug":"sprint-alpha"');
    expect(fixture.notifications.at(-1)).not.toContain("sprint-alpha");
    await handler("status", fixture.context);
    expect(fixture.notifications.at(-1)).toBe("Plan mode active. Tasks: 1 pending, 1 in progress, 0 accepted.");
    await handler("approve", fixture.context);
    expect(fixture.controller.mode()).toBe("execute");
    expect(fixture.entries.at(-1)?.data).toMatchObject({ mode: "execute", activePlan: { disposition: "approved" } });

    await handler("enter sprint-alpha", fixture.context);
    await handler("cancel", fixture.context);
    expect(fixture.controller.mode()).toBe("execute");
    expect(fixture.entries.at(-1)?.data).toMatchObject({ mode: "execute", activePlan: { disposition: "draft" } });
    expect(fixture.notifications.at(-1)).toBe("Plan draft preserved. Execute mode active.");
  });

  test("keeps plan mode on denial, confirmation failure, timeout, abort, and owner drift", async () => {
    for (const confirmation of [
      async () => false,
      async () => { throw new Error("ui failed"); },
      async () => await new Promise<boolean>(() => undefined),
    ]) {
      const fixture = planFixture();
      fixture.context.ui.confirm = confirmation;
      fixture.controller.register(fixture.context);
      const handler = fixture.commands.get("ca-plan")!.handler;
      await handler("enter sprint-alpha", fixture.context);
      await handler("approve", fixture.context);
      expect(fixture.controller.mode()).toBe("plan");
      expect(fixture.entries).toHaveLength(1);
    }

    const aborted = planFixture();
    const abort = new AbortController(); abort.abort();
    aborted.context.signal = abort.signal;
    aborted.controller.register(aborted.context);
    await aborted.commands.get("ca-plan")!.handler("enter sprint-alpha", aborted.context);
    expect(aborted.controller.mode()).toBe("execute");

    const drift = planFixture();
    drift.controller.register(drift.context);
    const handler = drift.commands.get("ca-plan")!.handler;
    await handler("enter sprint-alpha", drift.context);
    drift.context.ui.confirm = async () => { drift.setCurrent(Object.freeze({ lease: 2 })); return true; };
    await handler("approve", drift.context);
    expect(drift.controller.mode()).toBe("execute");
    expect(drift.entries).toHaveLength(1);
  });

  test.each([
    ["same task IDs with prose drift", `${ledger}\nChanged after confirmation.\n`],
    ["task status drift", ledger.replace("T01 | PENDING", "T01 | ACCEPTED")],
  ])("rechecks the exact approved disk snapshot after confirmation: %s", async (_name, changedLedger) => {
    const fixture = planFixture();
    fixture.controller.register(fixture.context);
    const handler = fixture.commands.get("ca-plan")!.handler;
    await handler("enter sprint-alpha", fixture.context);
    fixture.context.ui.confirm = async () => { fixture.setLedger(changedLedger); return true; };
    await handler("approve", fixture.context);
    expect(fixture.controller.mode()).toBe("plan");
    expect(fixture.entries).toHaveLength(1);
    expect(fixture.notifications.at(-1)).toBe("Pi plan approval became stale; plan mode remains active.");
  });

  test("refuses startup and late native ownership collisions without side effects", async () => {
    for (const action of ["enter sprint-alpha", "status", "approve", "cancel"] as const) {
      const fixture = planFixture();
      fixture.controller.register(fixture.context);
      if (action !== "enter sprint-alpha") {
        await fixture.commands.get("ca-plan")!.handler("enter sprint-alpha", fixture.context);
      }
      const calls = fixture.bridgeCalls.length;
      const entries = fixture.entries.length;
      const state = fixture.controller.status();
      fixture.addCollision();
      await fixture.commands.get("ca-plan")!.handler(action, fixture.context);
      expect(fixture.bridgeCalls).toHaveLength(calls);
      expect(fixture.entries).toHaveLength(entries);
      expect(fixture.controller.status()).toBe(state);
      expect(fixture.notifications.at(-1)).toBe("Pi plan command ownership changed; operation blocked.");
    }
  });

  test("refuses ownership changes during bridge and confirmation boundaries", async () => {
    const duringBridge = planFixture();
    duringBridge.controller.register(duringBridge.context);
    duringBridge.setBridgeHook(() => { duringBridge.setBridgeHook(undefined); duringBridge.addCollision(); });
    await duringBridge.commands.get("ca-plan")!.handler("enter sprint-alpha", duringBridge.context);
    expect(duringBridge.controller.mode()).toBe("execute");
    expect(duringBridge.entries).toHaveLength(0);

    const duringConfirm = planFixture();
    duringConfirm.controller.register(duringConfirm.context);
    const handler = duringConfirm.commands.get("ca-plan")!.handler;
    await handler("enter sprint-alpha", duringConfirm.context);
    duringConfirm.context.ui.confirm = async () => { duringConfirm.addCollision(); return true; };
    const calls = duringConfirm.bridgeCalls.length;
    await handler("approve", duringConfirm.context);
    expect(duringConfirm.controller.mode()).toBe("plan");
    expect(duringConfirm.entries).toHaveLength(1);
    expect(duringConfirm.bridgeCalls.length).toBe(calls + 1);

    const deniedWithCollision = planFixture();
    deniedWithCollision.controller.register(deniedWithCollision.context);
    const deniedHandler = deniedWithCollision.commands.get("ca-plan")!.handler;
    await deniedHandler("enter sprint-alpha", deniedWithCollision.context);
    deniedWithCollision.context.ui.confirm = async () => { deniedWithCollision.addCollision(); return false; };
    await deniedHandler("approve", deniedWithCollision.context);
    expect(deniedWithCollision.controller.mode()).toBe("plan");
    expect(deniedWithCollision.entries).toHaveLength(1);
    expect(deniedWithCollision.notifications.at(-1)).toBe("Pi plan command ownership changed; operation blocked.");
  });

  test("keeps the draft in plan mode when approve or cancel persistence fails", async () => {
    for (const action of ["approve", "cancel"] as const) {
      const fixture = planFixture();
      fixture.controller.register(fixture.context);
      const handler = fixture.commands.get("ca-plan")!.handler;
      await handler("enter sprint-alpha", fixture.context);
      fixture.setAppendFails(true);
      await handler(action, fixture.context);
      expect(fixture.controller.mode()).toBe("plan");
      expect(fixture.entries).toHaveLength(1);
      expect(fixture.notifications.at(-1)).toContain("/ca-doctor");
    }
  });

  test("restores only the latest valid session entry against disk and never rolls back", async () => {
    const source = planFixture();
    source.controller.register(source.context);
    await source.commands.get("ca-plan")!.handler("enter sprint-alpha", source.context);
    const valid = source.entries[0]!.data;

    const restored = planFixture();
    restored.sessionEntries.push({
      type: "custom", id: "1", parentId: null, timestamp: new Date().toISOString(),
      customType: "codearbiter.plan-mode.v1", data: valid,
    });
    restored.controller.register(restored.context);
    await restored.controller.restore(restored.context);
    expect(restored.controller.mode()).toBe("plan");

    restored.sessionEntries.push({
      type: "custom", id: "2", parentId: "1", timestamp: new Date().toISOString(),
      customType: "codearbiter.plan-mode.v1", data: { ...valid as object, mode: "broken" },
    });
    await restored.controller.restore(restored.context);
    expect(restored.controller.mode()).toBe("execute");
    expect(restored.controller.status()).toBeUndefined();
  });

  test("uses fixed syntax and rejects malformed, stale, cross-session, and append-failed invocations", async () => {
    const fixture = planFixture();
    fixture.controller.register(fixture.context);
    const handler = fixture.commands.get("ca-plan")!.handler;
    for (const args of ["", "enter", "enter ../escape", "status extra", "approve extra", "unknown", "x".repeat(600)]) {
      await handler(args, fixture.context);
      expect(fixture.controller.mode()).toBe("execute");
    }
    await handler("enter sprint-alpha", fixture.context);
    const entryCount = fixture.entries.length;
    await handler("enter sprint-alpha", { ...fixture.context, sessionManager: { ...fixture.context.sessionManager, getSessionId: () => "other" } });
    expect(fixture.controller.mode()).toBe("plan");
    expect(fixture.entries).toHaveLength(entryCount);
    fixture.setCurrent(undefined);
    await handler("enter sprint-alpha", fixture.context);
    expect(fixture.entries).toHaveLength(entryCount);
  });
});
