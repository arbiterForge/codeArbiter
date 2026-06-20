/**
 * multistack.test.ts — T-13. Covers AC-07.
 *
 * AC-07: "nixpacks builds a runnable image for each fixture repo
 * (node/python/go/rust); dephash is deterministic (hash twice -> identical)."
 *
 * This test drives the four minimal stack fixtures under `__fixtures__/`
 * (node, py, go, rust) through the SAME seam the lifecycle uses:
 *   - computeDepHash (dephash.ts)  — the cache key over a fixture's manifests;
 *   - buildOrReuseImage (build.ts) — the nixpacks-wrap + dephash-cache builder.
 *
 * Two layers, mirroring build.test.ts:
 *
 *   1. PURE (always-on) — for every fixture present, computing the dephash twice
 *      over the SAME manifest bytes yields the SAME 12-char key (AC-07's
 *      "deterministic" half), and a stack's two distinct manifest sets hash
 *      differently. This is the RED gate and needs no docker. It also asserts the
 *      two fixtures THIS task owns (go, rust) exist with their manifests, so the
 *      multi-stack matrix is real.
 *
 *   2. DOCKER-GATED (guarded by a `docker info` probe) — for every fixture
 *      present, buildOrReuseImage produces a RUNNABLE image (it `docker image
 *      inspect`s clean AND a `docker run` of it exits 0), and a SECOND build with
 *      the SAME dephash REUSES the cached image with NO rebuild — i.e. two builds
 *      of the same fixture are deterministic and converge on one identical tag
 *      (AC-04 cache identity, AC-07 "hash twice -> identical" end to end). Every
 *      docker object is namespaced with the task id `t13` and the
 *      `ca.sandbox.build=1` label and removed in afterAll.
 *
 * Honest scope note: in an environment WITHOUT nixpacks, build.ts takes its
 * generated-Dockerfile fallback, which only specializes node/python; go/rust then
 * build as a valid base image with the source baked at /work/repo. The test
 * therefore asserts the image is RUNNABLE (a docker-generic, environment-stable
 * fact) rather than stack-specific compilation, which is a nixpacks concern outside
 * this task's control. When nixpacks IS installed the same assertions hold a
 * fortiori.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { computeDepHash, type ManifestFile } from "./dephash.ts";
import { buildOrReuseImage, imageTag, type BuildResult } from "./build.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "__fixtures__");

/**
 * The multi-stack matrix. `manifests` are the dependency manifests/lockfiles the
 * dephash hashes for that stack (the same files build.ts's detector keys on).
 */
type Stack = {
  /** Stack id and `__fixtures__/<dir>` directory name. */
  dir: string;
  /** Manifest/lockfile filenames hashed for the cache key (must exist to count). */
  manifests: string[];
};

const STACKS: Stack[] = [
  { dir: "node", manifests: ["package.json"] },
  { dir: "py", manifests: ["requirements.txt"] },
  { dir: "go", manifests: ["go.mod"] },
  { dir: "rust", manifests: ["Cargo.toml", "Cargo.lock"] },
];

/** Absolute path to a fixture dir. */
function fixtureDir(stack: Stack): string {
  return path.join(FIXTURES, stack.dir);
}

/** True when the fixture dir AND all its declared manifests are present. */
function fixturePresent(stack: Stack): boolean {
  const dir = fixtureDir(stack);
  if (!existsSync(dir)) return false;
  return stack.manifests.every((m) => existsSync(path.join(dir, m)));
}

/** Read a fixture's manifest set as ManifestFile[] (relpath + raw bytes). */
function readManifests(stack: Stack): ManifestFile[] {
  const dir = fixtureDir(stack);
  return stack.manifests.map((rel) => ({
    path: rel,
    bytes: readFileSync(path.join(dir, rel)),
  }));
}

const PRESENT = STACKS.filter(fixturePresent);

