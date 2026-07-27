/**
 * farm.ts — codeArbiter's zero-LLM-token dispatcher.
 *
 * Papa Claude (your interactive Claude Code session) does the judgment work:
 * brainstorm -> spec -> write the FAILING tests into the repo -> emit plan.json.
 * Then he runs THIS script and walks away. No premium model calls happen in
 * here — the only model cost is the cheap Zen worker invoked per task.
 *
 * For each task the dispatcher:
 *   1. cuts an isolated git worktree off the *current integration HEAD*
 *      (so a task inherits the merged output of its dependencies),
 *   2. calls the Zen/DeepSeek API directly whose only job is to make the
 *      failing test pass,
 *   3. enforces filesInScope — any file outside the allowed set fails the task,
 *      and protects the failing test from being modified or deleted,
 *   4. enforces the gate deterministically (the test must go green, suite stays
 *      green, lint/types pass — whatever you put in gate.commands),
 *   5. runs a zero-token anti-gaming check (does the impl hard-code the test's
 *      expected values?) so obviously-gamed output is caught before review,
 *   6. retries with the gate failure fed back in, up to maxRetries, resetting
 *      the worktree between attempts so stale files never accumulate,
 *   7. on success commits + merges into the integration branch via a dedicated
 *      integration worktree (never touches the main repo checkout),
 *   8. on exhaustion leaves the worktree in place and ESCALATES the task.
 *
 * A circuit breaker aborts the run if too many tasks escalate (a bad/incapable
 * model), so you don't burn quota cutting 50 worktrees for nothing.
 *
 * It never merges to main — codeArbiter's PR-only rule is preserved. You review
 * the integration branch (each green task still routes through the normal
 * spec-compliance + quality + fresh-verification gates) and open the PR yourself.
 *
 * Canary mode (`--canary <plan.json>`): runs the smallest task against each
 * model in FARM_CANDIDATE_MODELS and reports a measured pass-rate ranking, so
 * model selection is objective rather than web hearsay. No merge, no mutation.
 */
import { readFile, writeFile, appendFile, mkdir, rm, stat, rename, open } from "node:fs/promises";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
// v2.rev.0020 god-module split (architecture-003): the process/shell layer, the
// outbound secret redactor, and the zero-token mutation engine now live in their
// own focused, tested modules. farm.ts imports what it consumes and re-exports
// the members the test suite + external consumers import from "./farm.ts", so
// this file stays the stable public surface. The graph is one-way: farm.ts ->
// {exec, redactor, mutation} and mutation -> exec (no cycle).
import { run, readWorktreeFile, SHELL_BIN, SHELL_FLAG, SHELL_OPTS, GATE_TIMEOUT_MS, numEnv } from "./exec.ts";
import type { RunResult } from "./exec.ts";
import { redactSecrets, isSecretBearingFilename } from "./redactor.ts";
import { MUT, mutationCheck, antiGamingCheck } from "./mutation.ts";
import type { MutationResult } from "./mutation.ts";
import { UnsafeWorktreePathError, isUnsafeWorktreePathError, writeWorktreeFile } from "./worktree-fs.ts";
export { run, redactSecrets, numEnv };
export { extractLiterals, codeLineCount, parseMutationHookOutput } from "./mutation.ts";

// --------------------------------------------------------------------------
// Types — the handoff contract. Claude emits plan.json conforming to this.
// --------------------------------------------------------------------------
export type Task = {
  id: string;
  description: string;
  deps?: string[];
  filesInScope: string[];
  test: { path: string };
  gate: { commands: string[] };
  context?: string;
  maxRetries?: number;
  // Optional per-worktree setup commands (#92). Shell commands run IN the task
  // worktree before the worker. The common case is repo-wide dependency install
  // (`npm ci`, `pip install -r requirements.txt`); set plan.meta.setup and it
  // propagates here at dispatch. A per-task value overrides the meta default.
  // Setup artifacts MUST be gitignored or they trip drift detection. A failing
  // setup command escalates the task immediately.
  //
  // #391: this phase runs ONCE per worktree, not once per attempt. The
  // inter-attempt reset is `git reset --hard` + `git clean -fd` (no `-x`), which
  // deliberately PRESERVES ignored paths — so the very dependency tree the
  // setup contract requires to be gitignored survives the reset, and
  // reinstalling it was pure waste (up to 3x the install on the default retry
  // budget). Commands that genuinely must rerun after a reset go in
  // `setupEachAttempt`.
  setup?: string[];
  // Optional per-attempt preparation (#391). Runs in the worktree before EVERY
  // worker attempt, after `setup`. This is the escape hatch for commands that
  // rebuild ignored outputs from tracked source (codegen, a build step) and can
  // therefore go stale once a reset rolls the tracked files back. A failing
  // command escalates the task exactly like `setup`.
  setupEachAttempt?: string[];
  // Optional declared inputs of `setup` (#391) — relative paths (e.g.
  // "package-lock.json"). Their content hashes join the setup fingerprint, so
  // the once-per-worktree cache INVALIDATES when the baseline moves under the
  // worktree. That is a real case, not a hypothetical: regenerate-on-conflict
  // resets the task worktree onto a NEW integration HEAD, which can carry a
  // different lockfile.
  setupInputs?: string[];
  // Optional per-task model override (AC-02). The effective model for a task is
  // `task.model ?? <run-level resolved model>`, layered where runTask invokes
  // the worker; absent → identical current behavior. Model id only — no second
  // provider or per-task apiBaseUrl.
  model?: string;
};
export type Plan = {
  meta: {
    name: string;
    repo?: string;
    model?: string;
    apiBaseUrl?: string;
    setup?: string[];
    setupEachAttempt?: string[];
    setupInputs?: string[];
  };
  tasks: Task[];
};

// Built-in default endpoint, used only when neither FARM_API_BASE_URL nor
// plan.meta.apiBaseUrl provides one. The live OpenCode Zen OpenAI-compatible
// host: `/models` and `/chat/completions` both 200 here. The former default
// `https://api.opencode.ai/v1` now answers 200 with body "Not Found" (#90), so
// every worker died with an opaque non-JSON parse error.
export const DEFAULT_API_BASE_URL = "https://opencode.ai/zen/v1";

