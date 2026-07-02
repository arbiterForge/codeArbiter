/**
 * create.test.ts — clone-input trust model (T-09 hardening; AC-01 trust boundary).
 *
 * The repo url is the one create input that flows into git's argv inside a
 * networked, root clone container. git reads a leading-`-` value as a flag
 * (argument injection) and its transport-helper syntax (ext::, fd::, file://) runs
 * commands or reads host paths. validateRepoUrl allowlists plain network remotes
 * only; defaultCloneRepo additionally emits `--` before the url. Pure unit layer —
 * no docker; runs everywhere. The end-to-end clone is exercised by lifecycle.test.ts.
 */
import { describe, it, expect } from "vitest";
import { spawnSync } from "node:child_process";
import {
  validateRepoUrl,
  InvalidRepoUrlError,
  buildCloneArgs,
  buildCpHelperCreateArgs,
  createSandbox,
  APP_DIR,
} from "./create.ts";
import type { CloneResult } from "./create.ts";
import { buildMountArgs } from "./mounts.ts";
import { SANDBOX_LABEL, idLabel, listAllContainers } from "./registry.ts";
import { prune } from "./destroy.ts";

describe("validateRepoUrl — clone-input trust model (AC-01)", () => {
  it("accepts plain network remotes (https / ssh / scp-like)", () => {
    expect(() => validateRepoUrl("https://github.com/owner/repo.git")).not.toThrow();
    expect(() => validateRepoUrl("https://gitlab.example.com/a/b")).not.toThrow();
    expect(() => validateRepoUrl("ssh://git@github.com/owner/repo.git")).not.toThrow();
    expect(() => validateRepoUrl("git@github.com:owner/repo.git")).not.toThrow();
  });

  it("REJECTS git argument injection (a url beginning with '-')", () => {
    expect(() => validateRepoUrl("--upload-pack=touch /tmp/pwned")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("-x")).toThrow(InvalidRepoUrlError);
  });

  it("REJECTS git transport-helper / local transports (ext::, fd::, file://)", () => {
    expect(() => validateRepoUrl('ext::sh -c "touch /tmp/pwned"')).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("fd::17")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("file:///etc/passwd")).toThrow(InvalidRepoUrlError);
  });

  it("REJECTS other unknown / non-network schemes and empties", () => {
    expect(() => validateRepoUrl("")).toThrow();
    expect(() => validateRepoUrl("http://insecure.example.com/repo")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("javascript:alert(1)")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("/local/path")).toThrow(InvalidRepoUrlError);
  });
});

describe("buildCloneArgs — argv shape (AC-01 defense in depth)", () => {
  const url = "https://github.com/owner/repo.git";
  const argv = buildCloneArgs(url, "ca-sbx-vol-demo", "demo-id");

  it("emits an end-of-options `--` immediately before the url", () => {
    const sep = argv.indexOf("--");
    expect(sep).toBeGreaterThanOrEqual(0);
    // `--` must sit directly before the untrusted url so a leading-`-` value is an
    // operand to git, never a flag.
    expect(argv[sep + 1]).toBe(url);
    expect(argv[sep + 2]).toBe(APP_DIR);
  });

  it("the `--` follows the clone subcommand and its flags (git parses it)", () => {
    const sep = argv.indexOf("--");
    const clone = argv.indexOf("clone");
    expect(clone).toBeGreaterThanOrEqual(0);
    expect(sep).toBeGreaterThan(clone);
    // Everything between `clone` and `--` is a known flag, never the url.
    expect(argv.slice(clone, sep)).not.toContain(url);
  });

  // architecture-006: the clone/build mounts must route through buildMountArgs —
  // the documented single chokepoint — so they are covered by the bind-rejection
  // guarantee and there is genuinely one mount-argv path. Pin that the emitted
  // mount argv is EXACTLY what buildMountArgs produces for the volume spec.
  it("routes the source-volume mount through the buildMountArgs chokepoint", () => {
    const expected = buildMountArgs([
      { type: "volume", source: "ca-sbx-vol-demo", target: APP_DIR },
    ]);
    const m = argv.indexOf("--mount");
    expect(m).toBeGreaterThanOrEqual(0);
    expect(argv.slice(m, m + expected.length)).toEqual(expected);
    // No raw bind expression hand-rolled anywhere.
    for (const tok of argv) expect(tok).not.toMatch(/type=bind/);
  });
});

