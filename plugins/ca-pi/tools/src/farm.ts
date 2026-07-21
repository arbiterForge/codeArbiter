/** farm.ts - Pi preview routing to the one shared, built farm backend. */
import { realpath, readdir, stat } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";

import type {
  LifecycleAuthorization,
  ToolDefinitionPort,
  ToolExecutionContextPort,
} from "./contracts.ts";
import {
  createProcessTreeCleanup,
  processTreeSpawnOptions,
  spawnProcessTree,
} from "./process-tree.ts";
import type { ManagedChildProcess, ProcessTreeCleanup, ProcessTreeSpawnInput } from "./process-tree.ts";

const FARM_OUTPUT_LIMIT = 65_536;
const FARM_ENVIRONMENT = /^(?:FARM_[A-Z0-9_]+|PATH|PATHEXT|SystemRoot|WINDIR|TEMP|TMP)$/iu;
const SOURCE_CLOCK_TOLERANCE_MS = 1_000;

export type FarmTerminal = "completed" | "cancelled" | "failed" | "degraded";

export interface FarmPreviewInput {
  packageRoot: string;
  projectRoot: string;
  planPath: string;
  nodePath: string;
  environment: Readonly<NodeJS.ProcessEnv>;
  authorization: LifecycleAuthorization;
  canary?: boolean;
}

export interface FarmResult {
  label: "preview";
  terminal: FarmTerminal;
  backend: string;
  exitCode?: number;
  message?: string;
}

export type FarmSpawn = (
  command: string,
  args: readonly string[],
  options: ProcessTreeSpawnInput & ReturnType<typeof processTreeSpawnOptions>,
) => ManagedChildProcess | Promise<ManagedChildProcess>;

interface FarmDependencies {
  spawn?: FarmSpawn;
  createCleanup?: (target: ManagedChildProcess) => ProcessTreeCleanup;
}

interface FarmToolDependencies {
  packageRoot: string;
  nodePath: string;
  environment: Readonly<NodeJS.ProcessEnv>;
  authorize(context: ToolExecutionContextPort): boolean | LifecycleAuthorization | undefined | Promise<boolean | LifecycleAuthorization | undefined>;
  run?: (input: FarmPreviewInput, signal: AbortSignal) => Promise<FarmResult>;
}

const LEGACY_TEST_AUTHORIZATION: LifecycleAuthorization = Object.freeze({
  lease: Object.freeze({}),
  isCurrent: () => true,
});

function contained(root: string, candidate: string): boolean {
  const path = relative(root, candidate);
  return path === "" || (!path.startsWith("..") && !isAbsolute(path));
}

function result(backend: string, terminal: FarmTerminal, additions: Partial<FarmResult> = {}): FarmResult {
  return Object.freeze({ label: "preview", terminal, backend, ...additions });
}

function farmEnvironment(source: Readonly<NodeJS.ProcessEnv>): NodeJS.ProcessEnv {
  const selected: NodeJS.ProcessEnv = {};
  for (const [name, value] of Object.entries(source)) {
    if (value !== undefined && FARM_ENVIRONMENT.test(name)) selected[name] = value;
  }
  delete selected.OPENAI_API_KEY;
  delete selected.ANTHROPIC_API_KEY;
  delete selected.CLAUDE_CODE_OAUTH_TOKEN;
  delete selected.CODEARBITER_SUBAGENT;
  return selected;
}

async function resolveBackend(packageRoot: string): Promise<{
  backend: string;
  backendRoot: string;
  checkoutRoot: string;
}> {
  const canonicalPackage = await realpath(packageRoot);
  const checkoutRoot = await realpath(resolve(canonicalPackage, "..", ".."));
  const expectedPackage = await realpath(resolve(checkoutRoot, "plugins", "ca-pi"));
  if (canonicalPackage !== expectedPackage) throw new Error("package");
  const backendRoot = await realpath(resolve(checkoutRoot, "plugins", "ca", "tools"));
  const backend = await realpath(resolve(backendRoot, "farm.js"));
  if (!contained(checkoutRoot, backend) || !contained(backendRoot, backend)) throw new Error("containment");
  const backendInfo = await stat(backend);
  if (!backendInfo.isFile()) throw new Error("file");

  const sourceNames = (await readdir(backendRoot, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => entry.name);
  if (!sourceNames.includes("farm.ts")) throw new Error("source");
  const sourceStats = await Promise.all(sourceNames.map(async (name) => await stat(resolve(backendRoot, name))));
  if (sourceStats.some((source) => source.mtimeMs > backendInfo.mtimeMs + SOURCE_CLOCK_TOLERANCE_MS)) {
    throw new Error("stale");
  }
  return { backend, backendRoot, checkoutRoot };
}

async function resolvePlan(projectRoot: string, planPath: string): Promise<{ projectRoot: string; planPath: string }> {
  const canonicalProject = await realpath(projectRoot);
  const canonicalPlan = await realpath(planPath);
  if (!contained(canonicalProject, canonicalPlan) || !(await stat(canonicalPlan)).isFile()) throw new Error("plan");
  return { projectRoot: canonicalProject, planPath: canonicalPlan };
}

function waitForFarm(
  child: ManagedChildProcess,
  signal: AbortSignal,
  createCleanup: (target: ManagedChildProcess) => ProcessTreeCleanup,
): Promise<{
  code: number | null;
  cancelled: boolean;
  cleanupVerified: boolean;
  overflow: boolean;
}> {
  return new Promise((resolveWait) => {
    let settled = false;
    let cancelled = signal.aborted;
    let outputBytes = 0;
    let overflow = false;
    const cleanup = createCleanup(child);
    const finish = (reason: "cancelled" | "protocol_overflow" | "parent_shutdown", code: number | null) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", abort);
      void cleanup.terminate(reason)
        .then((outcome) => resolveWait({ code, cancelled, cleanupVerified: outcome.verified, overflow }))
        .catch(() => resolveWait({ code, cancelled, cleanupVerified: false, overflow }));
    };
    const abort = () => {
      cancelled = true;
      finish("cancelled", null);
    };
    const drain = (chunk: Buffer | string) => {
      outputBytes += Buffer.byteLength(chunk);
      if (outputBytes > FARM_OUTPUT_LIMIT && !overflow) {
        overflow = true;
        finish("protocol_overflow", null);
      }
    };
    child.stdout.on("data", drain);
    child.stderr.on("data", drain);
    child.once("error", () => finish("parent_shutdown", null));
    child.once("close", (code) => finish("parent_shutdown", code));
    signal.addEventListener("abort", abort, { once: true });
    if (cancelled) abort();
  });
}

