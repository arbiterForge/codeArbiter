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
import { destroySandbox, prune } from "./destroy.ts";
import { runCli, type Handlers } from "./cli.ts";
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

  const run: DockerRun = (args) => {
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
  it("complete success reports zero failures and nothing remaining", () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const res = destroySandbox("id1", { dockerRun: run });

    expect(res.removedContainers).toEqual(["c1"]);
    expect(res.removedVolumes).toEqual(["ca-sbx-vol-id1"]);
    expect(res.failures).toEqual([]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingContainers).toEqual([]);
    expect(res.remainingVolumes).toEqual([]);
  });

  it("a mixed run keeps the successes AND records the failure with its docker code", () => {
    const { run } = fakeDocker(
      { containers: ["c1"], volumes: ["ca-sbx-vol-id1"] },
      { failRemove: (kind) => (kind === "volume" ? 125 : undefined) },
    );
    const res = destroySandbox("id1", { dockerRun: run });

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

  it("keeps attempting EVERY discovered target after the first failure", () => {
    const { run, calls } = fakeDocker(
      { containers: ["c1", "c2", "c3"], volumes: ["v1", "v2"] },
      { failRemove: (_k, ref) => (ref === "c1" || ref === "v1" ? 125 : undefined) },
    );
    const res = destroySandbox("id1", { dockerRun: run });

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

  it("a dead daemon is a FAILURE, not an empty successful sweep", () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] }, { failList: true });
    const res = destroySandbox("id1", { dockerRun: run });

    expect(res.removedContainers).toEqual([]);
    expect(res.removedVolumes).toEqual([]);
    // Discovery itself failed — reporting "nothing to remove" would be a lie.
    expect(res.failureCount).toBeGreaterThan(0);
    expect(res.failures.map((f) => f.op)).toContain("list-containers");
    expect(res.failures.map((f) => f.op)).toContain("list-volumes");
    expect(res.failures[0].message).toContain("Cannot connect to the Docker daemon");
  });

  it("--keep-volume: the deliberately kept volume is NOT reported as remaining", () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["ca-sbx-vol-id1"] });
    const res = destroySandbox("id1", { keepVolume: true, dockerRun: run });

    expect(res.keptVolumes).toEqual(["ca-sbx-vol-id1"]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingVolumes).toEqual([]);
    expect(res.remainingContainers).toEqual([]);
  });

  it("the failure list is BOUNDED while the count stays truthful", () => {
    const many = Array.from({ length: 50 }, (_, i) => `c${i}`);
    const { run } = fakeDocker({ containers: many }, { failRemove: () => 125 });
    const res = destroySandbox("id1", { dockerRun: run });

    expect(res.failureCount).toBe(50);
    expect(res.failures.length).toBeGreaterThan(0);
    expect(res.failures.length).toBeLessThanOrEqual(25);
  });
});

// --------------------------------------------------------------------------
// prune
// --------------------------------------------------------------------------
describe("prune — a failed reclaim is retained, not dropped (#393)", () => {
  it("complete success reports zero failures and nothing remaining", () => {
    const { run } = fakeDocker({ containers: ["c1", "c2"], volumes: ["vol-leaked"] });
    const res = prune({ dockerRun: run });

    expect(res.removedContainers).toEqual(["c1", "c2"]);
    expect(res.removedVolumes).toEqual(["vol-leaked"]);
    expect(res.failures).toEqual([]);
    expect(res.failureCount).toBe(0);
    expect(res.remainingContainers).toEqual([]);
    expect(res.remainingVolumes).toEqual([]);
  });

  it("a mixed run records the failure and names the object left behind", () => {
    const { run, calls } = fakeDocker(
      { containers: ["c1", "c2"], volumes: ["vol-leaked"] },
      { failRemove: (_k, ref) => (ref === "c2" ? 1 : undefined) },
    );
    const res = prune({ dockerRun: run });

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

  it("a dead daemon is a FAILURE, not an empty successful sweep", () => {
    const { run } = fakeDocker({ containers: ["c1"], volumes: ["v1"] }, { failList: true });
    const res = prune({ dockerRun: run });

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
    destroy: (id, opts) => destroySandbox(id, { keepVolume: opts.keepVolume, dockerRun: run }),
    prune: () => prune({ dockerRun: run }),
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
