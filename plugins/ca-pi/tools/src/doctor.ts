import type {
  BridgePort,
  Collision,
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
  SlashCommand,
  ToolInfoPort,
} from "./contracts.ts";
import { createHash } from "node:crypto";
import { existsSync, realpathSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
import { assertCommandOwnership, nativeSkillExpansion } from "./commands.ts";
import { atLeast as versionAtLeast } from "./compatibility.ts";

export type DiagnosisState = "healthy" | "degraded" | "unhealthy";

export interface Diagnosis {
  id: string;
  state: DiagnosisState;
  message: string;
  remediation: string;
}

export interface PiDoctorInput {
  package: {
    root: string;
    name: string;
    version: string;
    extensionPath: string;
    scope: "user" | "project" | "temporary";
    declared: boolean;
  };
  trust: { inspected: boolean; projectTrusted: boolean; required: boolean };
  runtime: {
    piVersion: string;
    nodeVersion: string;
    pythonMajor: number | null;
    cliEntry: string;
    moduleEntry: string;
    packageRoot: string;
  };
  core: { present: boolean; bridgeScript: string };
  commands: {
    collisions: readonly Collision[];
    ownerPaths: readonly string[];
    expansionVerifiedVersions: readonly string[];
    expansionMatches: boolean;
  };
  bridge: { healthy: boolean };
  child: { present: boolean; artifact: "enforced" | "unknown"; path: string };
  ambientMarker: { present: boolean; validatedChild: boolean };
  moduleIdentity: { selfConsistent: boolean };
  finalArguments: {
    verified: boolean;
    wrapperSourcePath?: string;
    activeTools?: readonly string[];
    toolSources?: Readonly<Record<string, string>>;
  };
}

export interface PiDoctorCollectorDependencies {
  packageRoot: string;
  packageScope: "user" | "project" | "temporary";
  extensionPath: string;
  runtime: PiDoctorInput["runtime"];
  context: ExtensionContextPort;
  commands: readonly SlashCommand[];
  catalog: readonly CommandCatalogEntry[];
  bridge: BridgePort;
  bridgePrepared: boolean;
  projectTrustRequired: boolean;
  childPath: string;
  wrapperSourcePath: string;
  activeTools: readonly string[];
  allTools: readonly ToolInfoPort[];
  expansionFingerprints: Readonly<Record<string, string>>;
  childFingerprint: string;
  expandSkill?: typeof nativeSkillExpansion;
}

const EXPANSION_CANARY_PATH = "ca-doctor/SKILL.md";
const EXPANSION_CANARY_BODY = "doctor expansion canary";

export function verifyNativeSkillExpansion(
  version: string,
  expectedFingerprints: Readonly<Record<string, string>>,
  expandSkill: typeof nativeSkillExpansion = nativeSkillExpansion,
): boolean {
  const expected = expectedFingerprints[version];
  if (!/^[a-f0-9]{64}$/u.test(expected ?? "")) return false;
  const expanded = expandSkill("doctor", EXPANSION_CANARY_PATH, EXPANSION_CANARY_BODY, "");
  const actual = createHash("sha256").update(expanded, "utf8").digest("hex");
  return actual === expected;
}

async function inspectChildArtifact(
  path: string,
  expectedFingerprint: string,
): Promise<PiDoctorInput["child"]["artifact"]> {
  if (!/^[a-f0-9]{64}$/u.test(expectedFingerprint)) return "unknown";
  let bytes: Buffer;
  try { bytes = await readFile(path); } catch { return "unknown"; }
  const actual = createHash("sha256").update(bytes).digest("hex");
  return actual === expectedFingerprint ? "enforced" : "unknown";
}

export async function collectPiDoctorInput(
  dependencies: PiDoctorCollectorDependencies,
): Promise<PiDoctorInput> {
  let manifest: { name?: unknown; version?: unknown; pi?: { extensions?: unknown } } = {};
  try {
    manifest = JSON.parse(await readFile(resolve(dependencies.packageRoot, "package.json"), "utf8")) as typeof manifest;
  } catch {
    // Diagnosis below reports the unreadable package without granting it authority.
  }
  const ownershipPort = { getCommands: () => [...dependencies.commands] } as ParentPiPort;
  const collisions = assertCommandOwnership(ownershipPort, dependencies.packageRoot, dependencies.catalog);
  const ownerPaths = dependencies.commands
    .filter((command) => command.name.startsWith("ca-") || command.name.startsWith("skill:ca-"))
    .map((command) => command.sourceInfo.path);
  const verifiedVersions = Object.keys(dependencies.expansionFingerprints).sort();
  const expansionMatches = verifyNativeSkillExpansion(
    dependencies.runtime.piVersion,
    dependencies.expansionFingerprints,
    dependencies.expandSkill,
  );
  let bridgeHealthy = false;
  if (dependencies.bridgePrepared) {
    try {
      const response = await dependencies.bridge.call({
        version: 1,
        event: "before_agent_start",
        cwd: dependencies.context.cwd,
      }, dependencies.context.signal ?? new AbortController().signal);
      bridgeHealthy = response.outcome !== "block" && response.ruleId !== "PI-BRIDGE";
    } catch {
      bridgeHealthy = false;
    }
  }
  const toolSources = Object.fromEntries(dependencies.allTools.map((tool) => [tool.name, tool.sourceInfo.path]));
  let projectTrusted = false;
  try {
    projectTrusted = dependencies.context.isProjectTrusted?.() === true;
  } catch {
    // A missing or failing host trust signal is never affirmative authorization.
  }
  return {
    package: {
      root: dependencies.packageRoot,
      name: typeof manifest.name === "string" ? manifest.name : "",
      version: typeof manifest.version === "string" ? manifest.version : "",
      extensionPath: dependencies.extensionPath,
      scope: dependencies.packageScope,
      declared: Array.isArray(manifest.pi?.extensions)
        && manifest.pi.extensions.includes("./extensions/codearbiter.js"),
    },
    trust: {
      inspected: true,
      projectTrusted,
      required: dependencies.projectTrustRequired,
    },
    runtime: dependencies.runtime,
    core: {
      present: existsSync(resolve(dependencies.packageRoot, "hooks", "pi-bridge.py")),
      bridgeScript: resolve(dependencies.packageRoot, "hooks", "pi-bridge.py"),
    },
    commands: { collisions, ownerPaths, expansionVerifiedVersions: verifiedVersions, expansionMatches },
    bridge: { healthy: bridgeHealthy },
    child: {
      present: existsSync(dependencies.childPath),
      artifact: await inspectChildArtifact(
        dependencies.childPath,
        dependencies.childFingerprint,
      ),
      path: dependencies.childPath,
    },
    ambientMarker: { present: process.env.CODEARBITER_SUBAGENT === "1", validatedChild: false },
    moduleIdentity: { selfConsistent: true },
    finalArguments: {
      verified: true,
      wrapperSourcePath: dependencies.wrapperSourcePath,
      activeTools: dependencies.activeTools,
      toolSources,
    },
  };
}

const REMEDIATION = {
  package: "Reinstall ca-pi from the approved pinned Git tag, then restart Pi.",
  trust: "Run /trust in Pi, inspect the project, grant trust only if you accept it, then start a new session.",
  version: "Upgrade Pi to 0.80.5 or 0.80.10 and Node to >=22.19.0, then restart Pi.",
  python: "Upgrade or install Python 3, then run /ca-doctor again.",
  core: "Reinstall ca-pi to restore the generated shared core, then run /ca-doctor again.",
  commands: "Remove conflicting command owners or run Pi 0.80.5/0.80.10, then restart Pi and run /ca-doctor.",
  bridge: "Reinstall ca-pi and Python 3, then run /ca-doctor again.",
  child: "Reinstall ca-pi if the hardened child artifact is missing or tampered, then run /ca-doctor again.",
  "ambient-marker": "Remove CODEARBITER_SUBAGENT from the parent environment and restart Pi.",
  "module-identity": "Reinstall the active Pi CLI and ca-pi from their approved origins, then restart Pi.",
  "final-arguments": "Reinstall ca-pi, remove competing mutating tool definitions, and run /ca-doctor again.",
  "active-dispatch": "Require passing supported-version real-host promotion/CI evidence before closing PI-AC-28.",
} as const;

function diagnosis(
  id: keyof typeof REMEDIATION,
  healthy: boolean,
  healthyMessage: string,
  unhealthyMessage: string,
): Diagnosis {
  return {
    id,
    state: healthy ? "healthy" : "unhealthy",
    message: healthy ? healthyMessage : unhealthyMessage,
    remediation: REMEDIATION[id],
  };
}

function canonical(path: string): string {
  try { return realpathSync.native(path); } catch { return resolve(path); }
}

function samePath(left: string, right: string): boolean {
  const a = canonical(left);
  const b = canonical(right);
  return process.platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b;
}

function inside(path: string, root: string): boolean {
  const suffix = relative(canonical(root), canonical(path));
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

export function diagnosePi(input: PiDoctorInput): readonly Diagnosis[] {
  const expectedExtension = resolve(input.package.root, "extensions", "codearbiter.js");
  const packageHealthy = input.package.declared && input.package.name === "ca-pi"
    && existsSync(input.package.root) && existsSync(input.package.extensionPath)
    && samePath(input.package.extensionPath, expectedExtension)
    && inside(input.package.extensionPath, input.package.root);
  const trustHealthy = input.trust.inspected && (!input.trust.required || input.trust.projectTrusted);
  const waitingForTrust = input.trust.required && !input.trust.projectTrusted;
  const versionHealthy = ["0.80.5", "0.80.10"].includes(input.runtime.piVersion)
    && versionAtLeast(input.runtime.nodeVersion, [22, 19, 0]);
  const piBelowMinimum = !versionAtLeast(input.runtime.piVersion, [0, 80, 5]);
  const supportedExpansion = input.commands.expansionVerifiedVersions.includes(input.runtime.piVersion);
  const expectedDoctorSkill = resolve(input.package.root, "skills", "ca-doctor", "SKILL.md");
  const ownerPathsHealthy = input.commands.ownerPaths.length > 0
    && input.commands.ownerPaths.every((path) => inside(path, input.package.root))
    && input.commands.ownerPaths.some((path) => samePath(path, expectedExtension))
    && input.commands.ownerPaths.some((path) => samePath(path, expectedDoctorSkill));
  const commandsHealthy = input.commands.collisions.length === 0
    && ownerPathsHealthy
    && input.commands.expansionMatches
    && (piBelowMinimum || supportedExpansion);
  const childPathHealthy = samePath(
    input.child.path,
    resolve(input.package.root, "extensions", "codearbiter-child.js"),
  ) && inside(input.child.path, input.package.root) && existsSync(input.child.path);
  const coreHealthy = input.core.present
    && existsSync(input.core.bridgeScript)
    && samePath(input.core.bridgeScript, resolve(input.package.root, "hooks", "pi-bridge.py"))
    && inside(input.core.bridgeScript, input.package.root);
  const runtimeIdentityHealthy = existsSync(input.runtime.cliEntry)
    && existsSync(input.runtime.moduleEntry)
    && inside(input.runtime.cliEntry, input.runtime.packageRoot)
    && inside(input.runtime.moduleEntry, input.runtime.packageRoot)
    && samePath(input.runtime.cliEntry, resolve(input.runtime.packageRoot, "dist", "cli.js"))
    && samePath(input.runtime.moduleEntry, resolve(input.runtime.packageRoot, "dist", "index.js"));
  const mutators = ["bash", "write", "edit"];
  const wrapperHealthy = input.finalArguments.wrapperSourcePath !== undefined
    && existsSync(input.finalArguments.wrapperSourcePath)
    && samePath(input.finalArguments.wrapperSourcePath, expectedExtension)
    && mutators.every((name) => input.finalArguments.activeTools?.includes(name) === true)
    && mutators.every((name) => {
      const path = input.finalArguments.toolSources?.[name];
      return path !== undefined && samePath(path, expectedExtension);
    });
  const ambientHealthy = !input.ambientMarker.present || input.ambientMarker.validatedChild;

  return [
    diagnosis(
      "package",
      packageHealthy,
      `${input.package.name} ${input.package.version} is active from ${input.package.root} as a ${input.package.scope} package.`,
      "The active ca-pi package is missing, undeclared, or has the wrong package identity.",
    ),
    diagnosis(
      "trust",
      trustHealthy,
      input.trust.projectTrusted
        ? "Pi reports the project as trusted after operator inspection. codeArbiter inspected trust state and did not grant it."
        : "Pi trust state was inspected and the repository is dormant, so no repository-aware startup is authorized or required.",
      "The arbiter-enabled project requires affirmative Pi trust before codeArbiter may perform repository-aware startup.",
    ),
    diagnosis(
      "version",
      versionHealthy,
      `Pi ${input.runtime.piVersion}, Node ${input.runtime.nodeVersion}, and the supported runtime floor are compatible.`,
      `Pi ${input.runtime.piVersion} or Node ${input.runtime.nodeVersion} is outside the supported runtime contract.`,
    ),
    waitingForTrust
      ? {
          id: "python",
          state: "degraded",
          message: "Python resolution was intentionally skipped until Pi reports affirmative project trust.",
          remediation: REMEDIATION.trust,
        }
      : diagnosis(
          "python",
          input.runtime.pythonMajor === 3,
          "Python 3 is available to the Pi bridge.",
          "The Pi bridge did not resolve a supported Python 3 interpreter.",
        ),
    diagnosis(
      "core",
      coreHealthy,
      `The generated shared Python core is present with bridge ${input.core.bridgeScript}.`,
      "The generated shared Python core or Pi bridge entry is missing.",
    ),
    diagnosis(
      "commands",
      commandsHealthy,
      `Command ownership is exact and DECISION-0018 native-equivalent expansion matches Pi ${input.commands.expansionVerifiedVersions.join(", ")}.`,
      "Command ownership collides or DECISION-0018 native-equivalent alias expansion has drifted for the active Pi version.",
    ),
    waitingForTrust
      ? {
          id: "bridge",
          state: "degraded",
          message: "The repository-aware bridge probe was intentionally skipped until Pi reports affirmative project trust.",
          remediation: REMEDIATION.trust,
        }
      : diagnosis(
          "bridge",
          input.bridge.healthy,
          "The bounded canonical Python bridge is healthy.",
          "The bounded canonical Python bridge failed its health check.",
        ),
    diagnosis(
      "child",
      input.child.present && input.child.artifact === "enforced" && childPathHealthy,
      `The exact hardened child enforcement artifact is present at ${input.child.path}.`,
      "The child artifact is missing, foreign, tampered, or lacks independently verified enforcement evidence.",
    ),
    diagnosis(
      "ambient-marker",
      ambientHealthy,
      "No unvalidated ambient CODEARBITER_SUBAGENT marker is active.",
      "CODEARBITER_SUBAGENT is present outside a validated child launch.",
    ),
    diagnosis(
      "module-identity",
      runtimeIdentityHealthy,
      `Active Pi CLI ${input.runtime.cliEntry}; module ${input.runtime.moduleEntry}; package ${input.runtime.packageRoot}; `
        + `version ${input.runtime.piVersion}. Module identity is self-consistent with the operator-launched Pi runtime; `
        + "this does not prove publisher authenticity.",
      "The active CLI, imported Pi module, package root, and reported version are not self-consistent.",
    ),
    waitingForTrust
      ? {
          id: "final-arguments",
          state: "degraded",
          message: "Final-execution wrapper installation and live verification were intentionally skipped until Pi reports affirmative project trust.",
          remediation: REMEDIATION.trust,
        }
      : diagnosis(
          "final-arguments",
          wrapperHealthy,
          "The active final-execution wrappers govern the arguments that reach Pi's built-in mutators.",
          "Final governed arguments or wrapper ownership could not be verified.",
        ),
    {
      id: "active-dispatch",
      state: "degraded",
      message: "Supported Pi 0.80.5/0.80.10 public extension APIs cannot submit this deterministic self-test through the active dispatcher; the wrapper self-test does not exercise active dispatch.",
      remediation: REMEDIATION["active-dispatch"],
    },
  ];
}

export interface PiWrapperSelfTestDependencies {
  enabled: boolean;
  projectTrusted?: boolean;
  executeBash(input: { command: string }): Promise<unknown>;
}

export async function runPiWrapperSelfTest(dependencies: PiWrapperSelfTestDependencies): Promise<Diagnosis> {
  const remediation = "Run /ca-doctor again in an arbiter-enabled repository after restoring or upgrading Pi/ca-pi.";
  if (!dependencies.enabled) {
    return {
      id: "wrapper-self-test",
      state: "degraded",
      message: "The repository is not arbiter-enabled, so the H-03 wrapper self-test was skipped.",
      remediation,
    };
  }
  if (dependencies.projectTrusted === false) {
    return {
      id: "wrapper-self-test",
      state: "degraded",
      message: "The H-03 wrapper self-test was skipped because the arbiter-enabled project has not received affirmative Pi project trust.",
      remediation: REMEDIATION.trust,
    };
  }
  try {
    await dependencies.executeBash({ command: "git add --all --dry-run" });
    return {
      id: "wrapper-self-test",
      state: "unhealthy",
      message: "The wrapper self-test command executed; the stored governed Pi bash wrapper did not return the exact H-03 block.",
      remediation,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/^BLOCKED \[H-03\](?::|$)/u.test(message)) {
      return {
        id: "wrapper-self-test",
        state: "healthy",
        message: "The stored governed Pi bash wrapper returned the exact shared-core H-03 block for git add --all --dry-run; no staging occurred.",
        remediation,
      };
    }
    return {
      id: "wrapper-self-test",
      state: "unhealthy",
      message: "The stored governed Pi bash wrapper did not return the exact shared-core H-03 block.",
      remediation,
    };
  }
}

export function formatPiDoctorReport(diagnoses: readonly Diagnosis[]): string {
  const lines = diagnoses.flatMap((row) => [
    `${row.state.toUpperCase()}  ${row.id}: ${row.message}`,
    ...(row.state === "healthy" ? [] : [`REMEDIATION  ${row.id}: ${row.remediation}`]),
  ]);
  const unhealthy = diagnoses.filter((row) => row.state === "unhealthy").length;
  const degraded = diagnoses.filter((row) => row.state === "degraded").length;
  const verdict = unhealthy > 0 ? "UNHEALTHY" : degraded > 0 ? "DEGRADED" : "HEALTHY";
  return [...lines, `doctor: ${verdict}`].join("\n");
}
