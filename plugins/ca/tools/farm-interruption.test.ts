/** Real Git/Farm interruption at an acknowledged merge effect; no provider/Docker. */
import { expect, it, vi } from "vitest";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const tools = fileURLToPath(new URL(".", import.meta.url));
const loader = pathToFileURL(createRequire(import.meta.url).resolve("tsx")).href;
type Result = { code: number | null; signal: NodeJS.Signals | null; out: string };
type Launch = { child: ChildProcess; result: Promise<Result>; output: () => string };
type HookAck = { pid: number; hookParentPid: number; head: string };

const runtimeKeys = ["PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"];
const farmKeys = new Set(["FARM_RUN_ID", "FARM_MUTATION", "FARM_SAMPLES", "FARM_CONCURRENCY", "FARM_API_MAX_RETRIES", "FARM_API_KEY"]);

function environment(home: string, extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const canonical of runtimeKeys) {
    const entry = Object.entries(process.env).find(([key]) => key.toUpperCase() === canonical.toUpperCase());
    if (entry?.[1] !== undefined) env[canonical] = entry[1];
  }
  for (const [key, value] of Object.entries(extra)) if (farmKeys.has(key)) env[key] = value;
  const drive = process.platform === "win32" ? path.parse(home).root.replace(/[\\/]$/, "") : "";
  return { ...env, HOME: home, USERPROFILE: home, HOMEDRIVE: drive,
    HOMEPATH: process.platform === "win32" ? home.slice(drive.length) : home,
    APPDATA: path.join(home, "AppData/Roaming"), LOCALAPPDATA: path.join(home, "AppData/Local"),
    XDG_CONFIG_HOME: path.join(home, ".config"), XDG_CACHE_HOME: path.join(home, ".cache"),
    GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: process.platform === "win32" ? "NUL" : "/dev/null",
    GIT_CONFIG_COUNT: "1", GIT_CONFIG_KEY_0: "commit.gpgsign", GIT_CONFIG_VALUE_0: "false" };
}

it("FARM interruption fixture excludes unrelated credential markers and inherited home aliases", async () => {
  const marker = "PrivateFixtureValue-inert-parent-marker";
  const home = realpathSync(mkdtempSync(path.join(tmpdir(), "farm-environment-control-")));
  for (const key of ["UNRELATED_PROVIDER_CREDENTIAL", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "FARM_API_KEY", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"])
    vi.stubEnv(key, marker);
  try {
    const env = environment(home, { FARM_API_KEY: "fixture-key", GH_TOKEN: marker });
    // Check before any child launch; the RED never transports parent secrets.
    expect(Object.values(env).some(value => value?.includes(marker))).toBe(false);
    expect(env.HOME === home && env.USERPROFILE === home && env.HOMEDRIVE! + env.HOMEPATH === home).toBe(true);
    const summary = JSON.parse(execFileSync(process.execPath, ["-e", `const e=process.env,h=process.argv[1];console.log(JSON.stringify({unrelatedAbsent:!('UNRELATED_PROVIDER_CREDENTIAL'in e)&&!('GH_TOKEN'in e)&&!('AWS_SECRET_ACCESS_KEY'in e),ownedHome:e.HOME===h&&e.USERPROFILE===h&&e.HOMEDRIVE+e.HOMEPATH===h,inertSettingPresent:e.FARM_API_KEY==='fixture-key'}));`, home], { env, encoding: "utf8", timeout: 5_000 }));
    expect(summary).toEqual({ unrelatedAbsent: true, ownedHome: true, inertSettingPresent: true });
  } finally {
    vi.unstubAllEnvs();
    if (path.dirname(home) !== realpathSync(tmpdir())) throw new Error("retain unexpected fixture environment root");
    rmSync(home, { recursive: true, force: true });
  }
});

function launch(repo: string, home: string, entry: "source" | "bundle", args: string[], env: NodeJS.ProcessEnv = {}): Launch {
  const child = spawn(process.execPath, [...(entry === "source" ? ["--import", loader, path.join(tools, "farm.ts")] : [path.join(tools, "farm.js")]), ...args],
    { cwd: repo, env: environment(home, env), stdio: ["ignore", "pipe", "pipe"] });
  let out = "";
  child.stdout.on("data", (b: Buffer) => { out += b; });
  child.stderr.on("data", (b: Buffer) => { out += b; });
  const result = new Promise<Result>((resolve, reject) => {
    child.once("error", reject);
    child.once("close", (code, signal) => resolve({ code, signal, out }));
  });
  return { child, result, output: () => out };
}

async function until<T>(read: () => T | undefined, detail: () => string, milliseconds = 15_000): Promise<T> {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    const result = read();
    if (result !== undefined) return result;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`owned interruption fixture did not reach its bounded observation: ${detail()}`);
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    // A killed orphan can remain a zombie until init reaps it. It has no live
    // execution or open cwd, and cannot mutate the retained fixture.
    if (process.platform === "linux") {
      try { if (/^\d+ \(.*\) Z /.test(readFileSync(`/proc/${pid}/stat`, "utf8"))) return false; } catch { /* recheck signal result below */ }
    }
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

type MetadataState = { kind: "present"; bytes: string } | { kind: "absent" };
function observeMetadata(file: string): MetadataState {
  try { return { kind: "present", bytes: readFileSync(file).toString("hex") }; }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { kind: "absent" };
    throw error;
  }
}

it("Farm interruption metadata observation distinguishes real absence, retained bytes and read failure", () => {
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), "farm-metadata-observation-")));
  try {
    expect(observeMetadata(path.join(root, "missing"))).toEqual({ kind: "absent" });
    const present = path.join(root, "MERGE_HEAD");
    writeFileSync(present, "owned candidate identity\n");
    expect(observeMetadata(present)).toEqual({ kind: "present", bytes: Buffer.from("owned candidate identity\n").toString("hex") });
    const unreadable = path.join(root, "directory"); mkdirSync(unreadable);
    expect(() => observeMetadata(unreadable)).toThrow();
  } finally {
    if (path.dirname(root) !== realpathSync(tmpdir())) throw new Error("retain unexpected metadata fixture root");
    rmSync(root, { recursive: true, force: true });
  }
});