export async function runFarmPreview(
  input: FarmPreviewInput,
  signal: AbortSignal,
  dependencies: FarmDependencies = {},
): Promise<FarmResult> {
  const expectedBackend = resolve(input.packageRoot, "..", "ca", "tools", "farm.js");
  let backend: string;
  try {
    ({ backend } = await resolveBackend(input.packageRoot));
  } catch {
    return result(expectedBackend, "degraded", {
      message: "shared farm backend is missing, outside the checkout, or stale; rebuild plugins/ca/tools/farm.js",
    });
  }
  let project: { projectRoot: string; planPath: string };
  try {
    project = await resolvePlan(input.projectRoot, input.planPath);
  } catch {
    return result(backend, "degraded", { message: "farm plan must be a regular file inside the active project" });
  }
  const env = farmEnvironment(input.environment);
  if (typeof env.FARM_API_KEY !== "string" || env.FARM_API_KEY === "") {
    return result(backend, "degraded", { message: "FARM_API_KEY is not configured for the preview farm backend" });
  }
  if (signal.aborted) return result(backend, "cancelled");

  let nodePath: string;
  try {
    nodePath = await realpath(input.nodePath);
  } catch {
    return result(backend, "degraded", { message: "shared farm backend could not be started" });
  }
  if (!input.authorization.isCurrent(input.authorization.lease)) {
    return result(backend, "degraded", { message: "farm preview lifecycle authorization changed before launch" });
  }
  if (signal.aborted) return result(backend, "cancelled");

  const spawnFarm = dependencies.spawn ?? (async (command, args, options) =>
    await spawnProcessTree(command, args, options));
  let child: ManagedChildProcess;
  try {
    child = await spawnFarm(
      nodePath,
      [backend, ...(input.canary === true ? ["--canary"] : []), project.planPath],
      {
        ...processTreeSpawnOptions(process.platform),
        cwd: project.projectRoot,
        env,
        stdio: ["pipe", "pipe", "pipe", "pipe"],
      },
    );
  } catch {
    return result(backend, "degraded", { message: "shared farm backend could not be started" });
  }
  const completed = await waitForFarm(child, signal, dependencies.createCleanup ?? createProcessTreeCleanup);
  if (completed.cancelled) return result(backend, "cancelled");
  if (completed.overflow) return result(backend, "degraded", { message: "shared farm backend output exceeded the preview limit" });
  if (!completed.cleanupVerified) return result(backend, "degraded", {
    ...(completed.code === null ? {} : { exitCode: completed.code }),
    message: "shared farm backend process-tree cleanup could not be verified",
  });
  if (completed.code !== 0) return result(backend, "failed", {
    ...(completed.code === null ? {} : { exitCode: completed.code }),
    message: "shared farm backend failed; inspect the bounded .farm report artifacts",
  });
  return result(backend, "completed", { exitCode: 0 });
}

export function createFarmPreviewTool(dependencies: FarmToolDependencies): ToolDefinitionPort {
  const run = dependencies.run ?? runFarmPreview;
  const degraded = (message: string): FarmResult => result(
    resolve(dependencies.packageRoot, "..", "ca", "tools", "farm.js"),
    "degraded",
    { message },
  );
  return {
    name: "codearbiter_farm_preview",
    label: "codeArbiter farm preview",
    description: "Run the shared codeArbiter farm backend with its existing plan contract.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["plan"],
      properties: {
        plan: { type: "string", minLength: 1, maxLength: 4_096 },
        canary: { type: "boolean" },
      },
    },
    execute: async (_toolCallId, params, signal, _onUpdate, context) => {
      let output: FarmResult;
      try {
        const authorized = context === undefined ? undefined : await dependencies.authorize(context);
        const authorization = authorized === true ? LEGACY_TEST_AUTHORIZATION : authorized;
        if (context === undefined || authorization === undefined || authorization === false) {
          output = degraded("farm preview is unavailable until codeArbiter activation and project trust are current");
        } else if (typeof context.cwd !== "string" || typeof params.plan !== "string"
          || (params.canary !== undefined && typeof params.canary !== "boolean")
          || Object.keys(params).some((key) => key !== "plan" && key !== "canary")) {
          output = degraded("farm preview request is invalid");
        } else {
          output = await run({
            packageRoot: dependencies.packageRoot,
            projectRoot: context.cwd,
            planPath: resolve(context.cwd, params.plan),
            nodePath: dependencies.nodePath,
            environment: dependencies.environment,
            authorization,
            ...(params.canary === true ? { canary: true } : {}),
          }, signal ?? context.signal ?? new AbortController().signal);
        }
      } catch {
        output = degraded("farm preview degraded unexpectedly; run /ca-doctor");
      }
      return {
        content: [{ type: "text", text: JSON.stringify(output) }],
        details: output,
      };
    },
  };
}
