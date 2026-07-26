/**
 * teardown.test.ts — #393. Teardown failures must be SURFACED and must FAIL.
 *
 * `destroySandbox` and `prune` used to write `if (r.code === 0) removed.push(x)`
 * and drop every non-zero docker result on the floor: the result objects carried
 * no failure field at all, and the CLI returned 0 unconditionally. A daemon
 * outage, a permissions failure, or an in-use object therefore left UNTRUSTED
 * sandbox containers and source volumes running while automation saw exit 0 —
 * the advertised teardown guarantee was false exactly on the path where it
 * matters.
 *
 * The obligations locked in here:
 *   1. every failed removal is retained in a BOUNDED failure list;
 *   2. teardown keeps attempting every discovered target after a failure
 *      (partial teardown must still remove what it can);
 *   3. a final label-scoped verification re-lists the scope and reports whatever
 *      is still present (a kept volume is expected, not "remaining");
 *   4. a discovery/verification docker failure is itself a teardown failure —
 *      "listed nothing while the daemon was down" must never read as success;
 *   5. `sandbox destroy` / `sandbox prune` exit NON-ZERO whenever any removal
 *      failed or any target remains, with a diagnostic that NAMES what was left
 *      behind so an operator can clean up.
 *
 * Everything here runs on an injected docker runner — no real docker. The fake
 * is STATEFUL (a successful `rm` really removes the object from later label
 * listings) so the post-teardown verification is exercised honestly rather than
 * against a listing frozen in time.
 */
import { describe, it, expect, vi } from "vitest";
import {
  MAX_DIAGNOSTIC_REFS,
  MAX_TEARDOWN_FAILURES,
  destroySandbox,
  formatTeardownDiagnostic,
  prune,
  teardownIncomplete,
} from "./destroy.ts";
import { TEARDOWN_FAILURE_EXIT, USAGE_ERROR_EXIT, runCli, type Handlers } from "./cli.ts";
import type { DockerRun } from "./registry.ts";

// --------------------------------------------------------------------------
// a stateful fake docker: listings reflect what has actually been removed
// --------------------------------------------------------------------------
type FakeOpts = {
  /** Return a non-zero exit code to make THIS removal fail. */
  failRemove?: (kind: "container" | "volume", ref: string) => number | undefined;
  /** Simulate a dead daemon: every label listing fails. */
  failList?: boolean;
};

function fakeDocker(
  world: { containers?: string[]; volumes?: string[] },
  opts: FakeOpts = {},
): { run: DockerRun; calls: string[][]; containers: string[]; volumes: string[] } {
  const calls: string[][] = [];
  const containers = [...(world.containers ?? [])];
  const volumes = [...(world.volumes ?? [])];
  const lines = (xs: string[]) => (xs.length ? `${xs.join("\n")}\n` : "");
  const DEAD = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock";

  const run: DockerRun = async (args) => {
    calls.push(args);
    if (args[0] === "ps") {
      if (opts.failList) return { code: 1, stdout: "", stderr: DEAD };
      return { code: 0, stdout: lines(containers), stderr: "" };
    }
    if (args[0] === "volume" && args[1] === "ls") {
      if (opts.failList) return { code: 1, stdout: "", stderr: DEAD };
      return { code: 0, stdout: lines(volumes), stderr: "" };
    }
    if (args[0] === "rm") {
      const ref = args[args.length - 1];
      const code = opts.failRemove?.("container", ref);
      if (code) return { code, stdout: "", stderr: `Error response from daemon: cannot remove container ${ref}` };
      const i = containers.indexOf(ref);
      if (i >= 0) containers.splice(i, 1);
      return { code: 0, stdout: "", stderr: "" };
    }
    if (args[0] === "volume" && args[1] === "rm") {
      const ref = args[args.length - 1];
      const code = opts.failRemove?.("volume", ref);
      if (code) return { code, stdout: "", stderr: `Error response from daemon: volume ${ref} is in use` };
      const i = volumes.indexOf(ref);
      if (i >= 0) volumes.splice(i, 1);
      return { code: 0, stdout: "", stderr: "" };
    }
    return { code: 0, stdout: "", stderr: "" };
  };
  return { run, calls, containers, volumes };
}

/** The refs a removal was ATTEMPTED against, in call order. */
const removalTargets = (calls: string[][]): string[] =>
  calls
    .filter((a) => a[0] === "rm" || (a[0] === "volume" && a[1] === "rm"))
    .map((a) => a[a.length - 1]);

