import { describe, expect, it } from 'vitest';
import { readdirSync } from 'node:fs';
import { buildGuideDirectory, guideGroups, type GuidePage } from './guide-directory';
import { guideMatches, normalizeGuideQuery } from '../src/scripts/guide-filter';

const pages = (): GuidePage[] => guideGroups.flatMap(group => group.slugs.map(slug => ({
  id: `guides/${slug}`,
  data: { title: `Title ${slug}`, description: `Description ${slug}`,
    journey: { level: 'Practitioner', time: 'Follow the procedure', outcome: `Outcome ${slug}` } },
})));

describe('the guide directory', () => {
  it('takes titles, descriptions and outcomes from the page rather than a copied catalog', () => {
    const input = pages();
    input[0].data.title = 'A revised page title';
    input[0].data.journey!.outcome = 'A revised outcome';
    const groups = buildGuideDirectory(input.reverse());
    expect(groups.map(group => group.id)).toEqual(guideGroups.map(group => group.id));
    expect(groups[0].guides[0]).toMatchObject({ title: 'A revised page title', outcome: 'A revised outcome' });
    expect(groups[0].guides[0].href).toBe('/guides/opt-in-a-repo/');
  });

  it('accounts for every authored guide, with no duplicate, fabricated or missing route', () => {
    const actual = readdirSync(new URL('../src/content/docs/guides', import.meta.url))
      .filter(name => /\.mdx?$/.test(name) && !/^index\./.test(name))
      .map(name => name.replace(/\.mdx?$/, '')).sort();
    const classified = guideGroups.flatMap(group => [...group.slugs]);
    expect(new Set(classified).size).toBe(classified.length);
    expect(classified.sort()).toEqual(actual);
  });

  it('ignores the landing page and other collections', () => {
    const input = [...pages(), { id: 'guides', data: { title: 'Guides', description: 'Index' } },
      { id: 'academy/example', data: { title: 'Academy', description: 'Separate course' } }];
    expect(buildGuideDirectory(input).flatMap(group => group.guides)).toHaveLength(pages().length);
  });

  it('fails clearly on a missing or duplicate guide rather than dropping a destination', () => {
    expect(() => buildGuideDirectory(pages().slice(1))).toThrow(/Missing guide/);
    expect(() => buildGuideDirectory([...pages(), pages()[0]])).toThrow(/Duplicate guide/);
  });

  it('requires deliberate classification for a newly authored guide', () => {
    expect(() => buildGuideDirectory([...pages(), { id: 'guides/new-route', data: {
      title: 'New', description: 'New', journey: { level: 'Practitioner', time: 'Review', outcome: 'New' },
    } }])).toThrow(/Unclassified guide/);
  });

  it.each(['title', 'description'] as const)('rejects an empty %s', field => {
    const input = pages(); input[0].data[field] = ' ';
    expect(() => buildGuideDirectory(input)).toThrow(/Incomplete guide/);
  });

  it('does not invent a time or outcome when metadata is absent', () => {
    const input = pages(); delete input[0].data.journey;
    expect(() => buildGuideDirectory(input)).toThrow(/Incomplete guide/);
  });
});

describe('local guide filtering', () => {
  const guide = { category: 'review-and-ship', searchText: 'Review a change. Inbound pull request. Keep a checkpoint report.' };
  it('combines category and all search terms without a command catalog dependency', () => {
    expect(guideMatches(guide, '', 'all')).toBe(true);
    expect(guideMatches(guide, 'PULL review', 'review-and-ship')).toBe(true);
    expect(guideMatches(guide, 'review missing', 'all')).toBe(false);
    expect(guideMatches(guide, 'review', 'make-a-change')).toBe(false);
    expect(guideMatches(guide, 'checkpoint', 'all')).toBe(true);
  });
  it('normalizes whitespace and compatibility characters and bounds free text', () => {
    expect(normalizeGuideQuery('  ＰＵＬＬ   review\n')).toBe('pull review');
    expect(normalizeGuideQuery('a'.repeat(1000)).length).toBe(160);
    expect(guideMatches(guide, '[<script>]', 'all')).toBe(false);
  });
});
