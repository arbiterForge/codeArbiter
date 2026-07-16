/** process-tree.ts - bounded cross-platform launch and child-tree cleanup. */

import { EventEmitter } from "node:events";
import { spawn } from "node:child_process";
import type { ChildProcess, ChildProcessWithoutNullStreams, SpawnOptions } from "node:child_process";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, win32 } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_GRACE_MS = 500;
const DEFAULT_VERIFY_MS = 2_000;
const DEFAULT_POLL_MS = 25;
const MAX_STEP_MS = 30_000;
const MAX_POLL_MS = 1_000;
const WINDOWS_JOB_READY_MS = 3_000;
const WINDOWS_NATIVE_EXIT_PRIORITY_MS = 50;
const WINDOWS_JOB_READY = "ATTACHED";
const WINDOWS_SUPERVISOR_START = "START\n";
const MAX_JOB_PROTOCOL_BYTES = 64;
const MAX_LAUNCH_PROTOCOL_BYTES = 262_144;

const WINDOWS_JOB_HELPER_SOURCE = String.raw`$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$source = @'
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class CodeArbiterJob {
  public const UInt32 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
  private const UInt32 PROCESS_TERMINATE = 0x0001;
  private const UInt32 PROCESS_SET_QUOTA = 0x0100;
  private const UInt32 PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
  private const UInt32 SYNCHRONIZE = 0x00100000;
  private const UInt32 INFINITE = 0xffffffff;
  private const UInt32 WAIT_OBJECT_0 = 0;

  [StructLayout(LayoutKind.Sequential)]
  private struct IO_COUNTERS {
    public UInt64 ReadOperationCount, WriteOperationCount, OtherOperationCount;
    public UInt64 ReadTransferCount, WriteTransferCount, OtherTransferCount;
  }
  [StructLayout(LayoutKind.Sequential)]
  private struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
    public Int64 PerProcessUserTimeLimit, PerJobUserTimeLimit;
    public UInt32 LimitFlags;
    public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
    public UInt32 ActiveProcessLimit;
    public Int64 Affinity;
    public UInt32 PriorityClass, SchedulingClass;
  }
  [StructLayout(LayoutKind.Sequential)]
  private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
    public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
    public IO_COUNTERS IoInfo;
    public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
  }
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, UInt32 length);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern IntPtr OpenProcess(UInt32 access, bool inherit, UInt32 pid);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern UInt32 WaitForMultipleObjects(UInt32 count, IntPtr[] handles, bool waitAll, UInt32 milliseconds);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool GetExitCodeProcess(IntPtr process, out UInt32 exitCode);
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern IntPtr CreateEvent(IntPtr attributes, bool manualReset, bool initialState, string name);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool SetEvent(IntPtr handle);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern UInt32 WaitForSingleObject(IntPtr handle, UInt32 milliseconds);
  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool CloseHandle(IntPtr handle);

  public static IntPtr CreateAndAssign(UInt32 pid) {
    IntPtr job = CreateJobObject(IntPtr.Zero, null);
    if (job == IntPtr.Zero) return IntPtr.Zero;
    var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    int size = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
    IntPtr memory = Marshal.AllocHGlobal(size);
    try {
      Marshal.StructureToPtr(info, memory, false);
      if (!SetInformationJobObject(job, 9, memory, (UInt32)size)) {
        CloseHandle(job); return IntPtr.Zero;
      }
    } finally { Marshal.FreeHGlobal(memory); }
    IntPtr process = OpenProcess(PROCESS_TERMINATE | PROCESS_SET_QUOTA, false, pid);
    if (process == IntPtr.Zero) { CloseHandle(job); return IntPtr.Zero; }
    try {
      if (!AssignProcessToJobObject(job, process)) { CloseHandle(job); return IntPtr.Zero; }
    } finally { CloseHandle(process); }
    return job;
  }

  public static IntPtr OpenWatch(UInt32 pid) {
    return OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
  }

  public static IntPtr StartStopReader() {
    IntPtr stop = CreateEvent(IntPtr.Zero, true, false, null);
    if (stop == IntPtr.Zero) return IntPtr.Zero;
    var reader = new Thread(() => {
      try { Console.In.ReadLine(); }
      finally { SetEvent(stop); }
    });
    reader.IsBackground = true;
    reader.Start();
    return stop;
  }

  public static Int32 WaitForRootOrParent(IntPtr root, IntPtr parent, IntPtr stop, out UInt32 exitCode) {
    exitCode = 0;
    UInt32 result = WaitForMultipleObjects(3, new [] { root, parent, stop }, false, INFINITE);
    if (result == WAIT_OBJECT_0) return GetExitCodeProcess(root, out exitCode) ? 0 : -1;
    if (result == WAIT_OBJECT_0 + 1) return 1;
    if (result == WAIT_OBJECT_0 + 2) return 2;
    return -1;
  }

  public static bool WaitForStop(IntPtr stop) { return WaitForSingleObject(stop, INFINITE) == WAIT_OBJECT_0; }
}
'@
try {
  Add-Type -TypeDefinition $source -Language CSharp | Out-Null
  $line = [Console]::In.ReadLine()
  if ($null -eq $line -or $line -notmatch '^([1-9][0-9]*) ([1-9][0-9]*)$') { exit 40 }
  [UInt32]$target = $Matches[1]
  [UInt32]$parent = $Matches[2]
  $job = [CodeArbiterJob]::CreateAndAssign($target)
  if ($job -eq [IntPtr]::Zero) { exit 41 }
  try {
    [Console]::Out.WriteLine('ATTACHED')
    [Console]::Out.Flush()
    $rootLine = [Console]::In.ReadLine()
    [UInt32]$root = 0
    if ($null -eq $rootLine -or -not [UInt32]::TryParse($rootLine, [ref]$root) -or $root -eq 0) { exit 43 }
    $rootHandle = [CodeArbiterJob]::OpenWatch($root)
    $parentHandle = [CodeArbiterJob]::OpenWatch($parent)
    $stopHandle = [CodeArbiterJob]::StartStopReader()
    if ($rootHandle -eq [IntPtr]::Zero -or $parentHandle -eq [IntPtr]::Zero -or $stopHandle -eq [IntPtr]::Zero) { exit 44 }
    try {
      [Console]::Out.WriteLine('WATCHING')
      [Console]::Out.Flush()
      [UInt32]$exitCode = 0
      $which = [CodeArbiterJob]::WaitForRootOrParent($rootHandle, $parentHandle, $stopHandle, [ref]$exitCode)
      if ($which -eq 0) {
        [Console]::Out.WriteLine("EXIT $exitCode")
        [Console]::Out.Flush()
        if (-not [CodeArbiterJob]::WaitForStop($stopHandle)) { exit 46 }
      } elseif ($which -ne 1 -and $which -ne 2) { exit 45 }
    } finally {
      if ($rootHandle -ne [IntPtr]::Zero) { [CodeArbiterJob]::CloseHandle($rootHandle) | Out-Null }
      if ($parentHandle -ne [IntPtr]::Zero) { [CodeArbiterJob]::CloseHandle($parentHandle) | Out-Null }
      if ($stopHandle -ne [IntPtr]::Zero) { [CodeArbiterJob]::CloseHandle($stopHandle) | Out-Null }
    }
  } finally { [CodeArbiterJob]::CloseHandle($job) | Out-Null }
} catch { exit 42 }
`;

