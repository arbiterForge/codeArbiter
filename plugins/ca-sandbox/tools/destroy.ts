/**
 * destroy.ts — ca-sandbox teardown + prune (T-09, covers AC-11).
 *
 * await destroySandbox(id, opts) removes the docker objects of ONE sandbox, discovered
 * purely by the `ca.sandbox.id=<id>` label (no JSON file — registry.ts is the
 * label-only state). It `docker rm -f`'s every labeled container and `volume rm`'s
 * the named volume UNLESS `--keep-volume` is set, in which case the container goes
 * but the volume (the cloned source) is preserved for a later re-run.
 *
 * await prune(opts) reclaims EVERY object carrying `ca.sandbox=1` — including a
 * manually-leaked one that lost its id label — so a partial/abandoned sandbox can
 * always be swept. This is the AC-11 guarantee: after a normal `create -> destroy`
 * there are zero `ca.sandbox=1` objects; a leaked labeled object is reclaimed by
 * `prune`.
 *
 * The contract: `destroySandbox` (no keepVolume) and `prune` both leave zero
 * `ca.sandbox=1` containers/volumes for the objects they target (cached images
 * are excepted — images are tracked by tag, never torn down here). Process/shell
 * handling mirrors registry.ts: injectable docker runner, MSYS_NO_PATHCONV=1 on
 * Windows + Git Bash (Spike A/B).
 *
 * FAILURE IS PART OF THE CONTRACT (#393). Both verbs used to write
 * `if (r.code === 0) removed.push(x)` and silently drop every non-zero docker
 * result, and the CLI returned 0 regardless — so a daemon outage, a permission
 * error, or an in-use object left UNTRUSTED containers and source volumes running
 * while automation read exit 0. The teardown guarantee was therefore false on the
 * exact path where cleanup matters. Now:
 *
 *   - every failed removal lands in a BOUNDED `failures` list (`failureCount`
 *     stays truthful past the bound) instead of being discarded;
 *   - a failure never aborts the sweep — partial teardown must still reclaim
 *     everything it can, so all discovered targets are attempted;
 *   - a failed DISCOVERY or VERIFICATION listing is itself a failure: "listed
 *     nothing while the daemon was down" must never read as "nothing is left";
 *   - after the removals a final label-scoped re-list reports what is STILL
 *     PRESENT (`remainingContainers` / `remainingVolumes`), naming the objects an
 *     operator has to clean up by hand. A `--keep-volume` volume is deliberate
 *     and is excluded from that set.
 *
 * The verbs still RETURN a structured result rather than throwing — the exit-code
 * decision belongs to the CLI (`teardownIncomplete` / `formatTeardownDiagnostic`),
 * so a library caller can inspect a partial teardown instead of catching.
 */
import {
  SANDBOX_LABEL,
  idLabel,
  listContainersResult,
  listVolumesResult,
  defaultDockerRun,
  type DockerRun,
} from "./registry.ts";

/**
 * At most this many individual failures are retained. The list is a diagnostic,
 * not a ledger: a wedged daemon can fail hundreds of removals and an unbounded
 * list would be echoed into stdout JSON and stderr verbatim. `failureCount`
 * remains exact, so the bound never understates the damage.
 */
export const MAX_TEARDOWN_FAILURES = 25;

/** At most this many refs are named per category in the stderr diagnostic. */
export const MAX_DIAGNOSTIC_REFS = 25;

/** docker stderr is truncated to this many characters per failure. */
export const MAX_FAILURE_MESSAGE_CHARS = 300;

/** What failed: a removal, or the listing that finds/verifies the targets. */
export type TeardownOp =
  | "remove-container"
  | "remove-volume"
  | "list-containers"
  | "list-volumes";

/** One docker operation that failed during teardown. */
export type TeardownFailure = {
  /** Which operation failed. */
  op: TeardownOp;
  /** The object left behind, or (for a listing) the label scope queried. */
  ref: string;
  /** docker's exit code. */
  code: number;
  /** Bounded, single-line docker stderr. */
  message: string;
};

