import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { guideGroups } from '../../scripts/guide-directory';

const expectedIds = guideGroups.flatMap(group => group.slugs.map(slug => `guides/${slug}`));
const entries = (page: Page) => page.locator('[data-guide-entry]:visible');

/** Check real visible row boxes, not a hard-coded CSS height. */
async function checkCards(page: Page) {
  const measurements = await page.locator('.ca-guide-directory__grid:visible').evaluateAll(grids => grids.map(grid => {
    const columns = getComputedStyle(grid).gridTemplateColumns.split(' ').length;
    return { columns, cards: Array.from(grid.children).filter(child => child.checkVisibility()).map(child => {
      const box = child.getBoundingClientRect(); const css = getComputedStyle(child);
      return { x: box.x, y: box.y, width: box.width, height: box.height,
        marginStart: css.marginBlockStart, marginEnd: css.marginBlockEnd };
    }) };
  }));
  expect(measurements.length).toBeGreaterThan(0);
  for (const group of measurements) {
    for (const card of group.cards) { expect(card.marginStart).toBe('0px'); expect(card.marginEnd).toBe('0px'); }
    if (group.columns < 2) continue;
    for (let i = 0; i < group.cards.length; i += group.columns) {
      for (const card of group.cards.slice(i, i + group.columns)) {
        expect(Math.abs(card.y - group.cards[i].y)).toBeLessThanOrEqual(1);
        expect(Math.abs(card.width - group.cards[i].width)).toBeLessThanOrEqual(1);
        expect(Math.abs(card.height - group.cards[i].height)).toBeLessThanOrEqual(1);
      }
    }
  }
  return measurements;
}

test('directory contains every guide and filters by both task and literal words', async ({ page }) => {
  await page.goto('/guides/');
  await expect(page.getByRole('search', { name: 'Find a guide' })).toBeVisible();
  await expect(page.locator('.ca-page-context')).toHaveCount(0);
  expect(await entries(page).evaluateAll(nodes => nodes.map(node => node.getAttribute('data-guide-entry')))).toEqual(expectedIds);
  await page.getByLabel('Task group', { exact: true }).selectOption('review-and-ship');
  await expect(entries(page)).toHaveCount(4);
  await page.getByLabel('What do you need to do?', { exact: true }).fill('inbound checkpoint');
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toHaveAttribute('data-guide-entry', 'guides/review-and-ship');
  await page.getByLabel('What do you need to do?', { exact: true }).fill('no such thing <script>');
  await expect(entries(page)).toHaveCount(0);
  await expect(page.locator('[data-guide-empty]')).toBeVisible();
  await expect(page.locator('[data-guide-count]')).toHaveText(`0 of ${expectedIds.length} guides`);
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(entries(page)).toHaveCount(expectedIds.length);
  await expect(page.getByLabel('What do you need to do?', { exact: true })).toBeFocused();
});

test('filtering makes no request or storage write and does not submit a query URL', async ({ page }) => {
  await page.goto('/guides/');
  const query = page.getByLabel('What do you need to do?', { exact: true });
  await expect(query).toBeVisible();
  const requests: string[] = [];
  const before = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  page.on('request', request => requests.push(request.url()));
  await query.fill('inbound checkpoint');
  await query.press('Enter');
  await expect(entries(page)).toHaveCount(1);
  await expect(page).toHaveURL(/\/guides\/$/);
  const after = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(after).toEqual(before);
  expect(requests).toEqual([]);
});

test('filter controls and the review guide reconnect after client navigation and back', async ({ page }) => {
  await page.goto('/guides/');
  await page.getByLabel('What do you need to do?', { exact: true }).fill('inbound checkpoint');
  const link = entries(page).getByRole('link', { name: 'Review and Ship a Change', exact: true });
  await link.focus(); await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/guides\/review-and-ship\/$/);
  await expect(page.locator('[data-reader-journey="review-delivery-map"] ol > li')).toHaveCount(4);
  await page.goBack();
  await expect(page).toHaveURL(/\/guides\/$/);
  await expect(page.getByLabel('Task group', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await page.getByLabel('Task group', { exact: true }).selectOption('initialize-and-understand');
  await expect(entries(page)).toHaveCount(3);
});

test('ordinary guide discovery and the new workflow remain complete without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:4322/guides/');
  await expect(entries(page)).toHaveCount(expectedIds.length);
  await expect(page.getByRole('search', { name: 'Find a guide' })).toHaveCount(0);
  await entries(page).getByRole('link', { name: 'Review and Ship a Change', exact: true }).click();
  await expect(page.locator('[data-reader-journey] ol > li')).toHaveCount(4);
  await expect(page.getByRole('heading', { name: 'When the path stops', exact: true })).toBeVisible();
  await context.close();
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`guide cards stay aligned before and after filtering at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/guides/'); await page.evaluate(() => document.fonts.ready);
    await checkCards(page);
    await page.getByLabel('Task group', { exact: true }).selectOption('review-and-ship');
    await expect(entries(page)).toHaveCount(4); await checkCards(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.goto('/guides/review-and-ship/');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  });
}

test('keyboard filtering, hidden targets, print and forced colors retain a usable reading path', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/guides/');
  const query = page.getByLabel('What do you need to do?', { exact: true });
  await query.focus(); await query.fill('inbound checkpoint');
  await page.keyboard.press('Tab'); await expect(page.getByLabel('Task group', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(page.getByRole('button', { name: 'Clear filters', exact: true })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(entries(page).getByRole('link')).toBeFocused();
  const result = await new AxeBuilder({ page }).include('ca-guide-directory').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  await page.emulateMedia({ media: 'print' });
  await expect(entries(page)).toHaveCount(expectedIds.length);
  await expect(page.getByRole('search', { name: 'Find a guide' })).toBeHidden();
});

test('record actual guide discovery and review-to-delivery layouts', async ({ page }) => {
  const directory = join(process.cwd(), '.astro', 'browser-evidence'); mkdirSync(directory, { recursive: true });
  const evidence: Record<string, unknown> = {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(),
  };
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/guides/'); await page.evaluate(() => document.fonts.ready);
    evidence[`all-${width}`] = await checkCards(page);
    await page.screenshot({ path: join(directory, `guide-directory-${width}.png`), fullPage: true });
    await page.getByLabel('Task group', { exact: true }).selectOption('review-and-ship');
    evidence[`filtered-${width}`] = await checkCards(page);
    await page.screenshot({ path: join(directory, `guide-directory-filtered-${width}.png`), fullPage: true });
    await page.goto('/guides/review-and-ship/'); await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(directory, `review-and-ship-${width}.png`), fullPage: true });
    await page.locator('[data-reader-journey]').screenshot({ path: join(directory, `review-delivery-map-${width}.png`) });
  }
  writeFileSync(join(directory, 'guide-discovery-geometry.json'), JSON.stringify(evidence, null, 2));
});