const WINDOWS_JOB_HELPER_ENCODED = Buffer.from(WINDOWS_JOB_HELPER_SOURCE, "utf16le").toString("base64");

export const PROCESS_TREE_CLEANUP_REASONS = Object.freeze([
  "timeout", "cancelled", "protocol_error", "protocol_overflow", "startup_failure", "parent_shutdown",
] as const);
export type ProcessTreeCleanupReason = typeof PROCESS_TREE_CLEANUP_REASONS[number];
export type ProcessTreeCleanupState = "terminated" | "already_exited" | "refused" | "failed";

export interface ProcessTreeTarget { readonly pid?: number }
export interface ProcessTreeCleanupOptions { readonly graceMs?: number; readonly verifyMs?: number; readonly pollMs?: number }
export interface ProcessTreePlanOptions extends ProcessTreeCleanupOptions { readonly taskkillExecutable?: string }
export interface ProcessTreeCleanupResult {
  readonly reason: ProcessTreeCleanupReason;
  readonly state: ProcessTreeCleanupState;
  readonly escalated: boolean;
  readonly verified: boolean;
}
export interface ProcessTreeCleanup {
  ready(): Promise<boolean>;
  terminate(reason: ProcessTreeCleanupReason): Promise<ProcessTreeCleanupResult>;
}
export interface WindowsJobHelperArgv {
  readonly command: string;
  readonly args: readonly string[];
  readonly options: Readonly<{ shell: false; windowsHide: true }>;
}
export interface WindowsSupervisorLaunchPlan {
  readonly command: string;
  readonly args: readonly string[];
  readonly control: "START\n";
  readonly options: Readonly<Omit<SpawnOptions, "stdio"> & { readonly stdio: readonly string[] }>;
}
export interface ProcessTreeSpawnInput {
  readonly cwd: string;
  readonly env: NodeJS.ProcessEnv;
  readonly stdio: readonly ["pipe", "pipe", "pipe", "pipe"];
}
export type ManagedChildProcess = ChildProcessWithoutNullStreams;
export type ProcessTreeTerminationStep =
  | Readonly<{ kind: "signal-group"; pid: number; signal: "SIGTERM" | "SIGKILL" }>
  | Readonly<{ kind: "taskkill"; command: string; args: readonly string[]; options: Readonly<{ shell: false; windowsHide: true }>; timeoutMs: number }>
  | Readonly<{ kind: "close-job"; timeoutMs: number }>
  | Readonly<{ kind: "wait-until-exited" | "verify-exited"; timeoutMs: number }>;

