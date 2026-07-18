/** runner.ts - codeArbiter's bounded fresh-process Pi child runner. */
import { randomBytes, randomUUID } from "node:crypto";
import { readFile, realpath, stat } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { StringDecoder } from "node:string_decoder";
import { fileURLToPath } from "node:url";

import { buildChildEnv, PI_PROVIDER_ENV } from "./child-env.ts";
import {
  CHILD_ATTESTATION_TIMEOUT_MS,
  CHILD_ATTESTATION_TITLE,
  childAttestationDigest,
} from "./attestation.ts";
import { compatibilityDirection } from "./compatibility.ts";
import { safeDiagnostic } from "./redaction.ts";
import { loadRoleCatalog } from "./roles.ts";
import { resolvePiRuntimeIdentity } from "./runtime-resolver.ts";
import {
  WINDOWS_SUPERVISOR_REFUSAL_REASONS,
  createProcessTreeCleanup,
  spawnProcessTree,
  windowsRefusalReasonFromMessage,
  type ProcessTreeCleanupReason,
  type WindowsSupervisorRefusalReason,
} from "./process-tree.ts";

const MAX_TASK_BYTES = 65_536;
const MAX_JSONL_LINE_BYTES = 65_536;
const MAX_STDOUT_BYTES = 1_048_576;
const MAX_STDERR_BYTES = 16_384;
const MAX_OUTPUT_BYTES = 65_536;
const HANDSHAKE_COMMAND = "codearbiter-internal-child-handshake";
const ALLOWED_TOOLS = new Set(["read", "bash", "edit", "write"]);
const MAX_JSON_DEPTH = 8;
const MAX_JSON_NODES = 2_048;
const MAX_JSON_KEYS = 64;
const MAX_JSON_ARRAY = 256;
const MAX_JSON_STRING_BYTES = 65_536;

interface ChildLaunchCommon {
  nodePath: string;
  piCliPath: string;
  provider: string;
  model: string;
  cwd: string;
  childExtensionPath: string;
  charterPath: string;
}

export interface RoleChildLaunchInput extends ChildLaunchCommon {
  launchKind?: "role";
  tools: readonly string[];
  skillPaths: readonly string[];
}

export interface InternalCompactionLaunchInput extends ChildLaunchCommon {
  launchKind: "internal-compaction";
  tools: readonly [];
  skillPaths: readonly [];
}

export type ChildLaunchInput = RoleChildLaunchInput | InternalCompactionLaunchInput;

export type PiChildRequest = ChildLaunchInput & {
  task: string;
  parentEnv?: Readonly<NodeJS.ProcessEnv>;
  platform?: NodeJS.Platform;
  timeoutMs?: number;
};

export interface ChildResult {
  terminal: "completed" | "degraded";
  pid?: number;
  correlationId?: string;
  output?: string;
  diagnostic?: string;
  /** Best-effort observability metrics for the audit sink; never a substitute for the
   * fail-open/fail-closed protocol decision itself, which is driven by `terminal`. */
  durationMs?: number;
  exitCode?: number;
  stdoutBytes?: number;
  stderrBytes?: number;
  /** Bounded, UNREDACTED raw stderr bytes captured from the child — the leading MAX_STDERR_BYTES
   * of stderr, not a rolling tail (named for what it holds, not stream position). Callers (e.g.
   * dispatch.ts's audit writer) MUST redact this via redaction.ts's safeDiagnostic before it is
   * ever logged, displayed, or otherwise persisted. */
  stderrHead?: string;
}

interface RuntimeIdentityPort {
  cliEntry: string;
  packageRoot: string;
  version: string;
}

interface LaunchValidationDependencies {
  activeNodePath?: string;
  packageRoot?: string;
  resolveRuntimeIdentity?: (candidate: string) => Promise<RuntimeIdentityPort>;
}

interface CapabilityPipe {
  destroyed?: boolean;
  writable?: boolean;
  on(event: "error", handler: () => void): unknown;
  end(chunk: string, encoding: BufferEncoding): unknown;
}

function isCapabilityPipe(value: unknown): value is CapabilityPipe {
  return value !== null && value !== undefined && typeof (value as CapabilityPipe).on === "function"
    && typeof (value as CapabilityPipe).end === "function";
}

