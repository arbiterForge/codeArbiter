/**
 * build.ts — ca-sandbox image build + dephash cache (T-05, covers AC-04 / AC-05).
 *
 * `buildOrReuseImage(repoDir, dephash)` is the nixpacks-wrap + dephash-cache seam:
 *
 *   1. Derive the cache tag `ca-sbx:<repo>-<dephash>` (repo = sanitized basename of
 *      repoDir; the dephash is computed by the caller via dephash.ts's
 *      computeDepHash — passed in here as the cache discriminator).
 *   2. CACHE CHECK — `docker image inspect <tag>`. Exit 0 => the image exists =>
 *      REUSE, run NO build (AC-04: a `create` from an unchanged repo recomputes the
 *      SAME dephash, finds the tag, and skips the build).
 *   3. CACHE MISS — build the image and tag it `<tag>`:
 *        a. nixpacks is the intended builder. If `nixpacks --version` works we wrap
 *           it (`nixpacks build <repoDir> --name <tag>`).
 *        b. If nixpacks is absent we try to install it via its official install
 *           script (https://nixpacks.com/install.sh). If the install is BLOCKED
 *           (offline / sandboxed / non-zero exit) we FALL BACK to a generated
 *           Dockerfile that mimics what nixpacks bakes, and we NOTE the missing
 *           dependency in the result (the plan's [NEEDS-TRIAGE] environment-UX item).
 *      Either way, the build RELOCATES installed deps OUT OF TREE to `/deps` and
 *      exports `NODE_PATH=/deps/node_modules` / `PYTHONPATH=/deps/site-packages`
 *      via image ENV (Spike A: mounting the source volume over the app dir at
 *      `/work/repo` would otherwise shadow deps; out-of-tree `/deps` survives).
 *   4. A manifest/lockfile change recomputes a DIFFERENT dephash => DIFFERENT tag =>
 *      cache miss => rebuild (AC-05). Source-only edits leave the dephash stable.
 *
 * Toolchain note (Spike A driver note): `docker build --label` is unreliable, so
 * sandbox images are tracked by their namespaced TAG, never by an image label.
 * Windows (Spike A/B): MSYS_NO_PATHCONV=1 is set when shelling docker so in-
 * container paths and `-e HOME` are not mangled by Git Bash path conversion.
 *
 * Process/shell handling mirrors farm.ts: a `run()` child-process helper returning
 * a RunResult, and the docker/build effects are injectable (BuildDeps) so the pure
 * cache/tag/relocation logic is unit-testable without real docker, while the
 * docker-gated test drives the real defaults.
 */
import { spawn, type SpawnOptionsWithoutStdio } from "node:child_process";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

/** Image tag prefix for every sandbox image. */
export const IMAGE_PREFIX = "ca-sbx";
/** Out-of-tree deps dir (Spike A). The source volume mounts only at /work/repo. */
export const DEPS_DIR = "/deps";
/** In-container app dir; the live source named volume mounts here at run time. */
export const APP_DIR = "/work/repo";
/** The dir nixpacks bakes the app + deps into (its default WORKDIR). The
 *  relocation overlay moves deps from HERE to /deps — NOT from APP_DIR (Spike A
 *  recorded this; the never-run native path had it pointing at APP_DIR). */
export const NIXPACKS_APP_DIR = "/app";
/** Official nixpacks install script (used only when nixpacks is absent). */
export const NIXPACKS_INSTALL_URL = "https://nixpacks.com/install.sh";

// --------------------------------------------------------------------------
// process helper (mirrors farm.ts run()/RunResult)
// --------------------------------------------------------------------------
export type RunResult = { code: number; out: string; stdout: string; stderr: string };

// On Windows + Git Bash, passing container paths / `-e HOME` to docker gets
// mangled by MSYS path conversion; MSYS_NO_PATHCONV=1 disables it (Spike A/B).
const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

// docker build of the nixpacks-generated Dockerfile needs BuildKit (it emits
// `RUN --mount=type=cache`). Docker Desktop defaults to BuildKit, but set it
// explicitly so the build is robust regardless of the daemon default.
const BUILD_ENV = { ...DOCKER_ENV, DOCKER_BUILDKIT: "1" };

// `opts.env`, when supplied, is an explicit typed override (e.g. BUILD_ENV
// below) rather than an unconstrained spread — a future opts literal is now
// compiler-checked to stay a well-formed env override (must preserve
// MSYS_NO_PATHCONV explicitly, not drop it by accident).
type RunOpts = { env?: NodeJS.ProcessEnv } & Omit<SpawnOptionsWithoutStdio, "env" | "shell">;

