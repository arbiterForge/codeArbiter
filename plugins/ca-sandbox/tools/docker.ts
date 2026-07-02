/**
 * docker.ts — ca-sandbox's single docker-primitive module (architecture-007).
 *
 * The ONE place that defines the Windows/Git-Bash env guard, the default
 * spawnSync-based docker runner, and the `{code,stdout,stderr}` result shape.
 * Mirrors `plugins/ca/tools/exec.ts`'s "every spawn routes through here"
 * discipline: build.ts, claude-inside.ts, cli.ts, cp.ts, create.ts, exec.ts,
 * registry.ts, and run.ts all import from here instead of each hand-rolling
 * their own copy — previously the guard and the runner were pasted verbatim
 * into every one of those modules (and the result shape recurred under three
 * names: `RunResult`, `ClaudeRunResult`, `DockerResult`), so a fix to one could
 * silently miss the other seven. This is a behavior-preserving extraction: no
 * call site's observable behavior changes.
 *
 * The injectable-runner seam every command module exposes (`opts.dockerRun`)
 * is unaffected — this module only supplies the DEFAULT implementation tests
 * override.
 */
import { spawnSync, type SpawnSyncOptionsWithStringEncoding } from "node:child_process";

// On Windows + Git Bash, container paths / label / `-e` values handed to docker
// get mangled by MSYS path conversion; MSYS_NO_PATHCONV=1 disables it (Spike
// A/B). Defined ONCE here; every module imports this constant rather than
// re-spreading process.env itself.
export const DOCKER_ENV: NodeJS.ProcessEnv = { ...process.env, MSYS_NO_PATHCONV: "1" };

/** The one result shape every docker invocation in this plugin returns. */
export type RunResult = { code: number; stdout: string; stderr: string };

/** An injectable docker runner — the seam every command module's tests use. */
export type DockerRun = (args: string[]) => RunResult;

/**
 * The actual spawnSync("docker", ...) call, shared by every default runner.
 * `extra` lets a caller (e.g. exec.ts, which captures large in-container
 * output) widen spawnSync's own options — such as maxBuffer — without forking
 * a second copy of the env-guard / result-mapping logic.
 */
function runDocker(
  args: string[],
  extra: Partial<SpawnSyncOptionsWithStringEncoding> = {},
): RunResult {
  const r = spawnSync("docker", args, { encoding: "utf8", env: DOCKER_ENV, ...extra });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : ""),
  };
}

/**
 * The default docker runner every command module falls back to when no
 * `dockerRun` is injected. `spawnSync("docker", args, { encoding: "utf8", env:
 * DOCKER_ENV })` — no extra spawnSync options.
 */
export function defaultDockerRun(args: string[]): RunResult {
  return runDocker(args);
}

/**
 * Build a docker runner with additional spawnSync options layered on top of
 * the shared env/encoding defaults. Used by exec.ts, whose captured
 * in-container output needs a much larger `maxBuffer` than the plain default
 * (spawnSync's own internal cap would otherwise throw on a large stream, where
 * exec.ts's own `capBytes` is meant to be the authoritative, deterministic
 * bound instead).
 */
export function makeDockerRun(extra: Partial<SpawnSyncOptionsWithStringEncoding>): DockerRun {
  return (args) => runDocker(args, extra);
}