const ENV = {
  // Model: plan.meta.model (set by subagent-driven-development before dispatch),
  // then FARM_MODEL env var override. Fails at startup if neither is set.
  model: process.env.FARM_MODEL ?? null,
  // No-default kept deliberately: dispatch records the chosen endpoint in
  // plan.meta.apiBaseUrl. A code default is provided only as a last resort so a
  // user who sets just FARM_API_KEY (per the docs) is not hard-blocked.
  apiBaseUrl: process.env.FARM_API_BASE_URL ?? null,
  apiKey: process.env.FARM_API_KEY ?? null,
  // reliability-014: every numeric knob below routes through numEnv (exec.ts)
  // so a typo'd value (e.g. FARM_CONCURRENCY="four") falls back to the default
  // LOUDLY instead of silently becoming NaN, which reads false in every
  // downstream safety comparison (concurrency cap, escalation breaker).
  concurrency: numEnv("FARM_CONCURRENCY", 4, { min: 1 }),
  maxRetries: numEnv("FARM_MAX_RETRIES", 2, { min: 0 }),
  base: process.env.FARM_BASE_BRANCH ?? "main",
  integration: process.env.FARM_INTEGRATION_BRANCH ?? "farm/integration",
  worktreeRoot: process.env.FARM_WORKTREE_ROOT ?? ".farm/worktrees",
  reportDir: process.env.FARM_REPORT_DIR ?? ".farm",
  // #397: an orchestrator may PIN this run's id, which is also the name of the
  // run-scoped artifact directory (`${reportDir}/runs/<runId>/`). Absent → a
  // fresh random id per invocation (mintRunId).
  runId: process.env.FARM_RUN_ID ?? null,
  // Per-request hard timeout so a hung endpoint can't deadlock a worker slot.
  requestTimeoutMs: numEnv("FARM_REQUEST_TIMEOUT_MS", 120_000, { min: 1 }),
  // Per-candidate wall-clock cap for the #93 entitlement pre-screen, so one
  // slow/dead model can't dominate the probe. Kept short (35s) — a screen, not a
  // capability run — and ≤ the per-request timeout.
  entitlementProbeTimeoutMs: numEnv("FARM_ENTITLEMENT_PROBE_TIMEOUT_MS", 35_000, { min: 1 }),
  // Transport-level retries (429 / 5xx) — distinct from model-quality retries.
  apiMaxRetries: numEnv("FARM_API_MAX_RETRIES", 3, { min: 0 }),
  // Circuit breaker: abort dispatch once the escalation rate exceeds this,
  // after at least abortMinTasks have settled.
  abortEscalationRate: numEnv("FARM_ABORT_ESCALATION_RATE", 0.5, { min: 0 }),
  abortMinTasks: numEnv("FARM_ABORT_MIN_TASKS", 3, { min: 1 }),
  // Default endpoint, used only when neither env nor plan.meta provides one.
  defaultApiBaseUrl:
    process.env.FARM_DEFAULT_API_BASE_URL ?? DEFAULT_API_BASE_URL,
  // Comma-separated candidate model ids for --canary mode.
  candidateModels: (process.env.FARM_CANDIDATE_MODELS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
  // AC-05 byte cap on the TOTAL injected enrichment context (test source +
  // in-scope file bodies) that leaves the trust boundary to the third-party
  // endpoint. Default 131072 (128 KiB): more repo content now flows outbound,
  // so the prompt must never be unbounded. 128 KiB is ~32K tokens of context —
  // generous enough for the real test + a handful of in-scope files, yet small
  // enough to stay well inside the FARM_REQUEST_TIMEOUT_MS (120s) single-request
  // budget and to bound per-task token spend. Truncation past the cap is
  // deterministic (in-order) with a visible marker; we never silently drop the
  // boundedness guarantee.
  enrichMaxBytes: numEnv("FARM_ENRICH_MAX_BYTES", 131_072, { min: 1 }),
};

// --------------------------------------------------------------------------
// process helpers — run(), treeKill(), SHELL_*, GATE_TIMEOUT_MS, the RunResult
// type, and the shared readWorktreeFile reader now live in ./exec.ts
// (v2.rev.0020 split); MUT and the mutation engine live in ./mutation.ts. Only
// the git/sleep wrappers stay here, over the imported run().
// --------------------------------------------------------------------------
type GitRunner = (args: string[], cwd?: string) => Promise<RunResult>;
const git: GitRunner = (args, cwd) => run("git", args, cwd);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// --------------------------------------------------------------------------
// Concurrency limiter (F1). A shared worker-call budget so best-of-N sampling
// (up to FARM_SAMPLES worker calls per task) never exceeds FARM_CONCURRENCY
// TOTAL in-flight calls, across tasks AND their samples (AC-F1.4). With
// FARM_SAMPLES=1 each task makes exactly one call and the scheduler already caps
// concurrent tasks at the same bound, so the limiter never blocks — behavior is
// identical to today. A job that throws still releases its slot (no leak).
// --------------------------------------------------------------------------
export type Limiter = { run<T>(fn: () => Promise<T>): Promise<T>; active(): number };
export function createLimiter(max: number): Limiter {
  const cap = Math.max(1, Math.floor(max) || 1);
  let active = 0;
  const queue: Array<() => void> = [];
  const pump = () => {
    if (active < cap && queue.length) {
      active++;
      queue.shift()!();
    }
  };
  const acquire = () =>
    new Promise<void>((resolve) => {
      queue.push(resolve);
      pump();
    });
  const release = () => {
    active--;
    pump();
  };
  return {
    async run(fn) {
      await acquire();
      try {
        return await fn();
      } finally {
        release();
      }
    },
    active: () => active,
  };
}
// Shared worker-call budget, sized to FARM_CONCURRENCY at module load.
const workerLimit = createLimiter(ENV.concurrency);

// Commit without signing — the farm makes mechanical commits; signing servers
// in CI environments reject unattended commits and would be misreported as
// merge conflicts. The integration PR the human opens is the signed artifact.
const NOSIGN = ["-c", "commit.gpgsign=false"];

// --------------------------------------------------------------------------
// path containment — untrusted worker output must never escape the worktree
// --------------------------------------------------------------------------
function isInside(root: string, target: string): boolean {
  const rel = path.relative(root, target);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

// #163: the farm worktree root is env-controlled (FARM_WORKTREE_ROOT) and each
// task worktree path is <root>/<task.id>, which prepareWorktree rm()'s
// recursively BEFORE git validates it as a real worktree. Without containment, a
// broad/misconfigured root (e.g. FARM_WORKTREE_ROOT=/Users/alice) plus a
// plausible task id (Desktop) recursively deletes an arbitrary directory. Two
// defenses, both fail-closed: (1) the resolved root must live inside the repo
// unless an explicit unsafe override is set; (2) every worktree path must be
// strictly inside that root (never the root itself) at the destructive op.
function repoTopLevel(): string {
  try {
    const out = spawnSync("git", ["rev-parse", "--show-toplevel"], {
      encoding: "utf8",
      timeout: 5_000,
    });
    const top = (out.stdout || "").trim();
    if (out.status === 0 && top) return path.resolve(top);
  } catch {
    /* fall through to cwd */
  }
  return path.resolve(process.cwd());
}

// Pure, side-effect-free root validation (directly unit-testable): the resolved
// worktree root must live inside `repo` unless `external` opts out. Throws with a
// remediating message otherwise; returns the resolved absolute root.
export function validateWorktreeRoot(rawRoot: string, repo: string, external: boolean): string {
  const root = path.resolve(rawRoot);
  if (!external && !isInside(path.resolve(repo), root))
    throw new Error(
      `FARM_WORKTREE_ROOT resolves to '${root}', outside the repository root '${path.resolve(repo)}'. ` +
        `farm recursively deletes task worktrees under this root, so an out-of-repo root is ` +
        `refused (#163). Point it inside the repo, or set FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1 ` +
        `to override.`,
    );
  return root;
}

let _allowedWorktreeRoot: string | null = null;
export function allowedWorktreeRoot(): string {
  if (_allowedWorktreeRoot) return _allowedWorktreeRoot;
  _allowedWorktreeRoot = validateWorktreeRoot(
    ENV.worktreeRoot,
    repoTopLevel(),
    process.env.FARM_ALLOW_EXTERNAL_WORKTREE_ROOT === "1",
  );
  return _allowedWorktreeRoot;
}

// Test seam: the module-level cache would otherwise pin the first-resolved root
// for the whole process, so a suite that varies FARM_WORKTREE_ROOT across cases
// must reset it. No effect on production (resolved once at run start).
export function _resetAllowedWorktreeRoot(): void {
  _allowedWorktreeRoot = null;
}

// Assert a task worktree path is safely contained before any recursive delete /
// worktree removal. Returns the resolved path so callers can reuse it.
export function assertContainedWorktree(wt: string): string {
  const root = allowedWorktreeRoot();
  const abs = path.resolve(wt);
  if (abs === root || !isInside(root, abs))
    throw new Error(
      `refusing to operate on worktree path '${abs}': it must be strictly inside the allowed ` +
        `farm worktree root '${root}' (#163).`,
    );
  return abs;
}

// --------------------------------------------------------------------------
// gate — pure determinism, no model. Each command runs through the shared
// SHELL_* config + run() from ./exec.ts (non-login shell so user dotfiles don't
// bleed in; cmd.exe /c with verbatim args on Windows).
// --------------------------------------------------------------------------
export async function runGate(cwd: string, commands: string[]) {
  for (const cmd of commands) {
    // T-06: bound each gate/setup command by the wall-clock timeout so a hung
    // command is killed and surfaces as a gate failure instead of wedging the
    // worker. The killed RunResult carries code!=0 (124), so the existing
    // non-zero branch below treats it exactly like any other gate failure.
    const r = await run(SHELL_BIN, [SHELL_FLAG, cmd], cwd, SHELL_OPTS, GATE_TIMEOUT_MS);
    if (r.code !== 0)
      // FINDING 2: the raw gate stdout+stderr tail flows into priorFailure and
      // is injected into the next worker prompt (buildPrompt), crossing the
      // trust boundary to the third party. Run it through the SAME span-aware
      // redaction as injected file bodies before it leaves runGate, so a
      // secret-shaped string a test/gate happens to print is never transmitted.
      // (redactSecrets is a hoisted function declaration — callable here.)
      return { ok: false as const, failed: cmd, tail: redactSecrets(r.out.slice(-3500)) };
  }
  return { ok: true as const };
}

// --------------------------------------------------------------------------
// shared worktree-file reader — readWorktreeFile now lives in ./exec.ts
// (v2.rev.0020). It is still the single read path every consumer goes through
// (buildEnrichment here, antiGamingCheck + mutationCheck in ./mutation.ts), so
// there are no parallel try/catch read paths; it is imported at the top.
// --------------------------------------------------------------------------

// --------------------------------------------------------------------------
// prompt enrichment (AC-03 / AC-04). Gathers the read-only source of the
// failing test plus the current contents of in-scope files that already exist
// in the worktree (best-effort direct context — no deep import resolution).
// On the first attempt these in-scope files hold the dependency-inherited
// baseline, which is exactly the context the worker needs to implement
// against. Reads reflect the per-attempt worktree state because runTask calls
// this AFTER any inter-attempt reset.
//
// ALL injected content is funneled through this ONE chokepoint and rendered by
// `renderInjectedFile`, so T-05 can wrap the byte cap + secret redaction here
// without touching buildPrompt or the call site. (T-04 does the injection +
// shared reader only — cap and redaction are explicitly NOT done here.)
// --------------------------------------------------------------------------
// `prior` (F2): this file is the worker's OWN output from a FAILED previous
// attempt, captured before the inter-attempt reset and shown read-only so a
// retry refines rather than restarts. Rendered in its own labeled section.
export type InjectedFile = { path: string; contents: string; readOnly: boolean; prior?: boolean };

// AC-05 secret redaction + the secret-bearing-filename denylist now live in
// ./redactor.ts (v2.rev.0020). redactSecrets + isSecretBearingFilename are
// imported at the top; behaviour, the span-aware PEM handling, and the
// corpus-parity pin (architecture-001) are unchanged.

// The single chokepoint for content that leaves the trust boundary. The byte
// cap (applied over the rendered array in buildEnrichment) and the per-line
// secret redaction (here) wrap every injected file body. Keep this the only
// place injected file bodies are formatted so the boundary stays in one spot.
function renderInjectedFile(file: InjectedFile): string {
  const label = file.prior
    ? `${file.path} (your previous attempt — FAILED)`
    : file.readOnly
      ? `${file.path} (read-only — the failing test)`
      : file.path;
  return [`--- ${label} ---`, redactSecrets(file.contents)].join("\n");
}

// Deterministic byte cap over the TOTAL injected enrichment. Operates on the
// InjectedFile[] (BEFORE buildPrompt renders it, so buildPrompt and the runTask
// call site stay untouched) but budgets against each file's FULLY RENDERED size
// — i.e. `renderInjectedFile` output, including the redaction substitutions and
// the path label — so the cap reflects exactly what crosses the boundary.
// Files are kept in order until the next would exceed the budget; the
// overflowing file's contents are hard-truncated (UTF-8 safe) to fit and a
// visible TRUNCATED marker appended; everything after is dropped. The prompt is
// never unbounded. Measured in UTF-8 bytes — the unit the request body is
// serialized in.
const TRUNCATION_MARKER = "--- [TRUNCATED — injected context exceeded FARM_ENRICH_MAX_BYTES] ---";

function capInjected(injected: InjectedFile[], maxBytes: number): InjectedFile[] {
  const out: InjectedFile[] = [];
  let used = 0;
  for (const file of injected) {
    const renderedBytes = Buffer.byteLength(renderInjectedFile(file), "utf8");
    if (used + renderedBytes <= maxBytes) {
      out.push(file);
      used += renderedBytes;
      continue;
    }
    // Fixed overhead this file's render adds around its contents (label line +
    // joins): the difference between the rendered size and the contents size.
    const contentBytes = Buffer.byteLength(redactSecrets(file.contents), "utf8");
    const overhead = renderedBytes - contentBytes;
    const remaining = maxBytes - used - overhead - Buffer.byteLength("\n" + TRUNCATION_MARKER, "utf8");
    if (remaining > 0) {
      // Truncate the (already redaction-safe) contents to the remaining byte
      // budget on a UTF-8 boundary, then append the marker.
      const safe = Buffer.from(redactSecrets(file.contents), "utf8")
        .subarray(0, remaining)
        .toString("utf8");
      out.push({ ...file, contents: safe + "\n" + TRUNCATION_MARKER });
    } else {
      // No room even for this file's frame — emit a marker-only stub so the
      // truncation is visible, then stop.
      out.push({ ...file, contents: TRUNCATION_MARKER });
    }
    break;
  }
  return out;
}

async function buildEnrichment(
  wt: string,
  t: Task,
  priorInScope: Array<{ path: string; contents: string }> = [],
): Promise<InjectedFile[]> {
  const injected: InjectedFile[] = [];
  const seen = new Set<string>();

  // AC-03: the read-only source of the failing test. Defense-in-depth: run the
  // test path through the same secret-bearing-filename denylist as in-scope
  // files (STEP-A) — a test.path pointing at .env/*.pem/*.key must never have its
  // body cross the trust boundary, regardless of per-line redaction.
  if (!isSecretBearingFilename(t.test.path)) {
    const testSrc = await readWorktreeFile(wt, t.test.path);
    if (testSrc !== null) {
      injected.push({ path: t.test.path, contents: testSrc, readOnly: true });
      seen.add(t.test.path);
    }
  } else {
    seen.add(t.test.path);
  }

  // AC-04: current contents of in-scope files that already exist on disk in the
  // worktree (best-effort). Skip the test path (already injected, read-only) and
  // files that do not yet exist (e.g. the not-yet-written target).
  for (const f of t.filesInScope) {
    if (seen.has(f)) continue;
    // Data-minimization: never even READ a secret-bearing filename
    // (.env/.env.*/*.pem/*.key/id_rsa*, etc.) into injected context — its body
    // must not cross the trust boundary regardless of per-line redaction.
    if (isSecretBearingFilename(f)) {
      seen.add(f);
      continue;
    }
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
    injected.push({ path: f, contents: src, readOnly: false });
    seen.add(f);
  }

  // F2: the worker's OWN prior failed in-scope output (captured before the
  // inter-attempt reset). Appended AFTER current files so the byte cap truncates
  // prior context FIRST — the current baseline keeps budget priority. Same
  // secret-bearing-filename denylist as everything else that leaves the boundary.
  for (const pf of priorInScope) {
    if (isSecretBearingFilename(pf.path)) continue;
    injected.push({ path: pf.path, contents: pf.contents, readOnly: true, prior: true });
  }

  // AC-05: byte-cap the TOTAL injected context before it leaves the trust
  // boundary. Redaction is applied per-file inside renderInjectedFile (the
  // chokepoint), but the truncation stub here means contents already carry the
  // redaction by the time they are re-rendered — redactSecrets is idempotent on
  // the marker, so a redacted-then-truncated body stays redacted.
  return capInjected(injected, ENV.enrichMaxBytes);
}

// F2: snapshot the worker's in-scope output from the worktree BEFORE the
// inter-attempt reset wipes it, so the next attempt can refine rather than
// restart blind. Reads only filesInScope (never the read-only test, never a
// secret-bearing filename), through the shared reader; a not-yet-written file is
// skipped. Out-of-scope drift is never in filesInScope, so it is never captured
// (AC-F2.2).
export async function captureInScope(
  wt: string,
  t: Task,
): Promise<Array<{ path: string; contents: string }>> {
  const out: Array<{ path: string; contents: string }> = [];
  for (const f of t.filesInScope) {
    if (f === t.test.path) continue;
    if (isSecretBearingFilename(f)) continue;
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
    out.push({ path: f, contents: src });
  }
  return out;
}

// --------------------------------------------------------------------------
// worker prompt
// --------------------------------------------------------------------------
export function buildPrompt(
  t: Task,
  injected: InjectedFile[],
  priorFailure?: string,
  forbiddenExtra?: string[],
) {
  // F2: split current source (the baseline + the read-only test) from the
  // worker's prior failed output, so each renders in its own clearly-labeled
  // section. A retry then sees BOTH what to build against and what it tried last.
  const current = injected.filter((f) => !f.prior);
  const priorFiles = injected.filter((f) => f.prior);
  const enrichment = current.length
    ? [
        ``,
        `Current source of the relevant files (the test is read-only; implement against it):`,
        ``,
        ...current.map(renderInjectedFile),
        ``,
      ]
    : [];
  const priorBlock = priorFiles.length
    ? [
        ``,
        `Your PREVIOUS attempt FAILED the gate. Here is what you wrote last time — do NOT just repeat it; change it to fix the cause shown at the end:`,
        ``,
        ...priorFiles.map(renderInjectedFile),
        ``,
      ]
    : [];
  return [
    `Implement exactly ONE task. Your only goal: make the failing test pass.`,
    ``,
    `TASK: ${t.description}`,
    t.context ? `\nCONTEXT:\n${t.context}\n` : ``,
    `The failing test is at: ${t.test.path}`,
    `Make it pass WITHOUT modifying, deleting, or weakening that test.`,
    `You may NOT create, edit, or delete ${t.test.path} — it is read-only.`,
    ``,
    `You may ONLY create or edit these files:`,
    ...t.filesInScope.map((f) => `  - ${f}`),
    `Touch nothing else. Do not run git. Do not install global packages.`,
    forbiddenExtra && forbiddenExtra.length
      ? `\nYour previous attempt wrote these FORBIDDEN paths — do NOT touch them again:\n${forbiddenExtra.map((f) => `  - ${f}`).join("\n")}`
      : ``,
    ...enrichment,
    ...priorBlock,
    `Solve the task with REAL logic. Do not hard-code the literal values the`,
    `test asserts — an implementation that only returns the expected constant`,
    `will be rejected.`,
    ``,
    `Respond with ONLY the files you need to create or modify.`,
    `For each file, use this exact format:`,
    ``,
    `\`\`\`typescript`,
    `// path: src/example.ts`,
    `<complete file content here>`,
    `\`\`\``,
    ``,
    `Do not include any explanation outside the code blocks.`,
    priorFailure
      ? `\nYour previous attempt FAILED the gate. Fix it.\nGate output (tail):\n${priorFailure}`
      : ``,
  ].join("\n");
}

// --------------------------------------------------------------------------
// response parsing — line-based fence scanner. Robust to language tags,
// `// path:` / `# path:` comments, and the ```lang:path fence convention.
// Returns the path + body for each file block.
// --------------------------------------------------------------------------
export function extractFileBlocks(content: string): Array<{ path: string; body: string }> {
  const lines = content.split("\n");
  const blocks: Array<{ path: string; body: string }> = [];
  let i = 0;
  while (i < lines.length) {
    const open = lines[i].match(/^\s*```(.*)$/);
    if (!open) {
      i++;
      continue;
    }
    const info = open[1].trim();
    // collect body until the next fence line
    const body: string[] = [];
    i++;
    while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
      body.push(lines[i]);
      i++;
    }
    i++; // consume closing fence (or fall off the end)

    // Determine the path: prefer `lang:path` info string, else a leading
    // `// path:` / `# path:` / `/* path: ... */` comment in the body.
    let filePath: string | null = null;
    const infoPath = info.match(/^[a-z0-9]*:(.+)$/i);
    if (infoPath && /[\/.]/.test(infoPath[1])) {
      filePath = infoPath[1].trim();
    } else if (body.length) {
      const first = body[0].trim();
      const m =
        first.match(/^(?:\/\/|#)\s*path:\s*(.+)$/i) ||
        first.match(/^\/\*\s*path:\s*(.+?)\s*\*\/$/i);
      if (m) {
        filePath = m[1].trim();
        body.shift(); // drop the path-marker line from the written content
      }
    }
    if (filePath) blocks.push({ path: filePath, body: body.join("\n") });
  }
  return blocks;
}

export type WorkerResult = {
  ok: boolean;
  filesWritten: string[];
  error?: string;
  promptTokens?: number;
  completionTokens?: number;
};

// Interpret a `/chat/completions` response BODY (already read as text). Split
// out from callApi (#90) so the non-JSON-body path is unit-testable without a
// network round-trip, and so the error it produces is actionable rather than an
// opaque `non-JSON response: SyntaxError`. A stale/misconfigured endpoint (the
// #90 failure: a 200 whose body is the literal "Not Found") is the common cause,
// so the error names a sanitized endpoint origin and the FARM_API_BASE_URL knob
// the operator must fix. Provider-controlled response bodies are never copied
// into logs, retry prompts, or reports.
function diagnosticApiOrigin(apiBaseUrl: string): string {
  try {
    // origin excludes userinfo, path, query, and fragment, any of which may
    // carry credentials or attacker-controlled terminal content.
    return new URL(apiBaseUrl).origin;
  } catch {
    return "<configured endpoint>";
  }
}

export function parseChatCompletion(
  text: string,
  apiBaseUrl: string,
):
  | { ok: true; content: string; usage?: { prompt_tokens?: number; completion_tokens?: number } }
  | { ok: false; error: string } {
  let data: { choices?: Array<{ message?: { content?: string } }>; usage?: { prompt_tokens?: number; completion_tokens?: number } };
  try {
    data = JSON.parse(text) as typeof data;
  } catch {
    return {
      ok: false,
      error: `endpoint ${diagnosticApiOrigin(apiBaseUrl)} returned a non-JSON body — check FARM_API_BASE_URL and that the endpoint path is correct (expected an OpenAI-compatible /chat/completions)`,
    };
  }
  // dx-001 (T-08a): the `as typeof data` cast is unsound — valid JSON of an
  // UNEXPECTED shape (an array, a non-object, or `{error: ...}`) passes the cast
  // and then yields a silent `ok:true content:""`, exhausting retries without
  // signalling the real cause (the #90 class of misconfiguration). Verify the
  // chat-completions shape (a `choices` array) before trusting it; on a mismatch
  // return an actionable, endpoint-naming error.
  if (!data || typeof data !== "object" || !Array.isArray((data as { choices?: unknown }).choices)) {
    return {
      ok: false,
      error: `endpoint ${diagnosticApiOrigin(apiBaseUrl)} returned an unexpected shape (no 'choices' array) — check FARM_API_BASE_URL and that the endpoint is an OpenAI-compatible /chat/completions`,
    };
  }
  return { ok: true, content: data.choices?.[0]?.message?.content ?? "", usage: data.usage };
}

// --------------------------------------------------------------------------
// Sampling parameters (F4). Today the request body is only {model, messages};
// without a `temperature` the provider default applies and best-of-N samples
// cannot diversify, and an unbounded completion can run past the request budget.
// `readSampling` reads the knobs LIVE from the environment (FARM_TEMPERATURE
// default 0 — deterministic, closest to "make the test pass"; FARM_MAX_TOKENS
// default 0 = omit, preserving today's unbounded behavior). `buildChatBody`
// renders the OpenAI-compatible body; max_tokens is included ONLY when > 0 so
// the default body is byte-equivalent to today plus the explicit temperature.
// An explicit `sampling` override is the seam runTask uses to vary temperature
// per run (the best-of-N auto-bump, AC-F1.3).
// --------------------------------------------------------------------------
export type Sampling = { temperature: number; maxTokens: number };

export function readSampling(): Sampling {
  return {
    temperature: numEnv("FARM_TEMPERATURE", 0),
    maxTokens: numEnv("FARM_MAX_TOKENS", 0, { min: 0 }),
  };
}

export function buildChatBody(
  model: string,
  messages: Array<{ role: string; content: string }>,
  sampling: Sampling = readSampling(),
): Record<string, unknown> {
  const body: Record<string, unknown> = { model, messages, temperature: sampling.temperature };
  if (sampling.maxTokens > 0) body.max_tokens = sampling.maxTokens;
  return body;
}

async function callApi(
  prompt: string,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
  sampling: Sampling = readSampling(),
): Promise<{ ok: true; content: string; usage?: { prompt_tokens?: number; completion_tokens?: number } } | { ok: false; error: string }> {
  // Validate at the fetch-producing boundary as well as at CLI config
  // resolution. Exported callers (for example httpWorker/runTask) must not be
  // able to bypass the transport rule by supplying their own base URL.
  try {
    assertSecureBaseUrl(apiBaseUrl);
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "apiBaseUrl must use HTTPS" };
  }
  for (let attempt = 0; attempt <= ENV.apiMaxRetries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ENV.requestTimeoutMs);
    let resp: Response;
    try {
      resp = await fetch(`${apiBaseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(buildChatBody(model, [{ role: "user", content: prompt }], sampling)),
        signal: ctrl.signal,
        // A validated HTTPS URL is not permission to follow a 307/308 onto an
        // unvalidated cleartext endpoint with the same POST body.
        redirect: "error",
      });
    } catch (e) {
      clearTimeout(timer);
      const aborted = (e as Error)?.name === "AbortError";
      // network / timeout: retry with backoff
      if (attempt < ENV.apiMaxRetries) {
        await sleep(Math.min(2 ** attempt * 1000, 16_000));
        continue;
      }
      return { ok: false, error: aborted ? `request timed out after ${ENV.requestTimeoutMs}ms` : `fetch failed: ${e}` };
    }

    // reliability-012: fetch() resolving only means the HEADERS arrived — the
    // body may still be streaming. The old code cleared the timer here, which
    // left every subsequent resp.text() call (below, and the error-path reads)
    // completely unbounded: an endpoint that sends headers then stalls the
    // body (slow-loris, buggy proxy buffering, a half-open connection) wedged
    // the worker slot forever, since the scheduler's Promise.race never
    // settles for the wedged task. Keep `ctrl`/`timer` ARMED through every body
    // read below — fetch's AbortSignal covers the whole request lifecycle,
    // including body consumption, so an abort here rejects an in-flight
    // resp.text() the same way it rejects a hung fetch() — and clear the timer
    // exactly once, in the finally, after the LAST body read on every branch.
    try {
      // Transport-level failure (rate limit / server) — back off and retry the
      // REQUEST, not the task. A 429 is not a failed implementation attempt.
      if (resp.status === 429 || resp.status >= 500) {
        if (attempt < ENV.apiMaxRetries) {
          const ra = Number(resp.headers.get("retry-after"));
          const wait = Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(2 ** attempt * 1000, 16_000);
          await sleep(wait);
          continue;
        }
        // Consume the body while the timeout is armed, but never reflect
        // provider-controlled content into stderr, retry prompts, or reports.
        await resp.text();
        return { ok: false, error: `API ${resp.status} after ${ENV.apiMaxRetries} retries` };
      }
      if (!resp.ok) {
        await resp.text();
        return { ok: false, error: `API ${resp.status}` };
      }

      // Read the body as text first, then parse — so a 2xx-with-non-JSON-body
      // (the #90 stale-endpoint failure: a 200 whose body is "Not Found")
      // yields an actionable, endpoint-naming error instead of an opaque
      // SyntaxError. The body is consumed once, so a re-read on parse failure
      // is not possible — parseChatCompletion works off the text we already
      // hold.
      const text = await resp.text();
      return parseChatCompletion(text, apiBaseUrl);
    } catch (e) {
      // reliability-012: a stalled body triggers the SAME armed AbortController
      // as a stalled header, so this catches it as a timeout (not an opaque
      // "fetch failed" — the request already succeeded at the transport level).
      const aborted = (e as Error)?.name === "AbortError";
      return {
        ok: false,
        error: aborted
          ? `request timed out after ${ENV.requestTimeoutMs}ms (reading response body)`
          : `failed reading response body: ${e}`,
      };
    } finally {
      clearTimeout(timer);
    }
  }
  return { ok: false, error: "exhausted API retries" };
}

async function runWorker(
  cwd: string,
  prompt: string,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
  forbidden: Set<string>,
  sampling?: Sampling,
): Promise<WorkerResult> {
  const api = await callApi(prompt, model, apiBaseUrl, apiKey, sampling ?? readSampling());
  if (!api.ok) return { ok: false, filesWritten: [], error: api.error };

  const blocks = extractFileBlocks(api.content);
  const filesWritten: string[] = [];
  for (const { path: filePath, body } of blocks) {
    const cleanPath = filePath.trim();
    const absPath = path.resolve(cwd, cleanPath);
    // Containment: untrusted output may not escape the worktree.
    if (!isInside(cwd, absPath)) {
      return { ok: false, filesWritten, error: `path escapes worktree: ${cleanPath}` };
    }
    // The failing test is read-only — refuse to let the worker touch it.
    // Normalize to forward slashes: plan paths are POSIX-style, but
    // path.relative emits backslashes on Windows and the guard would miss.
    const rel = path.relative(cwd, absPath).split(path.sep).join("/");
    if (forbidden.has(rel)) {
      return { ok: false, filesWritten, error: `worker tried to write read-only path: ${rel}` };
    }
    try {
      await writeWorktreeFile(cwd, rel, body.endsWith("\n") ? body : body + "\n");
    } catch (error) {
      if (isUnsafeWorktreePathError(error)) return { ok: false, filesWritten, error: error.message };
      throw error;
    }
    filesWritten.push(rel);
  }

  if (filesWritten.length === 0) {
    return {
      ok: false,
      filesWritten: [],
      error: "no parseable file blocks in response",
      promptTokens: api.usage?.prompt_tokens,
      completionTokens: api.usage?.completion_tokens,
    };
  }
  return {
    ok: true,
    filesWritten,
    promptTokens: api.usage?.prompt_tokens,
    completionTokens: api.usage?.completion_tokens,
  };
}

// --------------------------------------------------------------------------
// Worker seam (AC-01). The safety gates in runTask wrap ANY worker; the
// HTTP-chat author is just one implementation. A worker is handed the task,
// the resolved model/config, the worktree it must produce files into, and the
// read-only forbidden set, and returns which files it wrote into the worktree.
//
// T-01 scope: this is the indirection point ONLY. httpWorker preserves the
// existing runWorker behavior exactly (it still owns extractFileBlocks + write
// and the inline isInside/read-only guards). Moving apply-ownership and the
// containment sweep to a post-apply step in runTask is T-02 (D6) — not here.
// --------------------------------------------------------------------------
export type WorkerContext = {
  cwd: string;
  prompt: string;
  model: string;
  apiBaseUrl: string;
  apiKey: string;
  forbidden: Set<string>;
  // F4/F1: the effective sampling for this worker call. runTask computes it
  // (FARM_TEMPERATURE, with the best-of-N auto-bump applied per AC-F1.3) and
  // threads it here; absent → the worker reads the live env defaults.
  sampling?: Sampling;
};

export interface Worker {
  apply(ctx: WorkerContext): Promise<WorkerResult>;
}

// Default worker: the existing blind HTTP-chat author, unchanged.
export const httpWorker: Worker = {
  apply: (ctx) =>
    runWorker(ctx.cwd, ctx.prompt, ctx.model, ctx.apiBaseUrl, ctx.apiKey, ctx.forbidden, ctx.sampling),
};

// --------------------------------------------------------------------------
// drift check — path allowlist. Catches modified tracked files and new
// untracked files individually (status --porcelain groups by directory).
// --------------------------------------------------------------------------
// gitRunner is injectable (default = real git) so the stdout-only parsing is
// unit-testable without a repo. Parse STDOUT only (#91): a git stderr line —
// the Windows core.safecrlf `warning: ... LF will be replaced by CRLF` notably —
// must never be mistaken for a changed file path.
export async function checkDrift(
  cwd: string,
  allowed: Set<string>,
  gitRunner: GitRunner = git,
): Promise<string[]> {
  const tracked = await gitRunner(["diff", "--name-only", "HEAD"], cwd);
  const untracked = await gitRunner(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd,
  );
  const changed: string[] = [];
  if (tracked.code === 0)
    changed.push(...tracked.stdout.trim().split("\n").filter(Boolean));
  if (untracked.code === 0)
    changed.push(...untracked.stdout.split("\0").filter(Boolean));
  return [...new Set(changed)].filter((f) => !allowed.has(f));
}

// --------------------------------------------------------------------------
// post-apply containment sweep (D6) — task-level enforcement of containment
// (isInside) and the read-only-test guard over the worker's REPORTED writes.
// It runs in runTask AFTER worker.apply() returns, inspecting the
// `filesWritten` list the worker returns, so it protects against any worker
// type whose write path differs from runWorker's inline loop — provided that
// worker REPORTS what it wrote. The inline guards in runWorker stay as
// defense-in-depth; this task-level sweep catches an escape or a test-path
// write even when the inline guard was bypassed, as long as the path was
// reported. (FINDING 3: narrowed from the prior "AUTHORITATIVE … protects
// against ANY worker type" claim, which over-stated the guarantee.)
//
// [NEEDS-TRIAGE] Path-containment for a NON-REPORTING worker is NOT enforced
// here. A future agentic/premium worker that writes a file OUTSIDE the worktree
// without listing it in `filesWritten` is caught by neither this sweep nor
// checkDrift (which only sees paths inside the worktree). The robust fix is a
// process-level sandbox / cwd-jail guarantee around the worker, deferred to the
// item-3 cross-model roadmap (no sandbox is built in this slice). The shipped
// httpWorker reports its writes faithfully, so it is fully covered today.
//
// Returns a rejection reason (matching the existing /escapes worktree/ and
// read-only/tampered note patterns), or null when every REPORTED path is
// contained and none touches the read-only test.
// --------------------------------------------------------------------------
function postApplySweep(
  cwd: string,
  filesWritten: string[],
  forbidden: Set<string>,
): string | null {
  for (const f of filesWritten) {
    const absPath = path.resolve(cwd, f);
    // Containment: nothing the worker produced may escape the worktree.
    if (!isInside(cwd, absPath)) {
      return `path escapes worktree: ${f}`;
    }
    // The failing test is read-only — reject a worker that wrote it, normalizing
    // to forward slashes (plan paths are POSIX; path.relative emits backslashes
    // on Windows and the guard would otherwise miss).
    const rel = path.relative(cwd, absPath).split(path.sep).join("/");
    if (forbidden.has(rel)) {
      return `worker wrote read-only path: ${rel}`;
    }
  }
  return null;
}

// --------------------------------------------------------------------------
// anti-gaming guard — extractLiterals, codeLineCount, and antiGamingCheck now
// live in ./mutation.ts (v2.rev.0020). antiGamingCheck is imported above and
// wired into defaultRunTaskDeps; the two pure helpers are re-exported from
// "./farm.ts" at the top so the unit-test import surface is unchanged.
// --------------------------------------------------------------------------
async function fileHash(p: string): Promise<string | null> {
  try {
    const buf = await readFile(p);
    return createHash("sha256").update(buf).digest("hex");
  } catch {
    return null;
  }
}

// NOTE (#391): `clean -fd` — deliberately NOT `-fdx`. Ignored paths are
// PRESERVED, which is what makes a gitignored dependency tree survive the
// inter-attempt reset (and is why `setup` is once-per-worktree, not
// once-per-attempt). Tracked changes and non-ignored untracked worker output are
// still wiped, so nothing stale carries into the next attempt.
async function resetWorktree(wt: string) {
  await git(["reset", "--hard", "HEAD"], wt);
  await git(["clean", "-fd"], wt);
}

// --------------------------------------------------------------------------
// setup phases (#92 / #391)
// --------------------------------------------------------------------------
// Two distinct phases, because one `setup` list could not tell a one-time
// dependency install from a per-attempt rebuild:
//
//   setup            — once per worktree. Its output is required to be
//                      gitignored, and `git clean -fd` preserves ignored paths,
//                      so it survives every reset. Re-running it was paying the
//                      full install up to 3x (default budget) for nothing.
//   setupEachAttempt — before every attempt, for commands that rebuild ignored
//                      output from tracked source and DO go stale on reset.
//
// The `setup` cache is a fingerprint, scoped to exactly one worktree by living
// in a caller-owned SetupState (no module-level map, so nothing can leak across
// tasks or runs). It covers the setup commands plus the content hashes of the
// task's declared `setupInputs`, so a baseline that moves under the worktree —
// regenerate-on-conflict resets onto a NEW integration HEAD — reinstalls.
export type SetupState = { key: string | null };

async function setupFingerprint(wt: string, t: Task, deps: RunTaskDeps): Promise<string> {
  const parts = [JSON.stringify(t.setup ?? [])];
  for (const rel of t.setupInputs ?? [])
    parts.push(`${rel}=${(await deps.fileHash(path.resolve(wt, rel))) ?? "absent"}`);
  return createHash("sha256").update(parts.join(" ")).digest("hex");
}

/** Runs both setup phases for one attempt. Returns a redacted note on failure, null on success. */
async function runSetupPhases(
  wt: string,
  t: Task,
  deps: RunTaskDeps,
  state: SetupState,
): Promise<string | null> {
  if (t.setup && t.setup.length > 0) {
    const key = await setupFingerprint(wt, t, deps);
    if (key !== state.key) {
      const r = await deps.runGate(wt, t.setup);
      if (!r.ok) return redactSecrets(`setup failed: ${r.failed}\n${r.tail}`);
      state.key = key;
    }
  }
  if (t.setupEachAttempt && t.setupEachAttempt.length > 0) {
    const r = await deps.runGate(wt, t.setupEachAttempt);
    if (!r.ok) return redactSecrets(`setup failed (setupEachAttempt): ${r.failed}\n${r.tail}`);
  }
  return null;
}

// --------------------------------------------------------------------------
// mutation guard — shuffle, generateMutants, MutationResult, the exported
// parseMutationHookOutput, and mutationCheck now live in ./mutation.ts
// (v2.rev.0020). mutationCheck is imported above and wired into
// defaultRunTaskDeps; parseMutationHookOutput is re-exported from "./farm.ts" at
// the top so the unit-test import surface is unchanged.
// --------------------------------------------------------------------------

// --------------------------------------------------------------------------
// per-task lifecycle
// --------------------------------------------------------------------------
type Result = {
  id: string;
  status: "green" | "escalate";
  attempts: number;
  branch: string;
  worktree: string;
  note?: string;
  warning?: string;
  filesWritten?: string[];
  diffstat?: string;
  promptTokens?: number;
  completionTokens?: number;
  mutationScore?: number | null;
  // F1/AC-F1.6: best-of-N cost transparency. `samples` = candidates drawn for
  // the accepted attempt; `promptTokens`/`completionTokens` already SUM every
  // sample (total spend), and these expose the ACCEPTED candidate's own tokens
  // so the report can show accepted-vs-total. Absent / equal at FARM_SAMPLES=1.
  samples?: number;
  acceptedPromptTokens?: number;
  acceptedCompletionTokens?: number;
  // observability-003 (T-07c): run-level correlation id, stamped onto every
  // result before it is appended to farm-results.jsonl, so concurrent farm runs
  // writing to the same .farm/ directory produce distinguishable lines that tie
  // back to a single farm-report.json header.
  runId?: string;
  // #398: teardown outcomes for the resources this task owned — its worktree and
  // any best-of-N sample worktrees/branches. Present only when at least one
  // could not be verified released, so a green status is never unqualified:
  // the leak travels with the result, into the receipt, and into the exit code.
  cleanup?: CleanupOutcome[];
};

// observability-003 (T-07c): a run-id minted once at main() startup.
//
// #397 widened this from 3 bytes to 8. It was originally a cosmetic
// correlation label in a shared JSONL stream, where a rare duplicate cost
// nothing; it is now the NAME OF THE DIRECTORY that holds a run's durable
// receipts, so a collision does not merely duplicate a label — it makes a new
// run publish over a previous run's evidence. 24 bits put a birthday collision
// at roughly 4k runs in one long-lived `.farm/`, which is reachable; 64 bits
// put it past any plausible number of runs. 16 hex chars still fits
// assertSafeRunId's 64-character path-segment budget.
export function mintRunId(): string {
  return randomBytes(8).toString("hex");
}

const msgOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

// #397: a caller-supplied FARM_RUN_ID becomes a DIRECTORY NAME under
// `${reportDir}/runs/`, so it has to be exactly one safe path segment — no
// separator, no traversal, no dot-only id. Fail closed and loudly at startup
// rather than silently substituting a random id (which would hide a
// misconfigured orchestrator) or letting `../` place artifacts outside the
// report dir.
export const SAFE_RUN_ID = /^[A-Za-z0-9._-]{1,64}$/;

// #440: the character class above is necessary but NOT sufficient. Windows
// reserves a set of DEVICE names that match `[A-Za-z0-9._-]` perfectly, and
// resolves them before any extension — so `NUL`, `nul`, `NUL.txt` and
// `com1.log.1` all name the device, not a file. `mkdir` against one behaves
// unpredictably, and `mkdir(runDir)` sits OUTSIDE the run's try/finally, so the
// failure is an unhandled throw BEFORE the cleanup scope exists — and the run's
// receipts, which are its recovery record, are lost with it.
//
// Refused on EVERY platform, not only Windows. `FARM_RUN_ID` is set by an
// orchestrator whose configuration travels between machines, and an id that
// works on one developer's Linux box while detonating on a colleague's Windows
// one is exactly the class of failure a startup gate exists to prevent.
//
// Matched on the STEM ONLY — the text before the first `.`, which is what
// Windows itself resolves — and anchored, so ordinary ids that merely resemble
// a device name (`console`, `nulls`, `COM0`, `COM10`, `my-nul`) stay valid.
const RESERVED_RUN_ID_STEM = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
export function assertSafeRunId(id: string): string {
  if (!SAFE_RUN_ID.test(id) || id === "." || id === "..")
    throw new Error(
      `FARM_RUN_ID must be 1-64 characters of [A-Za-z0-9._-] and not "." or ".." (got ${JSON.stringify(id)})`,
    );
  if (RESERVED_RUN_ID_STEM.test(id.split(".")[0]))
    throw new Error(
      `FARM_RUN_ID must not be a Windows reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9), ` +
        `with or without an extension — the run directory could not be created (got ${JSON.stringify(id)})`,
    );
  return id;
}

// #397: every run owns a directory. The run dir holds this run's DURABLE
// receipts — stream, per-task diffs, JSON + Markdown report — written by this
// process alone, so two farm invocations against one repository can no longer
// erase each other's evidence. The historical top-level `.farm/farm-report.*`
// and `.farm/farm-results.jsonl` paths are retained as a "latest" convenience
// pointer for the documented consumer contract; under concurrency the pointer
// is last-writer-wins (but always a COMPLETE artifact — see atomicWriteFile),
// while the run dirs stay authoritative and attributable.
export function runArtifactDir(runId: string): string {
  return path.join(ENV.reportDir, "runs", runId);
}

// Windows can transiently refuse a replace-rename with EPERM/EACCES/EBUSY while
// another process (or a virus scanner) still holds the destination open — the
// exact situation two concurrent farm runs publishing a shared "latest" pointer
// create. A short bounded retry keeps that from spuriously failing a run.
async function renameWithRetry(from: string, to: string, attempts = 4): Promise<void> {
  for (let i = 0; ; i++) {
    try {
      await rename(from, to);
      return;
    } catch (e) {
      const code = (e as NodeJS.ErrnoException).code ?? "";
      if (i >= attempts - 1 || !["EPERM", "EACCES", "EBUSY"].includes(code)) throw e;
      await new Promise((r) => setTimeout(r, 15 * (i + 1)));
    }
  }
}

// #397: publish-or-preserve. A plain writeFile() TRUNCATES the destination
// before it writes, so a crash — or a second farm process — can leave a
// half-written farm-report.json where a complete one used to be, destroying the
// restart evidence exactly when it is needed. Write the whole payload to a
// same-directory temp file, fsync its CONTENTS, then rename over the
// destination. A rename within a directory is atomic, so a reader sees either
// the previous complete artifact or the new complete artifact — never a
// truncated one. On failure the temp file is removed and the destination is
// left exactly as it was.
//
// Scope of the guarantee, stated precisely rather than generously: what this
// buys is NO-TORN-FILE ATOMICITY against process death and against a concurrent
// publisher — the failure modes farm actually hits. It is NOT full crash
// durability: the directory entry created by the rename is never fsynced (Node
// has no portable directory-fsync, and none at all on Windows), so a power loss
// immediately after publication may still lose the rename. Do not read the
// fh.sync() below as a promise that a published receipt survives a host crash.
/** Injectable file-open seam. Production passes nothing; a test supplies a
 * handle whose write rejects, which is the only deterministic way to exercise
 * the WRITE-path cleanup - Node silently substitutes U+FFFD for an unencodable
 * payload rather than throwing, so there is no "bad data" that forces it. Same
 * dependency-injection shape this file already uses for RunTaskDeps and the
 * worker/gate seams (#439 AC-4). */
export type AtomicWriteDeps = { open?: typeof open };

export async function atomicWriteFile(
  dest: string,
  data: string,
  deps: AtomicWriteDeps = {},
): Promise<void> {
  const tmp = path.join(
    path.dirname(dest),
    `.${path.basename(dest)}.${process.pid}-${randomBytes(4).toString("hex")}.tmp`,
  );
  // #439 AC-3: the destination's mode, if it already exists. The old
  // `writeFile(dest, ...)` opened O_TRUNC and PRESERVED the mode; creating a
  // temp at the umask default (0644) and renaming over the destination lets the
  // temp's mode win, so an operator who hardened a report to 0600 got it reset
  // on every run. Read before the write so a mid-publish failure cannot lose it.
  const priorMode = await stat(dest).then((s) => s.mode & 0o777).catch(() => undefined);
  // "wx" (O_EXCL): the random suffix already makes the name unpredictable, but
  // exclusive creation means the temp can never follow a pre-existing symlink
  // planted at that path. Free, so there is no reason not to.
  const fh = await (deps.open ?? open)(tmp, "wx");
  try {
    await fh.writeFile(data, "utf8");
    await fh.sync();
    if (priorMode !== undefined) await fh.chmod(priorMode);
  } catch (e) {
    // #439 AC-4: cleanup used to be attached only to the RENAME. A failing
    // write or sync (ENOSPC, EIO, an unencodable payload) left a
    // partially-written temp file on disk holding the payload - and the test
    // that claimed to cover this only exercised the rename path, so its title
    // read broader than its coverage.
    await fh.close().catch(() => {});
    await rm(tmp, { force: true }).catch(() => {});
    throw e;
  }
  await fh.close();
  try {
    await renameWithRetry(tmp, dest);
  } catch (e) {
    await rm(tmp, { force: true }).catch(() => {});
    throw e;
  }
}

// #387/#397: the artifacts a run publishes fall into exactly two classes, and
// the whole exit-code contract rests on keeping them apart.
//
//   AUTHORITATIVE — `${reportDir}/runs/<runId>/farm-report.{json,md}`. This is
//   the run's durable, attributable receipt, written by this process alone.
//   Failing to publish it fails the run (exit 3): there is then nothing to
//   reconcile or audit against.
//
//   NON-AUTHORITATIVE — the shared "latest" pointers under `${reportDir}/`
//   (farm-report.{json,md}, farm-results.jsonl, diffs/) and the streaming rail
//   and per-task diffs generally. These are convenience and best-effort
//   evidence. A failure here must NOT sink a run whose authoritative receipt
//   landed — that would over-report failure exactly where two concurrent runs
//   race the same pointer, which is the case #397 exists for. But it can no
//   longer be swallowed silently either: it is recorded here and surfaced so a
//   consumer never infers completeness from a silently short file, follows a
//   patch link that was never written, or reads a stale pointer as this run's.
export type RunArtifactHealth = {
  stream: { errors: string[] };
  diffs: {
    unavailable: { id: string; reason: string }[];
    // The TRUE count, which `unavailable` deliberately stops recording at
    // MAX_RECORDED_ARTIFACT_ERRORS. Reported separately so bounding the list
    // never understates the damage.
    unavailableTotal: number;
    latestMirrorErrors: string[];
  };
  // Failures to refresh the shared latest report pointers. These cannot appear
  // inside the report itself (the payload is already serialized by the time the
  // pointers are written), so main() surfaces them on the summary instead.
  report: { latestMirrorErrors: string[] };
  // #398: RUN-level resource teardown that could not be verified — today the
  // integration worktree, which no task owns. Task-owned leaks ride on the
  // Result; these have nowhere else to live, so they are collected here and
  // folded into the same report section and exit code.
  cleanup: { failures: { target: string; detail: string }[] };
};

export function newRunArtifactHealth(): RunArtifactHealth {
  return {
    stream: { errors: [] },
    diffs: { unavailable: [], unavailableTotal: 0, latestMirrorErrors: [] },
    report: { latestMirrorErrors: [] },
    cleanup: { failures: [] },
  };
}

// #439 - what the run's PERMANENT receipt is allowed to carry.
//
// The run-scoped change did not create this exposure, it changed its shape.
// `.farm/farm-report.json` used to be clobbered by the next run; `.farm/runs/
// <runId>/` now accumulates indefinitely with no prune path, so a secret that
// used to be destroyed within one run persists instead.
//
// NOT an allowlist, deliberately. The issue proposed projecting
// `{name, repo, model, apiBaseUrl, setup}` at the sink, but `checkPlanObject`
// is already a CLOSED object check and plan-contract.test.ts pins that an
// unknown `meta` property throws at parse. A sink allowlist would be a second
// copy of a control that already exists, and would have caught nothing.
//
// The exposure is the opposite shape: the ALLOWED fields are the dangerous
// ones. `setup`, `setupEachAttempt` and `setupInputs` are raw shell-command
// arrays and `apiBaseUrl` is a URL that can carry credentials, so a token in a
// setup command is a perfectly legal plan that parses cleanly and lands
// verbatim in the receipt. Redaction - not deletion: a receipt that silently
// dropped the setup it ran would be a worse receipt.
//
// WHAT THIS DOES NOT CLOSE, stated plainly rather than implied. `redactSecrets`
// is keyword- and prefix-driven, so a credential wearing none of its shapes
// still lands in the receipt - measured misses include `glpat-`, `sk-proj-`,
// basic-auth in a clone URL (`https://user:pass@host`), and a bare
// `Authorization: Bearer eyJ...`. Several of those are widened in redactor.ts
// alongside this change, but the class is open-ended: this reduces the blast
// radius of a secret in a plan, it does not make plan.meta a safe place to put
// one. The per-task `.patch` files in the same run directory are also written
// raw, deliberately - a patch that has been redacted no longer applies.
export function projectPlanMetaForReport<T extends Record<string, unknown>>(meta: T): T {
  const scrub = (v: unknown): unknown =>
    typeof v === "string" ? redactSecrets(v) : Array.isArray(v) ? v.map(scrub) : v;
  return Object.fromEntries(Object.entries(meta).map(([k, v]) => [k, scrub(v)])) as T;
}

// Bound the recorded error list — a dead stream path fails once per settled
// task, and the report should carry a diagnosis, not N copies of it.
export const MAX_RECORDED_ARTIFACT_ERRORS = 10;
// #439: redact HERE rather than at each of the five call sites. Every other
// report-bound free-text field in this file is redacted at construction; the
// artifacts block was the one new class of report content that skipped the
// chokepoint, and it carries raw git stderr (`git diff failed: <output>`) and
// `msgOf(e)` strings straight into a permanently retained receipt. One sink,
// one rule - a sixth caller cannot forget. `redactSecrets` is documented
// idempotent, so a message that was already redacted upstream is unharmed.
export function noteArtifactError(bucket: string[], message: string) {
  const safe = redactSecrets(message);
  if (bucket.length < MAX_RECORDED_ARTIFACT_ERRORS) bucket.push(safe);
  else if (bucket.length === MAX_RECORDED_ARTIFACT_ERRORS) bucket.push("(further errors suppressed)");
}

// Same bound for the per-task diff-evidence list, which has the identical
// failure shape (one unusable diffs directory = one entry per task in the
// plan). The running total is kept so the report states how many tasks are
// actually affected even though it only lists the first few.
export function noteUnavailableDiff(diffs: RunArtifactHealth["diffs"], id: string, reason: string) {
  // #439: redacted here for the same reason noteArtifactError is. This is the
  // function that actually receives `git diff failed: <raw git stderr>`,
  // `diffs directory unavailable: <fs error>` and `patch write failed:
  // <msgOf(e)>` - the three strings the issue names. Those reasons reach BOTH
  // receipts: artifacts.diffs.unavailable[].reason in the JSON, and the
  // "Diff evidence" list in the Markdown.
  const safe = redactSecrets(reason);
  diffs.unavailableTotal += 1;
  if (diffs.unavailable.length < MAX_RECORDED_ARTIFACT_ERRORS) diffs.unavailable.push({ id, reason: safe });
  else if (diffs.unavailable.length === MAX_RECORDED_ARTIFACT_ERRORS)
    diffs.unavailable.push({
      id: "(suppressed)",
      reason: `further entries suppressed after ${MAX_RECORDED_ARTIFACT_ERRORS}`,
    });
}

// Integration merges happen inside a dedicated worktree — never the main
// checkout. mergeChain serializes access to that worktree.
let mergeChain: Promise<unknown> = Promise.resolve();
let integrationWorktree: string;

function withMergeLock<T>(fn: () => Promise<T>): Promise<T> {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {});
  return next;
}

async function prepareWorktree(branch: string, wt: string, from: string): Promise<string | null> {
  // #163: fail closed before the recursive delete — the resolved path must be
  // strictly inside the allowed (in-repo) farm worktree root. This is the
  // load-bearing guard: `rm(wt, {recursive, force})` below is the exact
  // destructive op an out-of-repo root + plausible task id would weaponize.
  try {
    assertContainedWorktree(wt);
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
  // Clean any stale worktree dir and branch so a re-run doesn't trip over the
  // leftovers of a prior run (git worktree add -b fails if the branch exists).
  await git(["worktree", "remove", "--force", wt]).catch(() => {});
  await rm(wt, { recursive: true, force: true }).catch(() => {});
  await git(["branch", "-D", branch]).catch(() => {});
  const add = await git(["worktree", "add", "-b", branch, wt, from]);
  if (add.code !== 0) return `worktree add failed: ${add.out.slice(0, 200)}`;
  return null;
}

// --------------------------------------------------------------------------
// #398 — verified resource teardown.
//
// Every teardown site in this file used to be `git(...).catch(() => {})`, and
// the task's success path returned `status: "green"` on the very next line. A
// Windows file lock, an antivirus scan holding a handle, or any git failure
// therefore left a worktree registered and on disk while the run reported
// success — and the NEXT run's best-effort destructive pre-cleanup was the only
// thing standing between that leak and an ambiguous re-registration.
//
// #430 established the tiering rule this follows: an authoritative outcome
// fails the run, a convenience mirror warns. Releasing ownership of a worktree
// is authoritative — it is the farm's claim on a directory and a branch — so a
// teardown that cannot be VERIFIED is reported on the result, printed on the
// summary, persisted in the receipt, and lifts the run's exit code. The
// operations below are non-destructive beyond what git itself does: they retry
// and then TELL you, rather than escalating to an unbounded rm.
// --------------------------------------------------------------------------

// The outcome of one bounded, verified teardown. `ok` means the resource is
// verifiably GONE — not merely that a removal command was issued.
export type CleanupOutcome = { ok: boolean; target: string; attempts: number; detail?: string };

// Bounded backoff for a transient Windows lock (a scanner or an editor holding a
// handle usually clears in tens of milliseconds). Deliberately small: the point
// is to ride out a race, not to wait out a genuinely stuck resource.
const CLEANUP_ATTEMPTS = 3;
const CLEANUP_DELAY_MS = 150;

// Path comparison for `git worktree list --porcelain` output. git prints
// forward slashes even on Windows, and Windows paths are case-insensitive, so
// compare RESOLVED, normalized forms rather than raw strings.
function samePath(a: string, b: string): boolean {
  const norm = (p: string) => {
    const r = path.resolve(p);
    return process.platform === "win32" ? r.toLowerCase() : r;
  };
  return norm(a) === norm(b);
}

// Does git still register `wt` as a worktree? This — not the removal command's
// exit code — is the authority: a removal that "failed" but left git with no
// registration and no directory has still released ownership, and a removal
// that "succeeded" while git keeps the registration has not.
async function stillRegistered(gitFn: GitRunner, wt: string): Promise<boolean> {
  const listed = await gitFn(["worktree", "list", "--porcelain"]);
  if (listed.code !== 0) return true; // cannot verify ⇒ do not claim success
  return listed.stdout
    .split("\n")
    .filter((l) => l.startsWith("worktree "))
    .some((l) => samePath(l.slice("worktree ".length).trim(), wt));
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

// Remove a farm worktree and PROVE it is gone: `worktree remove --force`, then
// `worktree prune` (which clears a registration whose directory already went
// away), then re-verify against `worktree list --porcelain` AND the filesystem.
// Retries a bounded number of times so a transient lock does not become a
// permanent leak, and returns a diagnosable ok:false when it cannot be cleared.
export async function removeWorktreeVerified(
  gitFn: GitRunner,
  wt: string,
  opts: { attempts?: number; delayMs?: number } = {},
): Promise<CleanupOutcome> {
  const attempts = opts.attempts ?? CLEANUP_ATTEMPTS;
  const delayMs = opts.delayMs ?? CLEANUP_DELAY_MS;
  let lastErr = "";
  for (let i = 1; i <= attempts; i++) {
    const rmR = await gitFn(["worktree", "remove", "--force", wt]);
    if (rmR.code !== 0) lastErr = rmR.out.trim().split("\n").slice(-1)[0] ?? "";
    let registered = await stillRegistered(gitFn, wt);
    const present = await pathExists(wt);
    // Prune clears a stale registration whose directory is already gone — the
    // exact state a partially-failed removal or an external delete leaves.
    // Run it ONLY in that state: `git worktree prune` is repo-wide, and a
    // blanket call would also deregister an unrelated worktree whose path is
    // merely unreachable right now (an unmounted volume, a temporarily denied
    // directory). Narrow it to the condition it is actually needed for.
    if (registered && !present) {
      await gitFn(["worktree", "prune"]);
      registered = await stillRegistered(gitFn, wt);
    }
    if (!registered && !present) return { ok: true, target: wt, attempts: i };
    if (i < attempts) await sleep(delayMs * i);
    else
      return {
        ok: false,
        target: wt,
        attempts: i,
        detail: redactSecrets(
          [
            registered ? `still registered as a git worktree after ${i} attempt(s)` : null,
            present ? `directory still present on disk after ${i} attempt(s)` : null,
            lastErr ? `last git error: ${lastErr}` : null,
          ]
            .filter(Boolean)
            .join("; "),
        ).slice(0, 500),
      };
  }
  /* istanbul ignore next — the loop always returns */
  return { ok: false, target: wt, attempts, detail: "cleanup loop did not settle" };
}

// Delete a farm scratch branch and PROVE it is gone. `branch --list` is used for
// verification rather than `rev-parse` because an empty listing unambiguously
// means "absent", whereas rev-parse's exit code also encodes other failures.
export async function deleteBranchVerified(
  gitFn: GitRunner,
  branch: string,
  opts: { attempts?: number; delayMs?: number } = {},
): Promise<CleanupOutcome> {
  const attempts = opts.attempts ?? CLEANUP_ATTEMPTS;
  const delayMs = opts.delayMs ?? CLEANUP_DELAY_MS;
  let lastErr = "";
  for (let i = 1; i <= attempts; i++) {
    const del = await gitFn(["branch", "-D", branch]);
    if (del.code !== 0) lastErr = del.out.trim().split("\n").slice(-1)[0] ?? "";
    const listed = await gitFn(["branch", "--list", branch]);
    const present = listed.code !== 0 || listed.stdout.trim() !== "";
    if (!present) return { ok: true, target: branch, attempts: i };
    if (i < attempts) await sleep(delayMs * i);
    else
      return {
        ok: false,
        target: branch,
        attempts: i,
        detail: redactSecrets(
          `branch still present after ${i} attempt(s)${lastErr ? `; last git error: ${lastErr}` : ""}`,
        ).slice(0, 500),
      };
  }
  /* istanbul ignore next — the loop always returns */
  return { ok: false, target: branch, attempts, detail: "cleanup loop did not settle" };
}

// The run's exit code from its two independent failure axes. #387 established
// 0/2/3; #398 adds a third input on the "2" side — a run that leaked a worktree
// or a branch has not come out clean, whatever the tasks did, because the next
// run inherits ambiguous state. (3, the authoritative-receipt failure, still
// outranks it and is applied by the caller.)
export function runExitCode(o: {
  escalated: number;
  blocked: number;
  aborted: boolean;
  cleanupFailures: number;
}): 0 | 2 {
  return o.escalated || o.blocked || o.aborted || o.cleanupFailures ? 2 : 0;
}

// Every unreleased resource this run is responsible for, from both places they
// can be recorded: the task results (worktrees and sample branches a task owned)
// and the run-level health (the integration worktree, owned by no task).
export function cleanupFailures(
  health: RunArtifactHealth,
  results: Result[],
): { owner: string; target: string; detail: string }[] {
  return [
    ...results.flatMap((r) =>
      (r.cleanup ?? [])
        .filter((c) => !c.ok)
        .map((c) => ({ owner: r.id, target: c.target, detail: c.detail ?? "unverified" })),
    ),
    ...health.cleanup.failures.map((f) => ({ owner: "run", target: f.target, detail: f.detail })),
  ];
}

// The report's cleanup section. Stated in both directions on purpose: silence is
// not evidence of a clean teardown, so the clean case says so explicitly rather
// than omitting the section (an operator must be able to tell "nothing leaked"
// from "this report predates the check").
export function cleanupReportLines(health: RunArtifactHealth, results: Result[]): string[] {
  const failures = cleanupFailures(health, results);
  if (failures.length === 0)
    return [`## Resource cleanup`, `Every farm worktree and scratch branch was removed and re-verified.`];
  return [
    `## Resource cleanup`,
    `> **CLEANUP DEGRADED** — ${failures.length} resource(s) could not be released and re-verified. ` +
      `They may still be registered with git or present on disk, and the next run will collide with or ` +
      `destructively pre-clean them. Exit code is non-zero for this reason alone.`,
    ...failures.map((f) => `- \`${f.target}\` (${f.owner}) — ${f.detail}`),
  ];
}

// #525: both mutation risk arms report the SAME quantity — how many mutants the
// task's test failed to catch — and they were written independently, so they
// drifted. The escalate arm interpolated `evaluated` under a "survived" label,
// so a run that killed 1 of 10 reported "10 mutants survived" while printing a
// 0.10 score in the same sentence. One formatter now renders it for both arms,
// so the two cannot disagree again.
//
// #525: state the score, and state a survivor count ONLY when the producer
// actually reported one. Three earlier fixes each tried to always produce a
// count — reading a list that is empty on the hook path, then deriving from the
// score, then substituting a default denominator — and each moved the
// fabrication to a different input instead of removing it. A hook is only
// required to print a numeric `score` (includes/farm.md), so for the rest there
// is often nothing to say, and saying nothing is the correct output.
//
// This note is the whole operator-facing justification for rejecting a task and
// it is fed back into the next worker's prompt. A missing count costs a reader
// some detail; an invented one tells them something false in the sentence that
// explains the rejection, which is what #525 was.
export function mutationSurvivalNote(m: MutationResult): string {
  const score = `score ${m.score.toFixed(2)}`;
  if (m.survivors === undefined) return score;
  const of = m.evaluated === undefined ? "" : `/${m.evaluated}`;
  return `${score} (${m.survivors.length}${of} survived)`;
}

// Injectable dependencies for runTask. Every field defaults to the real
// implementation, so callers (main/canary) get unchanged behavior. The seam
// exists so the task-execution path can drive a stub Worker — and stub its
// git/process/fs effects — under unit test without the network. The worker is
// injected here (not called as runWorker directly), which is the AC-01 cut.
export type RunTaskDeps = {
  worker: Worker;
  prepareWorktree: typeof prepareWorktree;
  resetWorktree: typeof resetWorktree;
  fileHash: typeof fileHash;
  checkDrift: typeof checkDrift;
  runGate: typeof runGate;
  antiGamingCheck: typeof antiGamingCheck;
  mutationCheck: typeof mutationCheck;
  git: typeof git;
  withMergeLock: typeof withMergeLock;
};

const defaultRunTaskDeps = (): RunTaskDeps => ({
  worker: httpWorker,
  prepareWorktree,
  resetWorktree,
  fileHash,
  checkDrift,
  runGate,
  antiGamingCheck,
  mutationCheck,
  git,
  withMergeLock,
});

// F1 — effective sampling for a run. AC-F1.3: N>1 with a deterministic
// temperature 0 produces N identical samples, which defeats best-of-N; bump to a
// diversifying default (logged) unless the operator set FARM_TEMPERATURE.
function effectiveSampling(samples: number): Sampling {
  const s = readSampling();
  // Bump only when the temperature is an UNSET default 0. An operator who set
  // FARM_TEMPERATURE explicitly — including to 0 — gets exactly what they asked
  // for; the stderr hint ("set FARM_TEMPERATURE to override") would otherwise lie
  // for the explicit-0 case.
  const explicit = (process.env.FARM_TEMPERATURE ?? "") !== "";
  if (samples > 1 && s.temperature === 0 && !explicit) {
    process.stderr.write(
      `[FARM] FARM_SAMPLES=${samples} with no FARM_TEMPERATURE set — bumping temperature to 0.7 so samples diversify (set FARM_TEMPERATURE to override)\n`,
    );
    return { ...s, temperature: 0.7 };
  }
  return s;
}

// F1 — materialize the winning sample's in-scope files into the task worktree,
// so the unchanged post-selection pipeline (sweep/tamper/drift/gate/anti-gaming/
// commit/merge) runs against `wt` exactly as in the single-sample path. Only
// in-scope impl files are written (the test is already present in `wt`); a path
// that would escape the worktree is refused (defense-in-depth — winner files are
// in-scope already).
export async function writeFilesInto(wt: string, files: Array<{ path: string; contents: string }>): Promise<void> {
  for (const f of files) {
    const abs = path.resolve(wt, f.path);
    if (!isInside(wt, abs)) throw new UnsafeWorktreePathError();
    await writeWorktreeFile(wt, f.path, f.contents.endsWith("\n") ? f.contents : f.contents + "\n");
  }
}

// F1 — one best-of-N sample: a full candidate gating (worker → containment sweep
// → test-tamper → drift → gate) in an isolated scratch worktree cut from
// integration HEAD. Drawn through the shared worker-call limiter (AC-F1.4). On
// green it captures the in-scope impl files so the winner can be materialized
// into the task worktree.
type SampleOutcome = {
  green: boolean;
  filesWritten: string[];
  files: Array<{ path: string; contents: string }>;
  inScope: Array<{ path: string; contents: string }>;
  note?: string;
  promptTokens: number;
  completionTokens: number;
  wt: string;
  branch: string;
};

async function bestOfN(
  t: Task,
  prompt: string,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
  sampling: Sampling,
  forbidden: Set<string>,
  allowed: Set<string>,
  n: number,
  deps: RunTaskDeps,
): Promise<{
  winner: SampleOutcome | null;
  bestFailure: SampleOutcome | null;
  promptTokens: number;
  completionTokens: number;
  // #398: one entry per sample resource torn down, ok or not.
  cleanup: CleanupOutcome[];
}> {
  // All sample worktrees are cut from the same integration HEAD as the task
  // worktree, so they share the baseline the single `prompt` was enriched
  // against — the prompt is reused rather than rebuilt per sample.
  // Samples are cut from the TASK branch (a frozen snapshot of integration HEAD
  // at task start) — NOT from the live `farm/integration` ref — so every sample
  // shares the EXACT baseline the task worktree re-gates and merges against
  // (AC-F1.2). This is immune to a non-overlapping sibling task moving
  // farm/integration mid-flight (which would otherwise gate a sample against a
  // newer baseline than the task worktree, causing a false escalation).
  const taskBranch = `farm/${t.id}`;
  const runSample = (k: number): Promise<SampleOutcome> =>
    workerLimit.run(async () => {
      const branch = `farm/${t.id}__s${k}`;
      const wt = path.resolve(ENV.worktreeRoot, `${t.id}__s${k}`);
      const base: SampleOutcome = {
        green: false, filesWritten: [], files: [], inScope: [], promptTokens: 0, completionTokens: 0, wt, branch,
      };
      try {
        const prep = await deps.prepareWorktree(branch, wt, taskBranch);
        if (prep) return { ...base, note: prep };
        // Each sample gets a FRESH worktree, so its setup cache starts empty and
        // dies with the sample — a sample never reuses another worktree's install.
        const setupNote = await runSetupPhases(wt, t, deps, { key: null });
        if (setupNote) return { ...base, note: setupNote };
        const testHashBefore = await deps.fileHash(path.resolve(wt, t.test.path));
        const w = await deps.worker.apply({ cwd: wt, prompt, model, apiBaseUrl, apiKey, forbidden, sampling });
        const pt = w.promptTokens ?? 0;
        const ct = w.completionTokens ?? 0;
        if (!w.ok) return { ...base, note: redactSecrets(`worker error: ${w.error}`), promptTokens: pt, completionTokens: ct };
        const sweep = postApplySweep(wt, w.filesWritten, forbidden);
        if (sweep) return { ...base, filesWritten: w.filesWritten, note: sweep, promptTokens: pt, completionTokens: ct };
        const testHashAfter = await deps.fileHash(path.resolve(wt, t.test.path));
        if (testHashBefore !== null && testHashAfter !== testHashBefore)
          return { ...base, filesWritten: w.filesWritten, note: `tampered test: ${t.test.path}`, promptTokens: pt, completionTokens: ct };
        const drift = await deps.checkDrift(wt, allowed);
        if (drift.length > 0)
          return { ...base, filesWritten: w.filesWritten, inScope: await captureInScope(wt, t), note: `drift: ${drift.join(", ")}`, promptTokens: pt, completionTokens: ct };
        const gate = await deps.runGate(wt, t.gate.commands);
        if (!gate.ok)
          return { ...base, filesWritten: w.filesWritten, inScope: await captureInScope(wt, t), note: redactSecrets(`failed: ${gate.failed}\n${gate.tail}`), promptTokens: pt, completionTokens: ct };
        const inScope = await captureInScope(wt, t);
        return { green: true, filesWritten: w.filesWritten, files: inScope, inScope, promptTokens: pt, completionTokens: ct, wt, branch };
      } catch (e) {
        // A sample that THROWS (fs/git error mid-flight) must still resolve to a
        // failure OUTCOME, not reject — so Promise.all below never rejects and the
        // cleanup loop always removes every scratch worktree (M1: no leak on the
        // exception path). `base` already carries this sample's wt/branch.
        return { ...base, note: `sample error: ${e instanceof Error ? e.message : String(e)}` };
      }
    });

  const outcomes = await Promise.all(Array.from({ length: n }, (_, k) => runSample(k)));
  const promptTokens = outcomes.reduce((s, o) => s + o.promptTokens, 0);
  const completionTokens = outcomes.reduce((s, o) => s + o.completionTokens, 0);
  // First green by sample index wins (deterministic; avoids a wall-clock race).
  const winner = outcomes.find((o) => o.green) ?? null;
  // Best failure to seed the retry: prefer one that reached the gate (has its
  // in-scope output for F2), else any failure.
  const bestFailure = outcomes.find((o) => !o.green && o.inScope.length > 0) ?? outcomes.find((o) => !o.green) ?? null;
  // Discard every sample worktree — the winner's files are already captured.
  // #398: verified, and EVERY sample is attempted even after one fails. The old
  // loop swallowed each failure, so one stuck sample was indistinguishable from
  // a clean sweep; worse, a leaked sample worktree keeps its branch checked out,
  // which then makes the branch delete fail too. Both outcomes are returned so
  // the task result can carry the full list of what is still on disk.
  const cleanup: CleanupOutcome[] = [];
  for (const o of outcomes) {
    cleanup.push(await removeWorktreeVerified(deps.git, o.wt));
    cleanup.push(await deleteBranchVerified(deps.git, o.branch));
  }
  return { winner, bestFailure, promptTokens, completionTokens, cleanup };
}

export async function runTask(
  t: Task,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
  deps: RunTaskDeps = defaultRunTaskDeps(),
): Promise<Result> {
  const branch = `farm/${t.id}`;
  const wt = path.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;
  // Per-task model (AC-02): layer the optional task-level override on top of the
  // run-level resolved model (the `model` param, from resolveConfig:
  // ENV.model ?? plan.meta.model — itself unchanged). Absent task.model →
  // effectiveModel === model, i.e. exactly today's behavior. Model id only.
  const effectiveModel = t.model ?? model;
  const allowed = new Set(t.filesInScope);
  const forbidden = new Set([t.test.path]);
  // F1: best-of-N. FARM_SAMPLES read live (default 1 = today's single-candidate
  // path). A non-numeric / non-finite value falls back to 1 rather than poisoning
  // the run with NaN — `Math.max(1, NaN)` is NaN, which would empty every sample
  // batch and silently mass-escalate the run. `sampling` carries the temperature
  // (auto-bumped when N>1, AC-F1.3).
  // reliability-014: FARM_SAMPLES now routes through the shared numEnv reader
  // (generalizing this pre-existing NaN hardening to every other FARM/MUT
  // numeric knob) — a non-finite value falls back to 1 with a stderr warning
  // rather than poisoning the run with NaN (`Math.max(1, NaN)` is NaN, which
  // would empty every sample batch and silently mass-escalate the run).
  const samples = Math.max(1, Math.floor(numEnv("FARM_SAMPLES", 1, { min: 1 })));
  const sampling = effectiveSampling(samples);

  // #398: resources this task owned that could NOT be verified released —
  // sample worktrees/branches from best-of-N, and the task worktree on the
  // success path. Attached to whatever Result the task returns, so a leak is
  // never dropped on the floor between the teardown and `status: "green"`.
  const cleanupIssues: CleanupOutcome[] = [];
  const noteCleanup = (...outcomes: CleanupOutcome[]) => {
    for (const c of outcomes) if (!c.ok) cleanupIssues.push(c);
  };
  // Every return below routes through finish() so the cleanup record rides
  // along regardless of which exit the task takes.
  const finish = (r: Result): Result => (cleanupIssues.length ? { ...r, cleanup: [...cleanupIssues] } : r);

  const prepErr = await deps.prepareWorktree(branch, wt, ENV.integration);
  if (prepErr)
    return finish({ id: t.id, status: "escalate", attempts: 0, branch, worktree: wt, note: prepErr });

  const testHashBefore = await deps.fileHash(path.resolve(wt, t.test.path));

  let priorFailure: string | undefined;
  let driftedOnce = false;
  let lastFilesWritten: string[] = [];
  // F2: the failed attempt's in-scope output, captured before each reset and
  // shown read-only to the next attempt (empty on the first attempt).
  let priorInScope: Array<{ path: string; contents: string }> = [];
  // F1/AC-F1.6: the accepted candidate's own token spend (vs the summed total).
  let acceptedPromptTokens = 0;
  let acceptedCompletionTokens = 0;
  let promptTokens = 0;
  let completionTokens = 0;
  let lastWarning: string | undefined;
  let mutationScore: number | null = null;
  // #391: the setup cache for THIS worktree only — created here, dropped when
  // the task ends, so a fresh worktree can never inherit a stale "already
  // installed" verdict from another task.
  const setupState: SetupState = { key: null };

  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    if (attempt > 1) {
      // F2: snapshot the failed attempt's in-scope output BEFORE the reset wipes
      // it, so the next attempt refines against what it wrote rather than
      // restarting from the baseline blind. Out-of-scope drift is not captured.
      // Only meaningful for the single-sample path (which writes into `wt`); under
      // best-of-N `priorInScope` is seeded explicitly from the best failing sample
      // below, so the task worktree (never sample-written) must not clobber it.
      // And only re-show output the worker ACTUALLY wrote: if the prior attempt
      // failed at the API level (no files written), captureInScope would return the
      // inherited baseline, which must not be mislabeled "your previous attempt".
      if (samples <= 1) priorInScope = lastFilesWritten.length > 0 ? await captureInScope(wt, t) : [];
      await deps.resetWorktree(wt); // never accumulate stale files
    }

    // Setup (#92/#391): `setup` runs ONCE per worktree — the reset above is
    // `clean -fd`, which preserves the ignored dependency tree setup is
    // contractually required to produce — and re-runs only if its fingerprint
    // (commands + declared setupInputs) changed. `setupEachAttempt` runs every
    // attempt. Both go through the same gate machinery (shell + exit code,
    // redacted tail). A setup failure is environmental, not the worker's fault,
    // so it escalates immediately rather than burning a worker retry.
    const setupNote = await runSetupPhases(wt, t, deps, setupState);
    if (setupNote)
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: setupNote, promptTokens, completionTokens });

    // Enrichment (AC-03/AC-04): read the per-attempt worktree state — AFTER any
    // reset above — so the test source and existing in-scope file contents
    // reflect what the worker would actually see this attempt.
    const injected = await buildEnrichment(wt, t, priorInScope);

    const forbiddenExtra = driftedOnce ? lastFilesWritten.filter((f) => !allowed.has(f)) : undefined;
    const prompt = buildPrompt(t, injected, priorFailure, forbiddenExtra);

    let worker: WorkerResult;
    if (samples <= 1) {
      // Single-sample path — identical to today (one worker call into the task
      // worktree), now drawn through the shared limiter (a no-op at N=1).
      worker = await workerLimit.run(() =>
        deps.worker.apply({ cwd: wt, prompt, model: effectiveModel, apiBaseUrl, apiKey, forbidden, sampling }),
      );
      promptTokens += worker.promptTokens ?? 0;
      completionTokens += worker.completionTokens ?? 0;
      acceptedPromptTokens = worker.promptTokens ?? 0;
      acceptedCompletionTokens = worker.completionTokens ?? 0;
      lastFilesWritten = worker.filesWritten;
      if (!worker.ok) {
        priorFailure = redactSecrets(`worker error: ${worker.error}`);
        continue;
      }
    } else {
      // Best-of-N (AC-F1.2): draw `samples` candidates concurrently in isolated
      // scratch worktrees, gate each, accept the first green. The winner's files
      // are materialized into `wt`; the post-selection pipeline below then runs
      // against `wt` UNCHANGED. No green → seed the retry from the best failure
      // (its in-scope output, per F2) and loop (AC-F1.5). Token spend across ALL
      // samples is summed; the winner's own tokens are recorded separately (AC-F1.6).
      const sel = await bestOfN(t, prompt, effectiveModel, apiBaseUrl, apiKey, sampling, forbidden, allowed, samples, deps);
      noteCleanup(...sel.cleanup); // #398: sample worktrees/branches left behind
      promptTokens += sel.promptTokens;
      completionTokens += sel.completionTokens;
      acceptedPromptTokens = sel.winner?.promptTokens ?? 0;
      acceptedCompletionTokens = sel.winner?.completionTokens ?? 0;
      if (!sel.winner) {
        lastFilesWritten = sel.bestFailure?.filesWritten ?? [];
        priorInScope = sel.bestFailure?.inScope ?? [];
        priorFailure = sel.bestFailure?.note ?? "all samples failed the gate";
        continue;
      }
      try {
        await writeFilesInto(wt, sel.winner.files);
      } catch (error) {
        if (isUnsafeWorktreePathError(error)) {
          return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: error.message, filesWritten: [], promptTokens, completionTokens });
        }
        throw error;
      }
      worker = { ok: true, filesWritten: sel.winner.filesWritten };
      lastFilesWritten = worker.filesWritten;
    }

    // Post-apply containment sweep (D6) — task-level enforcement over the
    // worker's REPORTED writes (see postApplySweep header). Inspects the
    // `filesWritten` the worker returned, so an escape or a read-only-test write
    // is rejected even when the worker bypassed runWorker's inline guard —
    // provided the path was reported. A NON-REPORTING worker that writes outside
    // its reported set is NOT covered here ([NEEDS-TRIAGE], deferred to the
    // item-3 sandbox). Runs alongside the checkDrift allowlist sweep below; the
    // inline guards remain defense-in-depth.
    const sweepErr = postApplySweep(wt, worker.filesWritten, forbidden);
    if (sweepErr) {
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: sweepErr, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }

    // The failing test must be untouched (defence in depth — the write path
    // already refuses test.path, this catches a sneaky in-scope edit too).
    const testHashAfter = await deps.fileHash(path.resolve(wt, t.test.path));
    if (testHashBefore !== null && testHashAfter !== testHashBefore) {
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `tampered test: ${t.test.path}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }

    // Drift: on the FIRST drift, retry once with a hardened prompt naming the
    // offending paths — usually the cheap model is just being dumb, not the
    // spec being ambiguous. Only escalate as drift after that retry.
    const driftFiles = await deps.checkDrift(wt, allowed);
    if (driftFiles.length > 0) {
      if (!driftedOnce && attempt <= limit) {
        driftedOnce = true;
        priorFailure = `drift: you wrote outside the allowed files: ${driftFiles.join(", ")}`;
        continue;
      }
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `drift: ${driftFiles.join(", ")}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }

    const gate = await deps.runGate(wt, t.gate.commands);
    if (!gate.ok) {
      // FINDING 2: redact the WHOLE priorFailure that reaches the next worker
      // prompt — not just the gate.tail (already redacted in runGate). The
      // failing command line (gate.failed) is echoed verbatim too, so a secret
      // embedded in a gate command would otherwise cross the trust boundary.
      // redactSecrets is idempotent, so re-running it over the already-redacted
      // tail is safe.
      priorFailure = redactSecrets(`failed: ${gate.failed}\n${gate.tail}`);
      continue;
    }

    // Zero-token anti-gaming guard: fast literal-leak pass, then the deeper
    // mutation pass (skipped if the leak pass already says "high").
    const gaming = await deps.antiGamingCheck(wt, t);
    let risk = gaming.risk;
    let riskNote = gaming.note;
    if (risk !== "high") {
      let mut: Awaited<ReturnType<typeof mutationCheck>>;
      try {
        mut = await deps.mutationCheck(wt, t);
      } catch (error) {
        if (isUnsafeWorktreePathError(error)) {
          return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: error.message, filesWritten: [], promptTokens, completionTokens });
        }
        throw error;
      }
      if (mut && "score" in mut) {
        mutationScore = mut.score;
        // #525: the unknown-count sentinel is GONE, and this is a deliberate,
        // narrow behaviour change. This floor exists to refuse hard-rejecting a
        // task on thin evidence; an unreported mutant count is the thinnest
        // evidence there is, so it no longer clears the floor. Such a run warns
        // instead of escalating.
        //
        // The alternative — keeping `?? 99` here — was measured and is worse.
        // Before #525 the sentinel only applied to a NULLISH count, so a hook
        // that reported an unusable one ("total":"4" from a shell hook that
        // quotes its numbers, -5, 2.5, true) kept that value and failed the
        // comparison, landing on warn. Routing every unusable value through the
        // sentinel flipped twelve such shapes to escalate — false rejections in
        // exactly the direction this floor guards. Requiring a reported count
        // restores all twelve AND resolves the unreported case the same way.
        if (mut.score <= MUT.escalateBelow && mut.evaluated !== undefined && mut.evaluated >= 5) {
          risk = "high";
          riskNote = `gaming: mutation ${mutationSurvivalNote(mut)} — the test does not constrain the implementation`;
        } else if (mut.score < MUT.warnBelow) {
          if (risk !== "warn") {
            risk = "warn";
            riskNote = `mutation-risk: ${mutationSurvivalNote(mut)} — weak test or under-implemented logic`;
          }
        }
      } else if (mut && "failed" in mut) {
        // observability-002 (#187): mutationCheck's pluggable-hook branch
        // distinguishes "configured but failed" (non-zero exit, timeout,
        // unparseable output) from "not configured" (both previously
        // collapsed to `null`, so a broken FARM_MUTATION_CMD integration
        // produced a report indistinguishable from one that never ran mutation
        // checking). Surface it — mirroring the diagnostic discipline the
        // primary API path already uses (callApi's stderr body dump) — without
        // escalating or blocking the task on a hook-infrastructure failure.
        process.stderr.write(`[FARM] mutation hook failed for task ${t.id}: ${mut.detail}\n`);
        if (risk === "none") {
          risk = "warn";
          riskNote = `mutation-hook-failed: ${mut.detail}`;
        }
      }
    }
    if (risk === "high") {
      priorFailure = `${riskNote}. Implement real logic; do not hard-code or special-case the asserted value.`;
      if (attempt <= limit) continue; // give it a chance to fix
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: riskNote, filesWritten: worker.filesWritten, promptTokens, completionTokens, mutationScore });
    }
    if (risk === "warn") lastWarning = riskNote;

    // Commit + merge into the dedicated integration worktree.
    // B-1: stage only the files the worker actually wrote, not everything in the
    // worktree — git add -A would silently include any stale or injected files.
    await deps.git(["add", "--", ...worker.filesWritten], wt);
    const commit = await deps.git([...NOSIGN, "commit", "-m", `farm(${t.id}): ${t.description}`], wt);
    if (commit.code !== 0)
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `commit failed: ${commit.out.slice(0, 200)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });

    const diffstat = (await deps.git(["diff", "--stat", `${ENV.base}...${branch}`], wt)).out.trim();

    // Merge into the integration branch is INSIDE the attempt loop (AC-07/D4):
    // a conflict is treated like a gate failure and re-enters regeneration,
    // consuming ONE of the existing `maxRetries` attempts rather than escalating
    // instantly. The merge stays serialized under withMergeLock so the
    // integration worktree is never touched concurrently (T-06 prevents most
    // overlaps; this is the residual defense-in-depth case).
    const merged = await deps.withMergeLock(async () => {
      const m = await deps.git([...NOSIGN, "merge", "--no-ff", "-m", `merge ${t.id}`, branch], integrationWorktree);
      if (m.code !== 0) {
        await deps.git(["merge", "--abort"], integrationWorktree).catch(() => {});
        return m.out;
      }
      return null;
    });
    if (merged !== null) {
      // Regenerate-on-conflict (AC-07): with retries left, rebuild against the
      // UPDATED baseline instead of escalating. Reset the task worktree+branch
      // onto the new integration HEAD (so the next attempt cuts from what the
      // merge target now contains), then re-run the worker with a redacted,
      // concise merge-conflict note seeded into priorFailure. resetWorktree at
      // the loop top is then a no-op reset to this same HEAD. Per D4 this is NOT
      // a new unbounded loop — it spends one of the existing attempts.
      if (attempt <= limit) {
        await deps.git(["reset", "--hard", ENV.integration], wt).catch(() => {});
        await deps.git(["clean", "-fd"], wt).catch(() => {});
        priorFailure = redactSecrets(`merge conflict vs integration: rebuild against the updated baseline (integration HEAD moved)\n${String(merged).slice(0, 160)}`);
        continue;
      }
      // retries exhausted — escalate exactly as before (worktree left for inspection)
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `merge failed vs integration: ${String(merged).slice(0, 160)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }

    // success — drop the worktree (branch stays, merged into integration).
    // #398: verified. This teardown used to be a bare `.catch(() => {})` one
    // line above `status: "green"`, so a locked or otherwise unremovable
    // worktree produced an unqualified green result and a silent leak. Now the
    // outcome travels on the Result (and from there into the receipt, the
    // summary, and the exit code) — green still means the work merged, but it
    // can no longer also mean "and we quietly abandoned a worktree".
    noteCleanup(await removeWorktreeVerified(deps.git, wt));
    return finish({ id: t.id, status: "green", attempts: attempt, branch, worktree: wt, warning: lastWarning, filesWritten: worker.filesWritten, diffstat, promptTokens, completionTokens, mutationScore, samples, acceptedPromptTokens, acceptedCompletionTokens });
  }

  // worktree intentionally left in place for inspection
  return finish({ id: t.id, status: "escalate", attempts: limit + 1, branch, worktree: wt, note: priorFailure?.split("\n")[0], filesWritten: lastFilesWritten, promptTokens, completionTokens, mutationScore });
}

