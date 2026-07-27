/**
 * Unit tests for exec.ts — the low-level process/shell layer.
 *
 * farm.unit.test.ts already pins `numEnv` (all four arms), `scrubbedEnv`, the
 * real-hang timeout, and treeKill's success path with a genuine grandchild.
 * This file does not restate any of that. What it adds is the CONTAINMENT
 * FAILURE half, which the existing suite cannot reach: every one of those tests
 * arranges a kill that WORKS, and the interesting branches are the ones taken
 * when it does not.
 *
 * That half is reachable deterministically because `run()` takes its killer as
 * a parameter — `kill: TreeKiller = treeKill` — documented in the source as
 * "the injectable containment seam ... so the 'cleanup could not be verified'
 * branch is testable without arranging a genuinely unkillable process (which is
 * not portable)". Using it means no real hang, no timing race, and a result
 * that is identical on every platform.
 */
import { afterEach, describe, expect, it } from "vitest";
import type { ChildProcess } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  EXIT_TIMEOUT,
  EXIT_TIMEOUT_UNCLEAN,
  readWorktreeFile,
  run,
  taskkillPath,
  treeKill,
} from "./exec.ts";

// A command that never exits, so the timeout is always what resolves the run.
const HANG = [process.execPath, ["-e", "setInterval(() => {}, 1000);"]] as const;

describe("run() — containment failure is distinguishable from a clean timeout", () => {
  it("reports EXIT_TIMEOUT and no cleanupFailed when the tree is verified gone", async () => {
    // The injected killer stands in for a VERIFIED kill. Paired with the case
    // below, this is what makes the two outcomes distinguishable rather than
    // both being "non-zero".
    const r = await run(HANG[0], [...HANG[1]], undefined, {}, 60, async () => ({ ok: true }));

    expect(r.code).toBe(EXIT_TIMEOUT);
    expect(r.timedOut).toBe(true);
    expect(r.cleanupFailed).toBeUndefined();
    expect(r.stderr).toContain("exceeded 60ms wall-clock timeout");
    expect(r.stderr).not.toContain("CLEANUP UNVERIFIED");
  });

  it("reports EXIT_TIMEOUT_UNCLEAN and carries the reason when the tree is NOT verified gone", async () => {
    // #395's whole point: a containment failure is not an ordinary timeout.
    // Descendants may still be executing model-authored commands against the
    // worktree, so it gets its own exit code and its own loud note rather than
    // hiding inside a clean-looking 124.
    const r = await run(HANG[0], [...HANG[1]], undefined, {}, 60, async () => ({
      ok: false,
      detail: "pid 4242 still present after taskkill",
    }));

    expect(r.code).toBe(EXIT_TIMEOUT_UNCLEAN);
    expect(r.code).not.toBe(EXIT_TIMEOUT);
    expect(r.timedOut).toBe(true);
    expect(r.cleanupFailed).toBe(true);
    expect(r.stderr).toContain("CLEANUP UNVERIFIED");
    // The DETAIL must survive into the note — a bare "unverified" is not
    // actionable, and this string is what an operator reads on a report.
    expect(r.stderr).toContain("pid 4242 still present after taskkill");
    expect(r.stderr).toContain("Descendants may still be running against this worktree");
    // ...and the containment warning is APPENDED to the timeout line, not
    // substituted for it. Both facts matter: what happened (the command blew its
    // wall clock) and what could not be established (that its tree is gone).
    expect(r.stderr).toContain("exceeded 60ms wall-clock timeout");
    expect(r.stderr).toContain("FARM_GATE_TIMEOUT_MS");
  });

  it("still says CLEANUP UNVERIFIED when the killer gives no detail", async () => {
    const r = await run(HANG[0], [...HANG[1]], undefined, {}, 60, async () => ({ ok: false }));
    expect(r.code).toBe(EXIT_TIMEOUT_UNCLEAN);
    expect(r.stderr).toContain("no detail");
  });

  it("merges the timeout note into `out` as well as `stderr`, leaving stdout clean", async () => {
    // Consumers read `out` (merged) or `stdout` (parsing contexts — see #91,
    // where a stderr line parsed as a file path tripped a false drift). The note
    // must reach the merged view without contaminating the parsed one.
    const r = await run(HANG[0], [...HANG[1]], undefined, {}, 60, async () => ({ ok: true }));
    expect(r.out).toContain("wall-clock timeout");
    expect(r.stdout).toBe("");
  });

  it("does not resolve twice when the child's own close races the timeout kill", async () => {
    // The kill CAUSES a close event. Without the `killing` flag set before the
    // awaited kill, that close would win the race and resolve an ordinary exit
    // result — discarding both the timedOut tag and the cleanup verdict.
    // A slow killer widens the window the flag has to cover.
    const r = await run(HANG[0], [...HANG[1]], undefined, {}, 60, async (child) => {
      child.kill("SIGKILL");
      await new Promise((resolve) => setTimeout(resolve, 120));
      return { ok: false, detail: "slow verification" };
    });

    expect(r.code).toBe(EXIT_TIMEOUT_UNCLEAN);
    expect(r.timedOut).toBe(true);
    expect(r.stderr).toContain("slow verification");
  });
});

