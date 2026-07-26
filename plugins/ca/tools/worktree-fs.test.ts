import { link, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
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

/**
 * Refusal paths (#511 slice 2).
 *
 * The suite above pins the writer's happy path and the three link attacks it was
 * built for. What it does not reach is the rest of the refusal surface: 19 of
 * this module's branches were untaken, and every one of them is an `unsafe()`
 * arm or a re-verification performed before the retained handle is truncated.
 * The line column reads 97% and hides all of it.
 *
 * Two rules throughout, both learned from slice 1:
 *
 *  - Assert the SENTINEL SURVIVED, never merely that the call rejected. A
 *    refusal that still wrote is the exact failure this module exists to
 *    prevent, and `rejects.toThrow()` alone cannot tell the two apart.
 *  - Assert the error IDENTITY, not just its message. Every failure in here is
 *    funnelled through `UnsafeWorktreePathError` deliberately, so that a caller
 *    cannot distinguish "escaped the root" from "disk error" and leak the
 *    difference; a test that accepts any throw would not notice that collapsing.
 */
describe("symlink-safe worktree writer — refusal paths", () => {
  const MESSAGE = "unsafe worktree path rejected";

  /** Every case builds a root and an external tree with a sentinel to protect. */
  async function arena(prefix: string): Promise<{ root: string; external: string; sentinel: string; cleanup: () => Promise<void> }> {
    const root = await mkdtemp(path.join(tmpdir(), `${prefix}-root-`));
    const external = await mkdtemp(path.join(tmpdir(), `${prefix}-ext-`));
    const sentinel = path.join(external, "sentinel.txt");
    await writeFile(sentinel, "outside-must-survive", "utf8");
    return {
      root,
      external,
      sentinel,
      cleanup: async () => {
        await rm(root, { recursive: true, force: true });
        await rm(external, { recursive: true, force: true });
      },
    };
  }

  async function expectRefused(promise: Promise<unknown>): Promise<void> {
    // Identity AND message. `isUnsafeWorktreePathError` is the discriminator
    // callers actually branch on (mutation.ts rethrows on it), so a refusal that
    // arrived as a plain Error would break them while still "throwing".
    const { isUnsafeWorktreePathError } = await implementation();
    await expect(promise).rejects.toThrow(MESSAGE);
    await promise.then(
      () => expect.unreachable("write should have been refused"),
      (error: unknown) => {
        expect(isUnsafeWorktreePathError(error)).toBe(true);
        expect((error as Error).name).toBe("UnsafeWorktreePathError");
      },
    );
  }

  it("refuses a worktree root that is a regular file, not a directory", async () => {
    const { writeWorktreeFile } = await implementation();
    const { root, cleanup } = await arena("farm-rootfile");
    const rootFile = path.join(root, "not-a-directory");
    await writeFile(rootFile, "original", "utf8");
    try {
      await expectRefused(writeWorktreeFile(rootFile, "a.txt", "payload"));
      expect(await readFile(rootFile, "utf8")).toBe("original");
    } finally {
      await cleanup();
    }
  });

  it("refuses a worktree root that is itself a link", async () => {
    // Distinct from the existing intermediate-link case: here the ROOT handed to
    // the writer is the link, so the very first lstat is what has to catch it.
    const { writeWorktreeFile } = await implementation();
    const { root, external, sentinel, cleanup } = await arena("farm-rootlink");
    const linkedRoot = path.join(root, "linked-root");
    try {
      await symlink(external, linkedRoot, process.platform === "win32" ? "junction" : "dir");
      await expectRefused(writeWorktreeFile(linkedRoot, "sentinel.txt", "overwrite"));
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await cleanup();
    }
  });

  it.each([
    ["..", "the parent directory"],
    ["../escaped.txt", "a sibling of the root"],
    ["", "the root itself"],
    [".", "the root itself via dot"],
  ])("refuses a relative path resolving to %s", async (relPath) => {
    const { writeWorktreeFile } = await implementation();
    const { root, cleanup } = await arena("farm-escape");
    try {
      await expectRefused(writeWorktreeFile(root, relPath, "payload"));
    } finally {
      await cleanup();
    }
  });

  it("judges an absolute destination by where it LANDS, not by its shape", async () => {
    // Both arms, because the guard is easy to misread. `path.isAbsolute` is
    // applied to the RESOLVED relative path, not to the caller's input — so an
    // absolute path inside the root is legitimate (it names the same file), and
    // an absolute path outside is caught by the `..` check rather than by being
    // absolute. Asserting only the refusal would let the guard be rewritten to
    // reject all absolute input, which silently breaks a valid caller.
    const { writeWorktreeFile } = await implementation();
    const { root, external, sentinel, cleanup } = await arena("farm-abs");
    try {
      await writeWorktreeFile(root, path.join(root, "inside.txt"), "accepted\n");
      expect(await readFile(path.join(root, "inside.txt"), "utf8")).toBe("accepted\n");

      await expectRefused(writeWorktreeFile(root, path.join(external, "sentinel.txt"), "overwrite"));
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await cleanup();
    }
  });

  it("refuses to write THROUGH a linked intermediate directory into an external tree", async () => {
    // The existing suite writes to `linked/sentinel.txt` — one level. This goes
    // deeper, so the refusal has to happen while walking segments rather than at
    // the destination check.
    const { writeWorktreeFile } = await implementation();
    const { root, external, cleanup } = await arena("farm-midlink");
    const nested = path.join(external, "nested");
    await mkdir(nested, { recursive: true });
    const deepSentinel = path.join(nested, "deep.txt");
    await writeFile(deepSentinel, "deep-must-survive", "utf8");
    try {
      await symlink(external, path.join(root, "linked"), process.platform === "win32" ? "junction" : "dir");
      await expectRefused(writeWorktreeFile(root, path.join("linked", "nested", "deep.txt"), "overwrite"));
      expect(await readFile(deepSentinel, "utf8")).toBe("deep-must-survive");
    } finally {
      await cleanup();
    }
  });

  it("refuses a destination that exists as a directory", async () => {
    // `safeRegularFile` rejects a non-file destination. Without it the open()
    // would fail on its own, but with a raw errno rather than the funnelled
    // refusal — and the directory would still be probed.
    const { writeWorktreeFile } = await implementation();
    const { root, cleanup } = await arena("farm-destdir");
    await mkdir(path.join(root, "target.txt"), { recursive: true });
    try {
      await expectRefused(writeWorktreeFile(root, "target.txt", "payload"));
    } finally {
      await cleanup();
    }
  });

  it("funnels an unexpected filesystem error into the same refusal, leaking nothing", async () => {
    // A root that does not exist makes the FIRST lstat throw ENOENT — not an
    // `unsafe()` call. The catch must convert it, so callers cannot distinguish
    // "escaped the root" from "disk error"; the raw errno must not surface.
    const { writeWorktreeFile } = await implementation();
    const missing = path.join(tmpdir(), `farm-missing-root-${Date.now()}`);
    await expectRefused(writeWorktreeFile(missing, "a.txt", "payload"));
    await expect(writeWorktreeFile(missing, "a.txt", "payload")).rejects.not.toThrow(/ENOENT/);
  });

  it("re-verifies the parent between open and truncate, refusing a late swap", async () => {
    // The destination is validated, opened, and then — before the handle is
    // truncated — the parent directory is replaced with a link to somewhere
    // else. Every pre-open observation is now stale, and the final
    // re-verification is the only thing standing between the retained handle and
    // an authorized write against a path nobody checked.
    const { writeWorktreeFile } = await implementation();
    const { root, external, sentinel, cleanup } = await arena("farm-lateswap");
    const parent = path.join(root, "sub");
    await mkdir(parent, { recursive: true });
    const destination = path.join(parent, "inside.txt");
    await writeFile(destination, "inside-original", "utf8");
    try {
      await expectRefused(
        writeWorktreeFile(root, path.join("sub", "inside.txt"), "overwrite", {
          beforeFinalAuthorization: async () => {
            await rm(parent, { recursive: true, force: true });
            await symlink(external, parent, process.platform === "win32" ? "junction" : "dir");
          },
        }),
      );
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await cleanup();
    }
  });

  it("creates missing intermediate directories with owner-only permissions", async () => {
    // The success counterpart of the walk above: `mkdir(..., { mode: 0o700 })`.
    // Worth pinning because the mode is the only thing keeping a shared temp
    // root from exposing worker output, and nothing else asserts it.
    const { writeWorktreeFile } = await implementation();
    const { root, cleanup } = await arena("farm-mkmode");
    try {
      await writeWorktreeFile(root, path.join("fresh", "deep", "file.txt"), "made\n");
      expect(await readFile(path.join(root, "fresh", "deep", "file.txt"), "utf8")).toBe("made\n");
      if (process.platform !== "win32") {
        const mode = (await lstat(path.join(root, "fresh"))).mode & 0o777;
        expect(mode).toBe(0o700);
      }
    } finally {
      await cleanup();
    }
  });

  it("truncates rather than appends when rewriting a shorter payload", async () => {
    // `truncate(0)` before `writeFile`. Without it the tail of a longer previous
    // payload survives, which for a restored mutant means the worktree silently
    // keeps mutated source.
    const { writeWorktreeFile } = await implementation();
    const { root, cleanup } = await arena("farm-truncate");
    try {
      await writeWorktreeFile(root, "f.txt", "AAAAAAAAAAAAAAAAAAAAAAAA\n");
      await writeWorktreeFile(root, "f.txt", "BBB\n");
      expect(await readFile(path.join(root, "f.txt"), "utf8")).toBe("BBB\n");
    } finally {
      await cleanup();
    }
  });
});
