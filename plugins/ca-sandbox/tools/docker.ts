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

/**
 * The one result shape every docker invocation in this plugin returns.
 *
 * `timedOut` (#394) is what makes a deadline actionable. spawnSync reports a
 * deadline kill through `error`/`signal`, and a plain `{code: 1}` is what an
 * ordinary docker failure looks like — a caller that cannot tell them apart
 * cannot escalate, and escalation is the whole point for `docker exec`.
 */
export type RunResult = { code: number; stdout: string; stderr: string; timedOut?: boolean };

/**
 * #394 — every docker invocation is bounded.
 *
 * The chokepoint below used to call `spawnSync("docker", ...)` with NO timeout.
 * An in-container `sleep infinity`, a wedged daemon, or a stalled build
 * therefore blocked the host process until something external killed it, and
 * untrusted repository code could deterministically wedge `sandbox exec`.
 * ca-sandbox is the driver that clones UNTRUSTED repositories into containers;
 * a hang it cannot escape is a control failure, not an inconvenience.
 *
 * The default is the bound for a plain client call — inspect, ps, rm, a label
 * query. Anything that legitimately takes minutes declares its own below.
 */
export const DEFAULT_DOCKER_TIMEOUT_MS = 120_000;

/**
 * Per-operation deadlines, keyed on the docker subcommand (`args[0]`).
 *
 * Deliberately generous where the work is genuinely long: a cold `build` or
 * `pull` over a slow network, and an `exec` that runs the user's own build
 * inside the box, are all legitimately slow. The bound exists so that "slow"
 * cannot become "never", not to second-guess how long real work takes. An
 * operation absent from this map takes DEFAULT_DOCKER_TIMEOUT_MS.
 */
export const DOCKER_OPERATION_TIMEOUTS_MS: Readonly<Record<string, number>> = Object.freeze({
  inspect: 30_000,
  ps: 30_000,
  images: 30_000,
  version: 30_000,
  info: 30_000,
  volume: 60_000,
  stop: 60_000,
  kill: 60_000,
  rm: 60_000,
  rmi: 120_000,
  network: 60_000,
  cp: 600_000,
  run: 900_000,
  create: 300_000,
  start: 300_000,
  exec: 1_800_000,
  build: 1_800_000,
  buildx: 1_800_000,
  pull: 1_800_000,
});

/** The deadline for `args`, chosen from its docker subcommand. */
export function timeoutForArgs(args: readonly string[]): number {
  return DOCKER_OPERATION_TIMEOUTS_MS[args[0] ?? ""] ?? DEFAULT_DOCKER_TIMEOUT_MS;
}

/** Conventional shell exit code for "killed by a timeout" (GNU `timeout`). */
export const DOCKER_TIMEOUT_EXIT_CODE = 124;

/** Options for the bounded runner; `spawn` is a test seam, never production. */
export type DockerRunOptions = {
  /** Override the per-operation deadline (tests, and callers with context). */
  timeoutMs?: number;
  /** Injectable spawn, so the deadline itself is assertable without a daemon. */
  spawn?: typeof spawnSync;
};

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
  options: DockerRunOptions = {},
): RunResult {
  const timeout = options.timeoutMs ?? timeoutForArgs(args);
  const spawn = options.spawn ?? spawnSync;
  // `timeout` + `killSignal` are the whole of the bound: spawnSync sends the
  // signal at the deadline and returns. `extra` is spread FIRST so a caller can
  // still widen maxBuffer, but cannot silently remove the deadline.
  const r = spawn("docker", args, {
    encoding: "utf8",
    env: DOCKER_ENV,
    ...extra,
    timeout,
    killSignal: "SIGKILL",
  });
  // A deadline kill surfaces as ETIMEDOUT (or, on some platforms, only as a
  // null status with a signal). Both are treated as the same typed outcome.
  const timedOut = (r.error as NodeJS.ErrnoException | undefined)?.code === "ETIMEDOUT"
    || (r.status === null && r.signal !== null && r.signal !== undefined);
  if (timedOut) {
    return {
      code: DOCKER_TIMEOUT_EXIT_CODE,
      stdout: r.stdout ?? "",
      stderr: `${r.stderr ?? ""}ca-sandbox: \`docker ${args[0] ?? ""}\` timed out after ${timeout}ms `
        + "and was killed (issue #394).",
      timedOut: true,
    };
  }
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
export function makeDockerRun(
  extra: Partial<SpawnSyncOptionsWithStringEncoding>,
  options: DockerRunOptions = {},
): DockerRun {
  return (args) => runDocker(args, extra, options);
}