describe("run() — a child killed by a signal", () => {
  it("reports code 1 when the close event carries no exit code", async () => {
    // A signal-terminated child closes with a null code. `code ?? 1` is what
    // stops that reaching callers as a FALSY value — every consumer branches on
    // `code !== 0`, so a null defaulting to 0 would read as success for a
    // process that was killed.
    const r = await run(process.execPath, ["-e", "process.kill(process.pid, 'SIGKILL');"], undefined, {}, 0);

    expect(r.code).toBe(1);
    expect(r.timedOut).toBeUndefined();
  }, 20000);
});

describe("run() — spawn failure", () => {
  it("resolves code 1 with the error text rather than rejecting", async () => {
    // Callers branch on `code !== 0`; a rejection here would take down the
    // worker instead of escalating the task.
    const r = await run("definitely-not-a-real-binary-xyz", [], undefined, {}, 0);

    expect(r.code).toBe(1);
    expect(r.stdout).toBe("");
    expect(r.stderr).toMatch(/ENOENT|not.*recognized|spawn/i);
    expect(r.out).toBe(r.stderr);
    expect(r.timedOut).toBeUndefined();
  });
});

describe("treeKill() — nothing to contain", () => {
  it("reports success when the spawn never produced a pid", async () => {
    // No pid means the spawn itself failed, so there is no tree. Reporting
    // ok:false here would turn every failed spawn into a containment incident.
    const k = await treeKill({ pid: undefined } as unknown as ChildProcess);
    expect(k).toEqual({ ok: true, detail: "child never started" });
  });
});

describe("treeKill() — the tree cannot be confirmed gone", () => {
  // The half the existing suite cannot reach: every test in farm.unit.test.ts
  // arranges a kill that WORKS. These arrange one that does not, and assert the
  // module says so rather than reporting a clean containment.
  //
  // The subject is a real, living process paired with a `kill` that does
  // nothing — so the pid genuinely stays present and `waitUntilGone` genuinely
  // times out. A short budget keeps it fast.
  let hanger: ChildProcess | undefined;

  afterEach(() => {
    hanger?.kill("SIGKILL");
    hanger = undefined;
  });

  async function livingPidWithInertKill(): Promise<ChildProcess> {
    const { spawn } = await import("node:child_process");
    hanger = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000);"], { stdio: "ignore" });
    await new Promise((resolve) => setTimeout(resolve, 100));
    return { pid: hanger.pid, kill: () => true } as unknown as ChildProcess;
  }

  it.skipIf(process.platform !== "win32")(
    "reports ok:false with the pid and budget when taskkill cannot be run",
    async () => {
      // Point taskkillPath at somewhere with no taskkill.exe, so the spawn
      // fails, the direct-kill fallback is inert, and the pid outlives the
      // verification budget. This is the containment incident #395 exists to
      // surface: a caller must be able to tell "we killed it" from "we could
      // not prove we killed it".
      // ORDER MATTERS: the subject process is spawned BEFORE SystemRoot is
      // repointed. Windows needs a valid SystemRoot to create a process at all,
      // so a child spawned after the override dies immediately — and treeKill
      // then reports a perfectly truthful ok:true about an already-dead pid,
      // which is not the branch under test.
      const subject = await livingPidWithInertKill();
      const savedRoot = process.env.SystemRoot;
      process.env.SystemRoot = path.join("Z:", "no-such-windows");
      try {
        const k = await treeKill(subject, { budgetMs: 150 });
        expect(k.ok).toBe(false);
        expect(k.detail).toContain(String(hanger!.pid));
        expect(k.detail).toContain("150ms");
        // The taskkill failure reason rides along — without it an operator sees
        // "still present" and has no idea the killer never even started.
        expect(k.detail).toMatch(/taskkill/i);
      } finally {
        if (savedRoot === undefined) delete process.env.SystemRoot;
        else process.env.SystemRoot = savedRoot;
      }
    },
  );

  it.skipIf(process.platform === "win32")(
    "reports ok:false naming the process group when SIGKILL leaves a live member",
    async () => {
      // The POSIX mirror. The child is not a group leader here, so the
      // group signal throws and is swallowed, the direct kill is inert, and the
      // pid survives the budget.
      const k = await treeKill(await livingPidWithInertKill(), { budgetMs: 150 });
      expect(k.ok).toBe(false);
      expect(k.detail).toContain(String(hanger!.pid));
      expect(k.detail).toContain("150ms");
      expect(k.detail).toMatch(/descendants may still be running/i);
    },
  );

  it("reports ok:true once the pid really is gone, even on a slow verify", async () => {
    // The other side of the same budget: a process that IS dead must verify
    // clean rather than waiting out the deadline.
    const { spawn } = await import("node:child_process");
    const doomed = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000);"], { stdio: "ignore" });
    await new Promise((resolve) => setTimeout(resolve, 100));

    const k = await treeKill(doomed, { budgetMs: 4000 });
    expect(k.ok).toBe(true);
    expect(k.detail).toBeUndefined();
  }, 20000);
});

