import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import capture from '../../src/data/context-examples.json' with { type: 'json' };

const concepts = ['provenance-drift', 'jit-context-injection', 'persona-and-context'];
const roots = 'ca-context-explorer, ca-execution-map';
const textRoots = 'ca-context-explorer, .ca-execution-map__reading, [data-role-reference]';

/** Inspect actual text rectangles, not only a containing page's scroll width. */
async function readable(page: Page) {
  const observation = await page.locator(textRoots).evaluateAll(regions => regions.filter(region => region.checkVisibility()).map(region => {
    const problems: string[] = [];
    const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || !node.textContent?.trim() || !parent.checkVisibility() || parent.closest('svg, script, style')) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      const box = region.getBoundingClientRect();
      for (const rect of Array.from(range.getClientRects())) {
        if (rect.width && (rect.left < Math.max(0, box.left) - 1 || rect.right > Math.min(innerWidth, box.right) + 1)) {
          problems.push(node.textContent.slice(0, 100));
        }
      }
    }
    return { region: region.tagName, width: region.getBoundingClientRect().width, problems };
  }));
  expect(observation.length).toBeGreaterThan(0);
  observation.forEach(item => expect(item.problems).toEqual([]));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 1);
  return observation;
}
async function showAll(page: Page) {
  const explorer = page.locator('ca-context-explorer');
  if (await explorer.count()) await explorer.locator('[data-context-select="all"]').click();
  const map = page.locator('ca-execution-map');
  if (await map.count()) await map.locator('[data-map-select="all"]').click();
}

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`C03 actual context observations and roles remain readable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    for (const slug of concepts) {
      await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
      await showAll(page); await readable(page);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    }
  });
}

test('every context selection exposes the unchanged actual capture and has no side effects', async ({ page }) => {
  await page.goto('/concepts/jit-context-injection/');
  const explorer = page.locator('ca-context-explorer');
  await expect(explorer.locator('[data-context-select="overlap"]')).toBeVisible();
  const before = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, url: location.href }));
  const requests: string[] = [];
  const listen = (request: { url(): string }) => requests.push(request.url());
  page.on('request', listen);
  for (const item of capture.cases) {
    const control = explorer.locator(`[data-context-select="${item.id}"]`);
    await control.click(); await expect(control).toHaveAttribute('aria-pressed', 'true');
    await expect(explorer.locator('[data-context-case]:visible')).toHaveCount(1);
    const reading = explorer.locator(`[data-context-case="${item.id}"]`);
    if (item.emitted) await expect(reading.locator('pre code')).toHaveText(item.emitted);
    else await expect(reading).toContainText('empty string');
    await readable(page);
  }
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, url: location.href }))).toEqual(before);
  expect(requests).toEqual([]); page.off('request', listen);
  await showAll(page); await expect(explorer.locator('[data-context-case]:visible')).toHaveCount(4);
  const response = await page.request.get('/examples/context-observations.json');
  expect(response.ok()).toBe(true); expect(await response.json()).toEqual(capture);
});

test('context controls reconnect after navigating to the other concept and back', async ({ page }) => {
  await page.goto('/concepts/jit-context-injection/');
  await page.locator('ca-context-explorer').getByRole('link', { name: 'Understand freshness', exact: true }).click();
  await expect(page).toHaveURL(/\/concepts\/provenance-drift\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.goBack(); await expect(page).toHaveURL(/\/concepts\/jit-context-injection\/$/);
  const control = page.locator('[data-context-select="changed"]');
  await expect(control).toBeVisible(); await control.click();
  await expect(control).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-context-case="changed"]')).toBeVisible();
});

for (const forcedColors of ['none', 'active'] as const) {
  test(`C03 controls retain keyboard operation and contrast with ${forcedColors} forced colors`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1000 }); await page.emulateMedia({ forcedColors });
    for (const slug of ['provenance-drift', 'jit-context-injection']) {
      await page.goto(`/concepts/${slug}/`);
      const buttons = page.locator('[data-context-select]');
      for (let i = 0; i < await buttons.count(); i++) {
        await buttons.nth(i).focus(); await page.keyboard.press('Enter');
        await expect(buttons.nth(i)).toBeFocused(); await readable(page);
      }
      const result = await new AxeBuilder({ page }).include('ca-context-explorer').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    }
  });
}

for (const slug of concepts) test(`${slug}: no-script, enlarged text and print preserve every observation`, async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage(); await page.goto(`http://127.0.0.1:4322/concepts/${slug}/`);
    await expect(page.locator('[data-context-select]:visible, [data-map-select]:visible')).toHaveCount(0);
    if (slug === 'persona-and-context') await expect(page.locator('[data-map-step]')).toHaveCount(16);
    else await expect(page.locator('[data-context-case]:visible')).toHaveCount(4);
    const text = await page.locator(roots).allTextContents(); await readable(page);
    const fontSize = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    await page.evaluate(size => { document.documentElement.style.fontSize = `${size * 2}px`; }, fontSize);
    expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))).toBeCloseTo(fontSize * 2, 2);
    expect(await page.locator(roots).allTextContents()).toEqual(text); await readable(page);
    await page.emulateMedia({ media: 'print' });
    expect(await page.locator(roots).allTextContents()).toEqual(text); await readable(page);
  } finally { await context.close(); }
});

