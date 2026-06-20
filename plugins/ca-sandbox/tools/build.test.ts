/**
 * build.test.ts — T-05. Covers AC-04 / AC-05.
 *
 * buildOrReuseImage(repoDir, dephash) is the nixpacks-wrap + dephash-cache layer.
 * Contract (spec AC-04 / AC-05, plan T-05):
 *   - the image is tagged `ca-sbx:<repo>-<dephash>` (repo = sanitized repoDir basename);
 *   - cache hit: `docker image inspect <tag>` exits 0 -> REUSE, NO build runs;
 *   - cache miss: build runs (nixpacks, or the generated-Dockerfile fallback) and
 *     the deps are relocated out-of-tree to /deps with NODE_PATH/PYTHONPATH ENV
 *     exported (Spike A layering);
 *   - an unchanged rerun recomputes the SAME dephash -> SAME tag -> cache hit -> no build;
 *   - a manifest change recomputes a DIFFERENT dephash -> DIFFERENT tag -> miss -> rebuild.
 *
 * Two test layers:
 *   1. PURE unit tests drive buildOrReuseImage through INJECTED docker/build deps
 *      (no real docker) to prove the tag shape, the cache-hit/no-build path, the
 *      miss-rebuild path, and the /deps relocation directives — these are the RED
 *      gate and run everywhere.
 *   2. A DOCKER-GATED integration test (guarded by a `docker info` probe) builds a
 *      real image for a tiny node fixture, proves the tag exists, proves an
 *      unchanged rerun performs NO build, proves a manifest change rebuilds under a
 *      new tag, and proves baked deps resolve from /deps at runtime. It namespaces
 *      and cleans up every docker object it creates.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  buildOrReuseImage,
  imageTag,
  relocationOverlay,
  type BuildDeps,
  type BuildResult,
} from "./build.ts";
import { computeDepHash } from "./dephash.ts";

// --------------------------------------------------------------------------
// nixpacks relocation overlay — pins the two bugs the never-run native path had
// (it moved deps from /work/repo not nixpacks' /app, and never reset the
// bash-login ENTRYPOINT that would break `sleep infinity`). Pure string check.
// --------------------------------------------------------------------------
describe("relocationOverlay — appended to the nixpacks-generated Dockerfile", () => {
  const overlay = relocationOverlay();
  it("relocates deps FROM /app (nixpacks' app dir) TO /deps, not from /work/repo", () => {
    expect(overlay).toMatch(/mv\s+\/app\/node_modules\s+\/deps\/node_modules/);
    // The move source must be /app, never /work/repo (the old, never-run bug).
    expect(overlay).not.toMatch(/mv\s+\/work\/repo\/node_modules/);
  });
  it("relocates python deps from nixpacks' /opt/venv, not /app/.venv only", () => {
    // nixpacks installs python into a venv at /opt/venv; the overlay must look there.
    expect(overlay).toMatch(/\/opt\/venv\/lib\/python\*\/site-packages/);
  });
  it("exports NODE_PATH/PYTHONPATH at /deps and resets the nixpacks ENTRYPOINT", () => {
    expect(overlay).toMatch(/ENV NODE_PATH=\/deps\/node_modules/);
    expect(overlay).toMatch(/ENV PYTHONPATH=\/deps\/site-packages/);
    // Reset so the sandbox `sleep infinity` keepalive runs as a plain command.
    expect(overlay).toMatch(/ENTRYPOINT \[\]/);
    expect(overlay).toMatch(/WORKDIR \/work\/repo/);
  });
});

// --------------------------------------------------------------------------
// PURE unit layer — injected deps, no real docker.
// --------------------------------------------------------------------------
describe("imageTag", () => {
  it("tags ca-sbx:<repo>-<dephash> from the repo dir basename", () => {
    expect(imageTag("/tmp/some/myrepo", "abc123def456")).toBe("ca-sbx:myrepo-abc123def456");
  });

  it("sanitizes a basename that is not docker-tag-safe", () => {
    const tag = imageTag("/tmp/My Repo!@#", "abc123def456");
    // docker tags allow [A-Za-z0-9_.-]; everything else folds away.
    expect(tag).toMatch(/^ca-sbx:[A-Za-z0-9_.-]+-abc123def456$/);
    expect(tag).not.toMatch(/[ !@#]/);
  });
});

describe("buildOrReuseImage — cache hit (AC-04)", () => {
  it("reuses an existing tag and performs NO build", async () => {
    let inspected: string | null = null;
    let buildCalls = 0;
    const deps: BuildDeps = {
      imageInspect: async (tag) => {
        inspected = tag;
        return 0; // exists
      },
      runBuild: async () => {
        buildCalls++;
        return { code: 0, out: "" };
      },
      nixpacksVersion: async () => "1.40.0",
      ensureNixpacks: async () => ({ available: true }),
    };
    const res = await buildOrReuseImage("/tmp/myrepo", "deadbeef0000", deps);
    expect(res.reused).toBe(true);
    expect(res.built).toBe(false);
    expect(buildCalls).toBe(0);
    expect(res.tag).toBe("ca-sbx:myrepo-deadbeef0000");
    expect(inspected).toBe("ca-sbx:myrepo-deadbeef0000");
  });
});

describe("buildOrReuseImage — cache miss builds (AC-05)", () => {
  it("builds when the tag does not exist", async () => {
    let buildCalls = 0;
    let builtTag: string | null = null;
    const deps: BuildDeps = {
      imageInspect: async () => 1, // missing
      runBuild: async (tag) => {
        buildCalls++;
        builtTag = tag;
        return { code: 0, out: "built" };
      },
      nixpacksVersion: async () => "1.40.0",
      ensureNixpacks: async () => ({ available: true }),
    };
    const res = await buildOrReuseImage("/tmp/myrepo", "feed0000face", deps);
    expect(res.built).toBe(true);
    expect(res.reused).toBe(false);
    expect(buildCalls).toBe(1);
    expect(builtTag).toBe("ca-sbx:myrepo-feed0000face");
  });

  it("propagates a build failure", async () => {
    const deps: BuildDeps = {
      imageInspect: async () => 1,
      runBuild: async () => ({ code: 7, out: "nixpacks blew up" }),
      nixpacksVersion: async () => "1.40.0",
      ensureNixpacks: async () => ({ available: true }),
    };
    await expect(buildOrReuseImage("/tmp/myrepo", "abcabcabcabc", deps)).rejects.toThrow(
      /build failed/i,
    );
  });

  it("records the generated-Dockerfile fallback note when nixpacks is unavailable", async () => {
    let usedFallback = false;
    const deps: BuildDeps = {
      imageInspect: async () => 1,
      runBuild: async (_tag, ctx) => {
        usedFallback = ctx.builder === "dockerfile-fallback";
        return { code: 0, out: "" };
      },
      nixpacksVersion: async () => {
        throw new Error("nixpacks: command not found");
      },
      ensureNixpacks: async () => ({
        available: false,
        note: "nixpacks not installed and its install script was blocked",
      }),
    };
    const res = await buildOrReuseImage("/tmp/myrepo", "0a0a0a0a0a0a", deps);
    expect(res.built).toBe(true);
    expect(usedFallback).toBe(true);
    expect(res.builder).toBe("dockerfile-fallback");
    expect(res.notes.join(" ")).toMatch(/nixpacks/i);
  });

  it("uses nixpacks when it is available", async () => {
    let builder: string | null = null;
    const deps: BuildDeps = {
      imageInspect: async () => 1,
      runBuild: async (_tag, ctx) => {
        builder = ctx.builder;
        return { code: 0, out: "" };
      },
      nixpacksVersion: async () => "1.40.0",
      ensureNixpacks: async () => ({ available: true }),
    };
    const res = await buildOrReuseImage("/tmp/myrepo", "111111111111", deps);
    expect(builder).toBe("nixpacks");
    expect(res.builder).toBe("nixpacks");
  });
});

describe("dephash drives the tag — unchanged vs manifest-changed (AC-04/AC-05)", () => {
  it("unchanged manifest set -> same tag -> cache hit -> no build", async () => {
    const manifests = [
      { path: "package.json", bytes: '{"dependencies":{"lodash":"^4"}}' },
    ];
    const hash1 = computeDepHash(manifests, "1.40.0");
    const hash2 = computeDepHash(
      [{ path: "package.json", bytes: '{"dependencies":{"lodash":"^4"}}' }],
      "1.40.0",
    );
    expect(hash1).toBe(hash2);

    let builds = 0;
    const deps: BuildDeps = {
      imageInspect: async () => 0, // tag exists (first build cached it)
      runBuild: async () => {
        builds++;
        return { code: 0, out: "" };
      },
      nixpacksVersion: async () => "1.40.0",
      ensureNixpacks: async () => ({ available: true }),
    };
    const a = await buildOrReuseImage("/tmp/myrepo", hash1, deps);
    const b = await buildOrReuseImage("/tmp/myrepo", hash2, deps);
    expect(a.tag).toBe(b.tag);
    expect(builds).toBe(0);
  });

  it("manifest change -> different dephash -> different tag", () => {
    const a = computeDepHash([{ path: "package.json", bytes: '{"lodash":"^4"}' }], "1.40.0");
    const b = computeDepHash([{ path: "package.json", bytes: '{"lodash":"^5"}' }], "1.40.0");
    expect(a).not.toBe(b);
    expect(imageTag("/tmp/myrepo", a)).not.toBe(imageTag("/tmp/myrepo", b));
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-04 + AC-05 + the /deps relocation).
// Builds a real image; proves cache-hit = no build; manifest change = rebuild;
// baked deps resolve from /deps. Namespaced + cleaned up.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}

const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

d("buildOrReuseImage [docker] — real build, cache, rebuild (AC-04/AC-05)", () => {
  const created: string[] = []; // image tags to clean up
  let workdir: string;

  beforeAll(() => {
    workdir = mkdtempSync(path.join(tmpdir(), "ca-sbx-t05-"));
  });

  afterAll(() => {
    for (const tag of created) {
      spawnSync("docker", ["rmi", "-f", tag], { encoding: "utf8" });
    }
    if (workdir) rmSync(workdir, { recursive: true, force: true });
  });

  it("first build tags the image, unchanged rerun does NO build, manifest change rebuilds, deps resolve from /deps", async () => {
    // Tiny node fixture: depends on left-pad-shaped local logic via a dep.
    // Use a dependency-free package.json that still exercises the npm-install
    // phase and the /deps relocation (an empty deps tree still relocates cleanly).
    const repoDir = path.join(workdir, "t05node");
    mkdirSync(repoDir, { recursive: true });
    writeFileSync(
      path.join(repoDir, "package.json"),
      JSON.stringify({ name: "t05node", version: "1.0.0", dependencies: { "is-odd": "3.0.1" } }),
    );
    writeFileSync(
      path.join(repoDir, "index.js"),
      "const isOdd = require('is-odd'); console.log('T05_OK', isOdd(3));",
    );

    const manifests = [
      { path: "package.json", bytes: JSON.stringify({ name: "t05node", version: "1.0.0", dependencies: { "is-odd": "3.0.1" } }) },
    ];
    // Namespace the dephash with the task id so other tasks' images never collide.
    const hash1 = "t05" + computeDepHash(manifests, "fallback").slice(0, 9);

    const r1: BuildResult = await buildOrReuseImage(repoDir, hash1);
    created.push(r1.tag);
    expect(r1.tag).toBe(imageTag(repoDir, hash1));
    expect(r1.built).toBe(true);
    expect(r1.reused).toBe(false);

    // The image exists.
    const inspect1 = spawnSync("docker", ["image", "inspect", r1.tag], { encoding: "utf8" });
    expect(inspect1.status).toBe(0);

    // Deps relocated to /deps and NODE_PATH exported -> the app resolves is-odd.
    const runDeps = spawnSync(
      "docker",
      ["run", "--rm", "-w", "/work/repo", r1.tag, "node", "index.js"],
      { encoding: "utf8", env: { ...process.env, MSYS_NO_PATHCONV: "1" } },
    );
    expect(runDeps.stdout + runDeps.stderr).toMatch(/T05_OK/);

    // NODE_PATH points at /deps/node_modules.
    const envCheck = spawnSync("docker", ["run", "--rm", r1.tag, "sh", "-c", "echo $NODE_PATH"], {
      encoding: "utf8",
      env: { ...process.env, MSYS_NO_PATHCONV: "1" },
    });
    expect(envCheck.stdout).toMatch(/\/deps\/node_modules/);

    // Unchanged rerun: SAME tag, NO build.
    const r2 = await buildOrReuseImage(repoDir, hash1);
    expect(r2.tag).toBe(r1.tag);
    expect(r2.reused).toBe(true);
    expect(r2.built).toBe(false);

    // Manifest change -> different dephash -> different tag -> rebuild.
    const hash2 = "t05" + computeDepHash(
      [{ path: "package.json", bytes: JSON.stringify({ name: "t05node", dependencies: { "is-odd": "3.0.1", "is-even": "1.0.0" } }) }],
      "fallback",
    ).slice(0, 9);
    expect(hash2).not.toBe(hash1);
    const r3 = await buildOrReuseImage(repoDir, hash2);
    created.push(r3.tag);
    expect(r3.tag).not.toBe(r1.tag);
    expect(r3.built).toBe(true);
  }, 300_000);
});