function originalFiles(root: string): Record<string, string> {
  const result: Record<string, string> = {};
  function walk(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(file);
      else if (!/^farm-recovered-[a-f0-9]+\.json$/.test(entry.name))
        result[path.relative(root, file)] = createHash("sha256").update(readFileSync(file)).digest("hex");
    }
  }
  walk(root);
  return result;
}

async function fixture(paused: boolean, boundary: "post-merge" | "post-commit" | "pre-merge-commit" = "post-merge") {
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), "farm-process-interruption-")));
  const repo = path.join(root, "repo"), control = path.join(root, "control");
  mkdirSync(repo); mkdirSync(control);
  const home = path.join(control, "home"); mkdirSync(home);
  const git = (...args: string[]) => execFileSync("git", ["-C", repo, ...args], { env: environment(home), encoding: "utf8", timeout: 10_000 }).trim();
  git("init", "-b", "main"); git("config", "user.email", "fixture@example.invalid"); git("config", "user.name", "Fixture");
  writeFileSync(path.join(repo, "README.md"), "owned fixture\n"); git("add", "README.md"); git("commit", "-m", "base");
  const base = git("rev-parse", "HEAD");
  const hooks = path.join(control, "hooks"), ackPath = path.join(control, "merge-ack.json"), release = path.join(control, "release");
  mkdirSync(hooks);
  const hookScript = path.join(control, `${boundary}.cjs`);
  writeFileSync(hookScript, `const fs=require('node:fs');const cp=require('node:child_process');
const head=cp.execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
fs.writeFileSync(${JSON.stringify(ackPath)},JSON.stringify({pid:process.pid,hookParentPid:process.ppid,head}));
if(${paused}){const check=setInterval(()=>{if(fs.existsSync(${JSON.stringify(release)})){clearInterval(check);process.exit(${boundary === "pre-merge-commit" ? 75 : 0});}},20);setTimeout(()=>process.exit(75),20000);}
`);
  const shellQuote = (s: string) => "'" + s.replace(/'/g, "'\\''") + "'";
  writeFileSync(path.join(hooks, boundary), `#!/bin/sh\nexec ${shellQuote(process.execPath.replaceAll("\\", "/"))} ${shellQuote(hookScript.replaceAll("\\", "/"))}\n`, { mode: 0o700 });
  git("config", "core.hooksPath", hooks.replaceAll("\\", "/"));
  let authors = 0;
  const server = createServer((req, res) => {
    let bytes = "";
    req.on("data", b => { bytes += b; });
    req.on("end", () => {
      authors++;
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ choices: [{ message: { content: "```typescript\n// path: src/task.ts\nexport const value = 7;\n```" } }] }));
    });
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  const plan = path.join(control, "plan.json");
  writeFileSync(plan, JSON.stringify({ meta: { name: "actual-interruption", model: "fixture", apiBaseUrl: `http://127.0.0.1:${port}` },
    tasks: [{ id: "task", description: "write implementation", filesInScope: ["src/task.ts"], test: { path: "src/task.spec.ts" }, gate: { commands: ["node -p 0"] }, maxRetries: 0 }] }));
  const running: Launch[] = [];
  function start(entry: "source" | "bundle", args = [plan], key = true): Launch {
    const launched = launch(repo, home, entry, args, { FARM_RUN_ID: "interrupted", FARM_MUTATION: "off", FARM_SAMPLES: "1", FARM_CONCURRENCY: "1", FARM_API_MAX_RETRIES: "0", ...(key ? { FARM_API_KEY: "fixture-key" } : {}) });
    running.push(launched); return launched;
  }
  function ack(): HookAck | undefined { try { return JSON.parse(readFileSync(ackPath, "utf8")) as HookAck; } catch { return undefined; } }
  async function dispose() {
    writeFileSync(release, "release owned Git hook\n");
    for (const run of running) if (run.child.exitCode === null && run.child.signalCode === null) run.child.kill("SIGKILL");
    await Promise.all(running.map(run => run.result));
    const observed = ack();
    if (observed) await until(() => !alive(observed.pid) && !alive(observed.hookParentPid) ? true : undefined, () => `retained owned hook/parent processes at ${root}`, 5_000);
    await new Promise<void>(resolve => server.close(() => resolve()));
    // Never delete a shared root or race a still-live owned process.
    if (path.dirname(root) !== realpathSync(tmpdir())) throw new Error(`retain unexpected fixture root: ${root}`);
    rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 });
  }
  return { root, repo, git, base, release, start, ack, dispose, authors: () => authors,
    runDir: path.join(repo, ".farm/runs/interrupted") };
}

