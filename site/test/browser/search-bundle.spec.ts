import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

test('a failed search module load retries the built UI with the retained query', async ({ page }) => {
  const attempts: string[] = [];
  await page.route('**/pagefind/pagefind.js*', route => {
    attempts.push(new URL(route.request().url()).search);
    if (attempts.length === 1) return route.fulfill({ status: 503, body: '' });
    return route.fulfill({ contentType: 'text/javascript', body: `
      export async function options() {}
      export async function search(query) {
        return { results: [{ async data() { return { url: '/overview/', meta: { title: query }, excerpt: '' }; } }] };
      }
    ` });
  });
  await page.goto('/concepts/workflow-routes/');
  const input = page.getByRole('combobox', { name: 'Search the docs', exact: true });
  await input.fill('retained module query');
  await expect(page.locator('.ca-search__status')).toContainText('temporarily unavailable');
  await expect(input).toHaveValue('retained module query');
  const results = page.getByRole('listbox', { name: 'Search results', exact: true });
  await expect(results.getByRole('option')).toHaveCount(0);
  const retry = page.getByRole('button', { name: 'Retry search', exact: true });
  await expect(retry).toBeEnabled();
  await retry.click();
  await expect(results.getByRole('option')).toContainText('retained module query');
  await expect(retry).toBeHidden();
  expect(attempts).toEqual(['', '?retry=1']);
});

for (const failure of ['query', 'data'] as const) {
  test(`current ${failure} failure retains the query and retries the built search UI`, async ({ page }) => {
    await page.route('**/pagefind/pagefind.js*', route => route.fulfill({ contentType: 'text/javascript', body: `
      let attempts = 0;
      export async function options() {}
      export async function search(query) {
        const fail = ++attempts === 1;
        if (fail && ${JSON.stringify(failure)} === 'query') throw new Error('controlled query rejection');
        return { results: [{ async data() {
          if (fail) throw new Error('controlled result rejection');
          return { url: '/overview/', meta: { title: query }, excerpt: 'Recovered result' };
        }}] };
      }
    ` }));
    await page.goto('/concepts/workflow-routes/');
    const input = page.getByRole('combobox', { name: 'Search the docs' });
    await input.fill('retained query');
    await expect(page.locator('.ca-search__status')).toContainText('temporarily unavailable');
    await expect(input).toHaveValue('retained query');
    await page.getByRole('button', { name: 'Retry search', exact: true }).click();
    await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toContainText('retained query');
    await expect(page.getByRole('button', { name: 'Retry search', exact: true })).toBeHidden();
    await input.press('ArrowDown');
    await expect(input).toHaveAttribute('aria-activedescendant', 'ca-search-opt-0');
  });
}

test('failed result expansion keeps existing results and can retry', async ({ page }) => {
  await page.route('**/pagefind/pagefind.js*', route => route.fulfill({ contentType: 'text/javascript', body: `
    let failed = false;
    export async function options() {}
    export async function search() { return { results: Array.from({ length: 10 }, (_, i) => ({ async data() {
      if (i === 8 && !failed) { failed = true; throw new Error('controlled expansion rejection'); }
      return { url: '/overview/', meta: { title: 'Result ' + i }, excerpt: '' };
    }})) }; }
  ` }));
  await page.goto('/concepts/workflow-routes/');
  await page.getByRole('combobox', { name: 'Search the docs', exact: true }).fill('expand');
  await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toHaveCount(8);
  await page.getByRole('button', { name: 'Show all 10 results' }).click();
  await expect(page.locator('.ca-search__status')).toContainText('Could not load more results');
  await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toHaveCount(8);
  const retry = page.getByRole('button', { name: 'Retry loading more results' });
  await expect(retry).toBeEnabled();
  await retry.click();
  await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toHaveCount(10);
});

for (const outcome of ['rejected', 'successful'] as const) {
  test(`an older ${outcome} query cannot replace newer successful results`, async ({ page }) => {
    await page.route('**/pagefind/pagefind.js*', route => route.fulfill({ contentType: 'text/javascript', body: `
      export async function options() {}
      export async function search(query) {
        if (query === 'old') {
          await new Promise(resolve => { window.settleOldSearch = resolve; });
          if (${JSON.stringify(outcome)} === 'rejected') throw new Error('old failure');
        }
        return { results: [{ async data() { return { url: '/overview/', meta: { title: query }, excerpt: '' }; }}] };
      }
    ` }));
    await page.goto('/concepts/workflow-routes/');
    const input = page.getByRole('combobox', { name: 'Search the docs', exact: true });
    await input.fill('old');
    type DeferredSearchWindow = Window & { settleOldSearch?: () => void };
    await expect.poll(() => page.evaluate(() => typeof (window as DeferredSearchWindow).settleOldSearch)).toBe('function');
    await input.fill('new');
    await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toContainText('new');
    await page.evaluate(async () => {
      (window as DeferredSearchWindow).settleOldSearch?.();
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    });
    await expect(page.getByRole('listbox', { name: 'Search results', exact: true }).getByRole('option')).toContainText('new');
    await expect(page.getByRole('button', { name: 'Retry search', exact: true })).toBeHidden();
  });
}

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
