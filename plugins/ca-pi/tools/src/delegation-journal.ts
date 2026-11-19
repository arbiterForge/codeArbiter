/**
 * delegation-journal.ts - durable exclusive claims and outcomes for delegated Pi operations
 * (PI-D04, the Pi side of the NT-10 seam).
 *
 * Owner: host bookkeeping, NOT the artifact store. Records live under the repository's Git
 * common directory (`<git-common>/codearbiter/pi-delegation/v1/`), outside the working tree
 * and outside the artifact reserved root, so no NT-02 namespace registration applies and no
 * repository file is dirtied. This is the seam NT-10 is asked to keep compatible:
 *
 * - one record file per (operation id, phase), created O_CREAT|O_EXCL so exactly one claim can
 *   exist per operation id; a second claimant observes the first instead of executing;
 * - every record is fsynced, and the directory is fsynced where the platform allows it (POSIX;
 *   Windows cannot open a directory for sync, which is reported as a limit, not hidden);
 * - linked (symlink/junction) directories and multiply-linked record files are refused;
 * - a claim is written before any effect and an observation before any acknowledgement;
 * - a claim with no observation reads as `outcome-unknown`, never "not executed";
 * - records are closed versioned data with no tokens, file contents or command text; unknown
 *   versions are left in place and reported, never deleted or rewritten.
 *
 * A false/undefined result here never means "nothing happened": a write that failed after
 * creating its file leaves an uncertain record, which readers treat as unknown.
 */
import { constants as fsConstants } from "node:fs";
import { createHash } from "node:crypto";
import { lstat, mkdir, open, opendir, realpath } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";

import { lexicallyInside } from "./path-boundary.ts";
import { canonicalJson, decodeJournalRecord, encodeJournalRecord } from "./delegation-contract.ts";
import type { JournalRecord } from "./delegation-contract.ts";

const JOURNAL_SEGMENTS = ["codearbiter", "pi-delegation", "v1"] as const;
const OPERATION_ID = /^[0-9a-f]{64}$/u;
const RECORD_FILE = /^([0-9a-f]{64})\.(claimed|started|observed)\.json$/u;
const MAX_SCAN_RECORDS = 4_096;
const MAX_GIT_POINTER_BYTES = 4_096;
const STORAGE_SCHEMA = "codearbiter.pi-delegation-storage/1";
interface JournalIdentity { readonly repositoryId: string; readonly worktreeId: string; }

async function boundedNames(root: string): Promise<string[]> {
  const names: string[] = [];
  const directory = await opendir(root);
  for await (const entry of directory) {
    if (names.length >= MAX_SCAN_RECORDS) throw new Error("Delegation journal scan exceeded bounds.");
    names.push(entry.name);
  }
  return names;
}

export type ClaimResult =
  | Readonly<{ state: "claimed" }>
  | Readonly<{ state: "exists"; claim: JournalRecord | undefined; observed: JournalRecord | undefined }>
  | Readonly<{ state: "unavailable" }>;

export interface UnresolvedOperation {
  readonly operationId: string;
  readonly claim: JournalRecord | undefined;
  readonly observed?: JournalRecord;
  readonly started?: JournalRecord;
}

export interface DelegationJournal {
  readonly root: string;
  readonly identity: JournalIdentity;
  claim(record: JournalRecord): Promise<ClaimResult>;
  observe(record: JournalRecord): Promise<boolean>;
  started(record: JournalRecord): Promise<boolean>;
  read(operationId: string): Promise<{ claim?: JournalRecord; observed?: JournalRecord; unreadable: boolean }>;
  /** Read-only: claims without observations (unknown outcomes) and unreadable records. */
  unresolved(): Promise<readonly UnresolvedOperation[]>;
}

async function plainDirectory(path: string): Promise<boolean> {
  try {
    const stats = await lstat(path);
    if (!stats.isDirectory() || stats.isSymbolicLink()) return false;
    const canonical = await realpath(path); const lexical = resolve(path);
    return process.platform === "win32" ? canonical.toLowerCase() === lexical.toLowerCase() : canonical === lexical;
  } catch { return false; }
}

