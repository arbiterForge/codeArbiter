import type {
  BridgePort,
  BuiltinToolFactories,
  ToolCategory,
  ToolDefinitionPort,
  ToolExecutionContextPort,
  ToolGuardPiPort,
  ToolResultPiPort,
} from "./contracts.ts";
import { randomUUID } from "node:crypto";
import { realpathSync } from "node:fs";
import { safeDiagnostic } from "./redaction.ts";
import { applyToolResultNotice } from "./notices.ts";

type LifecycleGeneration = object;
const STANDALONE_GENERATION: LifecycleGeneration = Object.freeze({});

export interface WrapBuiltinsOptions {
  cwd: string;
  descriptor: Readonly<Record<string, ToolCategory>>;
  factories: BuiltinToolFactories;
  nativeFactories?: BuiltinToolFactories;
  wrapperSourcePath: string;
}

export interface EnforcementReadinessPort {
  beginActivation(): void;
  beginBootstrap(): void;
  markReady(): void;
  deactivate(): void;
}

function failTool(message: string): never {
  throw new Error(safeDiagnostic(message));
}

function appendWarning(result: Record<string, unknown>, warning: string): Record<string, unknown> {
  const content = Array.isArray(result.content) ? [...result.content] : [];
  if (!JSON.stringify(content).includes(warning)) content.push({ type: "text", text: warning });
  return { ...result, content };
}

function canonicalSnapshot(value: unknown, seen = new Set<object>(), depth = 0): unknown {
  if (depth > 32) throw new TypeError("parameters exceed nesting limit");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("parameters contain a non-finite number");
    return value;
  }
  if (typeof value !== "object" || seen.has(value)) throw new TypeError("parameters are not acyclic JSON");
  seen.add(value);
  try {
    if (Array.isArray(value)) return Object.freeze(value.map((item) => canonicalSnapshot(item, seen, depth + 1)));
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) throw new TypeError("parameters contain a non-plain object");
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      if (key === "__proto__" || key === "constructor" || key === "prototype") throw new TypeError("parameters contain an unsafe key");
      output[key] = canonicalSnapshot(item, seen, depth + 1);
    }
    return Object.freeze(output);
  } finally {
    seen.delete(value);
  }
}

function nativeSessionId(context: ToolExecutionContextPort | undefined): string | undefined {
  const manager = context?.sessionManager;
  if (manager === undefined || typeof manager.getSessionId !== "function") return undefined;
  try {
    const value = manager.getSessionId.call(manager);
    if (typeof value !== "string" || value.trim() === "" || value.length > 1_024) return undefined;
    return value;
  } catch {
    return undefined;
  }
}

function fixedFallbackSessionId(): (context: ToolExecutionContextPort | undefined) => string {
  const fallback = randomUUID();
  return (context) => nativeSessionId(context) ?? fallback;
}

function executionCwd(context: ToolExecutionContextPort | undefined, fallback: string): string {
  return context !== null
    && typeof context === "object"
    && typeof (context as { cwd?: unknown }).cwd === "string"
    ? (context as { cwd: string }).cwd
    : fallback;
}

