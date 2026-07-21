// src/windows-supervisor.ts
import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";
import { createReadStream, createWriteStream } from "node:fs";
import { Socket } from "node:net";
var MAX_LAUNCH_BYTES = 3145728;
var MAX_CONTROL_BYTES = 16;
var MAX_ENV_ENTRIES = 256;
var MAX_ENV_BYTES = 262144;
var PROXY_DRAIN_MS = 500;
var START = "START\n";
var launchInput = createReadStream("", { fd: 4, autoClose: false });
var controlInput = createReadStream("", { fd: 5, autoClose: false });
var statusOutput = createWriteStream("", { fd: 6, autoClose: false });
var parentLeash = new Socket({ fd: 7, readable: true, writable: false });
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
  if (!exactObject(parsed, ["args", "command", "cwd", "env"])) throw new Error("invalid launch record");
  const { args, command, cwd, env } = parsed;
  if (typeof command !== "string" || !isAbsolute(command) || typeof cwd !== "string" || !isAbsolute(cwd) || !Array.isArray(args) || args.length > 256 || args.some((item) => typeof item !== "string" || Buffer.byteLength(item, "utf8") > 262144) || !Array.isArray(env) || env.length > MAX_ENV_ENTRIES) {
    throw new Error("invalid launch record");
  }
  let environmentBytes = 0;
  const environment = /* @__PURE__ */ Object.create(null);
  for (const entry of env) {
    if (!Array.isArray(entry) || entry.length !== 2) throw new Error("invalid launch record");
    const [key, value2] = entry;
    if (typeof key !== "string" || key.length === 0 || key.length > 256 || key.includes("\0") || Buffer.byteLength(key, "utf8") > 512 || typeof value2 !== "string" || value2.length > 32768 || value2.includes("\0") || Buffer.byteLength(value2, "utf8") > 65536 || Object.hasOwn(environment, key)) throw new Error("invalid launch record");
    environmentBytes += Buffer.byteLength(key, "utf8") + Buffer.byteLength(value2, "utf8");
    if (environmentBytes > MAX_ENV_BYTES) throw new Error("invalid launch record");
    environment[key] = value2;
  }
  return Object.freeze({
    args: Object.freeze([...args]),
    command,
    cwd,
    env: Object.freeze(environment)
  });
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
var failureReason;
var failClosed = () => {
  process.exitCode = 70;
  try {
    parentLeash.destroy();
  } catch {
  }
  try {
    launchInput.destroy();
  } catch {
  }
  try {
    controlInput.destroy();
  } catch {
  }
  try {
    statusOutput.destroy();
  } catch {
  }
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
  failureReason = "proto-overflow";
  const [launchText, control] = await Promise.all([
    boundedRead(launchInput, MAX_LAUNCH_BYTES),
    boundedRead(controlInput, MAX_CONTROL_BYTES)
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
    windowsHide: true
  });
  const capability = child.stdio[3];
  if (child.stdin === null || child.stdout === null || child.stderr === null || capability === null || capability === void 0 || typeof capability.write !== "function") {
    failureReason = "pipe-unavailable";
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
  failureReason = "spawn-error";
  await new Promise((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
  failureReason = "pid-invalid";
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
    await Promise.race([
      new Promise((resolveFlush) => {
        statusOutput.end(`REFUSED${failureReason === void 0 ? "" : ` ${failureReason}`}
`, () => resolveFlush());
      }),
      new Promise((resolveTimeout) => {
        setTimeout(resolveTimeout, PROXY_DRAIN_MS).unref?.();
      })
    ]);
  } catch {
  }
  failClosed();
}
