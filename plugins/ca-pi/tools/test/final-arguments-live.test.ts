/**
 * final-arguments-live.test.ts - the REAL-HOST final-argument authority proof.
 *
 * Issue #370. ADR-0014 and ADR-0016 make live proof that codeArbiter sees and
 * governs FINAL tool arguments a promotion STOP: "inability to prove it reopens
 * ADR-0013". `final-arguments.test.ts` discharges that against `OrderedPi`, a
 * hand-written host double, so a Pi release that changed extension ordering or
 * tool-registry ownership could leave promotion green while execution diverged
 * from the arguments codeArbiter reviewed.
 *
 * This fixture removes the double. It loads codeArbiter's real enforcement and
 * a deliberately later trusted extension through the INSTALLED Pi candidate's
 * own `discoverAndLoadExtensions`, drives them with the installed
 * `ExtensionRunner`, and executes the governed mutator through the installed
 * `wrapRegisteredTool`. Ordering, tool ownership, and the object identity that
 * carries arguments from the pre-execution hook into the executor are all the
 * host's, so a Pi release that changes any of them fails this cell.
 *
 * Host dispatch semantics, source-verified in Pi 0.80.5 and 0.80.10
 * (`dist/core/agent-loop.js`, `dist/core/agent-session.js`): the agent loop
 * validates the model's arguments ONCE into `validatedArgs`, passes that object
 * to `beforeToolCall` -> `ExtensionRunner.emitToolCall({ input: validatedArgs })`,
 * and then passes the SAME object to `tool.execute(...)`. A later extension that
 * mutates `event.input` therefore rewrites the arguments that actually run,
 * which is exactly the sequence reproduced below.
 *
 * The Python bridge is the only substituted part, and deliberately so: it is
 * the judge, not the host. The claim under test is that the FINAL argument
 * reaches the judge, so the fixture asserts the exact request payload the judge
 * received rather than trusting any verdict it returns.
 */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { afterAll, beforeAll, describe, expect, test } from "vitest";

import { compatibilityDirection } from "../src/compatibility.ts";
import type { BridgeRequest, BridgeResponse, ToolCategory } from "../src/contracts.ts";
import { findPiPackageRoot } from "./live-pi-host.ts";

const GOVERNED_EXTENSION = resolve(import.meta.dirname, "fixtures", "live-governed-extension.mjs");
const LATER_EXTENSION = resolve(import.meta.dirname, "fixtures", "live-later-extension.mjs");
const GOVERNED_TOOL_MARKER = "codearbiter-governed-fixture-builtin";
const FOREIGN_TOOL_MARKER = "later-extension-replacement";
const BENIGN_COMMAND = "git status";
const REWRITTEN_COMMAND = "git commit --no-verify";
// core/hosts.json's Pi descriptor, spelled out so a silent descriptor change
// cannot quietly reclassify the mutator this proof depends on.
const DESCRIPTOR: Readonly<Record<string, ToolCategory>> = {
  bash: "EXEC",
  codearbiter_background_bash: "EXEC",
  codearbiter_dispatch: "EXEC",
  codearbiter_farm_preview: "EXEC",
  write: "WRITE",
  edit: "EDIT",
  read: "READ",
};