for (const entry of ["source", "bundle"] as const) {
  it(`FARM-R01 real post-merge process interruption preserves unknown cleanup and concurrent receipt-only recovery (${entry})`, async () => {
    const f = await fixture(true);
    try {
      const running = f.start(entry);
      const observed = await until(f.ack, running.output);
      expect(running.child.exitCode).toBeNull();
      const effectFile = path.join(f.runDir, "effects/task.json");
      const effect = JSON.parse(readFileSync(effectFile, "utf8"));
      expect(effect.stage).toBe("merge-pending");
      expect(effect.integrationBefore.commit).toBe(f.base);
      expect(effect.candidate.commit).toBe(f.git("rev-parse", "farm/task"));
      expect(observed.head).toBe(f.git("rev-parse", "farm/integration"));
      expect(f.git("show", "-s", "--format=%P", observed.head).split(" ")).toEqual([f.base, effect.candidate.commit]);
      // This kills the real producer, rather than forging a post-crash journal.
      // Git has its own detached group; release its owned post-merge hook after
      // producer death and observe it separately, never assume parent death
      // established descendant containment.
      running.child.kill("SIGKILL");
      expect((await running.result).code).not.toBe(0);
      writeFileSync(f.release, "release after actual producer death\n");
      await until(() => !alive(observed.pid) && !alive(observed.hookParentPid) ? true : undefined, () => "owned Git hook has not settled", 5_000);
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
      const refs = f.git("show-ref"), registry = f.git("worktree", "list", "--porcelain"), originals = originalFiles(f.runDir);
      const recovered = await Promise.all([f.start(entry, ["--recover-receipt", "interrupted"], false).result,
        f.start(entry, ["--recover-receipt", "interrupted"], false).result]);
      for (const result of recovered) {
        expect(result.code, result.out).toBe(0);
        const receipt = JSON.parse(result.out);
        expect(receipt.results[0].merge).toBe("observed");
        expect(receipt.results).toMatchObject([{ stage: "merge-pending", candidateMatches: true, merge: "observed", status: "unknown", cleanup: "unknown", author: "not-invoked" }]);
      }
      expect(f.authors()).toBe(1);
      expect(f.git("show-ref")).toBe(refs);
      expect(f.git("worktree", "list", "--porcelain")).toBe(registry);
      expect(originalFiles(f.runDir)).toEqual(originals);
      expect(readdirSync(f.runDir).filter(name => /^farm-recovered-[a-f0-9]+\.json$/.test(name))).toHaveLength(2);
      expect(JSON.parse(readFileSync(effectFile, "utf8")).stage).toBe("merge-pending");
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
    } finally { await f.dispose(); }
  }, 30_000);
}

