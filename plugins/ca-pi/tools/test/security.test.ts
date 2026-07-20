import { link, lstat, mkdir, mkdtemp, open, readFile, realpath, rm, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, test } from "vitest";
import { buildChildEnv } from "../src/child-env.ts";
import { createFarmPreviewTool } from "../src/farm.ts";
import { installParent, installPiFarmPreview } from "../src/extension.ts";
import { appendPermissionAudit, appendPermissionAuditWithIo, guardUnknownTools } from "../src/tool-guard.ts";
import type { BridgePort, ExtensionContextPort, ParentPiPort, ToolCategory, ToolDefinitionPort } from "../src/contracts.ts";

type ToolCallHandler = (event: Record<string, unknown>) => unknown;

class SecurityPi {
  readonly handlers: ToolCallHandler[] = [];
  readonly sources = new Map<string, string>();
  readonly active = new Set<string>();

  on(event: string, handler: ToolCallHandler): void {
    if (event === "tool_call") this.handlers.push(handler);
  }

  getActiveTools(): string[] {
    return [...this.active];
  }

  getAllTools(): Array<{ name: string; sourceInfo: { path: string } }> {
    return [...this.sources].map(([name, path]) => ({ name, sourceInfo: { path } }));
  }

  async emit(toolName: string, input: Record<string, unknown> = {}): Promise<unknown> {
    for (const handler of this.handlers) {
      const result = await handler({ toolName, input });
      if ((result as { block?: boolean } | undefined)?.block === true) return result;
    }
    return undefined;
  }
}

async function piDescriptor(): Promise<Readonly<Record<string, ToolCategory>>> {
  const document = JSON.parse(
    await readFile(resolve(import.meta.dirname, "../../../../core/hosts.json"), "utf8"),
  ) as { hosts: Array<{ name: string; tool_classes: Record<string, ToolCategory> }> };
  const descriptor = document.hosts.find((host) => host.name === "pi")?.tool_classes;
  if (descriptor === undefined) throw new Error("generated Pi tool descriptor is missing");
  return descriptor;
}

