import { expect, test } from '@playwright/test';

const route = '/concepts/workflow-routes/';

test('entry selection, explicit permalinks, history and page lifecycle', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(route + '#atlas-fix');
  const atlas = page.locator('ca-workflow-atlas');
  const select = atlas.locator('[data-atlas-select]');
  await expect(atlas.locator('#atlas-fix')).toBeVisible();
  await expect(select).toHaveValue('fix');
  const initial = page.url();
  await select.selectOption('tribunal');
  expect(page.url()).toBe(initial);
  await atlas.locator('[data-atlas-permalink]').click();
  await expect(page).toHaveURL(/#atlas-tribunal$/);
  await page.reload();
  await expect(select).toHaveValue('tribunal');
  await page.goBack();
  await expect(select).toHaveValue('fix');
  await page.goForward();
  await expect(select).toHaveValue('tribunal');
  await page.goBack();
  await expect(select).toHaveValue('fix');

  // The actual Astro same-page router need not emit hashchange for this link.
  await atlas.locator('a[href="#atlas-view-context-layers"]').first().click();
  await expect(page).toHaveURL(/#atlas-view-context-layers$/);
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open', '');
  await expect(atlas.locator('#atlas-view-context-layers > summary')).toBeFocused();
  await expect(atlas.locator('#atlas-fix')).toBeHidden();
  await page.goBack();
  await expect(select).toHaveValue('fix');

  // A real client-navigation round trip, not two independent page.goto calls.
  await atlas.evaluate(element => { element.setAttribute('data-test-original', 'true'); });
  await page.evaluate(() => { Object.assign(window, { atlasTestDocument: 'retained' }); });
  await atlas.locator('#atlas-fix a[href="/reference/commands/fix/"]').click();
  await expect(page).toHaveURL(/\/reference\/commands\/fix\/$/);
  await page.locator(`a[href="${route}#atlas-fix"]`).first().click();
  await expect(select).toHaveValue('fix');
  await expect(atlas).not.toHaveAttribute('data-test-original');
  expect(await page.evaluate(() => Reflect.get(window, 'atlasTestDocument'))).toBe('retained');
  await atlas.locator('a[href="#atlas-tribunal"]').first().click();
  await expect(select).toHaveValue('tribunal');
  expect(errors).toEqual([]);
});

test('same-fragment and node links reveal their literal target without extra history', async ({ page }) => {
  await page.goto(route + '#atlas-view-context-layers');
  const atlas = page.locator('ca-workflow-atlas');
  const select = atlas.locator('[data-atlas-select]');
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open', '');
  await select.selectOption('prune');
  await expect(atlas.locator('#atlas-view-context-layers')).toBeHidden();
  const before = await page.evaluate(() => history.length);
  const link = atlas.locator('a[href="#atlas-view-context-layers"]').first();
  await link.focus();
  await page.keyboard.press('Enter');
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open', '');
  await expect(atlas.locator('#atlas-view-context-layers')).toBeVisible();
  await expect(atlas.locator('#atlas-view-context-layers > summary')).toBeFocused();
  expect(await page.evaluate(() => history.length)).toBe(before);

  const nodeLink = atlas.locator('#atlas-view-context-layers .ca-atlas-handoffs a[href^="#atlas-node-"]').first();
  const hash = await nodeLink.getAttribute('href');
  expect(hash).toMatch(/^#atlas-node-context-layers-[a-z0-9-]+$/);
  await nodeLink.click();
  await expect(page).toHaveURL(new RegExp(`${hash}$`));
  await expect(atlas.locator(hash!)).toBeVisible();
  await expect(atlas.locator(hash!)).toBeFocused();
  await page.reload();
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open', '');
  await expect(atlas.locator(hash!)).toBeVisible();
});

test('unrelated addresses and modified or canceled clicks do not select an atlas route', async ({ page }) => {
  await page.goto(route + '#atlas-fix');
  const atlas = page.locator('ca-workflow-atlas');
  const select = atlas.locator('[data-atlas-select]');
  await expect(select).toHaveValue('fix');
  const hashes = ['#unrelated-chapter', '#%E0%A4%A', '#%22%5D%5Bhidden%5D', '#' + 'x'.repeat(1025)];
  for (const hash of hashes) {
    await page.evaluate(value => { history.replaceState(history.state, '', value); window.dispatchEvent(new HashChangeEvent('hashchange')); }, hash);
    await expect(select).toHaveValue('fix');
  }
  const before = page.url();
  // Suppress native navigation in this guard probe; do not create real tabs.
  await atlas.evaluate(async element => {
    const link = element.querySelector<HTMLAnchorElement>('a[href="#atlas-tribunal"]')!;
    const stopDefault = (event: Event) => event.preventDefault();
    document.addEventListener('click', stopDefault);
    try {
      for (const init of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
        link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, ...init }));
        await Promise.resolve();
      }
      link.addEventListener('click', stopDefault, { once: true });
      link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      await Promise.resolve();
      for (const [name, value] of [['target', '_blank'], ['download', 'atlas']]) {
        link.setAttribute(name, value);
        link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        await Promise.resolve();
        link.removeAttribute(name);
      }
    } finally { document.removeEventListener('click', stopDefault); }
  });
  await expect(select).toHaveValue('fix');
  expect(page.url()).toBe(before);
});

