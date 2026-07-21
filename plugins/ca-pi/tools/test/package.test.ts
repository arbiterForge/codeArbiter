/** package.test.ts - codeArbiter's Pi package and host-module identity contract. */
import { execFileSync, spawn } from "node:child_process";
import { constants } from "node:fs";
import { access, chmod, copyFile, cp, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { createServer as createHttpServer } from "node:http";
import { connect, createServer } from "node:net";
import { tmpdir } from "node:os";
import { delimiter, dirname, parse, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, test } from "vitest";

import { compatibilityDirection } from "../src/compatibility.ts";
import { createCodeArbiterPi, createPiFooterMetricsLoader } from "../src/extension.ts";

const toolsRoot = resolve(import.meta.dirname, "..");
const pluginRoot = resolve(toolsRoot, "..");
const bundles = [
  resolve(pluginRoot, "extensions", "codearbiter.js"),
  resolve(pluginRoot, "extensions", "codearbiter-child.js"),
];
const windowsSupervisor = resolve(pluginRoot, "helpers", "windows-supervisor.js");
// This real-host isolation proof starts a loopback Git daemon, clones the pinned
// package, and loads the external Pi runtime. Cold hosted Windows I/O can exceed
// Vitest's default without any individual product operation hanging. Keep the
// aggregate fixture bound below the platform runner's 180-second command cap.
const LIVE_DUPLICATE_HOST_TIMEOUT_MS = 120_000;

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function findPiPackageRoot(): Promise<string> {
  const pathEntries = (process.env.PATH ?? "").split(delimiter).filter(Boolean);
  const executableNames = process.platform === "win32" ? ["pi.cmd", "pi.exe", "pi.ps1", "pi"] : ["pi"];
  for (const entry of pathEntries) {
    let executable: string | undefined;
    for (const name of executableNames) {
      const candidate = resolve(entry, name);
      try {
        await access(candidate, constants.X_OK);
        executable = candidate;
        break;
      } catch {
        // Continue to the next platform-native executable spelling.
      }
    }
    if (executable === undefined) continue;
    let cursor = dirname(await realpath(executable));
    for (let depth = 0; depth < 8; depth += 1) {
      const candidate = resolve(cursor, "package.json");
      if (await exists(candidate)) {
        const manifest = JSON.parse(await readFile(candidate, "utf8")) as { name?: string };
        if (manifest.name === "@earendil-works/pi-coding-agent") return cursor;
      }
      const parent = dirname(cursor);
      if (parent === cursor || cursor === parse(cursor).root) break;
      cursor = parent;
    }
    const adjacent = resolve(entry, "node_modules", "@earendil-works", "pi-coding-agent");
    const manifestPath = resolve(adjacent, "package.json");
    if (!await exists(resolve(adjacent, "dist", "index.js")) || !await exists(manifestPath)) continue;
    const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as { name?: string };
    if (manifest.name === "@earendil-works/pi-coding-agent") return await realpath(adjacent);
  }
  throw new Error("live Pi package root was not discoverable from PATH without npm/user config");
}

function minimalEnvironment(
  isolationRoot: string,
  registryUrl: string,
  parentEnvironment: NodeJS.ProcessEnv,
): NodeJS.ProcessEnv {
  const home = resolve(isolationRoot, "home");
  return {
    ALL_PROXY: "http://127.0.0.1:1",
    APPDATA: resolve(isolationRoot, "appdata"),
    ComSpec: parentEnvironment.ComSpec ?? "",
    GIT_ALLOW_PROTOCOL: "git",
    GIT_CONFIG_GLOBAL: resolve(isolationRoot, "gitconfig"),
    GIT_CONFIG_NOSYSTEM: "1",
    HOME: home,
    HTTPS_PROXY: "http://127.0.0.1:1",
    HTTP_PROXY: "http://127.0.0.1:1",
    NO_PROXY: "127.0.0.1,localhost",
    NPM_CONFIG_AUDIT: "false",
    NPM_CONFIG_CACHE: resolve(isolationRoot, "npm-cache"),
    NPM_CONFIG_FUND: "false",
    NPM_CONFIG_IGNORE_SCRIPTS: "true",
    NPM_CONFIG_OFFLINE: "true",
    NPM_CONFIG_REGISTRY: registryUrl,
    NPM_CONFIG_UPDATE_NOTIFIER: "false",
    NPM_CONFIG_USERCONFIG: resolve(isolationRoot, "npmrc"),
    PATH: parentEnvironment.PATH ?? "",
    SystemRoot: parentEnvironment.SystemRoot ?? "",
    TEMP: resolve(isolationRoot, "temp"),
    TMP: resolve(isolationRoot, "temp"),
    USERPROFILE: home,
    XDG_CONFIG_HOME: resolve(isolationRoot, "xdg"),
  };
}

async function prepareIsolatedEnvironment(
  isolationRoot: string,
  registryUrl: string,
  parentEnvironment: NodeJS.ProcessEnv,
): Promise<NodeJS.ProcessEnv> {
  const environment = minimalEnvironment(isolationRoot, registryUrl, parentEnvironment);
  for (const variable of ["HOME", "APPDATA", "TEMP", "XDG_CONFIG_HOME", "NPM_CONFIG_CACHE"]) {
    await mkdir(environment[variable]!, { recursive: true });
  }
  await writeFile(environment.GIT_CONFIG_GLOBAL!, "", "utf8");
  await writeFile(
    environment.NPM_CONFIG_USERCONFIG!,
    `offline=true\naudit=false\nfund=false\nignore-scripts=true\nupdate-notifier=false\nregistry=${registryUrl}\n`,
    "utf8",
  );
  return environment;
}

async function waitForProcessExit(child: ReturnType<typeof spawn>, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  return await new Promise<boolean>((resolveWait) => {
    const timer = setTimeout(() => {
      child.removeListener("exit", onExit);
      resolveWait(false);
    }, timeoutMs);
    const onExit = () => {
      clearTimeout(timer);
      resolveWait(true);
    };
    child.once("exit", onExit);
  });
}

function pidIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function firstOutputLine(child: ReturnType<typeof spawn>): Promise<string> {
  if (child.stdout === null) throw new Error("child stdout is unavailable");
  return await new Promise<string>((resolveLine, reject) => {
    let buffered = "";
    const timer = setTimeout(() => reject(new Error("child pid was not reported")), 2_000);
    child.stdout!.setEncoding("utf8");
    child.stdout!.on("data", (chunk: string) => {
      buffered += chunk;
      const newline = buffered.indexOf("\n");
      if (newline < 0) return;
      clearTimeout(timer);
      resolveLine(buffered.slice(0, newline).trim());
    });
    child.once("error", reject);
  });
}

async function forceProcessTreeExit(child: ReturnType<typeof spawn>): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (child.pid === undefined) throw new Error("process tree has no root pid");
  if (process.platform === "win32") {
    try {
      execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        encoding: "utf8",
        stdio: "ignore",
        windowsHide: true,
      });
    } catch {
      // taskkill reports failure when the process exits between the liveness check and invocation.
    }
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      // The group may already have exited.
    }
    if (!await waitForProcessExit(child, 300)) {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {
        // The group may already have exited.
      }
    }
  }
  if (!await waitForProcessExit(child, 2_000)) throw new Error(`process tree ${child.pid} did not exit`);
}

