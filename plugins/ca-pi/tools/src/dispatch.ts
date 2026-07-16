/** dispatch.ts - bounded single, chained, and FIFO-parallel Pi orchestration. */
import { resolve } from "node:path";

import type {
  LifecycleAuthorization,
  ToolDefinitionPort,
  ToolExecutionContextPort,
} from "./contracts.ts";
import { loadRoleCatalog } from "./roles.ts";
import type { PiRole } from "./roles.ts";
import { runPiChild } from "./runner.ts";
import type { ChildResult, PiChildRequest } from "./runner.ts";

export const DISPATCH_MODES = Object.freeze(["single", "chain", "parallel"] as const);
export type DispatchMode = (typeof DISPATCH_MODES)[number];

export const DISPATCH_TERMINALS = Object.freeze([
  "accepted",
  "changes_requested",
  "blocked",
  "cancelled",
  "timeout",
  "depth_exceeded",
  "oversized",
  "protocol_error",
  "crashed",
  "degraded",
] as const);
export type DispatchTerminal = (typeof DISPATCH_TERMINALS)[number];

export const DISPATCH_POLICY = Object.freeze({
  maxConcurrency: 4,
  maxDepth: 4,
  maxRoles: 8,
  maxTaskBytes: 65_536,
  maxChildOutputBytes: 65_536,
  maxAggregateOutputBytes: 262_144,
  timeoutMs: 120_000,
});

export interface DispatchLimits {
  concurrency?: number;
  maxDepth?: number;
  maxChildOutputBytes?: number;
  maxAggregateOutputBytes?: number;
  timeoutMs?: number;
}

export interface DispatchRuntime {
  nodePath: string;
  piCliPath: string;
  provider: string;
  model: string;
  cwd: string;
  packageRoot: string;
  childExtensionPath: string;
  parentEnv?: Readonly<NodeJS.ProcessEnv>;
  platform?: NodeJS.Platform;
}

export interface DispatchRequest {
  mode: DispatchMode;
  roles: readonly string[];
  task: string;
  depth?: number;
  limits?: DispatchLimits;
  runtime: DispatchRuntime;
}

export interface DispatchChild {
  role: string;
  state: DispatchTerminal;
  summary?: string;
  pid?: number;
  correlationId?: string;
}

export interface DispatchResult {
  state: DispatchTerminal;
  children: readonly DispatchChild[];
}

interface ResolvedLimits {
  concurrency: number;
  maxDepth: number;
  maxChildOutputBytes: number;
  maxAggregateOutputBytes: number;
  timeoutMs: number;
}

interface InternalChild extends DispatchChild {
  outputBytes: number;
}

interface DispatchDependencies {
  runChild(request: PiChildRequest, signal: AbortSignal): Promise<ChildResult>;
  loadRoles(packageRoot: string): Promise<ReadonlyMap<string, PiRole>>;
}

const JUDGMENT_STATES = new Set<DispatchTerminal>(["accepted", "changes_requested", "blocked"]);
const MODE_SET = new Set<string>(DISPATCH_MODES);
const LIMIT_KEYS = new Set(["concurrency", "maxDepth", "maxChildOutputBytes", "maxAggregateOutputBytes", "timeoutMs"]);

function fixedResult(state: DispatchTerminal, children: readonly DispatchChild[] = []): DispatchResult {
  return Object.freeze({ state, children: Object.freeze([...children]) });
}

function positiveBoundedInteger(value: unknown, maximum: number): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0 && (value as number) <= maximum;
}

function resolveLimits(input: DispatchLimits | undefined): ResolvedLimits | undefined {
  if (input !== undefined) {
    if (input === null || typeof input !== "object" || Array.isArray(input)) return undefined;
    if (Object.keys(input).some((key) => !LIMIT_KEYS.has(key))) return undefined;
  }
  const limits = {
    concurrency: input?.concurrency ?? DISPATCH_POLICY.maxConcurrency,
    maxDepth: input?.maxDepth ?? DISPATCH_POLICY.maxDepth,
    maxChildOutputBytes: input?.maxChildOutputBytes ?? DISPATCH_POLICY.maxChildOutputBytes,
    maxAggregateOutputBytes: input?.maxAggregateOutputBytes ?? DISPATCH_POLICY.maxAggregateOutputBytes,
    timeoutMs: input?.timeoutMs ?? DISPATCH_POLICY.timeoutMs,
  };
  return positiveBoundedInteger(limits.concurrency, DISPATCH_POLICY.maxConcurrency)
    && positiveBoundedInteger(limits.maxDepth, DISPATCH_POLICY.maxDepth)
    && positiveBoundedInteger(limits.maxChildOutputBytes, DISPATCH_POLICY.maxChildOutputBytes)
    && positiveBoundedInteger(limits.maxAggregateOutputBytes, DISPATCH_POLICY.maxAggregateOutputBytes)
    && positiveBoundedInteger(limits.timeoutMs, DISPATCH_POLICY.timeoutMs)
    ? limits
    : undefined;
}

