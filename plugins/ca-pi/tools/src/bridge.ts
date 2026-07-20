import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { accessSync, constants, realpathSync, statSync } from "node:fs";
import { appendFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, posix, relative, resolve, win32 } from "node:path";

import type {
  BridgePort,
  BridgeRequest,
  BridgeResponse,
  ExtensionContextPort,
  PiFooterActivationState,
  PiFooterStatusSnapshotPortResult,
  PiFooterUsageUpdateResult,
  PiUsageSnapshotPortResult,
  ToolCategory,
} from "./contracts.ts";
import { redactJson, safeDiagnostic } from "./redaction.ts";

const RESPONSE_KEYS = new Set(["version", "outcome", "ruleId", "message", "context", "resultPatch", "auditCode"]);
const OUTCOMES = new Set(["allow", "block", "warn", "notice"]);
const PI_USAGE_RANGE_SIZE = 256;
const PI_MAX_POSITION = 2_147_483_647;
const PI_MAX_TOKENS = 1_000_000_000_000_000;
const PI_MAX_COST_USD = 1_000_000_000;
const PI_MAX_SESSION_ID_CHARS = 1_024;
const PI_MAX_SESSION_FILE_CHARS = 32_768;
const PI_MAX_HOME_CHARS = 32_768;
const PI_PLAN_FILE_MAX_BYTES = 92_160;
const PI_BRIDGE_MAX_REQUEST_BYTES = 262_144;
const CONTROL_RE = /[\u0000-\u001f\u007f-\u009f]/u;
const PI_USAGE_TOTAL_KEYS = new Set([
  "inputTokens",
  "outputTokens",
  "cacheReadTokens",
  "cacheWriteTokens",
  "costUsd",
]);
const PI_USAGE_RESULT_KEYS = new Set(["status", "session", "today", "acceptedThrough", "highWater"]);
const PI_STATUS_RESULT_KEYS = new Set([
  "status",
  "stage",
  "tasks",
  "questions",
  "overrides",
  "sprint",
  "dev",
  "prune",
]);
type BridgeFailureDetail =
  | "path validation failed"
  | "request serialization failed"
  | "request overflow"
  | "cancelled"
  | "bridge launch failed"
  | "protocol overflow"
  | "timed out"
  | "bridge process failed"
  | "returned malformed protocol";

export interface BridgeClientOptions {
  bridgeScript: string;
  packageRoot: string;
  pythonExecutable?: string;
  pythonPrefixArgs?: readonly string[];
  gitExecutable?: string;
  toolClasses: Readonly<Record<string, ToolCategory>>;
  timeoutMs?: number;
  maxRequestBytes?: number;
  maxStreamBytes?: number;
  shouldAuditFailure?: (request: BridgeRequest) => boolean;
}

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function minimalEnvironment(
  identities?: { git: string; python: string },
  userHome?: string,
): NodeJS.ProcessEnv {
  const allowed = ["SystemRoot", "WINDIR", "TEMP", "TMP"] as const;
  const env: NodeJS.ProcessEnv = { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" };
  for (const key of allowed) if (process.env[key] !== undefined) env[key] = process.env[key];
  if (identities !== undefined) {
    const pathApi = process.platform === "win32" ? win32 : posix;
    const searchDirectories = new Set([
      pathApi.dirname(identities.git),
      pathApi.dirname(identities.python),
    ]);
    const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
    if (process.platform === "win32" && systemRoot !== undefined && win32.isAbsolute(systemRoot)) {
      searchDirectories.add(win32.join(systemRoot, "System32"));
    }
    env.PATH = [...searchDirectories].join(process.platform === "win32" ? ";" : ":");
    env.CODEARBITER_GIT_EXECUTABLE = identities.git;
    env.CODEARBITER_PYTHON_EXECUTABLE = identities.python;
  }
  if (userHome !== undefined) {
    if (process.platform === "win32") env.USERPROFILE = userHome;
    else env.HOME = userHome;
  }
  return env;
}

function canonicalExecutable(candidate: string, platform: NodeJS.Platform): string | undefined {
  const pathApi = platform === "win32" ? win32 : posix;
  if (!pathApi.isAbsolute(candidate)) return undefined;
  try {
    const canonical = realpathSync(candidate);
    if (!statSync(canonical).isFile()) return undefined;
    if (platform !== "win32") accessSync(canonical, constants.X_OK);
    return canonical;
  } catch {
    return undefined;
  }
}

function sameOrInside(path: string, root: string, platform: NodeJS.Platform): boolean {
  const pathApi = platform === "win32" ? win32 : posix;
  const suffix = pathApi.relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !pathApi.isAbsolute(suffix));
}

