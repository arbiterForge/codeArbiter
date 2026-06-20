/**
 * layering.test.ts — T-07. Covers AC-06 (Spike A, CONFIRM-06).
 *
 * The end-to-end proof of the /deps layout: with the live source named volume
 * mounted ONLY at /work/repo, the deps baked OUT OF TREE at /deps must
 *   (1) RESOLVE at runtime (the source imports a real dep and it works), and
 *   (2) SURVIVE an in-place source edit in the volume — editing the source in
 *       the volume and re-running takes effect AND the deps still resolve.
 *
 * This is the one layout Spike A proved correct (deps at /deps + NODE_PATH /
 * PYTHONPATH, source volume only at /work/repo): mounting the volume OVER the
 * app dir is fine because /deps is outside it, so the mount never shadows deps
 * and the source stays live-editable.
 *
 * Shape (both Node and Python fixtures):
 *   1. buildOrReuseImage(fixture) -> image with deps baked to /deps (build.ts).
 *   2. create a namespaced named volume; SEED it from the image's baked
 *      /work/repo so the live source starts as a faithful copy of the repo.
 *   3. runContainer(image, vol, "offline") -> the isolated keep-alive container,
 *      source volume at /work/repo, deps at /deps (run.ts). Offline: deps are
 *      baked, so no network is needed — this also proves /deps is self-contained.
 *   4. exec the entry point -> assert SRC=original AND DEP_OK=true
 *      (deps resolve at runtime under the mount).
 *   5. EDIT the source file IN the volume (rewrite SRC=edited).
 *   6. exec again -> assert SRC=edited AND DEP_OK=true
 *      (the edit took effect live AND deps still resolve).
 *
 * Pure layer: a fast, docker-free assertion that the run argv keeps deps and the
 * source on separate, non-shadowing paths (the structural precondition for the
 * layering to work at all) — the RED gate that runs everywhere.
 *
 * Docker-gated layer: the real end-to-end proof, guarded by a `docker info`
 * probe. Every docker object is namespaced with the task id + labeled
 * ca.sandbox.build=1 and torn down in afterAll.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildOrReuseImage, imageTag, APP_DIR, DEPS_DIR } from "./build.ts";
import { buildRunArgs, runContainer } from "./run.ts";
import { computeDepHash } from "./dephash.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "__fixtures__");

// --------------------------------------------------------------------------
// PURE layer — the structural precondition: deps and source never collide.
// --------------------------------------------------------------------------
describe("layering precondition — /deps is outside the /work/repo mount (AC-06)", () => {
  it("the run argv mounts the source volume at /work/repo and never at /deps", () => {
    const argv = buildRunArgs("ca-sbx:demo-abc", "ca-sbx-vol-demo", "offline");
    const mountValues = argv.filter((_, i) => argv[i - 1] === "--mount");
    // The source volume targets /work/repo …
    expect(mountValues.some((m) => m.includes(`target=${APP_DIR}`) && m.startsWith("type=volume"))).toBe(true);
    // … and NOTHING is mounted at /deps, so the baked deps are never shadowed.
    for (const m of mountValues) {
      expect(m).not.toContain(`target=${DEPS_DIR}`);
    }
  });

  it("APP_DIR and DEPS_DIR are disjoint paths (one cannot shadow the other)", () => {
    expect(DEPS_DIR).toBe("/deps");
    expect(APP_DIR).toBe("/work/repo");
    expect(APP_DIR.startsWith(DEPS_DIR + "/")).toBe(false);
    expect(DEPS_DIR.startsWith(APP_DIR + "/")).toBe(false);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED layer — the real end-to-end proof (AC-06).
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t07";
const BUILD_LABEL = "ca.sandbox.build=1";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

type Tracker = { containers: string[]; volumes: string[]; images: string[] };

/** Run docker with MSYS path conversion disabled (Windows); return the result. */
function docker(args: string[]) {
  return spawnSync("docker", args, { encoding: "utf8", env: DENV });
}

/**
 * Seed a fresh named volume with the image's baked /work/repo source, so the
 * live volume starts as a faithful copy of the repo (what a real clone-into-vol
 * would produce). Runs a throwaway helper container (NOT a sandbox run — this is
 * test scaffolding) as root so the copy succeeds, then the sandbox mounts it.
 */
function seedVolumeFromImage(image: string, vol: string) {
  const mk = docker(["volume", "create", "--label", BUILD_LABEL, "--label", "ca.sandbox=1", vol]);
  expect(mk.status, mk.stderr).toBe(0);
  const seed = docker([
    "run", "--rm", "--user", "0:0",
    "--mount", `type=volume,source=${vol},target=/seed`,
    image, "sh", "-c", `cp -a ${APP_DIR}/. /seed/ && chmod -R a+rwX /seed`,
  ]);
  expect(seed.status, seed.stderr).toBe(0);
}