function roleLaunch(runtime: DispatchRuntime, role: PiRole, task: string, timeoutMs: number): PiChildRequest {
  return {
    nodePath: runtime.nodePath,
    piCliPath: runtime.piCliPath,
    provider: runtime.provider,
    model: runtime.model,
    tools: role.tools,
    cwd: runtime.cwd,
    childExtensionPath: runtime.childExtensionPath,
    skillPaths: role.skillPaths.map((path) => resolve(runtime.packageRoot, path)),
    charterPath: resolve(runtime.packageRoot, role.charterPath),
    task,
    timeoutMs,
    ...(runtime.parentEnv === undefined ? {} : { parentEnv: runtime.parentEnv }),
    ...(runtime.platform === undefined ? {} : { platform: runtime.platform }),
  };
}

function parseStructuredOutput(result: ChildResult, maxBytes: number): InternalChild | undefined {
  if (result.terminal !== "completed" || typeof result.output !== "string") return undefined;
  const outputBytes = Buffer.byteLength(result.output, "utf8");
  if (outputBytes > maxBytes) {
    return { role: "", state: "oversized", outputBytes };
  }
  let value: unknown;
  try { value = JSON.parse(result.output); }
  catch { return { role: "", state: "protocol_error", outputBytes }; }
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return { role: "", state: "protocol_error", outputBytes };
  }
  const record = value as Record<string, unknown>;
  if (JSON.stringify(Object.keys(record).sort()) !== JSON.stringify(["state", "summary"])
    || typeof record.state !== "string" || !JUDGMENT_STATES.has(record.state as DispatchTerminal)
    || typeof record.summary !== "string" || record.summary.trim() === ""
    || Buffer.byteLength(record.summary, "utf8") > maxBytes) {
    return { role: "", state: "protocol_error", outputBytes };
  }
  return {
    role: "",
    state: record.state as DispatchTerminal,
    summary: record.summary,
    outputBytes,
    ...(result.pid === undefined ? {} : { pid: result.pid }),
    ...(result.correlationId === undefined ? {} : { correlationId: result.correlationId }),
  };
}

function publicChild(child: InternalChild): DispatchChild {
  const { outputBytes: _outputBytes, ...result } = child;
  return Object.freeze(result);
}

function overallState(children: readonly InternalChild[]): DispatchTerminal {
  const priority: readonly DispatchTerminal[] = [
    "cancelled",
    "timeout",
    "depth_exceeded",
    "oversized",
    "protocol_error",
    "crashed",
    "degraded",
    "blocked",
    "changes_requested",
  ];
  return priority.find((state) => children.some((child) => child.state === state)) ?? "accepted";
}

function enforceAggregateLimit(children: readonly InternalChild[], maximum: number): InternalChild[] {
  let total = 0;
  return children.map((child) => {
    if (!JUDGMENT_STATES.has(child.state)) return child;
    if (total + child.outputBytes > maximum) return { role: child.role, state: "oversized", outputBytes: child.outputBytes };
    total += child.outputBytes;
    return child;
  });
}

function taskEnvelope(task: string, prior?: InternalChild): string {
  return JSON.stringify({
    protocol: "codearbiter-dispatch-v1",
    task,
    ...(prior === undefined ? {} : { prior: {
      role: prior.role,
      state: prior.state,
      summary: prior.summary,
    } }),
    response: {
      exactKeys: ["state", "summary"],
      states: ["accepted", "changes_requested", "blocked"],
      summary: "Put the complete Markdown report required by your role charter in this JSON string. Emit only the JSON object.",
    },
  });
}