interface NormalizedTiming { graceMs: number; verifyMs: number; pollMs: number }
type TaskkillOutcome = Readonly<{ state: "completed"; code: number | null }> | Readonly<{ state: "refused" | "timed_out" }>;
interface WindowsJobGuard {
  readonly ready: Promise<boolean>;
  readonly exitCode: Promise<number | undefined>;
  arm(pid: number): Promise<boolean>;
  close(timeoutMs: number): Promise<boolean>;
}
interface WindowsProcessMetadata {
  readonly rootPid: number;
  readonly guard: WindowsJobGuard;
  readonly ready: Promise<boolean>;
}
const windowsMetadata = new WeakMap<object, WindowsProcessMetadata>();

function positivePid(pid: number | undefined): pid is number { return Number.isSafeInteger(pid) && (pid ?? 0) > 0; }
function boundedDuration(value: number | undefined, fallback: number, label: string): number {
  const duration = value ?? fallback;
  if (!Number.isSafeInteger(duration) || duration < 1 || duration > MAX_STEP_MS) throw new Error(`${label} must be a bounded positive integer`);
  return duration;
}
function normalizedTiming(options: ProcessTreeCleanupOptions): NormalizedTiming {
  const graceMs = boundedDuration(options.graceMs, DEFAULT_GRACE_MS, "graceMs");
  const verifyMs = boundedDuration(options.verifyMs, DEFAULT_VERIFY_MS, "verifyMs");
  const pollMs = boundedDuration(options.pollMs, DEFAULT_POLL_MS, "pollMs");
  if (pollMs > MAX_POLL_MS || pollMs > Math.max(graceMs, verifyMs)) throw new Error("pollMs must be bounded by the cleanup windows");
  return { graceMs, verifyMs, pollMs };
}

export function processTreeSpawnOptions(platform: NodeJS.Platform = process.platform): Readonly<Pick<SpawnOptions, "detached" | "shell" | "windowsHide">> {
  return Object.freeze({ detached: platform !== "win32", shell: false, windowsHide: true });
}

export function processTreeTerminationPlan(platform: NodeJS.Platform, pid: number, options: ProcessTreePlanOptions = {}): readonly ProcessTreeTerminationStep[] {
  if (!positivePid(pid)) throw new Error("process-tree pid must be a positive integer");
  const timing = normalizedTiming(options);
  if (platform !== "win32") return Object.freeze([
    Object.freeze({ kind: "signal-group", pid: -pid, signal: "SIGTERM" as const }),
    Object.freeze({ kind: "wait-until-exited", timeoutMs: timing.graceMs }),
    Object.freeze({ kind: "signal-group", pid: -pid, signal: "SIGKILL" as const }),
    Object.freeze({ kind: "verify-exited", timeoutMs: timing.verifyMs }),
  ]);
  const taskkill = options.taskkillExecutable;
  if (taskkill === undefined || !win32.isAbsolute(taskkill)) throw new Error("Windows process-tree cleanup requires an absolute taskkill executable");
  return Object.freeze([
    Object.freeze({ kind: "taskkill", command: taskkill, args: Object.freeze(["/PID", String(pid), "/T"]), options: Object.freeze({ shell: false as const, windowsHide: true as const }), timeoutMs: timing.graceMs }),
    Object.freeze({ kind: "wait-until-exited", timeoutMs: timing.graceMs }),
    Object.freeze({ kind: "close-job", timeoutMs: timing.verifyMs }),
    Object.freeze({ kind: "verify-exited", timeoutMs: timing.verifyMs }),
  ]);
}

