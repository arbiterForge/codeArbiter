/**
 * lifecycle.test.ts — T-09. Covers AC-01 and AC-11.
 *
 * create/destroy + the label-only registry:
 *   - create clones into a NAMED VOLUME and starts a container (AC-01);
 *   - create -> destroy leaves ZERO ca.sandbox=1 objects (AC-11);
 *   - --keep-volume leaves the volume (AC-11);
 *   - prune reclaims a manually-leaked labeled object (AC-11);
 *   - the registry finds/lists sandboxes via docker label filters ONLY — no JSON
 *     file (AC-11 "label-only state").
 *
 * Two layers:
 *   1. PURE unit tests with an INJECTED fake docker runner — prove the registry
 *      builds its filter args correctly, destroy/prune issue exactly the right
 *      rm/volume-rm calls, and --keep-volume spares the volume. The RED gate;
 *      runs everywhere.
 *   2. DOCKER-GATED integration (guarded by `docker info`) — a real create
 *      clones busybox-free into a named volume + starts a container, destroy
 *      sweeps to zero, --keep-volume spares the volume, and prune reclaims a
 *      hand-leaked labeled volume. Namespaced + fully cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import {
  listSandboxes,
  findSandbox,
  idLabel,
  SANDBOX_LABEL,
  type DockerRun,
  type DockerResult,
} from "./registry.ts";
import { destroySandbox, prune } from "./destroy.ts";
import { createSandbox } from "./create.ts";

// --------------------------------------------------------------------------
// PURE layer — injected fake docker runner. No real docker.
// --------------------------------------------------------------------------

/** A fake docker that records calls and returns scripted stdout per arg-match. */
function fakeDocker(routes: Array<{ match: (a: string[]) => boolean; stdout?: string; code?: number }>): {
  run: DockerRun;
  calls: string[][];
} {
  const calls: string[][] = [];
  const run: DockerRun = (args) => {
    calls.push(args);
    for (const r of routes) {
      if (r.match(args)) return { code: r.code ?? 0, stdout: r.stdout ?? "", stderr: "" };
    }
    return { code: 0, stdout: "", stderr: "" } as DockerResult;
  };
  return { run, calls };
}

// All `label=...` values across every --filter flag (docker ANDs separate
// --filter label= flags; a comma inside one value is NOT a label separator).
const labelFiltersOf = (args: string[]): string[] => {
  const out: string[] = [];
  args.forEach((a, i) => {
    if (a === "--filter" && args[i + 1]?.startsWith("label=")) out.push(args[i + 1].slice("label=".length));
  });
  return out;
};

describe("registry — label-only discovery (AC-11)", () => {
  it("findSandbox filters by ca.sandbox=1 AND ca.sandbox.id=<id>, no JSON file", () => {
    const { run, calls } = fakeDocker([
      { match: (a) => a[0] === "ps", stdout: "container123\n" },
      { match: (a) => a[0] === "volume" && a[1] === "ls", stdout: "ca-sbx-vol-abc\n" },
    ]);
    const rec = findSandbox("abc", run);
    expect(rec).not.toBeNull();
    expect(rec!.containers).toEqual(["container123"]);
    expect(rec!.volumes).toEqual(["ca-sbx-vol-abc"]);
    // Both queries filter by BOTH labels (separate --filter flags, ANDed) —
    // never read a file.
    const psCall = calls.find((a) => a[0] === "ps")!;
    expect(labelFiltersOf(psCall)).toEqual([SANDBOX_LABEL, idLabel("abc")]);
    const volCall = calls.find((a) => a[0] === "volume" && a[1] === "ls")!;
    expect(labelFiltersOf(volCall)).toEqual([SANDBOX_LABEL, idLabel("abc")]);
  });

  it("findSandbox returns null when no labeled object carries the id", () => {
    const { run } = fakeDocker([]); // everything returns empty stdout
    expect(findSandbox("missing", run)).toBeNull();
  });

  it("listSandboxes groups containers + volumes by their ca.sandbox.id label", () => {
    const { run } = fakeDocker([
      { match: (a) => a[0] === "ps", stdout: "c1\n" },
      { match: (a) => a[0] === "volume" && a[1] === "ls", stdout: "ca-sbx-vol-x\n" },
      { match: (a) => a[0] === "inspect", stdout: "x\n" }, // container id label
      { match: (a) => a[0] === "volume" && a[1] === "inspect", stdout: "x\n" }, // volume id label
    ]);
    const list = listSandboxes(run);
    expect(list).toHaveLength(1);
    expect(list[0]).toEqual({ id: "x", containers: ["c1"], volumes: ["ca-sbx-vol-x"] });
  });
});

