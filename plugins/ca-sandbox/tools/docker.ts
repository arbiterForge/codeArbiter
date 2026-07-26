/**
 * docker.ts — ca-sandbox's single docker-primitive module (architecture-007).
 *
 * The ONE place that defines the Windows/Git-Bash env guard, the default
 * async docker runner, and the `{code,stdout,stderr}` result shape.
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
import { spawn, type SpawnOptions } from "node:child_process";

// On Windows + Git Bash, container paths / label / `-e` values handed to docker
// get mangled by MSYS path conversion; MSYS_NO_PATHCONV=1 disables it (Spike
// A/B). Defined ONCE here; every module imports this constant rather than
// re-spreading process.env itself.
export const DOCKER_ENV: NodeJS.ProcessEnv = { ...process.env, MSYS_NO_PATHCONV: "1" };

/**
 * The one result shape every docker invocation in this plugin returns.
 *
 * `timedOut` (#394) is what makes a deadline actionable: a plain `{code: 1}` is
 * what an ordinary docker failure looks like, and a caller that cannot tell a
 * hang from a failure cannot escalate — escalation being the whole point for
 * `docker exec`.
 *
 * `aborted` and `overflowed` (#479) exist for the same reason, and they cannot
 * be derived from the close event. An async `spawn` reports EVERY kill as
 * `close(null, "SIGKILL")`, so a deadline kill, a cancellation, and an
 * output-cap kill are indistinguishable after the fact. The runner therefore
 * records WHICH killer fired, before killing, and maps from that.
 *
 * Distinguishing abort from timeout is not cosmetic: a timeout means the
 * operation is wedged and its container should be torn down, while an abort
 * means the OPERATOR asked to stop and the same teardown runs for a different
 * reason. Reporting one as the other would put "timed out" in an audit trail
 * for a deliberate Ctrl-C.
 */
export type RunResult = {
  code: number;
  stdout: string;
  stderr: string;
  timedOut?: boolean;
  aborted?: boolean;
  overflowed?: boolean;
};

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

/** Conventional shell exit code for "terminated by SIGINT" (128 + 2). #479. */
export const DOCKER_ABORT_EXIT_CODE = 130;

/**
 * Output cap for one docker invocation (#479).
 *
 * `spawnSync` took a `maxBuffer` and threw past it; async `spawn` has no such
 * option, so the cap has to live here or not exist. It is a BACKSTOP against an
 * unbounded in-container writer eating host memory, deliberately generous: a
 * caller with a real bound of its own (exec.ts's `capBytes`) stays the
 * authoritative, deterministic limit, and this only fires when nothing else
 * would.
 *
 * Note that the old path mis-classified this: `spawnSync` killed the child on a
 * maxBuffer breach, which surfaced as `status === null` with a signal — the same
 * shape the deadline check read — so an output overflow reported itself as a
 * TIMEOUT, with exit 124 and a "timed out" message. Typed separately now.
 */
export const DEFAULT_DOCKER_MAX_BUFFER = 64 * 1024 * 1024;

/** Options for the bounded runner; `spawn` is a test seam, never production. */
export type DockerRunOptions = {
  /** Override the per-operation deadline (tests, and callers with context). */
  timeoutMs?: number;
  /** Injectable spawn, so the deadline itself is assertable without a daemon. */
  spawn?: typeof spawn;
  /** Override the output backstop; see DEFAULT_DOCKER_MAX_BUFFER. */
  maxBuffer?: number;
};

/**
 * Per-CALL options, distinct from per-runner options (#479).
 *
 * The signal belongs to the invocation, not to the runner: one runner is built
 * once per command module and then used for several docker calls, and a
 * cancellation has to reach whichever call is in flight right now.
 */
export type DockerCallOptions = {
  /** Fires cancellation at the child; see runDocker for what that guarantees. */
  signal?: AbortSignal;
};

/** An injectable docker runner — the seam every command module's tests use. */
export type DockerRun = (args: string[], call?: DockerCallOptions) => Promise<RunResult>;

/**
 * The actual async `spawn("docker", ...)`, shared by every default runner.
 *
 * #479: this was `spawnSync`, which is uninterruptible BY CONSTRUCTION. A
 * deadline could be set on it — #394 did that — but nothing could interrupt the
 * call once in flight, because the calling thread sits inside the syscall and
 * there is no point at which an AbortSignal could be observed. Shipping a
 * deadline that LOOKS cancellable and is not would be worse than the honest gap,
 * so #394 stated it and this closes it.
 *
 * Three kills are possible and all three arrive as `close(null, "SIGKILL")`, so
 * `killedBy` is recorded before the kill rather than inferred after it.
 *
 * `extra` carries genuine spawn options; the output cap moved OUT of it into
 * `options.maxBuffer`, because `maxBuffer` is a `spawnSync`/`execFile` concept
 * that async `spawn` does not have.
 */
