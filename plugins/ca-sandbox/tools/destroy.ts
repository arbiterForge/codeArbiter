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
 */
import {
  SANDBOX_LABEL,
  idLabel,
  listContainers,
  listVolumes,
  listAllContainers,
  listAllVolumes,
  defaultDockerRun,
  type DockerRun,
} from "./registry.ts";

export type DestroyOptions = {
  /** Keep the named volume (the cloned source) — only remove the container. */
  keepVolume?: boolean;
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: DockerRun;
};

export type DestroyResult = {
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

  const containers = listContainers(labels, dockerRun);
  const volumes = listVolumes(labels, dockerRun);

  const removedContainers: string[] = [];
  for (const c of containers) {
    const r = dockerRun(["rm", "-f", c]);
    if (r.code === 0) removedContainers.push(c);
  }

  const removedVolumes: string[] = [];
  const keptVolumes: string[] = [];
  if (opts.keepVolume) {
    keptVolumes.push(...volumes);
  } else {
    // A volume in use by a container can't be removed until the container is
    // gone; containers were removed above, so this now succeeds.
    for (const v of volumes) {
      const r = dockerRun(["volume", "rm", "-f", v]);
      if (r.code === 0) removedVolumes.push(v);
    }
  }

  return { id, removedContainers, removedVolumes, keptVolumes };
}

export type PruneOptions = {
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: DockerRun;
};

export type PruneResult = {
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

  const removedContainers: string[] = [];
  for (const c of listAllContainers(dockerRun)) {
    const r = dockerRun(["rm", "-f", c]);
    if (r.code === 0) removedContainers.push(c);
  }

  const removedVolumes: string[] = [];
  for (const v of listAllVolumes(dockerRun)) {
    const r = dockerRun(["volume", "rm", "-f", v]);
    if (r.code === 0) removedVolumes.push(v);
  }

  return { removedContainers, removedVolumes };
}
