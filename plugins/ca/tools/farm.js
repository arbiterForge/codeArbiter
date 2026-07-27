#!/usr/bin/env node

// farm.ts
import { readFile as readFile2, writeFile, appendFile, mkdir as mkdir2, rm, stat, rename, open as open2 } from "node:fs/promises";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import path3 from "node:path";
import { fileURLToPath } from "node:url";

// exec.ts
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
var EXIT_TIMEOUT = 124;
var EXIT_TIMEOUT_UNCLEAN = 125;
var [SHELL_BIN, SHELL_FLAG] = process.platform === "win32" ? ["cmd.exe", "/c"] : ["bash", "-c"];
var SHELL_OPTS = process.platform === "win32" ? { windowsVerbatimArguments: true } : {};
function numEnv(name, def, opts = {}) {
  const raw = process.env[name];
  if (raw === void 0 || raw === "") return def;
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    process.stderr.write(
      `[FARM] ${name}=${JSON.stringify(raw)} is not a finite number \u2014 falling back to the default ${def}
`
    );
    return def;
  }
  if (opts.min !== void 0 && n < opts.min) {
    process.stderr.write(`[FARM] ${name}=${n} is below the minimum ${opts.min} \u2014 clamping to ${opts.min}
`);
    return opts.min;
  }
  return n;
}
var GATE_TIMEOUT_MS = numEnv("FARM_GATE_TIMEOUT_MS", 3e5, { min: 1e3 });
var KILL_VERIFY_DEFAULT_MS = 1e4;
function taskkillPath() {
  const root = process.env.SystemRoot ?? process.env.windir ?? "C:\\Windows";
  return path.join(root, "System32", "taskkill.exe");
}
function pidPresent(target) {
  try {
    process.kill(target, 0);
    return true;
  } catch (e) {
    return e.code === "EPERM";
  }
}
async function waitUntilGone(probe, deadline) {
  for (; ; ) {
    if (!probe()) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((r) => setTimeout(r, 25));
  }
}
function awaitTaskkill(pid, budgetMs) {
  return new Promise((resolve) => {
    let settled = false;
    let timer;
    const done = (r) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(r);
    };
    let tk;
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
      }
      done({ ok: false, detail: `taskkill did not exit within ${budgetMs}ms` });
    }, Math.max(1e3, budgetMs));
    tk.on("error", (e) => done({ ok: false, detail: `taskkill failed to start: ${e.message}` }));
    tk.on(
      "close",
      (code) => done(code === 0 || code === 128 ? { ok: true } : { ok: false, detail: `taskkill exited ${code}` })
    );
  });
}
async function treeKill(child, opts = {}) {
  const pid = child.pid;
  if (pid === void 0) return { ok: true, detail: "child never started" };
  const budget = opts.budgetMs ?? numEnv("FARM_KILL_VERIFY_MS", KILL_VERIFY_DEFAULT_MS, { min: 0 });
  const deadline = Date.now() + budget;
  if (process.platform === "win32") {
    const tk = await awaitTaskkill(pid, budget);
    if (!tk.ok) {
      try {
        child.kill("SIGKILL");
      } catch {
      }
    }
    if (await waitUntilGone(() => pidPresent(pid), deadline)) return { ok: true };
    return {
      ok: false,
      detail: `pid ${pid} and/or its descendants were still present ${budget}ms after taskkill /T /F${tk.detail ? ` (${tk.detail})` : ""}`
    };
  }
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
  }
  try {
    child.kill("SIGKILL");
  } catch {
  }
  if (await waitUntilGone(() => pidPresent(pid) || pidPresent(-pid), deadline)) return { ok: true };
  return {
    ok: false,
    detail: `process group ${pid} still had a live member ${budget}ms after SIGKILL \u2014 descendants may still be running`
  };
}
function scrubbedEnv(extra) {
  const env = { ...process.env, ...extra ?? {} };
  delete env.FARM_API_KEY;
  delete env.CLAUDE_CODE_OAUTH_TOKEN;
  return env;
}
function run(cmd, args, cwd, opts = {}, timeoutMs = 0, kill = treeKill) {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, {
      cwd,
      env: scrubbedEnv(),
      ...opts,
      // #395: off Windows the child leads its OWN process group, so a timeout
      // kill can address the whole tree (`kill(-pid)`) instead of just the
      // shell that fronts the operator's command. NOT on Windows, where
      // `detached` means "new console" and breaks the `cmd.exe /c` contract.
      detached: process.platform !== "win32"
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    let killing = false;
    let timer;
    const done = (r) => {
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
          const base = `
[FARM] command exceeded ${timeoutMs}ms wall-clock timeout \u2014 killed (FARM_GATE_TIMEOUT_MS)`;
          const note = k.ok ? base : `${base}
[FARM] CLEANUP UNVERIFIED \u2014 the child process tree could not be confirmed gone: ${k.detail ?? "no detail"}. Descendants may still be running against this worktree.`;
          done({
            code: k.ok ? EXIT_TIMEOUT : EXIT_TIMEOUT_UNCLEAN,
            out: stdout + stderr + note,
            stdout,
            stderr: stderr + note,
            timedOut: true,
            ...k.ok ? {} : { cleanupFailed: true }
          });
        })();
      }, timeoutMs);
    }
    c.stdout.on("data", (d) => stdout += d);
    c.stderr.on("data", (d) => stderr += d);
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
async function readWorktreeFile(wt, relPath) {
  try {
    return await readFile(path.resolve(wt, relPath), "utf8");
  } catch {
    return null;
  }
}

// redactor.ts
var SECRET_LINE = new RegExp(
  [
    "api[_-]?key",
    "token",
    "secret",
    "password",
    "BEGIN.*PRIVATE",
    "sk-ant",
    "sk-proj-[A-Za-z0-9_-]{8}",
    "AKIA[0-9A-Z]{16}",
    "ghp_[A-Za-z0-9]{36}",
    "glpat-[A-Za-z0-9_-]{8}",
    // basic auth in a URL: scheme://user:secret@host - the colon-and-at shape,
    // not any "@", so `https://example.com/@scope/pkg` is untouched.
    // NOTE the doubled backslashes: these are JS STRING literals, and "\\s" in
    // a string is a literal "s". The first cut of this shipped `[^/\s:@]`,
    // which silently became `[^/s:@]` and only matched by luck.
    "https?://[^/\\s:@]+:[^/\\s@]+@",
    // a bearer credential, which is dot-segmented base64url in practice
    "Bearer\\s+[A-Za-z0-9_-]{10,}"
    // DELIBERATELY NOT ADDED: a `-u user:pass` rule for curl. `-u 1000:1000`
    // is an everyday docker/podman uid:gid pair, so the shape collides with
    // benign input. Broad is the safe direction for this redactor, but not at
    // the cost of firing on ordinary container arguments.
  ].join("|"),
  "i"
);
var PEM_BEGIN = /^-----BEGIN .*-----\s*$/;
var PEM_END = /^-----END .*-----\s*$/;
var REDACTION_MARKER = "[REDACTED \u2014 secret-pattern match removed before transmission]";
var SECRET_FILENAME_DENYLIST = [
  /^\.env$/i,
  // .env
  /^\.env\..+$/i,
  // .env.local, .env.production, ...
  /\.pem$/i,
  // *.pem
  /\.key$/i,
  // *.key
  /^id_rsa(\..+)?$/i,
  // id_rsa, id_rsa.pub, id_rsa.bak
  /^id_ed25519(\..+)?$/i,
  // id_ed25519, id_ed25519.pub
  /^id_ecdsa(\..+)?$/i,
  // id_ecdsa, id_ecdsa.pub
  /\.p12$/i,
  // PKCS#12 keystore
  /\.pfx$/i
  // PKCS#12 keystore (Windows)
];
function isSecretBearingFilename(relPath) {
  const base = relPath.split(/[\\/]/).pop() ?? relPath;
  return SECRET_FILENAME_DENYLIST.some((re) => re.test(base));
}
function redactSecrets(contents) {
  const lines = contents.split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (PEM_BEGIN.test(line.trim())) {
      out.push(REDACTION_MARKER);
      i++;
      while (i < lines.length && !PEM_END.test(lines[i].trim())) i++;
      continue;
    }
    out.push(SECRET_LINE.test(line) ? REDACTION_MARKER : line);
  }
  return out.join("\n");
}

// mutation.ts
import { spawn as spawn2 } from "node:child_process";