it("FARM-R01 unblocked real post-merge hook control publishes normal green receipt (bundle)", async () => {
  const f = await fixture(false);
  try {
    const result = await f.start("bundle").result;
    expect(result.code, result.out).toBe(0);
    expect(f.ack()).toBeDefined();
    expect(f.authors()).toBe(1);
    const effect = JSON.parse(readFileSync(path.join(f.runDir, "effects/task.json"), "utf8"));
    expect(effect.stage).toBe("settled");
    expect(effect.runCleanup.verified).toBe(true);
    const report = JSON.parse(readFileSync(path.join(f.runDir, "farm-report.json"), "utf8"));
    expect(report.results).toMatchObject([{ id: "task", status: "green" }]);
  } finally { await f.dispose(); }
}, 30_000);

for (const entry of ["source", "bundle"] as const) {
  it(`FARM-R01 real post-commit process interruption retains unacknowledged candidate without recovered green (${entry})`, async () => {
    const f = await fixture(true, "post-commit");
    try {
      const running = f.start(entry);
      const observed = await until(f.ack, running.output);
      expect(running.child.exitCode).toBeNull();
      const effectFile = path.join(f.runDir, "effects/task.json");
      const effect = JSON.parse(readFileSync(effectFile, "utf8"));
      expect(effect.stage).toBe("commit-pending");
      expect(effect.base.commit).toBe(f.base);
      expect(effect.candidate).toBeUndefined();
      expect(observed.head).not.toBe(f.base);
      expect(observed.head).toBe(f.git("rev-parse", "farm/task"));
      expect(f.git("show", "-s", "--format=%P", observed.head)).toBe(f.base);
      expect(f.git("rev-parse", "farm/task^{tree}")).toBe(effect.expectedTree);
      expect(f.git("rev-parse", "farm/integration")).toBe(f.base);
      // The real commit exists, but the blocked post-commit acknowledgement has
      // not returned to Farm. Parent death is not a child-containment claim.
      running.child.kill("SIGKILL");
      expect((await running.result).code).not.toBe(0);
      writeFileSync(f.release, "release after actual producer death\n");
      await until(() => !alive(observed.pid) && !alive(observed.hookParentPid) ? true : undefined,
        () => "owned Git post-commit hook has not settled", 5_000);
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
      const refs = f.git("show-ref"), registry = f.git("worktree", "list", "--porcelain"), originals = originalFiles(f.runDir);
      const recovered = await Promise.all([f.start(entry, ["--recover-receipt", "interrupted"], false).result,
        f.start(entry, ["--recover-receipt", "interrupted"], false).result]);
      for (const result of recovered) {
        expect(result.code, result.out).toBe(0);
        const receipt = JSON.parse(result.out);
        expect(receipt.results[0].candidateMatches).toBe(false);
        expect(receipt.results).toMatchObject([{ stage: "commit-pending", candidateMatches: false,
          candidate: { commit: observed.head, tree: effect.expectedTree }, integration: { commit: f.base },
          merge: "unknown", status: "unknown", cleanup: "unknown", author: "not-invoked" }]);
      }
      expect(f.authors()).toBe(1);
      expect(f.git("show-ref")).toBe(refs);
      expect(f.git("worktree", "list", "--porcelain")).toBe(registry);
      expect(originalFiles(f.runDir)).toEqual(originals);
      expect(readdirSync(f.runDir).filter(name => /^farm-recovered-[a-f0-9]+\.json$/.test(name))).toHaveLength(2);
      expect(JSON.parse(readFileSync(effectFile, "utf8")).stage).toBe("commit-pending");
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
    } finally { await f.dispose(); }
  }, 30_000);
}

