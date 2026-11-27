import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { build } from "esbuild";
import { pathToFileURL } from "node:url";
import { afterEach, describe, expect, test } from "vitest";
import { openParentDelegation } from "../src/parent-delegation.ts";
import { createDelegationClient } from "../src/delegation-client.ts";
import { createDelegatedExecutor, credentialBlindHostEnvironment } from "../src/delegated-executor.ts";
import { openDelegationJournal } from "../src/delegation-journal.ts";
import { EnforcementInstaller, compileBuiltinPermissionPolicy } from "../src/tool-guard.ts";
import type { ToolDefinitionPort, ToolCategory, ToolExecutionContextPort } from "../src/contracts.ts";
import type { PiRole } from "../src/roles.ts";
import { findPiPackageRoot, findPiCliEntry } from "./live-pi-host.ts";
import { loadRoleCatalog } from "../src/roles.ts";
import { resolvePiBackgroundShell } from "../src/extension.ts";
import { compatibilityDirection } from "../src/compatibility.ts";

const roots: string[] = [];
afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });
describe("parent-authorized delegated file effects", () => {
  test("real packaged child RPC loop performs parent-owned effects (local provider and permission callback substituted)", async () => {
    const hostRoot = await findPiPackageRoot();
    const root = await mkdtemp(join(tmpdir(), "ca-live-child-delegation-")); roots.push(root);
    const worktree = join(root, "project"); const agent = join(root, "operator-agent");
    await mkdir(join(worktree, ".git"), { recursive: true }); await mkdir(agent);
    const operations = [
      { name: "write", arguments: { path: "result.txt", content: "before" } },
      { name: "edit", arguments: { path: "result.txt", edits: [{ oldText: "before", newText: "after" }] } },
      { name: "bash", arguments: { command: "printf child-command-proof > command.txt", timeout: 15 } },
    ];
    let requests = 0;
    const server = createServer((request, response) => {
      request.resume(); request.on("end", () => {
        const operation = operations[requests++];
        const delta = operation === undefined ? { content: JSON.stringify({ state: "accepted", summary: "Fixture effects completed" }) }
          : { role: "assistant", tool_calls: [{ index: 0, id: `fixture-call-${requests}`, type: "function",
            function: { name: operation.name, arguments: JSON.stringify(operation.arguments) } }] };
        const chunk = (value: unknown, finish: string | null) => ({ id: `fixture-response-${requests}`, object: "chat.completion.chunk",
          created: 1, model: "gpt-fixture", choices: [{ index: 0, delta: value, finish_reason: finish }] });
        response.writeHead(200, { "content-type": "text/event-stream" });
        response.end(`data: ${JSON.stringify(chunk(delta, null))}\n\ndata: ${JSON.stringify(chunk({}, operation === undefined ? "stop" : "tool_calls"))}\n\ndata: [DONE]\n\n`);
      });
    });
    const packageRoot = resolve(import.meta.dirname, "../..");
    const driver = join(packageRoot, "extensions", `.live-delegation-${randomUUID()}.mjs`);
    try {
    await new Promise<void>((ready, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", ready); });
    const address = server.address(); if (address === null || typeof address === "string") throw new Error("fixture unavailable");
    await writeFile(join(agent, "models.json"), JSON.stringify({ providers: { openai: {
      baseUrl: `http://127.0.0.1:${address.port}/v1`, api: "openai-completions", apiKey: "$OPENAI_API_KEY",
      models: [{ id: "gpt-fixture", name: "fixture", reasoning: false, input: ["text"], contextWindow: 128000, maxTokens: 4096,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    } } }));
    const role = (await loadRoleCatalog(packageRoot)).get("backend-author")!;
    // Bundle the instrumented parent at its actual package boundary. Importing
    // tools/src directly is intentionally refused by the production resolver:
    // its nearest manifest belongs to the private build-tools package.
    const compiled = await build({ stdin: { contents: `export { runPiChild, validateChildLaunch } from './runner.ts';
      export { openParentDelegation } from './parent-delegation.ts';
      export { createDelegatedExecutor } from './delegated-executor.ts';
      export { openDelegationJournal } from './delegation-journal.ts';`, resolveDir: join(packageRoot, "tools/src"), loader: "ts" },
      bundle: true, platform: "node", format: "esm", target: "node22", packages: "external", write: false });
    await writeFile(driver, compiled.outputFiles[0]!.contents);
      const launch = { nodePath: process.execPath, piCliPath: await findPiCliEntry(hostRoot), provider: "openai", model: "gpt-fixture",
        cwd: worktree, childExtensionPath: join(packageRoot, "extensions/codearbiter-child.js"), charterPath: join(packageRoot, role.charterPath),
        skillPaths: role.skillPaths.map((p) => join(packageRoot, p)), tools: role.tools };
      // The instrumented parent uses the real canonical CLI anchor as its first
      // argument, like existing package identity fixtures. It is not a live TUI
      // parent; no parent-host qualification is claimed from this callback.
      const script = `
        import { readFileSync } from 'node:fs';
        const config = JSON.parse(readFileSync(0, 'utf8'));
        const { runPiChild, validateChildLaunch, openParentDelegation, createDelegatedExecutor, openDelegationJournal } = await import(config.driver);
        const host = await import(config.host);
        const executor = createDelegatedExecutor({ journal: await openDelegationJournal(config.launch.cwd),
          write: host.createWriteToolDefinition, edit: host.createEditToolDefinition,
          shell: async () => ({ shellPath: config.shellPath }), environment: process.env });
        let approvals = 0;
        await validateChildLaunch(config.launch);
        const result = await runPiChild({ ...config.launch, task: 'Run the deterministic qualification fixture.', timeoutMs: 60000,
          parentEnv: process.env, openDelegation: async (runId, signal) => await openParentDelegation({ runId, role: config.role,
            parentToolCallId: 'live-fixture-call', worktree: config.launch.cwd, isCurrent: () => true, enabled: async () => true,
            signal, executor, gate: async (request, _signal, effect) => { approvals++; await effect(request.params); return { admitted: true }; } }),
        }, new AbortController().signal);
        process.stdout.write(JSON.stringify({result,approvals}));
      `;
      const input = { launch, role, host: pathToFileURL(join(hostRoot, "dist/index.js")).href,
        shellPath: await resolvePiBackgroundShell(undefined, process.env, process.platform),
        driver: pathToFileURL(driver).href };
      const output = await new Promise<string>((done, reject) => {
        const control = execFile(process.execPath, ["--input-type=module", "--eval", script, launch.piCliPath],
          { encoding: "utf8", timeout: 70000, maxBuffer: 1048576, env: { ...credentialBlindHostEnvironment(process.env),
            PI_CODING_AGENT_DIR: agent, OPENAI_API_KEY: "dummy-live-child-parent-only-value" } },
          (error, stdout, stderr) => error === null ? done(stdout) : reject(new Error(`${error.message}\n${stderr}`)));
        control.stdin!.end(JSON.stringify(input));
      });
      const { result, approvals } = JSON.parse(output);
      expect(result, JSON.stringify(result)).toMatchObject({ terminal: "completed", delegation: { completed: 3, failed: 0, unknown: 0 } });
      expect(approvals).toBe(3); expect(requests).toBe(4);
      expect(await readFile(join(worktree, "result.txt"), "utf8")).toBe("after");
      expect(await readFile(join(worktree, "command.txt"), "utf8")).toBe("child-command-proof");
    } finally {
      try { await rm(driver, { force: true }); }
      finally { server.closeAllConnections(); await new Promise<void>((done) => server.close(() => done())); }
    }
  }, 75000);
  test("real admitted Pi file factories and managed shell produce exact effects (permission callback substituted)", async () => {
    const hostRoot = await findPiPackageRoot();
    const host = await import(pathToFileURL(join(hostRoot, "dist", "index.js")).href);
    expect(compatibilityDirection({ piVersion: host.VERSION, nodeVersion: process.versions.node, pythonMajor: 3 })).toBeNull();
    const root = await mkdtemp(join(tmpdir(), "ca-native-delegated-effects-")); roots.push(root); await mkdir(join(root, ".git"));
    const journal = (await openDelegationJournal(root))!;
    const shellPath = await resolvePiBackgroundShell(undefined, process.env, process.platform);
    expect(shellPath).toBeDefined();
    const executor = createDelegatedExecutor({ journal, write: host.createWriteToolDefinition, edit: host.createEditToolDefinition,
      shell: async () => ({ shellPath: shellPath! }), environment: process.env });
    const channel = await openParentDelegation({ runId: "d".repeat(32), parentToolCallId: "native-effect-test", worktree: root,
      role: { name: "backend-author", classification: "author", charterPath: "agents/backend-author.md", skillPaths: [], tools: ["write", "edit", "bash"] },
      isCurrent: () => true, enabled: async () => true, signal: new AbortController().signal, executor,
      gate: async (request, _signal, effect) => { await effect(request.params as Record<string, unknown>); return { admitted: true }; } });
    try {
      const client = createDelegationClient(channel);
      expect((await client.execute("write", { path: "result.txt", content: "before" })).execution).toBe("completed");
      expect((await client.execute("edit", { path: "result.txt", edits: [{ oldText: "before", newText: "after" }] })).execution).toBe("completed");
      expect(await readFile(join(root, "result.txt"), "utf8")).toBe("after");
      const command = await client.execute("bash", { command: "printf command-proof > command.txt", timeout: 15 });
      expect(command.execution).toBe("completed"); expect(command.containment).toBe("verified-stopped");
      expect(await readFile(join(root, "command.txt"), "utf8")).toBe("command-proof");
    } finally { await channel.close(); }
  }, 30000);
  test("child proxy crosses real channel and parent final gate before durable file effect", async () => {
    const root = await mkdtemp(join(tmpdir(), "ca-parent-delegation-")); roots.push(root); await mkdir(join(root, ".git"));
    const tools = new Map<string, ToolDefinitionPort>();
    const source = "C:/package/extensions/codearbiter.js";
    const pi = { registerTool: (tool: ToolDefinitionPort) => tools.set(tool.name, tool), on: () => undefined,
      getActiveTools: () => [...tools.keys()], getAllTools: () => [...tools.keys()].map((name) => ({ name, sourceInfo: { path: source } })) };
    const descriptor: Readonly<Record<string, ToolCategory>> = { write: "WRITE", edit: "EDIT", bash: "EXEC", read: "READ" };
    const native = (name: string) => (_cwd: string) => ({ name, execute: async (_id: string, params: Record<string, unknown>) => {
      await writeFile(params.path as string, params.content as string); return { content: [{ type: "text", text: "written" }] };
    } });
    const factories = { write: native("write"), edit: native("edit"), bash: native("bash"), read: native("read") };
    const journal = (await openDelegationJournal(root))!;
    const executor = createDelegatedExecutor({ journal, write: factories.write, edit: factories.edit, shell: async () => undefined, environment: {} });
    let trusted = true; let enabled = true; let prompts = 0; let bridgeCalls = 0; let refuseBridge = false;
    const context: ToolExecutionContextPort = { cwd: root, mode: "tui", hasUI: true, isProjectTrusted: () => trusted,
      ui: { confirm: async () => { prompts++; return true; } } };
    const installer = new EnforcementInstaller(); installer.ensureBootstrap(pi, descriptor); installer.beginActivation();
    installer.ensureBuiltins(pi, { call: async () => { bridgeCalls++; return { version: 1, outcome: refuseBridge ? "block" : "allow" }; } },
      { cwd: root, descriptor, factories, wrapperSourcePath: source, projectTrust: () => trusted,
        permissionPolicy: compileBuiltinPermissionPolicy(descriptor, {}), permissionAudit: async () => true }); installer.markReady();
    const role: PiRole = { name: "backend-author", classification: "author", charterPath: "agents/backend-author.md", skillPaths: [], tools: ["read", "write"] };
    const channel = await openParentDelegation({ runId: "a".repeat(32), role, parentToolCallId: "actual-parent-call", worktree: root,
      isCurrent: () => trusted, enabled: async () => enabled, signal: new AbortController().signal, executor,
      gate: async (r, signal, effect) => await installer.executeDelegated(r.tool, r.requestId, r.params as Record<string, unknown>, signal, context, effect) });
    try {
      const child = createDelegationClient(channel);
      const outcome = await child.execute("write", { path: "approved.txt", content: "exact approved bytes" });
      expect(outcome.execution).toBe("completed"); expect(outcome.observation).toBe("exact");
      expect(await readFile(join(root, "approved.txt"), "utf8")).toBe("exact approved bytes");
      expect(prompts).toBe(1); expect(bridgeCalls).toBe(1); expect(await journal.unresolved()).toEqual([]);
      refuseBridge = true;
      expect((await child.execute("write", { path: "refused.txt", content: "never" })).admission).toBe("denied");
      expect(prompts).toBe(1); await expect(readFile(join(root, "refused.txt"))).rejects.toThrow();
      enabled = false;
      expect((await child.execute("write", { path: "disabled.txt", content: "never" })).admission).toBe("revoked");
      trusted = false;
      expect((await child.execute("write", { path: "untrusted.txt", content: "never" })).admission).toBe("revoked");
    } finally { await channel.close(); }
  });
});
