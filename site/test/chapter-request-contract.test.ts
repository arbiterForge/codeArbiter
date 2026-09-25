import { describe, expect, it } from 'vitest';
import { isNativeIconRead, type ChapterRequest } from './chapter-request-contract';

const icon = 'http://127.0.0.1:4322/favicon.svg';
const observed: ChapterRequest = {
  url: icon, method: 'GET', resourceType: 'other', body: null,
  headers: { 'sec-fetch-dest': 'image', 'sec-fetch-mode': 'no-cors', 'sec-fetch-site': 'same-origin' },
};

describe('chapter network observation boundary', () => {
  it('recognizes only the observed browser read of the exact published favicon', () => {
    expect(isNativeIconRead(observed, icon)).toBe(true);
  });
  it.each([
    { url: `${icon}?chapter=private` }, { url: `${icon}#selection` },
    { url: 'https://example.invalid/favicon.svg' },
    { url: 'http://127.0.0.1:4322/reference/skills/decompose/' },
    { method: 'POST' }, { body: 'selection=private' },
    { resourceType: 'fetch' }, { resourceType: 'xhr' },
    { resourceType: 'document' }, { headers: {} },
    { headers: { ...observed.headers, 'sec-fetch-dest': 'empty' } },
    { headers: { ...observed.headers, 'sec-fetch-mode': 'cors' } },
    { headers: { ...observed.headers, 'sec-fetch-site': 'cross-site' } },
  ])('rejects application traffic or a changed icon request: %j', change => {
    expect(isNativeIconRead({ ...observed, ...change }, icon)).toBe(false);
  });
});
