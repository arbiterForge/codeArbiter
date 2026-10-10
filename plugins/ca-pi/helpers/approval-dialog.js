// src/approval-entry.ts
import { realpath as realpath4 } from "node:fs/promises";
import { dirname as dirname3, resolve as resolve6 } from "node:path";
import { fileURLToPath as fileURLToPath2 } from "node:url";

// src/bridge.ts
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { accessSync, constants, realpathSync, statSync } from "node:fs";
import { realpath as realpath2 } from "node:fs/promises";
import { isAbsolute, posix as posix2, win32 as win322 } from "node:path";

// src/audit-sink.ts
import { constants as fsConstants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { relative, resolve as resolve2 } from "node:path";

// src/path-boundary.ts
import { posix, resolve, win32 } from "node:path";
function flavorForPlatform(platform) {
  return platform === "win32" ? "win32" : "posix";
}
function pathApiFor(flavor) {
  return flavor === "win32" ? win32 : posix;
}
function lexicallyInside(path, root, flavor = flavorForPlatform(process.platform)) {
  const pathApi = pathApiFor(flavor);
  const suffix = pathApi.relative(root, path);
  return suffix === "" || !suffix.startsWith("..") && !pathApi.isAbsolute(suffix);
}

// src/audit-sink.ts
var AUDIT_LOG_NAME = "gate-events.log";
var AUDIT_STATE_DIRECTORY = ".codearbiter";
var MAX_AUDIT_LINE_BYTES = 2048;
var NODE_AUDIT_SINK_IO = Object.freeze({ realpath, lstat, open });
function sameAuditFile(left, right) {
  return left.isFile() && right.isFile() && !left.isSymbolicLink() && !right.isSymbolicLink() && left.nlink === 1 && right.nlink === 1 && left.dev === right.dev && left.ino === right.ino;
}
function sameAuditDirectory(left, right) {
  return left.isDirectory() && right.isDirectory() && !left.isSymbolicLink() && !right.isSymbolicLink() && left.dev === right.dev && left.ino === right.ino;
}
async function openedAuditTarget(target, io) {
  const noFollow = typeof fsConstants.O_NOFOLLOW === "number" ? fsConstants.O_NOFOLLOW : 0;
  const existingFlags = fsConstants.O_WRONLY | fsConstants.O_APPEND | noFollow;
  const createFlags = existingFlags | fsConstants.O_CREAT | fsConstants.O_EXCL;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let expected;
    try {
      expected = await io.lstat(target);
      if (!expected.isFile() || expected.isSymbolicLink() || expected.nlink !== 1) return void 0;
    } catch (error) {
      if (error.code !== "ENOENT") return void 0;
    }
    let handle;
    try {
      handle = await io.open(target, expected === void 0 ? createFlags : existingFlags, 384);
    } catch (error) {
      if (expected === void 0 && error.code === "EEXIST" && attempt === 0) continue;
      return void 0;
    }
    try {
      const opened = await handle.stat();
      const pathname = await io.lstat(target);
      if (!sameAuditFile(opened, pathname) || expected !== void 0 && !sameAuditFile(opened, expected)) {
        await handle.close();
        return void 0;
      }
      return Object.freeze({ handle, identity: opened });
    } catch {
      try {
        await handle.close();
      } catch {
      }
      return void 0;
    }
  }
  return void 0;
}
async function appendAuditLineWithIo(cwd, line, io) {
  try {
    if (Buffer.byteLength(line, "utf8") > MAX_AUDIT_LINE_BYTES || !line.endsWith("\n") || line.slice(0, -1).includes("\n")) return false;
    const root = await io.realpath(cwd);
    const statePath = resolve2(root, AUDIT_STATE_DIRECTORY);
    const stateInfo = await io.lstat(statePath);
    if (!stateInfo.isDirectory() || stateInfo.isSymbolicLink()) return false;
    const state = await io.realpath(statePath);
    const stateRelative = relative(root, state);
    if (stateRelative === "" || !lexicallyInside(state, root) || resolve2(root, stateRelative) !== state) return false;
    const stateIdentity = await io.lstat(state);
    if (!sameAuditDirectory(stateInfo, stateIdentity)) return false;
    const stateIsCurrent = async () => {
      try {
        return await io.realpath(statePath) === state && sameAuditDirectory(stateIdentity, await io.lstat(statePath));
      } catch {
        return false;
      }
    };
    if (!await stateIsCurrent()) return false;
    const target = resolve2(state, AUDIT_LOG_NAME);
    const opened = await openedAuditTarget(target, io);
    if (opened === void 0) return false;
    const { handle, identity } = opened;
    try {
      const before = await handle.stat();
      const beforePath = await io.lstat(target);
      if (!sameAuditFile(identity, before) || !sameAuditFile(before, beforePath) || !await stateIsCurrent()) return false;
      await handle.appendFile(line, { encoding: "utf8" });
      await handle.sync();
      const after = await handle.stat();
      const afterPath = await io.lstat(target);
      if (!sameAuditFile(before, after) || !sameAuditFile(after, afterPath) || after.size < before.size + Buffer.byteLength(line, "utf8") || !await stateIsCurrent()) return false;
    } finally {
      await handle.close();
    }
    return true;
  } catch {
    return false;
  }
}
async function appendAuditLine(cwd, line) {
  return await appendAuditLineWithIo(cwd, line, NODE_AUDIT_SINK_IO);
}

