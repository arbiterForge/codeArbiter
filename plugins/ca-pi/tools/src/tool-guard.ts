import type {
  BridgePort,
  BuiltinToolFactories,
  ToolCategory,
  ToolDefinitionPort,
  ToolExecutionContextPort,
  ToolGuardPiPort,
  ToolResultPiPort,
} from "./contracts.ts";
import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants, realpathSync } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { types as utilTypes } from "node:util";
import { safeDiagnostic } from "./redaction.ts";
import { applyToolResultNotice } from "./notices.ts";
import {
  POLICY_ACTION_CLASSES,
  compilePermissionPolicyDescriptor,
  evaluatePolicy,
} from "./policy.ts";
import type {
  CompiledPermissionPolicyDescriptor,
  PolicyActionClass,
  PolicyMode,
} from "./policy.ts";

type LifecycleGeneration = object;
const STANDALONE_GENERATION: LifecycleGeneration = Object.freeze({});

export interface WrapBuiltinsOptions {
  cwd: string;
  descriptor: Readonly<Record<string, ToolCategory>>;
  factories: BuiltinToolFactories;
  nativeFactories?: BuiltinToolFactories;
  wrapperSourcePath: string;
  permissionPolicy?: CompiledPermissionPolicyDescriptor;
  getMode?: () => PolicyMode;
  permissionAudit?: PermissionAuditPort;
}

export interface WrapCustomToolOptions {
  cwd: string;
  name: string;
  bridgeToolName?: string;
  descriptor: Readonly<Record<string, ToolCategory>>;
  factory: (cwd: string) => ToolDefinitionPort;
  wrapperSourcePath: string;
  permissionPolicy?: CompiledPermissionPolicyDescriptor;
  getMode?: () => PolicyMode;
  permissionAudit?: PermissionAuditPort;
}

export type PermissionAuditDecision = "allow" | "approved" | "cancelled" | "denied";
export type PermissionAuditCode = "PI_PERMISSION_UNCLASSIFIED" | "PI_PERMISSION_INVALID_MODE";

interface PermissionAuditBase {
  readonly timestamp: string;
  readonly correlation: string;
  readonly toolClass: ToolCategory;
}

export type PermissionAuditRow = Readonly<PermissionAuditBase & (
  | { readonly actionClasses: readonly PolicyActionClass[]; readonly decision: PermissionAuditDecision; readonly auditCode?: never }
  | { readonly auditCode: PermissionAuditCode; readonly actionClasses?: never; readonly decision?: never }
)>;

export type PermissionAuditPort = (cwd: string, row: PermissionAuditRow) => Promise<boolean>;

export interface BackgroundJobAuditRow {
  readonly timestamp: string;
  readonly lifecycleId: string;
  readonly correlation: string;
  readonly event: "launch" | "terminal" | "cancel";
  readonly id: number;
  readonly state?: "queued" | "active" | "completed" | "failed" | "cancelled" | "timed-out";
  readonly timeoutMs?: number | null;
  readonly outputBytes?: number;
  readonly accepted?: boolean;
  readonly durationMs?: number;
  readonly exitClass?: "success" | "failure" | "cancelled" | "timeout";
}

interface PermissionAuditStatsPort {
  readonly dev: number;
  readonly ino: number;
  readonly nlink: number;
  readonly size: number;
  isDirectory(): boolean;
  isFile(): boolean;
  isSymbolicLink(): boolean;
}

interface PermissionAuditHandlePort {
  stat(): Promise<PermissionAuditStatsPort>;
  appendFile(data: string, options: { encoding: "utf8" }): Promise<unknown>;
  sync(): Promise<void>;
  close(): Promise<void>;
}

export interface PermissionAuditIoPort {
  realpath(path: string): Promise<string>;
  lstat(path: string): Promise<PermissionAuditStatsPort>;
  open(path: string, flags: number, mode?: number): Promise<PermissionAuditHandlePort>;
}

const NODE_PERMISSION_AUDIT_IO: PermissionAuditIoPort = Object.freeze({ realpath, lstat, open });

