/** runner-isolation.test.ts - Task 6 exact launch, protocol, role, and child enforcement obligations. */
import { EventEmitter } from "node:events";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { PassThrough, Readable } from "node:stream";
import { afterEach, describe, expect, test, vi } from "vitest";

const runnerMocks = vi.hoisted(() => {
  let randomBytesCall = 0;
  const spawn = vi.fn();
  const processTreeSpawnOptions = vi.fn((_platform?: NodeJS.Platform) => ({ detached: true, shell: false, windowsHide: true }));
  const cleanupTerminate = vi.fn(async (reason: string) => ({
    escalated: false,
    reason,
    state: "terminated",
    verified: true,
  }));
  const cleanupReady = vi.fn(async () => true);
  return {
    spawn,
    randomUUID: vi.fn(() => "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
    randomBytes: vi.fn(() => Buffer.from(
      randomBytesCall++ % 2 === 0
        ? "0123456789abcdef0123456789abcdef"
        : "fedcba9876543210fedcba9876543210",
      "hex",
    )),
    cleanupTerminate,
    cleanupReady,
    createProcessTreeCleanup: vi.fn(() => ({ ready: cleanupReady, terminate: cleanupTerminate })),
    processTreeSpawnOptions,
    spawnProcessTree: vi.fn(async (command: string, args: readonly string[], options: Record<string, unknown>) =>
      spawn(command, args, { ...processTreeSpawnOptions(process.platform), ...options })),
    resolveRuntimeIdentity: vi.fn(),
  };
});

vi.mock("node:child_process", async (importOriginal) => ({
  ...await importOriginal<typeof import("node:child_process")>(),
  spawn: runnerMocks.spawn,
}));
vi.mock("node:crypto", async (importOriginal) => ({
  ...await importOriginal<typeof import("node:crypto")>(),
  randomUUID: runnerMocks.randomUUID,
  randomBytes: runnerMocks.randomBytes,
}));
vi.mock("../src/runtime-resolver.ts", async (importOriginal) => ({
  ...await importOriginal<typeof import("../src/runtime-resolver.ts")>(),
  resolvePiRuntimeIdentity: runnerMocks.resolveRuntimeIdentity,
}));
vi.mock("../src/process-tree.ts", async (importOriginal) => ({
  ...await importOriginal<typeof import("../src/process-tree.ts")>(),
  createProcessTreeCleanup: runnerMocks.createProcessTreeCleanup,
  processTreeSpawnOptions: runnerMocks.processTreeSpawnOptions,
  spawnProcessTree: runnerMocks.spawnProcessTree,
}));

type RunnerModule = typeof import("../src/runner.ts");
type RolesModule = typeof import("../src/roles.ts");
type ChildModule = typeof import("../src/child-extension.ts");
type ChildLaunchInput = import("../src/runner.ts").ChildLaunchInput;

async function loadModule<T>(path: string, label: string): Promise<T> {
  try { return await import(path) as T; }
  catch (error) { throw new Error(`Task 6 ${label} implementation is missing`, { cause: error }); }
}

function launchFixture(root = "C:/fixture"): ChildLaunchInput {
  return {
    nodePath: resolve(root, "node.exe"),
    piCliPath: resolve(root, "dist", "cli.js"),
    provider: "openai",
    model: "gpt-test",
    tools: ["read", "bash", "edit", "write"],
    cwd: resolve(root, "repo"),
    childExtensionPath: resolve(root, "codearbiter-child.js"),
    skillPaths: [resolve(root, "skill.md")],
    charterPath: resolve(root, "backend-author.md"),
  };
}

const temporaryRoots: string[] = [];
const testValidation = new WeakMap<object, Record<string, unknown>>();

async function materializedRequest(task = "task-secret-sentinel") {
  const root = await realpath(await mkdtemp(resolve(tmpdir(), "ca-pi-task6-")));
  temporaryRoots.push(root);
  const packageRoot = resolve(import.meta.dirname, "..", "..");
  const piRoot = resolve(root, "pi-runtime");
  const request = {
    nodePath: process.execPath,
    piCliPath: resolve(piRoot, "dist", "cli.js"),
    provider: "openai",
    model: "gpt-test",
    tools: ["read", "bash", "edit", "write"] as const,
    cwd: resolve(root, "repo"),
    childExtensionPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
    skillPaths: [resolve(packageRoot, "routines", "tdd", "SKILL.md")],
    charterPath: resolve(packageRoot, "agents", "backend-author.md"),
    task,
    parentEnv: {
      ...process.env,
      OPENAI_API_KEY: "dummy-openai-value",
      ANTHROPIC_API_KEY: "dummy-anthropic-value",
      FARM_API_KEY: "dummy-farm-value",
      CLAUDE_CODE_OAUTH_TOKEN: "dummy-claude-value",
    },
    platform: process.platform,
    timeoutMs: 5_000,
  };
  await mkdir(request.cwd, { recursive: true });
  await mkdir(dirname(request.piCliPath), { recursive: true });
  await writeFile(request.piCliPath, "// Task 6 Pi CLI fixture\n", "utf8");
  await writeFile(resolve(piRoot, "package.json"), '{"name":"@earendil-works/pi-coding-agent","version":"0.80.10","bin":{"pi":"dist/cli.js"}}\n', "utf8");
  runnerMocks.resolveRuntimeIdentity.mockImplementation(async (candidate: string) => ({
    cliEntry: candidate,
    packageRoot: resolve(dirname(candidate), ".."),
    version: "0.80.10",
  }));
  testValidation.set(request, {
    activeNodePath: process.execPath,
    packageRoot,
    resolveRuntimeIdentity: async (candidate: string) => {
      if (candidate !== request.piCliPath) throw new Error("counterfeit Pi CLI");
      return { cliEntry: request.piCliPath, packageRoot: piRoot, version: "0.80.10" };
    },
  });
  return request;
}

async function materializedPathRequest(task = "task-secret-sentinel") {
  const request = await materializedRequest(task);
  const root = dirname(request.cwd);
  const packageRoot = resolve(root, "ca-pi-fixture");
  const pathRequest = {
    ...request,
    childExtensionPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
    skillPaths: [resolve(packageRoot, "routines", "tdd", "SKILL.md")],
    charterPath: resolve(packageRoot, "agents", "backend-author.md"),
  };
  for (const path of [pathRequest.childExtensionPath, pathRequest.charterPath, ...pathRequest.skillPaths]) {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, "// Task 6 path fixture\n", "utf8");
  }
  await writeFile(resolve(packageRoot, "package.json"), '{"name":"ca-pi","version":"0.1.0","type":"module"}\n', "utf8");
  await mkdir(resolve(packageRoot, "generated"), { recursive: true });
  await writeFile(resolve(packageRoot, "generated", "roles.json"), JSON.stringify([{
    name: "backend-author", classification: "author", charterPath: "agents/backend-author.md",
    skillPaths: ["routines/tdd/SKILL.md"], tools: ["read", "bash", "edit", "write"],
  }]) + "\n", "utf8");
  testValidation.set(pathRequest, { ...validationFor(request), packageRoot });
  return pathRequest;
}

