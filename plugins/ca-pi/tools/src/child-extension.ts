/** child-extension.ts - codeArbiter's enforcement-only isolated Pi child adapter. */
import { createReadStream } from "node:fs";
import { readFile, realpath } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  CHILD_ATTESTATION_TIMEOUT_MS,
  CHILD_ATTESTATION_TITLE,
  childAttestationDigest,
} from "./attestation.ts";
import { BridgeClient, resolveGitExecutable, resolvePythonCommand } from "./bridge.ts";
import { compatibilityDirection } from "./compatibility.ts";
import type {
  BridgePort,
  BuiltinToolFactories,
  ExtensionContextPort,
  ToolCategory,
  ToolGuardPiPort,
  ToolResultPiPort,
} from "./contracts.ts";
import { loadPiRuntime, resolvePiRuntimeIdentity } from "./runtime-resolver.ts";
import { EnforcementInstaller } from "./tool-guard.ts";

declare const __CODEARBITER_PI_TOOL_CLASSES__: unknown;

const HANDSHAKE_COMMAND = "codearbiter-internal-child-handshake";
const NONCE = /^[0-9a-f]{32}$/u;
const HANDSHAKE_ARGS = /^([0-9a-f]{32}) ([0-9a-f]{32})$/u;
const CHILD_TOOLS = new Set(["read", "bash", "edit", "write"]);

interface ChildPiPort extends ToolGuardPiPort, ToolResultPiPort {
  on(event: string, handler: (event: Record<string, unknown>, context: ExtensionContextPort) => unknown): void;
  registerCommand(name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }): void;
}

export interface ChildDependencies {
  marker: string | undefined;
  expectedNonce?: string;
  cwd?: string;
  wrapperSourcePath?: string;
  descriptor?: Readonly<Record<string, ToolCategory>>;
  bridge?: BridgePort;
  factories?: BuiltinToolFactories;
  nativeFactories?: BuiltinToolFactories;
}

function fixedFailure(message: string): Error {
  return new Error(`codeArbiter child handshake ${message}; child remains blocked; run /ca-doctor.`);
}

export function installChild(pi: ChildPiPort, dependencies: ChildDependencies): void {
  const descriptor = dependencies.descriptor ?? { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" };
  const enforcement = new EnforcementInstaller();
  let consumed = false;
  let activeCwd = dependencies.cwd;
  let wrappersInstalled = false;
  enforcement.ensureBootstrap(pi, descriptor);
  enforcement.beginActivation();
  if (dependencies.wrapperSourcePath !== undefined) enforcement.ensureGuard(pi, descriptor, dependencies.wrapperSourcePath);
  if (dependencies.bridge !== undefined) enforcement.ensureResults(pi, dependencies.bridge, descriptor);

  const installWrappers = (cwd: string) => {
    if (dependencies.bridge === undefined || dependencies.factories === undefined || dependencies.wrapperSourcePath === undefined) return false;
    enforcement.ensureBuiltins(pi, dependencies.bridge, {
      cwd,
      descriptor,
      factories: dependencies.factories,
      nativeFactories: dependencies.nativeFactories ?? dependencies.factories,
      wrapperSourcePath: dependencies.wrapperSourcePath,
    });
    wrappersInstalled = true;
    return true;
  };

  pi.on("session_start", (_event, context) => {
    activeCwd = context.cwd;
    enforcement.beginBootstrap();
    installWrappers(context.cwd);
  });
  pi.on("session_shutdown", () => {
    enforcement.deactivate();
    consumed = true;
  });

  pi.registerCommand(HANDSHAKE_COMMAND, {
    handler: async (args, context) => {
      if (dependencies.marker !== "1") throw fixedFailure("has no validated subagent marker");
      if (consumed) throw fixedFailure("nonce was already consumed");
      if (dependencies.expectedNonce === undefined) throw fixedFailure("capability is missing");
      if (!NONCE.test(dependencies.expectedNonce)) throw fixedFailure("capability is malformed");
      const framing = HANDSHAKE_ARGS.exec(args.trim());
      if (framing === null) throw fixedFailure("nonce or challenge is malformed");
      const [, nonce, challenge] = framing;
      if (nonce === undefined || challenge === undefined) throw fixedFailure("nonce or challenge is malformed");
      if (nonce !== dependencies.expectedNonce) throw fixedFailure("nonce does not match the parent capability");
      consumed = true;
      const cwd = activeCwd ?? context.cwd;
      if (cwd !== undefined) installWrappers(cwd);
      if (!wrappersInstalled) throw fixedFailure("enforcement is unavailable");
      const activeTools = [...pi.getActiveTools()].sort();
      let projectTrusted: boolean;
      try { projectTrusted = context.isProjectTrusted?.() ?? true; }
      catch { throw fixedFailure("attestation context is unavailable"); }
      if (context.mode !== "rpc" || context.hasUI !== true || context.ui.confirm === undefined
        || projectTrusted !== false || typeof cwd !== "string" || cwd === ""
        || context.model === undefined || typeof context.model.provider !== "string" || context.model.provider === ""
        || typeof context.model.id !== "string" || context.model.id === ""
        || new Set(activeTools).size !== activeTools.length
        || activeTools.some((tool) => !CHILD_TOOLS.has(tool) || descriptor[tool] === undefined)) {
        throw fixedFailure("attestation context is invalid");
      }
      const digest = childAttestationDigest({
        nonce,
        challenge,
        cwd,
        provider: context.model.provider,
        model: context.model.id,
        tools: activeTools,
        projectTrusted: false,
        mode: "rpc",
      });
      let confirmed: boolean;
      try {
        confirmed = await context.ui.confirm(CHILD_ATTESTATION_TITLE, digest, { timeout: CHILD_ATTESTATION_TIMEOUT_MS });
      } catch {
        throw fixedFailure("attestation confirmation failed");
      }
      if (!confirmed) throw fixedFailure("attestation confirmation was rejected");
      enforcement.markReady();
    },
  });
}

export async function readChildCapability(source: NodeJS.ReadableStream = createReadStream("", { fd: 3, autoClose: true })): Promise<string> {
  let value = "";
  let bytes = 0;
  try {
    for await (const chunk of source as AsyncIterable<Buffer | string>) {
      const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
      bytes += Buffer.byteLength(text, "utf8");
      if (bytes > 32) throw fixedFailure("capability is oversized");
      value += text;
    }
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("codeArbiter child handshake")) throw error;
    throw fixedFailure("capability pipe is unavailable");
  }
  if (!NONCE.test(value)) throw fixedFailure("capability is malformed");
  return value;
}

