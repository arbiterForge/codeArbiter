/** extension.ts - codeArbiter's dormant Pi parent entrypoint and compatibility guard. */
import { lstat, readFile, realpath } from "node:fs/promises";
import { realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { delimiter, dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { types as utilTypes } from "node:util";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { compatibilityDirection } from "./compatibility.ts";
import type { HostCompatibility } from "./compatibility.ts";
import { BridgeClient, resolveGitExecutable, resolvePythonCommand } from "./bridge.ts";
import type {
  BridgePort,
  BuiltinToolFactories,
  CommandCatalogEntry,
  ExtensionContextPort,
  LifecycleLease,
  ParentPiPort,
  ToolCategory,
  ToolDefinitionPort,
  ToolExecutionContextPort,
  ToolGuardPiPort,
  ToolResultPiPort,
} from "./contracts.ts";
import { isEnabled, readCachedUpdateVersion } from "./activation.ts";
import {
  assertCommandOwnership,
  assertNativeJobsCommandOwnership,
  assertNativePlanCommandOwnership,
  createNativeBackgroundController,
  createNativePlanController,
  registerAliases,
} from "./commands.ts";
import type { NativeBackgroundController } from "./commands.ts";
import { createBackgroundJobRuntime, MAX_JOB_ENV_ENTRIES } from "./background-jobs.ts";
import { createSessionActivityRegistry } from "./activity.ts";
import type { ActivityPublisher, SessionActivityRegistry } from "./activity.ts";
import { loadPiRuntime, resolvePiRuntimeIdentity } from "./runtime-resolver.ts";
import type { ResolvedPiRuntime } from "./runtime-resolver.ts";
import { PiFooterLifecycle, setArbiterStatus } from "./status.ts";
import type { FooterTextMetrics } from "./footer.ts";
import type { PolicyMode } from "./policy.ts";
import {
  EnforcementInstaller,
  appendBackgroundJobAudit,
  appendPermissionAudit,
  compileBuiltinPermissionPolicy,
} from "./tool-guard.ts";
import type { EnforcementReadinessPort } from "./tool-guard.ts";
import { collectPiDoctorInput, diagnosePi, formatPiDoctorReport, runPiWrapperSelfTest } from "./doctor.ts";
import { safeDiagnostic } from "./redaction.ts";
import { createDispatchTool } from "./dispatch.ts";
import type { DispatchRequest, DispatchResult } from "./dispatch.ts";
import { createFarmPreviewTool } from "./farm.ts";
import type { FarmPreviewInput, FarmResult } from "./farm.ts";
import {
  appendPiCompactionAudit,
  createPiCompactionRunner,
  installPiCompaction,
} from "./compaction.ts";

declare const __CODEARBITER_PI_TOOL_CLASSES__: unknown;
declare const __CODEARBITER_PI_PERMISSION_POLICY_SURFACES__: unknown;
declare const __CODEARBITER_PI_SKILL_EXPANSION_FINGERPRINTS__: unknown;
declare const __CODEARBITER_PI_CHILD_SHA256__: string;

export { compatibilityDirection } from "./compatibility.ts";
export { diagnosePi, formatPiDoctorReport, runPiWrapperSelfTest } from "./doctor.ts";
export { PI_RUNTIME_DIAGNOSIS, resolvePiRuntime } from "./runtime-resolver.ts";

export interface ParentDependencies {
  bridge: BridgePort;
  catalog: readonly CommandCatalogEntry[];
  packageRoot: string;
  loadPersona: () => Promise<string>;
  readActivation?: (cwd: string) => Promise<boolean>;
  resetBridge?: () => void;
  prepareFooterBridge?: (cwd: string, context: ExtensionContextPort) => Promise<void> | void;
  prepareBridge?: (cwd: string, context: ExtensionContextPort) => Promise<void> | void;
  readFooterUpdateVersion?: () => Promise<string | undefined>;
  loadFooterMetrics?: () => Promise<FooterTextMetrics>;
  footerMetrics?: FooterTextMetrics;
  installEnforcement?: (
    cwd: string,
    context: ExtensionContextPort,
    getMode: () => PolicyMode,
    backgroundToolFactory?: (cwd: string) => ToolDefinitionPort,
  ) => Promise<void> | void;
  enforcementReadiness?: EnforcementReadinessPort;
  doctorReport?: (
    context: ExtensionContextPort,
    health: Readonly<{
      footer: Readonly<{ expected: boolean; initialized: boolean }>;
      background: Readonly<{ expected: boolean; initialized: boolean; healthy: boolean }>;
    }>,
  ) => Promise<string>;
  installDispatch?: (
    currentLifecycle: () => LifecycleLease | undefined,
    currentActivity: () => ActivityPublisher | undefined,
  ) => void;
  installCompaction?: (currentLifecycle: () => LifecycleLease | undefined) => void;
  installFarmPreview?: (currentLifecycle: () => LifecycleLease | undefined) => void;
  planCommandDescriptor?: Readonly<Record<string, unknown>>;
  appendPlanEntry?: (customType: string, data: unknown) => void;
  installBackground?: (
    currentLifecycle: () => LifecycleLease | undefined,
    currentActivity: () => ActivityPublisher | undefined,
  ) => NativeBackgroundController;
}

const PI_TRUST_REQUIRED_STATUS = "codeArbiter host: pi waiting for project trust - run /trust in Pi, approve this project, then start a new session";

function hasAffirmativeProjectTrust(context: { isProjectTrusted?: () => boolean }): boolean {
  try {
    return context.isProjectTrusted?.() === true;
  } catch {
    return false;
  }
}

interface PiDispatchTarget {
  registerTool(tool: ToolDefinitionPort): void;
}

interface PiDispatchInstallOptions {
  packageRoot: string;
  piCliPath: string;
  currentLifecycle?: () => LifecycleLease | undefined;
  isLifecycleReady?: () => boolean;
  dispatch?: (request: DispatchRequest, signal: AbortSignal) => Promise<DispatchResult>;
  currentActivity?: () => ActivityPublisher | undefined;
}

export function installPiDispatch(pi: PiDispatchTarget, options: PiDispatchInstallOptions): void {
  const legacyLease = Object.freeze({});
  const currentLifecycle = () => options.currentLifecycle?.()
    ?? (options.isLifecycleReady?.() === true ? legacyLease : undefined);
  pi.registerTool(createDispatchTool({
    authorize: async (context) => {
      const lease = currentLifecycle();
      if (lease === undefined || !hasAffirmativeProjectTrust(context) || typeof context.cwd !== "string") return undefined;
      try {
        if (!await isEnabled(context.cwd) || currentLifecycle() !== lease) return undefined;
        return { lease, isCurrent: (candidate) => currentLifecycle() === candidate };
      } catch { return undefined; }
    },
    resolveRuntime: (context: ToolExecutionContextPort) => {
      if (typeof context.cwd !== "string"
        || typeof context.model?.provider !== "string" || context.model.provider.trim() === ""
        || typeof context.model.id !== "string" || context.model.id.trim() === "") {
        throw new Error("Pi dispatch runtime context is unavailable.");
      }
      return {
        nodePath: process.execPath,
        piCliPath: options.piCliPath,
        provider: context.model.provider,
        model: context.model.id,
        cwd: context.cwd,
        packageRoot: options.packageRoot,
        childExtensionPath: resolve(options.packageRoot, "extensions", "codearbiter-child.js"),
        parentEnv: process.env,
        platform: process.platform,
      };
    },
    ...(options.currentActivity === undefined ? {} : { activity: options.currentActivity }),
    ...(options.dispatch === undefined ? {} : { dispatch: options.dispatch }),
  }));
}

interface PiFarmPreviewInstallOptions {
  packageRoot: string;
  nodePath: string;
  environment: Readonly<NodeJS.ProcessEnv>;
  currentLifecycle?: () => LifecycleLease | undefined;
  isLifecycleReady?: () => boolean;
  run?: (input: FarmPreviewInput, signal: AbortSignal) => Promise<FarmResult>;
}

export function installPiFarmPreview(pi: PiDispatchTarget, options: PiFarmPreviewInstallOptions): void {
  const legacyLease = Object.freeze({});
  const currentLifecycle = () => options.currentLifecycle?.()
    ?? (options.isLifecycleReady?.() === true ? legacyLease : undefined);
  pi.registerTool(createFarmPreviewTool({
    packageRoot: options.packageRoot,
    nodePath: options.nodePath,
    environment: options.environment,
    authorize: async (context) => {
      const lease = currentLifecycle();
      if (lease === undefined || !hasAffirmativeProjectTrust(context) || typeof context.cwd !== "string") return undefined;
      try {
        if (!await isEnabled(context.cwd) || currentLifecycle() !== lease) return undefined;
        return { lease, isCurrent: (candidate) => currentLifecycle() === candidate };
      } catch { return undefined; }
    },
    ...(options.run === undefined ? {} : { run: options.run }),
  }));
}

const neverAborted = new AbortController().signal;

function appendPrompt(current: string, persona: string, state: string): string {
  return [current, persona, state].filter((part) => part.length > 0).join("\n\n");
}

const MAX_OS_ENV_VALUE_BYTES = 32_768;

export function boundedPiEnvironment(
  environment: Readonly<NodeJS.ProcessEnv>,
): readonly (readonly [string, string | undefined])[] | undefined {
  try {
    if (environment === null || typeof environment !== "object" || utilTypes.isProxy(environment)) return undefined;
    const names = Object.keys(environment);
    if (names.length > MAX_JOB_ENV_ENTRIES) return undefined;
    const entries: Array<readonly [string, string | undefined]> = [];
    for (const name of names) {
      const value = environment[name];
      if (name.length === 0 || name.length > 256 || /[=\u0000]/u.test(name)
        || (value !== undefined && (typeof value !== "string"
          || Buffer.byteLength(value, "utf8") > MAX_OS_ENV_VALUE_BYTES || value.includes("\0")))) return undefined;
      entries.push(Object.freeze([name, value] as const));
    }
    return Object.freeze(entries);
  } catch { return undefined; }
}

async function canonicalExecutable(candidate: string): Promise<string | undefined> {
  try {
    const canonical = await realpath(candidate);
    const stats = await lstat(canonical);
    return isAbsolute(canonical) && stats.isFile() && !stats.isSymbolicLink() ? canonical : undefined;
  } catch { return undefined; }
}

/** Resolves Pi's configured/default bash selection to the absolute identity T12 requires. */
export async function resolvePiBackgroundShell(
  configured: string | undefined,
  environment: Readonly<NodeJS.ProcessEnv> = process.env,
  platform: NodeJS.Platform = process.platform,
): Promise<string | undefined> {
  if (configured !== undefined) {
    if (typeof configured !== "string" || configured.length === 0 || configured.length > 4_096 || configured.includes("\0")) return undefined;
    return await canonicalExecutable(isAbsolute(configured) ? configured : resolve(configured));
  }
  const candidates: string[] = [];
  const pathDirectories: string[] = [];
  if (platform === "win32") {
    for (const key of ["ProgramFiles", "ProgramFiles(x86)"] as const) {
      const root = environment[key];
      if (typeof root === "string" && root.length <= 4_096) candidates.push(resolve(root, "Git", "bin", "bash.exe"));
    }
  } else {
    candidates.push("/bin/bash");
  }
  const pathValue = environment[Object.keys(environment).find((key) => key.toLowerCase() === "path") ?? "PATH"];
  if (typeof pathValue === "string" && pathValue.length <= 32_768) {
    const executable = platform === "win32" ? "bash.exe" : "bash";
    for (const directory of pathValue.split(delimiter).slice(0, 512)) {
      if (directory.length > 0 && directory.length <= 4_096) {
        pathDirectories.push(directory);
        candidates.push(resolve(directory, executable));
      }
    }
  }
  for (const candidate of candidates) {
    const canonical = await canonicalExecutable(candidate);
    if (canonical !== undefined) return canonical;
  }
  if (platform !== "win32") {
    for (const directory of pathDirectories) {
      const canonical = await canonicalExecutable(resolve(directory, "sh"));
      if (canonical !== undefined) return canonical;
    }
    return await canonicalExecutable("/bin/sh");
  }
  return undefined;
}

function ownershipStatus(
  pi: ParentPiPort,
  dependencies: ParentDependencies,
  nativePlanRegistered = false,
  nativeJobsRegistered = false,
): string | undefined {
  const collisions = assertCommandOwnership(pi, dependencies.packageRoot, dependencies.catalog);
  if (collisions.length > 0) {
    return `codeArbiter host: pi degraded - ${collisions.length} command ownership conflict(s); run /ca-doctor`;
  }
  const native = nativePlanRegistered ? assertNativePlanCommandOwnership(pi, dependencies.packageRoot) : [];
  const jobs = nativeJobsRegistered ? assertNativeJobsCommandOwnership(pi, dependencies.packageRoot) : [];
  if (native.length === 0 && jobs.length === 0) return undefined;
  if (jobs.length === 0) {
    return `codeArbiter host: pi degraded - ${native.length} native plan command ownership conflict(s); operations blocked`;
  }
  return `codeArbiter host: pi degraded - ${native.length + jobs.length} native command ownership conflict(s); operations blocked`;
}

export function installParent(pi: ParentPiPort, dependencies: ParentDependencies): void {
  let enabled = false;
  let persona = "";
  let state = "";
  let ownershipDegraded: string | undefined;
  let bridgeDegraded: string | undefined;
  let commandInvocationDegraded: string | undefined;
  let statusPublished = false;
  let footerActivationEnabled = false;
  let lifecycleSequence = 0;
  let activeLifecycle: LifecycleLease | undefined;
  let readyLifecycle: LifecycleLease | undefined;
  let nativePlanRegistered = false;
  let nativeJobsRegistered = false;
  let activity: SessionActivityRegistry | undefined;
  const plan = dependencies.planCommandDescriptor === undefined || dependencies.appendPlanEntry === undefined
    ? undefined
    : createNativePlanController(pi, {
      descriptor: dependencies.planCommandDescriptor,
      packageRoot: dependencies.packageRoot,
      bridge: dependencies.bridge,
      currentLifecycle: () => readyLifecycle,
      appendEntry: dependencies.appendPlanEntry,
    });
  const currentActivity = () => activity;
  const background = dependencies.installBackground?.(() => readyLifecycle, currentActivity);
  const loadFooterMetrics = dependencies.loadFooterMetrics
    ?? (dependencies.footerMetrics === undefined ? undefined : async () => dependencies.footerMetrics!);
  const footer = new PiFooterLifecycle(pi, dependencies.bridge, loadFooterMetrics, currentActivity);
  const readActivation = dependencies.readActivation ?? isEnabled;
  dependencies.installDispatch?.(() => readyLifecycle, currentActivity);
  dependencies.installCompaction?.(() => readyLifecycle);
  dependencies.installFarmPreview?.(() => readyLifecycle);
  const publishStatus = (context: ExtensionContextPort, text: string | undefined) => {
    setArbiterStatus(context, text);
    statusPublished = text !== undefined;
  };
  const resetSessionState = () => {
    plan?.clear();
    readyLifecycle = undefined;
    enabled = false;
    persona = "";
    state = "";
    ownershipDegraded = undefined;
    bridgeDegraded = undefined;
    commandInvocationDegraded = undefined;
    footerActivationEnabled = false;
  };
  const degradedStatus = () => ownershipDegraded ?? commandInvocationDegraded ?? bridgeDegraded;
  const doctorHealth = (context: ExtensionContextPort) => {
    const footerHealth = footer.health();
    // `enabled` records the authority under which this session initialized.
    // Live trust still gates operations, but withdrawal must not rewrite the
    // historical expectation for an already-owned session manager.
    const backgroundExpected = footerHealth.expected && enabled;
    const backgroundInitialized = background !== undefined
      && nativeJobsRegistered && readyLifecycle !== undefined;
    let backgroundHealthy = false;
    if (backgroundInitialized) {
      try { backgroundHealthy = background.healthy() === true; } catch { backgroundHealthy = false; }
    }
    return Object.freeze({
      footer: footerHealth,
      background: Object.freeze({
        expected: backgroundExpected,
        initialized: backgroundInitialized,
        healthy: backgroundHealthy,
      }),
    });
  };
  registerAliases(pi, dependencies.catalog, dependencies.packageRoot, (status) => {
    commandInvocationDegraded = status;
    statusPublished = true;
  }, async (entry, _args, context) => {
    if (entry.name !== "doctor" || dependencies.doctorReport === undefined) return undefined;
    const report = await dependencies.doctorReport(context, doctorHealth(context));
    return renderPiDoctorReportBlock(report);
  });

  pi.on("session_start", async (_event, context) => {
    activeLifecycle = undefined;
    readyLifecycle = undefined;
    if (background !== undefined) await background.stop("session-switch");
    activity?.dispose();
    activity = undefined;
    dependencies.enforcementReadiness?.deactivate();
    dependencies.enforcementReadiness?.beginActivation();
    dependencies.resetBridge?.();
    if (statusPublished) publishStatus(context, undefined);
    resetSessionState();
    activity = createSessionActivityRegistry({ onChange: () => footer.requestActivityRender() });
    const lifecycle = Object.freeze({ sequence: ++lifecycleSequence });
    activeLifecycle = lifecycle;
    const isCurrent = () => activeLifecycle === lifecycle;
    await footer.start(context);
    if (!isCurrent()) return;
    const markerEnabled = await readActivation(context.cwd);
    if (!isCurrent()) return;
    footerActivationEnabled = markerEnabled;
    await footer.refresh(context, {
      activation: { enabled: markerEnabled },
      prepareBridge: dependencies.prepareFooterBridge,
      readUpdateVersion: dependencies.readFooterUpdateVersion,
    });
    if (!isCurrent()) return;
    if (!markerEnabled) {
      activeLifecycle = undefined;
      dependencies.enforcementReadiness?.deactivate();
      return;
    }
    if (!hasAffirmativeProjectTrust(context)) {
      publishStatus(context, PI_TRUST_REQUIRED_STATUS);
      context.ui.notify(PI_TRUST_REQUIRED_STATUS, "warning");
      return;
    }
    enabled = true;
    nativePlanRegistered = plan?.register(context) === true;
    nativeJobsRegistered = background?.register(context) === true;
    dependencies.enforcementReadiness?.beginBootstrap();
    ownershipDegraded = ownershipStatus(pi, dependencies, nativePlanRegistered, nativeJobsRegistered);
    publishStatus(context, degradedStatus() ?? "codeArbiter host: pi starting");
    await dependencies.prepareBridge?.(context.cwd, context);
    if (!isCurrent()) return;
    try {
      await dependencies.installEnforcement?.(
        context.cwd,
        context,
        () => plan?.mode() ?? "execute",
        background === undefined || !nativeJobsRegistered ? undefined : (cwd) => background.toolFactory(cwd),
      );
      if (!isCurrent()) return;
      readyLifecycle = lifecycle;
      dependencies.enforcementReadiness?.markReady();
      if (background !== undefined && nativeJobsRegistered && !background.activate(context)) {
        throw new Error("codeArbiter background runtime could not activate; run /ca-doctor.");
      }
      await plan?.restore(context);
      if (!isCurrent()) return;
    } catch (error) {
      if (!isCurrent()) return;
      readyLifecycle = undefined;
      activeLifecycle = undefined;
      await background?.stop("fatal");
      enabled = false;
      bridgeDegraded = "codeArbiter host: pi unhealthy - enforcement installation failed; run /ca-doctor";
      publishStatus(context, bridgeDegraded);
      context.ui.notify(bridgeDegraded, "error");
      throw new Error(bridgeDegraded, { cause: error });
    }
    try {
      persona = await dependencies.loadPersona();
      if (!isCurrent()) return;
      const response = await dependencies.bridge.call({ version: 1, event: "session_start", cwd: context.cwd }, context.signal ?? neverAborted);
      if (!isCurrent()) return;
      state = response.context ?? "host: pi";
      if (response.outcome === "warn") {
        bridgeDegraded = "codeArbiter host: pi degraded - bridge unavailable; run /ca-doctor";
        if (response.message !== undefined) context.ui.notify(response.message, "warning");
      } else {
        bridgeDegraded = undefined;
      }
      publishStatus(context, degradedStatus() ?? "codeArbiter host: pi governed");
    } catch {
      if (!isCurrent()) return;
      state = "host: pi\nbridge unavailable; run /ca-doctor";
      bridgeDegraded = "codeArbiter host: pi degraded - bridge unavailable; run /ca-doctor";
      publishStatus(context, degradedStatus());
    }
  });

  pi.on("before_agent_start", async (event, context) => {
    const lifecycle = readyLifecycle;
    if (!enabled || lifecycle === undefined) return;
    ownershipDegraded = ownershipStatus(pi, dependencies, nativePlanRegistered, nativeJobsRegistered);
    if (degradedStatus() !== undefined) publishStatus(context, degradedStatus());
    try {
      const response = await dependencies.bridge.call({
        version: 1,
        event: "before_agent_start",
        cwd: context.cwd,
      }, context.signal ?? neverAborted);
      if (readyLifecycle !== lifecycle) return;
      if (response.context !== undefined) state = response.context;
      if (response.outcome === "warn") {
        bridgeDegraded = "codeArbiter host: pi degraded - bridge unavailable; run /ca-doctor";
        if (response.message !== undefined) context.ui.notify(response.message, "warning");
      } else {
        bridgeDegraded = undefined;
      }
    } catch {
      if (readyLifecycle !== lifecycle) return;
      bridgeDegraded = "codeArbiter host: pi degraded - bridge unavailable; run /ca-doctor";
      publishStatus(context, degradedStatus());
    }
    const systemPrompt = typeof event.systemPrompt === "string" ? event.systemPrompt : "";
    return { systemPrompt: appendPrompt(systemPrompt, persona, state) };
  });

  pi.on("agent_start", (_event, context) => {
    if (enabled) publishStatus(context, degradedStatus() ?? "codeArbiter host: pi governed");
  });
  pi.on("agent_settled", async (_event, context) => {
    await footer.refresh(context, { activation: { enabled: footerActivationEnabled } });
    if (enabled) publishStatus(context, degradedStatus());
  });
  const stopSession = async (reason: "session-switch" | "shutdown" | "unload" | "fatal", context: ExtensionContextPort) => {
    readyLifecycle = undefined;
    activeLifecycle = undefined;
    await background?.stop(reason);
    activity?.dispose();
    activity = undefined;
    footer.dispose();
    if (statusPublished) publishStatus(context, undefined);
    resetSessionState();
    dependencies.enforcementReadiness?.deactivate();
  };
  pi.on("session_shutdown", async (event, context) => {
    const reason = typeof event.reason === "string" ? event.reason : "";
    await stopSession(["new", "resume", "fork"].includes(reason)
      ? "session-switch"
      : reason === "reload" ? "unload" : "shutdown", context);
  });
}

const PI_DOCTOR_REPORT_MAX_BYTES = 16_000;
const PI_DOCTOR_TRUNCATION_MARKER = "\n[codeArbiter doctor report truncated]";

function encodePiDoctorReport(report: string): string {
  return JSON.stringify({ format: "codearbiter-doctor-v1", report })
    .replace(/[<>&\u007f-\u009f]/gu, (character) => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

function wrapPiDoctorPayload(payload: string): string {
  return `<codearbiter-doctor-report>\n${payload}\n</codearbiter-doctor-report>`;
}

export function renderPiDoctorReportBlock(report: string): string {
  const normalizedReport = safeDiagnostic(report, Number.MAX_SAFE_INTEGER);
  const complete = wrapPiDoctorPayload(encodePiDoctorReport(normalizedReport));
  if (Buffer.byteLength(complete, "utf8") <= PI_DOCTOR_REPORT_MAX_BYTES) return complete;

  let low = 0;
  let high = normalizedReport.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    const candidate = wrapPiDoctorPayload(encodePiDoctorReport(
      normalizedReport.slice(0, middle) + PI_DOCTOR_TRUNCATION_MARKER,
    ));
    if (Buffer.byteLength(candidate, "utf8") <= PI_DOCTOR_REPORT_MAX_BYTES) low = middle;
    else high = middle - 1;
  }
  if (low > 0 && /[\ud800-\udbff]/u.test(normalizedReport[low - 1]!)) low -= 1;
  return wrapPiDoctorPayload(encodePiDoctorReport(
    normalizedReport.slice(0, low) + PI_DOCTOR_TRUNCATION_MARKER,
  ));
}

function loadPiToolClasses(value: unknown): Readonly<Record<string, ToolCategory>> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("codeArbiter Pi tool descriptor is missing; run /ca-doctor.");
  }
  const categories = new Set<ToolCategory>(["EXEC", "WRITE", "EDIT", "READ", "OTHER"]);
  const classes: Record<string, ToolCategory> = {};
  for (const [name, category] of Object.entries(value as Record<string, unknown>)) {
    if (name === "" || typeof category !== "string" || !categories.has(category as ToolCategory)) {
      throw new Error("codeArbiter Pi tool descriptor is invalid; run /ca-doctor.");
    }
    classes[name] = category as ToolCategory;
  }
  return Object.freeze(classes);
}

export function createCodeArbiterPi(input: HostCompatibility) {
  return function codeArbiterPiForRuntime(_pi: ExtensionAPI): void {
    const direction = compatibilityDirection(input);
    if (direction !== null) throw new Error(direction);
  };
}

const PI_TUI_DIAGNOSIS = "codeArbiter could not load Pi terminal width support; run /ca-doctor.";

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

export function createPiFooterMetricsLoader(
  runtime: Pick<ResolvedPiRuntime, "moduleEntry" | "packageRoot">,
): () => Promise<FooterTextMetrics> {
  let loaded: FooterTextMetrics | undefined;
  let pending: Promise<FooterTextMetrics> | undefined;
  return async () => {
    if (loaded !== undefined) return loaded;
    pending ??= (async () => {
      try {
        const runtimeRoot = await realpath(runtime.packageRoot);
        const moduleEntry = await realpath(runtime.moduleEntry);
        if (!inside(moduleEntry, runtimeRoot)) throw new Error("runtime entry outside package");
        const runtimeRequire = createRequire(moduleEntry);
        const resolvedEntry = runtimeRequire.resolve("@earendil-works/pi-tui");
        const unresolvedRoot = resolve(runtimeRoot, "node_modules", "@earendil-works", "pi-tui");
        const rootInfo = await lstat(unresolvedRoot);
        if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) {
          throw new Error("TUI package root is linked or non-directory");
        }
        const expectedRoot = await realpath(unresolvedRoot);
        if (!inside(expectedRoot, runtimeRoot)) throw new Error("TUI package root outside runtime");
        const [entryInfo, manifestInfo] = await Promise.all([
          lstat(resolvedEntry),
          lstat(resolve(expectedRoot, "package.json")),
        ]);
        if (!entryInfo.isFile() || entryInfo.isSymbolicLink()
          || !manifestInfo.isFile() || manifestInfo.isSymbolicLink() || manifestInfo.size > 4_096) {
          throw new Error("runtime-owned TUI files are invalid");
        }
        const canonicalEntry = await realpath(resolvedEntry);
        if (!inside(canonicalEntry, expectedRoot)) throw new Error("TUI entry outside owner package");
        const manifest = JSON.parse(await readFile(resolve(expectedRoot, "package.json"), "utf8")) as { name?: unknown };
        if (manifest.name !== "@earendil-works/pi-tui") throw new Error("TUI package owner mismatch");
        const tuiModule = await import(pathToFileURL(canonicalEntry).href) as {
          visibleWidth?: unknown;
          truncateToWidth?: unknown;
        };
        if (typeof tuiModule.visibleWidth !== "function" || typeof tuiModule.truncateToWidth !== "function") {
          throw new Error("TUI export shape mismatch");
        }
        const [rootAfter, entryAfter, manifestAfter, canonicalRootAfter, canonicalEntryAfter] = await Promise.all([
          lstat(unresolvedRoot),
          lstat(resolvedEntry),
          lstat(resolve(expectedRoot, "package.json")),
          realpath(unresolvedRoot),
          realpath(resolvedEntry),
        ]);
        if (!rootAfter.isDirectory() || rootAfter.isSymbolicLink()
          || rootAfter.dev !== rootInfo.dev || rootAfter.ino !== rootInfo.ino
          || !entryAfter.isFile() || entryAfter.isSymbolicLink()
          || entryAfter.dev !== entryInfo.dev || entryAfter.ino !== entryInfo.ino
          || !manifestAfter.isFile() || manifestAfter.isSymbolicLink()
          || manifestAfter.dev !== manifestInfo.dev || manifestAfter.ino !== manifestInfo.ino
          || canonicalRootAfter !== expectedRoot || canonicalEntryAfter !== canonicalEntry) {
          throw new Error("TUI package identity changed during load");
        }
        loaded = Object.freeze({
          visibleWidth: tuiModule.visibleWidth as FooterTextMetrics["visibleWidth"],
          truncateToWidth: tuiModule.truncateToWidth as FooterTextMetrics["truncateToWidth"],
        });
        return loaded;
      } catch (error) {
        throw new Error(PI_TUI_DIAGNOSIS, { cause: error });
      }
    })();
    try {
      return await pending;
    } catch (error) {
      pending = undefined;
      throw error;
    }
  };
}

