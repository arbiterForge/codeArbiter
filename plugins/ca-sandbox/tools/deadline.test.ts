/**
 * deadline.test.ts — #394. Every Docker invocation is bounded.
 *
 * The single Docker chokepoint called `spawnSync("docker", args, ...)` with NO
 * timeout, and `execInSandbox` widened only `maxBuffer` before synchronously
 * waiting. So an in-container `sleep infinity`, a wedged daemon, or a stalled
 * build had no deadline at all: the host process blocked until something
 * external killed it, and untrusted repository code could deterministically
 * wedge `sandbox exec`. ca-sandbox is the driver that clones UNTRUSTED
 * repositories into containers — a hang it cannot escape is a control failure,
 * not an inconvenience.
 *
 * Two halves are tested here, and they are genuinely different:
 *
 *   ARGV/CONTRACT (no daemon needed) — every operation has a finite, declared
 *   deadline; a timed-out run returns a TYPED result rather than a bare
 *   non-zero; and a `docker exec` timeout escalates, because killing the docker
 *   CLI does NOT stop the process it started inside the container.
 *
 *   REAL DAEMON (docker-gated, per #406's discipline) — a genuinely hung
 *   in-container command terminates within its deadline and leaves nothing
 *   running behind it. That is the assertion the argv tests cannot make.
 */
import { EventEmitter } from "node:events";
import type { spawn } from "node:child_process";
import { describe, it, expect } from "vitest";
import {
  DEFAULT_DOCKER_TIMEOUT_MS,
  DOCKER_OPERATION_TIMEOUTS_MS,
  DOCKER_ABORT_EXIT_CODE,
  DOCKER_TIMEOUT_EXIT_CODE,
  defaultDockerRun,
  makeDockerRun,
  type DockerRun,
  type RunResult,
} from "./docker.ts";
import { execInSandbox } from "./exec.ts";
import { dockerGate } from "./docker-gate.ts";

/**
 * A minimal async child double — the shape `docker.ts` actually consumes now
 * that the chokepoint spawns instead of spawnSync-ing (#479).
 *
 * The important detail is `kill`: a real SIGKILL surfaces as
 * `close(null, signal)`, and that is IDENTICAL whether the deadline fired, the
 * caller aborted, or the output cap tripped. That indistinguishability is the
 * whole reason the runner records which killer fired instead of inferring it,
 * and this double reproduces it faithfully rather than helpfully labelling the
 * close event — a double that labelled it would let a broken runner pass.
 */
function fakeChild(opts: { code?: number | null; stdout?: string; stderr?: string;
                           hang?: boolean } = {}) {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
    kill: (signal?: string) => boolean;
    killed: boolean;
  };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.killed = false;
  child.kill = (signal?: string) => {
    child.killed = true;
    setImmediate(() => child.emit("close", null, signal ?? "SIGKILL"));
    return true;
  };
  // `hang` never settles on its own: the case a deadline or an abort has to
  // resolve, and the one spawnSync could not be interrupted in.
  if (!opts.hang) {
    setImmediate(() => {
      if (opts.stdout) child.stdout.emit("data", opts.stdout);
      if (opts.stderr) child.stderr.emit("data", opts.stderr);
      child.emit("close", opts.code ?? 0, null);
    });
  }
  return child;
}

/** Wrap a child factory as the `spawn` seam docker.ts injects. */
function fakeSpawn(make: (cmd: string, args: string[], options: unknown) => unknown) {
  return make as unknown as typeof spawn;
}

