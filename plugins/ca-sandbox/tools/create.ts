/**
 * create.ts — ca-sandbox lifecycle entry (T-09, covers AC-01 / AC-11).
 *
 * createSandbox(url, opts) pulls an untrusted repo into an isolated, ephemeral
 * box, end to end:
 *
 *   1. Mint a short random sandbox id and derive the namespaced object names.
 *   2. Create a LABELED named volume (`ca.sandbox=1` + `ca.sandbox.id=<id>`) — the
 *      live source mount. The volume is the registry record's only persistent
 *      part (label-only state; no JSON file — see registry.ts).
 *   3. CLONE the repo INTO that volume via a THROWAWAY `alpine/git` container with
 *      networking UP for the clone (the only point egress is needed by default;
 *      the sandbox container itself defaults to offline). The clone container
 *      mounts the volume at /work/repo and is `--rm`'d immediately after — it is
 *      NOT a sandbox object and carries no sandbox label, and (critically) it is
 *      never co-run with the untrusted code: clone-then-cut.
 *   4. BUILD (or reuse) the image via build.ts (dephash-cached, deps to /deps).
 *   5. RUN the sandbox container via run.ts — structurally isolated, no host bind,
 *      offline by default — tagging it `ca.sandbox=1` + `ca.sandbox.id=<id>`.
 *
 * Everything created is labeled so destroy.ts / prune() can reclaim it by label
 * alone. On any failure AFTER the volume is created, the partial objects are torn
 * down so a failed create never leaks a labeled half-sandbox.
 *
 * Process/shell handling mirrors run.ts / build.ts: an injectable docker runner,
 * MSYS_NO_PATHCONV=1 on Windows + Git Bash (Spike A/B), and a deterministic id
 * derived from crypto random bytes (farm.ts hashing style).
 */
import { spawnSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readdir } from "node:fs/promises";
import { runContainer, type NetPolicy } from "./run.ts";
import { buildOrReuseImage, type BuildResult } from "./build.ts";
import { computeDepHash, type ManifestFile } from "./dephash.ts";
import {
  SANDBOX_LABEL,
  idLabel,
  type DockerRun,
  type DockerResult,
} from "./registry.ts";

const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

/** Image used for the throwaway clone step (small, git built in). */
export const CLONE_IMAGE = "alpine/git:latest";
/** In-container app dir; the source volume mounts here for both clone and run. */
export const APP_DIR = "/work/repo";
/** Prefix for the named volume of a sandbox. */
export const VOLUME_PREFIX = "ca-sbx-vol";

export type CreateOptions = {
  /** Network policy for the SANDBOX container (run.ts). Defaults to "offline". */
  netPolicy?: NetPolicy;
  /** Extra labels (e.g. the test marker `ca.sandbox.build=1`). */
  extraLabels?: string[];
  /** Override the generated id (tests use a deterministic one). */
  id?: string;
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: DockerRun;
  /**
   * Injectable repo cloner. Defaults to the throwaway alpine/git container.
   * Returns 0 on success. Tests inject a fake to avoid real network.
   */
  cloneRepo?: (url: string, volumeName: string) => Promise<number>;
  /**
   * Injectable image builder. Defaults to build.ts buildOrReuseImage over a
   * temp checkout. Tests inject a fake that returns a prebuilt tag.
   */
  buildImage?: (volumeName: string) => Promise<BuildResult>;
};

/** Error thrown when an untrusted repo url fails the clone-input trust check. */
export class InvalidRepoUrlError extends Error {
  constructor(url: string, reason: string) {
    super(
      `ca-sandbox: refusing to clone ${JSON.stringify(url)} — ${reason}. The repo ` +
        `url is untrusted input handed straight to git: only plain network remotes ` +
        `(https://, ssh://, or user@host:path) are allowed. git transport-helper ` +
        `syntax (ext::, fd::, file://) can execute commands or read host paths, and a ` +
        `value beginning with '-' would be parsed by git as a flag (argument ` +
        `injection) — both are rejected here.`,
    );
    this.name = "InvalidRepoUrlError";
  }
}

/**
 * Validate an untrusted repo url BEFORE it reaches `git clone`. The plugin's
 * entire job is handling untrusted repos, and the url is the one create input
 * that flows into git's argv. Two git footguns are closed by allowlisting:
 *
 *   - a url beginning with `-` is read by git as a FLAG, not an operand (classic
 *     git argument injection, e.g. `--upload-pack=<cmd>`);
 *   - git's transport-helper syntax (`ext::sh -c <cmd>`, `fd::`, `file://`) runs
 *     commands or reads host paths.
 *
 * Only plain network remotes pass. Defense in depth: defaultCloneRepo ALSO emits
 * `--` before the url so even a leading-`-` value could never be parsed as a flag.
 */