test('every catalog entry, host exclusions and every map remain reachable', async ({ page }) => {
  await page.goto(route);
  const atlas = page.locator('ca-workflow-atlas');
  const ids = await atlas.locator('[data-atlas-select] option').evaluateAll(options => options.map(o => (o as HTMLOptionElement).value).filter(Boolean));
  expect(ids.length).toBe(37);
  for (const id of ids) {
    await atlas.locator('[data-atlas-select]').selectOption(id);
    await expect(atlas.locator(`#atlas-${id}`)).toBeVisible();
  }
  await atlas.locator('[data-atlas-select]').selectOption('prune');
  await atlas.locator('[data-atlas-host-select]').selectOption('codex');
  await expect(atlas.locator('#atlas-prune [data-atlas-host="codex"]')).toContainText('Not exposed');
  await atlas.locator('[data-atlas-show-all]').click();
  const views = await atlas.locator('[data-atlas-view]').evaluateAll(nodes => nodes.map(n => n.id));
  for (const id of views) {
    await page.goto(route + '#' + id);
    await expect(page.locator('#' + id)).toHaveAttribute('open', '');
  }
});

test('narrow reading, keyboard targets, reduced motion and print', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(route + '#atlas-view-tribunal');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  const atlas = page.locator('ca-workflow-atlas');
  await atlas.locator('[data-atlas-select]').focus();
  await expect(atlas.locator('[data-atlas-select]')).toBeFocused();
  const status = atlas.locator('[data-atlas-status]');
  await expect(status).toHaveCount(1);
  await expect(status).toHaveAttribute('role', 'status');
  await expect(status).toBeVisible();
  await expect(atlas.locator('#atlas-status')).toHaveAttribute('data-atlas-entry', 'status');
  await page.evaluate(() => { window.dispatchEvent(new Event('beforeprint')); window.dispatchEvent(new Event('beforeprint')); });
  await page.emulateMedia({ media: 'print' });
  await expect(atlas.locator('#atlas-view-debug-fix .ca-atlas-handoffs')).toBeVisible();
  await expect(atlas.locator('#atlas-status .ca-atlas-entry-body')).toBeVisible();
  await expect(status).toBeHidden();
  await expect(atlas.locator('[data-atlas-controls]')).toBeHidden();
  await page.emulateMedia({ media: 'screen', forcedColors: 'active' });
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await expect(atlas.locator('#atlas-view-tribunal')).toBeVisible();
  await expect(atlas.locator('#atlas-view-debug-fix')).toBeHidden();
  await expect(atlas.locator('#atlas-status')).toBeHidden();
  await expect(status).toBeVisible();
});

test('JavaScript-disabled reading and exact generated downloads', async ({ browser, request, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  try {
    await page.goto(new URL(route, baseURL).href);
    const atlas = page.locator('ca-workflow-atlas');
    await atlas.locator('#atlas-fix > summary').click();
    await expect(atlas.locator('#atlas-fix .ca-atlas-entry-body')).toBeVisible();
    await atlas.locator('#atlas-view-tribunal > summary').click();
    await expect(atlas.locator('#atlas-view-tribunal .ca-atlas-handoffs')).toBeVisible();
    const download = await atlas.locator('footer a').first().getAttribute('href');
    expect(download).toMatch(/\/workflow-atlas\/[0-9a-f]{40}\/atlas.html$/);
    const response = await request.get(download!);
    expect(response.ok()).toBeTruthy();
    expect(await response.text()).toContain('report-written');
    const svg = await request.get(download!.replace('atlas.html', 'context-layers.svg'));
    expect(svg.ok()).toBeTruthy();
    expect(await svg.text()).toContain('<svg');
  } finally { await context.close(); }
});

test('the generated offline edition has the same native navigation and print restoration', async ({ page }) => {
  await page.goto(route);
  const download = await page.locator('ca-workflow-atlas footer a').first().getAttribute('href');
  await page.goto(download! + '#atlas-fix');
  const atlas = page.locator('ca-workflow-atlas');
  await expect(atlas.locator('[data-atlas-select]')).toHaveValue('fix');
  await atlas.locator('a[href="#atlas-view-context-layers"]').first().click();
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open', '');
  await page.goBack();
  await expect(atlas.locator('[data-atlas-select]')).toHaveValue('fix');
  await page.evaluate(() => { window.dispatchEvent(new Event('beforeprint')); window.dispatchEvent(new Event('beforeprint')); window.dispatchEvent(new Event('afterprint')); });
  await expect(atlas.locator('#atlas-fix')).toBeVisible();
  await expect(atlas.locator('#atlas-tribunal')).toBeHidden();
});