function pathInsideWindows(candidate: string, root: string): boolean {
  const suffix = win32.relative(root, candidate);
  return suffix === "" || (!suffix.startsWith("..") && !win32.isAbsolute(suffix));
}
function canonicalWindowsSystemFile(parts: readonly string[], basename: string): string | undefined {
  if (process.platform !== "win32") return undefined;
  const configuredRoot = process.env.SystemRoot ?? process.env.WINDIR;
  if (configuredRoot === undefined || !win32.isAbsolute(configuredRoot)) return undefined;
  try {
    const root = realpathSync(configuredRoot);
    const system32 = realpathSync(win32.join(root, "System32"));
    const parent = realpathSync(win32.join(system32, ...parts.slice(0, -1)));
    const candidate = realpathSync(win32.join(system32, ...parts));
    if (!statSync(candidate).isFile() || !pathInsideWindows(system32, root) || !pathInsideWindows(parent, system32)
      || !pathInsideWindows(candidate, parent) || win32.basename(candidate).toLowerCase() !== basename) return undefined;
    return candidate;
  } catch { return undefined; }
}
export function resolveWindowsTaskkillExecutable(): string | undefined { return canonicalWindowsSystemFile(["taskkill.exe"], "taskkill.exe"); }
export function resolveWindowsPowerShellExecutable(): string | undefined {
  return canonicalWindowsSystemFile(["WindowsPowerShell", "v1.0", "powershell.exe"], "powershell.exe");
}
export function windowsJobHelperArgv(powershellExecutable: string): WindowsJobHelperArgv {
  if (!win32.isAbsolute(powershellExecutable)) throw new Error("Windows Job Object helper requires an absolute PowerShell executable");
  return Object.freeze({
    command: powershellExecutable,
    args: Object.freeze(["-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", WINDOWS_JOB_HELPER_ENCODED]),
    options: Object.freeze({ shell: false as const, windowsHide: true as const }),
  });
}
export function windowsSupervisorLaunchPlan(nodePath: string, supervisorPath: string, childEnvironment: NodeJS.ProcessEnv): WindowsSupervisorLaunchPlan {
  if (!win32.isAbsolute(nodePath) || !win32.isAbsolute(supervisorPath) || win32.basename(supervisorPath).toLowerCase() !== "windows-supervisor.js") {
    throw new Error("Windows supervisor launch requires canonical absolute artifacts");
  }
  return Object.freeze({
    command: nodePath,
    args: Object.freeze([supervisorPath]),
    control: WINDOWS_SUPERVISOR_START,
    options: Object.freeze({
      cwd: dirname(supervisorPath),
      env: Object.freeze({ ...childEnvironment }),
      detached: false,
      shell: false,
      stdio: Object.freeze(["pipe", "pipe", "pipe", "pipe", "pipe", "pipe", "pipe", "pipe"]),
      windowsHide: true,
    }),
  });
}

