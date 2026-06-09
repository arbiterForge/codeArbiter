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
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir, rm, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";

// --------------------------------------------------------------------------
// Types — the handoff contract. Claude emits plan.json conforming to this.
// --------------------------------------------------------------------------
type Task = {
  id: string;
  description: string;
  deps?: string[];
  filesInScope: string[];
  test: { path: string };
  gate: { commands: string[] };
  context?: string;
  maxRetries?: number;
};
type Plan = {
  meta: { name: string; repo?: string; model?: string; apiBaseUrl?: string };
  tasks: Task[];
};

const ENV = {
  // Model: plan.meta.model (set by subagent-driven-development before dispatch),
  // then FARM_MODEL env var override. Fails at startup if neither is set.
  model: process.env.FARM_MODEL ?? null,
  // No-default kept deliberately: dispatch records the chosen endpoint in
  // plan.meta.apiBaseUrl. A code default is provided only as a last resort so a
  // user who sets just FARM_API_KEY (per the docs) is not hard-blocked.
  apiBaseUrl: process.env.FARM_API_BASE_URL ?? null,
  apiKey: process.env.FARM_API_KEY ?? null,
  concurrency: Number(process.env.FARM_CONCURRENCY ?? 4),
  maxRetries: Number(process.env.FARM_MAX_RETRIES ?? 2),
  base: process.env.FARM_BASE_BRANCH ?? "main",
  integration: process.env.FARM_INTEGRATION_BRANCH ?? "farm/integration",
  worktreeRoot: process.env.FARM_WORKTREE_ROOT ?? ".farm/worktrees",
  reportDir: process.env.FARM_REPORT_DIR ?? ".farm",
  // Per-request hard timeout so a hung endpoint can't deadlock a worker slot.
  requestTimeoutMs: Number(process.env.FARM_REQUEST_TIMEOUT_MS ?? 120_000),
  // Transport-level retries (429 / 5xx) — distinct from model-quality retries.
  apiMaxRetries: Number(process.env.FARM_API_MAX_RETRIES ?? 3),
  // Circuit breaker: abort dispatch once the escalation rate exceeds this,
  // after at least abortMinTasks have settled.
  abortEscalationRate: Number(process.env.FARM_ABORT_ESCALATION_RATE ?? 0.5),
  abortMinTasks: Number(process.env.FARM_ABORT_MIN_TASKS ?? 3),
  // Default endpoint, used only when neither env nor plan.meta provides one.
  defaultApiBaseUrl:
    process.env.FARM_DEFAULT_API_BASE_URL ?? "https://api.opencode.ai/v1",
  // Comma-separated candidate model ids for --canary mode.
  candidateModels: (process.env.FARM_CANDIDATE_MODELS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
};

// Mutation guard — a zero-token quality signal. After the gate goes green we
// mutate the worker's in-scope impl and re-run ONLY the task's narrow test
// (gate.commands[0]); a mutant the test fails to catch ("survivor") is code the
// test does not constrain — gaming, dead code, or a weak test. Bounded by test
// strength, so a LOW score is a strong red flag but a high one is only
// necessary-not-sufficient. Low score → warning into Phase 3; only a near-zero
// score on a non-trivial impl hard-escalates. Pluggable: set FARM_MUTATION_CMD
// to a real per-language framework (it runs in the worktree with
// FARM_MUTATION_FILES / FARM_MUTATION_TEST_PATH / FARM_MUTATION_TEST_CMD set,
// and must print a trailing JSON line containing a numeric "score").
const MUT = {
  enabled: (process.env.FARM_MUTATION ?? "on").toLowerCase() !== "off",
  sample: Number(process.env.FARM_MUTATION_SAMPLE ?? 15),
  budgetMs: Number(process.env.FARM_MUTATION_BUDGET_MS ?? 30_000),
  warnBelow: Number(process.env.FARM_MUTATION_WARN_BELOW ?? 0.5),
  escalateBelow: Number(process.env.FARM_MUTATION_ESCALATE_BELOW ?? 0.1),
  cmd: process.env.FARM_MUTATION_CMD ?? null,
};

// --------------------------------------------------------------------------
// process helpers
// --------------------------------------------------------------------------
function run(cmd: string, args: string[], cwd?: string) {
  return new Promise<{ code: number; out: string }>((resolve) => {
    const c = spawn(cmd, args, { cwd, env: process.env });
    let out = "";
    c.stdout.on("data", (d) => (out += d));
    c.stderr.on("data", (d) => (out += d));
    c.on("error", (e) => resolve({ code: 1, out: String(e) }));
    c.on("close", (code) => resolve({ code: code ?? 1, out }));
  });
}
const git = (args: string[], cwd?: string) => run("git", args, cwd);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

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

// --------------------------------------------------------------------------
// gate — pure determinism, no model. `bash -c` (NOT -lc): a login shell would
// source the invoking user's dotfiles and make the gate non-deterministic.
// --------------------------------------------------------------------------
async function runGate(cwd: string, commands: string[]) {
  for (const cmd of commands) {
    const r = await run("bash", ["-c", cmd], cwd);
    if (r.code !== 0)
      return { ok: false as const, failed: cmd, tail: r.out.slice(-3500) };
  }
  return { ok: true as const };
}

// --------------------------------------------------------------------------
// worker prompt
// --------------------------------------------------------------------------
function buildPrompt(t: Task, priorFailure?: string, forbiddenExtra?: string[]) {
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
    ``,
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
function extractFileBlocks(content: string): Array<{ path: string; body: string }> {
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

type WorkerResult = {
  ok: boolean;
  filesWritten: string[];
  error?: string;
  promptTokens?: number;
  completionTokens?: number;
};

async function callApi(
  prompt: string,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
): Promise<{ ok: true; content: string; usage?: { prompt_tokens?: number; completion_tokens?: number } } | { ok: false; error: string }> {
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
        body: JSON.stringify({
          model,
          messages: [{ role: "user", content: prompt }],
        }),
        signal: ctrl.signal,
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
    clearTimeout(timer);

    // Transport-level failure (rate limit / server) — back off and retry the
    // REQUEST, not the task. A 429 is not a failed implementation attempt.
    if (resp.status === 429 || resp.status >= 500) {
      if (attempt < ENV.apiMaxRetries) {
        const ra = Number(resp.headers.get("retry-after"));
        const wait = Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(2 ** attempt * 1000, 16_000);
        await sleep(wait);
        continue;
      }
      const body = await resp.text().catch(() => "(unreadable)");
      return { ok: false, error: `API ${resp.status} after ${ENV.apiMaxRetries} retries: ${body.slice(0, 300)}` };
    }
    if (!resp.ok) {
      const body = await resp.text().catch(() => "(unreadable)");
      return { ok: false, error: `API ${resp.status}: ${body.slice(0, 500)}` };
    }

    let data: { choices?: Array<{ message?: { content?: string } }>; usage?: { prompt_tokens?: number; completion_tokens?: number } };
    try {
      data = (await resp.json()) as typeof data;
    } catch (e) {
      return { ok: false, error: `non-JSON response: ${e}` };
    }
    return { ok: true, content: data.choices?.[0]?.message?.content ?? "", usage: data.usage };
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
): Promise<WorkerResult> {
  const api = await callApi(prompt, model, apiBaseUrl, apiKey);
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
    const rel = path.relative(cwd, absPath);
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
// drift check — path allowlist. Catches modified tracked files and new
// untracked files individually (status --porcelain groups by directory).
// --------------------------------------------------------------------------
async function checkDrift(cwd: string, allowed: Set<string>): Promise<string[]> {
  const tracked = await git(["diff", "--name-only", "HEAD"], cwd);
  const untracked = await git(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd,
  );
  const changed: string[] = [];
  if (tracked.code === 0)
    changed.push(...tracked.out.trim().split("\n").filter(Boolean));
  if (untracked.code === 0)
    changed.push(...untracked.out.split("\0").filter(Boolean));
  return [...new Set(changed)].filter((f) => !allowed.has(f));
}

// --------------------------------------------------------------------------
// anti-gaming guard — zero-token heuristic. A cheap model can satisfy a narrow
// test by hard-coding the asserted value. We extract the literals the test
// asserts and flag an impl file that (a) is tiny and (b) reproduces a
// non-trivial test literal verbatim. Egregious cases escalate; borderline
// cases attach a warning that rides into the report for the human reviewer.
// --------------------------------------------------------------------------
function extractLiterals(testSrc: string): string[] {
  const lits = new Set<string>();
  // quoted strings
  for (const m of testSrc.matchAll(/(['"`])((?:\\.|(?!\1).){2,})\1/g)) lits.add(m[2]);
  // multi-digit / non-0-1 numbers
  for (const m of testSrc.matchAll(/\b(\d{2,}|[2-9])\b/g)) lits.add(m[1]);
  return [...lits];
}

function codeLineCount(src: string): number {
  return src
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("//") && !l.startsWith("#") && !l.startsWith("*") && !l.startsWith("/*")).length;
}

async function antiGamingCheck(
  cwd: string,
  task: Task,
): Promise<{ risk: "none" | "warn" | "high"; note?: string }> {
  let testSrc = "";
  try {
    testSrc = await readFile(path.resolve(cwd, task.test.path), "utf8");
  } catch {
    return { risk: "none" };
  }
  const literals = extractLiterals(testSrc).filter((l) => l.length > 1 || /\d{2,}/.test(l));
  if (literals.length === 0) return { risk: "none" };

  const hits: string[] = [];
  let anyTiny = false;
  for (const f of task.filesInScope) {
    if (f === task.test.path) continue;
    let src = "";
    try {
      src = await readFile(path.resolve(cwd, f), "utf8");
    } catch {
      continue;
    }
    const tiny = codeLineCount(src) <= 5;
    for (const lit of literals) {
      if (src.includes(lit)) {
        hits.push(`${f} contains test literal ${JSON.stringify(lit)}`);
        if (tiny) anyTiny = true;
      }
    }
  }
  if (hits.length === 0) return { risk: "none" };
  if (anyTiny) return { risk: "high", note: `gaming: ${hits[0]} (impl is trivial)` };
  return { risk: "warn", note: `gaming-risk: ${hits[0]}` };
}

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
// mutation guard
// --------------------------------------------------------------------------
function shuffle<T>(a: T[]): T[] {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Single-point text mutants. Space-padded operators bias toward real code (not
// string/generic content); invalid mutants that break compilation just fail the
// test and count as "killed" — the lenient direction (no false escalation).
function generateMutants(file: string, src: string): Array<{ file: string; mutated: string; tag: string }> {
  const lines = src.split("\n");
  const rules: Array<[RegExp, string, string]> = [
    [/ >= /, " > ", ">=>"], [/ <= /, " < ", "<=<"],
    [/ === /, " !== ", "===>!=="], [/ !== /, " === ", "!==>==="],
    [/ == /, " != ", "==>!="], [/ != /, " == ", "!=>=="],
    [/ > /, " >= ", ">>="], [/ < /, " <= ", "<<="],
    [/ \+ /, " - ", "+>-"], [/ - /, " + ", "->+"], [/ \* /, " \/ ", "*>/"],
    [/ && /, " || ", "&&>||"], [/ \|\| /, " && ", "||>&&"],
    [/\btrue\b/, "false", "true>false"], [/\bfalse\b/, "true", "false>true"],
  ];
  const out: Array<{ file: string; mutated: string; tag: string }> = [];
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const t = ln.trim();
    if (!t || t.startsWith("//") || t.startsWith("#") || t.startsWith("*") || t.startsWith("/*")) continue;
    for (const [re, rep, name] of rules) {
      if (re.test(ln)) {
        const mline = ln.replace(re, rep);
        if (mline !== ln) {
          const m = [...lines]; m[i] = mline;
          out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} ${name}` });
        }
      }
    }
    const rm = ln.match(/\breturn\s+(.+?);/);
    if (rm && rm[1].trim() !== "null" && rm[1].trim() !== "") {
      const m = [...lines];
      m[i] = ln.replace(/\breturn\s+.+?;/, "return null;");
      out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} return>null` });
    }
  }
  return out;
}

type MutationResult = { score: number; evaluated: number; survivors: string[] };

async function mutationCheck(wt: string, task: Task): Promise<MutationResult | null> {
  if (!MUT.enabled) return null;
  const testCmd = task.gate.commands[0];
  if (!testCmd) return null;
  const impl = task.filesInScope.filter((f) => f !== task.test.path);

  // Pluggable hook — hand off to a real per-language framework if configured.
  if (MUT.cmd) {
    const r = await new Promise<{ code: number; out: string }>((resolve) => {
      const c = spawn("bash", ["-c", MUT.cmd!], {
        cwd: wt,
        env: { ...process.env, FARM_MUTATION_FILES: impl.join(","), FARM_MUTATION_TEST_PATH: task.test.path, FARM_MUTATION_TEST_CMD: testCmd },
      });
      let out = "";
      c.stdout.on("data", (d) => (out += d));
      c.stderr.on("data", (d) => (out += d));
      c.on("error", (e) => resolve({ code: 1, out: String(e) }));
      c.on("close", (code) => resolve({ code: code ?? 1, out }));
    });
    const j = [...r.out.matchAll(/\{[^\n]*"score"[^\n]*\}/g)].pop();
    if (!j) return null;
    try {
      const parsed = JSON.parse(j[0]) as { score?: number; total?: number; evaluated?: number; survived?: string[] };
      if (typeof parsed.score === "number")
        return { score: parsed.score, evaluated: parsed.total ?? parsed.evaluated ?? 99, survivors: parsed.survived ?? [] };
    } catch {
      /* unparseable — skip leniently */
    }
    return null;
  }

  // Built-in text mutation.
  const originals = new Map<string, string>();
  let candidates: Array<{ file: string; mutated: string; tag: string }> = [];
  for (const f of impl) {
    let src: string;
    try {
      src = await readFile(path.resolve(wt, f), "utf8");
    } catch {
      continue;
    }
    if (codeLineCount(src) <= 2) continue; // trivial file — nothing to constrain
    originals.set(f, src);
    candidates.push(...generateMutants(f, src));
  }
  if (candidates.length === 0) return null;
  candidates = shuffle(candidates).slice(0, MUT.sample);

  const start = Date.now();
  let killed = 0;
  let evaluated = 0;
  const survivors: string[] = [];
  try {
    for (const c of candidates) {
      if (Date.now() - start > MUT.budgetMs) break;
      await writeFile(path.resolve(wt, c.file), c.mutated);
      const r = await run("bash", ["-c", testCmd], wt);
      await writeFile(path.resolve(wt, c.file), originals.get(c.file)!); // restore
      evaluated++;
      if (r.code !== 0) killed++;
      else survivors.push(c.tag);
    }
  } finally {
    // defensive: guarantee every impl file is back to the worker's output
    for (const [f, src] of originals) await writeFile(path.resolve(wt, f), src).catch(() => {});
  }
  if (evaluated < 3) return null; // too few mutants to judge fairly
  return { score: killed / evaluated, evaluated, survivors };
}

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
};

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
  // Clean any stale worktree dir and branch so a re-run doesn't trip over the
  // leftovers of a prior run (git worktree add -b fails if the branch exists).
  await git(["worktree", "remove", "--force", wt]).catch(() => {});
  await rm(wt, { recursive: true, force: true }).catch(() => {});
  await git(["branch", "-D", branch]).catch(() => {});
  const add = await git(["worktree", "add", "-b", branch, wt, from]);
  if (add.code !== 0) return `worktree add failed: ${add.out.slice(0, 200)}`;
  return null;
}

async function runTask(
  t: Task,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
): Promise<Result> {
  const branch = `farm/${t.id}`;
  const wt = path.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;
  const allowed = new Set(t.filesInScope);
  const forbidden = new Set([t.test.path]);

  const prepErr = await prepareWorktree(branch, wt, ENV.integration);
  if (prepErr)
    return { id: t.id, status: "escalate", attempts: 0, branch, worktree: wt, note: prepErr };

  const testHashBefore = await fileHash(path.resolve(wt, t.test.path));

  let priorFailure: string | undefined;
  let driftedOnce = false;
  let lastFilesWritten: string[] = [];
  let promptTokens = 0;
  let completionTokens = 0;
  let lastWarning: string | undefined;
  let mutationScore: number | null = null;

  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    if (attempt > 1) await resetWorktree(wt); // never accumulate stale files

    const worker = await runWorker(
      wt,
      buildPrompt(t, priorFailure, driftedOnce ? lastFilesWritten.filter((f) => !allowed.has(f)) : undefined),
      model,
      apiBaseUrl,
      apiKey,
      forbidden,
    );
    promptTokens += worker.promptTokens ?? 0;
    completionTokens += worker.completionTokens ?? 0;
    lastFilesWritten = worker.filesWritten;

    if (!worker.ok) {
      priorFailure = `worker error: ${worker.error}`;
      continue;
    }

    // The failing test must be untouched (defence in depth — the write path
    // already refuses test.path, this catches a sneaky in-scope edit too).
    const testHashAfter = await fileHash(path.resolve(wt, t.test.path));
    if (testHashBefore !== null && testHashAfter !== testHashBefore) {
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `tampered test: ${t.test.path}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    }

    // Drift: on the FIRST drift, retry once with a hardened prompt naming the
    // offending paths — usually the cheap model is just being dumb, not the
    // spec being ambiguous. Only escalate as drift after that retry.
    const driftFiles = await checkDrift(wt, allowed);
    if (driftFiles.length > 0) {
      if (!driftedOnce && attempt <= limit) {
        driftedOnce = true;
        priorFailure = `drift: you wrote outside the allowed files: ${driftFiles.join(", ")}`;
        continue;
      }
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `drift: ${driftFiles.join(", ")}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    }

    const gate = await runGate(wt, t.gate.commands);
    if (!gate.ok) {
      priorFailure = `failed: ${gate.failed}\n${gate.tail}`;
      continue;
    }

    // Zero-token anti-gaming guard: fast literal-leak pass, then the deeper
    // mutation pass (skipped if the leak pass already says "high").
    const gaming = await antiGamingCheck(wt, t);
    let risk = gaming.risk;
    let riskNote = gaming.note;
    if (risk !== "high") {
      const mut = await mutationCheck(wt, t);
      if (mut) {
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
      }
    }
    if (risk === "high") {
      priorFailure = `${riskNote}. Implement real logic; do not hard-code or special-case the asserted value.`;
      if (attempt <= limit) continue; // give it a chance to fix
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: riskNote, filesWritten: worker.filesWritten, promptTokens, completionTokens, mutationScore };
    }
    if (risk === "warn") lastWarning = riskNote;

    // Commit + merge into the dedicated integration worktree.
    await git(["add", "-A"], wt);
    const commit = await git([...NOSIGN, "commit", "-m", `farm(${t.id}): ${t.description}`], wt);
    if (commit.code !== 0)
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `commit failed: ${commit.out.slice(0, 200)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };

    const diffstat = (await git(["diff", "--stat", `${ENV.base}...${branch}`], wt)).out.trim();

    const merged = await withMergeLock(async () => {
      const m = await git([...NOSIGN, "merge", "--no-ff", "-m", `merge ${t.id}`, branch], integrationWorktree);
      if (m.code !== 0) {
        await git(["merge", "--abort"], integrationWorktree).catch(() => {});
        return m.out;
      }
      return null;
    });
    if (merged !== null)
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `merge failed vs integration: ${String(merged).slice(0, 160)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };

    // success — drop the worktree (branch stays, merged into integration)
    await git(["worktree", "remove", "--force", wt]).catch(() => {});
    return { id: t.id, status: "green", attempts: attempt, branch, worktree: wt, warning: lastWarning, filesWritten: worker.filesWritten, diffstat, promptTokens, completionTokens, mutationScore };
  }

  // worktree intentionally left in place for inspection
  return { id: t.id, status: "escalate", attempts: limit + 1, branch, worktree: wt, note: priorFailure?.split("\n")[0], filesWritten: lastFilesWritten, promptTokens, completionTokens, mutationScore };
}

// --------------------------------------------------------------------------
// validation — duplicate ids, unknown deps, AND cycles
// --------------------------------------------------------------------------
function validate(plan: Plan) {
  const ids = new Set<string>();
  for (const t of plan.tasks) {
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);
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
  if (!model) {
    console.error(
      "Error: No model configured.\n" +
        "Set FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\n" +
        "See .codearbiter/farm.md for setup instructions.",
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.\nSee .codearbiter/farm.md for setup instructions.");
    process.exit(1);
  }
  return { model, apiBaseUrl, apiKey };
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

  const results: Array<{ model: string; green: boolean; attempts: number; ms: number; note?: string }> = [];
  for (const model of ENV.candidateModels) {
    const t0 = Date.now();
    const r = await runTask({ ...task, id: `canary-${task.id}` }, model, apiBaseUrl, apiKey);
    results.push({ model, green: r.status === "green", attempts: r.attempts, ms: Date.now() - t0, note: r.note });
    await git(["worktree", "remove", "--force", path.resolve(ENV.worktreeRoot, `canary-${task.id}`)]).catch(() => {});
    await git(["branch", "-D", `farm/canary-${task.id}`]).catch(() => {});
  }
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});

  results.sort((a, b) => Number(b.green) - Number(a.green) || a.attempts - b.attempts || a.ms - b.ms);
  await writeFile(path.join(ENV.reportDir, "canary-report.json"), JSON.stringify({ task: task.id, results, ts: new Date().toISOString() }, null, 2));
  const summary = ["\nCanary results (best first):", ...results.map((r) => `  ${r.green ? "PASS" : "FAIL"}  ${r.model}  attempts=${r.attempts} ${r.ms}ms${r.note ? `  (${r.note})` : ""}`), `\nRecommended: ${results[0]?.green ? results[0].model : "NONE PASSED — set FARM_MODEL manually or revise the plan"}`, ""].join("\n");
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

  if (canary) return runCanary(plan);

  const { model, apiBaseUrl, apiKey } = resolveConfig(plan);

  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });

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

    const ready = () =>
      [...pending].filter((id) => {
        const deps = byId.get(id)!.deps ?? [];
        if (deps.some((d) => escalated.has(d))) return false;
        return deps.every((d) => done.get(d)?.status === "green");
      });

    const tripped = () => {
      const settled = done.size;
      if (settled < ENV.abortMinTasks) return false;
      return escalated.size / settled > ENV.abortEscalationRate;
    };

    while (pending.size > 0 || running.size > 0) {
      if (tripped()) {
        aborted = true;
        break;
      }
      for (const id of ready()) {
        if (running.size >= ENV.concurrency) break;
        pending.delete(id);
        running.set(
          id,
          runTask(byId.get(id)!, model, apiBaseUrl, apiKey).then(
            (r) => ({ id, r }),
            (e) => ({ id, r: { id, status: "escalate" as const, attempts: 0, branch: `farm/${id}`, worktree: path.resolve(ENV.worktreeRoot, id), note: `crashed: ${e?.message ?? e}` } }),
          ),
        );
      }
      if (running.size === 0) break;
      const { id, r } = await Promise.race(running.values());
      running.delete(id);
      done.set(id, r);
      if (r.status === "escalate") escalated.add(id);
    }

    // anything still pending is blocked (dependency escalated, cycle-free by validate, or aborted)
    for (const id of pending) {
      const deps = byId.get(id)!.deps ?? [];
      const culprit = deps.find((d) => escalated.has(d));
      blocked.push({ id, reason: aborted ? "run aborted (circuit breaker)" : culprit ? `dependency ${culprit} escalated` : "not scheduled" });
    }
  } finally {
    await writeReport(plan, [...done.values()], blocked, aborted).catch((e) => console.error("report write failed:", e));
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

async function writeReport(plan: Plan, results: Result[], blocked: { id: string; reason: string }[], aborted: boolean) {
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
    JSON.stringify({ plan: plan.meta, aborted, tokens: { prompt: pTok, completion: cTok }, results, blocked, ts: new Date().toISOString() }, null, 2),
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

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
