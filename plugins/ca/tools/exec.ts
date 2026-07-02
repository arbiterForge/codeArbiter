/**
 * exec.ts — codeArbiter's low-level process / shell execution layer.
 *
 * The shared, domain-free primitives that spawn child processes under the
 * farm's least-privilege discipline (secret-scrubbed env, per-command
 * wall-clock timeout, cross-platform tree-kill), the gate shell config, and the
 * single worktree-file reader. Extracted verbatim from farm.ts (v2.rev.0020 /
 * architecture-003) so the mutation engine can reuse them WITHOUT importing
 * farm.ts — the dependency graph stays one-way (farm.ts -> exec.ts and
 * mutation.ts -> exec.ts, never back). This is a move, not a rewrite: behaviour
 * is identical to the prior in-farm.ts definitions.
 */
import { spawn, type SpawnOptionsWithoutStdio } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Result of a spawned process. `out` stays the merged stdout+stderr string that
// existing consumers (runGate, diagnostics) read. `stdout`/`stderr` are kept
// SEPARATE so parsing contexts (checkDrift — #91) read only stdout: on Windows
// with core.safecrlf, git writes a `warning: ... LF will be replaced by CRLF`
// line to stderr that, when merged, was parsed as a changed file path and tripped
// a false `drift:` escalation. `timedOut` is set when a per-command wall-clock
// timeout fired and the child was killed (T-06 / reliability-001) — consumers
// surface it as a gate/setup/mutation failure rather than a clean exit.
export type RunResult = { code: number; out: string; stdout: string; stderr: string; timedOut?: true };

// gate shell — pure determinism, no model. Use a non-login shell (`-c`, not
// `-lc`) so user dotfiles don't bleed in. On Windows, fall back to cmd.exe /c.
export const [SHELL_BIN, SHELL_FLAG] =
  process.platform === "win32" ? ["cmd.exe", "/c"] : ["bash", "-c"];
// Node's default arg-quoting backslash-escapes embedded quotes, which cmd.exe
// does not understand — a gate like `node -e "process.exit(1)"` silently
// mangles. Pass the command line through verbatim on Windows.
export const SHELL_OPTS =
  process.platform === "win32" ? { windowsVerbatimArguments: true } : {};

// reliability-014: a single hardened numeric-env reader shared by farm.ts and
// mutation.ts (every FARM_*/MUT_* numeric knob routes through here). Plain
// `Number(process.env.X ?? default)` silently yields NaN on a typo (e.g.
// FARM_CONCURRENCY="four"), and NaN reads FALSE in every safety comparison
// built on it — the concurrency cap (`running.size >= ENV.concurrency`), the
// escalation-rate circuit breaker, and retry limits all silently disable with
// zero signal. Falls back to the default LOUDLY (stderr) on any non-finite
// parse; an optional `min` clamps a parsed-but-too-low value up to the floor
// the knob needs to stay meaningful (also logged). Lives in exec.ts (not
// farm.ts) so mutation.ts can use it too without a farm.ts -> mutation.ts ->
// farm.ts import cycle (function declarations hoist, so GATE_TIMEOUT_MS below
// can call it before this point in file order).
export function numEnv(name: string, def: number, opts: { min?: number } = {}): number {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return def;
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    process.stderr.write(
      `[FARM] ${name}=${JSON.stringify(raw)} is not a finite number — falling back to the default ${def}\n`,
    );
    return def;
  }
  if (opts.min !== undefined && n < opts.min) {
    process.stderr.write(`[FARM] ${name}=${n} is below the minimum ${opts.min} — clamping to ${opts.min}\n`);
    return opts.min;
  }
  return n;
}

// T-06 (reliability-001): per-command wall-clock timeout. The shared run() helper
// previously resolved ONLY on the child's close/error event, so a gate/setup/
// mutation command that never exits (a test blocking on stdin, a watch/dev-server
// invocation, an interactive prompt) wedged the awaiting worker forever — and the
// scheduler's Promise.race never settled, so the whole run hung with no report.
// This mirrors the AbortController discipline the API path already uses. Default a
// few minutes; configurable, independent of FARM_REQUEST_TIMEOUT_MS.
export const GATE_TIMEOUT_MS = numEnv("FARM_GATE_TIMEOUT_MS", 300_000, { min: 1000 });