function helperEnvironment(command: string): NodeJS.ProcessEnv {
  const environment: NodeJS.ProcessEnv = { PATH: dirname(command) };
  for (const key of ["SystemRoot", "WINDIR", "TEMP", "TMP"] as const) if (process.env[key] !== undefined) environment[key] = process.env[key];
  return environment;
}
function startWindowsJobGuard(pid: number, timing: NormalizedTiming): WindowsJobGuard | undefined {
  const powershell = resolveWindowsPowerShellExecutable();
  if (powershell === undefined) return undefined;
  const launch = windowsJobHelperArgv(powershell);
  let helper: ChildProcessWithoutNullStreams;
  try {
    helper = spawn(launch.command, [...launch.args], { cwd: dirname(launch.command), env: helperEnvironment(launch.command), shell: false, stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
  } catch { return undefined; }
  let closed = false;
  let intentional = false;
  let closePending: Promise<boolean> | undefined;
  let armed = false;
  let outputEnded = false;
  let outputBuffer = "";
  const outputLines: string[] = [];
  const outputWaiters: Array<(line?: string) => void> = [];
  let resolveExitCode!: (code?: number) => void;
  let exitCodeSettled = false;
  const exitCode = new Promise<number | undefined>((resolveExit) => { resolveExitCode = resolveExit; });
  const settleExitCode = (code?: number) => {
    if (exitCodeSettled) return;
    exitCodeSettled = true;
    resolveExitCode(code);
  };
  const finishOutput = () => {
    if (outputEnded) return;
    outputEnded = true;
    while (outputWaiters.length > 0) outputWaiters.shift()!(undefined);
    settleExitCode();
  };
  const readOutputLine = (timeoutMs?: number): Promise<string | undefined> => {
    if (outputLines.length > 0) return Promise.resolve(outputLines.shift());
    if (outputEnded) return Promise.resolve(undefined);
    return new Promise((resolveLine) => {
      let timer: NodeJS.Timeout | undefined;
      const finish = (line?: string) => {
        if (timer !== undefined) clearTimeout(timer);
        resolveLine(line);
      };
      outputWaiters.push(finish);
      if (timeoutMs !== undefined) timer = setTimeout(() => {
        const index = outputWaiters.indexOf(finish);
        if (index >= 0) outputWaiters.splice(index, 1);
        finish();
      }, timeoutMs);
    });
  };
  helper.stdout.setEncoding("utf8");
  helper.stdout.on("data", (chunk: string) => {
    if (outputEnded) return;
    outputBuffer += chunk;
    if (Buffer.byteLength(outputBuffer, "utf8") > MAX_JOB_PROTOCOL_BYTES) {
      finishOutput();
      try { helper.stdin.end(); } catch {}
      return;
    }
    let newline = outputBuffer.indexOf("\n");
    while (newline >= 0) {
      const line = outputBuffer.slice(0, newline).replace(/\r$/u, "");
      outputBuffer = outputBuffer.slice(newline + 1);
      const waiter = outputWaiters.shift();
      if (waiter === undefined) outputLines.push(line);
      else waiter(line);
      newline = outputBuffer.indexOf("\n");
    }
  });
  helper.stdout.once("end", finishOutput);
  helper.stdout.once("error", finishOutput);
  const helperClosed = new Promise<boolean>((resolveClosed) => {
    const finish = () => { if (!closed) { closed = true; finishOutput(); resolveClosed(true); } };
    helper.once("close", finish); helper.once("error", finish);
  });
  helper.stdin.on("error", () => undefined);
  const ready = new Promise<boolean>((resolveReady) => {
    let settled = false;
    let stderrBytes = 0;
    const finish = (accepted: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveReady(accepted);
      if (!accepted) { try { helper.stdin.end(); } catch {} try { helper.kill("SIGKILL"); } catch {} }
    };
    const timer = setTimeout(() => finish(false), Math.min(WINDOWS_JOB_READY_MS, timing.verifyMs));
    helper.stderr.on("data", (chunk: Buffer | string) => { stderrBytes += Buffer.byteLength(chunk); if (stderrBytes > MAX_JOB_PROTOCOL_BYTES) finish(false); });
    helper.once("close", () => { if (!intentional) finish(false); });
    helper.once("error", () => finish(false));
    void readOutputLine(Math.min(WINDOWS_JOB_READY_MS, timing.verifyMs)).then((line) => finish(line === WINDOWS_JOB_READY));
    try { helper.stdin.write(`${pid} ${process.pid}\n`, "utf8", (error) => { if (error) finish(false); }); } catch { finish(false); }
  });
  return Object.freeze({
    ready,
    exitCode,
    async arm(rootPid: number): Promise<boolean> {
      if (armed || !positivePid(rootPid) || !await ready || closed) return false;
      armed = true;
      const watched = readOutputLine(Math.min(WINDOWS_JOB_READY_MS, timing.verifyMs));
      const written = await new Promise<boolean>((resolveWrite) => {
        try { helper.stdin.write(`${rootPid}\n`, "utf8", (error) => resolveWrite(error === null || error === undefined)); }
        catch { resolveWrite(false); }
      });
      if (!written || await watched !== "WATCHING") return false;
      void readOutputLine().then((line) => {
        const match = line === undefined ? null : /^EXIT ([0-9]+)$/u.exec(line);
        const code = match === null ? undefined : Number(match[1]);
        settleExitCode(Number.isSafeInteger(code) && (code ?? -1) >= 0 && (code ?? 0) <= 0xffffffff ? code : undefined);
      });
      return true;
    },
    close(timeoutMs: number): Promise<boolean> {
      closePending ??= (async () => {
        intentional = true;
        if (!await ready) return false;
        if (closed) return true;
        try { helper.stdin.end(); } catch {}
        const graceful = await Promise.race([helperClosed, new Promise<boolean>((resolveTimeout) => setTimeout(() => resolveTimeout(false), timeoutMs))]);
        if (graceful) return true;
        try { helper.kill("SIGKILL"); } catch {}
        return await Promise.race([helperClosed, new Promise<boolean>((resolveTimeout) => setTimeout(() => resolveTimeout(false), Math.min(250, timeoutMs)))]);
      })();
      return closePending;
    },
  });
}

function waitSpawn(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.pid !== undefined) return Promise.resolve(true);
  return new Promise((resolveWait) => {
    const timer = setTimeout(() => resolveWait(false), timeoutMs);
    child.once("spawn", () => { clearTimeout(timer); resolveWait(true); });
    child.once("error", () => { clearTimeout(timer); resolveWait(false); });
  });
}
export function writeBoundedControl(stream: NodeJS.WritableStream | null, value: string, timeoutMs: number): Promise<boolean> {
  if (stream === null || typeof stream.write !== "function" || typeof stream.end !== "function") return Promise.resolve(false);
  const boundedTimeoutMs = boundedDuration(timeoutMs, timeoutMs, "control write timeout");
  return new Promise((resolveWrite) => {
    let settled = false;
    const finish = (accepted: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveWrite(accepted);
    };
    const timer = setTimeout(() => {
      try { (stream as { destroy?(): void }).destroy?.(); } catch {}
      finish(false);
    }, boundedTimeoutMs);
    stream.once?.("error", () => finish(false));
    try { stream.end(value, "utf8", () => finish(true)); } catch { finish(false); }
  });
}
function readStarted(stream: NodeJS.ReadableStream | null, timeoutMs: number): Promise<number | undefined> {
  if (stream === null) return Promise.resolve(undefined);
  return new Promise((resolveStarted) => {
    let settled = false;
    let text = "";
    const finish = (pid?: number) => { if (!settled) { settled = true; clearTimeout(timer); resolveStarted(pid); } };
    const timer = setTimeout(() => finish(), timeoutMs);
    stream.setEncoding?.("utf8");
    stream.on("data", (chunk: string | Buffer) => {
      text += typeof chunk === "string" ? chunk : chunk.toString("utf8");
      if (Buffer.byteLength(text, "utf8") > MAX_JOB_PROTOCOL_BYTES) return finish();
      const newline = text.indexOf("\n");
      if (newline < 0) return;
      const match = /^STARTED ([1-9][0-9]*)$/u.exec(text.slice(0, newline).replace(/\r$/u, ""));
      const pid = match === null ? undefined : Number(match[1]);
      finish(positivePid(pid) && text.slice(newline + 1) === "" ? pid : undefined);
    });
    stream.once("end", () => { if (!/^STARTED [1-9][0-9]*\r?\n$/u.test(text)) finish(); });
    stream.once("error", () => finish());
  });
}
function canonicalSupervisorPath(): string {
  let cursor = dirname(realpathSync(fileURLToPath(import.meta.url)));
  while (true) {
    try {
      const manifest = JSON.parse(readFileSync(resolve(cursor, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") {
        const packageRoot = realpathSync(cursor);
        const candidate = realpathSync(resolve(cursor, "helpers", "windows-supervisor.js"));
        const suffix = relative(packageRoot, candidate);
        if (!statSync(candidate).isFile() || suffix.startsWith("..") || isAbsolute(suffix)
          || win32.basename(candidate).toLowerCase() !== "windows-supervisor.js") throw new Error("invalid supervisor artifact");
        return candidate;
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    const parent = dirname(cursor);
    if (parent === cursor) throw new Error("canonical Windows supervisor artifact unavailable");
    cursor = parent;
  }
}

class WindowsContainedProcess extends EventEmitter {
  readonly stdin;
  readonly stdout;
  readonly stderr;
  readonly stdio;
  readonly pid: number;
  exitCode: number | null = null;
  signalCode: NodeJS.Signals | null = null;
  private readonly supervisor: ChildProcessWithoutNullStreams;
  constructor(supervisor: ChildProcessWithoutNullStreams, pid: number, guard: WindowsJobGuard, rootPid: number) {
    super();
    this.supervisor = supervisor;
    this.pid = pid;
    this.stdin = supervisor.stdin;
    this.stdout = supervisor.stdout;
    this.stderr = supervisor.stderr;
    this.stdio = [supervisor.stdin, supervisor.stdout, supervisor.stderr, supervisor.stdio[3]];
    windowsMetadata.set(this, { guard, ready: Promise.resolve(true), rootPid });
    supervisor.once("error", (error) => this.emit("error", error));
    let closeForwarded = false;
    const waitReadableDrain = (stream: NodeJS.ReadableStream): Promise<void> => {
      if ((stream as { readableEnded?: boolean }).readableEnded === true) return Promise.resolve();
      return new Promise((resolveDrain) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolveDrain();
        };
        const timer = setTimeout(finish, 500);
        stream.once("end", finish);
        stream.once("close", finish);
        stream.once("error", finish);
      });
    };
    const closeSupervisorPipe = (index: number) => {
      const stream = (supervisor.stdio as unknown as Array<NodeJS.ReadableStream | NodeJS.WritableStream | null>)[index];
      try { (stream as NodeJS.WritableStream | null)?.end?.(); } catch {}
      try { (stream as { destroy?(): void } | null)?.destroy?.(); } catch {}
    };
    const drainFacadeOutput = async () => await Promise.all([
      waitReadableDrain(supervisor.stdout),
      waitReadableDrain(supervisor.stderr),
    ]);
    const handleSupervisorClose = (code: number | null, signal: NodeJS.Signals | null, drainBeforeJob = false) => {
      if (closeForwarded) return;
      closeForwarded = true;
      for (const index of [3, 4, 5, 6]) closeSupervisorPipe(index);
      const finalize = async () => {
        if (drainBeforeJob) await drainFacadeOutput();
        await guard.close(DEFAULT_VERIFY_MS);
        closeSupervisorPipe(7);
        await drainFacadeOutput();
      };
      void finalize()
        .finally(() => {
          this.exitCode = code;
          this.signalCode = signal;
          this.emit("close", code, signal);
        });
    };
    void guard.exitCode.then((code) => {
      if (code !== undefined) handleSupervisorClose(code, null, true);
    });
    const handleSupervisorExit = (code: number | null, signal: NodeJS.Signals | null) => {
      setTimeout(() => {
        if (!closeForwarded) handleSupervisorClose(code === null || code === 0 ? 72 : code, signal);
      }, WINDOWS_NATIVE_EXIT_PRIORITY_MS);
    };
    supervisor.once("exit", handleSupervisorExit);
    if (supervisor.exitCode !== null || supervisor.signalCode !== null) {
      queueMicrotask(() => handleSupervisorExit(supervisor.exitCode, supervisor.signalCode));
    }
  }
  kill(signal?: NodeJS.Signals | number): boolean { return this.supervisor.kill(signal); }
}

export async function spawnProcessTree(command: string, args: readonly string[], options: ProcessTreeSpawnInput): Promise<ManagedChildProcess> {
  const canonicalCommand = realpathSync(command);
  const canonicalCwd = realpathSync(options.cwd);
  if (!statSync(canonicalCommand).isFile() || !statSync(canonicalCwd).isDirectory()) {
    throw new Error("process-tree launch identities are invalid");
  }
  if (process.platform !== "win32") {
    return spawn(canonicalCommand, [...args], { ...processTreeSpawnOptions(process.platform), cwd: canonicalCwd, env: options.env, stdio: [...options.stdio] }) as ChildProcessWithoutNullStreams;
  }
  const timing = normalizedTiming({});
  const supervisorPath = canonicalSupervisorPath();
  const plan = windowsSupervisorLaunchPlan(canonicalCommand, supervisorPath, options.env);
  const launchRecord = JSON.stringify({ args: [...args], command: canonicalCommand, cwd: canonicalCwd });
  if (Buffer.byteLength(launchRecord, "utf8") > MAX_LAUNCH_PROTOCOL_BYTES) throw new Error("Windows supervisor launch record exceeds protocol limit");
  const supervisor = spawn(plan.command, [...plan.args], {
    ...plan.options,
    stdio: [...plan.options.stdio] as SpawnOptions["stdio"],
  }) as ChildProcessWithoutNullStreams;
  if (!await waitSpawn(supervisor, timing.verifyMs) || !positivePid(supervisor.pid)) { try { supervisor.kill("SIGKILL"); } catch {} throw new Error("Windows inert supervisor failed to start"); }
  const rootPid = supervisor.pid;
  const guard = startWindowsJobGuard(rootPid, timing);
  if (guard === undefined || !await guard.ready) { try { supervisor.kill("SIGKILL"); } catch {} throw new Error("Windows Job Object holder refused containment"); }
  const supervisorStdio = supervisor.stdio as unknown as Array<NodeJS.ReadableStream | NodeJS.WritableStream | null>;
  const launchPipe = supervisorStdio[4] as NodeJS.WritableStream | null;
  const controlPipe = supervisorStdio[5] as NodeJS.WritableStream | null;
  const statusPipe = supervisorStdio[6] as NodeJS.ReadableStream | null;
  const leashPipe = supervisorStdio[7] as NodeJS.WritableStream | null;
  if (leashPipe === null) { await guard.close(timing.verifyMs); throw new Error("Windows parent-death leash unavailable"); }
  leashPipe.on?.("error", () => undefined);
  const launchWritten = await writeBoundedControl(launchPipe, launchRecord, timing.verifyMs);
  const controlWritten = launchWritten && await writeBoundedControl(controlPipe, plan.control, timing.verifyMs);
  const actualPid = controlWritten ? await readStarted(statusPipe, timing.verifyMs) : undefined;
  if (!positivePid(actualPid) || actualPid === rootPid) {
    try { leashPipe.end(); } catch {}
    await guard.close(timing.verifyMs);
    try { supervisor.kill("SIGKILL"); } catch {}
    throw new Error("Windows contained Pi launch was refused");
  }
  if (!await guard.arm(actualPid)) {
    try { leashPipe.end(); } catch {}
    await guard.close(timing.verifyMs);
    try { supervisor.kill("SIGKILL"); } catch {}
    throw new Error("Windows contained Pi exit watch was refused");
  }
  return new WindowsContainedProcess(supervisor, actualPid, guard, rootPid) as unknown as ManagedChildProcess;
}

function processTreeIsAlive(platform: NodeJS.Platform, pid: number): boolean {
  try { process.kill(platform === "win32" ? pid : -pid, 0); return true; }
  catch (error) { const code = (error as NodeJS.ErrnoException).code; if (code === "ESRCH") return false; if (code === "EPERM") return true; throw error; }
}
async function waitUntilTreeExits(platform: NodeJS.Platform, pid: number, timeoutMs: number, pollMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (processTreeIsAlive(platform, pid)) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) return false;
    await new Promise<void>((resolveWait) => setTimeout(resolveWait, Math.min(pollMs, remaining)));
  }
  return true;
}
function result(reason: ProcessTreeCleanupReason, state: ProcessTreeCleanupState, escalated: boolean, verified: boolean): ProcessTreeCleanupResult {
  return Object.freeze({ escalated, reason, state, verified });
}
function runTaskkill(step: Extract<ProcessTreeTerminationStep, { kind: "taskkill" }>): Promise<TaskkillOutcome> {
  return new Promise((resolveRun) => {
    let settled = false;
    let helper: ChildProcess;
    const finish = (outcome: TaskkillOutcome) => { if (!settled) { settled = true; clearTimeout(timer); resolveRun(outcome); } };
    try { helper = spawn(step.command, [...step.args], { cwd: dirname(step.command), env: helperEnvironment(step.command), shell: false, stdio: "ignore", windowsHide: true }); }
    catch { resolveRun(Object.freeze({ state: "refused" })); return; }
    const timer = setTimeout(() => { try { helper.kill("SIGKILL"); } catch {} finish(Object.freeze({ state: "timed_out" })); }, step.timeoutMs);
    helper.once("error", () => finish(Object.freeze({ state: "refused" })));
    helper.once("close", (code) => finish(Object.freeze({ code, state: "completed" })));
  });
}
async function terminatePosix(pid: number, reason: ProcessTreeCleanupReason, timing: NormalizedTiming): Promise<ProcessTreeCleanupResult> {
  if (!processTreeIsAlive(process.platform, pid)) return result(reason, "already_exited", false, true);
  try { process.kill(-pid, "SIGTERM"); } catch { return result(reason, processTreeIsAlive(process.platform, pid) ? "refused" : "terminated", false, !processTreeIsAlive(process.platform, pid)); }
  if (await waitUntilTreeExits(process.platform, pid, timing.graceMs, timing.pollMs)) return result(reason, "terminated", false, true);
  try { process.kill(-pid, "SIGKILL"); } catch { if (processTreeIsAlive(process.platform, pid)) return result(reason, "refused", true, false); }
  const verified = await waitUntilTreeExits(process.platform, pid, timing.verifyMs, timing.pollMs);
  return result(reason, verified ? "terminated" : "failed", true, verified);
}
async function terminateWindows(target: ProcessTreeTarget, pid: number, reason: ProcessTreeCleanupReason, timing: NormalizedTiming): Promise<ProcessTreeCleanupResult> {
  const metadata = windowsMetadata.get(target as object);
  if (metadata === undefined || !await metadata.ready) return result(reason, "refused", false, false);
  const rootWasAlive = processTreeIsAlive("win32", pid);
  let graceful: TaskkillOutcome = Object.freeze({ state: "completed", code: 0 });
  if (rootWasAlive) {
    const taskkill = resolveWindowsTaskkillExecutable();
    if (taskkill === undefined) graceful = Object.freeze({ state: "refused" });
    else graceful = await runTaskkill(processTreeTerminationPlan("win32", pid, { ...timing, taskkillExecutable: taskkill })[0] as Extract<ProcessTreeTerminationStep, { kind: "taskkill" }>);
    await waitUntilTreeExits("win32", pid, timing.graceMs, timing.pollMs);
  }
  const stillAlive = processTreeIsAlive("win32", pid) || processTreeIsAlive("win32", metadata.rootPid);
  const jobClosed = await metadata.guard.close(timing.verifyMs);
  const actualGone = await waitUntilTreeExits("win32", pid, timing.verifyMs, timing.pollMs);
  const supervisorGone = await waitUntilTreeExits("win32", metadata.rootPid, timing.verifyMs, timing.pollMs);
  const verified = jobClosed && actualGone && supervisorGone;
  if (verified) return result(reason, rootWasAlive ? "terminated" : "already_exited", stillAlive, true);
  return result(reason, graceful.state === "refused" || !jobClosed ? "refused" : "failed", stillAlive, false);
}

async function terminate(target: ProcessTreeTarget, reason: ProcessTreeCleanupReason, options: ProcessTreeCleanupOptions): Promise<ProcessTreeCleanupResult> {
  if (!positivePid(target.pid)) return result(reason, "refused", false, false);
  try {
    const timing = normalizedTiming(options);
    return process.platform === "win32" ? await terminateWindows(target, target.pid, reason, timing) : await terminatePosix(target.pid, reason, timing);
  } catch { return result(reason, "failed", false, false); }
}
export function createProcessTreeCleanup(target: ProcessTreeTarget, options: ProcessTreeCleanupOptions = {}): ProcessTreeCleanup {
  let pending: Promise<ProcessTreeCleanupResult> | undefined;
  const ready = async () => {
    if (!positivePid(target.pid)) return false;
    if (process.platform !== "win32") return true;
    const metadata = windowsMetadata.get(target as object);
    return metadata !== undefined && await metadata.ready;
  };
  return Object.freeze({
    ready,
    terminate(reason: ProcessTreeCleanupReason): Promise<ProcessTreeCleanupResult> {
      pending ??= terminate(target, reason, options);
      return pending;
    },
  });
}
