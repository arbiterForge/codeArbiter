/**
 * delegated-executor.ts - the parent-owned effect executor for delegated child operations
 * (PI-D03/PI-D04).
 *
 * Runs only AFTER the parent's final gate approved the exact frozen operation. It owns:
 * - target admission for write/edit: the request path must resolve inside the strictly observed
 *   canonical worktree, through no linked component, to a regular single-linked file (or an
 *   absent one), and never inside `.git`. These are admitted request targets, not a sandbox:
 *   they are observations, not an atomic guarantee against a concurrent external path swap;
 * - the durable exclusive claim before the effect and the observed outcome before the reply;
 * - command execution through `piShellLaunch` + a managed process tree with a credential-blind
 *   environment (never the parent's `process.env`, see DEF-PI-ENV-01), bounded output, a
 *   deadline, and verified tree cleanup whose result is reported as containment;
 * - honest observations: file hashes before/after; desired bytes after a crash are reported as
 *   observed state, never as proof that this operation ran exactly once.
 * Nothing here replays an uncertain effect or restores a before-image over later edits.
 */
import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";

import { PI_PROVIDER_ENV } from "./child-env.ts";
import { piShellLaunch } from "./background-jobs.ts";
import { openProcessTree } from "./process-tree.ts";
import type { ManagedProcessTree, ProcessTreeSpawnInput } from "./process-tree.ts";
import { lexicallyInside } from "./path-boundary.ts";
import { redactSecrets } from "./redaction.ts";
import { DELEGATION_PROFILE, MAX_OPERATION_RESULT_TEXT_BYTES, operationId } from "./delegation-contract.ts";
import type {
  ContainmentState,
  DelegatedTool,
  DelegationReason,
  ExecutionState,
  JournalRecord,
  ObservationState,
  OperationResponse,
  OperationResult,
  RecoveryState,
  RunGrant,
} from "./delegation-contract.ts";
import type { DelegationJournal } from "./delegation-journal.ts";
import type { ToolDefinitionPort } from "./contracts.ts";

const DEFAULT_BASH_TIMEOUT_SECONDS = 120;
const MAX_BASH_TIMEOUT_SECONDS = 600;
const OUTPUT_TRUNCATED = "\n[codeArbiter: output truncated]";
const MAX_OBSERVED_TARGET_BYTES = 16 * 1024 * 1024;

const WINDOWS_COMMAND_BASELINE = [
  "SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
  "APPDATA", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "ProgramW6432",
  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "SystemDrive", "USERNAME",
] as const;
const POSIX_COMMAND_BASELINE = ["HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL", "TERM"] as const;

/**
 * DEF-PI-ENV-01: delegated commands get an allowlisted host baseline only. Provider credential
 * variables, the inference broker token, the delegation token and every other parent variable
 * are absent. A credential stored in a FILE under the operator's home is still readable by an
 * approved command: the trusted-host profile promises no filesystem confinement.
 */
export function credentialBlindHostEnvironment(
  parent: Readonly<NodeJS.ProcessEnv>,
  platform: NodeJS.Platform = process.platform,
): NodeJS.ProcessEnv {
  const names: readonly string[] = platform === "win32" ? WINDOWS_COMMAND_BASELINE : POSIX_COMMAND_BASELINE;
  const env: NodeJS.ProcessEnv = {};
  const lookup = new Map(Object.keys(parent).map((key) => [platform === "win32" ? key.toLowerCase() : key, key]));
  for (const name of names) {
    const actual = lookup.get(platform === "win32" ? name.toLowerCase() : name);
    const value = actual === undefined ? undefined : parent[actual];
    if (typeof value === "string" && value.length > 0 && value.length <= 32_768 && !value.includes("\0")) env[name] = value;
  }
  for (const providerNames of Object.values(PI_PROVIDER_ENV)) for (const name of providerNames) delete env[name];
  return env;
}

