/**
 * windows-supervisor.test.ts - executes the real supervisor helper (built by build.mjs to
 * ../../helpers/windows-supervisor.js) as a child process, wired exactly the way
 * process-tree.ts's windowsSupervisorLaunchPlan() wires it: fd4 = launch record, fd5 = control
 * record, fd6 = status line out, fd7 = parent-death leash.
 *
 * The supervisor module runs top-level await against fixed fds (4-7) the instant it is
 * imported, so it cannot be imported in-process without racing the current Node process's own
 * fd table and possibly calling process.exit(70) inside the test worker. Driving it as a real
 * child process is the only harness that exercises parseLaunch, boundedRead, and the fail-closed
 * spawn wiring without risking the test runner itself. This mirrors the black-box convention
 * process-tree.test.ts already uses for the Windows Job Object PowerShell helper.
 */
import { spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { Duplex, Readable, Writable } from "node:stream";

import { describe, expect, test } from "vitest";

const SUPERVISOR_HELPER = new URL("../../helpers/windows-supervisor.js", import.meta.url);
const RUN_TIMEOUT_MS = 10_000;

interface SupervisorRun {
  readonly statusLine: string;
  readonly child: ChildProcessWithoutNullStreams;
}

/** Spawns the built supervisor helper with the same 8-slot stdio shape
 * windowsSupervisorLaunchPlan() uses, writes the given launch/control bytes, and resolves with
 * whatever single line the supervisor emits on its status pipe (fd6). */
function runSupervisor(launchBytes: string, controlBytes: string): Promise<SupervisorRun> {
  const child = spawn(process.execPath, [SUPERVISOR_HELPER.pathname.replace(/^\/([A-Za-z]:)/, "$1")], {
    stdio: ["ignore", "ignore", "ignore", "pipe", "pipe", "pipe", "pipe", "pipe"],
    windowsHide: true,
  }) as unknown as ChildProcessWithoutNullStreams;

  const stdio = child.stdio as unknown as ReadonlyArray<Duplex>;
  const launchPipe = stdio[4] as unknown as Writable;
  const controlPipe = stdio[5] as unknown as Writable;
  const statusPipe = stdio[6] as unknown as Readable;
  // fd7 (parent leash): left open and untouched, exactly like a live parent would hold it open
  // for the supervisor's whole lifetime. Closing it would itself trigger fail-closed exit.
  void stdio[7];

  // Resolve on the first complete "<line>\n" rather than waiting for the pipe's "end"/"close"
  // event. This is latency hygiene, not a hang workaround: the supervisor now exits reliably
  // (see the exit-code-70 test below), but its own process teardown is still a separate async
  // step from the status write completing, so waiting for stream "end" here would make every
  // test in this file pay that teardown latency instead of resolving as soon as the protocol
  // line itself is fully readable.
  const statusLine = new Promise<string>((resolve, reject) => {
    let text = "";
    const timer = setTimeout(() => reject(new Error("supervisor status pipe timed out")), RUN_TIMEOUT_MS);
    statusPipe.setEncoding("utf8");
    statusPipe.on("data", (chunk: string) => {
      text += chunk;
      if (text.includes("\n")) { clearTimeout(timer); resolve(text); }
    });
    statusPipe.once("end", () => { clearTimeout(timer); resolve(text); });
    statusPipe.once("error", (error) => { clearTimeout(timer); reject(error); });
  });

  try { launchPipe.end(launchBytes, "utf8"); } catch { /* Child may already have exited on a fast refusal. */ }
  try { controlPipe.end(controlBytes, "utf8"); } catch { /* Child may already have exited on a fast refusal. */ }

  return statusLine.then((line) => Object.freeze({ statusLine: line, child }));
}

/** Best-effort cleanup: forces the supervisor (and anything it spawned) to exit so a slow or
 * STARTED-path run never leaks a process across tests. */
function killSupervisor(child: ChildProcessWithoutNullStreams): void {
  try { ((child.stdio as unknown as ReadonlyArray<Duplex>)[7] as unknown as Writable).destroy(); } catch { /* Already gone. */ }
  try { child.kill("SIGKILL"); } catch { /* Already gone. */ }
}

const validCommand = process.execPath;
const validCwd = process.platform === "win32" ? "C:\\Windows" : "/";
const missingCommand = process.platform === "win32"
  ? "C:\\__codearbiter_missing__\\ghost.exe"
  : "/__codearbiter_missing__/ghost";

function validLaunch(overrides: Partial<{
  command: string;
  args: readonly string[];
  cwd: string;
  env: readonly (readonly [string, string])[];
}> = {}): string {
  return JSON.stringify({
    command: validCommand,
    args: ["-e", "process.exit(0)"],
    cwd: validCwd,
    env: [],
    ...overrides,
  });
}

/** Runs the supervisor, asserts on its status line, and unconditionally kills it afterward as a
 * safety net (see the exit-code-70 test below — the supervisor is now expected to exit on its
 * own, but a test failure should still never leak a live process). */
async function expectStatusLine(launchBytes: string, controlBytes: string, expected: string | RegExp): Promise<void> {
  const run = await runSupervisor(launchBytes, controlBytes);
  try {
    if (typeof expected === "string") expect(run.statusLine).toBe(expected);
    else expect(run.statusLine).toMatch(expected);
  } finally {
    killSupervisor(run.child);
  }
}

describe("windows-supervisor helper (real child process)", () => {
  test("STARTED <pid>: spawns the real target process and reports its pid", async () => {
    await expectStatusLine(validLaunch(), "START\n", /^STARTED [1-9][0-9]*\n$/u);
  });

  test("REFUSED launch-malformed: unparsable JSON launch record", async () => {
    await expectStatusLine("not json at all", "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: launch record missing a required field", async () => {
    await expectStatusLine(JSON.stringify({ command: validCommand, args: [] }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: launch record with an unexpected extra field", async () => {
    await expectStatusLine(
      JSON.stringify({ command: validCommand, args: [], cwd: validCwd, extra: true }),
      "START\n",
      "REFUSED launch-malformed\n",
    );
  });

  test("REFUSED launch-malformed: relative (non-absolute) command", async () => {
    await expectStatusLine(validLaunch({ command: "node" }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: relative (non-absolute) cwd", async () => {
    await expectStatusLine(validLaunch({ cwd: "relative/dir" }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: args array over the 256-entry cap", async () => {
    await expectStatusLine(validLaunch({ args: Array.from({ length: 257 }, () => "x") }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: child environment over the 256-entry cap", async () => {
    const env = Array.from({ length: 257 }, (_, index) => [`K${index}`, "v"] as const);
    await expectStatusLine(validLaunch({ env }), "START\n", "REFUSED launch-malformed\n");
  });

  test.each([
    { env: [["", "value"]] as const },
    { env: [["KEY", "x".repeat(32_769)]] as const },
    { env: [["DUPLICATE", "left"], ["DUPLICATE", "right"]] as const },
  ])("REFUSED launch-malformed: invalid bounded child environment %#", async ({ env }) => {
    await expectStatusLine(validLaunch({ env }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: a single arg over the 262,144-byte cap", async () => {
    await expectStatusLine(validLaunch({ args: ["x".repeat(262_145)] }), "START\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED launch-malformed: control record is not the exact START token", async () => {
    await expectStatusLine(validLaunch(), "GO\n", "REFUSED launch-malformed\n");
  });

  test("REFUSED proto-overflow: launch payload exceeds the 3,145,728-byte bound", async () => {
    await expectStatusLine("x".repeat(3_145_729), "START\n", "REFUSED proto-overflow\n");
  });

  test("REFUSED proto-overflow: control payload exceeds the 16-byte bound", async () => {
    await expectStatusLine(validLaunch(), "x".repeat(17), "REFUSED proto-overflow\n");
  });

  test("REFUSED spawn-error: well-formed launch record naming a nonexistent absolute command", async () => {
    await expectStatusLine(validLaunch({ command: missingCommand }), "START\n", "REFUSED spawn-error\n");
  });

  // NOTE (report-only, not a defect): "pipe-unavailable" and "pid-invalid" are not reachable
  // from this black-box harness. The supervisor spawns its target with a hardcoded
  // stdio: ["pipe","pipe","pipe","pipe"], so child.stdin/stdout/stderr/stdio[3] are only ever
  // null if Node's own child_process internals fail to allocate a pipe, and child.pid is only
  // ever invalid if the OS assigns one after a successful "spawn" event, contrary to Node's own
  // contract. Exercising those two branches for real would require mocking node:child_process
  // internals, which risks widening windows-supervisor.ts's exported surface beyond what this
  // task authorizes. The parser side of these reason codes (process-tree.test.ts) is covered.

  // Fixed defect (was report-only; fix authorized and applied). windows-supervisor.ts used to
  // put parentLeash (fd7) into flowing mode via an fs.createReadStream(fd).resume() and never
  // stop reading it before exiting on the fail-closed path. On this platform that left a
  // permanently pending, uncancellable threadpool read in flight, which blocked
  // process.exit()'s shutdown path from ever actually terminating the process — confirmed via a
  // minimal repro (fs.createReadStream({fd}).resume() then process.exit()) and via this exact
  // test hanging before the fix. The fix: parentLeash is now a node:net Socket over the same fd
  // (overlapped/IOCP I/O instead of a blocking threadpool read), so a still-pending read never
  // blocks shutdown; failClosed() also destroys all four fd streams before exiting, for
  // defense in depth. Fixing this also surfaced a second, previously-masked bug: a redundant
  // child.once("error", failClosed) listener could win a race against the outer catch block's
  // REFUSED-line write once exit became fast and reliable (harmless while exit hung, since the
  // write always finished first) — removed in favor of routing every spawn-time error through
  // the awaited promise's reject(), which the outer catch already handles correctly.
  test("the supervisor process self-terminates with exit code 70 after a refusal", async () => {
    const run = await runSupervisor("not json at all", "START\n");
    try {
      expect(run.statusLine).toBe("REFUSED launch-malformed\n");
      const exitCode = await new Promise<number | null | "timeout">((resolve) => {
        if (run.child.exitCode !== null) { resolve(run.child.exitCode); return; }
        run.child.once("exit", (code) => resolve(code));
        setTimeout(() => resolve("timeout"), 3_000);
      });
      expect(exitCode).toBe(70);
    } finally {
      // Safety net: kills the supervisor if the exit assertion above ever fails for any reason
      // (e.g. a future regression), so a broken test run still never leaks a live process.
      killSupervisor(run.child);
    }
  }, 5_000);
});
