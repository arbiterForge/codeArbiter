/**
 * create.ts — ca-sandbox lifecycle entry (T-09, covers AC-01 / AC-11).
 *
 * await createSandbox(url, opts) pulls an untrusted repo into an isolated, ephemeral
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
 *      NOT a sandbox object (destroy.ts never targets it directly), but it DOES
 *      carry the `ca.sandbox=1` + `ca.sandbox.id=<id>` labels (reliability-015)
 *      so await prune()'s sweep can still reclaim it if it outlives its `--rm`, and it
 *      is never co-run with the untrusted code: clone-then-cut.
 *   4. BUILD (or reuse) the image via build.ts (dephash-cached, deps to /deps).
 *   5. RUN the sandbox container via run.ts — structurally isolated, no host bind,
 *      offline by default — tagging it `ca.sandbox=1` + `ca.sandbox.id=<id>`.
 *
 * Everything created is labeled so destroy.ts / await prune() can reclaim it by label
 * alone — INCLUDING the throwaway clone container and the docker-cp helper
 * (reliability-015): both now carry `ca.sandbox=1` + `ca.sandbox.id=<id>` even
 * though neither is a sandbox object itself, so a hung clone / a host crash
 * mid-create still leaves something `await prune()` can reclaim, and each step is
 * wall-clock timed out so a dead remote / giant repo cannot hang forever. On
 * any failure AFTER the volume is created, the partial objects are torn down —
 * containers FIRST, then the volume (matching destroySandbox's order, so an
 * in-use volume never fails to remove) — and verified independently. Unknown cleanup retains the exact references; a
 * failed Docker observation never establishes absence.
 *
 * Process/shell handling routes through docker.ts (architecture-007): an
 * injectable docker runner, MSYS_NO_PATHCONV=1 on Windows + Git Bash (Spike
 * A/B), and a deterministic id derived from crypto random bytes (farm.ts
 * hashing style).
 */
import { randomBytes } from "node:crypto";
import { readdir } from "node:fs/promises";
import { runContainer, ordinaryNetworkCapability, type NetPolicy } from "./run.ts";
import { buildMountArgs } from "./mounts.ts";
import { buildOrReuseImage, type BuildResult, type BuildDeps } from "./build.ts";
import { computeDepHash, type ManifestFile } from "./dephash.ts";
import { SANDBOX_LABEL, idLabel, listContainersResult } from "./registry.ts";
import { DOCKER_ENV, defaultDockerRun, makeDockerRun, type DockerRun } from "./docker.ts";

/**
 * Image used for the throwaway clone step (small, git built in), PINNED to a
 * reviewed multi-arch index digest (issue #402). A floating tag would let a
 * retag or registry compromise swap the binary that checks out attacker-supplied
 * source into the sandbox volume. Docker resolves the digest, not the tag, so
 * the tag is kept only as human-readable provenance.
 *
 * Resolved 2026-07-24 with `docker buildx imagetools inspect alpine/git` (which
 * resolves the default tag).
 * Bump this ONLY through a reviewed dependency change (re-resolve the digest,
 * re-run the ca-sandbox suite including the docker-gated lifecycle tests).
 */
export const CLONE_IMAGE =
  "alpine/git:latest@sha256:77418e6e7c7f434c4a98eaff04ef16840cf03649c881c03948e3e213923e3136";
/** In-container app dir; the source volume mounts here for both clone and run. */
export const APP_DIR = "/work/repo";
/** Prefix for the named volume of a sandbox. */
export const VOLUME_PREFIX = "ca-sbx-vol";
/**
 * Wall-clock timeout (ms) for the throwaway clone step (reliability-015). A
 * dead remote or a giant repo must not hang the helper container forever;
 * exceeding this kills the local `docker run` client (SIGTERM, then the
 * process's own close handling resolves). The clone container is labeled
 * regardless of outcome, so even a kill that outlives the client-side timeout
 * (docker's sig-proxy is best-effort) leaves an object `await prune()` reclaims.
 * Overridable for tests via CA_SANDBOX_CLONE_TIMEOUT_MS.
 */