function canonicalUserHome(
  projectRoot: string,
  packageRoot: string,
  platform: NodeJS.Platform = process.platform,
): string | undefined {
  const pathApi = platform === "win32" ? win32 : posix;
  const candidate = platform === "win32" ? process.env.USERPROFILE : process.env.HOME;
  if (typeof candidate !== "string" || candidate.length < 1 || candidate.length > PI_MAX_HOME_CHARS
    || candidate !== candidate.trim() || CONTROL_RE.test(candidate) || !pathApi.isAbsolute(candidate)) return undefined;
  try {
    const canonical = realpathSync(candidate);
    if (!statSync(canonical).isDirectory()
      || sameOrInside(canonical, projectRoot, platform)
      || sameOrInside(canonical, packageRoot, platform)) return undefined;
    return canonical;
  } catch {
    return undefined;
  }
}

function trustedPathCandidate(
  basename: string,
  projectCwd: string,
  platform: NodeJS.Platform,
  pathValue: string,
): string | undefined {
  const pathApi = platform === "win32" ? win32 : posix;
  const separator = platform === "win32" ? ";" : ":";
  const canonicalProject = canonicalExecutable(projectCwd, platform) ?? (() => {
    try { return realpathSync(projectCwd); } catch { return pathApi.resolve(projectCwd); }
  })();
  for (const rawEntry of pathValue.split(separator)) {
    const entry = rawEntry.trim();
    if (entry === "" || !pathApi.isAbsolute(entry)) continue;
    let directory: string;
    try { directory = realpathSync(entry); } catch { continue; }
    const candidate = canonicalExecutable(pathApi.join(directory, basename), platform);
    if (candidate !== undefined && !sameOrInside(candidate, canonicalProject, platform)) return candidate;
  }
  return undefined;
}

export function resolveGitExecutable(
  projectCwd: string,
  platform: NodeJS.Platform = process.platform,
  pathValue: string = process.env.PATH ?? "",
): string {
  const name = platform === "win32" ? "git.exe" : "git";
  const executable = trustedPathCandidate(name, projectCwd, platform, pathValue);
  if (executable === undefined) {
    throw new Error("codeArbiter could not resolve an absolute trusted Git executable; run /ca-doctor.");
  }
  return executable;
}

function windowsTaskkillExecutable(): string | undefined {
  if (process.platform !== "win32") return undefined;
  const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
  if (systemRoot === undefined || !win32.isAbsolute(systemRoot)) return undefined;
  const candidate = canonicalExecutable(win32.join(systemRoot, "System32", "taskkill.exe"), "win32");
  if (candidate === undefined) return undefined;
  let canonicalRoot: string;
  try { canonicalRoot = realpathSync(systemRoot); } catch { return undefined; }
  return sameOrInside(candidate, canonicalRoot, "win32") ? candidate : undefined;
}

function validResponse(value: unknown): value is BridgeResponse {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !RESPONSE_KEYS.has(key))) return false;
  if (record.version !== 1 || typeof record.outcome !== "string" || !OUTCOMES.has(record.outcome)) return false;
  for (const key of ["ruleId", "message", "context", "auditCode"] as const) {
    if (record[key] !== undefined && typeof record[key] !== "string") return false;
  }
  return true;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function exactKeys(value: Record<string, unknown>, keys: ReadonlySet<string>): boolean {
  return Object.keys(value).length === keys.size && Object.keys(value).every((key) => keys.has(key));
}

function usageTotals(value: unknown): {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  costUsd: number;
} | undefined {
  const totals = record(value);
  if (totals === undefined || !exactKeys(totals, PI_USAGE_TOTAL_KEYS)) return undefined;
  for (const key of ["inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"] as const) {
    const amount = totals[key];
    if (typeof amount !== "number" || !Number.isInteger(amount) || amount < 0 || amount > PI_MAX_TOKENS) {
      return undefined;
    }
  }
  const costUsd = totals.costUsd;
  if (typeof costUsd !== "number" || !Number.isFinite(costUsd) || costUsd < 0 || costUsd > PI_MAX_COST_USD) {
    return undefined;
  }
  return {
    inputTokens: totals.inputTokens as number,
    outputTokens: totals.outputTokens as number,
    cacheReadTokens: totals.cacheReadTokens as number,
    cacheWriteTokens: totals.cacheWriteTokens as number,
    costUsd,
  };
}

function usageResult(response: BridgeResponse): {
  status: string;
  session: ReturnType<typeof usageTotals>;
  today: ReturnType<typeof usageTotals>;
  acceptedThrough: number;
  highWater: number;
} | undefined {
  if (response.outcome !== "allow" && response.outcome !== "notice") return undefined;
  const patch = record(response.resultPatch);
  if (patch === undefined || !exactKeys(patch, new Set(["footerUsage"]))) return undefined;
  const value = record(patch.footerUsage);
  if (value === undefined || !exactKeys(value, PI_USAGE_RESULT_KEYS) || typeof value.status !== "string") return undefined;
  const session = usageTotals(value.session);
  const today = usageTotals(value.today);
  const acceptedThrough = value.acceptedThrough;
  const highWater = value.highWater;
  if (session === undefined || today === undefined
    || typeof acceptedThrough !== "number" || !Number.isInteger(acceptedThrough)
    || acceptedThrough < -1 || acceptedThrough > PI_MAX_POSITION
    || typeof highWater !== "number" || !Number.isInteger(highWater)
    || highWater < -1 || highWater > PI_MAX_POSITION) return undefined;
  return { status: value.status, session, today, acceptedThrough, highWater };
}

