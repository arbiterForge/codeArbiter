/**
 * native-plan.ts - the native `/ca-plan` controller and its session plan lifecycle.
 *
 * The controller owns one plan session per interactive parent session: entering a plan from a
 * bridge-read plan file, reconciling the in-session state against what is on disk, confirming an
 * approval, and restoring a plan session from durable session entries. Like the jobs controller it
 * re-checks lease, session, cwd, trust, and command ownership around every await, and it is
 * descriptor-owned - no generated skill fallback participates.
 */
import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import type {
  BridgePort,
  ExtensionContextPort,
  LifecycleLease,
  ParentPiPort,
} from "./contracts.ts";
import { callPlanFileBridge } from "./bridge.ts";
import { assertNativePlanCommandOwnership } from "./command-ownership.ts";
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
import { CONTROL_CHARACTERS, interactiveParent, sessionId } from "./session-identity.ts";

const PLAN_COMMAND_DIAGNOSIS = "codeArbiter could not validate the Pi plan command; run /ca-doctor.";
const PLAN_SYNTAX = "Usage: /ca-plan enter <slug> | status | approve | cancel.";
const PLAN_SLUG = /^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/u;
const PLAN_ENTRY_LIMIT = 4_096;

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
    if (typeof rawArgs !== "string" || rawArgs.length > 512 || CONTROL_CHARACTERS.test(rawArgs)) {
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