export const CLONE_TIMEOUT_MS = Number(process.env.CA_SANDBOX_CLONE_TIMEOUT_MS ?? 5 * 60_000);
/**
 * Wall-clock timeout (ms) for each docker-cp helper step (create + cp) used to
 * materialize a temp checkout for dephash/build (reliability-015). Overridable
 * for tests via CA_SANDBOX_CP_TIMEOUT_MS.
 */
export const CP_TIMEOUT_MS = Number(process.env.CA_SANDBOX_CP_TIMEOUT_MS ?? 2 * 60_000);

/** Result returned by the injectable repo cloner. */
export type CloneResult = { code: number; stderr: string };
export type Compensation = { verified: boolean; containers: string[]; volume: string; failures: string[] };
export type BuildStagingCleanup = {
  helper: string; staging: string; removeCode: number; observationCode: number; stagingRemoved: boolean;
};
/** Build failure and independent staging observations have separate identities. */
export class BuildStagingFailure extends Error {
  constructor(readonly primaryFailure: unknown, readonly cleanup: BuildStagingCleanup) {
    const primary = primaryFailure === undefined ? "" :
      `${primaryFailure instanceof Error ? primaryFailure.message : String(primaryFailure)}\n`;
    super(`${primary}ca-sandbox: build staging cleanup unknown; helper=${cleanup.helper} (remove=${cleanup.removeCode}), staging=${cleanup.staging}`,
          primaryFailure === undefined ? undefined : { cause: primaryFailure });
    this.name = "BuildStagingFailure";
  }
}
export class CreateFailure extends Error {
  constructor(message: string, readonly id: string, readonly volumeName: string, readonly cleanup: Compensation, cause?: unknown) {
    super(`${message}\nca-sandbox: cleanup ${cleanup.verified ? "verified absent" : "unknown"}; sandbox=${id}, volume=${volumeName}; containers=${cleanup.containers.join(",") || "unobserved"}`,
          cause === undefined ? undefined : { cause });
    this.name = "CreateFailure";
  }
}
/** Compensation owns a fresh observation budget even after ordinary cancellation. */
export async function compensateCreate(id: string, volume: string, dockerRun: DockerRun): Promise<Compensation> {
  const failures: string[] = [];
  const scope = [SANDBOX_LABEL, idLabel(id)];
  const before = await listContainersResult(scope, dockerRun);
  if (before.code !== 0) failures.push(`container discovery unavailable (${before.code})`);
  // Never parse partial failure stdout as an authorized target set.
  const targets = before.code === 0 ? before.items : [];
  for (const target of targets) {
    const removed = await dockerRun(["rm", "-f", target]);
    if (removed.code !== 0) failures.push(`container removal unverified: ${target} (${removed.code})`);
  }
  const removedVolume = await dockerRun(["volume", "rm", "-f", volume]);
  if (removedVolume.code !== 0) failures.push(`volume removal unverified (${removedVolume.code})`);
  const after = await listContainersResult(scope, dockerRun);
  const volumes = await dockerRun(["volume", "ls", "-q", "--filter", `name=^${volume}$`]);
  const volumePresent = volumes.stdout.split(/\r?\n/).some(v => v.trim() === volume);
  const verified = before.code === 0 && after.code === 0 && !after.items.length && volumes.code === 0 && !volumePresent;
  if (!verified) failures.push("resource absence not verified");
  return { verified, containers: after.code === 0 ? after.items : targets, volume, failures };
}

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
   * Cancellation for the docker calls this create makes (#479). On abort
   * the failure path runs its normal best-effort teardown, so a cancelled
   * create does not leave the half-built sandbox behind.
   */
  signal?: AbortSignal;
  /**
   * Injectable repo cloner. Defaults to the throwaway alpine/git container.
   * Accepts either the new `CloneResult` shape (preferred — surfaces git stderr in
   * error messages) or a plain exit-code number (backward-compatible with existing
   * tests; treated as having no stderr).
   */
  cloneRepo?: (url: string, volumeName: string, id: string, signal?: AbortSignal) => Promise<CloneResult | number>;
  /**
   * Injectable image builder. Defaults to build.ts buildOrReuseImage over a
   * temp checkout. Tests inject a fake that returns a prebuilt tag.
   */
  buildDeps?: BuildDeps;
  buildImage?: (volumeName: string, id: string, signal?: AbortSignal) => Promise<BuildResult>;
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
  network?: ReturnType<typeof ordinaryNetworkCapability>;
  /** The minted (or supplied) sandbox id. */
  id: string;
  /** The named volume holding the cloned source. */
  volumeName: string;
  /** The built/reused image tag. */
  image: string;
  imageId?:string;
  /** The started container id. */
  containerId: string;
  /** Build notes (e.g. nixpacks-missing fallback). */
  notes: string[];
};