// src/redaction.ts
import { randomBytes } from "node:crypto";

// ../../ca/tools/redactor.ts
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

// src/redaction.ts
function redactSecrets2(value) {
  return redactSecrets(value);
}
var MIN_BENIGN_LITERAL_LENGTH = 8;
function maskBenign(value, benign) {
  const literals = [...new Set(benign)].filter((literal) => literal.length >= MIN_BENIGN_LITERAL_LENGTH).sort((a, b) => b.length - a.length);
  const identity = { masked: value, restore: (text) => text };
  if (literals.length === 0) return identity;
  const nonce = randomBytes(8).toString("hex");
  const captured = [];
  let masked = value;
  for (const literal of literals) {
    const pattern = new RegExp(literal.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "gu");
    masked = masked.replace(pattern, (match) => `${nonce}-${captured.push(match) - 1}`);
  }
  if (captured.length === 0) return identity;
  const placeholder = new RegExp(`${nonce}-(\\d+)`, "gu");
  return {
    masked,
    restore: (text) => text.replace(placeholder, (whole, index) => captured[Number(index)] ?? whole)
  };
}
function safeDiagnostic(value, maxChars = 2e3, benignPaths = []) {
  const { masked, restore } = maskBenign(value, benignPaths);
  const normalized = restore(redactSecrets2(masked)).replace(/\r\n?/gu, "\n").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "\uFFFD").trim();
  return normalized.length <= maxChars ? normalized : `${normalized.slice(0, maxChars)}\u2026`;
}
function redactJson(value, depth = 0) {
  if (depth > 32) return "[REDACTED OVERSIZE VALUE]";
  if (typeof value === "string") return safeDiagnostic(value, 16e3);
  if (Array.isArray(value)) return value.map((item) => redactJson(item, depth + 1));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redactJson(item, depth + 1)]));
  }
  return value;
}