async function cleanupProcessTreeAndRoots(
  daemon: ReturnType<typeof spawn>,
  roots: string[],
  options: { forceGracefulFailure?: boolean } = {},
): Promise<void> {
  const errors: unknown[] = [];
  try {
    let stopped = false;
    if (!options.forceGracefulFailure) {
      daemon.kill("SIGTERM");
      stopped = await waitForProcessExit(daemon, 750);
    }
    if (!stopped) await forceProcessTreeExit(daemon);
  } catch (error) {
    errors.push(error);
  }
  for (const root of roots) {
    try {
      await rm(root, { recursive: true, force: true });
    } catch (error) {
      errors.push(error);
    }
  }
  if (errors.length > 0) throw new AggregateError(errors, "process-tree/temp cleanup failed");
}

interface PartialFixtureResources {
  daemon?: ReturnType<typeof spawn>;
  roots: string[];
  server?: ReturnType<typeof createHttpServer>;
}

async function withFixtureCleanupBoundary<T>(
  work: (resources: PartialFixtureResources) => Promise<T>,
): Promise<T> {
  const resources: PartialFixtureResources = { roots: [] };
  try {
    return await work(resources);
  } finally {
    const errors: unknown[] = [];
    const processAndServer: Array<Promise<unknown>> = [];
    if (resources.daemon !== undefined) {
      processAndServer.push(cleanupProcessTreeAndRoots(resources.daemon, []));
    }
    if (resources.server?.listening) {
      processAndServer.push(new Promise<void>((resolveClosed, reject) => {
        resources.server!.close((error) => error ? reject(error) : resolveClosed());
      }));
    }
    for (const settled of await Promise.allSettled(processAndServer)) {
      if (settled.status === "rejected") errors.push(settled.reason);
    }
    const removals = resources.roots.map((root) => rm(root, { recursive: true, force: true }));
    for (const settled of await Promise.allSettled(removals)) {
      if (settled.status === "rejected") errors.push(settled.reason);
    }
    if (errors.length > 0) throw new AggregateError(errors, "partial fixture cleanup failed");
  }
}

async function freeLoopbackPort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((resolveReady, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolveReady());
  });
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("loopback port unavailable");
  await new Promise<void>((resolveClosed, reject) => server.close((error) => error ? reject(error) : resolveClosed()));
  return address.port;
}

async function waitForGitDaemon(port: number): Promise<void> {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    const ready = await new Promise<boolean>((resolveAttempt) => {
      const socket = connect(port, "127.0.0.1");
      socket.once("connect", () => { socket.destroy(); resolveAttempt(true); });
      socket.once("error", () => resolveAttempt(false));
    });
    if (ready) return;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 50));
  }
  throw new Error("local git daemon did not become ready");
}

async function loopbackConnectionSucceeds(port: number): Promise<boolean> {
  return await new Promise<boolean>((resolveAttempt) => {
    const socket = connect(port, "127.0.0.1");
    const finish = (connected: boolean) => {
      socket.destroy();
      resolveAttempt(connected);
    };
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
    socket.setTimeout(1_000, () => finish(false));
  });
}