/** A short, url-safe random id (12 hex chars), mirroring run.ts's name suffix. */
export function newSandboxId(): string {
  return randomBytes(6).toString("hex");
}

/** Spawn `cmd` asynchronously and resolve with the exit code and captured stderr.
 * stderr is collected (up to 500 bytes, last slice) so clone/pull failures can
 * surface actionable diagnostics (e.g. "fatal: repository not found"). argv and
 * env are never included in the returned value — only the child process's own
 * stderr stream is captured, keeping the secret-free contract of the failure path.
 *
 * `timeoutMs` (reliability-015) bounds the wall-clock time of the spawned
 * process: Node's own `timeout` spawn option sends `killSignal` (default
 * SIGTERM) once it elapses, so a dead remote / hung clone cannot block this
 * promise forever. The underlying docker container may still carry on past
 * the client-side kill (docker's sig-proxy is best-effort against SIGTERM) —
 * that is exactly why the CALLER must label the container so `await prune()` can
 * reclaim it regardless.
 */
async function spawnAsync(cmd: string, args: string[], timeoutMs?: number, signal?: AbortSignal): Promise<CloneResult> {
  if (cmd !== "docker") throw new Error("ca-sandbox: unsupported clone process");
  const result = await makeDockerRun({}, {timeoutMs})(args, { signal });
  return { code: result.code, stderr: result.stderr.slice(-500) };
}

/**
 * Clone `url` INTO the named volume via a throwaway alpine/git container with
 * networking up. The container mounts the volume at /work/repo and is `--rm`'d
 * the instant the clone finishes. It is NOT a sandbox object (destroy.ts never
 * targets it directly), but it now carries `ca.sandbox=1` + `ca.sandbox.id=<id>`
 * (reliability-015) so a hung clone / a host crash before the `--rm` fires still
 * leaves something `await prune()` can reclaim, and it is wall-clock timed out
 * (CLONE_TIMEOUT_MS) so a dead remote cannot hang indefinitely.
 */
export async function defaultCloneRepo(
  url: string,
  volumeName: string,
  id: string,
  signal?: AbortSignal,
): Promise<CloneResult> {
  return spawnAsync("docker", buildCloneArgs(url, volumeName, id), CLONE_TIMEOUT_MS, signal);
}

/**
 * The docker argv (everything after `docker`) for the throwaway clone container.
 * Pure so the argument-injection-hardening invariant is unit-testable:
 * `clone --depth 1 -- <url> <dir>` — the `--` end-of-options separator sits
 * directly before the untrusted url so a leading-`-` value can never be parsed by
 * git as a flag (belt to validateRepoUrl's suspenders). alpine/git ENTRYPOINT is
 * `git`, so the args after the image are git's; clone goes straight into the
 * volume mounted at /work/repo.
 *
 * Labeled `ca.sandbox=1` + `ca.sandbox.id=<id>` (reliability-015) — the ONE
 * change from the pre-fix argv shape — so this throwaway container is
 * discoverable by `await prune()`'s label sweep even though it is never a registered
 * sandbox object.
 */