async function readBounded(path: string, limit: number): Promise<string | undefined> {
  let handle;
  try {
    const stats = await lstat(path);
    if (!stats.isFile() || stats.isSymbolicLink() || stats.nlink !== 1 || stats.size > limit) return undefined;
    handle = await open(path, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
    const opened = await handle.stat();
    if (!opened.isFile() || opened.nlink !== 1 || opened.dev !== stats.dev || opened.ino !== stats.ino || opened.size > limit) return undefined;
    const bytes = Buffer.alloc(limit + 1);
    const result = await handle.read(bytes, 0, bytes.length, 0);
    if (result.bytesRead > limit) return undefined;
    const after = await lstat(path);
    if (!after.isFile() || after.isSymbolicLink() || after.nlink !== 1 || after.dev !== opened.dev || after.ino !== opened.ino
      || after.size !== opened.size || after.mtimeMs !== opened.mtimeMs) return undefined;
    return bytes.subarray(0, result.bytesRead).toString("utf8");
  } catch { return undefined; }
  finally { await handle?.close().catch(() => undefined); }
}

/** Resolves the Git common directory from the worktree's `.git` entry using the filesystem only
 * (no git subprocess, no project-controlled executable). Linked worktrees use `gitdir:` plus
 * `commondir`; anything linked, oversized or malformed is refused. */
export async function resolveGitCommonDir(worktree: string): Promise<string | undefined> {
  try {
    const root = await realpath(worktree);
    const dotGit = resolve(root, ".git");
    const stats = await lstat(dotGit);
    if (stats.isSymbolicLink()) return undefined;
    if (stats.isDirectory()) return await realpath(dotGit);
    if (!stats.isFile()) return undefined;
    const pointer = await readBounded(dotGit, MAX_GIT_POINTER_BYTES);
    const match = pointer === undefined ? null : /^gitdir: (.+?)\r?\n?$/u.exec(pointer);
    if (match === null) return undefined;
    const gitDir = isAbsolute(match[1]!) ? match[1]! : resolve(root, match[1]!);
    if (!await plainDirectory(gitDir)) return undefined;
    // A plain main .git directory was handled above. Pointer layouts must
    // positively name their common owner; absence cannot distinguish a broken
    // linked worktree from an unqualified separate-Git-dir/submodule layout.
    const common = await readBounded(resolve(gitDir, "commondir"), MAX_GIT_POINTER_BYTES);
    const commonMatch = common === undefined ? null : /^([^\r\n\0]+)\r?\n?$/u.exec(common);
    if (commonMatch === null) return undefined;
    const commonPath = commonMatch[1]!;
    if (commonPath.trim() !== commonPath || /[\u0000-\u001f\u007f]/u.test(commonPath)) return undefined;
    const commonDir = isAbsolute(commonPath) ? commonPath : resolve(gitDir, commonPath);
    return await plainDirectory(commonDir) ? await realpath(commonDir) : undefined;
  } catch { return undefined; }
}

async function ensureJournalRoot(commonDir: string, existingOnly = false): Promise<string | undefined> {
  let cursor = commonDir;
  for (const segment of JOURNAL_SEGMENTS) {
    cursor = resolve(cursor, segment);
    if (!existingOnly) {
      try { await mkdir(cursor); } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") return undefined;
      }
    }
    if (!await plainDirectory(cursor)) return undefined;
  }
  try {
    const canonical = await realpath(cursor);
    return lexicallyInside(canonical, commonDir) ? canonical : undefined;
  } catch { return undefined; }
}

async function syncDirectory(path: string): Promise<void> {
  if (process.platform === "win32") return; // Windows cannot open a directory handle for fsync.
  const handle = await open(path, fsConstants.O_RDONLY);
  try { await handle.sync(); } finally { await handle.close(); }
}

export interface JournalIo {
  /** Test seam: fault injection between create and sync. */
  readonly afterCreate?: (path: string) => Promise<void> | void;
  readonly existingOnly?: boolean;
}

async function createExclusive(root: string, name: string, text: string, io: JournalIo): Promise<"created" | "exists" | "failed"> {
  const path = resolve(root, name);
  let handle;
  try {
    handle = await open(path, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY
      | (fsConstants.O_NOFOLLOW ?? 0), 0o600);
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EEXIST" ? "exists" : "failed";
  }
  try {
    await io.afterCreate?.(path);
    await handle.writeFile(text, "utf8");
    await handle.sync();
    const stats = await handle.stat();
    if (!stats.isFile() || stats.nlink !== 1) return "failed";
  } catch {
    return "failed";
  } finally {
    await handle.close().catch(() => undefined);
  }
  try { await syncDirectory(root); } catch { return "failed"; }
  return "created";
}

