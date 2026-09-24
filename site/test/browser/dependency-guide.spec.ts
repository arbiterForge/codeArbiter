import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const route = '/guides/adding-a-dependency/';

/** Inspect rendered table text, not just the page's scroll width. */
async function inspectDecision(page: Page) {
  return page.locator('main .ca-table-shell').evaluateAll(shells => shells.map(shell => {
    const box = shell.getBoundingClientRect();
    const cells = Array.from(shell.querySelectorAll<HTMLElement>('th, td'));
    return {
      overflow: shell.scrollWidth > shell.clientWidth + 1,
      documentBox: { x: box.x + scrollX, y: box.y + scrollY, width: box.width, height: box.height },
      values: cells.map(cell => {
        const value = cell.querySelector<HTMLElement>('.ca-table-cell-value') ?? cell;
        const range = document.createRange(); range.selectNodeContents(value);
        const cellBox = cell.getBoundingClientRect();
        const rects = Array.from(range.getClientRects()).filter(rect => rect.width && rect.height);
        // The accessible column-header row is intentionally visually clipped in stacked mode.
        const hiddenHeader = Boolean(cell.closest('thead')) && getComputedStyle(cell.closest('thead')!).clipPath !== 'none';
        return { text: value.textContent, clipped: !hiddenHeader && rects.some(rect =>
          rect.left < Math.max(0, cellBox.left) - 1 || rect.right > Math.min(innerWidth, cellBox.right) + 1 ||
          rect.top < cellBox.top - 1 || rect.bottom > cellBox.bottom + 1) };
      }),
    };
  }));
}

for (const width of [320, 390, 1440]) {
  test(`dependency decision, commands and text remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await page.goto(route);
    const main = page.locator('main');
    await expect(main.getByRole('heading', { name: 'One-time inspection: nothing adopted', exact: true })).toBeVisible();
    for (const syntax of ['/ca:add-dep', '$ca-add-dep', '/ca-add-dep']) await expect(main).toContainText(syntax);
    await expect(main).toContainText('No package was downloaded or executed');
    const measurements = await inspectDecision(page);
    expect(measurements).toHaveLength(1);
    expect(measurements.flatMap(table => table.values).filter(cell => cell.clipped)).toEqual([]);
    expect(measurements.some(table => table.overflow)).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}

test('dependency decision and exact confirmation survive no-script reading and print', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 900 } });
  const page = await context.newPage();
  try {
    await page.goto(`http://127.0.0.1:4322${route}`);
    await expect(page.locator('[data-reader-journey="dependency-decision-map"] li')).toHaveCount(4);
    await expect(page.locator('main')).toContainText('You requested that specific tool by name in the current session');
    await expect(page.locator('main')).toContainText('confirmation naming the exact command before execution');
    const screen = await inspectDecision(page);
    expect(screen).toHaveLength(1);
    expect(screen.flatMap(table => table.values).filter(cell => cell.clipped)).toEqual([]);
    const before = screen.flatMap(table => table.values.map(cell => cell.text));
    await page.emulateMedia({ media: 'print' });
    const printed = await inspectDecision(page);
    expect(printed.flatMap(table => table.values.map(cell => cell.text))).toEqual(before);
    expect(printed.flatMap(table => table.values).filter(cell => cell.clipped)).toEqual([]);
    await expect(page.locator('main')).toContainText('already-dirty file can change again');
  } finally { await context.close(); }
});

for (const forcedColors of ['none', 'active'] as const) {
  test(`dependency map and decision table pass scoped accessibility in ${forcedColors} forced colors`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.emulateMedia({ forcedColors }); await page.goto(route);
    const results = await new AxeBuilder({ page }).include('[data-reader-journey="dependency-decision-map"]').include('main .ca-table-shell').analyze();
    expect(results.violations).toEqual([]);
    const link = page.getByRole('link', { name: 'Inspect the command contract', exact: true });
    await link.focus(); await page.keyboard.press('Enter'); await expect(page).toHaveURL(/\/reference\/commands\/add-dep\/$/);
    await page.goBack(); await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(page.locator('[data-reader-journey="dependency-decision-map"]')).toBeVisible();
  });
}

test('every shared reader map retains contrast and readable labels in forced colors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.emulateMedia({ forcedColors: 'active' });
  for (const slug of ['opt-in-a-repo', 'feature-lane', 'autonomous-sprints', 'review-and-ship', 'investigate-and-fix', 'adding-a-dependency']) {
    await page.goto(`/guides/${slug}/`);
    const map = page.locator('[data-reader-journey]');
    await expect(map.locator('ol > li')).toHaveCount(4);
    await expect(map.getByText('What you get', { exact: true })).toHaveCount(4);
    await expect(map.getByText('Before moving on', { exact: true })).toHaveCount(4);
    const result = await new AxeBuilder({ page }).include('[data-reader-journey]').analyze();
    expect(result.violations, slug).toEqual([]);
  }
});

test('capture the dependency guide with exact source identity and table geometry', async ({ page }) => {
  const directory = join(process.cwd(), '.astro', 'browser-evidence'); mkdirSync(directory, { recursive: true });
  const evidence: Record<string, unknown> = {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(),
    scope: 'Built documentation only; no third-party inspection tool was executed.',
  };
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 }); await page.goto(route); await page.evaluate(() => document.fonts.ready);
    evidence[String(width)] = await inspectDecision(page);
    await page.screenshot({ path: join(directory, `dependency-guide-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 900 }); await page.emulateMedia({ forcedColors: 'active' });
  await page.goto(route); await page.screenshot({ path: join(directory, 'dependency-guide-forced-colors-390.png'), fullPage: true });
  writeFileSync(join(directory, 'dependency-guide-evidence.json'), JSON.stringify(evidence, null, 2));
});