export function credentialBlindCommandEnvironment(parent: Readonly<NodeJS.ProcessEnv>, platform: NodeJS.Platform = process.platform): NodeJS.ProcessEnv {
  return { ...credentialBlindHostEnvironment(parent, platform), CODEARBITER_DELEGATED: "1" };
}

export function sha256(bytes: string | Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export interface AdmittedTarget {
  readonly absolute: string;
  readonly relative: string;
}

/** Strict admission of a write/edit request path against the canonical worktree. */
export async function admitTarget(worktree: string, raw: string, platform: NodeJS.Platform = process.platform): Promise<AdmittedTarget | undefined> {
  if (typeof raw !== "string" || raw === "" || raw.length > 4_096 || /[\u0000-\u001f\u007f]/u.test(raw)) return undefined;
  if (platform === "win32") {
    // UNC, device (\\?\, \\.\), drive-relative (C:foo) and alternate-data-stream spellings.
    if (/^[\\/]{2}/u.test(raw) || /^[A-Za-z]:(?![\\/])/u.test(raw) || raw.slice(2).includes(":")) return undefined;
  }
  let root: string;
  try { root = await realpath(worktree); } catch { return undefined; }
  const absolute = isAbsolute(raw) ? resolve(raw) : resolve(root, raw);
  if (!lexicallyInside(absolute, root) || absolute === root) return undefined;
  const rel = relative(root, absolute);
  const parts = rel.split(sep);
  if (parts.some((part) => part === "" || part === ".." || part.toLowerCase() === ".git")) return undefined;
  // Every existing component from the root down must be a plain directory (no symlink or
  // junction); the target itself, if present, a regular single-linked file.
  let cursor = root;
  for (let index = 0; index < parts.length; index += 1) {
    cursor = resolve(cursor, parts[index]!);
    let stats;
    try { stats = await lstat(cursor); } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") break;
      return undefined;
    }
    if (stats.isSymbolicLink()) return undefined;
    const last = index === parts.length - 1;
    if (last ? (!stats.isFile() || stats.nlink !== 1) : !stats.isDirectory()) return undefined;
    try { if (!lexicallyInside(await realpath(cursor), root)) return undefined; } catch { return undefined; }
  }
  return Object.freeze({ absolute, relative: rel.split(sep).join("/") });
}