async function createPinnedGitFixture(root: string, environment: NodeJS.ProcessEnv) {
  const worktree = resolve(root, "worktree");
  const remoteRoot = resolve(root, "remotes");
  const bare = resolve(remoteRoot, "fixture", "ca-pi.git");
  await mkdir(resolve(worktree, "plugins", "ca-pi"), { recursive: true });
  await cp(resolve(pluginRoot, "..", "..", "package.json"), resolve(worktree, "package.json"));
  await cp(resolve(pluginRoot, "package.json"), resolve(worktree, "plugins", "ca-pi", "package.json"));
  await cp(resolve(pluginRoot, "extensions"), resolve(worktree, "plugins", "ca-pi", "extensions"), { recursive: true });
  await cp(resolve(pluginRoot, "generated"), resolve(worktree, "plugins", "ca-pi", "generated"), { recursive: true });
  await cp(resolve(pluginRoot, "skills"), resolve(worktree, "plugins", "ca-pi", "skills"), { recursive: true });
  await cp(resolve(pluginRoot, "ORCHESTRATOR.md"), resolve(worktree, "plugins", "ca-pi", "ORCHESTRATOR.md"));
  const extensionRoot = resolve(worktree, "plugins", "ca-pi", "extensions");
  const poisonRoot = resolve(extensionRoot, "node_modules", "@earendil-works", "pi-coding-agent");
  const wrongRoot = resolve(extensionRoot, "wrong-package");
  const escapeRoot = resolve(extensionRoot, "escape-package");
  const symlinkRoot = resolve(extensionRoot, "symlink-package");
  await mkdir(resolve(poisonRoot, "dist"), { recursive: true });
  await mkdir(resolve(wrongRoot, "dist"), { recursive: true });
  await mkdir(resolve(escapeRoot, "dist"), { recursive: true });
  await writeFile(
    resolve(poisonRoot, "package.json"),
    '{"name":"@earendil-works/pi-coding-agent","version":"0.80.10","type":"module","bin":{"pi":"dist/cli.js"},"exports":{".":{"import":"./dist/index.js"}}}\n',
    "utf8",
  );
  await writeFile(resolve(poisonRoot, "dist", "cli.js"), "// poisoned fake CLI anchor\n", "utf8");
  await writeFile(
    resolve(poisonRoot, "dist", "index.js"),
    'globalThis.__CA_PI_POISON_HOST_EVALUATED__ = true; console.error("COUNTERFEIT_HOST_RUNTIME_EVALUATED"); export class ModelRegistry {} export const VERSION = "0.80.10";\n',
    "utf8",
  );
  await writeFile(
    resolve(extensionRoot, "ordinary-resolution-control.mjs"),
    'import { ModelRegistry } from "@earendil-works/pi-coding-agent"; console.log(ModelRegistry);\n',
    "utf8",
  );
  await writeFile(
    resolve(wrongRoot, "package.json"),
    '{"name":"not-pi","version":"0.80.10","type":"module","bin":{"pi":"dist/cli.js"},"exports":{".":{"import":"./dist/index.js"}}}\n',
    "utf8",
  );
  await writeFile(resolve(wrongRoot, "dist", "cli.js"), "// wrong package CLI\n", "utf8");
  await writeFile(resolve(wrongRoot, "dist", "index.js"), "export class ModelRegistry {} export const VERSION = '0.80.10';\n", "utf8");
  await writeFile(
    resolve(escapeRoot, "package.json"),
    '{"name":"@earendil-works/pi-coding-agent","version":"0.80.10","type":"module","bin":{"pi":"dist/cli.js"},"exports":{".":{"import":"../outside-runtime.js"}}}\n',
    "utf8",
  );
  await writeFile(resolve(escapeRoot, "dist", "cli.js"), "// escaping export CLI\n", "utf8");
  await writeFile(resolve(extensionRoot, "outside-runtime.js"), "export class ModelRegistry {} export const VERSION = '0.80.10';\n", "utf8");
  if (process.platform !== "win32") {
    await mkdir(resolve(symlinkRoot, "dist"), { recursive: true });
    await writeFile(
      resolve(symlinkRoot, "package.json"),
      '{"name":"@earendil-works/pi-coding-agent","version":"0.80.10","type":"module","bin":{"pi":"dist/cli.js"},"exports":{".":{"import":"./dist/index.js"}}}\n',
      "utf8",
    );
    await writeFile(resolve(symlinkRoot, "dist", "cli.js"), "// symlink escape CLI\n", "utf8");
    await symlink("../../outside-runtime.js", resolve(symlinkRoot, "dist", "index.js"));
  }
  const gitEnvironment = {
    ...environment,
    GIT_AUTHOR_DATE: "2000-01-01T00:00:00Z",
    GIT_AUTHOR_EMAIL: "fixture@example.invalid",
    GIT_AUTHOR_NAME: "ca-pi fixture",
    GIT_COMMITTER_DATE: "2000-01-01T00:00:00Z",
    GIT_COMMITTER_EMAIL: "fixture@example.invalid",
    GIT_COMMITTER_NAME: "ca-pi fixture",
  };
  execFileSync("git", ["init", "--quiet"], { cwd: worktree, env: gitEnvironment });
  execFileSync("git", ["add", "--", "package.json", "plugins/ca-pi"], { cwd: worktree, env: gitEnvironment });
  execFileSync("git", ["commit", "--quiet", "-m", "fixture"], { cwd: worktree, env: gitEnvironment });
  const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: worktree, encoding: "utf8", env: gitEnvironment }).trim();
  await mkdir(dirname(bare), { recursive: true });
  execFileSync("git", ["clone", "--quiet", "--bare", worktree, bare], {
    env: { ...gitEnvironment, GIT_ALLOW_PROTOCOL: "file", GIT_PROXY_COMMAND: "" },
  });
  const port = await freeLoopbackPort();
  const gitExecutableDirectory = execFileSync("git", ["--exec-path"], {
    encoding: "utf8",
    env: gitEnvironment,
  }).trim();
  const gitDaemon = resolve(gitExecutableDirectory, process.platform === "win32" ? "git-daemon.exe" : "git-daemon");
  const daemon = spawn(gitDaemon, [
    "--reuseaddr", "--export-all", `--base-path=${remoteRoot}`,
    "--listen=127.0.0.1", `--port=${port}`, remoteRoot,
  ], {
    detached: process.platform !== "win32",
    env: gitEnvironment,
    stdio: "ignore",
    windowsHide: true,
  });
  try {
    await waitForGitDaemon(port);
  } catch (error) {
    await forceProcessTreeExit(daemon);
    throw error;
  }
  return {
    commit,
    daemon,
    port,
    source: `git:git://127.0.0.1:${port}/fixture/ca-pi.git@${commit}`,
  };
}

