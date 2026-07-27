import { link, lstat, mkdtemp, readdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { isUnsafeWorktreePathError, writeWorktreeFile } from "./worktree-fs.ts";

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
 * built for. This block works the rest of the refusal surface.
 *
 * Two rules, and the first cut of this block broke both:
 *
 *  - Assert the POST-STATE, never merely that the call rejected. A refusal that
 *    still wrote is the exact failure this module exists to prevent, and
 *    `rejects.toThrow()` cannot tell the two apart. Measured: with the escape
 *    guards removed, `../escaped.txt` CREATES a file in the parent directory —
 *    an earlier version of these tests passed anyway, because it only checked
 *    that the promise rejected.
 *  - Assert error IDENTITY, not just the message. `isUnsafeWorktreePathError` is
 *    what callers branch on (mutation.ts rethrows on it); a refusal arriving as
 *    a plain Error would break them while still "throwing".
 *
 * On mutation testing here: the module is layered on purpose, so single-point
 * mutants mostly survive by design — removing all four `isSymbolicLink()` checks
 * still passes, because a junction also fails `isDirectory()`. The unit that
 * means anything is the PROPERTY (every layer guarding it removed at once), not
 * the line. That does NOT excuse leaving reachable arms untested: an earlier
 * draft of this block called four of them "structurally unreachable" and a NUL
 * byte, an over-long segment, and 40 concurrent calls reached three of them
 * through the public API with no seam at all.
 */
describe("symlink-safe worktree writer — refusal paths", () => {
  const MESSAGE = "unsafe worktree path rejected";

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
    await expect(promise).rejects.toThrow(MESSAGE);
    await promise.catch((error: unknown) => {
      expect(isUnsafeWorktreePathError(error)).toBe(true);
      expect((error as Error).name).toBe("UnsafeWorktreePathError");
    });
  }

  it("refuses a worktree root that is itself a link", async () => {
    // Sole killer of dropping the root guard entirely. Distinct from the
    // existing intermediate-link case: here the ROOT handed to the writer is the
    // link, so the very first lstat is what has to catch it.
    const { root, external, sentinel, cleanup } = await arena("farm-rootlink");
    const linkedRoot = path.join(root, "linked-root");
    try {
      await symlink(external, linkedRoot, process.platform === "win32" ? "junction" : "dir");
      await expectRefused(writeWorktreeFile(linkedRoot, "sentinel.txt", "overwrite"));
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
      expect(await readdir(external)).toEqual(["sentinel.txt"]);
    } finally {
      await cleanup();
    }
  });

  it("refuses an escaping relative path and writes NOTHING outside the root", async () => {
    // The post-state assertion is the whole test. Measured with the escape
    // guards removed, this input creates `escaped.txt` in the root's PARENT and
    // leaves it there — a version of this test that only asserted rejection
    // passed while that happened.
    const { root, cleanup } = await arena("farm-escape");
    const parentOfRoot = path.dirname(root);
    const wouldBe = path.join(parentOfRoot, "escaped.txt");
    try {
      await expectRefused(writeWorktreeFile(root, path.join("..", "escaped.txt"), "payload"));
      expect(existsSync(wouldBe)).toBe(false);
      expect(await readdir(root)).toEqual([]);
    } finally {
      await rm(wouldBe, { force: true });
      await cleanup();
    }
  });

  it("refuses a relative path resolving to the root itself", async () => {
    // `""` and `"."` both produce the same `relative === ""` arm, so one case
    // covers both; the second would be a duplicate.
    const { root, cleanup } = await arena("farm-rootself");
    try {
      await expectRefused(writeWorktreeFile(root, "", "payload"));
      expect(await readdir(root)).toEqual([]);
    } finally {
      await cleanup();
    }
  });

  it("judges an absolute destination by where it LANDS, not by its shape", async () => {
    // Both arms. `path.isAbsolute` is applied to the RESOLVED relative path, not
    // the caller's input — so an absolute path inside the root is legitimate (it
    // names the same file) and one outside is caught by the `..` check. Sole
    // killer of a guard rewritten to reject all absolute input, which would
    // silently break a valid caller.
    const { root, external, sentinel, cleanup } = await arena("farm-abs");
    try {
      await writeWorktreeFile(root, path.join(root, "inside.txt"), "accepted\n");
      expect(await readFile(path.join(root, "inside.txt"), "utf8")).toBe("accepted\n");

      // win32 `path.relative` is case-insensitive, so a case-variant absolute
      // path still lands inside and must still be accepted.
      if (process.platform === "win32") {
        await writeWorktreeFile(root, path.join(root, "cased.txt").toUpperCase(), "cased\n");
        expect(await readFile(path.join(root, "cased.txt"), "utf8")).toBe("cased\n");
      }

      await expectRefused(writeWorktreeFile(root, path.join(external, "sentinel.txt"), "overwrite"));
      expect(await readFile(sentinel, "utf8")).toBe("outside-must-survive");
    } finally {
      await cleanup();
    }
  });

  it("refuses a NUL byte in the destination segment", async () => {
    // Reaches the non-ENOENT arm of the destination lstat: the error is neither
    // "missing" nor an `unsafe()` call, so the catch has to funnel it. An
    // earlier draft called this arm structurally unreachable; it needs one byte.
    const { root, cleanup } = await arena("farm-nul-dest");
    try {
      await expectRefused(writeWorktreeFile(root, "a\0b.txt", "payload"));
      expect(await readdir(root)).toEqual([]);
    } finally {
      await cleanup();
    }
  });

  it("refuses a NUL byte in an intermediate segment", async () => {
    // The same arm one level up, in the segment walk rather than at the
    // destination — a different `lstat` with its own non-ENOENT guard.
    const { root, cleanup } = await arena("farm-nul-mid");
    try {
      await expectRefused(writeWorktreeFile(root, path.join("a\0b", "c.txt"), "payload"));
      expect(await readdir(root)).toEqual([]);
    } finally {
      await cleanup();
    }
  });

  it("refuses an intermediate segment the filesystem cannot create", async () => {
    // Reaches the non-EEXIST arm of the mkdir guard: lstat says ENOENT, so a
    // directory is attempted, and mkdir fails for a reason that is NOT a lost
    // race. That error must propagate rather than be mistaken for one.
    const { root, cleanup } = await arena("farm-longseg");
    try {
      await expectRefused(writeWorktreeFile(root, path.join("d".repeat(300), "x.txt"), "payload"));
    } finally {
      await cleanup();
    }
  });

  it("absorbs a lost mkdir race between concurrent writers", async () => {
    // The EEXIST arm — the race the guard exists for. Forty writers share the
    // same nested ancestors, so many of them lose the mkdir and must treat
    // EEXIST as success rather than as a failure. Any rejection here means a
    // legitimate concurrent write was refused.
    const { root, cleanup } = await arena("farm-mkdir-race");
    try {
      const writes = Array.from({ length: 40 }, (_, i) =>
        writeWorktreeFile(root, path.join("shared", "nested", "deep", `f${i}.txt`), `payload-${i}\n`),
      );
      await Promise.all(writes);
      const written = await readdir(path.join(root, "shared", "nested", "deep"));
      expect(written).toHaveLength(40);
      expect(await readFile(path.join(root, "shared", "nested", "deep", "f39.txt"), "utf8")).toBe("payload-39\n");
    } finally {
      await cleanup();
    }
  });

  it("refuses a destination swapped for a link after validation but before truncate", async () => {
    // The destination is validated, opened, and then — before the retained
    // handle is truncated — replaced with a link pointing outside the root. This
    // is the containment re-check, not the symlink check: every pre-open
    // observation is stale by this point.
    //
    // The post-state that matters is the EXTERNAL directory, not the sentinel:
    // the handle refers to the now-unlinked original inode, so the sentinel
    // survives whatever the guards do. What must not happen is a new file
    // appearing through the link.
    const { root, external, cleanup } = await arena("farm-lateswap");
    const destination = path.join(root, "inside.txt");
    await writeFile(destination, "inside-original", "utf8");
    try {
      await expectRefused(
        writeWorktreeFile(root, "inside.txt", "overwrite", {
          beforeFinalAuthorization: async () => {
            await rm(destination, { force: true });
            await symlink(external, destination, process.platform === "win32" ? "junction" : "dir");
          },
        }),
      );
      expect(await readdir(external)).toEqual(["sentinel.txt"]);
    } finally {
      await cleanup();
    }
  });

  it("funnels an unexpected filesystem error into the same refusal, leaking nothing", async () => {
    // A root that does not exist makes the FIRST lstat throw ENOENT — not an
    // `unsafe()` call. The catch must convert it, so a caller cannot tell
    // "escaped the root" from "disk error"; the raw errno must not surface, and
    // the missing root must not be created on the way out.
    const missing = path.join(tmpdir(), `farm-missing-root-${Date.now()}`);
    await expectRefused(writeWorktreeFile(missing, "a.txt", "payload"));
    await expect(writeWorktreeFile(missing, "a.txt", "payload")).rejects.not.toThrow(/ENOENT/);
    expect(existsSync(missing)).toBe(false);
  });

  it("leaves ancestor directories behind on a refusal — refusal is not a rollback", async () => {
    // Documented, previously unasserted. The segment walk creates missing
    // ancestors BEFORE the destination is validated, so a refused write can
    // leave empty directories. They are inside the root and owner-only, so this
    // is benign — but it is not atomic, and a caller assuming otherwise would be
    // wrong. Pinned so a change to it is a deliberate one.
    const { root, cleanup } = await arena("farm-partial");
    try {
      await expectRefused(writeWorktreeFile(root, path.join("n1", "n2", "a\0.txt"), "payload"));
      expect(existsSync(path.join(root, "n1", "n2"))).toBe(true);
      expect(await readdir(path.join(root, "n1", "n2"))).toEqual([]);
    } finally {
      await cleanup();
    }
  });
});

