/** The optional bookmark stores a reading destination, never verifier progress. */
export type BookmarkContext = {
  release: string;
  commit: string;
  base: string;
  lessonIds: readonly string[];
};
export type BookmarkStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};
export type BookmarkState =
  | { state: 'empty' | 'invalid' | 'stale' | 'unavailable' }
  | { state: 'ready'; lessonId: string };

/** Separate bookmarks for sites served under different paths on the same origin. */
export function bookmarkKey(base: string): string {
  return `codearbiter:academy-bookmark:v1:${encodeURIComponent(base.replace(/\/$/, '') || '/')}`;
}

/** Read without writing; only an inventory ID may become a navigation destination. */
export function readBookmark(acquire: () => BookmarkStorage, context: BookmarkContext): BookmarkState {
  let raw: string | null;
  try { raw = acquire().getItem(bookmarkKey(context.base)); }
  catch { return { state: 'unavailable' }; }
  if (raw === null) return { state: 'empty' };
  if (raw.length > 1024) return { state: 'invalid' };
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { state: 'invalid' };
    const record = value as Record<string, unknown>;
    if (Object.keys(record).sort().join(',') !== 'commit,lessonId,release,schemaVersion' ||
        record.schemaVersion !== 1 || typeof record.release !== 'string' ||
        typeof record.commit !== 'string' || !/^[a-f0-9]{40}$/.test(record.commit) ||
        typeof record.lessonId !== 'string' || !/^[FPU]\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(record.lessonId)) {
      return { state: 'invalid' };
    }
    if (record.release !== context.release || record.commit !== context.commit) return { state: 'stale' };
    return context.lessonIds.includes(record.lessonId)
      ? { state: 'ready', lessonId: record.lessonId }
      : { state: 'invalid' };
  } catch { return { state: 'invalid' }; }
}

/** Called only by an explicit Save button, not by lesson visits or navigation. */
export function saveBookmark(acquire: () => BookmarkStorage, context: BookmarkContext, lessonId: string): boolean {
  if (!context.lessonIds.includes(lessonId)) return false;
  try {
    acquire().setItem(bookmarkKey(context.base), JSON.stringify({
      schemaVersion: 1, release: context.release, commit: context.commit, lessonId,
    }));
    return true;
  } catch { return false; }
}

/** Remove this site's bookmark only; retain command preferences and other storage. */
export function clearBookmark(acquire: () => BookmarkStorage, base: string): boolean {
  try { acquire().removeItem(bookmarkKey(base)); return true; }
  catch { return false; }
}
