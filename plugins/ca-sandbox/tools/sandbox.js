#!/usr/bin/env node

// cli.ts
import { fileURLToPath } from "node:url";
import path2 from "node:path";
import { spawnSync as spawnSync2 } from "node:child_process";

// create.ts
import { spawnSync, spawn as spawn3 } from "node:child_process";
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
      child = spawnFn("docker", args, { env: DOCKER_ENV, ...extra });
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
import { spawn as spawn2 } from "node:child_process";
import { writeFile, readFile, rm } from "node:fs/promises";
import path from "node:path";
var IMAGE_PREFIX = "ca-sbx";
var DEPS_DIR = "/deps";
var APP_DIR2 = "/work/repo";
var NIXPACKS_APP_DIR = "/app";
var FALLBACK_BASE_IMAGE = "node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0";
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
function sanitizeRepoName(repoDir) {
  const base = path.basename(repoDir.replace(/[\\/]+$/, "")) || "repo";
  const cleaned = base.replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/-+/g, "-").replace(/^[-._]+/, "").replace(/[-._]+$/, "").toLowerCase();
  return cleaned || "repo";
}
function imageTag(repoDir, dephash) {
  return `${IMAGE_PREFIX}:${sanitizeRepoName(repoDir)}-${dephash}`;
}
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
  return r.code;
}
async function defaultNixpacksVersion() {
  const r = await run("nixpacks", ["--version"]);
  if (r.code !== 0) throw new Error(`nixpacks --version failed: ${r.out.trim()}`);
  const m = r.stdout.match(/(\d+\.\d+\.\d+)/);
  return m ? m[1] : r.stdout.trim();
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
  const m = ver.stdout.match(/(\d+\.\d+\.\d+)/);
  return { bin, version: m ? m[1] : ver.stdout.trim() };
}
async function defaultEnsureNixpacks(exec = run) {
  const probe = await exec("nixpacks", ["--version"]);
  if (probe.code === 0) {
    const m = probe.stdout.match(/(\d+\.\d+\.\d+)/);
    return { available: true, via: { via: "host" }, version: m ? m[1] : probe.stdout.trim() };
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
async function generateNixpacks(repoDir, nx) {
  if (nx.via === "host") {
    return run("nixpacks", ["build", repoDir, "--out", repoDir, "--no-error-without-start"]);
  }
  const wp = await run("wsl.exe", ["wslpath", "-a", repoDir.replace(/\\/g, "/")]);
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
    "--no-error-without-start"
  ]);
}
async function runNixpacksBuild(tag, ctx) {
  const nx = ctx.nixpacks ?? { via: "host" };
  const gen = await generateNixpacks(ctx.repoDir, nx);
  if (gen.code !== 0) return { code: gen.code, out: gen.out };
  const genPath = path.join(ctx.repoDir, ".nixpacks", "Dockerfile");
  let generated;
  try {
    generated = await readFile(genPath, "utf8");
  } catch (e) {
    return { code: 1, out: `nixpacks did not produce ${genPath}: ${String(e)}
${gen.out}` };
  }
  const dfPath = path.join(ctx.repoDir, ".ca-sandbox.nixpacks.Dockerfile");
  await writeFile(dfPath, generated + relocationOverlay());
  try {
    const b = await run("docker", ["build", "-t", tag, "-f", dfPath, ctx.repoDir], {
      env: BUILD_ENV
    });
    return { code: b.code, out: gen.out + "\n" + b.out };
  } finally {
    await rm(dfPath, { force: true }).catch(() => {
    });
    await rm(path.join(ctx.repoDir, ".nixpacks"), { recursive: true, force: true }).catch(() => {
    });
  }
}
async function defaultRunBuild(tag, ctx) {
  if (ctx.builder === "nixpacks") {
    return runNixpacksBuild(tag, ctx);
  }
  const stack = await detectStack(ctx.repoDir);
  const dockerfileContent = generateDockerfile(stack);
  const dockerfile = path.join(ctx.repoDir, ".ca-sandbox.Dockerfile");
  await writeFile(dockerfile, dockerfileContent);
  try {
    const b = await run("docker", ["build", "-t", tag, "-f", dockerfile, ctx.repoDir]);
    return { code: b.code, out: b.out };
  } finally {
    await rm(dockerfile, { force: true }).catch(() => {
    });
  }
}
var defaultDeps = () => ({
  imageInspect: defaultImageInspect,
  runBuild: defaultRunBuild,
  nixpacksVersion: defaultNixpacksVersion,
  ensureNixpacks: defaultEnsureNixpacks
});
async function buildOrReuseImage(repoDir, dephash, deps = defaultDeps(), reportStage) {
  const tag = imageTag(repoDir, dephash);
  const notes = [];
  reportBuildStage(reportStage, "image-inspect");
  const inspectCode = await deps.imageInspect(tag);
  if (inspectCode === 0) {
    return { tag, reused: true, built: false, builder: null, notes };
  }
  reportBuildStage(reportStage, "nixpacks-probe");
  const nixpacks = await deps.ensureNixpacks();
  let builder;
  if (nixpacks.available) {
    builder = "nixpacks";
    if (nixpacks.note) notes.push(nixpacks.note);
  } else {
    builder = "dockerfile-fallback";
    if (nixpacks.note) notes.push(nixpacks.note);
  }
  const ctx = { repoDir, builder, nixpacks: nixpacks.via, notes };
  reportBuildStage(reportStage, builder === "nixpacks" ? "nixpacks-build" : "dockerfile-build");
  const result = await deps.runBuild(tag, ctx);
  if (result.code !== 0) {
    throw new Error(
      `ca-sandbox: build failed for ${tag} (builder=${builder}, exit ${result.code})
` + result.out.slice(-2e3)
    );
  }
  return { tag, reused: false, built: true, builder, notes };
}

