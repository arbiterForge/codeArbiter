import { access, chmod, copyFile, mkdtemp, mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, isAbsolute, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, test } from "vitest";

import { BridgeClient, resolveGitExecutable, resolvePythonCommand } from "../src/bridge.ts";
import type { BridgePort, BuiltinToolFactories, ToolDefinitionPort, ToolGuardPiPort } from "../src/contracts.ts";
import { applyToolResultNotice } from "../src/notices.ts";
import { wrapBuiltins } from "../src/tool-guard.ts";

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

async function clientFixture(source: string, options: { timeoutMs?: number; maxStreamBytes?: number } = {}) {
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
});
