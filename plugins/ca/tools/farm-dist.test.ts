/**
 * farm-dist.test.ts — #407. The bundle users actually run is exercised.
 *
 * `includes/farm.md` tells operators to run `node <plugin>/tools/farm.js`, and
 * `package.json` defines `farm:dist` for exactly that. But the integration
 * launcher ran `farm.ts` through the tsx loader, the unit suite imported
 * `farm.ts`, and CI's only operation on `farm.js` was a post-test rebuild and
 * byte-diff against the committed copy.
 *
 * So the merge gate proved SOURCE behaviour and DETERMINISTIC GENERATION, and
 * never that the ESM bundle starts, parses argv, resolves its bundled modules,
 * preserves process/exit semantics, or completes a representative failure path
 * under plain Node. An esbuild or runtime-boundary regression could ship behind
 * a fully green source suite. A byte-identical artifact is not a working one.
 *
 * WHY A SEPARATE SHARD, not a parameterised sweep of farm.test.ts: that file is
 * 1700 lines and ~25 integration cases, each spawning a real child against a
 * real temp git repo. Running all of them twice would roughly double the
 * slowest suite in the repo to re-prove assertions that are about farm's LOGIC,
 * not its packaging. What needs proving here is the runtime boundary, so this
 * covers the cases named in the issue's AC-2 and adds an explicit parity test.
 *
 * The fixtures below are a deliberate small copy of farm.test.ts's, not an
 * extraction: hoisting them out of a file that 25 tests depend on is a larger,
 * riskier edit than ~60 lines of duplication, and this shard needs a narrower
 * fixture than that file's anyway.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { execSync, spawn } from "node:child_process";
import { copyFileSync, readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { tmpdir } from "node:os";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const FARM_TS = resolve(__dirname, "farm.ts");
const FARM_JS = resolve(__dirname, "farm.js");
const TSX_LOADER = pathToFileURL(createRequire(import.meta.url).resolve("tsx")).href;

/**
 * The two things a user can run. `dist` is the shipped bundle and is the point
 * of this file; `source` exists so the parity test can execute ONE fixture
 * through both and compare, rather than asserting the bundle in isolation.
 */
type Target = "source" | "dist";

/** argv for a target — the only difference between the two launchers. */
function argvFor(target: Target, entry: string, planPath: string): string[] {
  return target === "dist"
    // Plain Node, no loader, no transform. Exactly `npm run farm:dist`.
    ? [entry, planPath]
    : ["--import", TSX_LOADER, entry, planPath];
}

function entryFor(target: Target): string {
  return target === "dist" ? FARM_JS : FARM_TS;
}

function runFarm(
  target: Target,
  repoDir: string,
  planPath: string,
  env: Record<string, string | undefined>,
  entry = entryFor(target),
): Promise<{ code: number; out: string }> {
  return new Promise((settle) => {
    // spawn with an explicit argv array — never a shell — so a path containing
    // a space or a metacharacter is inert (the same discipline farm.test.ts's
    // launcher documents).
    const childEnv: Record<string, string> = {
      ...(process.env as Record<string, string>),
      GIT_CONFIG_COUNT: "1",
      GIT_CONFIG_KEY_0: "commit.gpgsign",
      GIT_CONFIG_VALUE_0: "false",
    };
    for (const [key, value] of Object.entries(env)) {
      if (value === undefined) delete childEnv[key];
      else childEnv[key] = value;
    }
    const child = spawn(process.execPath, argvFor(target, entry, planPath), {
      cwd: repoDir,
      env: childEnv,
    });
    let out = "";
    child.stdout.on("data", (d: Buffer) => (out += d));
    child.stderr.on("data", (d: Buffer) => (out += d));
    child.on("close", (code) => settle({ code: code ?? 1, out }));
    child.on("error", (e: Error) => settle({ code: 1, out: String(e) }));
  });
}

type MockHandler = (body: unknown) => string;

function startMockServer(handler: MockHandler): Promise<{ server: Server; port: number }> {
  return new Promise((settle) => {
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      let data = "";
      req.on("data", (chunk) => (data += chunk));
      req.on("end", () => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ choices: [{ message: { content: handler(JSON.parse(data || "{}")) } }] }));
      });
    });
    server.listen(0, "127.0.0.1", () => settle({ server, port: (server.address() as { port: number }).port }));
  });
}