export function createDispatcher(dependencies: DispatchDependencies) {
  return async function dispatchWithDependencies(
    request: DispatchRequest,
    signal: AbortSignal,
  ): Promise<DispatchResult> {
    const limits = resolveLimits(request.limits);
    if (limits === undefined
      || !MODE_SET.has(request.mode)
      || !Array.isArray(request.roles)
      || request.roles.length === 0
      || request.roles.length > DISPATCH_POLICY.maxRoles
      || request.roles.some((role) => typeof role !== "string" || role === "")
      || new Set(request.roles).size !== request.roles.length
      || typeof request.task !== "string"
      || request.task.trim() === ""
      || Buffer.byteLength(request.task, "utf8") > DISPATCH_POLICY.maxTaskBytes
      || !Number.isSafeInteger(request.depth ?? 0)
      || (request.depth ?? 0) < 0) {
      return fixedResult("protocol_error");
    }
    if ((request.depth ?? 0) > limits.maxDepth) return fixedResult("depth_exceeded");
    if (request.mode === "single" && request.roles.length !== 1) return fixedResult("protocol_error");
    const initialTask = taskEnvelope(request.task);
    if (Buffer.byteLength(initialTask, "utf8") > DISPATCH_POLICY.maxTaskBytes) return fixedResult("oversized");

    let catalog: ReadonlyMap<string, PiRole>;
    try { catalog = await dependencies.loadRoles(request.runtime.packageRoot); }
    catch { return fixedResult("degraded"); }
    const selected = request.roles.map((name) => catalog.get(name));
    if (selected.some((role) => role === undefined)) return fixedResult("protocol_error");
    if ((selected as PiRole[]).filter((role) => role.classification === "author").length > 1) {
      return fixedResult("protocol_error");
    }
    if (signal.aborted) {
      return fixedResult("cancelled", request.roles.map((role) => ({ role, state: "cancelled" })));
    }

    const runRole = async (role: PiRole, task: string): Promise<InternalChild> => {
      const controller = new AbortController();
      let timedOut = false;
      const cancel = () => controller.abort(signal.reason);
      signal.addEventListener("abort", cancel, { once: true });
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort(new Error("Pi dispatch timed out."));
      }, limits.timeoutMs);
      try {
        const result = await dependencies.runChild(roleLaunch(request.runtime, role, task, limits.timeoutMs), controller.signal);
        if (signal.aborted) return { role: role.name, state: "cancelled", outputBytes: 0 };
        if (timedOut) return { role: role.name, state: "timeout", outputBytes: 0 };
        if (result.terminal === "degraded") return { role: role.name, state: "degraded", outputBytes: 0 };
        const parsed = parseStructuredOutput(result, limits.maxChildOutputBytes);
        return parsed === undefined
          ? { role: role.name, state: "protocol_error", outputBytes: 0 }
          : { ...parsed, role: role.name };
      } catch {
        if (signal.aborted) return { role: role.name, state: "cancelled", outputBytes: 0 };
        if (timedOut) return { role: role.name, state: "timeout", outputBytes: 0 };
        return { role: role.name, state: "crashed", outputBytes: 0 };
      } finally {
        clearTimeout(timer);
        signal.removeEventListener("abort", cancel);
      }
    };

    let children: InternalChild[];
    if (request.mode === "chain") {
      children = [];
      let task = initialTask;
      for (const role of selected as PiRole[]) {
        if (Buffer.byteLength(task, "utf8") > DISPATCH_POLICY.maxTaskBytes) {
          children.push({ role: role.name, state: "oversized", outputBytes: 0 });
          break;
        }
        const child = await runRole(role, task);
        children.push(child);
        if (!JUDGMENT_STATES.has(child.state)) break;
        task = taskEnvelope(request.task, child);
      }
    } else if (request.mode === "parallel") {
      const results = new Array<InternalChild>(selected.length);
      let cursor = 0;
      const worker = async () => {
        while (cursor < selected.length) {
          const index = cursor;
          cursor += 1;
          const role = selected[index]!;
          results[index] = signal.aborted
            ? { role: role!.name, state: "cancelled", outputBytes: 0 }
            : await runRole(role!, initialTask);
        }
      };
      await Promise.all(Array.from(
        { length: Math.min(limits.concurrency, selected.length) },
        async () => await worker(),
      ));
      children = results;
    } else {
      children = [await runRole(selected[0]!, initialTask)];
    }

    children = enforceAggregateLimit(children, limits.maxAggregateOutputBytes);
    const state = signal.aborted ? "cancelled" : overallState(children);
    return fixedResult(state, children.map(publicChild));
  };
}