function assertLaunchShape(input: ChildLaunchInput): void {
  const compaction = input.launchKind === "internal-compaction";
  for (const [label, path] of [
    ["Node executable", input.nodePath],
    ["Pi CLI", input.piCliPath],
    ["child extension", input.childExtensionPath],
    [compaction ? "compaction charter" : "role charter", input.charterPath],
    ["working directory", input.cwd],
    ...input.skillPaths.map((path) => [compaction ? "compaction skill" : "role skill", path] as const),
  ] as const) {
    if (typeof path !== "string" || !isAbsolute(path)) throw new Error(`${label} path must be absolute for isolated child launch.`);
  }
  if (!(input.provider in PI_PROVIDER_ENV)) throw new Error("Unsupported Pi provider for isolated child launch.");
  if (typeof input.model !== "string" || input.model.trim() === "" || /[\r\n\0]/u.test(input.model)) throw new Error("Pi child model is invalid.");
  if (compaction) {
    if (input.tools.length !== 0) throw new Error("Pi internal compaction launches allow no tools.");
    if (input.skillPaths.length !== 0) throw new Error("Pi internal compaction launches allow no skills.");
    if (!input.charterPath.replace(/\\/gu, "/").endsWith("/includes/compaction-charter.md")) {
      throw new Error("Pi internal compaction charter resource is invalid.");
    }
  } else if (input.tools.length === 0 || new Set(input.tools).size !== input.tools.length || input.tools.some((tool) => !ALLOWED_TOOLS.has(tool))) {
    throw new Error("Pi child tools must be a unique explicit built-in allowlist.");
  }
}

async function canonicalFile(path: string, label: string): Promise<string> {
  const canonical = await realpath(path);
  if (!(await stat(canonical)).isFile()) throw new Error(`${label} must be a real file.`);
  return canonical;
}

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