// --------------------------------------------------------------------------
// validation — duplicate ids, unknown deps, AND cycles
// --------------------------------------------------------------------------
// Intentional divergence from plan.schema.json's task `id` pattern
// (`^[a-z0-9][a-z0-9-]*$`, strict kebab-case). The two are NOT meant to match:
//   - The schema `id` pattern is the AUTHORING contract — what writing-plans is
//     allowed to emit. It is deliberately narrow (kebab-case) for readable
//     branch names.
//   - SAFE_TASK_ID is the RUNTIME path-traversal defense. The id becomes a
//     branch name (`farm/<id>`) and a worktree directory, so this check must
//     hold regardless of HOW a plan was produced — including a hand-edited or
//     non-schema-validated plan that never went through the authoring gate.
//     It is therefore broader (`[A-Za-z0-9._-]`, capped at 64) but still admits
//     only characters that cannot escape a path or branch ref.
// Neither side is widened to match the other: tightening SAFE_TASK_ID to
// kebab-case would weaken the runtime defense's independence from the authoring
// layer, and widening the schema would loosen the authoring contract. A cleaner
// reconciliation (a single shared, runtime-strict pattern enforced by validate()
// AND advertised by the schema) is possible but is a behavior change to id
// acceptance and out of scope for AC-02 — noted, not made. [NEEDS-TRIAGE]
export const SAFE_TASK_ID = /^[A-Za-z0-9._-]{1,64}$/;