export function validateRepoUrl(url: string): void {
  if (!url) throw new Error("ca-sandbox: createSandbox requires a repo url");
  if (url.startsWith("-")) {
    throw new InvalidRepoUrlError(url, "a url may not begin with '-' (git would read it as a flag)");
  }
  const httpsOk = /^https:\/\/\S+$/i.test(url);
  const sshUrlOk = /^ssh:\/\/\S+$/i.test(url);
  // scp-like remote: user@host:path. The `:[^:]` guard rejects a transport-helper
  // `host::address` that sneaks a `@` in; the leading-scheme checks reject ext::/
  // fd::/file:// outright (they match none of the three).
  const scpOk = /^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^:].*$/.test(url);
  if (!(httpsOk || sshUrlOk || scpOk)) {
    throw new InvalidRepoUrlError(
      url,
      "only https://, ssh://, or user@host:path remotes are allowed",
    );
  }
}

export type CreateResult = {
  /** The minted (or supplied) sandbox id. */
  id: string;
  /** The named volume holding the cloned source. */
  volumeName: string;
  /** The built/reused image tag. */
  image: string;
  /** The started container id. */
  containerId: string;
  /** Build notes (e.g. nixpacks-missing fallback). */
  notes: string[];
};

function defaultDockerRun(args: string[]): DockerResult {
  const r = spawnSync("docker", args, { encoding: "utf8", env: DOCKER_ENV });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : ""),
  };
}

/** A short, url-safe random id (12 hex chars), mirroring run.ts's name suffix. */
export function newSandboxId(): string {
  return randomBytes(6).toString("hex");
}

function spawnAsync(cmd: string, args: string[]): Promise<number> {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, { env: DOCKER_ENV, stdio: "ignore" });
    c.on("error", () => resolve(1));
    c.on("close", (code) => resolve(code ?? 1));
  });
}

/**
 * Clone `url` INTO the named volume via a throwaway alpine/git container with
 * networking up. The container mounts the volume at /work/repo and is `--rm`'d
 * the instant the clone finishes — it carries NO sandbox label and is never the
 * sandbox itself. Cloning into an empty named volume's mount point; alpine/git's
 * entrypoint is `git`, so the args after the image are git's.
 */
export async function defaultCloneRepo(url: string, volumeName: string): Promise<number> {
  return spawnAsync("docker", buildCloneArgs(url, volumeName));
}

/**
 * The docker argv (everything after `docker`) for the throwaway clone container.
 * Pure so the argument-injection-hardening invariant is unit-testable:
 * `clone --depth 1 -- <url> <dir>` — the `--` end-of-options separator sits
 * directly before the untrusted url so a leading-`-` value can never be parsed by
 * git as a flag (belt to validateRepoUrl's suspenders). alpine/git ENTRYPOINT is
 * `git`, so the args after the image are git's; clone goes straight into the
 * volume mounted at /work/repo.
 */
export function buildCloneArgs(url: string, volumeName: string): string[] {
  return [
    "run",
    "--rm",
    "--mount",
    `type=volume,source=${volumeName},target=${APP_DIR}`,
    CLONE_IMAGE,
    "clone",
    "--depth",
    "1",
    "--",
    url,
    APP_DIR,
  ];
}

/**
 * Default image build: copy the cloned source OUT of the volume into a temp dir
 * (so build.ts can read manifests + run a docker build context), compute the
 * dephash from the manifest set, then buildOrReuseImage. The clone lives only in
 * the volume, so we materialize a transient checkout via a throwaway container's
 * `docker cp`. Kept injectable; the docker-gated lifecycle test exercises the
 * REAL default end to end on a tiny repo.
 */
