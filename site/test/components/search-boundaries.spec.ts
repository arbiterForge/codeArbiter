/// <reference lib="dom" />
/** Actual Search script/markup in Chrome; controlled Pagefind, not production-page proof. */
import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync('src/components/Search.astro', 'utf8');
const markup = source.slice(source.indexOf('<ca-site-search'), source.indexOf('<script>'))
  .replace('class={Astro.props.class} data-base={base}', 'data-base=""');
const script = ts.transpileModule(source.match(/<script>([\s\S]*?)<\/script>/)![1], {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;

async function mount(page: Page, failFirstModule = false) {
  const requests: string[] = [];
  await page.route('http://component.test/**', async route => {
    if (route.request().url().includes('/pagefind/')) {
      requests.push(route.request().url());
      if (failFirstModule && requests.length === 1) return route.fulfill({ status: 503, body: 'Unavailable' });
      return route.fulfill({ contentType: 'text/javascript', body: `
        export async function options() {}
        export async function search(query) {
          if (query === 'held') {
            window.queryStarted = true;
            await new Promise(resolve => { window.releaseQuery = resolve; });
          }
          return { results: [{ async data() { return {url:'/result',meta:{title:query},excerpt:''}; } }] };
        }` });
    }
    return route.fulfill({ contentType: 'text/html', body:
      `<!doctype html><button id="outside">Outside</button>${markup}<script type="module">${script}</script>` });
  });
  await page.goto('http://component.test/');
  await page.waitForFunction(() => !!customElements.get('ca-site-search'));
  return requests;
}

async function beginPendingQuery(page: Page) {
  const input = page.getByRole('combobox');
  await input.fill('ready');
  await expect(page.getByRole('option')).toHaveText('ready');
  await input.press('ArrowDown');
  await expect(input).toHaveAttribute('aria-activedescendant', 'ca-search-opt-0');
  await input.fill('held');
  await page.waitForFunction(() => (window as any).queryStarted === true);
  return input;
}

async function releasePendingQuery(page: Page) {
  await page.evaluate(async () => {
    (window as any).releaseQuery();
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  });
}

test('module failure retains query and retries a cache-busted import', async ({ page }) => {
  const requests = await mount(page, true);
  const input = page.getByRole('combobox');
  await input.fill('retained');
  await expect(page.getByText('Search is temporarily unavailable.')).toBeVisible();
  await expect(input).toHaveValue('retained');
  await expect(page.getByRole('option')).toHaveCount(0);
  expect(requests).toEqual(['http://component.test/pagefind/pagefind.js']);
  await page.getByRole('button', { name: 'Retry search', exact: true }).click();
  await expect(page.getByRole('option')).toHaveText('retained');
  await expect(page.getByRole('button', { name: 'Retry search', exact: true })).toBeHidden();
  expect(requests).toEqual(['http://component.test/pagefind/pagefind.js', 'http://component.test/pagefind/pagefind.js?retry=1']);
  await input.press('ArrowDown');
  await expect(input).toHaveAttribute('aria-activedescendant', 'ca-search-opt-0');
});

for (const action of ['clear', 'Escape', 'outside']) test(`pending query cannot reopen search after ${action}`, async ({ page }) => {
  await mount(page);
  const input = await beginPendingQuery(page);
  if (action === 'clear') await input.fill('');
  else if (action === 'Escape') await input.press('Escape');
  else await page.getByRole('button', { name: 'Outside', exact: true }).click();
  await expect(page.locator('.ca-search__panel')).toBeHidden();
  await expect(input).toHaveAttribute('aria-expanded', 'false');
  await expect(input).toHaveAttribute('aria-activedescendant', '');
  await expect(input).toHaveValue(action === 'outside' ? 'held' : '');
  await releasePendingQuery(page);
  await expect(page.locator('.ca-search__panel')).toBeHidden();
  await expect(input).toHaveAttribute('aria-expanded', 'false');
  await expect(input).toHaveAttribute('aria-activedescendant', '');
  await expect(page.locator('[role="option"]')).toHaveText('ready');
  await input.fill('fresh');
  await expect(page.getByRole('option')).toHaveText('fresh');
});

test('disconnect cancels pending render and releases shortcut until reconnect', async ({ page }) => {
  await mount(page);
  await beginPendingQuery(page);
  await page.evaluate(() => {
    const element = document.querySelector('ca-site-search')!;
    (window as any).savedSearch = element;
    element.remove();
  });
  const detached = () => page.evaluate(() => {
    const element = (window as any).savedSearch as HTMLElement;
    return { connected: element.isConnected, hidden: (element.querySelector('.ca-search__panel') as HTMLElement).hidden,
      expanded: element.querySelector('input')!.getAttribute('aria-expanded'),
      active: element.querySelector('input')!.getAttribute('aria-activedescendant'),
      title: element.querySelector('[role="option"]')!.textContent };
  });
  expect(await detached()).toEqual({ connected: false, hidden: true, expanded: 'false', active: '', title: 'ready' });
  expect(await page.evaluate(() => {
    const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, cancelable: true });
    window.dispatchEvent(event); return event.defaultPrevented;
  })).toBe(false);
  await releasePendingQuery(page);
  expect(await detached()).toEqual({ connected: false, hidden: true, expanded: 'false', active: '', title: 'ready' });
  await page.evaluate(() => document.body.append((window as any).savedSearch));
  expect(await page.evaluate(() => {
    const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, cancelable: true });
    window.dispatchEvent(event); return event.defaultPrevented;
  })).toBe(true);
  await expect(page.getByRole('combobox')).toBeFocused();
  await page.getByRole('combobox').fill('fresh');
  await expect(page.getByRole('option')).toHaveText('fresh');
});
