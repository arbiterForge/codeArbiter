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
import { spawn, type ChildProcess, type SpawnOptionsWithoutStdio } from "node:child_process";
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
// `cleanupFailed` (#395) is set when the timeout kill fired but the child
// process TREE could not be confirmed gone. It is a containment failure, not an
// ordinary timeout: descendants may still be executing model-authored commands
// against the worktree, so it carries its own exit code (see EXIT_* below) and
// its own loud note rather than hiding inside a clean-looking 124.
export type RunResult = {
  code: number;
  out: string;
  stdout: string;
  stderr: string;
  timedOut?: true;
  cleanupFailed?: true;
};

// #395: two distinguishable timeout outcomes. Both are non-zero, so every
// existing `code !== 0` consumer branch is unchanged; the split exists so a
// caller (and an operator reading a report) can tell "we killed it" from "we
// could not prove we killed it".
export const EXIT_TIMEOUT = 124; // killed, tree verified gone
export const EXIT_TIMEOUT_UNCLEAN = 125; // killed, tree NOT verified gone

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

// #395 — how long treeKill will wait for the tree to be OBSERVABLY gone before
// it reports the cleanup as unverified. This is a verification budget, not a
// grace period: the kill is already SIGKILL/`/F`, so the only thing being waited
// on is the kernel finishing the teardown (and, on Windows, taskkill walking the
// tree). Generous by default; a run never spends it unless something is wedged.
const KILL_VERIFY_DEFAULT_MS = 10_000;

// #395: the outcome of a tree kill. `ok` means the process tree was verified
// ABSENT, not merely that a kill signal was sent. `detail` explains an `ok:false`
// well enough to act on.
export type TreeKillResult = { ok: boolean; detail?: string };

// The kill seam run() uses. Defaulted to the real treeKill; injectable so the
// "cleanup could not be verified" branch is testable without arranging a
// genuinely unkillable process (which is not portable).
export type TreeKiller = (child: ChildProcess) => Promise<TreeKillResult>;

// #395: resolve taskkill ABSOLUTELY. An unqualified `spawn("taskkill", ...)` is
// resolved through %PATH%, so any earlier PATH entry containing a taskkill.exe
// (or, on some configurations, the current directory) decides what runs during
// our containment step — a privilege-relevant resolution hazard in exactly the
// code path whose job is to contain untrusted commands. %SystemRoot% is the
// canonical, non-user-writable boundary.
export function taskkillPath(): string {
  const root = process.env.SystemRoot ?? process.env.windir ?? "C:\\Windows";
  return path.join(root, "System32", "taskkill.exe");
}