// dephash.ts
import { createHash } from "node:crypto";
var DEPHASH_LENGTH = 12;
function sha256Hex(data) {
  const buf = typeof data === "string" ? Buffer.from(data, "utf8") : Buffer.isBuffer(data) ? data : Buffer.from(data);
  return createHash("sha256").update(buf).digest("hex");
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
  return createHash("sha256").update(payload, "utf8").digest("hex").slice(0, DEPHASH_LENGTH);
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
  return { code: r.code, items: splitLines(r.stdout), stderr: r.stderr, scope: scopeOf(labels) };
}
async function listVolumesResult(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  const r = await dockerRun(["volume", "ls", "-q", ...labelFilterArgs(labels)]);
  return { code: r.code, items: splitLines(r.stdout), stderr: r.stderr, scope: scopeOf(labels) };
}
async function listContainers(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  return (await listContainersResult(labels, dockerRun)).items;
}
async function listVolumes(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun) {
  return (await listVolumesResult(labels, dockerRun)).items;
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
function spawnAsync(cmd, args, timeoutMs) {
  return new Promise((resolve) => {
    const c = spawn3(cmd, args, {
      env: DOCKER_ENV,
      stdio: ["ignore", "ignore", "pipe"],
      ...timeoutMs !== void 0 ? { timeout: timeoutMs } : {}
    });
    const stderrChunks = [];
    c.stderr?.on("data", (chunk) => stderrChunks.push(chunk));
    c.on("error", () => resolve({ code: 1, stderr: "" }));
    c.on("close", (code) => {
      const raw = Buffer.concat(stderrChunks).toString("utf8");
      const stderr = raw.length > 500 ? raw.slice(-500) : raw;
      resolve({ code: code ?? 1, stderr });
    });
  });
}
async function defaultCloneRepo(url, volumeName, id) {
  return spawnAsync("docker", buildCloneArgs(url, volumeName, id), CLONE_TIMEOUT_MS);
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
async function defaultBuildImage(volumeName, id) {
  const { mkdtemp: mkdtemp2, rm: rm2 } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const path3 = await import("node:path");
  const dir = await mkdtemp2(path3.join(tmpdir(), "ca-sbx-checkout-"));
  const helper = `ca-sbx-cp-${newSandboxId()}`;
  const createResult = spawnSync("docker", buildCpHelperCreateArgs(volumeName, helper, id), {
    env: DOCKER_ENV,
    encoding: "utf8",
    timeout: CP_TIMEOUT_MS
  });
  if ((createResult.status ?? 1) !== 0) {
    const hint = (createResult.stderr ?? "").trim();
    await rm2(dir, { recursive: true, force: true }).catch(() => {
    });
    throw new Error(
      `ca-sandbox: docker create failed for helper container (exit ${createResult.status ?? 1})${hint ? `
${hint}` : ""}`
    );
  }
  try {
    const cpResult = spawnSync("docker", ["cp", `${helper}:${APP_DIR3}/.`, dir], {
      env: DOCKER_ENV,
      encoding: "utf8",
      timeout: CP_TIMEOUT_MS
    });
    if ((cpResult.status ?? 1) !== 0) {
      const hint = (cpResult.stderr ?? "").trim();
      throw new Error(
        `ca-sandbox: docker cp failed \u2014 empty checkout, cannot compute dephash (exit ${cpResult.status ?? 1})${hint ? `
${hint}` : ""}`
      );
    }
    const manifests = await readManifests(dir, path3);
    const dephash = computeDepHash(manifests);
    return await buildOrReuseImage(dir, dephash);
  } finally {
    spawnSync("docker", ["rm", "-f", helper], { env: DOCKER_ENV });
    await rm2(dir, { recursive: true, force: true }).catch(() => {
    });
  }
}
var MANIFEST_NAMES = /* @__PURE__ */ new Set([
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
  const { readFile: readFile2 } = await import("node:fs/promises");
  let entries = [];
  try {
    entries = await readdir(dir);
  } catch {
    return [];
  }
  const out = [];
  for (const name of entries) {
    if (!MANIFEST_NAMES.has(name)) continue;
    try {
      out.push({ path: name, bytes: await readFile2(path3.join(dir, name)) });
    } catch {
    }
  }
  return out;
}
async function createSandbox(url, opts = {}) {
  validateRepoUrl(url);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const cloneRepo = opts.cloneRepo ?? defaultCloneRepo;
  const buildImage = opts.buildImage ?? defaultBuildImage;
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
    throw new Error(
      `ca-sandbox: failed to create volume ${volumeName} (exit ${mk.code})
${mk.stderr.slice(-1e3)}`
    );
  }
  try {
    const cloneRaw = await cloneRepo(url, volumeName, id);
    const cloneCode = typeof cloneRaw === "number" ? cloneRaw : cloneRaw.code;
    const cloneStderr = typeof cloneRaw === "number" ? "" : cloneRaw.stderr;
    if (cloneCode !== 0) {
      const hint = cloneStderr.trim() ? `
${cloneStderr.trim()}` : "";
      throw new Error(
        `ca-sandbox: clone of ${url} into ${volumeName} failed (exit ${cloneCode})${hint}`
      );
    }
    const build = await buildImage(volumeName, id);
    const containerId = await runContainer(build.tag, volumeName, netPolicy, {
      extraLabels: [idLabel(id), ...opts.extraLabels ?? []],
      namePrefix: `ca-sbx-${id}`,
      signal: opts.signal,
      dockerRun: opts.dockerRun ? (args, call) => opts.dockerRun(args, call) : void 0
    });
    return {
      id,
      volumeName,
      image: build.tag,
      containerId,
      notes: build.notes
    };
  } catch (err) {
    const leftover = await dockerRun([
      "ps",
      "-a",
      "-q",
      "--no-trunc",
      "--filter",
      `label=${idLabel(id)}`
    ]);
    for (const c of leftover.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)) {
      await dockerRun(["rm", "-f", c]);
    }
    await dockerRun(["volume", "rm", "-f", volumeName]);
    throw err;
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
  const shape = message.replace(/"[^"]*"/g, '"<url>"').replace(/https?:\/\/\S+/g, "<url>").replace(/\d+/g, "<n>");
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
  if (r.timedOut || r.aborted) {
    const why = r.timedOut ? "the exec deadline" : "cancellation";
    const stopped = await dockerRun(["stop", "--time", "0", id]);
    escalation = stopped.code === 0 ? `
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
    ...r.aborted ? { aborted: true } : {}
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
  const r = spawnSync2("docker", ["exec", "-it", containerId, shell], {
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
