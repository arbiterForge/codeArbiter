/// <reference lib="dom" />
/** landing-scene.spec.ts - the landing's machine trace, machine section and host picker, in a real browser. */
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const scene = '[data-scene="hero-trace"]';
const step = (page: import('@playwright/test').Page) => page.locator(scene).getAttribute('data-step');

test('the hero trace plays on its own with a working pause control', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  const toggle = root.locator('[data-scene-toggle]');
  await expect(toggle).toHaveText(/Pause/);
  await expect.poll(async () => Number(await step(page)), { timeout: 9000 }).toBeGreaterThan(0);
  await toggle.click();
  await expect(toggle).toHaveText(/Play/);
  const held = await step(page);
  await page.waitForTimeout(3500);
  expect(await step(page)).toBe(held);
});

test('keyboard steps the scene and hands control to the reader', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await root.locator('[data-scene-go="3"]').focus();
  await page.keyboard.press('Enter');
  await expect(root).toHaveAttribute('data-step', '3');
  await expect(root.locator('[data-scene-toggle]')).toHaveText(/Play/);
  await expect(root.locator('.ca-scene__step[aria-current="step"]')).toContainText('BLOCKED [H-03]');
  await expect(root.locator('.ca-scene__svg--wide [data-el="guard"]')).toHaveAttribute('data-verdict', 'block');
  await page.keyboard.press('ArrowRight');
  await expect(root).toHaveAttribute('data-step', '4');
  await expect(root.locator('[data-scene-go="4"]')).toBeFocused();
  await page.keyboard.press('Home');
  await expect(root).toHaveAttribute('data-step', '0');
  await page.waitForTimeout(3200);
  await expect(root).toHaveAttribute('data-step', '0');
});

test('reduced motion keeps the complete, still scene', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).not.toHaveAttribute('data-js', /.*/);
  await expect(root.locator('[data-scene-controls]')).toBeHidden();
  const steps = root.locator('.ca-scene__step');
  await expect(steps).toHaveCount(7);
  for (const item of await steps.all()) await expect(item).toBeVisible();
  await expect(root.locator('[data-state]')).toHaveCount(0);
});

test('without JavaScript the scene reads as the full ordered steps', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root.locator('.ca-scene__step')).toHaveCount(7);
  await expect(root.locator('.ca-scene__step').nth(3)).toContainText("BLOCKED [H-03]: 'git add -A'");
  await expect(root.locator('[data-scene-controls]')).toBeHidden();
  await expect(root.locator('.ca-scene__svg--wide')).toBeVisible();
  await context.close();
});

test('phones get the tall composition without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root.locator('.ca-scene__svg--wide')).toBeHidden();
  await expect(root.locator('.ca-scene__svg--tall')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
  await root.locator('[data-scene-go="3"]').click();
  await expect(root.locator('.ca-scene__step[aria-current="step"] .ca-scene__terminal')).toBeVisible();
});

test('the host picker spells a command in every host and names an omission', async ({ page }) => {
  await page.goto('/');
  const hosts = page.locator('[data-host-switch]');
  await hosts.getByRole('button', { name: 'statusline', exact: true }).click();
  await expect(hosts.locator('[data-host="claude"] code')).toHaveText('/ca:statusline');
  await expect(hosts.locator('[data-host="claude"] code')).not.toHaveAttribute('data-omitted', /.*/);
  await expect(hosts.locator('[data-host="codex"] code')).toHaveAttribute('data-omitted', '');
  await expect(hosts.locator('[data-host="codex"]')).toContainText('Not available on Codex');
  await hosts.getByRole('button', { name: 'pr', exact: true }).click();
  await expect(hosts.locator('[data-host="codex"] code')).toHaveText('$ca-pr');
  await expect(hosts.locator('[data-host="pi"] code')).toHaveText('/ca-pr');
  await expect(hosts.locator('[data-host="codex"] .ca-host__omitted')).toBeHidden();
});

test('the machine section opens the 3D machine page', async ({ page }) => {
  await page.goto('/');
  const poster = page.locator('.ca-machine-teaser__poster');
  await expect(poster.locator('img')).toHaveAttribute('alt', /3D machine/);
  await poster.click();
  await expect(page).toHaveURL(/\/concepts\/machine\/$/);
});

test('the landing passes automated accessibility checks', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.locator(scene)).toHaveAttribute('data-js', 'on');
  const result = await new AxeBuilder({ page }).include('.ca-landing').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`)).toEqual([]);
});