// worktree-fs.ts
import { constants } from "node:fs";
import { lstat, mkdir, open, realpath } from "node:fs/promises";
import path2 from "node:path";
var UNSAFE_MESSAGE = "unsafe worktree path rejected";
var UnsafeWorktreePathError = class extends Error {
  constructor() {
    super(UNSAFE_MESSAGE);
    this.name = "UnsafeWorktreePathError";
  }
};
function isUnsafeWorktreePathError(error) {
  return error instanceof UnsafeWorktreePathError;
}
function unsafe() {
  throw new UnsafeWorktreePathError();
}
function isMissing(error) {
  return error?.code === "ENOENT";
}
function contained(root, candidate) {
  const relative = path2.relative(root, candidate);
  return relative === "" || !relative.startsWith(`..${path2.sep}`) && relative !== ".." && !path2.isAbsolute(relative);
}
function sameFile(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}
function safeRegularFile(metadata) {
  return metadata.isFile() && !metadata.isSymbolicLink() && metadata.nlink === 1;
}
async function writeWorktreeFile(worktree, relPath, contents, testHooks = {}) {
  let handle;
  try {
    const rootMetadata = await lstat(worktree);
    if (!rootMetadata.isDirectory() || rootMetadata.isSymbolicLink()) unsafe();
    const canonicalRoot = await realpath(worktree);
    const verifiedDirectories = [
      { path: canonicalRoot, metadata: await lstat(canonicalRoot) }
    ];
    const verifyDirectories = async () => {
      for (const verified of verifiedDirectories) {
        const current = await lstat(verified.path);
        if (!current.isDirectory() || current.isSymbolicLink() || !sameFile(current, verified.metadata)) unsafe();
        if (!contained(canonicalRoot, await realpath(verified.path))) unsafe();
      }
    };
    const target = path2.resolve(canonicalRoot, relPath);
    const relative = path2.relative(canonicalRoot, target);
    if (relative === "" || relative === ".." || relative.startsWith(`..${path2.sep}`) || path2.isAbsolute(relative)) unsafe();
    const segments = relative.split(path2.sep);
    let parent = canonicalRoot;
    for (const segment of segments.slice(0, -1)) {
      if (segment === "" || segment === "." || segment === "..") unsafe();
      const candidate = path2.join(parent, segment);
      let metadata;
      try {
        metadata = await lstat(candidate);
      } catch (error) {
        if (!isMissing(error)) throw error;
        try {
          await mkdir(candidate, { mode: 448 });
        } catch (mkdirError) {
          if (mkdirError?.code !== "EEXIST") throw mkdirError;
        }
        metadata = await lstat(candidate);
      }
      if (!metadata.isDirectory() || metadata.isSymbolicLink()) unsafe();
      const canonicalCandidate = await realpath(candidate);
      if (!contained(canonicalRoot, canonicalCandidate)) unsafe();
      verifiedDirectories.push({ path: candidate, metadata });
      parent = candidate;
    }
    await verifyDirectories();
    const canonicalParent = await realpath(parent);
    if (!contained(canonicalRoot, canonicalParent)) unsafe();
    let before;
    try {
      before = await lstat(target);
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
    if (before !== void 0 && !safeRegularFile(before)) unsafe();
    if (before !== void 0 && !contained(canonicalRoot, await realpath(target))) unsafe();
    const noFollow = typeof constants.O_NOFOLLOW === "number" ? constants.O_NOFOLLOW : 0;
    const flags = before === void 0 ? constants.O_RDWR | constants.O_CREAT | constants.O_EXCL | noFollow : constants.O_RDWR | noFollow;
    handle = await open(target, flags, 384);
    const opened = await handle.stat();
    const atPath = await lstat(target);
    if (!safeRegularFile(opened) || !safeRegularFile(atPath) || !sameFile(opened, atPath)) unsafe();
    await verifyDirectories();
    if (!contained(canonicalRoot, await realpath(parent))) unsafe();
    if (!contained(canonicalRoot, await realpath(target))) unsafe();
    await testHooks.beforeFinalAuthorization?.();
    await verifyDirectories();
    if (!contained(canonicalRoot, await realpath(parent))) unsafe();
    if (!contained(canonicalRoot, await realpath(target))) unsafe();
    const finalAtPath = await lstat(target);
    const finalOpened = await handle.stat();
    if (!safeRegularFile(finalOpened) || !safeRegularFile(finalAtPath) || !sameFile(finalOpened, finalAtPath)) unsafe();
    await handle.truncate(0);
    await handle.writeFile(contents, { encoding: "utf8" });
  } catch (error) {
    if (isUnsafeWorktreePathError(error)) throw error;
    throw new UnsafeWorktreePathError();
  } finally {
    await handle?.close().catch(() => void 0);
  }
}

// mutation.ts
var MUT = {
  enabled: (process.env.FARM_MUTATION ?? "on").toLowerCase() !== "off",
  // reliability-014: routed through the shared numEnv reader (exec.ts) so a
  // typo'd FARM_MUTATION_* value falls back to the default loudly instead of
  // silently becoming NaN (every comparison against MUT.warnBelow/escalateBelow
  // would then read false, disabling the anti-gaming mutation signal).
  sample: numEnv("FARM_MUTATION_SAMPLE", 15, { min: 1 }),
  budgetMs: numEnv("FARM_MUTATION_BUDGET_MS", 3e4, { min: 0 }),
  warnBelow: numEnv("FARM_MUTATION_WARN_BELOW", 0.5, { min: 0 }),
  escalateBelow: numEnv("FARM_MUTATION_ESCALATE_BELOW", 0.1, { min: 0 }),
  cmd: process.env.FARM_MUTATION_CMD ?? null
};
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
  const testSrc = await readWorktreeFile(cwd, task.test.path);
  if (testSrc === null) return { risk: "none" };
  const literals = extractLiterals(testSrc).filter((l) => l.length > 1 || /\d{2,}/.test(l));
  if (literals.length === 0) return { risk: "none" };
  const hits = [];
  let anyTiny = false;
  for (const f of task.filesInScope) {
    if (f === task.test.path) continue;
    const src = await readWorktreeFile(cwd, f);
    if (src === null) continue;
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
function parseMutationHookOutput(out) {
  const j = [...out.matchAll(/\{[^\n]*"score"[^\n]*\}/g)].pop();
  if (!j) return null;
  try {
    const parsed = JSON.parse(j[0]);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    if (typeof parsed.score === "number") {
      const survivors = Array.isArray(parsed.survived) ? parsed.survived.filter((s) => typeof s === "string") : [];
      const declared = parsed.total ?? parsed.evaluated;
      const evaluated = Number.isInteger(declared) && declared > 0 ? declared : 99;
      return { score: parsed.score, evaluated, survivors };
    }
  } catch {
  }
  return null;
}
async function mutationCheck(wt, task) {
  if (!MUT.enabled) return null;
  const testCmd = task.gate.commands[0];
  if (!testCmd) return null;
  const impl = task.filesInScope.filter((f) => f !== task.test.path);
  if (MUT.cmd) {
    const r = await new Promise((resolve) => {
      const c = spawn2(SHELL_BIN, [SHELL_FLAG, MUT.cmd], {
        cwd: wt,
        env: scrubbedEnv({ FARM_MUTATION_FILES: impl.join(","), FARM_MUTATION_TEST_PATH: task.test.path, FARM_MUTATION_TEST_CMD: testCmd }),
        ...SHELL_OPTS,
        // #395: process-group isolation, matching run(). The operator-authored
        // mutation hook is a grandchild behind `bash -c` / `cmd.exe /c`, so the
        // timeout kill must be able to address the group, not just the shell.
        detached: process.platform !== "win32"
      });
      let out = "";
      let settled = false;
      let killing = false;
      const finish = (res) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(res);
      };
      const timer = setTimeout(() => {
        killing = true;
        void treeKill(c).then((k) => {
          const note = k.ok ? "\n[FARM] FARM_MUTATION_CMD exceeded the wall-clock timeout \u2014 killed" : `
[FARM] FARM_MUTATION_CMD exceeded the wall-clock timeout \u2014 killed, but CLEANUP UNVERIFIED: ${k.detail ?? "no detail"}`;
          finish({ code: k.ok ? EXIT_TIMEOUT : EXIT_TIMEOUT_UNCLEAN, out: out + note });
        });
      }, GATE_TIMEOUT_MS);
      c.stdout.on("data", (d) => out += d);
      c.stderr.on("data", (d) => out += d);
      c.on("error", (e) => {
        if (killing) return;
        finish({ code: 1, out: String(e) });
      });
      c.on("close", (code) => {
        if (killing) return;
        finish({ code: code ?? 1, out });
      });
    });
    const parsed = parseMutationHookOutput(r.out);
    if (parsed !== null) return parsed;
    const tail = redactSecrets(r.out.slice(-500)).trim();
    return { failed: true, detail: `exit ${r.code}${tail ? `: ${tail}` : " (no output)"}` };
  }
  const originals = /* @__PURE__ */ new Map();
  let candidates = [];
  for (const f of impl) {
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
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
      await writeWorktreeFile(wt, c.file, c.mutated);
      const r = await run(SHELL_BIN, [SHELL_FLAG, testCmd], wt, SHELL_OPTS, GATE_TIMEOUT_MS);
      const orig = originals.get(c.file);
      if (orig !== void 0) await writeWorktreeFile(wt, c.file, orig);
      evaluated++;
      if (r.code !== 0) killed++;
      else survivors.push(c.tag);
    }
  } finally {
    for (const [f, src] of originals) {
      try {
        await writeWorktreeFile(wt, f, src);
      } catch (error) {
        if (isUnsafeWorktreePathError(error)) throw error;
      }
    }
  }
  if (evaluated < 3) return null;
  return { score: killed / evaluated, evaluated, survivors };
}