/** Remove a fixture directory, tolerating a Windows handle that has not yet
 * been released. Cleanup failures are never test failures (#462). */
function discard(dir: string): void {
  try {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  } catch {
    /* a leaked temp dir is the OS's problem, not this suite's verdict */
  }
}

function createTempRepo(dir: string): void {
  mkdirSync(dir, { recursive: true });
  const git = (args: string) => execSync(`git ${args}`, { cwd: dir, stdio: "pipe" });
  git("init -b main");
  git("config user.email test@test.com");
  git("config user.name Test");
  git("config commit.gpgsign false");
  writeFileSync(join(dir, "README.md"), "# test\n");
  git("add -A");
  git("commit -m init --no-gpg-sign");
  mkdirSync(join(dir, "src"), { recursive: true });
}

/** The two-task fixture plan, pointed at a local mock API. */
function greenPlan(port: number): Record<string, unknown> {
  const plan = JSON.parse(readFileSync(join(__dirname, "__fixtures__/simple.plan.json"), "utf8"));
  plan.meta.apiBaseUrl = `http://127.0.0.1:${port}`;
  return plan;
}

/** A worker response that satisfies whichever fixture task is being asked for. */
const fixtureWorker: MockHandler = (body) => {
  const prompt = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
  return prompt.includes("src/hello.ts")
    ? ["```typescript", "// path: src/hello.ts", "export function hello() { return 'hello'; }", "```"].join("\n")
    : ["```typescript", "// path: src/world.ts", "export function world() { return 'world'; }", "```"].join("\n");
};

