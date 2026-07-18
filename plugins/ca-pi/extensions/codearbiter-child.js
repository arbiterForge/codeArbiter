// <define:__CODEARBITER_PI_TOOL_CLASSES__>
var define_CODEARBITER_PI_TOOL_CLASSES_default = { bash: "EXEC", codearbiter_dispatch: "EXEC", codearbiter_farm_preview: "EXEC", write: "WRITE", edit: "EDIT", read: "READ" };

// src/child-extension.ts
import { createReadStream } from "node:fs";
import { readFile as readFile2, realpath as realpath3 } from "node:fs/promises";
import { dirname as dirname3, resolve as resolve3 } from "node:path";
import { fileURLToPath as fileURLToPath2 } from "node:url";

// src/attestation.ts
import { createHash } from "node:crypto";
var CHILD_ATTESTATION_DOMAIN = "ca-pi-child-attestation-v1";
var CHILD_ATTESTATION_TITLE = "codeArbiter isolated child readiness";
var CHILD_ATTESTATION_TIMEOUT_MS = 5e3;
function childAttestationDigest(input) {
  return createHash("sha256").update(JSON.stringify([
    CHILD_ATTESTATION_DOMAIN,
    input.nonce,
    input.challenge,
    input.cwd,
    input.provider,
    input.model,
    [...input.tools].sort(),
    input.projectTrusted,
    input.mode
  ]), "utf8").digest("hex");
}

// src/bridge.ts
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { accessSync, constants, realpathSync, statSync } from "node:fs";
import { appendFile, realpath } from "node:fs/promises";
import { isAbsolute, posix, relative, resolve, win32 } from "node:path";

