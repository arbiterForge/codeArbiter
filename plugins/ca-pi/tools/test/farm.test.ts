import { EventEmitter } from "node:events";
import { mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { PassThrough } from "node:stream";

import { afterEach, describe, expect, test, vi } from "vitest";

import {
  createFarmPreviewTool,
  runFarmPreview,
} from "../src/farm.ts";
import type { FarmPreviewInput, FarmSpawn } from "../src/farm.ts";
import { installPiFarmPreview } from "../src/extension.ts";
import type { ExtensionContextPort, ToolDefinitionPort } from "../src/contracts.ts";

const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

class FakeFarmChild extends EventEmitter {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  readonly kill = vi.fn(() => true);
}

async function fixture(): Promise<FarmPreviewInput> {
  const checkout = await mkdtemp(resolve(tmpdir(), "ca-pi-farm-"));
  temporaryRoots.push(checkout);
  const packageRoot = resolve(checkout, "plugins", "ca-pi");
  const backendRoot = resolve(checkout, "plugins", "ca", "tools");
  const projectRoot = resolve(checkout, "project");
  const planPath = resolve(projectRoot, ".codearbiter", "plans", "slice.plan.json");
  await mkdir(packageRoot, { recursive: true });
  await mkdir(backendRoot, { recursive: true });
  await mkdir(resolve(planPath, ".."), { recursive: true });
  await writeFile(resolve(backendRoot, "farm.ts"), "// authoritative source\n", "utf8");
  await writeFile(resolve(backendRoot, "farm.js"), "// built backend\n", "utf8");
  await writeFile(planPath, '{"meta":{"name":"slice"},"tasks":[]}\n', "utf8");
  await writeFile(resolve(projectRoot, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
  const older = new Date(Date.now() - 10_000);
  const newer = new Date(Date.now());
  await utimes(resolve(backendRoot, "farm.ts"), older, older);
  await utimes(resolve(backendRoot, "farm.js"), newer, newer);
  return {
    packageRoot,
    projectRoot,
    planPath,
    nodePath: process.execPath,
    environment: {
      FARM_API_KEY: "dummy-farm-key",
      FARM_MODEL: "test-model",
      Path: process.env.PATH ?? "C:/runtime",
      OPENAI_API_KEY: "ordinary-provider-key-must-not-cross",
      CLAUDE_CODE_OAUTH_TOKEN: "ordinary-oauth-must-not-cross",
      CODEARBITER_SUBAGENT: "1",
      HOME: "C:/Users/operator-private-home",
      USERPROFILE: "C:/Users/operator-private-profile",
    },
    authorization: { lease: Object.freeze({}), isCurrent: () => true },
  };
}

function successfulSpawn(capture: Array<{ command: string; args: readonly string[]; options: object }>): FarmSpawn {
  return ((command: string, args: readonly string[], options: Parameters<FarmSpawn>[2]) => {
    capture.push({ command, args, options });
    const child = new FakeFarmChild();
    setTimeout(() => {
      child.stdout.end();
      child.stderr.end();
      child.emit("close", 0, null);
    }, 0);
    return child;
  }) as unknown as FarmSpawn;
}

const verifiedCleanup = () => ({
  ready: async () => true,
  terminate: async (reason: "timeout" | "cancelled" | "protocol_error" | "protocol_overflow" | "startup_failure" | "parent_shutdown") => ({
    reason,
    state: "already_exited" as const,
    escalated: false,
    verified: true,
  }),
});

describe("Pi farm preview routing", () => {
  test("routes preview farm to the one absolute shared built backend with a farm-only environment", async () => {
    const input = await fixture();
    const calls: Array<{ command: string; args: readonly string[]; options: object }> = [];

    const result = await runFarmPreview(input, new AbortController().signal, {
      spawn: successfulSpawn(calls),
      createCleanup: verifiedCleanup,
    });

    const backend = resolve(input.packageRoot, "..", "ca", "tools", "farm.js");
    expect(result).toEqual({ label: "preview", terminal: "completed", backend, exitCode: 0 });
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      command: process.execPath,
      args: [backend, input.planPath],
      options: { cwd: input.projectRoot, shell: false, windowsHide: true },
    });
    const env = (calls[0]!.options as { env: NodeJS.ProcessEnv }).env;
    expect(env.FARM_API_KEY).toBe("dummy-farm-key");
    expect(env.FARM_MODEL).toBe("test-model");
    expect(env.Path).toBe(input.environment.Path);
    expect(env.OPENAI_API_KEY).toBeUndefined();
    expect(env.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined();
    expect(env.CODEARBITER_SUBAGENT).toBeUndefined();
    expect(env.HOME).toBeUndefined();
    expect(env.USERPROFILE).toBeUndefined();
  });

  test("awaits verified whole-tree cleanup after a root-first normal exit", async () => {
    const input = await fixture();
    const calls: Array<{ command: string; args: readonly string[]; options: object }> = [];
    let cleaned = false;
    const terminate = vi.fn(async () => {
      await new Promise<void>((resolveWait) => setTimeout(resolveWait, 5));
      cleaned = true;
      return { reason: "parent_shutdown" as const, state: "terminated" as const, escalated: true, verified: true };
    });

    const result = await runFarmPreview(input, new AbortController().signal, {
      spawn: successfulSpawn(calls),
      createCleanup: () => ({ ready: async () => true, terminate }),
    });

    expect(terminate).toHaveBeenCalledWith("parent_shutdown");
    expect(cleaned).toBe(true);
    expect(result).toMatchObject({ terminal: "completed", exitCode: 0 });
  });

  test("cancellation after spawn terminates the whole farm tree and never reports completion", async () => {
    const input = await fixture();
    const controller = new AbortController();
    const child = new FakeFarmChild();
    let markSpawned!: () => void;
    const spawned = new Promise<void>((resolveSpawned) => { markSpawned = resolveSpawned; });
    const terminate = vi.fn(async () => ({
      reason: "cancelled" as const,
      state: "terminated" as const,
      escalated: true,
      verified: true,
    }));
    const pending = runFarmPreview(input, controller.signal, {
      spawn: (() => { markSpawned(); return child; }) as unknown as FarmSpawn,
      createCleanup: () => ({ ready: async () => true, terminate }),
    });
    await spawned;
    await new Promise<void>((resolveTurn) => setImmediate(resolveTurn));
    controller.abort();

    await expect(pending).resolves.toMatchObject({ terminal: "cancelled" });
    expect(terminate).toHaveBeenCalledWith("cancelled");
  });

  test("cancellation during prelaunch filesystem checks prevents spawn", async () => {
    const input = await fixture();
    const controller = new AbortController();
    const spawn = vi.fn();
    const lease = Object.freeze({});
    input.authorization = {
      lease,
      isCurrent: () => { controller.abort(); return true; },
    };

    const result = await runFarmPreview(input, controller.signal, { spawn: spawn as FarmSpawn });

    expect(result).toMatchObject({ terminal: "cancelled" });
    expect(spawn).not.toHaveBeenCalled();
  });

  test("bounded-output overflow terminates the tree and degrades without retaining output", async () => {
    const input = await fixture();
    const child = new FakeFarmChild();
    let markSpawned!: () => void;
    const spawned = new Promise<void>((resolveSpawned) => { markSpawned = resolveSpawned; });
    const terminate = vi.fn(async () => ({
      reason: "protocol_overflow" as const,
      state: "terminated" as const,
      escalated: true,
      verified: true,
    }));
    const pending = runFarmPreview(input, new AbortController().signal, {
      spawn: (() => { markSpawned(); return child; }) as unknown as FarmSpawn,
      createCleanup: () => ({ ready: async () => true, terminate }),
    });
    await spawned;
    await new Promise<void>((resolveTurn) => setImmediate(resolveTurn));
    child.stderr.write("FARM_API_KEY=must-not-be-retained".padEnd(65_537, "x"));
    const result = await pending;

    expect(result).toMatchObject({ terminal: "degraded", message: expect.stringContaining("output exceeded") });
    expect(JSON.stringify(result)).not.toContain("must-not-be-retained");
    expect(terminate).toHaveBeenCalledWith("protocol_overflow");
  });

  test("nonzero and unverifiable cleanup terminals cannot promote", async () => {
    for (const [verified, terminal] of [[true, "failed"], [false, "degraded"]] as const) {
      const input = await fixture();
      const child = new FakeFarmChild();
      let markSpawned!: () => void;
      const spawned = new Promise<void>((resolveSpawned) => { markSpawned = resolveSpawned; });
      const pending = runFarmPreview(input, new AbortController().signal, {
        spawn: (() => { markSpawned(); return child; }) as unknown as FarmSpawn,
        createCleanup: () => ({
          ready: async () => true,
          terminate: async () => ({
            reason: "parent_shutdown" as const,
            state: "already_exited" as const,
            escalated: false,
            verified,
          }),
        }),
      });
      await spawned;
      await new Promise<void>((resolveTurn) => setImmediate(resolveTurn));
      child.stdout.end();
      child.stderr.end();
      child.emit("close", 23, null);

      await expect(pending).resolves.toMatchObject({ terminal, exitCode: 23 });
    }
  });

  test("passes canary as an argv element and never exposes paths or keys as tool parameters", async () => {
    const input = await fixture();
    const run = vi.fn(async () => ({
      label: "preview" as const,
      terminal: "completed" as const,
      backend: resolve(input.packageRoot, "..", "ca", "tools", "farm.js"),
      exitCode: 0,
    }));
    const tool = createFarmPreviewTool({
      packageRoot: input.packageRoot,
      nodePath: input.nodePath,
      environment: input.environment,
      authorize: async () => true,
      run,
    });
    const result = await tool.execute("farm-1", {
      plan: ".codearbiter/plans/slice.plan.json",
      canary: true,
    }, new AbortController().signal, undefined, {
      cwd: input.projectRoot,
      isProjectTrusted: () => true,
    });

    expect(tool.name).toBe("codearbiter_farm_preview");
    expect(JSON.stringify(tool.parameters)).not.toMatch(/api.?key|packageRoot|nodePath|environment/iu);
    expect(run).toHaveBeenCalledWith(expect.objectContaining({
      projectRoot: input.projectRoot,
      planPath: input.planPath,
      canary: true,
    }), expect.any(AbortSignal));
    expect(result.details).toMatchObject({ label: "preview", terminal: "completed" });
  });

  test("production registration requires enabled activation, current trust, and lifecycle readiness", async () => {
    const input = await fixture();
    const dormant = await mkdtemp(resolve(tmpdir(), "ca-pi-farm-dormant-"));
    temporaryRoots.push(dormant);
    let ready = true;
    let tool: ToolDefinitionPort | undefined;
    const run = vi.fn(async () => ({
      label: "preview" as const,
      terminal: "completed" as const,
      backend: resolve(input.packageRoot, "..", "ca", "tools", "farm.js"),
      exitCode: 0,
    }));
    installPiFarmPreview({ registerTool: (definition) => { tool = definition; } }, {
      packageRoot: input.packageRoot,
      nodePath: input.nodePath,
      environment: input.environment,
      isLifecycleReady: () => ready,
      run,
    });
    const context = (cwd: string, trusted: boolean): ExtensionContextPort => ({
      cwd,
      signal: new AbortController().signal,
      ui: { setStatus: () => undefined, notify: () => undefined },
      isProjectTrusted: () => trusted,
    });

    expect(tool?.name).toBe("codearbiter_farm_preview");
    const params = { plan: ".codearbiter/plans/slice.plan.json" };
    await tool!.execute("untrusted", params, undefined, undefined, context(input.projectRoot, false));
    await tool!.execute("dormant", params, undefined, undefined, context(dormant, true));
    ready = false;
    await tool!.execute("not-ready", params, undefined, undefined, context(input.projectRoot, true));
    expect(run).not.toHaveBeenCalled();
    ready = true;
    await tool!.execute("authorized", params, undefined, undefined, context(input.projectRoot, true));
    expect(run).toHaveBeenCalledTimes(1);
  });

  test.each([
    ["missing", async (input: FarmPreviewInput) => await rm(resolve(input.packageRoot, "..", "ca", "tools", "farm.js"))],
    ["stale", async (input: FarmPreviewInput) => {
      const source = resolve(input.packageRoot, "..", "ca", "tools", "farm.ts");
      const newer = new Date(Date.now() + 10_000);
      await utimes(source, newer, newer);
    }],
  ])("reports a %s shared backend as explicit preview degradation without spawning", async (_name, mutate) => {
    const input = await fixture();
    await mutate(input);
    const spawn = vi.fn();

    const result = await runFarmPreview(input, new AbortController().signal, { spawn: spawn as FarmSpawn });

    expect(result).toMatchObject({ label: "preview", terminal: "degraded" });
    expect(result.message).toMatch(/shared farm backend .*; rebuild plugins\/ca\/tools\/farm\.js/u);
    expect(spawn).not.toHaveBeenCalled();
  });

  test("rejects a plan that escapes the active project before spawning", async () => {
    const input = await fixture();
    const outsidePlan = resolve(input.projectRoot, "..", "outside.plan.json");
    await writeFile(outsidePlan, "{}\n", "utf8");
    const spawn = vi.fn();

    const result = await runFarmPreview(
      { ...input, planPath: outsidePlan },
      new AbortController().signal,
      { spawn: spawn as FarmSpawn },
    );

    expect(result).toMatchObject({ label: "preview", terminal: "degraded" });
    expect(result.message).toContain("plan must be a regular file inside the active project");
    expect(spawn).not.toHaveBeenCalled();
  });
});
