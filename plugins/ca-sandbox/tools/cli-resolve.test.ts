/**
 * cli-resolve.test.ts — regression for the create->exec/cp integration seam.
 *
 * The bug this pins: `create` names a container `ca-sbx-<id>-<suffix>`, but the
 * CLI `exec`/`cp`/`shell` handlers were passing the bare user-facing SANDBOX id
 * straight to `docker exec`, which fails with "No such container: <id>". The
 * unit/docker tests for exec.ts/cp.ts never caught it because they addressed a
 * container by its REAL id, never via the sandbox id whose container name differs.
 *
 * Two layers:
 *   1. PURE — resolveContainerId maps a sandbox id to its container id via the
 *      label registry (injected fake docker), and throws on an unknown id.
 *   2. DOCKER-GATED — start a real container whose NAME != its sandbox id, then
 *      drive the CLI's defaultHandlers.exec/cp BY THE SANDBOX ID and prove they
 *      resolve and run (AC-09 / AC-10 through the create-shaped naming).
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { resolveContainerId, type DockerRun, idLabel, SANDBOX_LABEL } from "./registry.ts";
import { defaultHandlers } from "./cli.ts";
import { execInSandbox } from "./exec.ts";

// --------------------------------------------------------------------------
// PURE — resolveContainerId via injected fake docker.
// --------------------------------------------------------------------------
describe("resolveContainerId — sandbox id -> container id (label registry)", () => {
  it("returns the container id discovered by the ca.sandbox.id label filter", () => {
    const run: DockerRun = (args) =>
      args[0] === "ps"
        ? { code: 0, stdout: "container-abc123\n", stderr: "" }
        : { code: 0, stdout: "", stderr: "" };
    expect(resolveContainerId("sbx1", run)).toBe("container-abc123");
  });

  it("throws when no labeled container carries the id (unknown/destroyed)", () => {
    const run: DockerRun = () => ({ code: 0, stdout: "", stderr: "" });
    expect(() => resolveContainerId("missing", run)).toThrow(/no running container/i);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED — the real seam: container NAME != sandbox id.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const d = dockerAvailable() ? describe : describe.skip;
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

d("CLI exec/cp resolve a sandbox id whose container name != id [docker] (AC-09/AC-10 regression)", () => {
  const containers: string[] = [];
  const tmps: string[] = [];
  afterAll(() => {
    for (const c of containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    for (const t of tmps) rmSync(t, { recursive: true, force: true });
  });

  it("exec by sandbox id resolves to the container; bare id does NOT (the bug)", () => {
    const id = `r${Date.now().toString(16)}`;
    const name = `ca-sbx-${id}-deadbeef`; // create-shaped: name != id
    const start = spawnSync(
      "docker",
      [
        "run", "-d", "--name", name,
        "--label", SANDBOX_LABEL, "--label", idLabel(id),
        "busybox", "sleep", "300",
      ],
      { encoding: "utf8", env: DENV },
    );
    expect(start.status, start.stderr).toBe(0);
    containers.push(name);

    // The OLD behavior: addressing the box by the bare sandbox id fails — the
    // container is not named after the id. This is the regression guard.
    const bare = execInSandbox(id, ["true"]);
    expect(bare.exitCode).not.toBe(0);
    expect(bare.stderr).toMatch(/no such container/i);

    // The FIX: the CLI handler resolves the sandbox id to the container id.
    const r = defaultHandlers.exec(id, ["sh", "-c", "echo RESOLVED_OK"]);
    expect(r.exitCode, r.stderr).toBe(0);
    expect(r.stdout).toContain("RESOLVED_OK");
    expect(r.id).toBe(id); // the sandbox id is preserved in the contract
  }, 120_000);

  it("cp by sandbox id pulls a file from the box to the host", () => {
    const id = `c${Date.now().toString(16)}`;
    const name = `ca-sbx-${id}-feedface`;
    const start = spawnSync(
      "docker",
      ["run", "-d", "--name", name, "--label", SANDBOX_LABEL, "--label", idLabel(id), "busybox", "sleep", "300"],
      { encoding: "utf8", env: DENV },
    );
    expect(start.status, start.stderr).toBe(0);
    containers.push(name);

    // Put a known file inside, then pull it out BY SANDBOX ID.
    defaultHandlers.exec(id, ["sh", "-c", "echo pulled-ok > /tmp/out.txt"]);
    const dir = mkdtempSync(path.join(tmpdir(), "ca-sbx-cpr-"));
    tmps.push(dir);
    const dest = path.join(dir, "out.txt");
    const cpr = defaultHandlers.cp(id, "/tmp/out.txt", dest);
    expect(cpr.code, cpr.stderr).toBe(0);
    expect(readFileSync(dest, "utf8")).toContain("pulled-ok");
  }, 120_000);
});