// src/bridge.ts
var RESPONSE_KEYS = /* @__PURE__ */ new Set(["version", "outcome", "ruleId", "message", "context", "resultPatch", "auditCode"]);
var OUTCOMES = /* @__PURE__ */ new Set(["allow", "block", "warn", "notice"]);
var PI_MAX_HOME_CHARS = 32768;
var CONTROL_RE = /[\u0000-\u001f\u007f-\u009f]/u;
function minimalEnvironment(identities, userHome) {
  const allowed = ["SystemRoot", "WINDIR", "TEMP", "TMP"];
  const env = { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" };
  for (const key of allowed) if (process.env[key] !== void 0) env[key] = process.env[key];
  if (identities !== void 0) {
    const pathApi = process.platform === "win32" ? win322 : posix2;
    const searchDirectories = /* @__PURE__ */ new Set([
      pathApi.dirname(identities.git),
      pathApi.dirname(identities.python)
    ]);
    const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
    if (process.platform === "win32" && systemRoot !== void 0 && win322.isAbsolute(systemRoot)) {
      searchDirectories.add(win322.join(systemRoot, "System32"));
    }
    env.PATH = [...searchDirectories].join(process.platform === "win32" ? ";" : ":");
    env.CODEARBITER_GIT_EXECUTABLE = identities.git;
    env.CODEARBITER_PYTHON_EXECUTABLE = identities.python;
  }
  if (userHome !== void 0) {
    if (process.platform === "win32") env.USERPROFILE = userHome;
    else env.HOME = userHome;
  }
  return env;
}
function canonicalExecutable(candidate, platform) {
  const pathApi = platform === "win32" ? win322 : posix2;
  if (!pathApi.isAbsolute(candidate)) return void 0;
  try {
    const canonical = realpathSync(candidate);
    if (!statSync(canonical).isFile()) return void 0;
    if (platform !== "win32") accessSync(canonical, constants.X_OK);
    return canonical;
  } catch {
    return void 0;
  }
}
async function canonicalUserHome(projectRoot, packageRoot, platform = process.platform) {
  const pathApi = platform === "win32" ? win322 : posix2;
  const candidate = platform === "win32" ? process.env.USERPROFILE : process.env.HOME;
  if (typeof candidate !== "string" || candidate.length < 1 || candidate.length > PI_MAX_HOME_CHARS || candidate !== candidate.trim() || CONTROL_RE.test(candidate) || !pathApi.isAbsolute(candidate)) return void 0;
  try {
    const canonical = await realpath2(candidate);
    if (!statSync(canonical).isDirectory() || lexicallyInside(canonical, projectRoot, flavorForPlatform(platform)) || lexicallyInside(canonical, packageRoot, flavorForPlatform(platform))) return void 0;
    return canonical;
  } catch {
    return void 0;
  }
}
function trustedPathCandidate(basename, projectCwd, platform, pathValue) {
  const pathApi = platform === "win32" ? win322 : posix2;
  const separator = platform === "win32" ? ";" : ":";
  const canonicalProject = canonicalExecutable(projectCwd, platform) ?? (() => {
    try {
      return realpathSync(projectCwd);
    } catch {
      return pathApi.resolve(projectCwd);
    }
  })();
  for (const rawEntry of pathValue.split(separator)) {
    const entry = rawEntry.trim();
    if (entry === "" || !pathApi.isAbsolute(entry)) continue;
    let directory;
    try {
      directory = realpathSync(entry);
    } catch {
      continue;
    }
    const candidate = canonicalExecutable(pathApi.join(directory, basename), platform);
    if (candidate !== void 0 && !lexicallyInside(candidate, canonicalProject, flavorForPlatform(platform))) return candidate;
  }
  return void 0;
}
function resolveGitExecutable(projectCwd, platform = process.platform, pathValue = process.env.PATH ?? "") {
  const name = platform === "win32" ? "git.exe" : "git";
  const executable = trustedPathCandidate(name, projectCwd, platform, pathValue);
  if (executable === void 0) {
    throw new Error("codeArbiter could not resolve an absolute trusted Git executable; run /ca-doctor.");
  }
  return executable;
}
function windowsTaskkillExecutable() {
  if (process.platform !== "win32") return void 0;
  const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
  if (systemRoot === void 0 || !win322.isAbsolute(systemRoot)) return void 0;
  const candidate = canonicalExecutable(win322.join(systemRoot, "System32", "taskkill.exe"), "win32");
  if (candidate === void 0) return void 0;
  let canonicalRoot;
  try {
    canonicalRoot = realpathSync(systemRoot);
  } catch {
    return void 0;
  }
  return lexicallyInside(candidate, canonicalRoot, "win32") ? candidate : void 0;
}
function validResponse(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record2 = value;
  if (Object.keys(record2).some((key) => !RESPONSE_KEYS.has(key))) return false;
  if (record2.version !== 1 || typeof record2.outcome !== "string" || !OUTCOMES.has(record2.outcome)) return false;
  for (const key of ["ruleId", "message", "context", "auditCode"]) {
    if (record2[key] !== void 0 && typeof record2[key] !== "string") return false;
  }
  return true;
}
var WINDOWS_TASKKILL_TIMEOUT_MS = 1e3;
var KILL_SETTLE_DEADLINE_MS = 2e3;
function killTree(child, taskkillExecutable) {
  if (child.pid === void 0) return;
  if (process.platform === "win32") {
    if (taskkillExecutable === void 0) {
      child.kill("SIGKILL");
      return;
    }
    void killWindowsTree(child, taskkillExecutable);
    return;
  }
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
}
function killWindowsTree(child, taskkillExecutable) {
  return new Promise((resolveKill) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolveKill();
    };
    let helper;
    try {
      helper = spawn(taskkillExecutable, ["/pid", String(child.pid), "/t", "/f"], {
        env: minimalEnvironment(),
        shell: false,
        stdio: "ignore",
        windowsHide: true
      });
    } catch {
      child.kill("SIGKILL");
      finish();
      return;
    }
    const timer = setTimeout(() => {
      try {
        helper.kill("SIGKILL");
      } catch {
      }
      child.kill("SIGKILL");
      finish();
    }, WINDOWS_TASKKILL_TIMEOUT_MS);
    timer.unref?.();
    helper.once("error", () => {
      clearTimeout(timer);
      child.kill("SIGKILL");
      finish();
    });
    helper.once("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) child.kill("SIGKILL");
      finish();
    });
  });
}
var BRIDGE_CORRELATION_RE = /^[a-f0-9]{64}$/u;
function normalizedRequest(request) {
  const { correlation, ...rest } = request;
  return typeof correlation === "string" && BRIDGE_CORRELATION_RE.test(correlation) ? { ...rest, correlation } : rest;
}
function sanitizedResponse(response, request) {
  return {
    ...response,
    ...response.ruleId === void 0 ? {} : { ruleId: safeDiagnostic(response.ruleId, 100) },
    ...response.message === void 0 ? {} : { message: safeDiagnostic(response.message) },
    ...response.context === void 0 ? {} : { context: safeDiagnostic(response.context, 16e3) },
    ...response.auditCode === void 0 ? {} : { auditCode: safeDiagnostic(response.auditCode, 100) },
    ...response.resultPatch === void 0 ? {} : {
      resultPatch: request.event === "plan_file" ? response.resultPatch : redactJson(response.resultPatch)
    }
  };
}
var spawnImpl = spawn;
var BridgeClient = class {
  constructor(options) {
    this.options = options;
    this.timeoutMs = options.timeoutMs ?? 1e4;
    this.maxRequestBytes = options.maxRequestBytes ?? 262144;
    this.maxStreamBytes = options.maxStreamBytes ?? 1048576;
    this.ready = this.validatePaths();
    this.ready.catch(() => void 0);
  }
  options;
  ready;
  timeoutMs;
  maxRequestBytes;
  maxStreamBytes;
  async validatePaths() {
    if (this.options.pythonExecutable === void 0 || this.options.gitExecutable === void 0) {
      throw new Error("Python 3 or Git is unavailable");
    }
    if (!isAbsolute(this.options.pythonExecutable) || !isAbsolute(this.options.gitExecutable) || !isAbsolute(this.options.bridgeScript) || !isAbsolute(this.options.packageRoot)) {
      throw new Error("bridge paths must be absolute");
    }
    const [git, python, script, root] = await Promise.all([
      realpath2(this.options.gitExecutable),
      realpath2(this.options.pythonExecutable),
      realpath2(this.options.bridgeScript),
      realpath2(this.options.packageRoot)
    ]);
    if (canonicalExecutable(git, process.platform) === void 0 || canonicalExecutable(python, process.platform) === void 0) {
      throw new Error("bridge executable identity is invalid");
    }
    if (!lexicallyInside(script, root)) throw new Error("bridge script is outside the installed package");
    const taskkill = windowsTaskkillExecutable();
    if (process.platform === "win32" && taskkill === void 0) throw new Error("taskkill is unavailable");
    return { git, python, root, script, ...taskkill === void 0 ? {} : { taskkill } };
  }
  failure(request, detail) {
    const category = this.options.toolClasses[request.tool ?? ""] ?? "OTHER";
    const advisory = request.event !== "tool_call" || category === "READ";
    return {
      version: 1,
      outcome: advisory ? "warn" : "block",
      ruleId: "PI-BRIDGE",
      message: `codeArbiter Pi bridge ${safeDiagnostic(detail)}; ${advisory ? "continuing advisory operation; " : "mutation blocked; "}run /ca-doctor.`,
      auditCode: advisory ? "PI_BRIDGE_WARN" : "PI_BRIDGE_BLOCK"
    };
  }
  async auditFailure(request, response, counts) {
    try {
      if (this.options.shouldAuditFailure?.(request) === false) return;
    } catch {
    }
    const line = [
      `[${(/* @__PURE__ */ new Date()).toISOString()}]`,
      "HOST: pi",
      `RULE: ${response.ruleId ?? "PI-BRIDGE"}`,
      `AUDIT: ${response.auditCode ?? "PI_BRIDGE_FAILURE"}`,
      `CORRELATION: ${request.correlation ?? randomUUID()}`,
      `REQUEST_BYTES: ${counts.request}`,
      `STDOUT_BYTES: ${counts.stdout}`,
      `STDERR_BYTES: ${counts.stderr}`
    ].join(" | ") + "\n";
    await appendAuditLine(request.cwd, line);
  }
  async failed(request, detail, counts = { request: 0, stdout: 0, stderr: 0 }) {
    const response = this.failure(request, detail);
    await this.auditFailure(request, response, counts);
    return response;
  }
  async call(rawRequest, signal) {
    const request = normalizedRequest(rawRequest);
    let paths;
    let userHome;
    try {
      paths = await this.ready;
    } catch {
      return await this.failed(request, "path validation failed");
    }
    try {
      const project = await realpath2(request.cwd);
      if (lexicallyInside(paths.git, project) || lexicallyInside(paths.python, project)) {
        return await this.failed(request, "path validation failed");
      }
      const canonicalHome = await canonicalUserHome(project, paths.root);
      if (canonicalHome === void 0) return await this.failed(request, "path validation failed");
      userHome = canonicalHome;
    } catch {
      return await this.failed(request, "path validation failed");
    }
    let body;
    try {
      body = Buffer.from(JSON.stringify(request), "utf8");
    } catch {
      return await this.failed(request, "request serialization failed");
    }
    if (body.byteLength > this.maxRequestBytes) return await this.failed(request, "request overflow", { request: body.byteLength, stdout: 0, stderr: 0 });
    if (signal.aborted) return await this.failed(request, "cancelled", { request: body.byteLength, stdout: 0, stderr: 0 });
    return await new Promise((resolveResponse) => {
      let child;
      try {
        child = spawnImpl(paths.python, [...this.options.pythonPrefixArgs ?? [], paths.script], {
          cwd: paths.root,
          detached: process.platform !== "win32",
          env: minimalEnvironment({ git: paths.git, python: paths.python }, userHome),
          shell: false,
          stdio: ["pipe", "pipe", "pipe"],
          windowsHide: true
        });
      } catch {
        void this.failed(
          request,
          "bridge launch failed",
          { request: body.byteLength, stdout: 0, stderr: 0 }
        ).then(resolveResponse, () => resolveResponse(this.failure(request, "bridge launch failed")));
        return;
      }
      const stdout = [];
      const stderr = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let reason;
      let settled = false;
      let finishing = false;
      let settleDeadline;
      const finish = (response) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (settleDeadline !== void 0) clearTimeout(settleDeadline);
        signal.removeEventListener("abort", abort);
        resolveResponse(response);
      };
      const failAndKill = (value) => {
        if (reason !== void 0) return;
        reason = value;
        killTree(child, paths.taskkill);
        settleDeadline = setTimeout(() => finishFailure(value), KILL_SETTLE_DEADLINE_MS);
        settleDeadline.unref?.();
      };
      const finishFailure = (detail) => {
        if (settled || finishing) return;
        finishing = true;
        void this.failed(request, detail, { request: body.byteLength, stdout: stdoutBytes, stderr: stderrBytes }).then(finish, () => finish(this.failure(request, detail)));
      };
      const collect = (target, chunk, stream) => {
        const count = stream === "stdout" ? stdoutBytes : stderrBytes;
        const remaining = Math.max(0, this.maxStreamBytes - count);
        if (remaining > 0) target.push(chunk.subarray(0, remaining));
        if (stream === "stdout") stdoutBytes += chunk.byteLength;
        else stderrBytes += chunk.byteLength;
        if (count + chunk.byteLength > this.maxStreamBytes) failAndKill("protocol overflow");
      };
      const abort = () => failAndKill("cancelled");
      const timer = setTimeout(() => failAndKill("timed out"), this.timeoutMs);
      signal.addEventListener("abort", abort, { once: true });
      child.stdout.on("data", (chunk) => collect(stdout, chunk, "stdout"));
      child.stderr.on("data", (chunk) => collect(stderr, chunk, "stderr"));
      child.on("error", () => finishFailure("bridge launch failed"));
      child.on("close", (code) => {
        if (reason !== void 0) return finishFailure(reason);
        if (code !== 0) return finishFailure("bridge process failed");
        const stdoutText = Buffer.concat(stdout).toString("utf8");
        let parsed;
        try {
          parsed = JSON.parse(stdoutText);
        } catch {
          return finishFailure("returned malformed protocol");
        }
        if (!validResponse(parsed)) return finishFailure("returned malformed protocol");
        finish(sanitizedResponse(parsed, request));
      });
      child.stdin.on("error", () => void 0);
      child.stdin.end(body);
    });
  }
};
function systemPythonProbe(executable, prefixArgs, cwd) {
  const probe = spawnSync(executable, [...prefixArgs, "-c", "import sys; print(sys.version_info[0]); print(sys.executable)"], {
    cwd,
    encoding: "utf8",
    env: minimalEnvironment(),
    shell: false,
    timeout: 2e3,
    windowsHide: true
  });
  return { status: probe.status, stdout: probe.stdout ?? "", stderr: probe.stderr ?? "" };
}
function resolvePythonCommand(platform = process.platform, probe = systemPythonProbe, searchCwd, excludedProjectCwd, pathValue = process.env.PATH ?? "") {
  const pathApi = platform === "win32" ? win322 : posix2;
  const safeCwd = searchCwd ?? (platform === "win32" ? win322.parse(process.execPath).root : "/");
  if (!pathApi.isAbsolute(safeCwd)) {
    throw new Error("codeArbiter Python search cwd must be absolute; run /ca-doctor.");
  }
  const candidates = platform === "win32" ? [["py.exe", ["-3"]], ["python.exe", []], ["python3.exe", []]] : [["python3", []], ["python", []]];
  for (const [candidate, prefixArgs] of candidates) {
    const probedCandidate = probe === systemPythonProbe ? trustedPathCandidate(candidate, excludedProjectCwd ?? safeCwd, platform, pathValue) : candidate.replace(/\.exe$/u, "");
    if (probedCandidate === void 0) continue;
    const result = probe(probedCandidate, prefixArgs, safeCwd);
    const lines = result.stdout.trim().split(/\r?\n/u);
    const executable = lines[1] ?? "";
    const absolute = platform === "win32" ? win322.isAbsolute(executable) : posix2.isAbsolute(executable);
    const canonical = absolute ? probe === systemPythonProbe ? canonicalExecutable(executable, platform) : executable : void 0;
    if (result.status === 0 && lines[0] === "3" && canonical !== void 0 && (probe !== systemPythonProbe || !lexicallyInside(canonical, excludedProjectCwd ?? safeCwd, flavorForPlatform(platform)))) {
      return { executable: canonical, prefixArgs: [] };
    }
  }
  throw new Error("codeArbiter could not resolve an absolute Python interpreter; run /ca-doctor.");
}