describe("taskkillPath() — absolute resolution", () => {
  const saved = { root: process.env.SystemRoot, windir: process.env.windir };
  afterEach(() => {
    if (saved.root === undefined) delete process.env.SystemRoot;
    else process.env.SystemRoot = saved.root;
    if (saved.windir === undefined) delete process.env.windir;
    else process.env.windir = saved.windir;
  });

  it("prefers SystemRoot", () => {
    process.env.SystemRoot = path.join("D:", "AltWindows");
    expect(taskkillPath()).toBe(path.join("D:", "AltWindows", "System32", "taskkill.exe"));
  });

  it("falls back to windir when SystemRoot is unset", () => {
    delete process.env.SystemRoot;
    process.env.windir = path.join("E:", "OtherWindows");
    expect(taskkillPath()).toBe(path.join("E:", "OtherWindows", "System32", "taskkill.exe"));
  });

  it("falls back to a literal C:\\Windows when neither is set", () => {
    // The last resort must stay ABSOLUTE. An unqualified `taskkill` would be
    // resolved through %PATH% during the containment step — the privilege
    // hazard this function exists to remove.
    delete process.env.SystemRoot;
    delete process.env.windir;
    expect(taskkillPath()).toBe(path.join("C:\\Windows", "System32", "taskkill.exe"));
    // WIN32 semantics deliberately, whatever the host: this path is only ever
    // spawned on Windows, and POSIX `isAbsolute` reports false for a
    // drive-letter path — which made this assertion pass on Windows and fail on
    // the Linux runner CI actually uses.
    expect(path.win32.isAbsolute(taskkillPath())).toBe(true);
  });
});

describe("readWorktreeFile()", () => {
  let wt: string;
  afterEach(async () => {
    await rm(wt, { recursive: true, force: true });
  });

  it("returns the file text for a worktree-relative path", async () => {
    wt = await mkdtemp(path.join(tmpdir(), "farm-read-"));
    await writeFile(path.join(wt, "a.txt"), "contents\n", "utf8");
    expect(await readWorktreeFile(wt, "a.txt")).toBe("contents\n");
  });

  it("returns null rather than throwing on any read failure", async () => {
    // Every consumer (antiGamingCheck, mutationCheck, prompt enrichment) treats
    // null as "not available"; a throw would escalate a task for a missing file.
    wt = await mkdtemp(path.join(tmpdir(), "farm-read-"));
    expect(await readWorktreeFile(wt, "absent.txt")).toBeNull();
    // A directory is a read failure too, not a special case.
    expect(await readWorktreeFile(wt, ".")).toBeNull();
  });
});

/*
 * MUTANTS THAT SURVIVE, and why each is left alone. Measured, not assumed.
 *
 *  - `done()`'s `if (settled) return;` removed. Calling `resolve()` twice on a
 *    settled promise is a no-op in JS and the only other statement is a
 *    `clearTimeout` of an already-fired timer, so the mutant is observationally
 *    identical. An equivalent mutant; no test can kill it.
 *  - the `error` handler's `if (killing) return;` removed. Reaching it needs a
 *    spawn error to arrive DURING the timeout kill — a genuine race with no
 *    seam to force it. The sibling guard on `close` IS pinned (by the slow-kill
 *    case above), and it is the one that actually fires, because the kill causes
 *    the close.
 *  - `code ?? 1` weakened to `code ?? 0`. This one is PLATFORM-SPLIT, not
 *    unreachable: a signal-terminated child closes with a null code on POSIX,
 *    where the mutant dies, but Windows supplies a real exit code so the `??`
 *    never fires and the mutant lives. The test asserts the correct result on
 *    both; only Linux can execute the branch. Same split as #521, and CI runs
 *    Linux — so the branch IS covered where it counts.
 *
 * NOT COVERED HERE, and why — carried into the slice's writeup rather than
 * chased:
 *
 *  - `awaitTaskkill`'s spawn-throw, its own timeout, and its close-code table
 *    (0 / 128 / other). Reaching them means actually spawning taskkill.exe, so
 *    they are Windows-only AND CI runs this job on ubuntu-latest — the same
 *    split recorded in #521.
 *  - The POSIX branch of `treeKill` (process-group SIGKILL) is dead on Windows
 *    and live on Linux; the win32 branch is the mirror. Neither host can cover
 *    both, which is #521 again and the reason that issue matters for AC-1.
 *  - `waitUntilGone`'s deadline-exceeded return. It needs a process that
 *    survives SIGKILL — deliberately not portable, which is exactly why the
 *    `kill` seam exists and why the tests above use it instead.
 */