// --------------------------------------------------------------------------
// destroySandbox
// --------------------------------------------------------------------------
describe("destroySandbox — a failed removal is retained, not dropped (#393)", () => {
  it("complete success reports zero failures and nothing remaining", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const res = await destroySandbox("id1", { dockerRun: run });

    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual(["ca-sbx-vol-id1"]);
    expect(res.failures).toEqual([]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingContainers).toEqual([]);
    expect(res.remainingVolumes).toEqual([]);
  });

  it("a mixed run keeps the successes AND records the failure with its docker code", async () => {
    const { run } = fakeDocker(
      { containers: ["c1"], volumes: ["ca-sbx-vol-id1"] },
      { failRemove: (kind) => (kind === "volume" ? 125 : undefined) },
    );
    const res = await destroySandbox("id1", { dockerRun: run });

    // The container really went; the volume did not.
    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual([]);

    expect(res.failureCount).toBe(1);
    expect(res.failures).toHaveLength(1);
    expect(res.failures[0].op).toBe("remove-volume");
    expect(res.failures[0].ref).toBe("ca-sbx-vol-id1");
    expect(res.failures[0].code).toBe(125);
    expect(res.failures[0].message).toContain("in use");

    // And the post-teardown verification names what was LEFT BEHIND.
    expect(res.remainingContainers).toEqual([]);
    expect(res.remainingVolumes).toEqual(["ca-sbx-vol-id1"]);
  });

  it("keeps attempting EVERY discovered target after the first failure", async () => {
    const { run, calls } = fakeDocker(
      { containers: ["c1", "c2", "c3"], volumes: ["v1", "v2"] },
      { failRemove: (_k, ref) => (ref === "c1" || ref === "v1" ? 125 : undefined) },
    );
    const res = await destroySandbox("id1", { dockerRun: run });

    // Partial teardown still removed what it could...
    expect(res.removedContainers).toEqual(["c2", "c3"]);
    expect(res.removedVolumes).toEqual(["v2"]);
    // ...and no target was skipped because an earlier one failed.
    expect(removalTargets(calls)).toEqual(["c1", "c2", "c3", "v1", "v2"]);

    expect(res.failureCount).toBe(2);
    expect(res.failures.map((f) => f.ref)).toEqual(["c1", "v1"]);
    expect(res.remainingContainers).toEqual(["c1"]);
    expect(res.remainingVolumes).toEqual(["v1"]);
  });

  it("a dead daemon is a FAILURE, not an empty successful sweep", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] }, { failList: true });
    const res = await destroySandbox("id1", { dockerRun: run });

    expect(res.removedContainers).toEqual([]);
    expect(res.removedVolumes).toEqual([]);
    // Discovery itself failed — reporting "nothing to remove" would be a lie.
    expect(res.failureCount).toBeGreaterThan(0);
    // #433 narrowed this from "both list-containers AND list-volumes appear".
    // That assertion pinned the duplication #433 filed as the defect: one
    // unreachable daemon reported four times. The obligation this test exists
    // for is that a failed discovery is RECORDED rather than swallowed, and
    // that the operator is told what is wrong — both still asserted, once.
    expect(res.failures.map((f) => f.op)).toContain("list-containers");
    expect(res.failures[0].message).toContain("Cannot connect to the Docker daemon");
  });

  it("--keep-volume: the deliberately kept volume is NOT reported as remaining", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const res = await destroySandbox("id1", { keepVolume: true, dockerRun: run });

    expect(res.keptVolumes).toEqual(["ca-sbx-vol-id1"]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingVolumes).toEqual([]);
    expect(res.remainingContainers).toEqual([]);
  });

  it("the failure list is BOUNDED while the count stays truthful", async () => {
    const many = Array.from({ length: 50 }, (_, i) => `c${i}`);
    const { run } = fakeDocker({ containers: many }, { failRemove: () => 125 });
    const res = await destroySandbox("id1", { dockerRun: run });

    expect(res.failureCount).toBe(50);
    expect(res.failures.length).toBeGreaterThan(0);
    expect(res.failures.length).toBeLessThanOrEqual(25);
  });
});

