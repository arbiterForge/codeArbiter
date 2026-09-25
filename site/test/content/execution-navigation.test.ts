import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fragmentId } from '../../src/scripts/execution-map-navigation';
import { workflows } from '../../scripts/execution-maps/workflows';
import { workflowMapHref } from '../../scripts/execution-maps/locations';

describe('explicit chapter addresses', () => {
  it('decodes a literal fragment once without treating it as a CSS selector', () => {
    expect(fragmentId('#sprint-execution-map-handoff')).toBe('sprint-execution-map-handoff');
    expect(fragmentId('#a%3Ab')).toBe('a:b');
    expect(fragmentId('#%2520')).toBe('%20');
    expect(fragmentId('#[data-map-chapter]')).toBe('[data-map-chapter]');
  });
  it('ignores missing, malformed and unbounded values', () => {
    for (const hash of ['', '#', 'not-a-fragment', '#%E0%A4%A', '#' + 'a'.repeat(1024)]) expect(fragmentId(hash)).toBeUndefined();
  });
  it('registers one unique literal destination per route without replacing procedure URLs', () => {
    expect(new Set(workflows.map(w => workflowMapHref(w))).size).toBe(workflows.length);
    for (const w of workflows) {
      const url = new URL(workflowMapHref(w), 'https://example.invalid');
      expect(url.origin).toBe('https://example.invalid');
      expect(url.pathname.startsWith('/guides/')).toBe(true);
      expect(fragmentId(url.hash)?.endsWith('-' + w.map.chapters[0].id)).toBe(true);
      expect(w.guide.includes('#')).toBe(false);
    }
  });
});


describe('map links wait for the reader to request a destination', () => {
  for (const file of ['ExecutionMap.astro', 'WorkflowMap.astro']) {
    it(`${file} disables speculative fetching on every authored link`, () => {
      const component = readFileSync(`src/components/${file}`, 'utf8');
      const anchors = component.match(/<a(?=[\s>])[^>]*>/g) ?? [];
      expect(anchors.length).toBeGreaterThan(0);
      expect(anchors.filter(anchor => !anchor.includes('data-astro-prefetch="false"'))).toEqual([]);
    });
  }
});