function callMember(receiver: unknown, name: string): unknown {
  const member = record(receiver)?.[name];
  if (typeof member !== "function") return undefined;
  try {
    return member.call(receiver);
  } catch {
    return undefined;
  }
}

function usageFact(entryValue: unknown, position: number): Record<string, unknown> | undefined {
  const entry = record(entryValue);
  const message = record(entry?.message);
  const usage = record(message?.usage);
  if (entry?.type !== "message" || message?.role !== "assistant" || usage === undefined) return undefined;
  const timestamp = entry.timestamp;
  if (typeof timestamp !== "string" || timestamp.length < 1 || timestamp.length > 64
    || timestamp !== timestamp.trim() || CONTROL_RE.test(timestamp)) return undefined;
  const raw = {
    inputTokens: usage.input,
    outputTokens: usage.output,
    cacheReadTokens: usage.cacheRead,
    cacheWriteTokens: usage.cacheWrite,
    costUsd: record(usage.cost)?.total ?? usage.cost,
  };
  const totals = usageTotals(raw);
  return totals === undefined ? undefined : { position, timestamp, ...totals };
}

interface UsageIdentityParts {
  readonly sessionId: string;
  readonly sessionFile: string | null;
}

function usageIdentityParts(manager: unknown): UsageIdentityParts | undefined {
  const sessionId = callMember(manager, "getSessionId");
  if (typeof sessionId !== "string" || sessionId.length === 0
    || sessionId.length > PI_MAX_SESSION_ID_CHARS || CONTROL_RE.test(sessionId)) return undefined;
  const receiver = record(manager);
  if (receiver === undefined) return undefined;
  let sessionFile: string | null;
  try {
    if (!("getSessionFile" in receiver)) {
      sessionFile = null;
    } else {
      const member = receiver.getSessionFile;
      if (typeof member !== "function") return undefined;
      const fileValue = member.call(manager);
      if (fileValue === undefined) {
        sessionFile = null;
      } else {
        if (typeof fileValue !== "string" || fileValue.length === 0
          || fileValue.length > PI_MAX_SESSION_FILE_CHARS || CONTROL_RE.test(fileValue)) return undefined;
        sessionFile = fileValue;
      }
    }
  } catch {
    return undefined;
  }
  return { sessionId, sessionFile };
}

function usageIdentity(parts: UsageIdentityParts): string {
  return createHash("sha256")
    .update(JSON.stringify([parts.sessionId, parts.sessionFile]), "utf8")
    .digest("hex");
}

function snapshotFromUsage(value: NonNullable<ReturnType<typeof usageResult>>): PiUsageSnapshotPortResult {
  return {
    session: { ...value.session! },
    today: {
      inputTokens: value.today!.inputTokens,
      outputTokens: value.today!.outputTokens,
      costUsd: value.today!.costUsd,
    },
  };
}

/**
 * Advance the user-global Pi usage ledger over canonical raw session-entry indexes.
 * The caller retains `acknowledgedCursor`; a retry passes it back so the first
 * unacknowledged range is replayed byte-for-byte from the still-canonical entries.
 */