function validationFor(request: object): Record<string, unknown> {
  const validation = testValidation.get(request);
  if (validation === undefined) throw new Error("Task 6 test validation identity is missing");
  return validation;
}

afterEach(async () => {
  runnerMocks.spawn.mockReset();
  runnerMocks.cleanupTerminate.mockReset();
  runnerMocks.cleanupTerminate.mockImplementation(async (reason: string) => ({
    escalated: false,
    reason,
    state: "terminated",
    verified: true,
  }));
  runnerMocks.createProcessTreeCleanup.mockReset();
  runnerMocks.cleanupReady.mockReset();
  runnerMocks.cleanupReady.mockResolvedValue(true);
  runnerMocks.createProcessTreeCleanup.mockImplementation(() => ({ ready: runnerMocks.cleanupReady, terminate: runnerMocks.cleanupTerminate }));
  runnerMocks.processTreeSpawnOptions.mockClear();
  runnerMocks.spawnProcessTree.mockReset();
  runnerMocks.spawnProcessTree.mockImplementation(async (command: string, args: readonly string[], options: Record<string, unknown>) =>
    runnerMocks.spawn(command, args, { ...runnerMocks.processTreeSpawnOptions(process.platform), ...options }));
  await Promise.all(temporaryRoots.splice(0).map(async (root) => await rm(root, { recursive: true, force: true })));
});

class FakeChild extends EventEmitter {
  readonly pid = 4242;
  exitCode: number | null = null;
  signalCode: NodeJS.Signals | null = null;
  readonly stdin = new PassThrough();
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  readonly capability = new PassThrough();
  readonly stdio = [this.stdin, this.stdout, this.stderr, this.capability] as const;
  readonly killCalls: Array<NodeJS.Signals | undefined> = [];
  private closed = false;
  constructor(private readonly closeOnKill = false) { super(); }
  kill(signal?: NodeJS.Signals) {
    this.killCalls.push(signal);
    if (this.closeOnKill) setImmediate(() => this.close(1));
    return true;
  }
  close(code = 0) {
    if (this.closed) return;
    this.closed = true;
    this.exitCode = code;
    this.stdout.end();
    this.stderr.end();
    this.capability.end();
    setImmediate(() => this.emit("close", code, null));
  }
}

const assistantMessage = {
  role: "assistant",
  content: [{ type: "text", text: "child-complete" }],
  api: "openai-responses",
  provider: "openai",
  model: "gpt-test",
  usage: {
    input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
  },
  stopReason: "stop",
  timestamp: 1,
} as const;

const userMessage = { role: "user", content: "task", timestamp: 1 } as const;
const ATTESTATION_TITLE = "codeArbiter isolated child readiness";
const ATTESTATION_TIMEOUT_MS = 5_000;
const FIXED_NONCE = "0123456789abcdef0123456789abcdef";
const FIXED_CHALLENGE = "fedcba9876543210fedcba9876543210";

function expectedAttestation(input: Pick<ChildLaunchInput, "cwd" | "provider" | "model" | "tools">): string {
  return createHash("sha256").update(JSON.stringify([
    "ca-pi-child-attestation-v1",
    FIXED_NONCE,
    FIXED_CHALLENGE,
    input.cwd,
    input.provider,
    input.model,
    [...input.tools].sort(),
    false,
    "rpc",
  ]), "utf8").digest("hex");
}

function writeValidAttestation(child: FakeChild, input: Pick<ChildLaunchInput, "cwd" | "provider" | "model" | "tools">, id = "ui-attestation-id"): void {
  child.stdout.write(JSON.stringify({
    type: "extension_ui_request",
    id,
    method: "confirm",
    title: ATTESTATION_TITLE,
    message: expectedAttestation(input),
    timeout: ATTESTATION_TIMEOUT_MS,
  }) + "\n");
}