function run(cmd: string, args: string[], opts: RunOpts = {}): Promise<RunResult> {
  return new Promise<RunResult>((resolve) => {
    const c = spawn(cmd, args, { env: DOCKER_ENV, ...opts });
    let stdout = "";
    let stderr = "";
    c.stdout?.on("data", (d) => (stdout += d));
    c.stderr?.on("data", (d) => (stderr += d));
    c.on("error", (e) => resolve({ code: 1, out: String(e), stdout: "", stderr: String(e) }));
    c.on("close", (code) => resolve({ code: code ?? 1, out: stdout + stderr, stdout, stderr }));
  });
}

// --------------------------------------------------------------------------
// tag derivation
// --------------------------------------------------------------------------
/**
 * Docker tags allow only [A-Za-z0-9_.-] and must not start with a separator.
 * The repo segment is the sanitized basename of repoDir; any other char folds to
 * `-`, runs collapse, and a leading separator is trimmed. An empty result falls
 * back to "repo" so the tag is always well-formed.
 */
function sanitizeRepoName(repoDir: string): string {
  const base = path.basename(repoDir.replace(/[\\/]+$/, "")) || "repo";
  const cleaned = base
    .replace(/[^A-Za-z0-9_.-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-._]+/, "")
    .replace(/[-._]+$/, "")
    .toLowerCase();
  return cleaned || "repo";
}

/** The cache tag for a repo + dephash: `ca-sbx:<repo>-<dephash>`. */
export function imageTag(repoDir: string, dephash: string): string {
  return `${IMAGE_PREFIX}:${sanitizeRepoName(repoDir)}-${dephash}`;
}

// --------------------------------------------------------------------------
// injectable build effects
// --------------------------------------------------------------------------
/** Which builder produced (or will produce) the image. */
export type Builder = "nixpacks" | "dockerfile-fallback";

/**
 * How nixpacks is invoked. On Linux/macOS it runs on the host. On Windows there
 * is no nixpacks binary, but a WSL distro can have one — and nixpacks `--out`
 * only GENERATES the Dockerfile (no docker daemon needed), so we run nixpacks in
 * WSL to generate, then build with the host's Docker (the same engine the driver
 * uses). `bin` is the absolute nixpacks path inside the distro.
 */
export type NixpacksInvocation =
  | { via: "host" }
  | { via: "wsl"; bin: string; distro?: string };

/** Context handed to runBuild so it knows which builder path to take. */
export type BuildContext = {
  repoDir: string;
  builder: Builder;
  /** How to invoke nixpacks (only set when builder === "nixpacks"). */
  nixpacks?: NixpacksInvocation;
  /** Notes accumulated so far (e.g. the nixpacks-missing fallback note). */
  notes: string[];
};

export type EnsureNixpacksResult = {
  available: boolean;
  /** How nixpacks is invoked (host or WSL bridge) when available. */
  via?: NixpacksInvocation;
  /** When unavailable, why (install blocked / not installed) — surfaced to the user. */
  note?: string;
  /** The resolved nixpacks version when available, folded into nothing here (the
   *  dephash already pins the toolchain version via computeDepHash). */
  version?: string;
};

/**
 * The docker/build effects, injected so the cache/tag/relocation control flow is
 * unit-testable without real docker. Defaults shell the real docker/nixpacks.
 */
export type BuildDeps = {
  /** `docker image inspect <tag>` exit code (0 => exists/reuse). */
  imageInspect: (tag: string) => Promise<number>;
  /** Build + tag the image for the given builder; resolves with the build result. */
  runBuild: (tag: string, ctx: BuildContext) => Promise<{ code: number; out: string }>;
  /** Resolve the installed nixpacks version; rejects if nixpacks is absent. */
  nixpacksVersion: () => Promise<string>;
  /** Ensure nixpacks is usable, installing it if needed; reports availability. */
  ensureNixpacks: () => Promise<EnsureNixpacksResult>;
};

export type BuildResult = {
  /** The image tag `ca-sbx:<repo>-<dephash>`. */
  tag: string;
  /** True when an existing tag was reused (cache hit, NO build). */
  reused: boolean;
  /** True when a build ran (cache miss). */
  built: boolean;
  /** Which builder produced the image (only meaningful when built). */
  builder: Builder | null;
  /** Human-facing notes — notably the nixpacks-missing fallback dependency note. */
  notes: string[];
};

// --------------------------------------------------------------------------
// default real-docker effects
// --------------------------------------------------------------------------
async function defaultImageInspect(tag: string): Promise<number> {
  const r = await run("docker", ["image", "inspect", tag]);
  return r.code;
}