test('print restores context cases hidden by a reading selection', async ({ page }) => {
  await page.goto('/concepts/jit-context-injection/');
  await page.locator('[data-context-select="changed"]').click();
  await expect(page.locator('[data-context-case]:visible')).toHaveCount(1);
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('[data-context-case]:visible')).toHaveCount(4);
  await expect(page.locator('[data-context-select]:visible')).toHaveCount(0);
  await readable(page);
});

test('historical rationale and hardening remain explicitly separate from current efficacy', async ({ page }) => {
  for (const slug of ['persona-research-basis', 'hardening-history']) {
    await page.goto(`/concepts/${slug}/`);
    await expect(page.locator('.sl-markdown-content')).toContainText('historical');
    const oldSource = page.locator(`.sl-markdown-content a[href*="${capture.source_revision}/site/src/content/docs/concepts/${slug}.md"]`);
    await expect(oldSource).toHaveCount(1);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  }
});

test('the exact role lookup stays complete and readable without JavaScript or lost release limits', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:4322/concepts/persona-and-context/');
    const disclosure = page.locator('[data-role-reference="packaged-charters"]');
    const summary = disclosure.locator('summary');
    await summary.focus(); await page.keyboard.press('Enter');
    await expect(disclosure).toHaveAttribute('open', '');
    const charters = readdirSync(join(process.cwd(), '..', 'plugins', 'ca-codex', 'agents'))
      .filter(name => name.endsWith('.md') && name !== 'INDEX.md')
      .map(name => name.slice(0, -3)).sort();
    const roleLinks = disclosure.locator('a[href^="/reference/agents/"]');
    expect((await roleLinks.allTextContents()).sort()).toEqual(charters);
    await expect(disclosure).toContainText('complete packaged resource charter set for that release');
    await expect(disclosure).toContainText('bounded 0.9.4 receipt');
    await expect(disclosure).toContainText('isolation is not mandatory');
    await expect(disclosure).toContainText('writer remains distinct from the read-only funnel');
    const original = await disclosure.textContent();
    await readable(page);
    const size = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    await page.evaluate(fontSize => { document.documentElement.style.fontSize = `${fontSize * 2}px`; }, size);
    expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))).toBeCloseTo(size * 2, 2);
    expect(await disclosure.textContent()).toBe(original);
    await readable(page);
    await roleLinks.last().focus(); await expect(roleLinks.last()).toBeFocused();
  } finally { await context.close(); }
});

test('record complete C03 pages, pointer cases and aligned arrows from the built candidate', async ({ page }) => {
  const directory = join(process.cwd(), '.astro', 'browser-evidence'); mkdirSync(directory, { recursive: true });
  const observations: Record<string, unknown> = {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    helperSource: capture.source_revision, browser: page.context().browser()?.version(),
  };
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const slug of concepts) {
      await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
      // The full-page capture shows the ordinary initial view, not an invented state.
      observations[`${slug}-${width}`] = await readable(page);
      await page.screenshot({ path: join(directory, `c03-${slug}-${width}.png`), fullPage: true });
      if (slug === 'persona-and-context') {
        await page.locator('[data-role-reference] summary').click();
        observations[`roles-open-${width}`] = await readable(page);
        await page.screenshot({ path: join(directory, `c03-roles-open-${width}.png`), fullPage: true });
      }
    }
    await page.goto('/concepts/jit-context-injection/');
    for (const item of capture.cases) {
      await page.locator(`[data-context-select="${item.id}"]`).click();
      observations[`${item.id}-${width}`] = await readable(page);
      await page.locator('ca-context-explorer').screenshot({ path: join(directory, `c03-pointer-${item.id}-${width}.png`) });
    }
    for (const slug of ['persona-research-basis', 'hardening-history']) {
      await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(directory, `c03-${slug}-${width}.png`), fullPage: true });
    }
  }
  await page.setViewportSize({ width: 390, height: 1000 }); await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/concepts/jit-context-injection/'); await showAll(page); await readable(page);
  await page.screenshot({ path: join(directory, 'c03-context-forced-colors-390.png'), fullPage: true });
  writeFileSync(join(directory, 'c03-context-evidence.json'), JSON.stringify(observations, null, 2));
});