describe("ca-pi package", () => {
  test.runIf(process.platform === "win32")("real Pi dormant load never executes a project-cwd Python candidate", async () => {
    const projectCwd = await mkdtemp(resolve(tmpdir(), "ca-pi-python-cwd-poison-"));
    const agentDir = await mkdtemp(resolve(tmpdir(), "ca-pi-python-cwd-agent-"));
    try {
      const installedPython = execFileSync(
        "python",
        ["-c", "import sys; print(sys.executable)"],
        { encoding: "utf8", windowsHide: true },
      ).trim();
      const sentinel = resolve(projectCwd, "poison-executed");
      await copyFile(installedPython, resolve(projectCwd, "py.exe"));
      await copyFile(installedPython, resolve(projectCwd, "python.exe"));
      await writeFile(
        resolve(projectCwd, "sitecustomize.py"),
        `from pathlib import Path\nPath(${JSON.stringify(sentinel)}).write_text("executed", encoding="utf-8")\n`,
        "utf8",
      );
      const livePiRoot = await findPiPackageRoot();
      const livePiCli = resolve(livePiRoot, "dist", "cli.js");
      const livePiEntry = resolve(livePiRoot, "dist", "index.js");
      const script = `
        import { pathToFileURL } from "node:url";
        const [entry, extension, cwd, agentDir] = process.argv.slice(2);
        const host = await import(pathToFileURL(entry).href);
        const result = await host.discoverAndLoadExtensions([extension], cwd, agentDir);
        console.log(JSON.stringify({ errors: result.errors }));
      `;
      const output = execFileSync(
        process.execPath,
        ["--input-type=module", "--eval", script, livePiCli, livePiEntry, bundles[0], projectCwd, agentDir],
        { cwd: projectCwd, encoding: "utf8", windowsHide: true },
      );
      const result = JSON.parse(output.trim().split(/\r?\n/u).at(-1) ?? "") as { errors: unknown[] };
      expect(result.errors).toEqual([]);
      await expect(access(sentinel)).rejects.toThrow();
    } finally {
      await rm(projectCwd, { recursive: true, force: true });
      await rm(agentDir, { recursive: true, force: true });
    }
  });

  test("minimal environment replaces poisoned operator homes and configs", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-isolation-red-"));
    const poison = await mkdtemp(resolve(tmpdir(), "ca-pi-poison-red-"));
    try {
      const environment = minimalEnvironment(root, "http://127.0.0.1:9/", {
        PATH: process.env.PATH,
        SystemRoot: process.env.SystemRoot,
        ComSpec: process.env.ComSpec,
        HOME: poison,
        USERPROFILE: poison,
        APPDATA: poison,
      });
      expect(environment.HOME).toBe(resolve(root, "home"));
      expect(environment.USERPROFILE).toBe(resolve(root, "home"));
      expect(environment.APPDATA).toBe(resolve(root, "appdata"));
      expect(environment.GIT_CONFIG_NOSYSTEM).toBe("1");
      expect(environment.NPM_CONFIG_OFFLINE).toBe("true");
      expect(environment.NPM_CONFIG_UPDATE_NOTIFIER).toBe("false");
      expect(environment.NPM_CONFIG_REGISTRY).toBe("http://127.0.0.1:9/");
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(poison, { recursive: true, force: true });
    }
  });

  test("forced process-tree fallback cannot skip independent temp cleanup", async () => {
    const rootA = await mkdtemp(resolve(tmpdir(), "ca-pi-cleanup-a-"));
    const rootB = await mkdtemp(resolve(tmpdir(), "ca-pi-cleanup-b-"));
    const treeScript = `
      const { spawn } = require("node:child_process");
      const child = spawn(process.execPath, ["--eval", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
      console.log(child.pid);
      setInterval(() => {}, 1000);
    `;
    const daemon = spawn(process.execPath, ["--eval", treeScript], {
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "ignore"],
      windowsHide: true,
    });
    const daemonPid = daemon.pid!;
    const childPid = Number(await firstOutputLine(daemon));
    try {
      await cleanupProcessTreeAndRoots(daemon, [rootA, rootB], { forceGracefulFailure: true });
      await expect(access(rootA)).rejects.toThrow();
      await expect(access(rootB)).rejects.toThrow();
      expect(pidIsAlive(daemonPid)).toBe(false);
      expect(pidIsAlive(childPid)).toBe(false);
    } finally {
      if (pidIsAlive(daemonPid)) await forceProcessTreeExit(daemon);
      if (pidIsAlive(childPid)) process.kill(childPid, "SIGKILL");
      await rm(rootA, { recursive: true, force: true });
      await rm(rootB, { recursive: true, force: true });
    }
  });

  test("early identity setup failure closes server and removes every initialized root", async () => {
    let root: string | undefined;
    let server: ReturnType<typeof createHttpServer> | undefined;
    try {
      await expect(withFixtureCleanupBoundary(async (resources) => {
        root = await mkdtemp(resolve(tmpdir(), "ca-pi-early-failure-"));
        resources.roots.push(root);
        server = createHttpServer();
        resources.server = server;
        await new Promise<void>((resolveReady, reject) => {
          server!.once("error", reject);
          server!.listen(0, "127.0.0.1", resolveReady);
        });
        throw new Error("forced early setup failure");
      })).rejects.toThrow("forced early setup failure");
      await expect(access(root!)).rejects.toThrow();
      expect(server!.listening).toBe(false);
    } finally {
      if (server?.listening) await new Promise<void>((resolveClosed) => server!.close(() => resolveClosed()));
      if (root !== undefined) await rm(root, { recursive: true, force: true });
    }
  });

  test("loads the reviewed native binding only on supported platforms", async () => {
    expect(process.env.NAPI_RS_FORCE_WASI).toBeUndefined();
    expect(["win32", "darwin", "linux"]).toContain(process.platform);
    const rolldown = await import("rolldown");
    expect(typeof rolldown.build).toBe("function");
  });

  test("bundles contain no bare runtime import or copied Pi source", async () => {
    for (const [index, bundle] of [...bundles, windowsSupervisor].entries()) {
      const text = await readFile(bundle, "utf8");
      expect(text).not.toMatch(/from\s+["']@earendil-works\/pi-coding-agent["']/u);
      expect(text).not.toContain("class AgentSession");
      expect(text).not.toContain("class ExtensionRunner");
      expect(text).not.toContain("sourceMappingURL");
      if (index === 0) expect(text).toContain("@earendil-works/pi-coding-agent");
    }
  });

  test("keeps the rich footer and its bridge events out of the hardened child inventory", async () => {
    const child = await readFile(resolve(pluginRoot, "extensions", "codearbiter-child.js"), "utf8");
    const childSource = await readFile(resolve(toolsRoot, "src", "child-extension.ts"), "utf8");
    for (const forbidden of [
      "PiFooterLifecycle",
      "setFooter",
      "footer_usage_update",
      "footer_status_snapshot",
      "codeArbiter footer unavailable",
      "codearbiter_background_bash",
      "ca-jobs",
      "createBackgroundJobRuntime",
    ]) {
      expect(child).not.toContain(forbidden);
      expect(childSource).not.toContain(forbidden);
    }
    expect(childSource).not.toMatch(/from\s+["']\.\/(?:footer|footer-state|status)\.ts["']/u);
  });

  test("loads footer metrics lazily from the validated runtime-owned Pi TUI package and rejects a counterfeit owner", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-metrics-"));
    try {
      const runtimeRoot = resolve(root, "pi");
      const moduleEntry = resolve(runtimeRoot, "dist", "index.js");
      const tuiRoot = resolve(runtimeRoot, "node_modules", "@earendil-works", "pi-tui");
      await mkdir(resolve(runtimeRoot, "dist"), { recursive: true });
      await mkdir(resolve(tuiRoot, "dist"), { recursive: true });
      await writeFile(moduleEntry, "export {};\n", "utf8");
      await writeFile(resolve(runtimeRoot, "package.json"), JSON.stringify({
        name: "@earendil-works/pi-coding-agent", type: "module",
      }) + "\n", "utf8");
      await writeFile(resolve(tuiRoot, "package.json"), JSON.stringify({
        name: "@earendil-works/pi-tui", type: "module", exports: "./dist/index.js",
      }) + "\n", "utf8");
      await writeFile(
        resolve(tuiRoot, "dist", "index.js"),
        "export const visibleWidth = (text) => text.length; export const truncateToWidth = (text, width) => text.slice(0, width);\n",
        "utf8",
      );

      const load = createPiFooterMetricsLoader({ moduleEntry, packageRoot: runtimeRoot });
      const metrics = await load();
      expect(metrics.visibleWidth("abc")).toBe(3);
      expect(metrics.truncateToWidth("abcd", 2, "")).toBe("ab");

      await writeFile(resolve(tuiRoot, "package.json"), JSON.stringify({
        name: "counterfeit-tui", type: "module", exports: "./dist/index.js",
      }) + "\n", "utf8");
      await expect(createPiFooterMetricsLoader({ moduleEntry, packageRoot: runtimeRoot })()).rejects.toThrow(
        "Pi terminal width support",
      );
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rejects a Pi TUI package root linked outside the canonical runtime package", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-footer-metrics-escape-"));
    try {
      const runtimeRoot = resolve(root, "pi");
      const moduleEntry = resolve(runtimeRoot, "dist", "index.js");
      const ownerParent = resolve(runtimeRoot, "node_modules", "@earendil-works");
      const linkedRoot = resolve(ownerParent, "pi-tui");
      const outsideRoot = resolve(root, "outside-tui");
      await mkdir(resolve(runtimeRoot, "dist"), { recursive: true });
      await mkdir(resolve(outsideRoot, "dist"), { recursive: true });
      await mkdir(ownerParent, { recursive: true });
      await writeFile(moduleEntry, "export {};\n", "utf8");
      await writeFile(resolve(runtimeRoot, "package.json"), JSON.stringify({
        name: "@earendil-works/pi-coding-agent", type: "module",
      }) + "\n", "utf8");
      await writeFile(resolve(outsideRoot, "package.json"), JSON.stringify({
        name: "@earendil-works/pi-tui", type: "module", exports: "./dist/index.js",
      }) + "\n", "utf8");
      await writeFile(
        resolve(outsideRoot, "dist", "index.js"),
        "export const visibleWidth = (text) => text.length; export const truncateToWidth = (text, width) => text.slice(0, width);\n",
        "utf8",
      );
      await symlink(outsideRoot, linkedRoot, process.platform === "win32" ? "junction" : "dir");

      await expect(createPiFooterMetricsLoader({ moduleEntry, packageRoot: runtimeRoot })()).rejects.toThrow(
        "Pi terminal width support",
      );
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("ships one UTF-8 Windows supervisor and keeps its stale-build gate coupled to source", async () => {
    const helpers = resolve(pluginRoot, "helpers");
    await expect((await import("node:fs/promises")).readdir(helpers)).resolves.toEqual(["windows-supervisor.js"]);
    const bytes = await readFile(windowsSupervisor);
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    expect(text).toContain("STARTED");
    expect(text).not.toContain("FINAL_RECORD");
    const buildSource = await readFile(resolve(toolsRoot, "build.mjs"), "utf8");
    expect(buildSource).toContain('entryPoints: ["src/windows-supervisor.ts"]');
    expect(buildSource).toContain('outfile: "../helpers/windows-supervisor.js"');
    const workflow = await readFile(resolve(pluginRoot, "..", "..", ".github", "workflows", "ci.yml"), "utf8");
    expect(workflow).toContain("git diff --quiet -- plugins/ca-pi/extensions plugins/ca-pi/helpers");
    expect(workflow).toContain("git --no-pager diff -- plugins/ca-pi/extensions plugins/ca-pi/helpers");
  });

  test("real Pi loader rejects ordinary duplicate-host resolution and stays offline/auth-isolated", async () => {
    const execution = await withFixtureCleanupBoundary(async (resources) => {
      const agentDir = await mkdtemp(resolve(tmpdir(), "ca-pi-agent-"));
      resources.roots.push(agentDir);
      const fixtureRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-git-"));
      resources.roots.push(fixtureRoot);
      const isolationRoot = await mkdtemp(resolve(tmpdir(), "ca-pi-isolated-home-"));
      resources.roots.push(isolationRoot);
      const poisonHome = await mkdtemp(resolve(tmpdir(), "ca-pi-poison-home-"));
      resources.roots.push(poisonHome);
      const poisonedRepository = await mkdtemp(resolve(tmpdir(), "ca-pi-poison-repo-"));
      resources.roots.push(poisonedRepository);
      const cleanProjectCwd = resolve(isolationRoot, "project");
      await mkdir(cleanProjectCwd, { recursive: true });
      const localConfigSentinel = resolve(isolationRoot, "repo-local-config-observed");
      const gitProxyHelper = resolve(poisonedRepository, "git-proxy-helper.cjs");
      await writeFile(
        gitProxyHelper,
        `require("node:fs").writeFileSync(${JSON.stringify(localConfigSentinel)}, "GIT_PROXY_SENTINEL_INVOKED\\n"); process.exit(73);\n`,
        "utf8",
      );
      const registryRequests: Array<{ method: string | undefined; url: string | undefined; authorization: boolean }> = [];
      const registry = createHttpServer((request, response) => {
        registryRequests.push({
          method: request.method,
          url: request.url,
          authorization: request.headers.authorization !== undefined,
        });
        response.writeHead(500);
        response.end("registry access forbidden");
      });
      resources.server = registry;
      await new Promise<void>((resolveReady, reject) => {
        registry.once("error", reject);
        registry.listen(0, "127.0.0.1", resolveReady);
      });
      const registryAddress = registry.address();
      if (registryAddress === null || typeof registryAddress === "string") throw new Error("registry trap unavailable");
      const registryUrl = `http://127.0.0.1:${registryAddress.port}/`;
      await writeFile(
        resolve(poisonHome, ".gitconfig"),
        '[url "git://sentinel.invalid/"]\n\tinsteadOf = git://127.0.0.1:\n',
        "utf8",
      );
      await writeFile(
        resolve(poisonHome, ".npmrc"),
        "registry=https://sentinel.invalid/\nalways-auth=true\n//sentinel.invalid/:_authToken=POISON_SENTINEL\n",
        "utf8",
      );
      const syntheticParent = {
        APPDATA: poisonHome,
        ComSpec: process.env.ComSpec,
        HOME: poisonHome,
        PATH: process.env.PATH,
        SystemRoot: process.env.SystemRoot,
        USERPROFILE: poisonHome,
        GIT_ALTERNATE_OBJECT_DIRECTORIES: resolve(poisonHome, "alternate-objects"),
        GIT_COMMON_DIR: resolve(poisonHome, "common-git-dir"),
        GIT_DIR: resolve(poisonHome, "ambient-git-dir"),
        GIT_INDEX_FILE: resolve(poisonHome, "ambient-index"),
        GIT_OBJECT_DIRECTORY: resolve(poisonHome, "ambient-objects"),
        GIT_WORK_TREE: resolve(poisonHome, "ambient-work-tree"),
      };
      const environment = await prepareIsolatedEnvironment(isolationRoot, registryUrl, syntheticParent);
      for (const variable of [
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
      ]) {
        expect(environment[variable]).toBeUndefined();
      }
      const livePiRoot = await findPiPackageRoot();
      const livePiEntry = resolve(livePiRoot, "dist", "index.js");
      const livePiCli = resolve(livePiRoot, "dist", "cli.js");
      const script = `
      import { execFileSync, spawnSync } from "node:child_process";
      import { existsSync } from "node:fs";
      import { dirname, relative } from "node:path";
      import { fileURLToPath, pathToFileURL } from "node:url";
      const [cliAnchor, entry, cwd, source, agentDir] = process.argv.slice(1);
      const localConfigProbe = spawnSync("git", ["config", "--local", "--get-regexp", ".*"], {
        cwd,
        encoding: "utf8",
        env: process.env,
      });
      const host = await import(pathToFileURL(entry).href);
      const settings = host.SettingsManager.inMemory({
        packages: [source],
        npmCommand: ["npm", "--offline", "--no-audit", "--no-fund", "--ignore-scripts", "--update-notifier=false"],
      }, { projectTrusted: true });
      const manager = new host.DefaultPackageManager({ cwd, agentDir, settingsManager: settings });
      const resolved = await manager.resolve(async () => "install");
      const discoveredExtensions = resolved.extensions.filter((item) => item.enabled).map((item) => item.path);
      const discoveredSkills = resolved.skills.filter((item) => item.enabled).map((item) => item.path);
      const controlScript = \`
        import { pathToFileURL } from "node:url";
        try {
          await import(pathToFileURL(process.argv[1]).href);
          process.exit(0);
        } catch (error) {
          console.error(error instanceof Error ? error.message : String(error));
          process.exit(42);
        }
      \`;
      const ordinaryControl = fileURLToPath(new URL("./ordinary-resolution-control.mjs", pathToFileURL(discoveredExtensions[0])));
      const ordinary = spawnSync(process.execPath, ["--input-type=module", "--eval", controlScript, ordinaryControl], {
        encoding: "utf8",
        env: process.env,
      });
      const child = fileURLToPath(new URL("./codearbiter-child.js", pathToFileURL(discoveredExtensions[0])));
      const result = await host.discoverAndLoadExtensions([...discoveredExtensions, child], cwd, agentDir);
      const poisonEvaluatedByRealLoader = globalThis.__CA_PI_POISON_HOST_EVALUATED__ === true;
      const shipped = await import(pathToFileURL(discoveredExtensions[0]).href);
      const resolvedRuntime = await shipped.resolvePiRuntime(cliAnchor);
      const compatibility = [];
      for (const input of [
        { piVersion: "0.80.5", nodeVersion: "22.19.0", pythonMajor: 3 },
        { piVersion: "0.80.10", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.4", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.7", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.81.0", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.10-rc.1", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.10+build.1", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "v0.80.10", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: " 0.80.10", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.10 ", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "not-a-version", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "1.0.0", nodeVersion: "24.16.0", pythonMajor: 3 },
        { piVersion: "0.80.10", nodeVersion: "22.18.0", pythonMajor: 3 },
        { piVersion: "0.80.10", nodeVersion: "24.16.0", pythonMajor: null },
      ]) {
        let apiAccesses = 0;
        const api = new Proxy({}, { get() { apiAccesses += 1; return () => undefined; } });
        let diagnosis = null;
        try {
          await shipped.createCodeArbiterPi(input)(api);
        } catch (error) {
          diagnosis = error instanceof Error ? error.message : String(error);
        }
        compatibility.push({ diagnosis, apiAccesses });
      }
      const fakeCli = fileURLToPath(new URL("./node_modules/@earendil-works/pi-coding-agent/dist/cli.js", pathToFileURL(discoveredExtensions[0])));
      const wrongCli = fileURLToPath(new URL("./wrong-package/dist/cli.js", pathToFileURL(discoveredExtensions[0])));
      const escapeCli = fileURLToPath(new URL("./escape-package/dist/cli.js", pathToFileURL(discoveredExtensions[0])));
      const symlinkCli = fileURLToPath(new URL("./symlink-package/dist/cli.js", pathToFileURL(discoveredExtensions[0])));
      const negativeDiagnoses = [];
      const negativeAnchors = [discoveredExtensions[0], entry, fakeCli, wrongCli, escapeCli];
      if (existsSync(symlinkCli)) negativeAnchors.push(symlinkCli);
      for (const anchor of negativeAnchors) {
        try {
          await shipped.resolvePiRuntime(anchor);
          negativeDiagnoses.push(null);
        } catch (error) {
          negativeDiagnoses.push(error instanceof Error ? error.message : String(error));
        }
      }
      const activeCounterfeitScript = \`
        import { pathToFileURL } from "node:url";
        const shipped = await import(pathToFileURL(process.argv[2]).href);
        try {
          await shipped.resolvePiRuntime();
          process.exit(0);
        } catch (error) {
          console.error(error instanceof Error ? error.message : String(error));
          process.exit(43);
        }
      \`;
      const activeCounterfeits = [fakeCli, wrongCli].map((anchor) => spawnSync(
          process.execPath,
          ["--input-type=module", "--eval", activeCounterfeitScript, anchor, discoveredExtensions[0]],
          { encoding: "utf8", env: process.env },
        ));
      const installedCommit = execFileSync("git", ["rev-parse", "HEAD"], {
        cwd: dirname(dirname(dirname(dirname(discoveredExtensions[0])))),
        encoding: "utf8",
      }).trim();
      const registrations = result.extensions.map((extension) =>
        [extension.handlers, extension.tools, extension.commands, extension.flags, extension.shortcuts]
          .reduce((total, value) => total + value.size, 0));
      console.log(JSON.stringify({
        errors: result.errors,
        count: result.extensions.length,
        registrations,
        discoveredExtensions,
        skillCount: discoveredSkills.length,
        ordinaryPoisonStatus: ordinary.status,
        ordinaryPoisonObserved: \`\${ordinary.stdout ?? ""} \${ordinary.stderr ?? ""}\`.includes("POISON_HOST_RUNTIME_EVALUATED"),
        ordinaryCounterfeitObserved: \`\${ordinary.stdout ?? ""} \${ordinary.stderr ?? ""}\`.includes("COUNTERFEIT_HOST_RUNTIME_EVALUATED"),
        poisonEvaluatedByRealLoader,
        strictIdentity: resolvedRuntime.ModelRegistry === host.ModelRegistry,
        canonicalModuleInsideRoot: relative(resolvedRuntime.packageRoot, resolvedRuntime.moduleEntry).split(/[\\/]/u)[0] !== "..",
        cliAndModuleSharePackageRoot: resolvedRuntime.cliEntry.startsWith(resolvedRuntime.packageRoot) && resolvedRuntime.moduleEntry.startsWith(resolvedRuntime.packageRoot),
        negativeDiagnoses,
        activeCounterfeitStatuses: activeCounterfeits.map((control) => control.status),
        activeCounterfeitDiagnoses: activeCounterfeits.map(
          (control) => \`\${control.stdout ?? ""} \${control.stderr ?? ""}\`.trim(),
        ),
        compatibility,
        installedCommit,
        packageSource: source,
        localConfigStatus: localConfigProbe.status,
        localConfigOutput: \`\${localConfigProbe.stdout ?? ""} \${localConfigProbe.stderr ?? ""}\`,
      }));
    `;
      const fixture = await createPinnedGitFixture(fixtureRoot, environment);
      resources.daemon = fixture.daemon;
      execFileSync("git", ["init", "--quiet"], { cwd: poisonedRepository, env: environment });
      const escapedProxyHelper = gitProxyHelper.replaceAll("\\", "/");
      await writeFile(
        resolve(poisonedRepository, ".git", "config"),
        `[core]\n\trepositoryformatversion = 0\n\tbare = false\n\tgitProxy = node "${escapedProxyHelper}"\n[url "git://127.0.0.1:1/REPO_LOCAL_REDIRECT_SENTINEL/"]\n\tinsteadOf = git://127.0.0.1:${fixture.port}/\n[http]\n\tproxy = http://127.0.0.1:1/REPO_LOCAL_PROXY_SENTINEL\n[credential]\n\thelper = !node "${escapedProxyHelper}"\n`,
        "utf8",
      );
      const output = execFileSync(
        process.execPath,
        ["--input-type=module", "--eval", script, livePiCli, livePiEntry, cleanProjectCwd, fixture.source, agentDir],
        {
          cwd: cleanProjectCwd,
          encoding: "utf8",
          env: {
            ...environment,
            PI_CODING_AGENT_DIR: agentDir,
            PI_TELEMETRY: "0",
          },
        },
      );
      const result = JSON.parse(output.trim().split(/\r?\n/).at(-1) ?? "") as {
        errors: unknown[];
        count: number;
        registrations: number[];
        discoveredExtensions: string[];
        skillCount: number;
        ordinaryPoisonStatus: number | null;
        ordinaryPoisonObserved: boolean;
        ordinaryCounterfeitObserved: boolean;
        poisonEvaluatedByRealLoader: boolean;
        strictIdentity: boolean;
        canonicalModuleInsideRoot: boolean;
        cliAndModuleSharePackageRoot: boolean;
        negativeDiagnoses: Array<string | null>;
        activeCounterfeitStatuses: Array<number | null>;
        activeCounterfeitDiagnoses: string[];
        compatibility: Array<{ diagnosis: string | null; apiAccesses: number }>;
        packageSource: string;
        installedCommit: string;
        localConfigStatus: number | null;
        localConfigOutput: string;
      };
      return {
        cleanProjectIsRepository: await exists(resolve(cleanProjectCwd, ".git")),
        daemonPort: fixture.port,
        environment,
        fixtureCommit: fixture.commit,
        localConfigSentinelObserved: await exists(localConfigSentinel),
        poisonHome,
        registryRequests,
        result,
      };
    });
    const {
      cleanProjectIsRepository,
      daemonPort,
      environment,
      fixtureCommit,
      localConfigSentinelObserved,
      poisonHome,
      registryRequests,
      result,
    } = execution;
      expect(await loopbackConnectionSucceeds(daemonPort)).toBe(false);
      expect(result.errors).toEqual([
        expect.objectContaining({
          error: "Failed to load extension: codeArbiter child handshake has no validated subagent marker; child remains blocked; run /ca-doctor.",
          path: expect.stringMatching(/plugins[\\/]ca-pi[\\/]extensions[\\/]codearbiter-child\.js$/u),
        }),
      ]);
      expect(result.count).toBe(1);
      const commandCount = JSON.parse(
        await readFile(resolve(pluginRoot, "generated", "command-catalog.json"), "utf8"),
      ).length as number;
      // Five parent lifecycle handlers, two tool-enforcement handlers,
      // Pi-native before/after compaction handlers, and the farm-preview tool
      // accompany the aliases.
      expect(result.registrations).toEqual([commandCount + 10]);
      expect(result.discoveredExtensions).toHaveLength(1);
      expect(result.discoveredExtensions[0].replaceAll("\\", "/")).toMatch(/\/plugins\/ca-pi\/extensions\/codearbiter\.js$/u);
      expect(result.skillCount).toBeGreaterThan(0);
      expect(result.ordinaryPoisonStatus).toBe(0);
      expect(result.ordinaryPoisonObserved).toBe(false);
      expect(result.ordinaryCounterfeitObserved).toBe(true);
      expect(result.poisonEvaluatedByRealLoader).toBe(false);
      expect(result.strictIdentity).toBe(true);
      expect(result.canonicalModuleInsideRoot).toBe(true);
      expect(result.cliAndModuleSharePackageRoot).toBe(true);
      expect(result.negativeDiagnoses).toHaveLength(process.platform === "win32" ? 5 : 6);
      expect(new Set(result.negativeDiagnoses)).toEqual(new Set([
        "codeArbiter could not validate the active Pi CLI runtime; start from the Pi CLI and run /ca-doctor.",
      ]));
      expect(result.activeCounterfeitStatuses).toEqual([43, 43]);
      for (const diagnosis of result.activeCounterfeitDiagnoses) {
        expect(diagnosis).toContain(
          "codeArbiter could not validate the active Pi CLI runtime; start from the Pi CLI and run /ca-doctor.",
        );
      }
      expect(result.compatibility).toEqual([
        { diagnosis: null, apiAccesses: 0 },
        { diagnosis: null, apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Node >=22.19.0 for Pi; upgrade Node and run /ca-doctor.", apiAccesses: 0 },
        { diagnosis: "codeArbiter requires Python 3; install Python 3 and run /ca-doctor.", apiAccesses: 0 },
      ]);
      expect(result.packageSource).toMatch(/^git:git:\/\/127\.0\.0\.1:\d+\/fixture\/ca-pi\.git@[0-9a-f]{40}$/u);
      expect(result.installedCommit).toBe(fixtureCommit);
      expect(result.localConfigStatus).not.toBe(0);
      expect(result.localConfigOutput).not.toMatch(/REPO_LOCAL_(?:REDIRECT|PROXY)_SENTINEL/u);
      expect(localConfigSentinelObserved).toBe(false);
      expect(cleanProjectIsRepository).toBe(false);
      expect(registryRequests).toEqual([]);
      expect(environment.HOME).not.toBe(poisonHome);
      expect(environment.APPDATA).not.toBe(poisonHome);
      expect(environment.USERPROFILE).not.toBe(poisonHome);
  }, LIVE_DUPLICATE_HOST_TIMEOUT_MS);

  test("exact supported Pi versions and prerequisites return fixed directions", () => {
    for (const piVersion of ["0.80.5", "0.80.10"]) {
      expect(compatibilityDirection({ piVersion, nodeVersion: "24.16.0", pythonMajor: 3 })).toBeNull();
    }
    const unsupportedDirection =
      "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.";
    for (const piVersion of [
      "0.80.4",
      "0.80.7",
      "0.81.0",
      "0.80.10-rc.1",
      "0.80.10+build.1",
      "v0.80.10",
      " 0.80.10",
      "0.80.10 ",
      "0.80",
      "0.80.10.0",
      "not-a-version",
      "1.0.0",
    ]) {
      expect(compatibilityDirection({ piVersion, nodeVersion: "24.16.0", pythonMajor: 3 })).toBe(
        unsupportedDirection,
      );
    }
    expect(compatibilityDirection({ piVersion: "0.80.10", nodeVersion: "22.18.0", pythonMajor: 3 })).toBe(
      "codeArbiter requires Node >=22.19.0 for Pi; upgrade Node and run /ca-doctor.",
    );
    expect(compatibilityDirection({ piVersion: "0.80.10", nodeVersion: "24.16.0", pythonMajor: null })).toBe(
      "codeArbiter requires Python 3; install Python 3 and run /ca-doctor.",
    );
  });

  test("a malformed Node version is never treated as satisfying the minimum floor", () => {
    // "22.19.0next" is not a valid semver: doctor.ts's anchored parse (/^(\d+)\.(\d+)\.(\d+)(?:$|[-+])/u)
    // requires the three numeric groups to be followed by end-of-string or a prerelease/build separator,
    // so it refuses to parse this and treats the version as below the floor. compatibility.ts's atLeast()
    // must use the same anchored parse rather than the looser /^(\d+)\.(\d+)\.(\d+)/u, which would greedily
    // match the "22.19.0" prefix and wrongly report the malformed/unparseable version as compatible.
    expect(compatibilityDirection({ piVersion: "0.80.10", nodeVersion: "22.19.0next", pythonMajor: 3 })).toBe(
      "codeArbiter requires Node >=22.19.0 for Pi; upgrade Node and run /ca-doctor.",
    );
  });

  test.each(["0.80.7", "0.80.10-rc.1", "1.0.0"])(
    "rejects unsupported Pi %s before API access",
    (piVersion) => {
      let apiAccesses = 0;
      const api = new Proxy({}, { get: () => { apiAccesses += 1; return undefined; } });
      expect(() => createCodeArbiterPi({
        piVersion,
        nodeVersion: "24.16.0",
        pythonMajor: 3,
      })(api as never)).toThrow(
        "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.",
      );
      expect(apiAccesses).toBe(0);
    },
  );

  test("shipped default rejects unsupported Pi before runtime module evaluation", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-unsupported-runtime-"));
    const packageRoot = resolve(root, "pi");
    const cliEntry = resolve(packageRoot, "dist", "cli.js");
    const moduleEntry = resolve(packageRoot, "dist", "index.js");
    const sentinelName = "__CA_PI_UNSUPPORTED_RUNTIME_EVALUATED__";
    const previousArgv1 = process.argv[1];
    try {
      await mkdir(resolve(packageRoot, "dist"), { recursive: true });
      await writeFile(
        resolve(packageRoot, "package.json"),
        '{"name":"@earendil-works/pi-coding-agent","version":"0.80.7","type":"module","bin":{"pi":"dist/cli.js"},"exports":{".":{"import":"./dist/index.js"}}}\n',
        "utf8",
      );
      await writeFile(cliEntry, "// unsupported Pi CLI anchor\n", "utf8");
      await writeFile(
        moduleEntry,
        `globalThis.${sentinelName} = true; throw new Error("unsupported runtime API evaluated");\n`,
        "utf8",
      );
      delete (globalThis as Record<string, unknown>)[sentinelName];
      process.argv[1] = cliEntry;
      let apiAccesses = 0;
      const api = new Proxy({}, { get: () => { apiAccesses += 1; return undefined; } });
      const shipped = await import(pathToFileURL(bundles[0]).href) as { default: (pi: unknown) => Promise<void> };
      let diagnosis: string | null = null;
      try {
        await shipped.default(api);
      } catch (error) {
        diagnosis = error instanceof Error ? error.message : String(error);
      }
      expect({
        apiAccesses,
        diagnosis,
        moduleEvaluated: (globalThis as Record<string, unknown>)[sentinelName] === true,
      }).toEqual({
        apiAccesses: 0,
        diagnosis: "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.",
        moduleEvaluated: false,
      });
    } finally {
      process.argv[1] = previousArgv1;
      delete (globalThis as Record<string, unknown>)[sentinelName];
      await rm(root, { recursive: true, force: true });
    }
  });

  test("installed Pi discovery ignores an adjacent package without a Pi executable", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "ca-pi-path-authenticity-"));
    const staleBin = resolve(root, "stale-bin");
    const actualBin = resolve(root, "actual-bin");
    const adjacentPackage = (entry: string) =>
      resolve(entry, "node_modules", "@earendil-works", "pi-coding-agent");
    const stalePackage = adjacentPackage(staleBin);
    const actualPackage = adjacentPackage(actualBin);
    const executableName = process.platform === "win32" ? "pi.cmd" : "pi";
    const previousPath = process.env.PATH;
    try {
      for (const [packageRoot, version] of [[stalePackage, "0.80.5"], [actualPackage, "0.80.10"]]) {
        await mkdir(resolve(packageRoot, "dist"), { recursive: true });
        await writeFile(
          resolve(packageRoot, "package.json"),
          `${JSON.stringify({ name: "@earendil-works/pi-coding-agent", version })}\n`,
          "utf8",
        );
        await writeFile(resolve(packageRoot, "dist", "index.js"), "export {};\n", "utf8");
      }
      await mkdir(actualBin, { recursive: true });
      const executable = resolve(actualBin, executableName);
      await writeFile(executable, process.platform === "win32" ? "@echo off\r\n" : "#!/bin/sh\n", "utf8");
      await chmod(executable, 0o755);
      process.env.PATH = [staleBin, actualBin].join(delimiter);
      expect(await realpath(await findPiPackageRoot())).toBe(await realpath(actualPackage));
    } finally {
      if (previousPath === undefined) delete process.env.PATH;
      else process.env.PATH = previousPath;
      await rm(root, { recursive: true, force: true });
    }
  });

  test("installed Pi runtime is admitted by the production boundary", async () => {
    const piRoot = await findPiPackageRoot();
    const manifest = JSON.parse(await readFile(resolve(piRoot, "package.json"), "utf8")) as { version?: unknown };
    if (typeof manifest.version !== "string") throw new Error("installed Pi manifest has no version");
    let apiAccesses = 0;
    const api = new Proxy({}, { get: () => { apiAccesses += 1; return undefined; } });
    createCodeArbiterPi({
      piVersion: manifest.version,
      nodeVersion: process.versions.node,
      pythonMajor: 3,
    })(api as never);
    expect(apiAccesses).toBe(0);
  });

});
