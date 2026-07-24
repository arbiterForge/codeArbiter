/**
 * Inert Windows launch supervisor.
 *
 * The process is born before Job Object attachment but cannot launch Pi until
 * its dedicated control pipe receives one exact START record.  Launch metadata
 * arrives on a separate bounded pipe; Pi stdin/stdout/stderr/fd3 remain raw.
 */
import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";
import { createReadStream, createWriteStream } from "node:fs";
import { Socket } from "node:net";

import type { WindowsSupervisorRefusalReason } from "./process-tree.ts";

const MAX_LAUNCH_BYTES = 3_145_728;
const MAX_CONTROL_BYTES = 16;
const MAX_ENV_ENTRIES = 256;
const MAX_ENV_BYTES = 262_144;
const PROXY_DRAIN_MS = 500;
const START = "START\n";
const launchInput = createReadStream("", { fd: 4, autoClose: false });
const controlInput = createReadStream("", { fd: 5, autoClose: false });
const statusOutput = createWriteStream("", { fd: 6, autoClose: false });
// parentLeash is read via net.Socket rather than fs.createReadStream. Unlike launchInput/
// controlInput (which are read once to completion before this process ever tries to exit),
// parentLeash stays in flowing mode (parentLeash.resume() below) for the whole process
// lifetime so it can detect the parent's death by EOF. A flowing fs.ReadStream over a raw pipe
// fd services its reads via libuv's threadpool with a blocking, uncancellable syscall; once
// that read is in flight, this platform's process.exit() shutdown path waits on it and can
// hang indefinitely instead of terminating. net.Socket over the same fd uses overlapped
// (non-blocking, IOCP-based) I/O instead, so a still-pending read never blocks process.exit().
const parentLeash = new Socket({ fd: 7, readable: true, writable: false });

interface LaunchRecord {
  readonly command: string;
  readonly args: readonly string[];
  readonly cwd: string;
  readonly env: NodeJS.ProcessEnv;
}

function exactObject(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
}

function parseLaunch(value: string): LaunchRecord {
  let parsed: unknown;
  try { parsed = JSON.parse(value); }
  catch { throw new Error("invalid launch record"); }
  if (!exactObject(parsed, ["args", "command", "cwd", "env"])) throw new Error("invalid launch record");
  const { args, command, cwd, env } = parsed;
  if (typeof command !== "string" || !isAbsolute(command)
    || typeof cwd !== "string" || !isAbsolute(cwd)
    || !Array.isArray(args) || args.length > 256
    || args.some((item) => typeof item !== "string" || Buffer.byteLength(item, "utf8") > 262_144)
    || !Array.isArray(env) || env.length > MAX_ENV_ENTRIES) {
    throw new Error("invalid launch record");
  }
  let environmentBytes = 0;
  const environment: NodeJS.ProcessEnv = Object.create(null) as NodeJS.ProcessEnv;
  for (const entry of env) {
    if (!Array.isArray(entry) || entry.length !== 2) throw new Error("invalid launch record");
    const [key, value] = entry as unknown[];
    if (typeof key !== "string" || key.length === 0 || key.length > 256 || key.includes("\0")
      || Buffer.byteLength(key, "utf8") > 512 || typeof value !== "string" || value.length > 32_768
      || value.includes("\0") || Buffer.byteLength(value, "utf8") > 65_536
      || Object.hasOwn(environment, key)) throw new Error("invalid launch record");
    environmentBytes += Buffer.byteLength(key, "utf8") + Buffer.byteLength(value, "utf8");
    if (environmentBytes > MAX_ENV_BYTES) throw new Error("invalid launch record");
    environment[key] = value;
  }
  return Object.freeze({
    args: Object.freeze([...args] as string[]),
    command,
    cwd,
    env: Object.freeze(environment),
  });
}

function boundedRead(stream: NodeJS.ReadableStream, maximum: number): Promise<string> {
  return new Promise((resolve, reject) => {
    let bytes = 0;
    let value = "";
    stream.setEncoding?.("utf8");
    stream.on("data", (chunk: string | Buffer) => {
      const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
      bytes += Buffer.byteLength(text, "utf8");
      if (bytes > maximum) reject(new Error("bounded supervisor protocol overflow"));
      else value += text;
    });
    stream.once("end", () => resolve(value));
    stream.once("error", reject);
  });
}

let started = false;
let child: ReturnType<typeof spawn> | undefined;
// Stable short reason code for the terminal REFUSED status line; set immediately before each
// throw so the catch-all below can report it. A never-set reason falls back to the legacy bare
// "REFUSED\n" token, which the parent (process-tree.ts) still fully accepts.
let failureReason: WindowsSupervisorRefusalReason | undefined;
// Destroys every stream this module holds open before forcing exit, so no dangling read/write
// keeps a handle referenced past the point this process must be gone. (parentLeash itself is
// now a net.Socket rather than an fs.ReadStream specifically so its permanently-flowing read
// can never block the process.exit() call below — see the parentLeash comment above.)
const failClosed = () => {
  process.exitCode = 70;
  try { parentLeash.destroy(); } catch { /* Already gone. */ }
  try { launchInput.destroy(); } catch { /* Already gone. */ }
  try { controlInput.destroy(); } catch { /* Already gone. */ }
  try { statusOutput.destroy(); } catch { /* Already gone. */ }
  setImmediate(() => process.exit(70));
};

