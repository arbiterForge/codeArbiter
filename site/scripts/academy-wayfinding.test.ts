import { describe, expect, it } from 'vitest';
import { buildAcademyWayfinding } from './academy-wayfinding';
import { bookmarkKey, readBookmark, saveBookmark, clearBookmark } from '../src/scripts/academy-bookmark';

const lessons = [
  { id: 'F01-first', track: 'foundations', title: 'First', prerequisites: [], nextLab: 'P01-second' },
  { id: 'P01-second', track: 'practitioner', title: 'Second', prerequisites: ['F01-first'], nextLab: 'U01-last' },
  { id: 'U01-last', track: 'power-user', title: 'Last', prerequisites: ['Read the local evidence first'], nextLab: null },
] as const;
const context = { release: 'preview-0.32', commit: 'a'.repeat(40), base: '/docs/', lessonIds: lessons.map(l => l.id) };
/** Provide isolated browser storage without sharing state between test cases. */
function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => { values.set(k, v); }, removeItem: (k: string) => { values.delete(k); } };
}

describe('source-owned Academy wayfinding', () => {
  it('preserves published order and explicit next routes across track boundaries', () => {
    const result = buildAcademyWayfinding(lessons);
    expect(result[1]).toMatchObject({ id: 'P01-second', position: 2, total: 3, trackPosition: 1, trackTotal: 1, previousId: 'F01-first', nextId: 'U01-last' });
    expect(result[0].previousId).toBeNull();
    expect(result[2].nextId).toBeNull();
  });
  it('does not silently invent a successor or convert prose into a prerequisite ID', () => {
    const result = buildAcademyWayfinding([{ ...lessons[0], nextLab: null }, lessons[1], lessons[2]]);
    expect(result[0].nextId).toBeNull();
    expect(result[2].prerequisites).toEqual([{ label: 'Read the local evidence first', lessonId: null }]);
    expect(result[1].prerequisites).toEqual([{ label: 'F01 · First', lessonId: 'F01-first' }]);
  });
  it.each([
    [[lessons[0], lessons[0]], /duplicate/i],
    [[{ ...lessons[0], nextLab: 'F99-missing' }], /next/i],
    [[{ ...lessons[0], nextLab: 'F01-first' }], /itself/i],
    [[{ ...lessons[0], id: '../../outside', nextLab: null }], /lesson ID/i],
    [[{ ...lessons[0], track: 'unpublished', nextLab: null }], /track/i],
  ])('rejects inconsistent navigation inputs before publishing links', (input, message) => {
    expect(() => buildAcademyWayfinding(input)).toThrow(message);
  });
});

describe('opt-in Academy bookmark, not verifier progress', () => {
  it('reads without writing and saves only the chosen lesson and source identity', () => {
    const storage = memory();
    expect(readBookmark(() => storage, context)).toEqual({ state: 'empty' });
    expect(storage.values.size).toBe(0);
    expect(saveBookmark(() => storage, context, 'P01-second')).toBe(true);
    expect(readBookmark(() => storage, context)).toEqual({ state: 'ready', lessonId: 'P01-second' });
    expect(JSON.parse(storage.getItem(bookmarkKey(context.base))!)).toEqual({ schemaVersion: 1, release: context.release, commit: context.commit, lessonId: 'P01-second' });
  });
  it('separates deployment paths and removes only its own key', () => {
    const storage = memory();
    storage.setItem('academy-os', 'linux');
    saveBookmark(() => storage, context, 'F01-first');
    saveBookmark(() => storage, { ...context, base: '/' }, 'U01-last');
    expect(bookmarkKey('/docs')).toBe(bookmarkKey('/docs/'));
    expect(clearBookmark(() => storage, context.base)).toBe(true);
    expect(storage.getItem('academy-os')).toBe('linux');
    expect(readBookmark(() => storage, { ...context, base: '/' })).toEqual({ state: 'ready', lessonId: 'U01-last' });
  });
  it.each([{ release: 'preview-0.33' }, { commit: 'b'.repeat(40) }])('rejects a different curriculum identity even with the same lesson ID', (delta) => {
    const storage = memory(); saveBookmark(() => storage, context, 'P01-second');
    expect(readBookmark(() => storage, { ...context, ...delta })).toEqual({ state: 'stale' });
  });
  it.each(['null', '[]', '{}', '{', 'x'.repeat(2048), JSON.stringify({ schemaVersion: 1, release: context.release, commit: context.commit, lessonId: 'https://evil.invalid/' }), JSON.stringify({ schemaVersion: 1, release: context.release, commit: context.commit, lessonId: 'F01-first', completed: true })])('rejects corrupt, oversized, URL or completion-bearing records', (raw) => {
    const storage = memory();storage.setItem(bookmarkKey(context.base), raw);
    expect(readBookmark(() => storage, context)).toEqual({ state: 'invalid' });
  });
  it('does not write an unknown lesson', () => {
    const storage = memory();expect(saveBookmark(() => storage, context, 'F99-missing')).toBe(false);expect(storage.values.size).toBe(0);
  });
  it('handles denied storage acquisition and access without hiding the reading path', () => {
    const denied = () => { throw new Error('denied'); };
    for (const acquire of [denied, () => ({ getItem: denied, setItem: denied, removeItem: denied })]) {
      expect(readBookmark(acquire, context)).toEqual({ state: 'unavailable' });
      expect(saveBookmark(acquire, context, 'F01-first')).toBe(false);
      expect(clearBookmark(acquire, context.base)).toBe(false);
    }
  });
});