// Single source of truth for the outbound base-URL scheme rule: require HTTPS,
// with an http:// exception ONLY for the loopback hosts test mocks bind to
// (127.0.0.1 / localhost). Parsed with new URL() rather than a regex so the
// host is the *resolved* host: userinfo tricks like
// `http://localhost@evil.example` (whose real host is evil.example) cannot be
// mistaken for loopback. Userinfo is rejected on every scheme: fetch refuses
// credential-bearing URLs, and echoing one through an error could disclose it.
// A malformed/unparseable URL is treated as insecure and rejected without
// reflecting attacker-controlled configuration into logs.
// This guards the Authorization: Bearer <FARM_API_KEY> header against
// cleartext transport. Rejection messages are fixed text and never echo the
// offending URL or key.
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost"]);

export function assertSecureBaseUrl(url: string) {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("apiBaseUrl must use HTTPS (HTTP is allowed only for bare loopback hosts)");
  }
  if (parsed.username !== "" || parsed.password !== "") {
    throw new Error("apiBaseUrl must use HTTPS without embedded credentials");
  }
  // HTTPS keeps the Bearer secret inside TLS regardless of host.
  if (parsed.protocol === "https:") return;
  // HTTP is permitted only for a bare loopback host.
  if (parsed.protocol === "http:" && LOOPBACK_HOSTS.has(parsed.hostname)) return;
  throw new Error("apiBaseUrl must use HTTPS (HTTP is allowed only for bare loopback hosts)");
}