/** The failure surface both teardown verbs share. */
export type TeardownReport = {
  /** Failed operations, capped at MAX_TEARDOWN_FAILURES. */
  failures: TeardownFailure[];
  /** Total failed operations, including any past the cap. */
  failureCount: number;
  /** Containers still carrying the target labels after teardown. */
  remainingContainers: string[];
  /** Volumes still carrying the target labels after teardown (kept ones excluded). */
  remainingVolumes: string[];
};

export type DestroyOptions = {
  /** Keep the named volume (the cloned source) — only remove the container. */
  keepVolume?: boolean;
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: DockerRun;
};

export type DestroyResult = TeardownReport & {
  /** The sandbox id targeted. */
  id: string;
  /** Container ids removed. */
  removedContainers: string[];
  /** Volume names removed (empty when keepVolume). */
  removedVolumes: string[];
  /** Volume names deliberately kept (keepVolume). */
  keptVolumes: string[];
};

/**
 * Accumulates failures while enforcing the retention bound, collapsing repeats.
 *
 * #433: one unreachable daemon used to read as FOUR failures. Discovery lists
 * containers and volumes, then the post-sweep verification re-lists the same two
 * scopes against the same dead daemon - four entries carrying the identical
 * "Cannot connect to the Docker daemon" for one fact. Measured against the
 * shipped artifact: `DOCKER_HOST=tcp://127.0.0.1:1 node sandbox.js prune`
 * reported `failureCount: 4`. An operator counting failures was being told the
 * damage was four times what it was.
 *
 * What counts as "the same fact" differs by operation, deliberately:
 *
 *   * A LISTING failure describes the DAEMON, not the scope. `list-containers`
 *     and `list-volumes` returning the same error code and message is one
 *     unreachable daemon reported twice, not two problems - so listings dedup on
 *     (code, message) and the first one recorded wins. Its message carries the
 *     actionable part; the scope does not change the remedy.
 *   * A REMOVAL failure describes ONE object, so it dedups on the whole identity
 *     (op, ref, code, message). Two containers refusing removal for their own
 *     reasons stay two failures - collapsing those would understate the damage.
 *
 * `count` counts distinct failures, so the retention bound still never
 * understates what happened.
 */
class FailureLog {
  readonly failures: TeardownFailure[] = [];
  count = 0;
  private readonly seen = new Set<string>();

  add(op: TeardownOp, ref: string, code: number, stderr: string): void {
    const message = oneLine(stderr);
    const listing = op === "list-containers" || op === "list-volumes";
    const identity = listing
      ? listingFingerprint(code, message)
      : `${op}\u0000${ref}\u0000${code}\u0000${message}`;
    if (this.seen.has(identity)) return;
    this.seen.add(identity);
    this.count += 1;
    if (this.failures.length >= MAX_TEARDOWN_FAILURES) return;
    this.failures.push({ op, ref, code, message });
  }
}

/**
 * The identity of a LISTING failure, for dedup purposes (#433).
 *
 * Keyed on the failure's SHAPE, not its text. Against a real dead daemon the two
 * discovery listings return the same connection error carrying DIFFERENT URLs -
 *
 *   error during connect: Get "http://127.0.0.1:1/v1.54/containers/json?..."
 *   error during connect: Get "http://127.0.0.1:1/v1.54/volumes?..."
 *
 * - so comparing whole messages collapses nothing and the operator still counts
 * one unreachable daemon as several failures. Stripping the quoted URL leaves
 * exactly the part that identifies the fault, so `connection refused` on both
 * listings reads as one problem while a genuinely different pair (say a
 * permission error on one and a connection error on the other) still reads as
 * two. This is used ONLY for dedup; the retained message is untouched.
 */
function listingFingerprint(code: number, message: string): string {
  const shape = message
    .replace(/"[^"]*"/g, '"<url>"')
    .replace(/https?:\/\/\S+/g, "<url>")
    .replace(/\d+/g, "<n>");
  return `listing\u0000${code}\u0000${shape}`;
}