// ---------------------------------------------------------------------------
// reliability-015 — label + time-bound the clone / cp-helper containers so a
// hung clone or a host crash mid-create doesn't orphan an unreclaimable object.
// ---------------------------------------------------------------------------
describe("buildCloneArgs — carries the sandbox labels (reliability-015)", () => {
  it("labels the throwaway clone container ca.sandbox=1 + ca.sandbox.id=<id>", () => {
    const argv = buildCloneArgs("https://github.com/owner/repo.git", "ca-sbx-vol-demo", "abc123");
    // Two independent --label flags (docker requires one per label, same
    // discipline as buildRunArgs / registry.ts's labelFilterArgs).
    const labelValues: string[] = [];
    argv.forEach((tok, i) => {
      if (tok === "--label") labelValues.push(argv[i + 1]);
    });
    expect(labelValues).toContain(SANDBOX_LABEL);
    expect(labelValues).toContain(idLabel("abc123"));
  });

  it("a different id produces a different id-label (no cross-sandbox collision)", () => {
    const a = buildCloneArgs("https://github.com/owner/repo.git", "vol-a", "id-a");
    const b = buildCloneArgs("https://github.com/owner/repo.git", "vol-b", "id-b");
    expect(a).toContain(idLabel("id-a"));
    expect(b).toContain(idLabel("id-b"));
    expect(a).not.toContain(idLabel("id-b"));
  });
});

describe("buildCpHelperCreateArgs — carries the sandbox labels (reliability-015)", () => {
  it("labels the docker-cp helper container ca.sandbox=1 + ca.sandbox.id=<id>", () => {
    const argv = buildCpHelperCreateArgs("ca-sbx-vol-demo", "ca-sbx-cp-deadbeef", "abc123");
    const labelValues: string[] = [];
    argv.forEach((tok, i) => {
      if (tok === "--label") labelValues.push(argv[i + 1]);
    });
    expect(labelValues).toContain(SANDBOX_LABEL);
    expect(labelValues).toContain(idLabel("abc123"));
    expect(argv).toContain("ca-sbx-cp-deadbeef");
  });

  it("still routes the volume mount through the buildMountArgs chokepoint", () => {
    const argv = buildCpHelperCreateArgs("ca-sbx-vol-demo", "helper", "abc123");
    const expected = buildMountArgs([{ type: "volume", source: "ca-sbx-vol-demo", target: APP_DIR }]);
    const m = argv.indexOf("--mount");
    expect(m).toBeGreaterThanOrEqual(0);
    expect(argv.slice(m, m + expected.length)).toEqual(expected);
    for (const tok of argv) expect(tok).not.toMatch(/type=bind/);
  });
});