export async function updateFooterUsageSnapshot(
  bridge: BridgePort,
  context: Pick<ExtensionContextPort, "cwd" | "signal" | "sessionManager">,
  acknowledgedCursor: number,
  options?: { readonly maxRanges: number },
): Promise<PiFooterUsageUpdateResult> {
  const manager = context.sessionManager;
  const identityBefore = usageIdentityParts(manager);
  if (identityBefore === undefined) return { acknowledgedCursor, retryRequired: true };
  const entriesValue = callMember(manager, "getEntries");
  const identityAfter = usageIdentityParts(manager);
  const stableIdentity = identityAfter !== undefined && identityBefore.sessionId === identityAfter.sessionId
    && identityBefore.sessionFile === identityAfter.sessionFile;
  if (!Array.isArray(entriesValue) || !stableIdentity
    || !Number.isInteger(acknowledgedCursor) || acknowledgedCursor < -1
    || acknowledgedCursor > PI_MAX_POSITION
    || entriesValue.length > PI_MAX_POSITION + 1
    || acknowledgedCursor >= entriesValue.length) {
    return { acknowledgedCursor, retryRequired: true };
  }
  const sessionKey = usageIdentity(identityBefore);
  const signal = context.signal ?? new AbortController().signal;
  const bounded = options !== undefined;
  const maxRanges = options?.maxRanges ?? Number.POSITIVE_INFINITY;
  if (bounded && (!Number.isInteger(maxRanges) || maxRanges < 1 || maxRanges > 1_024)) {
    return {
      acknowledgedCursor,
      retryRequired: true,
      ...(bounded ? { morePending: acknowledgedCursor < entriesValue.length - 1 } : {}),
    };
  }
  let cursor = acknowledgedCursor;
  let ranges = 0;
  let final: NonNullable<ReturnType<typeof usageResult>> | undefined;
  while (cursor < entriesValue.length - 1 && ranges < maxRanges) {
    const scanStart = cursor + 1;
    const scanEnd = Math.min(entriesValue.length - 1, scanStart + PI_USAGE_RANGE_SIZE - 1);
    const facts: Record<string, unknown>[] = [];
    for (let position = scanStart; position <= scanEnd; position += 1) {
      const fact = usageFact(entriesValue[position], position);
      if (fact !== undefined) facts.push(fact);
    }
    let response: BridgeResponse;
    try {
      response = await bridge.call({
        version: 1,
        event: "footer_usage_update",
        cwd: context.cwd,
        input: { sessionKey, scanStart, scanEnd, facts },
      }, signal);
    } catch {
      return {
        acknowledgedCursor: cursor,
        retryRequired: true,
        ...(bounded ? { morePending: cursor < entriesValue.length - 1 } : {}),
      };
    }
    const parsed = usageResult(response);
    if (parsed === undefined || parsed.status !== "ok"
      || parsed.acceptedThrough !== scanEnd
      || parsed.highWater < scanEnd || parsed.highWater >= entriesValue.length) {
      return {
        acknowledgedCursor: cursor,
        retryRequired: true,
        ...(bounded ? { morePending: cursor < entriesValue.length - 1 } : {}),
      };
    }
    cursor = parsed.highWater;
    ranges += 1;
    final = parsed;
  }
  const morePending = cursor < entriesValue.length - 1;
  return final === undefined
    ? { acknowledgedCursor: cursor, retryRequired: false, ...(bounded ? { morePending } : {}) }
    : {
      acknowledgedCursor: cursor,
      retryRequired: false,
      ...(bounded ? { morePending } : {}),
      snapshot: snapshotFromUsage(final),
    };
}

function boundedStatusCount(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 1_000_000
    ? value
    : undefined;
}

function statusResult(response: BridgeResponse): PiFooterStatusSnapshotPortResult | undefined {
  if (response.outcome !== "allow" && response.outcome !== "notice") return undefined;
  const patch = record(response.resultPatch);
  if (patch === undefined || !exactKeys(patch, new Set(["footerStatus"]))) return undefined;
  const value = record(patch.footerStatus);
  if (value === undefined || !exactKeys(value, PI_STATUS_RESULT_KEYS) || value.status !== "ok"
    || typeof value.stage !== "string" || value.stage.length < 1 || value.stage.length > 128
    || CONTROL_RE.test(value.stage)
    || boundedStatusCount(value.tasks) === undefined
    || boundedStatusCount(value.questions) === undefined
    || boundedStatusCount(value.overrides) === undefined
    || typeof value.sprint !== "boolean" || typeof value.dev !== "boolean"
    || (value.prune !== null && (typeof value.prune !== "string" || value.prune.length > 256
      || CONTROL_RE.test(value.prune)))) return undefined;
  return {
    stage: value.stage,
    tasks: value.tasks as number,
    questions: value.questions as number,
    overrides: value.overrides as number,
    sprint: value.sprint,
    dev: value.dev,
    prune: value.prune === null ? undefined : value.prune as string,
  };
}

export type PlanFileBridgeInput =
  | Readonly<{ slug: string; kind: "spec" | "plan"; action: "read" }>
  | Readonly<{ slug: string; kind: "spec" | "plan"; action: "replace"; expectedHash: string | null; content: string }>;

export type PlanFileBridgeResult =
  | Readonly<{ status: "unchanged"; exists: boolean; hash: string | null; content: string }>
  | Readonly<{ status: "committed"; observed: true; exists: boolean; hash: string | null; content: string;
      directoryDurable: boolean;
      postCommitDiagnostic?: "directory_durability_unavailable" | "directory_sync_failed"
        | "postcommit_changed" | "postcommit_cleanup_failed" }>
  | Readonly<{ status: "committed"; observed: false; exists: null; hash: null; content: null;
      directoryDurable: false; postCommitDiagnostic: "postcommit_unobserved" }>
  | Readonly<{ status: "conflict" | "error" }>;