async function defaultNixpacksVersion(): Promise<string> {
  const r = await run("nixpacks", ["--version"]);
  if (r.code !== 0) throw new Error(`nixpacks --version failed: ${r.out.trim()}`);
  // `nixpacks --version` prints e.g. "nixpacks 1.40.0" or "1.40.0".
  const m = r.stdout.match(/(\d+\.\d+\.\d+)/);
  return m ? m[1] : r.stdout.trim();
}

/**
 * Detect a nixpacks usable through the WSL bridge: nixpacks has no Windows
 * binary, but a WSL distro can have one. We only use it to GENERATE the
 * Dockerfile (`--out`, no docker daemon in WSL), then the host's Docker builds
 * it. Returns the absolute nixpacks path inside the default distro + version, or
 * null if WSL/nixpacks is absent.
 */
async function detectWslNixpacks(): Promise<{ bin: string; version: string } | null> {
  // Resolve the nixpacks path inside the default distro. `command -v` covers a
  // PATH install; the `||` fallback covers the user-dir install ($HOME/.local/bin).
  const probe = await run("wsl.exe", [
    "bash",
    "-lc",
    'command -v nixpacks || echo "$HOME/.local/bin/nixpacks"',
  ]);
  if (probe.code !== 0) return null;
  const bin = probe.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop();
  if (!bin) return null;
  // Verify it actually runs in WSL (the fallback path may not exist).
  const ver = await run("wsl.exe", ["--", bin, "--version"]);
  if (ver.code !== 0) return null;
  const m = ver.stdout.match(/(\d+\.\d+\.\d+)/);
  return { bin, version: m ? m[1] : ver.stdout.trim() };
}

/**
 * Ensure nixpacks is available, by precedence:
 *   1. host `nixpacks` on PATH (Linux/macOS, or a Windows host that has it);
 *   2. the WSL bridge (Windows) — nixpacks in a WSL distro generates the
 *      Dockerfile, host Docker builds it;
 *   3. the official install script on the host;
 * else report unavailable so the caller uses the generated-Dockerfile fallback
 * and surfaces the dependency.
 */
async function defaultEnsureNixpacks(): Promise<EnsureNixpacksResult> {
  const probe = await run("nixpacks", ["--version"]);
  if (probe.code === 0) {
    const m = probe.stdout.match(/(\d+\.\d+\.\d+)/);
    return { available: true, via: { via: "host" }, version: m ? m[1] : probe.stdout.trim() };
  }

  // WSL bridge: only meaningful on Windows, but the probe is harmless elsewhere
  // (no `wsl.exe` => null). nixpacks-in-WSL generates the Dockerfile; host Docker builds it.
  if (process.platform === "win32") {
    const wsl = await detectWslNixpacks();
    if (wsl) {
      return {
        available: true,
        via: { via: "wsl", bin: wsl.bin },
        version: wsl.version,
        note:
          "Windows: nixpacks has no native binary; using the WSL bridge — nixpacks " +
          `(${wsl.bin}, v${wsl.version}) generates the Dockerfile, host Docker builds it.`,
      };
    }
  }

  // Try the official install script: `curl -fsSL <url> | bash`.
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
    note:
      "nixpacks is not installed (no host binary, no WSL bridge, install script " +
      `blocked: ${NIXPACKS_INSTALL_URL}); fell back to a generated Dockerfile that ` +
      "mimics nixpacks. Install nixpacks for the intended build path (NEEDS-TRIAGE: " +
      "nixpacks-as-runtime-dependency).",
  };
}

// --------------------------------------------------------------------------
// generated-Dockerfile fallback — mimics what nixpacks bakes, with the Spike A
// out-of-tree /deps relocation baked in directly.
// --------------------------------------------------------------------------
/**
 * Build a Dockerfile that installs deps OUT OF TREE to /deps and exports
 * NODE_PATH/PYTHONPATH, so a source volume mounted only at /work/repo never
 * shadows the baked deps (Spike A). Detected stack by manifest presence:
 *   - package.json     -> npm install into /deps/node_modules, ENV NODE_PATH
 *   - requirements.txt -> pip install --target=/deps/site-packages, ENV PYTHONPATH
 * Both are emitted when both manifests are present. A repo with neither still
 * produces a runnable base image at /work/repo.
 */
