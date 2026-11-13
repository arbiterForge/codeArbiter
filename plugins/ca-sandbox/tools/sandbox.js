#!/usr/bin/env node

// cli.ts
import { fileURLToPath } from "node:url";
import path2 from "node:path";
import { spawnSync } from "node:child_process";

// create.ts
import { randomBytes } from "node:crypto";
import { readdir } from "node:fs/promises";

// mounts.ts
var BindMountRejectedError = class extends Error {
  constructor(detail) {
    super(
      `ca-sandbox: bind mount rejected \u2014 a sandbox container never gets a host bind mount (${detail}). Only type=volume and type=tmpfs mounts are permitted.`
    );
    this.name = "BindMountRejectedError";
  }
};
function looksLikeShorthand(value) {
  return typeof value === "string" && value.includes(":");
}
function renderSpec(spec, index) {
  if (typeof spec === "string") {
    throw new BindMountRejectedError(
      `spec[${index}] is a "-v host:container" shorthand string ${JSON.stringify(spec)}`
    );
  }
  if (spec === null || typeof spec !== "object") {
    throw new BindMountRejectedError(`spec[${index}] is not a mount spec object (${String(spec)})`);
  }
  const asRecord = spec;
  if ("v" in asRecord || "volume" in asRecord) {
    const sh = asRecord.v ?? asRecord.volume;
    throw new BindMountRejectedError(
      `spec[${index}] uses the "-v" shorthand (${JSON.stringify(sh)})` + (looksLikeShorthand(sh) ? " which expresses a host:container bind" : "")
    );
  }
  const type = asRecord.type;
  if (type === "bind") {
    throw new BindMountRejectedError(`spec[${index}] is an explicit type=bind mount`);
  }
  if (type !== "volume" && type !== "tmpfs") {
    throw new BindMountRejectedError(
      `spec[${index}] has unsupported mount type ${JSON.stringify(type)} (expected "volume" or "tmpfs")`
    );
  }
  const parts = [`type=${type}`];
  if (type === "volume") {
    const v = spec;
    if (!v.source) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty source`);
    }
    if (!v.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty target`);
    }
    parts.push(`source=${v.source}`, `target=${v.target}`);
    if (v.readonly) parts.push("readonly");
  } else {
    const t = spec;
    if (!t.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=tmpfs requires a non-empty target`);
    }
    parts.push(`target=${t.target}`);
    if (t.readonly) parts.push("readonly");
  }
  return parts.join(",");
}
function buildMountArgs(specs) {
  if (!Array.isArray(specs)) {
    throw new Error("ca-sandbox: buildMountArgs expects an array of mount specs");
  }
  const values = specs.map((spec, i) => renderSpec(spec, i));
  const argv = [];
  for (const value of values) {
    argv.push("--mount", value);
  }
  return argv;
}

// docker.ts
import { spawn } from "node:child_process";
var DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };
var DEFAULT_DOCKER_TIMEOUT_MS = 12e4;
var DOCKER_OPERATION_TIMEOUTS_MS = Object.freeze({
  inspect: 3e4,
  ps: 3e4,
  images: 3e4,
  version: 3e4,
  info: 3e4,
  volume: 6e4,
  stop: 6e4,
  kill: 6e4,
  rm: 6e4,
  rmi: 12e4,
  network: 6e4,
  cp: 6e5,
  run: 9e5,
  create: 3e5,
  start: 3e5,
  exec: 18e5,
  build: 18e5,
  buildx: 18e5,
  pull: 18e5
});
function timeoutForArgs(args) {
  return DOCKER_OPERATION_TIMEOUTS_MS[args[0] ?? ""] ?? DEFAULT_DOCKER_TIMEOUT_MS;
}
var DOCKER_TIMEOUT_EXIT_CODE = 124;
var DOCKER_ABORT_EXIT_CODE = 130;
var DEFAULT_DOCKER_MAX_BUFFER = 64 * 1024 * 1024;
function runDocker(args, extra = {}, options = {}, call = {}) {
  const timeout = options.timeoutMs ?? timeoutForArgs(args);
  const spawnFn = options.spawn ?? spawn;
  const maxBuffer = options.maxBuffer ?? DEFAULT_DOCKER_MAX_BUFFER;
  const signal = call.signal;
  const label = `docker ${args[0] ?? ""}`;
  if (signal?.aborted) {
    return Promise.resolve({
      code: DOCKER_ABORT_EXIT_CODE,
      stdout: "",
      stderr: `ca-sandbox: \`${label}\` was cancelled before it started (issue #479).`,
      aborted: true
    });
  }
  return new Promise((resolve) => {
    let child;
    try {
      child = spawnFn("docker", args, { env: DOCKER_ENV, ...extra, ...call.env ? { env: call.env } : {} });
    } catch (e) {
      resolve({ code: 1, stdout: "", stderr: String(e) });
      return;
    }
    let stdout = "";
    let stderr = "";
    let bytes = 0;
    let killedBy;
    let settled = false;
    const kill = (why) => {
      if (killedBy !== void 0) return;
      killedBy = why;
      try {
        child.kill("SIGKILL");
      } catch {
      }
    };
    const collect = (which) => (chunk) => {
      const text = String(chunk);
      bytes += Buffer.byteLength(text);
      if (bytes > maxBuffer) {
        kill("overflow");
        return;
      }
      if (which === "out") stdout += text;
      else stderr += text;
    };
    child.stdout?.setEncoding?.("utf8");
    child.stderr?.setEncoding?.("utf8");
    child.stdout?.on("data", collect("out"));
    child.stderr?.on("data", collect("err"));
    const timer = setTimeout(() => kill("timeout"), timeout);
    timer.unref?.();
    const onAbort = () => kill("abort");
    signal?.addEventListener?.("abort", onAbort, { once: true });
    const settle = (r) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener?.("abort", onAbort);
      resolve(r);
    };
    child.on("error", (e) => settle({ code: 1, stdout: "", stderr: String(e) }));
    child.on("close", (code) => {
      if (killedBy === "timeout") {
        settle({
          code: DOCKER_TIMEOUT_EXIT_CODE,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` timed out after ${timeout}ms and was killed (issue #394).`,
          timedOut: true
        });
        return;
      }
      if (killedBy === "abort") {
        settle({
          code: DOCKER_ABORT_EXIT_CODE,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` was cancelled and killed (issue #479).`,
          aborted: true
        });
        return;
      }
      if (killedBy === "overflow") {
        settle({
          code: 1,
          stdout,
          stderr: `${stderr}ca-sandbox: \`${label}\` exceeded the ${maxBuffer}-byte output cap and was killed (issue #479).`,
          overflowed: true
        });
        return;
      }
      settle({ code: code ?? 1, stdout, stderr });
    });
  });
}
function defaultDockerRun(args, call = {}) {
  return runDocker(args, {}, {}, call);
}
function makeDockerRun(extra, options = {}) {
  return (args, call) => runDocker(args, extra, options, call);
}

// run.ts
var APP_DIR = "/work/repo";
var SANDBOX_LABEL = "ca.sandbox=1";
var SANDBOX_USER = "1000:1000";
var NETWORKED_POLICIES = /* @__PURE__ */ new Set();
function ordinaryNetworkCapability(requested) {
  return { requested, effective: "offline", available: requested === "offline" };
}
function hardeningFlags() {
  return [
    "--user",
    SANDBOX_USER,
    "--read-only",
    // --read-only makes a writable /tmp essential; the `--tmpfs <path>` short
    // form is the idiomatic, spec-named flag. (run.ts also renders a tmpfs /tmp
    // via buildMountArgs; the duplicate is harmless and robust across engines.)
    "--tmpfs",
    "/tmp",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--pids-limit",
    "512",
    "--memory",
    "4g",
    "--cpus",
    "2"
  ];
}
function buildRunArgs(image, volumeName, netPolicy, opts = {}) {
  if (!image) throw new Error("ca-sandbox: runContainer requires a non-empty image");
  if (!volumeName) throw new Error("ca-sandbox: runContainer requires a non-empty volume name");
  const mountSpecs = [
    { type: "volume", source: volumeName, target: APP_DIR },
    { type: "tmpfs", target: "/tmp" }
  ];
  const mountArgs = buildMountArgs(mountSpecs);
  const labels = [SANDBOX_LABEL, ...opts.extraLabels ?? []];
  const labelArgs = labels.flatMap((l) => ["--label", l]);
  const nameArgs = opts.namePrefix ? ["--name", `${opts.namePrefix}-${Math.random().toString(16).slice(2, 10)}`] : [];
  const networkArgs = NETWORKED_POLICIES.has(netPolicy) ? [] : ["--network", "none"];
  return [
    "run",
    "-d",
    ...nameArgs,
    ...mountArgs,
    "--workdir",
    APP_DIR,
    // The shared, security-load-bearing isolation block (defined once, also
    // spliced by claude-inside.ts so the two never drift).
    ...hardeningFlags(),
    ...networkArgs,
    ...labelArgs,
    image,
    "sleep",
    "infinity"
  ];
}
async function runContainer(image, volumeName, netPolicy, opts = {}) {
  const args = buildRunArgs(image, volumeName, netPolicy, opts);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const r = await dockerRun(args, { signal: opts.signal });
  if (r.code !== 0) {
    throw new Error(
      `ca-sandbox: docker run failed for ${image} (exit ${r.code})
${(r.stderr || r.stdout).slice(-2e3)}`
    );
  }
  return r.stdout.trim();
}