function planFileContent(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length > Math.ceil(PI_PLAN_FILE_MAX_BYTES / 3) * 4) return undefined;
  const bytes = Buffer.from(value, "base64");
  if (bytes.toString("base64") !== value || bytes.length > PI_PLAN_FILE_MAX_BYTES) return undefined;
  const content = bytes.toString("utf8");
  return Buffer.from(content, "utf8").equals(bytes) ? content : undefined;
}

function planFileResult(response: BridgeResponse): PlanFileBridgeResult | undefined {
  if (response.outcome !== "allow" && response.outcome !== "notice") return undefined;
  const patch = record(response.resultPatch);
  if (patch === undefined || !exactKeys(patch, new Set(["planFile"]))) return undefined;
  const value = record(patch.planFile);
  if (value === undefined || typeof value.status !== "string") return undefined;
  if (value.status === "conflict" && exactKeys(value, new Set(["status"]))) return { status: "conflict" };
  if (value.status === "error" && exactKeys(value, new Set(["status", "code"]))
    && typeof value.code === "string" && /^[a-z_]{1,64}$/u.test(value.code)) return { status: "error" };
  const hash = value.hash;
  const content = planFileContent(value.contentBase64);
  if (hash !== null && (typeof hash !== "string" || !/^[a-f0-9]{64}$/u.test(hash))) return undefined;
  if (value.status === "unchanged" && exactKeys(value, new Set(["status", "exists", "hash", "contentBase64"]))
    && content !== undefined
    && typeof value.exists === "boolean" && (value.exists ? typeof hash === "string" : hash === null && content === "")) {
    return { status: "unchanged", exists: value.exists, hash: hash as string | null, content };
  }
  const diagnostic = value.postCommitDiagnostic;
  const diagnostics = new Set(["directory_durability_unavailable", "directory_sync_failed",
    "postcommit_changed", "postcommit_cleanup_failed"]);
  if (value.status === "committed" && exactKeys(value, new Set([
    "status", "observed", "exists", "hash", "contentBase64", "directoryDurable", "postCommitDiagnostic",
  ])) && value.observed === false && value.exists === null && hash === null && value.contentBase64 === null
    && value.directoryDurable === false && diagnostic === "postcommit_unobserved") {
    return { status: "committed", observed: false, exists: null, hash: null, content: null,
      directoryDurable: false, postCommitDiagnostic: "postcommit_unobserved" };
  }
  if (value.status === "committed" && (exactKeys(value, new Set([
    "status", "observed", "exists", "hash", "contentBase64", "directoryDurable",
  ])) || exactKeys(value, new Set([
    "status", "observed", "exists", "hash", "contentBase64", "directoryDurable", "postCommitDiagnostic",
  ]))) && value.observed === true && content !== undefined && typeof value.exists === "boolean"
    && (value.exists ? typeof hash === "string" : hash === null && content === "")
    && typeof value.directoryDurable === "boolean"
    && (diagnostic === undefined || typeof diagnostic === "string" && diagnostics.has(diagnostic))) {
    return { status: "committed", observed: true, exists: value.exists, hash: hash as string | null,
      content, directoryDurable: value.directoryDurable,
      ...(diagnostic === undefined ? {} : { postCommitDiagnostic: diagnostic as
        "directory_durability_unavailable" | "directory_sync_failed" | "postcommit_changed"
          | "postcommit_cleanup_failed" }) };
  }
  return undefined;
}

/** One fixed, path-free bridge action for the shared canonical plan-file helper. */
export async function callPlanFileBridge(
  bridge: BridgePort,
  cwd: string,
  input: PlanFileBridgeInput,
  signal: AbortSignal = new AbortController().signal,
): Promise<PlanFileBridgeResult | undefined> {
  try {
    if (!/^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/u.test(input.slug)
      || input.kind !== "spec" && input.kind !== "plan"
      || input.action !== "read" && input.action !== "replace"
      || input.action === "replace" && Buffer.byteLength(input.content, "utf8") > PI_PLAN_FILE_MAX_BYTES) {
      return undefined;
    }
    const wireInput = input.action === "read" ? input : {
      slug: input.slug, kind: input.kind, action: input.action, expectedHash: input.expectedHash,
      contentBase64: Buffer.from(input.content, "utf8").toString("base64"),
    };
    const request = { version: 1 as const, event: "plan_file", cwd, input: wireInput };
    if (Buffer.byteLength(JSON.stringify(request), "utf8") > PI_BRIDGE_MAX_REQUEST_BYTES) return undefined;
    return planFileResult(await bridge.call(request, signal));
  } catch {
    return undefined;
  }
}

