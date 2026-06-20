/**
 * Smoke tests for farm.ts. Uses a mock HTTP server so no real API key needed.
 * Tests run against a temp git repo to avoid touching the main worktree.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { execSync, spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, resolve, basename } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const farmTs = resolve(__dirname, "farm.ts");
// Absolute file: URL to the tsx ESM loader, resolved from THIS file's location
// (where tsx is installed) so it is independent of the child's cwd — the temp
// repo the child runs in has no node_modules.
const TSX_LOADER = pathToFileURL(
  createRequire(import.meta.url).resolve("tsx"),
).href;
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
    // D-6: use spawn() with an explicit args array — no shell. Run farm.ts
    // through Node's own tsx loader (process.execPath is an absolute path, no
    // PATH lookup) rather than round-tripping the tsx.cmd shim through
    // `cmd.exe /c`. The old path built a cmd.exe command line out of absolute
    // file paths (TSX_BIN/farmTs/planPath), which mis-parses any path containing
    // a space and is what CodeQL js/shell-command-injection-from-environment
    // flagged. This form passes each path as a discrete argv entry, never as
    // shell text, so spaced paths and metacharacters are inert.
    const child = spawn(
      process.execPath,
      ["--import", TSX_LOADER, farmTs, planPath],
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
    );
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

  it("streams each settled task to .farm/farm-results.jsonl as it settles (AC-08)", async () => {
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      const file = content.includes("src/hello.ts") ? "src/hello.ts" : "src/world.ts";
      return ["```typescript", `// path: ${file}`, `export const x = 1;`, "```"].join("\n");
    }));

    const planPath = join(tmpDir, "plan.json");
    const plan = JSON.parse(readFileSync(join(__dirname, "__fixtures__/simple.plan.json"), "utf8"));
    plan.meta.apiBaseUrl = `http://127.0.0.1:${port}`;
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });
    expect(result.code).toBe(0);
    expect(result.out).toContain("green=2");

    // The incremental settlement record exists and holds exactly one line per
    // settled task (D7: JSONL is the per-task stream; report is authoritative).
    const jsonlPath = join(tmpDir, ".farm/farm-results.jsonl");
    const raw = readFileSync(jsonlPath, "utf8");
    const lines = raw.split("\n").filter((l) => l.trim().length > 0);
    expect(lines).toHaveLength(2);

    // Each line parses to a JSON object carrying a result with an id.
    const parsed = lines.map((l) => JSON.parse(l) as { id: string });
    for (const entry of parsed) expect(typeof entry.id).toBe("string");

    // Both tasks are present (settlement order is non-deterministic across two
    // independent tasks — assert presence/count, not a strict order).
    const ids = parsed.map((e) => e.id).sort();
    expect(ids).toEqual(["task-a", "task-b"]);

    // The authoritative final summary is still written.
    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    expect(report.results).toHaveLength(2);
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

  it("enriches the worker prompt with the test source AND an in-scope sibling's contents (AC-03/AC-04)", async () => {
    // Capture every prompt the worker is sent. The mock returns a benign
    // in-scope file so the task can settle; the assertion is on what reached it.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => helper() + 1;", "```"].join("\n");
    }));

    // Plant the failing test AND an in-scope sibling in the worktree baseline
    // with recognizable, distinct content, then commit so they exist on the
    // integration HEAD the task's worktree is cut from.
    const TEST_MARKER = "RECOGNIZABLE_TEST_SOURCE_MARKER_8675309";
    const SIBLING_MARKER = "RECOGNIZABLE_SIBLING_CONTENTS_MARKER_24601";
    writeFileSync(
      join(tmpDir, "src", "feature.test.ts"),
      `// ${TEST_MARKER}\nexpect(feature()).toBe(1);\n`,
    );
    writeFileSync(
      join(tmpDir, "src", "helper.ts"),
      `// ${SIBLING_MARKER}\nexport const helper = () => 0;\n`,
    );
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add failing test + sibling" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "enrich-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature using helper",
          deps: [],
          // helper.ts is in scope (existing sibling), feature.ts is the target.
          filesInScope: ["src/feature.ts", "src/helper.ts"],
          test: { path: "src/feature.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(prompts.length).toBeGreaterThan(0);
    const firstPrompt = prompts[0];
    // AC-03: the read-only test source reached the worker.
    expect(firstPrompt).toContain(TEST_MARKER);
    // AC-04: the existing in-scope sibling's contents reached the worker.
    expect(firstPrompt).toContain(SIBLING_MARKER);
  });

  it("redacts secret-pattern matches from the injected context before transmission (AC-05)", async () => {
    // Capture every outgoing prompt. The mock returns a benign in-scope file so
    // the task can settle; the assertion is on what reached the third party.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => helper() + 1;", "```"].join("\n");
    }));

    // Plant secret-shaped strings in an in-scope sibling that enrichment reads.
    // The secret VALUES must never leave the trust boundary.
    const SECRET_TOKEN = "sk-ant-PLANTEDSECRET123";
    const SECRET_APIKEY = "PLANTEDSECRETVALUE";
    writeFileSync(
      join(tmpDir, "src", "feature.test.ts"),
      `expect(feature()).toBe(1);\n`,
    );
    writeFileSync(
      join(tmpDir, "src", "helper.ts"),
      [
        "export const helper = () => 0;",
        `const token = "${SECRET_TOKEN}";`,
        `api_key = "${SECRET_APIKEY}";`,
        "",
      ].join("\n"),
    );
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add test + sibling with planted secrets" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "redact-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature using helper",
          deps: [],
          filesInScope: ["src/feature.ts", "src/helper.ts"],
          test: { path: "src/feature.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(prompts.length).toBeGreaterThan(0);
    // No outgoing prompt may contain a planted secret value.
    for (const p of prompts) {
      expect(p).not.toContain(SECRET_TOKEN);
      expect(p).not.toContain(SECRET_APIKEY);
    }
    // The redaction marker stands in for what was removed.
    expect(prompts[0]).toContain("[REDACTED");
  });

  it("redacts a multi-line PEM private key as a span — no key-body line leaks (FINDING 1)", async () => {
    // A PEM block: only the BEGIN header matches the per-line trigger word
    // (PRIVATE). The base64 body lines carry no trigger word, so a per-line
    // redactor would transmit the key body. Span-aware redaction must remove
    // the whole BEGIN..END block.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => helper() + 1;", "```"].join("\n");
    }));

    // Fake (non-real) PEM key. Body lines are distinct, recognizable markers
    // with NO trigger word so a per-line redactor would let them through.
    const KEY_BODY_1 = "FAKEKEYBODYLINEONE0000000000000000000000000000";
    const KEY_BODY_2 = "FAKEKEYBODYLINETWO1111111111111111111111111111";
    const KEY_BODY_3 = "FAKEKEYBODYLINETHREE222222222222222222222222==";
    writeFileSync(join(tmpDir, "src", "feature.test.ts"), `expect(feature()).toBe(1);\n`);
    writeFileSync(
      join(tmpDir, "src", "helper.ts"),
      [
        "export const helper = () => 0;",
        "const pem = `",
        "-----BEGIN RSA PRIVATE KEY-----",
        KEY_BODY_1,
        KEY_BODY_2,
        KEY_BODY_3,
        "-----END RSA PRIVATE KEY-----",
        "`;",
        "",
      ].join("\n"),
    );
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add test + sibling with planted PEM" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "pem-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature using helper",
          deps: [],
          filesInScope: ["src/feature.ts", "src/helper.ts"],
          test: { path: "src/feature.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(prompts.length).toBeGreaterThan(0);
    // No outgoing prompt may contain ANY key-body line.
    for (const p of prompts) {
      expect(p).not.toContain(KEY_BODY_1);
      expect(p).not.toContain(KEY_BODY_2);
      expect(p).not.toContain(KEY_BODY_3);
    }
    // The redaction marker stands in for what was removed.
    expect(prompts[0]).toContain("[REDACTED");
  });

  it("redacts the gate-output tail before it reaches the retry prompt (FINDING 2)", async () => {
    // The gate prints a secret-shaped string then exits non-zero, forcing a
    // retry. The retry prompt embeds the prior gate tail as priorFailure — it
    // MUST be run through redaction so the secret value never reaches the worker.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/hello.ts", "export function hello() { return 'hello'; }", "```"].join("\n");
    }));

    const GATE_SECRET = "sk-ant-GATETAILSECRET99999";
    const plan = {
      meta: { name: "gate-tail-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write hello",
          deps: [],
          filesInScope: ["src/hello.ts"],
          test: { path: "src/hello.test.ts" },
          // Print a secret-shaped string to stdout, then fail → forces a retry
          // whose priorFailure carries the gate tail.
          gate: { commands: [`node -e "console.log('${GATE_SECRET}'); process.exit(1)"`] },
          maxRetries: 1,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    // More than one prompt means a retry happened (so a priorFailure was built).
    expect(prompts.length).toBeGreaterThan(1);
    // The planted secret must appear in NO outgoing prompt.
    for (const p of prompts) {
      expect(p).not.toContain(GATE_SECRET);
    }
  });

  it("never reads a denylisted secret-bearing file into injected context (FINDING / data-minimization)", async () => {
    // An in-scope .env file with recognizable contents must be skipped entirely
    // by buildEnrichment — its body is never read into the prompt regardless of
    // per-line redaction.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => 1;", "```"].join("\n");
    }));

    const ENV_MARKER = "DENYLISTED_ENV_FILE_CONTENTS_MARKER_4815162342";
    writeFileSync(join(tmpDir, "src", "feature.test.ts"), `expect(feature()).toBe(1);\n`);
    // A denylisted filename whose body would otherwise be injected.
    writeFileSync(join(tmpDir, "src", ".env"), `SOME_VAR=${ENV_MARKER}\n`);
    execSync("git add -A -f", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add test + denylisted .env" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "denylist-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature",
          deps: [],
          filesInScope: ["src/feature.ts", "src/.env"],
          test: { path: "src/feature.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(prompts.length).toBeGreaterThan(0);
    // The denylisted file's contents must appear in NO outgoing prompt.
    for (const p of prompts) {
      expect(p).not.toContain(ENV_MARKER);
    }
  });

  it("never injects a denylisted test.path source into injected context (STEP-A defense-in-depth)", async () => {
    // The read-only test source (task.test.path) is injected via the same
    // chokepoint as in-scope files, but until now it bypassed the
    // isSecretBearingFilename denylist that guards in-scope files. A test.path
    // pointing at a secret-bearing filename (e.g. *.pem/*.key/.env) must be
    // skipped too — its body must never cross the trust boundary.
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => 1;", "```"].join("\n");
    }));

    const TESTPATH_MARKER = "DENYLISTED_TESTPATH_CONTENTS_MARKER_2718281828";
    // A denylisted filename in the test.path slot whose body would otherwise be
    // injected read-only. The body carries NO secret trigger word, so per-line
    // redaction would NOT catch it — only the filename denylist can. That makes
    // this an assertion on the denylist gap specifically, not on redactSecrets.
    writeFileSync(join(tmpDir, "src", "creds.pem"), `harmless looking body ${TESTPATH_MARKER}\n`);
    execSync("git add -A -f", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add denylisted test.path source" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "denylist-testpath", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature",
          deps: [],
          filesInScope: ["src/feature.ts"],
          test: { path: "src/creds.pem" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    expect(prompts.length).toBeGreaterThan(0);
    // The denylisted test.path body must appear in NO outgoing prompt.
    for (const p of prompts) {
      expect(p).not.toContain(TESTPATH_MARKER);
    }
  });

  it("byte-caps the injected context with a visible truncation marker (AC-05)", async () => {
    const prompts: string[] = [];
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      prompts.push(content);
      return ["```typescript", "// path: src/feature.ts", "export const feature = () => helper() + 1;", "```"].join("\n");
    }));

    // An in-scope sibling far larger than the (test-lowered) cap, with a unique
    // marker only at the very tail — past the cap it must not be transmitted.
    const TAIL_MARKER = "TAIL_PAST_THE_CAP_MARKER_31337";
    const big = "// filler line of in-scope source content\n".repeat(4000);
    writeFileSync(join(tmpDir, "src", "feature.test.ts"), `expect(feature()).toBe(1);\n`);
    writeFileSync(join(tmpDir, "src", "helper.ts"), `export const helper = () => 0;\n${big}\n// ${TAIL_MARKER}\n`);
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add test + oversized sibling" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    const plan = {
      meta: { name: "cap-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Implement feature using helper",
          deps: [],
          filesInScope: ["src/feature.ts", "src/helper.ts"],
          test: { path: "src/feature.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key", FARM_ENRICH_MAX_BYTES: "2048" });

    expect(prompts.length).toBeGreaterThan(0);
    // Content past the cap is not transmitted; a visible truncation marker is.
    expect(prompts[0]).not.toContain(TAIL_MARKER);
    expect(prompts[0]).toContain("TRUNCATED");
  });

  it("serializes scope-overlapping tasks so the second inherits the first's merged change (AC-06)", async () => {
    // Two no-dep tasks whose filesInScope intersect on src/shared.ts.
    //  - task-a writes X = src/shared.ts (carrying a recognizable marker).
    //  - task-b lists src/shared.ts (overlap) in scope but writes a DIFFERENT
    //    file Y = src/b-out.ts; its gate asserts X is present with A's marker, so
    //    its success DEPENDS on inheriting A's merged change.
    // Without scope-aware readiness both dispatch concurrently (default
    // concurrency 4): task-b cuts its worktree from integration BEFORE A merges,
    // so src/shared.ts is absent and B's gate fails → escalate. With the
    // readiness filter B waits until A is green+merged, cuts from the post-A HEAD,
    // sees X, and both reach green with no merge conflict.
    const SHARED_MARKER = "SHARED_X_FROM_TASK_A_MARKER_112358";
    ({ server: mockServer, port } = await startMockServer((body) => {
      const content = (body as { messages?: Array<{ content?: string }> }).messages?.[0]?.content ?? "";
      // task-b's scope/target identifies it; otherwise it is task-a.
      if (content.includes("src/b-out.ts")) {
        return ["```typescript", "// path: src/b-out.ts", "export const b = 2;", "```"].join("\n");
      }
      return [
        "```typescript",
        "// path: src/shared.ts",
        `export const shared = "${SHARED_MARKER}";`,
        "```",
      ].join("\n");
    }));

    // Both tasks' failing tests exist on the baseline so enrichment can read them.
    writeFileSync(join(tmpDir, "src", "shared.test.ts"), `expect(shared).toBeDefined();\n`);
    writeFileSync(join(tmpDir, "src", "b.test.ts"), `expect(b).toBe(2);\n`);
    execSync("git add -A", { cwd: tmpDir, stdio: "pipe" });
    execSync(`git commit -m "add failing tests for overlap tasks" --no-gpg-sign`, { cwd: tmpDir, stdio: "pipe" });

    // task-b's gate proves it cut from the post-A-merge integration HEAD: it
    // requires src/shared.ts to exist AND to carry A's marker. If B ran before
    // A merged, shared.ts is absent → gate exits non-zero → escalate.
    const bGate =
      `node -e "const fs=require('fs');const s=fs.readFileSync('src/shared.ts','utf8');` +
      `if(!s.includes('${SHARED_MARKER}'))process.exit(1)"`;

    const plan = {
      meta: { name: "overlap-test", model: "test-model", apiBaseUrl: `http://127.0.0.1:${port}` },
      tasks: [
        {
          id: "task-a",
          description: "Write shared X",
          deps: [],
          filesInScope: ["src/shared.ts"],
          test: { path: "src/shared.test.ts" },
          gate: { commands: ["node -p 0"] },
          maxRetries: 0,
        },
        {
          id: "task-b",
          description: "Write b-out depending on shared X",
          deps: [],
          // Overlaps task-a on src/shared.ts; writes a different file.
          filesInScope: ["src/shared.ts", "src/b-out.ts"],
          test: { path: "src/b.test.ts" },
          gate: { commands: [bGate] },
          maxRetries: 0,
        },
      ],
    };
    const planPath = join(tmpDir, "plan.json");
    writeFileSync(planPath, JSON.stringify(plan));

    const result = await runFarm(tmpDir, planPath, { FARM_API_KEY: "test-key" });

    if (result.code !== 0) {
      console.error("AC-06 OUTPUT:", result.out);
    }
    // Both green, no escalation, no merge-conflict note anywhere.
    expect(result.code).toBe(0);
    expect(result.out).toContain("green=2");
    expect(result.out).toContain("escalate=0");

    const report = JSON.parse(readFileSync(join(tmpDir, ".farm/farm-report.json"), "utf8"));
    const b = report.results.find((r: { id: string }) => r.id === "task-b");
    expect(b.status).toBe("green");
    // No task escalated with a merge-conflict note.
    for (const r of report.results as Array<{ note?: string }>) {
      expect(r.note ?? "").not.toMatch(/merge failed/);
    }

    // The integration branch contains BOTH the merged X and Y — proving B cut
    // from the post-A-merge HEAD and merged cleanly on top.
    const integShared = execSync("git show farm/integration:src/shared.ts", {
      cwd: tmpDir,
      encoding: "utf8",
    });
    expect(integShared).toContain(SHARED_MARKER);
    const integB = execSync("git show farm/integration:src/b-out.ts", {
      cwd: tmpDir,
      encoding: "utf8",
    });
    expect(integB).toContain("export const b = 2;");
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

    // The streaming rail is truncated at run start, so a re-run does not
    // accumulate stale lines (the "safe to run twice" invariant covers it too).
    const raw = readFileSync(join(tmpDir, ".farm/farm-results.jsonl"), "utf8");
    const lines = raw.split("\n").filter((l) => l.trim().length > 0);
    expect(lines).toHaveLength(2);
  });
});