export function generateDockerfile(stack: { node: boolean; python: boolean }): string {
  const lines: string[] = [];
  // node:20-slim has both node and (via apt) python tooling for the common cases;
  // it matches the Node 20 driver stack and Spike B's clean install base family.
  lines.push("FROM node:20-slim");
  lines.push(`ENV NODE_PATH=${DEPS_DIR}/node_modules`);
  lines.push(`ENV PYTHONPATH=${DEPS_DIR}/site-packages`);
  lines.push(`RUN mkdir -p ${DEPS_DIR} ${APP_DIR}`);

  if (stack.node) {
    // Install deps into /deps (out of tree) — NOT into the app dir. Copy only the
    // manifests for a cache-friendly layer, install, then copy the source.
    lines.push(`WORKDIR ${DEPS_DIR}`);
    lines.push("COPY package.json package.json");
    lines.push("COPY package-lock.json* npm-shrinkwrap.json* yarn.lock* ./");
    // `npm install --prefix /deps` writes node_modules under /deps (resolved via NODE_PATH).
    lines.push(`RUN npm install --omit=dev --prefix ${DEPS_DIR} || npm install --prefix ${DEPS_DIR}`);
  }
  if (stack.python) {
    lines.push(`RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*`);
    lines.push("COPY requirements.txt /tmp/requirements.txt");
    lines.push(`RUN pip3 install --no-cache-dir --target=${DEPS_DIR}/site-packages -r /tmp/requirements.txt`);
  }

  // Source last so a source-only change doesn't bust the dep layers. The runtime
  // mounts the live source volume at /work/repo over this baked copy; because deps
  // live at /deps the mount never shadows them, and source stays live-editable.
  lines.push(`WORKDIR ${APP_DIR}`);
  lines.push(`COPY . ${APP_DIR}`);
  return lines.join("\n") + "\n";
}

async function detectStack(repoDir: string): Promise<{ node: boolean; python: boolean }> {
  const { access } = await import("node:fs/promises");
  const has = async (f: string) => {
    try {
      await access(path.join(repoDir, f));
      return true;
    } catch {
      return false;
    }
  };
  return { node: await has("package.json"), python: await has("requirements.txt") };
}

/**
 * The relocation overlay appended to the nixpacks-GENERATED Dockerfile. nixpacks
 * bakes deps into /app and sets a bash-login ENTRYPOINT; this moves the deps
 * out-of-tree to /deps (+ NODE_PATH/PYTHONPATH) so the source volume at
 * /work/repo never shadows them (Spike A), and resets the ENTRYPOINT so the
 * sandbox `sleep infinity` keepalive runs as a plain command.
 */
export function relocationOverlay(): string {
  return [
    "",
    "# --- ca-sandbox relocation overlay (Spike A) ------------------------------",
    `# nixpacks bakes deps into ${NIXPACKS_APP_DIR}; relocate them OUT OF TREE to`,
    `# ${DEPS_DIR} so the live source volume at ${APP_DIR} never shadows them, and`,
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
    `WORKDIR ${APP_DIR}`,
    `COPY . ${APP_DIR}`,
    "",
  ].join("\n");
}

/**
 * Generate the nixpacks Dockerfile into `repoDir/.nixpacks/` WITHOUT building
 * (nixpacks `--out` needs no docker daemon). On the WSL bridge we translate the
 * Windows path with `wslpath` and run nixpacks inside the distro writing into the
 * SAME physical dir (visible to the host at repoDir). The host's Docker then
 * builds it (see runNixpacksBuild).
 */
async function generateNixpacks(repoDir: string, nx: NixpacksInvocation): Promise<RunResult> {
  // ca-sandbox never RUNS the repo as an app (the container runs `sleep infinity`
  // and you exec in), so a library / bare repo with no start command must still
  // build. `--no-error-without-start` tells nixpacks not to fail in that case.
  if (nx.via === "host") {
    return run("nixpacks", ["build", repoDir, "--out", repoDir, "--no-error-without-start"]);
  }
  // wsl.exe eats backslashes in args, so hand wslpath a forward-slash Windows
  // path (wslpath accepts `C:/Users/...`); backslashes would arrive stripped.
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
    "--no-error-without-start",
  ]);
}

/**
 * Build via nixpacks: GENERATE the Dockerfile (host or WSL bridge), append the
 * /deps relocation overlay, then `docker build` it with the host's Docker (the
 * same engine ca-sandbox runs against). One docker build, no intermediate image.
 */
