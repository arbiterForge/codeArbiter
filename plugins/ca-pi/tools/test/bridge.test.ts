import { access, chmod, copyFile, mkdtemp, mkdir, readFile, readdir, realpath, rm, writeFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import { EventEmitter } from "node:events";
import { tmpdir } from "node:os";
import { delimiter, isAbsolute, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, test } from "vitest";

import {
  BridgeClient,
  __setBridgeSpawnForTests,
  callPlanFileBridge,
  readFooterStatusSnapshot,
  resolveGitExecutable,
  resolvePythonCommand,
  updateFooterUsageSnapshot,
} from "../src/bridge.ts";
import type { BridgeSpawnImpl } from "../src/bridge.ts";
import type {
  BridgePort,
  BridgeRequest,
  BridgeResponse,
  BuiltinToolFactories,
  ExtensionContextPort,
  PiFooterUsageUpdateResult,
  ToolDefinitionPort,
  ToolGuardPiPort,
} from "../src/contracts.ts";
import { applyToolResultNotice } from "../src/notices.ts";
import { wrapBuiltins } from "../src/tool-guard.ts";

function wirePlanFile(planFile: Record<string, unknown>): Record<string, unknown> {
  const output = { ...planFile };
  if (output.status === "committed" && output.observed === undefined) output.observed = true;
  if (Object.hasOwn(output, "content")) {
    const content = output.content;
    delete output.content;
    output.contentBase64 = content === null ? null : Buffer.from(String(content), "utf8").toString("base64");
  }
  return output;
}

describe("plan-file bridge protocol", () => {
  test("emits the fixed path-free request and accepts bounded exact results", async () => {
    const calls: BridgeRequest[] = [];
    const bridge: BridgePort = { call: async (request) => {
      calls.push(request);
      return {
        version: 1, outcome: "notice", resultPatch: { planFile: {
          status: "unchanged", exists: true, hash: createHash("sha256").update("plan").digest("hex"),
          contentBase64: Buffer.from("plan", "utf8").toString("base64"),
        } },
      };
    } };
    await expect(callPlanFileBridge(bridge, "C:/repo", {
      slug: "demo", kind: "plan", action: "read",
    })).resolves.toMatchObject({ status: "unchanged", content: "plan" });
    expect(calls).toEqual([{
      version: 1, event: "plan_file", cwd: "C:/repo",
      input: { slug: "demo", kind: "plan", action: "read" },
    }]);
  });

  test("rejects malformed, oversized, and hash-incoherent response shapes", async () => {
    const values: unknown[] = [
      { status: "conflict", extra: true },
      { status: "error", code: "raw path C:/secret" },
      { status: "unchanged", exists: false, hash: null, content: "not-empty" },
      { status: "committed", exists: true, hash: "x", content: "ok", directoryDurable: true },
      { status: "unchanged", exists: true, hash: "0".repeat(64), content: "x".repeat(92_161) },
      { status: "unchanged", exists: true, hash: "0".repeat(64), contentBase64: "Zg" },
      { status: "unchanged", exists: true, hash: "0".repeat(64), contentBase64: "/w==" },
    ];
    for (const planFile of values) {
      const bridge: BridgePort = { call: async () => ({
        version: 1, outcome: "notice", resultPatch: {
          planFile: wirePlanFile(planFile as Record<string, unknown>),
        },
      }) };
      await expect(callPlanFileBridge(bridge, "C:/repo", {
        slug: "demo", kind: "spec", action: "read",
      })).resolves.toBeUndefined();
    }
  });

  test("rejects content beyond the shared decoded bound before transport", async () => {
    let calls = 0;
    const bridge: BridgePort = { call: async () => {
      calls += 1;
      throw new Error("must not be called");
    } };
    await expect(callPlanFileBridge(bridge, "C:/repo", {
      slug: "demo", kind: "plan", action: "replace", expectedHash: null, content: "x".repeat(92_161),
    })).resolves.toBeUndefined();
    expect(calls).toBe(0);
  });

  test("round-trips the maximum escaped and non-ASCII payload through a real BridgeClient envelope", async () => {
    const content = '"\\é'.repeat(23_040);
    expect(Buffer.byteLength(content, "utf8")).toBe(92_160);
    const cwd = await realpath(await mkdtemp(resolve(tmpdir(), "ca-pi-plan-envelope-")));
    roots.push(cwd);
    await mkdir(resolve(cwd, ".codearbiter", "specs"), { recursive: true });
    await mkdir(resolve(cwd, ".codearbiter", "plans"));
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const bridge = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      maxStreamBytes: 262_144,
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    await expect(callPlanFileBridge(bridge, cwd, {
      slug: "demo", kind: "spec", action: "replace", expectedHash: null, content,
    })).resolves.toMatchObject({ status: "committed", observed: true, content });
    await expect(readFile(resolve(cwd, ".codearbiter", "specs", "demo.md"), "utf8")).resolves.toBe(content);
  });
});

const roots: string[] = [];

function pythonExecutable(): string {
  for (const candidate of process.platform === "win32" ? ["python", "python3"] : ["python3", "python"]) {
    const result = spawnSync(candidate, ["-c", "import sys; print(sys.executable)"], {
      encoding: "utf8",
      shell: false,
      windowsHide: true,
    });
    const value = result.stdout.trim();
    if (result.status === 0 && value !== "") return value;
  }
  throw new Error("Python is required for the Pi bridge tests");
}

function gitExecutable(): string {
  return resolveGitExecutable(tmpdir());
}

function windowsShortPath(input: string): string {
  const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
  if (process.platform !== "win32" || systemRoot === undefined) {
    throw new Error("Windows system root is required for the short-path regression");
  }
  const result = spawnSync(resolve(systemRoot, "System32", "cmd.exe"), [
    "/d", "/s", "/c", 'for %I in ("%CA_PI_LONG_PATH%") do @echo %~sI',
  ], {
    encoding: "utf8",
    env: { SystemRoot: systemRoot, CA_PI_LONG_PATH: input },
    shell: false,
    windowsVerbatimArguments: true,
    windowsHide: true,
  });
  const value = result.stdout.trim();
  if (result.status !== 0 || !isAbsolute(value) || value.toLowerCase() === input.toLowerCase()) {
    throw new Error("Windows short-path alias is unavailable for the containment regression");
  }
  return value;
}

async function clientFixture(source: string, options: {
  timeoutMs?: number;
  maxStreamBytes?: number;
  shouldAuditFailure?: (request: BridgeRequest) => boolean;
} = {}) {
  const packageRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-bridge-"));
  roots.push(packageRoot);
  const hooks = resolve(packageRoot, "hooks");
  await mkdir(hooks);
  const bridgeScript = resolve(hooks, "pi-bridge.py");
  await writeFile(bridgeScript, source, "utf8");
  return { packageRoot, bridge: new BridgeClient({
    bridgeScript,
    maxStreamBytes: options.maxStreamBytes ?? 16_384,
    packageRoot,
    pythonExecutable: pythonExecutable(),
    gitExecutable: gitExecutable(),
    timeoutMs: options.timeoutMs ?? 2_000,
    toolClasses: { bash: "EXEC", read: "READ", write: "WRITE", edit: "EDIT" },
    ...(options.shouldAuditFailure === undefined ? {} : { shouldAuditFailure: options.shouldAuditFailure }),
  }) };
}

async function clientFor(source: string, options: { timeoutMs?: number; maxStreamBytes?: number } = {}) {
  return (await clientFixture(source, options)).bridge;
}

function request(tool: string, input: Record<string, unknown>) {
  return { version: 1 as const, event: "tool_call", cwd: tmpdir(), tool, input };
}

async function executeWrappedRead(bridge: BridgePort, cwd: string): Promise<Record<string, unknown>> {
  const definitions = new Map<string, ToolDefinitionPort>();
  const pi: ToolGuardPiPort = {
    on: () => undefined,
    registerTool: (tool) => { definitions.set(tool.name, tool); },
    getActiveTools: () => [...definitions.keys()],
    getAllTools: () => [...definitions.keys()].map((name) => ({ name, sourceInfo: { path: resolve(cwd, "codearbiter.js") } })),
  };
  const create = (name: string) => () => ({
    name,
    execute: async () => ({
      content: [{ type: "text", text: name === "read" ? "native read output" : `${name} output` }],
      isError: false,
    }),
  });
  const factories: BuiltinToolFactories = {
    bash: create("bash"),
    edit: create("edit"),
    read: create("read"),
    write: create("write"),
  };
  wrapBuiltins(pi, bridge, {
    cwd,
    descriptor: { bash: "EXEC", edit: "EDIT", read: "READ", write: "WRITE" },
    factories,
    wrapperSourcePath: resolve(cwd, "codearbiter.js"),
  });
  return await definitions.get("read")!.execute(
    "read-diagnostic",
    { path: "README.md" },
    undefined,
    undefined,
    { sessionManager: { getSessionId: () => "bridge-diagnostic-session" } },
  );
}

afterEach(async () => {
  __setBridgeSpawnForTests(undefined);
  await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("BridgeClient", () => {
  test("ignores project-local, empty, and relative PATH entries when resolving Git", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-git-resolution-"));
    roots.push(root);
    const project = resolve(root, "project");
    const trusted = resolve(root, "trusted");
    await mkdir(project);
    await mkdir(trusted);
    const name = process.platform === "win32" ? "git.exe" : "git";
    const source = gitExecutable();
    const projectGit = resolve(project, name);
    const trustedGit = resolve(trusted, name);
    await copyFile(source, projectGit);
    await copyFile(source, trustedGit);
    if (process.platform !== "win32") {
      await chmod(projectGit, 0o755);
      await chmod(trustedGit, 0o755);
    }

    const resolved = resolveGitExecutable(
      project,
      process.platform,
      [project, "", "relative-bin", trusted].join(delimiter),
    );
    expect(resolved).toBe(realpathSync(trustedGit));
  });

  test("resolves launcher-only Windows, skips Python 2, and prefers python3 on POSIX", () => {
    const calls: string[] = [];
    const probe = (executable: string, prefixArgs: readonly string[], cwd: string) => {
      calls.push(`${executable} ${prefixArgs.join(" ")}`.trim() + ` @ ${cwd}`);
      if (executable === "py") return { status: 0, stdout: "3\nC:/Python311/python.exe\n", stderr: "" };
      return { status: 1, stdout: "", stderr: "" };
    };
    expect(resolvePythonCommand("win32", probe, "C:/trusted-package")).toEqual({ executable: "C:/Python311/python.exe", prefixArgs: [] });
    expect(calls[0]).toBe("py -3 @ C:/trusted-package");

    const mixed = (executable: string) => executable === "python"
      ? { status: 0, stdout: "2\nC:/Python27/python.exe\n", stderr: "" }
      : { status: 0, stdout: "3\nC:/Python311/python.exe\n", stderr: "" };
    expect(resolvePythonCommand("win32", mixed)).toEqual({ executable: "C:/Python311/python.exe", prefixArgs: [] });
    expect(resolvePythonCommand("linux", (executable) => executable === "python3"
      ? { status: 0, stdout: "3\n/usr/bin/python3\n", stderr: "" }
      : { status: 1, stdout: "", stderr: "" })).toEqual({ executable: "/usr/bin/python3", prefixArgs: [] });
  });

  test("redacts every shared corpus secret across protocol strings, nested patches, and stderr", async () => {
    const corpus = JSON.parse(await readFile(fileURLToPath(new URL("../../../ca/hooks/secret-detection-corpus.json", import.meta.url)), "utf8")) as { must_match: string[] };
    const joined = corpus.must_match.join(" | ");
    const protocol = await clientFor(`import json\ns=${JSON.stringify(joined)}\nprint(json.dumps({'version':1,'outcome':'notice','message':s,'context':s,'resultPatch':{'nested':[s]}}))\n`);
    const response = await protocol.call(request("read", { path: "README.md" }), new AbortController().signal);
    const serialized = JSON.stringify(response);
    for (const secret of corpus.must_match) expect(serialized).not.toContain(secret);
    const crash = await clientFor(`import sys\nsys.stderr.write(${JSON.stringify(joined)})\nsys.exit(1)\n`);
    const failure = await crash.call(request("read", { path: "README.md" }), new AbortController().signal);
    const failureText = JSON.stringify(failure);
    for (const secret of corpus.must_match) expect(failureText).not.toContain(secret);
  });
  test("runs Python from the trusted package and carries only absolute trusted executable identities", async () => {
    const packageRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-bridge-package-cwd-"));
    const projectCwd = await mkdtemp(resolve(tmpdir(), "ca-pi-bridge-project-cwd-"));
    roots.push(packageRoot, projectCwd);
    const hooks = resolve(packageRoot, "hooks");
    await mkdir(hooks);
    const bridgeScript = resolve(hooks, "pi-bridge.py");
    const trustedGit = await realpath(gitExecutable());
    const trustedPython = await realpath(pythonExecutable());
    await writeFile(
      bridgeScript,
      "import json, os\nprint(json.dumps({'version':1,'outcome':'notice','context':json.dumps({'cwd':os.getcwd(),'git':os.environ.get('CODEARBITER_GIT_EXECUTABLE'),'python':os.environ.get('CODEARBITER_PYTHON_EXECUTABLE'),'path':os.environ.get('PATH')})}))\n",
      "utf8",
    );
    const bridge = new BridgeClient({
      bridgeScript,
      packageRoot,
      pythonExecutable: trustedPython,
      gitExecutable: trustedGit,
      toolClasses: { read: "READ" },
    } as ConstructorParameters<typeof BridgeClient>[0]);

    const response = await bridge.call({
      ...request("read", { path: "README.md" }),
      cwd: projectCwd,
    }, new AbortController().signal);
    const observed = JSON.parse(response.context ?? "{}") as Record<string, string | undefined>;
    expect(observed.cwd).toBe(await realpath(packageRoot));
    expect(observed.git).toBe(trustedGit);
    expect(observed.python).toBe(trustedPython);
    const searchEntries = (observed.path ?? "").split(delimiter).filter(Boolean);
    expect(searchEntries.length).toBeGreaterThan(0);
    expect(searchEntries.every((entry) => isAbsolute(entry))).toBe(true);
    expect(searchEntries.some((entry) => entry.startsWith(projectCwd))).toBe(false);
    expect(searchEntries.some((entry) => entry.startsWith(packageRoot))).toBe(false);
    expect(observed.cwd).not.toBe(projectCwd);
  });
  test("carries a real subprocess bridge notice through the owned result patch boundary", async () => {
    const bridge = await clientFor(
      "import json\nprint(json.dumps({'version':1,'outcome':'notice','ruleId':'H-17','message':'REMINDER [H-17]: bridge context'}))\n",
    );
    const response = await bridge.call(request("read", { path: "README.md" }), new AbortController().signal);
    const original = { content: [{ type: "text", text: "native read output" }], details: { path: "README.md" } };
    const patch = applyToolResultNotice(original, response)!;
    expect(patch.content[0]).toEqual(original.content[0]);
    expect(JSON.stringify(patch.content)).toContain("REMINDER [H-17]: bridge context");
    expect(applyToolResultNotice({ ...original, ...patch }, response)).toBeUndefined();
  });
  test("blocks a mutating call when Python returns malformed protocol", async () => {
    const bridge = await clientFor("print('not-json')\n");
    const response = await bridge.call(request("bash", { command: "git status" }), new AbortController().signal);
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("/ca-doctor");
  });

  test("rejects a boolean bridge response protocol version", async () => {
    const bridge = await clientFor("import json\nprint(json.dumps({'version': True, 'outcome': 'allow'}))\n");
    const response = await bridge.call(request("bash", { command: "git status" }), new AbortController().signal);
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("/ca-doctor");
  });

  test("allows read on bridge failure and emits one redacted warning", async () => {
    const { bridge, packageRoot } = await clientFixture("import sys\nsys.stderr.write('OPENAI_API_KEY=synthetic-secret')\nsys.exit(1)\n");
    await mkdir(resolve(packageRoot, ".codearbiter"));
    await writeFile(resolve(packageRoot, ".codearbiter", "gate-events.log"), "", "utf8");
    const response = await bridge.call({ ...request("read", { path: "README.md" }), cwd: packageRoot }, new AbortController().signal);
    expect(response.outcome).toBe("warn");
    expect(response.ruleId).toBe("PI-BRIDGE");
    expect(response.message).toContain("/ca-doctor");
    expect(JSON.stringify(response)).not.toContain("synthetic-secret");
    const audit = await readFile(resolve(packageRoot, ".codearbiter", "gate-events.log"), "utf8");
    expect(audit).toContain("HOST: pi");
    expect(audit).toContain("AUDIT: PI_BRIDGE_WARN");
    expect(audit).toContain("CORRELATION:");
    expect(audit).not.toContain("synthetic-secret");
  });

  test("patched READ results classify invalid interpreter, script, and package paths without exposing them", async () => {
    const sentinel = "CA-PI-SENTINEL-USERNAME-private-root";
    const packageRoot = await mkdtemp(resolve(tmpdir(), `${sentinel}-`));
    roots.push(packageRoot);
    const hooks = resolve(packageRoot, "hooks");
    await mkdir(hooks);
    const bridgeScript = resolve(hooks, "pi-bridge.py");
    await writeFile(bridgeScript, "print('{}')\n", "utf8");
    await mkdir(resolve(packageRoot, ".codearbiter"));
    await writeFile(resolve(packageRoot, ".codearbiter", "gate-events.log"), "", "utf8");

    const invalid = [
      {
        bridgeScript,
        packageRoot,
        pythonExecutable: resolve(packageRoot, `${sentinel}-missing-python`),
      },
      {
        bridgeScript: resolve(hooks, `${sentinel}-missing-bridge.py`),
        packageRoot,
        pythonExecutable: pythonExecutable(),
      },
      {
        bridgeScript,
        packageRoot: resolve(packageRoot, `${sentinel}-missing-package`),
        pythonExecutable: pythonExecutable(),
      },
    ];

    for (const paths of invalid) {
      const bridge = new BridgeClient({
        ...paths,
        gitExecutable: gitExecutable(),
        toolClasses: { bash: "EXEC", read: "READ", write: "WRITE", edit: "EDIT" },
      });
      const serialized = JSON.stringify(await executeWrappedRead(bridge, packageRoot));
      expect(serialized).toContain("native read output");
      expect(serialized).toContain("path validation failed");
      expect(serialized).toContain("/ca-doctor");
      expect(serialized).not.toContain(sentinel);
      expect(serialized).not.toContain(paths.pythonExecutable);
      expect(serialized).not.toContain(paths.bridgeScript);
      expect(serialized).not.toContain(paths.packageRoot);
    }

    const audit = await readFile(resolve(packageRoot, ".codearbiter", "gate-events.log"), "utf8");
    expect(audit.match(/AUDIT: PI_BRIDGE_WARN/gu)).toHaveLength(3);
    expect(audit).not.toContain(sentinel);
  });

  test("patched READ results classify invalid executable identities without exposing their path", async () => {
    const sentinel = "CA-PI-SENTINEL-USERNAME-launch-root";
    const packageRoot = await mkdtemp(resolve(tmpdir(), `${sentinel}-`));
    roots.push(packageRoot);
    const hooks = resolve(packageRoot, "hooks");
    await mkdir(hooks);
    const bridgeScript = resolve(hooks, "pi-bridge.py");
    await writeFile(bridgeScript, "print('{}')\n", "utf8");
    const bridge = new BridgeClient({
      bridgeScript,
      packageRoot,
      pythonExecutable: packageRoot,
      gitExecutable: gitExecutable(),
      toolClasses: { bash: "EXEC", read: "READ", write: "WRITE", edit: "EDIT" },
    });

    const serialized = JSON.stringify(await executeWrappedRead(bridge, packageRoot));
    expect(serialized).toContain("native read output");
    expect(serialized).toContain("path validation failed");
    expect(serialized).toContain("/ca-doctor");
    expect(serialized).not.toContain(sentinel);
    expect(serialized).not.toContain(packageRoot);
  });

  test("patched READ results classify bridge process failures without exposing stderr paths", async () => {
    const sentinel = "CA-PI-SENTINEL-USERNAME-process-root";
    const { bridge, packageRoot } = await clientFixture(
      `import sys\nsys.stderr.write(${JSON.stringify(`C:/Users/${sentinel}/private/bridge.py`)})\nsys.exit(1)\n`,
    );

    const serialized = JSON.stringify(await executeWrappedRead(bridge, packageRoot));
    expect(serialized).toContain("native read output");
    expect(serialized).toContain("bridge process failed");
    expect(serialized).toContain("/ca-doctor");
    expect(serialized).not.toContain(sentinel);
    expect(serialized).not.toContain(`C:/Users/${sentinel}`);
  });

  test("redacts nested result patches before returning protocol data", async () => {
    const bridge = await clientFor("import json\nprint(json.dumps({'version': 1, 'outcome': 'notice', 'resultPatch': {'nested': ['OPENAI_API_KEY=synthetic-secret']}}))\n");
    const response = await bridge.call(request("read", { path: "README.md" }), new AbortController().signal);
    expect(response.outcome).toBe("notice");
    expect(JSON.stringify(response)).not.toContain("synthetic-secret");
    expect(JSON.stringify(response.resultPatch)).toContain("[REDACTED");
  });

  test("blocks mutation before retaining an overflowing protocol stream", async () => {
    const bridge = await clientFor("print('x' * 50000)\n", { maxStreamBytes: 1_024 });
    const response = await bridge.call(request("write", { path: "x", content: "x" }), new AbortController().signal);
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("overflow");
  });

  test("cancels a hung bridge tree and fails mutation closed", async () => {
    const sentinel = resolve(tmpdir(), `ca-pi-bridge-leak-${process.pid}-${Date.now()}`);
    const source = [
      "import subprocess, sys, time",
      `subprocess.Popen([sys.executable, '-c', \"import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('leak')\", ${JSON.stringify(sentinel)}])`,
      "time.sleep(30)",
    ].join("\n");
    try {
      const bridge = await clientFor(source, { timeoutMs: 100 });
      const response = await bridge.call(request("edit", { path: "x", edits: [] }), new AbortController().signal);
      expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
      expect(response.message).toContain("timed out");
      await new Promise((done) => setTimeout(done, 1_200));
      await expect(access(sentinel)).rejects.toThrow();
    } finally {
      await rm(sentinel, { force: true });
    }
  });

  test("rejects a bridge script outside the installed package", async () => {
    const packageRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-package-"));
    const otherRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-outside-"));
    roots.push(packageRoot, otherRoot);
    const outside = resolve(otherRoot, "pi-bridge.py");
    await writeFile(outside, "print('{}')\n", "utf8");
    const bridge = new BridgeClient({
      bridgeScript: outside,
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: { bash: "EXEC" },
    });
    const response = await bridge.call(request("bash", { command: "true" }), new AbortController().signal);
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("/ca-doctor");
  });

  test("blocks mutation when the absolute Python interpreter is missing", async () => {
    const packageRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-python-missing-"));
    roots.push(packageRoot);
    const hooks = resolve(packageRoot, "hooks");
    await mkdir(hooks);
    const bridgeScript = resolve(hooks, "pi-bridge.py");
    await writeFile(bridgeScript, "print('{}')\n", "utf8");
    const bridge = new BridgeClient({
      bridgeScript,
      packageRoot,
      pythonExecutable: resolve(packageRoot, "missing-python"),
      gitExecutable: gitExecutable(),
      toolClasses: { bash: "EXEC" },
    });
    const response = await bridge.call(request("bash", { command: "true" }), new AbortController().signal);
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("/ca-doctor");
  });

  test("rejects direct executable identities inside a project-local package repository", async () => {
    const project = await mkdtemp(resolve(tmpdir(), "ca-pi-project-local-identities-"));
    roots.push(project);
    const packageRoot = resolve(project, "plugins", "ca-pi");
    const hooks = resolve(packageRoot, "hooks");
    await mkdir(hooks, { recursive: true });
    const bridgeScript = resolve(hooks, "pi-bridge.py");
    await writeFile(bridgeScript, "print('{}')\n", "utf8");
    const insideGit = resolve(project, process.platform === "win32" ? "git.exe" : "git");
    const insidePython = resolve(project, process.platform === "win32" ? "python.exe" : "python");
    await copyFile(gitExecutable(), insideGit);
    await copyFile(pythonExecutable(), insidePython);
    if (process.platform !== "win32") {
      await chmod(insideGit, 0o755);
      await chmod(insidePython, 0o755);
    }

    for (const identities of [
      { gitExecutable: insideGit, pythonExecutable: pythonExecutable() },
      { gitExecutable: gitExecutable(), pythonExecutable: insidePython },
    ]) {
      const bridge = new BridgeClient({
        bridgeScript,
        packageRoot,
        ...identities,
        toolClasses: { bash: "EXEC" },
      });
      const response = await bridge.call({
        version: 1,
        event: "tool_call",
        cwd: project,
        tool: "bash",
        input: { command: "true" },
      }, new AbortController().signal);
      expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
      expect(response.message).toContain("path validation failed");
    }
  });

  test("cancellation terminates the bridge tree and blocks mutation", async () => {
    const sentinel = resolve(tmpdir(), `ca-pi-bridge-cancel-leak-${process.pid}-${Date.now()}`);
    const source = [
      "import subprocess, sys, time",
      `subprocess.Popen([sys.executable, '-c', \"import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('leak')\", ${JSON.stringify(sentinel)}])`,
      "time.sleep(30)",
    ].join("\n");
    try {
      const bridge = await clientFor(source, { timeoutMs: 10_000 });
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 100);
      const response = await bridge.call(request("bash", { command: "true" }), controller.signal);
      expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
      expect(response.message).toContain("cancelled");
      await new Promise((done) => setTimeout(done, 1_200));
      await expect(access(sentinel)).rejects.toThrow();
    } finally {
      await rm(sentinel, { force: true });
    }
  });

  test("force-settles a call whose child never emits close after a failed kill", async () => {
    const bridge = await clientFor("import time\ntime.sleep(30)\n", { timeoutMs: 50 });
    const fakeStdout = new EventEmitter();
    const fakeStderr = new EventEmitter();
    const fakeStdin = { on: () => undefined, end: () => undefined };
    const fakeChild = Object.assign(new EventEmitter(), {
      pid: 999_999,
      stdout: fakeStdout,
      stderr: fakeStderr,
      stdin: fakeStdin,
      kill: () => true,
    }) as unknown as ReturnType<BridgeSpawnImpl>;
    __setBridgeSpawnForTests((() => fakeChild) as unknown as BridgeSpawnImpl);
    const started = Date.now();
    const response = await bridge.call(request("bash", { command: "true" }), new AbortController().signal);
    const elapsed = Date.now() - started;
    expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
    expect(response.message).toContain("timed out");
    expect(elapsed).toBeLessThan(5_000);
  });

  test("a rejecting validatePaths produces no unhandledRejection and a later call() still fails with the validation error", async () => {
    let unhandled: unknown;
    const onUnhandled = (reason: unknown) => { unhandled = reason; };
    process.once("unhandledRejection", onUnhandled);
    try {
      const bridge = new BridgeClient({
        bridgeScript: resolve(tmpdir(), "ca-pi-missing-bridge.py"),
        packageRoot: tmpdir(),
        toolClasses: { read: "READ" },
      });
      await new Promise((done) => setImmediate(done));
      await new Promise((done) => setTimeout(done, 0));
      expect(unhandled).toBeUndefined();
      const response = await bridge.call(request("read", { path: "README.md" }), new AbortController().signal);
      expect(response.outcome).toBe("warn");
      expect(response.message).toContain("path validation failed");
    } finally {
      process.removeListener("unhandledRejection", onUnhandled);
    }
  });
});

describe("Pi footer bridge adapters", () => {
  test("rejects C1 controls in usage timestamps before facts cross the bridge", async () => {
    const requests: BridgeRequest[] = [];
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (bridgeRequest) => {
        requests.push(bridgeRequest);
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: { status: "ok", session: totals, today: totals, acceptedThrough: 0, highWater: 0 } },
        };
      },
    };
    const context = {
      cwd: "C:/work/c1-usage",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => "c1-usage-session",
        getEntries: () => [{
          type: "message",
          timestamp: "2026-07-19T12:00:00Z\u0080hidden",
          message: {
            role: "assistant",
            usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, cost: { total: 0.01 } },
          },
        }],
      },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, context, -1)).resolves.toMatchObject({
      acknowledgedCursor: 0,
      retryRequired: false,
    });
    expect(requests[0]?.input).toMatchObject({ scanStart: 0, scanEnd: 0, facts: [] });
  });

  test("sends project-independent bounded usage ranges and returns only the fixed validated snapshot", async () => {
    const sessionId = `full-session-${"s".repeat(990)}-tail`;
    const sessionFile = "C:/private/session/location/session.jsonl";
    const entries = Array.from({ length: 258 }, (_value, position) => position === 1 || position === 257
      ? {
          type: "message",
          id: `assistant-${position}`,
          parentId: "must-not-cross",
          timestamp: `2026-07-19T12:00:${position === 1 ? "01" : "02"}-04:00`,
          message: {
            role: "assistant",
            content: `private-message-${position}`,
            usage: {
              input: position === 1 ? 10 : 20,
              output: position === 1 ? 4 : 8,
              cacheRead: position === 1 ? 3 : 6,
              cacheWrite: position === 1 ? 2 : 4,
              cost: { total: position === 1 ? 0.25 : 0.5 },
            },
          },
        }
      : { type: "message", timestamp: "2026-07-19T12:00:00-04:00", message: { role: "user", content: `private-${position}` } });
    const requests: Array<Record<string, unknown>> = [];
    const bridge: BridgePort = {
      call: async (bridgeRequest) => {
        requests.push(bridgeRequest as unknown as Record<string, unknown>);
        const input = bridgeRequest.input as { scanEnd: number };
        const final = input.scanEnd === 257;
        return {
          version: 1,
          outcome: "notice",
          auditCode: "PI_FOOTER_USAGE",
          resultPatch: {
            footerUsage: {
              status: "ok",
              session: {
                inputTokens: final ? 30 : 10,
                outputTokens: final ? 12 : 4,
                cacheReadTokens: final ? 9 : 3,
                cacheWriteTokens: final ? 6 : 2,
                costUsd: final ? 0.75 : 0.25,
              },
              today: {
                inputTokens: final ? 30 : 10,
                outputTokens: final ? 12 : 4,
                cacheReadTokens: final ? 9 : 3,
                cacheWriteTokens: final ? 6 : 2,
                costUsd: final ? 0.75 : 0.25,
              },
              acceptedThrough: input.scanEnd,
              highWater: input.scanEnd,
            },
          },
        };
      },
    };
    const context = {
      cwd: "C:/work/project-a",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => sessionId,
        getSessionFile: () => sessionFile,
        getEntries: () => entries,
      },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    const result = await updateFooterUsageSnapshot(bridge, context, -1);

    expect(result).toEqual({
      acknowledgedCursor: 257,
      retryRequired: false,
      snapshot: {
        session: {
          inputTokens: 30,
          outputTokens: 12,
          cacheReadTokens: 9,
          cacheWriteTokens: 6,
          costUsd: 0.75,
        },
        today: { inputTokens: 30, outputTokens: 12, costUsd: 0.75 },
      },
    });
    expect(requests).toHaveLength(2);
    const expectedKey = createHash("sha256")
      .update(JSON.stringify([sessionId, sessionFile]), "utf8")
      .digest("hex");
    expect(requests.map((entry) => entry.input)).toEqual([
      {
        sessionKey: expectedKey,
        scanStart: 0,
        scanEnd: 255,
        facts: [{
          position: 1,
          timestamp: "2026-07-19T12:00:01-04:00",
          inputTokens: 10,
          outputTokens: 4,
          cacheReadTokens: 3,
          cacheWriteTokens: 2,
          costUsd: 0.25,
        }],
      },
      {
        sessionKey: expectedKey,
        scanStart: 256,
        scanEnd: 257,
        facts: [{
          position: 257,
          timestamp: "2026-07-19T12:00:02-04:00",
          inputTokens: 20,
          outputTokens: 8,
          cacheReadTokens: 6,
          cacheWriteTokens: 4,
          costUsd: 0.5,
        }],
      },
    ]);
    expect(requests.every((entry) => entry.event === "footer_usage_update")).toBe(true);
    const crossing = JSON.stringify(requests);
    expect(crossing).not.toContain(sessionId);
    expect(crossing).not.toContain(sessionFile);
    expect(crossing).not.toContain("private-message");
    expect(crossing).not.toContain("must-not-cross");
  });

  test("makes zero governance bridge calls unless activation is enabled and Pi trust is affirmative", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const bridge: BridgePort = {
      call: async (bridgeRequest) => {
        calls.push(bridgeRequest as unknown as Record<string, unknown>);
        return {
          version: 1,
          outcome: "notice",
          auditCode: "PI_FOOTER_STATUS",
          resultPatch: {
            footerStatus: {
              status: "ok",
              stage: "implementation",
              tasks: 2,
              questions: 1,
              overrides: 0,
              sprint: true,
              dev: false,
              prune: null,
            },
          },
        };
      },
    };
    const context = (trust?: () => boolean) => ({
      cwd: "C:/work/project-b",
      signal: new AbortController().signal,
      ...(trust === undefined ? {} : { isProjectTrusted: trust }),
      sessionManager: { getSessionId: () => "pi-session" },
    }) as Pick<ExtensionContextPort, "cwd" | "signal" | "isProjectTrusted" | "sessionManager">;

    await expect(readFooterStatusSnapshot(bridge, context(() => true), { enabled: false })).resolves.toBeUndefined();
    await expect(readFooterStatusSnapshot(bridge, context(() => false), { enabled: true })).resolves.toBeUndefined();
    await expect(readFooterStatusSnapshot(bridge, context(), { enabled: true })).resolves.toBeUndefined();
    await expect(readFooterStatusSnapshot(bridge, context(() => { throw new Error("trust unavailable"); }), { enabled: true })).resolves.toBeUndefined();
    expect(calls).toEqual([]);

    await expect(readFooterStatusSnapshot(bridge, context(() => true), { enabled: true })).resolves.toEqual({
      stage: "implementation",
      tasks: 2,
      questions: 1,
      overrides: 0,
      sprint: true,
      dev: false,
      prune: undefined,
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ version: 1, event: "footer_status_snapshot", cwd: "C:/work/project-b", sessionId: "pi-session" });
    expect(calls[0]).not.toHaveProperty("input");
  });

  test("dispatches footer usage only to the user-global ledger and never writes cwd project state or audit", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-usage-event-"));
    roots.push(root);
    const cwd = resolve(root, "project-without-codearbiter");
    const isolatedHome = resolve(root, "home");
    await mkdir(cwd);
    await mkdir(isolatedHome);
    const timestamp = new Date().toISOString();
    const bridgeRequest = {
      version: 1,
      event: "footer_usage_update",
      cwd,
      input: {
        sessionKey: "a".repeat(64),
        scanStart: 0,
        scanEnd: 1,
        facts: [{
          position: 1,
          timestamp,
          inputTokens: 10,
          outputTokens: 4,
          cacheReadTokens: 3,
          cacheWriteTokens: 2,
          costUsd: 0.25,
        }],
      },
    } as const;
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const bridge = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    const previousHome = process.env.HOME;
    const previousProfile = process.env.USERPROFILE;
    process.env.HOME = isolatedHome;
    process.env.USERPROFILE = isolatedHome;
    let response;
    try {
      response = await bridge.call(bridgeRequest, new AbortController().signal);
    } finally {
      if (previousHome === undefined) delete process.env.HOME;
      else process.env.HOME = previousHome;
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
    }

    expect(response).toEqual({
      version: 1,
      outcome: "notice",
      auditCode: "PI_FOOTER_USAGE",
      resultPatch: {
        footerUsage: {
          status: "ok",
          session: {
            inputTokens: 10,
            outputTokens: 4,
            cacheReadTokens: 3,
            cacheWriteTokens: 2,
            costUsd: 0.25,
          },
          today: {
            inputTokens: 10,
            outputTokens: 4,
            cacheReadTokens: 3,
            cacheWriteTokens: 2,
            costUsd: 0.25,
          },
          acceptedThrough: 1,
          highWater: 1,
        },
      },
    });
    expect(await readdir(cwd)).toEqual([]);
    await expect(access(resolve(isolatedHome, ".codearbiter", "pi-usage-ledger.json"))).resolves.toBeUndefined();
  });

  test("resumes from a stale local cursor through the real bridge without replay deadlock or double-counting", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-replay-cross-layer-"));
    roots.push(root);
    const cwd = resolve(root, "project");
    const isolatedHome = resolve(root, "home");
    await mkdir(cwd);
    await mkdir(isolatedHome);
    const timestamp = new Date().toISOString();
    const entries = Array.from({ length: 300 }, (_value, position) => position === 1 || position === 257
      ? {
          type: "message",
          timestamp,
          message: {
            role: "assistant",
            usage: {
              input: position === 1 ? 10 : 20,
              output: 0,
              cacheRead: 0,
              cacheWrite: 0,
              cost: { total: position === 1 ? 0.1 : 0.2 },
            },
          },
        }
      : { type: "message", timestamp, message: { role: "user" } });
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const client = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    let calls = 0;
    const bridge: BridgePort = {
      call: async (request, signal) => {
        calls += 1;
        return await client.call(request, signal);
      },
    };
    const context = {
      cwd,
      signal: new AbortController().signal,
      sessionManager: { getSessionId: () => "cross-layer-replay", getEntries: () => entries },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;
    const previousHome = process.env.HOME;
    const previousProfile = process.env.USERPROFILE;
    process.env.HOME = isolatedHome;
    process.env.USERPROFILE = isolatedHome;
    let first: PiFooterUsageUpdateResult;
    let resumed: PiFooterUsageUpdateResult;
    try {
      first = await updateFooterUsageSnapshot(bridge, context, -1);
      expect(calls).toBe(2);
      calls = 0;
      resumed = await updateFooterUsageSnapshot(bridge, context, -1);
    } finally {
      if (previousHome === undefined) delete process.env.HOME;
      else process.env.HOME = previousHome;
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
    }

    expect(first).toMatchObject({ acknowledgedCursor: 299, retryRequired: false });
    expect(first.snapshot?.session?.inputTokens).toBe(30);
    expect(resumed).toEqual(first);
    expect(calls).toBe(1);
    const sessionKey = createHash("sha256")
      .update(JSON.stringify(["cross-layer-replay", null]), "utf8")
      .digest("hex");
    const shard = JSON.parse(await readFile(
      resolve(isolatedHome, ".codearbiter", `pi-usage-ledger.json.sessions/${sessionKey}.json`),
      "utf8",
    )) as { highWater: number; totals: { inputTokens: number } };
    expect(shard).toMatchObject({ highWater: 299, totals: { inputTokens: 30 } });
  });

  test("rejects a C1 timestamp at the real Python ledger boundary", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-c1-ledger-"));
    roots.push(root);
    const cwd = resolve(root, "project");
    const isolatedHome = resolve(root, "home");
    await mkdir(cwd);
    await mkdir(isolatedHome);
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const bridge = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    const previousHome = process.env.HOME;
    const previousProfile = process.env.USERPROFILE;
    process.env.HOME = isolatedHome;
    process.env.USERPROFILE = isolatedHome;
    let response: BridgeResponse;
    try {
      response = await bridge.call({
        version: 1,
        event: "footer_usage_update",
        cwd,
        input: {
          sessionKey: "b".repeat(64),
          scanStart: 0,
          scanEnd: 0,
          facts: [{
            position: 0,
            timestamp: "2026-07-19\u008012:00:00+00:00",
            inputTokens: 1,
            outputTokens: 0,
            cacheReadTokens: 0,
            cacheWriteTokens: 0,
            costUsd: 0,
          }],
        },
      }, new AbortController().signal);
    } finally {
      if (previousHome === undefined) delete process.env.HOME;
      else process.env.HOME = previousHome;
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
    }

    expect(response.resultPatch).toEqual({
      footerUsage: {
        status: "invalid",
        session: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 },
        today: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 },
        acceptedThrough: -1,
        highWater: -1,
      },
    });
  });

  test("does not append a project audit row when the project-independent usage bridge fails", async () => {
    const { bridge, packageRoot } = await clientFixture("raise RuntimeError('synthetic failure')\n", {
      shouldAuditFailure: (request) => request.event !== "footer_usage_update",
    });
    await mkdir(resolve(packageRoot, ".codearbiter"));
    const auditPath = resolve(packageRoot, ".codearbiter", "gate-events.log");
    await writeFile(auditPath, "", "utf8");

    const response = await bridge.call({
      version: 1,
      event: "footer_usage_update",
      cwd: packageRoot,
      input: { sessionKey: "a".repeat(64), scanStart: 0, scanEnd: 0, facts: [] },
    }, new AbortController().signal);

    expect(response).toMatchObject({ outcome: "warn", ruleId: "PI-BRIDGE" });
    expect(await readFile(auditPath, "utf8")).toBe("");
  });

  test("stops at the first non-ok usage range and replays that exact range from the returned cursor", async () => {
    const entries = Array.from({ length: 300 }, () => ({
      type: "message",
      timestamp: "2026-07-19T12:00:00-04:00",
      message: { role: "user", content: "never-crosses" },
    }));
    const calls: Array<{ scanStart: number; scanEnd: number; facts: unknown[] }> = [];
    let failSecond = true;
    const totals = {
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
      costUsd: 0,
    };
    const bridge: BridgePort = {
      call: async (bridgeRequest) => {
        const input = bridgeRequest.input as { scanStart: number; scanEnd: number; facts: unknown[] };
        calls.push(input);
        return {
          version: 1,
          outcome: "notice",
          resultPatch: {
            footerUsage: {
              status: failSecond && input.scanStart === 256 ? "write_failed" : "ok",
              session: totals,
              today: totals,
              acceptedThrough: failSecond && input.scanStart === 256 ? -1 : input.scanEnd,
              highWater: input.scanEnd,
            },
          },
        };
      },
    };
    const context = {
      cwd: "C:/work/retry-project",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => "retry-session",
        getEntries: () => entries,
      },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    const failed = await updateFooterUsageSnapshot(bridge, context, -1);
    expect(failed).toEqual({ acknowledgedCursor: 255, retryRequired: true });
    expect(failed).not.toHaveProperty("snapshot");
    expect(calls.map(({ scanStart, scanEnd }) => ({ scanStart, scanEnd }))).toEqual([
      { scanStart: 0, scanEnd: 255 },
      { scanStart: 256, scanEnd: 299 },
    ]);

    failSecond = false;
    calls.length = 0;
    const retried = await updateFooterUsageSnapshot(bridge, context, failed.acknowledgedCursor);
    expect(retried).toMatchObject({ acknowledgedCursor: 299, retryRequired: false });
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ scanStart: 256, scanEnd: 299, facts: [] });
  });

  test("bounds one refresh to one requested 256-entry range and reports remaining work", async () => {
    const entries = Array.from({ length: 600 }, () => ({ type: "message", message: { role: "user" } }));
    const calls: Array<{ scanStart: number; scanEnd: number }> = [];
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => {
        const input = request.input as { scanStart: number; scanEnd: number };
        calls.push({ scanStart: input.scanStart, scanEnd: input.scanEnd });
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: {
            status: "ok",
            session: totals,
            today: totals,
            acceptedThrough: input.scanEnd,
            highWater: input.scanEnd,
          } },
        };
      },
    };
    const context = {
      cwd: "C:/work/bounded-refresh",
      signal: new AbortController().signal,
      sessionManager: { getSessionId: () => "bounded-refresh", getEntries: () => entries },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, context, -1, { maxRanges: 1 })).resolves.toEqual({
      acknowledgedCursor: 255,
      retryRequired: false,
      morePending: true,
      snapshot: {
        session: totals,
        today: { inputTokens: 0, outputTokens: 0, costUsd: 0 },
      },
    });
    expect(calls).toEqual([{ scanStart: 0, scanEnd: 255 }]);
  });

  test("rejects malformed or oversized fixed usage outputs without fabricating a snapshot", async () => {
    const entries = [{ type: "message", message: { role: "user", content: "private" } }];
    const base = {
      status: "ok",
      session: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 },
      today: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 },
      acceptedThrough: 0,
      highWater: 0,
    };
    const invalid = [
      { ...base, extra: "not-fixed" },
      { ...base, session: { ...base.session, inputTokens: 1_000_000_000_000_001 } },
      { ...base, today: { ...base.today, costUsd: Number.POSITIVE_INFINITY } },
      { ...base, acceptedThrough: 2_147_483_648 },
      { ...base, highWater: 2_147_483_648 },
      { ...base, status: "invented" },
    ];
    const context = {
      cwd: "C:/work/malformed-project",
      signal: new AbortController().signal,
      sessionManager: { getSessionId: () => "malformed-session", getEntries: () => entries },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    for (const footerUsage of invalid) {
      const bridge: BridgePort = {
        call: async () => ({ version: 1, outcome: "notice", resultPatch: { footerUsage } }),
      };
      const result = await updateFooterUsageSnapshot(bridge, context, -1);
      expect(result).toEqual({ acknowledgedCursor: -1, retryRequired: true });
      expect(result).not.toHaveProperty("snapshot");
    }
  });

  test("refuses to cross usage facts when the source-verified session file identity is not stable", async () => {
    let fileReads = 0;
    let bridgeCalls = 0;
    const bridge: BridgePort = {
      call: async () => {
        bridgeCalls += 1;
        return { version: 1, outcome: "allow" };
      },
    };
    const context = {
      cwd: "C:/work/session-switch",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => "same-session-id",
        getSessionFile: () => (++fileReads === 1 ? "C:/private/one.jsonl" : "C:/private/two.jsonl"),
        getEntries: () => [{ type: "message", message: { role: "user", content: "private" } }],
      },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, context, -1)).resolves.toEqual({
      acknowledgedCursor: -1,
      retryRequired: true,
    });
    expect(fileReads).toBe(2);
    expect(bridgeCalls).toBe(0);
  });

  test("maps absent or explicitly undefined session files to null while rejecting other present invalid implementations", async () => {
    let bridgeCalls = 0;
    let entryReads = 0;
    const sessionKeys: string[] = [];
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async (request) => {
        bridgeCalls += 1;
        sessionKeys.push((request.input as { sessionKey: string }).sessionKey);
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: { status: "ok", session: totals, today: totals, acceptedThrough: 0, highWater: 0 } },
        };
      },
    };
    const makeContext = (sessionManager: Record<string, unknown>) => ({
      cwd: "C:/work/session-file-capability",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => "session-file-capability",
        getEntries: () => { entryReads += 1; return [{ type: "message", message: { role: "user" } }]; },
        ...sessionManager,
      },
    }) as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, makeContext({}), -1)).resolves.toMatchObject({
      acknowledgedCursor: 0,
      retryRequired: false,
    });
    expect(entryReads).toBe(1);
    expect(bridgeCalls).toBe(1);

    await expect(updateFooterUsageSnapshot(
      bridge,
      makeContext({ getSessionFile: () => undefined }),
      -1,
    )).resolves.toMatchObject({ acknowledgedCursor: 0, retryRequired: false });
    const expectedNullIdentity = createHash("sha256")
      .update(JSON.stringify(["session-file-capability", null]), "utf8")
      .digest("hex");
    expect(sessionKeys).toEqual([expectedNullIdentity, expectedNullIdentity]);
    expect(entryReads).toBe(2);
    expect(bridgeCalls).toBe(2);

    for (const getSessionFile of [
      () => { throw new Error("unavailable"); },
      () => "",
      () => null,
      () => 42,
      () => ({}),
      () => "bad\u0080control",
      () => "p".repeat(32_769),
      "not-callable",
    ]) {
      await expect(updateFooterUsageSnapshot(bridge, makeContext({ getSessionFile }), -1)).resolves.toEqual({
        acknowledgedCursor: -1,
        retryRequired: true,
      });
    }
    expect(entryReads).toBe(2);
    expect(bridgeCalls).toBe(2);
  });

  test("reads the real fixed governance snapshot through shared state readers", async () => {
    const cwd = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-status-project-"));
    roots.push(cwd);
    const state = resolve(cwd, ".codearbiter");
    await mkdir(resolve(state, ".markers"), { recursive: true });
    await writeFile(resolve(state, "CONTEXT.md"), "---\narbiter: enabled\nstage: implementation\n---\n", "utf8");
    await writeFile(resolve(state, "open-tasks.md"), "- [ ] queued\n- [~] active\n- [x] done\n", "utf8");
    await writeFile(resolve(state, "open-questions.md"), "[CONFIRM-01] choose\n", "utf8");
    await writeFile(resolve(state, "overrides.log"), "one\ntwo\n", "utf8");
    await writeFile(resolve(state, "last-checkpoint"), "1\n", "utf8");
    await writeFile(resolve(state, "sprint-active"), "active\n", "utf8");
    await writeFile(resolve(state, ".markers", "dev-active"), "active\n", "utf8");
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const bridge = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    const context = {
      cwd,
      signal: new AbortController().signal,
      isProjectTrusted: () => true,
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "isProjectTrusted" | "sessionManager">;

    await expect(readFooterStatusSnapshot(bridge, context, { enabled: true })).resolves.toEqual({
      stage: "implementation",
      tasks: 2,
      questions: 1,
      overrides: 1,
      sprint: true,
      dev: true,
      prune: undefined,
    });
  });

  test.skipIf(process.platform !== "win32")("passes only a canonical non-project Windows home into the actual BridgeClient child environment", async () => {
    const home = await realpath(await mkdtemp(resolve(tmpdir(), "ca-pi-trusted-home-")));
    roots.push(home);
    const homeAlias = windowsShortPath(home);
    const previousProfile = process.env.USERPROFILE;
    const previousSentinel = process.env.CA_PI_PROJECT_SENTINEL;
    process.env.USERPROFILE = homeAlias;
    process.env.CA_PI_PROJECT_SENTINEL = "must-not-cross";
    try {
      const { bridge, packageRoot } = await clientFixture([
        "import json, os",
        "value = {'profile': os.environ.get('USERPROFILE'), 'expanded': os.path.expanduser('~'), 'sentinel': os.environ.get('CA_PI_PROJECT_SENTINEL')}",
        "print(json.dumps({'version': 1, 'outcome': 'notice', 'context': json.dumps(value)}))",
      ].join("\n"));
      const response = await bridge.call({
        version: 1,
        event: "footer_usage_update",
        cwd: packageRoot,
        input: { sessionKey: "a".repeat(64), scanStart: 0, scanEnd: 0, facts: [] },
      }, new AbortController().signal);
      expect(response.outcome).toBe("notice");
      const observed = JSON.parse(response.context ?? "{}") as Record<string, unknown>;
      expect(observed.profile).toBe(await realpath(home));
      expect(observed.expanded).toBe(await realpath(home));
      expect(observed.sentinel).toBeNull();
    } finally {
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
      if (previousSentinel === undefined) delete process.env.CA_PI_PROJECT_SENTINEL;
      else process.env.CA_PI_PROJECT_SENTINEL = previousSentinel;
    }
  });

  test.skipIf(process.platform !== "win32")("rejects a Windows short-path home alias inside the request project before spawning", async () => {
    const previousProfile = process.env.USERPROFILE;
    const { bridge, packageRoot } = await clientFixture(
      "import json\nprint(json.dumps({'version': 1, 'outcome': 'notice', 'context': 'child-ran'}))\n",
    );
    const canonicalPackageRoot = await realpath(packageRoot);
    process.env.USERPROFILE = windowsShortPath(canonicalPackageRoot);
    let spawnCalls = 0;
    __setBridgeSpawnForTests((() => {
      spawnCalls += 1;
      throw new Error("contained home aliases must fail before spawn");
    }) as BridgeSpawnImpl);
    try {
      const response = await bridge.call({
        version: 1,
        event: "footer_usage_update",
        cwd: canonicalPackageRoot,
        input: { sessionKey: "a".repeat(64), scanStart: 0, scanEnd: 0, facts: [] },
      }, new AbortController().signal);
      expect(response).toMatchObject({ outcome: "warn", ruleId: "PI-BRIDGE" });
      expect(response.context).not.toBe("child-ran");
      expect(spawnCalls).toBe(0);
    } finally {
      __setBridgeSpawnForTests(undefined);
      if (previousProfile === undefined) delete process.env.USERPROFILE;
      else process.env.USERPROFILE = previousProfile;
    }
  });

  test("rejects a forged per-call acknowledgment that does not equal scanEnd", async () => {
    const entries = Array.from({ length: 257 }, () => ({ type: "message", message: { role: "user" } }));
    let calls = 0;
    const totals = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, costUsd: 0 };
    const bridge: BridgePort = {
      call: async () => {
        calls += 1;
        return {
          version: 1,
          outcome: "notice",
          resultPatch: { footerUsage: { status: "ok", session: totals, today: totals, acceptedThrough: 256, highWater: 256 } },
        };
      },
    };
    const context = {
      cwd: "C:/work/no-skip",
      signal: new AbortController().signal,
      sessionManager: { getSessionId: () => "no-skip-session", getEntries: () => entries },
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, context, -1)).resolves.toEqual({
      acknowledgedCursor: -1,
      retryRequired: true,
    });
    expect(calls).toBe(1);
  });

  test("rejects C1 controls in fixed TypeScript governance stage and prune fields", async () => {
    const context = {
      cwd: "C:/work/c1",
      signal: new AbortController().signal,
      isProjectTrusted: () => true,
    } as Pick<ExtensionContextPort, "cwd" | "signal" | "isProjectTrusted" | "sessionManager">;
    for (const footerStatus of [
      { status: "ok", stage: "impl\u0080hidden", tasks: 0, questions: 0, overrides: 0, sprint: false, dev: false, prune: null },
      { status: "ok", stage: "impl", tasks: 0, questions: 0, overrides: 0, sprint: false, dev: false, prune: "cut\u009fhidden" },
    ]) {
      const bridge: BridgePort = {
        call: async () => ({ version: 1, outcome: "notice", resultPatch: { footerStatus } }),
      };
      await expect(readFooterStatusSnapshot(bridge, context, { enabled: true })).resolves.toBeUndefined();
    }
  });

  test("strips C1 controls from the real Python governance normalization boundary", async () => {
    const cwd = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-status-c1-"));
    roots.push(cwd);
    const state = resolve(cwd, ".codearbiter");
    await mkdir(state);
    await writeFile(resolve(state, "CONTEXT.md"), "---\narbiter: enabled\nstage: impl\u0080hidden\n---\n", "utf8");
    const packageRoot = fileURLToPath(new URL("../..", import.meta.url));
    const bridge = new BridgeClient({
      bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
      packageRoot,
      pythonExecutable: pythonExecutable(),
      gitExecutable: gitExecutable(),
      toolClasses: {},
    });
    const response = await bridge.call({
      version: 1,
      event: "footer_status_snapshot",
      cwd,
    }, new AbortController().signal);
    const patch = response.resultPatch as { footerStatus?: { stage?: unknown } } | undefined;
    expect(patch?.footerStatus?.stage).toBe("implhidden");
    expect(JSON.stringify(response)).not.toContain("\u0080");
  });

  test("strips C1 controls from both Python stage and prune normalization inputs", () => {
    const bridgeScript = fileURLToPath(new URL("../../hooks/pi-bridge.py", import.meta.url));
    const hooks = resolve(bridgeScript, "..");
    const source = [
      "import importlib.util, json, sys",
      `sys.path.insert(0, ${JSON.stringify(hooks)})`,
      `spec = importlib.util.spec_from_file_location('ca_pi_bridge_c1', ${JSON.stringify(bridgeScript)})`,
      "module = importlib.util.module_from_spec(spec)",
      "spec.loader.exec_module(module)",
      "print(json.dumps([module._bounded_footer_text('stage\\u0080x', 128), module._bounded_footer_text('prune\\u009fx', 256)]))",
    ].join("\n");
    const completed = spawnSync(pythonExecutable(), ["-c", source], {
      cwd: resolve(import.meta.dirname, "../.."),
      encoding: "utf8",
      shell: false,
      windowsHide: true,
    });

    expect(completed.status, completed.stderr).toBe(0);
    expect(JSON.parse(completed.stdout)).toEqual(["stagex", "prunex"]);
  });

  test("does not grow the project audit log when configured display polling calls fail", async () => {
    let decisions = 0;
    const { bridge, packageRoot } = await clientFixture("raise RuntimeError('poll failure')\n", {
      shouldAuditFailure: () => { decisions += 1; return false; },
    });
    await mkdir(resolve(packageRoot, ".codearbiter"));
    const auditPath = resolve(packageRoot, ".codearbiter", "gate-events.log");
    await writeFile(auditPath, "existing\n", "utf8");
    const request = { version: 1 as const, event: "tool_call", cwd: packageRoot, tool: "read" };

    await bridge.call(request, new AbortController().signal);
    await bridge.call(request, new AbortController().signal);

    expect(decisions).toBe(2);
    expect(await readFile(auditPath, "utf8")).toBe("existing\n");
  });

  test("fails soft before reading entries or hashing oversized session identity parts", async () => {
    let bridgeCalls = 0;
    let entryReads = 0;
    const bridge: BridgePort = {
      call: async () => {
        bridgeCalls += 1;
        return { version: 1, outcome: "allow" };
      },
    };
    const makeContext = (sessionId: string, sessionFile: string) => ({
      cwd: "C:/work/identity-bounds",
      signal: new AbortController().signal,
      sessionManager: {
        getSessionId: () => sessionId,
        getSessionFile: () => sessionFile,
        getEntries: () => { entryReads += 1; return []; },
      },
    }) as Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">;

    await expect(updateFooterUsageSnapshot(bridge, makeContext("s".repeat(1_025), "C:/safe/session.jsonl"), -1)).resolves.toEqual({
      acknowledgedCursor: -1,
      retryRequired: true,
    });
    await expect(updateFooterUsageSnapshot(bridge, makeContext("bounded", `C:/${"p".repeat(32_768)}`), -1)).resolves.toEqual({
      acknowledgedCursor: -1,
      retryRequired: true,
    });
    expect(entryReads).toBe(0);
    expect(bridgeCalls).toBe(0);
  });
});
