import { link, lstat, mkdir, mkdtemp, readdir, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { canonicalizeAncestors, isUnsafeWorktreePathError, writeWorktreeFile } from "./worktree-fs.ts";

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
 * byte and 40 concurrent calls reached three of them through the public API with
 * no seam at all.
 *
 * Platform note: this tree now runs on BOTH ubuntu-latest and windows-latest —
 * the tools job is still ubuntu-only, but #521's coverage-union cells execute
 * the suite on each host and merge the reports, so Linux is no longer the only
 * platform whose numbers count. Windows and Linux still do not agree here: an
 * over-long path segment reaches the mkdir failure arm on Windows but fails
 * earlier at `lstat` with ENAMETOOLONG on Linux. That divergence is the reason
 * the union exists rather than a reason to ignore one side, and it is why #541
 * — an absolute destination refused on Windows alone — went unseen until a
 * second host ran this file.
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
    await promise.then(
      () => expect.unreachable("write should have been refused"),
      (error: unknown) => {
        expect(isUnsafeWorktreePathError(error)).toBe(true);
        expect((error as Error).name).toBe("UnsafeWorktreePathError");
      },
    );
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
    // The post-state assertion is the whole test. Measured with every escape
    // guard removed, this input CREATES `escaped.txt` one level up and leaves it
    // there — an earlier version of this test passed while that happened,
    // because it only checked that the promise rejected.
    //
    // The root is nested inside a private container so the escape target is
    // ours. An earlier version used `path.dirname(root)` — which, for a root
    // from `mkdtemp(tmpdir())`, IS the shared OS temp directory: the assertion
    // failed spuriously if anything else had put an `escaped.txt` there, and the
    // cleanup then deleted a file this suite does not own.
    const container = await mkdtemp(path.join(tmpdir(), "farm-escape-box-"));
    const root = path.join(container, "root");
    await mkdir(root);
    try {
      await expectRefused(writeWorktreeFile(root, path.join("..", "escaped.txt"), "payload"));
      expect(existsSync(path.join(container, "escaped.txt"))).toBe(false);
      expect(await readdir(container)).toEqual(["root"]);
      expect(await readdir(root)).toEqual([]);
    } finally {
      await rm(container, { recursive: true, force: true });
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

  // #541 — the absolute-destination check compared the caller's spelling of the
  // root against `realpath(worktree)`. Those are the same directory and
  // different strings whenever a link or a Windows 8.3 short name is on the
  // path, so a caller writing INSIDE its own worktree was refused. Same root
  // cause as #539, one module down; it never reproduced on a developer box
  // whose tmpdir is already canonical, and surfaced only when #521's coverage
  // union first ran this tree on Windows CI.
  //
  // A junction gives two real spellings of one directory on any platform.
  it("accepts an absolute destination spelled through a link into the same root", async () => {
    const base = await realpath(await mkdtemp(path.join(tmpdir(), "farm-541-")));
    try {
      const real = path.join(base, "real");
      const root = path.join(real, "wt");
      await mkdir(root, { recursive: true });
      const link = path.join(base, "link");
      try {
        await symlink(real, link, "junction");
      } catch {
        return; // unprivileged Windows without developer mode
      }
      const rootViaLink = path.join(link, "wt");

      // Precondition: the two spellings are NOT lexically comparable, which is
      // the whole reason this case exists.
      expect(path.relative(root, rootViaLink).startsWith("..")).toBe(true);

      // The caller passes its own spelling as the worktree AND builds the
      // destination from it — the natural thing to do.
      await writeWorktreeFile(rootViaLink, path.join(rootViaLink, "inside.txt"), "accepted\n");
      expect(await readFile(path.join(root, "inside.txt"), "utf8")).toBe("accepted\n");

      // Mirror: canonical root, destination spelled through the link.
      await writeWorktreeFile(root, path.join(rootViaLink, "mirror.txt"), "accepted\n");
      expect(await readFile(path.join(root, "mirror.txt"), "utf8")).toBe("accepted\n");

      // Deep, not-yet-created ancestors through the link still land inside.
      await writeWorktreeFile(rootViaLink, path.join(rootViaLink, "a", "b", "deep.txt"), "deep\n");
      expect(await readFile(path.join(root, "a", "b", "deep.txt"), "utf8")).toBe("deep\n");
    } finally {
      await rm(base, { recursive: true, force: true });
    }
  });

  it("does NOT pre-resolve the leaf, so a symlinked destination is still refused", async () => {
    // The canonicalization added for #541 walks the ANCESTOR chain only. If it
    // resolved the final component too, a symlink AT the destination pointing
    // to another file INSIDE the root would resolve to a contained path, pass
    // containment, and be written THROUGH — silently overwriting the target the
    // per-segment checks exist to protect. Refusing symlinked destinations is
    // this module's contract, and canonicalizing must not quietly undo it.
    const base = await realpath(await mkdtemp(path.join(tmpdir(), "farm-541leaf-")));
    try {
      const root = path.join(base, "wt");
      await mkdir(root, { recursive: true });
      await writeFile(path.join(root, "real.txt"), "original\n", "utf8");
      try {
        await symlink(path.join(root, "real.txt"), path.join(root, "alias.txt"), "file");
      } catch {
        return; // unprivileged Windows without developer mode
      }
      await expectRefused(writeWorktreeFile(root, path.join(root, "alias.txt"), "written-through\n"));
      expect(await readFile(path.join(root, "real.txt"), "utf8")).toBe("original\n");
    } finally {
      await rm(base, { recursive: true, force: true });
    }
  });

  it("REFUSES when an ancestor cannot be canonicalized for a reason other than absence", async () => {
    // EACCES and ELOOP are not portably inducible, so the failure is injected.
    // Without this the refusal branch never runs and the fail-closed stance is
    // a comment rather than behaviour.
    const err = (code: string) => {
      const e = new Error(`simulated ${code}`) as NodeJS.ErrnoException;
      e.code = code;
      return e;
    };
    await expect(
      canonicalizeAncestors(path.join(path.sep, "repo", "wt", "f.txt"), async () => { throw err("EACCES"); }),
    ).rejects.toThrow(/EACCES/);
    await expect(
      canonicalizeAncestors(path.join(path.sep, "repo", "wt", "f.txt"), async () => { throw err("ELOOP"); }),
    ).rejects.toThrow(/ELOOP/);
  });

  it("treats a missing ancestor as normal and walks up to the deepest existing one", async () => {
    const seen: string[] = [];
    const target = path.join(path.sep, "a", "b", "c", "f.txt");
    const out = await canonicalizeAncestors(target, async (p) => {
      seen.push(p);
      if (p === path.resolve(path.sep, "a")) return path.resolve(path.sep, "REAL");
      const e = new Error("missing") as NodeJS.ErrnoException;
      e.code = "ENOENT";
      throw e;
    });
    expect(out).toBe(path.join(path.resolve(path.sep, "REAL"), "b", "c", "f.txt"));
    expect(seen.length).toBeGreaterThan(1);
  });

  it("still refuses an absolute destination whose ancestors link OUT of the root", async () => {
    // The tightening half. Canonicalizing the ancestor chain means a directory
    // inside the root that links outside is caught HERE, by containment, rather
    // than relying on a later check to notice.
    const base = await realpath(await mkdtemp(path.join(tmpdir(), "farm-541e-")));
    try {
      const root = path.join(base, "wt");
      const outside = path.join(base, "outside");
      await mkdir(root, { recursive: true });
      await mkdir(outside, { recursive: true });
      await writeFile(path.join(outside, "sentinel.txt"), "outside-must-survive", "utf8");

      const escape = path.join(root, "escape");
      try {
        await symlink(outside, escape, "junction");
      } catch {
        return;
      }
      // Lexically this looks contained — that is what makes it worth refusing.
      expect(path.relative(root, escape).startsWith("..")).toBe(false);

      await expectRefused(writeWorktreeFile(root, path.join(escape, "sentinel.txt"), "overwrite"));
      expect(await readFile(path.join(outside, "sentinel.txt"), "utf8")).toBe("outside-must-survive");
    } finally {
      await rm(base, { recursive: true, force: true });
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
    // Kills a WRONG encoding (latin1) on the write. It does NOT pin the option's
    // presence — `FileHandle.writeFile` defaults to utf8, so deleting it changes
    // nothing. Either way, a non-ASCII fixture is the only thing in this file
    // that would notice a re-encoding at all.
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