// --------------------------------------------------------------------------
// PURE layer — deterministic dephash across two reads (AC-07), no docker.
// --------------------------------------------------------------------------
describe("multistack fixtures — present + deterministic dephash (AC-07)", () => {
  it("ships the go and rust fixtures this task owns, with their manifests", () => {
    const go = STACKS.find((s) => s.dir === "go")!;
    const rust = STACKS.find((s) => s.dir === "rust")!;
    expect(fixturePresent(go)).toBe(true);
    expect(fixturePresent(rust)).toBe(true);
  });

  it("covers a real multi-stack matrix (at least go + rust present)", () => {
    expect(PRESENT.length).toBeGreaterThanOrEqual(2);
  });

  for (const stack of STACKS) {
    const present = fixturePresent(stack);
    const t = present ? it : it.skip;

    t(`[${stack.dir}] dephash is identical across two reads of the same fixture`, () => {
      const h1 = computeDepHash(readManifests(stack), "fallback");
      const h2 = computeDepHash(readManifests(stack), "fallback");
      expect(h1).toBe(h2);
      expect(h1).toMatch(/^[0-9a-f]{12}$/);
    });

    t(`[${stack.dir}] a manifest byte change yields a different dephash`, () => {
      const base = readManifests(stack);
      const mutated = base.map((m, i) =>
        i === 0 ? { ...m, bytes: Buffer.concat([Buffer.from(m.bytes as Buffer), Buffer.from("\n# x\n")]) } : m,
      );
      expect(computeDepHash(mutated, "fallback")).not.toBe(computeDepHash(base, "fallback"));
    });
  }
});

// --------------------------------------------------------------------------
// DOCKER-GATED layer — each fixture builds a runnable image; two builds of the
// same fixture are deterministic (identical tag, second build is a cache reuse).
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}

const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;
const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

/** Namespace every dephash for this task so tags never collide with other tasks. */
function t13Hash(stack: Stack): string {
  return "t13" + computeDepHash(readManifests(stack), "fallback").slice(0, 9);
}

d("multistack [docker] — each fixture builds a runnable image; deterministic across two builds (AC-07)", () => {
  const createdTags = new Set<string>();

  afterAll(() => {
    for (const tag of createdTags) {
      spawnSync("docker", ["rmi", "-f", tag], { encoding: "utf8", env: DOCKER_ENV });
      // The nixpacks path leaves an intermediate `<tag>-nixpacks-base`; remove it too if present.
      spawnSync("docker", ["rmi", "-f", `${tag}-nixpacks-base`], { encoding: "utf8", env: DOCKER_ENV });
    }
  });

  for (const stack of STACKS) {
    const present = fixturePresent(stack);
    const t = present && HAS_DOCKER ? it : it.skip;

    t(
      `[${stack.dir}] builds a runnable image, and a second build with the same dephash reuses it (no rebuild)`,
      async () => {
        const dir = fixtureDir(stack);
        const hash = t13Hash(stack);
        const expectedTag = imageTag(dir, hash);

        // FIRST build — cache miss -> a real image is produced and tagged.
        const r1: BuildResult = await buildOrReuseImage(dir, hash);
        createdTags.add(r1.tag);
        expect(r1.tag).toBe(expectedTag);
        expect(r1.built).toBe(true);
        expect(r1.reused).toBe(false);

        // The image exists.
        const inspect = spawnSync("docker", ["image", "inspect", r1.tag], {
          encoding: "utf8",
          env: DOCKER_ENV,
        });
        expect(inspect.status).toBe(0);

        // The image is RUNNABLE: a container starts and a command exits 0.
        const runOk = spawnSync(
          "docker",
          ["run", "--rm", r1.tag, "sh", "-c", "echo SANDBOX_RUNNABLE"],
          { encoding: "utf8", env: DOCKER_ENV },
        );
        expect(runOk.status).toBe(0);
        expect(runOk.stdout).toMatch(/SANDBOX_RUNNABLE/);

        // The baked source is present at /work/repo (the live mount point).
        const lsRepo = spawnSync(
          "docker",
          ["run", "--rm", "-w", "/work/repo", r1.tag, "sh", "-c", "ls -A | head -20"],
          { encoding: "utf8", env: DOCKER_ENV },
        );
        expect(lsRepo.status).toBe(0);
        expect(lsRepo.stdout.trim().length).toBeGreaterThan(0);

        // SECOND build, identical dephash -> SAME tag, REUSE, NO rebuild.
        // (Two builds of the same fixture are deterministic — AC-07 "hash twice
        //  -> identical" carried end to end into the cache tag.)
        const r2: BuildResult = await buildOrReuseImage(dir, hash);
        expect(r2.tag).toBe(r1.tag);
        expect(r2.reused).toBe(true);
        expect(r2.built).toBe(false);
      },
      300_000,
    );
  }
});
