/**
 * Smoke tests for farm.ts. Uses a mock HTTP server so no real API key needed.
 * Tests run against a temp git repo to avoid touching the main worktree.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { execSync, exec } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const TSX_BIN = resolve(__dirname, "node_modules/.bin/tsx");
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
    exec(
      `"${TSX_BIN}" "${farmTs}" "${planPath}"`,
      {
        cwd: repoDir,
        env: {
          ...process.env,
          // Disable commit signing in temp repos
          GIT_CONFIG_COUNT: "1",
          GIT_CONFIG_KEY_0: "commit.gpgsign",
          GIT_CONFIG_VALUE_0: "false",
          ...env,
        },
      },
      (err, stdout, stderr) => {
        resolve({ code: err?.code ?? 0, out: stdout + stderr });
      },
    );
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
    tmpDir = join("/tmp", `farm-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
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
          gate: { commands: ["bash -c 'exit 0'"] },
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
          gate: { commands: ["bash -c 'exit 0'"] },
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
          gate: { commands: ["false"] }, // always fails (exit 1)
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
});