function waitForReadableDrain(stream: NodeJS.ReadableStream): Promise<void> {
  if ((stream as { readableEnded?: boolean }).readableEnded === true) return Promise.resolve();
  return new Promise((resolveDrain) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveDrain();
    };
    const timer = setTimeout(finish, PROXY_DRAIN_MS);
    stream.once("end", finish);
    stream.once("close", finish);
    stream.once("error", finish);
  });
}

function waitForWritableDrain(stream: NodeJS.WritableStream): Promise<void> {
  if ((stream as { writableNeedDrain?: boolean }).writableNeedDrain !== true) return Promise.resolve();
  return new Promise((resolveDrain) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveDrain();
    };
    const timer = setTimeout(finish, PROXY_DRAIN_MS);
    stream.once("drain", finish);
    stream.once("close", finish);
    stream.once("error", finish);
  });
}

parentLeash.once("end", failClosed);
parentLeash.once("error", failClosed);
parentLeash.resume();
process.once("disconnect", failClosed);

try {
  failureReason = "proto-overflow";
  const [launchText, control] = await Promise.all([
    boundedRead(launchInput, MAX_LAUNCH_BYTES),
    boundedRead(controlInput, MAX_CONTROL_BYTES),
  ]);
  failureReason = "launch-malformed";
  if (control !== START || started) throw new Error("invalid supervisor control state");
  started = true;
  const launch = parseLaunch(launchText);
  failureReason = "spawn-error";
  child = spawn(launch.command, [...launch.args], {
    cwd: launch.cwd,
    env: launch.env,
    detached: false,
    shell: false,
    stdio: ["pipe", "pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  const capability = child.stdio[3];
  if (child.stdin === null || child.stdout === null || child.stderr === null || capability === null || capability === undefined
    || typeof (capability as NodeJS.WritableStream).write !== "function") {
    failureReason = "pipe-unavailable";
    throw new Error("Pi proxy pipes unavailable");
  }
  let proxyReady = false;
  let exitFinalized = false;
  let observedExit: Readonly<{ code: number | null }> | undefined;
  let capabilityInput: ReturnType<typeof createReadStream> | undefined;
  const finalizeExit = (code: number | null) => {
    observedExit = Object.freeze({ code });
    if (!proxyReady || exitFinalized) return;
    exitFinalized = true;
    process.stdin.unpipe(child!.stdin!);
    capabilityInput!.unpipe(capability as NodeJS.WritableStream);
    capabilityInput!.destroy();
    child!.stdin!.destroy();
    (capability as { destroy?(): void }).destroy?.();
    void Promise.all([
      waitForReadableDrain(child!.stdout!),
      waitForReadableDrain(child!.stderr!),
    ]).then(async () => await Promise.all([
      waitForWritableDrain(process.stdout),
      waitForWritableDrain(process.stderr),
    ])).finally(() => process.exit(typeof code === "number" ? code : 71));
  };
  child.once("exit", finalizeExit);
  // Intentionally no separate child.once("error", failClosed) here: a spawn-time "error" is
  // caught below by the awaited promise's reject(), which unwinds through the outer catch block
  // so the REFUSED <reason> status line is written before the process exits. A second, earlier
  // "error" listener that called failClosed() directly used to race the outer catch's status
  // write — harmless while process.exit() itself hung, but a real bug now that fail-closed exit
  // is reliable: failClosed() could win the race and exit before REFUSED was ever written.
  failureReason = "spawn-error";
  await new Promise<void>((resolve, reject) => {
    child!.once("spawn", resolve);
    child!.once("error", reject);
  });
  failureReason = "pid-invalid";
  if (child.pid === undefined || !Number.isSafeInteger(child.pid) || child.pid <= 0) {
    throw new Error("Pi pid unavailable");
  }
  if ((child.exitCode !== null || child.signalCode !== null) && observedExit === undefined) {
    observedExit = Object.freeze({ code: child.exitCode });
  }
  process.stdin.pipe(child.stdin);
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  capabilityInput = createReadStream("", { fd: 3, autoClose: false });
  capabilityInput.pipe(capability as NodeJS.WritableStream);
  proxyReady = true;
  statusOutput.end(`STARTED ${child.pid}\n`);
  if (observedExit !== undefined) queueMicrotask(() => finalizeExit(observedExit!.code));
} catch {
  try {
    // Wait for the write to actually flush before destroying statusOutput in failClosed(), so
    // the parent reliably observes the REFUSED <reason> line rather than a bare EOF race. Bounded
    // by the same PROXY_DRAIN_MS budget used elsewhere for pipe drains, so a wedged status pipe
    // can never stop failClosed() from being reached — the flush is best-effort, not a gate.
    await Promise.race([
      new Promise<void>((resolveFlush) => {
        statusOutput.end(`REFUSED${failureReason === undefined ? "" : ` ${failureReason}`}\n`, () => resolveFlush());
      }),
      new Promise<void>((resolveTimeout) => { setTimeout(resolveTimeout, PROXY_DRAIN_MS).unref?.(); }),
    ]);
  } catch { /* Parent treats EOF as refusal. */ }
  failClosed();
}