// --------------------------------------------------------------------------
// runtime plan contract (#412) — the EXECUTED schema
// --------------------------------------------------------------------------
// `main()` reads plan.json off disk, so the plan is untrusted input: it may be
// hand-edited, half-written, or emitted by a drifted generator. It used to be
// cast (`JSON.parse(...) as Plan`) and handed straight to validate(), which
// dereferences `plan.meta` and iterates `plan.tasks` — so `null` and `{}` came
// out as raw TypeErrors, and a numeric `id`/`description` sailed past checks
// that assume strings.
//
// AUTHORITY. PLAN_SHAPE below (enforced by parsePlan) is the AUTHORITATIVE,
// executed contract: nothing reaches validate(), resolveConfig(), a worktree, a
// branch, a report, or the network until a plan satisfies it exactly.
// `plan.schema.json` is the AUTHORING contract — what writing-plans validates
// its output against before handing off — and is never consulted at runtime.
// The two are kept key-for-key and type-for-type identical by the parity test in
// plan-contract.test.ts; adding a field to one side without the other fails CI.
// One divergence is deliberate and ratified there: the schema's kebab-case `id`
// pattern is an authoring rule, while the runtime path-traversal rule is
// SAFE_TASK_ID in validate() (see the note above it).
//
// Messages are bounded and field-specific: they name the JSON path (by task
// INDEX — the id is not yet trustworthy) and the offending value's TYPE, and
// never echo plan content back, which could be long or secret-bearing.
export type PlanFieldType = "string" | "integer" | "string[]" | "task[]" | "meta" | "test" | "gate";
type PlanObjectSpec = { required: readonly string[]; props: Readonly<Record<string, PlanFieldType>> };

