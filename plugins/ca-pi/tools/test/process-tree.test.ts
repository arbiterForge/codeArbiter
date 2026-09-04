import { spawn, spawnSync } from "node:child_process";
import * as childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { PassThrough, Writable } from "node:stream";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { win32 } from "node:path";

import { describe, expect, test, vi } from "vitest";

vi.mock("node:child_process", { spy: true });

import {
  PROCESS_TREE_CLEANUP_REASONS,
  WINDOWS_SUPERVISOR_REFUSAL_REASONS,
  awaitProgressTokens,
  createProcessTreeCleanup,
  openProcessTree,
  parseWindowsSupervisorStatusLine,
  processTreeSpawnOptions,
  processTreeTerminationPlan,
  resolveWindowsPowerShellExecutable,
  resolveWindowsTaskkillExecutable,
  spawnProcessTree,
  writeBoundedControl,
  windowsHelperNeedsTermination,
  windowsPowerShellCandidatePaths,
  windowsRefusalReasonFromMessage,
  windowsSupervisorLaunchPlan,
  windowsJobHelperArgv,
} from "../src/process-tree.ts";

function waitForSpawn(child: ReturnType<typeof spawn>): Promise<void> {
  if (child.pid !== undefined) return Promise.resolve();
  return new Promise((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
}

function forceFixtureCleanup(pid: number | undefined): void {
  if (pid === undefined) return;
  if (process.platform === "win32") {
    const taskkill = resolveWindowsTaskkillExecutable();
    if (taskkill === undefined) throw new Error("validated taskkill is required for fixture cleanup");
    spawnSync(taskkill, ["/PID", String(pid), "/T", "/F"], {
      shell: false,
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  try { process.kill(-pid, "SIGKILL"); } catch { /* The tree is already gone. */ }
}

const WINDOWS_JOB_ATTACH_REFUSAL = "Windows Job Object holder refused containment";
const PROOF_ATTEMPT_DIAGNOSTIC_MAX_CHARS = 512;
// This ceiling is derived from the product's own fail-closed bounds, not chosen:
// it must stay OUTSIDE them, or the harness starts masking the product's precise
// refusal with a bare "Test timed out". runWindowsLaunchAdmissionProof makes at
// most two attempts, each bounded by WINDOWS_JOB_READY_CEILING_MS (#428: 30 s,
// now a per-phase no-progress budget instead of one flat 15 s window), and the
// proof then adds its condition-based 10-second child-output wait and its
// 5.25-second cleanup window: 2*30 + 10 + 5.25 = 75.25 s. 90 s is the next round
// value above that. Measured cost when nothing stalls: 846-936 ms on an idle
// Windows 11 dev box over 6 runs, i.e. ~1% of this ceiling - it bounds a hang,
// it is not a budget anything is expected to approach.
const WINDOWS_LIVE_PROOF_TEST_TIMEOUT_MS = 90_000;

function isWindowsJobAttachRefusal(error: unknown): error is Error {
  // Issue #428 widened the refusal message with a parenthesised stall phase
  // ("... refused containment (stalled at ATTACHED after 30000ms): ready-timeout"),
  // so the prefix - not the prefix-plus-colon - is what identifies the refusal.
  return error instanceof Error && error.message.startsWith(WINDOWS_JOB_ATTACH_REFUSAL);
}

/**
 * A deterministic Job-holder handshake: each entry is how long the helper takes
 * to emit its next protocol line, driving a fake clock so a "slow" runner costs
 * the test nothing in real time.
 */
function scriptedHandshake(script: readonly Readonly<{ afterMs: number; line?: string }>[]) {
  const clock = { value: 0 };
  let index = 0;
  const readLine = async (timeoutMs: number): Promise<string | undefined> => {
    const step = script[index];
    index += 1;
    if (step === undefined || step.afterMs > timeoutMs) {
      clock.value += timeoutMs;
      return undefined;
    }
    clock.value += step.afterMs;
    return step.line;
  };
  return { clock, readLine, now: () => clock.value };
}

function boundedProofAttemptDiagnostic(attempt: number, error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const bounded = message.length <= PROOF_ATTEMPT_DIAGNOSTIC_MAX_CHARS
    ? message
    : `${message.slice(0, PROOF_ATTEMPT_DIAGNOSTIC_MAX_CHARS)}[truncated]`;
  const code = isWindowsJobAttachRefusal(error) ? "job-attach-refused" : "unknown";
  return `attempt ${attempt} code=${code} message=${JSON.stringify(bounded)}`;
}

async function runWindowsLaunchAdmissionProof<T>(launch: () => Promise<T>): Promise<T> {
  try {
    return await launch();
  } catch (firstError) {
    if (!isWindowsJobAttachRefusal(firstError)) throw firstError;
    try {
      return await launch();
    } catch (secondError) {
      throw new Error(
        `Windows launch-admission proof failed after one retry: ${boundedProofAttemptDiagnostic(1, firstError)}; ${boundedProofAttemptDiagnostic(2, secondError)}`,
      );
    }
  }
}

describe("Windows inert-supervisor refusal reason protocol", () => {
  test("parses a bare legacy STARTED/REFUSED line with no reason", () => {
    expect(parseWindowsSupervisorStatusLine("STARTED 4242")).toEqual({ outcome: "started", pid: 4242 });
    expect(parseWindowsSupervisorStatusLine("REFUSED")).toEqual({ outcome: "refused" });
  });

  test.each(WINDOWS_SUPERVISOR_REFUSAL_REASONS)("parses the reasoned REFUSED %s form", (reason) => {
    expect(parseWindowsSupervisorStatusLine(`REFUSED ${reason}`)).toEqual({ outcome: "refused", reason });
  });

  test.each([
    "REFUSED not-a-real-reason",
    "REFUSED ",
    "started 4242",
    "STARTED 0",
    "STARTED -1",
    "STARTED abc",
    "",
    "garbage",
  ])("rejects a malformed or unrecognized status line %s", (line) => {
    expect(parseWindowsSupervisorStatusLine(line)).toBeUndefined();
  });

  test.each(WINDOWS_SUPERVISOR_REFUSAL_REASONS)("extracts %s from a trailing process-tree diagnostic message", (reason) => {
    expect(windowsRefusalReasonFromMessage(`Windows contained Pi launch was refused: ${reason}`)).toBe(reason);
  });

  test("does not extract a reason from a message with no recognized trailing token", () => {
    expect(windowsRefusalReasonFromMessage("Windows contained Pi launch was refused")).toBeUndefined();
    expect(windowsRefusalReasonFromMessage("some other error: not-a-reason-code")).toBeUndefined();
  });
});

describe("Windows startup stage diagnostics", () => {
  const options = { idleMs: 15_000, ceilingMs: 30_000, windowsJobStages: true };

  // DG-01/02: diagnostic stages name the last completed operation but do not
  // renew either admission deadline or replace ATTACHED as admission proof.
  test.each([
    [[], "STARTING", "WAITING", 15_000],
    [["STARTING"], "ATTACHED", "STARTING", 15_010],
    [["STARTING", "COMPILED"], "ATTACHED", "COMPILED", 15_010],
    [["STARTING", "COMPILED", "PID_ACCEPTED"], "ATTACHED", "PID_ACCEPTED", 15_010],
  ] as const)("names the last stage after %j without admitting a silent helper", async (lines, phase, lastStage, totalMs) => {
    const handshake = scriptedHandshake(lines.map((line) => ({ afterMs: 10, line })));
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], {
      ...options, now: handshake.now,
    })).resolves.toEqual({ state: "stalled", phase, lastStage, waitedMs: 15_000 });
    expect(handshake.clock.value).toBe(totalMs);
  });

  test("admits only the ordered complete diagnostic handshake", async () => {
    const handshake = scriptedHandshake(["STARTING", "COMPILED", "PID_ACCEPTED", "ATTACHED"].map((line) => ({ afterMs: 100, line })));
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], {
      ...options, now: handshake.now,
    })).resolves.toEqual({ state: "ready" });
    expect(handshake.clock.value).toBe(400);
  });

  test("rejects Windows diagnostics on a different admission sequence", async () => {
    await expect(awaitProgressTokens(async () => "ATTACHED", ["ATTACHED"], options))
      .rejects.toThrow("bounded admission sequence");
  });

  test.each([
    ["COMPILED", "COMPILED"], ["PID_ACCEPTED", "STARTING"],
    ["ATTACHED", "STARTING"], ["COMPILED\nPID_ACCEPTED", "STARTING"],
    ["PRIVATE_INPUT_SENTINEL".repeat(100), "STARTING"],
  ])("rejects malformed or out-of-order stage %s without echoing it", async (line, lastStage) => {
    const lines = line === "COMPILED" ? ["STARTING", "COMPILED", line] : ["STARTING", line];
    const handshake = scriptedHandshake(lines.map((value) => ({ afterMs: 10, line: value })));
    const result = await awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], { ...options, now: handshake.now });
    expect(result).toMatchObject({ state: "stalled", phase: "ATTACHED", lastStage });
    expect(JSON.stringify(result)).not.toContain("PRIVATE_INPUT_SENTINEL");
  });

  test("does not extend the idle deadline with late diagnostic progress", async () => {
    const handshake = scriptedHandshake([
      { afterMs: 1_000, line: "STARTING" }, { afterMs: 10_000, line: "COMPILED" },
      { afterMs: 4_000, line: "PID_ACCEPTED" }, { afterMs: 2_000, line: "ATTACHED" },
    ]);
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], { ...options, now: handshake.now }))
      .resolves.toEqual({ state: "stalled", phase: "ATTACHED", lastStage: "PID_ACCEPTED", waitedMs: 15_000 });
    expect(handshake.clock.value).toBe(16_000);
  });

  test("does not extend the absolute ceiling with diagnostic progress", async () => {
    const handshake = scriptedHandshake([
      { afterMs: 12_000, line: "STARTING" }, { afterMs: 4_000, line: "COMPILED" },
      { afterMs: 3_000, line: "PID_ACCEPTED" }, { afterMs: 2_000, line: "ATTACHED" },
    ]);
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], { ...options, ceilingMs: 20_000, now: handshake.now }))
      .resolves.toEqual({ state: "stalled", phase: "ATTACHED", lastStage: "PID_ACCEPTED", waitedMs: 8_000 });
    expect(handshake.clock.value).toBe(20_000);
  });

  test("bounds a diagnostic flood without refreshing its budget", async () => {
    let reads = 0;
    const result = await awaitProgressTokens(async () => ++reads === 1 ? "STARTING" : "COMPILED", ["STARTING", "ATTACHED"], options);
    expect(result).toMatchObject({ state: "stalled", phase: "ATTACHED", lastStage: "COMPILED" });
    expect(reads).toBe(3);
  });

  test.skipIf(process.platform !== "win32")("bounds queued diagnostic bytes across individually small chunks before the reader resumes", async () => {
    const helper = Object.assign(new EventEmitter(), {
      stdout: new PassThrough(), stderr: new PassThrough(), stdin: new PassThrough(),
      exitCode: null, signalCode: null, kill: vi.fn(),
    });
    const supervisor = Object.assign(new EventEmitter(), { pid: 4242, kill: vi.fn(), exitCode: null, signalCode: null });
    const spawnMock = vi.spyOn(childProcess, "spawn")
      .mockReturnValueOnce(supervisor as never).mockReturnValueOnce(helper as never);
    const pending = spawnProcessTree(process.execPath, [], {
      cwd: process.cwd(), env: {}, stdio: ["pipe", "pipe", "pipe", "pipe"],
    }).catch((error: unknown) => error);
    try {
      await vi.waitFor(() => expect(spawnMock).toHaveBeenCalledTimes(2));
      // No microtask yield between chunks: line consumption cannot hide unbounded
      // queued data. This never starts an OS process or targets a real PID.
      for (let index = 0; index < 100; index += 1) helper.stdout.emit("data", "COMPILED\n");
      expect(helper.stdin.writableEnded).toBe(true);
    } finally {
      helper.stdout.emit("end");
      await pending;
      spawnMock.mockRestore();
    }
  });

  test.skipIf(process.platform !== "win32").each(["single", "cumulative"])("never writes a launch after ATTACHED races a %s output overflow", async (mode) => {
    const helper = Object.assign(new EventEmitter(), {
      stdout: new PassThrough(), stderr: new PassThrough(), stdin: new PassThrough(),
      exitCode: null, signalCode: null, kill: vi.fn(),
    });
    const pipes = Array.from({ length: 8 }, () => new PassThrough());
    const supervisor = Object.assign(new EventEmitter(), {
      pid: 4242, kill: vi.fn(), exitCode: null, signalCode: null, stdio: pipes,
    });
    const spawnMock = vi.spyOn(childProcess, "spawn")
      .mockReturnValueOnce(supervisor as never).mockReturnValueOnce(helper as never);
    let settled = false;
    const pending = spawnProcessTree(process.execPath, [], {
      cwd: process.cwd(), env: {}, stdio: ["pipe", "pipe", "pipe", "pipe"],
    }).catch((error: unknown) => error).finally(() => { settled = true; });
    try {
      await vi.waitFor(() => expect(spawnMock).toHaveBeenCalledTimes(2));
      helper.stdout.emit("data", "STARTING\nCOMPILED\nPID_ACCEPTED\n");
      await new Promise<void>((resolveTurn) => setTimeout(resolveTurn, 0));
      helper.stdout.emit("data", "ATTACHED\n");
      // The waiter has its ATTACHED value, but no promise continuation has run.
      if (mode === "single") helper.stdout.emit("data", "x".repeat(65));
      else for (let index = 0; index < 10; index += 1) helper.stdout.emit("data", "COMPILED\n");
      await vi.waitFor(() => expect(settled || pipes[4]!.readableLength > 0).toBe(true));
      expect(pipes[4]!.readableLength).toBe(0);
      expect(pipes[5]!.readableLength).toBe(0);
      expect(await pending).toBeInstanceOf(Error);
    } finally {
      helper.emit("close");
      pipes[6]!.end("REFUSED\n");
      await pending;
      spawnMock.mockRestore();
    }
  });

  test.skipIf(process.platform !== "win32")("live helper exposes compilation and accepted PID stages without disclosing input", async () => {
    const powershell = resolveWindowsPowerShellExecutable();
    expect(powershell).toBeDefined();
    const launch = windowsJobHelperArgv(powershell!);
    const helper = spawn(launch.command, [...launch.args], { shell: false, windowsHide: true, stdio: "pipe" });
    let output = "";
    let helperClosed = false;
    helper.stdout.setEncoding("utf8");
    helper.stdout.on("data", (chunk: string) => { output += chunk; });
    helper.stderr.resume();
    helper.stdin.on("error", () => undefined);
    const closed = new Promise<void>((resolveClosed, reject) => {
      helper.once("close", () => { helperClosed = true; resolveClosed(); });
      helper.once("error", reject);
    });
    // A valid UInt32 PID pair with a nonexistent target reaches native assignment
    // but cannot attach. No real process is placed in a kill-on-close Job.
    helper.stdin.end(`4294967295 ${process.pid}\n`);
    try {
      await closed;
      expect(output.replace(/\r/g, "")).toBe("STARTING\nCOMPILED\nPID_ACCEPTED\n");
    } finally {
      if (!helperClosed && helper.exitCode === null && helper.signalCode === null) forceFixtureCleanup(helper.pid);
    }
  }, 30_000);
});