// Kill a spawned child and its descendants. On Windows a plain child.kill() does
// not reap the process tree (cmd.exe /c spawns the real command as a grandchild),
// so use `taskkill /T /F` by PID; elsewhere SIGKILL the child. Best-effort —
// errors are swallowed (the child may already be gone).
export function treeKill(child: ReturnType<typeof spawn>): void {
  try {
    if (process.platform === "win32" && child.pid !== undefined) {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
    } else {
      child.kill("SIGKILL");
    }
  } catch {
    /* already exited / unkillable — best effort */
  }
}

// Least-privilege child env — the single source of truth for every spawned
// child. The dispatcher's secrets (the Zen API key and the OAuth token) are
// used only by the in-process fetch; NO child — git, the operator-authored
// gate/setup/test commands, or the pluggable mutation hook — needs them. Build
// the env from process.env plus any caller-supplied vars, then delete the
// secrets LAST so a caller var can never re-introduce one (CodeQL #5). Every
// spawn routes through here so the scrub cannot drift between call sites.
export function scrubbedEnv(extra?: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, ...(extra ?? {}) };
  delete env.FARM_API_KEY;
  delete env.CLAUDE_CODE_OAUTH_TOKEN;
  return env;
}

// `opts` excludes `env`, `cwd`, and `shell` so a caller can never re-introduce
// a raw env (and thus silently override scrubbedEnv()'s CodeQL #5 scrub),
// shadow the explicit `cwd` param, or opt into shell interpolation through the
// spread below — the compiler now enforces the single-scrub-path and
// argv-array invariants the header comment describes.
type RunOpts = Omit<SpawnOptionsWithoutStdio, "env" | "cwd" | "shell">;

// `timeoutMs` (opts) bounds the child's wall-clock; 0/undefined disables the
// timeout (used by git, which must not be killed mid-operation). On timeout the
// child tree is killed and a RunResult tagged `timedOut` resolves, so the caller
// treats it as a non-zero failure instead of awaiting forever.
export function run(
  cmd: string,
  args: string[],
  cwd?: string,
  opts: RunOpts = {},
  timeoutMs = 0,
): Promise<RunResult> {
  return new Promise<RunResult>((resolve) => {
    const c = spawn(cmd, args, { cwd, env: scrubbedEnv(), ...opts });
    let stdout = "";
    let stderr = "";
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const done = (r: RunResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(r);
    };
    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        treeKill(c);
        const note = `\n[FARM] command exceeded ${timeoutMs}ms wall-clock timeout — killed (FARM_GATE_TIMEOUT_MS)`;
        done({ code: 124, out: stdout + stderr + note, stdout, stderr: stderr + note, timedOut: true });
      }, timeoutMs);
    }
    c.stdout.on("data", (d) => (stdout += d));
    c.stderr.on("data", (d) => (stderr += d));
    c.on("error", (e) => done({ code: 1, out: String(e), stdout: "", stderr: String(e) }));
    c.on("close", (code) => done({ code: code ?? 1, out: stdout + stderr, stdout, stderr }));
  });
}

// shared file reader — single read path for every consumer that needs the
// current contents of a worktree file. Returns the file text, or null on any
// read failure (missing file, not yet created, permission). antiGamingCheck,
// mutationCheck, AND the prompt enrichment (AC-03/AC-04) all go through here
// rather than growing their own parallel try/catch read paths (spec Risks:
// "Duplicated file reads"). `wt`-relative paths are resolved against the
// worktree the caller passes.
export async function readWorktreeFile(wt: string, relPath: string): Promise<string | null> {
  try {
    return await readFile(path.resolve(wt, relPath), "utf8");
  } catch {
    return null;
  }
}