/** Collapse docker stderr to a bounded single line for a diagnostic. */
function oneLine(stderr: string): string {
  const s = stderr.replace(/\s+/g, " ").trim();
  if (!s) return "(no stderr from docker)";
  return s.length > MAX_FAILURE_MESSAGE_CHARS ? `${s.slice(0, MAX_FAILURE_MESSAGE_CHARS)}...` : s;
}

/**
 * Remove each ref, recording failures instead of dropping them. Every ref is
 * attempted even after one fails — a partial teardown must still reclaim what it
 * can. Returns the refs that were actually removed.
 */
async function removeEach(
  refs: string[],
  kind: "container" | "volume",
  dockerRun: DockerRun,
  log: FailureLog,
): Promise<string[]> {
  const removed: string[] = [];
  for (const ref of refs) {
    const args = kind === "container" ? ["rm", "-f", ref] : ["volume", "rm", "-f", ref];
    const r = await dockerRun(args);
    if (r.code === 0) removed.push(ref);
    else log.add(kind === "container" ? "remove-container" : "remove-volume", ref, r.code, r.stderr);
  }
  return removed;
}

/**
 * Re-list the label scope after the removals so the result reports what is STILL
 * PRESENT rather than only what we managed to delete. A failed verification
 * listing is recorded as a failure: an unverifiable teardown is not a clean one.
 */
async function verifyScope(
  labels: string | string[],
  dockerRun: DockerRun,
  log: FailureLog,
): Promise<{ containers: string[]; volumes: string[] }> {
  const c = await listContainersResult(labels, dockerRun);
  if (c.code !== 0) log.add("list-containers", c.scope, c.code, c.stderr);
  const v = await listVolumesResult(labels, dockerRun);
  if (v.code !== 0) log.add("list-volumes", v.scope, v.code, v.stderr);
  return { containers: c.items, volumes: v.items };
}

/**
 * Remove a single sandbox by id. Discovered by the `ca.sandbox.id=<id>` label
 * (plus `ca.sandbox=1`), so this never reads a state file.
 *
 * @param id the sandbox id (the `ca.sandbox.id` label value).
 * @param opts keepVolume to preserve the source volume; injectable docker runner.
 */