/** "absent" when no file exists; "unreadable" when it cannot be observed. */
export async function observeTarget(path: string): Promise<string> {
  let handle;
  try {
    const stats = await lstat(path);
    if (!stats.isFile() || stats.isSymbolicLink() || stats.nlink !== 1 || stats.size > MAX_OBSERVED_TARGET_BYTES) return "unreadable";
    handle = await open(path, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
    const opened = await handle.stat();
    if (!opened.isFile() || opened.nlink !== 1 || opened.dev !== stats.dev || opened.ino !== stats.ino
      || opened.size !== stats.size || opened.size > MAX_OBSERVED_TARGET_BYTES) return "unreadable";
    const digest = createHash("sha256"); const chunk = Buffer.alloc(64 * 1024); let offset = 0;
    while (true) {
      const read = await handle.read(chunk, 0, chunk.length, offset);
      if (read.bytesRead === 0) break;
      offset += read.bytesRead; if (offset > opened.size || offset > MAX_OBSERVED_TARGET_BYTES) return "unreadable";
      digest.update(chunk.subarray(0, read.bytesRead));
    }
    const after = await lstat(path);
    if (offset !== opened.size || after.isSymbolicLink() || after.nlink !== 1 || after.dev !== opened.dev || after.ino !== opened.ino
      || after.size !== opened.size || after.mtimeMs !== opened.mtimeMs) return "unreadable";
    return digest.digest("hex");
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "ENOENT" ? "absent" : "unreadable";
  }
  finally { await handle?.close().catch(() => undefined); }
}

function boundedText(text: string): string {
  text = redactSecrets(text);
  if (Buffer.byteLength(text, "utf8") <= MAX_OPERATION_RESULT_TEXT_BYTES) return text;
  const budget = MAX_OPERATION_RESULT_TEXT_BYTES - Buffer.byteLength(OUTPUT_TRUNCATED, "utf8");
  let cut = Buffer.from(text, "utf8").subarray(0, budget).toString("utf8");
  if (cut.endsWith("\ufffd")) cut = cut.slice(0, -1);
  return cut + OUTPUT_TRUNCATED;
}

function resultFromNative(value: unknown): OperationResult {
  const record = value as { content?: unknown; isError?: unknown } | undefined;
  const blocks = Array.isArray(record?.content) ? record!.content as unknown[] : [];
  const text = blocks.flatMap((block) => {
    const item = block as { type?: unknown; text?: unknown };
    return item?.type === "text" && typeof item.text === "string" ? [item.text] : [];
  }).join("\n");
  return Object.freeze({
    content: Object.freeze([Object.freeze({ type: "text" as const, text: boundedText(text === "" ? "Done." : text) })]),
    isError: record?.isError === true,
  });
}

export interface ExecutorPorts {
  readonly journal: DelegationJournal;
  readonly write: (cwd: string) => ToolDefinitionPort;
  readonly edit: (cwd: string) => ToolDefinitionPort;
  readonly shell: () => Promise<Readonly<{ shellPath: string; commandPrefix?: string }> | undefined>;
  readonly environment: Readonly<NodeJS.ProcessEnv>;
  readonly platform?: NodeJS.Platform;
  readonly openTree?: (command: string, args: readonly string[], options: ProcessTreeSpawnInput) => Promise<ManagedProcessTree>;
  readonly now?: () => Date;
}

export interface ExecutionRequest {
  readonly grant: RunGrant;
  readonly requestId: string;
  readonly tool: DelegatedTool;
  readonly params: Readonly<Record<string, unknown>>;
  readonly digest: string;
  readonly toolCallId: string;
  readonly signal: AbortSignal;
  /** Parent-only final enablement/lifecycle probe; never received over the child protocol. */
  readonly isCurrent?: () => boolean | Promise<boolean>;
  readonly shellBinding?: Readonly<{ shellPath: string; commandPrefix?: string }> | null;
  readonly permissionCorrelation?: string;
}

type Axes = Omit<OperationResponse, "v">;

function axes(
  requestId: string,
  execution: ExecutionState,
  containment: ContainmentState,
  observation: ObservationState,
  recovery: RecoveryState,
  extra: { reason?: DelegationReason; result?: OperationResult } = {},
): Axes {
  return Object.freeze({ requestId, admission: "admitted" as const, execution, containment, observation, recovery, ...extra });
}

export function createDelegatedExecutor(ports: ExecutorPorts) {
  const platform = ports.platform ?? process.platform;
  const now = ports.now ?? (() => new Date());
  let tail: Promise<unknown> = Promise.resolve();
  let containmentHeld = false;
  const stopped = (request: ExecutionRequest): Axes | undefined => {
    const cancelled = request.signal.aborted;
    if (!cancelled && performance.now() < request.grant.expiresAtMonotonicMs) return undefined;
    return Object.freeze({ requestId: request.requestId, admission: cancelled ? "cancelled" : "expired",
      execution: "not-started", containment: "not-applicable", observation: "unavailable",
      recovery: "new-operation-required", reason: cancelled ? "grant-revoked" : "grant-expired" });
  };
  const revalidate = async (request: ExecutionRequest): Promise<Axes | undefined> => {
    let live = true;
    try { live = request.isCurrent === undefined || await request.isCurrent() === true; } catch { live = false; }
    if (!live) return Object.freeze({ requestId: request.requestId, admission: "revoked", execution: "not-started",
      containment: "not-applicable", observation: "unavailable", recovery: "new-operation-required", reason: "grant-revoked" });
    return stopped(request);
  };
  const record = (
    request: ExecutionRequest,
    phase: "claimed" | "started" | "observed",
    extra: Partial<Pick<JournalRecord, "target" | "targetHash" | "execution" | "containment" | "processId">>,
  ): JournalRecord => Object.freeze({
    v: 1 as const,
    phase,
    operationId: operationId(request.grant.runId, request.requestId),
    runId: request.grant.runId,
    callerCorrelation: request.grant.callerCorrelation,
    role: request.grant.role,
    tool: request.tool,
    digest: request.digest,
    profile: DELEGATION_PROFILE,
    recordedAt: now().toISOString(),
    requestId: request.requestId,
    ...(request.permissionCorrelation === undefined ? {} : {
      consentSource: "parent-human-confirmation" as const, permissionCorrelation: request.permissionCorrelation,
    }),
    ...extra,
  });

  /** Claim first. Returns an axes reply when execution must not start. */
  const claim = async (request: ExecutionRequest, extra: Partial<JournalRecord>): Promise<Axes | undefined> => {
    const claimed = await ports.journal.claim(record(request, "claimed", extra));
    if (claimed.state === "claimed") return undefined;
    if (claimed.state === "unavailable") {
      // A failed/uncertain claim write is never permission to execute.
      return axes(request.requestId, "not-started", "not-applicable", "unavailable", "read-only-reconciliation", { reason: "journal-unavailable" });
    }
    if (claimed.claim !== undefined && claimed.claim.digest !== request.digest) {
      return axes(request.requestId, "not-started", "not-applicable", "unavailable", "new-operation-required", { reason: "operation-id-reused" });
    }
    const observed = claimed.observed;
    if (observed?.execution === "completed" || observed?.execution === "failed") {
      // Durable outcome exists but its response body was not retained: report the outcome
      // honestly without re-executing. The child sees the fact, not a fabricated result.
      return observed.execution === "completed"
        ? axes(request.requestId, "completed", observed.containment ?? "not-applicable", "target-state-only", "none",
          { result: { content: [{ type: "text", text: "Already applied by an earlier identical request; not re-executed." }], isError: false } })
        : axes(request.requestId, "failed", observed.containment ?? "not-applicable", "target-state-only", "new-operation-required", { reason: "executor-failed" });
    }
    return axes(request.requestId, "outcome-unknown", "unverified", "unavailable", "read-only-reconciliation", { reason: "journal-unknown" });
  };

  const finish = async (request: ExecutionRequest, reply: Axes, extra: Partial<JournalRecord>): Promise<Axes> => {
    const execution = reply.execution === "completed" || reply.execution === "failed" ? reply.execution
      : reply.execution === "not-started" ? "failed" : "outcome-unknown";
    const persisted = await ports.journal.observe(record(request, "observed", {
      ...extra, execution, containment: reply.containment,
    }));
    if (persisted) return reply;
    // The effect happened (or may have) but its outcome is not durable: never acknowledge it as
    // completed; recovery must re-observe.
    return axes(request.requestId, "outcome-unknown", reply.containment === "running" ? "unverified" : reply.containment,
      "unavailable", "read-only-reconciliation", { reason: "journal-unknown" });
  };

  const fileOperation = async (request: ExecutionRequest): Promise<Axes> => {
    const target = await admitTarget(request.grant.worktree, request.params.path as string, platform);
    if (target === undefined) {
      return Object.freeze({ requestId: request.requestId, admission: "denied" as const, execution: "not-started" as const,
        containment: "not-applicable" as const, observation: "unavailable" as const, recovery: "new-operation-required" as const,
        reason: "target-invalid" as const });
    }
    const before = await observeTarget(target.absolute);
    if (before === "unreadable") {
      return Object.freeze({ requestId: request.requestId, admission: "denied" as const, execution: "not-started" as const,
        containment: "not-applicable" as const, observation: "unavailable" as const, recovery: "new-operation-required" as const,
        reason: "target-invalid" as const });
    }
    const stop = await claim(request, { target: target.relative, targetHash: before });
    if (stop !== undefined) return stop;
    const cancelled = await revalidate(request);
    if (cancelled !== undefined) return await finish(request, cancelled, { target: target.relative, targetHash: before });
    // Refuse a known stale precondition between the claim and the effect.
    const recheck = await admitTarget(request.grant.worktree, request.params.path as string, platform);
    if (recheck === undefined || recheck.absolute !== target.absolute || await observeTarget(target.absolute) !== before) {
      return await finish(request, axes(request.requestId, "failed", "not-applicable", "stale", "new-operation-required",
        { reason: "target-invalid" }), { target: target.relative, targetHash: before });
    }
    let native: unknown;
    try {
      const cancelled = await revalidate(request);
      if (cancelled !== undefined) return await finish(request, cancelled, { target: target.relative, targetHash: before });
      const definition = (request.tool === "write" ? ports.write : ports.edit)(request.grant.worktree);
      native = await definition.execute(request.toolCallId, { ...request.params, path: target.absolute }, request.signal);
    } catch {
      const after = await observeTarget(target.absolute);
      const changed = after !== before;
      // A throw after a possible write is uncertain unless the target is observed unchanged.
      const reply = changed
        ? axes(request.requestId, "outcome-unknown", "not-applicable", "target-state-only", "read-only-reconciliation")
        : axes(request.requestId, "failed", "not-applicable", "target-state-only", "new-operation-required", {
          reason: "executor-failed",
          result: { content: [{ type: "text", text: "Parent executor failed; inspect the target before a new attempt." }], isError: true },
        });
      return await finish(request, reply, { target: target.relative, targetHash: after });
    }
    const after = await observeTarget(target.absolute);
    const result = resultFromNative(native);
    const exact = request.tool === "write" && after === sha256(Buffer.from(request.params.content as string, "utf8"));
    if (!result.isError && request.tool === "write" && !exact) {
      return await finish(request, axes(request.requestId, "outcome-unknown", "not-applicable", "target-state-only",
        "read-only-reconciliation", { reason: "executor-failed" }), { target: target.relative, targetHash: after });
    }
    const reply = result.isError
      ? axes(request.requestId, "failed", "not-applicable", "target-state-only", "new-operation-required", { reason: "executor-failed", result })
      : axes(request.requestId, "completed", "not-applicable", exact ? "exact" : "target-state-only", "none", { result });
    return await finish(request, reply, { target: target.relative, targetHash: after });
  };

  const commandOperation = async (request: ExecutionRequest): Promise<Axes> => {
    const shell = request.shellBinding === undefined ? await ports.shell() : request.shellBinding ?? undefined;
    const launch = shell === undefined ? undefined : piShellLaunch({
      shellPath: shell.shellPath,
      command: request.params.command as string,
      ...(shell.commandPrefix === undefined ? {} : { commandPrefix: shell.commandPrefix }),
    });
    if (launch === undefined) {
      return Object.freeze({ requestId: request.requestId, admission: "unavailable" as const, execution: "not-started" as const,
        containment: "not-applicable" as const, observation: "unavailable" as const, recovery: "new-operation-required" as const,
        reason: "executor-unavailable" as const });
    }
    const stop = await claim(request, {});
    if (stop !== undefined) return stop;
    const cancelled = await revalidate(request);
    if (cancelled !== undefined) return await finish(request, cancelled, {});
    const timeoutSeconds = Math.min(MAX_BASH_TIMEOUT_SECONDS, (request.params.timeout as number | undefined) ?? DEFAULT_BASH_TIMEOUT_SECONDS);
    let tree: ManagedProcessTree;
    try {
      tree = await (ports.openTree ?? openProcessTree)(launch.command, launch.args, {
        cwd: request.grant.worktree,
        env: credentialBlindCommandEnvironment(ports.environment, platform),
        stdio: ["pipe", "pipe", "pipe", "pipe"],
      });
    } catch {
      // Spawn refused: nothing started, and the claim records that durably.
      return await finish(request, axes(request.requestId, "failed", "not-applicable", "unavailable", "new-operation-required",
        { reason: "executor-unavailable" }), {});
    }
    const chunks: Buffer[] = [];
    let captured = 0;
    let truncated = false;
    const capture = (chunk: Buffer | string) => {
      const bytes = typeof chunk === "string" ? Buffer.from(chunk, "utf8") : chunk;
      if (captured >= MAX_OPERATION_RESULT_TEXT_BYTES) { truncated = true; return; }
      const slice = bytes.subarray(0, MAX_OPERATION_RESULT_TEXT_BYTES - captured);
      if (slice.length < bytes.length) truncated = true;
      captured += slice.length;
      chunks.push(slice);
    };
    const { child, cleanup } = tree;
    let ended: "exited" | "timeout" | "cancelled" | undefined;
    const exit = new Promise<number | null>((resolveExit) => {
      child.stdout.on("data", capture);
      child.stderr.on("data", capture);
      child.once("error", () => resolveExit(null));
      child.once("close", (code: number | null) => resolveExit(code));
    });
    const processId = Number.isSafeInteger(child.pid) && child.pid! > 0 ? child.pid! : null;
    const retireSpawned = async (retired: Axes): Promise<Axes> => {
      const termination = await cleanup.terminate(retired.admission === "expired" ? "timeout" : "cancelled").catch(() => undefined);
      const containment = termination?.verified === true ? "verified-stopped" : "unverified";
      containmentHeld ||= containment === "unverified";
      // A managed process already exists; startup code may have run even when
      // legacy shell command bytes were withheld. Preserve that uncertainty.
      // Admission already happened before spawn. Retirement is a later fact,
      // carried by its fixed reason; it cannot rewrite history to "never ran".
      return await finish(request, axes(request.requestId, "outcome-unknown", containment, "unavailable",
        containmentHeld ? "dependent-resource-held" : "read-only-reconciliation", { reason: retired.reason }), { processId });
    };
    const afterSpawn = await revalidate(request);
    if (afterSpawn !== undefined) return await retireSpawned(afterSpawn);
    // Keep the launch observation separate from direct-file state. This PID is a
    // historical reference only: recovery never signals it or assumes it has not
    // been reused. A crash between spawn and this write remains an unknown claim.
    if (!await ports.journal.started(record(request, "started", { processId }))) {
      const stopped = await cleanup.terminate("cancelled").catch(() => undefined);
      const containment = stopped?.verified === true ? "verified-stopped" : "unverified";
      containmentHeld ||= containment === "unverified";
      return await finish(request, axes(request.requestId, "outcome-unknown", containment, "unavailable",
        containmentHeld ? "dependent-resource-held" : "read-only-reconciliation", { reason: "journal-unknown" }), { processId });
    }
    const beforeRelease = await revalidate(request) ?? stopped(request);
    if (beforeRelease !== undefined) return await retireSpawned(beforeRelease);
    try {
      const capability = child.stdio[3] as { end?: () => void } | undefined;
      capability?.end?.();
      if (launch.stdin !== undefined) child.stdin.end(launch.stdin, "utf8");
      else child.stdin.end();
    } catch { /* The exit path below observes the failure. */ }
    let timer: NodeJS.Timeout | undefined;
    const aborted = new Promise<"cancelled">((resolveAbort) => {
      if (request.signal.aborted) resolveAbort("cancelled");
      else request.signal.addEventListener("abort", () => resolveAbort("cancelled"), { once: true });
    });
    const timedOut = new Promise<"timeout">((resolveTimeout) => {
      timer = setTimeout(() => resolveTimeout("timeout"), timeoutSeconds * 1_000);
    });
    let code: number | null = null;
    const first = await Promise.race([exit.then((value) => ({ value })), aborted, timedOut]);
    if (timer !== undefined) clearTimeout(timer);
    if (typeof first === "object") { ended = "exited"; code = first.value; } else ended = first;
    // Verify the whole tree is gone even after a normal exit: descendants may survive the shell.
    const termination = await cleanup.terminate(ended === "exited" ? "completed" : ended).catch(() => undefined);
    const containment: ContainmentState = termination?.verified === true ? "verified-stopped" : "unverified";
    if (containment === "unverified") containmentHeld = true;
    if (ended !== "exited") await Promise.race([exit, new Promise((r) => setTimeout(r, 2_000))]);
    let output = Buffer.concat(chunks).toString("utf8");
    if (truncated) output = boundedText(output + OUTPUT_TRUNCATED);
    if (ended !== "exited") {
      // A command stopped mid-run has an uncertain effect; it is not "failed and harmless".
      return await finish(request, axes(request.requestId, "outcome-unknown", containment, "unavailable",
        containment === "verified-stopped" ? "read-only-reconciliation" : "dependent-resource-held",
        { reason: containment === "unverified" ? "containment-unverified" : "executor-failed" }), { processId });
    }
    const text = boundedText(`${output}${output.endsWith("\n") || output === "" ? "" : "\n"}[exit code ${code ?? "unknown"}]`);
    const result: OperationResult = Object.freeze({ content: Object.freeze([Object.freeze({ type: "text" as const, text })]), isError: code !== 0 });
    const reply = code === 0
      ? axes(request.requestId, "completed", containment, "exact", containmentHeld ? "dependent-resource-held" : "none", { result })
      : axes(request.requestId, "failed", containment, "exact", containmentHeld ? "dependent-resource-held" : "new-operation-required", { result });
    return await finish(request, reply, { processId });
  };

  return {
    async execute(request: ExecutionRequest): Promise<Axes> {
      const execution = tail.then(async () => {
        const stop = await revalidate(request);
        if (stop !== undefined) return stop;
        try {
          const pending = await ports.journal.unresolved();
          containmentHeld ||= pending.some((operation) => operation.claim === undefined
            || operation.observed?.containment === "unverified"
            || (operation.claim.tool === "bash" && operation.observed === undefined));
          // An uncertain file effect is scoped to its direct target. A fresh operation
          // must not silently overwrite later edits while that target is unresolved.
          // Bash has unbounded host effects, so it depends on every unresolved target.
          const currentId = operationId(request.grant.runId, request.requestId);
          const target = request.tool === "bash" ? undefined
            : await admitTarget(request.grant.worktree, request.params.path as string, platform);
          const samePath = (a: string, b: string) => platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b;
          const dependent = pending.some((operation) => operation.operationId !== currentId
            && operation.claim?.tool !== "bash" && (request.tool === "bash"
              || (target !== undefined && operation.claim?.target !== undefined
                && samePath(target.relative, operation.claim.target))));
          if (dependent) return { ...axes(request.requestId, "not-started", "not-applicable", "unavailable", "dependent-resource-held",
            { reason: "journal-unknown" }), admission: "unavailable" as const };
        } catch {
          return { ...axes(request.requestId, "not-started", "not-applicable", "unavailable", "dependent-resource-held",
            { reason: "journal-unavailable" }), admission: "unavailable" as const };
        }
        if (containmentHeld) return { ...axes(request.requestId, "not-started", "not-applicable", "unavailable", "dependent-resource-held",
          { reason: "containment-unverified" }), admission: "unavailable" as const };
        if (request.tool === "bash") return await commandOperation(request);
        return await fileOperation(request);
      });
      tail = execution.catch(() => undefined);
      return await execution;
    },
  };
}