// src/approval-dialog.ts
import { randomUUID as randomUUID2 } from "node:crypto";
import { isAbsolute as isAbsolute2, resolve as resolve4 } from "node:path";
var UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u;
var HASH = /^[0-9a-f]{64}$/u;
var FLAGS = [
  "--no-extensions",
  "--no-tools",
  "--no-skills",
  "--no-prompt-templates",
  "--no-themes",
  "--no-context-files",
  "--no-session",
  "-e"
];
function validApprovalLaunch(args, entry, execArgs, nodeOptions) {
  return isAbsolute2(entry) && execArgs.length === 0 && !nodeOptions && args.length === FLAGS.length + 1 && FLAGS.every((flag, index) => args[index] === flag) && isAbsolute2(args[FLAGS.length]) && resolve4(args[FLAGS.length]) === resolve4(entry);
}
function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
}
function pendingSnapshot(value) {
  return record(value) && Object.keys(value).sort().join(",") === "artifact_id,kind,model_sha256,normative_sha256,pending_sha256,revision" && typeof value.artifact_id === "string" && /^[A-Z][A-Z0-9-]{1,79}$/u.test(value.artifact_id) && (value.kind === "spec" || value.kind === "plan") && Number.isSafeInteger(value.revision) && value.revision >= 1 && [value.model_sha256, value.normative_sha256, value.pending_sha256].every((hash) => typeof hash === "string" && HASH.test(hash));
}
async function runApprovalDialog(context, options) {
  let consuming = false;
  const controller = new AbortController();
  const abort = () => controller.abort();
  context.signal?.addEventListener("abort", abort, { once: true });
  let timer;
  try {
    const session = context.sessionManager?.getSessionId?.();
    const cwd = context.cwd;
    const valid = () => options.isCurrent() && context.mode === "tui" && context.hasUI === true && context.isProjectTrusted?.() === true && context.cwd === cwd && isAbsolute2(cwd) && context.sessionManager?.getSessionId?.() === session && typeof session === "string" && UUID.test(session) && !context.signal?.aborted && !controller.signal.aborted && Array.isArray(options.activeTools()) && options.activeTools().length === 0;
    if (!valid() || typeof context.ui.input !== "function") return { status: "unavailable" };
    const generation = randomUUID2();
    const bridge = options.bridge(cwd);
    const snapshot = await bridge.call({ version: 1, event: "native_approval_inspect", cwd }, controller.signal);
    if (!valid()) return { status: "stale" };
    if (snapshot.outcome !== "allow" || !pendingSnapshot(snapshot.resultPatch)) return { status: "unavailable" };
    const pending = snapshot.resultPatch;
    timer = setTimeout(abort, 3e5);
    const reply = await context.ui.input(
      `Review ${pending.kind} ${pending.artifact_id} revision ${pending.revision}
Normative SHA-256: ${pending.normative_sha256}
Enter the exact armed approval reply, or deny. Escape preserves the request.`,
      void 0,
      { signal: controller.signal, timeout: 3e5 }
    );
    if (!valid()) return { status: "stale" };
    if (reply === void 0) return { status: "cancelled" };
    if (reply === "deny") return { status: "denied" };
    if (typeof reply !== "string" || Buffer.byteLength(reply, "utf8") > 512) return { status: "unmatched" };
    consuming = true;
    const response = await bridge.call({
      version: 1,
      event: "native_approval_consume",
      cwd,
      sessionId: session,
      input: { reply, generation, pending_sha256: pending.pending_sha256 }
    }, controller.signal);
    if (!valid() || response.outcome !== "allow" || !record(response.resultPatch)) return { status: "outcome-unknown" };
    if (response.resultPatch.approved === true && response.resultPatch.artifact_id === pending.artifact_id) {
      return { status: "approved", artifact_id: pending.artifact_id };
    }
    if (response.resultPatch.approved === false && response.resultPatch.matched === false) return { status: "unmatched" };
    return { status: "outcome-unknown" };
  } catch {
    return { status: consuming ? "outcome-unknown" : "unavailable" };
  } finally {
    if (timer !== void 0) clearTimeout(timer);
    controller.abort();
    context.signal?.removeEventListener("abort", abort);
  }
}

