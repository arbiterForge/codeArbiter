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
import { readFile, writeFile, appendFile, mkdir, rm, stat } from "node:fs/promises";
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
  // worktree before the worker, on every attempt (so they survive the
  // inter-attempt reset that wipes untracked deps). The common case is repo-wide
  // dependency install (`npm ci`, `pip install -r requirements.txt`); set
  // plan.meta.setup and it propagates here at dispatch. A per-task value
  // overrides the meta default. Setup artifacts MUST be gitignored or they trip
  // drift detection. A failing setup command escalates the task immediately.
  setup?: string[];
  // Optional per-task model override (AC-02). The effective model for a task is
  // `task.model ?? <run-level resolved model>`, layered where runTask invokes
  // the worker; absent → identical current behavior. Model id only — no second
  // provider or per-task apiBaseUrl.
  model?: string;
};
type Plan = {
  meta: { name: string; repo?: string; model?: string; apiBaseUrl?: string; setup?: string[] };
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
    await mkdir(path.dirname(absPath), { recursive: true });
    await writeFile(absPath, body.endsWith("\n") ? body : body + "\n");
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

async function resetWorktree(wt: string) {
  await git(["reset", "--hard", "HEAD"], wt);
  await git(["clean", "-fd"], wt);
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
};

// observability-003 (T-07c): a short run-id minted once at main() startup. Six
// hex chars from crypto.randomBytes — enough to disambiguate concurrent runs in
// the shared JSONL stream without bloating every line.
export function mintRunId(): string {
  return randomBytes(3).toString("hex");
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
async function writeFilesInto(wt: string, files: Array<{ path: string; contents: string }>): Promise<void> {
  for (const f of files) {
    const abs = path.resolve(wt, f.path);
    if (!isInside(wt, abs)) continue;
    await mkdir(path.dirname(abs), { recursive: true });
    await writeFile(abs, f.contents.endsWith("\n") ? f.contents : f.contents + "\n");
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
        if (t.setup && t.setup.length > 0) {
          const sr = await deps.runGate(wt, t.setup);
          if (!sr.ok) return { ...base, note: redactSecrets(`setup failed: ${sr.failed}\n${sr.tail}`) };
        }
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
  for (const o of outcomes) {
    await deps.git(["worktree", "remove", "--force", o.wt]).catch(() => {});
    await deps.git(["branch", "-D", o.branch]).catch(() => {});
  }
  return { winner, bestFailure, promptTokens, completionTokens };
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

  const prepErr = await deps.prepareWorktree(branch, wt, ENV.integration);
  if (prepErr)
    return { id: t.id, status: "escalate", attempts: 0, branch, worktree: wt, note: prepErr };

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

    // Per-worktree setup (#92): run dependency-setup commands in the worktree
    // before the worker. Runs every attempt because the reset above wipes
    // untracked deps (node_modules etc.); on the happy path (attempt 1 passes)
    // it runs once. Executed through the same gate machinery (shell + exit
    // code, redacted tail). A setup failure is environmental, not the worker's
    // fault, so it escalates immediately rather than burning a worker retry.
    if (t.setup && t.setup.length > 0) {
      const setupResult = await deps.runGate(wt, t.setup);
      if (!setupResult.ok)
        return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: redactSecrets(`setup failed: ${setupResult.failed}\n${setupResult.tail}`), promptTokens, completionTokens };
    }

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
      await writeFilesInto(wt, sel.winner.files);
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
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: sweepErr, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    }

    // The failing test must be untouched (defence in depth — the write path
    // already refuses test.path, this catches a sneaky in-scope edit too).
    const testHashAfter = await deps.fileHash(path.resolve(wt, t.test.path));
    if (testHashBefore !== null && testHashAfter !== testHashBefore) {
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `tampered test: ${t.test.path}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
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
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `drift: ${driftFiles.join(", ")}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
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
      const mut = await deps.mutationCheck(wt, t);
      if (mut && "score" in mut) {
        mutationScore = mut.score;
        if (mut.score <= MUT.escalateBelow && mut.evaluated >= 5) {
          risk = "high";
          riskNote = `gaming: mutation score ${mut.score.toFixed(2)} (${mut.evaluated} mutants survived — the test does not constrain the implementation)`;
        } else if (mut.score < MUT.warnBelow) {
          if (risk !== "warn") {
            risk = "warn";
            riskNote = `mutation-risk: score ${mut.score.toFixed(2)} (${mut.survivors.length}/${mut.evaluated} survived) — weak test or under-implemented logic`;
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
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: riskNote, filesWritten: worker.filesWritten, promptTokens, completionTokens, mutationScore };
    }
    if (risk === "warn") lastWarning = riskNote;

    // Commit + merge into the dedicated integration worktree.
    // B-1: stage only the files the worker actually wrote, not everything in the
    // worktree — git add -A would silently include any stale or injected files.
    await deps.git(["add", "--", ...worker.filesWritten], wt);
    const commit = await deps.git([...NOSIGN, "commit", "-m", `farm(${t.id}): ${t.description}`], wt);
    if (commit.code !== 0)
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `commit failed: ${commit.out.slice(0, 200)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };

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
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `merge failed vs integration: ${String(merged).slice(0, 160)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    }

    // success — drop the worktree (branch stays, merged into integration)
    await deps.git(["worktree", "remove", "--force", wt]).catch(() => {});
    return { id: t.id, status: "green", attempts: attempt, branch, worktree: wt, warning: lastWarning, filesWritten: worker.filesWritten, diffstat, promptTokens, completionTokens, mutationScore, samples, acceptedPromptTokens, acceptedCompletionTokens };
  }

  // worktree intentionally left in place for inspection
  return { id: t.id, status: "escalate", attempts: limit + 1, branch, worktree: wt, note: priorFailure?.split("\n")[0], filesWritten: lastFilesWritten, promptTokens, completionTokens, mutationScore };
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
  if (plan.meta.setup) checkSetup("plan.meta.setup", plan.meta.setup);

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
  const plan = JSON.parse(await readFile(planPath, "utf8")) as Plan;
  validate(plan);

  // #92: propagate the repo-wide meta.setup to every task that did not declare
  // its own (task.setup wins; meta.setup fills the gap). Done once at dispatch,
  // before main and canary, so runTask only ever reads the effective t.setup.
  if (plan.meta.setup)
    for (const t of plan.tasks) if (t.setup === undefined) t.setup = plan.meta.setup;

  if (canary) return runCanary(plan);

  const { model, apiBaseUrl, apiKey } = resolveConfig(plan);

  // observability-003 (T-07c): one run-id for this whole invocation, threaded
  // into every farm-results.jsonl line and the farm-report.json header.
  const runId = mintRunId();

  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });

  // Streaming rail (AC-08 / D7): the incremental, append-only record of settled
  // tasks, consumed in completion order. Truncate/initialize it at run start so
  // a re-run does not accumulate stale lines (the "safe to run twice" invariant).
  // The authoritative final summary remains farm-report.json (written in the
  // finally, even on abort); on abort the consumer reconciles against it.
  const resultsStream = path.join(ENV.reportDir, "farm-results.jsonl");
  await writeFile(resultsStream, "").catch((e) => console.error("results stream init failed:", e));

  const done = new Map<string, Result>();
  const blocked: { id: string; reason: string }[] = [];
  let aborted = false;

  try {
    const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
    if (branchResult.code !== 0)
      throw new Error(`could not create integration branch '${ENV.integration}' from '${ENV.base}': ${branchResult.out}`);

    integrationWorktree = path.resolve(ENV.reportDir, "integration-wt");
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
      // order. Resilient by design — mirror the report-write .catch so a stream
      // failure logs but never crashes the run (the report stays authoritative).
      await appendFile(resultsStream, JSON.stringify(r) + "\n").catch((e) => console.error("results stream append failed:", e));
      if (r.status === "escalate") escalated.add(id);
    }

    // anything still pending is blocked (dependency escalated, cycle-free by validate, or aborted)
    for (const id of pending) {
      const deps = byId.get(id)!.deps ?? [];
      const culprit = deps.find((d) => escalated.has(d));
      blocked.push({ id, reason: aborted ? "run aborted (circuit breaker)" : culprit ? `dependency ${culprit} escalated` : "not scheduled" });
    }
  } finally {
    await writeReport(plan, [...done.values()], blocked, aborted, runId).catch((e) => console.error("report write failed:", e));
    // reliability-004 (T-07a): only remove the integration worktree if it was
    // actually assigned. An early throw (e.g. the integration branch could not
    // be created) leaves `integrationWorktree` undefined; passing undefined as an
    // argv element into spawn throws a synchronous TypeError out of this finally,
    // masking the real, actionable error. Guard it so the original error
    // surfaces.
    if (integrationWorktree)
      await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});
  }

  const results = [...done.values()];
  const esc = results.filter((r) => r.status === "escalate").length;
  const green = results.filter((r) => r.status === "green").length;
  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  const exitCode = esc || blocked.length || aborted ? 2 : 0;
  const summary = [
    aborted ? `\nABORTED by circuit breaker — escalation rate exceeded ${ENV.abortEscalationRate}. The model may not be capable of this plan; consider the premium path or a different FARM_MODEL.` : ``,
    `\nDone. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Report: ${path.join(ENV.reportDir, "farm-report.md")}`,
    "",
  ].join("\n");
  await new Promise<void>((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(exitCode);
}

async function writeReport(plan: Plan, results: Result[], blocked: { id: string; reason: string }[], aborted: boolean, runId?: string) {
  // per-task diff artifacts for audit
  await mkdir(path.join(ENV.reportDir, "diffs"), { recursive: true }).catch(() => {});
  for (const r of results) {
    const d = await git(["diff", `${ENV.base}...${r.branch}`]);
    if (d.code === 0 && d.out.trim())
      await writeFile(path.join(ENV.reportDir, "diffs", `${r.id}.patch`), d.out).catch(() => {});
  }

  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);

  await writeFile(
    path.join(ENV.reportDir, "farm-report.json"),
    JSON.stringify({ run_id: runId, plan: plan.meta, aborted, tokens: { prompt: pTok, completion: cTok }, results, blocked, ts: new Date().toISOString() }, null, 2),
  );

  const md = [
    `# Farm report — ${plan.meta.name}`,
    ``,
    aborted ? `> **ABORTED by circuit breaker** — escalation rate exceeded threshold.\n` : ``,
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
    `## Warnings — review during spec-compliance`,
    ...results.filter((r) => r.warning).map((r) => `- **${r.id}** — ${r.warning} (diff: \`${path.join(ENV.reportDir, "diffs", r.id + ".patch")}\`)`),
  ].join("\n");
  await writeFile(path.join(ENV.reportDir, "farm-report.md"), md);
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
