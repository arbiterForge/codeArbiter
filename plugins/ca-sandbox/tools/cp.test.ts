/**
 * cp.test.ts — T-12. Covers AC-10.
 *
 * Host-initiated, PULL-ONLY file extraction. `cpOut(id, containerPath, hostDest)`
 * shells `docker cp <container>:<path> <hostDest>` — the host reaches IN and pulls
 * a file out. The reverse direction (getting host files INTO the box) is the
 * danger: the only way to bulk-inject host files would be a bind mount, and the
 * load-bearing invariant (spec AC-02 / AC-10) is that a sandbox container NEVER
 * gets a host bind. So this module routes any "copy-in" mount request through
 * mounts.ts's buildMountArgs, which THROWS on any bind spec — making a
 * host->container bind structurally impossible.
 *
 * Two layers:
 *   1. PURE unit tests — buildCpOutArgs(...) assembles the right pull-only argv
 *      (`cp <id>:<path> <dest>`, in that direction, never the reverse), and the
 *      reverse-direction guard rejects a host->container bind via the mount
 *      chokepoint. RED gate; runs everywhere.
 *   2. A DOCKER-GATED integration test (guarded by `docker info`): start a real
 *      container, write a file at /work, cpOut it to a host temp dir, assert the
 *      bytes match. Namespaced + cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildCpOutArgs, cpOut, assertNoCopyInBind } from "./cp.ts";
import { BindMountRejectedError } from "./mounts.ts";

// --------------------------------------------------------------------------
// PURE unit layer — argv assembly + reverse-bind rejection, no real docker.
// --------------------------------------------------------------------------
describe("buildCpOutArgs — pull-only direction (AC-10)", () => {
  it("assembles `cp <id>:<containerPath> <hostDest>` in the pull direction", () => {
    const argv = buildCpOutArgs("abc123", "/work/out.txt", "./dest/out.txt");
    expect(argv).toEqual(["cp", "abc123:/work/out.txt", "./dest/out.txt"]);
  });

  it("never produces the reverse direction (host source before container dest)", () => {
    const argv = buildCpOutArgs("abc123", "/work/out.txt", "./dest/out.txt");
    // The container ref (`<id>:`) is the SOURCE (argv[1]); the host path is the
    // DEST (argv[2]). A reversed `cp <hostDest> <id>:<path>` would be a push.
    expect(argv[1]).toBe("abc123:/work/out.txt");
    expect(argv[2]).toBe("./dest/out.txt");
    expect(argv[2].startsWith("abc123:")).toBe(false);
  });

  it("refuses an empty container id, container path, or host dest", () => {
    expect(() => buildCpOutArgs("", "/work/x", "./x")).toThrow();
    expect(() => buildCpOutArgs("abc", "", "./x")).toThrow();
    expect(() => buildCpOutArgs("abc", "/work/x", "")).toThrow();
  });
});

describe("assertNoCopyInBind — host->container bind is impossible (AC-10)", () => {
  it("throws (via the mount chokepoint) on a -v host:container bind copy-in", () => {
    expect(() => assertNoCopyInBind("/home/user/secrets:/work/secrets")).toThrow(
      BindMountRejectedError,
    );
  });

  it("throws on an explicit type=bind copy-in spec", () => {
    expect(() =>
      assertNoCopyInBind({ type: "bind", source: "/etc", target: "/work/etc" }),
    ).toThrow(/bind/i);
  });

  it("the rejection comes from mounts.ts (cp does not hand-roll its own check)", () => {
    // BindMountRejectedError is mounts.ts's error type — proving the routing.
    let err: unknown;
    try {
      assertNoCopyInBind("/x:/work/x");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(BindMountRejectedError);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-10).
// cpOut copies a real file out of a real container to the host.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t12";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

d("cpOut [docker] — pulls a file from /work to the host (AC-10)", () => {
  const created = { containers: [] as string[] };
  let tmp: string | undefined;

  afterAll(() => {
    for (const c of created.containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    if (tmp) rmSync(tmp, { recursive: true, force: true });
  });

  it("copies /work/<f> out to a host dest with identical bytes", () => {
    const image = "busybox:latest";
    const pull = spawnSync("docker", ["pull", image], { encoding: "utf8", env: DENV });
    expect(pull.status, pull.stderr).toBe(0);

    const name = `${NS}-${Date.now()}`;
    // A minimal container that writes a known file at /work then idles. No mounts
    // at all — cp reaches into the container's own FS, no host bind anywhere.
    const marker = "ca-sandbox-cp-out-marker-12345";
    const run = spawnSync(
      "docker",
      [
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "ca.sandbox.build=1",
        image,
        "sh",
        "-c",
        `mkdir -p /work && printf '%s' '${marker}' > /work/out.txt && sleep infinity`,
      ],
      { encoding: "utf8", env: DENV },
    );
    expect(run.status, run.stderr).toBe(0);
    const id = run.stdout.trim();
    created.containers.push(id);

    // Give the container a beat to write the file (sh runs the printf at start).
    // Poll docker exec for the file rather than sleeping blindly.
    let ready = false;
    for (let i = 0; i < 50 && !ready; i++) {
      const chk = spawnSync("docker", ["exec", id, "test", "-f", "/work/out.txt"], { env: DENV });
      ready = chk.status === 0;
      if (!ready) spawnSync("docker", ["exec", id, "true"], { env: DENV }); // tiny yield
    }
    expect(ready, "file /work/out.txt should exist in the container").toBe(true);

    tmp = mkdtempSync(path.join(tmpdir(), "ca-sbx-t12-"));
    const dest = path.join(tmp, "pulled.txt");

    const r = cpOut(id, "/work/out.txt", dest, { dockerRun: (args) => {
      const res = spawnSync("docker", args, { encoding: "utf8", env: DENV });
      return { code: res.status ?? 1, stdout: res.stdout ?? "", stderr: res.stderr ?? "" };
    } });
    expect(r.code, r.stderr).toBe(0);

    expect(existsSync(dest)).toBe(true);
    expect(readFileSync(dest, "utf8")).toBe(marker);
  }, 120_000);
});