// src/runtime-resolver.ts
import { lstat as lstat2, readFile, realpath as realpath3 } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname as dirname2, isAbsolute as isAbsolute3, resolve as resolve5 } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
var PI_RUNTIME_DIAGNOSIS = "codeArbiter could not validate the active Pi CLI runtime; start from the Pi CLI and run /ca-doctor.";
var trustedIdentities = /* @__PURE__ */ new WeakSet();
function fail(cause) {
  throw new Error(PI_RUNTIME_DIAGNOSIS, cause === void 0 ? void 0 : { cause });
}
async function owningPackageRoot(file, expectedName) {
  let cursor = dirname2(file);
  while (true) {
    const candidate = resolve5(cursor, "package.json");
    try {
      const manifest = JSON.parse(await readFile(candidate, "utf8"));
      if (manifest.name !== expectedName) return fail();
      const canonicalRoot = await realpath3(cursor);
      if (!lexicallyInside(file, canonicalRoot) || !lexicallyInside(await realpath3(candidate), canonicalRoot)) return fail();
      return canonicalRoot;
    } catch (error) {
      if (error.code !== "ENOENT") return fail(error);
    }
    const parent = dirname2(cursor);
    if (parent === cursor) return fail();
    cursor = parent;
  }
}
function binTarget(manifest) {
  if (typeof manifest.bin === "string") return manifest.bin;
  if (manifest.bin !== null && typeof manifest.bin === "object") {
    const value = manifest.bin.pi;
    if (typeof value === "string") return value;
  }
  return fail();
}
function importTarget(manifest) {
  if (manifest.exports === null || typeof manifest.exports !== "object") return fail();
  const rootExport = manifest.exports["."];
  if (typeof rootExport === "string") return rootExport;
  if (rootExport !== null && typeof rootExport === "object") {
    const value = rootExport.import;
    if (typeof value === "string") return value;
  }
  return fail();
}
async function resolvePiRuntimeIdentity(cliCandidate) {
  try {
    const activeAnchor = process.argv[1];
    if (typeof activeAnchor !== "string" || activeAnchor.length === 0 || !isAbsolute3(activeAnchor)) return fail();
    const canonicalAnchor = await realpath3(activeAnchor);
    if (cliCandidate !== void 0) {
      if (!isAbsolute3(cliCandidate) || await realpath3(cliCandidate) !== canonicalAnchor) return fail();
    }
    const shippedModule = await realpath3(fileURLToPath(import.meta.url));
    const extensionPackageRoot = await owningPackageRoot(shippedModule, "@arbiterforge/ca-pi");
    let cursor = dirname2(canonicalAnchor);
    let manifest;
    let manifestPath = "";
    while (true) {
      const candidate = resolve5(cursor, "package.json");
      try {
        manifest = JSON.parse(await readFile(candidate, "utf8"));
        manifestPath = candidate;
        break;
      } catch (error) {
        if (error.code !== "ENOENT") return fail(error);
      }
      const parent = dirname2(cursor);
      if (parent === cursor) return fail();
      cursor = parent;
    }
    if (manifest.name !== "@earendil-works/pi-coding-agent" || typeof manifest.version !== "string") return fail();
    const packageRoot = await realpath3(cursor);
    const canonicalManifest = await realpath3(manifestPath);
    if (!lexicallyInside(canonicalAnchor, packageRoot) || !lexicallyInside(canonicalManifest, packageRoot)) return fail();
    if (lexicallyInside(packageRoot, extensionPackageRoot)) return fail();
    const declaredBin = resolve5(packageRoot, binTarget(manifest));
    if (!lexicallyInside(declaredBin, packageRoot) || await realpath3(declaredBin) !== canonicalAnchor) return fail();
    if (!(await lstat2(canonicalAnchor)).isFile()) return fail();
    const declaredExport = importTarget(manifest);
    if (!declaredExport.startsWith("./")) return fail();
    const requireFromPi = createRequire(resolve5(packageRoot, "package.json"));
    const moduleEntry = await realpath3(requireFromPi.resolve(declaredExport));
    if (!lexicallyInside(moduleEntry, packageRoot)) return fail();
    if (!(await lstat2(moduleEntry)).isFile()) return fail();
    const identity = Object.freeze({
      cliEntry: canonicalAnchor,
      manifestPath: canonicalManifest,
      moduleEntry,
      packageRoot,
      version: manifest.version
    });
    trustedIdentities.add(identity);
    return identity;
  } catch (error) {
    if (error instanceof Error && error.message === PI_RUNTIME_DIAGNOSIS) throw error;
    return fail(error);
  }
}