async function readRecord(root: string, name: string, identity: JournalIdentity): Promise<{ record?: JournalRecord; present: boolean; unreadable: boolean; foreign?: boolean }> {
  const path = resolve(root, name);
  try {
    const stats = await lstat(path);
    if (!stats.isFile() || stats.isSymbolicLink() || stats.nlink !== 1 || stats.size > 16_384) {
      return { present: true, unreadable: true };
    }
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "ENOENT"
      ? { present: false, unreadable: false }
      : { present: true, unreadable: true };
  }
  try {
    const text = await readBounded(path, 16_384);
    if (text === undefined) return { present: true, unreadable: true };
    const stored = JSON.parse(text) as Record<string, unknown>;
    if (stored === null || Array.isArray(stored) || typeof stored !== "object" || canonicalJson(stored) !== text
      || Object.keys(stored).sort().join(",") !== "record,repositoryId,schema,worktreeId" || stored.schema !== STORAGE_SCHEMA
      || stored.repositoryId !== identity.repositoryId || typeof stored.worktreeId !== "string" || !OPERATION_ID.test(stored.worktreeId)) {
      return { present: true, unreadable: true };
    }
    if (stored.worktreeId !== identity.worktreeId) return { present: true, unreadable: false, foreign: true };
    const record = decodeJournalRecord(canonicalJson(stored.record));
    if (name !== `${record.operationId}.${record.phase}.json`) return { present: true, unreadable: true };
    return { record, present: true, unreadable: false };
  } catch {
    return { present: true, unreadable: true };
  }
}

function sameClaim(claim: JournalRecord, outcome: JournalRecord): boolean {
  return claim.phase === "claimed" && (outcome.phase === "observed" || outcome.phase === "started")
    && (["operationId", "runId", "callerCorrelation", "role", "tool", "digest", "profile", "target", "requestId", "consentSource", "permissionCorrelation"] as const)
      .every((key) => claim[key] === outcome[key]);
}