// ../../ca/tools/redactor.ts
var SECRET_LINE = /(api[_-]?key|token|secret|password|BEGIN.*PRIVATE|sk-ant|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})/i;
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
function safeDiagnostic(value, maxChars = 2e3) {
  const normalized2 = redactSecrets2(value).replace(/\r\n?/gu, "\n").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "\uFFFD").trim();
  return normalized2.length <= maxChars ? normalized2 : `${normalized2.slice(0, maxChars)}\u2026`;
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
function inside(path, root) {
  const suffix = relative(root, path);
  return suffix === "" || !suffix.startsWith("..") && !isAbsolute(suffix);
}
function minimalEnvironment(identities) {
  const allowed = ["SystemRoot", "WINDIR", "TEMP", "TMP"];
  const env = { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" };
  for (const key of allowed) if (process.env[key] !== void 0) env[key] = process.env[key];
  if (identities !== void 0) {
    const pathApi = process.platform === "win32" ? win32 : posix;
    const searchDirectories = /* @__PURE__ */ new Set([
      pathApi.dirname(identities.git),
      pathApi.dirname(identities.python)
    ]);
    const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
    if (process.platform === "win32" && systemRoot !== void 0 && win32.isAbsolute(systemRoot)) {
      searchDirectories.add(win32.join(systemRoot, "System32"));
    }
    env.PATH = [...searchDirectories].join(process.platform === "win32" ? ";" : ":");
    env.CODEARBITER_GIT_EXECUTABLE = identities.git;
    env.CODEARBITER_PYTHON_EXECUTABLE = identities.python;
  }
  return env;
}
function canonicalExecutable(candidate, platform) {
  const pathApi = platform === "win32" ? win32 : posix;
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
function sameOrInside(path, root, platform) {
  const pathApi = platform === "win32" ? win32 : posix;
  const suffix = pathApi.relative(root, path);
  return suffix === "" || !suffix.startsWith("..") && !pathApi.isAbsolute(suffix);
}
function trustedPathCandidate(basename, projectCwd, platform, pathValue) {
  const pathApi = platform === "win32" ? win32 : posix;
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
    if (candidate !== void 0 && !sameOrInside(candidate, canonicalProject, platform)) return candidate;
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
  if (systemRoot === void 0 || !win32.isAbsolute(systemRoot)) return void 0;
  const candidate = canonicalExecutable(win32.join(systemRoot, "System32", "taskkill.exe"), "win32");
  if (candidate === void 0) return void 0;
  let canonicalRoot;
  try {
    canonicalRoot = realpathSync(systemRoot);
  } catch {
    return void 0;
  }
  return sameOrInside(candidate, canonicalRoot, "win32") ? candidate : void 0;
}
function validResponse(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value;
  if (Object.keys(record).some((key) => !RESPONSE_KEYS.has(key))) return false;
  if (record.version !== 1 || typeof record.outcome !== "string" || !OUTCOMES.has(record.outcome)) return false;
  for (const key of ["ruleId", "message", "context", "auditCode"]) {
    if (record[key] !== void 0 && typeof record[key] !== "string") return false;
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
    const result = spawnSync(taskkillExecutable, ["/pid", String(child.pid), "/t", "/f"], {
      env: minimalEnvironment(),
      shell: false,
      stdio: "ignore",
      timeout: WINDOWS_TASKKILL_TIMEOUT_MS,
      windowsHide: true
    });
    if (result.error !== void 0 || result.status !== 0) child.kill("SIGKILL");
    return;
  }
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
}
function sanitizedResponse(response) {
  return {
    ...response,
    ...response.ruleId === void 0 ? {} : { ruleId: safeDiagnostic(response.ruleId, 100) },
    ...response.message === void 0 ? {} : { message: safeDiagnostic(response.message) },
    ...response.context === void 0 ? {} : { context: safeDiagnostic(response.context, 16e3) },
    ...response.auditCode === void 0 ? {} : { auditCode: safeDiagnostic(response.auditCode, 100) },
    ...response.resultPatch === void 0 ? {} : { resultPatch: redactJson(response.resultPatch) }
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
      realpath(this.options.gitExecutable),
      realpath(this.options.pythonExecutable),
      realpath(this.options.bridgeScript),
      realpath(this.options.packageRoot)
    ]);
    if (canonicalExecutable(git, process.platform) === void 0 || canonicalExecutable(python, process.platform) === void 0) {
      throw new Error("bridge executable identity is invalid");
    }
    if (!inside(script, root)) throw new Error("bridge script is outside the installed package");
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
    const line = [
      `[${(/* @__PURE__ */ new Date()).toISOString()}]`,
      "HOST: pi",
      `RULE: ${response.ruleId ?? "PI-BRIDGE"}`,
      `AUDIT: ${response.auditCode ?? "PI_BRIDGE_FAILURE"}`,
      `CORRELATION: ${randomUUID()}`,
      `REQUEST_BYTES: ${counts.request}`,
      `STDOUT_BYTES: ${counts.stdout}`,
      `STDERR_BYTES: ${counts.stderr}`
    ].join(" | ") + "\n";
    try {
      await appendFile(resolve(request.cwd, ".codearbiter", "gate-events.log"), line, { encoding: "utf8" });
    } catch {
    }
  }
  async failed(request, detail, counts = { request: 0, stdout: 0, stderr: 0 }) {
    const response = this.failure(request, detail);
    await this.auditFailure(request, response, counts);
    return response;
  }
  async call(request, signal) {
    let paths;
    try {
      paths = await this.ready;
    } catch {
      return await this.failed(request, "path validation failed");
    }
    try {
      const project = await realpath(request.cwd);
      if (inside(paths.git, project) || inside(paths.python, project)) {
        return await this.failed(request, "path validation failed");
      }
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
          env: minimalEnvironment({ git: paths.git, python: paths.python }),
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
        finish(sanitizedResponse(parsed));
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
  const pathApi = platform === "win32" ? win32 : posix;
  const safeCwd = searchCwd ?? (platform === "win32" ? win32.parse(process.execPath).root : "/");
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
    const absolute = platform === "win32" ? win32.isAbsolute(executable) : posix.isAbsolute(executable);
    const canonical = absolute ? probe === systemPythonProbe ? canonicalExecutable(executable, platform) : executable : void 0;
    if (result.status === 0 && lines[0] === "3" && canonical !== void 0 && (probe !== systemPythonProbe || !sameOrInside(canonical, excludedProjectCwd ?? safeCwd, platform))) {
      return { executable: canonical, prefixArgs: [] };
    }
  }
  throw new Error("codeArbiter could not resolve an absolute Python interpreter; run /ca-doctor.");
}

// src/compatibility.ts
var SUPPORTED_PI_VERSIONS = /* @__PURE__ */ new Set(["0.80.5", "0.80.10"]);
var MINIMUM_NODE = [22, 19, 0];
var SEMVER_PREFIX = /^(\d+)\.(\d+)\.(\d+)(?:$|[-+])/u;
function atLeast(version, minimum) {
  const match = SEMVER_PREFIX.exec(version.replace(/^v/u, ""));
  if (match === null) return false;
  const actual = match.slice(1).map(Number);
  for (let index = 0; index < minimum.length; index += 1) {
    if (actual[index] > minimum[index]) return true;
    if (actual[index] < minimum[index]) return false;
  }
  return true;
}
function compatibilityDirection(input) {
  if (!SUPPORTED_PI_VERSIONS.has(input.piVersion)) {
    return "codeArbiter requires Pi 0.80.5 or 0.80.10; install a supported Pi version and run /ca-doctor.";
  }
  if (!atLeast(input.nodeVersion, MINIMUM_NODE)) {
    return "codeArbiter requires Node >=22.19.0 for Pi; upgrade Node and run /ca-doctor.";
  }
  if (input.pythonMajor !== 3) {
    return "codeArbiter requires Python 3; install Python 3 and run /ca-doctor.";
  }
  return null;
}

// src/runtime-resolver.ts
import { lstat, readFile, realpath as realpath2 } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname as dirname2, isAbsolute as isAbsolute2, relative as relative2, resolve as resolve2 } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
var PI_RUNTIME_DIAGNOSIS = "codeArbiter could not validate the active Pi CLI runtime; start from the Pi CLI and run /ca-doctor.";
var trustedIdentities = /* @__PURE__ */ new WeakSet();
function inside2(path, root) {
  const suffix = relative2(root, path);
  return suffix === "" || !suffix.startsWith("..") && !isAbsolute2(suffix);
}
function fail(cause) {
  throw new Error(PI_RUNTIME_DIAGNOSIS, cause === void 0 ? void 0 : { cause });
}
async function owningPackageRoot(file, expectedName) {
  let cursor = dirname2(file);
  while (true) {
    const candidate = resolve2(cursor, "package.json");
    try {
      const manifest = JSON.parse(await readFile(candidate, "utf8"));
      if (manifest.name !== expectedName) return fail();
      const canonicalRoot = await realpath2(cursor);
      if (!inside2(file, canonicalRoot) || !inside2(await realpath2(candidate), canonicalRoot)) return fail();
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
function identitiesMatch(left, right) {
  return left.cliEntry === right.cliEntry && left.manifestPath === right.manifestPath && left.moduleEntry === right.moduleEntry && left.packageRoot === right.packageRoot && left.version === right.version;
}
async function resolvePiRuntimeIdentity(cliCandidate) {
  try {
    const activeAnchor = process.argv[1];
    if (typeof activeAnchor !== "string" || activeAnchor.length === 0 || !isAbsolute2(activeAnchor)) return fail();
    const canonicalAnchor = await realpath2(activeAnchor);
    if (cliCandidate !== void 0) {
      if (!isAbsolute2(cliCandidate) || await realpath2(cliCandidate) !== canonicalAnchor) return fail();
    }
    const shippedModule = await realpath2(fileURLToPath(import.meta.url));
    const extensionPackageRoot = await owningPackageRoot(shippedModule, "ca-pi");
    let cursor = dirname2(canonicalAnchor);
    let manifest;
    let manifestPath = "";
    while (true) {
      const candidate = resolve2(cursor, "package.json");
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
    const packageRoot = await realpath2(cursor);
    const canonicalManifest = await realpath2(manifestPath);
    if (!inside2(canonicalAnchor, packageRoot) || !inside2(canonicalManifest, packageRoot)) return fail();
    if (inside2(packageRoot, extensionPackageRoot)) return fail();
    const declaredBin = resolve2(packageRoot, binTarget(manifest));
    if (!inside2(declaredBin, packageRoot) || await realpath2(declaredBin) !== canonicalAnchor) return fail();
    if (!(await lstat(canonicalAnchor)).isFile()) return fail();
    const declaredExport = importTarget(manifest);
    if (!declaredExport.startsWith("./")) return fail();
    const requireFromPi = createRequire(resolve2(packageRoot, "package.json"));
    const moduleEntry = await realpath2(requireFromPi.resolve(declaredExport));
    if (!inside2(moduleEntry, packageRoot)) return fail();
    if (!(await lstat(moduleEntry)).isFile()) return fail();
    const identity2 = Object.freeze({
      cliEntry: canonicalAnchor,
      manifestPath: canonicalManifest,
      moduleEntry,
      packageRoot,
      version: manifest.version
    });
    trustedIdentities.add(identity2);
    return identity2;
  } catch (error) {
    if (error instanceof Error && error.message === PI_RUNTIME_DIAGNOSIS) throw error;
    return fail(error);
  }
}
async function loadPiRuntime(identity2) {
  try {
    if (!trustedIdentities.has(identity2)) return fail();
    const beforeImport = await resolvePiRuntimeIdentity(identity2.cliEntry);
    if (!identitiesMatch(identity2, beforeImport)) return fail();
    const runtime = await import(pathToFileURL(identity2.moduleEntry).href);
    const requiredFunctions = [
      "getAgentDir",
      "createBashToolDefinition",
      "createWriteToolDefinition",
      "createEditToolDefinition",
      "createReadToolDefinition"
    ];
    if (runtime.VERSION !== identity2.version || typeof runtime.ModelRegistry !== "function" || typeof runtime.SettingsManager !== "function" || requiredFunctions.some((name) => typeof runtime[name] !== "function")) return fail();
    const afterImport = await resolvePiRuntimeIdentity(identity2.cliEntry);
    if (!identitiesMatch(identity2, afterImport)) return fail();
    return {
      cliEntry: identity2.cliEntry,
      moduleEntry: identity2.moduleEntry,
      packageRoot: identity2.packageRoot,
      version: identity2.version,
      ModelRegistry: runtime.ModelRegistry,
      SettingsManager: runtime.SettingsManager,
      getAgentDir: runtime.getAgentDir,
      createBashToolDefinition: runtime.createBashToolDefinition,
      createWriteToolDefinition: runtime.createWriteToolDefinition,
      createEditToolDefinition: runtime.createEditToolDefinition,
      createReadToolDefinition: runtime.createReadToolDefinition
    };
  } catch (error) {
    if (error instanceof Error && error.message === PI_RUNTIME_DIAGNOSIS) throw error;
    return fail(error);
  }
}

// src/tool-guard.ts
import { randomUUID as randomUUID2 } from "node:crypto";
import { realpathSync as realpathSync2 } from "node:fs";

// src/notices.ts
import { createHash as createHash2 } from "node:crypto";
var MAX_NOTICE_BYTES = 16e3;
var TRUNCATED = "\n[codeArbiter notice truncated]";
function normalized(value) {
  return redactSecrets2(value).replace(/\r\n?/gu, "\n").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "\uFFFD").trim();
}
function identity(ruleId, value) {
  const normalizedRule = normalized(ruleId ?? "context");
  return createHash2("sha256").update(`${normalizedRule}\0${value}`, "utf8").digest("hex");
}
function owned(block, id) {
  if (block === null || typeof block !== "object" || Array.isArray(block)) return false;
  const value = block;
  return value.type === "text" && value.codearbiter?.kind === "codearbiter-notice" && value.codearbiter.version === 1 && value.codearbiter.id === id && typeof value.text === "string" && value.text.includes(`:${id} -->`);
}
function truncateBody(prefix, body) {
  if (Buffer.byteLength(prefix + body, "utf8") <= MAX_NOTICE_BYTES) return prefix + body;
  const budget = MAX_NOTICE_BYTES - Buffer.byteLength(prefix + TRUNCATED, "utf8");
  let kept = "";
  let used = 0;
  for (const character of body) {
    const size = Buffer.byteLength(character, "utf8");
    if (used + size > budget) break;
    kept += character;
    used += size;
  }
  return prefix + kept + TRUNCATED;
}
function applyToolResultNotice(event, response) {
  if (response.outcome !== "notice" && response.outcome !== "warn") return void 0;
  const raw = response.message ?? response.context;
  if (typeof raw !== "string" || raw.length === 0) return void 0;
  const body = normalized(raw);
  if (body.length === 0) return void 0;
  const id = identity(response.ruleId, body);
  const original = Array.isArray(event.content) ? event.content : [];
  if (original.some((block2) => owned(block2, id))) return void 0;
  const prefix = `<!-- codearbiter:pi-tool-result:${id} -->
`;
  const block = {
    type: "text",
    text: truncateBody(prefix, body),
    codearbiter: { kind: "codearbiter-notice", version: 1, id }
  };
  return { content: [...original, block] };
}

// src/tool-guard.ts
var STANDALONE_GENERATION = Object.freeze({});
function failTool(message) {
  throw new Error(safeDiagnostic(message));
}
function appendWarning(result, warning) {
  const content = Array.isArray(result.content) ? [...result.content] : [];
  if (!JSON.stringify(content).includes(warning)) content.push({ type: "text", text: warning });
  return { ...result, content };
}
function canonicalSnapshot(value, seen = /* @__PURE__ */ new Set(), depth = 0) {
  if (depth > 32) throw new TypeError("parameters exceed nesting limit");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("parameters contain a non-finite number");
    return value;
  }
  if (typeof value !== "object" || seen.has(value)) throw new TypeError("parameters are not acyclic JSON");
  seen.add(value);
  try {
    if (Array.isArray(value)) return Object.freeze(value.map((item) => canonicalSnapshot(item, seen, depth + 1)));
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) throw new TypeError("parameters contain a non-plain object");
    const output = {};
    for (const [key, item] of Object.entries(value)) {
      if (key === "__proto__" || key === "constructor" || key === "prototype") throw new TypeError("parameters contain an unsafe key");
      output[key] = canonicalSnapshot(item, seen, depth + 1);
    }
    return Object.freeze(output);
  } finally {
    seen.delete(value);
  }
}
function nativeSessionId(context) {
  const manager = context?.sessionManager;
  if (manager === void 0 || typeof manager.getSessionId !== "function") return void 0;
  try {
    const value = manager.getSessionId.call(manager);
    if (typeof value !== "string" || value.trim() === "" || value.length > 1024) return void 0;
    return value;
  } catch {
    return void 0;
  }
}
function fixedFallbackSessionId() {
  const fallback = randomUUID2();
  return (context) => nativeSessionId(context) ?? fallback;
}
function executionCwd(context, fallback) {
  return context !== null && typeof context === "object" && typeof context.cwd === "string" ? context.cwd : fallback;
}
function wrappedDefinition(factory, nativeFactory, category, cwd, bridge, boundGeneration, activeGeneration, isReady, sessionIdFor) {
  const original = factory(cwd);
  const executeNativeFromContext = async (toolCallId, params, signal, onUpdate, context) => {
    const currentCwd = executionCwd(context, cwd);
    const native = nativeFactory(currentCwd);
    return await native.execute(toolCallId, params, signal, onUpdate, context);
  };
  return {
    ...original,
    execute: async (toolCallId, params, signal, onUpdate, context) => {
      const generation = activeGeneration();
      if (generation === void 0 || generation !== boundGeneration || !isReady()) {
        if (generation !== void 0 && category !== "READ") {
          return failTool("codeArbiter enforcement is not ready; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, params, signal, onUpdate, context);
      }
      let approved;
      try {
        approved = canonicalSnapshot(params);
      } catch {
        return failTool("Pi tool parameters are not canonical JSON; mutation blocked; run /ca-doctor.");
      }
      let response;
      try {
        response = await bridge.call({
          version: 1,
          event: "tool_call",
          cwd,
          ...category === "READ" ? { sessionId: sessionIdFor(context) } : {},
          tool: original.name,
          input: approved
        }, signal ?? new AbortController().signal);
      } catch (error) {
        if (activeGeneration() === generation) throw error;
        if (category !== "READ") {
          return failTool("codeArbiter lifecycle changed while approval was pending; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, approved, signal, onUpdate, context);
      }
      if (activeGeneration() !== generation) {
        if (category !== "READ") {
          return failTool("codeArbiter lifecycle changed while approval was pending; mutation blocked; run /ca-doctor.");
        }
        return await executeNativeFromContext(toolCallId, approved, signal, onUpdate, context);
      }
      if (response.outcome === "block") return failTool(response.message ?? `Blocked by ${response.ruleId ?? "codeArbiter"}`);
      if (category !== "READ" && response.outcome === "warn") {
        return failTool(`Mutation bridge returned an advisory verdict; mutation blocked; run /ca-doctor.`);
      }
      const result = await original.execute(toolCallId, approved, signal, onUpdate, context);
      if (activeGeneration() !== generation) return result;
      if (category === "READ") {
        const patch = applyToolResultNotice(result, response);
        return patch === void 0 ? result : { ...result, ...patch };
      }
      if ((response.outcome === "warn" || response.outcome === "notice") && response.message !== void 0) {
        return appendWarning(result, response.message);
      }
      return result;
    }
  };
}
function wrapMissingBuiltins(pi, bridge, options, wrapped, definitions, definitionGenerations, activeGeneration = () => STANDALONE_GENERATION, isReady = () => true, sessionIdFor = fixedFallbackSessionId()) {
  const boundGeneration = activeGeneration() ?? STANDALONE_GENERATION;
  for (const name of ["bash", "write", "edit", "read"]) {
    if (wrapped.has(name) && definitionGenerations?.get(name) === boundGeneration) continue;
    const category = options.descriptor[name] ?? "OTHER";
    if (category === "OTHER") throw new Error(`Pi descriptor does not classify built-in ${name}; run /ca-doctor.`);
    const definition = wrappedDefinition(
      options.factories[name],
      (options.nativeFactories ?? options.factories)[name],
      category,
      options.cwd,
      bridge,
      boundGeneration,
      activeGeneration,
      isReady,
      sessionIdFor
    );
    pi.registerTool(definition);
    definitions?.set(name, definition);
    definitionGenerations?.set(name, boundGeneration);
    wrapped.add(name);
  }
}
var EnforcementInstaller = class {
  bootstrapInstalled = false;
  bootstrapActive = false;
  ready = false;
  guardInstalled = false;
  resultsInstalled = false;
  wrapped = /* @__PURE__ */ new Set();
  definitions = /* @__PURE__ */ new Map();
  definitionGenerations = /* @__PURE__ */ new Map();
  fallbackSessionId;
  lifecycleGeneration;
  sessionIdFor(context) {
    const native = nativeSessionId(context);
    if (native !== void 0) return native;
    this.fallbackSessionId ??= randomUUID2();
    return this.fallbackSessionId;
  }
  ensureBootstrap(pi, descriptor) {
    if (this.bootstrapInstalled) return;
    pi.on("tool_call", (event) => {
      if (!this.bootstrapActive || this.ready) return void 0;
      const name = typeof event.toolName === "string" ? event.toolName : "";
      if ((descriptor[name] ?? "OTHER") === "READ") return void 0;
      return {
        block: true,
        reason: "codeArbiter enforcement is not ready; this Pi tool is potentially mutating and is blocked; run /ca-doctor."
      };
    });
    this.bootstrapInstalled = true;
  }
  beginBlockedGeneration() {
    this.bootstrapActive = true;
    this.ready = false;
    this.fallbackSessionId = randomUUID2();
    this.lifecycleGeneration = Object.freeze({});
  }
  beginActivation() {
    this.beginBlockedGeneration();
  }
  beginBootstrap() {
    this.beginBlockedGeneration();
  }
  markReady() {
    if (this.bootstrapActive) this.ready = true;
  }
  deactivate() {
    this.bootstrapActive = false;
    this.ready = false;
    this.fallbackSessionId = void 0;
    this.lifecycleGeneration = void 0;
  }
  ensureGuard(pi, descriptor, wrapperSourcePath) {
    if (this.guardInstalled) return;
    guardUnknownTools(pi, descriptor, wrapperSourcePath, () => this.bootstrapActive);
    this.guardInstalled = true;
  }
  ensureResults(pi, bridge, descriptor) {
    if (this.resultsInstalled) return;
    bridgeToolResults(pi, bridge, descriptor, () => this.lifecycleGeneration);
    this.resultsInstalled = true;
  }
  ensureBuiltins(pi, bridge, options) {
    wrapMissingBuiltins(
      pi,
      bridge,
      options,
      this.wrapped,
      this.definitions,
      this.definitionGenerations,
      () => this.lifecycleGeneration,
      () => this.ready,
      (context) => this.sessionIdFor(context)
    );
  }
  async runDoctorWrapperSelfTest(signal) {
    const bash = this.definitions.get("bash");
    if (bash === void 0) throw new Error("The active Pi bash wrapper is unavailable; run /ca-doctor.");
    return await bash.execute(
      "codearbiter-doctor-wrapper-self-test",
      { command: "git add --all --dry-run" },
      signal ?? new AbortController().signal
    );
  }
};
function samePath(left, right) {
  const equal = (a, b) => process.platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b;
  if (equal(left, right)) return true;
  try {
    return equal(realpathSync2(left), realpathSync2(right));
  } catch {
    return false;
  }
}
function guardUnknownTools(pi, descriptor, wrapperSourcePath, isActive = () => true) {
  pi.on("tool_call", (event) => {
    if (!isActive()) return void 0;
    const name = typeof event.toolName === "string" ? event.toolName : "";
    const category = descriptor[name] ?? "OTHER";
    if (category === "OTHER") {
      return { block: true, reason: "An unknown Pi tool is potentially mutating and is blocked; classify it in the generated descriptor or run /ca-doctor." };
    }
    if (category === "READ") return void 0;
    const active = new Set(pi.getActiveTools());
    const info = pi.getAllTools().find((tool) => tool.name === name);
    if (!active.has(name) || info === void 0 || !samePath(info.sourceInfo.path, wrapperSourcePath)) {
      return { block: true, reason: `Governed Pi tool ${name} has source drift or no active final-execution wrapper; mutation blocked; run /ca-doctor.` };
    }
    return void 0;
  });
}
function bridgeToolResults(pi, bridge, descriptor, activeGeneration = () => STANDALONE_GENERATION) {
  pi.on("tool_result", async (event, context) => {
    const generation = activeGeneration();
    if (generation === void 0) return void 0;
    const name = typeof event.toolName === "string" ? event.toolName : "";
    const category = descriptor[name] ?? "OTHER";
    if (category !== "WRITE" && category !== "EDIT") return void 0;
    let response;
    try {
      response = await bridge.call({
        version: 1,
        event: "tool_result",
        cwd: context.cwd,
        tool: name,
        input: event.input,
        result: { content: event.content, isError: event.isError === true }
      }, context.signal ?? new AbortController().signal);
    } catch (error) {
      if (activeGeneration() !== generation) return void 0;
      throw error;
    }
    if (activeGeneration() !== generation) return void 0;
    if (response.outcome === "warn" && response.message !== void 0) {
      context.ui.notify(response.message, "warning");
    }
    return applyToolResultNotice(event, response);
  });
}

// src/child-extension.ts
var HANDSHAKE_COMMAND = "codearbiter-internal-child-handshake";
var NONCE = /^[0-9a-f]{32}$/u;
var HANDSHAKE_ARGS = /^([0-9a-f]{32}) ([0-9a-f]{32})$/u;
var CHILD_TOOLS = /* @__PURE__ */ new Set(["read", "bash", "edit", "write"]);
function fixedFailure(message) {
  return new Error(`codeArbiter child handshake ${message}; child remains blocked; run /ca-doctor.`);
}
function installChild(pi, dependencies) {
  const descriptor = dependencies.descriptor ?? { read: "READ", bash: "EXEC", edit: "EDIT", write: "WRITE" };
  const enforcement = new EnforcementInstaller();
  let consumed = false;
  let activeCwd = dependencies.cwd;
  let wrappersInstalled = false;
  enforcement.ensureBootstrap(pi, descriptor);
  enforcement.beginActivation();
  if (dependencies.wrapperSourcePath !== void 0) enforcement.ensureGuard(pi, descriptor, dependencies.wrapperSourcePath);
  if (dependencies.bridge !== void 0) enforcement.ensureResults(pi, dependencies.bridge, descriptor);
  const installWrappers = (cwd) => {
    if (dependencies.bridge === void 0 || dependencies.factories === void 0 || dependencies.wrapperSourcePath === void 0) return false;
    enforcement.ensureBuiltins(pi, dependencies.bridge, {
      cwd,
      descriptor,
      factories: dependencies.factories,
      nativeFactories: dependencies.nativeFactories ?? dependencies.factories,
      wrapperSourcePath: dependencies.wrapperSourcePath
    });
    wrappersInstalled = true;
    return true;
  };
  pi.on("session_start", (_event, context) => {
    activeCwd = context.cwd;
    enforcement.beginBootstrap();
    installWrappers(context.cwd);
  });
  pi.on("session_shutdown", () => {
    enforcement.deactivate();
    consumed = true;
  });
  pi.registerCommand(HANDSHAKE_COMMAND, {
    handler: async (args, context) => {
      if (dependencies.marker !== "1") throw fixedFailure("has no validated subagent marker");
      if (consumed) throw fixedFailure("nonce was already consumed");
      if (dependencies.expectedNonce === void 0) throw fixedFailure("capability is missing");
      if (!NONCE.test(dependencies.expectedNonce)) throw fixedFailure("capability is malformed");
      const framing = HANDSHAKE_ARGS.exec(args.trim());
      if (framing === null) throw fixedFailure("nonce or challenge is malformed");
      const [, nonce, challenge] = framing;
      if (nonce === void 0 || challenge === void 0) throw fixedFailure("nonce or challenge is malformed");
      if (nonce !== dependencies.expectedNonce) throw fixedFailure("nonce does not match the parent capability");
      consumed = true;
      const cwd = activeCwd ?? context.cwd;
      if (cwd !== void 0) installWrappers(cwd);
      if (!wrappersInstalled) throw fixedFailure("enforcement is unavailable");
      const activeTools = [...pi.getActiveTools()].sort();
      let projectTrusted;
      try {
        projectTrusted = context.isProjectTrusted?.() ?? true;
      } catch {
        throw fixedFailure("attestation context is unavailable");
      }
      if (context.mode !== "rpc" || context.hasUI !== true || context.ui.confirm === void 0 || projectTrusted !== false || typeof cwd !== "string" || cwd === "" || context.model === void 0 || typeof context.model.provider !== "string" || context.model.provider === "" || typeof context.model.id !== "string" || context.model.id === "" || new Set(activeTools).size !== activeTools.length || activeTools.some((tool) => !CHILD_TOOLS.has(tool) || descriptor[tool] === void 0)) {
        throw fixedFailure("attestation context is invalid");
      }
      const digest = childAttestationDigest({
        nonce,
        challenge,
        cwd,
        provider: context.model.provider,
        model: context.model.id,
        tools: activeTools,
        projectTrusted: false,
        mode: "rpc"
      });
      let confirmed;
      try {
        confirmed = await context.ui.confirm(CHILD_ATTESTATION_TITLE, digest, { timeout: CHILD_ATTESTATION_TIMEOUT_MS });
      } catch {
        throw fixedFailure("attestation confirmation failed");
      }
      if (!confirmed) throw fixedFailure("attestation confirmation was rejected");
      enforcement.markReady();
    }
  });
}
async function readChildCapability(source = createReadStream("", { fd: 3, autoClose: true })) {
  let value = "";
  let bytes = 0;
  try {
    for await (const chunk of source) {
      const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
      bytes += Buffer.byteLength(text, "utf8");
      if (bytes > 32) throw fixedFailure("capability is oversized");
      value += text;
    }
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("codeArbiter child handshake")) throw error;
    throw fixedFailure("capability pipe is unavailable");
  }
  if (!NONCE.test(value)) throw fixedFailure("capability is malformed");
  return value;
}
function loadToolClasses(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw fixedFailure("descriptor is unavailable");
  const allowed = /* @__PURE__ */ new Set(["EXEC", "WRITE", "EDIT", "READ", "OTHER"]);
  const descriptor = {};
  for (const [name, category] of Object.entries(value)) {
    if (name === "" || typeof category !== "string" || !allowed.has(category)) throw fixedFailure("descriptor is invalid");
    descriptor[name] = category;
  }
  return Object.freeze(descriptor);
}
async function codeArbiterPiChild(pi) {
  if (process.env.CODEARBITER_SUBAGENT !== "1") throw fixedFailure("has no validated subagent marker");
  const expectedNonce = await readChildCapability();
  const runtimeIdentity = await resolvePiRuntimeIdentity();
  const direction = compatibilityDirection({ piVersion: runtimeIdentity.version, nodeVersion: process.versions.node, pythonMajor: 3 });
  if (direction !== null) throw new Error(direction);
  const runtime = await loadPiRuntime(runtimeIdentity);
  const modulePath = await realpath3(fileURLToPath2(import.meta.url));
  let packageRoot = dirname3(modulePath);
  while (true) {
    try {
      const manifest = JSON.parse(await readFile2(resolve3(packageRoot, "package.json"), "utf8"));
      if (manifest.name === "ca-pi") break;
    } catch {
    }
    const parent = dirname3(packageRoot);
    if (parent === packageRoot) throw fixedFailure("could not locate the ca-pi package");
    packageRoot = parent;
  }
  const cwd = process.cwd();
  const python = resolvePythonCommand(process.platform, void 0, packageRoot, cwd);
  const gitExecutable = resolveGitExecutable(cwd);
  const descriptor = loadToolClasses(define_CODEARBITER_PI_TOOL_CLASSES_default);
  const bridge = new BridgeClient({
    bridgeScript: resolve3(packageRoot, "hooks", "pi-bridge.py"),
    packageRoot,
    pythonExecutable: python.executable,
    pythonPrefixArgs: python.prefixArgs,
    gitExecutable,
    toolClasses: descriptor
  });
  const factories = {
    bash: (root) => {
      const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted: false });
      return runtime.createBashToolDefinition(root, { commandPrefix: settings.getShellCommandPrefix(), shellPath: settings.getShellPath() });
    },
    read: (root) => {
      const settings = runtime.SettingsManager.create(root, runtime.getAgentDir(), { projectTrusted: false });
      return runtime.createReadToolDefinition(root, { autoResizeImages: settings.getImageAutoResize() });
    },
    edit: (root) => runtime.createEditToolDefinition(root),
    write: (root) => runtime.createWriteToolDefinition(root)
  };
  installChild(pi, {
    marker: process.env.CODEARBITER_SUBAGENT,
    expectedNonce,
    cwd,
    wrapperSourcePath: modulePath,
    descriptor,
    bridge,
    factories,
    nativeFactories: factories
  });
}
export {
  codeArbiterPiChild as default,
  installChild,
  readChildCapability
};