/** Read trusted enabled governance facts; every false/missing/error gate is zero-call. */
export async function readFooterStatusSnapshot(
  bridge: BridgePort,
  context: Pick<ExtensionContextPort, "cwd" | "signal" | "isProjectTrusted" | "sessionManager">,
  activation: PiFooterActivationState,
): Promise<PiFooterStatusSnapshotPortResult | undefined> {
  if (activation.enabled !== true) return undefined;
  try {
    if (typeof context.isProjectTrusted !== "function" || context.isProjectTrusted() !== true) return undefined;
  } catch {
    return undefined;
  }
  const rawSessionId = callMember(context.sessionManager, "getSessionId");
  const sessionId = typeof rawSessionId === "string" && rawSessionId.length <= 1_024
    ? rawSessionId
    : undefined;
  try {
    const response = await bridge.call({
      version: 1,
      event: "footer_status_snapshot",
      cwd: context.cwd,
      ...(sessionId === undefined ? {} : { sessionId }),
    }, context.signal ?? new AbortController().signal);
    return statusResult(response);
  } catch {
    return undefined;
  }
}

// Mirrors process-tree.ts's WINDOWS_HELPER_CLEANUP_MS: taskkill must never block the event loop.
const WINDOWS_TASKKILL_TIMEOUT_MS = 1_000;
// Bounded backstop: if 'close' never arrives after a kill attempt, force-settle the pending call.
const KILL_SETTLE_DEADLINE_MS = 2_000;

function killTree(child: ReturnType<typeof spawn>, taskkillExecutable: string | undefined): void {
  if (child.pid === undefined) return;
  if (process.platform === "win32") {
    if (taskkillExecutable === undefined) {
      child.kill("SIGKILL");
      return;
    }
    const result = spawnSync(taskkillExecutable, ["/pid", String(child.pid), "/t", "/f"], {
      env: minimalEnvironment(),
      shell: false,
      stdio: "ignore",
      timeout: WINDOWS_TASKKILL_TIMEOUT_MS,
      windowsHide: true,
    });
    if (result.error !== undefined || result.status !== 0) child.kill("SIGKILL");
    return;
  }
  try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); }
}

function sanitizedResponse(response: BridgeResponse, request: BridgeRequest): BridgeResponse {
  return {
    ...response,
    ...(response.ruleId === undefined ? {} : { ruleId: safeDiagnostic(response.ruleId, 100) }),
    ...(response.message === undefined ? {} : { message: safeDiagnostic(response.message) }),
    ...(response.context === undefined ? {} : { context: safeDiagnostic(response.context, 16_000) }),
    ...(response.auditCode === undefined ? {} : { auditCode: safeDiagnostic(response.auditCode, 100) }),
    ...(response.resultPatch === undefined ? {} : {
      resultPatch: request.event === "plan_file" ? response.resultPatch : redactJson(response.resultPatch),
    }),
  };
}

export type BridgeSpawnImpl = typeof spawn;
let spawnImpl: BridgeSpawnImpl = spawn;
/** Test-only seam: overrides the spawn implementation used by BridgeClient#call. Pass undefined to restore the default. */
export function __setBridgeSpawnForTests(impl: BridgeSpawnImpl | undefined): void {
  spawnImpl = impl ?? spawn;
}

export class BridgeClient implements BridgePort {
  private readonly ready: Promise<{ git: string; python: string; root: string; script: string; taskkill?: string }>;
  private readonly timeoutMs: number;
  private readonly maxRequestBytes: number;
  private readonly maxStreamBytes: number;

  constructor(private readonly options: BridgeClientOptions) {
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.maxRequestBytes = options.maxRequestBytes ?? 262_144;
    this.maxStreamBytes = options.maxStreamBytes ?? 1_048_576;
    this.ready = this.validatePaths();
    // call() attaches its own handler only when the first request awaits `ready`, which can be
    // much later than construction; without this, an interim rejection is unhandled and crashes
    // the process on modern Node. The chained catch does not alter what call() observes.
    this.ready.catch(() => undefined);
  }

  private async validatePaths(): Promise<{ git: string; python: string; root: string; script: string; taskkill?: string }> {
    if (this.options.pythonExecutable === undefined || this.options.gitExecutable === undefined) {
      throw new Error("Python 3 or Git is unavailable");
    }
    if (!isAbsolute(this.options.pythonExecutable) || !isAbsolute(this.options.gitExecutable) || !isAbsolute(this.options.bridgeScript) || !isAbsolute(this.options.packageRoot)) {
      throw new Error("bridge paths must be absolute");
    }
    const [git, python, script, root] = await Promise.all([
      realpath(this.options.gitExecutable),
      realpath(this.options.pythonExecutable),
      realpath(this.options.bridgeScript),
      realpath(this.options.packageRoot),
    ]);
    if (canonicalExecutable(git, process.platform) === undefined || canonicalExecutable(python, process.platform) === undefined) {
      throw new Error("bridge executable identity is invalid");
    }
    if (!inside(script, root)) throw new Error("bridge script is outside the installed package");
    const taskkill = windowsTaskkillExecutable();
    if (process.platform === "win32" && taskkill === undefined) throw new Error("taskkill is unavailable");
    return { git, python, root, script, ...(taskkill === undefined ? {} : { taskkill }) };
  }