const CONFIRMATION_TITLE = "Allow governed operation?";
const CONFIRMATION_TIMEOUT_MS = 60_000;
const COMMAND_LIMIT = 8_192;
const SHELL_CONTROL = /[\r\n\u0000;&|<>`(){}]|\$\(/u;
const DANGEROUS_INSPECTION_OPTION = /(?:^|\s)(?:--ext-diff|--textconv|--config-env|--output|--pre|--hostname-bin|--search-zip)(?:[=\s]|$)/iu;
const CONFIG_PATH = /(?:^|\/)(?:\.codearbiter|\.github)(?:\/|$)|(?:^|\/)(?:package(?:-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|tsconfig(?:\.[^/]*)?\.json|pyproject\.toml|cargo\.toml|cargo\.lock|go\.mod|go\.sum|dockerfile|makefile|\.env(?:\.[^/]*)?|[^/]+\.(?:json|ya?ml|toml|ini|cfg|conf|lock))(?:$)/iu;
const INSPECTION_COMMANDS = Object.freeze([
  /^(?:pwd|cd|ls|dir|Get-ChildItem|Get-Location)(?:\s+[^;&|<>`]*)?$/iu,
  /^(?:cat|type|Get-Content|head|tail|wc|where|where\.exe|Get-Command)(?:\s+[^;&|<>`]*)?$/iu,
  /^(?:rg|grep|findstr)(?![^\r\n]*(?:--pre|--hostname-bin|--search-zip))(?:\s+[^;&|<>`]*)?$/iu,
  /^git\s+(?:status(?:\s+[^;&|<>`]*)?|log(?=[^;&|<>`]*--no-ext-diff(?:\s|$))(?=[^;&|<>`]*--no-textconv(?:\s|$))(?:\s+[^;&|<>`]*)?|show(?=[^;&|<>`]*--no-ext-diff(?:\s|$))(?=[^;&|<>`]*--no-textconv(?:\s|$))(?:\s+[^;&|<>`]*)?|branch\s+--show-current|rev-parse(?:\s+[^;&|<>`]*)?|diff(?=[^;&|<>`]*--no-ext-diff(?:\s|$))(?=[^;&|<>`]*--no-textconv(?:\s|$))(?:\s+[^;&|<>`]*)?|add\s+[^;&|<>`]*--dry-run[^;&|<>`]*)$/iu,
]);
const DEPENDENCY_COMMAND = /(?:^|\s)(?:npm\s+(?:i|install|ci|uninstall|update)|pnpm\s+(?:add|install|remove|update)|yarn\s+(?:add|install|remove|upgrade)|bun\s+(?:add|install|remove|update)|pip(?:3)?\s+(?:install|uninstall)|python(?:3)?\s+-m\s+pip\s+(?:install|uninstall)|cargo\s+(?:add|remove|update)|dotnet\s+(?:add|remove)\s+package)(?:\s|$)/iu;
const NETWORK_COMMAND = /(?:^|\s)(?:curl|wget|Invoke-WebRequest|iwr|git\s+(?:push|pull|fetch)|gh\s+|npm\s+(?:i|install|ci|publish)|pnpm\s+(?:add|install)|yarn\s+(?:add|install)|bun\s+(?:add|install)|pip(?:3)?\s+install|python(?:3)?\s+-m\s+pip\s+install|cargo\s+(?:add|publish)|twine\s+upload)(?:\s|$)/iu;
const EXTERNAL_COMMAND = /(?:^|\s)(?:curl|wget|Invoke-WebRequest|iwr|gh\s+|git\s+push|npm\s+(?:i|install|ci|publish)|pnpm\s+(?:add|install)|yarn\s+(?:add|install)|bun\s+(?:add|install)|pip(?:3)?\s+install|python(?:3)?\s+-m\s+pip\s+install|cargo\s+(?:add|publish)|twine\s+upload)(?:\s|$)/iu;
const PUSH_COMMAND = /(?:^|\s)git\s+push(?:\s|$)/iu;
const RELEASE_COMMAND = /(?:^|\s)(?:gh\s+release|npm\s+publish|cargo\s+publish|twine\s+upload|dotnet\s+nuget\s+push|git\s+tag)(?:\s|$)/iu;

function hasOwn(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

export function compileBuiltinPermissionPolicy(
  toolClasses: Readonly<Record<string, ToolCategory>>,
  actionClasses: Readonly<Record<string, string>>,
): CompiledPermissionPolicyDescriptor | undefined {
  return compilePermissionPolicyDescriptor({ toolClasses: { ...toolClasses }, actionClasses: { ...actionClasses } });
}

function orderedActions(values: ReadonlySet<PolicyActionClass>): readonly PolicyActionClass[] {
  return Object.freeze(POLICY_ACTION_CLASSES.filter((value) => values.has(value)));
}

function normalizedPath(params: Readonly<Record<string, unknown>>): string | undefined {
  const value = hasOwn(params, "path") ? params.path : hasOwn(params, "file_path") ? params.file_path : undefined;
  if (typeof value !== "string" || value.length === 0 || value.length > 4_096 || /[\u0000-\u001f\u007f]/u.test(value)) return undefined;
  return value.replace(/\\/gu, "/");
}

/** Derives closed policy labels from canonical request facts only. */
export function classifyPermissionActions(
  descriptor: CompiledPermissionPolicyDescriptor,
  tool: string,
  params: Readonly<Record<string, unknown>>,
): readonly PolicyActionClass[] | undefined {
  try {
    if (!hasOwn(descriptor.toolClasses, tool)) return undefined;
    const category = descriptor.toolClasses[tool];
    if (category === "OTHER" || category === undefined) return undefined;
    const exact = hasOwn(descriptor.actionClasses, tool) ? descriptor.actionClasses[tool] : undefined;
    const background = exact === "background-launch";
    if (exact !== undefined && !background) return orderedActions(new Set<PolicyActionClass>([exact]));
    if (category === "READ") return Object.freeze(["read"]);
    if (category === "WRITE" || category === "EDIT") {
      const path = normalizedPath(params);
      if (path === undefined) return undefined;
      const config = CONFIG_PATH.test(path);
      return Object.freeze([category === "WRITE"
        ? (config ? "config-write" : "source-write")
        : (config ? "config-edit" : "source-edit")]);
    }
    if (category !== "EXEC") return undefined;
    const command = hasOwn(params, "command") ? params.command : undefined;
    if (typeof command !== "string" || command.length === 0 || command.length > COMMAND_LIMIT) return undefined;
    const normalized = command.trim().replace(/\s+/gu, " ");
    const labels = new Set<PolicyActionClass>(["shell-mutation"]);
    if (background) labels.add("background-launch");
    if (normalized === "" || SHELL_CONTROL.test(command) || DANGEROUS_INSPECTION_OPTION.test(normalized)) {
      return orderedActions(labels);
    }
    if (!background && INSPECTION_COMMANDS.some((pattern) => pattern.test(normalized))) return Object.freeze(["inspection"]);
    if (DEPENDENCY_COMMAND.test(normalized)) labels.add("dependency-change");
    if (NETWORK_COMMAND.test(normalized)) labels.add("network-side-effect");
    if (EXTERNAL_COMMAND.test(normalized)) labels.add("external-side-effect");
    if (PUSH_COMMAND.test(normalized)) labels.add("push");
    if (RELEASE_COMMAND.test(normalized)) labels.add("release");
    return orderedActions(labels);
  } catch {
    return undefined;
  }
}

function auditCorrelation(toolCallId: string): string {
  return createHash("sha256").update(toolCallId, "utf8").digest("hex");
}

function permissionAuditRow(
  toolCallId: string,
  toolClass: ToolCategory,
  actionClasses: readonly PolicyActionClass[],
  decision: PermissionAuditDecision,
): PermissionAuditRow {
  return Object.freeze({
    timestamp: new Date().toISOString(),
    correlation: auditCorrelation(toolCallId),
    toolClass,
    actionClasses: Object.freeze([...actionClasses]),
    decision,
  });
}

function permissionAuditCodeRow(
  toolCallId: string,
  toolClass: ToolCategory,
  auditCode: PermissionAuditCode,
): PermissionAuditRow {
  return Object.freeze({
    timestamp: new Date().toISOString(),
    correlation: auditCorrelation(toolCallId),
    toolClass,
    auditCode,
  });
}

/** Appends one closed, command-free permission row. Approved mutation audit is fail-closed. */
function sameAuditFile(left: PermissionAuditStatsPort, right: PermissionAuditStatsPort): boolean {
  return left.isFile() && right.isFile()
    && !left.isSymbolicLink() && !right.isSymbolicLink()
    && left.nlink === 1 && right.nlink === 1
    && left.dev === right.dev && left.ino === right.ino;
}

function sameAuditDirectory(left: PermissionAuditStatsPort, right: PermissionAuditStatsPort): boolean {
  return left.isDirectory() && right.isDirectory()
    && !left.isSymbolicLink() && !right.isSymbolicLink()
    && left.dev === right.dev && left.ino === right.ino;
}

async function openedAuditTarget(
  target: string,
  io: PermissionAuditIoPort,
): Promise<Readonly<{ handle: PermissionAuditHandlePort; identity: PermissionAuditStatsPort }> | undefined> {
  const noFollow = typeof fsConstants.O_NOFOLLOW === "number" ? fsConstants.O_NOFOLLOW : 0;
  const existingFlags = fsConstants.O_WRONLY | fsConstants.O_APPEND | noFollow;
  const createFlags = existingFlags | fsConstants.O_CREAT | fsConstants.O_EXCL;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let expected: PermissionAuditStatsPort | undefined;
    try {
      expected = await io.lstat(target);
      if (!expected.isFile() || expected.isSymbolicLink() || expected.nlink !== 1) return undefined;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") return undefined;
    }
    let handle: PermissionAuditHandlePort;
    try {
      handle = await io.open(target, expected === undefined ? createFlags : existingFlags, 0o600);
    } catch (error) {
      if (expected === undefined && (error as NodeJS.ErrnoException).code === "EEXIST" && attempt === 0) continue;
      return undefined;
    }
    try {
      const opened = await handle.stat();
      const pathname = await io.lstat(target);
      if (!sameAuditFile(opened, pathname) || expected !== undefined && !sameAuditFile(opened, expected)) {
        await handle.close();
        return undefined;
      }
      return Object.freeze({ handle, identity: opened });
    } catch {
      try { await handle.close(); } catch { /* fail closed below */ }
      return undefined;
    }
  }
  return undefined;
}

async function appendAuditLineWithIo(cwd: string, line: string, io: PermissionAuditIoPort): Promise<boolean> {
  try {
    if (Buffer.byteLength(line, "utf8") > 2_048 || !line.endsWith("\n") || line.slice(0, -1).includes("\n")) return false;
    const root = await io.realpath(cwd);
    const statePath = resolve(root, ".codearbiter");
    const stateInfo = await io.lstat(statePath);
    if (!stateInfo.isDirectory() || stateInfo.isSymbolicLink()) return false;
    const state = await io.realpath(statePath);
    const stateRelative = relative(root, state);
    if (stateRelative === "" || stateRelative.startsWith("..") || resolve(root, stateRelative) !== state) return false;
    const stateIdentity = await io.lstat(state);
    if (!sameAuditDirectory(stateInfo, stateIdentity)) return false;
    const stateIsCurrent = async (): Promise<boolean> => {
      try {
        return await io.realpath(statePath) === state
          && sameAuditDirectory(stateIdentity, await io.lstat(statePath));
      } catch {
        return false;
      }
    };
    if (!await stateIsCurrent()) return false;
    const target = resolve(state, "gate-events.log");
    const opened = await openedAuditTarget(target, io);
    if (opened === undefined) return false;
    const { handle, identity } = opened;
    try {
      const before = await handle.stat();
      const beforePath = await io.lstat(target);
      if (!sameAuditFile(identity, before) || !sameAuditFile(before, beforePath) || !await stateIsCurrent()) return false;
      await handle.appendFile(line, { encoding: "utf8" });
      await handle.sync();
      const after = await handle.stat();
      const afterPath = await io.lstat(target);
      if (!sameAuditFile(before, after) || !sameAuditFile(after, afterPath)
        || after.size < before.size + Buffer.byteLength(line, "utf8") || !await stateIsCurrent()) return false;
    } finally {
      await handle.close();
    }
    return true;
  } catch {
    return false;
  }
}

export async function appendPermissionAuditWithIo(
  cwd: string,
  row: PermissionAuditRow,
  io: PermissionAuditIoPort,
): Promise<boolean> {
  try {
    const timestamp = row.timestamp;
    const correlation = row.correlation;
    const toolClass = row.toolClass;
    const actionClasses = row.actionClasses;
    const decision = row.decision;
    const auditCode = row.auditCode;
    const codeRow = auditCode !== undefined;
    if (typeof timestamp !== "string" || timestamp.length !== 24
      || new Date(timestamp).toISOString() !== timestamp
      || typeof correlation !== "string" || !/^[a-f0-9]{64}$/u.test(correlation)
      || !(["EXEC", "WRITE", "EDIT", "READ", "OTHER"] as const).includes(toolClass)
      || (codeRow
        ? actionClasses !== undefined || decision !== undefined
          || !(["PI_PERMISSION_UNCLASSIFIED", "PI_PERMISSION_INVALID_MODE"] as const).includes(auditCode)
        : !Array.isArray(actionClasses) || actionClasses.length < 1 || actionClasses.length > POLICY_ACTION_CLASSES.length
          || actionClasses.some((action, index) => !POLICY_ACTION_CLASSES.includes(action)
            || POLICY_ACTION_CLASSES.indexOf(action) <= (index === 0 ? -1 : POLICY_ACTION_CLASSES.indexOf(actionClasses[index - 1]!)))
          || !(["allow", "approved", "cancelled", "denied"] as const).includes(decision!))) return false;
    return await appendAuditLineWithIo(cwd, [
      `[${timestamp}]`, "HOST: pi", "RULE: PI-PERMISSION", `CORRELATION: ${correlation}`,
      `TOOL_CLASS: ${toolClass}`,
      ...(codeRow ? [`AUDIT: ${auditCode}`] : [`ACTION_CLASSES: ${actionClasses!.join(",")}`, `DECISION: ${decision}`]),
    ].join(" | ") + "\n", io);
  } catch { return false; }
}

export async function appendBackgroundJobAudit(cwd: string, row: BackgroundJobAuditRow): Promise<boolean> {
  try {
    const keys = Object.keys(row).sort().join(",");
    const expectedKeys = row.event === "launch" ? "correlation,event,id,lifecycleId,state,timeoutMs,timestamp"
      : row.event === "terminal" ? "correlation,durationMs,event,exitClass,id,lifecycleId,outputBytes,state,timestamp"
        : row.event === "cancel" ? "accepted,correlation,event,id,lifecycleId,timestamp" : "";
    if (keys !== expectedKeys || row.timestamp.length !== 24 || new Date(row.timestamp).toISOString() !== row.timestamp
      || !/^[a-f0-9]{64}$/u.test(row.lifecycleId) || !/^[a-f0-9]{64}$/u.test(row.correlation)
      || !Number.isSafeInteger(row.id) || row.id < 1
      || (row.event === "launch" && (!(["queued", "active", "completed", "failed", "cancelled", "timed-out"] as const).includes(row.state as never)
        || row.timeoutMs !== null && (!Number.isSafeInteger(row.timeoutMs) || row.timeoutMs! < 1_000 || row.timeoutMs! > 604_800_000)))
      || (row.event === "terminal" && (!(["completed", "failed", "cancelled", "timed-out"] as const).includes(row.state as never)
        || !(["success", "failure", "cancelled", "timeout"] as const).includes(row.exitClass as never)
        || row.exitClass !== (row.state === "completed" ? "success" : row.state === "failed" ? "failure"
          : row.state === "cancelled" ? "cancelled" : "timeout")
        || !Number.isSafeInteger(row.durationMs) || row.durationMs! < 0
        || !Number.isSafeInteger(row.outputBytes) || row.outputBytes! < 0 || row.outputBytes! > 65_536))
      || (row.event === "cancel" && typeof row.accepted !== "boolean")) return false;
    return await appendAuditLineWithIo(cwd, [
      `[${row.timestamp}]`, "HOST: pi", "RULE: PI-BACKGROUND-JOB", `CORRELATION: ${row.correlation}`,
      `LIFECYCLE: ${row.lifecycleId}`, `EVENT: ${row.event}`, `JOB_ID: ${row.id}`,
      ...(row.state === undefined ? [] : [`STATE: ${row.state}`]),
      ...(row.timeoutMs === undefined ? [] : [`TIMEOUT_MS: ${row.timeoutMs === null ? "none" : row.timeoutMs}`]),
      ...(row.outputBytes === undefined ? [] : [`OUTPUT_BYTES: ${row.outputBytes}`]),
      ...(row.durationMs === undefined ? [] : [`DURATION_MS: ${row.durationMs}`]),
      ...(row.exitClass === undefined ? [] : [`EXIT_CLASS: ${row.exitClass}`]),
      ...(row.accepted === undefined ? [] : [`ACCEPTED: ${row.accepted}`]),
    ].join(" | ") + "\n", NODE_PERMISSION_AUDIT_IO);
  } catch { return false; }
}

export async function appendPermissionAudit(cwd: string, row: PermissionAuditRow): Promise<boolean> {
  return await appendPermissionAuditWithIo(cwd, row, NODE_PERMISSION_AUDIT_IO);
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
  if (typeof value !== "object" || seen.has(value) || utilTypes.isProxy(value)) throw new TypeError("parameters are not acyclic JSON");
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      const descriptors = Object.getOwnPropertyDescriptors(value) as Record<string, PropertyDescriptor>;
      const length = descriptors.length?.value;
      if (!Number.isSafeInteger(length) || length < 0 || Reflect.ownKeys(value).length !== length + 1) {
        throw new TypeError("parameters contain a sparse or decorated array");
      }
      const output: unknown[] = [];
      for (let index = 0; index < length; index += 1) {
        const descriptor = descriptors[String(index)];
        if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) {
          throw new TypeError("parameters contain an accessor");
        }
        output.push(canonicalSnapshot(descriptor.value, seen, depth + 1));
      }
      return Object.freeze(output);
    }
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) throw new TypeError("parameters contain a non-plain object");
    const output: Record<string, unknown> = {};
    const descriptors = Object.getOwnPropertyDescriptors(value);
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string") throw new TypeError("parameters contain a symbol key");
      if (key === "__proto__" || key === "constructor" || key === "prototype") throw new TypeError("parameters contain an unsafe key");
      const descriptor = descriptors[key];
      if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) {
        throw new TypeError("parameters contain an accessor");
      }
      output[key] = canonicalSnapshot(descriptor.value, seen, depth + 1);
    }
    return Object.freeze(output);
  } finally {
    seen.delete(value);
  }
}

function matchesSnapshot(raw: unknown, snapshot: unknown, seen = new Set<object>(), depth = 0): boolean {
  if (depth > 32) return false;
  if (snapshot === null || typeof snapshot !== "object") return Object.is(raw, snapshot);
  if (raw === null || typeof raw !== "object" || utilTypes.isProxy(raw) || seen.has(raw)) return false;
  seen.add(raw);
  try {
    if (Array.isArray(snapshot)) {
      if (!Array.isArray(raw)) return false;
      const descriptors = Object.getOwnPropertyDescriptors(raw) as Record<string, PropertyDescriptor>;
      if (descriptors.length?.value !== snapshot.length || Reflect.ownKeys(raw).length !== snapshot.length + 1) return false;
      return snapshot.every((item, index) => {
        const descriptor = descriptors[String(index)];
        return descriptor !== undefined && "value" in descriptor && descriptor.enumerable === true
          && matchesSnapshot(descriptor.value, item, seen, depth + 1);
      });
    }
    if (Array.isArray(raw) || Object.getPrototypeOf(raw) !== Object.prototype && Object.getPrototypeOf(raw) !== null) return false;
    const descriptors = Object.getOwnPropertyDescriptors(raw);
    const rawKeys = Reflect.ownKeys(raw);
    const snapshotKeys = Object.keys(snapshot as Record<string, unknown>);
    if (rawKeys.some((key) => typeof key !== "string") || rawKeys.length !== snapshotKeys.length) return false;
    return snapshotKeys.every((key) => {
      const descriptor = descriptors[key];
      return descriptor !== undefined && "value" in descriptor && descriptor.enumerable === true
        && matchesSnapshot(descriptor.value, (snapshot as Record<string, unknown>)[key], seen, depth + 1);
    });
  } catch {
    return false;
  } finally {
    seen.delete(raw);
  }
}

function currentMode(getMode: () => PolicyMode): PolicyMode | undefined {
  try {
    const mode = getMode();
    return mode === "execute" || mode === "plan" ? mode : undefined;
  } catch {
    return undefined;
  }
}

function registryOwns(
  pi: ToolGuardPiPort,
  tool: string,
  wrapperSourcePath: string,
): boolean {
  try {
    if (!pi.getActiveTools().includes(tool)) return false;
    const info = pi.getAllTools().find((candidate) => candidate.name === tool);
    return info !== undefined && samePath(info.sourceInfo.path, wrapperSourcePath);
  } catch {
    return false;
  }
}

function confirmationMessage(actions: readonly PolicyActionClass[], cwd: string, consequence: string): string {
  return [
    `Action classes: ${actions.join(", ")}`,
    `Working directory: ${cwd}`,
    `Consequence: ${consequence}`,
  ].join("\n");
}

function confirmationUi(context: ToolExecutionContextPort | undefined): Readonly<{
  ui: NonNullable<ToolExecutionContextPort["ui"]>;
  confirm: NonNullable<NonNullable<ToolExecutionContextPort["ui"]>["confirm"]>;
}> | undefined {
  try {
    if (context?.mode !== "tui" || context.hasUI !== true) return undefined;
    const ui = context.ui;
    const confirm = ui?.confirm;
    return ui !== undefined && typeof confirm === "function" ? Object.freeze({ ui, confirm }) : undefined;
  } catch {
    return undefined;
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
  pi: ToolGuardPiPort,
  toolName: string,
  factory: (cwd: string) => ToolDefinitionPort,
  nativeFactory: (cwd: string) => ToolDefinitionPort,
  category: ToolCategory,
  cwd: string,
  bridge: BridgePort,
  boundGeneration: LifecycleGeneration,
  activeGeneration: () => LifecycleGeneration | undefined,
  isReady: () => boolean,
  sessionIdFor: (context: ToolExecutionContextPort | undefined) => string,
  permissionPolicy: CompiledPermissionPolicyDescriptor,
  getMode: () => PolicyMode,
  permissionAudit: PermissionAuditPort | undefined,
  wrapperSourcePath: string,
  allowNativeFallback = true,
  bridgeToolName = toolName,
): ToolDefinitionPort {
  const original = factory(cwd);
  if (original.name !== toolName || typeof original.execute !== "function") {
    throw new Error(`Pi built-in ${toolName} factory identity is invalid; run /ca-doctor.`);
  }
  const originalExecute = original.execute;
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
        if (!allowNativeFallback || (generation !== undefined && category !== "READ")) {
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
          tool: bridgeToolName,
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
      if (response.outcome !== "allow" && response.outcome !== "notice" && response.outcome !== "warn") {
        return failTool("Mutation bridge returned an unknown verdict; mutation blocked; run /ca-doctor.");
      }
      const mode = currentMode(getMode);
      const actions = classifyPermissionActions(permissionPolicy, toolName, approved);
      const policy = mode === undefined || actions === undefined
        ? { decision: "deny" as const }
        : evaluatePolicy(permissionPolicy, { mode, tool: toolName, actions, cwd });
      const audit = async (decision: PermissionAuditDecision): Promise<boolean> => {
        if (actions === undefined || permissionAudit === undefined) return false;
        try {
          return await permissionAudit(
            cwd,
            permissionAuditRow(toolCallId, category, actions, decision),
          ) === true;
        } catch {
          return false;
        }
      };
      const auditFixed = async (auditCode: PermissionAuditCode): Promise<boolean> => {
        if (permissionAudit === undefined) return false;
        try {
          return await permissionAudit(cwd, permissionAuditCodeRow(toolCallId, category, auditCode)) === true;
        } catch {
          return false;
        }
      };
      if (policy.decision === "deny" || actions === undefined || mode === undefined) {
        if (actions === undefined) await auditFixed("PI_PERMISSION_UNCLASSIFIED");
        else if (mode === undefined) await auditFixed("PI_PERMISSION_INVALID_MODE");
        else await audit("denied");
        return failTool("Pi permission policy denied this operation; run /ca-doctor.");
      }
      const executeOriginal = async () => await originalExecute.call(original, toolCallId, approved, signal, onUpdate, context);
      const revalidate = (): "current" | "lifecycle-stale" | "request-stale" => {
        const requestStable = currentMode(getMode) === mode
          && registryOwns(pi, toolName, wrapperSourcePath)
          && original.execute === originalExecute
          && matchesSnapshot(params, approved)
          && signal?.aborted !== true;
        if (!requestStable) return "request-stale";
        return activeGeneration() === generation && generation === boundGeneration && isReady()
          ? "current"
          : "lifecycle-stale";
      };
      if (policy.decision === "ask") {
        const confirmation = confirmationUi(context);
        if (confirmation === undefined) {
          await audit("denied");
          return failTool("Pi confirmation UI is unavailable; mutation blocked.");
        }
        if (!registryOwns(pi, toolName, wrapperSourcePath) || original.execute !== originalExecute) {
          await audit("denied");
          return failTool("Pi tool ownership changed before confirmation; mutation blocked; run /ca-doctor.");
        }
        let confirmed = false;
        try {
          confirmed = await confirmation.confirm.call(
            confirmation.ui,
            CONFIRMATION_TITLE,
            confirmationMessage(policy.confirmation.actionClasses, policy.confirmation.cwd, policy.confirmation.consequence),
            { timeout: CONFIRMATION_TIMEOUT_MS, signal },
          ) === true;
        } catch {
          confirmed = false;
        }
        if (!confirmed) {
          await audit("cancelled");
          return failTool("Pi permission confirmation was cancelled; mutation blocked.");
        }
        if (revalidate() !== "current") {
          await audit("denied");
          return failTool("Pi permission approval became stale; mutation blocked; run /ca-doctor.");
        }
        if (!await audit("approved")) {
          return failTool("Pi permission audit is unavailable; approved mutation blocked; run /ca-doctor.");
        }
        if (revalidate() !== "current") {
          return failTool("Pi permission approval became stale; mutation blocked; run /ca-doctor.");
        }
      } else {
        // Read/inspection audit is best effort: it never turns a non-mutating allow into a mutation.
        await audit("allow");
        const current = revalidate();
        if (current !== "current") {
          if (current === "lifecycle-stale" && category === "READ") {
            return await executeNativeFromContext(toolCallId, approved, signal, onUpdate, context);
          }
          return failTool("Pi permission allowance became stale; operation blocked; run /ca-doctor.");
        }
      }
      const result = await executeOriginal();
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
  const permissionPolicy = options.permissionPolicy ?? compileBuiltinPermissionPolicy(options.descriptor, {});
  if (permissionPolicy === undefined) throw new Error("Pi permission policy descriptor is invalid; run /ca-doctor.");
  const getMode = options.getMode ?? (() => "execute" as const);
  for (const name of ["bash", "write", "edit", "read"] as const) {
    if (wrapped.has(name) && definitionGenerations?.get(name) === boundGeneration) continue;
    const category = options.descriptor[name] ?? "OTHER";
    if (category === "OTHER") throw new Error(`Pi descriptor does not classify built-in ${name}; run /ca-doctor.`);
    const definition = wrappedDefinition(
      pi,
      name,
      options.factories[name],
      (options.nativeFactories ?? options.factories)[name],
      category,
      options.cwd,
      bridge,
      boundGeneration,
      activeGeneration,
      isReady,
      sessionIdFor,
      permissionPolicy,
      getMode,
      options.permissionAudit,
      options.wrapperSourcePath,
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

  ensureCustomTool(pi: ToolGuardPiPort, bridge: BridgePort, options: WrapCustomToolOptions): void {
    const boundGeneration = this.lifecycleGeneration ?? STANDALONE_GENERATION;
    if (this.wrapped.has(options.name) && this.definitionGenerations.get(options.name) === boundGeneration) return;
    const category = options.descriptor[options.name] ?? "OTHER";
    if (category === "OTHER" || category === "READ") {
      throw new Error(`Pi descriptor does not classify custom mutator ${options.name}; run /ca-doctor.`);
    }
    const bridgeToolName = options.bridgeToolName ?? options.name;
    if ((options.descriptor[bridgeToolName] ?? "OTHER") !== category) {
      throw new Error("Pi custom tool bridge alias category is invalid; run /ca-doctor.");
    }
    const permissionPolicy = options.permissionPolicy
      ?? compileBuiltinPermissionPolicy(options.descriptor, {});
    if (permissionPolicy === undefined) throw new Error("Pi permission policy descriptor is invalid; run /ca-doctor.");
    const definition = wrappedDefinition(
      pi,
      options.name,
      options.factory,
      options.factory,
      category,
      options.cwd,
      bridge,
      boundGeneration,
      () => this.lifecycleGeneration,
      () => this.ready,
      (context) => this.sessionIdFor(context),
      permissionPolicy,
      options.getMode ?? (() => "execute" as const),
      options.permissionAudit,
      options.wrapperSourcePath,
      false,
      bridgeToolName,
    );
    pi.registerTool(definition);
    this.definitions.set(options.name, definition);
    this.definitionGenerations.set(options.name, boundGeneration);
    this.wrapped.add(options.name);
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
