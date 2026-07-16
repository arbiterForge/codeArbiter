// src/windows-supervisor.ts
import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";
import { createReadStream, createWriteStream } from "node:fs";
var MAX_LAUNCH_BYTES = 262144;
var MAX_CONTROL_BYTES = 16;
var PROXY_DRAIN_MS = 500;
var START = "START\n";
var launchInput = createReadStream("", { fd: 4, autoClose: false });
var controlInput = createReadStream("", { fd: 5, autoClose: false });
var statusOutput = createWriteStream("", { fd: 6, autoClose: false });
var parentLeash = createReadStream("", { fd: 7, autoClose: false });
function exactObject(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
}
function parseLaunch(value) {
  let parsed;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("invalid launch record");
  }
  if (!exactObject(parsed, ["args", "command", "cwd"])) throw new Error("invalid launch record");
  const { args, command, cwd } = parsed;
  if (typeof command !== "string" || !isAbsolute(command) || typeof cwd !== "string" || !isAbsolute(cwd) || !Array.isArray(args) || args.length > 256 || args.some((item) => typeof item !== "string" || Buffer.byteLength(item, "utf8") > 65536)) {
    throw new Error("invalid launch record");
  }
  return Object.freeze({ args: Object.freeze([...args]), command, cwd });
}
function boundedRead(stream, maximum) {
  return new Promise((resolve, reject) => {
    let bytes = 0;
    let value = "";
    stream.setEncoding?.("utf8");
    stream.on("data", (chunk) => {
      const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
      bytes += Buffer.byteLength(text, "utf8");
      if (bytes > maximum) reject(new Error("bounded supervisor protocol overflow"));
      else value += text;
    });
    stream.once("end", () => resolve(value));
    stream.once("error", reject);
  });
}
var started = false;
var child;
var failClosed = () => {
  process.exitCode = 70;
  setImmediate(() => process.exit(70));
};
function waitForReadableDrain(stream) {
  if (stream.readableEnded === true) return Promise.resolve();
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
function waitForWritableDrain(stream) {
  if (stream.writableNeedDrain !== true) return Promise.resolve();
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
  const [launchText, control] = await Promise.all([
    boundedRead(launchInput, MAX_LAUNCH_BYTES),
    boundedRead(controlInput, MAX_CONTROL_BYTES)
  ]);
  if (control !== START || started) throw new Error("invalid supervisor control state");
  started = true;
  const launch = parseLaunch(launchText);
  child = spawn(launch.command, [...launch.args], {
    cwd: launch.cwd,
    env: process.env,
    detached: false,
    shell: false,
    stdio: ["pipe", "pipe", "pipe", "pipe"],
    windowsHide: true
  });
  const capability = child.stdio[3];
  if (child.stdin === null || child.stdout === null || child.stderr === null || capability === null || capability === void 0 || typeof capability.write !== "function") {
    throw new Error("Pi proxy pipes unavailable");
  }
  let proxyReady = false;
  let exitFinalized = false;
  let observedExit;
  let capabilityInput;
  const finalizeExit = (code) => {
    observedExit = Object.freeze({ code });
    if (!proxyReady || exitFinalized) return;
    exitFinalized = true;
    process.stdin.unpipe(child.stdin);
    capabilityInput.unpipe(capability);
    capabilityInput.destroy();
    child.stdin.destroy();
    capability.destroy?.();
    void Promise.all([
      waitForReadableDrain(child.stdout),
      waitForReadableDrain(child.stderr)
    ]).then(async () => await Promise.all([
      waitForWritableDrain(process.stdout),
      waitForWritableDrain(process.stderr)
    ])).finally(() => process.exit(typeof code === "number" ? code : 71));
  };
  child.once("exit", finalizeExit);
  child.once("error", failClosed);
  await new Promise((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
  if (child.pid === void 0 || !Number.isSafeInteger(child.pid) || child.pid <= 0) {
    throw new Error("Pi pid unavailable");
  }
  if ((child.exitCode !== null || child.signalCode !== null) && observedExit === void 0) {
    observedExit = Object.freeze({ code: child.exitCode });
  }
  process.stdin.pipe(child.stdin);
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  capabilityInput = createReadStream("", { fd: 3, autoClose: false });
  capabilityInput.pipe(capability);
  proxyReady = true;
  statusOutput.end(`STARTED ${child.pid}
`);
  if (observedExit !== void 0) queueMicrotask(() => finalizeExit(observedExit.code));
} catch {
  try {
    statusOutput.end("REFUSED\n");
  } catch {
  }
  failClosed();
}
