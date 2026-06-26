/**
 * run.test.ts — T-06. Covers AC-01.
 *
 * runContainer(image, volumeName, netPolicy) starts an isolated sandbox
 * container. The load-bearing invariant (spec "Load-bearing invariant" / AC-01):
 * untrusted code in the box can never reach the host filesystem, enforced
 * STRUCTURALLY by the run flags:
 *   docker run -d
 *     --mount type=volume,source=<vol>,target=/work/repo   (NEVER a host bind)
 *     --workdir /work/repo --user 1000:1000 --read-only
 *     --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges
 *     --pids-limit 512 --memory 4g --cpus 2 --label ca.sandbox=1
 *     <image> sleep infinity
 *   NO host bind, NO /var/run/docker.sock, NEVER --privileged.
 *
 * Two layers:
 *   1. PURE unit tests over buildRunArgs(...) — the argv assembly — prove every
 *      isolation flag is present, the mount is type=volume (never bind), no
 *      docker.sock, no --privileged. This is the RED gate; runs everywhere.
 *   2. A DOCKER-GATED integration test (guarded by `docker info`) starts a real
 *      container and `docker inspect`s it: no "Type":"bind" mount, no
 *      /var/run/docker.sock mount, Privileged:false, CapDrop contains ALL,
 *      read-only root, non-root user. Namespaced + cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { buildRunArgs, runContainer } from "./run.ts";

// --------------------------------------------------------------------------
// PURE unit layer — argv assembly, no real docker.
// --------------------------------------------------------------------------
describe("buildRunArgs — isolation flags (AC-01)", () => {
  const argv = buildRunArgs("ca-sbx:demo-abc", "ca-sbx-vol-demo", "offline");

  it("is a detached run with the image and the sleep-infinity keep-alive command", () => {
    expect(argv[0]).toBe("run");
    expect(argv).toContain("-d");
    // image then `sleep infinity` are the final tokens, in order.
    expect(argv.slice(-3)).toEqual(["ca-sbx:demo-abc", "sleep", "infinity"]);
  });

  it("mounts the source volume at /work/repo via type=volume (never a bind)", () => {
    expect(argv).toContain("--mount");
    expect(argv).toContain("type=volume,source=ca-sbx-vol-demo,target=/work/repo");
    // No bind expression anywhere in the argv.
    for (const tok of argv) {
      expect(tok).not.toMatch(/type=bind/);
    }
  });

  it("sets workdir, non-root user, read-only root, and a tmpfs /tmp", () => {
    expect(argvPair(argv, "--workdir")).toBe("/work/repo");
    expect(argvPair(argv, "--user")).toBe("1000:1000");
    expect(argv).toContain("--read-only");
    expect(argvPair(argv, "--tmpfs")).toBe("/tmp");
  });

  it("drops all caps, blocks privilege escalation, and applies the resource caps", () => {
    expect(argvPair(argv, "--cap-drop")).toBe("ALL");
    expect(argvPair(argv, "--security-opt")).toBe("no-new-privileges");
    expect(argvPair(argv, "--pids-limit")).toBe("512");
    expect(argvPair(argv, "--memory")).toBe("4g");
    expect(argvPair(argv, "--cpus")).toBe("2");
  });

  it("labels the container ca.sandbox=1 for the lifecycle registry", () => {
    expect(argvPair(argv, "--label")).toBe("ca.sandbox=1");
  });

  it("NEVER passes --privileged and NEVER mounts the docker socket", () => {
    expect(argv).not.toContain("--privileged");
    expect(argv.join(" ")).not.toMatch(/docker\.sock/);
  });
});

describe("buildRunArgs — network policy (AC-01 / AC-08 seam)", () => {
  it("offline detaches the container from all networking", () => {
    const argv = buildRunArgs("img", "vol", "offline");
    expect(argvPair(argv, "--network")).toBe("none");
  });

  // dx-006: the safe default is fail-CLOSED. Only a RECOGNIZED networked policy
  // (T-10 will add these) may skip the airgap; any UNRECOGNIZED value — a typo of
  // "offline", or a policy no layer implements — must still get --network none
  // rather than silently run on docker's default bridge. (Replaces the prior test
  // that asserted a bare non-offline string passed through, which was the gap.)
  it("a typo of 'offline' still gets --network none (fail closed)", () => {
    const argv = buildRunArgs("img", "vol", "offlien");
    expect(argvPair(argv, "--network")).toBe("none");
  });

  it("an unrecognized policy fails closed to --network none", () => {
    for (const policy of ["open", "Offline", " offline ", "bridge", ""]) {
      const argv = buildRunArgs("img", "vol", policy);
      expect(networkValues(argv), `policy ${JSON.stringify(policy)} must airgap`).toContain("none");
    }
  });

  it("refuses an empty image or volume name", () => {
    expect(() => buildRunArgs("", "vol", "offline")).toThrow();
    expect(() => buildRunArgs("img", "", "offline")).toThrow();
  });
});

// Helpers: read the value following a flag; collect all --network values.
function argvPair(argv: string[], flag: string): string | undefined {
  const i = argv.indexOf(flag);
  return i >= 0 ? argv[i + 1] : undefined;
}
function networkValues(argv: string[]): string[] {
  const out: string[] = [];
  argv.forEach((a, i) => {
    if (a === "--network") out.push(argv[i + 1]);
  });
  return out;
}

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-01).
// Starts a real container and inspects it for the structural guarantees.
// Namespaced with the task id; every object is cleaned up.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t06";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

d("runContainer [docker] — real container is structurally isolated (AC-01)", () => {
  const created = { containers: [] as string[], volumes: [] as string[], images: [] as string[] };

  afterAll(() => {
    for (const c of created.containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    for (const v of created.volumes) spawnSync("docker", ["volume", "rm", "-f", v], { env: DENV });
    for (const i of created.images) spawnSync("docker", ["rmi", "-f", i], { env: DENV });
  });

  it("inspect shows no bind mount, no docker.sock, not privileged, cap-drop ALL, read-only, non-root", () => {
    // A tiny base image with a shell + `sleep`. busybox is small and ubiquitous.
    const image = "busybox:latest";
    const pull = spawnSync("docker", ["pull", image], { encoding: "utf8", env: DENV });
    expect(pull.status, pull.stderr).toBe(0);
    created.images.push(image); // remove what we pulled for this test

    // A namespaced, labeled named volume (the live source mount at /work/repo).
    const vol = `${NS}-vol-${Date.now()}`;
    const mk = spawnSync(
      "docker",
      ["volume", "create", "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1", vol],
      { encoding: "utf8", env: DENV },
    );
    expect(mk.status, mk.stderr).toBe(0);
    created.volumes.push(vol);

    const id = runContainer(image, vol, "offline", {
      extraLabels: ["ca.sandbox.build=1"],
      namePrefix: NS,
    });
    expect(id).toMatch(/^[0-9a-f]{12,}$/);
    created.containers.push(id);

    const inspect = spawnSync("docker", ["inspect", id], { encoding: "utf8", env: DENV });
    expect(inspect.status, inspect.stderr).toBe(0);
    const info = JSON.parse(inspect.stdout)[0];

    // AC-01: no bind mount of ANY kind.
    const mounts: Array<{ Type?: string; Source?: string; Destination?: string }> =
      info.Mounts ?? [];
    for (const m of mounts) {
      expect(m.Type).not.toBe("bind");
    }
    // The source volume is mounted at /work/repo as a volume.
    const repoMount = mounts.find((m) => m.Destination === "/work/repo");
    expect(repoMount?.Type).toBe("volume");

    // AC-01: the docker socket is mounted NOWHERE.
    const all = JSON.stringify(info);
    expect(all).not.toMatch(/docker\.sock/);

    // AC-01: not privileged.
    expect(info.HostConfig.Privileged).toBe(false);

    // cap-drop ALL applied.
    expect(info.HostConfig.CapDrop).toContain("ALL");

    // Read-only root + non-root user (the structural FS-isolation pair).
    expect(info.HostConfig.ReadonlyRootfs).toBe(true);
    expect(info.Config.User).toBe("1000:1000");

    // no-new-privileges security opt.
    expect(JSON.stringify(info.HostConfig.SecurityOpt)).toMatch(/no-new-privileges/);

    // The container is actually running (sleep infinity keep-alive).
    expect(info.State.Running).toBe(true);
  }, 120_000);
});