  private failure(request: BridgeRequest, detail: BridgeFailureDetail): BridgeResponse {
    const category = this.options.toolClasses[request.tool ?? ""] ?? "OTHER";
    const advisory = request.event !== "tool_call" || category === "READ";
    return {
      version: 1,
      outcome: advisory ? "warn" : "block",
      ruleId: "PI-BRIDGE",
      message: `codeArbiter Pi bridge ${safeDiagnostic(detail)}; ${advisory ? "continuing advisory operation; " : "mutation blocked; "}run /ca-doctor.`,
      auditCode: advisory ? "PI_BRIDGE_WARN" : "PI_BRIDGE_BLOCK",
    };
  }

  private async auditFailure(
    request: BridgeRequest,
    response: BridgeResponse,
    counts: { request: number; stdout: number; stderr: number },
  ): Promise<void> {
    try {
      if (this.options.shouldAuditFailure?.(request) === false) return;
    } catch {
      // A malformed selector fails toward retaining the ordinary audit.
    }
    const line = [
      `[${new Date().toISOString()}]`,
      "HOST: pi",
      `RULE: ${response.ruleId ?? "PI-BRIDGE"}`,
      `AUDIT: ${response.auditCode ?? "PI_BRIDGE_FAILURE"}`,
      `CORRELATION: ${randomUUID()}`,
      `REQUEST_BYTES: ${counts.request}`,
      `STDOUT_BYTES: ${counts.stdout}`,
      `STDERR_BYTES: ${counts.stderr}`,
    ].join(" | ") + "\n";
    try {
      await appendFile(resolve(request.cwd, ".codearbiter", "gate-events.log"), line, { encoding: "utf8" });
    } catch {
      // A bridge failure must retain its fail direction even if the audit sink is unavailable.
    }
  }

  private async failed(
    request: BridgeRequest,
    detail: BridgeFailureDetail,
    counts: { request: number; stdout: number; stderr: number } = { request: 0, stdout: 0, stderr: 0 },
  ): Promise<BridgeResponse> {
    const response = this.failure(request, detail);
    await this.auditFailure(request, response, counts);
    return response;
  }

  async call(request: BridgeRequest, signal: AbortSignal): Promise<BridgeResponse> {
    let paths: { git: string; python: string; root: string; script: string; taskkill?: string };
    let userHome: string;
    try {
      paths = await this.ready;
    } catch {
      return await this.failed(request, "path validation failed");
    }
    try {
      const project = await realpath(request.cwd);
      if (inside(paths.git, project) || inside(paths.python, project)) {
        return await this.failed(request, "path validation failed");
      }
      const canonicalHome = canonicalUserHome(project, paths.root);
      if (canonicalHome === undefined) return await this.failed(request, "path validation failed");
      userHome = canonicalHome;
    } catch {
      return await this.failed(request, "path validation failed");
    }
    let body: Buffer;
    try {
      body = Buffer.from(JSON.stringify(request), "utf8");
    } catch {
      return await this.failed(request, "request serialization failed");
    }
    if (body.byteLength > this.maxRequestBytes) return await this.failed(request, "request overflow", { request: body.byteLength, stdout: 0, stderr: 0 });
    if (signal.aborted) return await this.failed(request, "cancelled", { request: body.byteLength, stdout: 0, stderr: 0 });

    return await new Promise<BridgeResponse>((resolveResponse) => {
      let child: ReturnType<typeof spawn>;
      try {
        child = spawnImpl(paths.python, [...(this.options.pythonPrefixArgs ?? []), paths.script], {
          cwd: paths.root,
          detached: process.platform !== "win32",
          env: minimalEnvironment({ git: paths.git, python: paths.python }, userHome),
          shell: false,
          stdio: ["pipe", "pipe", "pipe"],
          windowsHide: true,
        });
      } catch {
        void this.failed(
          request,
          "bridge launch failed",
          { request: body.byteLength, stdout: 0, stderr: 0 },
        ).then(resolveResponse, () => resolveResponse(this.failure(request, "bridge launch failed")));
        return;
      }
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let reason: BridgeFailureDetail | undefined;
      let settled = false;
      let finishing = false;
      let settleDeadline: NodeJS.Timeout | undefined;
      const finish = (response: BridgeResponse) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (settleDeadline !== undefined) clearTimeout(settleDeadline);
        signal.removeEventListener("abort", abort);
        resolveResponse(response);
      };
      const failAndKill = (value: BridgeFailureDetail) => {
        if (reason !== undefined) return;
        reason = value;
        killTree(child, paths.taskkill);
        // If the kill attempt fails silently or 'close' otherwise never arrives, force-settle
        // with the already-recorded failure reason rather than hanging the caller forever.
        settleDeadline = setTimeout(() => finishFailure(value), KILL_SETTLE_DEADLINE_MS);
        settleDeadline.unref?.();
      };
      const finishFailure = (detail: BridgeFailureDetail) => {
        if (settled || finishing) return;
        finishing = true;
        void this.failed(request, detail, { request: body.byteLength, stdout: stdoutBytes, stderr: stderrBytes })
          .then(finish, () => finish(this.failure(request, detail)));
      };
      const collect = (target: Buffer[], chunk: Buffer, stream: "stdout" | "stderr") => {
        const count = stream === "stdout" ? stdoutBytes : stderrBytes;
        const remaining = Math.max(0, this.maxStreamBytes - count);
        if (remaining > 0) target.push(chunk.subarray(0, remaining));
        if (stream === "stdout") stdoutBytes += chunk.byteLength;
        else stderrBytes += chunk.byteLength;
        if (count + chunk.byteLength > this.maxStreamBytes) failAndKill("protocol overflow");
      };
      const abort = () => failAndKill("cancelled");
      const timer = setTimeout(() => failAndKill("timed out"), this.timeoutMs);
      signal.addEventListener("abort", abort, { once: true });
      child.stdout!.on("data", (chunk: Buffer) => collect(stdout, chunk, "stdout"));
      child.stderr!.on("data", (chunk: Buffer) => collect(stderr, chunk, "stderr"));
      child.on("error", () => finishFailure("bridge launch failed"));
      child.on("close", (code) => {
        if (reason !== undefined) return finishFailure(reason);
        if (code !== 0) return finishFailure("bridge process failed");
        const stdoutText = Buffer.concat(stdout).toString("utf8");
        let parsed: unknown;
        try { parsed = JSON.parse(stdoutText); } catch { return finishFailure("returned malformed protocol"); }
        if (!validResponse(parsed)) return finishFailure("returned malformed protocol");
        finish(sanitizedResponse(parsed, request));
      });
      child.stdin!.on("error", () => undefined);
      child.stdin!.end(body);
    });
  }
}