function wrappedDefinition(
  factory: (cwd: string) => ToolDefinitionPort,
  nativeFactory: (cwd: string) => ToolDefinitionPort,
  category: ToolCategory,
  cwd: string,
  bridge: BridgePort,
  boundGeneration: LifecycleGeneration,
  activeGeneration: () => LifecycleGeneration | undefined,
  isReady: () => boolean,
  sessionIdFor: (context: ToolExecutionContextPort | undefined) => string,
): ToolDefinitionPort {
  const original = factory(cwd);
  const executeNativeFromContext = async (
    toolCallId: string,
    params: Record<string, unknown>,
    signal: AbortSignal | undefined,
    onUpdate: unknown,
    context: ToolExecutionContextPort | undefined,
  ) => {
    const currentCwd = executionCwd(context, cwd);
    const native = nativeFactory(currentCwd);
    return await native.execute(toolCallId, params, signal, onUpdate, context);
  };
  return {
    ...original,
    execute: async (toolCallId, params, signal, onUpdate, context) => {
      const generation = activeGeneration();
      if (generation === undefined || generation !== boundGeneration || !isReady()) {
        if (generation !== undefined && category !== "READ") {
          return failTool("codeArbiter enforcement is not ready; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, params, signal, onUpdate, context);
      }
      let approved: Record<string, unknown>;
      try {
        approved = canonicalSnapshot(params) as Record<string, unknown>;
      } catch {
        return failTool("Pi tool parameters are not canonical JSON; mutation blocked; run /ca-doctor.");
      }
      let response: Awaited<ReturnType<BridgePort["call"]>>;
      try {
        response = await bridge.call({
          version: 1,
          event: "tool_call",
          cwd,
          ...(category === "READ" ? { sessionId: sessionIdFor(context) } : {}),
          tool: original.name,
          input: approved,
        }, signal ?? new AbortController().signal);
      } catch (error) {
        if (activeGeneration() === generation) throw error;
        if (category !== "READ") {
          return failTool("codeArbiter lifecycle changed while approval was pending; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, approved, signal, onUpdate, context);
      }
      if (activeGeneration() !== generation) {
        if (category !== "READ") {
          return failTool("codeArbiter lifecycle changed while approval was pending; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, approved, signal, onUpdate, context);
      }
      if (response.outcome === "block") return failTool(response.message ?? `Blocked by ${response.ruleId ?? "codeArbiter"}`);
      if (category !== "READ" && response.outcome === "warn") {
        return failTool(`Mutation bridge returned an advisory verdict; mutation blocked; run /ca-doctor.`);
      }
      const result = await original.execute(toolCallId, approved, signal, onUpdate, context);
      if (activeGeneration() !== generation) return result;
      if (category === "READ") {
        const patch = applyToolResultNotice(result, response);
        return patch === undefined ? result : { ...result, ...patch };
      }
      if ((response.outcome === "warn" || response.outcome === "notice") && response.message !== undefined) {
        return appendWarning(result, response.message);
      }
      return result;
    },
  };
}

export function wrapBuiltins(pi: ToolGuardPiPort, bridge: BridgePort, options: WrapBuiltinsOptions): void {
  wrapMissingBuiltins(
    pi,
    bridge,
    options,
    new Set(),
    undefined,
    undefined,
    () => STANDALONE_GENERATION,
    () => true,
    fixedFallbackSessionId(),
  );
}

function wrapMissingBuiltins(
  pi: ToolGuardPiPort,
  bridge: BridgePort,
  options: WrapBuiltinsOptions,
  wrapped: Set<string>,
  definitions?: Map<string, ToolDefinitionPort>,
  definitionGenerations?: Map<string, LifecycleGeneration>,
  activeGeneration: () => LifecycleGeneration | undefined = () => STANDALONE_GENERATION,
  isReady: () => boolean = () => true,
  sessionIdFor: (context: ToolExecutionContextPort | undefined) => string = fixedFallbackSessionId(),
): void {
  const boundGeneration = activeGeneration() ?? STANDALONE_GENERATION;
  for (const name of ["bash", "write", "edit", "read"] as const) {
    if (wrapped.has(name) && definitionGenerations?.get(name) === boundGeneration) continue;
    const category = options.descriptor[name] ?? "OTHER";
    if (category === "OTHER") throw new Error(`Pi descriptor does not classify built-in ${name}; run /ca-doctor.`);
    const definition = wrappedDefinition(
      options.factories[name],
      (options.nativeFactories ?? options.factories)[name],
      category,
      options.cwd,
      bridge,
      boundGeneration,
      activeGeneration,
      isReady,
      sessionIdFor,
    );
    pi.registerTool(definition);
    definitions?.set(name, definition);
    definitionGenerations?.set(name, boundGeneration);
    wrapped.add(name);
  }
}

export class EnforcementInstaller {
  private bootstrapInstalled = false;
  private bootstrapActive = false;
  private ready = false;
  private guardInstalled = false;
  private resultsInstalled = false;
  private readonly wrapped = new Set<string>();
  private readonly definitions = new Map<string, ToolDefinitionPort>();
  private readonly definitionGenerations = new Map<string, LifecycleGeneration>();
  private fallbackSessionId: string | undefined;
  private lifecycleGeneration: LifecycleGeneration | undefined;

  private sessionIdFor(context: ToolExecutionContextPort | undefined): string {
    const native = nativeSessionId(context);
    if (native !== undefined) return native;
    this.fallbackSessionId ??= randomUUID();
    return this.fallbackSessionId;
  }

  ensureBootstrap(pi: ToolGuardPiPort, descriptor: Readonly<Record<string, ToolCategory>>): void {
    if (this.bootstrapInstalled) return;
    pi.on("tool_call", (event) => {
      if (!this.bootstrapActive || this.ready) return undefined;
      const name = typeof event.toolName === "string" ? event.toolName : "";
      if ((descriptor[name] ?? "OTHER") === "READ") return undefined;
      return {
        block: true,
        reason: "codeArbiter enforcement is not ready; this Pi tool is potentially mutating and is blocked; run /ca-doctor.",
      };
    });
    this.bootstrapInstalled = true;
  }

  private beginBlockedGeneration(): void {
    this.bootstrapActive = true;
    this.ready = false;
    this.fallbackSessionId = randomUUID();
    this.lifecycleGeneration = Object.freeze({});
  }

  beginActivation(): void {
    this.beginBlockedGeneration();
  }

  beginBootstrap(): void {
    this.beginBlockedGeneration();
  }

  markReady(): void {
    if (this.bootstrapActive) this.ready = true;
  }

  deactivate(): void {
    this.bootstrapActive = false;
    this.ready = false;
    this.fallbackSessionId = undefined;
    this.lifecycleGeneration = undefined;
  }

  ensureGuard(pi: ToolGuardPiPort, descriptor: Readonly<Record<string, ToolCategory>>, wrapperSourcePath: string): void {
    if (this.guardInstalled) return;
    guardUnknownTools(pi, descriptor, wrapperSourcePath, () => this.bootstrapActive);
    this.guardInstalled = true;
  }

  ensureResults(pi: ToolResultPiPort, bridge: BridgePort, descriptor: Readonly<Record<string, ToolCategory>>): void {
    if (this.resultsInstalled) return;
    bridgeToolResults(pi, bridge, descriptor, () => this.lifecycleGeneration);
    this.resultsInstalled = true;
  }

  ensureBuiltins(pi: ToolGuardPiPort, bridge: BridgePort, options: WrapBuiltinsOptions): void {
    wrapMissingBuiltins(
      pi,
      bridge,
      options,
      this.wrapped,
      this.definitions,
      this.definitionGenerations,
      () => this.lifecycleGeneration,
      () => this.ready,
      (context) => this.sessionIdFor(context),
    );
  }

  async runDoctorWrapperSelfTest(signal?: AbortSignal): Promise<unknown> {
    const bash = this.definitions.get("bash");
    if (bash === undefined) throw new Error("The active Pi bash wrapper is unavailable; run /ca-doctor.");
    return await bash.execute(
      "codearbiter-doctor-wrapper-self-test",
      { command: "git add --all --dry-run" },
      signal ?? new AbortController().signal,
    );
  }
}

function samePath(left: string, right: string): boolean {
  const equal = (a: string, b: string) => process.platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b;
  if (equal(left, right)) return true;
  try { return equal(realpathSync(left), realpathSync(right)); } catch { return false; }
}

export function guardUnknownTools(
  pi: ToolGuardPiPort,
  descriptor: Readonly<Record<string, ToolCategory>>,
  wrapperSourcePath: string,
  isActive: () => boolean = () => true,
): void {
  pi.on("tool_call", (event) => {
    if (!isActive()) return undefined;
    const name = typeof event.toolName === "string" ? event.toolName : "";
    const category = descriptor[name] ?? "OTHER";
    if (category === "OTHER") {
      return { block: true, reason: "An unknown Pi tool is potentially mutating and is blocked; classify it in the generated descriptor or run /ca-doctor." };
    }
    if (category === "READ") return undefined;
    const active = new Set(pi.getActiveTools());
    const info = pi.getAllTools().find((tool) => tool.name === name);
    if (!active.has(name) || info === undefined || !samePath(info.sourceInfo.path, wrapperSourcePath)) {
      return { block: true, reason: `Governed Pi tool ${name} has source drift or no active final-execution wrapper; mutation blocked; run /ca-doctor.` };
    }
    return undefined;
  });
}

export function bridgeToolResults(
  pi: ToolResultPiPort,
  bridge: BridgePort,
  descriptor: Readonly<Record<string, ToolCategory>>,
  activeGeneration: () => LifecycleGeneration | undefined = () => STANDALONE_GENERATION,
): void {
  pi.on("tool_result", async (event, context) => {
    const generation = activeGeneration();
    if (generation === undefined) return undefined;
    const name = typeof event.toolName === "string" ? event.toolName : "";
    const category = descriptor[name] ?? "OTHER";
    if (category !== "WRITE" && category !== "EDIT") return undefined;
    let response: Awaited<ReturnType<BridgePort["call"]>>;
    try {
      response = await bridge.call({
        version: 1,
        event: "tool_result",
        cwd: context.cwd,
        tool: name,
        input: event.input,
        result: { content: event.content, isError: event.isError === true },
      }, context.signal ?? new AbortController().signal);
    } catch (error) {
      if (activeGeneration() !== generation) return undefined;
      throw error;
    }
    if (activeGeneration() !== generation) return undefined;
    if (response.outcome === "warn" && response.message !== undefined) {
      context.ui.notify(response.message, "warning");
    }
    return applyToolResultNotice(event, response);
  });
}
