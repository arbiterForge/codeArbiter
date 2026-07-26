/**
 * claude-inside-cli.ts — the shipped entry point for `--with-claude` (#377).
 *
 * WHY THIS IS A SEPARATE BINARY, not a `sandbox` subcommand.
 *
 * This starts a container holding a LIVE Claude Code OAuth token. The
 * `sandbox-claude-inside` skill wraps that in five BLOCK gates: posture, image,
 * token, run, teardown. Wiring it into `sandbox.js` as `sandbox with-claude`
 * would let anyone start a token-bearing box with one ungated command, which
 * turns those gates from enforcement into advice.
 *
 * So it ships as its own artifact. The routine is the only sanctioned caller,
 * and reaching for it directly is a deliberate act rather than a subcommand
 * someone finds in `--help`. The cost is a second declared payload artifact and
 * its own CI staleness gate, which is the trade the maintainer chose.
 *
 * WHY IT EXISTS AT ALL. Before this, the feature was documented and had no
 * shipped code path whatsoever: `runClaudeInside` had zero callers, so esbuild
 * tree-shook it out of `sandbox.js` entirely (`grep -c runClaudeInside
 * sandbox.js` was 0). The skill told an operator to call TypeScript that no
 * install contained.
 *
 * THE TOKEN NEVER TOUCHES ARGV. It is read from the environment only. A process
 * argument list is world-readable on every platform this runs on (`ps`,
 * /proc/<pid>/cmdline, Windows WMI), so a `--token` flag would publish the
 * credential to every other process on the box. security-controls.md's approved
 * access method for CLAUDE_CODE_OAUTH_TOKEN is env-injection, and this is that
 * rule at the CLI boundary.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  TOKEN_ENV_VAR,
  TokenCoMountRejectedError,
  runClaudeInside,
  type ClaudeNetPolicy,
  type ClaudeRunOptions,
} from "./claude-inside.ts";
import { defaultDockerRun, type RunResult } from "./docker.ts";

/** A usage error, mirroring cli.ts's exit-code contract. */
export const USAGE_ERROR_EXIT = 2;
/** The postures a token-bearing box may take. Never wide-open. */
const NET_POLICIES: readonly ClaudeNetPolicy[] = ["offline", "anthropic-only"];

export class ClaudeCliError extends Error {}

export type ParsedClaudeCli = {
  image: string;
  homeVolume: string;
  netPolicy: ClaudeNetPolicy;
};

/**
 * Parse argv (everything after the script). Pure: no env, no docker, no I/O, so
 * every refusal below is unit-testable.
 *
 * @throws ClaudeCliError on any usage problem.
 */
export function parseClaudeCli(argv: readonly string[]): ParsedClaudeCli {
  let image = "";
  let homeVolume = "";
  let netPolicy: ClaudeNetPolicy = "offline";

  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const value = () => {
      const v = argv[++i];
      if (v === undefined) throw new ClaudeCliError(`${flag} requires a value`);
      return v;
    };
    switch (flag) {
      case "--image": image = value(); break;
      case "--home-volume": homeVolume = value(); break;
      case "--net": {
        const v = value();
        if (!NET_POLICIES.includes(v as ClaudeNetPolicy)) {
          throw new ClaudeCliError(
            `--net must be one of ${NET_POLICIES.join(", ")} (got ${JSON.stringify(v)}). ` +
              `A token-bearing box never gets wide-open egress.`,
          );
        }
        netPolicy = v as ClaudeNetPolicy;
        break;
      }
      // The token is env-only, deliberately. Naming the flag explicitly gives a
      // better refusal than "unknown flag" to someone reaching for the obvious
      // thing, and states WHY rather than just no.
      case "--token":
        throw new ClaudeCliError(
          `--token is refused: a process argument list is world-readable, so passing a ` +
            `credential there publishes it to every process on the host. Set ${TOKEN_ENV_VAR} ` +
            `in the environment instead.`,
        );
      // The co-mount guard is structural in buildClaudeRunArgs; refusing the
      // flag here means the mistake is caught before a container is created.
      case "--source-volume":
        throw new ClaudeCliError(
          `--source-volume is refused: the token volume is NEVER co-mounted with an ` +
            `untrusted-code run (ADR-0007 / Spike B). Run the untrusted source in an ` +
            `ordinary sandbox instead.`,
        );
      default:
        throw new ClaudeCliError(`unknown argument ${JSON.stringify(flag)}`);
    }
  }

  if (!image) throw new ClaudeCliError("--image is required");
  if (!homeVolume) throw new ClaudeCliError("--home-volume is required");
  return { image, homeVolume, netPolicy };
}