export interface PythonCommand {
  executable: string;
  prefixArgs: readonly string[];
}

export interface PythonProbeResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

export type PythonProbe = (executable: string, prefixArgs: readonly string[], cwd: string) => PythonProbeResult;

function systemPythonProbe(executable: string, prefixArgs: readonly string[], cwd: string): PythonProbeResult {
  const probe = spawnSync(executable, [...prefixArgs, "-c", "import sys; print(sys.version_info[0]); print(sys.executable)"], {
      cwd,
      encoding: "utf8",
      env: minimalEnvironment(),
      shell: false,
      timeout: 2_000,
      windowsHide: true,
  });
  return { status: probe.status, stdout: probe.stdout ?? "", stderr: probe.stderr ?? "" };
}

export function resolvePythonCommand(
  platform: NodeJS.Platform = process.platform,
  probe: PythonProbe = systemPythonProbe,
  searchCwd?: string,
  excludedProjectCwd?: string,
  pathValue: string = process.env.PATH ?? "",
): PythonCommand {
  const pathApi = platform === "win32" ? win32 : posix;
  const safeCwd = searchCwd ?? (platform === "win32" ? win32.parse(process.execPath).root : "/");
  if (!pathApi.isAbsolute(safeCwd)) {
    throw new Error("codeArbiter Python search cwd must be absolute; run /ca-doctor.");
  }
  const candidates: ReadonlyArray<readonly [string, readonly string[]]> = platform === "win32"
    ? [["py.exe", ["-3"]], ["python.exe", []], ["python3.exe", []]]
    : [["python3", []], ["python", []]];
  for (const [candidate, prefixArgs] of candidates) {
    const probedCandidate = probe === systemPythonProbe
      ? trustedPathCandidate(candidate, excludedProjectCwd ?? safeCwd, platform, pathValue)
      : candidate.replace(/\.exe$/u, "");
    if (probedCandidate === undefined) continue;
    const result = probe(probedCandidate, prefixArgs, safeCwd);
    const lines = result.stdout.trim().split(/\r?\n/u);
    const executable = lines[1] ?? "";
    const absolute = platform === "win32" ? win32.isAbsolute(executable) : posix.isAbsolute(executable);
    const canonical = absolute
      ? (probe === systemPythonProbe ? canonicalExecutable(executable, platform) : executable)
      : undefined;
    if (
      result.status === 0
      && lines[0] === "3"
      && canonical !== undefined
      && (probe !== systemPythonProbe || !sameOrInside(canonical, excludedProjectCwd ?? safeCwd, platform))
    ) {
      return { executable: canonical, prefixArgs: [] };
    }
  }
  throw new Error("codeArbiter could not resolve an absolute Python interpreter; run /ca-doctor.");
}
