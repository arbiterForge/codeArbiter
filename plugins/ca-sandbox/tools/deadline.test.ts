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
import { describe, it, expect } from "vitest";
import { spawnSync } from "node:child_process";
import {
  DEFAULT_DOCKER_TIMEOUT_MS,
  DOCKER_OPERATION_TIMEOUTS_MS,
  defaultDockerRun,
  makeDockerRun,
  type RunResult,
} from "./docker.ts";
import { execInSandbox } from "./exec.ts";
import { dockerGate } from "./docker-gate.ts";

describe("#394 — every docker invocation carries a finite deadline", () => {
  it("declares a default timeout, and it is finite and plausible", () => {
    expect(Number.isFinite(DEFAULT_DOCKER_TIMEOUT_MS)).toBe(true);
    expect(DEFAULT_DOCKER_TIMEOUT_MS).toBeGreaterThan(0);
    // A deadline nobody can hit is not a deadline. Anything past a few minutes
    // for a plain client call means the bound has drifted into decoration.
    expect(DEFAULT_DOCKER_TIMEOUT_MS).toBeLessThanOrEqual(5 * 60_000);
  });

  it("gives every declared operation a finite deadline, longest for builds", () => {
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

  it("passes the deadline through to the spawn, not merely stores it", () => {
    // An argv whose subcommand is NOT in the per-operation map, so the value
    // handed to spawnSync is unambiguously the DEFAULT rather than a coincidence.
    // The failure this catches: a timeout constant that exists, is exported,
    // is asserted by a test, and is never handed to spawnSync.
    const seen: Array<Record<string, unknown>> = [];
    const run = makeDockerRun({}, { spawn: ((_cmd: string, _args: string[], options: unknown) => {
      seen.push(options as Record<string, unknown>);
      return { status: 0, stdout: "", stderr: "" };
    }) as unknown as typeof spawnSync });
    run(["totally-not-a-docker-subcommand"]);
    expect(seen).toHaveLength(1);
    expect(seen[0]!.timeout).toBe(DEFAULT_DOCKER_TIMEOUT_MS);
    expect(seen[0]!.killSignal).toBeDefined();
  });

  it("reports a timeout as a TYPED result, not an indistinguishable non-zero", () => {
    // spawnSync signals a deadline kill through `error` / `signal`, and a plain
    // `{code: 1}` is what a normal docker failure looks like. A caller that
    // cannot tell them apart cannot escalate, which is the whole point.
    const timedOut = makeDockerRun({}, { spawn: (() => ({
      status: null,
      signal: "SIGTERM",
      stdout: "",
      stderr: "",
      error: Object.assign(new Error("spawnSync docker ETIMEDOUT"), { code: "ETIMEDOUT" }),
    })) as unknown as typeof spawnSync });
    const result: RunResult = timedOut(["totally-not-a-docker-subcommand"]);
    expect(result.timedOut).toBe(true);
    expect(result.code).not.toBe(0);
    expect(result.stderr).toMatch(/timed out/i);
    expect(result.stderr).toMatch(new RegExp(String(DEFAULT_DOCKER_TIMEOUT_MS)));
  });

  it("does not mark an ordinary docker failure as a timeout", () => {
    const failed = makeDockerRun({}, { spawn: (() => ({
      status: 1, signal: null, stdout: "", stderr: "no such container", error: undefined,
    })) as unknown as typeof spawnSync });
    const result = failed(["inspect", "missing"]);
    expect(result.timedOut).toBeFalsy();
    expect(result.code).toBe(1);
  });

  it("escalates a timed-out exec: the container process is stopped, not orphaned", () => {
    // THE POINT OF THE ESCALATION. spawnSync's timeout kills the docker CLIENT.
    // The process it started inside the container keeps running, holding the
    // box open and whatever it was doing. So a timed-out exec must reach back
    // in and stop the container it targeted.
    const calls: string[][] = [];
    const dockerRun = (args: string[]): RunResult => {
      calls.push(args);
      if (args[0] === "exec") {
        return { code: 124, stdout: "", stderr: "docker exec timed out", timedOut: true };
      }
      return { code: 0, stdout: "", stderr: "" };
    };
    const result = execInSandbox("box-1", ["sh", "-c", "sleep infinity"], { dockerRun });

    expect(result.timedOut).toBe(true);
    expect(result.exitCode).not.toBe(0);
    const escalation = calls.slice(1);
    expect(escalation.length, "a timed-out exec performed no cleanup").toBeGreaterThan(0);
    expect(escalation.some((argv) => argv[0] === "stop" && argv.includes("box-1"))).toBe(true);
  });

  it("does not escalate when the exec merely fails", () => {
    // Escalation stops a container. Doing that on an ordinary non-zero exit
    // would destroy a working box every time a command returned 1.
    const calls: string[][] = [];
    const dockerRun = (args: string[]): RunResult => {
      calls.push(args);
      return { code: 7, stdout: "", stderr: "" };
    };
    const result = execInSandbox("box-2", ["sh", "-c", "exit 7"], { dockerRun });
    expect(result.exitCode).toBe(7);
    expect(result.timedOut).toBeFalsy();
    expect(calls).toHaveLength(1);
  });

  it("still returns a result when the escalation itself fails", () => {
    // A wedged daemon is exactly the case where the escalation cannot succeed.
    // Reporting the original timeout matters more than reporting the cleanup.
    const dockerRun = (args: string[]): RunResult => (args[0] === "exec"
      ? { code: 124, stdout: "", stderr: "timed out", timedOut: true }
      : { code: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" });
    const result = execInSandbox("box-3", ["sh", "-c", "sleep infinity"], { dockerRun });
    expect(result.timedOut).toBe(true);
    expect(result.stderr).toMatch(/timed out/i);
  });
});

const realDocker = dockerGate("deadline", { linux: true });

realDocker("#394 — a real hung command terminates within its deadline", () => {
  it("a sleeping exec is killed at the deadline and leaves nothing running", () => {
    const name = `ca-sbx-deadline-${Date.now().toString(36)}`;
    const created = defaultDockerRun([
      "run", "-d", "--rm", "--name", name, "alpine:latest", "sleep", "600",
    ]);
    expect(created.code, created.stderr).toBe(0);
    const id = created.stdout.trim();
    try {
      const started = Date.now();
      const result = execInSandbox(id, ["sh", "-c", "sleep 600"], {
        dockerRun: makeDockerRun({ maxBuffer: 8 * 1024 * 1024 }, { timeoutMs: 4_000 }),
      });
      const elapsed = Date.now() - started;

      expect(result.timedOut).toBe(true);
      // Generous upper bound: this asserts the deadline EXISTS, not that the
      // runner is fast. Without it the call never returns at all.
      expect(elapsed).toBeLessThan(60_000);

      // AC: no targeted process is left running in the container. The
      // escalation stops the box, so the container itself is gone (--rm).
      const alive = defaultDockerRun(["ps", "-q", "--filter", `name=${name}`]);
      expect(alive.stdout.trim()).toBe("");
    } finally {
      defaultDockerRun(["rm", "-f", id || name]);
    }
  }, 120_000);
});
