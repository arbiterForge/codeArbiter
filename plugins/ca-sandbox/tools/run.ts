/**
 * run.ts — ca-sandbox container start (T-06, covers AC-01).
 *
 * runContainer(image, volumeName, netPolicy) starts a detached, structurally
 * isolated sandbox container for an already-built image. The load-bearing
 * invariant (spec "Load-bearing invariant" / AC-01): untrusted code inside the
 * box can NEVER reach the host filesystem. That is enforced here STRUCTURALLY,
 * by construction, not by trust:
 *
 *   docker run -d
 *     --mount type=volume,source=<vol>,target=/work/repo   (the live source
 *         volume — built via mounts.ts's buildMountArgs, which THROWS on any
 *         bind spec, so a host bind can never enter the argv)
 *     --tmpfs /tmp            (writable scratch with no host backing)
 *     --workdir /work/repo
 *     --user 1000:1000        (non-root)
 *     --read-only             (read-only root fs)
 *     --cap-drop ALL          (no Linux capabilities)
 *     --security-opt no-new-privileges
 *     --pids-limit 512 --memory 4g --cpus 2   (resource caps)
 *     --label ca.sandbox=1    (lifecycle/registry label — AC-11)
 *     <image> sleep infinity  (keep-alive so the box stays up to exec into)
 *
 * NEGATIVE guarantees, enforced structurally: NO host bind mount, NO
 * /var/run/docker.sock mount, NEVER --privileged. The mount argv is built ONLY
 * through buildMountArgs (mounts.ts), so the single mount chokepoint rejects
 * binds before any argv is produced — run.ts never hand-rolls a `-v` or a
 * `type=bind`.
 *
 * Network is configurable (offline / clone-then-cut / allowlist — T-10 owns the
 * richer policy). T-06 wires only the safe default: `offline` => `--network none`.
 * Any other policy is passed through untouched here (T-10 layers the real flags).
 *
 * Process/shell handling routes through docker.ts (architecture-007): a shared
 * docker-runner returning a RunResult, and on Windows + Git Bash
 * MSYS_NO_PATHCONV=1 is set so in-container paths passed to docker are not
 * mangled (Spike A/B).
 */
import { buildMountArgs, type MountSpec } from "./mounts.ts";
import { defaultDockerRun, type RunResult } from "./docker.ts";

/** In-container app dir; the live source named volume mounts here (Spike A). */
export const APP_DIR = "/work/repo";
/** The lifecycle/registry label every sandbox container carries (AC-11). */
export const SANDBOX_LABEL = "ca.sandbox=1";
/** Non-root uid:gid the container process runs as. */
export const SANDBOX_USER = "1000:1000";

/**
 * Network policy for a sandbox run. T-06 only distinguishes the safe default
 * (`offline` => no networking at all); the richer clone-then-cut / allowlist
 * policies are layered by T-10 (AC-08). A string is accepted so this stays a
 * stable seam — but the resolution is FAIL-CLOSED (dx-006): only a policy in the
 * closed NETWORKED_POLICIES set escapes the airgap, so a typo of `offline` (or
 * any policy no layer implements) gets `--network none` rather than silently
 * running networked.
 */
export type NetPolicy = "offline" | (string & {});

/**
 * The closed set of policies that intentionally run WITH networking. T-10 adds
 * its allowlist/clone-then-cut policy names here as it implements them. EMPTY
 * today: the only T-06 posture is the airgap, so every policy — including
 * `offline` and any misspelling of it — currently resolves to `--network none`.
 * This is the fail-closed safe default (dx-006): the airgap is only dropped for
 * an EXACT, recognized networked policy, never for an unrecognized string.
 */
const NETWORKED_POLICIES: ReadonlySet<string> = new Set<string>();

/** Optional knobs for runContainer that the test harness / callers may set. */
export type RunOptions = {
  /**
   * Extra `key=value` labels in addition to the always-present ca.sandbox=1
   * (e.g. the build/test marker `ca.sandbox.build=1`, or a per-id label).
   */
  extraLabels?: string[];
  /**
   * Optional `--name` prefix; when set the container is named
   * `<prefix>-<short-random>` so test objects are easy to find and clean up.
   */
  namePrefix?: string;
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: (args: string[]) => RunResult;
};