// build.ts
import { createHash } from "node:crypto";
import { spawn as spawn2 } from "node:child_process";
import { writeFile, readFile, rm, lstat, open, realpath, opendir } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
var IMAGE_PREFIX = "ca-sbx";
var DEPS_DIR = "/deps";
var APP_DIR2 = "/work/repo";
var NIXPACKS_APP_DIR = "/app";
var FALLBACK_BASE_IMAGE = "node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0";
var NIXPACKS_BASE_IMAGE = "ghcr.io/railwayapp/nixpacks@sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de";
var NIXPACKS_GENERATOR_ARGS = Object.freeze(["--no-error-without-start"]);
var NATIVE_RUNTIME_START = Object.freeze({ runImage: NIXPACKS_BASE_IMAGE, onlyIncludeFiles: Object.freeze(["."]) });
var MAX_NATIVE_INPUT_BYTES = 1024 * 1024;
var NIXPACKS_BUILD_PROFILE = Object.freeze({
  schema: 2,
  buildImage: NIXPACKS_BASE_IMAGE,
  generatorArgs: NIXPACKS_GENERATOR_ARGS,
  environmentPolicy: "minimal-os-v1",
  dockerfilePolicy: "all-image-refs-sha256-no-frontend-v2",
  inputPolicy: "no-project-config-or-existing-output-v1",
  providerPolicy: "explicit-node-python-go-mod-nonworkspace-rust-v2",
  nativeInputPolicy: "owned-utf8-max1MiB-rust-no-workspace-or-backslash-v1",
  nativeRuntime: NATIVE_RUNTIME_START
});
function nixpacksEnvironment() {
  const env = { MSYS_NO_PATHCONV: "1" };
  for (const key of [
    "PATH",
    "Path",
    "PATHEXT",
    "SystemRoot",
    "SYSTEMROOT",
    "WINDIR",
    "ComSpec",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL"
  ]) {
    if (process.env[key] !== void 0) env[key] = process.env[key];
  }
  return env;
}
function validateGeneratedImageInputs(dockerfile) {
  if (/^\s*#\s*syntax\s*=/im.test(dockerfile))
    throw new Error("ca-sandbox: unsupported Dockerfile frontend; pinned image profile required");
  const escape = /^\s*#\s*escape\s*=\s*(\S+)/im.exec(dockerfile);
  if (escape && escape[1] !== "\\")
    throw new Error("ca-sandbox: unsupported Dockerfile escape in pinned image profile");
  const stages = /* @__PURE__ */ new Map();
  let count = 0;
  const pinned = (image) => /^[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}$/.test(image);
  const source = (image, numeric) => {
    const stage = stages.get(image.toLowerCase());
    if (pinned(image) || stage !== void 0 && stage < count - 1 || numeric && /^(?:0|[1-9][0-9]*)$/.test(image) && Number(image) < count - 1) return;
    throw new Error("ca-sandbox: unpinned or unsupported external image source; pinned digest or prior stage required");
  };
  const active = dockerfile.split(/\r?\n/).filter((line) => !/^\s*#/.test(line)).join("\n");
  for (const line of active.replace(/\\[ \t]*\r?\n/g, " ").split(/\r?\n/)) {
    const tokens = line.trim().split(/\s+/);
    const instruction = tokens.shift()?.toUpperCase();
    if (instruction === "ONBUILD")
      throw new Error("ca-sandbox: unsupported deferred image instructions in pinned profile");
    if (instruction === "FROM") {
      if (tokens[0]?.startsWith("--platform=")) tokens.shift();
      if (tokens.length !== 1 && !(tokens.length === 3 && tokens[1].toUpperCase() === "AS" && /^[a-zA-Z][a-zA-Z0-9_.-]*$/.test(tokens[2])))
        throw new Error("ca-sandbox: unsupported FROM declaration; immutable image required");
      const image = tokens[0];
      if (!image || image.toLowerCase() !== "scratch" && !stages.has(image.toLowerCase()) && !pinned(image))
        throw new Error("ca-sandbox: unpinned external FROM image; every generated image requires a sha256 digest");
      if (tokens.length === 3) {
        const alias = tokens[2].toLowerCase();
        if (stages.has(alias)) throw new Error("ca-sandbox: ambiguous FROM stage alias");
        stages.set(alias, count);
      }
      count++;
      continue;
    }
    if (instruction !== "COPY" && instruction !== "ADD" && instruction !== "RUN") continue;
    const seen = /* @__PURE__ */ new Set();
    for (const flag of tokens) {
      if (!flag.startsWith("--")) break;
      if (/["'\\$`]/.test(flag)) throw new Error("ca-sandbox: unsupported quoted/dynamic image flag in pinned profile");
      const option = /^--([a-z-]+)(?:=(.+))?$/.exec(flag);
      if (!option) throw new Error("ca-sandbox: unsupported image flag in pinned profile");
      const [, key, value] = option;
      if (instruction === "RUN") {
        if (!value || !["mount", "network", "security"].includes(key))
          throw new Error("ca-sandbox: unsupported RUN flag in pinned image profile");
        if (key !== "mount") continue;
        const origins = value.split(",").filter((part) => part.split("=", 1)[0].toLowerCase() === "from");
        if (origins.length > 1) throw new Error("ca-sandbox: ambiguous mount image source in pinned profile");
        if (origins.length) {
          const origin = /^from=(.+)$/i.exec(origins[0]);
          if (!origin) throw new Error("ca-sandbox: unsupported mount image source in pinned profile");
          source(origin[1], false);
        }
      } else {
        if (!value && !["link", "parents"].includes(key))
          throw new Error("ca-sandbox: unsupported COPY/ADD flag in pinned image profile");
        if (key === "from") {
          if (seen.has(key)) throw new Error("ca-sandbox: ambiguous COPY image source in pinned profile");
          source(value, true);
        }
        seen.add(key);
      }
    }
  }
  if (!count) throw new Error("ca-sandbox: generated Dockerfile has no supported pinned FROM declaration");
}
var BUILD_ENV = { ...DOCKER_ENV, DOCKER_BUILDKIT: "1" };
function run(cmd, args, opts = {}) {
  const { timeoutMs, ...spawnOpts } = opts;
  const deadline = timeoutMs ?? (cmd === "docker" ? timeoutForArgs(args) : DEFAULT_DOCKER_TIMEOUT_MS);
  return new Promise((resolve) => {
    const c = spawn2(cmd, args, { env: DOCKER_ENV, ...spawnOpts });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let settled = false;
    const settle = (r) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(r);
    };
    const timer = setTimeout(() => {
      timedOut = true;
      try {
        c.kill("SIGKILL");
      } catch {
      }
      settle({
        code: DOCKER_TIMEOUT_EXIT_CODE,
        out: `${stdout}${stderr}ca-sandbox: \`${cmd} ${args[0] ?? ""}\` timed out after ${deadline}ms and was killed (issue #394).`,
        stdout,
        stderr,
        timedOut: true
      });
    }, deadline);
    timer.unref?.();
    c.stdout?.on("data", (d) => stdout += d);
    c.stderr?.on("data", (d) => stderr += d);
    c.on("error", (e) => settle({ code: 1, out: String(e), stdout: "", stderr: String(e) }));
    c.on("close", (code) => {
      if (timedOut) return;
      settle({ code: code ?? 1, out: stdout + stderr, stdout, stderr });
    });
  });
}
function imageTag(_repoDir, cacheKey) {
  return `${IMAGE_PREFIX}:v2-${cacheKey}`;
}
var CACHE_LABEL = "ca.sandbox.cache-key";
function reportBuildStage(reporter, stage) {
  try {
    const pending = reporter?.(stage);
    const thenable = pending;
    if (typeof thenable?.then === "function") {
      void Promise.resolve(pending).catch(() => void 0);
    }
  } catch {
  }
}
async function defaultImageInspect(tag) {
  const r = await run("docker", ["image", "inspect", tag]);
  if (r.code !== 0 && !/no such image/i.test(r.out)) throw new Error("ca-sandbox: cache observation unavailable");
  return r.code;
}
async function defaultImageIdentity(tag) {
  const r = await run("docker", ["image", "inspect", tag]);
  if (r.code !== 0) return null;
  try {
    const image = JSON.parse(r.stdout)[0];
    return { id: image.Id, cacheKey: image.Config?.Labels?.[CACHE_LABEL] };
  } catch {
    return null;
  }
}
async function defaultTargetPlatform() {
  const r = await run("docker", ["version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"]);
  const platform = r.stdout.trim();
  if (r.code !== 0 || !/^[a-z0-9]+\/[a-z0-9_]+(?:\/[a-z0-9]+)?$/.test(platform)) {
    throw new Error("ca-sandbox: target Docker platform observation unavailable; no cache reuse or build");
  }
  return platform;
}
function buildIdentityArgs(ctx) {
  if (!ctx.cacheKey || !ctx.platform) throw new Error("ca-sandbox: missing build identity");
  return ["--platform", ctx.platform, "--label", `${CACHE_LABEL}=${ctx.cacheKey}`];
}
function observedNixpacksVersion(output) {
  return /^(?:nixpacks\s+)?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$/.exec(output.trim())?.[1] ?? output.trim();
}
async function defaultNixpacksVersion() {
  const r = await run("nixpacks", ["--version"]);
  if (r.code !== 0) throw new Error(`nixpacks --version failed: ${r.out.trim()}`);
  return observedNixpacksVersion(r.stdout);
}
async function detectWslNixpacks(exec = run) {
  const probe = await exec("wsl.exe", [
    "bash",
    "-lc",
    'command -v nixpacks || echo "$HOME/.local/bin/nixpacks"'
  ]);
  if (probe.code !== 0) return null;
  const bin = probe.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop();
  if (!bin) return null;
  const ver = await exec("wsl.exe", ["--", bin, "--version"]);
  if (ver.code !== 0) return null;
  return { bin, version: observedNixpacksVersion(ver.stdout) };
}
async function defaultEnsureNixpacks(exec = run) {
  const probe = await exec("nixpacks", ["--version"]);
  if (probe.code === 0) {
    return { available: true, via: { via: "host" }, version: observedNixpacksVersion(probe.stdout) };
  }
  if (process.platform === "win32") {
    const wsl = await detectWslNixpacks(exec);
    if (wsl) {
      return {
        available: true,
        via: { via: "wsl", bin: wsl.bin },
        version: wsl.version,
        note: `Windows: nixpacks has no native binary; using the WSL bridge \u2014 nixpacks (${wsl.bin}, v${wsl.version}) generates the Dockerfile, host Docker builds it.`
      };
    }
  }
  return {
    available: false,
    note: "nixpacks is not installed (no host binary, no WSL bridge); fell back to a generated Dockerfile that mimics nixpacks (node/python only). Install nixpacks for the intended build path \u2014 see https://nixpacks.com for the install options; ca-sandbox deliberately does not install it for you."
  };
}
function generateDockerfile(stack) {
  const lines = [];
  lines.push(`FROM ${FALLBACK_BASE_IMAGE}`);
  lines.push(`ENV NODE_PATH=${DEPS_DIR}/node_modules`);
  lines.push(`ENV PYTHONPATH=${DEPS_DIR}/site-packages`);
  lines.push(`RUN mkdir -p ${DEPS_DIR} ${APP_DIR2}`);
  if (stack.node) {
    lines.push(`WORKDIR ${DEPS_DIR}`);
    lines.push("COPY package.json package.json");
    lines.push("COPY package-lock.json* npm-shrinkwrap.json* yarn.lock* ./");
    lines.push(`RUN npm install --omit=dev --prefix ${DEPS_DIR} || npm install --prefix ${DEPS_DIR}`);
  }
  if (stack.python) {
    lines.push(`RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*`);
    lines.push("COPY requirements.txt /tmp/requirements.txt");
    lines.push(`RUN pip3 install --no-cache-dir --target=${DEPS_DIR}/site-packages -r /tmp/requirements.txt`);
  }
  lines.push(`WORKDIR ${APP_DIR2}`);
  lines.push(`COPY . ${APP_DIR2}`);
  return lines.join("\n") + "\n";
}
function buildCapabilities(stack, nixpacksAvailable) {
  return {
    builder: nixpacksAvailable ? "nixpacks" : "dockerfile-fallback",
    supported: nixpacksAvailable || stack.node || stack.python,
    fallbackStacks: ["Node (package.json)", "Python (requirements.txt)"]
  };
}
async function detectStack(repoDir) {
  const { access } = await import("node:fs/promises");
  const has = async (f) => {
    try {
      await access(path.join(repoDir, f));
      return true;
    } catch {
      return false;
    }
  };
  return { node: await has("package.json"), python: await has("requirements.txt") };
}
async function inspectNativeProviderInputs(repoDir) {
  const rootInfo = await lstat(repoDir);
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) throw new Error("ca-sandbox: unsafe native input root");
  const root = await realpath(repoDir);
  const records = [];
  const owned = async (relative, kind, optional) => {
    let current = root;
    const parts = relative.split("/");
    for (let index = 0; index < parts.length; index++) {
      current = path.join(current, parts[index]);
      let info;
      try {
        info = await lstat(current);
      } catch (error) {
        if (optional && error.code === "ENOENT") return null;
        throw new Error(`ca-sandbox: native input unavailable: ${relative}`);
      }
      const last = index === parts.length - 1;
      if (info.isSymbolicLink() || path.relative(current, await realpath(current)) !== "" || (!last || kind === "directory" ? !info.isDirectory() : kind === "file" ? !info.isFile() || info.nlink !== 1 : !info.isDirectory() && (!info.isFile() || info.nlink !== 1)))
        throw new Error(`ca-sandbox: unsafe native input: ${relative}`);
      if (last) return { file: current, info };
    }
    throw new Error("ca-sandbox: unsafe native input path");
  };
  const read = async (relative) => {
    const found = await owned(relative, "file", true);
    if (!found) {
      records.push({ path: relative, absent: true });
      return void 0;
    }
    const before = found.info;
    if (before.size > MAX_NATIVE_INPUT_BYTES) throw new Error(`ca-sandbox: oversized native input: ${relative}`);
    const flags = constants.O_RDONLY | (process.platform === "win32" ? 0 : constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const handle = await open(found.file, flags);
    try {
      const unchanged = (info) => info.isFile() && !info.isSymbolicLink() && info.nlink === 1 && info.dev === before.dev && info.ino === before.ino && info.size === before.size && info.mtimeMs === before.mtimeMs && info.ctimeMs === before.ctimeMs;
      if (!unchanged(await handle.stat())) throw new Error(`ca-sandbox: changed native input: ${relative}`);
      const buffer = Buffer.alloc(MAX_NATIVE_INPUT_BYTES + 1);
      let length = 0;
      while (length < buffer.length) {
        const { bytesRead } = await handle.read(buffer, length, buffer.length - length, length);
        if (!bytesRead) break;
        length += bytesRead;
      }
      if (length > MAX_NATIVE_INPUT_BYTES) throw new Error(`ca-sandbox: oversized native input: ${relative}`);
      const after = await owned(relative, "file", false);
      if (length !== before.size || !unchanged(await handle.stat()) || !after || !unchanged(after.info))
        throw new Error(`ca-sandbox: changed native input: ${relative}`);
      const bytes = buffer.subarray(0, length);
      let text;
      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch {
        throw new Error(`ca-sandbox: invalid UTF-8 native input: ${relative}`);
      }
      records.push({ path: relative, sha256: createHash("sha256").update(bytes).digest("hex") });
      return text;
    } finally {
      await handle.close();
    }
  };
  const entries = async (relative, maximum, rootGoOnly = false) => {
    const dir = relative === "." ? { file: root } : await owned(relative, "directory", true);
    if (!dir) {
      records.push({ path: relative, absent: true });
      return;
    }
    const names = [];
    let count = 0;
    for await (const entry of await opendir(dir.file)) {
      if (++count > maximum) throw new Error("ca-sandbox: native input metadata limit exceeded");
      if (rootGoOnly && !entry.name.endsWith(".go")) continue;
      const rel = relative === "." ? entry.name : `${relative}/${entry.name}`;
      const item = await owned(rel, rootGoOnly ? "file" : "either", false);
      if (!item) throw new Error("ca-sandbox: native input metadata unavailable");
      names.push(`${entry.name}:${item.info.isDirectory() ? "directory" : "file"}`);
    }
    if (relative !== ".") await owned(relative, "directory", false);
    records.push({ path: relative, entries: names.sort() });
  };
  const go = await read("go.mod"), rust = await read("Cargo.toml");
  if (go === void 0 && rust === void 0) return void 0;
  const providers = [];
  if (go !== void 0) {
    providers.push("go");
    await read("go.sum");
    await entries(".", 4096, true);
    await entries("cmd", 256);
  }
  if (rust !== void 0) {
    if (rust.includes("workspace")) throw new Error("ca-sandbox: unsupported Rust workspace metadata; bounded non-workspace profile required");
    if (rust.includes("\\")) throw new Error("ca-sandbox: unsupported Rust backslash/escaped manifest; bounded ordinary UTF-8 profile required");
    providers.push("rust");
    for (const name of ["Cargo.lock", ".cargo/config.toml", "rust-toolchain", "rust-toolchain.toml"]) await read(name);
  }
  return { providers, sha256: createHash("sha256").update(JSON.stringify(records)).digest("hex") };
}
function relocationOverlay() {
  return [
    "",
    "# --- ca-sandbox relocation overlay (Spike A) ------------------------------",
    `# nixpacks bakes deps into ${NIXPACKS_APP_DIR}; relocate them OUT OF TREE to`,
    `# ${DEPS_DIR} so the live source volume at ${APP_DIR2} never shadows them, and`,
    "# reset nixpacks' bash-login ENTRYPOINT so `sleep infinity` runs as-is.",
    `RUN mkdir -p ${DEPS_DIR} && \\`,
    `    ( [ -d ${NIXPACKS_APP_DIR}/node_modules ] && mv ${NIXPACKS_APP_DIR}/node_modules ${DEPS_DIR}/node_modules || true ) && \\`,
    // nixpacks python installs into a venv at /opt/venv (not /app/.venv); copy the
    // first site-packages found to /deps/site-packages. /app/.venv is a fallback
    // for other nixpacks layouts. `break` so we copy exactly one (cp into a fresh
    // /deps/site-packages; a second copy would nest it).
    `    ( for sp in /opt/venv/lib/python*/site-packages ${NIXPACKS_APP_DIR}/.venv/lib/python*/site-packages; do [ -d "$sp" ] && cp -r "$sp" ${DEPS_DIR}/site-packages && break; done || true )`,
    `ENV NODE_PATH=${DEPS_DIR}/node_modules`,
    `ENV PYTHONPATH=${DEPS_DIR}/site-packages`,
    "ENTRYPOINT []",
    `WORKDIR ${APP_DIR2}`,
    `COPY . ${APP_DIR2}`,
    ""
  ].join("\n");
}
async function generateNixpacks(repoDir, nx, providers, signal) {
  const nativeRuntime = providers.some((provider) => provider === "go" || provider === "rust");
  const args = [...NIXPACKS_GENERATOR_ARGS, "--json-plan", JSON.stringify({
    buildImage: NIXPACKS_BASE_IMAGE,
    providers,
    ...nativeRuntime ? { start: NATIVE_RUNTIME_START } : {}
  })];
  if (nx.via === "host") {
    return run("nixpacks", ["build", repoDir, "--out", repoDir, ...args], { env: nixpacksEnvironment(), signal });
  }
  const wp = await run("wsl.exe", ["wslpath", "-a", repoDir.replace(/\\/g, "/")], { env: nixpacksEnvironment(), signal });
  if (wp.code !== 0)
    return { code: wp.code || 1, out: `wslpath failed: ${wp.out}`, stdout: "", stderr: wp.out };
  const wslRepo = wp.stdout.trim();
  const base = nx.distro ? ["-d", nx.distro] : [];
  return run("wsl.exe", [
    ...base,
    "--",
    nx.bin,
    "build",
    wslRepo,
    "--out",
    wslRepo,
    ...args
  ], { env: nixpacksEnvironment(), signal });
}
async function runNixpacksBuild(tag, ctx) {
  const nx = ctx.nixpacks ?? { via: "host" };
  const dfPath = path.join(ctx.repoDir, ".ca-sandbox.nixpacks.Dockerfile");
  for (const name of ["nixpacks.toml", "nixpacks.json", ".nixpacks", ".ca-sandbox.nixpacks.Dockerfile"]) {
    let present;
    try {
      await lstat(path.join(ctx.repoDir, name));
      present = true;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      present = false;
    }
    if (present) throw new Error(`ca-sandbox: unsupported Nixpacks input ${name}; project config and preexisting output are refused`);
  }
  const stack = await detectStack(ctx.repoDir);
  const nativeInputs = await inspectNativeProviderInputs(ctx.repoDir);
  if (JSON.stringify(nativeInputs) !== JSON.stringify(ctx.nativeProviderInputs))
    throw new Error("ca-sandbox: native provider inputs changed after cache admission; retry with a fresh observation");
  const providers = [...stack.node ? ["node"] : [], ...stack.python ? ["python"] : [], ...nativeInputs?.providers ?? []];
  if (!providers.length) throw new Error("ca-sandbox: supported Nixpacks providers require Node package.json, Python requirements.txt, Go go.mod or bounded non-workspace Rust Cargo.toml");
  try {
    const gen = await generateNixpacks(ctx.repoDir, nx, providers, ctx.signal);
    if (gen.code !== 0) return { code: gen.code, out: gen.out };
    const genPath = path.join(ctx.repoDir, ".nixpacks", "Dockerfile");
    let generated;
    try {
      generated = await readFile(genPath, "utf8");
    } catch (error) {
      return { code: 1, out: `nixpacks did not produce ${genPath}: ${String(error)}
${gen.out}` };
    }
    validateGeneratedImageInputs(generated);
    await writeFile(dfPath, generated + relocationOverlay());
    const built = await run("docker", ["build", ...buildIdentityArgs(ctx), "-t", tag, "-f", dfPath, ctx.repoDir], {
      env: BUILD_ENV,
      signal: ctx.signal
    });
    return { code: built.code, out: gen.out + "\n" + built.out };
  } finally {
    await rm(dfPath, { force: true }).catch(() => {
    });
    await rm(path.join(ctx.repoDir, ".nixpacks"), { recursive: true, force: true }).catch(() => {
    });
  }
}
async function verifyBuiltIdentity(result, tag, ctx) {
  if (result.code !== 0) return result;
  const identity = await defaultImageIdentity(tag);
  if (!identity || !/^sha256:[a-f0-9]{64}$/.test(identity.id) || identity.cacheKey !== ctx.cacheKey)
    return { code: 1, out: "build effect succeeded but image identity/provenance observation is unavailable; inspect the retained cache tag" };
  return { ...result, imageId: identity.id };
}
async function defaultRunBuild(tag, ctx) {
  if (ctx.builder === "nixpacks") {
    return verifyBuiltIdentity(await runNixpacksBuild(tag, ctx), tag, ctx);
  }
  const stack = await detectStack(ctx.repoDir);
  const dockerfileContent = generateDockerfile(stack);
  const dockerfile = path.join(ctx.repoDir, ".ca-sandbox.Dockerfile");
  await writeFile(dockerfile, dockerfileContent);
  try {
    const b = await run("docker", ["build", ...buildIdentityArgs(ctx), "-t", tag, "-f", dockerfile, ctx.repoDir], { signal: ctx.signal });
    return verifyBuiltIdentity({ code: b.code, out: b.out }, tag, ctx);
  } finally {
    await rm(dockerfile, { force: true }).catch(() => {
    });
  }
}
var defaultBuildDeps = () => ({
  imageInspect: defaultImageInspect,
  imageIdentity: defaultImageIdentity,
  targetPlatform: defaultTargetPlatform,
  detectStack,
  nativeProviderInputs: inspectNativeProviderInputs,
  runBuild: defaultRunBuild,
  nixpacksVersion: defaultNixpacksVersion,
  ensureNixpacks: defaultEnsureNixpacks
});
async function buildOrReuseImage(repoDir, dephash, deps = defaultBuildDeps(), reportStage, signal) {
  signal?.throwIfAborted();
  const notes = [];
  reportBuildStage(reportStage, "nixpacks-probe");
  const nixpacks = await deps.ensureNixpacks();
  const builder = nixpacks.available ? "nixpacks" : "dockerfile-fallback";
  if (deps.detectStack && !buildCapabilities(await deps.detectStack(repoDir), nixpacks.available).supported)
    throw new Error("ca-sandbox: unsupported fallback stack; install/provide an already usable nixpacks builder; fallback supports Node package.json or Python requirements.txt");
  if (nixpacks.note) notes.push(nixpacks.note);
  const version = nixpacks.available ? nixpacks.version ?? await deps.nixpacksVersion() : "fallback-v2";
  if (nixpacks.available && !/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error("ca-sandbox: malformed nixpacks version; no cache reuse or build");
  }
  const nativeProviderInputs = nixpacks.available && deps.nativeProviderInputs ? await deps.nativeProviderInputs(repoDir) : void 0;
  if (!deps.targetPlatform) throw new Error("ca-sandbox: target Docker platform observation unavailable");
  const platform = await deps.targetPlatform();
  if (!/^[a-z0-9]+\/[a-z0-9_]+(?:\/[a-z0-9]+)?$/.test(platform)) throw new Error("ca-sandbox: target Docker platform observation unavailable");
  const cacheKey = createHash("sha256").update(JSON.stringify({
    schema: 2,
    manifests: dephash,
    builder,
    version,
    platform,
    ...builder === "nixpacks" ? { nixpacksProfile: NIXPACKS_BUILD_PROFILE } : {},
    ...nativeProviderInputs ? { nativeProviderInputs } : {},
    fallback: generateDockerfile({ node: true, python: true }),
    relocation: relocationOverlay()
  })).digest("hex");
  const tag = imageTag(repoDir, cacheKey);
  reportBuildStage(reportStage, "image-inspect");
  const inspectCode = await deps.imageInspect(tag);
  if (inspectCode === 0 && deps.imageIdentity) {
    const identity = await deps.imageIdentity(tag);
    if (identity && /^sha256:[a-f0-9]{64}$/.test(identity.id) && identity.cacheKey === cacheKey) {
      return { tag, cacheKey, imageId: identity.id, reused: true, built: false, builder, notes };
    }
  }
  const ctx = { repoDir, builder, nixpacks: nixpacks.via, notes, cacheKey, platform, signal, nativeProviderInputs };
  signal?.throwIfAborted();
  reportBuildStage(reportStage, builder === "nixpacks" ? "nixpacks-build" : "dockerfile-build");
  const result = await deps.runBuild(tag, ctx);
  if (result.code !== 0) {
    throw new Error(
      `ca-sandbox: build failed for ${tag} (builder=${builder}, exit ${result.code})
` + result.out.slice(-2e3)
    );
  }
  return { tag, cacheKey, imageId: result.imageId, reused: false, built: true, builder, notes };
}

// dephash.ts
import { createHash as createHash2 } from "node:crypto";
var DEPHASH_LENGTH = 12;
function sha256Hex(data) {
  const buf = typeof data === "string" ? Buffer.from(data, "utf8") : Buffer.isBuffer(data) ? data : Buffer.from(data);
  return createHash2("sha256").update(buf).digest("hex");
}
function computeDepHash(manifestFiles, nixpacksVersion = "") {
  const seen = /* @__PURE__ */ new Set();
  const lines = [];
  for (const f of manifestFiles) {
    if (seen.has(f.path)) {
      throw new Error(`computeDepHash: duplicate manifest relpath "${f.path}"`);
    }
    seen.add(f.path);
    lines.push(`${f.path}\0${sha256Hex(f.bytes)}`);
  }
  lines.sort();
  const payload = lines.join("\n") + `
nixpacks=${nixpacksVersion}`;
  return createHash2("sha256").update(payload, "utf8").digest("hex").slice(0, DEPHASH_LENGTH);
}

// registry.ts
var SANDBOX_LABEL2 = "ca.sandbox=1";
var SANDBOX_ID_LABEL_KEY = "ca.sandbox.id";
function idLabel(id) {
  return `${SANDBOX_ID_LABEL_KEY}=${id}`;
}
function labelFilterArgs(labels) {
  const list = Array.isArray(labels) ? labels : [labels];
  return list.flatMap((l) => ["--filter", `label=${l}`]);
}
var scopeOf = (labels) => (Array.isArray(labels) ? labels : [labels]).map((l) => `label=${l}`).join(" ");
async function listContainersResult(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  const r = await dockerRun(["ps", "-a", "-q", "--no-trunc", ...labelFilterArgs(labels)]);
  return { code: r.code, items: r.code === 0 ? splitLines(r.stdout) : [], stderr: r.stderr, scope: scopeOf(labels) };
}
async function listVolumesResult(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  const r = await dockerRun(["volume", "ls", "-q", ...labelFilterArgs(labels)]);
  return { code: r.code, items: r.code === 0 ? splitLines(r.stdout) : [], stderr: r.stderr, scope: scopeOf(labels) };
}
async function listContainers(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  const result = await listContainersResult(labels, dockerRun);
  if (result.code !== 0) throw new Error(`ca-sandbox: container observation unavailable (exit ${result.code})`);
  return result.items;
}
async function listVolumes(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  const result = await listVolumesResult(labels, dockerRun);
  if (result.code !== 0) throw new Error(`ca-sandbox: volume observation unavailable (exit ${result.code})`);
  return result.items;
}
function splitLines(out) {
  return out.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
}
async function findSandbox(id, dockerRun = defaultDockerRun) {
  const labels = [SANDBOX_LABEL2, idLabel(id)];
  const containers = await listContainers(labels, dockerRun);
  const volumes = await listVolumes(labels, dockerRun);
  if (containers.length === 0 && volumes.length === 0) return null;
  return { id, containers, volumes };
}
async function resolveContainerId(id, dockerRun = defaultDockerRun) {
  const rec = await findSandbox(id, dockerRun);
  const containerId = rec?.containers[0];
  if (!containerId)
    throw new Error(
      `ca-sandbox: no running container for sandbox '${id}' (unknown id, or it was destroyed \u2014 see \`sandbox prune\`/\`list\`)`
    );
  return containerId;
}

// create.ts
var CLONE_IMAGE = "alpine/git:latest@sha256:77418e6e7c7f434c4a98eaff04ef16840cf03649c881c03948e3e213923e3136";
var APP_DIR3 = "/work/repo";
var VOLUME_PREFIX = "ca-sbx-vol";
var CLONE_TIMEOUT_MS = Number(process.env.CA_SANDBOX_CLONE_TIMEOUT_MS ?? 5 * 6e4);
var CP_TIMEOUT_MS = Number(process.env.CA_SANDBOX_CP_TIMEOUT_MS ?? 2 * 6e4);
var BuildStagingFailure = class extends Error {
  constructor(primaryFailure, cleanup) {
    const primary = primaryFailure === void 0 ? "" : `${primaryFailure instanceof Error ? primaryFailure.message : String(primaryFailure)}
`;
    super(
      `${primary}ca-sandbox: build staging cleanup unknown; helper=${cleanup.helper} (remove=${cleanup.removeCode}), staging=${cleanup.staging}`,
      primaryFailure === void 0 ? void 0 : { cause: primaryFailure }
    );
    this.primaryFailure = primaryFailure;
    this.cleanup = cleanup;
    this.name = "BuildStagingFailure";
  }
  primaryFailure;
  cleanup;
};
var CreateFailure = class extends Error {
  constructor(message, id, volumeName, cleanup, cause) {
    super(
      `${message}
ca-sandbox: cleanup ${cleanup.verified ? "verified absent" : "unknown"}; sandbox=${id}, volume=${volumeName}; containers=${cleanup.containers.join(",") || "unobserved"}`,
      cause === void 0 ? void 0 : { cause }
    );
    this.id = id;
    this.volumeName = volumeName;
    this.cleanup = cleanup;
    this.name = "CreateFailure";
  }
  id;
  volumeName;
  cleanup;
};
async function compensateCreate(id, volume, dockerRun) {
  const failures = [];
  const scope = [SANDBOX_LABEL2, idLabel(id)];
  const before = await listContainersResult(scope, dockerRun);
  if (before.code !== 0) failures.push(`container discovery unavailable (${before.code})`);
  const targets = before.code === 0 ? before.items : [];
  for (const target of targets) {
    const removed = await dockerRun(["rm", "-f", target]);
    if (removed.code !== 0) failures.push(`container removal unverified: ${target} (${removed.code})`);
  }
  const removedVolume = await dockerRun(["volume", "rm", "-f", volume]);
  if (removedVolume.code !== 0) failures.push(`volume removal unverified (${removedVolume.code})`);
  const after = await listContainersResult(scope, dockerRun);
  const volumes = await dockerRun(["volume", "ls", "-q", "--filter", `name=^${volume}$`]);
  const volumePresent = volumes.stdout.split(/\r?\n/).some((v) => v.trim() === volume);
  const verified = before.code === 0 && after.code === 0 && !after.items.length && volumes.code === 0 && !volumePresent;
  if (!verified) failures.push("resource absence not verified");
  return { verified, containers: after.code === 0 ? after.items : targets, volume, failures };
}
var InvalidRepoUrlError = class extends Error {
  constructor(url, reason) {
    super(
      `ca-sandbox: refusing to clone ${JSON.stringify(url)} \u2014 ${reason}. The repo url is untrusted input handed straight to git: only plain network remotes (https://, ssh://, or user@host:path) are allowed. git transport-helper syntax (ext::, fd::, file://) can execute commands or read host paths, and a value beginning with '-' would be parsed by git as a flag (argument injection) \u2014 both are rejected here.`
    );
    this.name = "InvalidRepoUrlError";
  }
};
function validateRepoUrl(url) {
  if (!url) throw new Error("ca-sandbox: createSandbox requires a repo url");
  if (url.startsWith("-")) {
    throw new InvalidRepoUrlError(url, "a url may not begin with '-' (git would read it as a flag)");
  }
  const httpsOk = /^https:\/\/\S+$/i.test(url);
  const sshUrlOk = /^ssh:\/\/\S+$/i.test(url);
  const scpOk = /^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^:].*$/.test(url);
  if (!(httpsOk || sshUrlOk || scpOk)) {
    throw new InvalidRepoUrlError(
      url,
      "only https://, ssh://, or user@host:path remotes are allowed"
    );
  }
}
function newSandboxId() {
  return randomBytes(6).toString("hex");
}
async function spawnAsync(cmd, args, timeoutMs, signal) {
  if (cmd !== "docker") throw new Error("ca-sandbox: unsupported clone process");
  const result = await makeDockerRun({}, { timeoutMs })(args, { signal });
  return { code: result.code, stderr: result.stderr.slice(-500) };
}
async function defaultCloneRepo(url, volumeName, id, signal) {
  return spawnAsync("docker", buildCloneArgs(url, volumeName, id), CLONE_TIMEOUT_MS, signal);
}
function buildCloneArgs(url, volumeName, id) {
  return [
    "run",
    "--rm",
    // Mount via the buildMountArgs chokepoint (architecture-006) so this caller is
    // covered by the bind-rejection guarantee and there is genuinely one mount-argv
    // path. Same volume spec as before -> byte-identical argv.
    ...buildMountArgs([{ type: "volume", source: volumeName, target: APP_DIR3 }]),
    "--label",
    SANDBOX_LABEL2,
    "--label",
    idLabel(id),
    CLONE_IMAGE,
    "clone",
    "--depth",
    "1",
    "--",
    url,
    APP_DIR3
  ];
}
function buildCpHelperCreateArgs(volumeName, helperName, id) {
  return [
    "create",
    "--name",
    helperName,
    "--label",
    SANDBOX_LABEL2,
    "--label",
    idLabel(id),
    // Same buildMountArgs chokepoint as buildCloneArgs (architecture-006).
    ...buildMountArgs([{ type: "volume", source: volumeName, target: APP_DIR3 }]),
    CLONE_IMAGE,
    "true"
  ];
}
async function defaultBuildImage(volumeName, id, signal, buildDeps) {
  const { mkdtemp: mkdtemp2, rm: rm2 } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const path3 = await import("node:path");
  const dir = await mkdtemp2(path3.join(tmpdir(), "ca-sbx-checkout-"));
  const helper = `ca-sbx-cp-${newSandboxId()}`;
  let helperCreated = false;
  let primaryFailure;
  try {
    const createResult = await makeDockerRun({}, { timeoutMs: CP_TIMEOUT_MS })(buildCpHelperCreateArgs(volumeName, helper, id), { signal });
    if (createResult.code !== 0) throw new Error(`ca-sandbox: helper creation unavailable (exit ${createResult.code}); target=${helper}`);
    helperCreated = true;
    const cpResult = await makeDockerRun({}, { timeoutMs: CP_TIMEOUT_MS })(["cp", `${helper}:${APP_DIR3}/.`, dir], { signal });
    if (cpResult.code !== 0) throw new Error(`ca-sandbox: checkout materialization unavailable (exit ${cpResult.code}); target=${helper}`);
    const manifests = await readManifests(dir, path3);
    const dephash = computeDepHash(manifests);
    return await buildOrReuseImage(dir, dephash, buildDeps, void 0, signal);
  } catch (error) {
    primaryFailure = error;
    throw error;
  } finally {
    const removed = helperCreated ? await defaultDockerRun(["rm", "-f", helper]) : { code: 1 };
    const observed = await defaultDockerRun(["ps", "-a", "-q", "--filter", `name=^/${helper}$`]);
    let stagingRemoved = false;
    try {
      await rm2(dir, { recursive: true, force: true });
      stagingRemoved = true;
    } catch {
    }
    if (observed.code !== 0 || observed.stdout.trim() || !stagingRemoved) {
      throw new BuildStagingFailure(primaryFailure, {
        helper,
        staging: dir,
        removeCode: removed.code,
        observationCode: observed.code,
        stagingRemoved
      });
    }
  }
}
var MANIFEST_NAMES = /* @__PURE__ */ new Set([
  "nixpacks.toml",
  "nixpacks.json",
  ".dockerignore",
  "package.json",
  "package-lock.json",
  "npm-shrinkwrap.json",
  "yarn.lock",
  "pnpm-lock.yaml",
  "requirements.txt",
  "Pipfile.lock",
  "poetry.lock",
  "go.mod",
  "go.sum",
  "Cargo.toml",
  "Cargo.lock"
]);
async function readManifests(dir, path3) {
  const { readFile: readFile2, lstat: lstat2 } = await import("node:fs/promises");
  const entries = await readdir(dir);
  const out = [];
  for (const name of entries) {
    if (!MANIFEST_NAMES.has(name)) continue;
    const inputPath = path3.join(dir, name);
    try {
      const entry = await lstat2(inputPath);
      if (!entry.isFile() || entry.isSymbolicLink()) {
        throw new Error("unsafe declared input");
      }
      out.push({ path: name, bytes: await readFile2(inputPath) });
    } catch (error) {
      if (error.code === "ENOENT") {
        try {
          await lstat2(inputPath);
        } catch (observed) {
          if (observed.code === "ENOENT") continue;
        }
      }
      const code = error.code ?? "unsafe input";
      throw new Error(`ca-sandbox: manifest observation unavailable: ${name} (${code}); cache/build admission refused`);
    }
  }
  return out;
}
async function createSandbox(url, opts = {}) {
  validateRepoUrl(url);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const cloneRepo = opts.cloneRepo ?? defaultCloneRepo;
  const buildImage = opts.buildImage ?? ((volume, id2, signal) => defaultBuildImage(volume, id2, signal, opts.buildDeps));
  const netPolicy = opts.netPolicy ?? "offline";
  const id = opts.id ?? newSandboxId();
  const volumeName = `${VOLUME_PREFIX}-${id}`;
  const sandboxLabels = [SANDBOX_LABEL2, idLabel(id), ...opts.extraLabels ?? []];
  const volLabelArgs = sandboxLabels.flatMap((l) => ["--label", l]);
  const mk = await dockerRun(
    ["volume", "create", ...volLabelArgs, volumeName],
    { signal: opts.signal }
  );
  if (mk.code !== 0) {
    throw new CreateFailure(
      `ca-sandbox: failed to create volume ${volumeName} (exit ${mk.code})`,
      id,
      volumeName,
      { verified: false, containers: [], volume: volumeName, failures: ["volume creation effect unknown; inspect before cleanup or a new create"] }
    );
  }
  try {
    const cloneRaw = await cloneRepo(url, volumeName, id, opts.signal);
    const cloneCode = typeof cloneRaw === "number" ? cloneRaw : cloneRaw.code;
    const cloneStderr = typeof cloneRaw === "number" ? "" : cloneRaw.stderr;
    if (cloneCode !== 0) {
      const hint = cloneStderr.trim() ? `
${cloneStderr.trim()}` : "";
      throw new Error(
        `ca-sandbox: clone of ${url} into ${volumeName} failed (exit ${cloneCode})${hint}`
      );
    }
    opts.signal?.throwIfAborted();
    const build = await buildImage(volumeName, id, opts.signal);
    opts.signal?.throwIfAborted();
    const containerId = await runContainer(build.imageId ?? build.tag, volumeName, netPolicy, {
      extraLabels: [idLabel(id), ...opts.extraLabels ?? []],
      namePrefix: `ca-sbx-${id}`,
      signal: opts.signal,
      dockerRun: opts.dockerRun ? (args, call) => opts.dockerRun(args, call) : void 0
    });
    return {
      id,
      volumeName,
      network: ordinaryNetworkCapability(netPolicy),
      image: build.tag,
      imageId: build.imageId,
      containerId,
      notes: build.notes
    };
  } catch (err) {
    const cleanup = await compensateCreate(id, volumeName, dockerRun);
    throw new CreateFailure(err instanceof Error ? err.message : String(err), id, volumeName, cleanup, err);
  }
}

// destroy.ts
var MAX_TEARDOWN_FAILURES = 25;
var MAX_DIAGNOSTIC_REFS = 25;
var MAX_FAILURE_MESSAGE_CHARS = 300;
var FailureLog = class {
  failures = [];
  count = 0;
  seen = /* @__PURE__ */ new Set();
  add(op, ref, code, stderr) {
    const message = oneLine(stderr);
    const listing = op === "list-containers" || op === "list-volumes";
    const identity = listing ? listingFingerprint(code, message) : `${op}\0${ref}\0${code}\0${message}`;
    if (this.seen.has(identity)) return;
    this.seen.add(identity);
    this.count += 1;
    if (this.failures.length >= MAX_TEARDOWN_FAILURES) return;
    this.failures.push({ op, ref, code, message });
  }
};
function listingFingerprint(code, message) {
  const shape = message.replace(/"[^"]*"/g, '"<url>"').replace(/\bhttps?:\/\/\S+/g, "<url>").replace(/\b\d+\b/g, "<n>");
  return `listing\0${code}\0${shape}`;
}
function oneLine(stderr) {
  const s = stderr.replace(/\s+/g, " ").trim();
  if (!s) return "(no stderr from docker)";
  return s.length > MAX_FAILURE_MESSAGE_CHARS ? `${s.slice(0, MAX_FAILURE_MESSAGE_CHARS)}...` : s;
}
async function removeEach(refs, kind, dockerRun, log) {
  const removed = [];
  for (const ref of refs) {
    const args = kind === "container" ? ["rm", "-f", ref] : ["volume", "rm", "-f", ref];
    const r = await dockerRun(args);
    if (r.code === 0) removed.push(ref);
    else log.add(kind === "container" ? "remove-container" : "remove-volume", ref, r.code, r.stderr);
  }
  return removed;
}
async function verifyScope(labels, dockerRun, log) {
  const c = await listContainersResult(labels, dockerRun);
  if (c.code !== 0) log.add("list-containers", c.scope, c.code, c.stderr);
  const v = await listVolumesResult(labels, dockerRun);
  if (v.code !== 0) log.add("list-volumes", v.scope, v.code, v.stderr);
  return { containers: c.items, volumes: v.items };
}
async function destroySandbox(id, opts = {}) {
  if (!id) throw new Error("ca-sandbox: destroySandbox requires a sandbox id");
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const labels = [SANDBOX_LABEL2, idLabel(id)];
  const log = new FailureLog();
  const containersList = await listContainersResult(labels, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const volumesList = await listVolumesResult(labels, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);
  const removedContainers = await removeEach(containersList.items, "container", dockerRun, log);
  const removedVolumes = [];
  const keptVolumes = [];
  if (opts.keepVolume) {
    keptVolumes.push(...volumesList.items);
  } else {
    removedVolumes.push(...await removeEach(volumesList.items, "volume", dockerRun, log));
  }
  const still = await verifyScope(labels, dockerRun, log);
  const survivingVolumes = opts.keepVolume ? [] : still.volumes.filter((v) => !keptVolumes.includes(v));
  const keptFromVerification = opts.keepVolume ? [.../* @__PURE__ */ new Set([...keptVolumes, ...still.volumes])] : keptVolumes;
  return {
    id,
    removedContainers,
    removedVolumes,
    keptVolumes: keptFromVerification,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers,
    remainingVolumes: survivingVolumes
  };
}
async function prune(opts = {}) {
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const log = new FailureLog();
  const containersList = await listContainersResult(SANDBOX_LABEL2, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const removedContainers = await removeEach(containersList.items, "container", dockerRun, log);
  const volumesList = await listVolumesResult(SANDBOX_LABEL2, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);
  const removedVolumes = await removeEach(volumesList.items, "volume", dockerRun, log);
  const targetedContainers = new Set(containersList.items);
  const targetedVolumes = new Set(volumesList.items);
  const still = await verifyScope(SANDBOX_LABEL2, dockerRun, log);
  return {
    removedContainers,
    removedVolumes,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers.filter((c) => targetedContainers.has(c)),
    remainingVolumes: still.volumes.filter((v) => targetedVolumes.has(v))
  };
}
function teardownIncomplete(r) {
  return r.failureCount > 0 || r.remainingContainers.length > 0 || r.remainingVolumes.length > 0;
}
function boundedRefs(label, refs) {
  if (refs.length === 0) return [];
  const shown = refs.slice(0, MAX_DIAGNOSTIC_REFS);
  const lines = shown.map((r) => `  still present: ${label} ${r}`);
  if (refs.length > shown.length) lines.push(`  ... and ${refs.length - shown.length} more ${label}(s)`);
  return lines;
}
function formatTeardownDiagnostic(verb, r) {
  if (!teardownIncomplete(r)) return "";
  const lines = [
    `sandbox ${verb}: teardown INCOMPLETE \u2014 ${r.failureCount} docker operation(s) failed; ${r.remainingContainers.length} container(s) and ${r.remainingVolumes.length} volume(s) still present.`
  ];
  for (const f of r.failures) lines.push(`  ${f.op} ${f.ref}: docker exit ${f.code}: ${f.message}`);
  if (r.failureCount > r.failures.length)
    lines.push(`  ... and ${r.failureCount - r.failures.length} more failure(s) not shown`);
  lines.push(...boundedRefs("container", r.remainingContainers));
  lines.push(...boundedRefs("volume", r.remainingVolumes));
  lines.push("  These objects may be running UNTRUSTED code \u2014 remove them by hand (`docker rm -f` / `docker volume rm`).");
  return lines.join("\n");
}

// exec.ts
var DEFAULT_EXEC_MAX_BYTES = Number(
  process.env.CA_SANDBOX_EXEC_MAX_BYTES ?? 1024 * 1024
);
var defaultDockerRun2 = makeDockerRun({}, { maxBuffer: 256 * 1024 * 1024 });
function buildExecArgs(id, argv) {
  if (!id) throw new Error("ca-sandbox: execInSandbox requires a non-empty container id");
  if (!argv || argv.length === 0)
    throw new Error("ca-sandbox: execInSandbox requires a non-empty command argv");
  return ["exec", id, ...argv];
}
function capBytes(s, maxBytes) {
  const buf = Buffer.from(s, "utf8");
  if (buf.length <= maxBytes) return { value: s, truncated: false };
  let value = buf.subarray(0, maxBytes).toString("utf8");
  while (Buffer.byteLength(value, "utf8") > maxBytes && value.length > 0) {
    value = value.slice(0, -1);
  }
  return { value, truncated: true };
}
async function execInSandbox(id, argv, opts = {}) {
  const args = buildExecArgs(id, argv);
  const dockerRun = opts.dockerRun ?? defaultDockerRun2;
  const maxBytes = opts.maxBytes ?? DEFAULT_EXEC_MAX_BYTES;
  const start = Date.now();
  const r = await dockerRun(args, { signal: opts.signal });
  const durationMs = Date.now() - start;
  let escalation = "";
  let containment;
  if (r.timedOut || r.aborted || r.overflowed) {
    const why = r.overflowed ? "lost output observation" : r.timedOut ? "the exec deadline" : "cancellation";
    const stopped = await dockerRun(["stop", "--time", "0", id]);
    const observed = await dockerRun(["inspect", "--format", "{{.State.Running}}", id]);
    containment = stopped.code === 0 && observed.code === 0 && observed.stdout.trim() === "false" ? "verified-stopped" : "unknown";
    escalation = containment === "verified-stopped" ? `
ca-sandbox: stopped container ${id} after ${why}.` : `
ca-sandbox: could not stop container ${id} after ${why} (${stopped.stderr.trim() || `exit ${stopped.code}`}); it may still be running.`;
  }
  const out = capBytes(r.stdout, maxBytes);
  const err = capBytes(r.stderr + escalation, maxBytes);
  return {
    id,
    exitCode: r.code,
    stdout: out.value,
    stderr: err.value,
    durationMs,
    truncated: out.truncated || err.truncated,
    ...r.timedOut ? { timedOut: true } : {},
    ...r.aborted ? { aborted: true } : {},
    ...r.overflowed ? { overflowed: true } : {},
    ...containment ? { containment } : {}
  };
}

// cp.ts
function buildCpOutArgs(id, containerPath, hostDest) {
  if (!id) throw new Error("ca-sandbox: cpOut requires a non-empty container id");
  if (!containerPath) throw new Error("ca-sandbox: cpOut requires a non-empty container path");
  if (!hostDest) throw new Error("ca-sandbox: cpOut requires a non-empty host destination");
  return ["cp", `${id}:${containerPath}`, hostDest];
}
function cpOut(id, containerPath, hostDest, opts = {}) {
  const args = buildCpOutArgs(id, containerPath, hostDest);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  return dockerRun(args, { signal: opts.signal });
}

// cli.ts
var NET_POLICIES = ["offline", "clone-then-cut", "allowlist"];
var DEFAULT_SHELL = "sh";
var CliError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "CliError";
  }
};
var SIGINT_EXIT_CODE = 130;
function isFlag(tok) {
  return tok.startsWith("--");
}
function splitFlag(tok) {
  const eq = tok.indexOf("=");
  if (eq === -1) return [tok, void 0];
  return [tok.slice(0, eq), tok.slice(eq + 1)];
}
function rejectUnknown(sub, tok) {
  if (isFlag(tok)) throw new CliError(`sandbox ${sub}: unknown flag '${tok}'`);
  throw new CliError(`sandbox ${sub}: unexpected argument '${tok}'`);
}
function parseCli(argv) {
  const [sub, ...rest] = argv;
  if (!sub) throw new CliError(usage());
  switch (sub) {
    case "create":
      return parseCreate(rest);
    case "shell":
      return parseShell(rest);
    case "exec":
      return parseExec(rest);
    case "cp":
      return parseCp(rest);
    case "destroy":
      return parseDestroy(rest);
    case "prune":
      return parsePrune(rest);
    default:
      throw new CliError(`sandbox: unknown subcommand '${sub}'
${usage()}`);
  }
}
function parseCreate(args) {
  let url;
  let netPolicy = "offline";
  for (let i = 0; i < args.length; i++) {
    const tok = args[i];
    if (isFlag(tok)) {
      const [name, inline] = splitFlag(tok);
      if (name === "--net") {
        const val = inline ?? args[++i];
        if (val === void 0) throw new CliError("sandbox create: --net requires a value");
        if (!NET_POLICIES.includes(val))
          throw new CliError(
            `sandbox create: unknown --net value '${val}' (one of: ${NET_POLICIES.join(", ")})`
          );
        netPolicy = val;
      } else {
        rejectUnknown("create", tok);
      }
    } else if (url === void 0) {
      url = tok;
    } else {
      rejectUnknown("create", tok);
    }
  }
  if (!url) throw new CliError("sandbox create: requires a repo <url>");
  return { kind: "create", url, netPolicy };
}
function parseShell(args) {
  let id;
  let shell = DEFAULT_SHELL;
  for (let i = 0; i < args.length; i++) {
    const tok = args[i];
    if (isFlag(tok)) {
      const [name, inline] = splitFlag(tok);
      if (name === "--shell") {
        const val = inline ?? args[++i];
        if (val === void 0) throw new CliError("sandbox shell: --shell requires a value");
        shell = val;
      } else {
        rejectUnknown("shell", tok);
      }
    } else if (id === void 0) {
      id = tok;
    } else {
      rejectUnknown("shell", tok);
    }
  }
  if (!id) throw new CliError("sandbox shell: requires a sandbox <id>");
  return { kind: "shell", id, shell };
}
function parseExec(args) {
  const sep = args.indexOf("--");
  const head = sep === -1 ? args : args.slice(0, sep);
  const tail = sep === -1 ? [] : args.slice(sep + 1);
  let id;
  for (const tok of head) {
    if (isFlag(tok)) {
      rejectUnknown("exec", tok);
    } else if (id === void 0) {
      id = tok;
    } else {
      rejectUnknown("exec", tok);
    }
  }
  if (!id) throw new CliError("sandbox exec: requires a sandbox <id>");
  if (tail.length === 0)
    throw new CliError("sandbox exec: requires a command after '--' (e.g. exec <id> -- sh -c ...)");
  return { kind: "exec", id, argv: tail };
}
function parseCp(args) {
  let source;
  let hostDest;
  for (const tok of args) {
    if (isFlag(tok)) {
      rejectUnknown("cp", tok);
    } else if (source === void 0) {
      source = tok;
    } else if (hostDest === void 0) {
      hostDest = tok;
    } else {
      rejectUnknown("cp", tok);
    }
  }
  if (!source || !hostDest)
    throw new CliError("sandbox cp: requires `<id>:<containerPath> <hostDest>` (pull-only)");
  const colon = source.indexOf(":");
  if (colon <= 0)
    throw new CliError(
      `sandbox cp: source must be '<id>:<containerPath>' (got '${source}'); host->container copy-in is not supported`
    );
  const id = source.slice(0, colon);
  const containerPath = source.slice(colon + 1);
  if (!containerPath)
    throw new CliError(`sandbox cp: source '${source}' is missing the container path after ':'`);
  return { kind: "cp", id, containerPath, hostDest };
}
function parseDestroy(args) {
  let id;
  let keepVolume = false;
  for (const tok of args) {
    if (isFlag(tok)) {
      const [name] = splitFlag(tok);
      if (name === "--keep-volume") keepVolume = true;
      else rejectUnknown("destroy", tok);
    } else if (id === void 0) {
      id = tok;
    } else {
      rejectUnknown("destroy", tok);
    }
  }
  if (!id) throw new CliError("sandbox destroy: requires a sandbox <id>");
  return { kind: "destroy", id, keepVolume };
}
function parsePrune(args) {
  for (const tok of args) rejectUnknown("prune", tok);
  return { kind: "prune" };
}
async function defaultShell(id, shell) {
  const containerId = await resolveContainerId(id);
  const r = spawnSync("docker", ["exec", "-it", containerId, shell], {
    stdio: "inherit",
    env: DOCKER_ENV
  });
  return r.status ?? 1;
}
function makeDefaultHandlers(call = {}) {
  return {
    create: async (url, opts) => await createSandbox(url, { netPolicy: opts.netPolicy, signal: call.signal }),
    destroy: async (id, opts) => await destroySandbox(id, { keepVolume: opts.keepVolume }),
    prune: async () => await prune(),
    // Preserve the sandbox id the caller passed in the returned contract, even
    // though the exec runs against the resolved container id.
    exec: async (id, argv) => ({
      ...await execInSandbox(await resolveContainerId(id), argv, { signal: call.signal }),
      id
    }),
    cp: async (id, containerPath, hostDest) => await cpOut(await resolveContainerId(id), containerPath, hostDest, { signal: call.signal }),
    shell: defaultShell
  };
}
var defaultHandlers = makeDefaultHandlers();
var TEARDOWN_FAILURE_EXIT = 1;
var USAGE_ERROR_EXIT = 2;
function teardownExit(verb, r) {
  if (!teardownIncomplete(r)) return 0;
  process.stderr.write(`${formatTeardownDiagnostic(verb, r)}
`);
  return TEARDOWN_FAILURE_EXIT;
}
async function runCli(argv, handlers = defaultHandlers) {
  let cmd;
  try {
    cmd = parseCli(argv);
  } catch (e) {
    if (e instanceof CliError) {
      process.stderr.write(`${e.message}
`);
      return USAGE_ERROR_EXIT;
    }
    throw e;
  }
  switch (cmd.kind) {
    case "create": {
      const r = await handlers.create(cmd.url, { netPolicy: cmd.netPolicy });
      process.stdout.write(`${JSON.stringify(r)}
`);
      return 0;
    }
    case "shell":
      return await handlers.shell(cmd.id, cmd.shell);
    case "exec": {
      const r = await handlers.exec(cmd.id, cmd.argv);
      process.stdout.write(`${JSON.stringify(r)}
`);
      return r.exitCode;
    }
    case "cp": {
      const r = await handlers.cp(cmd.id, cmd.containerPath, cmd.hostDest);
      if (r.code !== 0 && r.stderr) process.stderr.write(`${r.stderr}
`);
      return r.code;
    }
    case "destroy": {
      const r = await handlers.destroy(cmd.id, { keepVolume: cmd.keepVolume });
      process.stdout.write(`${JSON.stringify(r)}
`);
      return teardownExit("destroy", r);
    }
    case "prune": {
      const r = await handlers.prune();
      process.stdout.write(`${JSON.stringify(r)}
`);
      return teardownExit("prune", r);
    }
  }
}
function usage() {
  return [
    "usage: sandbox <subcommand> ...",
    "  create <url> [--net offline|clone-then-cut|allowlist]",
    "  shell <id> [--shell sh|bash]",
    "  exec <id> -- <cmd> [args...]",
    "  cp <id>:<containerPath> <hostDest>",
    "  destroy <id> [--keep-volume]",
    "  prune"
  ].join("\n");
}
var _thisFile = fileURLToPath(import.meta.url);
var _entryFile = path2.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  const cancel = new AbortController();
  let interrupted = false;
  process.on("SIGINT", () => {
    if (interrupted) {
      process.exit(SIGINT_EXIT_CODE);
    }
    interrupted = true;
    process.stderr.write(
      "ca-sandbox: cancelling - stopping the container this command started, then exiting. Press Ctrl-C again to exit immediately.\n"
    );
    cancel.abort();
  });
  runCli(process.argv.slice(2), makeDefaultHandlers({ signal: cancel.signal })).then((code) => process.exit(interrupted ? SIGINT_EXIT_CODE : code)).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
export {
  CliError,
  DEFAULT_SHELL,
  NET_POLICIES,
  SIGINT_EXIT_CODE,
  TEARDOWN_FAILURE_EXIT,
  USAGE_ERROR_EXIT,
  defaultHandlers,
  makeDefaultHandlers,
  parseCli,
  runCli
};
