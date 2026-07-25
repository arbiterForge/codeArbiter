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
    const target = path.resolve(canonicalRoot, relPath);
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