export function usage(): string {
  return [
    "ca-sandbox claude-inside — start a Claude-Code-bearing sandbox box.",
    "",
    "  claude-inside --image <tag> --home-volume <name> [--net offline|anthropic-only]",
    "",
    `The OAuth token is read from ${TOKEN_ENV_VAR} in the environment. It is never`,
    "accepted on the command line: an argument list is world-readable.",
    "",
    "Sanctioned caller: the `sandbox-claude-inside` skill, whose five BLOCK gates",
    "(posture, image, token, run, teardown) are the reason this is not a",
    "`sandbox` subcommand.",
  ].join("\n");
}

export type ClaudeCliDeps = {
  dockerRun?: (args: string[]) => RunResult;
  run?: (opts: ClaudeRunOptions, dockerRun: (args: string[]) => RunResult) => string;
  stdout?: (line: string) => void;
  stderr?: (line: string) => void;
};

/**
 * Parse, check the token, start the box, print the container id. Returns a
 * process exit code and NEVER throws for an expected condition, mirroring
 * cli.ts's contract so a caller can rely on the code alone.
 */
export function runClaudeInsideCli(
  argv: readonly string[],
  env: NodeJS.ProcessEnv = process.env,
  deps: ClaudeCliDeps = {},
): number {
  const out = deps.stdout ?? ((l: string) => process.stdout.write(`${l}\n`));
  const err = deps.stderr ?? ((l: string) => process.stderr.write(`${l}\n`));

  let parsed: ParsedClaudeCli;
  try {
    parsed = parseClaudeCli(argv);
  } catch (e) {
    if (e instanceof ClaudeCliError) {
      err(`ca-sandbox: ${e.message}`);
      err(usage());
      return USAGE_ERROR_EXIT;
    }
    throw e;
  }

  const token = env[TOKEN_ENV_VAR];
  if (!token) {
    err(
      `ca-sandbox: ${TOKEN_ENV_VAR} is not set. The token is read from the environment ` +
        `and never from argv; see the sandbox-claude-inside skill for the approved store.`,
    );
    return USAGE_ERROR_EXIT;
  }

  try {
    const id = (deps.run ?? runClaudeInside)(
      { image: parsed.image, homeVolume: parsed.homeVolume, netPolicy: parsed.netPolicy, token },
      deps.dockerRun ?? defaultDockerRun,
    );
    out(id);
    return 0;
  } catch (e) {
    // The co-mount guard is the one refusal worth naming, because it is a
    // deliberate structural block rather than an operational failure.
    const prefix = e instanceof TokenCoMountRejectedError ? "co-mount refused" : "failed";
    // The message may carry docker's stderr. It never carries the token: the
    // token is only ever in the child's environment, never in argv or a message.
    err(`ca-sandbox: claude-inside ${prefix}: ${e instanceof Error ? e.message : String(e)}`);
    return 1;
  }
}

// Only execute when this file is the direct entry point (not when imported by
// unit tests). tsx/esbuild resolve import.meta.url correctly in both modes.
const _thisFile = fileURLToPath(import.meta.url);
const _entryFile = path.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  process.exit(runClaudeInsideCli(process.argv.slice(2)));
}