export function buildCloneArgs(url: string, volumeName: string, id: string): string[] {
  return [
    "run",
    "--rm",
    // Mount via the buildMountArgs chokepoint (architecture-006) so this caller is
    // covered by the bind-rejection guarantee and there is genuinely one mount-argv
    // path. Same volume spec as before -> byte-identical argv.
    ...buildMountArgs([{ type: "volume", source: volumeName, target: APP_DIR }]),
    "--label",
    SANDBOX_LABEL,
    "--label",
    idLabel(id),
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
 * The docker argv (everything after `docker`) for the `docker create` step of
 * the throwaway docker-cp helper container. Pure so the labeling is
 * unit-testable without docker. Labeled `ca.sandbox=1` + `ca.sandbox.id=<id>`
 * (reliability-015) — the helper is never a registered sandbox object (it
 * exists only to `docker cp` a temp checkout out of the volume), but the label
 * makes it discoverable by `await prune()`'s sweep if the host process dies before
 * the `finally` block's `docker rm -f` runs.
 */
export function buildCpHelperCreateArgs(volumeName: string, helperName: string, id: string): string[] {
  return [
    "create",
    "--name",
    helperName,
    "--label",
    SANDBOX_LABEL,
    "--label",
    idLabel(id),
    // Same buildMountArgs chokepoint as buildCloneArgs (architecture-006).
    ...buildMountArgs([{ type: "volume", source: volumeName, target: APP_DIR }]),
    CLONE_IMAGE,
    "true",
  ];
}

/**
 * Default image build: copy the cloned source OUT of the volume into a temp dir
 * (so build.ts can read manifests + run a docker build context), compute the
 * dephash from the manifest set, then buildOrReuseImage. The clone lives only in
 * the volume, so we materialize a transient checkout via a throwaway container's
 * `docker cp`. Kept injectable; the docker-gated lifecycle test exercises the
 * REAL default end to end on a tiny repo.
 *
 * The helper container is labeled and each docker step (create + cp) is
 * wall-clock timed out (CP_TIMEOUT_MS, reliability-015) so a stuck copy cannot
 * hang forever and, if it does, the label still makes it `await prune()`-reclaimable.
 */
async function defaultBuildImage(volumeName: string, id: string, signal?: AbortSignal, buildDeps?:BuildDeps): Promise<BuildResult> {
  const { mkdtemp, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const path = await import("node:path");
  const dir = await mkdtemp(path.join(tmpdir(), "ca-sbx-checkout-"));
  // Materialize the volume contents to the host temp dir via a helper container:
  // mount the volume read-only and `docker cp` its /work/repo out.
  const helper = `ca-sbx-cp-${newSandboxId()}`;
  let helperCreated=false;
  let primaryFailure: unknown;
  try {
    const createResult = await makeDockerRun({}, {timeoutMs:CP_TIMEOUT_MS})(buildCpHelperCreateArgs(volumeName, helper, id), {signal});
    if (createResult.code !== 0) throw new Error(`ca-sandbox: helper creation unavailable (exit ${createResult.code}); target=${helper}`);
    helperCreated=true;
    const cpResult = await makeDockerRun({}, {timeoutMs:CP_TIMEOUT_MS})(["cp", `${helper}:${APP_DIR}/.`, dir], {signal});
    if (cpResult.code !== 0) throw new Error(`ca-sandbox: checkout materialization unavailable (exit ${cpResult.code}); target=${helper}`);
    const manifests = await readManifests(dir, path);
    const dephash = computeDepHash(manifests);
    return await buildOrReuseImage(dir, dephash, buildDeps, undefined, signal);
  } catch (error) {
    primaryFailure = error;
    throw error;
  } finally {
    // Cleanup has independent authority; observe this exact named helper.
    const removed = helperCreated ? await defaultDockerRun(["rm", "-f", helper]) : {code:1};
    const observed = await defaultDockerRun(["ps", "-a", "-q", "--filter", `name=^/${helper}$`]);
    let stagingRemoved = false;
    try { await rm(dir, { recursive: true, force: true }); stagingRemoved = true; } catch { /* reported below */ }
    if (observed.code !== 0 || observed.stdout.trim() || !stagingRemoved) {
      throw new BuildStagingFailure(primaryFailure, {
        helper, staging: dir, removeCode: removed.code,
        observationCode: observed.code, stagingRemoved,
      });
    }
  }
}

const MANIFEST_NAMES = new Set([
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
  "Cargo.lock",
]);

export async function readManifests(
  dir: string,
  path: typeof import("node:path"),
): Promise<ManifestFile[]> {
  const { readFile, lstat } = await import("node:fs/promises");
  const entries = await readdir(dir);
  const out: ManifestFile[] = [];
  for (const name of entries) {
    if (!MANIFEST_NAMES.has(name)) continue;
    const inputPath=path.join(dir,name);
    try {
      const entry=await lstat(inputPath);
      if(!entry.isFile() || entry.isSymbolicLink()) {
        throw new Error("unsafe declared input");
      }
      out.push({ path: name, bytes: await readFile(inputPath) });
    } catch(error) {
      // Only an actually absent input may be omitted. A dangling link is
      // present, and EISDIR/EACCES/EPERM or a failed observation is unavailable.
      if((error as NodeJS.ErrnoException).code==="ENOENT") {
        try { await lstat(inputPath); }
        catch(observed) {
          if((observed as NodeJS.ErrnoException).code==="ENOENT") continue;
        }
      }
      const code=(error as NodeJS.ErrnoException).code ?? "unsafe input";
      throw new Error(`ca-sandbox: manifest observation unavailable: ${name} (${code}); cache/build admission refused`);
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
  const buildImage = opts.buildImage ?? ((volume:string,id:string,signal?:AbortSignal)=>defaultBuildImage(volume,id,signal,opts.buildDeps));
  const netPolicy = opts.netPolicy ?? "offline";
  const id = opts.id ?? newSandboxId();
  const volumeName = `${VOLUME_PREFIX}-${id}`;
  const sandboxLabels = [SANDBOX_LABEL, idLabel(id), ...(opts.extraLabels ?? [])];

  // 1. Labeled named volume (the live source mount). Labels make it discoverable
  // by destroy/prune via label filter alone.
  const volLabelArgs = sandboxLabels.flatMap((l) => ["--label", l]);
  const mk = await dockerRun(["volume", "create", ...volLabelArgs, volumeName],
                             { signal: opts.signal });
  if (mk.code !== 0) {
    throw new CreateFailure(`ca-sandbox: failed to create volume ${volumeName} (exit ${mk.code})`,id,volumeName,
      {verified:false,containers:[],volume:volumeName,failures:["volume creation effect unknown; inspect before cleanup or a new create"]});
  }

  // From here on, tear down the volume (and anything else) on any failure and observes its outcome independently. Unknown cleanup remains visible.
  try {
    // 2. Clone INTO the volume via the throwaway alpine/git container (net up).
    const cloneRaw = await cloneRepo(url, volumeName, id, opts.signal);
    // Accept either a plain exit code (backward-compatible) or a CloneResult with
    // captured stderr (preferred — surfaces actionable git diagnostics on failure).
    const cloneCode = typeof cloneRaw === "number" ? cloneRaw : cloneRaw.code;
    const cloneStderr = typeof cloneRaw === "number" ? "" : cloneRaw.stderr;
    if (cloneCode !== 0) {
      const hint = cloneStderr.trim() ? `\n${cloneStderr.trim()}` : "";
      throw new Error(
        `ca-sandbox: clone of ${url} into ${volumeName} failed (exit ${cloneCode})${hint}`,
      );
    }

    opts.signal?.throwIfAborted();
    // 3. Build (or reuse) the image — dephash-cached, deps relocated to /deps.
    const build = await buildImage(volumeName, id, opts.signal);

    opts.signal?.throwIfAborted();
    // 4. Run the isolated sandbox container, labeled with the id.
    const containerId = await runContainer(build.imageId ?? build.tag, volumeName, netPolicy, {
      extraLabels: [idLabel(id), ...(opts.extraLabels ?? [])],
      namePrefix: `ca-sbx-${id}`,
      signal: opts.signal,
      dockerRun: opts.dockerRun
        ? (args, call) => opts.dockerRun!(args, call)
        : undefined,
    });

    return {
      id,
      volumeName,
      network:ordinaryNetworkCapability(netPolicy),
      image: build.tag,
      imageId:build.imageId,
      containerId,
      notes: build.notes,
    };
  } catch (err) {
    const cleanup = await compensateCreate(id, volumeName, dockerRun);
    throw new CreateFailure(err instanceof Error ? err.message : String(err), id, volumeName, cleanup, err);
  }
}