export const dispatch = createDispatcher({
  runChild: runPiChild,
  loadRoles: loadRoleCatalog,
});

interface DispatchToolDependencies {
  authorize(context: ToolExecutionContextPort): boolean | LifecycleAuthorization | undefined | Promise<boolean | LifecycleAuthorization | undefined>;
  resolveRuntime(context: ToolExecutionContextPort): DispatchRuntime | Promise<DispatchRuntime>;
  dispatch?: (request: DispatchRequest, signal: AbortSignal) => Promise<DispatchResult>;
}

function exactObject(value: unknown, allowed: ReadonlySet<string>): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value as Record<string, unknown>).every((key) => allowed.has(key));
}

function parseToolRequest(params: Record<string, unknown>, runtime: DispatchRuntime): DispatchRequest | undefined {
  if (!exactObject(params, new Set(["mode", "roles", "task", "depth", "limits"]))) return undefined;
  if (typeof params.mode !== "string" || !MODE_SET.has(params.mode)
    || !Array.isArray(params.roles) || params.roles.some((role) => typeof role !== "string")
    || typeof params.task !== "string"
    || (params.depth !== undefined && !Number.isSafeInteger(params.depth))
    || (params.limits !== undefined && !exactObject(params.limits, LIMIT_KEYS))) return undefined;
  return {
    mode: params.mode as DispatchMode,
    roles: params.roles as string[],
    task: params.task,
    ...(params.depth === undefined ? {} : { depth: params.depth as number }),
    ...(params.limits === undefined ? {} : { limits: params.limits as DispatchLimits }),
    runtime,
  };
}

export function createDispatchTool(dependencies: DispatchToolDependencies): ToolDefinitionPort {
  const runDispatch = dependencies.dispatch ?? dispatch;
  return {
    name: "codearbiter_dispatch",
    label: "codeArbiter dispatch",
    description: "Run bounded isolated codeArbiter author or reviewer roles.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["mode", "roles", "task"],
      properties: {
        mode: { type: "string", enum: [...DISPATCH_MODES] },
        roles: { type: "array", minItems: 1, maxItems: DISPATCH_POLICY.maxRoles, items: { type: "string" } },
        task: { type: "string", minLength: 1, maxLength: DISPATCH_POLICY.maxTaskBytes },
        depth: { type: "integer", minimum: 0, maximum: DISPATCH_POLICY.maxDepth },
        limits: {
          type: "object",
          additionalProperties: false,
          properties: {
            concurrency: { type: "integer", minimum: 1, maximum: DISPATCH_POLICY.maxConcurrency },
            maxDepth: { type: "integer", minimum: 1, maximum: DISPATCH_POLICY.maxDepth },
            maxChildOutputBytes: { type: "integer", minimum: 1, maximum: DISPATCH_POLICY.maxChildOutputBytes },
            maxAggregateOutputBytes: { type: "integer", minimum: 1, maximum: DISPATCH_POLICY.maxAggregateOutputBytes },
            timeoutMs: { type: "integer", minimum: 1, maximum: DISPATCH_POLICY.timeoutMs },
          },
        },
      },
    },
    execute: async (_toolCallId, params, signal, _onUpdate, context) => {
      const activeSignal = signal ?? context?.signal ?? new AbortController().signal;
      let result: DispatchResult;
      try {
        if (context === undefined) return {
          content: [{ type: "text", text: JSON.stringify(fixedResult("degraded")) }],
          details: fixedResult("degraded"),
        };
        const authorization = await dependencies.authorize(context);
        if (authorization !== true && (authorization === false || authorization === undefined)) return {
          content: [{ type: "text", text: JSON.stringify(fixedResult("degraded")) }],
          details: fixedResult("degraded"),
        };
        const runtime = await dependencies.resolveRuntime(context);
        const request = parseToolRequest(params, runtime);
        if (authorization !== true && !authorization.isCurrent(authorization.lease)) {
          result = fixedResult("degraded");
        } else {
          result = request === undefined ? fixedResult("protocol_error") : await runDispatch(request, activeSignal);
        }
      } catch {
        result = fixedResult("degraded");
      }
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };
}
