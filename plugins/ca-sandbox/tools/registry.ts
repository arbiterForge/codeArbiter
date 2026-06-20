/**
 * registry.ts — ca-sandbox label-only state (T-09, covers AC-11).
 *
 * There is NO JSON state file. The set of live sandboxes IS the set of docker
 * objects carrying the `ca.sandbox=1` label, discovered purely via docker label
 * filters. A sandbox's per-instance identity is the additional `ca.sandbox.id=<id>`
 * label every object of that sandbox carries (container + named volume). This
 * means the registry can never drift from reality: there is no file to get stale,
 * and `docker` is the single source of truth. A manually-leaked labeled object is
 * therefore visible to `list()`/`prune()` for free — exactly what AC-11 asks for.
 *
 * Process/shell handling mirrors farm.ts / run.ts / build.ts: a thin docker
 * runner returning code/stdout/stderr, MSYS_NO_PATHCONV=1 set on Windows + Git
 * Bash so labels/paths handed to docker are not mangled (Spike A/B), and the
 * docker effect is injectable so the parsing logic is unit-testable without real
 * docker while the docker-gated tests drive the real default.
 */
import { spawnSync } from "node:child_process";

/** The label every ca-sandbox object carries — the registry membership marker. */
export const SANDBOX_LABEL_KEY = "ca.sandbox";
export const SANDBOX_LABEL = "ca.sandbox=1";
/** The per-instance identity label key; value is the sandbox id. */
export const SANDBOX_ID_LABEL_KEY = "ca.sandbox.id";

// On Windows + Git Bash, label/path args handed to docker get mangled by MSYS
// path conversion; MSYS_NO_PATHCONV=1 disables it (Spike A/B).
const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

export type DockerResult = { code: number; stdout: string; stderr: string };
/** Injectable docker runner (defaults to spawnSync("docker", ...)). */
export type DockerRun = (args: string[]) => DockerResult;

export function defaultDockerRun(args: string[]): DockerResult {
  const r = spawnSync("docker", args, { encoding: "utf8", env: DOCKER_ENV });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : ""),
  };
}

/** A discovered sandbox: its id plus the docker objects that make it up. */
export type SandboxRecord = {
  /** The per-instance id (the `ca.sandbox.id` label value). */
  id: string;
  /** Container ids carrying this id (normally one). */
  containers: string[];
  /** Named volumes carrying this id (normally one). */
  volumes: string[];
};

/** The id-label expression for a given sandbox id (`ca.sandbox.id=<id>`). */
export function idLabel(id: string): string {
  return `${SANDBOX_ID_LABEL_KEY}=${id}`;
}

// --------------------------------------------------------------------------
// raw label-filtered discovery (the only state source)
// --------------------------------------------------------------------------
/**
 * Render one or more label expressions into repeated `--filter label=<expr>`
 * args. Docker ANDs multiple `--filter label=` flags, but treats a comma INSIDE
 * a single `label=` value as part of the value — so a combined filter MUST be
 * passed as separate flags, one per label, never `label=a=1,b=2`.
 */
function labelFilterArgs(labels: string | string[]): string[] {
  const list = Array.isArray(labels) ? labels : [labels];
  return list.flatMap((l) => ["--filter", `label=${l}`]);
}

/**
 * Container ids matching one or more label expressions (ANDed). `docker ps -a -q
 * --no-trunc --filter label=<expr> [...]` prints one full id per line; blank
 * output => none. Pass an array to require ALL labels (e.g. membership + id).
 */
export function listContainers(
  labels: string | string[] = SANDBOX_LABEL,
  dockerRun: DockerRun = defaultDockerRun,
): string[] {
  const r = dockerRun(["ps", "-a", "-q", "--no-trunc", ...labelFilterArgs(labels)]);
  return splitLines(r.stdout);
}

/**
 * Named volumes matching one or more label expressions (ANDed). `docker volume
 * ls -q --filter label=<expr> [...]` prints one volume name per line.
 */
export function listVolumes(
  labels: string | string[] = SANDBOX_LABEL,
  dockerRun: DockerRun = defaultDockerRun,
): string[] {
  const r = dockerRun(["volume", "ls", "-q", ...labelFilterArgs(labels)]);
  return splitLines(r.stdout);
}

