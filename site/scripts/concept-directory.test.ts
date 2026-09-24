import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { buildJourneySidebar } from './journey-navigation';
import { conceptGroups, conceptBackground, buildConceptDirectory } from './concept-directory';

const all = [...conceptGroups.flatMap(group => group.items.map(item => ({ slug: item.slug }))), ...conceptBackground];
const pages = () => all.map(item => ({ id: item.slug, data: { title: `Title ${item.slug}`, description: `Description ${item.slug}` } }));

describe('concept discovery', () => {
  it('includes every concept with one primary classification and preserves background routes', () => {
    const files = readdirSync('src/content/docs/concepts').filter(file => /\.mdx?$/.test(file)).map(file => `concepts/${file.replace(/\.mdx?$/, '')}`);
    expect(all.map(item => item.slug).filter(slug => slug.startsWith('concepts/')).sort()).toEqual(files.sort());
    expect(new Set(all.map(item => item.slug)).size).toBe(all.length);
    expect(conceptGroups).toHaveLength(5);
  });
  it('uses the content collection for labels and fails instead of dropping a missing destination', () => {
    const input = pages(); input[0].data.title = 'Revised title';
    expect(buildConceptDirectory(input)[0].items[0].title).toBe('Revised title');
    expect(() => buildConceptDirectory(input.slice(1))).toThrow(/Missing concept/);
  });
  it('shares exact group order and membership with the sidebar', () => {
    const sidebar = buildJourneySidebar([], []).find(group => group.label === 'Concepts')!;
    const groups = sidebar.items.filter(item => 'items' in item).slice(0, 5);
    expect(groups.map(group => group.label)).toEqual(conceptGroups.map(group => group.title));
    groups.forEach((group, index) => {
      expect('items' in group && group.items.map(item => 'slug' in item && item.slug))
        .toEqual(conceptGroups[index].items.map(item => item.slug));
      if ('items' in group) group.items.forEach(item => expect(item.label).toBeTruthy());
    });
  });
  it('keeps the approved program separate from execution or release proof', () => {
    const plan = readFileSync('CONCEPTS-OVERHAUL.md', 'utf8');
    for (const scope of ['C01:', 'C02:', 'C03:', 'C04:']) expect(plan).toContain(scope);
    expect(plan).toContain('not a native artifact-engine approval');
    expect(plan).toContain('NOT_STARTED');
  });
});