describe("Task 6 exact Pi child launch", () => {
  test("puts no task, prompt, or credential in exact discovery-disabled argv", async () => {
    const { buildChildArgv } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const input = launchFixture();
    const argv = buildChildArgv(input);
    expect(argv).toEqual([
      input.piCliPath, "--mode", "rpc", "--no-approve", "--no-extensions",
      "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
      "--no-session", "--offline", "--provider", "openai", "--model", "gpt-test",
      "--tools", "read,bash,edit,write", "-e", input.childExtensionPath,
      "--append-system-prompt", input.charterPath, "--skill", input.skillPaths[0],
    ]);
    expect(argv.join(" ")).not.toContain("task-secret-sentinel");
    expect(JSON.stringify(input)).not.toContain("task-secret-sentinel");
  });

  test("rejects relative, missing, duplicate, and unsupported launch identities before spawn", async () => {
    const { validateChildLaunch } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    await expect(validateChildLaunch({ ...launchFixture(), nodePath: "node" } as never)).rejects.toThrow("absolute");
    await expect(validateChildLaunch({ ...launchFixture(), tools: ["read", "read"] } as never)).rejects.toThrow("tools");
    await expect(validateChildLaunch({ ...launchFixture(), provider: "unknown" } as never)).rejects.toThrow("provider");
  });

  test("uses a bounded two-record stdin handshake with a random correlation unrelated to task content", async () => {
    const { encodeChildInput } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const encoded = encodeChildInput("task-secret-sentinel", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", FIXED_NONCE, FIXED_CHALLENGE);
    const lines = encoded.trimEnd().split("\n").map((line) => JSON.parse(line) as Record<string, unknown>);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toEqual({ id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", type: "prompt", message: `/codearbiter-internal-child-handshake ${FIXED_NONCE} ${FIXED_CHALLENGE}` });
    expect(lines[1]).toEqual({ id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", type: "prompt", message: "task-secret-sentinel" });
    expect(JSON.stringify(lines[0])).not.toContain("task-secret-sentinel");
    expect(() => encodeChildInput("x".repeat(65_537), crypto.randomUUID(), "0".repeat(32), "1".repeat(32))).toThrow("task exceeds");
  });

  test("requires exact keys and value shapes for every accepted Pi JSONL event", async () => {
    const { parseChildJsonLine, childFailure } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const partialToolCallMessage = {
      ...assistantMessage,
      content: [{
        type: "toolCall", id: "call", name: "bash", arguments: {},
        partialArgs: '{"command":"', streamIndex: 0,
      }],
      stopReason: "toolUse",
    };
    const validAndInvalid: ReadonlyArray<readonly [Record<string, unknown>, Record<string, unknown>]> = [
      [{ type: "response", id: "task", command: "prompt", success: true }, { type: "response", id: 7, command: "prompt", success: true }],
      [{ type: "agent_start" }, { type: "agent_start", injected: true }],
      [{ type: "agent_end", messages: [assistantMessage], willRetry: false }, { type: "agent_end", messages: [assistantMessage] }],
      [{ type: "agent_settled" }, { type: "agent_settled", settled: true }],
      [{ type: "turn_start" }, { type: "turn_start", turnIndex: 1 }],
      [{ type: "turn_end", message: assistantMessage, toolResults: [] }, { type: "turn_end", message: assistantMessage, toolResults: "none" }],
      [{ type: "message_start", message: userMessage }, { type: "message_start", message: { role: "user", content: "task" } }],
      // Pi 0.80.10 streams the partialArgs scratch buffer inside message_start/end
      // assistant records; accepted via the same partial normalization as message_update.
      [{ type: "message_start", message: partialToolCallMessage }, { type: "message_start", message: { ...partialToolCallMessage, content: [{ ...partialToolCallMessage.content[0], partialArgs: 7 }] } }],
      [{ type: "message_end", message: partialToolCallMessage }, { type: "message_end", message: { ...partialToolCallMessage, content: [{ ...partialToolCallMessage.content[0], streamIndex: -1 }] } }],
      [{ type: "message_update", message: partialToolCallMessage, assistantMessageEvent: { type: "toolcall_start", contentIndex: 0, partial: partialToolCallMessage } }, { type: "message_update", message: { ...partialToolCallMessage, content: [{ ...partialToolCallMessage.content[0], partialArgs: 7 }] }, assistantMessageEvent: { type: "toolcall_start", contentIndex: 0, partial: partialToolCallMessage } }],
      [{ type: "message_end", message: assistantMessage }, { type: "message_end", message: { ...assistantMessage, content: "done" } }],
      [{ type: "tool_execution_start", toolCallId: "call", toolName: "bash", args: {} }, { type: "tool_execution_start", toolCallId: 3, toolName: "bash", args: {} }],
      [{ type: "tool_execution_update", toolCallId: "call", toolName: "bash", args: {}, partialResult: {} }, { type: "tool_execution_update", toolCallId: "call", toolName: "bash", args: {} }],
      [{ type: "tool_execution_end", toolCallId: "call", toolName: "bash", result: {}, isError: false }, { type: "tool_execution_end", toolCallId: "call", toolName: "bash", result: {}, isError: "false" }],
      [{ type: "extension_ui_request", id: "ui", method: "confirm", title: ATTESTATION_TITLE, message: "a".repeat(64), timeout: ATTESTATION_TIMEOUT_MS }, { type: "extension_ui_request", id: "ui", method: "confirm", title: ATTESTATION_TITLE, message: "a".repeat(64) }],
      [{ type: "extension_error", extensionPath: "child.js", event: "tool_call", error: "failure" }, { type: "extension_error", extensionPath: "child.js", event: "tool_call" }],
    ];
    for (const [valid, invalid] of validAndInvalid) {
      expect(parseChildJsonLine(JSON.stringify(valid))).toEqual(valid);
      expect(() => parseChildJsonLine(JSON.stringify(invalid))).toThrow("schema");
    }
    for (const scratch of [
      { partialArgs: '{"command":"' },
      { partialJson: '{"command":"' },
      { partialJson: '{"command":"', index: 0 },
      { streamIndex: 0 },
      { index: 0 },
    ]) {
      const partial = { ...assistantMessage, content: [{ type: "toolCall", id: "call", name: "bash", arguments: {}, ...scratch }], stopReason: "toolUse" };
      expect(parseChildJsonLine(JSON.stringify({
        type: "message_update", message: partial,
        assistantMessageEvent: { type: "toolcall_start", contentIndex: 0, partial },
      }))).toMatchObject({ type: "message_update" });
    }
    for (const content of [
      { type: "text", text: "partial", index: 0 },
      { type: "thinking", thinking: "partial", thinkingSignature: "sig", index: 0 },
    ]) {
      const partial = { ...assistantMessage, content: [content] };
      expect(parseChildJsonLine(JSON.stringify({
        type: "message_update", message: partial,
        assistantMessageEvent: { type: "start", partial },
      }))).toMatchObject({ type: "message_update" });
    }
    for (const content of [
      { type: "text", text: "partial", index: -1 },
      { type: "thinking", thinking: "partial", index: 0, unknown: true },
    ]) {
      const partial = { ...assistantMessage, content: [content] };
      expect(() => parseChildJsonLine(JSON.stringify({
        type: "message_update", message: partial,
        assistantMessageEvent: { type: "start", partial },
      }))).toThrow("schema");
    }
    expect(() => parseChildJsonLine(JSON.stringify({
      type: "message_update",
      message: { ...partialToolCallMessage, content: [{ ...partialToolCallMessage.content[0], partialArgs: "x".repeat(65_537) }] },
      assistantMessageEvent: { type: "toolcall_start", contentIndex: 0, partial: partialToolCallMessage },
    }))).toThrow(/schema|limit/u);
    for (const invalid of [
      { type: "message_end", message: { ...assistantMessage, responseId: 7 } },
      { type: "message_end", message: { ...assistantMessage, usage: { ...assistantMessage.usage, reasoning: "one" } } },
      { type: "message_end", message: { ...assistantMessage, content: [{ type: "unknown", text: "child-complete" }] } },
      { type: "message_end", message: { ...assistantMessage, content: [{ type: "text", text: "child-complete", injected: true }] } },
      { type: "tool_execution_start", toolCallId: "call", toolName: "bash", args: { nested: { too: { deep: { for: { the: { bounded: { protocol: { value: { here: true } } } } } } } } } },
      { type: "tool_execution_update", toolCallId: "call", toolName: "bash", args: {}, partialResult: { value: "x".repeat(70_000) } },
      { type: "tool_execution_end", toolCallId: "call", toolName: "bash", result: { keys: Object.fromEntries(Array.from({ length: 70 }, (_, index) => [`k${index}`, index])) }, isError: false },
      { type: "response", id: "task", command: "prompt", success: true, data: {} },
      { type: "agent_end", messages: Array.from({ length: 257 }, () => assistantMessage), willRetry: false },
      { type: "turn_end", message: assistantMessage, toolResults: Array.from({ length: 257 }, () => ({ role: "toolResult", toolCallId: "call", toolName: "bash", content: [], isError: false, timestamp: 1 })) },
    ]) expect(() => parseChildJsonLine(JSON.stringify(invalid))).toThrow(/schema|limit/u);
    expect(() => parseChildJsonLine(JSON.stringify({ type: "agent_settled", injected: true }))).toThrow("schema");
    expect(() => parseChildJsonLine("{" + "x".repeat(70_000))).toThrow("limit");
    const failed = childFailure("OPENAI_API_KEY=dummy-provider-value\r\nraw-provider-error");
    expect(failed.terminal).toBe("degraded");
    expect(JSON.stringify(failed)).toContain("/ca-doctor");
    expect(JSON.stringify(failed)).not.toContain("dummy-provider-value");
    expect(JSON.stringify(failed)).not.toContain("raw-provider-error");
  });

  test("spawns exact Node and withholds the task until a correlated handshake success", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild();
    const captures: Array<{ command: string; args: readonly string[]; options: Record<string, unknown> }> = [];
    let input = "";
    let capability = "";
    child.capability.on("data", (chunk) => { capability += chunk.toString("utf8"); });
    child.stdin.on("data", (chunk) => {
      input += chunk.toString("utf8");
      const records = input.trimEnd().split("\n");
      if (records.length === 1) {
        writeValidAttestation(child, request);
      } else if (records.length === 2) {
        const attestation = JSON.parse(records[1]!) as Record<string, unknown>;
        expect(attestation).toEqual({ type: "extension_ui_response", id: "ui-attestation-id", confirmed: true });
        child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
      } else if (records.length === 3) {
        const task = JSON.parse(records[2]!) as { id: string; message: string };
        child.stdout.write(JSON.stringify({ type: "response", id: task.id, command: "prompt", success: true }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_start" }) + "\n");
        child.stdout.write(JSON.stringify({ type: "message_end", message: assistantMessage }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_end", messages: [assistantMessage], willRetry: false }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
        child.close();
      }
    });
    const request = await materializedRequest();
    runnerMocks.spawn.mockImplementation((command: string, args: readonly string[], options: Record<string, unknown>) => {
      captures.push({ command, args, options });
      return child;
    });
    const result = await runPiChild(request as never, new AbortController().signal);
    expect(result).toMatchObject({ terminal: "completed", pid: 4242, output: "child-complete" });
    expect(captures).toHaveLength(1);
    expect(captures[0]).toMatchObject({ command: process.execPath, options: { detached: true, shell: false, cwd: request.cwd, stdio: ["pipe", "pipe", "pipe", "pipe"], windowsHide: true } });
    expect(runnerMocks.processTreeSpawnOptions).toHaveBeenCalledWith(process.platform);
    expect(runnerMocks.createProcessTreeCleanup).toHaveBeenCalledWith(child);
    expect(captures[0]!.args[0]).toBe(request.piCliPath);
    expect(JSON.stringify(captures)).not.toContain("task-secret-sentinel");
    const env = captures[0]!.options.env as NodeJS.ProcessEnv;
    expect(env.OPENAI_API_KEY).toBe("dummy-openai-value");
    expect(env.ANTHROPIC_API_KEY).toBeUndefined();
    expect(env.FARM_API_KEY).toBeUndefined();
    expect(input.trimEnd().split("\n")).toHaveLength(3);
    expect(capability).toBe("0123456789abcdef0123456789abcdef");
  });

  test("never fabricates completion when a valid lifecycle exits nonzero", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild();
    let input = "";
    child.stdin.on("data", (chunk) => {
      input += chunk.toString("utf8");
      const records = input.trimEnd().split("\n");
      if (records.length === 1) writeValidAttestation(child, request);
      else if (records.length === 2) {
        child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
      } else if (records.length === 3) {
        const task = JSON.parse(records[2]!) as { id: string };
        child.stdout.write(JSON.stringify({ type: "response", id: task.id, command: "prompt", success: true }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_start" }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_end", messages: [assistantMessage], willRetry: false }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
        child.close(7);
      }
    });
    const request = await materializedRequest();
    runnerMocks.spawn.mockReturnValue(child);
    expect(await runPiChild(request as never, new AbortController().signal)).toEqual({
      terminal: "degraded",
      diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
    });
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("protocol_error");
  });

  test("decodes JSONL correctly when a multibyte output character is split across chunks", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild();
    const unicodeAssistant = {
      ...assistantMessage,
      content: [{ type: "text", text: "child-🙂" }],
    };
    let input = "";
    child.stdin.on("data", (chunk) => {
      input += chunk.toString("utf8");
      const records = input.trimEnd().split("\n");
      if (records.length === 1) writeValidAttestation(child, request);
      else if (records.length === 2) {
        child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
      } else if (records.length === 3) {
        const task = JSON.parse(records[2]!) as { id: string };
        child.stdout.write(JSON.stringify({ type: "response", id: task.id, command: "prompt", success: true }) + "\n");
        child.stdout.write(JSON.stringify({ type: "agent_start" }) + "\n");
        const finalLine = Buffer.from(JSON.stringify({ type: "agent_end", messages: [unicodeAssistant], willRetry: false }) + "\n", "utf8");
        const emoji = Buffer.from("🙂", "utf8");
        const split = finalLine.indexOf(emoji) + 1;
        expect(split).toBeGreaterThan(0);
        child.stdout.write(finalLine.subarray(0, split));
        child.stdout.write(finalLine.subarray(split));
        child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
        child.close(0);
      }
    });
    const request = await materializedRequest();
    runnerMocks.spawn.mockReturnValue(child);
    expect(await runPiChild(request as never, new AbortController().signal)).toMatchObject({
      terminal: "completed",
      output: "child-🙂",
      pid: 4242,
    });
  });

  test("never writes task content after failed or uncorrelated handshake acknowledgement", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    for (const response of [
      { type: "response", id: "wrong-handshake", command: "prompt", success: true },
      { type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: false, error: "OPENAI_API_KEY=dummy-provider-value" },
    ]) {
      const child = new FakeChild();
      let input = "";
      child.stdin.on("data", (chunk) => {
        input += chunk.toString("utf8");
        const count = input.trimEnd().split("\n").length;
        if (count === 1) writeValidAttestation(child, request);
        if (count === 2) {
          child.stdout.write(JSON.stringify(response) + "\n");
          child.close(1);
        }
      });
      const request = await materializedRequest();
      runnerMocks.spawn.mockReturnValue(child);
      const result = await runPiChild(request as never, new AbortController().signal);
      expect(result.terminal).toBe("degraded");
      expect(JSON.stringify(result)).not.toContain("dummy-provider-value");
      expect(input).not.toContain("task-secret-sentinel");
      expect(input.trimEnd().split("\n")).toHaveLength(2);
    }
  });

  test("requires correlated task acceptance and an ordered post-task lifecycle before completion", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const scenarios = [
      [{ type: "agent_settled" }],
      [
        { type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", command: "prompt", success: true },
        { type: "message_end", message: assistantMessage },
      ],
      [
        { type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", command: "prompt", success: true },
        { type: "agent_settled" },
      ],
      [
        { type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", command: "prompt", success: true },
        { type: "agent_start" },
        { type: "agent_settled" },
      ],
    ] as const;
    for (const recordsAfterHandshake of scenarios) {
      const child = new FakeChild(true);
      let input = "";
      child.stdin.on("data", (chunk) => {
        input += chunk.toString("utf8");
        const count = input.trimEnd().split("\n").length;
        if (count === 1) writeValidAttestation(child, request);
        if (count === 2) {
          child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
          for (const record of recordsAfterHandshake) child.stdout.write(JSON.stringify(record) + "\n");
          setImmediate(() => child.close());
        }
      });
      const request = await materializedRequest();
      runnerMocks.spawn.mockReturnValue(child);
      const result = await runPiChild(request as never, new AbortController().signal);
      expect(result).toEqual({ terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." });
      expect(result).not.toHaveProperty("output");
    }
  });

  test("requires one exact digest-only RPC confirm attestation before handshake acknowledgement", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const request = await materializedRequest();
    const expected = { terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." };
    const valid = {
      type: "extension_ui_request", id: "ui-attestation-id", method: "confirm",
      title: ATTESTATION_TITLE, message: expectedAttestation(request), timeout: ATTESTATION_TIMEOUT_MS,
    };
    for (const exposed of [valid.title, valid.message, JSON.stringify(valid)]) {
      expect(exposed).not.toContain(FIXED_NONCE);
      expect(exposed).not.toContain(FIXED_CHALLENGE);
      expect(exposed).not.toContain("dummy-openai-value");
    }
    const invalidRecords = [
      { type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true },
      { ...valid, id: "" },
      { ...valid, method: "select" },
      { ...valid, title: "wrong title" },
      { ...valid, message: "0".repeat(64) },
      { ...valid, timeout: 1 },
      { ...valid, injected: true },
      Object.fromEntries(Object.entries(valid).filter(([key]) => key !== "timeout")),
    ];
    for (const invalidRecord of invalidRecords) {
      const child = new FakeChild(true);
      let input = "";
      child.stdin.on("data", (chunk) => {
        input += chunk.toString("utf8");
        child.stdout.write(JSON.stringify(invalidRecord) + "\n");
        setImmediate(() => child.close(1));
      });
      runnerMocks.spawn.mockReturnValue(child);
      expect(await runPiChild(request as never, new AbortController().signal)).toEqual(expected);
      expect(input.trimEnd().split("\n")).toHaveLength(1);
    }

    const replayChild = new FakeChild(true);
    let replayInput = "";
    replayChild.stdin.on("data", (chunk) => {
      replayInput += chunk.toString("utf8");
      if (replayInput.trimEnd().split("\n").length === 1) {
        replayChild.stdout.write(JSON.stringify(valid) + "\n" + JSON.stringify(valid) + "\n");
        setImmediate(() => replayChild.close(1));
      }
    });
    runnerMocks.spawn.mockReturnValue(replayChild);
    expect(await runPiChild(request as never, new AbortController().signal)).toEqual(expected);
    expect(replayInput).not.toContain("task-secret-sentinel");
    expect(replayInput.trimEnd().split("\n")).toHaveLength(2);
  });

  test("returns the same fixed degraded result for every isolated-runner failure branch", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const expected = { terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." };
    const request = await materializedRequest();
    let spawnCalls = 0;
    runnerMocks.spawn.mockImplementation(() => { spawnCalls += 1; throw new Error("must not spawn"); });
    expect(await runPiChild({ ...request, nodePath: "node" } as never, new AbortController().signal)).toEqual(expected);
    expect(spawnCalls).toBe(0);

    const preAborted = new AbortController();
    preAborted.abort();
    const abortedRequest = await materializedRequest();
    runnerMocks.spawn.mockImplementation(() => { spawnCalls += 1; return new FakeChild(true); });
    expect(await runPiChild({ ...abortedRequest, timeoutMs: 5 } as never, preAborted.signal)).toEqual(expected);
    expect(spawnCalls).toBe(0);

    const spawnRequest = await materializedRequest();
    runnerMocks.spawn.mockImplementation(() => { throw new Error("spawn raw-secret-sentinel"); });
    expect(await runPiChild(spawnRequest as never, new AbortController().signal)).toEqual(expected);

    const runEventFailure = async (
      trigger: (child: FakeChild, controller: AbortController) => void,
      timeoutMs = 5_000,
    ) => {
      const child = new FakeChild(true);
      const controller = new AbortController();
      const baseRequest = await materializedRequest();
      const failureRequest = { ...baseRequest, timeoutMs };
      runnerMocks.spawn.mockImplementation(() => {
        setImmediate(() => trigger(child, controller));
        return child;
      });
      const result = await runPiChild(failureRequest as never, controller.signal);
      expect(result).toEqual(expected);
      expect(JSON.stringify(result)).not.toContain("raw-secret-sentinel");
    };
    await runEventFailure((child) => child.emit("error", new Error("raw-secret-sentinel")));
    await runEventFailure((_child, controller) => controller.abort());
    await runEventFailure((child) => child.stdout.write("{malformed raw-secret-sentinel}\n"));
    await runEventFailure((child) => child.stdout.write("x".repeat(65_537)));
    await runEventFailure((child) => child.stdout.write("x".repeat(1_048_577)));
    await runEventFailure((child) => child.stderr.write("raw-secret-sentinel" + "x".repeat(16_385)));
    await runEventFailure((child) => child.close(7));
    await runEventFailure(() => { /* timeout is the trigger */ }, 1);
  });

  test.each([
    ["cancelled", (child: FakeChild, controller: AbortController) => controller.abort()],
    ["protocol_error", (child: FakeChild) => child.stdout.write("{malformed}\n")],
    ["protocol_overflow", (child: FakeChild) => child.stdout.write("x".repeat(65_537))],
    ["startup_failure", (child: FakeChild) => child.emit("error", new Error("launch refused"))],
  ] as const)("awaits one idempotent %s tree cleanup even when close never arrives", async (reason, trigger) => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild(false);
    const controller = new AbortController();
    const request = await materializedRequest();
    runnerMocks.spawn.mockImplementation(() => {
      setImmediate(() => {
        trigger(child, controller);
        child.emit("error", new Error("duplicate failure trigger"));
      });
      return child;
    });
    const observed = await Promise.race([
      runPiChild(request as never, controller.signal),
      new Promise<"unresolved">((resolve) => setTimeout(() => resolve("unresolved"), 250)),
    ]);
    expect(observed).toEqual({ terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." });
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledOnce();
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith(reason);
    expect(child.killCalls).toEqual([]);
  });

  test("maps timeout and early close to verified cleanup and resolves despite kill refusal", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const expected = { terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." };
    runnerMocks.cleanupTerminate.mockResolvedValue({
      escalated: true,
      reason: "timeout",
      state: "refused",
      verified: false,
    });
    const timeoutChild = new FakeChild(false);
    runnerMocks.spawn.mockReturnValue(timeoutChild);
    const timeoutRequest = await materializedRequest();
    const timeoutObserved = await Promise.race([
      runPiChild({ ...timeoutRequest, timeoutMs: 1 } as never, new AbortController().signal),
      new Promise<"unresolved">((resolve) => setTimeout(() => resolve("unresolved"), 250)),
    ]);
    expect(timeoutObserved).toEqual(expected);
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("timeout");

    runnerMocks.cleanupTerminate.mockClear();
    runnerMocks.cleanupTerminate.mockResolvedValue({
      escalated: false,
      reason: "protocol_error",
      state: "already_exited",
      verified: true,
    });
    const closedChild = new FakeChild(false);
    runnerMocks.spawn.mockImplementation(() => {
      setImmediate(() => closedChild.close(7));
      return closedChild;
    });
    const closeRequest = await materializedRequest();
    expect(await runPiChild(closeRequest as never, new AbortController().signal)).toEqual(expected);
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledOnce();
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("protocol_error");
  });

  test("fails closed before capability or handshake bytes when containment readiness is unavailable", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild(false);
    let stdin = "";
    let capability = "";
    child.stdin.on("data", (chunk) => { stdin += chunk.toString("utf8"); });
    child.capability.on("data", (chunk) => { capability += chunk.toString("utf8"); });
    runnerMocks.spawn.mockReturnValue(child);
    runnerMocks.cleanupReady.mockResolvedValue(false);
    const request = await materializedRequest();
    expect(await runPiChild(request as never, new AbortController().signal)).toEqual({
      terminal: "degraded",
      diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
    });
    expect(stdin).toBe("");
    expect(capability).toBe("");
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("startup_failure");
  });

  test.each(["spawn", "readiness"] as const)(
    "replays cancellation that lands during async %s before any capability or task bytes",
    async (phase) => {
      const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
      const child = new FakeChild(false);
      const controller = new AbortController();
      let stdin = "";
      let capability = "";
      child.stdin.on("data", (chunk) => { stdin += chunk.toString("utf8"); });
      child.capability.on("data", (chunk) => { capability += chunk.toString("utf8"); });
      if (phase === "spawn") {
        runnerMocks.spawnProcessTree.mockImplementationOnce(async () => {
          controller.abort();
          return child;
        });
      } else {
        runnerMocks.spawn.mockReturnValue(child);
        runnerMocks.cleanupReady.mockImplementationOnce(async () => {
          controller.abort();
          return true;
        });
      }
      const request = await materializedRequest();
      expect(await runPiChild(request as never, controller.signal)).toEqual({
        terminal: "degraded",
        diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
      });
      expect(stdin).toBe("");
      expect(capability).toBe("");
      expect(runnerMocks.cleanupTerminate).toHaveBeenCalledOnce();
      expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("cancelled");
      runnerMocks.cleanupTerminate.mockClear();
    },
  );

  test("does not launch when cancellation lands during canonical validation", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const controller = new AbortController();
    const request = await materializedRequest();
    runnerMocks.resolveRuntimeIdentity.mockImplementationOnce(async (candidate: string) => {
      controller.abort();
      return { cliEntry: candidate, packageRoot: resolve(dirname(candidate), ".."), version: "0.80.10" };
    });
    expect(await runPiChild(request as never, controller.signal)).toEqual({
      terminal: "degraded",
      diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
    });
    expect(runnerMocks.spawnProcessTree).not.toHaveBeenCalled();
    expect(runnerMocks.createProcessTreeCleanup).not.toHaveBeenCalled();
  });

  test("detects a contained child that closed before listener installation without waiting for timeout", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild(false);
    child.close(7);
    runnerMocks.spawn.mockReturnValue(child);
    const request = await materializedRequest();
    const observed = await Promise.race([
      runPiChild(request as never, new AbortController().signal),
      new Promise<"unresolved">((resolve) => setTimeout(() => resolve("unresolved"), 250)),
    ]);
    expect(observed).toEqual({
      terminal: "degraded",
      diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
    });
    expect(runnerMocks.cleanupTerminate).toHaveBeenCalledWith("startup_failure");
  });

  test("public runPiChild is a two-argument production-bound entry with no dependency override", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const request = await materializedRequest();
    const injectedSpawn = vi.fn(() => new FakeChild());
    runnerMocks.spawn.mockImplementation(() => { throw new Error("production spawn selected"); });
    const result = await (runPiChild as unknown as (...args: unknown[]) => Promise<unknown>)(
      request,
      new AbortController().signal,
      { spawn: injectedSpawn, validation: { packageRoot: request.cwd } },
    );
    expect(runPiChild.length).toBe(2);
    expect(result).toEqual({ terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." });
    expect(runnerMocks.spawn).toHaveBeenCalledOnce();
    expect(injectedSpawn).not.toHaveBeenCalled();
  });

  test("routes stdin EPIPE and early close before or after handshake through fixed degraded", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const expected = { terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." };
    for (const afterHandshake of [false, true]) {
      const child = new FakeChild(true);
      let input = "";
      child.stdin.on("data", (chunk) => {
        input += chunk.toString("utf8");
        const count = input.trimEnd().split("\n").length;
        if (afterHandshake && count === 1) {
          writeValidAttestation(child, request);
          return;
        }
        if (afterHandshake && count === 2) {
          child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
        }
        child.stdin.destroy(new Error("EPIPE raw-secret-sentinel"));
        setImmediate(() => child.close(1));
      });
      const request = await materializedRequest();
      runnerMocks.spawn.mockReturnValue(child);
      const result = await runPiChild(request as never, new AbortController().signal);
      expect(result).toEqual(expected);
      expect(JSON.stringify(result)).not.toContain("raw-secret-sentinel");
    }
  });

  test("fails degraded without the inherited fd3 capability pipe", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const child = new FakeChild(true);
    (child.stdio as unknown as Array<unknown>)[3] = null;
    const request = await materializedRequest();
    runnerMocks.spawn.mockReturnValue(child);
    const result = await runPiChild(request as never, new AbortController().signal);
    expect(result).toEqual({ terminal: "degraded", diagnostic: "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor." });
  });

  test("requires a successful final assistant bound to the requested provider and model", async () => {
    const { runPiChild } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const failures = [
      { ...assistantMessage, stopReason: "error", errorMessage: "provider failed" },
      { ...assistantMessage, stopReason: "aborted", errorMessage: "aborted" },
      { ...assistantMessage, stopReason: "length" },
      { ...assistantMessage, stopReason: "toolUse" },
      { ...assistantMessage, provider: "anthropic" },
      { ...assistantMessage, model: "wrong-model" },
      { ...assistantMessage, content: [] },
    ];
    for (const finalMessage of failures) {
      const child = new FakeChild();
      let input = "";
      child.stdin.on("data", (chunk) => {
        input += chunk.toString("utf8");
        const records = input.trimEnd().split("\n");
        if (records.length === 1) {
          writeValidAttestation(child, request);
        } else if (records.length === 2) {
          child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee-handshake", command: "prompt", success: true }) + "\n");
        } else if (records.length === 3) {
          child.stdout.write(JSON.stringify({ type: "response", id: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", command: "prompt", success: true }) + "\n");
          child.stdout.write(JSON.stringify({ type: "agent_start" }) + "\n");
          child.stdout.write(JSON.stringify({ type: "message_end", message: finalMessage }) + "\n");
          child.stdout.write(JSON.stringify({ type: "agent_end", messages: [finalMessage], willRetry: false }) + "\n");
          child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
          child.close();
        }
      });
      const request = await materializedRequest();
      runnerMocks.spawn.mockReturnValue(child);
      const result = await runPiChild(request as never, new AbortController().signal);
      expect(result.terminal).toBe("degraded");
      expect(result).not.toHaveProperty("output");
    }
  });

  test("binds launch paths to current Node, supported Pi identity, and the generated ca-pi role catalog", async () => {
    const { validateChildLaunch } = await loadModule<RunnerModule>("../src/runner.ts", "runner");
    const request = await materializedPathRequest();
    const validation = validationFor(request);
    await expect(validateChildLaunch(request as never, validation as never)).resolves.toMatchObject({ nodePath: process.execPath, model: "gpt-test" });

    const wrongNode = resolve(dirname(request.cwd), "wrong-node.exe");
    await writeFile(wrongNode, "counterfeit node\n", "utf8");
    await expect(validateChildLaunch({ ...request, nodePath: wrongNode } as never, validation as never)).rejects.toThrow(/Node|identity/u);

    const wrongCli = resolve(dirname(request.cwd), "counterfeit-pi.js");
    await writeFile(wrongCli, "counterfeit pi\n", "utf8");
    await expect(validateChildLaunch({ ...request, piCliPath: wrongCli } as never, validation as never)).rejects.toThrow(/Pi|identity|counterfeit/u);
    await expect(validateChildLaunch(request as never, { ...validation, resolveRuntimeIdentity: async () => ({ cliEntry: request.piCliPath, packageRoot: dirname(request.piCliPath), version: "0.80.7" }) } as never)).rejects.toThrow(/0\.80\.5|0\.80\.6|supported/u);

    const outside = resolve(dirname(request.cwd), "outside.md");
    await writeFile(outside, "outside\n", "utf8");
    await expect(validateChildLaunch({ ...request, charterPath: outside } as never, validation as never)).rejects.toThrow(/role|package|catalog|resource/u);
    await expect(validateChildLaunch({ ...request, cwd: dirname(request.childExtensionPath) } as never, validation as never)).rejects.toThrow(/working directory|child|inside/u);

    const packageRoot = validation.packageRoot as string;
    const escapedDirectory = resolve(dirname(request.cwd), "escaped-extensions");
    await mkdir(escapedDirectory, { recursive: true });
    await writeFile(resolve(escapedDirectory, "codearbiter-child.js"), "escaped\n", "utf8");
    await rm(resolve(packageRoot, "extensions"), { recursive: true, force: true });
    await symlink(escapedDirectory, resolve(packageRoot, "extensions"), process.platform === "win32" ? "junction" : "dir");
    await expect(validateChildLaunch(request as never, validation as never)).rejects.toThrow(/escape|package|resource/u);
  });

  test("generates exact author/reviewer roles from canonical charters", async () => {
    const { loadRoleCatalog } = await loadModule<RolesModule>("../src/roles.ts", "role catalog");
    const packageRoot = resolve(import.meta.dirname, "..", "..");
    const roles = await loadRoleCatalog(packageRoot);
    expect(roles.get("backend-author")).toEqual({
      name: "backend-author", classification: "author", charterPath: "agents/backend-author.md",
      skillPaths: ["routines/tdd/SKILL.md"], tools: ["read", "bash", "edit", "write"],
    });
    expect(roles.get("security-reviewer")).toMatchObject({ classification: "reviewer", tools: ["read", "bash"] });
    expect([...roles.values()].every((role) => ["author", "reviewer"].includes(role.classification))).toBe(true);
  });
});

class FakePi {
  readonly handlers = new Map<string, Array<(event: Record<string, unknown>, context: Record<string, unknown>) => unknown>>();
  readonly commands = new Map<string, (args: string, context: Record<string, unknown>) => unknown>();
  readonly definitions = new Map<string, { name: string; execute: (...args: unknown[]) => Promise<Record<string, unknown>> }>();
  registerCommand(name: string, options: { handler: (args: string, context: Record<string, unknown>) => unknown }) { this.commands.set(name, options.handler); }
  registerTool(tool: { name: string; execute: (...args: unknown[]) => Promise<Record<string, unknown>> }) { this.definitions.set(tool.name, tool); }
  on(event: string, handler: (event: Record<string, unknown>, context: Record<string, unknown>) => unknown) { this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]); }
  getActiveTools() { return ["read", "bash", "edit", "write"]; }
  getAllTools() { return [...this.definitions].map(([name]) => ({ name, sourceInfo: { path: "C:/package/extensions/codearbiter-child.js" } })); }
  sendUserMessage() { throw new Error("child handshake must not relay task text through extension APIs"); }
  async emit(event: string, value: Record<string, unknown>, context: Record<string, unknown> = {}) {
    const results = [];
    for (const handler of this.handlers.get(event) ?? []) results.push(await handler(value, context));
    return results;
  }
}

function childContext(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    cwd: "C:/repo",
    mode: "rpc",
    hasUI: true,
    model: { provider: "openai", id: "gpt-test" },
    isProjectTrusted: () => false,
    signal: new AbortController().signal,
    ui: {
      confirm: async () => true,
      notify() {},
      setStatus() {},
    },
    ...overrides,
  };
}

describe("Task 6 enforcement-only child adapter", () => {
  test("keeps mutators blocked for an ambient marker until one private nonce is consumed", async () => {
    const { installChild } = await loadModule<ChildModule>("../src/child-extension.ts", "child adapter");
    const pi = new FakePi();
    const executions: string[] = [];
    installChild(pi as never, {
      marker: "1", expectedNonce: "0123456789abcdef0123456789abcdef", cwd: "C:/repo", wrapperSourcePath: "C:/package/extensions/codearbiter-child.js",
      descriptor: { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" },
      bridge: { call: async (request: { tool?: string }) => request.tool === "bash" ? { version: 1, outcome: "block", ruleId: "H-03", message: "Blocked by H-03" } : { version: 1, outcome: "allow" } },
      factories: Object.fromEntries(["read", "bash", "edit", "write"].map((name) => [name, () => ({ name, execute: async () => { executions.push(name); return { content: [] }; } })])),
    } as never);
    await pi.emit("session_start", {}, { cwd: "C:/repo", signal: new AbortController().signal, ui: { notify() {}, setStatus() {} } });
    expect((await pi.emit("tool_call", { toolName: "bash", input: { command: "git add -A" } }))[0]).toMatchObject({ block: true });
    const handshake = pi.commands.get("codearbiter-internal-child-handshake");
    expect(handshake).toBeTypeOf("function");
    const confirm = vi.fn(async () => true);
    const attestationContext = childContext({ ui: { confirm, notify() {}, setStatus() {} } });
    await handshake!(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, attestationContext);
    expect(confirm).toHaveBeenCalledWith(
      ATTESTATION_TITLE,
      expectedAttestation({ cwd: "C:/repo", provider: "openai", model: "gpt-test", tools: ["read", "bash", "edit", "write"] }),
      { timeout: ATTESTATION_TIMEOUT_MS },
    );
    await expect(handshake!(`fedcba9876543210fedcba9876543210 ${FIXED_CHALLENGE}`, attestationContext)).rejects.toThrow("already consumed");
    await pi.emit("session_start", {}, { cwd: "C:/repo", signal: new AbortController().signal, ui: { notify() {}, setStatus() {} } });
    await expect(handshake!(`fedcba9876543210fedcba9876543210 ${FIXED_CHALLENGE}`, attestationContext)).rejects.toThrow("already consumed");
    await expect(pi.definitions.get("bash")!.execute("call", { command: "git add -A" })).rejects.toThrow("not ready");
    expect(executions).toEqual([]);
  });

  test("missing marker, malformed nonce, and replay never release enforcement", async () => {
    const { installChild } = await loadModule<ChildModule>("../src/child-extension.ts", "child adapter");
    for (const marker of [undefined, "0"]) {
      const pi = new FakePi();
      installChild(pi as never, { marker, expectedNonce: "0123456789abcdef0123456789abcdef" } as never);
      const handshake = pi.commands.get("codearbiter-internal-child-handshake")!;
      await expect(handshake(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow("marker");
      expect((await pi.emit("tool_call", { toolName: "bash" }))[0]).toMatchObject({ block: true });
    }
    const pi = new FakePi();
    installChild(pi as never, { marker: "1", expectedNonce: "0123456789abcdef0123456789abcdef" } as never);
    const handshake = pi.commands.get("codearbiter-internal-child-handshake")!;
    await expect(handshake(`short ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow("nonce");
    await expect(handshake(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow("enforcement is unavailable");
    await expect(handshake(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow("already consumed");
    expect((await pi.emit("tool_call", { toolName: "bash" }))[0]).toMatchObject({ block: true });
  });

  test("missing, malformed, or mismatched fd3 capability never releases enforcement", async () => {
    const { installChild, readChildCapability } = await loadModule<ChildModule>("../src/child-extension.ts", "child adapter");
    await expect(readChildCapability(Readable.from([]))).rejects.toThrow("malformed");
    await expect(readChildCapability(Readable.from(["short"]))).rejects.toThrow("malformed");
    await expect(readChildCapability(Readable.from(["x".repeat(33)]))).rejects.toThrow("oversized");
    const failedPipe = new Readable({ read() { this.destroy(new Error("raw pipe error")); } });
    await expect(readChildCapability(failedPipe)).rejects.toThrow("unavailable");
    await expect(readChildCapability(Readable.from(["0123456789abcdef0123456789abcdef"]))).resolves.toBe("0123456789abcdef0123456789abcdef");
    for (const expectedNonce of [undefined, "short", "fedcba9876543210fedcba9876543210"]) {
      const pi = new FakePi();
      installChild(pi as never, { marker: "1", expectedNonce } as never);
      const handshake = pi.commands.get("codearbiter-internal-child-handshake")!;
      await expect(handshake(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow(/capability|match|malformed/u);
      expect((await pi.emit("tool_call", { toolName: "bash" }))[0]).toMatchObject({ block: true });
    }
  });

  test("attestation context mismatch, unavailable UI, or rejected confirmation never marks ready", async () => {
    const { installChild } = await loadModule<ChildModule>("../src/child-extension.ts", "child adapter");
    const contexts = [
      childContext({ mode: "tui" }),
      childContext({ hasUI: false }),
      childContext({ model: undefined }),
      childContext({ isProjectTrusted: () => true }),
      childContext({ ui: { confirm: async () => false, notify() {}, setStatus() {} } }),
    ];
    for (const context of contexts) {
      const pi = new FakePi();
      installChild(pi as never, {
        marker: "1", expectedNonce: FIXED_NONCE, cwd: "C:/repo", wrapperSourcePath: "C:/package/extensions/codearbiter-child.js",
        descriptor: { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" },
        bridge: { call: async () => ({ version: 1, outcome: "allow" }) },
        factories: Object.fromEntries(["read", "bash", "edit", "write"].map((name) => [name, () => ({ name, execute: async () => ({ content: [] }) })])),
      } as never);
      const handshake = pi.commands.get("codearbiter-internal-child-handshake")!;
      await expect(handshake(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, context)).rejects.toThrow(/attestation|context|confirm|blocked/u);
      expect((await pi.emit("tool_call", { toolName: "bash" }))[0]).toMatchObject({ block: true });
    }
    const pi = new FakePi();
    pi.getActiveTools = () => ["read", "bash", "unknown"];
    installChild(pi as never, {
      marker: "1", expectedNonce: FIXED_NONCE, cwd: "C:/repo", wrapperSourcePath: "C:/package/extensions/codearbiter-child.js",
      descriptor: { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" },
      bridge: { call: async () => ({ version: 1, outcome: "allow" }) },
      factories: Object.fromEntries(["read", "bash", "edit", "write"].map((name) => [name, () => ({ name, execute: async () => ({ content: [] }) })])),
    } as never);
    await expect(pi.commands.get("codearbiter-internal-child-handshake")!(`${FIXED_NONCE} ${FIXED_CHALLENGE}`, childContext())).rejects.toThrow(/attestation|tools|context/u);
  });

  test("registers no public aliases, dispatch, farm, or recursive orchestration", async () => {
    const { installChild } = await loadModule<ChildModule>("../src/child-extension.ts", "child adapter");
    const pi = new FakePi();
    installChild(pi as never, { marker: undefined } as never);
    expect([...pi.commands.keys()]).toEqual(["codearbiter-internal-child-handshake"]);
    expect([...pi.commands.keys()].some((name) => name.startsWith("ca-") || /dispatch|farm|agent/u.test(name))).toBe(false);
    expect([...pi.definitions.keys()].some((name) => /dispatch|farm|agent/u.test(name))).toBe(false);
  });
});