// --------------------------------------------------------------------------
// prune
// --------------------------------------------------------------------------
describe("prune — a failed reclaim is retained, not dropped (#393)", () => {
  it("complete success reports zero failures and nothing remaining", async () => {
    const { run } = fakeDocker({ containers: ["c1", "c2"], volumes: ["vol-leaked"] });
    const res = await prune({ dockerRun: run });

    expect(res.removedContainers).toEqual(["c1", "c2"]);
    expect(res.removedVolumes).toEqual(["vol-leaked"]);
    expect(res.failures).toEqual([]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingContainers).toEqual([]);
    expect(res.remainingVolumes).toEqual([]);
  });

  it("a mixed run records the failure and names the object left behind", async () => {
    const { run, calls } = fakeDocker(
      { containers: ["c1", "c2"], volumes: ["vol-leaked"] },
      { failRemove: (_k, ref) => (ref === "c2" ? 1 : undefined) },
    );
    const res = await prune({ dockerRun: run });

    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual(["vol-leaked"]);
    // c2's failure did not abort the sweep of the volumes.
    expect(removalTargets(calls)).toEqual(["c1", "c2", "vol-leaked"]);

    expect(res.failureCount).toBe(1);
    expect(res.failures[0].op).toBe("remove-container");
    expect(res.failures[0].ref).toBe("c2");
    expect(res.failures[0].code).toBe(1);
    expect(res.remainingContainers).toEqual(["c2"]);
    expect(res.remainingVolumes).toEqual([]);
  });

  it("a dead daemon is a FAILURE, not an empty successful sweep", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] }, { failList: true });
    const res = await prune({ dockerRun: run });

    expect(res.removedContainers).toEqual([]);
    expect(res.failureCount).toBeGreaterThan(0);
    expect(res.failures.map((f) => f.op)).toContain("list-containers");
  });
});

// --------------------------------------------------------------------------
// the CLI exit code — the part automation actually reads
// --------------------------------------------------------------------------
function handlersOver(run: DockerRun): Handlers {
  return {
    create: async () => {
      throw new Error("not used");
    },
    destroy: async (id, opts) => await destroySandbox(id, { keepVolume: opts.keepVolume, dockerRun: run }),
    prune: async () => await prune({ dockerRun: run }),
    exec: () => {
      throw new Error("not used");
    },
    cp: () => {
      throw new Error("not used");
    },
    shell: () => {
      throw new Error("not used");
    },
  };
}

/** Run the CLI with stdout/stderr captured. */
async function runCaptured(argv: string[], h: Handlers): Promise<{ code: number; out: string; err: string }> {
  let out = "";
  let err = "";
  const o = vi.spyOn(process.stdout, "write").mockImplementation((c: any) => {
    out += String(c);
    return true;
  });
  const e = vi.spyOn(process.stderr, "write").mockImplementation((c: any) => {
    err += String(c);
    return true;
  });
  try {
    const code = await runCli(argv, h);
    return { code, out, err };
  } finally {
    o.mockRestore();
    e.mockRestore();
  }
}

describe("runCli — teardown failure must not exit 0 (#393)", () => {
  it("`destroy` exits 0 and stays quiet on a clean teardown", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const { code, err } = await runCaptured(["destroy", "id1"], handlersOver(run));
    expect(code).toBe(0);
    expect(err).toBe("");
  });

  it("`destroy` exits NON-ZERO and names the object left behind", async () => {
    const { run } = fakeDocker(
      { containers: ["c1"], volumes: ["ca-sbx-vol-id1"] },
      { failRemove: (kind) => (kind === "volume" ? 125 : undefined) },
    );
    const { code, out, err } = await runCaptured(["destroy", "id1"], handlersOver(run));

    expect(code).not.toBe(0);
    // The diagnostic must name the leftover so an operator can clean up.
    expect(err).toContain("ca-sbx-vol-id1");
    expect(err).toMatch(/125/);
    // The machine-readable result still carries the structured failures.
    const parsed = JSON.parse(out.trim());
    expect(parsed.failureCount).toBe(1);
    expect(parsed.remainingVolumes).toEqual(["ca-sbx-vol-id1"]);
  });

  it("`destroy` on a dead daemon exits NON-ZERO", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] }, { failList: true });
    const { code, err } = await runCaptured(["destroy", "id1"], handlersOver(run));
    expect(code).not.toBe(0);
    expect(err).toContain("Cannot connect to the Docker daemon");
  });

  it("`destroy --keep-volume` still exits 0 — a kept volume is not a leak", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const { code } = await runCaptured(["destroy", "id1", "--keep-volume"], handlersOver(run));
    expect(code).toBe(0);
  });

  it("`prune` exits 0 on a clean sweep", async () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] });
    const { code, err } = await runCaptured(["prune"], handlersOver(run));
    expect(code).toBe(0);
    expect(err).toBe("");
  });

  it("`prune` exits NON-ZERO and names every object left behind", async () => {
    const { run } = fakeDocker(
      { containers: ["c1"], volumes: ["v1"] },
      { failRemove: () => 125 },
    );
    const { code, out, err } = await runCaptured(["prune"], handlersOver(run));

    expect(code).not.toBe(0);
    expect(err).toContain("c1");
    expect(err).toContain("v1");
    const parsed = JSON.parse(out.trim());
    expect(parsed.failureCount).toBe(2);
    expect(parsed.remainingContainers).toEqual(["c1"]);
    expect(parsed.remainingVolumes).toEqual(["v1"]);
  });

  it("`prune` on a dead daemon exits NON-ZERO", async () => {
    const { run } = fakeDocker({ containers: ["c1"] }, { failList: true });
    const { code } = await runCaptured(["prune"], handlersOver(run));
    expect(code).not.toBe(0);
  });
});

