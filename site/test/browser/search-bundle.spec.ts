import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

/** Check the actual emitted and served module, not a mocked search provider. */
test('the served search entry matches complete build bytes and exposes the real query API', async ({ page }) => {
  await page.goto('/concepts/workflow-routes/');
  const modulePath = '/pagefind/pagefind.js';
  const expected = readFileSync(join(process.cwd(), 'dist', modulePath));
  const response = await page.request.get(modulePath);
  expect(response.status()).toBe(200);
  const served = await response.body();
  expect(served.equals(expected)).toBe(true);
  const result = await page.evaluate(async path => {
    const provider = await import(path);
    const query = await provider.search('Protect Your First Repository');
    return { exports: Object.keys(provider).sort(), paths: await Promise.all(query.results.map(async (entry: { data(): Promise<{url: string}> }) => (await entry.data()).url)) };
  }, modulePath);
  expect(result.exports).toEqual(expect.arrayContaining(['search', 'options', 'init']));
  expect(result.paths).toContain('/getting-started/quickstart/');
  const directory = join(process.cwd(), '.astro', 'browser-evidence');
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, 'search-bundle-integrity.json'), JSON.stringify({
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(),
    path: modulePath, bytes: served.length, sha256: createHash('sha256').update(served).digest('hex'),
    servedBytesMatchBuild: true, ...result,
  }, null, 2));
});
