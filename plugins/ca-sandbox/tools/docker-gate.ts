/**
 * docker-gate.ts — the ONE docker-integration gate for the ca-sandbox suite
 * (issue #406).
 *
 * Every real-container spec in this plugin used to paste in its own copy of
 *
 *     function dockerAvailable() { ...spawnSync("docker", ["info", ...]) }
 *     const d = dockerAvailable() ? describe : describe.skip;
 *
 * which is exactly right on a developer machine and exactly wrong on the
 * REQUIRED merge gate: a runner Docker outage, a daemon that failed to start, a
 * permissions regression or a runtime incompatibility silently converted the
 * isolation, mount, network, lifecycle and teardown layers into skips, and the
 * job still exited 0 off the pure argv-builder specs. ca-sandbox is the driver
 * that clones UNTRUSTED repositories into a container — "the containment tests
 * did not run" must never be indistinguishable from "the containment tests
 * passed".
 *
 * This module keeps the developer-machine behavior and adds an explicit
 * REQUIRED mode plus an execution sentinel:
 *
 *   CA_SANDBOX_REQUIRE_DOCKER=1
 *       Docker is a prerequisite, not a nicety. An unavailable daemon throws
 *       from module scope, so Vitest fails to collect the file and the run
 *       exits non-zero. CI sets this; developer machines do not.
 *
 *   CA_SANDBOX_DOCKER_SENTINEL=<path>
 *       Each gated layer appends its name to this file when its suite actually
 *       STARTS. `.github/scripts/check_sandbox_docker_layers.py` then asserts
 *       the recorded set against the layers declared in this directory's
 *       sources, so "green" has to mean "every real-container layer executed"
 *       rather than merely "the process exited 0".
 *
 * The gate deliberately makes NO network/daemon assumption of its own beyond a
 * `docker info` probe: the suites themselves own the real container work.
 */
import { spawnSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { beforeAll, describe } from "vitest";

/** Set to a truthy value to make an unavailable daemon fatal instead of a skip. */
export const REQUIRE_ENV = "CA_SANDBOX_REQUIRE_DOCKER";
/** Path of the append-only file recording which gated layers actually ran. */
export const SENTINEL_ENV = "CA_SANDBOX_DOCKER_SENTINEL";

/** The `docker info` result the gate reasons about — the injectable seam. */
export type ProbeResult = { status: number | null; stdout: string };
export type DockerProbe = () => ProbeResult;

export type GateOptions = {
  /**
   * The layer needs a daemon serving LINUX containers. A Windows-container
   * daemon answers `docker info` happily but cannot attest anything this
   * plugin claims about linux isolation or egress policy.
   */
  linux?: boolean;
  /** Environment to read the mode switches from (defaults to `process.env`). */
  env?: NodeJS.ProcessEnv;
  /** Docker probe override — tests inject a daemon that is up, down or wrong. */
  probe?: DockerProbe;
};

export type GateDecision =
  | { run: true; ostype: string }
  | { run: false; reason: string };

/** A gated suite declaration: `d("name", () => { ... })`, and nothing else. */
export type GatedDescribe = (name: string, body: () => void) => void;

/** The real `docker info` probe. `env` is a parameter so a test can mask PATH. */
export function defaultProbe(env: NodeJS.ProcessEnv = process.env): ProbeResult {
  const result = spawnSync("docker", ["info", "--format", "{{.OSType}}"], {
    encoding: "utf8",
    env,
  });
  return { status: result.status, stdout: result.stdout ?? "" };
}

/**
 * Is Docker a REQUIRED prerequisite for this run?
 *
 * Unset / empty / `0` / `false` mean "local mode, self-skipping is fine".
 * Anything else means required. The permissive spelling is deliberate: the cost
 * of misreading a typo as "required" is a loud failure, while misreading it as
 * "local" is the silent green this whole module exists to abolish.
 */
export function requiredMode(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = (env[REQUIRE_ENV] ?? "").trim().toLowerCase();
  return raw !== "" && raw !== "0" && raw !== "false";
}

/** Probe the daemon and decide whether a gated layer can run against it. */
export function decideGate(options: GateOptions = {}): GateDecision {
  const probe = options.probe ?? (() => defaultProbe(options.env ?? process.env));
  const result = probe();
  const ostype = result.stdout.trim();
  if (result.status !== 0) {
    const detail =
      result.status === null
        ? "`docker info` never ran (docker is not on PATH)"
        : `\`docker info\` exited ${result.status}`;
    return { run: false, reason: detail };
  }
  if (options.linux === true && !/linux/i.test(ostype)) {
    return {
      run: false,
      reason:
        `the docker daemon serves OSType "${ostype || "<empty>"}", ` +
        "but this layer needs a daemon serving linux containers",
    };
  }
  return { run: true, ostype };
}

/**
 * Append `layer` to the sentinel file, if one is configured. Inert otherwise,
 * so a developer run writes nothing. `appendFileSync` on an O_APPEND handle is
 * the whole mechanism — Vitest runs these files serially (`fileParallelism:
 * false` in vitest.config.ts) precisely because they contend for the daemon.
 */
export function recordLayer(layer: string, env: NodeJS.ProcessEnv = process.env): void {
  const target = env[SENTINEL_ENV];
  if (target === undefined || target.trim() === "") return;
  appendFileSync(target, `${layer}\n`, { encoding: "utf8" });
}

/**
 * The gate every real-container suite declares itself with:
 *
 *     const d = dockerGate("isolation");
 *     d("host-FS isolation canary [docker] (AC-03)", () => { ... });
 *
 * `layer` is the sentinel key and must be unique across this directory; the
 * convention is the test file's stem.
 *
 * In required mode an unavailable daemon throws HERE, at module scope, which is
 * what turns a missing prerequisite into a non-zero Vitest exit instead of a
 * quiet skip.
 */
export function dockerGate(layer: string, options: GateOptions = {}): GatedDescribe {
  const env = options.env ?? process.env;
  const decision = decideGate(options);
  if (decision.run === false) {
    if (requiredMode(env)) {
      throw new Error(
        `${REQUIRE_ENV} is set, but the "${layer}" real-container layer cannot run: ` +
          `${decision.reason}. Docker is a REQUIRED prerequisite in this mode — a missing ` +
          "daemon fails the run rather than silently deleting the only evidence that " +
          "ca-sandbox contains an untrusted repository (issue #406). Unset " +
          `${REQUIRE_ENV} to restore developer self-skipping.`,
      );
    }
    return (name, body) => {
      describe.skip(name, body);
    };
  }
  return (name, body) => {
    describe(name, () => {
      beforeAll(() => recordLayer(layer, env));
      body();
    });
  };
}