describe("#394 — every docker invocation carries a finite deadline", () => {
  it("declares a default timeout, and it is finite and plausible", async () => {
    expect(Number.isFinite(DEFAULT_DOCKER_TIMEOUT_MS)).toBe(true);
    expect(DEFAULT_DOCKER_TIMEOUT_MS).toBeGreaterThan(0);
    // A deadline nobody can hit is not a deadline. Anything past a few minutes
    // for a plain client call means the bound has drifted into decoration.
    expect(DEFAULT_DOCKER_TIMEOUT_MS).toBeLessThanOrEqual(5 * 60_000);
  });

  it("gives every declared operation a finite deadline, longest for builds", async () => {
    const entries = Object.entries(DOCKER_OPERATION_TIMEOUTS_MS);
    expect(entries.length).toBeGreaterThan(0);
    for (const [operation, ms] of entries) {
      expect(Number.isFinite(ms), `${operation} has no finite deadline`).toBe(true);
      expect(ms, `${operation} deadline must be positive`).toBeGreaterThan(0);
    }
    // A pull or a build legitimately takes minutes; an inspect does not. If
    // these ever equalise, the per-operation map has stopped meaning anything.
    expect(DOCKER_OPERATION_TIMEOUTS_MS.build).toBeGreaterThan(DOCKER_OPERATION_TIMEOUTS_MS.inspect);
  });

  it("passes the deadline through to the spawn, not merely stores it", async () => {
    // An argv whose subcommand is NOT in the per-operation map, so the value
    // handed to spawnSync is unambiguously the DEFAULT rather than a coincidence.
    // The failure this catches: a timeout constant that exists, is exported,
    // is asserted by a test, and is never handed to spawnSync.
    // #479: the deadline is no longer a spawn OPTION - async spawn has none -
    // so it is asserted through observable behaviour instead: a child that never
    // settles must still resolve, as a typed timeout, at the default bound.
    const seen: string[][] = [];
    const run = makeDockerRun({}, {
      timeoutMs: 15,
      spawn: fakeSpawn((_cmd, args) => {
        seen.push(args);
        return fakeChild({ hang: true });
      }),
    });
    const result = await run(["totally-not-a-docker-subcommand"]);
    expect(seen).toHaveLength(1);
    expect(result.timedOut).toBe(true);
    expect(DEFAULT_DOCKER_TIMEOUT_MS).toBeGreaterThan(0);
  });

  it("reports a timeout as a TYPED result, not an indistinguishable non-zero", async () => {
    // spawnSync signals a deadline kill through `error` / `signal`, and a plain
    // `{code: 1}` is what a normal docker failure looks like. A caller that
    // cannot tell them apart cannot escalate, which is the whole point.
    const timedOut = makeDockerRun({}, {
      timeoutMs: 15,
      spawn: fakeSpawn(() => fakeChild({ hang: true })),
    });
    const result: RunResult = await timedOut(["totally-not-a-docker-subcommand"]);
    expect(result.timedOut).toBe(true);
    expect(result.aborted).toBeFalsy();
    expect(result.code).toBe(DOCKER_TIMEOUT_EXIT_CODE);
    expect(result.stderr).toMatch(/timed out/i);
  });

  it("does not mark an ordinary docker failure as a timeout", async () => {
    const failed = makeDockerRun({}, {
      spawn: fakeSpawn(() => fakeChild({ code: 1, stderr: "no such container" })),
    });
    const result = await failed(["inspect", "missing"]);
    expect(result.timedOut).toBeFalsy();
    expect(result.aborted).toBeFalsy();
    expect(result.code).toBe(1);
    expect(result.stderr).toContain("no such container");
  });

  it("escalates a timed-out exec: the container process is stopped, not orphaned", async () => {
    // THE POINT OF THE ESCALATION. spawnSync's timeout kills the docker CLIENT.
    // The process it started inside the container keeps running, holding the
    // box open and whatever it was doing. So a timed-out exec must reach back
    // in and stop the container it targeted.
    const calls: string[][] = [];
    const dockerRun = async (args: string[]): Promise<RunResult> => {
      calls.push(args);
      if (args[0] === "exec") {
        return { code: 124, stdout: "", stderr: "docker exec timed out", timedOut: true };
      }
      return { code: 0, stdout: "", stderr: "" };
    };
    const result = await execInSandbox("box-1", ["sh", "-c", "sleep infinity"], { dockerRun });

    expect(result.timedOut).toBe(true);
    expect(result.exitCode).not.toBe(0);
    const escalation = calls.slice(1);
    expect(escalation.length, "a timed-out exec performed no cleanup").toBeGreaterThan(0);
    expect(escalation.some((argv) => argv[0] === "stop" && argv.includes("box-1"))).toBe(true);
  });

  it("does not escalate when the exec merely fails", async () => {
    // Escalation stops a container. Doing that on an ordinary non-zero exit
    // would destroy a working box every time a command returned 1.
    const calls: string[][] = [];
    const dockerRun = async (args: string[]): Promise<RunResult> => {
      calls.push(args);
      return { code: 7, stdout: "", stderr: "" };
    };
    const result = await execInSandbox("box-2", ["sh", "-c", "exit 7"], { dockerRun });
    expect(result.exitCode).toBe(7);
    expect(result.timedOut).toBeFalsy();
    expect(calls).toHaveLength(1);
  });

  it("still returns a result when the escalation itself fails", async () => {
    // A wedged daemon is exactly the case where the escalation cannot succeed.
    // Reporting the original timeout matters more than reporting the cleanup.
    const dockerRun = async (args: string[]): Promise<RunResult> => (args[0] === "exec"
      ? { code: 124, stdout: "", stderr: "timed out", timedOut: true }
      : { code: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" });
    const result = await execInSandbox("box-3", ["sh", "-c", "sleep infinity"], { dockerRun });
    expect(result.timedOut).toBe(true);
    expect(result.stderr).toMatch(/timed out/i);
  });
});

const realDocker = dockerGate("deadline", { linux: true });

realDocker("#394 — a real hung command terminates within its deadline", () => {
  it("a sleeping exec is killed at the deadline and leaves nothing running", async () => {
    const name = `ca-sbx-deadline-${Date.now().toString(36)}`;
    const created = await defaultDockerRun([
      "run", "-d", "--rm", "--name", name, "alpine:latest", "sleep", "600",
    ]);
    expect(created.code, created.stderr).toBe(0);
    const id = created.stdout.trim();
    try {
      const started = Date.now();
      const result = await execInSandbox(id, ["sh", "-c", "sleep 600"], {
        dockerRun: makeDockerRun({}, { maxBuffer: 8 * 1024 * 1024, timeoutMs: 4_000 }),
      });
      const elapsed = Date.now() - started;

      expect(result.timedOut).toBe(true);
      // Generous upper bound: this asserts the deadline EXISTS, not that the
      // runner is fast. Without it the call never returns at all.
      expect(elapsed).toBeLessThan(60_000);

      // AC: no targeted process is left running in the container. The
      // escalation stops the box, so the container itself is gone (--rm).
      const alive = await defaultDockerRun(["ps", "-q", "--filter", `name=${name}`]);
      expect(alive.stdout.trim()).toBe("");
    } finally {
      defaultDockerRun(["rm", "-f", id || name]);
    }
  }, 120_000);
});

describe("#479 — an in-flight docker call is cancellable", () => {
  it("aborts a call that would otherwise run to its deadline (AC-1)", async () => {
    // The child NEVER settles on its own. Under spawnSync this was
    // unreachable by construction: the thread sat inside the syscall, so there
    // was no point at which a signal could be observed. The only thing that
    // could end it was the deadline - which is why #394 could bound the call
    // but not cancel it.
    const controller = new AbortController();
    const run = makeDockerRun({}, {
      timeoutMs: 60_000,        // far beyond the test, so ONLY the abort can end it
      spawn: fakeSpawn(() => fakeChild({ hang: true })),
    });
    const started = Date.now();
    const pending = run(["exec", "box", "sleep", "infinity"], { signal: controller.signal });
    controller.abort();
    const result = await pending;

    expect(result.aborted).toBe(true);
    expect(result.timedOut).toBeFalsy();
    expect(result.code).toBe(DOCKER_ABORT_EXIT_CODE);
    expect(result.stderr).toMatch(/cancelled/i);
    // It returned because of the abort, not because a deadline elapsed.
    expect(Date.now() - started).toBeLessThan(10_000);
  });

  it("kills the child rather than merely resolving around it (AC-1)", async () => {
    // Resolving the promise while leaving the process alive would look like
    // cancellation and leak a running docker client.
    const controller = new AbortController();
    let child: ReturnType<typeof fakeChild> | undefined;
    const run = makeDockerRun({}, {
      timeoutMs: 60_000,
      spawn: fakeSpawn(() => (child = fakeChild({ hang: true }))),
    });
    const pending = run(["ps"], { signal: controller.signal });
    controller.abort();
    await pending;
    expect(child!.killed).toBe(true);
  });

  it("refuses to spawn at all when the signal is ALREADY aborted (AC-1)", async () => {
    // Checking only after the spawn would still create the next container in a
    // multi-step command that was cancelled mid-way, and teardown would then
    // have something to reclaim the caller never knew existed.
    const controller = new AbortController();
    controller.abort();
    let spawned = 0;
    const run = makeDockerRun({}, {
      spawn: fakeSpawn(() => {
        spawned += 1;
        return fakeChild({});
      }),
    });
    const result = await run(["run", "-d", "image"], { signal: controller.signal });

    expect(spawned).toBe(0);
    expect(result.aborted).toBe(true);
    expect(result.code).toBe(DOCKER_ABORT_EXIT_CODE);
    expect(result.stderr).toMatch(/before it started/i);
  });

  it("types an abort apart from a timeout (AC-4)", async () => {
    // Both arrive as close(null, "SIGKILL"), so the runner has to record WHICH
    // killer fired. Reporting one as the other would put "timed out" in an
    // audit trail for a deliberate Ctrl-C, and would send a caller looking for
    // a wedged daemon that does not exist.
    const controller = new AbortController();
    const spawn = fakeSpawn(() => fakeChild({ hang: true }));

    const aborting = makeDockerRun({}, { timeoutMs: 60_000, spawn });
    const pending = aborting(["ps"], { signal: controller.signal });
    controller.abort();
    const aborted = await pending;

    const expiring = makeDockerRun({}, { timeoutMs: 15, spawn });
    const timedOut = await expiring(["ps"]);

    expect(aborted.aborted).toBe(true);
    expect(aborted.timedOut).toBeFalsy();
    expect(timedOut.timedOut).toBe(true);
    expect(timedOut.aborted).toBeFalsy();
    expect(aborted.code).not.toBe(timedOut.code);
  });

  it("an unrelated signal firing after the call settles changes nothing", async () => {
    // The listener has to come off, or a later abort on a reused controller
    // would try to kill a child that already closed.
    const controller = new AbortController();
    const run = makeDockerRun({}, {
      spawn: fakeSpawn(() => fakeChild({ code: 0, stdout: "ok" })),
    });
    const result = await run(["ps"], { signal: controller.signal });
    expect(result.code).toBe(0);
    expect(result.aborted).toBeFalsy();
    expect(() => controller.abort()).not.toThrow();
    expect(result.aborted).toBeFalsy();
  });

  it("stops the container an ABORTED exec targeted, exactly as a timeout does (AC-2)", async () => {
    // The box is left running whether the deadline fired or the operator
    // pressed Ctrl-C, and an orphan is the same leak either way.
    const calls: string[][] = [];
    const dockerRun: DockerRun = async (args) => {
      calls.push(args);
      if (args[0] === "exec") {
        return {
          code: DOCKER_ABORT_EXIT_CODE, stdout: "", stderr: "cancelled", aborted: true,
        };
      }
      return { code: 0, stdout: "", stderr: "" };
    };
    const result = await execInSandbox("box-9", ["sh", "-c", "sleep infinity"], { dockerRun });

    expect(result.aborted).toBe(true);
    const escalation = calls.slice(1);
    expect(escalation).toHaveLength(1);
    expect(escalation[0]).toEqual(["stop", "--time", "0", "box-9"]);
    expect(result.stderr).toMatch(/stopped container box-9 after cancellation/i);
  });

  it("does not stop the container on an ordinary non-zero exec (AC-2)", async () => {
    // Escalation destroys a working box; doing it on exit 1 would tear one down
    // every time a command in it simply failed.
    const calls: string[][] = [];
    const dockerRun: DockerRun = async (args) => {
      calls.push(args);
      return { code: 1, stdout: "", stderr: "command failed" };
    };
    const result = await execInSandbox("box-10", ["false"], { dockerRun });

    expect(result.exitCode).toBe(1);
    expect(result.aborted).toBeFalsy();
    expect(calls).toHaveLength(1);
  });
});