async function owningCaPackageRoot(): Promise<string> {
  let cursor = dirname(await realpath(fileURLToPath(import.meta.url)));
  while (true) {
    try {
      const manifest = JSON.parse(await readFile(resolve(cursor, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") return await realpath(cursor);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    const parent = dirname(cursor);
    if (parent === cursor) throw new Error("Pi child package identity is unavailable.");
    cursor = parent;
  }
}

function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export async function validateChildLaunch(
  input: ChildLaunchInput,
  dependencies: LaunchValidationDependencies = {},
): Promise<ChildLaunchInput> {
  assertLaunchShape(input);
  const cwd = await realpath(input.cwd);
  if (!(await stat(cwd)).isDirectory()) throw new Error("Pi child working directory must be a real directory.");
  const nodePath = await canonicalFile(input.nodePath, "Node executable");
  const activeNodePath = await canonicalFile(dependencies.activeNodePath ?? process.execPath, "active Node executable");
  if (nodePath !== activeNodePath) throw new Error("Pi child Node executable does not match the active Node identity.");

  const piCliPath = await canonicalFile(input.piCliPath, "Pi CLI");
  const runtimeIdentity = await (dependencies.resolveRuntimeIdentity ?? resolvePiRuntimeIdentity)(piCliPath);
  const runtimeCli = await canonicalFile(runtimeIdentity.cliEntry, "resolved Pi CLI");
  const runtimeRoot = await realpath(runtimeIdentity.packageRoot);
  if (runtimeCli !== piCliPath || !inside(piCliPath, runtimeRoot)) throw new Error("Pi child CLI does not match the resolved Pi runtime identity.");
  const incompatibility = compatibilityDirection({ piVersion: runtimeIdentity.version, nodeVersion: process.versions.node, pythonMajor: 3 });
  if (incompatibility !== null) throw new Error(incompatibility);

  const packageRoot = await realpath(dependencies.packageRoot ?? await owningCaPackageRoot());
  const packageManifest = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8")) as { name?: unknown };
  if (packageManifest.name !== "ca-pi") throw new Error("Pi child package identity is invalid.");
  const childExtensionPath = await canonicalFile(input.childExtensionPath, "Pi child extension");
  const expectedChildExtension = await canonicalFile(resolve(packageRoot, "extensions", "codearbiter-child.js"), "packaged Pi child extension");
  if (childExtensionPath !== expectedChildExtension || !inside(childExtensionPath, packageRoot)) {
    throw new Error("Pi child extension escapes the trusted package resource boundary.");
  }
  const compaction = input.launchKind === "internal-compaction";
  const charterPath = await canonicalFile(input.charterPath, compaction ? "Pi compaction charter" : "Pi role charter");
  const skillPaths = await Promise.all(input.skillPaths.map(async (path) => await canonicalFile(path, "Pi role skill")));
  if (compaction) {
    const expectedCharter = await canonicalFile(resolve(packageRoot, "includes", "compaction-charter.md"), "packaged Pi compaction charter");
    if (charterPath !== expectedCharter || !inside(charterPath, packageRoot)) {
      throw new Error("Pi compaction charter resource escapes the trusted package boundary.");
    }
  } else {
    const catalog = await loadRoleCatalog(packageRoot);
    let roleMatched = false;
    for (const role of catalog.values()) {
      const catalogCharter = await canonicalFile(resolve(packageRoot, role.charterPath), "catalog Pi role charter");
      const catalogSkills = await Promise.all(role.skillPaths.map(async (path) => await canonicalFile(resolve(packageRoot, path), "catalog Pi role skill")));
      if (!inside(catalogCharter, packageRoot) || catalogSkills.some((path) => !inside(path, packageRoot))) {
        throw new Error("Pi role catalog resource escapes the trusted package boundary.");
      }
      if (charterPath === catalogCharter && sameStrings(skillPaths, catalogSkills) && sameStrings(input.tools, role.tools)) {
        roleMatched = true;
      }
    }
    if (!roleMatched) throw new Error("Pi child resources do not match one generated role catalog entry.");
  }
  if ([nodePath, piCliPath, childExtensionPath, charterPath, ...skillPaths].some((path) => inside(path, cwd))) {
    throw new Error("Pi child working directory contains a trusted executable or package resource.");
  }
  const common = {
    nodePath,
    piCliPath,
    provider: input.provider,
    model: input.model,
    cwd,
    childExtensionPath,
    charterPath,
  };
  if (compaction) return Object.freeze({
    ...common,
    launchKind: "internal-compaction" as const,
    tools: Object.freeze([]) as readonly [],
    skillPaths: Object.freeze([]) as readonly [],
  });
  return Object.freeze({
    ...common,
    launchKind: "role" as const,
    tools: Object.freeze([...input.tools]),
    skillPaths: Object.freeze(skillPaths),
  });
}

export function buildChildArgv(input: ChildLaunchInput): readonly string[] {
  assertLaunchShape(input);
  const argv = [
    input.piCliPath,
    "--mode", "rpc",
    "--no-approve",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-session",
    "--offline",
    "--provider", input.provider,
    "--model", input.model,
    ...(input.launchKind === "internal-compaction" ? ["--no-tools"] : ["--tools", input.tools.join(",")]),
    "-e", input.childExtensionPath,
    "--append-system-prompt", input.charterPath,
  ];
  for (const skillPath of input.skillPaths) argv.push("--skill", skillPath);
  return Object.freeze(argv);
}

function rpcRecord(id: string, message: string): string {
  return JSON.stringify({ id, type: "prompt", message }) + "\n";
}

export function encodeChildInput(task: string, correlationId: string, nonce: string, challenge: string): string {
  if (Buffer.byteLength(task, "utf8") > MAX_TASK_BYTES) throw new Error("Pi child task exceeds the stdin limit.");
  if (!/^[0-9a-f]{32}$/u.test(nonce) || !/^[0-9a-f]{32}$/u.test(challenge)) throw new Error("Pi child nonce or challenge is invalid.");
  return rpcRecord(`${correlationId}-handshake`, `/${HANDSHAKE_COMMAND} ${nonce} ${challenge}`)
    + rpcRecord(correlationId, task);
}

function rpcConfirmation(id: string): string {
  return JSON.stringify({ type: "extension_ui_response", id, confirmed: true });
}

type ProtocolRecord = Record<string, unknown> & { type: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[], required: readonly string[] = allowed): boolean {
  return Object.keys(value).every((key) => allowed.includes(key))
    && required.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

function boundedString(value: unknown): value is string {
  return typeof value === "string" && Buffer.byteLength(value, "utf8") <= MAX_JSON_STRING_BYTES;
}

function validOpaqueJson(value: unknown, depth = 0, budget = { nodes: 0 }): boolean {
  budget.nodes += 1;
  if (budget.nodes > MAX_JSON_NODES || depth > MAX_JSON_DEPTH) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "string") return boundedString(value);
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) {
    return value.length <= MAX_JSON_ARRAY && value.every((item) => validOpaqueJson(item, depth + 1, budget));
  }
  if (!isRecord(value) || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) return false;
  const keys = Object.keys(value);
  return keys.length <= MAX_JSON_KEYS
    && keys.every((key) => boundedString(key) && validOpaqueJson(value[key], depth + 1, budget));
}

type ContentKind = "user" | "assistant" | "toolResult";

function validContentBlock(value: unknown, kind: ContentKind): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false;
  switch (value.type) {
    case "text":
      return exactKeys(value, ["type", "text", "textSignature"], ["type", "text"])
        && boundedString(value.text)
        && (value.textSignature === undefined || boundedString(value.textSignature));
    case "image":
      return kind !== "assistant"
        && exactKeys(value, ["type", "data", "mimeType"])
        && boundedString(value.data) && boundedString(value.mimeType);
    case "thinking":
      return kind === "assistant"
        && exactKeys(value, ["type", "thinking", "thinkingSignature", "redacted"], ["type", "thinking"])
        && boundedString(value.thinking)
        && (value.thinkingSignature === undefined || boundedString(value.thinkingSignature))
        && (value.redacted === undefined || typeof value.redacted === "boolean");
    case "toolCall":
      return kind === "assistant"
        && exactKeys(value, ["type", "id", "name", "arguments", "thoughtSignature"], ["type", "id", "name", "arguments"])
        && boundedString(value.id) && boundedString(value.name)
        && validOpaqueJson(value.arguments)
        && (value.thoughtSignature === undefined || boundedString(value.thoughtSignature));
    default:
      return false;
  }
}

function validContent(value: unknown, kind: ContentKind): boolean {
  if (kind === "user" && typeof value === "string") return boundedString(value);
  return Array.isArray(value)
    && value.length <= MAX_JSON_ARRAY
    && value.every((block) => validContentBlock(block, kind));
}

function validUsage(value: unknown): boolean {
  if (!isRecord(value) || !exactKeys(value,
    ["input", "output", "cacheRead", "cacheWrite", "cacheWrite1h", "reasoning", "totalTokens", "cost"],
    ["input", "output", "cacheRead", "cacheWrite", "totalTokens", "cost"])) return false;
  if (!["input", "output", "cacheRead", "cacheWrite", "totalTokens"].every((key) => typeof value[key] === "number" && Number.isFinite(value[key]))) return false;
  if (value.cacheWrite1h !== undefined && (typeof value.cacheWrite1h !== "number" || !Number.isFinite(value.cacheWrite1h))) return false;
  if (value.reasoning !== undefined && (typeof value.reasoning !== "number" || !Number.isFinite(value.reasoning))) return false;
  const cost = value.cost;
  return isRecord(cost)
    && exactKeys(cost, ["input", "output", "cacheRead", "cacheWrite", "total"])
    && ["input", "output", "cacheRead", "cacheWrite", "total"].every((key) => typeof cost[key] === "number" && Number.isFinite(cost[key]));
}

function validDiagnostic(value: unknown): boolean {
  if (!isRecord(value) || !exactKeys(value, ["type", "timestamp", "error", "details"], ["type", "timestamp"])
    || !boundedString(value.type) || typeof value.timestamp !== "number" || !Number.isFinite(value.timestamp)) return false;
  if (value.error !== undefined) {
    if (!isRecord(value.error) || !exactKeys(value.error, ["name", "message", "stack", "code"], ["message"])
      || !boundedString(value.error.message)
      || (value.error.name !== undefined && !boundedString(value.error.name))
      || (value.error.stack !== undefined && !boundedString(value.error.stack))
      || (value.error.code !== undefined && !boundedString(value.error.code) && (typeof value.error.code !== "number" || !Number.isFinite(value.error.code)))) return false;
  }
  return value.details === undefined || validOpaqueJson(value.details);
}

function validMessage(value: unknown): boolean {
  if (!isRecord(value) || typeof value.role !== "string") return false;
  if (value.role === "user") {
    return exactKeys(value, ["role", "content", "timestamp"])
      && validContent(value.content, "user")
      && typeof value.timestamp === "number" && Number.isFinite(value.timestamp);
  }
  if (value.role === "assistant") {
    return exactKeys(value,
      ["role", "content", "api", "provider", "model", "responseModel", "responseId", "diagnostics", "usage", "stopReason", "errorMessage", "timestamp"],
      ["role", "content", "api", "provider", "model", "usage", "stopReason", "timestamp"])
      && validContent(value.content, "assistant")
      && ["api", "provider", "model", "stopReason"].every((key) => typeof value[key] === "string")
      && (value.responseModel === undefined || boundedString(value.responseModel))
      && (value.responseId === undefined || boundedString(value.responseId))
      && (value.errorMessage === undefined || boundedString(value.errorMessage))
      && (value.diagnostics === undefined || (Array.isArray(value.diagnostics) && value.diagnostics.length <= MAX_JSON_ARRAY && value.diagnostics.every(validDiagnostic)))
      && validUsage(value.usage)
      && typeof value.timestamp === "number" && Number.isFinite(value.timestamp);
  }
  if (value.role === "toolResult") {
    return exactKeys(value,
      ["role", "toolCallId", "toolName", "content", "details", "isError", "timestamp"],
      ["role", "toolCallId", "toolName", "content", "isError", "timestamp"])
      && typeof value.toolCallId === "string"
      && typeof value.toolName === "string"
      && validContent(value.content, "toolResult")
      && (value.details === undefined || validOpaqueJson(value.details))
      && typeof value.isError === "boolean"
      && typeof value.timestamp === "number" && Number.isFinite(value.timestamp);
  }
  return false;
}

function invalidProtocol(): never {
  throw new Error("Pi child JSONL schema is invalid.");
}

function validPartialAssistantMessage(value: unknown): boolean {
  if (!isRecord(value) || value.role !== "assistant" || !Array.isArray(value.content)
    || value.content.length > MAX_JSON_ARRAY) return false;
  const normalized: unknown[] = [];
  for (const block of value.content) {
    if (isRecord(block) && (block.type === "text" || block.type === "thinking")
      && Object.prototype.hasOwnProperty.call(block, "index")) {
      const allowed = block.type === "text"
        ? ["type", "text", "textSignature", "index"]
        : ["type", "thinking", "thinkingSignature", "redacted", "index"];
      const required = block.type === "text" ? ["type", "text", "index"] : ["type", "thinking", "index"];
      if (!exactKeys(block, allowed, required)
        || !Number.isSafeInteger(block.index) || (block.index as number) < 0) return false;
      const { index: _index, ...withoutIndex } = block;
      if (!validContentBlock(withoutIndex, "assistant")) return false;
      normalized.push(withoutIndex);
      continue;
    }
    if (!isRecord(block) || block.type !== "toolCall"
      || !["partialArgs", "streamIndex", "partialJson", "index"]
        .some((key) => Object.prototype.hasOwnProperty.call(block, key))) {
      if (!validContentBlock(block, "assistant")) return false;
      normalized.push(block);
      continue;
    }
    if (!exactKeys(block, ["type", "id", "name", "arguments", "thoughtSignature", "partialArgs", "streamIndex", "partialJson", "index"],
      ["type", "id", "name", "arguments"])
      || !["partialArgs", "streamIndex", "partialJson", "index"].some((key) => Object.prototype.hasOwnProperty.call(block, key))
      || !boundedString(block.id) || !boundedString(block.name) || !validOpaqueJson(block.arguments)
      || (block.partialArgs !== undefined && !boundedString(block.partialArgs))
      || (block.partialJson !== undefined && !boundedString(block.partialJson))
      || (block.streamIndex !== undefined && (!Number.isSafeInteger(block.streamIndex) || (block.streamIndex as number) < 0))
      || (block.index !== undefined && (!Number.isSafeInteger(block.index) || (block.index as number) < 0))
      || (block.thoughtSignature !== undefined && !boundedString(block.thoughtSignature))) return false;
    normalized.push({
      type: block.type, id: block.id, name: block.name, arguments: block.arguments,
      ...(block.thoughtSignature === undefined ? {} : { thoughtSignature: block.thoughtSignature }),
    });
  }
  return validMessage({ ...value, content: normalized });
}

function validAssistantEvent(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false;
  const partial = () => validPartialAssistantMessage(value.partial);
  const contentIndex = () => Number.isSafeInteger(value.contentIndex) && (value.contentIndex as number) >= 0;
  switch (value.type) {
    case "start":
      return exactKeys(value, ["type", "partial"]) && partial();
    case "text_start":
    case "thinking_start":
    case "toolcall_start":
      return exactKeys(value, ["type", "contentIndex", "partial"]) && contentIndex() && partial();
    case "text_delta":
    case "thinking_delta":
    case "toolcall_delta":
      return exactKeys(value, ["type", "contentIndex", "delta", "partial"])
        && contentIndex() && boundedString(value.delta) && partial();
    case "text_end":
    case "thinking_end":
      return exactKeys(value, ["type", "contentIndex", "content", "partial"])
        && contentIndex() && boundedString(value.content) && partial();
    case "toolcall_end":
      return exactKeys(value, ["type", "contentIndex", "toolCall", "partial"])
        && contentIndex() && validContentBlock(value.toolCall, "assistant") && partial();
    case "done":
      return exactKeys(value, ["type", "reason", "message"])
        && ["stop", "length", "toolUse"].includes(value.reason as string)
        && validMessage(value.message) && (value.message as Record<string, unknown>).role === "assistant";
    case "error":
      return exactKeys(value, ["type", "reason", "error"])
        && ["aborted", "error"].includes(value.reason as string)
        && validMessage(value.error) && (value.error as Record<string, unknown>).role === "assistant";
    default:
      return false;
  }
}

export function parseChildJsonLine(line: string): ProtocolRecord {
  if (Buffer.byteLength(line, "utf8") > MAX_JSONL_LINE_BYTES) throw new Error("Pi child JSONL line exceeds protocol limit.");
  let parsed: unknown;
  try { parsed = JSON.parse(line); }
  catch { throw new Error("Pi child JSONL is malformed."); }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Pi child JSONL schema is invalid.");
  const record = parsed as ProtocolRecord;
  if (typeof record.type !== "string") throw new Error("Pi child JSONL schema is invalid.");
  switch (record.type) {
    case "response":
      if (typeof record.id !== "string" || record.command !== "prompt" || typeof record.success !== "boolean") invalidProtocol();
      if (record.success === true) {
        if (!exactKeys(record, ["type", "id", "command", "success"])) invalidProtocol();
      } else if (!exactKeys(record, ["type", "id", "command", "success", "error"])
        || typeof record.error !== "string") invalidProtocol();
      break;
    case "agent_start":
    case "agent_settled":
    case "turn_start":
      if (!exactKeys(record, ["type"])) invalidProtocol();
      break;
    case "agent_end":
      if (!exactKeys(record, ["type", "messages", "willRetry"])
        || !Array.isArray(record.messages) || record.messages.length > MAX_JSON_ARRAY || !record.messages.every(validMessage)
        || typeof record.willRetry !== "boolean") invalidProtocol();
      break;
    case "turn_end":
      if (!exactKeys(record, ["type", "message", "toolResults"])
        || !validMessage(record.message)
        || !Array.isArray(record.toolResults) || record.toolResults.length > MAX_JSON_ARRAY || !record.toolResults.every(validMessage)) invalidProtocol();
      break;
    case "message_start":
    case "message_end":
      // Pi 0.80.10 leaves the streaming partialArgs scratch buffer on assistant
      // toolCall blocks here, not only in message_update; the partial validator
      // normalizes those known streaming keys and re-validates strictly (#337).
      if (!exactKeys(record, ["type", "message"])
        || (!validMessage(record.message) && !validPartialAssistantMessage(record.message))) invalidProtocol();
      break;
    case "message_update":
      if (!exactKeys(record, ["type", "message", "assistantMessageEvent"])
        || !validPartialAssistantMessage(record.message) || !validAssistantEvent(record.assistantMessageEvent)) invalidProtocol();
      break;
    case "tool_execution_start":
      if (!exactKeys(record, ["type", "toolCallId", "toolName", "args"])
        || typeof record.toolCallId !== "string" || typeof record.toolName !== "string"
        || !validOpaqueJson(record.args)) invalidProtocol();
      break;
    case "tool_execution_update":
      if (!exactKeys(record, ["type", "toolCallId", "toolName", "args", "partialResult"])
        || typeof record.toolCallId !== "string" || typeof record.toolName !== "string"
        || !validOpaqueJson(record.args) || !validOpaqueJson(record.partialResult)) invalidProtocol();
      break;
    case "tool_execution_end":
      if (!exactKeys(record, ["type", "toolCallId", "toolName", "result", "isError"])
        || typeof record.toolCallId !== "string" || typeof record.toolName !== "string"
        || !validOpaqueJson(record.result) || typeof record.isError !== "boolean") invalidProtocol();
      break;
    case "extension_error":
      if (!exactKeys(record, ["type", "extensionPath", "event", "error"])
        || typeof record.extensionPath !== "string" || typeof record.event !== "string" || typeof record.error !== "string") invalidProtocol();
      break;
    case "extension_ui_request":
      if (!exactKeys(record, ["type", "id", "method", "title", "message", "timeout"])
        || typeof record.id !== "string" || record.id === "" || Buffer.byteLength(record.id, "utf8") > 256
        || record.method !== "confirm" || typeof record.title !== "string" || typeof record.message !== "string"
        || record.timeout !== CHILD_ATTESTATION_TIMEOUT_MS) invalidProtocol();
      break;
    default:
      invalidProtocol();
  }
  return record;
}

/** `detail`, only when it is a recognized WindowsSupervisorRefusalReason, is appended as a
 * stable short identifier to the diagnostic — anything else (arbitrary error text, provider
 * material, etc.) is silently dropped, never interpolated or leaked. This keeps a Windows
 * containment refusal's cause observable without widening this channel unsafely. */
export function childFailure(detail?: unknown): ChildResult {
  const reason = typeof detail === "string" && (WINDOWS_SUPERVISOR_REFUSAL_REASONS as readonly string[]).includes(detail)
    ? detail as WindowsSupervisorRefusalReason
    : undefined;
  return Object.freeze({
    terminal: "degraded",
    diagnostic: reason === undefined
      ? "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor."
      : `Pi child isolation failed safely (${reason}); no inline promotion is available; run /ca-doctor.`,
  });
}

function assistantText(message: unknown): string | undefined {
  if (!validMessage(message)) return undefined;
  const record = message as { role: string; content: unknown[] };
  if (record.role !== "assistant") return undefined;
  const text = record.content.flatMap((item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return [];
    const block = item as Record<string, unknown>;
    return block.type === "text" && typeof block.text === "string" ? [block.text] : [];
  }).join("");
  if (text.trim() === "" || Buffer.byteLength(text, "utf8") > MAX_OUTPUT_BYTES) return undefined;
  const safe = safeDiagnostic(text, MAX_OUTPUT_BYTES);
  return safe === "" || Buffer.byteLength(safe, "utf8") > MAX_OUTPUT_BYTES ? undefined : safe;
}

function successfulFinalAssistant(message: unknown, launch: ChildLaunchInput): string | undefined {
  if (!validMessage(message)) return undefined;
  const assistant = message as Record<string, unknown>;
  if (assistant.role !== "assistant"
    || assistant.provider !== launch.provider
    || assistant.model !== launch.model
    || assistant.stopReason !== "stop"
    || Object.prototype.hasOwnProperty.call(assistant, "errorMessage")) return undefined;
  return assistantText(message);
}

export async function runPiChild(
  request: PiChildRequest,
  signal: AbortSignal,
): Promise<ChildResult> {
  if (signal.aborted) return childFailure();
  let launch: ChildLaunchInput;
  try {
    launch = await validateChildLaunch(request);
    if (Buffer.byteLength(request.task, "utf8") > MAX_TASK_BYTES) return childFailure();
  } catch {
    return childFailure();
  }
  if (signal.aborted) return childFailure();
  const correlationId = randomUUID();
  const nonce = randomBytes(16).toString("hex");
  const challenge = randomBytes(16).toString("hex");
  let records: string;
  try { records = encodeChildInput(request.task, correlationId, nonce, challenge); }
  catch { return childFailure(); }
  const [handshakeRecord, taskRecord] = records.trimEnd().split("\n");
  if (handshakeRecord === undefined || taskRecord === undefined) return childFailure();
  if (signal.aborted) return childFailure();

  const startedAt = Date.now();
  let child;
  try {
    child = await spawnProcessTree(launch.nodePath, buildChildArgv(launch), {
      cwd: launch.cwd,
      env: buildChildEnv({
        platform: request.platform ?? process.platform,
        parent: request.parentEnv ?? process.env,
        provider: launch.provider,
      }),
      stdio: ["pipe", "pipe", "pipe", "pipe"],
    });
  } catch (error) {
    return childFailure(error instanceof Error ? windowsRefusalReasonFromMessage(error.message) : undefined);
  }
  const cleanup = createProcessTreeCleanup(child);
  let abortedDuringReadiness: boolean = signal.aborted;
  let cancellationCleanup: Promise<unknown> | undefined;
  const readinessAbort = () => {
    abortedDuringReadiness = true;
    cancellationCleanup ??= cleanup.terminate("cancelled");
  };
  if (!abortedDuringReadiness) signal.addEventListener("abort", readinessAbort, { once: true });
  const containmentReady = await cleanup.ready();
  signal.removeEventListener("abort", readinessAbort);
  if (abortedDuringReadiness || signal.aborted) {
    cancellationCleanup ??= cleanup.terminate("cancelled");
    await cancellationCleanup;
    return childFailure();
  }
  if (!containmentReady) {
    await cleanup.terminate("startup_failure");
    return childFailure();
  }

  return await new Promise<ChildResult>((resolveResult) => {
    let phase: "await-attestation" | "await-handshake" | "await-task-ack" | "await-agent-start" | "in-task" | "await-settled" | "complete" = "await-attestation";
    let failed = false;
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let stderrHead = "";
    let lastExitCode: number | undefined;
    let pending = "";
    let output: string | undefined;
    // Best-effort observability metrics attached only to a successful completion. A degraded
    // result carries no metrics or stderr head at all — it stays a fixed diagnostic-only shape
    // (see "returns the same fixed degraded result for every isolated-runner failure branch"),
    // varying only in its diagnostic string, and only by an allowlisted refusal reason code
    // (childFailure's WINDOWS_SUPERVISOR_REFUSAL_REASONS check), never by raw error content or
    // byte counts. The dispatch-layer audit measures its own duration around the runChild call
    // for degraded outcomes instead.
    const metrics = () => ({
      durationMs: Date.now() - startedAt,
      stdoutBytes,
      stderrBytes,
      stderrHead,
      ...(lastExitCode === undefined ? {} : { exitCode: lastExitCode }),
    });
    const stdoutDecoder = new StringDecoder("utf8");
    let stdoutDecoderEnded = false;
    const expectedAttestation = childAttestationDigest({
      nonce,
      challenge,
      cwd: launch.cwd,
      provider: launch.provider,
      model: launch.model,
      tools: launch.tools,
      projectTrusted: false,
      mode: "rpc",
    });
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const settle = (value: ChildResult) => {
      if (settled) return;
      settled = true;
      if (timer !== undefined) clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      resolveResult(value);
    };
    const finishFailure = (reason: ProcessTreeCleanupReason = "protocol_error") => {
      if (failed || settled) return;
      failed = true;
      try { child.stdin.end(); } catch { /* process already closed */ }
      void cleanup.terminate(reason).then(
        () => settle(childFailure()),
        () => settle(childFailure()),
      );
    };
    const abort = () => finishFailure("cancelled");
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      finishFailure("cancelled");
      return;
    }
    child.stdin.on("error", () => finishFailure("protocol_error"));
    const capability = child.stdio[3];
    if (!isCapabilityPipe(capability)) {
      finishFailure("startup_failure");
    } else {
      capability.on("error", () => finishFailure("startup_failure"));
      if (capability.destroyed === true || capability.writable === false) finishFailure("startup_failure");
      else {
        try { capability.end(nonce, "utf8"); }
        catch { finishFailure("startup_failure"); }
      }
    }
    const writeInput = (record: string) => {
      if (failed || child.stdin.destroyed || !child.stdin.writable) { finishFailure("protocol_error"); return; }
      try { child.stdin.write(record + "\n", "utf8", (error) => { if (error !== null && error !== undefined) finishFailure("protocol_error"); }); }
      catch { finishFailure("protocol_error"); }
    };
    const endInput = () => {
      if (child.stdin.destroyed) return;
      try { child.stdin.end(); }
      catch { finishFailure("protocol_error"); }
    };
    const processLine = (line: string) => {
      if (line === "" || failed) return;
      let record: ProtocolRecord;
      try { record = parseChildJsonLine(line); }
      catch { finishFailure("protocol_error"); return; }
      if (record.type === "extension_ui_request") {
        if (phase !== "await-attestation"
          || record.title !== CHILD_ATTESTATION_TITLE
          || record.message !== expectedAttestation
          || record.timeout !== CHILD_ATTESTATION_TIMEOUT_MS) { finishFailure("protocol_error"); return; }
        phase = "await-handshake";
        writeInput(rpcConfirmation(record.id as string));
      } else if (record.type === "response" && record.command === "prompt") {
        if (phase === "await-handshake") {
          if (record.id !== `${correlationId}-handshake` || record.success !== true) { finishFailure("protocol_error"); return; }
          phase = "await-task-ack";
          writeInput(taskRecord);
        } else if (phase === "await-task-ack") {
          if (record.id !== correlationId || record.success !== true) { finishFailure("protocol_error"); return; }
          phase = "await-agent-start";
        } else {
          finishFailure("protocol_error");
        }
      } else if (record.type === "extension_error") {
        finishFailure("protocol_error");
      } else if (phase === "await-agent-start") {
        if (record.type !== "agent_start") { finishFailure("protocol_error"); return; }
        phase = "in-task";
      } else if (phase === "in-task") {
        if (record.type === "agent_end") {
          const messages = record.messages as unknown[];
          const finalAssistant = [...messages].reverse().find((message) => isRecord(message) && message.role === "assistant");
          const finalOutput = successfulFinalAssistant(finalAssistant, launch);
          if (record.willRetry !== false || finalOutput === undefined) { finishFailure("protocol_error"); return; }
          output = finalOutput;
          phase = "await-settled";
        } else if (["agent_start", "agent_settled", "response"].includes(record.type)) {
          finishFailure("protocol_error");
        }
      } else if (record.type === "agent_settled") {
        if (phase !== "await-settled") { finishFailure("protocol_error"); return; }
        phase = "complete";
        endInput();
      } else {
        finishFailure("protocol_error");
      }
    };
    child.stdout.on("data", (chunk: Buffer | string) => {
      const raw = typeof chunk === "string" ? Buffer.from(chunk, "utf8") : chunk;
      stdoutBytes += raw.byteLength;
      if (stdoutBytes > MAX_STDOUT_BYTES) { finishFailure("protocol_overflow"); return; }
      const value = stdoutDecoder.write(raw);
      pending += value;
      let newline = pending.indexOf("\n");
      while (newline >= 0) {
        processLine(pending.slice(0, newline));
        pending = pending.slice(newline + 1);
        newline = pending.indexOf("\n");
      }
      if (Buffer.byteLength(pending, "utf8") > MAX_JSONL_LINE_BYTES) finishFailure("protocol_overflow");
    });
    child.stderr.on("data", (chunk: Buffer | string) => {
      const raw = typeof chunk === "string" ? Buffer.from(chunk, "utf8") : chunk;
      stderrBytes += raw.byteLength;
      const remaining = Math.max(0, MAX_STDERR_BYTES - Buffer.byteLength(stderrHead, "utf8"));
      if (remaining > 0) stderrHead += raw.subarray(0, remaining).toString("utf8");
      if (stderrBytes > MAX_STDERR_BYTES) finishFailure("protocol_overflow");
    });
    child.on("error", () => finishFailure("startup_failure"));
    timer = setTimeout(() => finishFailure("timeout"), Math.max(1, request.timeoutMs ?? 120_000));
    const handleClose = (code: number | null) => {
      if (code !== null) lastExitCode = code;
      if (!stdoutDecoderEnded) {
        stdoutDecoderEnded = true;
        pending += stdoutDecoder.end();
      }
      if (pending !== "") processLine(pending);
      if (settled) return;
      if (failed || phase !== "complete" || code !== 0) {
        finishFailure("protocol_error");
        return;
      }
      void cleanup.terminate("parent_shutdown").then((cleanupResult) => {
        if (!cleanupResult.verified) settle(childFailure());
        else settle(Object.freeze({ terminal: "completed", pid: child.pid, correlationId, ...metrics(), ...(output === undefined ? {} : { output }) }));
      }, () => settle(childFailure()));
    };
    child.on("close", handleClose);
    if ((child.exitCode !== undefined && child.exitCode !== null)
      || (child.signalCode !== undefined && child.signalCode !== null)) {
      queueMicrotask(() => handleClose(child.exitCode));
    }
    if (!failed) writeInput(handshakeRecord);
  });
}
