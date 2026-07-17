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

import type { WindowsSupervisorRefusalReason } from "./process-tree.ts";

const MAX_LAUNCH_BYTES = 262_144;
const MAX_CONTROL_BYTES = 16;
const PROXY_DRAIN_MS = 500;
const START = "START\n";
const launchInput = createReadStream("", { fd: 4, autoClose: false });
const controlInput = createReadStream("", { fd: 5, autoClose: false });
const statusOutput = createWriteStream("", { fd: 6, autoClose: false });
const parentLeash = createReadStream("", { fd: 7, autoClose: false });

interface LaunchRecord {
  readonly command: string;
  readonly args: readonly string[];
  readonly cwd: string;
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
  if (!exactObject(parsed, ["args", "command", "cwd"])) throw new Error("invalid launch record");
  const { args, command, cwd } = parsed;
  if (typeof command !== "string" || !isAbsolute(command)
    || typeof cwd !== "string" || !isAbsolute(cwd)
    || !Array.isArray(args) || args.length > 256
    || args.some((item) => typeof item !== "string" || Buffer.byteLength(item, "utf8") > 65_536)) {
    throw new Error("invalid launch record");
  }
  return Object.freeze({ args: Object.freeze([...args] as string[]), command, cwd });
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
const failClosed = () => {
  process.exitCode = 70;
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
    env: process.env,
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
  child.once("error", failClosed);
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
  try { statusOutput.end(`REFUSED${failureReason === undefined ? "" : ` ${failureReason}`}\n`); } catch { /* Parent treats EOF as refusal. */ }
  failClosed();
}
