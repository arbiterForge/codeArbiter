/**
 * docker-gate.test.ts — #406. Docker is a REQUIRED prerequisite in CI.
 *
 * Every real-container ca-sandbox suite used to carry its own `docker info`
 * probe and degrade to `describe.skip` when the probe failed — including on the
 * REQUIRED merge-gate job. A runner Docker outage therefore deleted the only
 * isolation / mount / network / lifecycle / teardown evidence this plugin has
 * while the board reported green off pure argv-builder tests. ca-sandbox is the
 * driver that clones UNTRUSTED repositories; "the containment tests did not run"
 * must never be indistinguishable from "the containment tests passed".
 *
 * The obligations locked in here:
 *   1. self-skip survives on a developer machine (no CA_SANDBOX_REQUIRE_DOCKER);
 *   2. in required mode an unavailable daemon THROWS, so the file fails to
 *      collect and Vitest exits non-zero;
 *   3. a daemon of the wrong OSType is "unavailable" for a suite that needs a
 *      linux daemon — a Windows-container daemon cannot attest linux isolation;
 *   4. a suite that really executes appends its layer to the sentinel file, so
 *      required CI can assert the layer set rather than trust an exit code;
 *   5. end-to-end: a Vitest child whose PATH has been masked of docker exits
 *      NON-ZERO in required mode (this is the reproduction from the issue).
 */
import { describe, it, expect } from "vitest";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  REQUIRE_ENV,
  SENTINEL_ENV,
  decideGate,
  defaultProbe,
  dockerGate,
  recordLayer,
  requiredMode,
  type DockerProbe,
} from "./docker-gate.ts";

const HERE = dirname(fileURLToPath(import.meta.url));

/** A probe standing in for a daemon that is simply not there. */
const absent: DockerProbe = () => ({ status: null, stdout: "" });
/** A probe standing in for `docker info` answering with an error. */
const broken: DockerProbe = () => ({ status: 1, stdout: "" });
/** A healthy linux daemon. */
const linux: DockerProbe = () => ({ status: 0, stdout: "linux\n" });
/** A healthy daemon serving WINDOWS containers. */
const windows: DockerProbe = () => ({ status: 0, stdout: "windows\n" });

/** An env with every case-spelling of PATH pointed at an empty directory. */
function maskDockerFromPath(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const empty = mkdtempSync(join(tmpdir(), "ca-sbx-nopath-"));
  const env: NodeJS.ProcessEnv = { ...process.env, ...extra };
  for (const key of Object.keys(env)) {
    if (/^path$/i.test(key)) env[key] = empty;
  }
  return env;
}

describe("requiredMode — the explicit local/required switch (AC-2)", () => {
  it("is off when the variable is unset, empty, 0 or false", async () => {
    expect(requiredMode({})).toBe(false);
    expect(requiredMode({ [REQUIRE_ENV]: "" })).toBe(false);
    expect(requiredMode({ [REQUIRE_ENV]: "   " })).toBe(false);
    expect(requiredMode({ [REQUIRE_ENV]: "0" })).toBe(false);
    expect(requiredMode({ [REQUIRE_ENV]: "false" })).toBe(false);
  });

  it("is on for the spellings CI actually uses", async () => {
    expect(requiredMode({ [REQUIRE_ENV]: "1" })).toBe(true);
    expect(requiredMode({ [REQUIRE_ENV]: "true" })).toBe(true);
  });
});

describe("decideGate — what counts as an available daemon", () => {
  it("runs on a healthy daemon", async () => {
    expect(decideGate({ probe: linux })).toMatchObject({ run: true });
  });

  it("does not run when docker is not on PATH at all", async () => {
    const decision = decideGate({ probe: absent });
    expect(decision.run).toBe(false);
    expect(decision.run === false && decision.reason).toMatch(/PATH/i);
  });

  it("does not run when `docker info` exits non-zero", async () => {
    const decision = decideGate({ probe: broken });
    expect(decision.run).toBe(false);
    expect(decision.run === false && decision.reason).toMatch(/exited 1/);
  });

  it("treats a windows-container daemon as unavailable for a linux-only layer", async () => {
    expect(decideGate({ probe: windows, linux: true }).run).toBe(false);
    // ...and as fine for a layer that does not care.
    expect(decideGate({ probe: windows }).run).toBe(true);
  });
});

describe("dockerGate — required mode fails instead of skipping (AC-1)", () => {
  it("throws, naming the layer and the switch, when the daemon is unavailable", async () => {
    expect(() =>
      dockerGate("isolation", { probe: absent, env: { [REQUIRE_ENV]: "1" } }),
    ).toThrow(new RegExp(`${REQUIRE_ENV}[\\s\\S]*isolation|isolation[\\s\\S]*${REQUIRE_ENV}`));
  });

  it("throws when a linux-only layer meets a windows daemon", async () => {
    expect(() =>
      dockerGate("network", { probe: windows, linux: true, env: { [REQUIRE_ENV]: "1" } }),
    ).toThrow(/windows/i);
  });

  it("still self-skips on a developer machine with the switch off", async () => {
    expect(() => dockerGate("isolation", { probe: absent, env: {} })).not.toThrow();
  });

  it("does not throw when the daemon is healthy", async () => {
    expect(() =>
      dockerGate("isolation", { probe: linux, env: { [REQUIRE_ENV]: "1" } }),
    ).not.toThrow();
  });
});

describe("recordLayer — the machine-checkable execution sentinel (AC-3)", () => {
  it("appends one line per executed layer", async () => {
    const sentinel = join(mkdtempSync(join(tmpdir(), "ca-sbx-sentinel-")), "layers.txt");
    recordLayer("isolation", { [SENTINEL_ENV]: sentinel });
    recordLayer("lifecycle", { [SENTINEL_ENV]: sentinel });
    expect(readFileSync(sentinel, "utf8").trim().split(/\r?\n/)).toEqual([
      "isolation",
      "lifecycle",
    ]);
  });

  it("is inert when no sentinel path is configured", async () => {
    expect(() => recordLayer("isolation", {})).not.toThrow();
  });
});

describe("PATH-masked reproduction — the issue's own repro (AC-4)", () => {
  it("the real probe reports unavailable when docker is masked from PATH", async () => {
    const result = defaultProbe(maskDockerFromPath());
    expect(result.status).not.toBe(0);
  });

  it("a required-mode Vitest child with docker masked from PATH exits NON-ZERO", async () => {
    const env = maskDockerFromPath({ [REQUIRE_ENV]: "1" });
    delete env[SENTINEL_ENV];
    const child = spawnSync(
      process.execPath,
      [
        join(HERE, "node_modules", "vitest", "vitest.mjs"),
        "run",
        "--config",
        join("__fixtures__", "docker-required", "vitest.config.ts"),
      ],
      { cwd: HERE, env, encoding: "utf8" },
    );
    const output = `${child.stdout ?? ""}${child.stderr ?? ""}`;
    expect(child.status, `expected a non-zero run, got:\n${output}`).not.toBe(0);
    // ...and non-zero for the RIGHT reason: the gate refused, naming its layer.
    // Without this the assertion above would also accept "Vitest failed to
    // start", which is not the contract under test.
    expect(output).toContain(REQUIRE_ENV);
    expect(output).toContain("fixture-layer");
  }, 120_000);
});