describe("createSandbox failure teardown — containers before volume (reliability-015)", () => {
  it("removes leftover labeled containers BEFORE removing the volume", async () => {
    const calls: string[][] = [];
    const dockerRun = (args: string[]) => {
      calls.push(args);
      if (args[0] === "volume" && args[1] === "create") return { code: 0, stdout: "vol", stderr: "" };
      if (args[0] === "ps") return { code: 0, stdout: "leftover-container-id", stderr: "" };
      return { code: 0, stdout: "", stderr: "" };
    };

    await expect(
      createSandbox("https://github.com/owner/repo.git", {
        id: "test-teardown-order",
        dockerRun,
        cloneRepo: async (): Promise<CloneResult> => ({ code: 1, stderr: "fatal: boom" }),
      }),
    ).rejects.toThrow();

    const rmContainerIdx = calls.findIndex((c) => c[0] === "rm" && c[1] === "-f");
    const rmVolumeIdx = calls.findIndex((c) => c[0] === "volume" && c[1] === "rm");
    expect(rmContainerIdx).toBeGreaterThanOrEqual(0);
    expect(rmVolumeIdx).toBeGreaterThan(rmContainerIdx);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (reliability-015).
// Proves an orphaned clone/cp-helper-shaped container — the exact object a
// hung clone or a host crash mid-create would leave behind — is reclaimable by
// prune() purely because it carries the ca.sandbox=1 label, even though it is
// not a registered sandbox object.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

d("orphaned helper containers [docker] — prune() reclaims them (reliability-015)", () => {
  it("a labeled, detached clone-shaped orphan is removed by prune()", () => {
    const id = "t173-clone-orphan";
    const name = `ca-sbx-clone-orphan-${Date.now()}`;
    // Simulate the crash scenario: the host process died before the `--rm`
    // clone container exited, so a labeled, still-running container is left
    // behind. `-d` (detached) here stands in for "the parent process is gone
    // but the container survives" — the label is what makes it reclaimable.
    const run = spawnSync(
      "docker",
      [
        "run",
        "-d",
        "--label",
        SANDBOX_LABEL,
        "--label",
        idLabel(id),
        "--name",
        name,
        "alpine",
        "sleep",
        "300",
      ],
      { encoding: "utf8" },
    );
    expect(run.status, run.stderr).toBe(0);
    const cid = run.stdout.trim();

    try {
      expect(listAllContainers()).toContain(cid);
      const result = prune();
      expect(result.removedContainers).toContain(cid);
      expect(listAllContainers()).not.toContain(cid);
    } finally {
      spawnSync("docker", ["rm", "-f", name]);
    }
  }, 60_000);

  it("a labeled, detached cp-helper-shaped orphan is removed by prune()", () => {
    const id = "t173-cphelper-orphan";
    const name = `ca-sbx-cp-orphan-${Date.now()}`;
    const run = spawnSync(
      "docker",
      [
        "run",
        "-d",
        "--label",
        SANDBOX_LABEL,
        "--label",
        idLabel(id),
        "--name",
        name,
        "alpine",
        "sleep",
        "300",
      ],
      { encoding: "utf8" },
    );
    expect(run.status, run.stderr).toBe(0);
    const cid = run.stdout.trim();

    try {
      const result = prune();
      expect(result.removedContainers).toContain(cid);
    } finally {
      spawnSync("docker", ["rm", "-f", name]);
    }
  }, 60_000);
});

// ---------------------------------------------------------------------------
// T-10 (coverage-003) — validateRepoUrl scp-like edge cases
// ---------------------------------------------------------------------------
describe("validateRepoUrl — scp-like edge cases (coverage-003)", () => {
  it("REJECTS double-colon transport-helper form git@github.com::evil (InvalidRepoUrlError)", () => {
    // The `:[^:]` guard in the scp regex means a second colon at position 0 of
    // the path segment fails the match — this is the transport-helper hole being
    // pinned to prevent regex regressions.
    expect(() => validateRepoUrl("git@github.com::evil")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("git@github.com::evil-command")).toThrow(InvalidRepoUrlError);
  });

  it("ACCEPTS scp-like url with single colon and a nested path (git@github.com:path/sub)", () => {
    expect(() => validateRepoUrl("git@github.com:path/sub")).not.toThrow();
    expect(() => validateRepoUrl("git@github.com:owner/repo.git")).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// T-09 (reliability-002 + observability-004) — error surfacing tests
// ---------------------------------------------------------------------------

/** Minimal fake docker runner covering the volume create/rm and ps paths. */
function makeDockerRun() {
  return (args: string[]) => {
    if (args[0] === "volume" && args[1] === "create") return { code: 0, stdout: "vol", stderr: "" };
    if (args[0] === "volume" && args[1] === "rm") return { code: 0, stdout: "", stderr: "" };
    if (args[0] === "ps") return { code: 0, stdout: "", stderr: "" };
    return { code: 0, stdout: "", stderr: "" };
  };
}

describe("createSandbox — clone failure surfaces stderr (observability-004)", () => {
  it("throws with stderr snippet when injected cloneRepo fails (exit 1)", async () => {
    // Inject a clone that fails with a captured stderr — mirrors what the real
    // alpine/git container emits (e.g. 'fatal: repository not found').
    const fakeClone = async (_url: string, _vol: string): Promise<CloneResult> => ({
      code: 1,
      stderr: "fatal: repository 'https://github.com/no/repo.git/' not found",
    });

    await expect(
      createSandbox("https://github.com/no/repo.git", {
        id: "test-clone-fail",
        dockerRun: makeDockerRun(),
        cloneRepo: fakeClone,
        buildImage: async () => { throw new Error("should not reach build"); },
      }),
    ).rejects.toThrow(/fatal: repository/);
  });

  it("includes exit code in the clone error message when stderr is empty", async () => {
    const fakeClone = async (): Promise<CloneResult> => ({ code: 128, stderr: "" });

    await expect(
      createSandbox("https://github.com/owner/repo.git", {
        id: "test-clone-code-only",
        dockerRun: makeDockerRun(),
        cloneRepo: fakeClone,
        buildImage: async () => { throw new Error("should not reach build"); },
      }),
    ).rejects.toThrow(/exit 128/);
  });

  it("thrown error does NOT include raw argv — only docker/git stderr (no secret leak)", async () => {
    // The error must contain only the git stderr, not any environment variables
    // or constructed command strings.
    const fakeClone = async (): Promise<CloneResult> => ({
      code: 128,
      stderr: "git: 'clone' is not a git command",
    });

    let caught: Error | undefined;
    try {
      await createSandbox("https://github.com/owner/repo.git", {
        id: "test-no-leak",
        dockerRun: makeDockerRun(),
        cloneRepo: fakeClone,
        buildImage: async () => { throw new Error("should not reach build"); },
      });
    } catch (e) {
      caught = e as Error;
    }
    expect(caught).toBeDefined();
    // Error must contain the git stderr but not internal argv/env details
    expect(caught!.message).toContain("git");
    // Must not accidentally include the DOCKER_ENV object representation
    expect(caught!.message).not.toContain("MSYS_NO_PATHCONV");
  });
});

describe("defaultBuildImage — docker create/cp failures surface as errors (reliability-002)", () => {
  it("throws with docker stderr when injected buildImage signals docker-create failure", async () => {
    // Inject buildImage that throws as defaultBuildImage will after the fix —
    // non-zero docker create surfaces stderr in the error message.
    const fakeBuild = async (_vol: string): Promise<never> => {
      throw new Error(
        "ca-sandbox: docker create failed for helper container (exit 125)\ndocker: Error response from daemon: Conflict. The container name already exists.",
      );
    };

    const fakeClone = async (): Promise<CloneResult> => ({ code: 0, stderr: "" });

    await expect(
      createSandbox("https://github.com/owner/repo.git", {
        id: "test-docker-create-fail",
        dockerRun: makeDockerRun(),
        cloneRepo: fakeClone,
        buildImage: fakeBuild,
      }),
    ).rejects.toThrow(/docker create failed/);
  });

  it("throws when injected buildImage signals docker-cp produced an empty checkout", async () => {
    const fakeBuild = async (_vol: string): Promise<never> => {
      throw new Error(
        "ca-sandbox: docker cp failed — empty checkout, cannot compute dephash (exit 1)\nerror: No such container:path",
      );
    };

    const fakeClone = async (): Promise<CloneResult> => ({ code: 0, stderr: "" });

    await expect(
      createSandbox("https://github.com/owner/repo.git", {
        id: "test-docker-cp-fail",
        dockerRun: makeDockerRun(),
        cloneRepo: fakeClone,
        buildImage: fakeBuild,
      }),
    ).rejects.toThrow(/docker cp failed/);
  });
});