export async function openDelegationJournal(worktree: string, io: JournalIo = {}): Promise<DelegationJournal | undefined> {
  const commonDir = await resolveGitCommonDir(worktree);
  if (commonDir === undefined) return undefined;
  const root = await ensureJournalRoot(commonDir, io.existingOnly);
  if (root === undefined) return undefined;
  const canonicalWorktree = await realpath(worktree);
  const rootIdentity = await lstat(root);
  const pathIdentity = (path: string) => createHash("sha256").update(process.platform === "win32" ? path.toLowerCase() : path).digest("hex");
  const identity: JournalIdentity = Object.freeze({ repositoryId: pathIdentity(commonDir), worktreeId: pathIdentity(canonicalWorktree) });
  const readOwned = (name: string) => readRecord(root, name, identity);
  const encodeStored = (record: JournalRecord) => canonicalJson({ schema: STORAGE_SCHEMA, ...identity, record: JSON.parse(encodeJournalRecord(record)) });
  const stillOwned = async () => {
    try {
      const current = await lstat(root);
      return current.dev === rootIdentity.dev && current.ino === rootIdentity.ino
        && await plainDirectory(root) && await realpath(root) === root
        && await realpath(worktree) === canonicalWorktree && await resolveGitCommonDir(worktree) === commonDir;
    } catch { return false; }
  };
  return Object.freeze({
    root,
    identity,
    async claim(record: JournalRecord): Promise<ClaimResult> {
      if (record.phase !== "claimed" || !OPERATION_ID.test(record.operationId) || !await stillOwned()) {
        return { state: "unavailable" };
      }
      let text: string;
      try { text = encodeStored(record); } catch { return { state: "unavailable" }; }
      try {
        // Retention is never silently pruned. Stop new effects before the bounded journal
        // fills; existing claims can still be observed and inspected without new authority.
        const names = await boundedNames(root);
        if (!names.includes(`${record.operationId}.claimed.json`) && names.length >= MAX_SCAN_RECORDS - 3) {
          return { state: "unavailable" };
        }
      } catch { return { state: "unavailable" }; }
      const outcome = await createExclusive(root, `${record.operationId}.claimed.json`, text, io);
      if (outcome === "created") return { state: "claimed" };
      if (outcome === "exists") {
        const claim = await readOwned(`${record.operationId}.claimed.json`);
        const observed = await readOwned(`${record.operationId}.observed.json`);
        if (claim.foreign || observed.foreign) return { state: "unavailable" };
        return { state: "exists", claim: claim.record,
          observed: claim.record !== undefined && observed.record !== undefined && sameClaim(claim.record, observed.record)
            ? observed.record : undefined };
      }
      // A failed claim write may still have left bytes: it is NOT proof of absence, and it is
      // never permission to execute.
      return { state: "unavailable" };
    },
    async observe(record: JournalRecord): Promise<boolean> {
      if (record.phase !== "observed" || !OPERATION_ID.test(record.operationId) || !await stillOwned()) return false;
      const claim = await readOwned(`${record.operationId}.claimed.json`);
      if (claim.record === undefined || !sameClaim(claim.record, record)) return false;
      let text: string;
      try { text = encodeStored(record); } catch { return false; }
      return await createExclusive(root, `${record.operationId}.observed.json`, text, io) === "created";
    },
    async started(record: JournalRecord): Promise<boolean> {
      if (record.phase !== "started" || !OPERATION_ID.test(record.operationId) || !await stillOwned()) return false;
      const claim = await readOwned(`${record.operationId}.claimed.json`);
      if (claim.record === undefined || !sameClaim(claim.record, record)) return false;
      let text: string;
      try { text = encodeStored(record); } catch { return false; }
      return await createExclusive(root, `${record.operationId}.started.json`, text, io) === "created";
    },
    async read(operationId: string) {
      if (!OPERATION_ID.test(operationId) || !await stillOwned()) return { unreadable: true };
      const claim = await readOwned(`${operationId}.claimed.json`);
      const observed = await readOwned(`${operationId}.observed.json`);
      const mismatched = observed.record !== undefined
        && (claim.record === undefined || !sameClaim(claim.record, observed.record));
      return {
        ...(claim.record === undefined ? {} : { claim: claim.record }),
        ...(observed.record === undefined || mismatched ? {} : { observed: observed.record }),
        unreadable: claim.unreadable || observed.unreadable || mismatched || claim.foreign === true || observed.foreign === true,
      };
    },
    async unresolved(): Promise<readonly UnresolvedOperation[]> {
      let names: string[];
      if (!await stillOwned()) throw new Error("Delegation journal scan unavailable.");
      try { names = await boundedNames(root); } catch { throw new Error("Delegation journal scan unavailable or exceeded bounds."); }
      const ids = new Set<string>();
      const observedIds = new Set<string>();
      for (const name of names) {
        const match = RECORD_FILE.exec(name);
        if (match === null) continue;
        ids.add(match[1]!);
        if (match[2] === "observed") observedIds.add(match[1]!);
      }
      const result: UnresolvedOperation[] = [];
      for (const id of ids) {
        const claim = await readOwned(`${id}.claimed.json`);
        const observed = observedIds.has(id) ? await readOwned(`${id}.observed.json`) : undefined;
        const started = await readOwned(`${id}.started.json`);
        if (claim.foreign || observed?.foreign || started.foreign) continue;
        if (observed?.record !== undefined && claim.record !== undefined
          && sameClaim(claim.record, observed.record) && observed.record.execution !== "outcome-unknown"
          && observed.record.containment !== "unverified" && !claim.unreadable && !started.unreadable
          && (started.record === undefined || sameClaim(claim.record, started.record))) continue;
        result.push(Object.freeze({ operationId: id, claim: claim.record,
          ...(started.record === undefined || claim.record === undefined || !sameClaim(claim.record, started.record)
            ? {} : { started: started.record }),
          ...(observed?.record === undefined ? {} : { observed: observed.record }) }));
      }
      return Object.freeze(result);
    },
  });
}

export interface DelegationRecoverySummary {
  readonly state: "clear" | "pending" | "unavailable";
  readonly count: number;
  readonly operationIds: readonly string[];
}

/** Bounded inspection only: never creates a journal, restores a token or replays an effect. */
export async function readDelegationRecovery(worktree: string): Promise<DelegationRecoverySummary> {
  const unavailable = (): DelegationRecoverySummary => ({ state: "unavailable", count: 0, operationIds: [] });
  const commonDir = await resolveGitCommonDir(worktree);
  if (commonDir === undefined) return unavailable();
  let cursor = commonDir;
  for (const segment of JOURNAL_SEGMENTS) {
    cursor = resolve(cursor, segment);
    try {
      const observed = await lstat(cursor);
      if (!observed.isDirectory() || observed.isSymbolicLink()) return unavailable();
    } catch (error) {
      return (error as NodeJS.ErrnoException).code === "ENOENT"
        ? { state: "clear", count: 0, operationIds: [] } : unavailable();
    }
  }
  try {
    const journal = await openDelegationJournal(worktree, { existingOnly: true });
    if (journal === undefined) return unavailable();
    const operations = await journal.unresolved();
    return { state: operations.length === 0 ? "clear" : "pending", count: operations.length,
      operationIds: operations.slice(0, 8).map((operation) => operation.operationId) };
  } catch { return unavailable(); }
}
