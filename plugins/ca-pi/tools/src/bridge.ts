import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { accessSync, constants, realpathSync, statSync } from "node:fs";
import { appendFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, posix, relative, resolve, win32 } from "node:path";

import type { BridgePort, BridgeRequest, BridgeResponse, ToolCategory } from "./contracts.ts";
import { redactJson, safeDiagnostic } from "./redaction.ts";

const RESPONSE_KEYS = new Set(["version", "outcome", "ruleId", "message", "context", "resultPatch", "auditCode"]);
const OUTCOMES = new Set(["allow", "block", "warn", "notice"]);
type BridgeFailureDetail =
  | "path validation failed"
  | "request serialization failed"
  | "request overflow"
  | "cancelled"
  | "bridge launch failed"
  | "protocol overflow"
  | "timed out"
  | "bridge process failed"
  | "returned malformed protocol";

export interface BridgeClientOptions {
  bridgeScript: string;
  packageRoot: string;
  pythonExecutable?: string;
  pythonPrefixArgs?: readonly string[];
  gitExecutable?: string;
  toolClasses: Readonly<Record<string, ToolCategory>>;
  timeoutMs?: number;
  maxRequestBytes?: number;
  maxStreamBytes?: number;
}

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function minimalEnvironment(identities?: { git: string; python: string }): NodeJS.ProcessEnv {
  const allowed = ["SystemRoot", "WINDIR", "TEMP", "TMP"] as const;
  const env: NodeJS.ProcessEnv = { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" };
  for (const key of allowed) if (process.env[key] !== undefined) env[key] = process.env[key];
  if (identities !== undefined) {
    const pathApi = process.platform === "win32" ? win32 : posix;
    const searchDirectories = new Set([
      pathApi.dirname(identities.git),
      pathApi.dirname(identities.python),
    ]);
    const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
    if (process.platform === "win32" && systemRoot !== undefined && win32.isAbsolute(systemRoot)) {
      searchDirectories.add(win32.join(systemRoot, "System32"));
    }
    env.PATH = [...searchDirectories].join(process.platform === "win32" ? ";" : ":");
    env.CODEARBITER_GIT_EXECUTABLE = identities.git;
    env.CODEARBITER_PYTHON_EXECUTABLE = identities.python;
  }
  return env;
}

function canonicalExecutable(candidate: string, platform: NodeJS.Platform): string | undefined {
  const pathApi = platform === "win32" ? win32 : posix;
  if (!pathApi.isAbsolute(candidate)) return undefined;
  try {
    const canonical = realpathSync(candidate);
    if (!statSync(canonical).isFile()) return undefined;
    if (platform !== "win32") accessSync(canonical, constants.X_OK);
    return canonical;
  } catch {
    return undefined;
  }
}

function sameOrInside(path: string, root: string, platform: NodeJS.Platform): boolean {
  const pathApi = platform === "win32" ? win32 : posix;
  const suffix = pathApi.relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !pathApi.isAbsolute(suffix));
}

function trustedPathCandidate(
  basename: string,
  projectCwd: string,
  platform: NodeJS.Platform,
  pathValue: string,
): string | undefined {
  const pathApi = platform === "win32" ? win32 : posix;
  const separator = platform === "win32" ? ";" : ":";
  const canonicalProject = canonicalExecutable(projectCwd, platform) ?? (() => {
    try { return realpathSync(projectCwd); } catch { return pathApi.resolve(projectCwd); }
  })();
  for (const rawEntry of pathValue.split(separator)) {
    const entry = rawEntry.trim();
    if (entry === "" || !pathApi.isAbsolute(entry)) continue;
    let directory: string;
    try { directory = realpathSync(entry); } catch { continue; }
    const candidate = canonicalExecutable(pathApi.join(directory, basename), platform);
    if (candidate !== undefined && !sameOrInside(candidate, canonicalProject, platform)) return candidate;
  }
  return undefined;
}