export const PLAN_SHAPE = {
  plan: {
    required: ["meta", "tasks"],
    props: { meta: "meta", tasks: "task[]" },
  },
  meta: {
    required: ["name"],
    props: {
      name: "string",
      repo: "string",
      model: "string",
      apiBaseUrl: "string",
      setup: "string[]",
      setupEachAttempt: "string[]",
      setupInputs: "string[]",
    },
  },
  task: {
    required: ["id", "description", "filesInScope", "test", "gate"],
    props: {
      id: "string",
      description: "string",
      deps: "string[]",
      filesInScope: "string[]",
      test: "test",
      gate: "gate",
      context: "string",
      model: "string",
      maxRetries: "integer",
      setup: "string[]",
      setupEachAttempt: "string[]",
      setupInputs: "string[]",
    },
  },
  test: { required: ["path"], props: { path: "string" } },
  gate: { required: ["commands"], props: { commands: "string[]" } },
} as const satisfies Record<string, PlanObjectSpec>;

type PlanSpecName = keyof typeof PLAN_SHAPE;

// Arrays the schema declares `minItems: 1`, keyed "<spec>.<prop>".
const PLAN_NON_EMPTY: ReadonlySet<string> = new Set(["plan.tasks", "task.filesInScope", "gate.commands"]);
// Integer fields and their schema `minimum`.
const PLAN_INT_MIN: Readonly<Record<string, number>> = { "task.maxRetries": 0 };

const PLAN_LABEL_MAX = 40;
const clipLabel = (s: string) => (s.length <= PLAN_LABEL_MAX ? s : `${s.slice(0, PLAN_LABEL_MAX)}…`);
const jsonTypeName = (v: unknown) => (v === null ? "null" : Array.isArray(v) ? "array" : typeof v);
const isJsonObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function checkPlanField(v: unknown, type: PlanFieldType, at: string, key: string): void {
  switch (type) {
    case "string":
      if (typeof v !== "string") throw new Error(`${at} must be a string (got ${jsonTypeName(v)})`);
      return;
    case "integer": {
      const min = PLAN_INT_MIN[key] ?? 0;
      if (typeof v !== "number" || !Number.isInteger(v))
        throw new Error(`${at} must be an integer >= ${min} (got ${jsonTypeName(v)})`);
      if (v < min) throw new Error(`${at} must be an integer >= ${min}`);
      return;
    }
    case "string[]": {
      if (!Array.isArray(v)) throw new Error(`${at} must be an array of strings (got ${jsonTypeName(v)})`);
      if (PLAN_NON_EMPTY.has(key) && v.length === 0)
        throw new Error(`${at} must list at least one entry`);
      for (const [i, entry] of v.entries())
        if (typeof entry !== "string")
          throw new Error(`${at}[${i}] must be a string (got ${jsonTypeName(entry)})`);
      return;
    }
    case "task[]": {
      if (!Array.isArray(v)) throw new Error(`${at} must be an array of task objects (got ${jsonTypeName(v)})`);
      if (PLAN_NON_EMPTY.has(key) && v.length === 0)
        throw new Error(`${at} must list at least one task`);
      for (const [i, entry] of v.entries()) checkPlanObject(entry, "task", `${at}[${i}]`);
      return;
    }
    default:
      // nested closed object — "meta" | "test" | "gate"
      checkPlanObject(v, type, at);
  }
}

function checkPlanObject(value: unknown, spec: PlanSpecName, at: string): void {
  if (!isJsonObject(value)) throw new Error(`${at} must be a JSON object (got ${jsonTypeName(value)})`);
  const { required, props } = PLAN_SHAPE[spec];
  const declared = props as Readonly<Record<string, PlanFieldType>>;
  // Closed object: an unknown property is a contract breach, not a courtesy —
  // it is how a drifted generator or a typo'd hand edit silently loses a field.
  for (const key of Object.keys(value))
    if (!Object.hasOwn(declared, key)) throw new Error(`${at}: unknown property "${clipLabel(key)}"`);
  for (const key of required)
    if (value[key] === undefined) throw new Error(`${at}.${key} is required`);
  for (const [key, type] of Object.entries(declared)) {
    const v = value[key];
    if (v === undefined) continue;
    checkPlanField(v, type, `${at}.${key}`, `${spec}.${key}`);
  }
}

/**
 * The runtime boundary (#412). Validates parsed-but-untrusted JSON against
 * PLAN_SHAPE and returns it typed. Throws a bounded, field-specific Error on the
 * FIRST violation. Call this before touching any field of a plan.
 */
export function parsePlan(raw: unknown): Plan {
  checkPlanObject(raw, "plan", "plan");
  return raw as Plan;
}

