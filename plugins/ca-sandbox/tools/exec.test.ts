/**
 * exec.test.ts — T-11. Covers AC-09.
 *
 * execInSandbox(id, argv) wraps `docker exec` and returns a JSON contract:
 *   { id, exitCode, stdout, stderr, durationMs, truncated }
 * stdout and stderr are captured SEPARATELY (reusing farm's RunResult shape),
 * and each stream is bounded by a byte cap (reusing farm's cap discipline) —
 * output past the cap sets `truncated:true`.
 *
 * Two layers:
 *   1. PURE unit tests with an INJECTED docker runner — prove the JSON shape,
 *      that stdout/stderr stay separate, that the exit code is propagated, and
 *      that the byte cap trips `truncated`. Runs everywhere (the RED gate).
 *   2. A DOCKER-GATED integration test (guarded by `docker info`) runs a real
 *      `docker exec ... sh -c 'exit 7'` against a namespaced container and
 *      asserts exitCode 7 + separate streams + truncation past the cap.
 *      Namespaced (ca-sbx-t11), labeled, and cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import { execInSandbox, buildExecArgs, type ExecResult } from "./exec.ts";

// --------------------------------------------------------------------------
// PURE unit layer — injected docker runner, no real docker.
// --------------------------------------------------------------------------
describe("buildExecArgs — docker exec argv assembly (AC-09)", () => {
  it("wraps the argv as a non-interactive `docker exec <id> -- <argv>`", () => {
    const args = buildExecArgs("deadbeef", ["sh", "-c", "exit 7"]);
    expect(args[0]).toBe("exec");
    expect(args).toContain("deadbeef");
    // the user argv is preserved verbatim, in order, at the tail.
    expect(args.slice(-3)).toEqual(["sh", "-c", "exit 7"]);
    // never interactive / tty-allocating (that would hang a wrapped exec).
    expect(args).not.toContain("-it");
    expect(args).not.toContain("-t");
  });

  it("refuses an empty id or empty argv", () => {
    expect(() => buildExecArgs("", ["sh"])).toThrow();
    expect(() => buildExecArgs("id", [])).toThrow();
  });
});

describe("execInSandbox — JSON contract (AC-09)", () => {
  it("is importable and callable from a vitest and returns the full shape", () => {
    const res: ExecResult = execInSandbox("box1", ["sh", "-c", "true"], {
      dockerRun: () => ({ code: 0, stdout: "", stderr: "" }),
    });
    expect(res.id).toBe("box1");
    expect(res.exitCode).toBe(0);
    expect(res.stdout).toBe("");
    expect(res.stderr).toBe("");
    expect(typeof res.durationMs).toBe("number");
    expect(res.truncated).toBe(false);
  });

  it("propagates a non-zero exit code (exit 7 -> exitCode 7)", () => {
    const res = execInSandbox("box1", ["sh", "-c", "exit 7"], {
      dockerRun: () => ({ code: 7, stdout: "", stderr: "" }),
    });
    expect(res.exitCode).toBe(7);
  });

  it("captures stdout and stderr SEPARATELY", () => {
    const res = execInSandbox("box1", ["sh", "-c", "..."], {
      dockerRun: () => ({ code: 0, stdout: "this is stdout", stderr: "this is stderr" }),
    });
    expect(res.stdout).toBe("this is stdout");
    expect(res.stderr).toBe("this is stderr");
  });

  it("does NOT truncate when both streams are within the byte cap", () => {
    const res = execInSandbox("box1", ["sh"], {
      maxBytes: 100,
      dockerRun: () => ({ code: 0, stdout: "x".repeat(50), stderr: "y".repeat(50) }),
    });
    expect(res.truncated).toBe(false);
    expect(res.stdout.length).toBe(50);
    expect(res.stderr.length).toBe(50);
  });

  it("trips truncated:true and caps stdout past the byte cap", () => {
    const res = execInSandbox("box1", ["sh"], {
      maxBytes: 100,
      dockerRun: () => ({ code: 0, stdout: "x".repeat(500), stderr: "" }),
    });
    expect(res.truncated).toBe(true);
    expect(Buffer.byteLength(res.stdout, "utf8")).toBeLessThanOrEqual(100);
  });

  it("trips truncated:true when only stderr exceeds the cap", () => {
    const res = execInSandbox("box1", ["sh"], {
      maxBytes: 100,
      dockerRun: () => ({ code: 0, stdout: "", stderr: "e".repeat(500) }),
    });
    expect(res.truncated).toBe(true);
    expect(Buffer.byteLength(res.stderr, "utf8")).toBeLessThanOrEqual(100);
  });

  it("caps each stream INDEPENDENTLY (a huge stdout does not steal stderr budget)", () => {
    const res = execInSandbox("box1", ["sh"], {
      maxBytes: 10,
      dockerRun: () => ({ code: 0, stdout: "x".repeat(500), stderr: "yyyyy" }),
    });
    expect(res.truncated).toBe(true);
    expect(Buffer.byteLength(res.stdout, "utf8")).toBeLessThanOrEqual(10);
    // stderr was under its own cap and is preserved whole.
    expect(res.stderr).toBe("yyyyy");
  });

  it("truncates on a UTF-8 boundary (no mojibake / no partial code unit)", () => {
    // 'é' is 2 bytes in UTF-8; a naive byte slice at an odd cap would split it.
    const res = execInSandbox("box1", ["sh"], {
      maxBytes: 5,
      dockerRun: () => ({ code: 0, stdout: "é".repeat(20), stderr: "" }),
    });
    expect(res.truncated).toBe(true);
    // the captured stdout must remain valid UTF-8 (re-encoding round-trips).
    expect(Buffer.byteLength(res.stdout, "utf8")).toBeLessThanOrEqual(5);
    expect(Buffer.from(res.stdout, "utf8").toString("utf8")).toBe(res.stdout);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-09).
// Starts a real container, execs a real command, asserts the JSON contract.
// Namespaced with the task id; every object is cleaned up.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0;
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t11";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

d("execInSandbox [docker] — real exec JSON contract (AC-09)", () => {
  const created = { containers: [] as string[] };
  let cid = "";

  afterAll(() => {
    for (const c of created.containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
  });

  // Start one keep-alive busybox container we exec into for every assertion.
  function ensureContainer(): string {
    if (cid) return cid;
    const image = "busybox:latest";
    const pull = spawnSync("docker", ["pull", image], { encoding: "utf8", env: DENV });
    expect(pull.status, pull.stderr).toBe(0);
    const name = `${NS}-${Date.now()}`;
    const run = spawnSync(
      "docker",
      ["run", "-d", "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1", "--name", name, image, "sleep", "300"],
      { encoding: "utf8", env: DENV },
    );
    expect(run.status, run.stderr).toBe(0);
    cid = run.stdout.trim();
    created.containers.push(cid);
    return cid;
  }

  it("`sh -c 'exit 7'` -> exitCode 7 in the JSON", () => {
    const id = ensureContainer();
    const res = execInSandbox(id, ["sh", "-c", "exit 7"]);
    expect(res.id).toBe(id);
    expect(res.exitCode).toBe(7);
    expect(typeof res.durationMs).toBe("number");
  }, 120_000);

  it("captures stdout and stderr SEPARATELY from a real exec", () => {
    const id = ensureContainer();
    const res = execInSandbox(id, ["sh", "-c", "echo OUT; echo ERR 1>&2"]);
    expect(res.exitCode).toBe(0);
    expect(res.stdout).toContain("OUT");
    expect(res.stdout).not.toContain("ERR");
    expect(res.stderr).toContain("ERR");
    expect(res.stderr).not.toContain("OUT");
  }, 120_000);

  it("trips truncated:true on output past the byte cap", () => {
    const id = ensureContainer();
    // emit ~5000 bytes to stdout, cap at 100.
    const res = execInSandbox(id, ["sh", "-c", "yes x | head -c 5000"], { maxBytes: 100 });
    expect(res.exitCode).toBe(0);
    expect(res.truncated).toBe(true);
    expect(Buffer.byteLength(res.stdout, "utf8")).toBeLessThanOrEqual(100);
  }, 120_000);

  it("does NOT trip truncated for small real output under the cap", () => {
    const id = ensureContainer();
    const res = execInSandbox(id, ["sh", "-c", "echo hi"], { maxBytes: 1024 });
    expect(res.exitCode).toBe(0);
    expect(res.truncated).toBe(false);
    expect(res.stdout).toContain("hi");
  }, 120_000);
});
