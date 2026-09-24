import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { guideGroups } from '../../scripts/guide-directory';

const targets = ['review-and-ship', 'investigate-and-fix'];
const tables = (page: Page) => page.locator('table[data-ca-table="stacked"]');
const values = (page: Page) => page.locator('.ca-table-cell-value').allTextContents();

/** Compare the layout with its content-box query, not the outer viewport width. */
async function assertPresentation(page: Page) {
  const layouts = await page.locator('.ca-table-shell--stackable').evaluateAll(shells => shells.map(shell => {
    const style = getComputedStyle(shell);
    const width = shell.getBoundingClientRect().width - parseFloat(style.borderLeftWidth) -
      parseFloat(style.borderRightWidth) - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const stacked = width <= 40 * parseFloat(getComputedStyle(document.documentElement).fontSize);
    return { stacked, display: getComputedStyle(shell.querySelector('table')!).display,
      labels: Array.from(shell.querySelectorAll<HTMLElement>('.ca-table-cell-label'))
        .map(label => label.checkVisibility()) };
  }));
  expect(layouts.length).toBeGreaterThan(0);
  for (const layout of layouts) {
    expect(layout.display).toBe(layout.stacked ? 'block' : 'table');
    expect(layout.labels.length).toBeGreaterThan(0);
    expect(layout.labels.every(visible => visible === layout.stacked)).toBe(true);
  }
  return layouts;
}

/** Enlarge actual text through DevTools without waiting on disabled page-script events. */
async function enlargeText(page: Page) {
  const value = page.locator('.ca-table-cell-value').first();
  const before = await value.evaluate(node => parseFloat(getComputedStyle(node).fontSize));
  await page.evaluate(() => {
    const root = document.documentElement;
    root.style.fontSize = `${2 * parseFloat(getComputedStyle(root).fontSize)}px`;
  });
  const after = await value.evaluate(node => parseFloat(getComputedStyle(node).fontSize));
  expect(after).toBeCloseTo(before * 2, 1);
}

/** Page width alone misses text cut off inside a nested scroll container. */
async function inspectCells(page: Page) {
  return page.locator('.ca-table-shell--stackable').evaluateAll(shells => shells.map(shell => {
    const cellValues = Array.from(shell.querySelectorAll<HTMLElement>('.ca-table-cell-value'));
    const clips: string[] = [];
    for (const cell of cellValues) {
      const box = cell.getBoundingClientRect();
      const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        if (!node.textContent?.trim()) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        for (const rect of Array.from(range.getClientRects())) {
          if (rect.width && (rect.left < box.left - 1 || rect.right > box.right + 1 ||
              rect.top < box.top - 1 || rect.bottom > box.bottom + 1 ||
              rect.left < -1 || rect.right > window.innerWidth + 1)) {
            clips.push(node.textContent!.slice(0, 100));
          }
        }
      }
    }
    return { clientWidth: shell.clientWidth, scrollWidth: shell.scrollWidth,
      cellCount: cellValues.length, clips, values: cellValues.map(cell => cell.textContent),
      columnCount: shell.querySelectorAll('thead th').length,
      rowCount: shell.querySelectorAll('tbody tr').length };
  }));
}

async function assertReadable(page: Page, examples = true) {
  const result = await inspectCells(page);
  expect(result.length).toBeGreaterThan(0);
  for (const table of result) {
    expect(table.cellCount).toBe(table.columnCount * table.rowCount);
    expect(table.scrollWidth).toBeLessThanOrEqual(table.clientWidth + 1);
    expect(table.clips).toEqual([]);
  }
  if (examples) for (const block of await page.locator('.expressive-code pre').evaluateAll(nodes => nodes.map(node => ({ client: node.clientWidth, scroll: node.scrollWidth })))) {
    expect(block.scroll).toBeLessThanOrEqual(block.client + 1);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 1);
  return result;
}

for (const slug of targets) {
  for (const width of [320, 390, 768]) {
    test(`${slug}: every table cell remains readable at ${width}px with all content retained`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(`/guides/${slug}/`); await page.evaluate(() => document.fonts.ready);
      const original = await values(page);
      await expect(tables(page)).toHaveCount(3);
      expect(original.length).toBeGreaterThan(20);
      await page.setViewportSize({ width, height: 1000 });
      expect(await values(page)).toEqual(original);
      await assertReadable(page);
      await assertPresentation(page);
    });
  }
}

test('the same viewport supports both sides of the table container breakpoint', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/guides/review-and-ship/');
  const original = await values(page);
  for (const rem of [39, 40, 41]) {
    // Change only the containing box, keeping viewport and original cell nodes fixed.
    await page.locator('.ca-table-shell--stackable').evaluateAll((shells, size) => {
      for (const shell of shells as HTMLElement[]) {
        shell.style.boxSizing = 'content-box';
        shell.style.width = `${size}rem`;
        shell.style.maxWidth = 'none';
      }
    }, rem);
    const layouts = await assertPresentation(page);
    expect(layouts.every(layout => layout.stacked === (rem <= 40))).toBe(true);
    expect(await values(page)).toEqual(original);
    await assertReadable(page);
  }
});

