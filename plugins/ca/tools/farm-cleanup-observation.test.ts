import { afterEach, describe, expect, it, vi } from "vitest";
import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { mkdtemp, mkdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { removeWorktreeVerified, validateWorktreeRoot } from "./farm.ts";
import type { RunResult } from "./exec.ts";

const observation = vi.hoisted(() => ({ target: "", code: "" }));
vi.mock("node:fs/promises", async (original) => {
  const actual = await original<typeof import("node:fs/promises")>();
  const observe = (read: typeof actual.stat) => (...args: Parameters<typeof actual.stat>) => {
    if (String(args[0]) === observation.target && observation.code) {
      return Promise.reject(Object.assign(new Error("fixture observation unavailable"), { code: observation.code }));
    }
    return read(...args);
  };
  return { ...actual, stat: observe(actual.stat), lstat: observe(actual.lstat) };
});

const roots: string[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  observation.target = "";
  observation.code = "";
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

const result = (code: number, out = ""): RunResult => ({ code, out, stdout: out, stderr: "" });
async function fixture(nested = false) {
  // Git records the physical path; TEMP may use a junction or an 8.3 alias.
  // Resolve only this newly owned fixture before constructing its Git paths.
  const root = await realpath(await mkdtemp(path.join(tmpdir(), "ca-farm-cleanup-observation-")));
  roots.push(root);
  const repo = path.join(root, "repo");
  const wt = nested ? path.join(repo, "owned-worktrees", "task") : path.join(root, "worktree");
  await mkdir(repo);
  const git = async (args: string[]): Promise<RunResult> => {
    const run = spawnSync("git", args, { cwd: repo, encoding: "utf8", windowsHide: true });
    if (run.error) throw run.error;
    return { code: run.status ?? 1, stdout: run.stdout, stderr: run.stderr, out: run.stdout + run.stderr };
  };
  for (const args of [["init"], ["config", "user.name", "Cleanup fixture"],
    ["config", "user.email", "fixture@example.invalid"]]) {
    expect((await git(args)).code).toBe(0);
  }
  await writeFile(path.join(repo, "owned.txt"), "fixture\n");
  expect((await git(["add", "owned.txt"])).code).toBe(0);
  expect((await git(["-c", "core.hooksPath=", "commit", "-m", "fixture"])).code).toBe(0);
  await mkdir(path.dirname(wt), { recursive: true });
  expect((await git(["worktree", "add", "--detach", wt])).code).toBe(0);
  return { root, wt, git };
}

describe("worktree cleanup filesystem observation", () => {
  for (const code of ["EACCES", "EIO"]) {
    for (const registered of [false, true]) {
      it(`refuses ${code} with ${registered ? "retained" : "absent"} Git registration without prune or destructive retry`, async () => {
        const { wt, git } = await fixture();
        const calls: string[][] = [];
        observation.target = wt;
        observation.code = code;
        const controlledGit = async (args: string[]) => {
          calls.push(args);
          if (registered && args[1] === "remove") return result(1, "fixture removal refused");
          return git(args);
        };
        const outcome = await removeWorktreeVerified(controlledGit, wt, { attempts: 3, delayMs: 0 });
        expect(outcome).toMatchObject({ ok: false, target: wt, attempts: 1 });
        expect(outcome.detail).toMatch(/filesystem observation unavailable/i);
        expect(outcome.detail).toContain(code);
        expect(calls.filter(args => args[1] === "remove")).toHaveLength(1);
        expect(calls.some(args => args[1] === "prune")).toBe(false);
        expect((await git(["worktree", "list", "--porcelain"])).stdout.includes(wt.replaceAll("\\", "/"))).toBe(registered);
      });
    }
  }

  it("accepts ENOENT only after real Git removal and an absent registration", async () => {
    const { wt, git } = await fixture();
    expect(await removeWorktreeVerified(git, wt, { attempts: 3, delayMs: 0 }))
      .toEqual({ ok: true, target: wt, attempts: 1 });
  });

  it("retains known-present paths and the existing bounded retry policy", async () => {
    const { wt } = await fixture();
    const calls: string[][] = [];
    const git = async (args: string[]) => { calls.push(args); return result(args[1] === "remove" ? 1 : 0); };
    const outcome = await removeWorktreeVerified(git, wt, { attempts: 3, delayMs: 0 });
    expect(outcome).toMatchObject({ ok: false, target: wt, attempts: 3 });
    expect(outcome.detail).toMatch(/directory still present/);
    expect(calls.filter(args => args[1] === "remove")).toHaveLength(3);
    expect(calls.some(args => args[1] === "prune")).toBe(false);
  });

  it("does not mistake a dangling directory link for an absent owned path", async () => {
    const { root, wt, git } = await fixture();
    expect((await git(["worktree", "remove", "--force", wt])).code).toBe(0);
    await symlink(path.join(root, "missing-target"), wt, process.platform === "win32" ? "junction" : "dir");
    const outcome = await removeWorktreeVerified(async () => result(0), wt, { attempts: 1, delayMs: 0 });
    expect(outcome).toMatchObject({ ok: false, target: wt, attempts: 1 });
    expect(outcome.detail).toMatch(/directory still present/);
  });

  async function aliasedFixture() {
    const fixtureValue = await fixture(true);
    const repo = path.join(fixtureValue.root, "repo");
    const aliasRoot = path.join(repo, "alias-worktrees");
    await symlink(path.dirname(fixtureValue.wt), aliasRoot, process.platform === "win32" ? "junction" : "dir");
    // This is an admitted same-repository root, not an external-root override.
    expect(validateWorktreeRoot(aliasRoot, repo, false)).toBe(aliasRoot);
    return { ...fixtureValue, alias: path.join(aliasRoot, "task") };
  }

  it("refuses cleanup success through an admitted alias while a locked missing worktree remains registered", async () => {
    const { wt, alias, git } = await aliasedFixture();
    expect((await git(["worktree", "lock", "--reason", "fixture retention", wt])).code).toBe(0);
    // Both the physical directory and its alias were created inside this one
    // fixture-owned root. Leave the locked Git registration as the oracle.
    await rm(wt, { recursive: true, force: true });
    const outcome = await removeWorktreeVerified(git, alias, { attempts: 3, delayMs: 0 });
    expect(outcome).toMatchObject({ ok: false, target: alias, attempts: 3 });
    expect(outcome.detail).toMatch(/still registered/);
    expect((await git(["worktree", "list", "--porcelain"])).stdout).toContain(wt.replaceAll("\\", "/"));
  });

  it("accepts actual Git removal and verified absence through an admitted alias", async () => {
    const { wt, alias, git } = await aliasedFixture();
    expect(await removeWorktreeVerified(git, alias, { attempts: 3, delayMs: 0 }))
      .toEqual({ ok: true, target: alias, attempts: 1 });
    expect((await git(["worktree", "list", "--porcelain"])).stdout).not.toContain(wt.replaceAll("\\", "/"));
  });

  for (const code of ["EACCES", "EIO"]) {
    it(`keeps alias registration ${code} canonicalization unknown without prune or destructive retry`, async () => {
      const { wt, alias, git } = await aliasedFixture();
      expect((await git(["worktree", "lock", "--reason", "fixture retention", wt])).code).toBe(0);
      await rm(wt, { recursive: true, force: true });
      const native = realpathSync.native;
      vi.spyOn(realpathSync, "native").mockImplementation(((p: string) => {
        if (p === alias) throw Object.assign(new Error("fixture canonicalization unavailable"), { code });
        return native(p);
      }) as typeof realpathSync.native);
      const calls: string[][] = [];
      const outcome = await removeWorktreeVerified(async args => { calls.push(args); return git(args); }, alias,
        { attempts: 3, delayMs: 0 });
      expect(outcome).toMatchObject({ ok: false, target: alias, attempts: 1 });
      expect(outcome.detail).toMatch(/registration.*observation unavailable/i);
      expect(calls.filter(args => args[1] === "remove")).toHaveLength(1);
      expect(calls.some(args => args[1] === "prune")).toBe(false);
      expect((await git(["worktree", "list", "--porcelain"])).stdout).toContain(wt.replaceAll("\\", "/"));
    });
  }

  for (const afterPrune of [false, true]) {
    it(`keeps unavailable registry ${afterPrune ? "readback" : "observation"} unknown without another destructive attempt`, async () => {
      const { wt, git } = await fixture(true);
      expect((await git(["worktree", "lock", "--reason", "fixture retention", wt])).code).toBe(0);
      await rm(wt, { recursive: true, force: true });
      const calls: string[][] = [];
      let lists = 0;
      const outcome = await removeWorktreeVerified(async args => {
        calls.push(args);
        if (args[1] === "list" && ++lists > (afterPrune ? 1 : 0)) return result(128, "fixture registry unavailable");
        return git(args);
      }, wt, { attempts: 3, delayMs: 0 });
      expect(outcome).toMatchObject({ ok: false, target: wt, attempts: 1 });
      expect(outcome.detail).toMatch(/registration.*observation unavailable/i);
      expect(calls.filter(args => args[1] === "remove")).toHaveLength(1);
      expect(calls.filter(args => args[1] === "prune")).toHaveLength(afterPrune ? 1 : 0);
      expect((await git(["worktree", "list", "--porcelain"])).stdout).toContain(wt.replaceAll("\\", "/"));
    });
  }

  it("keeps a registry comparison unknown when no physical ancestor can be observed", async () => {
    const { wt, alias, git } = await aliasedFixture();
    expect((await git(["worktree", "lock", "--reason", "fixture retention", wt])).code).toBe(0);
    await rm(wt, { recursive: true, force: true });
    const unavailable = new Set<string>();
    for (let p = alias; ; p = path.dirname(p)) {
      unavailable.add(p);
      if (path.dirname(p) === p) break;
    }
    const native = realpathSync.native;
    // Inject unavailable identity observations through the volume root; no
    // real volume is unmounted and ordinary fixture file reads still work.
    vi.spyOn(realpathSync, "native").mockImplementation(((p: string) => {
      if (unavailable.has(p)) throw Object.assign(new Error("fixture ancestor unavailable"), { code: "ENOENT" });
      return native(p);
    }) as typeof realpathSync.native);
    const calls: string[][] = [];
    const outcome = await removeWorktreeVerified(async args => { calls.push(args); return git(args); }, alias,
      { attempts: 3, delayMs: 0 });
    expect(outcome).toMatchObject({ ok: false, target: alias, attempts: 1 });
    expect(outcome.detail).toMatch(/registration.*observation unavailable/i);
    expect(calls.filter(args => args[1] === "remove")).toHaveLength(1);
    expect(calls.some(args => args[1] === "prune")).toBe(false);
    expect((await git(["worktree", "list", "--porcelain"])).stdout).toContain(wt.replaceAll("\\", "/"));
  });
});
