import { createHash, randomUUID } from "node:crypto";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { types as utilTypes } from "node:util";

import type {
  Collision,
  BridgePort,
  CommandCatalogEntry,
  ExtensionContextPort,
  LifecycleLease,
  ParentPiPort,
  SlashCommand,
  ToolDefinitionPort,
  ToolExecutionContextPort,
} from "./contracts.ts";
import type {
  BackgroundJobRuntime,
  BackgroundJobSnapshot,
  BackgroundJobStopReason,
} from "./background-jobs.ts";
import { MAX_ACTIVE_JOBS } from "./background-jobs.ts";
import { callPlanFileBridge } from "./bridge.ts";
import {
  PLAN_SESSION_ENTRY_TYPE,
  approvePlan,
  cancelPlan,
  encodePlanSessionState,
  enterPlan,
  reconcilePlanState,
  restorePlanSessionState,
} from "./plan-mode.ts";
import type { PlanSessionState } from "./plan-mode.ts";
import type { PolicyMode } from "./policy.ts";

const COMMAND_DIAGNOSIS = "codeArbiter could not validate the Pi command surface; run /ca-doctor.";
const NAME = /^[a-z][a-z0-9-]*$/u;
const ENVELOPE_UNSAFE = /[\n\r"<>]/u;
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u;
const PLAN_COMMAND_DIAGNOSIS = "codeArbiter could not validate the Pi plan command; run /ca-doctor.";
const PLAN_SYNTAX = "Usage: /ca-plan enter <slug> | status | approve | cancel.";
const PLAN_SLUG = /^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/u;
const PLAN_ENTRY_LIMIT = 4_096;

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function pluginRootFromModule(): string {
  let cursor = dirname(fileURLToPath(import.meta.url));
  while (true) {
    try {
      const manifest = JSON.parse(readFileSync(resolve(cursor, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") return realpathSync(cursor);
    } catch {
      // Continue toward the filesystem root; ca-pi-tools is intentionally skipped.
    }
    const parent = dirname(cursor);
    if (parent === cursor) throw new Error(COMMAND_DIAGNOSIS);
    cursor = parent;
  }
}

function validatedEntry(entry: CommandCatalogEntry): void {
  if (!NAME.test(entry.name) || ENVELOPE_UNSAFE.test(entry.name)) throw new Error(COMMAND_DIAGNOSIS);
  if (entry.skillPath !== `skills/ca-${entry.name}/SKILL.md` || isAbsolute(entry.skillPath)) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
  if (entry.skillPath.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
}

function strictUtf8(path: string): string {
  const bytes = readFileSync(path);
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function hasSymlinkComponent(root: string, path: string): boolean {
  const lexicalRoot = resolve(root);
  const lexicalPath = resolve(path);
  if (!inside(lexicalPath, lexicalRoot) || lstatSync(lexicalRoot).isSymbolicLink()) return true;
  const suffix = relative(lexicalRoot, lexicalPath);
  let cursor = lexicalRoot;
  for (const part of suffix.split(/[\\/]/u).filter(Boolean)) {
    cursor = resolve(cursor, part);
    if (lstatSync(cursor).isSymbolicLink()) return true;
  }
  return false;
}

function stripStartingFrontmatter(content: string): string {
  const normalized = content.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  if (!normalized.startsWith("---\n")) return normalized.trim();
  let end = normalized.indexOf("\n---\n", 4);
  if (end < 0 && normalized.endsWith("\n---")) end = normalized.length - 4;
  if (end < 0) return normalized.trim();
  return normalized.slice(end + 4).trim();
}

export function nativeSkillExpansion(
  name: string,
  path: string,
  body: string,
  args: string,
): string {
  const baseDir = dirname(path);
  const block = `<skill name="ca-${name}" location="${path}">\n`
    + `References are relative to ${baseDir}.\n\n${body}\n</skill>`;
  return args.length > 0 ? `${block}\n\n${args}` : block;
}

function declaredPackageOwner(command: SlashCommand, expectedPath: string): boolean {
  try {
    if (command.sourceInfo.origin !== "package" || command.sourceInfo.baseDir === undefined) return false;
    if (hasSymlinkComponent(command.sourceInfo.baseDir, command.sourceInfo.path)) return false;
    const canonicalPath = realpathSync(command.sourceInfo.path);
    const canonicalExpected = realpathSync(expectedPath);
    const canonicalBase = realpathSync(command.sourceInfo.baseDir);
    if (canonicalPath !== canonicalExpected || !inside(canonicalPath, canonicalBase)) return false;
    const manifest = JSON.parse(strictUtf8(resolve(canonicalBase, "package.json"))) as {
      name?: unknown;
      pi?: { extensions?: unknown; skills?: unknown };
    };
    if (manifest.name !== "ca-pi" || manifest.pi === undefined) return false;
    const declared = command.source === "extension" ? manifest.pi.extensions : manifest.pi.skills;
    if (!Array.isArray(declared) || !declared.every((item) => typeof item === "string")) return false;
    return declared.some((item) => {
      const target = resolve(canonicalBase, item as string);
      return command.source === "extension"
        ? realpathSync(target) === canonicalPath
        : inside(canonicalPath, realpathSync(target));
    });
  } catch {
    return false;
  }
}

function fallbackCommand(
  pi: ParentPiPort,
  packageRoot: string,
  entry: CommandCatalogEntry,
): SlashCommand | undefined {
  const expected = resolve(packageRoot, ...entry.skillPath.split("/"));
  const matches = pi.getCommands().filter((command) => command.name === `skill:ca-${entry.name}`);
  if (matches.length !== 1 || matches[0].source !== "skill") return undefined;
  return declaredPackageOwner(matches[0], expected) ? matches[0] : undefined;
}

export function registerAliases(
  pi: ParentPiPort,
  catalog: readonly CommandCatalogEntry[],
  packageRoot = pluginRootFromModule(),
  onDegraded?: (status: string) => void,
  appendGeneratedContent?: (
    entry: CommandCatalogEntry,
    args: string,
    context: ExtensionContextPort,
  ) => Promise<string | undefined>,
): void {
  const canonicalRoot = realpathSync(packageRoot);
  for (const entry of catalog) {
    validatedEntry(entry);
    pi.registerCommand(`ca-${entry.name}`, {
      description: entry.description,
      handler: async (args, context) => {
        try {
          if (assertCommandOwnership(pi, canonicalRoot, [entry]).length > 0) {
            throw new Error(COMMAND_DIAGNOSIS);
          }
          const fallback = fallbackCommand(pi, canonicalRoot, entry);
          if (fallback === undefined) throw new Error(COMMAND_DIAGNOSIS);
          const expectedPath = resolve(canonicalRoot, ...entry.skillPath.split("/"));
          if (fallback.sourceInfo.baseDir === undefined ||
              hasSymlinkComponent(fallback.sourceInfo.baseDir, fallback.sourceInfo.path)) {
            throw new Error(COMMAND_DIAGNOSIS);
          }
          const path = realpathSync(fallback.sourceInfo.path);
          if (path !== realpathSync(expectedPath) ||
              !inside(path, canonicalRoot) ||
              ENVELOPE_UNSAFE.test(path)) throw new Error(COMMAND_DIAGNOSIS);
          if (!lstatSync(path).isFile()) throw new Error(COMMAND_DIAGNOSIS);
          const body = stripStartingFrontmatter(strictUtf8(path));
          if (body.includes("</skill>")) throw new Error(COMMAND_DIAGNOSIS);
          if (ENVELOPE_UNSAFE.test(dirname(path))) throw new Error(COMMAND_DIAGNOSIS);
          const expanded = nativeSkillExpansion(entry.name, path, body, args);
          const generated = await appendGeneratedContent?.(entry, args, context);
          const content = generated === undefined ? expanded : `${expanded}\n\n${generated}`;
          pi.sendUserMessage(content, { deliverAs: "followUp" });
        } catch {
          const status = "codeArbiter host: pi degraded - command surface; run /ca-doctor";
          onDegraded?.(status);
          context.ui.setStatus("codearbiter", status);
          context.ui.notify(COMMAND_DIAGNOSIS, "error");
        }
      },
    });
  }
}

export function assertCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
  catalog: readonly CommandCatalogEntry[],
): Collision[] {
  const collisions: Collision[] = [];
  const canonicalRoot = realpathSync(packageRoot);
  const commands = pi.getCommands();
  for (const entry of catalog) {
    validatedEntry(entry);
    const alias = `ca-${entry.name}`;
    const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
    const exact = commands.filter((command) => command.name === alias);
    const suffixed = commands.filter((command) => command.name.startsWith(`${alias}:`));
    const validExact = exact.filter((command) =>
      command.source === "extension" && declaredPackageOwner(command, expectedExtension));
    if (validExact.length === 0) collisions.push({ command: alias, reason: "missing-alias" });
    if (exact.length > 1 || validExact.length > 1) collisions.push({ command: alias, reason: "duplicate-alias" });
    for (const command of [...exact, ...suffixed]) {
      if (command.source !== "extension" || !declaredPackageOwner(command, expectedExtension)) {
        collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
      }
    }
    for (const command of suffixed) {
      collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
    }
    const fallbackName = `skill:ca-${entry.name}`;
    const fallbacks = commands.filter((command) => command.name === fallbackName);
    const expectedSkill = resolve(canonicalRoot, ...entry.skillPath.split("/"));
    const validFallbacks = fallbacks.filter((command) =>
      command.source === "skill" && declaredPackageOwner(command, expectedSkill));
    if (validFallbacks.length === 0) collisions.push({ command: fallbackName, reason: "missing-fallback" });
    if (fallbacks.length > 1) collisions.push({ command: fallbackName, reason: "duplicate-alias" });
    for (const command of fallbacks) {
      if (command.source !== "skill" || !declaredPackageOwner(command, expectedSkill)) {
        collisions.push({ command: fallbackName, reason: "foreign-owner", owner: command.sourceInfo.path });
      }
    }
    if (validExact.length === 1 && validFallbacks.length === 1 &&
        validExact[0].sourceInfo.source !== validFallbacks[0].sourceInfo.source) {
      collisions.push({
        command: fallbackName,
        reason: "foreign-owner",
        owner: validFallbacks[0].sourceInfo.path,
      });
    }
  }
  return collisions;
}

export function assertNativePlanCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
): Collision[] {
  const canonicalRoot = realpathSync(packageRoot);
  const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
  const commands = pi.getCommands();
  const exact = commands.filter((command) => command.name === "ca-plan");
  const suffixed = commands.filter((command) => command.name.startsWith("ca-plan:"));
  const fallbacks = commands.filter((command) => command.name === "skill:ca-plan");
  const valid = exact.filter((command) => command.source === "extension"
    && declaredPackageOwner(command, expectedExtension));
  const collisions: Collision[] = [];
  if (valid.length === 0) collisions.push({ command: "ca-plan", reason: "missing-alias" });
  if (exact.length > 1 || valid.length > 1) collisions.push({ command: "ca-plan", reason: "duplicate-alias" });
  for (const command of [...exact, ...suffixed, ...fallbacks]) {
    const owned = command.name === "ca-plan" && command.source === "extension"
      && declaredPackageOwner(command, expectedExtension);
    if (!owned) collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
  }
  for (const command of suffixed) {
    collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
  }
  return collisions;
}

export function assertNativeJobsCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
): Collision[] {
  const canonicalRoot = realpathSync(packageRoot);
  const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
  const commands = pi.getCommands();
  const exact = commands.filter((command) => command.name === "ca-jobs");
  const related = commands.filter((command) => command.name.startsWith("ca-jobs:")
    || command.name === "skill:ca-jobs");
  const valid = exact.filter((command) => command.source === "extension"
    && declaredPackageOwner(command, expectedExtension));
  const collisions: Collision[] = [];
  if (valid.length === 0) collisions.push({ command: "ca-jobs", reason: "missing-alias" });
  if (exact.length > 1 || valid.length > 1) collisions.push({ command: "ca-jobs", reason: "duplicate-alias" });
  for (const command of [...exact, ...related]) {
    if (command.name !== "ca-jobs" || command.source !== "extension"
      || !declaredPackageOwner(command, expectedExtension)) {
      collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
    }
  }
  for (const command of related.filter((command) => command.name.startsWith("ca-jobs:"))) {
    collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
  }
  return collisions;
}

const JOBS_SYNTAX = "Usage: /ca-jobs list | tail <id> | cancel <id>.";
const JOB_TOOL_FAILURE = "Background job launch was blocked; run /ca-doctor.";
const JOB_ID = /^[1-9][0-9]{0,15}$/u;

export interface BackgroundJobLaunchConfiguration {
  readonly shellPath: string;
  readonly commandPrefix?: string;
  readonly env: readonly (readonly [string, string | undefined])[];
}

export interface NativeBackgroundControllerOptions {
  readonly packageRoot: string;
  readonly currentLifecycle: () => LifecycleLease | undefined;
  readonly createRuntime: () => BackgroundJobRuntime | undefined;
  readonly resolveLaunch: (cwd: string) => Promise<BackgroundJobLaunchConfiguration | undefined>;
  readonly toolOwnershipValid: () => boolean;
  readonly createAuditLifecycleId?: () => string;
  readonly now?: () => number;
  readonly audit?: (cwd: string, facts: Readonly<Record<string, unknown>>) => Promise<boolean>;
}

export interface NativeBackgroundController {
  register(context: ExtensionContextPort): boolean;
  activate(context: ExtensionContextPort): boolean;
  toolFactory(cwd: string): ToolDefinitionPort;
  stop(reason: BackgroundJobStopReason): Promise<boolean>;
  healthy(): boolean;
}

interface OwnedBackgroundRuntime {
  readonly lease: LifecycleLease;
  readonly sessionId: string;
  readonly cwd: string;
  readonly runtime: BackgroundJobRuntime;
  readonly ui: ExtensionContextPort["ui"];
  readonly watchers: Map<number, Promise<void>>;
  readonly pendingLaunchAudits: Set<Promise<boolean>>;
  readonly trust: () => boolean;
  readonly healthNotice: { sent: boolean };
  readonly auditLifecycleId: string;
  readonly jobAudit: Map<number, Readonly<{
    correlation: string;
    startedAt: number;
    notifyOnCompletion: { value: boolean };
  }>>;
  readonly auditHealthy: { value: boolean };
  readonly reservations: Map<symbol, Readonly<{ done: Promise<void>; release: () => void }>>;
}

function jobSummary(job: Readonly<BackgroundJobSnapshot>): string {
  return `#${job.id} ${job.label} [${job.state}] ${job.status} (${job.outputBytes} bytes)`;
}

function toolFailure(message = JOB_TOOL_FAILURE): Promise<Record<string, unknown>> {
  return Promise.resolve({
    content: [{ type: "text", text: message }],
    details: undefined,
    isError: true,
  });
}

/** Native parent-only background tool and `/ca-jobs`; durable session entries are deliberately absent. */
export function createNativeBackgroundController(
  pi: ParentPiPort,
  options: NativeBackgroundControllerOptions,
): NativeBackgroundController {
  let registered = false;
  let owned: OwnedBackgroundRuntime | undefined;
  let healthy = true;
  const now = options.now ?? Date.now;
  const mintLifecycleAuditId = () => {
    try {
      const value = options.createAuditLifecycleId?.()
        ?? createHash("sha256").update(randomUUID(), "utf8").digest("hex");
      return /^[a-f0-9]{64}$/u.test(value) ? value : undefined;
    } catch { return undefined; }
  };
  const lifecycle = () => {
    try { return options.currentLifecycle(); } catch { return undefined; }
  };
  const ownershipValid = () => {
    try { return assertNativeJobsCommandOwnership(pi, options.packageRoot).length === 0; }
    catch { return false; }
  };
  const affirmativeTrust = (context: Pick<ToolExecutionContextPort, "isProjectTrusted">) => {
    try { return context.isProjectTrusted?.() === true; } catch { return false; }
  };
  const toolOwnershipValid = () => {
    try { return options.toolOwnershipValid() === true; } catch { return false; }
  };
  const authorityCurrent = (value: OwnedBackgroundRuntime, context?: ToolExecutionContextPort | ExtensionContextPort) => {
    if (owned !== value || lifecycle() !== value.lease || !ownershipValid() || !toolOwnershipValid() || !value.trust()) return false;
    if (context === undefined) return true;
    return context.cwd === value.cwd && context.mode === "tui" && context.hasUI === true
      && context.signal?.aborted !== true && affirmativeTrust(context)
      && sessionId(context as ExtensionContextPort) === value.sessionId;
  };
  const runtimeHealthy = (value: OwnedBackgroundRuntime) => {
    try { return value.runtime.health().healthy === true; } catch { return false; }
  };
  const stable = (value: OwnedBackgroundRuntime, context?: ToolExecutionContextPort | ExtensionContextPort) =>
    healthy && value.auditHealthy.value && runtimeHealthy(value) && authorityCurrent(value, context);
  const degrade = (value: OwnedBackgroundRuntime) => {
    healthy = false;
    if (!value.healthNotice.sent && authorityCurrent(value)) {
      value.healthNotice.sent = true;
      value.ui.notify("Background job runtime is unhealthy; run /ca-doctor.", "error");
    }
  };
  const audit = async (value: OwnedBackgroundRuntime, facts: Readonly<Record<string, unknown>>) => {
    if (options.audit === undefined) return true;
    try { return await options.audit(value.cwd, facts) === true; } catch { return false; }
  };
  const reserve = (value: OwnedBackgroundRuntime) => {
    if (value.reservations.size >= MAX_ACTIVE_JOBS) return undefined;
    const token = Symbol("background-job-capacity");
    let resolveDone!: () => void;
    const done = new Promise<void>((resolveReservation) => { resolveDone = resolveReservation; });
    let released = false;
    const reservation = Object.freeze({
      done,
      release: () => {
        if (released) return;
        released = true;
        value.reservations.delete(token);
        resolveDone();
      },
    });
    value.reservations.set(token, reservation);
    return reservation;
  };
  const watchCompletion = (
    value: OwnedBackgroundRuntime,
    id: number,
    reservation: Readonly<{ done: Promise<void>; release: () => void }>,
  ) => {
    if (value.watchers.has(id)) return false;
    const watcher = (async () => {
      try {
        await value.runtime.settled(id);
        const job = value.runtime.getJob(id);
        const jobAudit = value.jobAudit.get(id);
        if (job === undefined || !(["completed", "failed", "cancelled", "timed-out"] as const).includes(job.state as never)
          || jobAudit === undefined || !runtimeHealthy(value)) {
          value.auditHealthy.value = false;
          degrade(value);
          return;
        }
        const exitClass = job.state === "completed" ? "success" : job.state === "failed" ? "failure"
          : job.state === "cancelled" ? "cancelled" : "timeout";
        const durationMs = Math.max(0, Math.min(Number.MAX_SAFE_INTEGER, now() - jobAudit.startedAt));
        const audited = await audit(value, Object.freeze({
          lifecycleId: value.auditLifecycleId, correlation: jobAudit.correlation,
          event: "terminal", id: job.id, state: job.state, exitClass, durationMs, outputBytes: job.outputBytes,
        }));
        if (!audited) {
          value.auditHealthy.value = false;
          degrade(value);
          return;
        }
        if (jobAudit.notifyOnCompletion.value && owned === value && stable(value)) {
          value.ui.notify(`Background job completed: ${jobSummary(job)}`, "info");
        }
      } catch {
        value.auditHealthy.value = false;
        degrade(value);
      } finally {
        value.watchers.delete(id);
        value.jobAudit.delete(id);
        reservation.release();
      }
    })();
    value.watchers.set(id, watcher);
    return true;
  };

  const handle = async (rawArgs: string, context: ExtensionContextPort): Promise<void> => {
    if (!ownershipValid() || typeof rawArgs !== "string" || rawArgs.length > 128 || CONTROL.test(rawArgs)) {
      context.ui.notify(ownershipValid() ? JOBS_SYNTAX : "Pi jobs command ownership changed; operation blocked.", "error");
      return;
    }
    const value = owned;
    if (value !== undefined && (!healthy || !runtimeHealthy(value))) {
      if (!value.healthNotice.sent) degrade(value);
      return;
    }
    if (value === undefined || !stable(value, context)) {
      context.ui.notify(healthy ? "No active Pi background-job session." : JOB_TOOL_FAILURE, healthy ? "info" : "error");
      return;
    }
    const args = rawArgs.trim().split(/\s+/u).filter(Boolean);
    if (args.length === 1 && args[0] === "list") {
      const jobs = value.runtime.listJobs();
      context.ui.notify(jobs.length === 0 ? "No background jobs." : jobs.map(jobSummary).join("\n"), "info");
      return;
    }
    if (args.length === 2 && args[0] === "tail" && JOB_ID.test(args[1]!)) {
      const tail = value.runtime.tail(Number(args[1]));
      context.ui.notify(tail === undefined ? "Background job not found." : tail.replace(/\r\n?/gu, "\n"), tail === undefined ? "warning" : "info");
      return;
    }
    if (args.length === 2 && args[0] === "cancel" && JOB_ID.test(args[1]!)) {
      const id = Number(args[1]);
      const jobAudit = value.jobAudit.get(id);
      if (jobAudit === undefined) {
        const snapshot = value.runtime.getJob(id);
        if (snapshot !== undefined && (["completed", "failed", "cancelled", "timed-out"] as const).includes(snapshot.state as never)) {
          context.ui.notify("Background job could not be cancelled.", "warning");
          return;
        }
        degrade(value);
        return;
      }
      const cancelled = await value.runtime.cancel(id);
      if (!stable(value, context)) {
        context.ui.notify("Pi jobs command ownership changed; operation blocked.", "error"); return;
      }
      const audited = await audit(value, Object.freeze({
        lifecycleId: value.auditLifecycleId, correlation: jobAudit.correlation, event: "cancel", id, accepted: cancelled,
      }));
      if (!audited) { degrade(value); return; }
      if (!stable(value, context)) {
        context.ui.notify("Pi jobs command ownership changed; operation blocked.", "error"); return;
      }
      context.ui.notify(cancelled ? `Background job #${id} cancelled.` : "Background job could not be cancelled.", cancelled ? "info" : "warning");
      return;
    }
    context.ui.notify(JOBS_SYNTAX, "warning");
  };

  return Object.freeze({
    register(context: ExtensionContextPort) {
      if (!interactiveParent(context)) return false;
      if (!registered) {
        pi.registerCommand("ca-jobs", { description: "List, inspect, or cancel session background jobs.", handler: handle });
        registered = true;
      }
      return true;
    },
    activate(context: ExtensionContextPort) {
      const lease = lifecycle();
      const id = sessionId(context);
      if (!healthy || lease === undefined || id === undefined || !interactiveParent(context)
        || !ownershipValid() || !toolOwnershipValid()) return false;
      const auditLifecycleId = mintLifecycleAuditId();
      if (auditLifecycleId === undefined) return false;
      const runtime = options.createRuntime();
      if (runtime === undefined) return false;
      owned = Object.freeze({
        lease, sessionId: id, cwd: context.cwd, runtime, ui: context.ui,
        watchers: new Map<number, Promise<void>>(), pendingLaunchAudits: new Set<Promise<boolean>>(),
        trust: () => affirmativeTrust(context), healthNotice: { sent: false },
        auditLifecycleId, jobAudit: new Map<number, Readonly<{
          correlation: string;
          startedAt: number;
          notifyOnCompletion: { value: boolean };
        }>>(),
        auditHealthy: { value: true },
        reservations: new Map<symbol, Readonly<{ done: Promise<void>; release: () => void }>>(),
      });
      return true;
    },
    toolFactory(cwd: string): ToolDefinitionPort {
      return {
        name: "codearbiter_background_bash",
        label: "codeArbiter background bash",
        description: "Start a governed shell command as a bounded session-local background job.",
        parameters: {
          type: "object",
          additionalProperties: false,
          required: ["command", "label"],
          properties: {
            command: { type: "string" },
            label: { type: "string" },
            timeoutMs: { type: "number" },
          },
        },
        execute: async (_toolCallId, params, signal, _onUpdate, context) => {
          const currentToolSignal = () => signal;
          const value = owned;
          if (value !== undefined && !runtimeHealthy(value)) degrade(value);
          if (value === undefined || cwd !== value.cwd || context === undefined || !stable(value, context)
            || currentToolSignal()?.aborted === true || Object.keys(params).some((key) => !["command", "label", "timeoutMs"].includes(key))
            || typeof params.command !== "string" || typeof params.label !== "string"
            || (params.timeoutMs !== undefined && typeof params.timeoutMs !== "number")) return await toolFailure();
          const reservation = reserve(value);
          if (reservation === undefined) return await toolFailure("Background job capacity is full.");
          let transferred = false;
          try {
          const frozen = Object.freeze({
            command: params.command,
            label: params.label,
            ...(params.timeoutMs === undefined ? {} : { timeoutMs: params.timeoutMs }),
          });
          const launch = await options.resolveLaunch(value.cwd);
          if (!stable(value, context) || launch === undefined || currentToolSignal()?.aborted === true) return await toolFailure();
          const startedAt = now();
          const job = await value.runtime.launch({
            authorization: {
              lease: value.lease,
              isCurrent: (candidate) => candidate === value.lease
                && stable(value, context) && currentToolSignal()?.aborted !== true,
            },
            ...frozen,
            cwd: value.cwd,
            env: launch.env,
            shellPath: launch.shellPath,
            ...(launch.commandPrefix === undefined ? {} : { commandPrefix: launch.commandPrefix }),
          });
          if (job === undefined) {
            if (!runtimeHealthy(value)) degrade(value);
            return await toolFailure(value.runtime.health().diagnostic);
          }
          if (!(stable(value, context) && currentToolSignal()?.aborted !== true)) {
            await value.runtime.cancel(job.id);
            return await toolFailure();
          }
          if (value.jobAudit.has(job.id) || value.watchers.has(job.id)) {
            await value.runtime.cancel(job.id);
            degrade(value);
            return await toolFailure("Background job identity was reused; run /ca-doctor.");
          }
          const correlation = createHash("sha256").update(`${value.auditLifecycleId}:${job.id}`, "utf8").digest("hex");
          const jobAudit = Object.freeze({ correlation, startedAt, notifyOnCompletion: { value: true } });
          value.jobAudit.set(job.id, jobAudit);
          const launchAudit = (async () => {
            const appended = await audit(value, Object.freeze({
              lifecycleId: value.auditLifecycleId, correlation,
              event: "launch", id: job.id, state: job.state, timeoutMs: job.timeoutMs,
            }));
            if (appended) {
              if (currentToolSignal()?.aborted === true) jobAudit.notifyOnCompletion.value = false;
              transferred = watchCompletion(value, job.id, reservation);
            }
            return appended;
          })();
          value.pendingLaunchAudits.add(launchAudit);
          void launchAudit.finally(() => value.pendingLaunchAudits.delete(launchAudit));
          if (!await launchAudit) {
            await value.runtime.cancel(job.id);
            value.jobAudit.delete(job.id);
            degrade(value);
            return await toolFailure("Background job audit is unavailable; launch cancelled; run /ca-doctor.");
          }
          if (!(stable(value, context) && currentToolSignal()?.aborted !== true)) {
            jobAudit.notifyOnCompletion.value = false;
            await value.runtime.cancel(job.id);
            return await toolFailure();
          }
          return {
            content: [{ type: "text", text: `Background job started: ${jobSummary(job)}` }],
            details: { id: job.id, label: job.label, state: job.state, status: job.status, outputBytes: job.outputBytes },
            isError: false,
          };
          } finally {
            if (!transferred) reservation.release();
          }
        },
      };
    },
    async stop(reason: BackgroundJobStopReason) {
      const value = owned;
      owned = undefined;
      if (value === undefined) return healthy;
      const stopped = await value.runtime.stop(reason);
      await Promise.all([...value.pendingLaunchAudits]);
      await Promise.all([...value.watchers.values()]);
      await Promise.all([...value.reservations.values()].map((reservation) => reservation.done));
      const disposed = stopped && await value.runtime.dispose();
      if (!stopped || !disposed || !runtimeHealthy(value) || !value.auditHealthy.value || !healthy) {
        healthy = false;
        if (!value.healthNotice.sent) {
          value.healthNotice.sent = true;
          value.ui.notify("Background job runtime is unhealthy; run /ca-doctor.", "error");
        }
      }
      return healthy;
    },
    healthy: () => healthy && (owned === undefined || owned.auditHealthy.value && runtimeHealthy(owned)),
  });
}

interface NativePlanPiPort extends ParentPiPort {}

export interface NativePlanControllerOptions {
  readonly descriptor: Readonly<Record<string, unknown>>;
  readonly packageRoot: string;
  readonly bridge: BridgePort;
  readonly currentLifecycle: () => LifecycleLease | undefined;
  readonly appendEntry: (customType: string, data: unknown) => void;
  readonly confirmationTimeoutMs?: number;
}

export interface NativePlanController {
  register(context: ExtensionContextPort): boolean;
  restore(context: ExtensionContextPort): Promise<void>;
  clear(): void;
  mode(): PolicyMode;
  status(): PlanSessionState | undefined;
}

interface OwnedPlanState {
  readonly lease: LifecycleLease;
  readonly sessionId: string;
  readonly cwd: string;
  readonly state: PlanSessionState;
}

function interactiveParent(context: ExtensionContextPort): boolean {
  try {
    return context.mode === "tui" && context.hasUI === true && context.isProjectTrusted?.() === true;
  } catch {
    return false;
  }
}

function sessionId(context: ExtensionContextPort): string | undefined {
  try {
    const value = context.sessionManager?.getSessionId?.();
    return typeof value === "string" && value.length > 0 && value.length <= 256 && !CONTROL.test(value)
      ? value
      : undefined;
  } catch {
    return undefined;
  }
}

function entryRecord(value: unknown): Readonly<Record<string, unknown>> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return undefined;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Object.values(descriptors).some((descriptor) => !("value" in descriptor))) return undefined;
  return Object.fromEntries((keys as string[]).map((key) => [key, descriptors[key]!.value]));
}

function latestPlanEntryState(entries: unknown): PlanSessionState | undefined {
  if (!Array.isArray(entries) || utilTypes.isProxy(entries) || entries.length > PLAN_ENTRY_LIMIT) return undefined;
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    if (!(index in entries)) return undefined;
    const record = entryRecord(entries[index]);
    if (record === undefined) return undefined;
    if (record.type !== "custom" || record.customType !== PLAN_SESSION_ENTRY_TYPE) continue;
    if (Object.keys(record).sort().join(",") !== "customType,data,id,parentId,timestamp,type") return undefined;
    return encodePlanSessionState(record.data as PlanSessionState);
  }
  return undefined;
}

