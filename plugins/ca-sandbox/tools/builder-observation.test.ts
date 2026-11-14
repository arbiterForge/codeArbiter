import { createHash } from "node:crypto";
import { expect, it, vi } from "vitest";
import { buildOrReuseImage, generateDockerfile, relocationOverlay, NIXPACKS_BUILD_PROFILE,
  type BuildDeps, type BuildContext, type EnsureNixpacksResult } from "./build.ts";

const installed: EnsureNixpacksResult = { available: true, version: "1.41.0", via: { via: "host" } };
function effects(initial: EnsureNixpacksResult, current: EnsureNixpacksResult) {
  let observed = initial;
  const runBuild = vi.fn(async (_tag: string, _ctx: BuildContext) => ({ code: 0, out: "built" }));
  const ensureNixpacks = vi.fn(async () => observed);
  const deps: BuildDeps = {
    imageInspect: async () => { observed = current; return 1; },
    targetPlatform: async () => "linux/amd64", detectStack: async () => ({ node: true, python: false }),
    ensureNixpacks, nixpacksVersion: async () => "1.41.0", runBuild,
  };
  return { deps, runBuild, ensureNixpacks };
}

it.each([
  ["version changed", installed, { ...installed, version: "1.42.0" }],
  ["builder disappeared", installed, { available: false }],
  ["version became malformed", installed, { ...installed, version: "not-a-version" }],
  ["invocation changed", installed, { ...installed, via: { via: "wsl", bin: "/reviewed/nixpacks" } }],
  ["preferred builder appeared", { available: false }, installed],
  ["WSL binary changed", { ...installed, via: { via: "wsl", bin: "/first/nixpacks", distro: "fixture" } },
    { ...installed, via: { via: "wsl", bin: "/second/nixpacks", distro: "fixture" } }],
  ["WSL distro changed", { ...installed, via: { via: "wsl", bin: "/first/nixpacks", distro: "first" } },
    { ...installed, via: { via: "wsl", bin: "/first/nixpacks", distro: "second" } }],
] as const)("SBX-D01 refuses %s after cache observation before a build effect", async (_name, initial, current) => {
  const { deps, runBuild } = effects(initial, current);
  await expect(buildOrReuseImage("/fixture", "fixture-manifests", deps)).rejects.toThrow(/builder.*changed|builder.*unavailable/i);
  expect(runBuild).not.toHaveBeenCalled();
});

it("SBX-D01 stable reobservation admits one build under the observed identity", async () => {
  const { deps, runBuild, ensureNixpacks } = effects(installed, { ...installed });
  const built = await buildOrReuseImage("/fixture", "fixture-manifests", deps);
  expect(built).toMatchObject({ built: true, reused: false, builder: "nixpacks" });
  expect(ensureNixpacks).toHaveBeenCalledTimes(2);
  expect(runBuild).toHaveBeenCalledTimes(1);
  expect(runBuild.mock.calls[0][1]).toMatchObject({ builder: "nixpacks", nixpacks: { via: "host" }, cacheKey: built.cacheKey });
});

it("SBX-C01 verified cache reuse needs no build-time capability after the initial observation", async () => {
  const { deps, runBuild, ensureNixpacks } = effects(installed, { available: false });
  const initialInspect = deps.imageInspect;
  deps.imageInspect = async tag => { await initialInspect(tag); return 0; };
  deps.imageIdentity = async tag => ({ id: `sha256:${"a".repeat(64)}`, cacheKey: tag.split(":v2-")[1] });
  const cached = await buildOrReuseImage("/fixture", "fixture-manifests", deps);
  expect(cached).toMatchObject({ reused: true, built: false });
  expect(runBuild).not.toHaveBeenCalled();
  expect(ensureNixpacks).toHaveBeenCalledTimes(1);
});

it("SBX-C01 a weaker profile2 provenance label is a non-destructive cache miss", async () => {
  const legacyProfile: Record<string, unknown> = { ...NIXPACKS_BUILD_PROFILE, schema: 2 };
  delete legacyProfile.builderObservationPolicy;
  const legacyKey = createHash("sha256").update(JSON.stringify({ schema: 2, manifests: "fixture-manifests",
    builder: "nixpacks", version: "1.41.0", platform: "linux/amd64", nixpacksProfile: legacyProfile,
    fallback: generateDockerfile({ node: true, python: true }), relocation: relocationOverlay(),
  })).digest("hex");
  const { deps, runBuild } = effects(installed, installed);
  deps.imageInspect = async () => 0;
  deps.imageIdentity = async () => ({ id: `sha256:${"a".repeat(64)}`, cacheKey: legacyKey });
  const built = await buildOrReuseImage("/fixture", "fixture-manifests", deps);
  expect(built).toMatchObject({ built: true, reused: false });
  expect(built.cacheKey).not.toBe(legacyKey);
  expect(runBuild).toHaveBeenCalledTimes(1);
  // The build interface has no remove/retag operation; the old image remains.
});

it("SBX-D01 legacy version resolver is freshly observed before the build", async () => {
  const { deps, runBuild } = effects({ available: true }, { available: true });
  deps.nixpacksVersion = vi.fn().mockResolvedValueOnce("1.41.0").mockResolvedValue("1.42.0");
  await expect(buildOrReuseImage("/fixture", "fixture-manifests", deps)).rejects.toThrow(/builder.*changed/i);
  expect(runBuild).not.toHaveBeenCalled();
});

it("SBX-D01 cancellation during reobservation admits no build", async () => {
  const { deps, runBuild } = effects(installed, installed);
  const signal = new AbortController();
  let probes = 0;
  deps.ensureNixpacks = async () => { if (++probes === 2) signal.abort(); return installed; };
  await expect(buildOrReuseImage("/fixture", "fixture-manifests", deps, undefined, signal.signal)).rejects.toThrow();
  expect(probes).toBe(2);
  expect(runBuild).not.toHaveBeenCalled();
});
