/**
 * Smoke tests for farm.ts. Uses a mock HTTP server so no real API key needed.
 * Tests run against a temp git repo to avoid touching the main worktree.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { execSync, spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const TSX_BIN = resolve(
  __dirname,
  "node_modules/.bin",
  process.platform === "win32" ? "tsx.cmd" : "tsx",
);
const farmTs = resolve(__dirname, "farm.ts");
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import type { Server } from "node:http";

// --------------------------------------------------------------------------
// Mini mock HTTP server that returns canned file-block responses
// --------------------------------------------------------------------------
type MockHandler = (body: unknown) => string;

function startMockServer(handler: MockHandler): Promise<{ server: Server; port: number }> {
  return new Promise((resolve) => {
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      let data = "";
      req.on("data", (chunk) => (data += chunk));
      req.on("end", () => {
        const body = JSON.parse(data || "{}");
        const content = handler(body);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            choices: [{ message: { content } }],
          }),
        );
      });
    });
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address() as { port: number };
      resolve({ server, port: addr.port });
    });
  });
}

// --------------------------------------------------------------------------
// Temp git repo setup
// --------------------------------------------------------------------------
function createTempRepo(dir: string) {
  mkdirSync(dir, { recursive: true });
  execSync("git init -b main", { cwd: dir, stdio: "pipe" });
  execSync("git config user.email test@test.com", { cwd: dir, stdio: "pipe" });
  execSync("git config user.name Test", { cwd: dir, stdio: "pipe" });
  execSync("git config commit.gpgsign false", { cwd: dir, stdio: "pipe" });
  // Initial commit so we have a HEAD on main
  writeFileSync(join(dir, "README.md"), "# test\n");
  execSync("git add -A", { cwd: dir, stdio: "pipe" });
  execSync("git commit -m init --no-gpg-sign", { cwd: dir, stdio: "pipe" });
  mkdirSync(join(dir, "src"), { recursive: true });
}

// --------------------------------------------------------------------------
// Run farm.ts via tsx (dev path) against the temp repo
// --------------------------------------------------------------------------
function runFarm(
  repoDir: string,
  planPath: string,
  env: Record<string, string>,
): Promise<{ code: number; out: string }> {
  return new Promise((resolve) => {
    // D-6: use spawn() with explicit args array instead of exec() with a
    // shell-interpolated string — eliminates shell injection surface.
    // On Windows, .cmd files must be invoked via cmd.exe /c (same pattern
    // as runGate in farm.ts itself).
    const [bin, args] =
      process.platform === "win32"
        ? (["cmd.exe", ["/c", TSX_BIN, farmTs, planPath]] as const)
        : ([TSX_BIN, [farmTs, planPath]] as const);
    const child = spawn(bin, args, {
      cwd: repoDir,
      env: {
        ...process.env,
        // Disable commit signing in temp repos
        GIT_CONFIG_COUNT: "1",
        GIT_CONFIG_KEY_0: "commit.gpgsign",
        GIT_CONFIG_VALUE_0: "false",
        ...env,
      },
      ...(process.platform === "win32" ? { windowsVerbatimArguments: true } : {}),
    });
    let out = "";
    child.stdout.on("data", (d: Buffer) => (out += d));
    child.stderr.on("data", (d: Buffer) => (out += d));
    child.on("close", (code: number | null) => resolve({ code: code ?? 1, out }));
    child.on("error", (e: Error) => resolve({ code: 1, out: String(e) }));
  });
}

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------
describe("farm.ts smoke tests", () => {
  let tmpDir: string;
  let mockServer: Server;
  let port: number;

  beforeEach(async () => {
    tmpDir = join(tmpdir(), `farm-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    createTempRepo(tmpDir);
  });

  afterEach(() => {
    mockServer?.close();
    rmSync(tmpDir, { recursive: true, force: true });
    // Clean up any leftover farm worktrees
    rmSync(join(tmpDir, "../.codearbiter-farm"), { recursive: true, force: true });
  });

  it("fails immediately when FARM_MODEL is not set", async () => {
    const plan = {
      meta: { name: "test" },
      tasks: [
        {
          id: "t1",
          description: "test",
          filesInScope: ["src/a.ts"],
          test: { path: "src/a.test.ts" },
          gate: { commands: ["node -p 0"] },
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_API_BASE_URL: "http://localhost:9",
      // No FARM_MODEL, no meta.model
    });

    expect(result.code).toBe(1);
    expect(result.out).toContain("No model configured");
  });

  it("completes two tasks green when API returns valid file blocks", async () => {
    ({ server: mockServer, port } = await startMockServer((body) => {
      // Return a file block appropriate to the task described in the prompt
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      if (content.includes("src/hello.ts")) {
        return [
          "```typescript",
          "// path: src/hello.ts",
          "export function hello() { return 'hello'; }",
          "```",
        ].join("\n");
      }
      return [
        "```typescript",
        "// path: src/world.ts",
        "export function world() { return 'world'; }",
        "```",
      ].join("\n");
    }));

    const planPath = join(tmpDir, "plan.json");
    const plan = JSON.parse(
      readFileSync(join(__dirname, "__fixtures__/simple.plan.json"), "utf8"),
    );
    plan.meta.apiBaseUrl = `http://127.0.0.1:${port}`;
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, {
      FARM_API_KEY: "test-key",
      FARM_BASE_BRANCH: "main",
    });

    if (result.code !== 0) {
      console.error("FARM OUTPUT:", result.out);
      try {
        const r = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
        console.error("REPORT:", JSON.stringify(r.results, null, 2));
      } catch {}
    }
    expect(result.code).toBe(0);
    expect(result.out).toContain("green=2");
    expect(result.out).toContain("escalate=0");

    // Report written
    const report = JSON.parse(
      readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"),
    );
    expect(report.results).toHaveLength(2);
    expect(report.results.every((r: { status: string }) => r.status === "green")).toBe(true);
  });

  it("escalates with 'drift:' note when worker writes outside filesInScope", async () => {
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```typescript",
        "// path: src/hello.ts",
        "export function hello() { return 'hello'; }",
        "```",
        "```typescript",
        "// path: src/UNAUTHORIZED.ts",
        "// this file should not be here",
        "```",
      ].join("\n"),
    ));

    const plan = {
      meta: { name: "drift-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write hello",
          deps: [],
          filesInScope: ["src/hello.ts"],
          test: { path: "src/hello.test.ts" },
          gate: { commands: ["node -p 0"] },
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    console.error("DRIFT TEST OUTPUT:", result.out);
    expect(result.code).toBe(2);
    const report = JSON.parse(
      readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"),
    );
    const escalated = report.results.find((r: { id: string }) => r.id === "task-a");
    expect(escalated.status).toBe("escalate");
    expect(escalated.note).toMatch(/^drift:/);
  });

  it("escalates with gate failure note after maxRetries exceeded", async () => {
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```typescript",
        "// path: src/hello.ts",
        "export function hello() { return 'hello'; }",
        "```",
      ].join("\n"),
    ));

    const plan = {
      meta: { name: "gate-fail-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write hello",
          deps: [],
          filesInScope: ["src/hello.ts"],
          test: { path: "src/hello.test.ts" },
          gate: { commands: ['node -e "process.exit(1)"'] }, // always fails (exit 1)
          maxRetries: 1,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(result.code).toBe(2);
    const report = JSON.parse(
      readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"),
    );
    expect(report.results[0].status).toBe("escalate");
  });

  it("blocks path traversal — worker cannot write outside the worktree", async () => {
    const sentinel = join(tmpDir, "..", `farm-escape-${Date.now()}.txt`);
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```typescript",
        `// path: ../${basename(sentinel)}`,
        "export const pwned = true;",
        "```",
      ].join("\n"),
    ));

    const plan = {
      meta: { name: "traversal-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write hello",
          deps: [],
          filesInScope: ["src/hello.ts"],
          test: { path: "src/hello.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(result.code).toBe(2);
    // The escape file must NOT have been written anywhere outside the worktree.
    expect(existsSync(sentinel)).toBe(false);
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results[0].status).toBe("escalate");
    expect(report.results[0].note).toMatch(/escapes worktree/);
  });

  it("protects the failing test — worker cannot overwrite test.path", async () => {
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```typescript",
        "// path: src/hello.test.ts",
        "// neutered test that always passes",
        "```",
      ].join("\n"),
    ));

    const plan = {
      meta: { name: "test-protect", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write hello",
          deps: [],
          filesInScope: ["src/hello.ts"],
          test: { path: "src/hello.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(result.code).toBe(2);
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results[0].status).toBe("escalate");
    expect(report.results[0].note).toMatch(/read-only|tampered/);
  });

  it("flags anti-gaming — tiny impl that hard-codes the asserted literal escalates", async () => {
    ({ server: mockServer, port } = await startMockServer(() =>
      ["```typescript", "// path: src/answer.ts", "export const answer = 42;", "```"].join("\n"),
    ));

    // Commit a test that asserts a specific literal, so it exists in the worktree.
    writeFileSync(join(tmpDir, "src", "answer.test.ts"), "expect(answer).toBe(42);\n");
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add failing test" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "gaming-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Compute the answer",
          deps: [],
          filesInScope: ["src/answer.ts"],
          test: { path: "src/answer.test.ts" },
          gate: { commands: ["node -p 0"] }, // gate passes; guard must still catch gaming
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(result.code).toBe(2);
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results[0].status).toBe("escalate");
    expect(report.results[0].note).toMatch(/^gaming:/);
  });

  it("mutation guard — flags an impl whose branches the narrow test does not constrain", async () => {
    // Worker returns a multi-branch impl; the narrow test only exercises one path,
    // so mutating the unexercised branch/operator survives → low mutation score.
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```javascript",
        "// path: src/classify.js",
        "module.exports.classify = function (n) {",
        '  if (n > 10) return "big";',
        '  return "small";',
        "};",
        "```",
      ].join("\n"),
    ));

    const narrowTest =
      `node -e "const {classify}=require('./src/classify.js'); process.exit(classify(5)==='small'?0:1)"`;
    const plan = {
      meta: { name: "mutation-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Classify a number",
          deps: [],
          filesInScope: ["src/classify.js"],
          test: { path: "src/classify.test.js" },
          gate: { commands: [narrowTest] }, // gate.commands[0] = the narrow behavioral test
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    // Score is low but not near-zero (the "small" return IS killed), so it warns
    // into Phase 3 rather than hard-escalating: task stays green with a warning.
    expect(result.code).toBe(0);
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    const r = report.results[0];
    expect(r.status).toBe("green");
    expect(r.mutationScore).toBeLessThan(0.5);
    expect(r.warning).toMatch(/mutation-risk/);
  });

  it("mutation guard — near-zero score on a non-trivial impl hard-escalates", async () => {
    // A multi-branch impl behind a no-op gate: nothing is constrained, so every
    // mutant survives (score ~0) and the guard escalates.
    ({ server: mockServer, port } = await startMockServer(() =>
      [
        "```javascript",
        "// path: src/m.js",
        "module.exports.f = function (a, b) {",
        "  if (a > b) return 1;",
        "  if (a < b) return 2;",
        "  if (a === b) return 3;",
        "  return 4;",
        "};",
        "```",
      ].join("\n"),
    ));

    const plan = {
      meta: { name: "mutation-escalate", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Compare",
          deps: [],
          filesInScope: ["src/m.js"],
          test: { path: "src/m.test.js" },
          gate: { commands: ["node -p 0"] }, // no-op gate constrains nothing
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(result.code).toBe(2);
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results[0].status).toBe("escalate");
    expect(report.results[0].note).toMatch(/mutation score/);
  });

  it("is safe to run twice in a row (stale branches cleaned)", async () => {
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      const file = content.includes("src/hello.ts") ? "src/hello.ts" : "src/world.ts";
      return ["```typescript", `// path: ${file}`, `export const x = 1;`, "```"].join("\n");
    }));

    const planPath = join(tmpDir, "plan.json");
    const plan = JSON.parse(readFileSync(join(__dirname, "__fixtures__/simple.plan.json"), "utf8"));
    plan.meta.apiBaseUrl = `http://127.0.0.1:${port}`;
    writeFileSync(planPath, JSON.stringify(plan));

    const first = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });
    expect(first.code).toBe(0);
    // Second run against the same repo must not fail on stale farm/* branches.
    const second = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });
    expect(second.code).toBe(0);
    expect(second.out).toContain("green=2");
  });
});