// --------------------------------------------------------------------------
// #433 — the diagnostics themselves, after the adversarial review of #429
// --------------------------------------------------------------------------
describe("#433 — teardown diagnostics say what actually happened", () => {
  it("AC-1: one unreachable daemon is ONE failure, not four", async () => {
    // Reproduced against the shipped artifact:
    //   DOCKER_HOST=tcp://127.0.0.1:1 node sandbox.js prune -> failureCount: 4
    // Discovery lists containers and volumes, then verifyScope re-lists the
    // SAME two scopes against the same dead daemon. Four identical
    // "error during ..." lines for one fact. An operator counting failures is
    // being told the damage is four times what it is.
    const { run } = fakeDocker({ containers: ["c1"] }, { failList: true });
    const report = await prune({ dockerRun: run });
    expect(report.failureCount).toBe(1);
    expect(report.failures).toHaveLength(1);
    expect(report.failures[0]!.message).toMatch(/Cannot connect to the Docker daemon/);
  });

  it("AC-1: a REAL dead daemon dedups, even though the two errors differ", async () => {
    // The synthetic fake above returns the identical string for both listings,
    // so it cannot catch this. Against a real dead daemon the two errors carry
    // DIFFERENT URLs, and a whole-message comparison collapses nothing:
    //   error during connect: Get "http://127.0.0.1:1/v1.54/containers/json?..."
    //   error during connect: Get "http://127.0.0.1:1/v1.54/volumes?..."
    // Verified against the shipped artifact with DOCKER_HOST=tcp://127.0.0.1:1,
    // which reported failureCount 4 before and 1 after.
    const message = (path: string) =>
      `error during connect: Get "http://127.0.0.1:1/v1.54/${path}": `
      + "dial tcp 127.0.0.1:1: connectex: No connection could be made because "
      + "the target machine actively refused it.";
    const run: DockerRun = async (args) => {
      if (args[0] === "ps") return { code: 1, stdout: "", stderr: message("containers/json?all=1") };
      if (args[0] === "volume" && args[1] === "ls") return { code: 1, stdout: "", stderr: message("volumes?filters=x") };
      return { code: 0, stdout: "", stderr: "" };
    };
    const report = await prune({ dockerRun: run });
    expect(report.failureCount).toBe(1);
  });

  it("AC-1: two listings failing DIFFERENTLY stay two failures", async () => {
    // The fingerprint must not become a blanket "all listing failures are one".
    const run: DockerRun = async (args) => {
      if (args[0] === "ps") return { code: 1, stdout: "", stderr: "permission denied while trying to connect" };
      if (args[0] === "volume" && args[1] === "ls") return { code: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" };
      return { code: 0, stdout: "", stderr: "" };
    };
    const report = await prune({ dockerRun: run });
    expect(report.failureCount).toBe(2);
  });

  it("AC-1: genuinely different failures are still counted separately", async () => {
    // Dedup must collapse REPEATS of one fact, never distinct facts. Two
    // containers that each refuse removal for their own reason are two
    // failures, and collapsing them would understate the damage.
    const { run } = fakeDocker(
      { containers: ["c1", "c2"] },
      { failRemove: (_kind, ref) => (ref === "c1" ? 125 : 126) },
    );
    const report = await prune({ dockerRun: run });
    expect(report.failureCount).toBe(2);
    expect(new Set(report.failures.map((f) => f.ref))).toEqual(new Set(["c1", "c2"]));
  });

  it("AC-2: a sandbox created AFTER discovery does not fail prune", async () => {
    // prune verified by re-listing the GLOBAL ca.sandbox=1 scope, so a box
    // another agent created mid-run landed in remainingContainers and produced
    // "These objects may be running UNTRUSTED code" for something prune never
    // targeted. It fails safe, but a scary false positive teaches operators to
    // ignore the signal - which defeats the point of #393.
    const containers = ["c1"];
    let listed = 0;
    const run: DockerRun = async (args) => {
      if (args[0] === "ps") {
        listed += 1;
        // The second listing is the post-sweep verification; by then another
        // process has created its own sandbox.
        const world = listed === 1 ? containers : ["someone-elses-box"];
        return { code: 0, stdout: world.map((c) => `${c}\n`).join(""), stderr: "" };
      }
      if (args[0] === "volume" && args[1] === "ls") return { code: 0, stdout: "", stderr: "" };
      return { code: 0, stdout: "", stderr: "" };
    };
    const report = await prune({ dockerRun: run });
    expect(report.removedContainers).toEqual(["c1"]);
    expect(report.remainingContainers).toEqual([]);
    expect(teardownIncomplete(report)).toBe(false);
  });

  it("AC-2: an object this invocation DID target and failed to remove is still reported", async () => {
    // The scoping must not become a blindfold. A container prune tried to
    // remove and could not is exactly what remainingContainers is for.
    const { run } = fakeDocker({ containers: ["c1"] }, { failRemove: () => 125 });
    const report = await prune({ dockerRun: run });
    expect(report.remainingContainers).toEqual(["c1"]);
    expect(teardownIncomplete(report)).toBe(true);
  });

  it("AC-3: the teardown exit code is pinned, and differs from the usage error", async () => {
    // Every existing assertion is `not.toBe(0)`, so this could regress to 2 -
    // colliding with the usage-error code that #429's comment explicitly says
    // it is distinct from - and the whole suite would stay green.
    expect(TEARDOWN_FAILURE_EXIT).toBe(1);
    expect(TEARDOWN_FAILURE_EXIT).not.toBe(USAGE_ERROR_EXIT);
    expect(USAGE_ERROR_EXIT).toBe(2);
  });

  it("AC-4: the RENDERED diagnostic elides an over-long failure list", async () => {
    // The bounded-failure test asserted only on the result object. The bound
    // that matters is the one on the string an operator actually reads.
    const many = Array.from({ length: MAX_TEARDOWN_FAILURES + 7 }, (_, i) => `c${i}`);
    const { run } = fakeDocker({ containers: many }, { failRemove: () => 125 });
    const report = await prune({ dockerRun: run });
    const text = formatTeardownDiagnostic("prune", report);
    expect(report.failureCount).toBe(many.length);
    expect(text).toMatch(/and 7 more failure\(s\) not shown/);
  });

  it("AC-4: the RENDERED diagnostic elides an over-long remaining list", async () => {
    const many = Array.from({ length: MAX_DIAGNOSTIC_REFS + 3 }, (_, i) => `c${i}`);
    const { run } = fakeDocker({ containers: many }, { failRemove: () => 125 });
    const report = await prune({ dockerRun: run });
    const text = formatTeardownDiagnostic("prune", report);
    expect(report.remainingContainers).toHaveLength(many.length);
    expect(text).toMatch(/and 3 more container\(s\)/);
  });

  it("AC-5: a deliberately kept volume is never reported as remaining", async () => {
    // If the DISCOVERY volume listing fails, keptVolumes is empty - but the
    // VERIFICATION listing can still succeed, and the volume the operator
    // explicitly asked to keep then falls through the filter and is named as a
    // leak. The exit is already non-zero from the listing failure, so there is
    // no false success; the diagnostic is just confusing at the worst moment.
    let volumeListings = 0;
    const run: DockerRun = async (args) => {
      if (args[0] === "ps") return { code: 0, stdout: "", stderr: "" };
      if (args[0] === "volume" && args[1] === "ls") {
        volumeListings += 1;
        // Discovery fails; verification succeeds and sees the kept volume.
        return volumeListings === 1
          ? { code: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" }
          : { code: 0, stdout: "ca-sbx-vol-id1\n", stderr: "" };
      }
      return { code: 0, stdout: "", stderr: "" };
    };
    const report = await destroySandbox("id1", { keepVolume: true, dockerRun: run });
    expect(report.remainingVolumes).toEqual([]);
    expect(report.keptVolumes).toEqual(["ca-sbx-vol-id1"]);
    // The listing failure is still a failure - this hides a confusing line, not
    // a real problem.
    expect(report.failureCount).toBeGreaterThan(0);
    expect(formatTeardownDiagnostic("destroy", report)).not.toContain("ca-sbx-vol-id1");
  });
});