describe("ADR-0014 adversarial promotion contract", () => {
  test("permission audit is append-only and rejects attacker-controlled row fields", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-permission-audit-"));
    try {
      const state = resolve(root, ".codearbiter");
      const audit = resolve(state, "gate-events.log");
      await mkdir(state);
      await writeFile(audit, "sentinel\n", "utf8");
      await expect(appendPermissionAudit(root, {
        timestamp: "2026-07-19T00:00:00.000Z",
        correlation: "a".repeat(64),
        toolClass: "EXEC",
        actionClasses: ["shell-mutation", "push"],
        decision: "approved",
      })).resolves.toBe(true);
      const afterValid = await readFile(audit, "utf8");
      expect(afterValid.startsWith("sentinel\n")).toBe(true);
      expect(afterValid).toContain("ACTION_CLASSES: shell-mutation,push");
      expect(afterValid).not.toContain(root);

      await expect(appendPermissionAudit(root, {
        timestamp: "2026-07-19T00:00:00.000Z\nOPENAI_API_KEY=synthetic-secret",
        correlation: "not-a-correlation",
        toolClass: "EXEC\nFORGED" as never,
        actionClasses: ["shell-mutation\nFORGED"] as never,
        decision: "approved\nFORGED" as never,
      })).resolves.toBe(false);
      expect(await readFile(audit, "utf8")).toBe(afterValid);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("permission audit rejects hardlinks and nonregular sinks", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-permission-sinks-"));
    try {
      const state = resolve(root, ".codearbiter");
      const target = resolve(state, "gate-events.log");
      const other = resolve(root, "other.log");
      await mkdir(state);
      await writeFile(other, "other\n", "utf8");
      await link(other, target);
      const row = {
        timestamp: "2026-07-19T00:00:00.000Z", correlation: "b".repeat(64), toolClass: "WRITE" as const,
        actionClasses: ["source-write"] as const, decision: "approved" as const,
      };
      await expect(appendPermissionAudit(root, row)).resolves.toBe(false);
      expect(await readFile(other, "utf8")).toBe("other\n");
      await rm(target);
      await mkdir(target);
      await expect(appendPermissionAudit(root, row)).resolves.toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("permission audit rejects validation-open path swaps and opened-handle mismatches", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-permission-race-"));
    try {
      const state = resolve(root, ".codearbiter");
      const target = resolve(state, "gate-events.log");
      const replacement = resolve(state, "replacement.log");
      await mkdir(state);
      await writeFile(target, "target\n", "utf8");
      await writeFile(replacement, "replacement\n", "utf8");
      const targetStats = await lstat(target);
      const replacementStats = await lstat(replacement);
      const row = {
        timestamp: "2026-07-19T00:00:00.000Z", correlation: "c".repeat(64), toolClass: "EXEC" as const,
        actionClasses: ["shell-mutation"] as const, decision: "approved" as const,
      };
      let targetLstats = 0;
      const swappedIo = {
        realpath,
        lstat: async (path: string) => {
          if (path === target) return ++targetLstats === 1 ? targetStats : replacementStats;
          return await lstat(path);
        },
        open: async () => await open(replacement, "a"),
      };
      await expect(appendPermissionAuditWithIo(root, row, swappedIo)).resolves.toBe(false);
      expect(await readFile(replacement, "utf8")).toBe("replacement\n");

      const mismatchedIo = {
        realpath,
        lstat,
        open: async () => await open(replacement, "a"),
      };
      await expect(appendPermissionAuditWithIo(root, row, mismatchedIo)).resolves.toBe(false);
      expect(await readFile(replacement, "utf8")).toBe("replacement\n");

      let afterAppendLstats = 0;
      const afterAppendSwapIo = {
        realpath,
        lstat: async (path: string) => {
          if (path === target) return ++afterAppendLstats < 4 ? targetStats : replacementStats;
          return await lstat(path);
        },
        open: async () => await open(target, "a"),
      };
      await expect(appendPermissionAuditWithIo(root, row, afterAppendSwapIo)).resolves.toBe(false);
      expect(await readFile(replacement, "utf8")).toBe("replacement\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("permission audit creates exclusively and rejects a hardlink raced into an absent target", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-permission-create-"));
    try {
      const state = resolve(root, ".codearbiter");
      const target = resolve(state, "gate-events.log");
      const other = resolve(root, "other.log");
      await mkdir(state);
      const row = {
        timestamp: "2026-07-19T00:00:00.000Z", correlation: "d".repeat(64), toolClass: "EDIT" as const,
        actionClasses: ["source-edit"] as const, decision: "approved" as const,
      };
      await expect(appendPermissionAudit(root, row)).resolves.toBe(true);
      const created = await lstat(target);
      expect(created.isFile()).toBe(true);
      expect(created.nlink).toBe(1);

      await rm(target);
      await writeFile(other, "other\n", "utf8");
      let raced = false;
      const raceIo = {
        realpath,
        lstat,
        open: async (path: string, flags: number, mode?: number) => {
          if (path === target && !raced) {
            raced = true;
            await link(other, target);
          }
          return await open(path, flags, mode);
        },
      };
      await expect(appendPermissionAuditWithIo(root, row, raceIo)).resolves.toBe(false);
      expect(await readFile(other, "utf8")).toBe("other\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test.each(["project_write_anywhere", "__proto__", "constructor", "prototype"])(
    "blocks undeclared potentially mutating tool %s without echoing attacker input",
    async (toolName) => {
      const pi = new SecurityPi();
      pi.active.add(toolName);
      pi.sources.set(toolName, "C:/foreign/adversarial-extension.js");
      guardUnknownTools(
        pi as never,
        await piDescriptor(),
        "C:/package/extensions/codearbiter.js",
      );

      const result = await pi.emit(toolName, {
        path: "../../README.md\r\nOPENAI_API_KEY=fixture-value",
      });

      expect(result).toMatchObject({ block: true });
      expect(JSON.stringify(result)).not.toContain("fixture-value");
      expect(JSON.stringify(result)).not.toContain("README.md");
    },
  );

  test("admits only the selected provider environment and excludes farm/auth bleed", () => {
    const child = buildChildEnv({
      platform: "win32",
      provider: "openai",
      parent: {
        SystemRoot: "C:/Windows",
        USERPROFILE: "C:/isolated-home",
        APPDATA: "C:/isolated-home/appdata",
        OPENAI_API_KEY: "selected-provider-fixture",
        ANTHROPIC_API_KEY: "foreign-provider-fixture",
        FARM_API_KEY: "farm-fixture",
        CLAUDE_CODE_OAUTH_TOKEN: "claude-fixture",
        CODEARBITER_PRIVATE_STATE: "private-fixture",
      },
    });

    expect(child).toMatchObject({
      CODEARBITER_SUBAGENT: "1",
      OPENAI_API_KEY: "selected-provider-fixture",
      PI_OFFLINE: "1",
      PI_TELEMETRY: "0",
    });
    for (const forbidden of [
      "ANTHROPIC_API_KEY",
      "FARM_API_KEY",
      "CLAUDE_CODE_OAUTH_TOKEN",
      "CODEARBITER_PRIVATE_STATE",
    ]) expect(child[forbidden]).toBeUndefined();
  });

  test("an obsolete session_start cannot mint readiness after shutdown and reactivation", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-security-generation-"));
    try {
      const first = resolve(root, "first");
      const second = resolve(root, "second");
      for (const project of [first, second]) {
        await mkdir(resolve(project, ".codearbiter"), { recursive: true });
        await writeFile(resolve(project, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
      }
      const handlers = new Map<string, Array<(event: Record<string, unknown>, context: ExtensionContextPort) => unknown>>();
      const host: ParentPiPort = {
        on: (name, handler) => handlers.set(name, [...(handlers.get(name) ?? []), handler]),
        registerCommand: () => undefined,
        sendUserMessage: () => undefined,
        getCommands: () => [],
      };
      let releaseFirst!: () => void;
      const firstPrepared = new Promise<void>((resolvePrepared) => { releaseFirst = resolvePrepared; });
      const bridgeCwds: string[] = [];
      const readyLeases: unknown[] = [];
      let currentReady: (() => unknown) | undefined;
      installParent(host, {
        bridge: {
          call: async (request) => {
            bridgeCwds.push(request.cwd);
            return { version: 1, outcome: "allow", context: `host: pi ${request.cwd}` };
          },
        },
        catalog: [],
        packageRoot: root,
        loadPersona: async () => "persona",
        prepareBridge: async (cwd) => { if (cwd === first) await firstPrepared; },
        installEnforcement: async () => undefined,
        installFarmPreview: ((provider: () => unknown) => { currentReady = provider; }) as never,
        enforcementReadiness: {
          beginActivation: () => undefined,
          beginBootstrap: () => undefined,
          markReady: () => { readyLeases.push(currentReady?.()); },
          deactivate: () => undefined,
        },
      });
      const context = (cwd: string): ExtensionContextPort => ({
        cwd,
        signal: undefined,
        ui: { setStatus: () => undefined, notify: () => undefined },
        isProjectTrusted: () => true,
      });
      const emit = async (name: string, cwd: string) => {
        for (const handler of handlers.get(name) ?? []) await handler({ type: name }, context(cwd));
      };

      const stale = emit("session_start", first);
      await new Promise<void>((resolveTurn) => setImmediate(resolveTurn));
      await emit("session_shutdown", first);
      await emit("session_start", second);
      const currentLease = currentReady?.();
      releaseFirst();
      await stale;

      expect(currentLease).toEqual(expect.any(Object));
      expect(currentReady?.()).toBe(currentLease);
      expect(bridgeCwds).toEqual([second]);
      expect(readyLeases).toEqual([currentLease]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("farm authorization rejects a lease replaced while enabled-state proof is pending", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-security-farm-auth-"));
    try {
      await mkdir(resolve(root, ".codearbiter"), { recursive: true });
      await writeFile(resolve(root, ".codearbiter", "CONTEXT.md"), "---\narbiter: enabled\n---\n", "utf8");
      const initialLease = Object.freeze({});
      const replacementLease = Object.freeze({});
      let reads = 0;
      let tool: ToolDefinitionPort | undefined;
      const run = async () => ({ label: "preview" as const, terminal: "completed" as const, backend: "fixture", exitCode: 0 });
      const runCalls: unknown[] = [];
      installPiFarmPreview({ registerTool: (definition) => { tool = definition; } }, {
        packageRoot: resolve(root, "package"),
        nodePath: process.execPath,
        environment: { FARM_API_KEY: "farm-fixture" },
        currentLifecycle: () => (++reads === 1 ? initialLease : replacementLease),
        isLifecycleReady: () => true,
        run: async (...args: Parameters<typeof run>) => { runCalls.push(args); return await run(...args); },
      } as never);
      const result = await tool!.execute("stale-farm", { plan: ".codearbiter/plans/slice.plan.json" }, undefined, undefined, {
        cwd: root,
        isProjectTrusted: () => true,
      });

      expect(result).toMatchObject({ details: { terminal: "degraded" } });
      expect(runCalls).toEqual([]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("farm runner rechecks the identical lifecycle lease after filesystem awaits and before spawn", async () => {
    const run = await import("../src/farm.ts");
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-security-farm-spawn-"));
    try {
      const packageRoot = resolve(root, "plugins", "ca-pi");
      const backendRoot = resolve(root, "plugins", "ca", "tools");
      const projectRoot = resolve(root, "project");
      const planPath = resolve(projectRoot, "slice.plan.json");
      await mkdir(packageRoot, { recursive: true });
      await mkdir(backendRoot, { recursive: true });
      await mkdir(projectRoot, { recursive: true });
      await writeFile(resolve(backendRoot, "farm.ts"), "// source\n", "utf8");
      await writeFile(resolve(backendRoot, "farm.js"), "// build\n", "utf8");
      await writeFile(planPath, "{}\n", "utf8");
      const old = new Date(Date.now() - 10_000);
      const fresh = new Date();
      await utimes(resolve(backendRoot, "farm.ts"), old, old);
      await utimes(resolve(backendRoot, "farm.js"), fresh, fresh);
      const current = Object.freeze({});
      const spawnCalls: unknown[] = [];
      const result = await run.runFarmPreview({
        packageRoot,
        projectRoot,
        planPath,
        nodePath: process.execPath,
        environment: { FARM_API_KEY: "farm-fixture" },
        authorization: { lease: current, isCurrent: () => false },
      } as never, new AbortController().signal, {
        spawn: ((...args: unknown[]) => { spawnCalls.push(args); throw new Error("must not spawn"); }) as never,
      });

      expect(result).toMatchObject({ terminal: "degraded", message: expect.stringContaining("lifecycle") });
      expect(spawnCalls).toEqual([]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("pins CodeQL and scans both TypeScript sources and shipped JavaScript", async () => {
    const workflow = await readFile(resolve(import.meta.dirname, "../../../../.github/workflows/codeql.yml"), "utf8");
    expect(workflow).toContain("github/codeql-action/init@7188fc363630916deb702c7fdcf4e481b751f97a");
    expect(workflow).toContain("github/codeql-action/analyze@7188fc363630916deb702c7fdcf4e481b751f97a");
    expect(workflow).toContain("languages: javascript-typescript");
    expect(workflow).toContain("plugins/ca-pi/tools/src");
    expect(workflow).toContain("plugins/ca-pi/extensions");
    expect(workflow).toContain("plugins/ca-pi/tools/node_modules");
    expect(workflow).toContain("test_pi_security.py --sarif");
  });

  test("security evidence output is result-code-only even with secret-bearing ambient values", () => {
    const python = process.platform === "win32" ? "python" : "python3";
    const script = resolve(import.meta.dirname, "../../../../.github/scripts/test_pi_security.py");
    const completed = spawnSync(python, [script, "--contract-only"], {
      cwd: resolve(import.meta.dirname, "../../../.."),
      encoding: "utf8",
      env: {
        ...process.env,
        FARM_API_KEY: "must-not-appear-farm-fixture",
        OPENAI_API_KEY: "must-not-appear-provider-fixture",
      },
    });
    expect(completed.status, completed.stderr).toBe(0);
    const report = JSON.parse(completed.stdout) as Record<string, unknown>;
    expect(report).toMatchObject({ schema: "codearbiter-pi-security-v1", status: "pass" });
    expect(JSON.stringify(report)).not.toContain("fixture");
    expect(JSON.stringify(report)).not.toContain("env");
    expect(JSON.stringify(report)).not.toContain("prompt");
    expect(JSON.stringify(report)).not.toContain("provider");
    expect(JSON.stringify(report)).not.toContain("stderr");
  });

  test("SARIF high gate reports only a fixed code and count", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-security-sarif-"));
    try {
      const sarif = resolve(root, "javascript-typescript.sarif");
      await writeFile(sarif, JSON.stringify({
        version: "2.1.0",
        runs: [{
          tool: { driver: { rules: [{ id: "js/fixture", properties: { "security-severity": "9.1" } }] } },
          results: [{
            ruleId: "js/fixture",
            message: { text: "OPENAI_API_KEY=must-not-appear-provider-fixture" },
          }],
        }],
      }), "utf8");
      const python = process.platform === "win32" ? "python" : "python3";
      const script = resolve(import.meta.dirname, "../../../../.github/scripts/test_pi_security.py");
      const completed = spawnSync(python, [script, "--sarif", sarif], {
        cwd: resolve(import.meta.dirname, "../../../.."),
        encoding: "utf8",
      });
      const report = JSON.parse(completed.stdout) as { status: string; results: Array<Record<string, unknown>> };

      expect(completed.status).toBe(1);
      expect(report).toMatchObject({
        status: "fail",
        results: expect.arrayContaining([{ code: "PI-SEC-CODEQL-HIGH", status: "fail", count: 1 }]),
      });
      expect(JSON.stringify(report)).not.toContain("fixture");
      expect(JSON.stringify(report)).not.toContain("OPENAI_API_KEY");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
