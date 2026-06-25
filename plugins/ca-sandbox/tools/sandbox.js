#!/usr/bin/env node

// cli.ts
import { fileURLToPath } from "node:url";
import path2 from "node:path";
import { spawnSync as spawnSync6 } from "node:child_process";

// create.ts
import { spawnSync as spawnSync3, spawn as spawn2 } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readdir } from "node:fs/promises";

// run.ts
import { spawnSync } from "node:child_process";

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

// run.ts
var APP_DIR = "/work/repo";
var SANDBOX_LABEL = "ca.sandbox=1";
var SANDBOX_USER = "1000:1000";
var DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };
function defaultDockerRun(args) {
  const r = spawnSync("docker", args, { encoding: "utf8", env: DOCKER_ENV });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
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
  const networkArgs = netPolicy === "offline" ? ["--network", "none"] : [];
  return [
    "run",
    "-d",
    ...nameArgs,
    ...mountArgs,
    "--workdir",
    APP_DIR,
    "--user",
    SANDBOX_USER,
    "--read-only",
    // --tmpfs is rendered by buildMountArgs as `--mount type=tmpfs,target=/tmp`,
    // BUT docker's `--read-only` makes a writable /tmp essential and the
    // `--tmpfs <path>` short form is the idiomatic, spec-named flag. Emit it
    // explicitly too so the run is robust on engines that treat a tmpfs --mount
    // and a read-only root differently; the duplicate tmpfs is harmless.
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
    "2",
    ...networkArgs,
    ...labelArgs,
    image,
    "sleep",
    "infinity"
  ];
}
function runContainer(image, volumeName, netPolicy, opts = {}) {
  const args = buildRunArgs(image, volumeName, netPolicy, opts);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const r = dockerRun(args);
  if (r.code !== 0) {
    throw new Error(
      `ca-sandbox: docker run failed for ${image} (exit ${r.code})
${(r.stderr || r.stdout).slice(-2e3)}`
    );
  }
  return r.stdout.trim();
}

