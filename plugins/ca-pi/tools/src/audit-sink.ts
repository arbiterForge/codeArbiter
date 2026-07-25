/**
 * audit-sink.ts - the single owner of every Pi write into a project's governance log.
 *
 * Permission decisions, background-job lifecycle rows, bridge failures, child dispatches, and
 * confirmed compactions all land in the same project-local `.codearbiter/gate-events.log`. That path is
 * derived from a caller-supplied project cwd, so a trusted project that plants a symlink,
 * junction, or hardlink there could otherwise redirect a governance record onto another
 * same-user file and leave the real log without it. `node:fs`'s own `appendFile` follows all
 * three, which is why no producer is allowed to call it directly - `module-structure.test.ts`
 * fails when a second implementation appears.
 *
 * The primitive answers one question - "is this still the project's own regular, single-linked
 * log?" - at every step where the answer could have changed:
 *
 * 1. The project root and `.codearbiter` are canonicalized; a linked or escaping state
 *    directory is rejected before any target path is formed.
 * 2. The target is opened `O_NOFOLLOW` (where the platform has it), and created
 *    `O_CREAT|O_EXCL` so a hardlink raced into an absent target cannot be adopted.
 * 3. The opened handle's device/inode identity is compared against the validated path before
 *    the append, and again after it, so a swap on either side of the write is caught.
 *
 * Every failure is a `false` return, never a throw: an unavailable or hostile sink must not
 * change the enforcement outcome the caller already decided. Callers keep their own fail
 * direction and emit only their own bounded diagnostic.
 */
import { constants as fsConstants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { relative, resolve } from "node:path";

import { lexicallyInside } from "./path-boundary.ts";

/** The single governance log file name every Pi producer appends to. */
const AUDIT_LOG_NAME = "gate-events.log";

/** The project-relative state directory that must hold it. */
const AUDIT_STATE_DIRECTORY = ".codearbiter";

/** One row must stay small enough that a hostile field cannot bloat or straddle the log. */
export const MAX_AUDIT_LINE_BYTES = 2_048;

export interface AuditSinkStatsPort {
  readonly dev: number;
  readonly ino: number;
  readonly nlink: number;
  readonly size: number;
  isDirectory(): boolean;
  isFile(): boolean;
  isSymbolicLink(): boolean;
}

export interface AuditSinkHandlePort {
  stat(): Promise<AuditSinkStatsPort>;
  appendFile(data: string, options: { encoding: "utf8" }): Promise<unknown>;
  sync(): Promise<void>;
  close(): Promise<void>;
}

/** The filesystem seam, injectable so the adversarial race cases are testable from either host. */
export interface AuditSinkIoPort {
  realpath(path: string): Promise<string>;
  lstat(path: string): Promise<AuditSinkStatsPort>;
  open(path: string, flags: number, mode?: number): Promise<AuditSinkHandlePort>;
}

export const NODE_AUDIT_SINK_IO: AuditSinkIoPort = Object.freeze({ realpath, lstat, open });

function sameAuditFile(left: AuditSinkStatsPort, right: AuditSinkStatsPort): boolean {
  return left.isFile() && right.isFile()
    && !left.isSymbolicLink() && !right.isSymbolicLink()
    && left.nlink === 1 && right.nlink === 1
    && left.dev === right.dev && left.ino === right.ino;
}

function sameAuditDirectory(left: AuditSinkStatsPort, right: AuditSinkStatsPort): boolean {
  return left.isDirectory() && right.isDirectory()
    && !left.isSymbolicLink() && !right.isSymbolicLink()
    && left.dev === right.dev && left.ino === right.ino;
}

async function openedAuditTarget(
  target: string,
  io: AuditSinkIoPort,
): Promise<Readonly<{ handle: AuditSinkHandlePort; identity: AuditSinkStatsPort }> | undefined> {
  const noFollow = typeof fsConstants.O_NOFOLLOW === "number" ? fsConstants.O_NOFOLLOW : 0;
  const existingFlags = fsConstants.O_WRONLY | fsConstants.O_APPEND | noFollow;
  const createFlags = existingFlags | fsConstants.O_CREAT | fsConstants.O_EXCL;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let expected: AuditSinkStatsPort | undefined;
    try {
      expected = await io.lstat(target);
      if (!expected.isFile() || expected.isSymbolicLink() || expected.nlink !== 1) return undefined;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") return undefined;
    }
    let handle: AuditSinkHandlePort;
    try {
      handle = await io.open(target, expected === undefined ? createFlags : existingFlags, 0o600);
    } catch (error) {
      if (expected === undefined && (error as NodeJS.ErrnoException).code === "EEXIST" && attempt === 0) continue;
      return undefined;
    }
    try {
      const opened = await handle.stat();
      const pathname = await io.lstat(target);
      if (!sameAuditFile(opened, pathname) || expected !== undefined && !sameAuditFile(opened, expected)) {
        await handle.close();
        return undefined;
      }
      return Object.freeze({ handle, identity: opened });
    } catch {
      try { await handle.close(); } catch { /* fail closed below */ }
      return undefined;
    }
  }
  return undefined;
}