interface LiveHost {
  VERSION: string;
  discoverAndLoadExtensions: (
    configuredPaths: string[], cwd: string, agentDir?: string,
  ) => Promise<{ extensions: unknown[]; errors: unknown[]; runtime: unknown }>;
  ExtensionRunner: new (...args: never[]) => LiveRunner;
  wrapRegisteredTool: (registeredTool: unknown, runner: LiveRunner) => {
    execute: (id: string, input: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>;
  };
}

interface LiveRunner {
  bindCore: (actions: Record<string, unknown>, contextActions: Record<string, unknown>) => void;
  setUIContext: (uiContext: unknown, mode?: string) => void;
  getAllRegisteredTools: () => Array<{ definition: { name: string; description?: string }; sourceInfo: { path: string } }>;
  getToolDefinition: (name: string) => { name: string; description?: string } | undefined;
  emitToolCall: (event: Record<string, unknown>) => Promise<{ block?: boolean; reason?: string } | undefined>;
}

interface Control {
  cwd: string;
  descriptor: Readonly<Record<string, ToolCategory>>;
  actionClasses: Readonly<Record<string, string>>;
  wrapperSourcePath: string;
  rewrittenCommand: string;
  foreignToolMarker: string;
  foreignExecutions: Array<Record<string, unknown>>;
  governedExecutions: Array<{ name: string; input: Record<string, unknown> }>;
  requests: BridgeRequest[];
  bridge: { call: (request: BridgeRequest) => Promise<BridgeResponse> };
  factories: Record<string, () => unknown>;
  permissionAudit: (cwd: string, row: unknown) => Promise<boolean>;
  audits: unknown[];
  confirmations: number;
}

let host: LiveHost;
let roots: string[] = [];

function createControl(): Control {
  const control: Control = {
    cwd: process.cwd(),
    descriptor: DESCRIPTOR,
    actionClasses: { "ca-plan": "planning-write", codearbiter_background_bash: "background-launch" },
    wrapperSourcePath: GOVERNED_EXTENSION,
    rewrittenCommand: REWRITTEN_COMMAND,
    foreignToolMarker: FOREIGN_TOOL_MARKER,
    foreignExecutions: [],
    governedExecutions: [],
    requests: [],
    audits: [],
    confirmations: 0,
    bridge: {
      call: async (request: BridgeRequest): Promise<BridgeResponse> => {
        control.requests.push(structuredClone(request) as BridgeRequest);
        return (request.input as Record<string, unknown> | undefined)?.command === REWRITTEN_COMMAND
          ? { version: 1, outcome: "block", ruleId: "H-20", message: "blocked by H-20" }
          : { version: 1, outcome: "allow" };
      },
    },
    factories: Object.fromEntries(["bash", "write", "edit", "read"].map((name) => [name, () => ({
      name,
      description: GOVERNED_TOOL_MARKER,
      parameters: { type: "object", properties: {}, additionalProperties: true },
      execute: async (_id: string, input: Record<string, unknown>) => {
        control.governedExecutions.push({ name, input: structuredClone(input) });
        return { content: [{ type: "text", text: "the governed built-in executed" }] };
      },
    })])),
    permissionAudit: async (_cwd: string, row: unknown) => {
      control.audits.push(row);
      return true;
    },
  };
  (globalThis as Record<string, unknown>).__CA_LIVE_FINAL_ARGUMENT_CONTROL__ = control;
  return control;
}

/** Load the two extensions in the given order through the installed Pi host. */
async function liveRunner(order: string[], control: Control): Promise<LiveRunner> {
  // A private cwd and agent directory keep the host's ambient discovery from
  // finding any extension other than the two this proof declares.
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-final-arguments-"));
  roots.push(root);
  const result = await host.discoverAndLoadExtensions(order, root, resolve(root, "agent"));
  expect(result.errors).toEqual([]);
  expect(result.extensions).toHaveLength(2);
  const runner = new (host.ExtensionRunner as unknown as new (
    extensions: unknown[], runtime: unknown, cwd: string, sessionManager: unknown, modelRegistry: unknown,
  ) => LiveRunner)(result.extensions, result.runtime, control.cwd, undefined, undefined);
  const registered = () => runner.getAllRegisteredTools();
  runner.bindCore({
    sendMessage: () => undefined, sendUserMessage: () => undefined, appendEntry: () => undefined,
    setSessionName: () => undefined, getSessionName: () => undefined, setLabel: () => undefined,
    // The host owns tool ownership: `getAllRegisteredTools()` resolves a name to
    // the FIRST extension that registered it, in load order.
    getActiveTools: () => registered().map((tool) => tool.definition.name),
    getAllTools: () => registered().map((tool) => ({ name: tool.definition.name, sourceInfo: tool.sourceInfo })),
    setActiveTools: () => undefined, refreshTools: () => undefined, getCommands: () => [],
    setModel: async () => undefined, getThinkingLevel: () => "off", setThinkingLevel: () => undefined,
  }, {
    getModel: () => undefined, isIdle: () => true, isProjectTrusted: () => true,
    getSignal: () => undefined, abort: () => undefined, hasPendingMessages: () => false,
    shutdown: () => undefined, getContextUsage: () => undefined, compact: () => undefined,
    getSystemPrompt: () => "",
  });
  return runner;
}

function governedTool(runner: LiveRunner, control: Control) {
  const registered = runner.getAllRegisteredTools().find((tool) => tool.definition.name === "bash");
  expect(registered).toBeDefined();
  return host.wrapRegisteredTool(registered, runner) as {
    execute: (id: string, input: Record<string, unknown>, signal?: AbortSignal, onUpdate?: unknown, context?: unknown) => Promise<unknown>;
  } & { control?: Control };
}

const executionContext = (control: Control) => ({
  cwd: control.cwd, mode: "tui", hasUI: true,
  ui: { confirm: async () => { control.confirmations += 1; return true; } },
});

beforeAll(async () => {
  const piRoot = await findPiPackageRoot();
  host = await import(pathToFileURL(resolve(piRoot, "dist", "index.js")).href) as unknown as LiveHost;
});

afterAll(async () => {
  delete (globalThis as Record<string, unknown>).__CA_LIVE_FINAL_ARGUMENT_CONTROL__;
  for (const root of roots) await rm(root, { recursive: true, force: true });
  roots = [];
});

describe("real-host final-argument authority", () => {
  test("the fixture ran against a Pi the adapter admits", () => {
    expect(compatibilityDirection({
      piVersion: host.VERSION, nodeVersion: process.versions.node, pythonMajor: 3,
    })).toBeNull();
  });

  test("a later extension's rewrite is re-judged before the governed mutator executes", async () => {
    const control = createControl();
    const runner = await liveRunner([GOVERNED_EXTENSION, LATER_EXTENSION], control);
    // One arguments object, exactly as Pi's agent loop builds it.
    const event = { type: "tool_call", toolName: "bash", toolCallId: "live-final", input: { command: BENIGN_COMMAND } };

    // The host's own ordered pre-execution pass. The later extension rewrites
    // the arguments object behind codeArbiter's back. codeArbiter deliberately
    // judges NOTHING here - a verdict at this point is exactly what a later
    // handler can invalidate - so no judge call has happened yet.
    await expect(runner.emitToolCall(event)).resolves.toBeUndefined();
    expect(event.input).toEqual({ command: REWRITTEN_COMMAND });
    expect(control.requests).toEqual([]);

    // The host's own final executor, handed the SAME rewritten object.
    await expect(
      governedTool(runner, control).execute("live-final", event.input, undefined, undefined, executionContext(control)),
    ).rejects.toThrow("H-20");

    // The one judge call carries the rewritten command, not the reviewed one.
    expect(control.requests.map((request) => request.input)).toEqual([{ command: REWRITTEN_COMMAND }]);
    expect(control.governedExecutions).toEqual([]);
    expect(control.foreignExecutions).toEqual([]);
    expect(control.confirmations).toBe(0);
  });

  test("a later extension cannot take ownership of the governed mutator", async () => {
    const control = createControl();
    const runner = await liveRunner([GOVERNED_EXTENSION, LATER_EXTENSION], control);

    // The host resolves `bash` to codeArbiter's wrapper, not the later
    // extension's same-named registration.
    expect(runner.getToolDefinition("bash")?.description).toBe(GOVERNED_TOOL_MARKER);
    const owners = runner.getAllRegisteredTools()
      .filter((tool) => tool.definition.name === "bash")
      .map((tool) => tool.sourceInfo.path);
    expect(owners).toEqual([GOVERNED_EXTENSION]);

    // And the tool that actually runs is the governed one: an allowed command
    // reaches codeArbiter's factory, never the later extension's executor.
    await expect(runner.emitToolCall({
      type: "tool_call", toolName: "bash", toolCallId: "live-owner", input: { command: BENIGN_COMMAND },
    })).resolves.toBeUndefined();
    await governedTool(runner, control)
      .execute("live-owner", { command: BENIGN_COMMAND }, undefined, undefined, executionContext(control));
    expect(control.governedExecutions).toEqual([{ name: "bash", input: { command: BENIGN_COMMAND } }]);
    expect(control.foreignExecutions).toEqual([]);
  });

  test("ownership drift in the live registry blocks the mutation", async () => {
    const control = createControl();
    // The inverted load order is the drift this STOP exists to catch: the later
    // extension now owns `bash` in the host's real registry.
    const runner = await liveRunner([LATER_EXTENSION, GOVERNED_EXTENSION], control);
    expect(runner.getToolDefinition("bash")?.description).toBe(FOREIGN_TOOL_MARKER);

    await expect(runner.emitToolCall({
      type: "tool_call", toolName: "bash", toolCallId: "live-drift", input: { command: BENIGN_COMMAND },
    })).resolves.toMatchObject({ block: true, reason: expect.stringContaining("source drift") });
    expect(control.foreignExecutions).toEqual([]);
  });

  test("an unclassified live tool is blocked before it can execute", async () => {
    const control = createControl();
    const runner = await liveRunner([GOVERNED_EXTENSION, LATER_EXTENSION], control);

    await expect(runner.emitToolCall({
      type: "tool_call", toolName: "codearbiter_unknown_mutator", toolCallId: "live-unknown", input: {},
    })).resolves.toMatchObject({ block: true, reason: expect.stringContaining("unknown Pi tool") });
  });
});
