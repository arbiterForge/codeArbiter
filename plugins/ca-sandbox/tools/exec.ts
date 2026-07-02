/**
 * exec.ts — ca-sandbox in-container command exec (T-11, covers AC-09).
 *
 * execInSandbox(id, argv) wraps `docker exec`, captures stdout and stderr
 * SEPARATELY, and returns a stable JSON contract:
 *
 *   { id, exitCode, stdout, stderr, durationMs, truncated }
 *
 * This is the programmatic exec seam the CLI (`sandbox exec <id> -- <argv>`,
 * T-15) and a future farm `item-3` integration drive. Two design rules carried
 * over from farm.ts:
 *
 *   - SEPARATE streams (farm's RunResult shape, FINDING/#91): stdout and stderr
 *     are never merged. A wrapped exec whose output is parsed downstream must be
 *     able to read clean stdout; on Windows + Git Bash a docker/MSYS warning
 *     line on stderr must never leak into stdout. We keep them apart.
 *
 *   - A BYTE CAP per stream (farm's `capInjected` discipline / AC-05): the
 *     output of untrusted in-container code is bounded so a runaway/abusive
 *     command cannot flood the host process. Each stream is capped INDEPENDENTLY
 *     in UTF-8 bytes on a code-point boundary; exceeding EITHER cap sets
 *     `truncated:true`. The default (1 MiB/stream) is generous for interactive
 *     use yet bounded.
 *
 * Process/shell handling routes through docker.ts (architecture-007): a
 * spawnSync-based docker runner (injectable for unit tests), and on Windows +
 * Git Bash MSYS_NO_PATHCONV=1 is set so container paths / `-e` values handed to
 * docker are not mangled (Spike A/B). docker exec is run NON-interactively (no
 * `-it`) so a wrapped call never blocks on a tty.
 */
import { makeDockerRun, type RunResult } from "./docker.ts";

/**
 * Default per-stream output cap in bytes (1 MiB). Bounds the host-side capture
 * of untrusted in-container output. Override per call via ExecOptions.maxBytes;
 * or globally via CA_SANDBOX_EXEC_MAX_BYTES. Applied SEPARATELY to stdout and to
 * stderr (mirrors farm's bounded-context discipline).
 */
export const DEFAULT_EXEC_MAX_BYTES = Number(
  process.env.CA_SANDBOX_EXEC_MAX_BYTES ?? 1024 * 1024,
);

/** Raw result of a spawned docker process — farm's RunResult shape (separate streams). */
export type { RunResult };

/**
 * The exec JSON contract (AC-09). `exitCode` is the in-container command's exit
 * status; `stdout`/`stderr` are the captured streams (each ≤ the byte cap);
 * `durationMs` is the wall-clock exec time; `truncated` is true iff EITHER
 * stream was clipped by the cap.
 */
export type ExecResult = {
  id: string;
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
  truncated: boolean;
};

export type ExecOptions = {
  /** Per-stream byte cap; defaults to DEFAULT_EXEC_MAX_BYTES. */
  maxBytes?: number;
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: (args: string[]) => RunResult;
};

// maxBuffer is set high so spawnSync itself does not throw on large output;
// our own byte cap (capBytes) is the authoritative, deterministic bound.
const defaultDockerRun = makeDockerRun({ maxBuffer: 256 * 1024 * 1024 });

/**
 * Assemble the `docker exec` argv (everything AFTER `docker`). Pure: builds the
 * array, runs nothing — so the wrapping is unit-testable without real docker.
 * The user `argv` is appended verbatim after the container id; exec runs
 * NON-interactively (no `-it`) so a wrapped call cannot block on a tty.
 *
 * @throws if `id` is empty or `argv` is empty (an exec must have both).
 */
export function buildExecArgs(id: string, argv: string[]): string[] {
  if (!id) throw new Error("ca-sandbox: execInSandbox requires a non-empty container id");
  if (!argv || argv.length === 0)
    throw new Error("ca-sandbox: execInSandbox requires a non-empty command argv");
  return ["exec", id, ...argv];
}

/**
 * Deterministically cap a captured stream to `maxBytes` UTF-8 bytes on a
 * code-point boundary, mirroring farm's `capInjected` truncation discipline.
 * Returns the (possibly clipped) string and whether it was clipped. A naive
 * `string.slice` counts UTF-16 units (wrong for the byte budget) and a naive
 * `Buffer.subarray` can split a multi-byte code point (mojibake); decoding the
 * subarray and re-encoding yields the longest valid-UTF-8 prefix within budget.
 */
function capBytes(s: string, maxBytes: number): { value: string; truncated: boolean } {
  const buf = Buffer.from(s, "utf8");
  if (buf.length <= maxBytes) return { value: s, truncated: false };
  // Decode the byte-budget prefix; Node's UTF-8 decoder drops a trailing
  // partial code unit, so the result is the longest valid prefix that fits.
  let value = buf.subarray(0, maxBytes).toString("utf8");
  // Defensive: a lone replacement char from a split code point could push the
  // re-encoded length over budget; trim it back if so.
  while (Buffer.byteLength(value, "utf8") > maxBytes && value.length > 0) {
    value = value.slice(0, -1);
  }
  return { value, truncated: true };
}

/**
 * Run `argv` inside the sandbox container `id` via `docker exec`, capturing
 * stdout and stderr separately, each bounded by the per-stream byte cap. Returns
 * the ExecResult JSON contract (AC-09). Synchronous (spawnSync) so the seam is
 * trivially callable from a CLI dispatch and from a vitest.
 *
 * @param id the running sandbox container id.
 * @param argv the command + args to run inside the box (e.g. ["sh","-c","exit 7"]).
 * @param opts optional per-stream cap / injectable docker runner.
 * @returns { id, exitCode, stdout, stderr, durationMs, truncated }.
 */
export function execInSandbox(id: string, argv: string[], opts: ExecOptions = {}): ExecResult {
  const args = buildExecArgs(id, argv);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const maxBytes = opts.maxBytes ?? DEFAULT_EXEC_MAX_BYTES;

  const start = Date.now();
  const r = dockerRun(args);
  const durationMs = Date.now() - start;

  // Cap each stream INDEPENDENTLY (a huge stdout must not steal stderr's budget).
  const out = capBytes(r.stdout, maxBytes);
  const err = capBytes(r.stderr, maxBytes);

  return {
    id,
    exitCode: r.code,
    stdout: out.value,
    stderr: err.value,
    durationMs,
    truncated: out.truncated || err.truncated,
  };
}