export function resolveGitExecutable(
  projectCwd: string,
  platform: NodeJS.Platform = process.platform,
  pathValue: string = process.env.PATH ?? "",
): string {
  const name = platform === "win32" ? "git.exe" : "git";
  const executable = trustedPathCandidate(name, projectCwd, platform, pathValue);
  if (executable === undefined) {
    throw new Error("codeArbiter could not resolve an absolute trusted Git executable; run /ca-doctor.");
  }
  return executable;
}

function windowsTaskkillExecutable(): string | undefined {
  if (process.platform !== "win32") return undefined;
  const systemRoot = process.env.SystemRoot ?? process.env.WINDIR;
  if (systemRoot === undefined || !win32.isAbsolute(systemRoot)) return undefined;
  const candidate = canonicalExecutable(win32.join(systemRoot, "System32", "taskkill.exe"), "win32");
  if (candidate === undefined) return undefined;
  let canonicalRoot: string;
  try { canonicalRoot = realpathSync(systemRoot); } catch { return undefined; }
  return sameOrInside(candidate, canonicalRoot, "win32") ? candidate : undefined;
}

function validResponse(value: unknown): value is BridgeResponse {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !RESPONSE_KEYS.has(key))) return false;
  if (record.version !== 1 || typeof record.outcome !== "string" || !OUTCOMES.has(record.outcome)) return false;
  for (const key of ["ruleId", "message", "context", "auditCode"] as const) {
    if (record[key] !== undefined && typeof record[key] !== "string") return false;
  }
  return true;
}