/**
 * Append exactly one already-rendered governance row to the project's own
 * `.codearbiter/gate-events.log`, resolved beneath `cwd`.
 *
 * `line` must be a single bounded line ending in one newline: the sink is the last place that
 * can refuse a forged embedded newline, and it does, rather than letting one producer's
 * unsanitized field write a second structurally valid row.
 *
 * Returns whether the row is durably in the project's own log. Never throws.
 */
export async function appendAuditLineWithIo(cwd: string, line: string, io: AuditSinkIoPort): Promise<boolean> {
  try {
    if (Buffer.byteLength(line, "utf8") > MAX_AUDIT_LINE_BYTES
      || !line.endsWith("\n") || line.slice(0, -1).includes("\n")) return false;
    const root = await io.realpath(cwd);
    const statePath = resolve(root, AUDIT_STATE_DIRECTORY);
    const stateInfo = await io.lstat(statePath);
    if (!stateInfo.isDirectory() || stateInfo.isSymbolicLink()) return false;
    const state = await io.realpath(statePath);
    const stateRelative = relative(root, state);
    if (stateRelative === "" || !lexicallyInside(state, root) || resolve(root, stateRelative) !== state) return false;
    const stateIdentity = await io.lstat(state);
    if (!sameAuditDirectory(stateInfo, stateIdentity)) return false;
    const stateIsCurrent = async (): Promise<boolean> => {
      try {
        return await io.realpath(statePath) === state
          && sameAuditDirectory(stateIdentity, await io.lstat(statePath));
      } catch {
        return false;
      }
    };
    if (!await stateIsCurrent()) return false;
    const target = resolve(state, AUDIT_LOG_NAME);
    const opened = await openedAuditTarget(target, io);
    if (opened === undefined) return false;
    const { handle, identity } = opened;
    try {
      const before = await handle.stat();
      const beforePath = await io.lstat(target);
      if (!sameAuditFile(identity, before) || !sameAuditFile(before, beforePath) || !await stateIsCurrent()) return false;
      await handle.appendFile(line, { encoding: "utf8" });
      await handle.sync();
      const after = await handle.stat();
      const afterPath = await io.lstat(target);
      if (!sameAuditFile(before, after) || !sameAuditFile(after, afterPath)
        || after.size < before.size + Buffer.byteLength(line, "utf8") || !await stateIsCurrent()) return false;
    } finally {
      await handle.close();
    }
    return true;
  } catch {
    return false;
  }
}

/** `appendAuditLineWithIo` bound to the real filesystem: the call every producer makes. */
export async function appendAuditLine(cwd: string, line: string): Promise<boolean> {
  return await appendAuditLineWithIo(cwd, line, NODE_AUDIT_SINK_IO);
}

/**
 * Render one governance field so a hostile value cannot forge a second row.
 *
 * The shared redactor already strips secrets and control characters, but it deliberately
 * preserves newlines for human-readable diagnostics. A single log line cannot, so the residual
 * line breaks collapse to spaces here rather than causing the sink to drop the whole record.
 */
export function auditField(value: string): string {
  return value.replaceAll("\n", " ");
}
