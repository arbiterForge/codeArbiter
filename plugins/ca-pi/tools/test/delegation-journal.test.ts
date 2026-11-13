import { access, mkdtemp, mkdir, readFile, writeFile, rm, symlink, rename, link, chmod, realpath } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import { openDelegationJournal, readDelegationRecovery, resolveGitCommonDir } from "../src/delegation-journal.ts";
import { DELEGATION_PROFILE, operationId } from "../src/delegation-contract.ts";
import type { JournalRecord } from "../src/delegation-contract.ts";

const roots: string[] = [];
afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "ca-delegation-test-")); roots.push(root);
  await mkdir(join(root, ".git"));
  return root;
}
function claim(): JournalRecord {
  return { v: 1, phase: "claimed", operationId: operationId("a".repeat(32), "request-1"),
    runId: "a".repeat(32), callerCorrelation: "b".repeat(64), role: "backend-author", tool: "write",
    digest: "c".repeat(64), profile: DELEGATION_PROFILE, recordedAt: "2026-11-13T00:00:00Z",
    target: "test.txt", targetHash: "absent" };
}
describe("parent delegated operation journal", () => {
  test("an actual default Git main and linked worktree positively share the common owner", async () => {
    const main = await fixture(); const worktree = await fixture(); const inert = join(main, "empty-config"); await mkdir(inert);
    const env = { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, WINDIR: process.env.WINDIR,
      TEMP: process.env.TEMP, TMP: process.env.TMP, HOME: main, USERPROFILE: main,
      GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: process.platform === "win32" ? "NUL" : "/dev/null" };
    const git = (...args: string[]) => execFileSync("git", ["-C", main, "-c", `core.hooksPath=${inert}`,
      "-c", "commit.gpgsign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", ...args],
    { env, encoding: "utf8", timeout: 10000, stdio: "pipe" });
    git("init", "--quiet", `--template=${inert}`); git("commit", "--quiet", "--allow-empty", "-m", "fixture");
    await rm(join(worktree, ".git"), { recursive: true }); git("worktree", "add", "--quiet", "--detach", worktree);
    const common = await realpath(join(main, ".git"));
    expect(await resolveGitCommonDir(main)).toBe(common); expect(await resolveGitCommonDir(worktree)).toBe(common);
    const journal = (await openDelegationJournal(worktree))!; expect((await journal.claim(claim())).state).toBe("claimed");
    expect(await readDelegationRecovery(worktree)).toEqual({ state: "pending", count: 1, operationIds: [claim().operationId] });
  }, 15000);
  test.each(["missing", "oversized", "empty", "directory", "linked", "hardlinked"] as const)("unsafe %s commondir never becomes a fresh recovery owner", async (fault) => {
    const main = await fixture(); const worktree = await fixture(); const gitDir = join(main, ".git", "worktrees", "linked");
    await mkdir(gitDir, { recursive: true }); await rm(join(worktree, ".git"), { recursive: true });
    await writeFile(join(worktree, ".git"), `gitdir: ${gitDir}\n`);
    const pointer = join(gitDir, "commondir"); await writeFile(pointer, "../..\n");
    const journal = (await openDelegationJournal(worktree))!; await journal.claim(claim());
    const retainedClaim = join(journal.root, `${claim().operationId}.claimed.json`);
    await rm(pointer);
    if (fault === "directory") await mkdir(pointer);
    else if (fault === "linked") await symlink(join(main, ".git"), pointer, process.platform === "win32" ? "junction" : "dir");
    else if (fault === "hardlinked") {
      const other = join(gitDir, "other-pointer"); await writeFile(other, "../..\n"); await link(other, pointer);
    } else if (fault !== "missing") await writeFile(pointer, fault === "empty" ? "\n" : "x".repeat(4097));
    expect(await resolveGitCommonDir(worktree)).toBeUndefined();
    expect(await openDelegationJournal(worktree)).toBeUndefined();
    expect(await readDelegationRecovery(worktree)).toEqual({ state: "unavailable", count: 0, operationIds: [] });
    await expect(access(retainedClaim)).resolves.toBeUndefined();
  });
  test.skipIf(process.platform === "win32" || process.getuid?.() === 0)("unreadable commondir is unknown rather than absent", async () => {
    const root = await fixture(); const gitDir = join(root, "private-git"); const common = join(root, "common");
    await mkdir(gitDir); await mkdir(common);
    await rm(join(root, ".git"), { recursive: true }); await writeFile(join(root, ".git"), "gitdir: private-git\n");
    const pointer = join(gitDir, "commondir"); await writeFile(pointer, "../common\n");
    expect(await resolveGitCommonDir(root)).toBe(common);
    await chmod(pointer, 0);
    try { expect(await resolveGitCommonDir(root)).toBeUndefined(); }
    finally { await chmod(pointer, 0o600); }
  });
  test("a replaced plain journal directory cannot inherit live journal ownership", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    await rename(journal.root, `${journal.root}-saved`); await mkdir(journal.root);
    expect((await journal.claim(claim())).state).toBe("unavailable");
  });
  test("repository identity drift cannot reuse a previously opened journal", async () => {
    const root = await fixture();
    await rename(join(root, ".git"), join(root, "saved-git"));
    const first = join(root, "saved-git", "worktrees", "linked"); await mkdir(first, { recursive: true });
    await writeFile(join(first, "commondir"), "../..\n");
    await writeFile(join(root, ".git"), `gitdir: ${first}\n`);
    const journal = (await openDelegationJournal(root))!;
    const second = join(root, "other-git", "worktrees", "linked"); await mkdir(second, { recursive: true });
    await writeFile(join(second, "commondir"), "../..\n"); await writeFile(join(root, ".git"), `gitdir: ${second}\n`);
    expect((await journal.claim(claim())).state).toBe("unavailable");
  });
  test("retains a separate command launch observation for interrupted read-only recovery", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    const command = { ...claim(), tool: "bash" as const, target: undefined, targetHash: undefined };
    await journal.claim(command);
    const started = { ...command, phase: "started" as const, processId: 4321 };
    expect(await journal.started(started)).toBe(true);
    const reopened = (await openDelegationJournal(root))!;
    expect((await reopened.unresolved())[0]?.started?.processId).toBe(4321);
    expect(await journal.started({ ...started, digest: "d".repeat(64) })).toBe(false);
  });
  test("recovery inspection does not create state or restore authority", async () => {
    const root = await fixture();
    expect(await readDelegationRecovery(root)).toEqual({ state: "clear", count: 0, operationIds: [] });
    await expect(access(join(root, ".git", "codearbiter"))).rejects.toThrow();
    const journal = (await openDelegationJournal(root))!; await journal.claim(claim());
    expect(await readDelegationRecovery(root)).toEqual({ state: "pending", count: 1, operationIds: [claim().operationId] });
  });
  test("linked Git worktrees share storage without adopting each other's recovery authority", async () => {
    const root = await fixture(); const sibling = await fixture(); await rm(join(sibling, ".git"), { recursive: true });
    const gitDir = join(root, ".git", "worktrees", "sibling"); await mkdir(gitDir, { recursive: true });
    await writeFile(join(gitDir, "commondir"), "../..\n"); await writeFile(join(sibling, ".git"), `gitdir: ${gitDir}\n`);
    const first = (await openDelegationJournal(root))!; const second = (await openDelegationJournal(sibling))!;
    expect(first.identity.repositoryId).toBe(second.identity.repositoryId); expect(first.identity.worktreeId).not.toBe(second.identity.worktreeId);
    await first.claim(claim()); expect(await second.unresolved()).toEqual([]);
    expect((await second.read(claim().operationId)).unreadable).toBe(true);
    expect(await second.claim(claim())).toEqual({ state: "unavailable" });
  });
  test("exactly one concurrent claimant wins; restart exposes uncertain outcome without execution", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    const results = await Promise.all(Array.from({ length: 12 }, () => journal.claim(claim())));
    expect(results.filter((r) => r.state === "claimed")).toHaveLength(1);
    const reopened = (await openDelegationJournal(root))!;
    expect(await reopened.unresolved()).toEqual([{ operationId: claim().operationId, claim: claim() }]);
    const observed = { ...claim(), phase: "observed" as const, execution: "completed" as const,
      containment: "not-applicable" as const, targetHash: "d".repeat(64) };
    expect(await reopened.observe(observed)).toBe(true);
    expect(await reopened.observe(observed)).toBe(false);
    expect(await reopened.unresolved()).toEqual([]);
  });
  test("interrupted exclusive claim is retained as unknown and never claimable again", async () => {
    const root = await fixture();
    const journal = (await openDelegationJournal(root, { afterCreate: () => { throw new Error("injected interruption"); } }))!;
    expect(await journal.claim(claim())).toEqual({ state: "unavailable" });
    const reopened = (await openDelegationJournal(root))!;
    expect((await reopened.claim(claim())).state).toBe("exists");
    expect(await reopened.unresolved()).toEqual([{ operationId: claim().operationId, claim: undefined }]);
  });
  test("unknown record version remains unreadable and retained", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    const path = join(journal.root, `${claim().operationId}.claimed.json`);
    await writeFile(path, '{"v":99}');
    expect((await journal.read(claim().operationId)).unreadable).toBe(true);
    expect(await readFile(path, "utf8")).toBe('{"v":99}');
  });
  test("an outcome whose identity differs from the claimed filename is not trusted", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    expect(await journal.claim(claim())).toEqual({ state: "claimed" });
    const changed = { ...claim(), phase: "observed" as const, execution: "completed" as const,
      containment: "not-applicable" as const, digest: "d".repeat(64) };
    expect(await journal.observe(changed)).toBe(false);
    expect(await journal.unresolved()).toHaveLength(1);
  });
  test("linked journal ancestor is refused without adopting it", async () => {
    const root = await fixture(); const outside = await fixture();
    await symlink(outside, join(root, ".git", "codearbiter"), process.platform === "win32" ? "junction" : "dir");
    expect(await openDelegationJournal(root)).toBeUndefined();
  });
  test("a Git pointer through a linked ancestor is not adopted", async () => {
    const root = await fixture(); const outside = await fixture(); const pointer = join(root, "linked-git");
    await mkdir(join(outside, "nested")); await symlink(outside, pointer, process.platform === "win32" ? "junction" : "dir");
    await rm(join(root, ".git"), { recursive: true }); await writeFile(join(root, ".git"), `gitdir: ${join(pointer, "nested")}\n`);
    expect(await openDelegationJournal(root)).toBeUndefined();
  });
  test("an overfull journal is unavailable rather than an apparently empty recovery scan", async () => {
    const root = await fixture(); const journal = (await openDelegationJournal(root))!;
    for (let offset = 0; offset < 4097; offset += 64) {
      await Promise.all(Array.from({ length: Math.min(64, 4097 - offset) }, (_, index) =>
        writeFile(join(journal.root, `retained-unknown-${offset + index}`), "")));
    }
    await expect(journal.unresolved()).rejects.toThrow("scan");
    expect(await journal.claim(claim())).toEqual({ state: "unavailable" });
  });
});
