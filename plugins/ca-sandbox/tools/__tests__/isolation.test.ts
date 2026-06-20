/**
 * isolation.test.ts — T-08. Covers AC-03.
 *
 * The load-bearing invariant of ca-sandbox (spec "Load-bearing invariant"):
 * untrusted code in the box can NEVER reach the host filesystem. AC-01 proves it
 * STRUCTURALLY (run.test.ts: docker inspect shows no bind, no docker.sock, not
 * privileged). This test proves it BEHAVIORALLY, the way an attacker would test
 * it — a positive/negative canary pair:
 *
 *   1. Plant a host-side canary: a real file on the HOST filesystem whose
 *      contents are a freshly minted, globally unique uuid.
 *   2. Start a real, isolated sandbox container (runContainer, offline).
 *   3. POSITIVE host-FS isolation: a process INSIDE the box cannot read that
 *      exact host abspath — AND a brute, whole-filesystem `grep -rl <uuid> /`
 *      from inside the box finds the uuid NOWHERE. The host's bytes are simply
 *      not present in the container's view of the world.
 *   4. NEGATIVE control: the very same canary IS readable from the HOST at the
 *      same abspath — proving the file genuinely exists and the uuid is real, so
 *      the in-box failure is true isolation and not a bad path or an empty file.
 *   5. Structural cross-check: `docker inspect` on the running container shows no
 *      "Type":"bind" mount (the structural reason the canary is unreachable).
 *
 * Docker-gated: the whole suite guards behind a `docker info` probe and skips
 * cleanly on a host without Docker. Every object created is namespaced with this
 * task id and the `ca.sandbox.build=1` label, and torn down in afterAll.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { runContainer } from "../run.ts";

// On Windows + Git Bash, container paths / `-e HOME` handed to docker get
// mangled by MSYS path conversion; MSYS_NO_PATHCONV=1 disables it (Spike A/B).
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t08";

// Exec a command inside the running container, capturing stdout/stderr/exit.
function execIn(id: string, argv: string[]): { code: number; stdout: string; stderr: string } {
  const r = spawnSync("docker", ["exec", id, ...argv], { encoding: "utf8", env: DENV });
  return { code: r.status ?? 1, stdout: r.stdout ?? "", stderr: r.stderr ?? (r.error ? String(r.error) : "") };
}

d("host-FS isolation canary [docker] (AC-03)", () => {
  const created = { containers: [] as string[], volumes: [] as string[], images: [] as string[] };
  let hostDir = "";
  let hostCanaryPath = "";
  let uuid = "";
  let containerId = "";

  beforeAll(() => {
    // 1. Plant the host-side canary with a globally unique marker.
    uuid = randomUUID();
    hostDir = mkdtempSync(join(tmpdir(), `${NS}-canary-`));
    hostCanaryPath = join(hostDir, "host-secret.txt");
    writeFileSync(hostCanaryPath, `CA_SANDBOX_HOST_CANARY ${uuid}\n`, "utf8");

    // A tiny base image with a shell + the coreutils the canary checks need
    // (cat, grep). busybox is small, ubiquitous, and ships both.
    const image = "busybox:latest";
    const pull = spawnSync("docker", ["pull", image], { encoding: "utf8", env: DENV });
    expect(pull.status, pull.stderr).toBe(0);
    created.images.push(image);

    // A namespaced, labeled named volume — the live source mount at /work/repo.
    const vol = `${NS}-vol-${Date.now()}`;
    const mk = spawnSync(
      "docker",
      ["volume", "create", "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1", vol],
      { encoding: "utf8", env: DENV },
    );
    expect(mk.status, mk.stderr).toBe(0);
    created.volumes.push(vol);

    // 2. Start the real isolated sandbox container (no host bind, offline).
    containerId = runContainer(image, vol, "offline", {
      extraLabels: ["ca.sandbox.build=1"],
      namePrefix: NS,
    });
    expect(containerId).toMatch(/^[0-9a-f]{12,}$/);
    created.containers.push(containerId);
  }, 180_000);

  afterAll(() => {
    for (const c of created.containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    for (const v of created.volumes) spawnSync("docker", ["volume", "rm", "-f", v], { env: DENV });
    for (const i of created.images) spawnSync("docker", ["rmi", "-f", i], { env: DENV });
    if (hostDir) rmSync(hostDir, { recursive: true, force: true });
  });

  it("NEGATIVE control: the canary IS readable from the HOST at its abspath", () => {
    // Proves the file genuinely exists and carries the real uuid, so the in-box
    // failure below is true isolation — not a bad path or an empty file.
    const onHost = readFileSync(hostCanaryPath, "utf8");
    expect(onHost).toContain(uuid);
  });

  it("a process INSIDE the box cannot read the host canary at its real abspath", () => {
    // The host abspath (Windows or POSIX) simply does not exist in the
    // container's filesystem view — reading it MUST fail and MUST NOT surface
    // the uuid. We probe both the raw host abspath and a POSIX-normalized form
    // so the assertion holds regardless of host OS path style.
    const posixPath = hostCanaryPath.replace(/\\/g, "/");
    for (const probe of new Set([hostCanaryPath, posixPath])) {
      const r = execIn(containerId, ["cat", probe]);
      expect(r.code).not.toBe(0); // cat of a non-existent path fails
      expect(r.stdout).not.toContain(uuid);
      expect(r.stderr).not.toContain(uuid);
    }
  });

  it("a brute whole-FS grep for the uuid INSIDE the box finds NOTHING", () => {
    // The attacker's strongest move: scan the entire container filesystem for
    // the marker. We grep every REAL on-disk root, EXCLUDING the kernel
    // pseudo-filesystems /proc, /sys and /dev. That exclusion is correct, not a
    // dodge: those trees are kernel/virtual, not the host filesystem the canary
    // lives on — and grepping them is pathological (a plain `grep -rl <uuid> /`
    // recurses /proc/kcore, a multi-TB pseudo-file, which OOM-kills the
    // container, exit 137, before it can prove anything). So the brute scan
    // covers exactly the surface where a leaked host file COULD appear: the
    // container's real disk. -r recurse, -s suppress unreadable/permission
    // errors, -l list matching files only. Clean isolation => no path printed,
    // the uuid appears nowhere in stdout, and grep exits non-zero (no match).
    const r = execIn(containerId, [
      "sh",
      "-c",
      `grep -rsl ${uuid} $(ls -d /* | grep -vE '^/(proc|sys|dev)$')`,
    ]);
    expect(r.stdout.trim()).toBe(""); // no real file in the box contains the uuid
    expect(r.stdout).not.toContain(uuid);
    expect(r.code).not.toBe(0); // grep: nothing matched

    // The container is still alive after the brute scan — i.e. the scan was a
    // genuine search, not a process the kernel OOM-killed mid-traversal.
    const alive = spawnSync(
      "docker",
      ["inspect", containerId, "--format", "{{.State.Running}}"],
      { encoding: "utf8", env: DENV },
    );
    expect(alive.status, alive.stderr).toBe(0);
    expect(alive.stdout.trim()).toBe("true");
  });

  it("docker inspect shows NO bind mount (the structural reason the canary is unreachable)", () => {
    const inspect = spawnSync("docker", ["inspect", containerId], { encoding: "utf8", env: DENV });
    expect(inspect.status, inspect.stderr).toBe(0);
    const info = JSON.parse(inspect.stdout)[0];

    const mounts: Array<{ Type?: string; Source?: string; Destination?: string }> = info.Mounts ?? [];
    for (const m of mounts) {
      expect(m.Type).not.toBe("bind");
    }
    // Defense-in-depth: the host canary dir is the source of NO mount at all.
    const all = JSON.stringify(info);
    expect(all).not.toContain(hostDir);
  });
});