describe("symlink-safe worktree writer — write contracts", () => {
  it("truncates rather than appends when rewriting a shorter payload", async () => {
    // Sole killer of dropping `truncate(0)`. Without it the tail of a longer
    // previous payload survives, which for a restored mutant means the worktree
    // silently keeps mutated source.
    const root = await mkdtemp(path.join(tmpdir(), "farm-truncate-"));
    try {
      await writeWorktreeFile(root, "f.txt", "AAAAAAAAAAAAAAAAAAAAAAAA\n");
      await writeWorktreeFile(root, "f.txt", "BBB\n");
      expect(await readFile(path.join(root, "f.txt"), "utf8")).toBe("BBB\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("round-trips non-ASCII content without re-encoding it", async () => {
    // Pins the utf8 encoding on both the write and the read-back. A latin1 slip
    // is invisible to every ASCII fixture in this file.
    const root = await mkdtemp(path.join(tmpdir(), "farm-utf8-"));
    try {
      const content = "héllo — ünïcode ✓\n";
      await writeWorktreeFile(root, "u.txt", content);
      expect(await readFile(path.join(root, "u.txt"), "utf8")).toBe(content);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it.skipIf(process.platform === "win32")("creates directories 0o700 and files 0o600", async () => {
    // Both modes, and both matter: the directory mode is what keeps a shared
    // temp root from listing worker output, the file mode is what keeps its
    // CONTENTS unreadable. An earlier draft asserted only the directory, and
    // skipped the whole assertion on the measurement platform — so on Windows it
    // asserted nothing at all while appearing to pin the threat model.
    const root = await mkdtemp(path.join(tmpdir(), "farm-mode-"));
    try {
      await writeWorktreeFile(root, path.join("fresh", "deep", "file.txt"), "made\n");
      expect((await lstat(path.join(root, "fresh"))).mode & 0o777).toBe(0o700);
      expect((await lstat(path.join(root, "fresh", "deep", "file.txt"))).mode & 0o777).toBe(0o600);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