// farm.ts
var DEFAULT_API_BASE_URL = "https://opencode.ai/zen/v1";
var ENV = {
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
  requestTimeoutMs: numEnv("FARM_REQUEST_TIMEOUT_MS", 12e4, { min: 1 }),
  // Per-candidate wall-clock cap for the #93 entitlement pre-screen, so one
  // slow/dead model can't dominate the probe. Kept short (35s) — a screen, not a
  // capability run — and ≤ the per-request timeout.
  entitlementProbeTimeoutMs: numEnv("FARM_ENTITLEMENT_PROBE_TIMEOUT_MS", 35e3, { min: 1 }),
  // Transport-level retries (429 / 5xx) — distinct from model-quality retries.
  apiMaxRetries: numEnv("FARM_API_MAX_RETRIES", 3, { min: 0 }),
  // Circuit breaker: abort dispatch once the escalation rate exceeds this,
  // after at least abortMinTasks have settled.
  abortEscalationRate: numEnv("FARM_ABORT_ESCALATION_RATE", 0.5, { min: 0 }),
  abortMinTasks: numEnv("FARM_ABORT_MIN_TASKS", 3, { min: 1 }),
  // Default endpoint, used only when neither env nor plan.meta provides one.
  defaultApiBaseUrl: process.env.FARM_DEFAULT_API_BASE_URL ?? DEFAULT_API_BASE_URL,
  // Comma-separated candidate model ids for --canary mode.
  candidateModels: (process.env.FARM_CANDIDATE_MODELS ?? "").split(",").map((s) => s.trim()).filter(Boolean),
  // AC-05 byte cap on the TOTAL injected enrichment context (test source +
  // in-scope file bodies) that leaves the trust boundary to the third-party
  // endpoint. Default 131072 (128 KiB): more repo content now flows outbound,
  // so the prompt must never be unbounded. 128 KiB is ~32K tokens of context —
  // generous enough for the real test + a handful of in-scope files, yet small
  // enough to stay well inside the FARM_REQUEST_TIMEOUT_MS (120s) single-request
  // budget and to bound per-task token spend. Truncation past the cap is
  // deterministic (in-order) with a visible marker; we never silently drop the
  // boundedness guarantee.
  enrichMaxBytes: numEnv("FARM_ENRICH_MAX_BYTES", 131072, { min: 1 })
};
var git = (args, cwd) => run("git", args, cwd);
var sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function createLimiter(max) {
  const cap = Math.max(1, Math.floor(max) || 1);
  let active = 0;
  const queue = [];
  const pump = () => {
    if (active < cap && queue.length) {
      active++;
      queue.shift()();
    }
  };
  const acquire = () => new Promise((resolve) => {
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
    active: () => active
  };
}
var workerLimit = createLimiter(ENV.concurrency);
var NOSIGN = ["-c", "commit.gpgsign=false"];
function isInside(root, target) {
  const rel = path3.relative(root, target);
  return rel === "" || !rel.startsWith("..") && !path3.isAbsolute(rel);
}
function repoTopLevel() {
  try {
    const out = spawnSync("git", ["rev-parse", "--show-toplevel"], {
      encoding: "utf8",
      timeout: 5e3
    });
    const top = (out.stdout || "").trim();
    if (out.status === 0 && top) return path3.resolve(top);
  } catch {
  }
  return path3.resolve(process.cwd());
}
function validateWorktreeRoot(rawRoot, repo, external) {
  const root = path3.resolve(rawRoot);
  if (!external && !isInside(path3.resolve(repo), root))
    throw new Error(
      `FARM_WORKTREE_ROOT resolves to '${root}', outside the repository root '${path3.resolve(repo)}'. farm recursively deletes task worktrees under this root, so an out-of-repo root is refused (#163). Point it inside the repo, or set FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1 to override.`
    );
  return root;
}
var _allowedWorktreeRoot = null;
function allowedWorktreeRoot() {
  if (_allowedWorktreeRoot) return _allowedWorktreeRoot;
  _allowedWorktreeRoot = validateWorktreeRoot(
    ENV.worktreeRoot,
    repoTopLevel(),
    process.env.FARM_ALLOW_EXTERNAL_WORKTREE_ROOT === "1"
  );
  return _allowedWorktreeRoot;
}
function _resetAllowedWorktreeRoot() {
  _allowedWorktreeRoot = null;
}
function assertContainedWorktree(wt) {
  const root = allowedWorktreeRoot();
  const abs = path3.resolve(wt);
  if (abs === root || !isInside(root, abs))
    throw new Error(
      `refusing to operate on worktree path '${abs}': it must be strictly inside the allowed farm worktree root '${root}' (#163).`
    );
  return abs;
}
async function runGate(cwd, commands) {
  for (const cmd of commands) {
    const r = await run(SHELL_BIN, [SHELL_FLAG, cmd], cwd, SHELL_OPTS, GATE_TIMEOUT_MS);
    if (r.code !== 0)
      return { ok: false, failed: cmd, tail: redactSecrets(r.out.slice(-3500)) };
  }
  return { ok: true };
}
function renderInjectedFile(file) {
  const label = file.prior ? `${file.path} (your previous attempt \u2014 FAILED)` : file.readOnly ? `${file.path} (read-only \u2014 the failing test)` : file.path;
  return [`--- ${label} ---`, redactSecrets(file.contents)].join("\n");
}
var TRUNCATION_MARKER = "--- [TRUNCATED \u2014 injected context exceeded FARM_ENRICH_MAX_BYTES] ---";
function capInjected(injected, maxBytes) {
  const out = [];
  let used = 0;
  for (const file of injected) {
    const renderedBytes = Buffer.byteLength(renderInjectedFile(file), "utf8");
    if (used + renderedBytes <= maxBytes) {
      out.push(file);
      used += renderedBytes;
      continue;
    }
    const contentBytes = Buffer.byteLength(redactSecrets(file.contents), "utf8");
    const overhead = renderedBytes - contentBytes;
    const remaining = maxBytes - used - overhead - Buffer.byteLength("\n" + TRUNCATION_MARKER, "utf8");
    if (remaining > 0) {
      const safe = Buffer.from(redactSecrets(file.contents), "utf8").subarray(0, remaining).toString("utf8");
      out.push({ ...file, contents: safe + "\n" + TRUNCATION_MARKER });
    } else {
      out.push({ ...file, contents: TRUNCATION_MARKER });
    }
    break;
  }
  return out;
}
async function buildEnrichment(wt, t, priorInScope = []) {
  const injected = [];
  const seen = /* @__PURE__ */ new Set();
  if (!isSecretBearingFilename(t.test.path)) {
    const testSrc = await readWorktreeFile(wt, t.test.path);
    if (testSrc !== null) {
      injected.push({ path: t.test.path, contents: testSrc, readOnly: true });
      seen.add(t.test.path);
    }
  } else {
    seen.add(t.test.path);
  }
  for (const f of t.filesInScope) {
    if (seen.has(f)) continue;
    if (isSecretBearingFilename(f)) {
      seen.add(f);
      continue;
    }
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
    injected.push({ path: f, contents: src, readOnly: false });
    seen.add(f);
  }
  for (const pf of priorInScope) {
    if (isSecretBearingFilename(pf.path)) continue;
    injected.push({ path: pf.path, contents: pf.contents, readOnly: true, prior: true });
  }
  return capInjected(injected, ENV.enrichMaxBytes);
}
async function captureInScope(wt, t) {
  const out = [];
  for (const f of t.filesInScope) {
    if (f === t.test.path) continue;
    if (isSecretBearingFilename(f)) continue;
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
    out.push({ path: f, contents: src });
  }
  return out;
}
function buildPrompt(t, injected, priorFailure, forbiddenExtra) {
  const current = injected.filter((f) => !f.prior);
  const priorFiles = injected.filter((f) => f.prior);
  const enrichment = current.length ? [
    ``,
    `Current source of the relevant files (the test is read-only; implement against it):`,
    ``,
    ...current.map(renderInjectedFile),
    ``
  ] : [];
  const priorBlock = priorFiles.length ? [
    ``,
    `Your PREVIOUS attempt FAILED the gate. Here is what you wrote last time \u2014 do NOT just repeat it; change it to fix the cause shown at the end:`,
    ``,
    ...priorFiles.map(renderInjectedFile),
    ``
  ] : [];
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
    ...enrichment,
    ...priorBlock,
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
    const open3 = lines[i].match(/^\s*```(.*)$/);
    if (!open3) {
      i++;
      continue;
    }
    const info = open3[1].trim();
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
function diagnosticApiOrigin(apiBaseUrl) {
  try {
    return new URL(apiBaseUrl).origin;
  } catch {
    return "<configured endpoint>";
  }
}
function parseChatCompletion(text, apiBaseUrl) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return {
      ok: false,
      error: `endpoint ${diagnosticApiOrigin(apiBaseUrl)} returned a non-JSON body \u2014 check FARM_API_BASE_URL and that the endpoint path is correct (expected an OpenAI-compatible /chat/completions)`
    };
  }
  if (!data || typeof data !== "object" || !Array.isArray(data.choices)) {
    return {
      ok: false,
      error: `endpoint ${diagnosticApiOrigin(apiBaseUrl)} returned an unexpected shape (no 'choices' array) \u2014 check FARM_API_BASE_URL and that the endpoint is an OpenAI-compatible /chat/completions`
    };
  }
  return { ok: true, content: data.choices?.[0]?.message?.content ?? "", usage: data.usage };
}
function readSampling() {
  return {
    temperature: numEnv("FARM_TEMPERATURE", 0),
    maxTokens: numEnv("FARM_MAX_TOKENS", 0, { min: 0 })
  };
}
function buildChatBody(model, messages, sampling = readSampling()) {
  const body = { model, messages, temperature: sampling.temperature };
  if (sampling.maxTokens > 0) body.max_tokens = sampling.maxTokens;
  return body;
}
async function callApi(prompt, model, apiBaseUrl, apiKey, sampling = readSampling()) {
  try {
    assertSecureBaseUrl(apiBaseUrl);
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "apiBaseUrl must use HTTPS" };
  }
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
        body: JSON.stringify(buildChatBody(model, [{ role: "user", content: prompt }], sampling)),
        signal: ctrl.signal,
        // A validated HTTPS URL is not permission to follow a 307/308 onto an
        // unvalidated cleartext endpoint with the same POST body.
        redirect: "error"
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
    try {
      if (resp.status === 429 || resp.status >= 500) {
        if (attempt < ENV.apiMaxRetries) {
          const ra = Number(resp.headers.get("retry-after"));
          const wait = Number.isFinite(ra) && ra > 0 ? ra * 1e3 : Math.min(2 ** attempt * 1e3, 16e3);
          await sleep(wait);
          continue;
        }
        await resp.text();
        return { ok: false, error: `API ${resp.status} after ${ENV.apiMaxRetries} retries` };
      }
      if (!resp.ok) {
        await resp.text();
        return { ok: false, error: `API ${resp.status}` };
      }
      const text = await resp.text();
      return parseChatCompletion(text, apiBaseUrl);
    } catch (e) {
      const aborted = e?.name === "AbortError";
      return {
        ok: false,
        error: aborted ? `request timed out after ${ENV.requestTimeoutMs}ms (reading response body)` : `failed reading response body: ${e}`
      };
    } finally {
      clearTimeout(timer);
    }
  }
  return { ok: false, error: "exhausted API retries" };
}
async function runWorker(cwd, prompt, model, apiBaseUrl, apiKey, forbidden, sampling) {
  const api = await callApi(prompt, model, apiBaseUrl, apiKey, sampling ?? readSampling());
  if (!api.ok) return { ok: false, filesWritten: [], error: api.error };
  const blocks = extractFileBlocks(api.content);
  const filesWritten = [];
  for (const { path: filePath, body } of blocks) {
    const cleanPath = filePath.trim();
    const absPath = path3.resolve(cwd, cleanPath);
    if (!isInside(cwd, absPath)) {
      return { ok: false, filesWritten, error: `path escapes worktree: ${cleanPath}` };
    }
    const rel = path3.relative(cwd, absPath).split(path3.sep).join("/");
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
var httpWorker = {
  apply: (ctx) => runWorker(ctx.cwd, ctx.prompt, ctx.model, ctx.apiBaseUrl, ctx.apiKey, ctx.forbidden, ctx.sampling)
};
async function checkDrift(cwd, allowed, gitRunner = git) {
  const tracked = await gitRunner(["diff", "--name-only", "HEAD"], cwd);
  const untracked = await gitRunner(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd
  );
  const changed = [];
  if (tracked.code === 0)
    changed.push(...tracked.stdout.trim().split("\n").filter(Boolean));
  if (untracked.code === 0)
    changed.push(...untracked.stdout.split("\0").filter(Boolean));
  return [...new Set(changed)].filter((f) => !allowed.has(f));
}
function postApplySweep(cwd, filesWritten, forbidden) {
  for (const f of filesWritten) {
    const absPath = path3.resolve(cwd, f);
    if (!isInside(cwd, absPath)) {
      return `path escapes worktree: ${f}`;
    }
    const rel = path3.relative(cwd, absPath).split(path3.sep).join("/");
    if (forbidden.has(rel)) {
      return `worker wrote read-only path: ${rel}`;
    }
  }
  return null;
}
async function fileHash(p) {
  try {
    const buf = await readFile2(p);
    return createHash("sha256").update(buf).digest("hex");
  } catch {
    return null;
  }
}
async function resetWorktree(wt) {
  await git(["reset", "--hard", "HEAD"], wt);
  await git(["clean", "-fd"], wt);
}
async function setupFingerprint(wt, t, deps) {
  const parts = [JSON.stringify(t.setup ?? [])];
  for (const rel of t.setupInputs ?? [])
    parts.push(`${rel}=${await deps.fileHash(path3.resolve(wt, rel)) ?? "absent"}`);
  return createHash("sha256").update(parts.join("\0")).digest("hex");
}
async function runSetupPhases(wt, t, deps, state) {
  if (t.setup && t.setup.length > 0) {
    const key = await setupFingerprint(wt, t, deps);
    if (key !== state.key) {
      const r = await deps.runGate(wt, t.setup);
      if (!r.ok) return redactSecrets(`setup failed: ${r.failed}
${r.tail}`);
      state.key = key;
    }
  }
  if (t.setupEachAttempt && t.setupEachAttempt.length > 0) {
    const r = await deps.runGate(wt, t.setupEachAttempt);
    if (!r.ok) return redactSecrets(`setup failed (setupEachAttempt): ${r.failed}
${r.tail}`);
  }
  return null;
}
function mintRunId() {
  return randomBytes(8).toString("hex");
}
var msgOf = (e) => e instanceof Error ? e.message : String(e);
var SAFE_RUN_ID = /^[A-Za-z0-9._-]{1,64}$/;
var RESERVED_RUN_ID_STEM = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
function assertSafeRunId(id) {
  if (!SAFE_RUN_ID.test(id) || id === "." || id === "..")
    throw new Error(
      `FARM_RUN_ID must be 1-64 characters of [A-Za-z0-9._-] and not "." or ".." (got ${JSON.stringify(id)})`
    );
  if (RESERVED_RUN_ID_STEM.test(id.split(".")[0]))
    throw new Error(
      `FARM_RUN_ID must not be a Windows reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9), with or without an extension \u2014 the run directory could not be created (got ${JSON.stringify(id)})`
    );
  return id;
}
function runArtifactDir(runId) {
  return path3.join(ENV.reportDir, "runs", runId);
}
async function renameWithRetry(from, to, attempts = 4) {
  for (let i = 0; ; i++) {
    try {
      await rename(from, to);
      return;
    } catch (e) {
      const code = e.code ?? "";
      if (i >= attempts - 1 || !["EPERM", "EACCES", "EBUSY"].includes(code)) throw e;
      await new Promise((r) => setTimeout(r, 15 * (i + 1)));
    }
  }
}
async function atomicWriteFile(dest, data, deps = {}) {
  const tmp = path3.join(
    path3.dirname(dest),
    `.${path3.basename(dest)}.${process.pid}-${randomBytes(4).toString("hex")}.tmp`
  );
  const priorMode = await stat(dest).then((s) => s.mode & 511).catch(() => void 0);
  const fh = await (deps.open ?? open2)(tmp, "wx");
  try {
    await fh.writeFile(data, "utf8");
    await fh.sync();
    if (priorMode !== void 0) await fh.chmod(priorMode);
  } catch (e) {
    await fh.close().catch(() => {
    });
    await rm(tmp, { force: true }).catch(() => {
    });
    throw e;
  }
  await fh.close();
  try {
    await renameWithRetry(tmp, dest);
  } catch (e) {
    await rm(tmp, { force: true }).catch(() => {
    });
    throw e;
  }
}
function newRunArtifactHealth() {
  return {
    stream: { errors: [] },
    diffs: { unavailable: [], unavailableTotal: 0, latestMirrorErrors: [] },
    report: { latestMirrorErrors: [] },
    cleanup: { failures: [] }
  };
}
function projectPlanMetaForReport(meta) {
  const scrub = (v) => typeof v === "string" ? redactSecrets(v) : Array.isArray(v) ? v.map(scrub) : v;
  return Object.fromEntries(Object.entries(meta).map(([k, v]) => [k, scrub(v)]));
}
var MAX_RECORDED_ARTIFACT_ERRORS = 10;
function noteArtifactError(bucket, message) {
  const safe = redactSecrets(message);
  if (bucket.length < MAX_RECORDED_ARTIFACT_ERRORS) bucket.push(safe);
  else if (bucket.length === MAX_RECORDED_ARTIFACT_ERRORS) bucket.push("(further errors suppressed)");
}
function noteUnavailableDiff(diffs, id, reason) {
  const safe = redactSecrets(reason);
  diffs.unavailableTotal += 1;
  if (diffs.unavailable.length < MAX_RECORDED_ARTIFACT_ERRORS) diffs.unavailable.push({ id, reason: safe });
  else if (diffs.unavailable.length === MAX_RECORDED_ARTIFACT_ERRORS)
    diffs.unavailable.push({
      id: "(suppressed)",
      reason: `further entries suppressed after ${MAX_RECORDED_ARTIFACT_ERRORS}`
    });
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
  try {
    assertContainedWorktree(wt);
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
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
var CLEANUP_ATTEMPTS = 3;
var CLEANUP_DELAY_MS = 150;
function samePath(a, b) {
  const norm = (p) => {
    const r = path3.resolve(p);
    return process.platform === "win32" ? r.toLowerCase() : r;
  };
  return norm(a) === norm(b);
}
async function stillRegistered(gitFn, wt) {
  const listed = await gitFn(["worktree", "list", "--porcelain"]);
  if (listed.code !== 0) return true;
  return listed.stdout.split("\n").filter((l) => l.startsWith("worktree ")).some((l) => samePath(l.slice("worktree ".length).trim(), wt));
}
async function pathExists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}
async function removeWorktreeVerified(gitFn, wt, opts = {}) {
  const attempts = opts.attempts ?? CLEANUP_ATTEMPTS;
  const delayMs = opts.delayMs ?? CLEANUP_DELAY_MS;
  let lastErr = "";
  for (let i = 1; i <= attempts; i++) {
    const rmR = await gitFn(["worktree", "remove", "--force", wt]);
    if (rmR.code !== 0) lastErr = rmR.out.trim().split("\n").slice(-1)[0] ?? "";
    let registered = await stillRegistered(gitFn, wt);
    const present = await pathExists(wt);
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
            lastErr ? `last git error: ${lastErr}` : null
          ].filter(Boolean).join("; ")
        ).slice(0, 500)
      };
  }
  return { ok: false, target: wt, attempts, detail: "cleanup loop did not settle" };
}
async function deleteBranchVerified(gitFn, branch, opts = {}) {
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
          `branch still present after ${i} attempt(s)${lastErr ? `; last git error: ${lastErr}` : ""}`
        ).slice(0, 500)
      };
  }
  return { ok: false, target: branch, attempts, detail: "cleanup loop did not settle" };
}
function runExitCode(o) {
  return o.escalated || o.blocked || o.aborted || o.cleanupFailures ? 2 : 0;
}
function cleanupFailures(health, results) {
  return [
    ...results.flatMap(
      (r) => (r.cleanup ?? []).filter((c) => !c.ok).map((c) => ({ owner: r.id, target: c.target, detail: c.detail ?? "unverified" }))
    ),
    ...health.cleanup.failures.map((f) => ({ owner: "run", target: f.target, detail: f.detail }))
  ];
}
function cleanupReportLines(health, results) {
  const failures = cleanupFailures(health, results);
  if (failures.length === 0)
    return [`## Resource cleanup`, `Every farm worktree and scratch branch was removed and re-verified.`];
  return [
    `## Resource cleanup`,
    `> **CLEANUP DEGRADED** \u2014 ${failures.length} resource(s) could not be released and re-verified. They may still be registered with git or present on disk, and the next run will collide with or destructively pre-clean them. Exit code is non-zero for this reason alone.`,
    ...failures.map((f) => `- \`${f.target}\` (${f.owner}) \u2014 ${f.detail}`)
  ];
}
function mutationSurvivalNote(m) {
  const derived = Math.round(m.evaluated * (1 - m.score));
  const survived = m.survivors.length > 0 ? m.survivors.length : derived;
  const bounded = Math.max(0, Math.min(m.evaluated, survived));
  return `score ${m.score.toFixed(2)} (${bounded}/${m.evaluated} survived)`;
}
var defaultRunTaskDeps = () => ({
  worker: httpWorker,
  prepareWorktree,
  resetWorktree,
  fileHash,
  checkDrift,
  runGate,
  antiGamingCheck,
  mutationCheck,
  git,
  withMergeLock
});
function effectiveSampling(samples) {
  const s = readSampling();
  const explicit = (process.env.FARM_TEMPERATURE ?? "") !== "";
  if (samples > 1 && s.temperature === 0 && !explicit) {
    process.stderr.write(
      `[FARM] FARM_SAMPLES=${samples} with no FARM_TEMPERATURE set \u2014 bumping temperature to 0.7 so samples diversify (set FARM_TEMPERATURE to override)
`
    );
    return { ...s, temperature: 0.7 };
  }
  return s;
}
async function writeFilesInto(wt, files) {
  for (const f of files) {
    const abs = path3.resolve(wt, f.path);
    if (!isInside(wt, abs)) throw new UnsafeWorktreePathError();
    await writeWorktreeFile(wt, f.path, f.contents.endsWith("\n") ? f.contents : f.contents + "\n");
  }
}
async function bestOfN(t, prompt, model, apiBaseUrl, apiKey, sampling, forbidden, allowed, n, deps) {
  const taskBranch = `farm/${t.id}`;
  const runSample = (k) => workerLimit.run(async () => {
    const branch = `farm/${t.id}__s${k}`;
    const wt = path3.resolve(ENV.worktreeRoot, `${t.id}__s${k}`);
    const base = {
      green: false,
      filesWritten: [],
      files: [],
      inScope: [],
      promptTokens: 0,
      completionTokens: 0,
      wt,
      branch
    };
    try {
      const prep = await deps.prepareWorktree(branch, wt, taskBranch);
      if (prep) return { ...base, note: prep };
      const setupNote = await runSetupPhases(wt, t, deps, { key: null });
      if (setupNote) return { ...base, note: setupNote };
      const testHashBefore = await deps.fileHash(path3.resolve(wt, t.test.path));
      const w = await deps.worker.apply({ cwd: wt, prompt, model, apiBaseUrl, apiKey, forbidden, sampling });
      const pt = w.promptTokens ?? 0;
      const ct = w.completionTokens ?? 0;
      if (!w.ok) return { ...base, note: redactSecrets(`worker error: ${w.error}`), promptTokens: pt, completionTokens: ct };
      const sweep = postApplySweep(wt, w.filesWritten, forbidden);
      if (sweep) return { ...base, filesWritten: w.filesWritten, note: sweep, promptTokens: pt, completionTokens: ct };
      const testHashAfter = await deps.fileHash(path3.resolve(wt, t.test.path));
      if (testHashBefore !== null && testHashAfter !== testHashBefore)
        return { ...base, filesWritten: w.filesWritten, note: `tampered test: ${t.test.path}`, promptTokens: pt, completionTokens: ct };
      const drift = await deps.checkDrift(wt, allowed);
      if (drift.length > 0)
        return { ...base, filesWritten: w.filesWritten, inScope: await captureInScope(wt, t), note: `drift: ${drift.join(", ")}`, promptTokens: pt, completionTokens: ct };
      const gate = await deps.runGate(wt, t.gate.commands);
      if (!gate.ok)
        return { ...base, filesWritten: w.filesWritten, inScope: await captureInScope(wt, t), note: redactSecrets(`failed: ${gate.failed}
${gate.tail}`), promptTokens: pt, completionTokens: ct };
      const inScope = await captureInScope(wt, t);
      return { green: true, filesWritten: w.filesWritten, files: inScope, inScope, promptTokens: pt, completionTokens: ct, wt, branch };
    } catch (e) {
      return { ...base, note: `sample error: ${e instanceof Error ? e.message : String(e)}` };
    }
  });
  const outcomes = await Promise.all(Array.from({ length: n }, (_, k) => runSample(k)));
  const promptTokens = outcomes.reduce((s, o) => s + o.promptTokens, 0);
  const completionTokens = outcomes.reduce((s, o) => s + o.completionTokens, 0);
  const winner = outcomes.find((o) => o.green) ?? null;
  const bestFailure = outcomes.find((o) => !o.green && o.inScope.length > 0) ?? outcomes.find((o) => !o.green) ?? null;
  const cleanup = [];
  for (const o of outcomes) {
    cleanup.push(await removeWorktreeVerified(deps.git, o.wt));
    cleanup.push(await deleteBranchVerified(deps.git, o.branch));
  }
  return { winner, bestFailure, promptTokens, completionTokens, cleanup };
}
async function runTask(t, model, apiBaseUrl, apiKey, deps = defaultRunTaskDeps()) {
  const branch = `farm/${t.id}`;
  const wt = path3.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;
  const effectiveModel = t.model ?? model;
  const allowed = new Set(t.filesInScope);
  const forbidden = /* @__PURE__ */ new Set([t.test.path]);
  const samples = Math.max(1, Math.floor(numEnv("FARM_SAMPLES", 1, { min: 1 })));
  const sampling = effectiveSampling(samples);
  const cleanupIssues = [];
  const noteCleanup = (...outcomes) => {
    for (const c of outcomes) if (!c.ok) cleanupIssues.push(c);
  };
  const finish = (r) => cleanupIssues.length ? { ...r, cleanup: [...cleanupIssues] } : r;
  const prepErr = await deps.prepareWorktree(branch, wt, ENV.integration);
  if (prepErr)
    return finish({ id: t.id, status: "escalate", attempts: 0, branch, worktree: wt, note: prepErr });
  const testHashBefore = await deps.fileHash(path3.resolve(wt, t.test.path));
  let priorFailure;
  let driftedOnce = false;
  let lastFilesWritten = [];
  let priorInScope = [];
  let acceptedPromptTokens = 0;
  let acceptedCompletionTokens = 0;
  let promptTokens = 0;
  let completionTokens = 0;
  let lastWarning;
  let mutationScore = null;
  const setupState = { key: null };
  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    if (attempt > 1) {
      if (samples <= 1) priorInScope = lastFilesWritten.length > 0 ? await captureInScope(wt, t) : [];
      await deps.resetWorktree(wt);
    }
    const setupNote = await runSetupPhases(wt, t, deps, setupState);
    if (setupNote)
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: setupNote, promptTokens, completionTokens });
    const injected = await buildEnrichment(wt, t, priorInScope);
    const forbiddenExtra = driftedOnce ? lastFilesWritten.filter((f) => !allowed.has(f)) : void 0;
    const prompt = buildPrompt(t, injected, priorFailure, forbiddenExtra);
    let worker;
    if (samples <= 1) {
      worker = await workerLimit.run(
        () => deps.worker.apply({ cwd: wt, prompt, model: effectiveModel, apiBaseUrl, apiKey, forbidden, sampling })
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
      const sel = await bestOfN(t, prompt, effectiveModel, apiBaseUrl, apiKey, sampling, forbidden, allowed, samples, deps);
      noteCleanup(...sel.cleanup);
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
    const sweepErr = postApplySweep(wt, worker.filesWritten, forbidden);
    if (sweepErr) {
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: sweepErr, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }
    const testHashAfter = await deps.fileHash(path3.resolve(wt, t.test.path));
    if (testHashBefore !== null && testHashAfter !== testHashBefore) {
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `tampered test: ${t.test.path}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }
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
      priorFailure = redactSecrets(`failed: ${gate.failed}
${gate.tail}`);
      continue;
    }
    const gaming = await deps.antiGamingCheck(wt, t);
    let risk = gaming.risk;
    let riskNote = gaming.note;
    if (risk !== "high") {
      let mut;
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
        if (mut.score <= MUT.escalateBelow && mut.evaluated >= 5) {
          risk = "high";
          riskNote = `gaming: mutation ${mutationSurvivalNote(mut)} \u2014 the test does not constrain the implementation`;
        } else if (mut.score < MUT.warnBelow) {
          if (risk !== "warn") {
            risk = "warn";
            riskNote = `mutation-risk: ${mutationSurvivalNote(mut)} \u2014 weak test or under-implemented logic`;
          }
        }
      } else if (mut && "failed" in mut) {
        process.stderr.write(`[FARM] mutation hook failed for task ${t.id}: ${mut.detail}
`);
        if (risk === "none") {
          risk = "warn";
          riskNote = `mutation-hook-failed: ${mut.detail}`;
        }
      }
    }
    if (risk === "high") {
      priorFailure = `${riskNote}. Implement real logic; do not hard-code or special-case the asserted value.`;
      if (attempt <= limit) continue;
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: riskNote, filesWritten: worker.filesWritten, promptTokens, completionTokens, mutationScore });
    }
    if (risk === "warn") lastWarning = riskNote;
    await deps.git(["add", "--", ...worker.filesWritten], wt);
    const commit = await deps.git([...NOSIGN, "commit", "-m", `farm(${t.id}): ${t.description}`], wt);
    if (commit.code !== 0)
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `commit failed: ${commit.out.slice(0, 200)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    const diffstat = (await deps.git(["diff", "--stat", `${ENV.base}...${branch}`], wt)).out.trim();
    const merged = await deps.withMergeLock(async () => {
      const m = await deps.git([...NOSIGN, "merge", "--no-ff", "-m", `merge ${t.id}`, branch], integrationWorktree);
      if (m.code !== 0) {
        await deps.git(["merge", "--abort"], integrationWorktree).catch(() => {
        });
        return m.out;
      }
      return null;
    });
    if (merged !== null) {
      if (attempt <= limit) {
        await deps.git(["reset", "--hard", ENV.integration], wt).catch(() => {
        });
        await deps.git(["clean", "-fd"], wt).catch(() => {
        });
        priorFailure = redactSecrets(`merge conflict vs integration: rebuild against the updated baseline (integration HEAD moved)
${String(merged).slice(0, 160)}`);
        continue;
      }
      return finish({ id: t.id, status: "escalate", attempts: attempt, branch, worktree: wt, note: `merge failed vs integration: ${String(merged).slice(0, 160)}`, filesWritten: worker.filesWritten, promptTokens, completionTokens });
    }
    noteCleanup(await removeWorktreeVerified(deps.git, wt));
    return finish({ id: t.id, status: "green", attempts: attempt, branch, worktree: wt, warning: lastWarning, filesWritten: worker.filesWritten, diffstat, promptTokens, completionTokens, mutationScore, samples, acceptedPromptTokens, acceptedCompletionTokens });
  }
  return finish({ id: t.id, status: "escalate", attempts: limit + 1, branch, worktree: wt, note: priorFailure?.split("\n")[0], filesWritten: lastFilesWritten, promptTokens, completionTokens, mutationScore });
}
var SAFE_TASK_ID = /^[A-Za-z0-9._-]{1,64}$/;
var LOOPBACK_HOSTS = /* @__PURE__ */ new Set(["127.0.0.1", "localhost"]);
function assertSecureBaseUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("apiBaseUrl must use HTTPS (HTTP is allowed only for bare loopback hosts)");
  }
  if (parsed.username !== "" || parsed.password !== "") {
    throw new Error("apiBaseUrl must use HTTPS without embedded credentials");
  }
  if (parsed.protocol === "https:") return;
  if (parsed.protocol === "http:" && LOOPBACK_HOSTS.has(parsed.hostname)) return;
  throw new Error("apiBaseUrl must use HTTPS (HTTP is allowed only for bare loopback hosts)");
}
var PLAN_SHAPE = {
  plan: {
    required: ["meta", "tasks"],
    props: { meta: "meta", tasks: "task[]" }
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
      setupInputs: "string[]"
    }
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
      setupInputs: "string[]"
    }
  },
  test: { required: ["path"], props: { path: "string" } },
  gate: { required: ["commands"], props: { commands: "string[]" } }
};
var PLAN_NON_EMPTY = /* @__PURE__ */ new Set(["plan.tasks", "task.filesInScope", "gate.commands"]);
var PLAN_INT_MIN = { "task.maxRetries": 0 };
var PLAN_LABEL_MAX = 40;
var clipLabel = (s) => s.length <= PLAN_LABEL_MAX ? s : `${s.slice(0, PLAN_LABEL_MAX)}\u2026`;
var jsonTypeName = (v) => v === null ? "null" : Array.isArray(v) ? "array" : typeof v;
var isJsonObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);
function checkPlanField(v, type, at, key) {
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
      checkPlanObject(v, type, at);
  }
}
function checkPlanObject(value, spec, at) {
  if (!isJsonObject(value)) throw new Error(`${at} must be a JSON object (got ${jsonTypeName(value)})`);
  const { required, props } = PLAN_SHAPE[spec];
  const declared = props;
  for (const key of Object.keys(value))
    if (!Object.hasOwn(declared, key)) throw new Error(`${at}: unknown property "${clipLabel(key)}"`);
  for (const key of required)
    if (value[key] === void 0) throw new Error(`${at}.${key} is required`);
  for (const [key, type] of Object.entries(declared)) {
    const v = value[key];
    if (v === void 0) continue;
    checkPlanField(v, type, `${at}.${key}`, `${spec}.${key}`);
  }
}
function parsePlan(raw) {
  checkPlanObject(raw, "plan", "plan");
  return raw;
}
function validate(plan) {
  if (plan.meta.apiBaseUrl) assertSecureBaseUrl(plan.meta.apiBaseUrl);
  const checkSetup = (label, cmds) => {
    for (const cmd of cmds) {
      if (!cmd || typeof cmd !== "string")
        throw new Error(`${label}: setup entries must be non-empty strings`);
      if (cmd.length > 1024) throw new Error(`${label}: setup command exceeds 1024 chars`);
    }
  };
  const checkSetupInputs = (label, inputs) => {
    for (const rel of inputs) {
      if (!rel || typeof rel !== "string")
        throw new Error(`${label}: setupInputs entries must be non-empty strings`);
      if (rel.includes("..") || path3.isAbsolute(rel))
        throw new Error(`${label}: setupInputs entry "${rel}" must be a relative path with no ".." segments`);
    }
  };
  if (plan.meta.setup) checkSetup("plan.meta.setup", plan.meta.setup);
  if (plan.meta.setupEachAttempt) checkSetup("plan.meta.setupEachAttempt", plan.meta.setupEachAttempt);
  if (plan.meta.setupInputs) checkSetupInputs("plan.meta", plan.meta.setupInputs);
  const ids = /* @__PURE__ */ new Set();
  for (const t of plan.tasks) {
    if (!SAFE_TASK_ID.test(t.id))
      throw new Error(`task id "${t.id}" must match [A-Za-z0-9._-], max 64 chars`);
    if (t.id === "." || t.id === "..")
      throw new Error(`task id "${t.id}" is reserved (resolves to the worktree root or its parent)`);
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);
    if (!t.test || typeof t.test.path !== "string")
      throw new Error(`task ${t.id}: test.path is required (string)`);
    if (!Array.isArray(t.filesInScope))
      throw new Error(`task ${t.id}: filesInScope is required (array of relative paths)`);
    if (!t.gate || !Array.isArray(t.gate.commands))
      throw new Error(`task ${t.id}: gate.commands is required (array of strings)`);
    if (t.test.path.includes("..") || path3.isAbsolute(t.test.path))
      throw new Error(`task ${t.id}: test.path must be a relative path with no ".." segments`);
    for (const f of t.filesInScope)
      if (f.includes("..") || path3.isAbsolute(f))
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
  assertSecureBaseUrl(apiBaseUrl);
  if (!model) {
    console.error(
      "Error: No model configured.\nSet FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\nSee ${CLAUDE_PLUGIN_ROOT}/includes/farm.md for setup instructions."
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.\nSee ${CLAUDE_PLUGIN_ROOT}/includes/farm.md for setup instructions.");
    process.exit(1);
  }
  return { model, apiBaseUrl, apiKey };
}
async function screenEntitlements(models, probe, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? ENV.entitlementProbeTimeoutMs;
  const sleepFn = opts.sleepFn ?? sleep;
  const survivors = [];
  const skipped = [];
  for (const model of models) {
    let res;
    try {
      res = await Promise.race([
        probe(model),
        sleepFn(timeoutMs).then(() => null)
      ]);
    } catch (e) {
      skipped.push({ model, reason: "error", note: `entitlement probe error: ${e}` });
      continue;
    }
    if (res === null) {
      skipped.push({ model, reason: "timeout", note: `entitlement probe exceeded ${timeoutMs}ms \u2014 model is slow or dead` });
      continue;
    }
    if (res.status === 401) {
      skipped.push({ model, reason: "entitlement", note: "401 \u2014 not entitled / free promotion ended" });
      continue;
    }
    survivors.push(model);
  }
  return { survivors, skipped };
}
function makeEntitlementProbe(apiBaseUrl, apiKey, timeoutMs) {
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
        redirect: "error"
      });
      return { status: resp.status };
    } catch {
      return { status: 0 };
    } finally {
      clearTimeout(timer);
    }
  };
}
async function runCanary(plan) {
  if (ENV.candidateModels.length === 0) {
    console.error("Error: --canary requires FARM_CANDIDATE_MODELS (comma-separated model ids).");
    process.exit(1);
  }
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl ?? ENV.defaultApiBaseUrl;
  const apiKey = ENV.apiKey;
  assertSecureBaseUrl(apiBaseUrl);
  if (!apiKey) {
    console.error("Error: FARM_API_KEY is not set.");
    process.exit(1);
  }
  await mkdir2(ENV.worktreeRoot, { recursive: true });
  await mkdir2(ENV.reportDir, { recursive: true });
  await git(["branch", "-f", ENV.integration, ENV.base]);
  integrationWorktree = path3.resolve(ENV.reportDir, "integration-wt");
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  await rm(integrationWorktree, { recursive: true, force: true }).catch(() => {
  });
  await git(["worktree", "add", integrationWorktree, ENV.integration]).catch(() => {
  });
  const task = [...plan.tasks].filter((t) => (t.deps ?? []).length === 0).sort((a, b) => a.filesInScope.length - b.filesInScope.length)[0] ?? plan.tasks[0];
  const { survivors, skipped } = await screenEntitlements(
    ENV.candidateModels,
    makeEntitlementProbe(apiBaseUrl, apiKey, ENV.entitlementProbeTimeoutMs)
  );
  if (skipped.length)
    process.stderr.write(`Entitlement screen dropped ${skipped.length}/${ENV.candidateModels.length}: ${skipped.map((s) => `${s.model} (${s.reason})`).join(", ")}
`);
  const results = [];
  for (const model of survivors) {
    const t0 = Date.now();
    const r = await runTask({ ...task, id: `canary-${task.id}` }, model, apiBaseUrl, apiKey);
    results.push({ model, green: r.status === "green", attempts: r.attempts, ms: Date.now() - t0, note: r.note });
    await git(["worktree", "remove", "--force", path3.resolve(ENV.worktreeRoot, `canary-${task.id}`)]).catch(() => {
    });
    await git(["branch", "-D", `farm/canary-${task.id}`]).catch(() => {
    });
  }
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  results.sort((a, b) => Number(b.green) - Number(a.green) || a.attempts - b.attempts || a.ms - b.ms);
  await writeFile(path3.join(ENV.reportDir, "canary-report.json"), JSON.stringify({ task: task.id, results, skipped, ts: (/* @__PURE__ */ new Date()).toISOString() }, null, 2));
  const summary = [
    "\nCanary results (best first):",
    ...results.map((r) => `  ${r.green ? "PASS" : "FAIL"}  ${r.model}  attempts=${r.attempts} ${r.ms}ms${r.note ? `  (${r.note})` : ""}`),
    ...skipped.map((s) => `  SKIP  ${s.model}  (${s.reason}: ${s.note})`),
    `
Recommended: ${results[0]?.green ? results[0].model : "NONE PASSED \u2014 set FARM_MODEL manually or revise the plan"}`,
    ""
  ].join("\n");
  await new Promise((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(results[0]?.green ? 0 : 2);
}
async function main() {
  const args = process.argv.slice(2);
  const canary = args.includes("--canary");
  const planPath = args.find((a) => !a.startsWith("--")) ?? "plan.json";
  let plan;
  try {
    plan = parsePlan(JSON.parse(await readFile2(planPath, "utf8")));
    validate(plan);
  } catch (e) {
    console.error(`Error: invalid plan ${planPath}: ${msgOf(e).slice(0, 300)}`);
    return process.exit(1);
  }
  for (const t of plan.tasks) {
    if (plan.meta.setup && t.setup === void 0) t.setup = plan.meta.setup;
    if (plan.meta.setupEachAttempt && t.setupEachAttempt === void 0)
      t.setupEachAttempt = plan.meta.setupEachAttempt;
    if (plan.meta.setupInputs && t.setupInputs === void 0) t.setupInputs = plan.meta.setupInputs;
  }
  if (canary) return runCanary(plan);
  const { model, apiBaseUrl, apiKey } = resolveConfig(plan);
  let runId;
  try {
    runId = ENV.runId === null ? mintRunId() : assertSafeRunId(ENV.runId);
  } catch (e) {
    console.error(`Error: ${msgOf(e)}`);
    return process.exit(1);
  }
  const runDir = runArtifactDir(runId);
  await mkdir2(ENV.worktreeRoot, { recursive: true });
  await mkdir2(ENV.reportDir, { recursive: true });
  await mkdir2(runDir, { recursive: true });
  const health = newRunArtifactHealth();
  const resultsStream = path3.join(runDir, "farm-results.jsonl");
  const latestStream = path3.join(ENV.reportDir, "farm-results.jsonl");
  const streamLines = [];
  const noteStreamFailure = (what, e) => {
    const m = `${what}: ${msgOf(e)}`;
    console.error(`results stream ${m}`);
    noteArtifactError(health.stream.errors, m);
  };
  await writeFile(resultsStream, "").catch((e) => noteStreamFailure("run-scoped init failed", e));
  await atomicWriteFile(latestStream, "").catch((e) => noteStreamFailure("latest pointer init failed", e));
  const done = /* @__PURE__ */ new Map();
  const blocked = [];
  let aborted = false;
  let publishError = null;
  try {
    const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
    if (branchResult.code !== 0)
      throw new Error(`could not create integration branch '${ENV.integration}' from '${ENV.base}': ${branchResult.out}`);
    integrationWorktree = path3.resolve(runDir, "integration-wt");
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
    const scopeOf = (id) => new Set(byId.get(id).filesInScope ?? []);
    const overlaps = (a, b) => {
      for (const f of b) if (a.has(f)) return true;
      return false;
    };
    const ready = () => [...pending].filter((id) => {
      const deps = byId.get(id).deps ?? [];
      if (deps.some((d) => escalated.has(d))) return false;
      if (!deps.every((d) => done.get(d)?.status === "green")) return false;
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
      if (!aborted && tripped()) aborted = true;
      if (!aborted) {
        for (const id2 of ready()) {
          if (running.size >= ENV.concurrency) break;
          pending.delete(id2);
          running.set(
            id2,
            runTask(byId.get(id2), model, apiBaseUrl, apiKey).then(
              (r2) => ({ id: id2, r: r2 }),
              // observability-003 (T-07c): a crash produces an escalate Result with
              // a correlated, stack-bearing note. The truncated err.stack gives the
              // post-mortem a call site (e.g. the spawn TypeError from
              // reliability-004) instead of a one-line message with no origin.
              (e) => ({
                id: id2,
                r: {
                  id: id2,
                  status: "escalate",
                  attempts: 0,
                  branch: `farm/${id2}`,
                  worktree: path3.resolve(ENV.worktreeRoot, id2),
                  note: `crashed: ${e?.message ?? e}${e?.stack ? `
${String(e.stack).slice(0, 1500)}` : ""}`
                }
              })
            )
          );
        }
      }
      if (running.size === 0) break;
      const { id, r } = await Promise.race(running.values());
      running.delete(id);
      r.runId = runId;
      if (aborted && r.status === "escalate" && !/run aborted/.test(r.note ?? "")) {
        r.note = r.note ? `${r.note} (run aborted by circuit breaker while in flight)` : "escalate: run aborted (in flight)";
      }
      done.set(id, r);
      const line = JSON.stringify(r) + "\n";
      streamLines.push(line);
      await appendFile(resultsStream, line).catch((e) => noteStreamFailure("run-scoped append failed", e));
      await atomicWriteFile(latestStream, streamLines.join("")).catch(
        (e) => noteStreamFailure("latest pointer publish failed", e)
      );
      if (r.status === "escalate") escalated.add(id);
    }
    for (const id of pending) {
      const deps = byId.get(id).deps ?? [];
      const culprit = deps.find((d) => escalated.has(d));
      blocked.push({ id, reason: aborted ? "run aborted (circuit breaker)" : culprit ? `dependency ${culprit} escalated` : "not scheduled" });
    }
  } finally {
    if (integrationWorktree) {
      try {
        const c = await removeWorktreeVerified(git, integrationWorktree);
        if (!c.ok) health.cleanup.failures.push({ target: c.target, detail: c.detail ?? "unverified" });
      } catch (e) {
        health.cleanup.failures.push({ target: integrationWorktree, detail: `teardown threw: ${msgOf(e)}` });
      }
    }
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
  const leaks = cleanupFailures(health, results);
  const runOutcome = runExitCode({ escalated: esc, blocked: blocked.length, aborted, cleanupFailures: leaks.length });
  const exitCode = publishError ? 3 : runOutcome;
  const latestReportErrors = health.report.latestMirrorErrors;
  const summary = [
    aborted ? `
ABORTED by circuit breaker \u2014 escalation rate exceeded ${ENV.abortEscalationRate}. The model may not be capable of this plan; consider the premium path or a different FARM_MODEL.` : ``,
    `
Done. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Worker tokens: prompt=${pTok} completion=${cTok}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Run: ${runId}  (artifacts: ${runDir})`,
    // #398: never let a leak be something the operator has to go looking for.
    leaks.length ? [
      `
CLEANUP DEGRADED \u2014 ${leaks.length} resource(s) could not be released and re-verified:`,
      ...leaks.map((l) => `  - ${l.target} (${l.owner}): ${l.detail}`),
      `Git may still register these worktrees, or the directories may still be on disk. The next run's`,
      `pre-cleanup is destructive and best-effort, so clear them before re-running. Exit is non-zero for this alone.`
    ].join("\n") : ``,
    // The success breadcrumb is SUPPRESSED when the authoritative publication
    // failed — pointing an operator at a farm-report.md that is not there is
    // the defect. Every claim below has to be true of what is actually on disk:
    // the message names the run directory and says "missing or incomplete"
    // rather than asserting no receipt exists, because a partial failure (e.g.
    // the JSON landed and the Markdown did not) leaves a real receipt behind.
    publishError ? [
      `
RECEIPT PUBLICATION FAILED \u2014 run ${runId} could not publish its complete authoritative report under ${runDir}: ${msgOf(publishError)}`,
      `The tasks themselves finished ${runOutcome === 0 ? "green" : "with escalations/blocks/unreleased worktrees"}, but this run's durable receipt is missing or incomplete,`,
      `so it cannot be reliably reconciled or audited. Inspect ${runDir} for whatever did land.`,
      `${path3.join(ENV.reportDir, "farm-report.json")} / .md were NOT refreshed and do not describe run ${runId}.`,
      `Exiting 3 (receipt failure) rather than ${runOutcome} (task outcome).`
    ].join("\n") : latestReportErrors.length ? (
      // Non-fatal, and stated as such. The authoritative receipt is
      // unaffected; what the operator must not assume is that the shared
      // path now describes THIS run.
      [
        `Report: ${path3.join(runDir, "farm-report.md")}`,
        `WARNING: the latest convenience pointer under ${ENV.reportDir} could not be refreshed for this run:`,
        ...latestReportErrors.map((m) => `  - ${m}`),
        `The authoritative receipt above is unaffected, but ${path3.join(ENV.reportDir, "farm-report.json")} does not describe run ${runId}.`
      ].join("\n")
    ) : `Report: ${path3.join(runDir, "farm-report.md")}  (latest: ${path3.join(ENV.reportDir, "farm-report.md")})`,
    ""
  ].join("\n");
  await new Promise((resolve) => process.stdout.write(summary, () => resolve()));
  process.exit(exitCode);
}
async function writeReport(plan, results, blocked, aborted, runId, health) {
  const runDir = runArtifactDir(runId);
  const diffsDir = path3.join(runDir, "diffs");
  const latestDiffsDir = path3.join(ENV.reportDir, "diffs");
  const unavailable = health.diffs.unavailable;
  const patchPath = /* @__PURE__ */ new Map();
  let diffsDirError = null;
  await mkdir2(diffsDir, { recursive: true }).catch((e) => {
    diffsDirError = msgOf(e);
  });
  await mkdir2(latestDiffsDir, { recursive: true }).catch(
    (e) => noteArtifactError(health.diffs.latestMirrorErrors, `mkdir: ${msgOf(e)}`)
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
    if (!d.out.trim()) continue;
    const dest = path3.join(diffsDir, `${r.id}.patch`);
    try {
      await atomicWriteFile(dest, d.out);
      patchPath.set(r.id, dest);
    } catch (e) {
      noteUnavailableDiff(health.diffs, r.id, `patch write failed: ${msgOf(e)}`);
      continue;
    }
    await atomicWriteFile(path3.join(latestDiffsDir, `${r.id}.patch`), d.out).catch(
      (e) => noteArtifactError(health.diffs.latestMirrorErrors, `${r.id}: ${msgOf(e)}`)
    );
  }
  const pTok = results.reduce((n, r) => n + (r.promptTokens ?? 0), 0);
  const cTok = results.reduce((n, r) => n + (r.completionTokens ?? 0), 0);
  const leaks = cleanupFailures(health, results);
  const streamComplete = health.stream.errors.length === 0;
  const artifacts = {
    run_dir: runDir,
    stream: {
      path: path3.join(runDir, "farm-results.jsonl"),
      latest: path3.join(ENV.reportDir, "farm-results.jsonl"),
      complete: streamComplete,
      errors: health.stream.errors
    },
    diffs: {
      dir: diffsDir,
      latest_dir: latestDiffsDir,
      // `unavailable` is capped; `unavailable_total` is not, so a bounded list
      // never understates how many tasks lack diff evidence.
      unavailable,
      unavailable_total: health.diffs.unavailableTotal,
      latest_mirror_errors: health.diffs.latestMirrorErrors
    },
    // #398: the run's resource-ownership statement. `released` is an explicit
    // positive claim, so a consumer can distinguish "nothing leaked" from "this
    // report predates the check" without inferring it from an absent key.
    cleanup: { released: leaks.length === 0, failures: leaks }
  };
  const reportMeta = projectPlanMetaForReport(plan.meta);
  const json = JSON.stringify(
    { run_id: runId, plan: reportMeta, aborted, tokens: { prompt: pTok, completion: cTok }, results, blocked, artifacts, ts: (/* @__PURE__ */ new Date()).toISOString() },
    null,
    2
  );
  const md = [
    `# Farm report \u2014 ${reportMeta.name}`,
    ``,
    aborted ? `> **ABORTED by circuit breaker** \u2014 escalation rate exceeded threshold.
` : ``,
    streamComplete ? `` : `> **Streaming rail incomplete** \u2014 ${health.stream.errors.length} write failure(s) on \`farm-results.jsonl\`; this report is authoritative for settled tasks.
`,
    leaks.length ? `> **CLEANUP DEGRADED** \u2014 ${leaks.length} worktree/branch could not be released; see Resource cleanup below.
` : ``,
    `Run: \`${runId}\` \u2014 artifacts under \`${runDir}\``,
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
    `## Diff evidence`,
    ...health.diffs.unavailableTotal ? [
      `${health.diffs.unavailableTotal} task(s) have no diff evidence${unavailable.length < health.diffs.unavailableTotal ? ` (first ${MAX_RECORDED_ARTIFACT_ERRORS} listed)` : ``}:`,
      ...unavailable.map((u) => `- **${u.id}** \u2014 diff evidence unavailable: ${u.reason}`)
    ] : [`Every settled task with a non-empty diff has a patch under \`${diffsDir}\`.`],
    ``,
    ...cleanupReportLines(health, results),
    ``,
    `## Warnings \u2014 review during spec-compliance`,
    ...results.filter((r) => r.warning).map((r) => {
      const p = patchPath.get(r.id);
      return `- **${r.id}** \u2014 ${r.warning} (${p ? `diff: \`${p}\`` : "diff evidence unavailable"})`;
    })
  ].join("\n");
  await atomicWriteFile(path3.join(runDir, "farm-report.json"), json);
  await atomicWriteFile(path3.join(runDir, "farm-report.md"), md);
  for (const [dest, data] of [
    [path3.join(ENV.reportDir, "farm-report.json"), json],
    [path3.join(ENV.reportDir, "farm-report.md"), md]
  ])
    await atomicWriteFile(dest, data).catch(
      (e) => noteArtifactError(health.report.latestMirrorErrors, `${dest}: ${msgOf(e)}`)
    );
}
var _thisFile = fileURLToPath(import.meta.url);
var _entryFile = path3.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
export {
  DEFAULT_API_BASE_URL,
  MAX_RECORDED_ARTIFACT_ERRORS,
  PLAN_SHAPE,
  SAFE_RUN_ID,
  SAFE_TASK_ID,
  _resetAllowedWorktreeRoot,
  allowedWorktreeRoot,
  assertContainedWorktree,
  assertSafeRunId,
  assertSecureBaseUrl,
  atomicWriteFile,
  buildChatBody,
  buildPrompt,
  captureInScope,
  checkDrift,
  cleanupFailures,
  cleanupReportLines,
  codeLineCount,
  createLimiter,
  deleteBranchVerified,
  extractFileBlocks,
  extractLiterals,
  httpWorker,
  makeEntitlementProbe,
  mintRunId,
  mutationSurvivalNote,
  newRunArtifactHealth,
  noteArtifactError,
  noteUnavailableDiff,
  numEnv,
  parseChatCompletion,
  parseMutationHookOutput,
  parsePlan,
  projectPlanMetaForReport,
  readSampling,
  redactSecrets,
  removeWorktreeVerified,
  run,
  runArtifactDir,
  runExitCode,
  runGate,
  runTask,
  screenEntitlements,
  validate,
  validateWorktreeRoot,
  writeFilesInto
};