export type { RunResult };

/**
 * Assemble the full `docker run` argv (everything AFTER `docker`) for an
 * isolated sandbox container. Pure: builds the array, runs nothing — so the
 * isolation flags are unit-testable without real docker. The mount argv comes
 * ONLY from buildMountArgs, so a bind can never be hand-rolled in here.
 *
 * @throws if image or volumeName is empty (a sandbox must have both).
 * @throws (BindMountRejectedError, via buildMountArgs) — unreachable here since
 *   we only construct volume/tmpfs specs, but the chokepoint is the guarantee.
 */
/**
 * The shared container hardening argv (architecture-002). This block is
 * security-load-bearing — non-root, read-only root fs, a tmpfs /tmp, every Linux
 * capability dropped, no privilege escalation, and resource caps. It is defined
 * ONCE here and spliced by BOTH buildRunArgs and claude-inside.ts's
 * buildClaudeRunArgs, so the token-bearing --with-claude box can never drift to a
 * softer lockdown than the ordinary sandbox. NOT included: --workdir (the two
 * callers point it at different in-container dirs) and the per-call mount/label/
 * network/name argv.
 */
export function hardeningFlags(): string[] {
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
    "2",
  ];
}

export function buildRunArgs(
  image: string,
  volumeName: string,
  netPolicy: NetPolicy,
  opts: RunOptions = {},
): string[] {
  if (!image) throw new Error("ca-sandbox: runContainer requires a non-empty image");
  if (!volumeName) throw new Error("ca-sandbox: runContainer requires a non-empty volume name");

  // Mounts go through the ONE chokepoint (mounts.ts). The live source volume at
  // /work/repo and the tmpfs /tmp are the only mounts — both bind-free by type.
  const mountSpecs: MountSpec[] = [
    { type: "volume", source: volumeName, target: APP_DIR },
    { type: "tmpfs", target: "/tmp" },
  ];
  const mountArgs = buildMountArgs(mountSpecs);

  const labels = [SANDBOX_LABEL, ...(opts.extraLabels ?? [])];
  const labelArgs = labels.flatMap((l) => ["--label", l]);

  const nameArgs =
    opts.namePrefix
      ? ["--name", `${opts.namePrefix}-${Math.random().toString(16).slice(2, 10)}`]
      : [];

  // Network: the safe default is total isolation, resolved FAIL-CLOSED (dx-006).
  // Only an EXACT, recognized networked policy (T-10 registers these in
  // NETWORKED_POLICIES) skips the airgap; every other value — "offline", a typo
  // of it, or any unimplemented policy — gets --network none. A misspelled
  // policy can never silently drop the airgap onto docker's default bridge.
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
    "infinity",
  ];
}

/**
 * Start an isolated sandbox container for `image` with the live source named
 * volume at /work/repo, under the network policy. Returns the started
 * container id (docker run -d prints the full id to stdout).
 *
 * @param image the built sandbox image tag (`ca-sbx:<repo>-<dephash>`).
 * @param volumeName the docker named volume holding the cloned source.
 * @param netPolicy network policy (T-06 wires `offline`; T-10 the rest).
 * @param opts optional labels / name prefix / injectable docker runner.
 * @returns the container id.
 * @throws if `docker run` fails (non-zero exit).
 */
export function runContainer(
  image: string,
  volumeName: string,
  netPolicy: NetPolicy,
  opts: RunOptions = {},
): string {
  const args = buildRunArgs(image, volumeName, netPolicy, opts);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const r = dockerRun(args);
  if (r.code !== 0) {
    throw new Error(
      `ca-sandbox: docker run failed for ${image} (exit ${r.code})\n${(r.stderr || r.stdout).slice(-2000)}`,
    );
  }
  return r.stdout.trim();
}
