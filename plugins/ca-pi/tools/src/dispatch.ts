/** dispatch.ts - bounded single, chained, and FIFO-parallel Pi orchestration. */
import { randomUUID } from "node:crypto";
import { appendFile } from "node:fs/promises";
import { resolve } from "node:path";
import { types as utilTypes } from "node:util";

import type {
  LifecycleAuthorization,
  ToolDefinitionPort,
  ToolExecutionContextPort,
} from "./contracts.ts";
import { publishActivity } from "./activity.ts";
import type { ActivityPublisher } from "./activity.ts";
import { safeDiagnostic } from "./redaction.ts";
import { loadRoleCatalog, validRoleName } from "./roles.ts";
import type { PiRole } from "./roles.ts";
import { runPiChild } from "./runner.ts";
import type { ChildResult, PiChildRequest } from "./runner.ts";

// Mirrors runner.ts's own bounded stderr capture: never re-widen the head beyond what runner.ts
// already collected.
const MAX_AUDIT_STDERR_HEAD_CHARS = 4_000;

interface DispatchAuditRecord {
  cwd: string;
  role: string;
  provider: string;
  model: string;
  terminal: ChildResult["terminal"];
  exitCode?: number;
  durationMs?: number;
  stdoutBytes?: number;
  stderrBytes?: number;
  stderrHead?: string;
  diagnostic?: string;
}

/** Appends one gate-events.log line per Pi child dispatch completion (success or failure),
 * mirroring bridge.ts's auditFailure and compaction.ts's appendPiCompactionAudit: same target
 * resolution, same append-only best-effort fail-open contract. An unwritable audit sink NEVER
 * changes dispatch behavior or its result. Task/prompt content is never included; stderr is
 * always routed through safeDiagnostic before it is written. */
export async function appendDispatchAudit(record: DispatchAuditRecord): Promise<void> {
  const line = [
    `[${new Date().toISOString()}]`,
    "HOST: pi",
    "RULE: PI-DISPATCH",
    `AUDIT: ${record.terminal === "completed" ? "PI_DISPATCH_COMPLETED" : "PI_DISPATCH_DEGRADED"}`,
    `CORRELATION: ${randomUUID()}`,
    `ROLE: ${safeDiagnostic(record.role, 100)}`,
    `PROVIDER: ${safeDiagnostic(record.provider, 100)}`,
    `MODEL: ${safeDiagnostic(record.model, 100)}`,
    `EXIT: ${record.terminal}${record.exitCode === undefined ? "" : `(${record.exitCode})`}`,
    `DURATION_MS: ${record.durationMs ?? 0}`,
    `STDOUT_BYTES: ${record.stdoutBytes ?? 0}`,
    `STDERR_BYTES: ${record.stderrBytes ?? 0}`,
    // safeDiagnostic intentionally preserves newlines for other callers; a raw child stderr head
    // must never introduce a newline into this append-only, one-record-per-line audit sink, or a
    // child could forge extra structurally-valid audit lines. Fold after redaction, before embed.
    `STDERR_HEAD: ${safeDiagnostic(record.stderrHead ?? "", MAX_AUDIT_STDERR_HEAD_CHARS).replace(/\n/gu, "\\n")}`,
    ...(record.diagnostic === undefined ? [] : [`DIAGNOSTIC: ${safeDiagnostic(record.diagnostic, 200)}`]),
  ].join(" | ") + "\n";
  try {
    await appendFile(resolve(record.cwd, ".codearbiter", "gate-events.log"), line, { encoding: "utf8" });
  } catch {
    // A dispatch outcome remains valid if its append-only audit sink is unavailable.
  }
}

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
      const startedAt = Date.now();
      try {
        const result = await dependencies.runChild(roleLaunch(request.runtime, role, task, limits.timeoutMs), controller.signal);
        await appendDispatchAudit({
          cwd: request.runtime.cwd,
          role: role.name,
          provider: request.runtime.provider,
          model: request.runtime.model,
          terminal: result.terminal,
          durationMs: result.durationMs ?? (Date.now() - startedAt),
          ...(result.exitCode === undefined ? {} : { exitCode: result.exitCode }),
          ...(result.stdoutBytes === undefined ? {} : { stdoutBytes: result.stdoutBytes }),
          ...(result.stderrBytes === undefined ? {} : { stderrBytes: result.stderrBytes }),
          ...(result.stderrHead === undefined ? {} : { stderrHead: result.stderrHead }),
          ...(result.diagnostic === undefined ? {} : { diagnostic: result.diagnostic }),
        });
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
  activity?: () => ActivityPublisher | undefined;
  createActivityId?: () => string;
}

