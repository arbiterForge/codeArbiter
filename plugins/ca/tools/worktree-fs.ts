/** Symlink-safe writes for all model-controlled farm worktree mutations. */
import { constants } from "node:fs";
import type { Stats } from "node:fs";
import { lstat, mkdir, open, realpath } from "node:fs/promises";
import path from "node:path";

const UNSAFE_MESSAGE = "unsafe worktree path rejected";

export class UnsafeWorktreePathError extends Error {
  constructor() {
    super(UNSAFE_MESSAGE);
    this.name = "UnsafeWorktreePathError";
  }
}

export function isUnsafeWorktreePathError(error: unknown): error is UnsafeWorktreePathError {
  return error instanceof UnsafeWorktreePathError;
}

export interface WorktreeWriteTestHooks {
  /** Test seam for a deterministic replacement/link race before final authorization. */
  beforeFinalAuthorization?(): Promise<void>;
}

function unsafe(): never {
  throw new UnsafeWorktreePathError();
}

function isMissing(error: unknown): boolean {
  return (error as NodeJS.ErrnoException)?.code === "ENOENT";
}

function contained(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

// #541 — an ABSOLUTE destination is compared against `realpath(worktree)`, but
// resolved from the caller's own spelling of the root. Those are the same
// directory and different strings whenever a link or a Windows 8.3 short name
// sits on the path: a GitHub runner hands out `C:\Users\RUNNER~1\...` while
// realpath returns `C:\Users\runneradmin\...`, so a caller building an absolute
// path from the root IT passed in was refused for writing inside the worktree.
// Same root cause as #539, one module down.
//
// Only the ANCESTOR chain is canonicalized; the final component is kept
// literal. Resolving the leaf would follow a symlink AT the destination, which
// is precisely what the per-segment lstat checks below exist to catch — this
// must not quietly pre-resolve the thing they are guarding.
//
// Canonicalizing tightens rather than loosens: a path whose ancestors traverse
// a symlink OUT of the root now fails `contained` here instead of relying on a
// later check. A missing ancestor is normal (directories are created on
// demand), so walk up to the deepest existing one; any non-ENOENT failure
// propagates and refuses rather than falling through.
// `resolvePath` is injectable for the same reason #539's canonicalize is: an
// EACCES or ELOOP cannot be induced portably, and a guard whose refusal path
// never executes is a fail-closed stance asserted rather than proven.
export async function canonicalizeAncestors(
  target: string,
  resolvePath: (p: string) => Promise<string> = realpath,
): Promise<string> {
  const resolved = path.resolve(target);
  const leaf = path.basename(resolved);
  const missing: string[] = [];
  let cursor = path.dirname(resolved);
  for (;;) {
    try {
      const real = await resolvePath(cursor);
      return path.join(real, ...missing.slice().reverse(), leaf);
    } catch (error) {
      if (!isMissing(error)) throw error;
      const parent = path.dirname(cursor);
      if (parent === cursor) return resolved;
      missing.push(path.basename(cursor));
      cursor = parent;
    }
  }
}

function sameFile(left: Stats, right: Stats): boolean {
  return left.dev === right.dev && left.ino === right.ino;
}

function safeRegularFile(metadata: Stats): boolean {
  return metadata.isFile() && !metadata.isSymbolicLink() && metadata.nlink === 1;
}

/**
 * Write one worktree-relative file without following a link/reparse point.
 * Existing ancestors and the destination are checked before open and again
 * before the retained handle is truncated, so the write never targets a path
 * selected only by lexical containment.
 */
export async function writeWorktreeFile(
  worktree: string,
  relPath: string,
  contents: string,
  testHooks: WorktreeWriteTestHooks = {},
): Promise<void> {
  let handle: Awaited<ReturnType<typeof open>> | undefined;
  try {
    const rootMetadata = await lstat(worktree);
    if (!rootMetadata.isDirectory() || rootMetadata.isSymbolicLink()) unsafe();
    const canonicalRoot = await realpath(worktree);
    const verifiedDirectories: Array<{ path: string; metadata: Stats }> = [
      { path: canonicalRoot, metadata: await lstat(canonicalRoot) },
    ];
    const verifyDirectories = async (): Promise<void> => {
      for (const verified of verifiedDirectories) {
        const current = await lstat(verified.path);
        if (!current.isDirectory() || current.isSymbolicLink() || !sameFile(current, verified.metadata)) unsafe();
        if (!contained(canonicalRoot, await realpath(verified.path))) unsafe();
      }
    };
    // #541: an absolute destination is canonicalized against the same reality
    // `canonicalRoot` came from, so the two are comparable. A relative one is
    // resolved against `canonicalRoot`, which is already canonical, and is
    // therefore untouched.
    const requested = path.isAbsolute(relPath) ? await canonicalizeAncestors(relPath) : relPath;
    const target = path.resolve(canonicalRoot, requested);
    const relative = path.relative(canonicalRoot, target);
    if (relative === "" || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) unsafe();

    const segments = relative.split(path.sep);
    let parent = canonicalRoot;
    for (const segment of segments.slice(0, -1)) {
      if (segment === "" || segment === "." || segment === "..") unsafe();
      const candidate = path.join(parent, segment);
      let metadata: Stats;
      try {
        metadata = await lstat(candidate);
      } catch (error) {
        if (!isMissing(error)) throw error;
        try {
          await mkdir(candidate, { mode: 0o700 });
        } catch (mkdirError) {
          if ((mkdirError as NodeJS.ErrnoException)?.code !== "EEXIST") throw mkdirError;
        }
        metadata = await lstat(candidate);
      }
      if (!metadata.isDirectory() || metadata.isSymbolicLink()) unsafe();
      const canonicalCandidate = await realpath(candidate);
      if (!contained(canonicalRoot, canonicalCandidate)) unsafe();
      verifiedDirectories.push({ path: candidate, metadata });
      parent = candidate;
    }

    await verifyDirectories();
    const canonicalParent = await realpath(parent);
    if (!contained(canonicalRoot, canonicalParent)) unsafe();

    let before: Stats | undefined;
    try {
      before = await lstat(target);
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
    if (before !== undefined && !safeRegularFile(before)) unsafe();
    if (before !== undefined && !contained(canonicalRoot, await realpath(target))) unsafe();

    const noFollow = typeof constants.O_NOFOLLOW === "number" ? constants.O_NOFOLLOW : 0;
    const flags = before === undefined
      ? constants.O_RDWR | constants.O_CREAT | constants.O_EXCL | noFollow
      : constants.O_RDWR | noFollow;
    handle = await open(target, flags, 0o600);

    const opened = await handle.stat();
    const atPath = await lstat(target);
    if (!safeRegularFile(opened) || !safeRegularFile(atPath) || !sameFile(opened, atPath)) unsafe();
    await verifyDirectories();
    if (!contained(canonicalRoot, await realpath(parent))) unsafe();
    if (!contained(canonicalRoot, await realpath(target))) unsafe();

    await testHooks.beforeFinalAuthorization?.();
    await verifyDirectories();
    if (!contained(canonicalRoot, await realpath(parent))) unsafe();
    if (!contained(canonicalRoot, await realpath(target))) unsafe();
    // These are the final awaited checks before the retained handle is
    // truncated: path identity and link count cannot be authorized from a
    // stale pre-open observation.
    const finalAtPath = await lstat(target);
    const finalOpened = await handle.stat();
    if (!safeRegularFile(finalOpened) || !safeRegularFile(finalAtPath) || !sameFile(finalOpened, finalAtPath)) unsafe();

    await handle.truncate(0);
    await handle.writeFile(contents, { encoding: "utf8" });
  } catch (error) {
    if (isUnsafeWorktreePathError(error)) throw error;
    throw new UnsafeWorktreePathError();
  } finally {
    await handle?.close().catch(() => undefined);
  }
}