export function validate(plan: Plan) {
  // meta-level schema checks — require HTTPS except for loopback (test mocks)
  if (plan.meta.apiBaseUrl) assertSecureBaseUrl(plan.meta.apiBaseUrl);

  // #92: setup commands (meta-level and per-task) are validated like
  // gate.commands — non-empty strings, capped length.
  const checkSetup = (label: string, cmds: string[]) => {
    for (const cmd of cmds) {
      if (!cmd || typeof cmd !== "string")
        throw new Error(`${label}: setup entries must be non-empty strings`);
      if (cmd.length > 1024) throw new Error(`${label}: setup command exceeds 1024 chars`);
    }
  };
  // #391: `setupInputs` are relative paths resolved against the worktree and
  // read (hashed) by the setup fingerprint, so they get the same relative-path
  // rule as test.path / filesInScope.
  const checkSetupInputs = (label: string, inputs: string[]) => {
    for (const rel of inputs) {
      if (!rel || typeof rel !== "string")
        throw new Error(`${label}: setupInputs entries must be non-empty strings`);
      if (rel.includes("..") || path.isAbsolute(rel))
        throw new Error(`${label}: setupInputs entry "${rel}" must be a relative path with no ".." segments`);
    }
  };
  if (plan.meta.setup) checkSetup("plan.meta.setup", plan.meta.setup);
  if (plan.meta.setupEachAttempt) checkSetup("plan.meta.setupEachAttempt", plan.meta.setupEachAttempt);
  if (plan.meta.setupInputs) checkSetupInputs("plan.meta", plan.meta.setupInputs);

  const ids = new Set<string>();
  for (const t of plan.tasks) {
    // B-2: restrict id to safe characters to prevent path traversal in branch
    // names and worktree paths derived from it
    if (!SAFE_TASK_ID.test(t.id))
      throw new Error(`task id "${t.id}" must match [A-Za-z0-9._-], max 64 chars`);
    // #163: SAFE_TASK_ID admits "." and ".." (both are all-dot strings), which
    // as a worktree path segment resolve to the root itself or its parent —
    // `path.resolve(worktreeRoot, "..")` escapes the root, and "." names the
    // root, both feeding a recursive delete. Reject them explicitly at the
    // authoring boundary (assertContainedWorktree is the runtime backstop).
    if (t.id === "." || t.id === "..")
      throw new Error(`task id "${t.id}" is reserved (resolves to the worktree root or its parent)`);
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);

    // migration-004 (T-07b): guard the REQUIRED structured fields before
    // dereferencing them. These are `required` in plan.schema.json, but
    // validate() runs against a `JSON.parse(...) as Plan` assertion (no runtime
    // schema check), so a hand-crafted or partially-written plan.json with
    // `test:null`, `gate:null`, or `filesInScope:null` would otherwise throw an
    // opaque `TypeError: Cannot read properties of null` instead of a named
    // error identifying the task and the field. Fail-closed either way; this
    // just makes the failure diagnosable.
    if (!t.test || typeof t.test.path !== "string")
      throw new Error(`task ${t.id}: test.path is required (string)`);
    if (!Array.isArray(t.filesInScope))
      throw new Error(`task ${t.id}: filesInScope is required (array of relative paths)`);
    if (!t.gate || !Array.isArray(t.gate.commands))
      throw new Error(`task ${t.id}: gate.commands is required (array of strings)`);

    // D-2: reject relative-path traversal in test.path and filesInScope
    if (t.test.path.includes("..") || path.isAbsolute(t.test.path))
      throw new Error(`task ${t.id}: test.path must be a relative path with no ".." segments`);
    for (const f of t.filesInScope)
      if (f.includes("..") || path.isAbsolute(f))
        throw new Error(`task ${t.id}: filesInScope entry "${f}" must be a relative path with no ".." segments`);
    for (const cmd of t.gate.commands) {
      if (!cmd || typeof cmd !== "string")
        throw new Error(`task ${t.id}: gate.commands entries must be non-empty strings`);
      if (cmd.length > 1024)
        throw new Error(`task ${t.id}: gate command exceeds 1024 chars`);
    }
    if (t.setup) checkSetup(`task ${t.id} setup`, t.setup);
    if (t.setupEachAttempt) checkSetup(`task ${t.id} setupEachAttempt`, t.setupEachAttempt);
    if (t.setupInputs) checkSetupInputs(`task ${t.id}`, t.setupInputs);
  }
  for (const t of plan.tasks)
    for (const d of t.deps ?? [])
      if (!ids.has(d)) throw new Error(`task ${t.id} depends on unknown task ${d}`);

  // cycle detection (DFS)
  const byId = new Map(plan.tasks.map((t) => [t.id, t]));
  const state = new Map<string, 0 | 1 | 2>(); // 0=unseen 1=onstack 2=done
  const visit = (id: string, stack: string[]) => {
    if (state.get(id) === 2) return;
    if (state.get(id) === 1)
      throw new Error(`dependency cycle: ${[...stack, id].join(" -> ")}`);
    state.set(id, 1);
    for (const d of byId.get(id)!.deps ?? []) visit(d, [...stack, id]);
    state.set(id, 2);
  };
  for (const t of plan.tasks) visit(t.id, []);
}