async function defaultBuildImage(volumeName: string): Promise<BuildResult> {
  const { mkdtemp, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const path = await import("node:path");
  const dir = await mkdtemp(path.join(tmpdir(), "ca-sbx-checkout-"));
  // Materialize the volume contents to the host temp dir via a helper container:
  // mount the volume read-only and `docker cp` its /work/repo out.
  const helper = `ca-sbx-cp-${newSandboxId()}`;
  spawnSync(
    "docker",
    [
      "create",
      "--name",
      helper,
      "--mount",
      `type=volume,source=${volumeName},target=${APP_DIR}`,
      CLONE_IMAGE,
      "true",
    ],
    { env: DOCKER_ENV, encoding: "utf8" },
  );
  try {
    spawnSync("docker", ["cp", `${helper}:${APP_DIR}/.`, dir], { env: DOCKER_ENV });
    const manifests = await readManifests(dir, path);
    const dephash = computeDepHash(manifests);
    return await buildOrReuseImage(dir, dephash);
  } finally {
    spawnSync("docker", ["rm", "-f", helper], { env: DOCKER_ENV });
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

const MANIFEST_NAMES = new Set([
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
  "Cargo.lock",
]);

async function readManifests(
  dir: string,
  path: typeof import("node:path"),
): Promise<ManifestFile[]> {
  const { readFile } = await import("node:fs/promises");
  let entries: string[] = [];
  try {
    entries = await readdir(dir);
  } catch {
    return [];
  }
  const out: ManifestFile[] = [];
  for (const name of entries) {
    if (!MANIFEST_NAMES.has(name)) continue;
    try {
      out.push({ path: name, bytes: await readFile(path.join(dir, name)) });
    } catch {
      /* unreadable — skip */
    }
  }
  return out;
}

/**
 * Create a sandbox for `url`: labeled named volume -> clone into it -> build/reuse
 * image -> run an isolated container. Every object is labeled `ca.sandbox=1` +
 * `ca.sandbox.id=<id>` for label-only registry/teardown.
 *
 * @throws if volume creation, the clone, the build, or the run fails. On a
 *   failure AFTER the volume exists, partial objects are torn down (no leak).
 */
export async function createSandbox(
  url: string,
  opts: CreateOptions = {},
): Promise<CreateResult> {
  // The url is untrusted: validate it before it touches git's argv (the clone
  // step runs git, networked, in a throwaway container — a malicious url must not
  // inject git arguments or a remote-helper command there).
  validateRepoUrl(url);

  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const cloneRepo = opts.cloneRepo ?? defaultCloneRepo;
  const buildImage = opts.buildImage ?? defaultBuildImage;
  const netPolicy = opts.netPolicy ?? "offline";
  const id = opts.id ?? newSandboxId();
  const volumeName = `${VOLUME_PREFIX}-${id}`;
  const sandboxLabels = [SANDBOX_LABEL, idLabel(id), ...(opts.extraLabels ?? [])];

  // 1. Labeled named volume (the live source mount). Labels make it discoverable
  // by destroy/prune via label filter alone.
  const volLabelArgs = sandboxLabels.flatMap((l) => ["--label", l]);
  const mk = dockerRun(["volume", "create", ...volLabelArgs, volumeName]);
  if (mk.code !== 0) {
    throw new Error(
      `ca-sandbox: failed to create volume ${volumeName} (exit ${mk.code})\n${mk.stderr.slice(-1000)}`,
    );
  }

  // From here on, tear down the volume (and anything else) on any failure so a
  // failed create never leaves a labeled half-sandbox behind.
  try {
    // 2. Clone INTO the volume via the throwaway alpine/git container (net up).
    const cloneCode = await cloneRepo(url, volumeName);
    if (cloneCode !== 0) {
      throw new Error(`ca-sandbox: clone of ${url} into ${volumeName} failed (exit ${cloneCode})`);
    }

    // 3. Build (or reuse) the image — dephash-cached, deps relocated to /deps.
    const build = await buildImage(volumeName);

    // 4. Run the isolated sandbox container, labeled with the id.
    const containerId = runContainer(build.tag, volumeName, netPolicy, {
      extraLabels: [idLabel(id), ...(opts.extraLabels ?? [])],
      namePrefix: `ca-sbx-${id}`,
      dockerRun: opts.dockerRun
        ? (args) => opts.dockerRun!(args)
        : undefined,
    });

    return {
      id,
      volumeName,
      image: build.tag,
      containerId,
      notes: build.notes,
    };
  } catch (err) {
    // Best-effort teardown of the labeled objects of THIS id (label-only).
    dockerRun(["volume", "rm", "-f", volumeName]);
    const leftover = dockerRun([
      "ps",
      "-a",
      "-q",
      "--no-trunc",
      "--filter",
      `label=${idLabel(id)}`,
    ]);
    for (const c of leftover.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)) {
      dockerRun(["rm", "-f", c]);
    }
    throw err;
  }
}
