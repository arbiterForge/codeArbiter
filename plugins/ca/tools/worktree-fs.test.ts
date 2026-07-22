import { link, lstat, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

type WorktreeFs = typeof import("./worktree-fs.ts");

async function implementation(): Promise<WorktreeFs> {
  try {
    return await import("./worktree-fs.ts");
  } catch (error) {
    throw new Error("symlink-safe worktree writer is missing", { cause: error });
  }
}

describe("symlink-safe worktree writer", () => {
  it("writes a normal nested file beneath the canonical root", async () => {
    const { writeWorktreeFile } = await implementation();
    const root = await mkdtemp(path.join(tmpdir(), "farm-safe-root-"));
    try {
      await writeWorktreeFile(root, "src/nested/value.txt", "safe\n");
      expect(await readFile(path.join(root, "src", "nested", "value.txt"), "utf8")).toBe("safe\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("rejects a directory symlink or Windows junction without changing an external sentinel", async () => {
    const { writeWorktreeFile } = await implementation();
    const root = await mkdtemp(path.join(tmpdir(), "farm-link-root-"));
    const external = await mkdtemp(path.join(tmpdir(), "farm-link-external-"));
    const sentinel = path.join(external, "sentinel.txt");
    await writeFile(sentinel, "outside-must-survive", "utf8");
    try {
      await symlink(external, path.join(root, "linked"), process.platform === "win32" ? "junction" : "dir");
      await expect(writeWorktreeFile(root, "linked/sentinel.txt", "overwrite")).rejects.toThrow("unsafe worktree path rejected");
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(external, { recursive: true, force: true });
    }
  });

  it.skipIf(process.platform === "win32")("rejects a file symlink without changing its external target", async () => {
    const { writeWorktreeFile } = await implementation();
    const root = await mkdtemp(path.join(tmpdir(), "farm-file-link-root-"));
    const external = await mkdtemp(path.join(tmpdir(), "farm-file-link-external-"));
    const sentinel = path.join(external, "sentinel.txt");
    await writeFile(sentinel, "outside-must-survive", "utf8");
    try {
      await symlink(sentinel, path.join(root, "inside.txt"), "file");
      await expect(writeWorktreeFile(root, "inside.txt", "overwrite")).rejects.toThrow("unsafe worktree path rejected");
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(external, { recursive: true, force: true });
    }
  });

  it("rejects a multiply-linked existing destination", async () => {
    const { writeWorktreeFile } = await implementation();
    const root = await mkdtemp(path.join(tmpdir(), "farm-hardlink-root-"));
    const external = await mkdtemp(path.join(tmpdir(), "farm-hardlink-external-"));
    const sentinel = path.join(external, "sentinel.txt");
    await writeFile(sentinel, "outside-must-survive", "utf8");
    try {
      await link(sentinel, path.join(root, "inside.txt"));
      expect((await lstat(path.join(root, "inside.txt"))).nlink).toBeGreaterThan(1);
      await expect(writeWorktreeFile(root, "inside.txt", "overwrite")).rejects.toThrow("unsafe worktree path rejected");
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(external, { recursive: true, force: true });
    }
  });

  it("rejects a hard link introduced after initial destination validation", async () => {
    const { writeWorktreeFile } = await implementation();
    const root = await mkdtemp(path.join(tmpdir(), "farm-race-root-"));
    const external = await mkdtemp(path.join(tmpdir(), "farm-race-external-"));
    const destination = path.join(root, "inside.txt");
    const externalLink = path.join(external, "late-link.txt");
    await writeFile(destination, "inside-original", "utf8");
    try {
      await expect(writeWorktreeFile(root, "inside.txt", "overwrite", {
        beforeFinalAuthorization: async () => await link(destination, externalLink),
      })).rejects.toThrow("unsafe worktree path rejected");
      expect(await readFile(destination, "utf8")).toBe("inside-original");
      expect(await readFile(externalLink, "utf8")).toBe("inside-original");
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(external, { recursive: true, force: true });
    }
  });

  it("pins every farm and mutation write/restore path to the shared primitive", async () => {
    const farm = await readFile(new URL("./farm.ts", import.meta.url), "utf8");
    const mutation = await readFile(new URL("./mutation.ts", import.meta.url), "utf8");
    expect(farm).toContain('from "./worktree-fs.ts"');
    expect(mutation).toContain('from "./worktree-fs.ts"');
    expect(farm).not.toMatch(/writeFile\((?:absPath|abs),/u);
    expect(mutation).not.toContain("writeFile(path.resolve(wt");
    expect((mutation.match(/writeWorktreeFile\(/gu) ?? []).length).toBeGreaterThanOrEqual(3);
  });
});