async function readReconciledPlan(
  state: PlanSessionState,
  cwd: string,
  bridge: BridgePort,
  signal: AbortSignal | undefined,
): Promise<Readonly<{ content: string; hash: string; state: PlanSessionState }> | undefined> {
  const response = await callPlanFileBridge(bridge, cwd, {
    slug: state.activePlan.slug,
    kind: "plan",
    action: "read",
  }, signal ?? new AbortController().signal);
  if (response === undefined || response.status !== "unchanged" || !response.exists || response.hash === null
    || createHash("sha256").update(response.content, "utf8").digest("hex") !== response.hash) return undefined;
  const reconciled = reconcilePlanState(state, response.content);
  return reconciled === undefined ? undefined : Object.freeze({
    content: response.content,
    hash: response.hash,
    state: reconciled,
  });
}

function taskStatusMessage(state: PlanSessionState): string {
  let pending = 0;
  let inProgress = 0;
  let accepted = 0;
  for (const task of state.activePlan.tasks) {
    if (task.status === "PENDING") pending += 1;
    else if (task.status === "IN_PROGRESS") inProgress += 1;
    else accepted += 1;
  }
  const prefix = state.mode === "plan"
    ? "Plan mode active."
    : state.activePlan.disposition === "approved"
      ? "Execute mode active with an approved plan."
      : "Execute mode active with a preserved draft.";
  return `${prefix} Tasks: ${pending} pending, ${inProgress} in progress, ${accepted} accepted.`;
}

