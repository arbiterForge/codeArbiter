import { expect, test, type Page } from '@playwright/test';
import type { Atlas } from '../../scripts/execution-maps/atlas-model';

const route = '/concepts/workflow-routes/';
const root = (page: Page) => page.locator('ca-workflow-atlas');
const settle = (page: Page) => page.evaluate(() => new Promise<void>(resolve => {
  requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
}));
const repeatNotifications = (page: Page) => page.evaluate(() => {
  window.dispatchEvent(new PopStateEvent('popstate', { state: history.state }));
  window.dispatchEvent(new HashChangeEvent('hashchange'));
  document.dispatchEvent(new Event('astro:page-load'));
});

test('duplicate native notifications retain stage, node and reading focus', async ({ page }) => {
  await page.goto(route + '#atlas-view-context-layers~feature');
  const atlas = root(page);
  await expect(atlas).toHaveAttribute('data-route', 'feature');
  const permalink = atlas.locator('[data-atlas-permalink]');
  await expect(permalink).toHaveAttribute('data-astro-reload', '');
  // Only same-document atlas links opt out. Procedure navigation still uses Astro.
  await expect(atlas.locator('[data-atlas-inspector] a[href="/reference/commands/feature/"]'))
    .not.toHaveAttribute('data-astro-reload');
  expect(await atlas.locator('a[href^="#atlas-"]:not([data-astro-reload])').count()).toBe(0);

  const historyLength = await page.evaluate(() => history.length);
  await permalink.focus();
  await page.keyboard.press('Enter');
  await expect(atlas.locator('[data-atlas-stage]')).toBeFocused();
  expect(await page.evaluate(() => history.length)).toBe(historyLength);

  const node = atlas.locator('[data-atlas-stage] [data-node="c-green"]');
  await node.focus();
  await page.keyboard.press('Enter');
  await permalink.focus();
  await page.keyboard.press('Enter');
  await expect(node).toBeFocused();
  await node.evaluate(element => element.setAttribute('data-test-retained', 'yes'));
  await repeatNotifications(page);
  await settle(page);
  await expect(node).toBeFocused();
  await expect(node).toHaveAttribute('data-test-retained', 'yes');
  await expect(atlas).toHaveAttribute('data-route', 'feature');

  await atlas.locator('[data-action="reading"]').click();
  const reading = atlas.locator('#atlas-reading');
  await expect(reading).toBeFocused();
  await repeatNotifications(page);
  await settle(page);
  await expect(reading).toBeFocused();

  // An unrelated fragment is not a new atlas selection, but returning from it is.
  await permalink.click();
  await expect(node).toBeFocused();
  await page.evaluate(() => {
    history.pushState(history.state, '', '#unrelated-page-heading');
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
  await atlas.locator('[data-atlas-select]').selectOption('fix');
  await page.goBack();
  await expect(atlas).toHaveAttribute('data-route', 'feature');
  await expect(atlas).toHaveAttribute('data-selected-node', 'c-green');
});

test('later cancellation and newer manual choices win over pending fragment clicks', async ({ page }) => {
  await page.goto(route + '#atlas-fix');
  const offline = await root(page).locator('.atlas-downloads a').first().getAttribute('href');
  expect(offline).toMatch(/\/workflow-atlas\/[0-9a-f]{40}\/atlas.html$/);
  for (const destination of [route, offline!]) {
    await page.goto(destination + '#atlas-fix');
    const atlas = root(page);
    await expect(atlas).toHaveAttribute('data-route', 'fix');
    const before = page.url();
    await atlas.evaluate(element => {
      const link = element.querySelector<HTMLAnchorElement>('[data-atlas-permalink]')!;
      link.hash = 'atlas-tribunal';
      // Cancellation occurs after the component's listener, not on the link.
      document.addEventListener('click', event => event.preventDefault(), { once: true });
      link.click();
    });
    await settle(page);
    expect(page.url()).toBe(before);
    await expect(atlas).toHaveAttribute('data-route', 'fix');
    await expect(atlas).toHaveAttribute('data-active-view', 'change-lanes');

    await atlas.evaluate(element => {
      const link = element.querySelector<HTMLAnchorElement>('[data-atlas-permalink]')!;
      link.hash = 'atlas-tribunal';
      link.click();
      const select = element.querySelector<HTMLSelectElement>('[data-atlas-select]')!;
      select.value = 'review';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      element.querySelector<HTMLButtonElement>('[data-action="read-size"]')!.click();
      element.querySelector<HTMLButtonElement>('[data-action="plus"]')!.click();
    });
    await expect(page).toHaveURL(url => url.hash === '#atlas-tribunal');
    await settle(page);
    await repeatNotifications(page);
    await settle(page);
    await expect(atlas).toHaveAttribute('data-route', 'review');
    await expect(atlas).toHaveAttribute('data-active-view', 'change-lanes');
    expect(Number(await atlas.getAttribute('data-zoom'))).toBeCloseTo(0.85 * 1.22, 5);
  }
});

test('Read size requires route membership and a complete command token', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const title of ['/prune /preview /pr-extra', '/pr']) {
    await page.goto(route + '#atlas-view-all-routes');
    const atlas = root(page);
    await expect(atlas).toHaveAttribute('data-active-view', 'all-routes');
    // Controlled metadata collision. Production coordinates and SVG templates
    // remain untouched; an early decoy must not replace the real o-pr target.
    const expected = await atlas.evaluate((element, decoyTitle) => {
      const parent = element.parentElement!;
      const data = element.querySelector('[data-atlas-data]')!;
      const model = JSON.parse(data.textContent!) as Atlas;
      const view = model.views.find(candidate => candidate.id === 'all-routes')!;
      const target = view.nodes.find(node => node.id === 'o-pr')!;
      const decoy = view.nodes.find(node => node.kind === 'cmd')!;
      element.remove();
      decoy.title = decoyTitle;
      decoy.routes = decoyTitle === '/pr' ? ['prune'] : ['pr'];
      data.textContent = JSON.stringify(model);
      parent.append(element);
      return { x: target.x * 0.85 - 25, y: target.y * 0.85 - 65 };
    }, title);
    await atlas.locator('[data-atlas-select]').selectOption('pr');
    await settle(page);
    const actual = await atlas.locator('[data-atlas-stage]').evaluate(element => ({
      x: element.scrollLeft, y: element.scrollTop,
    }));
    expect(Math.abs(actual.x - Math.max(0, expected.x))).toBeLessThanOrEqual(1);
    expect(Math.abs(actual.y - Math.max(0, expected.y))).toBeLessThanOrEqual(1);
    await expect(atlas).toHaveAttribute('data-route', 'pr');
  }
});