describe("destroySandbox — teardown by label (AC-11)", () => {
  it("removes the container AND the volume of the id", () => {
    const { run, calls } = fakeDocker([
      { match: (a) => a[0] === "ps", stdout: "c1\n" },
      { match: (a) => a[0] === "volume" && a[1] === "ls", stdout: "ca-sbx-vol-id1\n" },
    ]);
    const res = destroySandbox("id1", { dockerRun: run });
    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual(["ca-sbx-vol-id1"]);
    expect(res.keptVolumes).toEqual([]);
    expect(calls).toContainEqual(["rm", "-f", "c1"]);
    expect(calls).toContainEqual(["volume", "rm", "-f", "ca-sbx-vol-id1"]);
  });

  it("--keep-volume removes the container but SPARES the volume", () => {
    const { run, calls } = fakeDocker([
      { match: (a) => a[0] === "ps", stdout: "c1\n" },
      { match: (a) => a[0] === "volume" && a[1] === "ls", stdout: "ca-sbx-vol-id1\n" },
    ]);
    const res = destroySandbox("id1", { keepVolume: true, dockerRun: run });
    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual([]);
    expect(res.keptVolumes).toEqual(["ca-sbx-vol-id1"]);
    // The volume rm must NOT have been issued.
    expect(calls.find((a) => a[0] === "volume" && a[1] === "rm")).toBeUndefined();
  });
});

describe("prune — reclaims ALL ca.sandbox=1 objects incl. leaked (AC-11)", () => {
  it("removes every labeled container and volume regardless of id label", () => {
    const { run, calls } = fakeDocker([
      { match: (a) => a[0] === "ps", stdout: "c1\nc2\n" },
      { match: (a) => a[0] === "volume" && a[1] === "ls", stdout: "vol-leaked\n" },
    ]);
    const res = prune({ dockerRun: run });
    expect(res.removedContainers).toEqual(["c1", "c2"]);
    expect(res.removedVolumes).toEqual(["vol-leaked"]);
    // The discovery filter is the bare membership label (no id) — so leaked
    // objects without an id label are caught.
    const psCall = calls.find((a) => a[0] === "ps")!;
    expect(labelFiltersOf(psCall)).toEqual([SANDBOX_LABEL]);
  });
});

