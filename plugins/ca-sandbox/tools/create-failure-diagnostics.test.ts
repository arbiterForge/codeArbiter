import { beforeEach, describe, expect, it, vi } from "vitest";
import { existsSync } from "node:fs";
import type { BuildDeps } from "./build.ts";
const seam = vi.hoisted(() => ({ stage: vi.fn(), cleanup: vi.fn() }));
vi.mock("./docker.ts", async original => ({
  ...await original<typeof import("./docker.ts")>(),
  makeDockerRun: () => seam.stage,
  defaultDockerRun: seam.cleanup,
}));
import { createSandbox, CreateFailure } from "./create.ts";

const result = (code = 0, stdout = "") => ({ code, stdout, stderr: "" });
let stage: "helper" | "copy" | "build" | "success";
let cleanupUnknown: boolean;
const primary = new Error("primary builder failed");
const imageId = "sha256:" + "2".repeat(64);
const deps: BuildDeps = {
  imageInspect: async () => 1,
  imageIdentity: async tag => ({ id: imageId, cacheKey: tag.split("v2-")[1] }),
  targetPlatform: async () => "linux/amd64",
  detectStack: async () => ({ node: true, python: false }),
  ensureNixpacks: async () => ({ available: true, version: "1.41.0" }),
  nixpacksVersion: async () => "1.41.0",
  runBuild: async () => { if (stage === "build") throw primary; return { code: 0, out: "", imageId }; },
};
async function exercise(): Promise<CreateFailure> {
  return await createSandbox("https://example.test/repo.git", {
    id: "failure-fixture", cloneRepo: async () => 0, buildDeps: deps,
    dockerRun: async () => result(),
  }).then(() => { throw new Error("expected failed create"); }, error => error);
}
beforeEach(() => {
  vi.clearAllMocks(); cleanupUnknown = true;
  seam.stage.mockImplementation(async (args: string[]) => result(
    (args[0] === "create" && stage === "helper") ? 61 :
    (args[0] === "cp" && stage === "copy") ? 62 : 0));
  seam.cleanup.mockImplementation(async (args: string[]) => result(cleanupUnknown ? 73 : 0));
});

describe("default build primary and staging cleanup diagnostics", () => {
  it.each([
    ["helper", "helper creation unavailable (exit 61)"],
    ["copy", "checkout materialization unavailable (exit 62)"],
    ["build", "primary builder failed"],
  ] as const)("retains %s failure when independent staging cleanup is unknown", async (selected, expected) => {
    stage = selected;
    const error = await exercise();
    expect(error).toBeInstanceOf(CreateFailure);
    expect(error.message).toContain(expected);
    expect(error.message).toContain("build staging cleanup unknown");
    expect(error.cleanup.verified).toBe(true); // Separate outer sandbox absence observation.
    expect(error.cause).toMatchObject({
      name: "BuildStagingFailure", primaryFailure: expect.any(Error),
      cleanup: { helper: expect.stringMatching(/^ca-sbx-cp-/), removeCode: selected === "helper" ? 1 : 73,
        observationCode: 73, stagingRemoved: true },
    });
    const failure = error.cause as Error & { primaryFailure: Error; cleanup: { helper: string; staging: string } };
    expect(failure.primaryFailure.message).toContain(expected);
    if (selected === "build") expect(failure.primaryFailure).toBe(primary);
    expect(existsSync(failure.cleanup.staging)).toBe(false);
    expect(seam.cleanup.mock.calls.some(([args]) => args.includes(`name=^/${failure.cleanup.helper}$`))).toBe(true);
    expect(seam.cleanup.mock.calls.every(([, options]) => options === undefined)).toBe(true);
  });
  it("keeps the primary failure when helper absence is verified", async () => {
    stage = "build"; cleanupUnknown = false;
    const error = await exercise();
    expect(error.message).toContain(primary.message);
    expect(error.message).not.toContain("build staging cleanup unknown");
    expect(error.cause).toBe(primary);
  });
  it("retains cleanup-only failure without inventing a primary error", async () => {
    stage = "success";
    const error = await exercise();
    expect(error.message).toContain("build staging cleanup unknown");
    expect(error.cause).toMatchObject({ name: "BuildStagingFailure", primaryFailure: undefined,
      cleanup: { observationCode: 73, stagingRemoved: true } });
    expect(error.message).not.toContain(primary.message);
  });
});