function currentActivity(source: DispatchToolDependencies["activity"]): ActivityPublisher | undefined {
  try { return source?.(); } catch { return undefined; }
}

function activityIds(count: number, create: () => string): readonly string[] | undefined {
  try {
    return Object.freeze(Array.from({ length: count }, () => create()));
  } catch {
    return undefined;
  }
}

function exactDataRecord(
  value: unknown,
  allowed: ReadonlySet<string>,
): Readonly<Record<string, PropertyDescriptor>> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  if (Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const keys = Reflect.ownKeys(value);
  if (keys.length > allowed.size || keys.some((key) => typeof key !== "string" || !allowed.has(key))) return undefined;
  const fields: Record<string, PropertyDescriptor> = {};
  for (const key of keys as string[]) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)) return undefined;
    fields[key] = descriptor;
  }
  return Object.freeze(fields);
}

function fixedRoles(value: unknown): readonly string[] | undefined {
  if (!Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  const length = Object.getOwnPropertyDescriptor(value, "length");
  if (length === undefined || !("value" in length) || !Number.isSafeInteger(length.value)
    || length.value === 0 || length.value > DISPATCH_POLICY.maxRoles) return undefined;
  const roles: string[] = [];
  for (let index = 0; index < length.value; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)
      || !validRoleName(descriptor.value)) return undefined;
    roles.push(descriptor.value);
  }
  return new Set(roles).size === roles.length ? Object.freeze(roles) : undefined;
}

function parseToolRequest(params: Record<string, unknown>, runtime: DispatchRuntime): DispatchRequest | undefined {
  const fields = exactDataRecord(params, new Set(["mode", "roles", "task", "depth", "limits"]));
  if (fields === undefined || fields.mode === undefined || fields.roles === undefined || fields.task === undefined) return undefined;
  const mode = fields.mode.value as unknown;
  const roles = fixedRoles(fields.roles.value);
  const task = fields.task.value as unknown;
  const depth = fields.depth?.value as unknown;
  const rawLimits = fields.limits?.value;
  const limitFields: Readonly<Record<string, PropertyDescriptor>> | undefined = rawLimits === undefined
    ? Object.freeze({} as Record<string, PropertyDescriptor>)
    : exactDataRecord(rawLimits, LIMIT_KEYS);
  if (limitFields === undefined) return undefined;
  const limitValues = Object.freeze(Object.fromEntries(
    Object.keys(limitFields).map((key) => [key, limitFields[key]!.value]),
  )) as DispatchLimits;
  if (typeof mode !== "string" || !MODE_SET.has(mode)
    || roles === undefined || (mode === "single" && roles.length !== 1)
    || typeof task !== "string"
    || task.length === 0 || task.length > DISPATCH_POLICY.maxTaskBytes
    || task.trim() === "" || Buffer.byteLength(task, "utf8") > DISPATCH_POLICY.maxTaskBytes
    || (depth !== undefined && (!Number.isSafeInteger(depth) || (depth as number) < 0))) return undefined;
  const limits = resolveLimits(limitValues);
  if (limits === undefined || ((depth as number | undefined) ?? 0) > limits.maxDepth
    || Buffer.byteLength(taskEnvelope(task), "utf8") > DISPATCH_POLICY.maxTaskBytes) return undefined;
  return {
    mode: mode as DispatchMode,
    roles,
    task,
    ...(depth === undefined ? {} : { depth: depth as number }),
    ...(rawLimits === undefined ? {} : { limits: limitValues }),
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
          if (request === undefined) {
            result = fixedResult("protocol_error");
          } else {
            const activity = currentActivity(dependencies.activity);
            const ids = activity === undefined
              ? undefined
              : activityIds(request.roles.length, dependencies.createActivityId ?? randomUUID);
            if (ids !== undefined) {
              for (let index = 0; index < request.roles.length; index += 1) {
                publishActivity(activity, {
                  kind: "child", id: ids[index]!, label: request.roles[index]!, state: "active",
                });
              }
            }
            try {
              result = await runDispatch(request, activeSignal);
            } finally {
              if (ids !== undefined) {
                for (let index = 0; index < request.roles.length; index += 1) {
                  publishActivity(activity, {
                    kind: "child", id: ids[index]!, label: request.roles[index]!, state: "completed",
                  });
                }
              }
            }
          }
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