// build.ts
import { spawn } from "node:child_process";
import { writeFile, readFile, rm } from "node:fs/promises";
import path from "node:path";
var IMAGE_PREFIX = "ca-sbx";
var DEPS_DIR = "/deps";
var APP_DIR2 = "/work/repo";
var NIXPACKS_APP_DIR = "/app";
var NIXPACKS_INSTALL_URL = "https://nixpacks.com/install.sh";
var DOCKER_ENV2 = { ...process.env, MSYS_NO_PATHCONV: "1" };
var BUILD_ENV = { ...DOCKER_ENV2, DOCKER_BUILDKIT: "1" };
function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, { env: DOCKER_ENV2, ...opts });
    let stdout = "";
    let stderr = "";
    c.stdout?.on("data", (d) => stdout += d);
    c.stderr?.on("data", (d) => stderr += d);
    c.on("error", (e) => resolve({ code: 1, out: String(e), stdout: "", stderr: String(e) }));
    c.on("close", (code) => resolve({ code: code ?? 1, out: stdout + stderr, stdout, stderr }));
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
async function detectWslNixpacks() {
  const probe = await run("wsl.exe", [
    "bash",
    "-lc",
    'command -v nixpacks || echo "$HOME/.local/bin/nixpacks"'
  ]);
  if (probe.code !== 0) return null;
  const bin = probe.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop();
  if (!bin) return null;
  const ver = await run("wsl.exe", ["--", bin, "--version"]);
  if (ver.code !== 0) return null;
  const m = ver.stdout.match(/(\d+\.\d+\.\d+)/);
  return { bin, version: m ? m[1] : ver.stdout.trim() };
}
async function defaultEnsureNixpacks() {
  const probe = await run("nixpacks", ["--version"]);
  if (probe.code === 0) {
    const m = probe.stdout.match(/(\d+\.\d+\.\d+)/);
    return { available: true, via: { via: "host" }, version: m ? m[1] : probe.stdout.trim() };
  }
  if (process.platform === "win32") {
    const wsl = await detectWslNixpacks();
    if (wsl) {
      return {
        available: true,
        via: { via: "wsl", bin: wsl.bin },
        version: wsl.version,
        note: `Windows: nixpacks has no native binary; using the WSL bridge \u2014 nixpacks (${wsl.bin}, v${wsl.version}) generates the Dockerfile, host Docker builds it.`
      };
    }
  }
  const install = await run("bash", ["-c", `curl -fsSL ${NIXPACKS_INSTALL_URL} | bash`]);
  if (install.code === 0) {
    const after = await run("nixpacks", ["--version"]);
    if (after.code === 0) {
      const m = after.stdout.match(/(\d+\.\d+\.\d+)/);
      return { available: true, via: { via: "host" }, version: m ? m[1] : after.stdout.trim() };
    }
  }
  return {
    available: false,
    note: `nixpacks is not installed (no host binary, no WSL bridge, install script blocked: ${NIXPACKS_INSTALL_URL}); fell back to a generated Dockerfile that mimics nixpacks. Install nixpacks for the intended build path (NEEDS-TRIAGE: nixpacks-as-runtime-dependency).`
  };
}
function generateDockerfile(stack) {
  const lines = [];
  lines.push("FROM node:20-slim");
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
async function buildOrReuseImage(repoDir, dephash, deps = defaultDeps()) {
  const tag = imageTag(repoDir, dephash);
  const notes = [];
  const inspectCode = await deps.imageInspect(tag);
  if (inspectCode === 0) {
    return { tag, reused: true, built: false, builder: null, notes };
  }
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
import { spawnSync as spawnSync2 } from "node:child_process";
var SANDBOX_LABEL2 = "ca.sandbox=1";
var SANDBOX_ID_LABEL_KEY = "ca.sandbox.id";
var DOCKER_ENV3 = { ...process.env, MSYS_NO_PATHCONV: "1" };
function defaultDockerRun2(args) {
  const r = spawnSync2("docker", args, { encoding: "utf8", env: DOCKER_ENV3 });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
}
function idLabel(id) {
  return `${SANDBOX_ID_LABEL_KEY}=${id}`;
}
function labelFilterArgs(labels) {
  const list = Array.isArray(labels) ? labels : [labels];
  return list.flatMap((l) => ["--filter", `label=${l}`]);
}
function listContainers(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun2) {
  const r = dockerRun(["ps", "-a", "-q", "--no-trunc", ...labelFilterArgs(labels)]);
  return splitLines(r.stdout);
}
function listVolumes(labels = SANDBOX_LABEL2, dockerRun = defaultDockerRun2) {
  const r = dockerRun(["volume", "ls", "-q", ...labelFilterArgs(labels)]);
  return splitLines(r.stdout);
}
function splitLines(out) {
  return out.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
}
function listAllContainers(dockerRun = defaultDockerRun2) {
  return listContainers(SANDBOX_LABEL2, dockerRun);
}
function listAllVolumes(dockerRun = defaultDockerRun2) {
  return listVolumes(SANDBOX_LABEL2, dockerRun);
}
function findSandbox(id, dockerRun = defaultDockerRun2) {
  const labels = [SANDBOX_LABEL2, idLabel(id)];
  const containers = listContainers(labels, dockerRun);
  const volumes = listVolumes(labels, dockerRun);
  if (containers.length === 0 && volumes.length === 0) return null;
  return { id, containers, volumes };
}
function resolveContainerId(id, dockerRun = defaultDockerRun2) {
  const rec = findSandbox(id, dockerRun);
  const containerId = rec?.containers[0];
  if (!containerId)
    throw new Error(
      `ca-sandbox: no running container for sandbox '${id}' (unknown id, or it was destroyed \u2014 see \`sandbox prune\`/\`list\`)`
    );
  return containerId;
}

// create.ts
var DOCKER_ENV4 = { ...process.env, MSYS_NO_PATHCONV: "1" };
var CLONE_IMAGE = "alpine/git:latest";
var APP_DIR3 = "/work/repo";
var VOLUME_PREFIX = "ca-sbx-vol";
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
function defaultDockerRun3(args) {
  const r = spawnSync3("docker", args, { encoding: "utf8", env: DOCKER_ENV4 });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
}
function newSandboxId() {
  return randomBytes(6).toString("hex");
}
function spawnAsync(cmd, args) {
  return new Promise((resolve) => {
    const c = spawn2(cmd, args, { env: DOCKER_ENV4, stdio: ["ignore", "ignore", "pipe"] });
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
async function defaultCloneRepo(url, volumeName) {
  return spawnAsync("docker", buildCloneArgs(url, volumeName));
}
function buildCloneArgs(url, volumeName) {
  return [
    "run",
    "--rm",
    "--mount",
    `type=volume,source=${volumeName},target=${APP_DIR3}`,
    CLONE_IMAGE,
    "clone",
    "--depth",
    "1",
    "--",
    url,
    APP_DIR3
  ];
}
async function defaultBuildImage(volumeName) {
  const { mkdtemp: mkdtemp2, rm: rm2 } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const path3 = await import("node:path");
  const dir = await mkdtemp2(path3.join(tmpdir(), "ca-sbx-checkout-"));
  const helper = `ca-sbx-cp-${newSandboxId()}`;
  const createResult = spawnSync3(
    "docker",
    [
      "create",
      "--name",
      helper,
      "--mount",
      `type=volume,source=${volumeName},target=${APP_DIR3}`,
      CLONE_IMAGE,
      "true"
    ],
    { env: DOCKER_ENV4, encoding: "utf8" }
  );
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
    const cpResult = spawnSync3("docker", ["cp", `${helper}:${APP_DIR3}/.`, dir], {
      env: DOCKER_ENV4,
      encoding: "utf8"
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
    spawnSync3("docker", ["rm", "-f", helper], { env: DOCKER_ENV4 });
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
  const dockerRun = opts.dockerRun ?? defaultDockerRun3;
  const cloneRepo = opts.cloneRepo ?? defaultCloneRepo;
  const buildImage = opts.buildImage ?? defaultBuildImage;
  const netPolicy = opts.netPolicy ?? "offline";
  const id = opts.id ?? newSandboxId();
  const volumeName = `${VOLUME_PREFIX}-${id}`;
  const sandboxLabels = [SANDBOX_LABEL2, idLabel(id), ...opts.extraLabels ?? []];
  const volLabelArgs = sandboxLabels.flatMap((l) => ["--label", l]);
  const mk = dockerRun(["volume", "create", ...volLabelArgs, volumeName]);
  if (mk.code !== 0) {
    throw new Error(
      `ca-sandbox: failed to create volume ${volumeName} (exit ${mk.code})
${mk.stderr.slice(-1e3)}`
    );
  }
  try {
    const cloneRaw = await cloneRepo(url, volumeName);
    const cloneCode = typeof cloneRaw === "number" ? cloneRaw : cloneRaw.code;
    const cloneStderr = typeof cloneRaw === "number" ? "" : cloneRaw.stderr;
    if (cloneCode !== 0) {
      const hint = cloneStderr.trim() ? `
${cloneStderr.trim()}` : "";
      throw new Error(
        `ca-sandbox: clone of ${url} into ${volumeName} failed (exit ${cloneCode})${hint}`
      );
    }
    const build = await buildImage(volumeName);
    const containerId = runContainer(build.tag, volumeName, netPolicy, {
      extraLabels: [idLabel(id), ...opts.extraLabels ?? []],
      namePrefix: `ca-sbx-${id}`,
      dockerRun: opts.dockerRun ? (args) => opts.dockerRun(args) : void 0
    });
    return {
      id,
      volumeName,
      image: build.tag,
      containerId,
      notes: build.notes
    };
  } catch (err) {
    dockerRun(["volume", "rm", "-f", volumeName]);
    const leftover = dockerRun([
      "ps",
      "-a",
      "-q",
      "--no-trunc",
      "--filter",
      `label=${idLabel(id)}`
    ]);
    for (const c of leftover.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)) {
      dockerRun(["rm", "-f", c]);
    }
    throw err;
  }
}

// destroy.ts
function destroySandbox(id, opts = {}) {
  if (!id) throw new Error("ca-sandbox: destroySandbox requires a sandbox id");
  const dockerRun = opts.dockerRun ?? defaultDockerRun2;
  const labels = [SANDBOX_LABEL2, idLabel(id)];
  const containers = listContainers(labels, dockerRun);
  const volumes = listVolumes(labels, dockerRun);
  const removedContainers = [];
  for (const c of containers) {
    const r = dockerRun(["rm", "-f", c]);
    if (r.code === 0) removedContainers.push(c);
  }
  const removedVolumes = [];
  const keptVolumes = [];
  if (opts.keepVolume) {
    keptVolumes.push(...volumes);
  } else {
    for (const v of volumes) {
      const r = dockerRun(["volume", "rm", "-f", v]);
      if (r.code === 0) removedVolumes.push(v);
    }
  }
  return { id, removedContainers, removedVolumes, keptVolumes };
}
function prune(opts = {}) {
  const dockerRun = opts.dockerRun ?? defaultDockerRun2;
  const removedContainers = [];
  for (const c of listAllContainers(dockerRun)) {
    const r = dockerRun(["rm", "-f", c]);
    if (r.code === 0) removedContainers.push(c);
  }
  const removedVolumes = [];
  for (const v of listAllVolumes(dockerRun)) {
    const r = dockerRun(["volume", "rm", "-f", v]);
    if (r.code === 0) removedVolumes.push(v);
  }
  return { removedContainers, removedVolumes };
}

// exec.ts
import { spawnSync as spawnSync4 } from "node:child_process";
var DEFAULT_EXEC_MAX_BYTES = Number(
  process.env.CA_SANDBOX_EXEC_MAX_BYTES ?? 1024 * 1024
);
var DOCKER_ENV5 = { ...process.env, MSYS_NO_PATHCONV: "1" };
function defaultDockerRun4(args) {
  const r = spawnSync4("docker", args, {
    encoding: "utf8",
    env: DOCKER_ENV5,
    maxBuffer: 256 * 1024 * 1024
  });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
}
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
function execInSandbox(id, argv, opts = {}) {
  const args = buildExecArgs(id, argv);
  const dockerRun = opts.dockerRun ?? defaultDockerRun4;
  const maxBytes = opts.maxBytes ?? DEFAULT_EXEC_MAX_BYTES;
  const start = Date.now();
  const r = dockerRun(args);
  const durationMs = Date.now() - start;
  const out = capBytes(r.stdout, maxBytes);
  const err = capBytes(r.stderr, maxBytes);
  return {
    id,
    exitCode: r.code,
    stdout: out.value,
    stderr: err.value,
    durationMs,
    truncated: out.truncated || err.truncated
  };
}

// cp.ts
import { spawnSync as spawnSync5 } from "node:child_process";
var DOCKER_ENV6 = { ...process.env, MSYS_NO_PATHCONV: "1" };
function defaultDockerRun5(args) {
  const r = spawnSync5("docker", args, { encoding: "utf8", env: DOCKER_ENV6 });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
}
function buildCpOutArgs(id, containerPath, hostDest) {
  if (!id) throw new Error("ca-sandbox: cpOut requires a non-empty container id");
  if (!containerPath) throw new Error("ca-sandbox: cpOut requires a non-empty container path");
  if (!hostDest) throw new Error("ca-sandbox: cpOut requires a non-empty host destination");
  return ["cp", `${id}:${containerPath}`, hostDest];
}
function cpOut(id, containerPath, hostDest, opts = {}) {
  const args = buildCpOutArgs(id, containerPath, hostDest);
  const dockerRun = opts.dockerRun ?? defaultDockerRun5;
  return dockerRun(args);
}

// cli.ts
var DOCKER_ENV7 = { ...process.env, MSYS_NO_PATHCONV: "1" };
var NET_POLICIES = ["offline", "clone-then-cut", "allowlist"];
var DEFAULT_SHELL = "sh";
var CliError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "CliError";
  }
};
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
function defaultShell(id, shell) {
  const containerId = resolveContainerId(id);
  const r = spawnSync6("docker", ["exec", "-it", containerId, shell], {
    stdio: "inherit",
    env: DOCKER_ENV7
  });
  return r.status ?? 1;
}
var defaultHandlers = {
  create: (url, opts) => createSandbox(url, { netPolicy: opts.netPolicy }),
  destroy: (id, opts) => destroySandbox(id, { keepVolume: opts.keepVolume }),
  prune: () => prune(),
  // Preserve the sandbox id the caller passed in the returned contract, even
  // though the exec runs against the resolved container id.
  exec: (id, argv) => ({ ...execInSandbox(resolveContainerId(id), argv), id }),
  cp: (id, containerPath, hostDest) => cpOut(resolveContainerId(id), containerPath, hostDest),
  shell: defaultShell
};
async function runCli(argv, handlers = defaultHandlers) {
  let cmd;
  try {
    cmd = parseCli(argv);
  } catch (e) {
    if (e instanceof CliError) {
      process.stderr.write(`${e.message}
`);
      return 2;
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
      return handlers.shell(cmd.id, cmd.shell);
    case "exec": {
      const r = handlers.exec(cmd.id, cmd.argv);
      process.stdout.write(`${JSON.stringify(r)}
`);
      return r.exitCode;
    }
    case "cp": {
      const r = handlers.cp(cmd.id, cmd.containerPath, cmd.hostDest);
      if (r.code !== 0 && r.stderr) process.stderr.write(`${r.stderr}
`);
      return r.code;
    }
    case "destroy": {
      const r = handlers.destroy(cmd.id, { keepVolume: cmd.keepVolume });
      process.stdout.write(`${JSON.stringify(r)}
`);
      return 0;
    }
    case "prune": {
      const r = handlers.prune();
      process.stdout.write(`${JSON.stringify(r)}
`);
      return 0;
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
  runCli(process.argv.slice(2)).then((code) => process.exit(code)).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
export {
  CliError,
  DEFAULT_SHELL,
  NET_POLICIES,
  defaultHandlers,
  parseCli,
  runCli
};
