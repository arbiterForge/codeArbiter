/// <reference lib="dom" />
/** explorers.spec.ts - the reference explorers: Hook Gates, the command matrix and the changelog. */
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const axe = (page: Page, selector: string) => new AxeBuilder({ page }).include(selector).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test.describe('Hook Gates explorer', () => {
  test('decodes the captured refusal to its gate and the line that printed it', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const explorer = page.locator('ca-gate-explorer');
    await explorer.locator('button[data-example]').first().click();
    const result = explorer.locator('[data-gate-result]');
    await expect(result).toContainText('Exact match');
    await expect(result.locator('.ca-gates__match-tag')).toHaveText('H-03');
    await expect(result.locator('a[href*="/plugins/ca/hooks/_bashguardlib.py#L"]')).toBeVisible();
    await expect(explorer.locator('.ca-gate[data-gate="H-03"]')).toHaveAttribute('data-match', '');
    await result.locator('a.ca-button').click();
    await expect(page).toHaveURL(/#h-03$/);
  });

  test('a gate ID this version does not print is named as unknown', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    await page.locator('#gate-decode-input').fill('BLOCKED [H-42]: something');
    await expect(page.locator('[data-gate-result]')).toContainText('H-42 is not a gate ID');
  });

  test('filters the gates by what they do and where they fire', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const explorer = page.locator('ca-gate-explorer');
    await explorer.getByRole('radio', { name: /^Reminds/ }).check();
    await expect(explorer.locator('[data-gate-count]')).toHaveText('8 of 22 gates');
    for (const tile of await explorer.locator('.ca-gates__board .ca-gate:visible').all()) await expect(tile).toHaveAttribute('data-kind', 'remind');
    await explorer.getByRole('radio', { name: 'Git backstop' }).check();
    await expect(explorer.locator('[data-gate-empty]')).toBeVisible();
    await explorer.getByRole('radio', { name: /^Blocks/ }).check();
    await expect(explorer.locator('[data-gate-count]')).toHaveText('5 of 22 gates');
  });

  test('every gate link lands on its entry', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const targets = await page.locator('ca-gate-explorer a[href^="#"]').evaluateAll((links) => [...new Set(links.map((link) => link.getAttribute('href')!.slice(1)))]);
    expect(targets.length).toBeGreaterThanOrEqual(22);
    const missing = await page.evaluate((ids) => ids.filter((id) => !document.getElementById(id)), targets);
    expect(missing).toEqual([]);
  });

  test('without JavaScript the map and the gate list stay, and the tools that need a script do not show', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto('/reference/hooks-gates/');
    await expect(page.locator('[data-gate-decoder]')).toBeHidden();
    await expect(page.locator('[data-gate-filters]')).toBeHidden();
    await expect(page.locator('.ca-gates__board .ca-gate')).toHaveCount(22);
    await expect(page.locator('.ca-gates__lane')).toHaveCount(4);
    await context.close();
  });

  test('passes automated accessibility checks and fits a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/reference/hooks-gates/');
    await page.locator('ca-gate-explorer button[data-example]').first().click();
    expect((await axe(page, 'ca-gate-explorer')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
});

test.describe('Command matrix', () => {
  test('spells every command for every host and filters by host, level and word', async ({ page }) => {
    await page.goto('/reference/commands/');
    const matrix = page.locator('ca-command-matrix');
    await expect(matrix.locator('[data-matrix-row]')).toHaveCount(33);
    const feature = matrix.locator('[data-matrix-row]').filter({ has: page.locator('a', { hasText: /^feature$/ }) });
    await expect(feature.locator('td[data-host="codex"] code')).toHaveText('$ca-feature');
    await expect(feature.locator('td[data-host="pi"] code')).toHaveText('/ca-feature');
    await matrix.getByRole('radio', { name: /^Codex CLI/ }).check();
    const codexCount = await matrix.locator('[data-matrix-row]:visible').count();
    expect(codexCount).toBeLessThan(33);
    for (const row of await matrix.locator('[data-matrix-row]:visible').all()) await expect(row.locator('td[data-host="codex"] code')).toBeVisible();
    await matrix.getByRole('radio', { name: 'Every host' }).check();
    await page.locator('#matrix-find').fill('adr');
    await expect(matrix.locator('[data-matrix-count]')).toHaveText(/^\d+ of 33 commands$/);
    for (const row of await matrix.locator('[data-matrix-row]:visible').all()) expect((await row.textContent())!.toLowerCase()).toContain('adr');
  });

  test('copies a spelling and says so', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/reference/commands/');
    const button = page.locator('ca-command-matrix [data-copy="$ca-feature"]');
    await button.click();
    await expect(page.locator('[data-matrix-copied]')).toHaveText('Copied $ca-feature');
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('$ca-feature');
  });

  test('an alias names the command that replaces it', async ({ page }) => {
    await page.goto('/reference/commands/');
    const cleanup = page.locator('[data-matrix-row]').filter({ has: page.locator('a', { hasText: /^cleanup$/ }) });
    await expect(cleanup).toContainText('Now runs pr --cleanup');
  });

  test('passes automated accessibility checks and becomes cards on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/reference/commands/');
    expect((await axe(page, 'ca-command-matrix')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await expect(page.locator('ca-command-matrix thead')).toHaveCSS('position', 'absolute');
  });
});

test.describe('Changelog navigator', () => {
  test('finds a gate across the whole history and lights its releases in the timeline', async ({ page }) => {
    await page.goto('/changelog/');
    const nav = page.locator('ca-changelog-navigator');
    await page.locator('#history-find').fill('H-22');
    await expect(nav.locator('[data-history-count]')).toHaveText(/^\d+ of \d+ entries, in \d+ releases?$/);
    const lit = await nav.locator('[data-history-bar]:not([data-dim])').count();
    expect(lit).toBeGreaterThan(0);
    expect(lit).toBeLessThan(20);
    for (const item of await page.locator('.sl-markdown-content li:visible').all()) expect(await item.textContent()).toContain('H-22');
    await page.locator('#history-find').fill('');
    await expect(nav.locator('[data-history-bar][data-dim]')).toHaveCount(0);
  });

  test('filters by kind and jumps to a release', async ({ page }) => {
    await page.goto('/changelog/');
    const nav = page.locator('ca-changelog-navigator');
    await nav.getByRole('radio', { name: 'Security' }).check();
    await expect(nav.locator('[data-history-count]')).toHaveText(/^\d+ of \d+ entries/);
    await nav.getByRole('radio', { name: 'All' }).check();
    await page.locator('#history-jump').selectOption({ index: 3 });
    await expect(page).toHaveURL(/#\d+---\d{4}-\d{2}-\d{2}$/);
  });

  test('without JavaScript the timeline is links to releases and the filters do not show', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto('/changelog/');
    await expect(page.locator('[data-history-filters]')).toBeHidden();
    const bars = page.locator('[data-history-bar]');
    expect(await bars.count()).toBeGreaterThan(150);
    const missing = await bars.evaluateAll((links) => links.map((link) => link.getAttribute('href')!.slice(1)).filter((id) => !document.getElementById(id)));
    expect(missing).toEqual([]);
    await context.close();
  });

  test('passes automated accessibility checks and fits a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/changelog/');
    expect((await axe(page, 'ca-changelog-navigator')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
});