function killTree(child: ReturnType<typeof spawn>, taskkillExecutable: string | undefined): void {
  if (child.pid === undefined) return;
  if (process.platform === "win32") {
    if (taskkillExecutable === undefined) {
      child.kill("SIGKILL");
      return;
    }
    spawnSync(taskkillExecutable, ["/pid", String(child.pid), "/t", "/f"], {
      env: minimalEnvironment(),
      shell: false,
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); }
}

function sanitizedResponse(response: BridgeResponse): BridgeResponse {
  return {
    ...response,
    ...(response.ruleId === undefined ? {} : { ruleId: safeDiagnostic(response.ruleId, 100) }),
    ...(response.message === undefined ? {} : { message: safeDiagnostic(response.message) }),
    ...(response.context === undefined ? {} : { context: safeDiagnostic(response.context, 16_000) }),
    ...(response.auditCode === undefined ? {} : { auditCode: safeDiagnostic(response.auditCode, 100) }),
    ...(response.resultPatch === undefined ? {} : { resultPatch: redactJson(response.resultPatch) }),
  };
}

export class BridgeClient implements BridgePort {
  private readonly ready: Promise<{ git: string; python: string; root: string; script: string; taskkill?: string }>;
  private readonly timeoutMs: number;
  private readonly maxRequestBytes: number;
  private readonly maxStreamBytes: number;

  constructor(private readonly options: BridgeClientOptions) {
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.maxRequestBytes = options.maxRequestBytes ?? 262_144;
    this.maxStreamBytes = options.maxStreamBytes ?? 1_048_576;
    this.ready = this.validatePaths();
  }

  private async validatePaths(): Promise<{ git: string; python: string; root: string; script: string; taskkill?: string }> {
    if (this.options.pythonExecutable === undefined || this.options.gitExecutable === undefined) {
      throw new Error("Python 3 or Git is unavailable");
    }
    if (!isAbsolute(this.options.pythonExecutable) || !isAbsolute(this.options.gitExecutable) || !isAbsolute(this.options.bridgeScript) || !isAbsolute(this.options.packageRoot)) {
      throw new Error("bridge paths must be absolute");
    }
    const [git, python, script, root] = await Promise.all([
      realpath(this.options.gitExecutable),
      realpath(this.options.pythonExecutable),
      realpath(this.options.bridgeScript),
      realpath(this.options.packageRoot),
    ]);
    if (canonicalExecutable(git, process.platform) === undefined || canonicalExecutable(python, process.platform) === undefined) {
      throw new Error("bridge executable identity is invalid");
    }
    if (!inside(script, root)) throw new Error("bridge script is outside the installed package");
    const taskkill = windowsTaskkillExecutable();
    if (process.platform === "win32" && taskkill === undefined) throw new Error("taskkill is unavailable");
    return { git, python, root, script, ...(taskkill === undefined ? {} : { taskkill }) };
  }

  private failure(request: BridgeRequest, detail: BridgeFailureDetail): BridgeResponse {
    const category = this.options.toolClasses[request.tool ?? ""] ?? "OTHER";
    const advisory = request.event !== "tool_call" || category === "READ";
    return {
      version: 1,
      outcome: advisory ? "warn" : "block",
      ruleId: "PI-BRIDGE",
      message: `codeArbiter Pi bridge ${safeDiagnostic(detail)}; ${advisory ? "continuing advisory operation; " : "mutation blocked; "}run /ca-doctor.`,
      auditCode: advisory ? "PI_BRIDGE_WARN" : "PI_BRIDGE_BLOCK",
    };
  }

  private async auditFailure(
    request: BridgeRequest,
    response: BridgeResponse,
    counts: { request: number; stdout: number; stderr: number },
  ): Promise<void> {
    const line = [
      `[${new Date().toISOString()}]`,
      "HOST: pi",
      `RULE: ${response.ruleId ?? "PI-BRIDGE"}`,
      `AUDIT: ${response.auditCode ?? "PI_BRIDGE_FAILURE"}`,
      `CORRELATION: ${randomUUID()}`,
      `REQUEST_BYTES: ${counts.request}`,
      `STDOUT_BYTES: ${counts.stdout}`,
      `STDERR_BYTES: ${counts.stderr}`,
    ].join(" | ") + "\n";
    try {
      await appendFile(resolve(request.cwd, ".codearbiter", "gate-events.log"), line, { encoding: "utf8" });
    } catch {
      // A bridge failure must retain its fail direction even if the audit sink is unavailable.
    }
  }

  private async failed(
    request: BridgeRequest,
    detail: BridgeFailureDetail,
    counts: { request: number; stdout: number; stderr: number } = { request: 0, stdout: 0, stderr: 0 },
  ): Promise<BridgeResponse> {
    const response = this.failure(request, detail);
    await this.auditFailure(request, response, counts);
    return response;
  }

  async call(request: BridgeRequest, signal: AbortSignal): Promise<BridgeResponse> {
    let paths: { git: string; python: string; root: string; script: string; taskkill?: string };
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
    let body: Buffer;
    try {
      body = Buffer.from(JSON.stringify(request), "utf8");
    } catch {
      return await this.failed(request, "request serialization failed");
    }
    if (body.byteLength > this.maxRequestBytes) return await this.failed(request, "request overflow", { request: body.byteLength, stdout: 0, stderr: 0 });
    if (signal.aborted) return await this.failed(request, "cancelled", { request: body.byteLength, stdout: 0, stderr: 0 });

    return await new Promise<BridgeResponse>((resolveResponse) => {
      let child: ReturnType<typeof spawn>;
      try {
        child = spawn(paths.python, [...(this.options.pythonPrefixArgs ?? []), paths.script], {
          cwd: paths.root,
          detached: process.platform !== "win32",
          env: minimalEnvironment({ git: paths.git, python: paths.python }),
          shell: false,
          stdio: ["pipe", "pipe", "pipe"],
          windowsHide: true,
        });
      } catch {
        void this.failed(
          request,
          "bridge launch failed",
          { request: body.byteLength, stdout: 0, stderr: 0 },
        ).then(resolveResponse, () => resolveResponse(this.failure(request, "bridge launch failed")));
        return;
      }
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let reason: BridgeFailureDetail | undefined;
      let settled = false;
      let finishing = false;
      const finish = (response: BridgeResponse) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        resolveResponse(response);
      };
      const failAndKill = (value: BridgeFailureDetail) => {
        if (reason !== undefined) return;
        reason = value;
        killTree(child, paths.taskkill);
      };
      const finishFailure = (detail: BridgeFailureDetail) => {
        if (settled || finishing) return;
        finishing = true;
        void this.failed(request, detail, { request: body.byteLength, stdout: stdoutBytes, stderr: stderrBytes })
          .then(finish, () => finish(this.failure(request, detail)));
      };
      const collect = (target: Buffer[], chunk: Buffer, stream: "stdout" | "stderr") => {
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
      child.stdout!.on("data", (chunk: Buffer) => collect(stdout, chunk, "stdout"));
      child.stderr!.on("data", (chunk: Buffer) => collect(stderr, chunk, "stderr"));
      child.on("error", () => finishFailure("bridge launch failed"));
      child.on("close", (code) => {
        if (reason !== undefined) return finishFailure(reason);
        if (code !== 0) return finishFailure("bridge process failed");
        const stdoutText = Buffer.concat(stdout).toString("utf8");
        let parsed: unknown;
        try { parsed = JSON.parse(stdoutText); } catch { return finishFailure("returned malformed protocol"); }
        if (!validResponse(parsed)) return finishFailure("returned malformed protocol");
        finish(sanitizedResponse(parsed));
      });
      child.stdin!.on("error", () => undefined);
      child.stdin!.end(body);
    });
  }
}

export interface PythonCommand {
  executable: string;
  prefixArgs: readonly string[];
}

export interface PythonProbeResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

export type PythonProbe = (executable: string, prefixArgs: readonly string[], cwd: string) => PythonProbeResult;

function systemPythonProbe(executable: string, prefixArgs: readonly string[], cwd: string): PythonProbeResult {
  const probe = spawnSync(executable, [...prefixArgs, "-c", "import sys; print(sys.version_info[0]); print(sys.executable)"], {
      cwd,
      encoding: "utf8",
      env: minimalEnvironment(),
      shell: false,
      timeout: 2_000,
      windowsHide: true,
  });
  return { status: probe.status, stdout: probe.stdout ?? "", stderr: probe.stderr ?? "" };
}

export function resolvePythonCommand(
  platform: NodeJS.Platform = process.platform,
  probe: PythonProbe = systemPythonProbe,
  searchCwd?: string,
  excludedProjectCwd?: string,
  pathValue: string = process.env.PATH ?? "",
): PythonCommand {
  const pathApi = platform === "win32" ? win32 : posix;
  const safeCwd = searchCwd ?? (platform === "win32" ? win32.parse(process.execPath).root : "/");
  if (!pathApi.isAbsolute(safeCwd)) {
    throw new Error("codeArbiter Python search cwd must be absolute; run /ca-doctor.");
  }
  const candidates: ReadonlyArray<readonly [string, readonly string[]]> = platform === "win32"
    ? [["py.exe", ["-3"]], ["python.exe", []], ["python3.exe", []]]
    : [["python3", []], ["python", []]];
  for (const [candidate, prefixArgs] of candidates) {
    const probedCandidate = probe === systemPythonProbe
      ? trustedPathCandidate(candidate, excludedProjectCwd ?? safeCwd, platform, pathValue)
      : candidate.replace(/\.exe$/u, "");
    if (probedCandidate === undefined) continue;
    const result = probe(probedCandidate, prefixArgs, safeCwd);
    const lines = result.stdout.trim().split(/\r?\n/u);
    const executable = lines[1] ?? "";
    const absolute = platform === "win32" ? win32.isAbsolute(executable) : posix.isAbsolute(executable);
    const canonical = absolute
      ? (probe === systemPythonProbe ? canonicalExecutable(executable, platform) : executable)
      : undefined;
    if (
      result.status === 0
      && lines[0] === "3"
      && canonical !== undefined
      && (probe !== systemPythonProbe || !sameOrInside(canonical, excludedProjectCwd ?? safeCwd, platform))
    ) {
      return { executable: canonical, prefixArgs: [] };
    }
  }
  throw new Error("codeArbiter could not resolve an absolute Python interpreter; run /ca-doctor.");
}
