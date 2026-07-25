/**
 * destroy.ts — ca-sandbox teardown + prune (T-09, covers AC-11).
 *
 * destroySandbox(id, opts) removes the docker objects of ONE sandbox, discovered
 * purely by the `ca.sandbox.id=<id>` label (no JSON file — registry.ts is the
 * label-only state). It `docker rm -f`'s every labeled container and `volume rm`'s
 * the named volume UNLESS `--keep-volume` is set, in which case the container goes
 * but the volume (the cloned source) is preserved for a later re-run.
 *
 * prune(opts) reclaims EVERY object carrying `ca.sandbox=1` — including a
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

/** Accumulates failures while enforcing the retention bound. */
class FailureLog {
  readonly failures: TeardownFailure[] = [];
  count = 0;

  add(op: TeardownOp, ref: string, code: number, stderr: string): void {
    this.count += 1;
    if (this.failures.length >= MAX_TEARDOWN_FAILURES) return;
    this.failures.push({ op, ref, code, message: oneLine(stderr) });
  }
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
function removeEach(
  refs: string[],
  kind: "container" | "volume",
  dockerRun: DockerRun,
  log: FailureLog,
): string[] {
  const removed: string[] = [];
  for (const ref of refs) {
    const args = kind === "container" ? ["rm", "-f", ref] : ["volume", "rm", "-f", ref];
    const r = dockerRun(args);
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
function verifyScope(
  labels: string | string[],
  dockerRun: DockerRun,
  log: FailureLog,
): { containers: string[]; volumes: string[] } {
  const c = listContainersResult(labels, dockerRun);
  if (c.code !== 0) log.add("list-containers", c.scope, c.code, c.stderr);
  const v = listVolumesResult(labels, dockerRun);
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
export function destroySandbox(id: string, opts: DestroyOptions = {}): DestroyResult {
  if (!id) throw new Error("ca-sandbox: destroySandbox requires a sandbox id");
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const labels = [SANDBOX_LABEL, idLabel(id)];
  const log = new FailureLog();

  const containersList = listContainersResult(labels, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const volumesList = listVolumesResult(labels, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);

  const removedContainers = removeEach(containersList.items, "container", dockerRun, log);

  const removedVolumes: string[] = [];
  const keptVolumes: string[] = [];
  if (opts.keepVolume) {
    keptVolumes.push(...volumesList.items);
  } else {
    // A volume in use by a container can't be removed until the container is
    // gone; containers were removed above, so this now succeeds.
    removedVolumes.push(...removeEach(volumesList.items, "volume", dockerRun, log));
  }

  const still = verifyScope(labels, dockerRun, log);
  return {
    id,
    removedContainers,
    removedVolumes,
    keptVolumes,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers,
    // A kept volume is a deliberate survivor, not a leak.
    remainingVolumes: still.volumes.filter((v) => !keptVolumes.includes(v)),
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
export function prune(opts: PruneOptions = {}): PruneResult {
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  const log = new FailureLog();

  const containersList = listContainersResult(SANDBOX_LABEL, dockerRun);
  if (containersList.code !== 0)
    log.add("list-containers", containersList.scope, containersList.code, containersList.stderr);
  const removedContainers = removeEach(containersList.items, "container", dockerRun, log);

  const volumesList = listVolumesResult(SANDBOX_LABEL, dockerRun);
  if (volumesList.code !== 0)
    log.add("list-volumes", volumesList.scope, volumesList.code, volumesList.stderr);
  const removedVolumes = removeEach(volumesList.items, "volume", dockerRun, log);

  const still = verifyScope(SANDBOX_LABEL, dockerRun, log);
  return {
    removedContainers,
    removedVolumes,
    failures: log.failures,
    failureCount: log.count,
    remainingContainers: still.containers,
    remainingVolumes: still.volumes,
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