// A liveness probe. libuv maps signal 0 to "does this exist?" on every platform
// (on Windows it reports ESRCH for a terminated-but-not-yet-freed process, so a
// dead pid reads dead). EPERM means the target exists but is not ours to signal
// — still PRESENT, so it must not read as gone.
function pidPresent(target: number): boolean {
  try {
    process.kill(target, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function waitUntilGone(probe: () => boolean, deadline: number): Promise<boolean> {
  for (;;) {
    if (!probe()) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((r) => setTimeout(r, 25));
  }
}

// Await `taskkill /T /F` to COMPLETION. The prior code spawned it and returned
// immediately, so run() resolved a "clean timeout" while the tree teardown had
// not even started. Exit 0 = terminated; exit 128 = "process not found", i.e.
// already gone, which is success for our purposes.
function awaitTaskkill(pid: number, budgetMs: number): Promise<TreeKillResult> {
  return new Promise<TreeKillResult>((resolve) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const done = (r: TreeKillResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(r);
    };
    let tk: ChildProcess;
    try {
      tk = spawn(taskkillPath(), ["/pid", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    } catch (e) {
      done({ ok: false, detail: `taskkill could not be spawned: ${String(e)}` });
      return;
    }
    timer = setTimeout(() => {
      try {
        tk.kill();
      } catch {
        /* best effort */
      }
      done({ ok: false, detail: `taskkill did not exit within ${budgetMs}ms` });
    }, Math.max(1000, budgetMs));
    tk.on("error", (e) => done({ ok: false, detail: `taskkill failed to start: ${e.message}` }));
    tk.on("close", (code) =>
      done(code === 0 || code === 128 ? { ok: true } : { ok: false, detail: `taskkill exited ${code}` }),
    );
  });
}

// Kill a spawned child AND ITS DESCENDANTS, then VERIFY the tree is gone (#395).
//
// The thing being contained is a grandchild: every gate/setup/mutation command
// runs as `bash -c <cmd>` / `cmd.exe /c <cmd>`, so the operator-authored (and
// therefore model-influenced) command is one level below the child we hold. The
// previous implementation SIGKILLed only that direct child off-Windows — the
// real command survived, reparented to init, still holding ports, still writing
// into the worktree the farm had already moved on from.
//
//   POSIX  — run() spawns `detached`, so the child LEADS its own process group
//            and `kill(-pid)` addresses the whole tree at once. The direct
//            child is also signalled explicitly so a caller that spawned
//            non-detached (mutation.ts's own spawn predates this) is still
//            covered. Verification polls both the pid and the group: a group
//            with any surviving member still answers signal 0.
//   Windows — `taskkill /T /F` against an ABSOLUTE taskkill.exe, awaited to
//            completion, then the pid is probed.
//
// Resolves ok:false (never throws, never hangs) when the tree cannot be
// confirmed absent within the verification budget.
export async function treeKill(child: ChildProcess, opts: { budgetMs?: number } = {}): Promise<TreeKillResult> {
  const pid = child.pid;
  // No pid means the spawn itself failed — there is no tree to contain.
  if (pid === undefined) return { ok: true, detail: "child never started" };
  const budget = opts.budgetMs ?? numEnv("FARM_KILL_VERIFY_MS", KILL_VERIFY_DEFAULT_MS, { min: 0 });
  const deadline = Date.now() + budget;

  if (process.platform === "win32") {
    const tk = await awaitTaskkill(pid, budget);
    if (!tk.ok) {
      // taskkill failed outright — fall back to at least killing what we hold,
      // then still verify rather than assume.
      try {
        child.kill("SIGKILL");
      } catch {
        /* already exited */
      }
    }
    if (await waitUntilGone(() => pidPresent(pid), deadline)) return { ok: true };
    return {
      ok: false,
      detail: `pid ${pid} and/or its descendants were still present ${budget}ms after taskkill /T /F${tk.detail ? ` (${tk.detail})` : ""}`,
    };
  }

  // POSIX. Group first (the detached-leader case: reaches grandchildren), then
  // the child directly (covers a non-detached caller). A pid is unique, so a
  // process group whose id equals our child's pid can only be our child's own
  // group — the negative-pid signal cannot stray onto an unrelated group.
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    /* not a group leader, or already gone */
  }
  try {
    child.kill("SIGKILL");
  } catch {
    /* already exited */
  }
  // The child is our own, so it lingers as a zombie (and still answers signal 0)
  // until Node reaps it; the awaits below let the event loop do that.
  if (await waitUntilGone(() => pidPresent(pid) || pidPresent(-pid), deadline)) return { ok: true };
  return {
    ok: false,
    detail: `process group ${pid} still had a live member ${budget}ms after SIGKILL — descendants may still be running`,
  };
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

// `opts` excludes `env`, `cwd`, `shell`, and `detached` so a caller can never
// re-introduce a raw env (and thus silently override scrubbedEnv()'s CodeQL #5
// scrub), shadow the explicit `cwd` param, opt into shell interpolation through
// the spread below, or opt OUT of the process-group isolation the timeout kill
// depends on (#395) — the compiler now enforces the single-scrub-path, the
// argv-array, and the one-group-per-child invariants the header describes.
type RunOpts = Omit<SpawnOptionsWithoutStdio, "env" | "cwd" | "shell" | "detached">;

// `timeoutMs` (opts) bounds the child's wall-clock; 0/undefined disables the
// timeout (used by git, which must not be killed mid-operation). On timeout the
// child tree is killed, VERIFIED absent (#395), and a RunResult tagged
// `timedOut` resolves, so the caller treats it as a non-zero failure instead of
// awaiting forever. `kill` is the injectable containment seam (defaults to the
// real treeKill) — see TreeKiller.
export function run(
  cmd: string,
  args: string[],
  cwd?: string,
  opts: RunOpts = {},
  timeoutMs = 0,
  kill: TreeKiller = treeKill,
): Promise<RunResult> {
  return new Promise<RunResult>((resolve) => {
    const c = spawn(cmd, args, {
      cwd,
      env: scrubbedEnv(),
      ...opts,
      // #395: off Windows the child leads its OWN process group, so a timeout
      // kill can address the whole tree (`kill(-pid)`) instead of just the
      // shell that fronts the operator's command. NOT on Windows, where
      // `detached` means "new console" and breaks the `cmd.exe /c` contract.
      detached: process.platform !== "win32",
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    // #395: set the instant the timeout fires, BEFORE the (now awaited) kill.
    // Without it the child's own `close` — which the kill itself causes — would
    // win the race and resolve an ordinary exit result, discarding both the
    // `timedOut` tag and the cleanup verdict.
    let killing = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const done = (r: RunResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(r);
    };
    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        killing = true;
        void (async () => {
          const k = await kill(c);
          const base = `\n[FARM] command exceeded ${timeoutMs}ms wall-clock timeout — killed (FARM_GATE_TIMEOUT_MS)`;
          const note = k.ok
            ? base
            : `${base}\n[FARM] CLEANUP UNVERIFIED — the child process tree could not be confirmed gone: ${k.detail ?? "no detail"}. Descendants may still be running against this worktree.`;
          done({
            code: k.ok ? EXIT_TIMEOUT : EXIT_TIMEOUT_UNCLEAN,
            out: stdout + stderr + note,
            stdout,
            stderr: stderr + note,
            timedOut: true,
            ...(k.ok ? {} : { cleanupFailed: true as const }),
          });
        })();
      }, timeoutMs);
    }
    c.stdout.on("data", (d) => (stdout += d));
    c.stderr.on("data", (d) => (stderr += d));
    c.on("error", (e) => {
      if (killing) return;
      done({ code: 1, out: String(e), stdout: "", stderr: String(e) });
    });
    c.on("close", (code) => {
      if (killing) return;
      done({ code: code ?? 1, out: stdout + stderr, stdout, stderr });
    });
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
