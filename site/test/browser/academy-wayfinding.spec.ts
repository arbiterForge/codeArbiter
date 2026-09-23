import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const key = 'codearbiter:academy-bookmark:v1:%2F';
const first = '/academy/f01-fork-clone-doctor/';
const practitioner = '/academy/p01-feature-through-plan/';

test('a bookmark is opt-in, survives navigation, and never becomes completion', async ({ page }) => {
  await page.goto(practitioner);
  const bookmark = page.locator('ca-academy-bookmark');
  await expect(bookmark.locator('[data-bookmark-save]')).toBeVisible();
  expect(await page.evaluate(k => localStorage.getItem(k), key)).toBeNull();
  await bookmark.getByRole('button', { name: 'Save this lesson in this browser' }).click();
  await expect(bookmark.getByRole('status')).toContainText('does not mark the lesson complete');
  const saved = await page.evaluate(k => JSON.parse(localStorage.getItem(k)!), key);
  expect(Object.keys(saved).sort()).toEqual(['commit', 'lessonId', 'release', 'schemaVersion']);
  expect(saved.lessonId).toBe('P01-feature-through-plan');
  await page.locator('a[rel="next"]').click();
  await expect(page).toHaveURL(/p02-commit-review-pr/);
  expect(await page.evaluate(k => JSON.parse(localStorage.getItem(k)!).lessonId, key)).toBe(saved.lessonId);
  await page.getByRole('navigation', { name: 'Academy lesson context' }).getByRole('link', { name: 'All lessons' }).click();
  await expect(bookmark.locator('[data-bookmark-resume]')).toHaveAttribute('href', practitioner);
  await bookmark.locator('[data-bookmark-resume]').click();
  await expect(page).toHaveURL(new RegExp(practitioner));
  await page.goBack();
  await expect(bookmark.locator('[data-bookmark-resume]')).toBeVisible();
  await bookmark.getByRole('button', { name: 'Remove saved place' }).click();
  expect(await page.evaluate(k => localStorage.getItem(k), key)).toBeNull();
  await expect(bookmark.getByRole('status')).toBeFocused();
  await expect(bookmark.locator('[data-bookmark-resume]')).toBeHidden();
});

test('stale source identity has no resume URL and clearing retains command preferences', async ({ page }) => {
  await page.goto(first);
  await page.locator('[data-bookmark-save]').click();
  await page.evaluate(k => {
    const saved = JSON.parse(localStorage.getItem(k)!);
    saved.commit = '0'.repeat(40);
    localStorage.setItem(k, JSON.stringify(saved));
    localStorage.setItem('academy-os', 'linux');
  }, key);
  await page.goto('/academy/');
  const bookmark = page.locator('ca-academy-bookmark');
  await expect(bookmark.getByRole('status')).toContainText('different curriculum snapshot');
  await expect(bookmark.locator('[data-bookmark-resume]')).not.toHaveAttribute('href');
  await bookmark.locator('[data-bookmark-clear]').click();
  expect(await page.evaluate(() => localStorage.getItem('academy-os'))).toBe('linux');
});

test('denied storage retains the full lesson and an actionable explanation', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw new Error('denied for test'); } }));
  await page.goto(first);
  const bookmark = page.locator('ca-academy-bookmark');
  await expect(bookmark.getByRole('status')).toContainText('storage is unavailable');
  await bookmark.locator('[data-bookmark-save]').click();
  await expect(bookmark.getByRole('status')).toContainText('could not be saved');
  await expect(page.getByRole('navigation', { name: 'Academy lesson context' }).getByRole('link', { name: 'View Foundation track' })).toBeVisible();
  await expect(page.locator('.academy-action').first()).toBeVisible();
});

test('track insertion cannot replace cross-track lesson pagination', async ({ page }) => {
  await page.goto('/academy/f04-fix-with-evidence/');
  await page.locator('a[rel="next"]').click();
  await expect(page).toHaveURL(new RegExp(practitioner));
  const place = page.getByRole('complementary', { name: 'Your place in the curriculum' });
  await expect(place).toContainText('Lesson 5 of 19');
  await expect(place).toContainText('Lesson 1 of 8');
  await expect(place.getByRole('link', { name: /F04/ })).toHaveAttribute('href', '/academy/f04-fix-with-evidence/');
  await page.locator('a[rel="prev"]').click();
  await expect(page).toHaveURL(/f04-fix-with-evidence/);
  await page.goto('/academy/u07-capstone/');
  await expect(page.locator('a[rel="next"]')).toHaveCount(0);
});

test('Academy View all lessons reconnects after client navigation', async ({ page }) => {
  await page.goto('/academy/');
  await page.locator('[data-academy-show-all]').click();
  await expect(page.locator('.academy-overview__more[open]')).toHaveCount(3);
  await page.locator('.academy-overview__start-link').click();
  await page.getByRole('navigation', { name: 'Academy lesson context' }).getByRole('link', { name: 'All lessons' }).click();
  await page.locator('[data-academy-show-all]').click();
  await expect(page.locator('.academy-overview__more[open]')).toHaveCount(3);
  await expect(page.locator('[data-academy-show-all]')).toHaveAttribute('aria-expanded', 'true');
});

test('track pages and lesson wayfinding are usable without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto('/academy/tracks/practitioner/');
    await expect(page.locator('[data-academy-track-lesson]')).toHaveCount(8);
    await expect(page.locator('[data-bookmark-controls]')).toBeHidden();
    await page.locator('[data-academy-track-lesson="P01-feature-through-plan"] h2 a').click();
    await expect(page).toHaveURL(new RegExp(practitioner));
    await expect(page.getByRole('navigation', { name: 'Academy lesson context' })).toBeVisible();
    await expect(page.locator('h1')).toHaveCount(1);
  } finally { await context.close(); }
});

for (const width of [320, 390, 1440]) {
  test(`Academy wayfinding reflows at ${width}px and remains accessible`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const route of ['/academy/', '/academy/tracks/practitioner/', practitioner]) {
      await page.goto(route);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      await expect(page.locator('h1')).toHaveCount(1);
      const result = await new AxeBuilder({ page }).include('ca-academy-bookmark').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    }
  });
}

test('saving and removing a place work by keyboard in forced colors', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto(first);
  const save = page.locator('[data-bookmark-save]');
  await save.focus();
  expect(await save.evaluate(node => getComputedStyle(node).outlineStyle)).not.toBe('none');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-bookmark-status]')).toContainText('Reading place saved');
  await page.keyboard.press('Tab');
  await expect(page.locator('[data-bookmark-clear]')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(save).toBeFocused();
});

test('capture Academy track and return surfaces for human review', async ({ page }) => {
  const root = join(process.cwd(), '.astro/browser-evidence');
  mkdirSync(root, { recursive: true });
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(practitioner);
    await page.locator('[data-bookmark-save]').click();
    await page.goto('/academy/tracks/practitioner/');
    await page.screenshot({ path: join(root, `academy-track-${width}.png`), fullPage: true });
    await page.goto('/academy/#academy-return');
    await page.locator('#academy-return').screenshot({ path: join(root, `academy-return-${width}.png`) });
  }
  writeFileSync(join(root, 'academy-wayfinding-context.json'), JSON.stringify({ head: process.env.GITHUB_SHA ?? null, browser: page.context().browser()?.version(), widths: [390, 1440], note: 'Reading bookmark and generated curriculum views. Not verifier progress or an installed-host recording.' }, null, 2));
});