function resolveConfig(plan: Plan): { model: string; apiBaseUrl: string; apiKey: string } {
  const model = ENV.model ?? plan.meta.model;
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl ?? ENV.defaultApiBaseUrl;
  const apiKey = ENV.apiKey;
  // Re-validate the EFFECTIVE base URL after the env→plan→default precedence:
  // validate() only sees plan.meta, so FARM_API_BASE_URL=http://evil would
  // otherwise reach fetch() and leak the Bearer key over cleartext.
  assertSecureBaseUrl(apiBaseUrl);
  if (!model) {
    console.error(
      "Error: No model configured.\n" +
        "Set FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\n" +
        "See ${CLAUDE_PLUGIN_ROOT}/includes/farm.md for setup instructions.",
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.\nSee ${CLAUDE_PLUGIN_ROOT}/includes/farm.md for setup instructions.");
    process.exit(1);
  }
  return { model, apiBaseUrl, apiKey };
}

// --------------------------------------------------------------------------
// entitlement pre-screen (#93). OpenCode Zen's /models catalog lists models the
// API key is NOT entitled to (expired `*-free` promos); /chat/completions then
// returns 401 "Free promotion has ended for ...". The canary cannot tell that
// from a capability failure and burns full attempts/timeouts on dead candidates.
// This cheap screen runs one minimal probe per candidate and drops the 401s
// BEFORE the real canary, surfacing them distinctly (never conflated with a
// capability FAIL). Pure + injectable (probe, sleepFn) so it is unit-testable
// without the network; the per-candidate wall-clock cap is enforced here via a
// race, so a hung/dead endpoint cannot dominate the screen.
// --------------------------------------------------------------------------
export type EntitlementSkip = { model: string; reason: "entitlement" | "timeout" | "error"; note: string };
export type EntitlementScreen = { survivors: string[]; skipped: EntitlementSkip[] };
export type EntitlementProbe = (model: string) => Promise<{ status: number }>;

export async function screenEntitlements(
  models: string[],
  probe: EntitlementProbe,
  opts: { timeoutMs?: number; sleepFn?: (ms: number) => Promise<void> } = {},
): Promise<EntitlementScreen> {
  const timeoutMs = opts.timeoutMs ?? ENV.entitlementProbeTimeoutMs;
  const sleepFn = opts.sleepFn ?? sleep;
  const survivors: string[] = [];
  const skipped: EntitlementSkip[] = [];
  for (const model of models) {
    // null is the timeout sentinel — the probe itself never resolves to null,
    // so `res === null` cleanly means the wall-clock race fired.
    let res: { status: number } | null;
    try {
      res = await Promise.race<{ status: number } | null>([
        probe(model),
        sleepFn(timeoutMs).then(() => null),
      ]);
    } catch (e) {
      skipped.push({ model, reason: "error", note: `entitlement probe error: ${e}` });
      continue;
    }
    if (res === null) {
      skipped.push({ model, reason: "timeout", note: `entitlement probe exceeded ${timeoutMs}ms — model is slow or dead` });
      continue;
    }
    if (res.status === 401) {
      skipped.push({ model, reason: "entitlement", note: "401 — not entitled / free promotion ended" });
      continue;
    }
    // Any other status (200, 4xx≠401, 5xx) → let the real canary judge capability.
    survivors.push(model);
  }
  return { survivors, skipped };
}

// Real entitlement probe: one minimal /chat/completions call (max_tokens: 1),
// returning only the HTTP status. Its own AbortController bounds the underlying
// fetch so a hung socket is actually torn down (the screen's race is the
// higher-level cap). A network/abort failure maps to status 0 → screened as a
// survivor, not an entitlement drop (only a real 401 drops a candidate).
// coverage-003 (#183): exported so the request-shape (Bearer header, POST body)
// and the AbortController timeout behavior are directly unit-testable against a
// mocked global fetch, rather than only through the pure screenEntitlements
// decision logic (which is already tested with an injected fake probe).
export function makeEntitlementProbe(apiBaseUrl: string, apiKey: string, timeoutMs: number): EntitlementProbe {
  // This function is exported and may be called without runCanary's earlier
  // config resolution, so enforce the transport boundary at construction.
  assertSecureBaseUrl(apiBaseUrl);
  return async (model) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetch(`${apiBaseUrl}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({ model, messages: [{ role: "user", content: "ping" }], max_tokens: 1 }),
        signal: ctrl.signal,
        redirect: "error",
      });
      return { status: resp.status };
    } catch {
      return { status: 0 };
    } finally {
      clearTimeout(timer);
    }
  };
}

// --------------------------------------------------------------------------
// canary — measure candidate models on the smallest task. No merge.
// --------------------------------------------------------------------------
async function runCanary(plan: Plan) {
  if (ENV.candidateModels.length === 0) {
    console.error("Error: --canary requires FARM_CANDIDATE_MODELS (comma-separated model ids).");
    process.exit(1);
  }
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl ?? ENV.defaultApiBaseUrl;
  const apiKey = ENV.apiKey;
  // Same effective-URL guard as resolveConfig — canary also reaches fetch().
  assertSecureBaseUrl(apiBaseUrl);
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.");
    process.exit(1);
  }
  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });
  // Reset integration to base so canary worktrees branch from a clean point.
  await git(["branch", "-f", ENV.integration, ENV.base]);
  integrationWorktree = path.resolve(ENV.reportDir, "integration-wt");
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});
  await rm(integrationWorktree, { recursive: true, force: true }).catch(() => {});
  await git(["worktree", "add", integrationWorktree, ENV.integration]).catch(() => {});

  // smallest task = fewest filesInScope, no deps
  const task = [...plan.tasks]
    .filter((t) => (t.deps ?? []).length === 0)
    .sort((a, b) => a.filesInScope.length - b.filesInScope.length)[0] ?? plan.tasks[0];

  // #93: entitlement pre-screen. Drop candidates the key isn't entitled to (401
  // "free promotion ended") BEFORE the expensive per-candidate canary, so a dead
  // promo model can't burn full attempts/timeouts. Bounded per candidate.
  const { survivors, skipped } = await screenEntitlements(
    ENV.candidateModels,
    makeEntitlementProbe(apiBaseUrl, apiKey, ENV.entitlementProbeTimeoutMs),
  );
  if (skipped.length)
    process.stderr.write(`Entitlement screen dropped ${skipped.length}/${ENV.candidateModels.length}: ${skipped.map((s) => `${s.model} (${s.reason})`).join(", ")}\n`);

  const results: Array<{ model: string; green: boolean; attempts: number; ms: number; note?: string }> = [];
  for (const model of survivors) {
    const t0 = Date.now();
    const r = await runTask({ ...task, id: `canary-${task.id}` }, model, apiBaseUrl, apiKey);
    results.push({ model, green: r.status === "green", attempts: r.attempts, ms: Date.now() - t0, note: r.note });
    await git(["worktree", "remove", "--force", path.resolve(ENV.worktreeRoot, `canary-${task.id}`)]).catch(() => {});
    await git(["branch", "-D", `farm/canary-${task.id}`]).catch(() => {});
  }
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});

  results.sort((a, b) => Number(b.green) - Number(a.green) || a.attempts - b.attempts || a.ms - b.ms);
  // Skipped candidates are surfaced DISTINCTLY (their own array), never folded
  // into the capability `results` as a FAIL.
  await writeFile(path.join(ENV.reportDir, "canary-report.json"), JSON.stringify({ task: task.id, results, skipped, ts: new Date().toISOString() }, null, 2));
  const summary = [
    "\nCanary results (best first):",
    ...results.map((r) => `  ${r.green ? "PASS" : "FAIL"}  ${r.model}  attempts=${r.attempts} ${r.ms}ms${r.note ? `  (${r.note})` : ""}`),
    ...skipped.map((s) => `  SKIP  ${s.model}  (${s.reason}: ${s.note})`),
    `\nRecommended: ${results[0]?.green ? results[0].model : "NONE PASSED — set FARM_MODEL manually or revise the plan"}`,
    "",
  ].join("\n");
  await new Promise<void>((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(results[0]?.green ? 0 : 2);
}

// --------------------------------------------------------------------------
// main — DAG scheduler with a concurrency cap and a circuit breaker
// --------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const canary = args.includes("--canary");
  const planPath = args.find((a) => !a.startsWith("--")) ?? "plan.json";
  // #412: plan.json is untrusted input. parsePlan enforces the runtime contract
  // (PLAN_SHAPE) on the parsed JSON BEFORE any field is dereferenced, and
  // everything below — validate, resolveConfig, worktrees, branches, reports,
  // the network — is downstream of it. A malformed plan exits here, with a
  // bounded field-specific message instead of a raw TypeError and a stack, and
  // with no side effect of any kind performed.
  let plan: Plan;
  try {
    plan = parsePlan(JSON.parse(await readFile(planPath, "utf8")));
    validate(plan);
  } catch (e) {
    console.error(`Error: invalid plan ${planPath}: ${msgOf(e).slice(0, 300)}`);
    return process.exit(1);
  }

  // #92: propagate the repo-wide meta setup fields to every task that did not
  // declare its own (the task value wins; meta fills the gap). Done once at
  // dispatch, before main and canary, so runTask only ever reads the effective
  // task-level values.
  for (const t of plan.tasks) {
    if (plan.meta.setup && t.setup === undefined) t.setup = plan.meta.setup;
    if (plan.meta.setupEachAttempt && t.setupEachAttempt === undefined)
      t.setupEachAttempt = plan.meta.setupEachAttempt;
    if (plan.meta.setupInputs && t.setupInputs === undefined) t.setupInputs = plan.meta.setupInputs;
  }

  if (canary) return runCanary(plan);

  const { model, apiBaseUrl, apiKey } = resolveConfig(plan);

  // observability-003 (T-07c): one run-id for this whole invocation, threaded
  // into every farm-results.jsonl line and the farm-report.json header.
  // #397: the run-id is now also an OWNERSHIP BOUNDARY — every artifact this
  // run publishes lives under `${reportDir}/runs/<runId>/`, which is what makes
  // two farm processes on one repository non-destructive to each other.
  let runId: string;
  try {
    runId = ENV.runId === null ? mintRunId() : assertSafeRunId(ENV.runId);
  } catch (e) {
    console.error(`Error: ${msgOf(e)}`);
    return process.exit(1);
  }
  const runDir = runArtifactDir(runId);

  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });
  await mkdir(runDir, { recursive: true });

  const health = newRunArtifactHealth();

  // Streaming rail (AC-08 / D7): the incremental, append-only record of settled
  // tasks, consumed in completion order. The authoritative final summary remains
  // farm-report.json (written in the finally, even on abort); on abort the
  // consumer reconciles against it.
  //
  // #397: the rail this run appends to is run-scoped and therefore exclusively
  // owned — no other farm process truncates it or interleaves its lines. The
  // documented `${reportDir}/farm-results.jsonl` path is kept as the "latest"
  // convenience pointer and is REPUBLISHED ATOMICALLY (full content, temp +
  // rename) after every settlement, so a consumer of that path always reads a
  // complete, parseable file. It is initialized empty at run start, preserving
  // the "safe to run twice" invariant (a re-run never shows stale lines).
  const resultsStream = path.join(runDir, "farm-results.jsonl");
  const latestStream = path.join(ENV.reportDir, "farm-results.jsonl");
  const streamLines: string[] = [];
  const noteStreamFailure = (what: string, e: unknown) => {
    const m = `${what}: ${msgOf(e)}`;
    console.error(`results stream ${m}`);
    noteArtifactError(health.stream.errors, m);
  };
  await writeFile(resultsStream, "").catch((e) => noteStreamFailure("run-scoped init failed", e));
  await atomicWriteFile(latestStream, "").catch((e) => noteStreamFailure("latest pointer init failed", e));

  const done = new Map<string, Result>();
  const blocked: { id: string; reason: string }[] = [];
  let aborted = false;
  // #387: publication of the authoritative receipt is part of the run's
  // outcome, not a console breadcrumb. Captured here, consumed by the exit-code
  // derivation below.
  let publishError: unknown = null;

  try {
    const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
    if (branchResult.code !== 0)
      throw new Error(`could not create integration branch '${ENV.integration}' from '${ENV.base}': ${branchResult.out}`);

    // #397: the integration worktree is per-run scratch that lived at a shared,
    // run-agnostic path — a second farm process force-removed it out from under
    // the first mid-merge. Scope it to the run directory alongside the run's
    // receipts.
    integrationWorktree = path.resolve(runDir, "integration-wt");
    await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});
    await rm(integrationWorktree, { recursive: true, force: true }).catch(() => {});
    const wtResult = await git(["worktree", "add", integrationWorktree, ENV.integration]);
    if (wtResult.code !== 0)
      throw new Error(`could not create integration worktree: ${wtResult.out}`);

    const byId = new Map(plan.tasks.map((t) => [t.id, t]));
    const escalated = new Set<string>();
    const pending = new Set(plan.tasks.map((t) => t.id));
    const running = new Map<string, Promise<{ id: string; r: Result }>>();

    // AC-06: scope-aware readiness. Two tasks whose filesInScope intersect
    // collide at merge time if dispatched concurrently, and a later-cut worktree
    // would miss the earlier task's merge. This is enforced as a DERIVED
    // readiness filter — never written as a `deps` edge — so it cannot create a
    // plan-validation cycle (Risks: "Scheduling deadlock/starvation").
    const scopeOf = (id: string) => new Set(byId.get(id)!.filesInScope ?? []);
    const overlaps = (a: Set<string>, b: Iterable<string>) => {
      for (const f of b) if (a.has(f)) return true;
      return false;
    };

    const ready = () =>
      [...pending].filter((id) => {
        const deps = byId.get(id)!.deps ?? [];
        if (deps.some((d) => escalated.has(d))) return false;
        if (!deps.every((d) => done.get(d)?.status === "green")) return false;

        // A candidate is ready iff its written deps are green (above) AND no
        // overlapping sibling is still in flight or ordered ahead of it:
        //   - no currently-RUNNING task with intersecting filesInScope, AND
        //   - no still-PENDING task with intersecting filesInScope and a lower
        //     (lexicographic) id.
        // Effect: among an overlapping group, members run sequentially in id
        // order, each cutting its worktree from the integration HEAD that already
        // contains the prior member's merge. A SETTLED sibling (green-merged or
        // escalated) is neither running nor pending, so it no longer blocks —
        // hence no deadlock and no starvation.
        const myScope = scopeOf(id);
        if (myScope.size === 0) return true;
        for (const rid of running.keys()) {
          if (overlaps(myScope, scopeOf(rid))) return false;
        }
        for (const pid of pending) {
          if (pid === id) continue;
          if (pid < id && overlaps(myScope, scopeOf(pid))) return false;
        }
        return true;
      });

    const tripped = () => {
      const settled = done.size;
      if (settled < ENV.abortMinTasks) return false;
      return escalated.size / settled > ENV.abortEscalationRate;
    };

    while (pending.size > 0 || running.size > 0) {
      // reliability-013: once tripped, stop DISPATCHING new tasks, but do NOT
      // break out of the loop while `running` still holds in-flight promises —
      // the old `break` here left those ids in neither `done` nor `pending`
      // (they vanish from farm-report.json entirely) and let the `finally`
      // remove the integration worktree while an in-flight task could still be
      // inside its withMergeLock merge into that same worktree. Falling through
      // to the existing drain-and-record logic below instead means every
      // dispatched task is awaited to a real, recorded status before the loop
      // exits, so the integration worktree is only torn down once no merge can
      // still be in flight.
      if (!aborted && tripped()) aborted = true;
      if (!aborted) {
        for (const id of ready()) {
          if (running.size >= ENV.concurrency) break;
          pending.delete(id);
          running.set(
            id,
            runTask(byId.get(id)!, model, apiBaseUrl, apiKey).then(
              (r) => ({ id, r }),
              // observability-003 (T-07c): a crash produces an escalate Result with
              // a correlated, stack-bearing note. The truncated err.stack gives the
              // post-mortem a call site (e.g. the spawn TypeError from
              // reliability-004) instead of a one-line message with no origin.
              (e) => ({
                id,
                r: {
                  id,
                  status: "escalate" as const,
                  attempts: 0,
                  branch: `farm/${id}`,
                  worktree: path.resolve(ENV.worktreeRoot, id),
                  note: `crashed: ${e?.message ?? e}${e?.stack ? `\n${String(e.stack).slice(0, 1500)}` : ""}`,
                },
              }),
            ),
          );
        }
      }
      if (running.size === 0) break;
      const { id, r } = await Promise.race(running.values());
      running.delete(id);
      // observability-003 (T-07c): stamp the run-id onto every settled result —
      // crash or clean — so the JSONL line and the report header share it.
      r.runId = runId;
      // reliability-013: a task that was still in flight when the breaker
      // tripped settles here with its REAL outcome (the drain above waits for
      // its actual completion, including any merge) — annotate an escalate
      // note so the report distinguishes "aborted while in flight" from an
      // ordinary escalation, without discarding a genuine result.
      if (aborted && r.status === "escalate" && !/run aborted/.test(r.note ?? "")) {
        r.note = r.note ? `${r.note} (run aborted by circuit breaker while in flight)` : "escalate: run aborted (in flight)";
      }
      done.set(id, r);
      // Streaming rail (AC-08 / D7): append this settled task as one JSONL line
      // the moment it settles, so a pipelined consumer can act in completion
      // order. Resilient by design — a stream failure never crashes the run (the
      // report stays authoritative) — but #387: it is no longer MUTE either. Each
      // failure is recorded and republished in farm-report.json, so a consumer
      // can tell "the rail is short because the run is short" from "the rail is
      // short because writes failed".
      const line = JSON.stringify(r) + "\n";
      streamLines.push(line);
      await appendFile(resultsStream, line).catch((e) => noteStreamFailure("run-scoped append failed", e));
      await atomicWriteFile(latestStream, streamLines.join("")).catch((e) =>
        noteStreamFailure("latest pointer publish failed", e),
      );
      if (r.status === "escalate") escalated.add(id);
    }

    // anything still pending is blocked (dependency escalated, cycle-free by validate, or aborted)
    for (const id of pending) {
      const deps = byId.get(id)!.deps ?? [];
      const culprit = deps.find((d) => escalated.has(d));
      blocked.push({ id, reason: aborted ? "run aborted (circuit breaker)" : culprit ? `dependency ${culprit} escalated` : "not scheduled" });
    }
  } finally {
    // reliability-004 (T-07a): only remove the integration worktree if it was
    // actually assigned. An early throw (e.g. the integration branch could not
    // be created) leaves `integrationWorktree` undefined; passing undefined as an
    // argv element into spawn throws a synchronous TypeError out of this finally,
    // masking the real, actionable error. Guard it so the original error
    // surfaces.
    //
    // #398: this now runs BEFORE writeReport, not after. The teardown outcome
    // has to be IN the receipt — a leak an operator only learns about from a
    // console line they scrolled past is exactly the silent-green failure this
    // fixes — and the report payload is serialized inside writeReport, so any
    // teardown performed afterwards could never appear in it. Nothing in
    // writeReport reads the integration worktree (its `git diff` runs against
    // the main checkout), so the reordering is safe.
    if (integrationWorktree) {
      try {
        const c = await removeWorktreeVerified(git, integrationWorktree);
        if (!c.ok) health.cleanup.failures.push({ target: c.target, detail: c.detail ?? "unverified" });
      } catch (e) {
        // Belt and braces: nothing in removeWorktreeVerified is expected to
        // throw (git() resolves rather than rejects, stat is guarded), but a
        // throw HERE would propagate out of the finally and mask an in-flight
        // exception — the exact failure mode reliability-004 fixed above.
        health.cleanup.failures.push({ target: integrationWorktree, detail: `teardown threw: ${msgOf(e)}` });
      }
    }
    // #387: the report is still written from the `finally` (so an abort or a
    // mid-run throw still produces a receipt), but its failure is no longer
    // absorbed by a console.error. It is captured and turned into a distinct
    // non-zero exit below. The catch is kept here only so a publication failure
    // cannot MASK an in-flight exception propagating out of the try.
    try {
      await writeReport(plan, [...done.values()], blocked, aborted, runId, health);
    } catch (e) {
      publishError = e;
      console.error("report publication failed:", e);
    }
  }

  const results = [...done.values()];
  const esc = results.filter((r) => r.status === "escalate").length;
  const green = results.filter((r) => r.status === "green").length;
  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  // #387: two independent outcomes, two distinguishable exit codes.
  //   0 — every task settled green AND the authoritative receipt was published.
  //   2 — the RUN did not come out clean (escalation, blocked, breaker abort);
  //       the receipt IS on disk and can be reconciled.
  //   3 — the run-scoped AUTHORITATIVE receipt could not be published in full.
  //       Whatever the tasks did, this run's durable record is missing or
  //       incomplete, so it cannot be reliably reconciled or audited — its own
  //       failure mode, not a success and not "tasks failed".
  //
  // Deliberately NOT exit 3: a failure to refresh the shared "latest" pointers
  // under `${reportDir}`. Those are documented as non-authoritative and
  // last-writer-wins; failing the run on them would over-report failure in
  // exactly the concurrent-run case this design exists to make safe. They are
  // reported as a warning below instead.
  //
  // #398 adds a fourth input on the "2" side: an unreleased worktree or branch.
  // That is NOT a convenience-mirror failure — it is the farm still holding a
  // claim on a directory and a ref that the next run will collide with or
  // destructively pre-clean, so it belongs with "the run did not come out
  // clean" rather than in a warning line.
  const leaks = cleanupFailures(health, results);
  const runOutcome = runExitCode({ escalated: esc, blocked: blocked.length, aborted, cleanupFailures: leaks.length });
  const exitCode = publishError ? 3 : runOutcome;
  const latestReportErrors = health.report.latestMirrorErrors;
  const summary = [
    aborted ? `\nABORTED by circuit breaker — escalation rate exceeded ${ENV.abortEscalationRate}. The model may not be capable of this plan; consider the premium path or a different FARM_MODEL.` : ``,
    `\nDone. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Run: ${runId}  (artifacts: ${runDir})`,
    // #398: never let a leak be something the operator has to go looking for.
    leaks.length
      ? [
          `\nCLEANUP DEGRADED — ${leaks.length} resource(s) could not be released and re-verified:`,
          ...leaks.map((l) => `  - ${l.target} (${l.owner}): ${l.detail}`),
          `Git may still register these worktrees, or the directories may still be on disk. The next run's`,
          `pre-cleanup is destructive and best-effort, so clear them before re-running. Exit is non-zero for this alone.`,
        ].join("\n")
      : ``,
    // The success breadcrumb is SUPPRESSED when the authoritative publication
    // failed — pointing an operator at a farm-report.md that is not there is
    // the defect. Every claim below has to be true of what is actually on disk:
    // the message names the run directory and says "missing or incomplete"
    // rather than asserting no receipt exists, because a partial failure (e.g.
    // the JSON landed and the Markdown did not) leaves a real receipt behind.
    publishError
      ? [
          `\nRECEIPT PUBLICATION FAILED — run ${runId} could not publish its complete authoritative report under ${runDir}: ${msgOf(publishError)}`,
          `The tasks themselves finished ${runOutcome === 0 ? "green" : "with escalations/blocks/unreleased worktrees"}, but this run's durable receipt is missing or incomplete,`,
          `so it cannot be reliably reconciled or audited. Inspect ${runDir} for whatever did land.`,
          `${path.join(ENV.reportDir, "farm-report.json")} / .md were NOT refreshed and do not describe run ${runId}.`,
          `Exiting 3 (receipt failure) rather than ${runOutcome} (task outcome).`,
        ].join("\n")
      : latestReportErrors.length
        ? // Non-fatal, and stated as such. The authoritative receipt is
          // unaffected; what the operator must not assume is that the shared
          // path now describes THIS run.
          [
            `Report: ${path.join(runDir, "farm-report.md")}`,
            `WARNING: the latest convenience pointer under ${ENV.reportDir} could not be refreshed for this run:`,
            ...latestReportErrors.map((m) => `  - ${m}`),
            `The authoritative receipt above is unaffected, but ${path.join(ENV.reportDir, "farm-report.json")} does not describe run ${runId}.`,
          ].join("\n")
        : `Report: ${path.join(runDir, "farm-report.md")}  (latest: ${path.join(ENV.reportDir, "farm-report.md")})`,
    "",
  ].join("\n");
  await new Promise<void>((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(exitCode);
}

async function writeReport(
  plan: Plan,
  results: Result[],
  blocked: { id: string; reason: string }[],
  aborted: boolean,
  runId: string,
  health: RunArtifactHealth,
) {
  const runDir = runArtifactDir(runId);
  const diffsDir = path.join(runDir, "diffs");
  const latestDiffsDir = path.join(ENV.reportDir, "diffs");
  const unavailable = health.diffs.unavailable;
  // Only tasks whose patch actually landed get a link below (#387: the report
  // previously linked patch paths that the swallowed writes never created).
  const patchPath = new Map<string, string>();

  // Per-task diff artifacts for audit. Best-effort evidence: a failure here
  // does not sink the run, but it is recorded per task instead of being
  // discarded by a bare `.catch(() => {})`.
  let diffsDirError: string | null = null;
  await mkdir(diffsDir, { recursive: true }).catch((e) => {
    diffsDirError = msgOf(e);
  });
  await mkdir(latestDiffsDir, { recursive: true }).catch((e) =>
    noteArtifactError(health.diffs.latestMirrorErrors, `mkdir: ${msgOf(e)}`),
  );

  for (const r of results) {
    if (diffsDirError !== null) {
      noteUnavailableDiff(health.diffs, r.id, `diffs directory unavailable: ${diffsDirError}`);
      continue;
    }
    const d = await git(["diff", `${ENV.base}...${r.branch}`]);
    if (d.code !== 0) {
      noteUnavailableDiff(health.diffs, r.id, `git diff failed: ${d.out.trim().split("\n")[0] ?? ""}`.slice(0, 300));
      continue;
    }
    // An empty diff is a legitimate outcome (nothing was written), not missing
    // evidence — it produces no patch and no "unavailable" marker.
    if (!d.out.trim()) continue;
    const dest = path.join(diffsDir, `${r.id}.patch`);
    try {
      await atomicWriteFile(dest, d.out);
      patchPath.set(r.id, dest);
    } catch (e) {
      noteUnavailableDiff(health.diffs, r.id, `patch write failed: ${msgOf(e)}`);
      continue;
    }
    await atomicWriteFile(path.join(latestDiffsDir, `${r.id}.patch`), d.out).catch((e) =>
      noteArtifactError(health.diffs.latestMirrorErrors, `${r.id}: ${msgOf(e)}`),
    );
  }

  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  const leaks = cleanupFailures(health, results);

  // #387: the report carries its own integrity statement, so a consumer never
  // has to guess whether a short stream or a missing patch is real or a
  // swallowed write failure.
  const streamComplete = health.stream.errors.length === 0;
  const artifacts = {
    run_dir: runDir,
    stream: {
      path: path.join(runDir, "farm-results.jsonl"),
      latest: path.join(ENV.reportDir, "farm-results.jsonl"),
      complete: streamComplete,
      errors: health.stream.errors,
    },
    diffs: {
      dir: diffsDir,
      latest_dir: latestDiffsDir,
      // `unavailable` is capped; `unavailable_total` is not, so a bounded list
      // never understates how many tasks lack diff evidence.
      unavailable,
      unavailable_total: health.diffs.unavailableTotal,
      latest_mirror_errors: health.diffs.latestMirrorErrors,
    },
    // #398: the run's resource-ownership statement. `released` is an explicit
    // positive claim, so a consumer can distinguish "nothing leaked" from "this
    // report predates the check" without inferring it from an absent key.
    cleanup: { released: leaks.length === 0, failures: leaks },
  };

  // One projection, two sinks. #439.
  const reportMeta = projectPlanMetaForReport(plan.meta);

  const json = JSON.stringify(
    { run_id: runId, plan: reportMeta, aborted, tokens: { prompt: pTok, completion: cTok }, results, blocked, artifacts, ts: new Date().toISOString() },
    null,
    2,
  );

  // #439: BOTH receipts, not just the JSON. `farm-report.md` is written by the
  // same tier-1 publish and mirrored to the latest pointer, so redacting the
  // JSON alone left the one field it does redact leaking verbatim into the
  // Markdown sibling. Projected once, above, and used by both sinks - a second
  // call here would be a second place to forget.
  const md = [
    `# Farm report — ${reportMeta.name}`,
    ``,
    aborted ? `> **ABORTED by circuit breaker** — escalation rate exceeded threshold.\n` : ``,
    streamComplete ? `` : `> **Streaming rail incomplete** — ${health.stream.errors.length} write failure(s) on \`farm-results.jsonl\`; this report is authoritative for settled tasks.\n`,
    leaks.length ? `> **CLEANUP DEGRADED** — ${leaks.length} worktree/branch could not be released; see Resource cleanup below.\n` : ``,
    `Run: \`${runId}\` — artifacts under \`${runDir}\``,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    ``,
    `| task | status | attempts | files | mut | branch | note |`,
    `| --- | --- | --- | --- | --- | --- | --- |`,
    ...results.map((r) => `| ${r.id} | ${r.status}${r.warning ? " ⚠" : ""} | ${r.attempts} | ${(r.filesWritten ?? []).length} | ${r.mutationScore == null ? "—" : r.mutationScore.toFixed(2)} | ${r.branch} | ${r.note ?? r.warning ?? ""} |`),
    ...blocked.map((b) => `| ${b.id} | blocked | 0 | 0 | — | — | ${b.reason} |`),
    ``,
    `## Escalations — handle only these`,
    ...results
      .filter((r) => r.status === "escalate")
      .map((r) => `- **${r.id}** — worktree \`${r.worktree}\`, branch \`${r.branch}\`. ${r.note ?? ""}`),
    ``,
    `## Diff evidence`,
    ...(health.diffs.unavailableTotal
      ? [
          `${health.diffs.unavailableTotal} task(s) have no diff evidence${unavailable.length < health.diffs.unavailableTotal ? ` (first ${MAX_RECORDED_ARTIFACT_ERRORS} listed)` : ``}:`,
          ...unavailable.map((u) => `- **${u.id}** — diff evidence unavailable: ${u.reason}`),
        ]
      : [`Every settled task with a non-empty diff has a patch under \`${diffsDir}\`.`]),
    ``,
    ...cleanupReportLines(health, results),
    ``,
    `## Warnings — review during spec-compliance`,
    ...results.filter((r) => r.warning).map((r) => {
      const p = patchPath.get(r.id);
      return `- **${r.id}** — ${r.warning} (${p ? `diff: \`${p}\`` : "diff evidence unavailable"})`;
    }),
  ].join("\n");

  // #387/#397: publication, in two clearly separated tiers.
  //
  // Tier 1 — the AUTHORITATIVE receipt, run-scoped and exclusively owned. Any
  // failure THROWS, and main() turns it into exit 3 instead of a console line
  // behind a green summary.
  await atomicWriteFile(path.join(runDir, "farm-report.json"), json);
  await atomicWriteFile(path.join(runDir, "farm-report.md"), md);

  // Tier 2 — the shared "latest" convenience pointers. These are explicitly
  // NON-authoritative and last-writer-wins, so their failure must not fail a
  // run whose durable receipt just landed above. (Getting this wrong inverts
  // the fix: two concurrent runs racing this very rename on Windows are what
  // renameWithRetry exists for, and exhausting its retries would otherwise sink
  // a fully green, fully receipted run.) Recorded and surfaced on the summary,
  // never silently dropped — a stale pointer that is not this run's is exactly
  // the thing an operator must not be left to assume.
  for (const [dest, data] of [
    [path.join(ENV.reportDir, "farm-report.json"), json],
    [path.join(ENV.reportDir, "farm-report.md"), md],
  ] as const)
    await atomicWriteFile(dest, data).catch((e) =>
      noteArtifactError(health.report.latestMirrorErrors, `${dest}: ${msgOf(e)}`),
    );
}

// Only execute when this file is the direct entry point (not when imported by
// unit tests). tsx resolves import.meta.url correctly in both modes.
const _thisFile = fileURLToPath(import.meta.url);
const _entryFile = path.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