/** Overwrite a file in the live volume (root helper), proving in-place edits. */
function editFileInVolume(vol: string, relPath: string, contents: string) {
  // base64 the new contents so arbitrary bytes survive the shell hop unmangled.
  const b64 = Buffer.from(contents, "utf8").toString("base64");
  const edit = docker([
    "run", "--rm", "--user", "0:0",
    "--mount", `type=volume,source=${vol},target=/work/repo`,
    "busybox:latest", "sh", "-c",
    `echo ${b64} | base64 -d > ${APP_DIR}/${relPath} && chmod a+rwX ${APP_DIR}/${relPath}`,
  ]);
  expect(edit.status, edit.stderr).toBe(0);
}

/** Exec the entry point inside the running sandbox container; return combined output. */
function execApp(containerId: string, cmd: string[]): string {
  const r = docker(["exec", containerId, ...cmd]);
  return r.stdout + r.stderr;
}

function cleanup(t: Tracker) {
  for (const c of t.containers) docker(["rm", "-f", c]);
  for (const v of t.volumes) docker(["volume", "rm", "-f", v]);
  for (const i of t.images) docker(["rmi", "-f", i]);
}

d("layering [docker] — deps at /deps survive the /work/repo volume + live-editable source (AC-06)", () => {
  const t: Tracker = { containers: [], volumes: [], images: [] };

  // busybox is the edit-helper base image; track it so the test is self-cleaning.
  const pull = docker(["pull", "busybox:latest"]);
  if (pull.status === 0) t.images.push("busybox:latest");

  afterAll(() => cleanup(t));

  it("node fixture: baked is-odd resolves at runtime AND an in-volume index.js edit takes effect", async () => {
    const repoDir = path.join(FIXTURES, "node");
    // Namespace the dephash with the task id so this image can never collide
    // with another task's cache entry (and is easy to identify + clean up).
    const dephash = "t07n" + computeDepHash(
      [{ path: "package.json", bytes: '{"is-odd":"3.0.1"}' }],
      "fallback",
    ).slice(0, 8);

    const build = await buildOrReuseImage(repoDir, dephash);
    t.images.push(build.tag);
    expect(build.tag).toBe(imageTag(repoDir, dephash));

    const vol = `${NS}-node-vol-${Date.now()}`;
    seedVolumeFromImage(build.tag, vol);
    t.volumes.push(vol);

    // Start the isolated sandbox container: source volume only at /work/repo,
    // deps baked at /deps, offline (deps are self-contained — no network).
    const id = runContainer(build.tag, vol, "offline", {
      extraLabels: [BUILD_LABEL],
      namePrefix: `${NS}-node`,
    });
    t.containers.push(id);

    // (1) deps RESOLVE at runtime under the volume mount, original source runs.
    const out1 = execApp(id, ["node", "index.js"]);
    expect(out1, out1).toContain("NODE_FIXTURE SRC=original DEP_OK=true");

    // (2) edit the source IN the volume -> the edit takes effect on re-run AND
    //     the baked deps still resolve.
    editFileInVolume(
      vol,
      "index.js",
      'const isOdd = require("is-odd");\n' +
        'const SRC = "edited";\n' +
        "const depOk = isOdd(3) === true && isOdd(4) === false;\n" +
        "console.log(`NODE_FIXTURE SRC=${SRC} DEP_OK=${depOk}`);\n",
    );
    const out2 = execApp(id, ["node", "index.js"]);
    expect(out2, out2).toContain("NODE_FIXTURE SRC=edited DEP_OK=true");
  }, 300_000);

  it("python fixture: baked six resolves at runtime AND an in-volume main.py edit takes effect", async () => {
    const repoDir = path.join(FIXTURES, "py");
    const dephash = "t07p" + computeDepHash(
      [{ path: "requirements.txt", bytes: "six==1.16.0\n" }],
      "fallback",
    ).slice(0, 8);

    const build = await buildOrReuseImage(repoDir, dephash);
    t.images.push(build.tag);
    expect(build.tag).toBe(imageTag(repoDir, dephash));

    const vol = `${NS}-py-vol-${Date.now()}`;
    seedVolumeFromImage(build.tag, vol);
    t.volumes.push(vol);

    const id = runContainer(build.tag, vol, "offline", {
      extraLabels: [BUILD_LABEL],
      namePrefix: `${NS}-py`,
    });
    t.containers.push(id);

    // (1) deps RESOLVE at runtime under the volume mount, original source runs.
    const out1 = execApp(id, ["python3", "main.py"]);
    expect(out1, out1).toContain("PY_FIXTURE SRC=original DEP_OK=True");

    // (2) edit the source IN the volume -> takes effect AND deps still resolve.
    editFileInVolume(
      vol,
      "main.py",
      "import six\n" +
        'SRC = "edited"\n' +
        "DEP_OK = hasattr(six, '__version__') and six.PY3 is True\n" +
        'print(f"PY_FIXTURE SRC={SRC} DEP_OK={DEP_OK}")\n',
    );
    const out2 = execApp(id, ["python3", "main.py"]);
    expect(out2, out2).toContain("PY_FIXTURE SRC=edited DEP_OK=True");
  }, 300_000);
});
