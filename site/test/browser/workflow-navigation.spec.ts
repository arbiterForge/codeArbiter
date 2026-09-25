import { test, expect, type Request } from '@playwright/test';
import { isNativeIconRead } from '../chapter-request-contract';
import { workflows } from '../../scripts/execution-maps/workflows';
import { workflowMapHref } from '../../scripts/execution-maps/locations';

for (const w of workflows) test(`${w.id}: the directory opens the exact map, not a closed or sibling route`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/concepts/workflow-routes/');
  const link = page.locator(`[data-workflow-link="${w.id}"] [data-workflow-map-link]`);
  await expect(link).toHaveAttribute('href', workflowMapHref(w));
  await link.focus(); await link.press('Enter');
  await expect(page).toHaveURL(new RegExp(workflowMapHref(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
  const map = page.locator(`[data-workflow="${w.id}"]`);
  const first = map.locator(`[data-map-chapter="${w.map.chapters[0].id}"]`);
  await expect(first).toBeVisible();
  await expect(map.locator(`[data-map-select="${w.map.chapters[0].id}"]`)).toHaveAttribute('aria-pressed', 'true');
  if (w.id === 'greenfield' || w.id === 'brownfield') {
    const other = w.id === 'greenfield' ? 'brownfield' : 'greenfield';
    await expect(page.locator(`[data-workflow="${other}"]`)).toBeHidden();
  }
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('chapter links advance, restore Back, reload and same-fragment selection without a saved bookmark', async ({ page }) => {
  const w = workflows[0];
  await page.goto(workflowMapHref(w));
  const map = page.locator('[data-workflow="sprint"]');
  const state = () => page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  const before = await state();
  const first = map.locator('[data-map-chapter="review-pair"]');
  await expect(first).toBeVisible();
  const next = first.locator('[data-map-next]');
  await next.focus(); await expect(next).toBeFocused();
  await next.press('Enter');
  const second = map.locator('[data-map-chapter="execute-tasks"]');
  await expect(second).toBeVisible(); await expect(first).toBeHidden();
  await expect(second).toBeFocused();
  await expect(page).toHaveURL(/#sprint-execution-map-execute-tasks$/);
  // In-document links must not persist anything. A full reload is a separate
  // lifecycle: Starlight stores its sidebar state on visibilitychange. Snapshot
  // again afterward rather than attributing that shell write to a chapter link.
  expect(await state()).toEqual(before);
  await page.reload(); await expect(second).toBeVisible();
  const afterReload = await state();
  await map.locator('[data-map-select="all"]').click();
  await second.locator('[data-map-permalink]').click(); // Same hash still restores this view.
  await expect(map.locator('[data-map-chapter]:visible')).toHaveCount(1);
  await page.goBack(); await expect(first).toBeVisible();
  await expect(second).toBeHidden();
  await expect(page).toHaveURL(/#sprint-execution-map-review-pair$/);
  await page.goForward(); await expect(second).toBeVisible();
  await expect(first).toBeHidden();
  await expect(page).toHaveURL(/#sprint-execution-map-execute-tasks$/);
  expect(await state()).toEqual(afterReload);
});


for (const w of workflows) test(`${w.id}: chapter navigation preserves storage and makes no application requests`, async ({ page }) => {
  await page.goto(workflowMapHref(w));
  const map = page.locator(`[data-workflow="${w.id}"]`);
  await expect(map.locator('.ca-execution-map__controls')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const state = () => page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  const before = await state();
  // Observe, but do not block or replace, the real storage behavior. No key is
  // allowlisted. The fresh page owns these temporary test instrumentation hooks.
  await page.evaluate(() => {
    const writes: string[][] = [];
    Object.defineProperty(window, '__mapStorageWrites', { value: writes });
    for (const name of ['setItem', 'removeItem', 'clear'] as const) {
      const original = Storage.prototype[name];
      Object.defineProperty(Storage.prototype, name, {
        configurable: true, writable: true,
        value: function(this: Storage, ...args: string[]) {
          writes.push([this === localStorage ? 'local' : 'session', name, ...args]);
          return Reflect.apply(original, this, args);
        },
      });
    }
  });
  // Native hash navigation can revalidate the document's favicon. Keep that
  // exact browser read visible, but reject fetch/XHR, prefetch and all other URLs.
  const iconUrl = await page.locator('link[rel="icon"]').evaluate(node => (node as HTMLLinkElement).href);
  expect(iconUrl).toBe(new URL('/favicon.svg', page.url()).href);
  for (const link of await map.locator('a').all()) {
    await expect(link).toHaveAttribute('data-astro-prefetch', 'false');
  }
  const requests: Request[] = [];
  const sockets: string[] = [];
  page.on('request', request => requests.push(request));
  page.on('websocket', socket => sockets.push(socket.url()));
  for (const [index, chapter] of w.map.chapters.entries()) {
    const section = map.locator(`[data-map-chapter="${chapter.id}"]`);
    await expect(section).toBeVisible();
    await section.locator('[data-map-permalink]').focus();
    await section.locator('[data-map-permalink]').press('Enter');
    await expect(section).toBeFocused();
    if (index + 1 < w.map.chapters.length) {
      await section.locator('[data-map-next]').focus();
      await section.locator('[data-map-next]').press('Enter');
      await expect(map.locator(`[data-map-chapter="${w.map.chapters[index + 1].id}"]`)).toBeFocused();
    }
  }
  const last = map.locator(`[data-map-chapter="${w.map.chapters.at(-1)!.id}"]`);
  await map.locator('[data-map-select="all"]').click();
  await last.locator('[data-map-permalink]').click();
  await expect(last).toBeFocused();
  await expect(map.locator('[data-map-chapter]:visible')).toHaveCount(1);
  expect(await state()).toEqual(before);
  expect(await page.evaluate(() => (window as unknown as { __mapStorageWrites: string[][] }).__mapStorageWrites)).toEqual([]);
  const network = await Promise.all(requests.map(async request => ({
    url: request.url(), method: request.method(), resourceType: request.resourceType(),
    body: request.postData(), headers: await request.allHeaders(),
  })));
  expect(network.filter(request => !isNativeIconRead(request, iconUrl))).toEqual([]);
  expect(sockets).toEqual([]);
  // Retain the observed exception rather than hiding it from the evidence.
  await test.info().attach(`${w.id}-chapter-network`, {
    body: JSON.stringify({ nativeIconReads: network, applicationRequests: [], storageWrites: [] }, null, 2),
    contentType: 'application/json',
  });
});

test('all chapter permalinks, previous/next links and final outcomes agree with the source map', async ({ page }) => {
  for (const w of workflows) {
    await page.goto(workflowMapHref(w));
    const map = page.locator(`[data-workflow="${w.id}"]`);
    const id = await map.locator('ca-execution-map').getAttribute('id');
    for (const [index, chapter] of w.map.chapters.entries()) {
      const section = map.locator(`[data-map-chapter="${chapter.id}"]`);
      await map.locator(`[data-map-select="${chapter.id}"]`).click();
      await expect(section.locator('[data-map-permalink]')).toHaveAttribute('href', `#${id}-${chapter.id}`);
      await expect(section.locator('[data-map-previous]')).toHaveCount(index > 0 ? 1 : 0);
      if (index > 0) await expect(section.locator('[data-map-previous]')).toHaveAttribute('href', `#${id}-${w.map.chapters[index - 1].id}`);
      if (index + 1 < w.map.chapters.length) await expect(section.locator('[data-map-next]')).toHaveAttribute('href', `#${id}-${w.map.chapters[index + 1].id}`);
      else {
        await expect(section.locator('[data-map-next]')).toHaveCount(0);
        await expect(section.locator('[data-map-end]')).toHaveAttribute('href', '/concepts/workflow-routes/');
        await expect(map).toContainText(w.map.outcome);
      }
    }
  }
});

test('unknown and malformed fragments do not execute selectors or open unrelated disclosures', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  for (const hash of ['#%E0%A4%A', '#unrelated', '#%23%5Bdata-map-chapter%5D']) {
    await page.goto(`/guides/opt-in-a-repo/${hash}`);
    await expect(page.locator('#initialization-routes')).not.toHaveAttribute('open');
    await expect(page.locator('[data-workflow="greenfield"]')).toBeHidden();
  }
  expect(errors).toEqual([]);
});

test('native chapter links and all content survive without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage();
    for (const w of [workflows[0], workflows[4], workflows[5]]) {
      await page.goto(`http://127.0.0.1:4322${workflowMapHref(w)}`);
      const chapter = page.locator(`[data-workflow="${w.id}"] [data-map-chapter]`).first();
      await expect(chapter).toBeVisible();
      await expect(page.locator(`[data-workflow="${w.id}"] [data-map-step]:visible`)).toHaveCount(w.map.chapters.flatMap(c => c.nodes).length);
      await expect(page.locator(`[data-workflow="${w.id}"] [data-map-select]:visible`)).toHaveCount(0);
    }
  } finally { await context.close(); }
});
