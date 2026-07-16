/** extension.ts - codeArbiter's dormant Pi parent entrypoint and compatibility guard. */
import { readFile, realpath } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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
import { isEnabled } from "./activation.ts";
import { assertCommandOwnership, registerAliases } from "./commands.ts";
import { loadPiRuntime, resolvePiRuntimeIdentity } from "./runtime-resolver.ts";
import { setArbiterStatus } from "./status.ts";
import { EnforcementInstaller } from "./tool-guard.ts";
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
  resetBridge?: () => void;
  prepareBridge?: (cwd: string, context: ExtensionContextPort) => Promise<void> | void;
  installEnforcement?: (cwd: string, context: ExtensionContextPort) => Promise<void> | void;
  enforcementReadiness?: EnforcementReadinessPort;
  doctorReport?: (context: ExtensionContextPort) => Promise<string>;
  installDispatch?: (currentLifecycle: () => LifecycleLease | undefined) => void;
  installCompaction?: (currentLifecycle: () => LifecycleLease | undefined) => void;
  installFarmPreview?: (currentLifecycle: () => LifecycleLease | undefined) => void;
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

function ownershipStatus(
  pi: ParentPiPort,
  dependencies: ParentDependencies,
): string | undefined {
  const collisions = assertCommandOwnership(pi, dependencies.packageRoot, dependencies.catalog);
  return collisions.length === 0
    ? undefined
    : `codeArbiter host: pi degraded - ${collisions.length} command ownership conflict(s); run /ca-doctor`;
}

export function installParent(pi: ParentPiPort, dependencies: ParentDependencies): void {
  let enabled = false;
  let persona = "";
  let state = "";
  let ownershipDegraded: string | undefined;
  let bridgeDegraded: string | undefined;
  let commandInvocationDegraded: string | undefined;
  let statusPublished = false;
  let lifecycleSequence = 0;
  let activeLifecycle: LifecycleLease | undefined;
  let readyLifecycle: LifecycleLease | undefined;
  dependencies.installDispatch?.(() => readyLifecycle);
  dependencies.installCompaction?.(() => readyLifecycle);
  dependencies.installFarmPreview?.(() => readyLifecycle);
  const publishStatus = (context: ExtensionContextPort, text: string | undefined) => {
    setArbiterStatus(context, text);
    statusPublished = text !== undefined;
  };
  const resetSessionState = () => {
    readyLifecycle = undefined;
    enabled = false;
    persona = "";
    state = "";
    ownershipDegraded = undefined;
    bridgeDegraded = undefined;
    commandInvocationDegraded = undefined;
  };
  const degradedStatus = () => ownershipDegraded ?? commandInvocationDegraded ?? bridgeDegraded;
  registerAliases(pi, dependencies.catalog, dependencies.packageRoot, (status) => {
    commandInvocationDegraded = status;
    statusPublished = true;
  }, async (entry, _args, context) => {
    if (entry.name !== "doctor" || dependencies.doctorReport === undefined) return undefined;
    const report = await dependencies.doctorReport(context);
    return renderPiDoctorReportBlock(report);
  });

  pi.on("session_start", async (_event, context) => {
    activeLifecycle = undefined;
    dependencies.enforcementReadiness?.deactivate();
    dependencies.enforcementReadiness?.beginActivation();
    dependencies.resetBridge?.();
    if (statusPublished) publishStatus(context, undefined);
    resetSessionState();
    const lifecycle = Object.freeze({ sequence: ++lifecycleSequence });
    activeLifecycle = lifecycle;
    const isCurrent = () => activeLifecycle === lifecycle;
    const markerEnabled = await isEnabled(context.cwd);
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
    dependencies.enforcementReadiness?.beginBootstrap();
    ownershipDegraded = ownershipStatus(pi, dependencies);
    publishStatus(context, degradedStatus() ?? "codeArbiter host: pi starting");
    await dependencies.prepareBridge?.(context.cwd, context);
    if (!isCurrent()) return;
    try {
      await dependencies.installEnforcement?.(context.cwd, context);
      if (!isCurrent()) return;
      readyLifecycle = lifecycle;
      dependencies.enforcementReadiness?.markReady();
    } catch (error) {
      if (!isCurrent()) return;
      readyLifecycle = undefined;
      activeLifecycle = undefined;
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
    ownershipDegraded = ownershipStatus(pi, dependencies);
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
  pi.on("agent_settled", (_event, context) => {
    if (enabled) publishStatus(context, degradedStatus());
  });
  pi.on("session_shutdown", (_event, context) => {
    if (statusPublished) publishStatus(context, undefined);
    resetSessionState();
    activeLifecycle = undefined;
    dependencies.enforcementReadiness?.deactivate();
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
  const expansionFingerprints = __CODEARBITER_PI_SKILL_EXPANSION_FINGERPRINTS__ as Readonly<Record<string, string>>;
  let pythonCommand: ReturnType<typeof resolvePythonCommand> | undefined;
  let gitExecutable: string | undefined;
  let pythonResolutionAttempted = false;
  let concreteBridge: BridgeClient | undefined;
  let unavailableBridge: BridgeClient | undefined;
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
  const enforcement = new EnforcementInstaller();
  enforcement.ensureBootstrap(pi as unknown as ToolGuardPiPort, toolClasses);
  installParent(pi as unknown as ParentPiPort, {
    bridge,
    catalog,
    packageRoot,
    enforcementReadiness: enforcement,
    loadPersona: async () => await readFile(resolve(packageRoot, "ORCHESTRATOR.md"), "utf8"),
    resetBridge,
    installDispatch: (currentLifecycle) => installPiDispatch(pi as unknown as ToolGuardPiPort, {
      packageRoot,
      piCliPath: runtime.cliEntry,
      currentLifecycle,
    }),
    installCompaction: (currentLifecycle) => installPiCompaction(pi as never, {
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
    installFarmPreview: (currentLifecycle) => installPiFarmPreview(pi as unknown as ToolGuardPiPort, {
      packageRoot,
      nodePath: process.execPath,
      environment: process.env,
      currentLifecycle,
    }),
    prepareBridge: (cwd) => {
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
    },
    doctorReport: async (context) => {
      const enabledForDoctor = await isEnabled(context.cwd);
      const trustedForDoctor = hasAffirmativeProjectTrust(context);
      const commands = (pi as unknown as ParentPiPort).getCommands();
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
        projectTrustRequired: enabledForDoctor,
        childPath: resolve(packageRoot, "extensions", "codearbiter-child.js"),
        wrapperSourcePath: modulePath,
        activeTools: (pi as unknown as ToolGuardPiPort).getActiveTools(),
        allTools: (pi as unknown as ToolGuardPiPort).getAllTools(),
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
    installEnforcement: (cwd, context) => {
      const guardPi = pi as unknown as ToolGuardPiPort;
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
      enforcement.ensureResults(pi as unknown as ToolResultPiPort, bridge, toolClasses);
      enforcement.ensureBuiltins(guardPi, bridge, {
        cwd,
        descriptor: toolClasses,
        factories,
        nativeFactories,
        wrapperSourcePath: modulePath,
      });
    },
  });
}