function loadToolClasses(value: unknown): Readonly<Record<string, ToolCategory>> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw fixedFailure("descriptor is unavailable");
  const allowed = new Set<ToolCategory>(["EXEC", "WRITE", "EDIT", "READ", "OTHER"]);
  const descriptor: Record<string, ToolCategory> = {};
  for (const [name, category] of Object.entries(value as Record<string, unknown>)) {
    if (name === "" || typeof category !== "string" || !allowed.has(category as ToolCategory)) throw fixedFailure("descriptor is invalid");
    descriptor[name] = category as ToolCategory;
  }
  return Object.freeze(descriptor);
}

export default async function codeArbiterPiChild(pi: ExtensionAPI): Promise<void> {
  if (process.env.CODEARBITER_SUBAGENT !== "1") throw fixedFailure("has no validated subagent marker");
  const expectedNonce = await readChildCapability();
  const runtimeIdentity = await resolvePiRuntimeIdentity();
  const direction = compatibilityDirection({ piVersion: runtimeIdentity.version, nodeVersion: process.versions.node, pythonMajor: 3 });
  if (direction !== null) throw new Error(direction);
  const runtime = await loadPiRuntime(runtimeIdentity);
  const modulePath = await realpath(fileURLToPath(import.meta.url));
  let packageRoot = dirname(modulePath);
  while (true) {
    try {
      const manifest = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") break;
    } catch {
      // Continue to the owning distribution root.
    }
    const parent = dirname(packageRoot);
    if (parent === packageRoot) throw fixedFailure("could not locate the ca-pi package");
    packageRoot = parent;
  }
  const cwd = process.cwd();
  const python = resolvePythonCommand(process.platform, undefined, packageRoot, cwd);
  const gitExecutable = resolveGitExecutable(cwd);
  const descriptor = loadToolClasses(__CODEARBITER_PI_TOOL_CLASSES__);
  const bridge = new BridgeClient({
    bridgeScript: resolve(packageRoot, "hooks", "pi-bridge.py"),
    packageRoot,
    pythonExecutable: python.executable,
    pythonPrefixArgs: python.prefixArgs,
    gitExecutable,
    toolClasses: descriptor,
  });
  const factories: BuiltinToolFactories = {
    bash: (root) => {
      const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted: false });
      return runtime.createBashToolDefinition(root, { commandPrefix: settings.getShellCommandPrefix(), shellPath: settings.getShellPath() });
    },
    read: (root) => {
      const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted: false });
      return runtime.createReadToolDefinition(root, { autoResizeImages: settings.getImageAutoResize() });
    },
    edit: (root) => runtime.createEditToolDefinition(root),
    write: (root) => runtime.createWriteToolDefinition(root),
  };
  installChild(pi, {
    marker: process.env.CODEARBITER_SUBAGENT,
    expectedNonce,
    cwd,
    wrapperSourcePath: modulePath,
    descriptor,
    bridge,
    factories,
    nativeFactories: factories,
  });
}