export async function destroySandbox(
  id: string,
  opts: DestroyOptions = {},
): Promise<DestroyResult> {
  if (!id) throw new Error("ca-sandbox: destroySandbox requires a sandbox id");
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const labels = [SANDBOX_LABEL, idLabel(id)];
  const log = new FailureLog();

  const containersList = await listContainersResult(labels, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const volumesList = await listVolumesResult(labels, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);

  const removedContainers = await removeEach(containersList.items, "container", dockerRun, log);

  const removedVolumes: string[] = [];
  const keptVolumes: string[] = [];
  if (opts.keepVolume) {
    keptVolumes.push(...volumesList.items);
  } else {
    // A volume in use by a container can't be removed until the container is
    // gone; containers were removed above, so this now succeeds.
    removedVolumes.push(...await removeEach(volumesList.items, "volume", dockerRun, log));
  }

  const still = verifyScope(labels, dockerRun, log);
  // #433: under --keep-volume NO volume was targeted for removal, so no volume
  // can be a leak - and the surviving ones ARE the kept ones. Filtering against
  // `keptVolumes` alone was not enough: when the DISCOVERY listing failed,
  // `keptVolumes` was empty while the VERIFICATION listing still succeeded, so
  // the volume the operator explicitly asked to keep fell through and was named
  // as remaining. The exit was already non-zero from the listing failure, so
  // there was no false success - the diagnostic was simply confusing at exactly
  // the wrong moment.
  const survivingVolumes = opts.keepVolume ? [] : still.volumes.filter((v) => !keptVolumes.includes(v));
  const keptFromVerification = opts.keepVolume
    ? [...new Set([...keptVolumes, ...still.volumes])]
    : keptVolumes;
  return {
    id,
    removedContainers,
    removedVolumes,
    keptVolumes: keptFromVerification,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers,
    remainingVolumes: survivingVolumes,
  };
}

export type PruneOptions = {
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: DockerRun;
};

export type PruneResult = TeardownReport & {
  /** Every ca.sandbox=1 container id removed (including leaked ones). */
  removedContainers: string[];
  /** Every ca.sandbox=1 volume removed (including leaked ones). */
  removedVolumes: string[];
};

/**
 * Reclaim EVERY object carrying `ca.sandbox=1`, regardless of id label — so a
 * manually-leaked container/volume that lost (or never had) its id label is still
 * swept. Containers are removed before volumes so an in-use volume frees up.
 * Cached images are intentionally NOT removed (tracked by tag; reused across
 * creates — AC-11 "cached images excepted").
 */
export async function prune(opts: PruneOptions = {}): Promise<PruneResult> {
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const log = new FailureLog();

  const containersList = await listContainersResult(SANDBOX_LABEL, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const removedContainers = await removeEach(containersList.items, "container", dockerRun, log);

  const volumesList = await listVolumesResult(SANDBOX_LABEL, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);
  const removedVolumes = await removeEach(volumesList.items, "volume", dockerRun, log);

  // #433: verification is scoped to what THIS invocation targeted. Re-listing
  // the global ca.sandbox=1 scope meant a sandbox another process created AFTER
  // discovery landed in remainingContainers and produced "These objects may be
  // running UNTRUSTED code - remove them by hand" for something prune never
  // touched. It failed safe, but a scary false positive teaches operators to
  // ignore the signal, which defeats the point of #393. An object prune DID
  // target and could not remove is still reported - that is what this is for.
  const targetedContainers = new Set(containersList.items);
  const targetedVolumes = new Set(volumesList.items);
  const still = verifyScope(SANDBOX_LABEL, dockerRun, log);
  return {
    removedContainers,
    removedVolumes,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers.filter((c) => targetedContainers.has(c)),
    remainingVolumes: still.volumes.filter((v) => targetedVolumes.has(v)),
  };
}

// --------------------------------------------------------------------------
// the verdict the CLI turns into an exit code
// --------------------------------------------------------------------------
/**
 * True when teardown did NOT fully succeed — any docker operation failed, or any
 * targeted object is still present. The CLI maps this to a non-zero exit code so
 * automation can never mistake a leaked untrusted container for a clean sweep.
 */
export function teardownIncomplete(r: TeardownReport): boolean {
  return r.failureCount > 0 || r.remainingContainers.length > 0 || r.remainingVolumes.length > 0;
}

/** Render at most MAX_DIAGNOSTIC_REFS refs, noting how many were elided. */
function boundedRefs(label: string, refs: string[]): string[] {
  if (refs.length === 0) return [];
  const shown = refs.slice(0, MAX_DIAGNOSTIC_REFS);
  const lines = shown.map((r) => `  still present: ${label} ${r}`);
  if (refs.length > shown.length) lines.push(`  ... and ${refs.length - shown.length} more ${label}(s)`);
  return lines;
}

/**
 * A bounded, operator-actionable diagnostic: what failed, with docker's own
 * message, and — the part that matters — the NAMES of the objects still running.
 * Returns "" when teardown was clean, so the caller can print unconditionally.
 */
export function formatTeardownDiagnostic(verb: string, r: TeardownReport): string {
  if (!teardownIncomplete(r)) return "";
  const lines: string[] = [
    `sandbox ${verb}: teardown INCOMPLETE — ${r.failureCount} docker operation(s) failed; ` +
      `${r.remainingContainers.length} container(s) and ${r.remainingVolumes.length} volume(s) still present.`,
  ];
  for (const f of r.failures) lines.push(`  ${f.op} ${f.ref}: docker exit ${f.code}: ${f.message}`);
  if (r.failureCount > r.failures.length)
    lines.push(`  ... and ${r.failureCount - r.failures.length} more failure(s) not shown`);
  lines.push(...boundedRefs("container", r.remainingContainers));
  lines.push(...boundedRefs("volume", r.remainingVolumes));
  lines.push("  These objects may be running UNTRUSTED code — remove them by hand (`docker rm -f` / `docker volume rm`).");
  return lines.join("\n");
}