export default async function codeArbiterPi(pi: ExtensionAPI): Promise<void> {
  const runtimeIdentity = await resolvePiRuntimeIdentity();
  const direction = compatibilityDirection({
    piVersion: runtimeIdentity.version,
    nodeVersion: process.versions.node,
    // Python is resolved only after enabled activation reaches Pi's established trust context.
    pythonMajor: 3,
  });
  if (direction !== null) throw new Error(direction);
  const runtime = await loadPiRuntime(runtimeIdentity);
  const loadFooterMetrics = createPiFooterMetricsLoader(runtime);
  const modulePath = await realpath(fileURLToPath(import.meta.url));
  let packageRoot = dirname(modulePath);
  while (true) {
    try {
      const manifest = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") break;
    } catch {
      // Keep walking to the ca-pi distribution manifest.
    }
    const parent = dirname(packageRoot);
    if (parent === packageRoot) throw new Error("codeArbiter could not locate the ca-pi package; run /ca-doctor.");
    packageRoot = parent;
  }
  const catalog = JSON.parse(await readFile(resolve(packageRoot, "generated", "command-catalog.json"), "utf8")) as CommandCatalogEntry[];
  const toolClasses = loadPiToolClasses(__CODEARBITER_PI_TOOL_CLASSES__);
  const rawPermissionSurfaces = __CODEARBITER_PI_PERMISSION_POLICY_SURFACES__;
  if (rawPermissionSurfaces === null || typeof rawPermissionSurfaces !== "object" || Array.isArray(rawPermissionSurfaces)) {
    throw new Error("codeArbiter could not load the Pi permission policy descriptor; run /ca-doctor.");
  }
  const permissionPolicy = compileBuiltinPermissionPolicy(
    toolClasses,
    rawPermissionSurfaces as Readonly<Record<string, string>>,
  );
  if (permissionPolicy === undefined) {
    throw new Error("codeArbiter could not compile the Pi permission policy descriptor; run /ca-doctor.");
  }
  const planCommandDescriptor = Object.freeze({ ...permissionPolicy.actionClasses });
  const expansionFingerprints = __CODEARBITER_PI_SKILL_EXPANSION_FINGERPRINTS__ as Readonly<Record<string, string>>;
  let pythonCommand: ReturnType<typeof resolvePythonCommand> | undefined;
  let gitExecutable: string | undefined;
  let pythonResolutionAttempted = false;
  let concreteBridge: BridgeClient | undefined;
  let unavailableBridge: BridgeClient | undefined;
  const shouldAuditBridgeFailure = (request: Parameters<BridgePort["call"]>[0]) =>
    request.event !== "footer_usage_update" && request.event !== "footer_status_snapshot";
  const bridge: BridgePort = {
    call: async (request, signal) => {
      const selectedPython = pythonCommand;
      const selectedGit = gitExecutable;
      if (selectedPython === undefined || selectedGit === undefined) {
        unavailableBridge ??= new BridgeClient({
          bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
          packageRoot,
          pythonExecutable: undefined,
          gitExecutable: undefined,
          toolClasses,
          shouldAuditFailure: shouldAuditBridgeFailure,
        });
        return await unavailableBridge.call(request, signal);
      }
      concreteBridge ??= new BridgeClient({
        bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
        packageRoot,
        pythonExecutable: selectedPython?.executable,
        pythonPrefixArgs: selectedPython?.prefixArgs,
        gitExecutable: selectedGit,
        toolClasses,
        shouldAuditFailure: shouldAuditBridgeFailure,
      });
      return await concreteBridge.call(request, signal);
    },
  };
  const resetBridge = () => {
    pythonCommand = undefined;
    gitExecutable = undefined;
    pythonResolutionAttempted = false;
    concreteBridge = undefined;
    unavailableBridge = undefined;
  };
  const prepareBridgeIdentity = (cwd: string) => {
    pythonResolutionAttempted = true;
    concreteBridge = undefined;
    unavailableBridge = undefined;
    try {
      pythonCommand = resolvePythonCommand(process.platform, undefined, packageRoot, cwd);
      gitExecutable = resolveGitExecutable(cwd);
    } catch {
      pythonCommand = undefined;
      gitExecutable = undefined;
    }
  };
  const enforcement = new EnforcementInstaller();
  enforcement.ensureBootstrap(pi, toolClasses);
  installParent(pi, {
    bridge,
    catalog,
    packageRoot,
    planCommandDescriptor,
    appendPlanEntry: (customType, data) => {
      (pi as ExtensionAPI & { appendEntry(customType: string, data: unknown): void }).appendEntry(customType, data);
    },
    enforcementReadiness: enforcement,
    loadPersona: async () => await readFile(resolve(packageRoot, "ORCHESTRATOR.md"), "utf8"),
    resetBridge,
    prepareFooterBridge: (cwd) => { prepareBridgeIdentity(cwd); },
    readFooterUpdateVersion: async () => await readCachedUpdateVersion(packageRoot),
    loadFooterMetrics,
    installDispatch: (currentLifecycle, currentActivity) => installPiDispatch(pi, {
      packageRoot,
      piCliPath: runtime.cliEntry,
      currentLifecycle,
      currentActivity,
    }),
    installCompaction: (currentLifecycle) => installPiCompaction(pi, {
      packageRoot,
      currentLifecycle,
      runner: createPiCompactionRunner({
        bridge,
        runtime: {
          nodePath: process.execPath,
          piCliPath: runtime.cliEntry,
          packageRoot,
          childExtensionPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
          parentEnv: process.env,
          platform: process.platform,
        },
      }),
      audit: appendPiCompactionAudit,
    }),
    installFarmPreview: (currentLifecycle) => installPiFarmPreview(pi, {
      packageRoot,
      nodePath: process.execPath,
      environment: process.env,
      currentLifecycle,
    }),
    installBackground: (currentLifecycle, currentActivity) => createNativeBackgroundController(pi, {
      packageRoot,
      currentLifecycle,
      toolOwnershipValid: () => {
        try {
          if (!pi.getActiveTools().includes("codearbiter_background_bash")) return false;
          const matches = pi.getAllTools().filter((tool) => tool.name === "codearbiter_background_bash");
          if (matches.length !== 1) return false;
          const source = realpathSync(matches[0]!.sourceInfo.path);
          return process.platform === "win32"
            ? source.toLowerCase() === modulePath.toLowerCase()
            : source === modulePath;
        } catch { return false; }
      },
      createRuntime: () => createBackgroundJobRuntime({ activity: currentActivity() }),
      resolveLaunch: async (cwd) => {
        const settings = runtime.SettingsManager.create(cwd, runtime.getAgentDir(), { projectTrusted: true });
        const shellPath = await resolvePiBackgroundShell(settings.getShellPath(), process.env, process.platform);
        const env = boundedPiEnvironment(process.env);
        if (shellPath === undefined || env === undefined) return undefined;
        const commandPrefix = settings.getShellCommandPrefix();
        return Object.freeze({
          shellPath,
          env,
          ...(commandPrefix === undefined ? {} : { commandPrefix }),
        });
      },
      audit: async (cwd, facts) => {
        const base = {
          timestamp: new Date().toISOString(), lifecycleId: facts.lifecycleId as string,
          correlation: facts.correlation as string, id: facts.id as number,
        };
        if (facts.event === "launch") return await appendBackgroundJobAudit(cwd, {
          ...base, event: "launch", state: facts.state as "queued" | "active" | "completed" | "failed" | "cancelled" | "timed-out",
          timeoutMs: facts.timeoutMs as number | null,
        });
        if (facts.event === "terminal") return await appendBackgroundJobAudit(cwd, {
          ...base, event: "terminal", state: facts.state as "completed" | "failed" | "cancelled" | "timed-out",
          exitClass: facts.exitClass as "success" | "failure" | "cancelled" | "timeout",
          durationMs: facts.durationMs as number, outputBytes: facts.outputBytes as number,
        });
        if (facts.event === "cancel") return await appendBackgroundJobAudit(cwd, {
          ...base, event: "cancel", accepted: facts.accepted as boolean,
        });
        return false;
      },
    }),
    prepareBridge: (cwd) => { prepareBridgeIdentity(cwd); },
    doctorReport: async (context, health) => {
      const enabledForDoctor = await isEnabled(context.cwd);
      const trustedForDoctor = hasAffirmativeProjectTrust(context);
      const commands = pi.getCommands();
      const doctorAlias = commands.find((command) => command.name === "ca-doctor");
      const packageScope = doctorAlias?.sourceInfo.scope ?? "temporary";
      const input = await collectPiDoctorInput({
        packageRoot,
        packageScope,
        extensionPath: modulePath,
        runtime: {
          piVersion: runtime.version,
          nodeVersion: process.versions.node,
          pythonMajor: trustedForDoctor && pythonCommand !== undefined ? 3 : null,
          cliEntry: runtime.cliEntry,
          moduleEntry: runtime.moduleEntry,
          packageRoot: runtime.packageRoot,
        },
        context,
        commands,
        catalog,
        bridge,
        bridgePrepared: enabledForDoctor && trustedForDoctor && pythonResolutionAttempted,
        footerExpected: health.footer.expected,
        footerInitialized: health.footer.initialized,
        backgroundExpected: health.background.expected,
        backgroundInitialized: health.background.initialized,
        backgroundHealthy: health.background.healthy,
        projectTrustRequired: enabledForDoctor,
        childPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
        wrapperSourcePath: modulePath,
        activeTools: pi.getActiveTools(),
        allTools: pi.getAllTools(),
        expansionFingerprints,
        childFingerprint: __CODEARBITER_PI_CHILD_SHA256__,
      });
      const wrapperSelfTest = await runPiWrapperSelfTest({
        enabled: enabledForDoctor,
        projectTrusted: trustedForDoctor,
        executeBash: async () => await enforcement.runDoctorWrapperSelfTest(context.signal),
      });
      return formatPiDoctorReport([...diagnosePi(input), wrapperSelfTest]);
    },
    installEnforcement: (cwd, context, getMode, backgroundToolFactory) => {
      const guardPi = pi;
      enforcement.ensureGuard(guardPi, toolClasses, modulePath);
      const factoriesFor = (projectTrusted: boolean): BuiltinToolFactories => ({
        bash: (root) => {
          const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted });
          return runtime.createBashToolDefinition(root, {
            commandPrefix: settings.getShellCommandPrefix(),
            shellPath: settings.getShellPath(),
          });
        },
        read: (root) => {
          const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted });
          return runtime.createReadToolDefinition(root, {
            autoResizeImages: settings.getImageAutoResize(),
          });
        },
        edit: (root) => runtime.createEditToolDefinition(root),
        write: (root) => runtime.createWriteToolDefinition(root),
      });
      // session_start already required an affirmative trust decision before this
      // installer can run. Do not re-read a mutable host signal mid-bootstrap.
      const factories = factoriesFor(true);
      const nativeFactories = factoriesFor(false);
      enforcement.ensureResults(pi, bridge, toolClasses);
      enforcement.ensureBuiltins(guardPi, bridge, {
        cwd,
        descriptor: toolClasses,
        factories,
        nativeFactories,
        wrapperSourcePath: modulePath,
        permissionPolicy,
        getMode,
        permissionAudit: appendPermissionAudit,
      });
      if (backgroundToolFactory !== undefined) {
        enforcement.ensureCustomTool(guardPi, bridge, {
          cwd,
          name: "codearbiter_background_bash",
          bridgeToolName: "bash",
          descriptor: toolClasses,
          factory: backgroundToolFactory,
          wrapperSourcePath: modulePath,
          permissionPolicy,
          getMode,
          permissionAudit: appendPermissionAudit,
        });
      }
    },
  });
}
