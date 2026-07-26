/**
 * native-background.ts - the native parent-only background-job tool and `/ca-jobs` controller.
 *
 * The controller owns one background-job runtime per interactive parent session and holds the
 * lifecycle state that goes with it: capacity reservations, per-job audit correlation, completion
 * watchers, health degradation, and teardown. Every operation re-checks that the lease, session,
 * cwd, trust, and command ownership behind it are still the ones it was created for; durable
 * session entries are deliberately absent.
 */
import { createHash, randomUUID } from "node:crypto";

import type {
  ExtensionContextPort,
  LifecycleLease,
  ParentPiPort,
  ToolDefinitionPort,
  ToolExecutionContextPort,
} from "./contracts.ts";
import type {
  BackgroundJobRuntime,
  BackgroundJobSnapshot,
  BackgroundJobStopReason,
} from "./background-jobs.ts";
import { MAX_ACTIVE_JOBS } from "./background-jobs.ts";
import { assertNativeJobsCommandOwnership } from "./command-ownership.ts";
import { CONTROL_CHARACTERS, interactiveParent, sessionId } from "./session-identity.ts";

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
    if (!ownershipValid() || typeof rawArgs !== "string" || rawArgs.length > 128 || CONTROL_CHARACTERS.test(rawArgs)) {
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
          // #504: four of the five refusal paths are policy decisions this caller can predict;
          // the fifth is a spawn failure it cannot. Capture that one per launch so a real
          // environment failure reaches the operator instead of the generic block message.
          let spawnRefusal: string | undefined;
          const job = await value.runtime.launch({
            authorization: {
              lease: value.lease,
              isCurrent: (candidate) => candidate === value.lease
                && stable(value, context) && currentToolSignal()?.aborted !== true,
            },
            ...frozen,
            cwd: value.cwd,
            env: launch.env,
            onRefusal: (diagnostic) => { spawnRefusal = diagnostic; },
            shellPath: launch.shellPath,
            ...(launch.commandPrefix === undefined ? {} : { commandPrefix: launch.commandPrefix }),
          });
          if (job === undefined) {
            if (!runtimeHealthy(value)) degrade(value);
            return await toolFailure(value.runtime.health().diagnostic ?? spawnRefusal);
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