describe("process-tree cleanup", () => {
  test.each(["linux", "darwin", "win32"] as const)(
    "launches a hidden distinct process group on %s without a shell",
    (platform) => {
      expect(processTreeSpawnOptions(platform)).toEqual({
        detached: platform !== "win32",
        shell: false,
        windowsHide: true,
      });
    },
  );

  test("plans POSIX group SIGTERM, a bounded grace, SIGKILL, and verification", () => {
    expect(processTreeTerminationPlan("linux", 4312, {
      graceMs: 75,
      verifyMs: 225,
    })).toEqual([
      { kind: "signal-group", pid: -4312, signal: "SIGTERM" },
      { kind: "wait-until-exited", timeoutMs: 75 },
      { kind: "signal-group", pid: -4312, signal: "SIGKILL" },
      { kind: "verify-exited", timeoutMs: 225 },
    ]);
  });

  test("plans Windows taskkill with exact argv, no shell, a hidden window, wait, and verification", () => {
    const taskkill = "C:\\Windows\\System32\\taskkill.exe";
    expect(processTreeTerminationPlan("win32", 4312, {
      graceMs: 75,
      taskkillExecutable: taskkill,
      verifyMs: 225,
    })).toEqual([
      {
        args: ["/PID", "4312", "/T"],
        command: taskkill,
        kind: "taskkill",
        options: { shell: false, windowsHide: true },
        timeoutMs: 75,
      },
      { kind: "wait-until-exited", timeoutMs: 75 },
      { kind: "close-job", timeoutMs: 225 },
      { kind: "verify-exited", timeoutMs: 225 },
    ]);
  });

  test("uses one constant encoded no-profile PowerShell helper with no pid or provider material", () => {
    const powershell = "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe";
    const argv = windowsJobHelperArgv(powershell);
    expect(argv.command).toBe(powershell);
    expect(argv.args.slice(0, 3)).toEqual(["-NoLogo", "-NoProfile", "-NonInteractive"]);
    expect(argv.args.at(-2)).toBe("-EncodedCommand");
    const source = Buffer.from(argv.args.at(-1)!, "base64").toString("utf16le");
    expect(source).toContain("JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE");
    expect(source).toContain("AssignProcessToJobObject");
    // #428: the helper announces its host start BEFORE the Add-Type compile, so the
    // two cold costs are separately observable phases rather than one opaque wait.
    expect(source).toContain("STARTING");
    expect(source.indexOf("STARTING")).toBeLessThan(source.indexOf("Add-Type"));
    expect(source).toContain("ATTACHED");
    expect(source).toContain("WATCHING");
    expect(source).toContain("WaitForMultipleObjects");
    expect(source).toContain("GetExitCodeProcess");
    expect(source).toContain("CreateEvent");
    expect(source).toContain("StartStopReader");
    expect(source).toContain("EXIT ");
    expect(argv.options).toEqual({ shell: false, windowsHide: true });
    for (const forbidden of ["4312", "task-secret-sentinel", "dummy-openai-value", "OPENAI_API_KEY"]) {
      expect(JSON.stringify(argv)).not.toContain(forbidden);
    }
  });

  // Issue #428, AC-1/AC-3. Cold Windows admission pays two independent costs before
  // the Job holder can report ATTACHED - PowerShell host start, then the one-time
  // Add-Type C# compile of the constant helper - and the pre-#428 code covered BOTH
  // with a single flat 15 s window, which blew twice under runner contention on
  // 2026-07-24. The budget is now a NO-PROGRESS budget per observable phase plus a
  // hard absolute ceiling, so a slow-but-advancing helper is admitted while a silent
  // one still fails closed. Measured phase costs on an idle Windows 11 dev box over
  // 6 runs: host start 107-127 ms, Add-Type compile 101-158 ms. 15 s per phase is
  // ~100x the slower of the two, and 30 s bounds the whole handshake.
  test("bounds Windows Job-holder admission by observable progress rather than one flat window", () => {
    const source = readFileSync(new URL("../src/process-tree.ts", import.meta.url), "utf8");
    expect(source).toContain("const WINDOWS_JOB_READY_IDLE_MS = 15_000;");
    expect(source).toContain("const WINDOWS_JOB_READY_CEILING_MS = 30_000;");
    expect(source).toContain("normalizedTiming({ verifyMs: WINDOWS_JOB_READY_IDLE_MS })");
    expect(source).toContain("awaitProgressTokens(readOutputLine, WINDOWS_JOB_READY_TOKENS");
    expect(source).not.toContain("const WINDOWS_JOB_READY_MS");
  });

  // AC-2 of #428 for the containment path: a deliberately slowed handshake is
  // admitted, and a genuinely silent one still fails inside a bounded window with
  // the stalled phase named. Both are driven off a fake clock, so proving a 25 s
  // "slow runner" costs the suite no real time at all.
  test("admits a handshake slower than one flat window while every phase keeps advancing", async () => {
    const handshake = scriptedHandshake([
      { afterMs: 12_000, line: "STARTING" },
      { afterMs: 13_000, line: "ATTACHED" },
    ]);
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], {
      idleMs: 15_000, ceilingMs: 30_000, now: handshake.now,
    })).resolves.toEqual({ state: "ready" });
    // 25 s total - the pre-#428 single 15 s window would have refused this.
    expect(handshake.clock.value).toBe(25_000);
  });

  test.each([
    ["a helper that never starts", [] as const, "STARTING", 15_000, 15_000],
    ["a helper that starts and then goes silent", [{ afterMs: 900, line: "STARTING" }] as const, "ATTACHED", 15_000, 15_900],
    ["a helper that emits the wrong token", [{ afterMs: 20, line: "REFUSED" }] as const, "STARTING", 20, 20],
  ])("stalls on %s with the phase and wait named", async (_name, script, phase, waitedMs, totalMs) => {
    const handshake = scriptedHandshake(script);
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], {
      idleMs: 15_000, ceilingMs: 30_000, now: handshake.now,
    })).resolves.toEqual({ state: "stalled", phase, waitedMs });
    expect(handshake.clock.value).toBe(totalMs);
  });

  test("never waits past its absolute ceiling even while progress keeps arriving", async () => {
    const handshake = scriptedHandshake([
      { afterMs: 15_000, line: "STARTING" },
      { afterMs: 15_000, line: "ATTACHED" },
    ]);
    await expect(awaitProgressTokens(handshake.readLine, ["STARTING", "ATTACHED"], {
      idleMs: 15_000, ceilingMs: 20_000, now: handshake.now,
    })).resolves.toEqual({ state: "stalled", phase: "ATTACHED", waitedMs: 5_000 });
    expect(handshake.clock.value).toBe(20_000);
  });

  test("refuses an unusable progress budget instead of waiting unbounded", async () => {
    for (const options of [
      { idleMs: 0, ceilingMs: 30_000 },
      { idleMs: 15_000, ceilingMs: 0 },
      { idleMs: 40_000, ceilingMs: 30_000 },
    ]) {
      await expect(awaitProgressTokens(async () => undefined, ["STARTING"], options)).rejects.toThrow("bounded");
    }
  });

  test("a stalled Job-holder refusal names its phase and keeps a machine-readable reason", () => {
    const message = `${WINDOWS_JOB_ATTACH_REFUSAL} (stalled at ATTACHED after 30000ms): ready-timeout`;
    expect(isWindowsJobAttachRefusal(new Error(message))).toBe(true);
    expect(windowsRefusalReasonFromMessage(message)).toBe("ready-timeout");
    expect(isWindowsJobAttachRefusal(new Error("Windows contained Pi launch was refused: ready-timeout"))).toBe(false);
  });

  test("orders canonical PowerShell 7 before the stock Windows fallback without PATH lookup", () => {
    expect(windowsPowerShellCandidatePaths("C:\\Windows")).toEqual([
      "C:\\Program Files\\PowerShell\\7\\pwsh.exe",
      "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    ]);
  });

  test.skipIf(process.platform !== "win32")("selects the installed canonical helper despite a PATH shadow", () => {
    const previous = process.env.PATH;
    process.env.PATH = "C:\\fixture\\attacker-bin";
    try {
      const resolved = resolveWindowsPowerShellExecutable();
      expect(resolved).toBeDefined();
      expect(resolved!.toLowerCase()).not.toContain("attacker-bin");
      const modern = windowsPowerShellCandidatePaths(process.env.SystemRoot ?? process.env.WINDIR!)[0];
      if (existsSync(modern)) expect(resolved!.toLowerCase()).toBe(realpathSync(modern).toLowerCase());
      else expect(win32.basename(resolved!).toLowerCase()).toBe("powershell.exe");
    } finally {
      if (previous === undefined) delete process.env.PATH;
      else process.env.PATH = previous;
    }
  });

  test("launches only the canonical inert supervisor before Job attachment with a minimal environment", () => {
    const node = "C:\\Program Files\\nodejs\\node.exe";
    const supervisor = "C:\\fixture\\ca-pi\\helpers\\windows-supervisor.js";
    const previousNodeOptions = process.env.NODE_OPTIONS;
    const previousOpenAiKey = process.env.OPENAI_API_KEY;
    process.env.NODE_OPTIONS = '--import=data:text/javascript,console.error("task-secret-sentinel")';
    process.env.OPENAI_API_KEY = "dummy-openai-value";
    let launch: ReturnType<typeof windowsSupervisorLaunchPlan>;
    try {
      launch = windowsSupervisorLaunchPlan(node, supervisor);
    } finally {
      if (previousNodeOptions === undefined) delete process.env.NODE_OPTIONS;
      else process.env.NODE_OPTIONS = previousNodeOptions;
      if (previousOpenAiKey === undefined) delete process.env.OPENAI_API_KEY;
      else process.env.OPENAI_API_KEY = previousOpenAiKey;
    }
    expect(launch).toMatchObject({
      command: node,
      args: [supervisor],
      control: "START\n",
      options: {
        cwd: "C:\\fixture\\ca-pi\\helpers",
        detached: false,
        shell: false,
        stdio: ["pipe", "pipe", "pipe", "pipe", "pipe", "pipe", "pipe", "pipe"],
        windowsHide: true,
      },
    });
    const exposed = JSON.stringify({ args: launch.args, env: launch.options.env, control: launch.control });
    expect(exposed).not.toContain("task-secret-sentinel");
    expect(exposed).not.toContain("dummy-openai-value");
    expect(exposed).not.toContain("dummy-farm-value");
  });

  test("retries only an exact Job-holder admission refusal once with bounded diagnostics", async () => {
    const failures: string[] = [];
    const check = async (name: string, probe: () => Promise<void>): Promise<void> => {
      try {
        await probe();
      } catch (error) {
        failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
      }
    };

    await check("matching refusal then success", async () => {
      let attempts = 0;
      const result = await runWindowsLaunchAdmissionProof(async () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error("Windows Job Object holder refused containment: ready-timeout");
        }
        return "started";
      });
      expect(result).toBe("started");
      expect(attempts).toBe(2);
    });

    await check("second matching refusal is terminal", async () => {
      let attempts = 0;
      let observed: unknown;
      try {
        await runWindowsLaunchAdmissionProof(async () => {
          attempts += 1;
          throw new Error("Windows Job Object holder refused containment: ready-timeout");
        });
      } catch (error) {
        observed = error;
      }
      expect(attempts).toBe(2);
      expect(observed).toBeInstanceOf(Error);
      expect((observed as Error).message).toContain("attempt 1 code=job-attach-refused");
      expect((observed as Error).message).toContain("attempt 2 code=job-attach-refused");
    });

    await check("nonmatching admission failure is not retried", async () => {
      const refusal = new Error("Windows contained Pi launch was refused: ready-timeout");
      let attempts = 0;
      let observed: unknown;
      try {
        await runWindowsLaunchAdmissionProof(async () => {
          attempts += 1;
          throw refusal;
        });
      } catch (error) {
        observed = error;
      }
      expect(attempts).toBe(1);
      expect(observed).toBe(refusal);
    });

    await check("post-admission failure is not retried", async () => {
      let attempts = 0;
      const runProof = async (): Promise<void> => {
        await runWindowsLaunchAdmissionProof(async () => {
          attempts += 1;
          return "started";
        });
        throw new Error("containment-ready proof failed");
      };
      await expect(runProof()).rejects.toThrow("containment-ready proof failed");
      expect(attempts).toBe(1);
    });

    await check("two-attempt diagnostics are bounded", async () => {
      let observed: unknown;
      try {
        await runWindowsLaunchAdmissionProof(async () => {
          throw new Error(`Windows Job Object holder refused containment: ${"x".repeat(10_000)}`);
        });
      } catch (error) {
        observed = error;
      }
      expect(observed).toBeInstanceOf(Error);
      expect((observed as Error).message).toContain("[truncated]");
      expect((observed as Error).message.length).toBeLessThan(1_300);
    });

    expect(failures).toEqual([]);
  });

  test.runIf(process.platform === "win32")("starts Node with scrubbed controls and delivers them only to the contained child", async () => {
    const supervisorSentinel = "UNCONTAINED_SUPERVISOR_PRELOAD";
    const preloadSource = `if(process.argv[1]?.toLowerCase().endsWith("windows-supervisor.js"))console.error("${supervisorSentinel}");process.env.CA_PI_CHILD_PRELOAD="contained"`;
    const nodeOptions = `--import=data:text/javascript,${encodeURIComponent(preloadSource)}`;
    const child = await runWindowsLaunchAdmissionProof(() => spawnProcessTree(process.execPath, [
      "-e",
      'process.stdout.write(`${process.env.CA_PI_CHILD_PRELOAD}|${process.env.CA_PI_EXPLICIT}`);setInterval(() => {}, 1000)',
    ], {
      cwd: process.cwd(),
      env: {
        CA_PI_EXPLICIT: "delivered",
        NODE_OPTIONS: nodeOptions,
        SystemRoot: process.env.SystemRoot,
        TEMP: process.env.TEMP,
        TMP: process.env.TMP,
      },
      stdio: ["pipe", "pipe", "pipe", "pipe"],
    }));
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    try {
      await vi.waitFor(() => expect(stdout).toBe("contained|delivered"), { timeout: 10_000 });
      expect(stderr).not.toContain(supervisorSentinel);
    } finally {
      const cleanup = createProcessTreeCleanup(child, { graceMs: 250, verifyMs: 5_000 });
      await expect(cleanup.terminate("completed")).resolves.toMatchObject({ verified: true });
    }
  }, WINDOWS_LIVE_PROOF_TEST_TIMEOUT_MS);

  test("refuses invalid process identities, relative taskkill paths, and unbounded timing", () => {
    expect(() => processTreeTerminationPlan("linux", 0)).toThrow("positive integer");
    expect(() => processTreeTerminationPlan("win32", 42, {
      taskkillExecutable: "taskkill.exe",
    })).toThrow("absolute");
    expect(() => processTreeTerminationPlan("linux", 42, { graceMs: 0 })).toThrow("bounded");
    expect(() => processTreeTerminationPlan("linux", 42, { verifyMs: 60_001 })).toThrow("bounded");
  });

  test("bounds a wedged supervisor control write and destroys its pipe", async () => {
    const wedged = new Writable({ write() { /* Intentionally never acknowledges the write. */ } });
    const started = Date.now();
    await expect(writeBoundedControl(wedged, "START\n", 25)).resolves.toBe(false);
    expect(wedged.destroyed).toBe(true);
    expect(Date.now() - started).toBeLessThan(500);
  });

  test("supervisor fail-closed path delegates force cleanup to the Job boundary", () => {
    const source = readFileSync(new URL("../src/windows-supervisor.ts", import.meta.url), "utf8");
    expect(source).not.toContain('child.kill("SIGKILL")');
  });

  test("rejected Job helpers receive bounded canonical subtree cleanup", () => {
    const source = readFileSync(new URL("../src/process-tree.ts", import.meta.url), "utf8");
    expect(source).toContain('spawnSync(taskkill, ["/PID", String(helper.pid), "/T", "/F"]');
    expect(source).toContain("timeout: WINDOWS_HELPER_CLEANUP_MS");
    expect(source).toContain("result.error === undefined && result.status === 0");
    expect(source).toContain("cwd: dirname(taskkill)");
    expect(source).toContain("env: helperEnvironment(taskkill)");
  });

  test("never sends subtree cleanup to an already-exited helper PID", () => {
    expect(windowsHelperNeedsTermination({ pid: 42, exitCode: null, signalCode: null })).toBe(true);
    expect(windowsHelperNeedsTermination({ pid: 42, exitCode: 0, signalCode: null })).toBe(false);
    expect(windowsHelperNeedsTermination({ pid: 42, exitCode: null, signalCode: "SIGTERM" })).toBe(false);
    expect(windowsHelperNeedsTermination({ pid: undefined, exitCode: null, signalCode: null })).toBe(false);
    expect(windowsHelperNeedsTermination({ pid: 42, exitCode: null, signalCode: null }, true)).toBe(false);
  });

  test("returns bounded refusal results for every cleanup trigger without throwing", async () => {
    expect(PROCESS_TREE_CLEANUP_REASONS).toEqual([
      "timeout",
      "cancelled",
      "protocol_error",
      "protocol_overflow",
      "startup_failure",
      "parent_shutdown",
      "completed",
      "session_switch",
      "shutdown",
      "unload",
      "fatal_error",
    ]);
    for (const reason of PROCESS_TREE_CLEANUP_REASONS) {
      const started = Date.now();
      const cleanup = createProcessTreeCleanup({ pid: undefined });
      await expect(cleanup.ready()).resolves.toBe(false);
      const result = await cleanup.terminate(reason);
      expect(result).toEqual({
        escalated: false,
        reason,
        state: "refused",
        verified: false,
      });
      expect(Date.now() - started).toBeLessThan(1_000);
    }
  });

  test.skipIf(process.platform === "win32")("is idempotent and bounds cleanup of a real POSIX child", async () => {
    const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {
      ...processTreeSpawnOptions(process.platform),
      stdio: "ignore",
    });
    try {
      await waitForSpawn(child);
      const cleanup = createProcessTreeCleanup(child, {
        graceMs: 250,
        pollMs: 10,
        verifyMs: 2_000,
      });
      await expect(cleanup.ready()).resolves.toBe(true);
      const first = cleanup.terminate("timeout");
      const second = cleanup.terminate("cancelled");
      const [left, right] = await Promise.all([first, second]);
      expect(left).toBe(right);
      expect(left).toMatchObject({ reason: "timeout", state: "terminated", verified: true });
      expect(await cleanup.terminate("parent_shutdown")).toBe(left);
    } finally {
      forceFixtureCleanup(child.pid);
    }
  }, 10_000);

  test("exposes one minimal child plus cleanup handle", async () => {
    const child = spawn(process.execPath, ["-e", "process.exit(0)"], {
      ...processTreeSpawnOptions(process.platform), stdio: ["pipe", "pipe", "pipe", "pipe"],
    });
    const spawnTree = vi.fn(async () => child as never);
    const cleanup = { ready: async () => true, terminate: vi.fn() };
    const createCleanup = vi.fn(() => cleanup as never);
    const managed = await openProcessTree(process.execPath, ["-e", "process.exit(0)"], {
      cwd: process.cwd(), env: {}, stdio: ["pipe", "pipe", "pipe", "pipe"],
    }, { spawnTree, createCleanup });
    expect(managed).toEqual({ child, cleanup });
    expect(spawnTree).toHaveBeenCalledOnce();
    expect(createCleanup).toHaveBeenCalledWith(child);
  });
});