test('review host entries include readable Pi and every full command at 390px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/guides/review-and-ship/');
  const hostTable = tables(page).nth(1);
  await expect(hostTable.getByRole('columnheader', { name: 'Pi', exact: true })).toHaveCount(1);
  await expect(hostTable.getByRole('cell', { name: '/ca-pr --cleanup', exact: true })).toHaveCount(1);
  expect(await hostTable.locator('.ca-table-cell-value').allTextContents()).toContain('/ca-pr --watch 123');
  await assertReadable(page);
  // Native column names remain in the accessibility tree; decorative repeats do not.
  const semantics = await hostTable.ariaSnapshot();
  expect(semantics).toContain('columnheader "Pi"');
  expect(semantics).toContain('cell "/ca-pr --cleanup"');
  await expect(hostTable.locator('.ca-table-cell-label').first()).toHaveAttribute('aria-hidden', 'true');
});

test('all simple guide tables reflow, not only the reported screenshot', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  let checked = 0;
  for (const group of guideGroups) {
    for (const slug of group.slugs) {
      await page.goto(`/guides/${slug}/`);
      if (await tables(page).count()) { await assertReadable(page, false); checked++; }
    }
  }
  expect(checked).toBeGreaterThan(10);
});

test('table content stays readable with enlarged text and without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  const page = await context.newPage();
  for (const slug of targets) {
    await page.goto(`http://127.0.0.1:4322/guides/${slug}/`);
    await assertReadable(page);
    const original = await values(page);
    await enlargeText(page);
    expect(await values(page)).toEqual(original);
    await assertPresentation(page);
    await assertReadable(page);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  }
  await context.close();
});

for (const slug of targets) {
  for (const forcedColors of ['none', 'active'] as const) {
    test(`${slug}: readable table contrast and associations in ${forcedColors} forced colors`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 1000 });
      await page.emulateMedia({ forcedColors });
      await page.goto(`/guides/${slug}/`);
      await assertReadable(page);
      await assertPresentation(page);
      const result = await new AxeBuilder({ page }).include('.ca-table-shell--stackable')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    });
  }
}

test('table links remain keyboard-operable after navigating back', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/guides/investigate-and-fix/');
  const continuation = tables(page).last().getByRole('link', { name: 'Resume and recover', exact: true });
  await continuation.focus(); await expect(continuation).toBeFocused();
  await continuation.press('Enter'); await expect(page).toHaveURL(/\/guides\/resume-and-recover\/$/);
  await page.goBack(); await assertReadable(page);
});

test('printing retains all table values and does not clip their text', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  for (const slug of targets) {
    await page.emulateMedia({ media: 'screen' });
    await page.goto(`/guides/${slug}/`);
    const original = await values(page);
    await page.emulateMedia({ media: 'print' });
    expect(await values(page)).toEqual(original);
    await expect(page.locator('.ca-table-cell-value')).toHaveCount(original.length);
    await assertReadable(page);
  }
});

test('capture complete corrected tables and the investigation guide at desktop and mobile widths', async ({ page }) => {
  const directory = join(process.cwd(), '.astro', 'browser-evidence'); mkdirSync(directory, { recursive: true });
  const evidence: Record<string, unknown> = {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(),
  };
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const slug of targets) {
      await page.goto(`/guides/${slug}/`); await page.evaluate(() => document.fonts.ready);
      evidence[`${slug}-${width}`] = await inspectCells(page);
      if (width <= 390) await assertReadable(page);
      await page.screenshot({ path: join(directory, `${slug}-reflow-${width}.png`), fullPage: true });
      for (let index = 0; index < await tables(page).count(); index++) {
        await page.locator('.ca-table-shell--stackable').nth(index).screenshot({ path: join(directory, `${slug}-table-${index + 1}-${width}.png`) });
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.emulateMedia({ forcedColors: 'active' }); await page.goto('/guides/review-and-ship/');
  await assertReadable(page);
  await page.screenshot({ path: join(directory, 'review-and-ship-reflow-forced-colors-390.png'), fullPage: true });
  await page.emulateMedia({ forcedColors: 'none' });
  await enlargeText(page);
  evidence['review-and-ship-enlarged-390'] = await assertReadable(page);
  await page.locator('.ca-table-shell--stackable').nth(1).screenshot({ path: join(directory, 'review-host-entries-enlarged-390.png') });
  writeFileSync(join(directory, 'guide-reflow-evidence.json'), JSON.stringify(evidence, null, 2));
});