// src/approval-entry.ts
function approvalEntry(pi) {
  let generation;
  let started = false;
  pi.on("input", () => ({ action: "handled" }));
  for (const event of ["session_before_switch", "session_shutdown"]) {
    pi.on(event, () => {
      generation = void 0;
    });
  }
  pi.on("session_start", async (_event, context) => {
    const lease = {};
    generation = lease;
    try {
      if (started) throw new Error("one dialog per process");
      started = true;
      const entry = await realpath4(fileURLToPath2(import.meta.url));
      if (!validApprovalLaunch(process.argv.slice(2), entry, process.execArgv, process.env.NODE_OPTIONS)) {
        throw new Error("unsupported launch profile");
      }
      const runtime = await resolvePiRuntimeIdentity();
      if (runtime.version !== "1.0.2") throw new Error("unqualified host version");
      const packageRoot = resolve6(dirname3(entry), "..");
      const result = await runApprovalDialog(context, {
        isCurrent: () => generation === lease,
        activeTools: () => pi.getActiveTools(),
        bridge: (cwd) => {
          const python = resolvePythonCommand(process.platform, void 0, packageRoot, cwd);
          return new BridgeClient({
            packageRoot,
            bridgeScript: resolve6(packageRoot, "hooks", "pi-approval.py"),
            pythonExecutable: python.executable,
            pythonPrefixArgs: ["-B", ...python.prefixArgs],
            gitExecutable: resolveGitExecutable(cwd),
            toolClasses: {},
            maxRequestBytes: 16384,
            maxStreamBytes: 16384,
            shouldAuditFailure: () => false
          });
        }
      });
      context.ui.notify(
        result.status === "approved" ? `Approval recorded for ${result.artifact_id}.` : result.status === "outcome-unknown" ? "Approval outcome unknown. Read the artifact's durable state before any retry." : `Approval ${result.status}; no approval was recorded by this dialog.`,
        result.status === "approved" ? "info" : "warning"
      );
    } catch {
      context.ui.notify("Pi native approval unavailable for this launch. Ordinary workflow refusal remains in force.", "warning");
    } finally {
      generation = void 0;
      context.shutdown();
    }
  });
}
export {
  approvalEntry as default
};