function runDocker(
  args: string[],
  extra: Partial<SpawnOptions> = {},
  options: DockerRunOptions = {},
  call: DockerCallOptions = {},
): Promise<RunResult> {
  const timeout = options.timeoutMs ?? timeoutForArgs(args);
  const spawnFn = options.spawn ?? spawn;
  const maxBuffer = options.maxBuffer ?? DEFAULT_DOCKER_MAX_BUFFER;
  const signal = call.signal;
  const label = `docker ${args[0] ?? ""}`;

  // An ALREADY-aborted signal must not start a container at all. Checking only
  // after the spawn would still create the next container in a multi-step
  // command that was cancelled mid-way, and teardown would then have something
  // to reclaim that the caller never knew existed.
  if (signal?.aborted) {
    return Promise.resolve({
      code: DOCKER_ABORT_EXIT_CODE,
      stdout: "",
      stderr: `ca-sandbox: \`${label}\` was cancelled before it started (issue #479).`,
      aborted: true,
    });
  }

  return new Promise<RunResult>((resolve) => {
    // A launch failure must be a RESULT, not a rejection. `spawnSync` reported
    // one through `r.error` and the old runner mapped it to `{code: 1}`; async
    // `spawn` normally emits an `error` event, but an invalid argument, a bad
    // `cwd`, or a blocked exec can still throw straight out of `spawn()`. A
    // throw inside a Promise executor rejects, and nothing in this driver
    // catches - so an unusable docker would surface as an unhandled rejection
    // rather than the `{code: 1}` every caller is written against.
    let child;
    try {
      child = spawnFn("docker", args, { env: DOCKER_ENV, ...extra });
    } catch (e) {
      resolve({ code: 1, stdout: "", stderr: String(e) });
      return;
    }
    let stdout = "";
    let stderr = "";
    let bytes = 0;
    let killedBy: "timeout" | "abort" | "overflow" | undefined;
    let settled = false;

    const kill = (why: "timeout" | "abort" | "overflow") => {
      // First killer wins: a deadline that fires while an abort is already
      // tearing the child down must not relabel the outcome.
      if (killedBy !== undefined) return;
      killedBy = why;
      try {
        child.kill("SIGKILL");
      } catch {
        /* already gone */
      }
    };

    const collect = (which: "out" | "err") => (chunk: unknown) => {
      const text = String(chunk);
      bytes += Buffer.byteLength(text);
      if (bytes > maxBuffer) {
        kill("overflow");
        return;
      }
      if (which === "out") stdout += text;
      else stderr += text;
    };

    child.stdout?.setEncoding?.("utf8");
    child.stderr?.setEncoding?.("utf8");
    child.stdout?.on("data", collect("out"));
    child.stderr?.on("data", collect("err"));

    const timer = setTimeout(() => kill("timeout"), timeout);
    // `unref` so a pending deadline cannot hold the process open past a call
    // that already finished.
    timer.unref?.();
    const onAbort = () => kill("abort");
    signal?.addEventListener?.("abort", onAbort, { once: true });

    const settle = (r: RunResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener?.("abort", onAbort);
      resolve(r);
    };

    child.on("error", (e: unknown) =>
      settle({ code: 1, stdout: "", stderr: String(e) }));

    child.on("close", (code: number | null) => {
      if (killedBy === "timeout") {
        settle({
          code: DOCKER_TIMEOUT_EXIT_CODE,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` timed out after ${timeout}ms `
            + "and was killed (issue #394).",
          timedOut: true,
        });
        return;
      }
      if (killedBy === "abort") {
        settle({
          code: DOCKER_ABORT_EXIT_CODE,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` was cancelled and killed (issue #479).`,
          aborted: true,
        });
        return;
      }
      if (killedBy === "overflow") {
        settle({
          code: 1,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` exceeded the ${maxBuffer}-byte `
            + "output cap and was killed (issue #479).",
          overflowed: true,
        });
        return;
      }
      settle({ code: code ?? 1, stdout, stderr });
    });
  });
}

/**
 * The default docker runner every command module falls back to when no
 * `dockerRun` is injected. `spawn("docker", args, { env: DOCKER_ENV })` — no
 * extra spawn options.
 */
export function defaultDockerRun(args: string[], call: DockerCallOptions = {}): Promise<RunResult> {
  return runDocker(args, {}, {}, call);
}

/**
 * Build a docker runner with additional spawn options layered on top of the
 * shared env default.
 *
 * The output cap is `options.maxBuffer`, NOT part of `extra` — async `spawn` has
 * no `maxBuffer`, so a caller that kept passing it inside the spawn options bag
 * would have silently lost its bound. Callers whose in-container output is large
 * (exec.ts) raise the backstop here while their own `capBytes` stays the
 * authoritative, deterministic limit.
 */
export function makeDockerRun(
  extra: Partial<SpawnOptions>,
  options: DockerRunOptions = {},
): DockerRun {
  return (args, call) => runDocker(args, extra, options, call);
}