async function boundedConfirmation(
  context: ExtensionContextPort,
  timeoutMs: number,
): Promise<boolean> {
  if (context.signal?.aborted === true || typeof context.ui.confirm !== "function") return false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let abortListener: (() => void) | undefined;
  try {
    const timeout = new Promise<false>((resolveTimeout) => {
      timer = setTimeout(() => resolveTimeout(false), timeoutMs);
    });
    const aborted = new Promise<false>((resolveAbort) => {
      if (context.signal === undefined) return;
      abortListener = () => resolveAbort(false);
      context.signal.addEventListener("abort", abortListener, { once: true });
    });
    const confirmed = context.ui.confirm(
      "Approve codeArbiter plan?",
      "Approve this governed plan and return this session to execute mode?",
      { timeout: timeoutMs, ...(context.signal === undefined ? {} : { signal: context.signal }) },
    );
    return await Promise.race([confirmed, timeout, aborted]) === true;
  } catch {
    return false;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    if (abortListener !== undefined) context.signal?.removeEventListener("abort", abortListener);
  }
}

/** Descriptor-owned native `/ca-plan`; no generated skill fallback participates. */
export function createNativePlanController(
  pi: NativePlanPiPort,
  options: NativePlanControllerOptions,
): NativePlanController {
  const descriptor = options.descriptor;
  const descriptorFields = descriptor === null || typeof descriptor !== "object" || utilTypes.isProxy(descriptor)
    || Object.getPrototypeOf(descriptor) !== Object.prototype
    ? undefined
    : Object.getOwnPropertyDescriptors(descriptor);
  if (descriptorFields === undefined || descriptorFields["ca-plan"]?.value !== "planning-write"
    || !("value" in descriptorFields["ca-plan"]) || descriptorFields["skill:ca-plan"] !== undefined) {
    throw new Error(PLAN_COMMAND_DIAGNOSIS);
  }
  const timeoutMs = Number.isSafeInteger(options.confirmationTimeoutMs)
    && options.confirmationTimeoutMs! > 0 && options.confirmationTimeoutMs! <= 60_000
    ? options.confirmationTimeoutMs!
    : 60_000;
  let registered = false;
  let owned: OwnedPlanState | undefined;
  const ownershipValid = (): boolean => {
    try {
      return assertNativePlanCommandOwnership(pi, options.packageRoot).length === 0;
    } catch {
      return false;
    }
  };
  const lifecycle = (): LifecycleLease | undefined => {
    try { return options.currentLifecycle(); } catch { return undefined; }
  };

  const clear = () => { owned = undefined; };
  const currentOwned = (): OwnedPlanState | undefined => {
    if (owned === undefined || lifecycle() !== owned.lease) return undefined;
    return owned;
  };
  const ownerFor = (context: ExtensionContextPort): OwnedPlanState | undefined => {
    const value = currentOwned();
    return value !== undefined && interactiveParent(context) && context.cwd === value.cwd
      && sessionId(context) === value.sessionId && context.signal?.aborted !== true
      ? value
      : undefined;
  };
  const baseOwner = (context: ExtensionContextPort): Readonly<{
    lease: LifecycleLease; sessionId: string; cwd: string;
  }> | undefined => {
    const lease = lifecycle();
    const id = sessionId(context);
    return lease !== undefined && id !== undefined && interactiveParent(context)
      && context.signal?.aborted !== true
      ? Object.freeze({ lease, sessionId: id, cwd: context.cwd })
      : undefined;
  };
  const stable = (base: Readonly<{ lease: LifecycleLease; sessionId: string; cwd: string }>, context: ExtensionContextPort) =>
    lifecycle() === base.lease && sessionId(context) === base.sessionId
      && context.cwd === base.cwd && interactiveParent(context) && context.signal?.aborted !== true;
  const persist = (base: Readonly<{ lease: LifecycleLease; sessionId: string; cwd: string }>, state: PlanSessionState) => {
    const encoded = encodePlanSessionState(state);
    if (encoded === undefined) return false;
    try {
      options.appendEntry(PLAN_SESSION_ENTRY_TYPE, encoded);
      return true;
    } catch {
      return false;
    }
  };

  const handle = async (rawArgs: string, context: ExtensionContextPort): Promise<void> => {
    if (!ownershipValid()) {
      context.ui.notify("Pi plan command ownership changed; operation blocked.", "error");
      return;
    }
    if (typeof rawArgs !== "string" || rawArgs.length > 512 || CONTROL.test(rawArgs)) {
      context.ui.notify(PLAN_SYNTAX, "warning");
      return;
    }
    const args = rawArgs.trim().split(/\s+/u).filter(Boolean);
    const action = args[0];
    if (action === "enter" && args.length === 2 && PLAN_SLUG.test(args[1]!)) {
      if (currentOwned() !== undefined && ownerFor(context) === undefined) {
        context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
      }
      const base = baseOwner(context);
      if (base === undefined) { context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return; }
      const response = await callPlanFileBridge(options.bridge, base.cwd, {
        slug: args[1]!, kind: "plan", action: "read",
      }, context.signal ?? new AbortController().signal);
      if (!ownershipValid() || !stable(base, context) || response === undefined
        || response.status !== "unchanged" || !response.exists
        || response.hash === null || createHash("sha256").update(response.content, "utf8").digest("hex") !== response.hash) {
        context.ui.notify(ownershipValid()
          ? PLAN_COMMAND_DIAGNOSIS
          : "Pi plan command ownership changed; operation blocked.", "error"); return;
      }
      const state = enterPlan(args[1], response.content);
      if (state === undefined || !stable(base, context) || !ownershipValid()
        || !persist(base, state) || !stable(base, context) || !ownershipValid()) {
        context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
      }
      owned = Object.freeze({ ...base, state });
      context.ui.notify(taskStatusMessage(state), "info");
      return;
    }
    if (action === "status" && args.length === 1) {
      const value = ownerFor(context);
      if (value === undefined) { context.ui.notify("No active Pi plan session.", "info"); return; }
      const disk = await readReconciledPlan(value.state, value.cwd, options.bridge, context.signal);
      if (!ownershipValid()) {
        context.ui.notify("Pi plan command ownership changed; operation blocked.", "error");
        return;
      }
      if (disk === undefined || ownerFor(context) !== value) {
        clear();
        context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error");
        return;
      }
      owned = Object.freeze({ ...value, state: disk.state });
      context.ui.notify(taskStatusMessage(disk.state), "info");
      return;
    }
    if ((action === "approve" || action === "cancel") && args.length === 1) {
      const value = ownerFor(context);
      if (value === undefined || value.state.mode !== "plan") {
        context.ui.notify("No active plan mode session.", "warning"); return;
      }
      let currentState = value.state;
      let approvedSnapshot: Readonly<{ content: string; hash: string; state: PlanSessionState }> | undefined;
      if (action === "approve") {
        const disk = await readReconciledPlan(value.state, value.cwd, options.bridge, context.signal);
        if (!ownershipValid()) {
          context.ui.notify("Pi plan command ownership changed; operation blocked.", "error"); return;
        }
        if (disk === undefined || ownerFor(context) !== value) {
          context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
        }
        approvedSnapshot = disk;
        currentState = disk.state;
        const confirmed = await boundedConfirmation(context, timeoutMs);
        if (!ownershipValid()) {
          context.ui.notify("Pi plan command ownership changed; operation blocked.", "error"); return;
        }
        if (ownerFor(context) !== value) {
          context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
        }
        if (!confirmed) {
          context.ui.notify("Plan approval cancelled; plan mode remains active.", "warning"); return;
        }
        const observed = await readReconciledPlan(currentState, value.cwd, options.bridge, context.signal);
        if (!ownershipValid()) {
          context.ui.notify("Pi plan command ownership changed; operation blocked.", "error"); return;
        }
        if (observed === undefined || ownerFor(context) !== value
          || observed.hash !== approvedSnapshot.hash || observed.content !== approvedSnapshot.content) {
          context.ui.notify("Pi plan approval became stale; plan mode remains active.", "warning"); return;
        }
        currentState = observed.state;
      }
      if (ownerFor(context) !== value) {
        context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
      }
      const next = action === "approve" ? approvePlan(currentState) : cancelPlan(currentState);
      if (next === undefined || !ownershipValid() || ownerFor(context) !== value
        || !persist(value, next) || ownerFor(context) !== value || !ownershipValid()) {
        context.ui.notify(PLAN_COMMAND_DIAGNOSIS, "error"); return;
      }
      owned = Object.freeze({ ...value, state: next });
      context.ui.notify(action === "approve"
        ? "Plan approved. Execute mode active."
        : "Plan draft preserved. Execute mode active.", "info");
      return;
    }
    context.ui.notify(PLAN_SYNTAX, "warning");
  };

  return Object.freeze({
    register(context: ExtensionContextPort) {
      if (!interactiveParent(context)) return false;
      if (!registered) {
        try {
          pi.registerCommand("ca-plan", {
            description: "Manage the current governed Pi plan session.",
            handler: handle,
          });
        } catch (error) {
          throw new Error(PLAN_COMMAND_DIAGNOSIS, { cause: error });
        }
        registered = true;
      }
      return true;
    },
    async restore(context: ExtensionContextPort) {
      clear();
      if (!ownershipValid()) return;
      const base = baseOwner(context);
      if (base === undefined) return;
      let entries: unknown;
      try { entries = context.sessionManager?.getEntries?.(); } catch { return; }
      const candidate = latestPlanEntryState(entries);
      if (candidate === undefined) return;
      const disk = await readReconciledPlan(candidate, base.cwd, options.bridge, context.signal);
      if (disk === undefined || !ownershipValid() || !stable(base, context)) return;
      const restored = restorePlanSessionState(entries, disk.content);
      if (restored === undefined || !stable(base, context)) return;
      owned = Object.freeze({ ...base, state: restored });
    },
    clear,
    mode() { return currentOwned()?.state.mode ?? "execute"; },
    status() { return currentOwned()?.state; },
  });
}