for (const entry of ["source", "bundle"] as const) {
  it(`FARM-R01 real pre-merge interruption preserves pending merge resources through receipt-only recovery (${entry})`, async () => {
    const f = await fixture(true, "pre-merge-commit");
    try {
      const running = f.start(entry);
      const observed = await until(f.ack, running.output);
      const integration = path.join(f.runDir, "integration-wt");
      const effectFile = path.join(f.runDir, "effects/task.json");
      const effect = JSON.parse(readFileSync(effectFile, "utf8"));
      expect(running.child.exitCode).toBeNull();
      expect(effect.stage).toBe("merge-pending");
      expect(effect.integrationBefore.commit).toBe(f.base);
      expect(effect.candidate.commit).toBe(f.git("rev-parse", "farm/task"));
      expect(observed.head).toBe(f.base);
      expect(f.git("rev-parse", "farm/integration")).toBe(f.base);
      const metadata = (name: string) => f.git("-C", integration, "rev-parse", "--path-format=absolute", "--git-path", name);
      const mergeHead = metadata("MERGE_HEAD"), index = metadata("index");
      // The staged index is the pre-commit effect. Git's MERGE_HEAD may be
      // unpublished when producer death closes its pipes (POSIX SIGPIPE).
      // Preserve the state actually observed, never infer a completed merge.
      const beforeMergeMetadata = observeMetadata(mergeHead);
      if (beforeMergeMetadata.kind === "present")
        expect(Buffer.from(beforeMergeMetadata.bytes, "hex").toString("utf8").trim()).toBe(effect.candidate.commit);
      expect(f.git("-C", integration, "diff", "--cached", "--name-only")).toBe("src/task.ts");
      expect(f.git("-C", integration, "diff", "--cached", "--exit-code", effect.candidate.commit, "--")).toBe("");
      // Kill the real producer while the merge is staged but uncommitted. The
      // owned hook then refuses commit, leaving Git's actual pending merge for
      // inspection. This does not claim parent death stopped detached Git.
      running.child.kill("SIGKILL");
      expect((await running.result).code).not.toBe(0);
      writeFileSync(f.release, "release owned hook with controlled refusal\n");
      await until(() => !alive(observed.pid) && !alive(observed.hookParentPid) ? true : undefined,
        () => "owned pre-merge hook/Git has not settled", 5_000);
      expect(f.git("rev-parse", "farm/integration")).toBe(f.base);
      const afterMergeMetadata = observeMetadata(mergeHead);
      if (afterMergeMetadata.kind === "present")
        expect(Buffer.from(afterMergeMetadata.bytes, "hex").toString("utf8").trim()).toBe(effect.candidate.commit);
      const pending = () => ({ mergeHead: observeMetadata(mergeHead), index: readFileSync(index).toString("hex"),
        implementation: readFileSync(path.join(integration, "src/task.ts"), "utf8") });
      const effects = pending();
      expect(effects.mergeHead).toEqual(afterMergeMetadata);
      expect(f.git("-C", integration, "diff", "--cached", "--name-only")).toBe("src/task.ts");
      expect(f.git("-C", integration, "diff", "--cached", "--exit-code", effect.candidate.commit, "--")).toBe("");
      expect(effects.implementation).toBe("export const value = 7;\n");
      const refs = f.git("show-ref"), registry = f.git("worktree", "list", "--porcelain"), originals = originalFiles(f.runDir);
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
      const recovered = await Promise.all([f.start(entry, ["--recover-receipt", "interrupted"], false).result,
        f.start(entry, ["--recover-receipt", "interrupted"], false).result]);
      for (const result of recovered) {
        expect(result.code, result.out).toBe(0);
        const receipt = JSON.parse(result.out);
        expect(receipt.results[0].merge).toBe("unknown");
        expect(receipt.results).toMatchObject([{ stage: "merge-pending", candidateMatches: true,
          candidate: { commit: effect.candidate.commit }, integration: { commit: f.base },
          merge: "unknown", status: "unknown", cleanup: "unknown", author: "not-invoked" }]);
      }
      expect(f.authors()).toBe(1);
      expect(pending()).toEqual(effects);
      expect(f.git("show-ref")).toBe(refs);
      expect(f.git("worktree", "list", "--porcelain")).toBe(registry);
      expect(originalFiles(f.runDir)).toEqual(originals);
      expect(readdirSync(f.runDir).filter(name => /^farm-recovered-[a-f0-9]+\.json$/.test(name))).toHaveLength(2);
      expect(JSON.parse(readFileSync(effectFile, "utf8")).stage).toBe("merge-pending");
      expect(existsSync(path.join(f.runDir, "farm-report.json"))).toBe(false);
    } finally { await f.dispose(); }
  }, 30_000);
}