describe("#407 — the SHIPPED farm.js bundle, under plain Node", () => {
  let tmpDir: string;
  let mockServer: Server | undefined;

  beforeEach(() => {
    tmpDir = join(tmpdir(), `farm-dist-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    createTempRepo(tmpDir);
  });

  afterEach(() => {
    mockServer?.close();
    mockServer = undefined;
    // #462's rule: a cleanup helper must never be the thing that fails a suite.
    // On Windows a just-exited child (or a farm worktree) can still hold the
    // directory for a moment, and rmSync raises EPERM through `force: true`.
    // The worktree sibling goes first, since it is what holds the repo open.
    discard(join(tmpDir, "..", ".codearbiter-farm"));
    discard(tmpDir);
  });

  it("starts at all: the bundle parses and resolves its own modules", async () => {
    // The cheapest possible regression detector for an esbuild boundary
    // problem. A bundle that cannot start fails here with a module or syntax
    // error rather than somewhere confusing deep in a later assertion.
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, "{}");
    const result = await runFarm("dist", tmpDir, planPath, { FARM_API_KEY: "test-key" });
    expect(result.out).not.toMatch(/Cannot find (module|package)/i);
    expect(result.out).not.toMatch(/SyntaxError|ERR_MODULE_NOT_FOUND|ERR_UNKNOWN_FILE_EXTENSION/);
  });

  it("validates the plan and refuses unparseable JSON with a bounded message", async () => {
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, "{ not json");
    const result = await runFarm("dist", tmpDir, planPath, { FARM_API_KEY: "test-key" });
    expect(result.code).not.toBe(0);
    // Bounded diagnostic, not a stack trace escaping the bundle.
    expect(result.out).not.toContain("at Object.");
  });

  it("fails closed when the credential is missing", async () => {
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(greenPlan(1)));
    // Absent, not merely un-overridden: a CI shell may already export it.
    const result = await runFarm("dist", tmpDir, planPath, { FARM_API_KEY: undefined });
    expect(result.code).not.toBe(0);
    expect(result.out).toMatch(/FARM_API_KEY/);
  });

  it("completes green against the loopback API and emits a report", async () => {
    ({ server: mockServer } = await startMockServer(fixtureWorker));
    const port = (mockServer!.address() as { port: number }).port;
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(greenPlan(port)));

    const result = await runFarm("dist", tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_BASE_BRANCH: "main",
    });
    if (result.code !== 0) console.error("FARM.JS OUTPUT:", result.out);

    expect(result.code).toBe(0);
    expect(result.out).toContain("green=2");
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results).toHaveLength(2);
    // This is a two-task, real-git-worktree integration proof. Windows hosted
    // runners can exceed Vitest's 5s unit-test default under concurrent CI
    // load even though the child completes normally; keep the proof bounded
    // without weakening any of its behavioral assertions.
  }, 30_000);

  it("escalates and exits non-zero when the API fails", async () => {
    // Loopback FAILURE path: the port is closed, so every worker call errors.
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(greenPlan(1)));
    const result = await runFarm("dist", tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_BASE_BRANCH: "main",
    });
    expect(result.code).not.toBe(0);
    expect(result.out).toMatch(/green=0/);
    // Retries plus a real git worktree per task: this legitimately takes longer
    // than vitest's 5s default, and a timeout here would read as a bundle fault.
  }, 120_000);

  it("PARITY: one fixture through farm.ts and farm.js gives the same result", async () => {
    // AC-3. The bundle is not merely byte-identical to a rebuild, it behaves
    // the same as the source it was built from - on exit code, on the
    // human-readable tally, and on the emitted report.
    ({ server: mockServer } = await startMockServer(fixtureWorker));
    const port = (mockServer!.address() as { port: number }).port;

    const observe = async (target: Target) => {
      const dir = join(tmpdir(), `farm-parity-${target}-${Date.now()}-${Math.random().toString(36).slice(2)}`);
      createTempRepo(dir);
      try {
        const planPath = join(dir, "plan.json");
        writeFileSync(planPath, JSON.stringify(greenPlan(port)));
        const run = await runFarm(target, dir, planPath, {
          FARM_API_KEY: "test-key",
          FARM_BASE_BRANCH: "main",
        });
        const report = JSON.parse(readFileSync(join(dir, ".farm/farm-report.json"), "utf8"));
        return {
          code: run.code,
          tally: run.out.match(/green=\d+ *escalate=\d+/)?.[0] ?? run.out,
          statuses: report.results.map((r: { id: string; status: string }) => `${r.id}:${r.status}`).sort(),
        };
      } finally {
        discard(join(dir, "..", ".codearbiter-farm"));
        discard(dir);
      }
    };

    const [source, dist] = [await observe("source"), await observe("dist")];
    expect(dist).toEqual(source);
    expect(dist.code).toBe(0);
  }, 120_000);

  it("NEGATIVE CONTROL: a behaviourally altered bundle fails this shard", async () => {
    // AC-4, and the assertion that makes the rest of this file mean something.
    // A shard that passes against a broken artifact proves nothing. The mutant
    // is syntactically valid and would be byte-DIFFERENT from a rebuild - but
    // the point is that it is caught HERE, by behaviour, rather than only by
    // the staleness diff, which cannot see a bundler that emits valid-but-wrong
    // output from unchanged source.
    ({ server: mockServer } = await startMockServer(fixtureWorker));
    const port = (mockServer!.address() as { port: number }).port;

    const mutant = join(tmpDir, "farm-mutant.js");
    copyFileSync(FARM_JS, mutant);
    const original = readFileSync(mutant, "utf8");
    // Force a clean exit regardless of outcome: the single most dangerous
    // packaging regression, because it turns every failure green.
    const patched = `${original}\nprocess.exitCode = 0;\nprocess.on("exit", () => process.reallyExit(0));\n`;
    expect(patched).not.toBe(original);
    writeFileSync(mutant, patched);

    const planPath = join(tmpDir, "plan.json");
    // A plan that MUST fail: the API port is closed.
    writeFileSync(planPath, JSON.stringify(greenPlan(1)));
    const result = await runFarm("dist", tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_BASE_BRANCH: "main",
    }, mutant);

    // Side by side, in ONE test, so the linkage is proven rather than asserted
    // in a comment: the real bundle fails the run, the mutant reports success.
    // Any shard assertion of the form `expect(code).not.toBe(0)` therefore goes
    // red against the mutant while every farm.ts test stays green - which is
    // exactly the regression class this file exists to catch.
    const genuine = await runFarm("dist", tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_BASE_BRANCH: "main",
    });
    expect(genuine.code).not.toBe(0);
    expect(result.code).toBe(0);
    void port;
  }, 240_000);
});