describe("createSandbox — clones into a named volume + runs (AC-01)", () => {
  it("creates a LABELED named volume, clones into it, builds, and runs a container", async () => {
    const created: string[][] = [];
    const cloneCalls: Array<{ url: string; vol: string }> = [];
    const run: DockerRun = (args) => {
      created.push(args);
      // runContainer's docker run prints the container id to stdout.
      if (args[0] === "run") return { code: 0, stdout: "deadbeefcafe123456\n", stderr: "" };
      return { code: 0, stdout: "", stderr: "" };
    };
    const res = await createSandbox("https://example.com/repo.git", {
      id: "fixed1",
      dockerRun: run,
      cloneRepo: async (url, vol) => {
        cloneCalls.push({ url, vol });
        return 0;
      },
      buildImage: async () => ({
        tag: "ca-sbx:repo-deadbeef",
        reused: false,
        built: true,
        builder: "dockerfile-fallback",
        notes: [],
      }),
    });

    expect(res.id).toBe("fixed1");
    expect(res.volumeName).toBe("ca-sbx-vol-fixed1");
    expect(res.image).toBe("ca-sbx:repo-deadbeef");
    expect(res.containerId).toBe("deadbeefcafe123456");

    // A labeled named volume was created with BOTH the membership and id labels.
    const volCreate = created.find((a) => a[0] === "volume" && a[1] === "create")!;
    expect(volCreate).toBeDefined();
    expect(volCreate).toContain("ca-sbx-vol-fixed1");
    expect(volCreate.join(" ")).toContain(SANDBOX_LABEL);
    expect(volCreate.join(" ")).toContain(idLabel("fixed1"));

    // The clone targeted that volume.
    expect(cloneCalls).toEqual([{ url: "https://example.com/repo.git", vol: "ca-sbx-vol-fixed1" }]);

    // A container was started with the id label.
    const runCall = created.find((a) => a[0] === "run")!;
    expect(runCall.join(" ")).toContain(idLabel("fixed1"));
  });

  it("tears down the volume if the clone fails (no leaked half-sandbox)", async () => {
    const calls: string[][] = [];
    const run: DockerRun = (args) => {
      calls.push(args);
      return { code: 0, stdout: "", stderr: "" };
    };
    await expect(
      createSandbox("https://example.com/repo.git", {
        id: "fail1",
        dockerRun: run,
        cloneRepo: async () => 1, // clone fails
        buildImage: async () => {
          throw new Error("should not build after a failed clone");
        },
      }),
    ).rejects.toThrow(/clone/);
    // The volume was force-removed on the failure path.
    expect(calls).toContainEqual(["volume", "rm", "-f", "ca-sbx-vol-fail1"]);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-01 / AC-11). Real objects, namespaced,
// cleaned up. Uses a LOCAL fake repo served by a throwaway git container so the
// clone needs no external network.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t09";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

function countLabeled(): { containers: number; volumes: number } {
  const c = spawnSync(
    "docker",
    ["ps", "-a", "-q", "--filter", `label=${SANDBOX_LABEL}`, "--filter", "label=ca.sandbox.build=1"],
    { encoding: "utf8", env: DENV },
  );
  const v = spawnSync(
    "docker",
    ["volume", "ls", "-q", "--filter", `label=${SANDBOX_LABEL}`, "--filter", "label=ca.sandbox.build=1"],
    { encoding: "utf8", env: DENV },
  );
  const lines = (s: string) => s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean).length;
  return { containers: lines(c.stdout), volumes: lines(v.stdout) };
}

d("create -> destroy lifecycle [docker] (AC-01, AC-11)", () => {
  // Track everything for guaranteed teardown even on assertion failure.
  const ids: string[] = [];
  const extraVolumes: string[] = [];
  const extraContainers: string[] = [];
  let images: string[] = [];

  afterAll(() => {
    for (const id of ids) {
      spawnSync("docker", ["rm", "-f", ...containersOfId(id)], { env: DENV });
      spawnSync("docker", ["volume", "rm", "-f", `ca-sbx-vol-${id}`], { env: DENV });
    }
    for (const v of extraVolumes) spawnSync("docker", ["volume", "rm", "-f", v], { env: DENV });
    for (const c of extraContainers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    for (const i of images) spawnSync("docker", ["rmi", "-f", i], { env: DENV });
  });

  function containersOfId(id: string): string[] {
    const r = spawnSync(
      "docker",
      ["ps", "-a", "-q", "--filter", `label=${idLabel(id)}`],
      { encoding: "utf8", env: DENV },
    );
    return r.stdout.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  }

  // A minimal real "repo" served from a named volume via file:// so the clone
  // exercises the REAL alpine/git throwaway-container clone path with NO external
  // network. We seed a git repo into a source volume, then clone file:// from it.
  function seedLocalRepo(): string {
    const srcVol = `${NS}-src-${Date.now()}`;
    extraVolumes.push(srcVol);
    // Build a tiny repo (package.json so build.ts detects the node stack) inside
    // a throwaway container, committed, in /src — left in the volume.
    const script = [
      "set -e",
      "cd /src",
      "git init -q",
      "git config user.email t@t",
      "git config user.name t",
      'echo "{\\"name\\":\\"t09fix\\",\\"version\\":\\"1.0.0\\"}" > package.json',
      "git add -A",
      "git commit -qm init",
    ].join(" && ");
    const r = spawnSync(
      "docker",
      [
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        "--mount",
        `type=volume,source=${srcVol},target=/src`,
        "alpine/git:latest",
        "-c",
        script,
      ],
      { encoding: "utf8", env: DENV },
    );
    expect(r.status, r.stderr).toBe(0);
    return srcVol;
  }

  it("create clones into a named volume + starts a container; destroy sweeps to zero", () => {
    const srcVol = seedLocalRepo();
    images.push();

    // Clone via a throwaway alpine/git container that mounts BOTH the source repo
    // volume (read) and the destination sandbox volume — file:// clone, no net.
    const cloneViaLocal = (id: string) => async (_url: string, destVol: string) => {
      const r = spawnSync(
        "docker",
        [
          "run",
          "--rm",
          "--mount",
          `type=volume,source=${srcVol},target=/src,readonly`,
          "--mount",
          `type=volume,source=${destVol},target=/work/repo`,
          "alpine/git:latest",
          "clone",
          "file:///src",
          "/work/repo",
        ],
        { encoding: "utf8", env: DENV },
      );
      return r.status ?? 1;
    };

    const id = `live${Date.now().toString(16)}`;
    ids.push(id);

    // Build the real image from the cloned volume (default build path); capture
    // the image tag for cleanup.
    let builtTag = "";
    return createSandbox("https://example.invalid/src.git", {
      id,
      extraLabels: ["ca.sandbox.build=1"],
      cloneRepo: cloneViaLocal(id),
      buildImage: async (vol) => {
        const { buildOrReuseImage } = await import("./build.ts");
        const { computeDepHash } = await import("./dephash.ts");
        // Materialize manifests from the volume to compute a dephash + context.
        const { mkdtemp, rm, readdir, readFile } = await import("node:fs/promises");
        const { tmpdir } = await import("node:os");
        const path = await import("node:path");
        const dir = await mkdtemp(path.join(tmpdir(), "t09-ck-"));
        const helper = `${NS}-cp-${Date.now()}`;
        extraContainers.push(helper);
        spawnSync(
          "docker",
          ["create", "--name", helper, "--mount", `type=volume,source=${vol},target=/work/repo`, "alpine/git:latest", "true"],
          { env: DENV },
        );
        spawnSync("docker", ["cp", `${helper}:/work/repo/.`, dir], { env: DENV });
        spawnSync("docker", ["rm", "-f", helper], { env: DENV });
        const names = await readdir(dir).catch(() => [] as string[]);
        const manifests = [] as Array<{ path: string; bytes: Buffer }>;
        if (names.includes("package.json"))
          manifests.push({ path: "package.json", bytes: await readFile(path.join(dir, "package.json")) });
        const dephash = computeDepHash(manifests);
        const res = await buildOrReuseImage(dir, dephash);
        builtTag = res.tag;
        images.push(res.tag);
        await rm(dir, { recursive: true, force: true }).catch(() => {});
        return res;
      },
    }).then((res) => {
      // AC-01: a container was started and a named volume holds the clone.
      expect(res.containerId).toMatch(/^[0-9a-f]{12,}$/);
      expect(res.volumeName).toBe(`ca-sbx-vol-${id}`);

      // The named volume exists and is discoverable by label ONLY (no file).
      const found = findSandbox(id);
      expect(found).not.toBeNull();
      expect(found!.volumes).toContain(`ca-sbx-vol-${id}`);
      expect(found!.containers).toContain(res.containerId);

      // The clone really landed in the volume: package.json is present at
      // /work/repo (proves create cloned INTO the named volume).
      const ls = spawnSync(
        "docker",
        ["run", "--rm", "--entrypoint", "sh", "--mount", `type=volume,source=${res.volumeName},target=/work/repo`, "alpine/git:latest", "-c", "ls /work/repo"],
        { encoding: "utf8", env: DENV },
      );
      expect(ls.stdout).toMatch(/package\.json/);

      // AC-11: create -> destroy leaves ZERO ca.sandbox=1 objects (this id).
      const dres = destroySandbox(id);
      expect(dres.removedContainers).toContain(res.containerId);
      expect(dres.removedVolumes).toContain(res.volumeName);
      expect(findSandbox(id)).toBeNull();
    });
  }, 300_000);

  it("--keep-volume leaves the volume after destroy", () => {
    const srcVol = seedLocalRepo();
    const cloneViaLocal = async (_url: string, destVol: string) => {
      const r = spawnSync(
        "docker",
        [
          "run",
          "--rm",
          "--mount",
          `type=volume,source=${srcVol},target=/src,readonly`,
          "--mount",
          `type=volume,source=${destVol},target=/work/repo`,
          "alpine/git:latest",
          "clone",
          "file:///src",
          "/work/repo",
        ],
        { encoding: "utf8", env: DENV },
      );
      return r.status ?? 1;
    };

    const id = `keep${Date.now().toString(16)}`;
    ids.push(id);

    return createSandbox("https://example.invalid/src.git", {
      id,
      extraLabels: ["ca.sandbox.build=1"],
      cloneRepo: cloneViaLocal,
      buildImage: async (vol) => {
        const { buildOrReuseImage } = await import("./build.ts");
        const { computeDepHash } = await import("./dephash.ts");
        const { mkdtemp, rm, readdir, readFile } = await import("node:fs/promises");
        const { tmpdir } = await import("node:os");
        const path = await import("node:path");
        const dir = await mkdtemp(path.join(tmpdir(), "t09-ck2-"));
        const helper = `${NS}-cp2-${Date.now()}`;
        extraContainers.push(helper);
        spawnSync("docker", ["create", "--name", helper, "--mount", `type=volume,source=${vol},target=/work/repo`, "alpine/git:latest", "true"], { env: DENV });
        spawnSync("docker", ["cp", `${helper}:/work/repo/.`, dir], { env: DENV });
        spawnSync("docker", ["rm", "-f", helper], { env: DENV });
        const names = await readdir(dir).catch(() => [] as string[]);
        const manifests = [] as Array<{ path: string; bytes: Buffer }>;
        if (names.includes("package.json"))
          manifests.push({ path: "package.json", bytes: await readFile(path.join(dir, "package.json")) });
        const res = await buildOrReuseImage(dir, computeDepHash(manifests));
        images.push(res.tag);
        await rm(dir, { recursive: true, force: true }).catch(() => {});
        return res;
      },
    }).then((res) => {
      const dres = destroySandbox(id, { keepVolume: true });
      expect(dres.removedContainers).toContain(res.containerId);
      expect(dres.keptVolumes).toContain(res.volumeName);
      expect(dres.removedVolumes).toEqual([]);

      // The container is gone but the volume survives.
      expect(findSandbox(id)!.containers).toEqual([]);
      const volExists = spawnSync("docker", ["volume", "inspect", res.volumeName], { encoding: "utf8", env: DENV });
      expect(volExists.status).toBe(0);

      // Clean the kept volume so we don't leak it past the suite.
      spawnSync("docker", ["volume", "rm", "-f", res.volumeName], { env: DENV });
    });
  }, 300_000);

  it("prune reclaims a manually-leaked ca.sandbox=1 object", () => {
    // Hand-leak a labeled volume with NO id label — exactly the abandoned/partial
    // object prune must reclaim.
    const leaked = `${NS}-leaked-${Date.now()}`;
    extraVolumes.push(leaked);
    const mk = spawnSync(
      "docker",
      ["volume", "create", "--label", SANDBOX_LABEL, "--label", "ca.sandbox.build=1", leaked],
      { encoding: "utf8", env: DENV },
    );
    expect(mk.status, mk.stderr).toBe(0);

    // It's visible to the registry by the bare membership label.
    const before = listSandboxes().some((s) => s.volumes.includes(leaked));
    expect(before).toBe(true);

    const pres = prune();
    expect(pres.removedVolumes).toContain(leaked);

    // Gone — no ca.sandbox=1 + build-marked objects remain.
    const after = countLabeled();
    expect(after.volumes).toBe(0);
    expect(after.containers).toBe(0);
  }, 300_000);
});
