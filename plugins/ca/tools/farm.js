#!/usr/bin/env node

// farm.ts
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
var ENV = {
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
  requestTimeoutMs: Number(process.env.FARM_REQUEST_TIMEOUT_MS ?? 12e4),
  // Transport-level retries (429 / 5xx) — distinct from model-quality retries.
  apiMaxRetries: Number(process.env.FARM_API_MAX_RETRIES ?? 3),
  // Circuit breaker: abort dispatch once the escalation rate exceeds this,
  // after at least abortMinTasks have settled.
  abortEscalationRate: Number(process.env.FARM_ABORT_ESCALATION_RATE ?? 0.5),
  abortMinTasks: Number(process.env.FARM_ABORT_MIN_TASKS ?? 3),
  // Default endpoint, used only when neither env nor plan.meta provides one.
  defaultApiBaseUrl: process.env.FARM_DEFAULT_API_BASE_URL ?? "https://api.opencode.ai/v1",
  // Comma-separated candidate model ids for --canary mode.
  candidateModels: (process.env.FARM_CANDIDATE_MODELS ?? "").split(",").map((s) => s.trim()).filter(Boolean)
};
var MUT = {
  enabled: (process.env.FARM_MUTATION ?? "on").toLowerCase() !== "off",
  sample: Number(process.env.FARM_MUTATION_SAMPLE ?? 15),
  budgetMs: Number(process.env.FARM_MUTATION_BUDGET_MS ?? 3e4),
  warnBelow: Number(process.env.FARM_MUTATION_WARN_BELOW ?? 0.5),
  escalateBelow: Number(process.env.FARM_MUTATION_ESCALATE_BELOW ?? 0.1),
  cmd: process.env.FARM_MUTATION_CMD ?? null
};
function run(cmd, args, cwd, opts = {}) {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, { cwd, env: process.env, ...opts });
    let out = "";
    c.stdout.on("data", (d) => out += d);
    c.stderr.on("data", (d) => out += d);
    c.on("error", (e) => resolve({ code: 1, out: String(e) }));
    c.on("close", (code) => resolve({ code: code ?? 1, out }));
  });
}
var git = (args, cwd) => run("git", args, cwd);
var sleep = (ms) => new Promise((r) => setTimeout(r, ms));
var NOSIGN = ["-c", "commit.gpgsign=false"];
function isInside(root, target) {
  const rel = path.relative(root, target);
  return rel === "" || !rel.startsWith("..") && !path.isAbsolute(rel);
}
var [SHELL_BIN, SHELL_FLAG] = process.platform === "win32" ? ["cmd.exe", "/c"] : ["bash", "-c"];
var SHELL_OPTS = process.platform === "win32" ? { windowsVerbatimArguments: true } : {};
async function runGate(cwd, commands) {
  for (const cmd of commands) {
    const r = await run(SHELL_BIN, [SHELL_FLAG, cmd], cwd, SHELL_OPTS);
    if (r.code !== 0)
      return { ok: false, failed: cmd, tail: r.out.slice(-3500) };
  }
  return { ok: true };
}
function buildPrompt(t, priorFailure, forbiddenExtra) {
  return [
    `Implement exactly ONE task. Your only goal: make the failing test pass.`,
    ``,
    `TASK: ${t.description}`,
    t.context ? `
CONTEXT:
${t.context}
` : ``,
    `The failing test is at: ${t.test.path}`,
    `Make it pass WITHOUT modifying, deleting, or weakening that test.`,
    `You may NOT create, edit, or delete ${t.test.path} \u2014 it is read-only.`,
    ``,
    `You may ONLY create or edit these files:`,
    ...t.filesInScope.map((f) => `  - ${f}`),
    `Touch nothing else. Do not run git. Do not install global packages.`,
    forbiddenExtra && forbiddenExtra.length ? `
Your previous attempt wrote these FORBIDDEN paths \u2014 do NOT touch them again:
${forbiddenExtra.map((f) => `  - ${f}`).join("\n")}` : ``,
    ``,
    `Solve the task with REAL logic. Do not hard-code the literal values the`,
    `test asserts \u2014 an implementation that only returns the expected constant`,
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
    priorFailure ? `
Your previous attempt FAILED the gate. Fix it.
Gate output (tail):
${priorFailure}` : ``
  ].join("\n");
}
function extractFileBlocks(content) {
  const lines = content.split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const open = lines[i].match(/^\s*```(.*)$/);
    if (!open) {
      i++;
      continue;
    }
    const info = open[1].trim();
    const body = [];
    i++;
    while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
      body.push(lines[i]);
      i++;
    }
    i++;
    let filePath = null;
    const infoPath = info.match(/^[a-z0-9]*:(.+)$/i);
    if (infoPath && /[\/.]/.test(infoPath[1])) {
      filePath = infoPath[1].trim();
    } else if (body.length) {
      const first = body[0].trim();
      const m = first.match(/^(?:\/\/|#)\s*path:\s*(.+)$/i) || first.match(/^\/\*\s*path:\s*(.+?)\s*\*\/$/i);
      if (m) {
        filePath = m[1].trim();
        body.shift();
      }
    }
    if (filePath) blocks.push({ path: filePath, body: body.join("\n") });
  }
  return blocks;
}
async function callApi(prompt, model, apiBaseUrl, apiKey) {
  for (let attempt = 0; attempt <= ENV.apiMaxRetries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ENV.requestTimeoutMs);
    let resp;
    try {
      resp = await fetch(`${apiBaseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model,
          messages: [{ role: "user", content: prompt }]
        }),
        signal: ctrl.signal
      });
    } catch (e) {
      clearTimeout(timer);
      const aborted = e?.name === "AbortError";
      if (attempt < ENV.apiMaxRetries) {
        await sleep(Math.min(2 ** attempt * 1e3, 16e3));
        continue;
      }
      return { ok: false, error: aborted ? `request timed out after ${ENV.requestTimeoutMs}ms` : `fetch failed: ${e}` };
    }
    clearTimeout(timer);
    if (resp.status === 429 || resp.status >= 500) {
      if (attempt < ENV.apiMaxRetries) {
        const ra = Number(resp.headers.get("retry-after"));
        const wait = Number.isFinite(ra) && ra > 0 ? ra * 1e3 : Math.min(2 ** attempt * 1e3, 16e3);
        await sleep(wait);
        continue;
      }
      const body = await resp.text().catch(() => "(unreadable)");
      process.stderr.write(`API ${resp.status} body: ${body.slice(0, 300)}
`);
      return { ok: false, error: `API ${resp.status} after ${ENV.apiMaxRetries} retries` };
    }
    if (!resp.ok) {
      const body = await resp.text().catch(() => "(unreadable)");
      process.stderr.write(`API ${resp.status} body: ${body.slice(0, 500)}
`);
      return { ok: false, error: `API ${resp.status}` };
    }
    let data;
    try {
      data = await resp.json();
    } catch (e) {
      return { ok: false, error: `non-JSON response: ${e}` };
    }
    return { ok: true, content: data.choices?.[0]?.message?.content ?? "", usage: data.usage };
  }
  return { ok: false, error: "exhausted API retries" };
}
async function runWorker(cwd, prompt, model, apiBaseUrl, apiKey, forbidden) {
  const api = await callApi(prompt, model, apiBaseUrl, apiKey);
  if (!api.ok) return { ok: false, filesWritten: [], error: api.error };
  const blocks = extractFileBlocks(api.content);
  const filesWritten = [];
  for (const { path: filePath, body } of blocks) {
    const cleanPath = filePath.trim();
    const absPath = path.resolve(cwd, cleanPath);
    if (!isInside(cwd, absPath)) {
      return { ok: false, filesWritten, error: `path escapes worktree: ${cleanPath}` };
    }
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
      completionTokens: api.usage?.completion_tokens
    };
  }
  return {
    ok: true,
    filesWritten,
    promptTokens: api.usage?.prompt_tokens,
    completionTokens: api.usage?.completion_tokens
  };
}
async function checkDrift(cwd, allowed) {
  const tracked = await git(["diff", "--name-only", "HEAD"], cwd);
  const untracked = await git(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd
  );
  const changed = [];
  if (tracked.code === 0)
    changed.push(...tracked.out.trim().split("\n").filter(Boolean));
  if (untracked.code === 0)
    changed.push(...untracked.out.split("\0").filter(Boolean));
  return [...new Set(changed)].filter((f) => !allowed.has(f));
}
function extractLiterals(testSrc) {
  const lits = /* @__PURE__ */ new Set();
  for (const m of testSrc.matchAll(/(['"`])((?:\\.|(?!\1).){2,})\1/g)) lits.add(m[2]);
  for (const m of testSrc.matchAll(/\b(\d{2,}|[2-9])\b/g)) lits.add(m[1]);
  return [...lits];
}
function codeLineCount(src) {
  return src.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("//") && !l.startsWith("#") && !l.startsWith("*") && !l.startsWith("/*")).length;
}
async function antiGamingCheck(cwd, task) {
  let testSrc = "";
  try {
    testSrc = await readFile(path.resolve(cwd, task.test.path), "utf8");
  } catch {
    return { risk: "none" };
  }
  const literals = extractLiterals(testSrc).filter((l) => l.length > 1 || /\d{2,}/.test(l));
  if (literals.length === 0) return { risk: "none" };
  const hits = [];
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
async function fileHash(p) {
  try {
    const buf = await readFile(p);
    return createHash("sha256").update(buf).digest("hex");
  } catch {
    return null;
  }
}
async function resetWorktree(wt) {
  await git(["reset", "--hard", "HEAD"], wt);
  await git(["clean", "-fd"], wt);
}
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
function generateMutants(file, src) {
  const lines = src.split("\n");
  const rules = [
    [/ >= /, " > ", ">=>"],
    [/ <= /, " < ", "<=<"],
    [/ === /, " !== ", "===>!=="],
    [/ !== /, " === ", "!==>==="],
    [/ == /, " != ", "==>!="],
    [/ != /, " == ", "!=>=="],
    [/ > /, " >= ", ">>="],
    [/ < /, " <= ", "<<="],
    [/ \+ /, " - ", "+>-"],
    [/ - /, " + ", "->+"],
    [/ \* /, " / ", "*>/"],
    [/ && /, " || ", "&&>||"],
    [/ \|\| /, " && ", "||>&&"],
    [/\btrue\b/, "false", "true>false"],
    [/\bfalse\b/, "true", "false>true"]
  ];
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const t = ln.trim();
    if (!t || t.startsWith("//") || t.startsWith("#") || t.startsWith("*") || t.startsWith("/*")) continue;
    for (const [re, rep, name] of rules) {
      if (re.test(ln)) {
        const mline = ln.replace(re, rep);
        if (mline !== ln) {
          const m = [...lines];
          m[i] = mline;
          out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} ${name}` });
        }
      }
    }
    const rm2 = ln.match(/\breturn\s+(.+?);/);
    if (rm2 && rm2[1].trim() !== "null" && rm2[1].trim() !== "") {
      const m = [...lines];
      m[i] = ln.replace(/\breturn\s+.+?;/, "return null;");
      out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} return>null` });
    }
  }
  return out;
}
async function mutationCheck(wt, task) {
  if (!MUT.enabled) return null;
  const testCmd = task.gate.commands[0];
  if (!testCmd) return null;
  const impl = task.filesInScope.filter((f) => f !== task.test.path);
  if (MUT.cmd) {
    const r = await new Promise((resolve) => {
      const c = spawn(SHELL_BIN, [SHELL_FLAG, MUT.cmd], {
        cwd: wt,
        env: { ...process.env, FARM_MUTATION_FILES: impl.join(","), FARM_MUTATION_TEST_PATH: task.test.path, FARM_MUTATION_TEST_CMD: testCmd },
        ...SHELL_OPTS
      });
      let out = "";
      c.stdout.on("data", (d) => out += d);
      c.stderr.on("data", (d) => out += d);
      c.on("error", (e) => resolve({ code: 1, out: String(e) }));
      c.on("close", (code) => resolve({ code: code ?? 1, out }));
    });
    const j = [...r.out.matchAll(/\{[^\n]*"score"[^\n]*\}/g)].pop();
    if (!j) return null;
    try {
      const parsed = JSON.parse(j[0]);
      if (typeof parsed.score === "number")
        return { score: parsed.score, evaluated: parsed.total ?? parsed.evaluated ?? 99, survivors: parsed.survived ?? [] };
    } catch {
    }
    return null;
  }
  const originals = /* @__PURE__ */ new Map();
  let candidates = [];
  for (const f of impl) {
    let src;
    try {
      src = await readFile(path.resolve(wt, f), "utf8");
    } catch {
      continue;
    }
    if (codeLineCount(src) <= 2) continue;
    originals.set(f, src);
    candidates.push(...generateMutants(f, src));
  }
  if (candidates.length === 0) return null;
  candidates = shuffle(candidates).slice(0, MUT.sample);
  const start = Date.now();
  let killed = 0;
  let evaluated = 0;
  const survivors = [];
  try {
    for (const c of candidates) {
      if (Date.now() - start > MUT.budgetMs) break;
      await writeFile(path.resolve(wt, c.file), c.mutated);
      const r = await run(SHELL_BIN, [SHELL_FLAG, testCmd], wt, SHELL_OPTS);
      await writeFile(path.resolve(wt, c.file), originals.get(c.file));
      evaluated++;
      if (r.code !== 0) killed++;
      else survivors.push(c.tag);
    }
  } finally {
    for (const [f, src] of originals) await writeFile(path.resolve(wt, f), src).catch(() => {
    });
  }
  if (evaluated < 3) return null;
  return { score: killed / evaluated, evaluated, survivors };
}
var mergeChain = Promise.resolve();
var integrationWorktree;
function withMergeLock(fn) {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {
  });
  return next;
}
async function prepareWorktree(branch, wt, from) {
  await git(["worktree", "remove", "--force", wt]).catch(() => {
  });
  await rm(wt, { recursive: true, force: true }).catch(() => {
  });
  await git(["branch", "-D", branch]).catch(() => {
  });
  const add = await git(["worktree", "add", "-b", branch, wt, from]);
  if (add.code !== 0) return `worktree add failed: ${add.out.slice(0, 200)}`;
  return null;
}
async function runTask(t, model, apiBaseUrl, apiKey) {
  const branch = `farm/${t.id}`;
  const wt = path.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;
  const allowed = new Set(t.filesInScope);
  const forbidden = /* @__PURE__ */ new Set([t.test.path]);
  const prepErr = await prepareWorktree(branch, wt, ENV.integration);
  if (prepErr)
    return { id: t.id, status: "escalate", attempts: 0, branch, worktree: wt, note: prepErr };
  const testHashBefore = await fileHash(path.resolve(wt, t.test.path));
  let priorFailure;
  let driftedOnce = false;
  let lastFilesWritten = [];
  let promptTokens = 0;
  let completionTokens = 0;
  let lastWarning;
  let mutationScore = null;
  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    if (attempt > 1) await resetWorktree(wt);
    const worker = await runWorker(
      wt,
      buildPrompt(t, priorFailure, driftedOnce ? lastFilesWritten.filter((f) => !allowed.has(f)) : void 0),
      model,
      apiBaseUrl,
      apiKey,
      forbidden
    );
    promptTokens += worker.promptTokens ?? 0;
    completionTokens += worker.completionTokens ?? 0;
    lastFilesWritten = worker.filesWritten;
    if (!worker.ok) {
      priorFailure = `worker error: ${worker.error}`;
      continue;
    }
    const testHashAfter = await fileHash(path.resolve(wt, t.test.path));
    if (testHashBefore !== null && testHashAfter !== testHashBefore) {
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `tampered test: ${t.test.path}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    }
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
      priorFailure = `failed: ${gate.failed}
${gate.tail}`;
      continue;
    }
    const gaming = await antiGamingCheck(wt, t);
    let risk = gaming.risk;
    let riskNote = gaming.note;
    if (risk !== "high") {
      const mut = await mutationCheck(wt, t);
      if (mut) {
        mutationScore = mut.score;
        if (mut.score <= MUT.escalateBelow && mut.evaluated >= 5) {
          risk = "high";
          riskNote = `gaming: mutation score ${mut.score.toFixed(2)} (${mut.evaluated} mutants survived \u2014 the test does not constrain the implementation)`;
        } else if (mut.score < MUT.warnBelow) {
          if (risk !== "warn") {
            risk = "warn";
            riskNote = `mutation-risk: score ${mut.score.toFixed(2)} (${mut.survivors.length}/${mut.evaluated} survived) \u2014 weak test or under-implemented logic`;
          }
        }
      }
    }
    if (risk === "high") {
      priorFailure = `${riskNote}. Implement real logic; do not hard-code or special-case the asserted value.`;
      if (attempt <= limit) continue;
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: riskNote, filesWritten: worker.filesWritten, promptTokens, completionTokens, mutationScore };
    }
    if (risk === "warn") lastWarning = riskNote;
    await git(["add", "--", ...worker.filesWritten], wt);
    const commit = await git([...NOSIGN, "commit", "-m", `farm(${t.id}): ${t.description}`], wt);
    if (commit.code !== 0)
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `commit failed: ${commit.out.slice(0, 200)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    const diffstat = (await git(["diff", "--stat", `${ENV.base}...${branch}`], wt)).out.trim();
    const merged = await withMergeLock(async () => {
      const m = await git([...NOSIGN, "merge", "--no-ff", "-m", `merge ${t.id}`, branch], integrationWorktree);
      if (m.code !== 0) {
        await git(["merge", "--abort"], integrationWorktree).catch(() => {
        });
        return m.out;
      }
      return null;
    });
    if (merged !== null)
      return { id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `merge failed vs integration: ${String(merged).slice(0, 160)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens };
    await git(["worktree", "remove", "--force", wt]).catch(() => {
    });
    return { id: t.id, status: "green", attempts: attempt, branch, worktree: wt, warning: lastWarning, filesWritten: worker.filesWritten, diffstat, promptTokens, completionTokens, mutationScore };
  }
  return { id: t.id, status: "escalate", attempts: limit + 1, branch, worktree: wt, note: priorFailure?.split("\n")[0], filesWritten: lastFilesWritten, promptTokens, completionTokens, mutationScore };
}
var SAFE_TASK_ID = /^[A-Za-z0-9._-]{1,64}$/;
function validate(plan) {
  if (plan.meta.apiBaseUrl && !plan.meta.apiBaseUrl.startsWith("https://") && !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?/.test(plan.meta.apiBaseUrl))
    throw new Error(`plan meta.apiBaseUrl must use HTTPS, got: ${plan.meta.apiBaseUrl}`);
  const ids = /* @__PURE__ */ new Set();
  for (const t of plan.tasks) {
    if (!SAFE_TASK_ID.test(t.id))
      throw new Error(`task id "${t.id}" must match [A-Za-z0-9._-], max 64 chars`);
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);
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
  }
  for (const t of plan.tasks)
    for (const d of t.deps ?? [])
      if (!ids.has(d)) throw new Error(`task ${t.id} depends on unknown task ${d}`);
  const byId = new Map(plan.tasks.map((t) => [t.id, t]));
  const state = /* @__PURE__ */ new Map();
  const visit = (id, stack) => {
    if (state.get(id) === 2) return;
    if (state.get(id) === 1)
      throw new Error(`dependency cycle: ${[...stack, id].join(" -> ")}`);
    state.set(id, 1);
    for (const d of byId.get(id).deps ?? []) visit(d, [...stack, id]);
    state.set(id, 2);
  };
  for (const t of plan.tasks) visit(t.id, []);
}
function resolveConfig(plan) {
  const model = ENV.model ?? plan.meta.model;
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl ?? ENV.defaultApiBaseUrl;
  const apiKey = ENV.apiKey;
  if (!model) {
    console.error(
      "Error: No model configured.\nSet FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\nSee .codearbiter/farm.md for setup instructions."
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.\nSee .codearbiter/farm.md for setup instructions.");
    process.exit(1);
  }
  return { model, apiBaseUrl, apiKey };
}
async function runCanary(plan) {
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
  await git(["branch", "-f", ENV.integration, ENV.base]);
  integrationWorktree = path.resolve(ENV.reportDir, "integration-wt");
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  await rm(integrationWorktree, { recursive: true, force: true }).catch(() => {
  });
  await git(["worktree", "add", integrationWorktree, ENV.integration]).catch(() => {
  });
  const task = [...plan.tasks].filter((t) => (t.deps ?? []).length === 0).sort((a, b) => a.filesInScope.length - b.filesInScope.length)[0] ?? plan.tasks[0];
  const results = [];
  for (const model of ENV.candidateModels) {
    const t0 = Date.now();
    const r = await runTask({ ...task, id: `canary-${task.id}` }, model, apiBaseUrl, apiKey);
    results.push({ model, green: r.status === "green", attempts: r.attempts, ms: Date.now() - t0, note: r.note });
    await git(["worktree", "remove", "--force", path.resolve(ENV.worktreeRoot, `canary-${task.id}`)]).catch(() => {
    });
    await git(["branch", "-D", `farm/canary-${task.id}`]).catch(() => {
    });
  }
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  results.sort((a, b) => Number(b.green) - Number(a.green) || a.attempts - b.attempts || a.ms - b.ms);
  await writeFile(path.join(ENV.reportDir, "canary-report.json"), JSON.stringify({ task: task.id, results, ts: (/* @__PURE__ */ new Date()).toISOString() }, null, 2));
  const summary = ["\nCanary results (best first):", ...results.map((r) => `  ${r.green ? "PASS" : "FAIL"}  ${r.model}  attempts=${r.attempts} ${r.ms}ms${r.note ? `  (${r.note})` : ""}`), `
Recommended: ${results[0]?.green ? results[0].model : "NONE PASSED \u2014 set FARM_MODEL manually or revise the plan"}`, ""].join("\n");
  await new Promise((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(results[0]?.green ? 0 : 2);
}
async function main() {
  const args = process.argv.slice(2);
  const canary = args.includes("--canary");
  const planPath = args.find((a) => !a.startsWith("--")) ?? "plan.json";
  const plan = JSON.parse(await readFile(planPath, "utf8"));
  validate(plan);
  if (canary) return runCanary(plan);
  const { model, apiBaseUrl, apiKey } = resolveConfig(plan);
  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });
  const done = /* @__PURE__ */ new Map();
  const blocked = [];
  let aborted = false;
  try {
    const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
    if (branchResult.code !== 0)
      throw new Error(`could not create integration branch '${ENV.integration}' from '${ENV.base}': ${branchResult.out}`);
    integrationWorktree = path.resolve(ENV.reportDir, "integration-wt");
    await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
    });
    await rm(integrationWorktree, { recursive: true, force: true }).catch(() => {
    });
    const wtResult = await git(["worktree", "add", integrationWorktree, ENV.integration]);
    if (wtResult.code !== 0)
      throw new Error(`could not create integration worktree: ${wtResult.out}`);
    const byId = new Map(plan.tasks.map((t) => [t.id, t]));
    const escalated = /* @__PURE__ */ new Set();
    const pending = new Set(plan.tasks.map((t) => t.id));
    const running = /* @__PURE__ */ new Map();
    const ready = () => [...pending].filter((id) => {
      const deps = byId.get(id).deps ?? [];
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
      for (const id2 of ready()) {
        if (running.size >= ENV.concurrency) break;
        pending.delete(id2);
        running.set(
          id2,
          runTask(byId.get(id2), model, apiBaseUrl, apiKey).then(
            (r2) => ({ id: id2, r: r2 }),
            (e) => ({ id: id2, r: { id: id2, status: "escalate", attempts: 0, branch: `farm/${id2}`, worktree: path.resolve(ENV.worktreeRoot, id2), note: `crashed: ${e?.message ?? e}` } })
          )
        );
      }
      if (running.size === 0) break;
      const { id, r } = await Promise.race(running.values());
      running.delete(id);
      done.set(id, r);
      if (r.status === "escalate") escalated.add(id);
    }
    for (const id of pending) {
      const deps = byId.get(id).deps ?? [];
      const culprit = deps.find((d) => escalated.has(d));
      blocked.push({ id, reason: aborted ? "run aborted (circuit breaker)" : culprit ? `dependency ${culprit} escalated` : "not scheduled" });
    }
  } finally {
    await writeReport(plan, [...done.values()], blocked, aborted).catch((e) => console.error("report write failed:", e));
    await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
    });
  }
  const results = [...done.values()];
  const esc = results.filter((r) => r.status === "escalate").length;
  const green = results.filter((r) => r.status === "green").length;
  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  const exitCode = esc || blocked.length || aborted ? 2 : 0;
  const summary = [
    aborted ? `
ABORTED by circuit breaker \u2014 escalation rate exceeded ${ENV.abortEscalationRate}. The model may not be capable of this plan; consider the premium path or a different FARM_MODEL.` : ``,
    `
Done. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Report: ${path.join(ENV.reportDir, "farm-report.md")}`,
    ""
  ].join("\n");
  await new Promise((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(exitCode);
}
async function writeReport(plan, results, blocked, aborted) {
  await mkdir(path.join(ENV.reportDir, "diffs"), { recursive: true }).catch(() => {
  });
  for (const r of results) {
    const d = await git(["diff", `${ENV.base}...${r.branch}`]);
    if (d.code === 0 && d.out.trim())
      await writeFile(path.join(ENV.reportDir, "diffs", `${r.id}.patch`), d.out).catch(() => {
      });
  }
  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  await writeFile(
    path.join(ENV.reportDir, "farm-report.json"),
    JSON.stringify({ plan: plan.meta, aborted, tokens: { prompt: pTok, completion: cTok }, results, blocked, ts: (/* @__PURE__ */ new Date()).toISOString() }, null, 2)
  );
  const md = [
    `# Farm report \u2014 ${plan.meta.name}`,
    ``,
    aborted ? `> **ABORTED by circuit breaker** \u2014 escalation rate exceeded threshold.
` : ``,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    ``,
    `| task | status | attempts | files | mut | branch | note |`,
    `| --- | --- | --- | --- | --- | --- | --- |`,
    ...results.map((r) => `| ${r.id} | ${r.status}${r.warning ? " \u26A0" : ""} | ${r.attempts} | ${(r.filesWritten ?? []).length} | ${r.mutationScore == null ? "\u2014" : r.mutationScore.toFixed(2)} | ${r.branch} | ${r.note ?? r.warning ?? ""} |`),
    ...blocked.map((b) => `| ${b.id} | blocked | 0 | 0 | \u2014 | \u2014 | ${b.reason} |`),
    ``,
    `## Escalations \u2014 handle only these`,
    ...results.filter((r) => r.status === "escalate").map((r) => `- **${r.id}** \u2014 worktree \`${r.worktree}\`, branch \`${r.branch}\`. ${r.note ?? ""}`),
    ``,
    `## Warnings \u2014 review during spec-compliance`,
    ...results.filter((r) => r.warning).map((r) => `- **${r.id}** \u2014 ${r.warning} (diff: \`${path.join(ENV.reportDir, "diffs", r.id + ".patch")}\`)`)
  ].join("\n");
  await writeFile(path.join(ENV.reportDir, "farm-report.md"), md);
}
var _thisFile = fileURLToPath(import.meta.url);
var _entryFile = path.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
export {
  SAFE_TASK_ID,
  codeLineCount,
  extractFileBlocks,
  extractLiterals,
  validate
};
