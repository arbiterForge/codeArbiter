import { spawn, spawnSync } from "node:child_process";
import { Writable } from "node:stream";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { win32 } from "node:path";

import { describe, expect, test, vi } from "vitest";

import {
  PROCESS_TREE_CLEANUP_REASONS,
  WINDOWS_SUPERVISOR_REFUSAL_REASONS,
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
// The live proof may consume two bounded 15-second admission windows, then its
// 10-second child-output wait and 5.25-second cleanup window. Keep Vitest's
// ceiling outside those product bounds so it observes the proof result instead
// of racing a valid retry on a loaded Windows runner.
const WINDOWS_LIVE_PROOF_TEST_TIMEOUT_MS = 60_000;

function isWindowsJobAttachRefusal(error: unknown): error is Error {
  return error instanceof Error && (
    error.message === WINDOWS_JOB_ATTACH_REFUSAL
    || error.message.startsWith(`${WINDOWS_JOB_ATTACH_REFUSAL}:`)
  );
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

  test("reserves a bounded fifteen-second cold admission budget before any Windows child starts", () => {
    const source = readFileSync(new URL("../src/process-tree.ts", import.meta.url), "utf8");
    expect(source).toContain("const WINDOWS_JOB_READY_MS = 15_000;");
    expect(source).toContain("normalizedTiming({ verifyMs: WINDOWS_JOB_READY_MS })");
    expect(source).toContain("Math.min(WINDOWS_JOB_READY_MS, timing.verifyMs)");
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