function splitLines(out: string): string[] {
  return out
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

// --------------------------------------------------------------------------
// grouped views
// --------------------------------------------------------------------------
/**
 * Every ca-sandbox container id (label=ca.sandbox=1). Flat — does not group by
 * instance; `list()` is the grouped view, this is the raw membership set used by
 * `prune()` to reclaim ALL labeled containers including manually-leaked ones.
 */
export function listAllContainers(dockerRun: DockerRun = defaultDockerRun): string[] {
  return listContainers(SANDBOX_LABEL, dockerRun);
}

/** Every ca-sandbox named volume (label=ca.sandbox=1), including leaked ones. */
export function listAllVolumes(dockerRun: DockerRun = defaultDockerRun): string[] {
  return listVolumes(SANDBOX_LABEL, dockerRun);
}

/**
 * Read the `ca.sandbox.id` label value off a container or volume, or "" when the
 * object carries no id label (a leaked object labeled only `ca.sandbox=1`).
 *
 * `docker inspect -f '{{ index .Config.Labels "ca.sandbox.id" }}'` works for a
 * container; volumes expose `.Labels` directly. We try the container shape first,
 * then the volume shape, since the caller may not know the object kind.
 */
function labelValue(objectRef: string, kind: "container" | "volume", dockerRun: DockerRun): string {
  const fmt =
    kind === "container"
      ? `{{ index .Config.Labels "${SANDBOX_ID_LABEL_KEY}" }}`
      : `{{ index .Labels "${SANDBOX_ID_LABEL_KEY}" }}`;
  const args =
    kind === "container"
      ? ["inspect", "-f", fmt, objectRef]
      : ["volume", "inspect", "-f", fmt, objectRef];
  const r = dockerRun(args);
  if (r.code !== 0) return "";
  // Go template prints "<no value>" when the label is absent on some engines.
  const v = r.stdout.trim();
  return v === "<no value>" ? "" : v;
}

/**
 * List sandboxes grouped by their `ca.sandbox.id`. Pure label-filter discovery,
 * no JSON file. Objects that carry `ca.sandbox=1` but NO id label are grouped
 * under the empty-string id "" — these are the leaked objects `prune()` reclaims.
 */
export function listSandboxes(dockerRun: DockerRun = defaultDockerRun): SandboxRecord[] {
  const byId = new Map<string, SandboxRecord>();
  const ensure = (id: string): SandboxRecord => {
    let rec = byId.get(id);
    if (!rec) {
      rec = { id, containers: [], volumes: [] };
      byId.set(id, rec);
    }
    return rec;
  };

  for (const c of listAllContainers(dockerRun)) {
    ensure(labelValue(c, "container", dockerRun)).containers.push(c);
  }
  for (const v of listAllVolumes(dockerRun)) {
    ensure(labelValue(v, "volume", dockerRun)).volumes.push(v);
  }
  return [...byId.values()];
}

/**
 * Find a single sandbox by id via the `ca.sandbox.id=<id>` label filter ONLY
 * (no scan of a JSON file). Returns the record, or null when no labeled object
 * carries that id.
 */
export function findSandbox(
  id: string,
  dockerRun: DockerRun = defaultDockerRun,
): SandboxRecord | null {
  const labels = [SANDBOX_LABEL, idLabel(id)];
  const containers = listContainers(labels, dockerRun);
  const volumes = listVolumes(labels, dockerRun);
  if (containers.length === 0 && volumes.length === 0) return null;
  return { id, containers, volumes };
}

/**
 * Resolve a user-facing sandbox id (the `ca.sandbox.id` label value that
 * `create` returns) to the actual docker container id, via the label filter.
 *
 * This is the bridge the CLI/exec/cp/shell surfaces need: the container is NOT
 * named after the bare sandbox id (it is `ca-sbx-<id>-<suffix>`), so `docker
 * exec <id>` fails with "no such container". Every command that operates on a
 * running box must map the sandbox id to its container id here first.
 *
 * @throws if no labeled container carries that sandbox id (unknown/destroyed id).
 */
export function resolveContainerId(
  id: string,
  dockerRun: DockerRun = defaultDockerRun,
): string {
  const rec = findSandbox(id, dockerRun);
  const containerId = rec?.containers[0];
  if (!containerId)
    throw new Error(
      `ca-sandbox: no running container for sandbox '${id}' ` +
        "(unknown id, or it was destroyed — see `sandbox prune`/`list`)",
    );
  return containerId;
}
