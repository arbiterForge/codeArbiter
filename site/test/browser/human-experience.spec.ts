/// <reference lib="dom" />
import { expect, test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const routes = ['/product-tour/', '/guides/plan-a-new-project/', '/guides/review-artifacts/', '/guides/first-feature/', '/guides/resume-and-recover/'];

test('the primary destinations and learning order remain explicit', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Primary', exact: true }).getByRole('link')).toHaveText(['Get started', 'Guides', 'Concepts', 'Academy', 'Reference', 'Trust']);
  await page.getByRole('navigation', { name: 'Primary', exact: true }).getByRole('link', { name: 'Guides', exact: true }).click();
  await expect(page).toHaveURL(/\/guides\/$/);
  await expect(page.locator('h1')).toHaveCount(1);
});

test('criterion selection works with keyboard, remains draft, and reconnects after navigation', async ({ page }) => {
  await page.goto('/product-tour/');
  let workbench = page.locator('[data-example="artifacts"]');
  await workbench.getByRole('button', { name: /AC-002/ }).focus();
  await page.keyboard.press('Enter');
  await expect(workbench.locator('[data-pane]:visible')).toContainText('Round-trip');
  await expect(workbench.locator('[data-pane]:visible')).toContainText('TestExport.test_round_trip');
  await expect(workbench.getByRole('button', { name: /AC-002/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(workbench).toContainText('Unapproved fixture');
  await page.getByRole('link', { name: 'complete feature walkthrough', exact: true }).click();
  await expect(page).toHaveURL(/\/guides\/first-feature\/$/);
  await expect(page.locator('h1')).toHaveCount(1);
  await page.goBack();
  await expect(page).toHaveURL(/\/product-tour\/$/);
  workbench = page.locator('[data-example="artifacts"]');
  await workbench.getByRole('button', { name: /AC-003/ }).click();
  await expect(workbench.locator('[data-pane]:visible')).toContainText('TestExport.test_empty');
  await page.keyboard.press('Home');
  await expect(workbench.getByRole('button', { name: /AC-001/ })).toBeFocused();
  await expect(workbench.locator('[data-pane]:visible')).toContainText('TestExport.test_rows');
  await page.keyboard.press('ArrowRight');
  await expect(workbench.getByRole('button', { name: /AC-002/ })).toBeFocused();
  await expect(workbench.locator('[data-pane]:visible')).toContainText('TestExport.test_round_trip');
});

test('all demonstrations have a complete no-script reading path', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage(); await page.goto('/product-tour/');
    await expect(page.locator('[data-example="artifacts"] [data-pane]:visible')).toHaveCount(3);
    await expect(page.locator('[data-example="delivery"] [data-pane]:visible')).toHaveCount(5);
    await expect(page.locator('[data-example="themes"] [data-pane]:visible')).toHaveCount(5);
    await expect(page.locator('.ca-example-controls:visible')).toHaveCount(0);
    await expect(page.locator('h1')).toHaveCount(1);
  } finally { await context.close(); }
});

for (const width of [320, 390, 1440]) {
  test(`new journeys fit ${width}px with reduced motion`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const route of routes) {
      await page.goto(route);
      const dimensions = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
      expect(dimensions.page, route).toBeLessThanOrEqual(dimensions.viewport + 1);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('main')).not.toBeEmpty();
    }
  });
}

test('new interactive regions meet automated accessibility checks', async ({ page }) => {
  await page.goto('/product-tour/');
  for (const example of ['artifacts', 'delivery', 'hosts', 'themes']) {
    const region = page.locator(`[data-example="${example}"]`);
    for (const button of await region.locator('.ca-example-controls button').all()) {
      await button.click();
      const result = await new AxeBuilder({ page }).include(`[data-example="${example}"]`).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations, `${example}: ${await button.textContent()}`).toEqual([]);
    }
  }
});

test('forced colors retain selection and focus affordances', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/product-tour/');
  const button = page.locator('[data-example="artifacts"]').getByRole('button', { name: /AC-002/ });
  await button.click(); await button.focus();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  expect(await button.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe('none');
});

test('native documents require no script or off-origin request', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    const requests: string[] = []; page.on('request', (request) => requests.push(request.url()));
    await page.goto('/examples/saved-searches/specs/saved-searches.html');
    await expect(page.locator('h1')).toContainText('Export saved searches');
    await expect(page.locator('#AC-002')).toBeVisible();
    expect(requests.filter((url) => !url.startsWith('http://127.0.0.1:4322/'))).toEqual([]);
    await expect(page.locator('script:not([type="application/json"])')).toHaveCount(0);
    await expect(page.locator('script[type="application/json"]')).toHaveCount(1);
  } finally { await context.close(); }
});

// Captures are review evidence, not pixel-baseline approval. The workflow retains
// successful-run captures so a reviewer can inspect the actual hosted render.
test('capture representative product-window layouts for review', async ({ page }) => {
  const root = join(process.cwd(), '.astro/browser-evidence');
  mkdirSync(root, { recursive: true });
  const captures = [];
  for (const [name, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await page.screenshot({ path: join(root, `home-${name}.png`) });
    // A full-page capture avoids a fixed header obscuring a tall element during
    // Playwright's automatic scroll-to-center for element screenshots.
    await page.screenshot({ path: join(root, `home-full-${name}.png`), fullPage: true });
    await page.goto('/product-tour/');
    await page.screenshot({ path: join(root, `tour-${name}.png`), fullPage: true });
    captures.push({ name, width, height });
  }
  writeFileSync(join(root, 'capture-context.json'), JSON.stringify({ browser: page.context().browser()?.version(), viewports: captures, scope: 'Built-site browser capture, not installed-host or real-user certification.' }, null, 2));
});