async function runNixpacksBuild(
  tag: string,
  ctx: BuildContext,
): Promise<{ code: number; out: string }> {
  const nx = ctx.nixpacks ?? { via: "host" };
  const gen = await generateNixpacks(ctx.repoDir, nx);
  if (gen.code !== 0) return { code: gen.code, out: gen.out };

  const genPath = path.join(ctx.repoDir, ".nixpacks", "Dockerfile");
  let generated: string;
  try {
    generated = await readFile(genPath, "utf8");
  } catch (e) {
    return { code: 1, out: `nixpacks did not produce ${genPath}: ${String(e)}\n${gen.out}` };
  }

  const dfPath = path.join(ctx.repoDir, ".ca-sandbox.nixpacks.Dockerfile");
  await writeFile(dfPath, generated + relocationOverlay());
  try {
    const b = await run("docker", ["build", "-t", tag, "-f", dfPath, ctx.repoDir], {
      env: BUILD_ENV,
    });
    return { code: b.code, out: gen.out + "\n" + b.out };
  } finally {
    // Clean up the generated build artifacts so they never pollute the context
    // dir. This matters for the fixture-based tests, where repoDir IS a committed
    // fixture dir: without this, every test run would leave a stray `.nixpacks/`.
    await rm(dfPath, { force: true }).catch(() => {});
    await rm(path.join(ctx.repoDir, ".nixpacks"), { recursive: true, force: true }).catch(() => {});
  }
}

/**
 * Default build effect. nixpacks path: generate the Dockerfile (host or WSL
 * bridge) + relocation overlay, then docker build. Fallback path: `docker build`
 * the generated Dockerfile, which already installs deps to /deps.
 */
async function defaultRunBuild(
  tag: string,
  ctx: BuildContext,
): Promise<{ code: number; out: string }> {
  if (ctx.builder === "nixpacks") {
    return runNixpacksBuild(tag, ctx);
  }

  // Fallback: generated Dockerfile (already installs deps to /deps + ENV).
  const stack = await detectStack(ctx.repoDir);
  const dockerfileContent = generateDockerfile(stack);
  const dockerfile = path.join(ctx.repoDir, ".ca-sandbox.Dockerfile");
  await writeFile(dockerfile, dockerfileContent);
  try {
    const b = await run("docker", ["build", "-t", tag, "-f", dockerfile, ctx.repoDir]);
    return { code: b.code, out: b.out };
  } finally {
    await rm(dockerfile, { force: true }).catch(() => {});
  }
}

const defaultDeps = (): BuildDeps => ({
  imageInspect: defaultImageInspect,
  runBuild: defaultRunBuild,
  nixpacksVersion: defaultNixpacksVersion,
  ensureNixpacks: defaultEnsureNixpacks,
});

// --------------------------------------------------------------------------
// the entry point
// --------------------------------------------------------------------------
/**
 * Build the sandbox image for `repoDir`, or reuse the cached image when one
 * already exists for this dephash.
 *
 * @param repoDir absolute path to the cloned repo (its basename names the tag).
 * @param dephash the dependency cache key from computeDepHash (dephash.ts).
 * @param deps injectable docker/build effects (defaults shell real docker/nixpacks).
 * @returns the tag plus whether the image was reused or freshly built, the
 *   builder used, and any user-facing notes (e.g. the nixpacks-missing fallback).
 * @throws if a build was attempted and failed (non-zero exit).
 */
export async function buildOrReuseImage(
  repoDir: string,
  dephash: string,
  deps: BuildDeps = defaultDeps(),
): Promise<BuildResult> {
  const tag = imageTag(repoDir, dephash);
  const notes: string[] = [];

  // CACHE CHECK (AC-04): an existing tag => reuse, NO build.
  const inspectCode = await deps.imageInspect(tag);
  if (inspectCode === 0) {
    return { tag, reused: true, built: false, builder: null, notes };
  }

  // CACHE MISS (AC-05): decide the builder. Prefer nixpacks; fall back to the
  // generated Dockerfile (and NOTE the dependency) when nixpacks is unavailable.
  const nixpacks = await deps.ensureNixpacks();
  let builder: Builder;
  if (nixpacks.available) {
    builder = "nixpacks";
    // Surface the WSL-bridge note (or any availability note) so the user knows
    // which build path ran.
    if (nixpacks.note) notes.push(nixpacks.note);
  } else {
    builder = "dockerfile-fallback";
    if (nixpacks.note) notes.push(nixpacks.note);
  }

  const ctx: BuildContext = { repoDir, builder, nixpacks: nixpacks.via, notes };
  const result = await deps.runBuild(tag, ctx);
  if (result.code !== 0) {
    throw new Error(
      `ca-sandbox: build failed for ${tag} (builder=${builder}, exit ${result.code})\n` +
        result.out.slice(-2000),
    );
  }

  return { tag, reused: false, built: true, builder, notes };
}
