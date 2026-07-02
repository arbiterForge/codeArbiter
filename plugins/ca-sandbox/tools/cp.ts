/**
 * cp.ts — host-initiated, PULL-ONLY file extraction from a sandbox (T-12, AC-10).
 *
 * Controlled egress out of the box is host-initiated ONLY (spec "Scope": "sandbox
 * cp <id>:/work/<f> ./dest via docker cp"). `cpOut(id, containerPath, hostDest)`
 * shells `docker cp <container>:<path> <hostDest>` — the host reaches IN and pulls
 * a file OUT. There is no `cpIn` counterpart by design: the box is for exploring
 * untrusted code, so the only sanctioned data flow is OUT to the host.
 *
 * The dangerous reverse direction is not "docker cp host->container" (which still
 * touches one file) but a host bind mount — the bulk channel that would expose the
 * whole host FS to untrusted code. The load-bearing invariant (spec AC-02 / AC-10)
 * is that a sandbox container NEVER receives a host bind. This module does NOT
 * hand-roll its own bind check: it routes any copy-in mount request through
 * mounts.ts's `buildMountArgs`, the ONE chokepoint that THROWS
 * (BindMountRejectedError) on every bind expression. So a host->container bind is
 * structurally impossible to build from here — exactly the same guarantee run.ts
 * relies on.
 *
 * Process/shell handling routes through docker.ts (architecture-007): a shared
 * child-process helper returning a RunResult, and on Windows + Git Bash
 * MSYS_NO_PATHCONV=1 is set so the in-container path passed to `docker cp`
 * (e.g. `<id>:/work/out.txt`) is not mangled by MSYS path conversion (Spike A/B).
 */
import { buildMountArgs, type MountSpec } from "./mounts.ts";
import { defaultDockerRun, type RunResult } from "./docker.ts";

export type { RunResult };

/** Optional knobs for cpOut — chiefly an injectable docker runner for tests. */
export type CpOptions = {
  /** Injectable docker runner (defaults to spawnSync("docker", ...)). */
  dockerRun?: (args: string[]) => RunResult;
};

/**
 * Assemble the `docker cp` argv (everything AFTER `docker`) for a PULL-only copy
 * OUT of the container. Pure: builds the array, runs nothing — so the direction
 * is unit-testable. The container ref is always the SOURCE and the host path
 * always the DEST, so the produced argv can never express a push (host->container).
 *
 *   cp <id>:<containerPath> <hostDest>
 *
 * @throws if any of id / containerPath / hostDest is empty.
 */
export function buildCpOutArgs(
  id: string,
  containerPath: string,
  hostDest: string,
): string[] {
  if (!id) throw new Error("ca-sandbox: cpOut requires a non-empty container id");
  if (!containerPath) throw new Error("ca-sandbox: cpOut requires a non-empty container path");
  if (!hostDest) throw new Error("ca-sandbox: cpOut requires a non-empty host destination");
  // Direction is fixed: `<id>:<path>` (SOURCE, in the container) -> `<hostDest>`
  // (DEST, on the host). This is the only direction this builder emits.
  return ["cp", `${id}:${containerPath}`, hostDest];
}

/**
 * Copy a file OUT of a sandbox container to the host (`docker cp <id>:<path>
 * <dest>`). Pull-only — there is deliberately no cpIn. Returns the RunResult so
 * callers can inspect docker's exit code / stderr.
 *
 * @param id the sandbox container id.
 * @param containerPath the in-container source path (e.g. `/work/out.txt`).
 * @param hostDest the host destination path/dir.
 * @param opts optional injectable docker runner.
 */
export function cpOut(
  id: string,
  containerPath: string,
  hostDest: string,
  opts: CpOptions = {},
): RunResult {
  const args = buildCpOutArgs(id, containerPath, hostDest);
  const dockerRun = opts.dockerRun ?? defaultDockerRun;
  return dockerRun(args);
}

/**
 * Reverse-direction guard (AC-10): prove a host->container BIND copy-in is
 * impossible. A caller that tries to inject host files into the box via a bind
 * mount must route the spec through here; we hand it straight to mounts.ts's
 * `buildMountArgs`, the single mount chokepoint, which THROWS
 * (BindMountRejectedError) on any bind expression — the `-v host:container`
 * shorthand string, the `{ v: ... }` object form, or an explicit `type=bind`.
 *
 * This does NOT re-implement the bind check (that would be a second, drift-prone
 * parse path); it delegates so the SAME structural guarantee that protects
 * `docker run` also protects any cp-shaped mount request. There is intentionally
 * no "copy-in" path that succeeds.
 *
 * @throws BindMountRejectedError (from mounts.ts) for any bind spec.
 */
export function assertNoCopyInBind(spec: MountSpec | string | object): void {
  // Route through the chokepoint. For volume/tmpfs specs this returns argv
  // harmlessly; for any bind expression it throws — which is the whole point.
  buildMountArgs([spec as MountSpec]);
}
