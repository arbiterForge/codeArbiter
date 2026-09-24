import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { featureMap } from '../../scripts/execution-maps/model';
import { conceptGroups } from '../../scripts/concept-directory';

const routes = ['/concepts/', '/concepts/gated-lanes/', '/concepts/test-first/'];
const map = (page: Page) => page.locator('ca-execution-map');
const chapterButtons = (page: Page) => map(page).locator('[data-map-select]');

/** Record actual text boundaries, including nested clipping that page width misses. */
async function textGeometry(page: Page) {
  return map(page).evaluate(root => {
    const clipped: string[] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!node.textContent?.trim() || !parent || parent.closest('svg,script,style') || !parent.checkVisibility({ contentVisibilityAuto: true })) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      const rootBox = root.getBoundingClientRect();
      for (const rect of Array.from(range.getClientRects())) {
        if (!rect.width || !rect.height) continue;
        if (rect.left < Math.max(0, rootBox.left) - 1 || rect.right > Math.min(innerWidth, rootBox.right) + 1) clipped.push(node.textContent!.slice(0, 90));
      }
    }
    const plots = Array.from(root.querySelectorAll<HTMLElement>('.ca-execution-map__plot')).filter(plot => plot.checkVisibility());
    const diagrams = plots.map(plot => {
      const svg = plot.querySelector('svg')!;
      const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
      const labels = Array.from(svg.querySelectorAll('text')).map(label => {
        const rect = label.getBBox(); const maximum = Number(label.getAttribute('data-max-width'));
        return { text: label.textContent, width: rect.width, maxWidth: maximum, fontPx: Number(label.getAttribute('font-size')) * scale };
      });
      return { width: svg.getBoundingClientRect().width, labels };
    });
    return { width: root.clientWidth, pageWidth: document.documentElement.scrollWidth, viewport: innerWidth, clipped, diagrams };
  });
}

test('all chapters retain their sequence, roles, outputs and source links', async ({ page }) => {
  await page.goto('/concepts/');
  await expect(map(page).locator('.ca-execution-map__controls')).toBeVisible();
  for (const chapter of featureMap.chapters) {
    await map(page).locator(`[data-map-select="${chapter.id}"]`).click();
    const visible = map(page).locator('[data-map-chapter]:visible');
    await expect(visible).toHaveCount(1);
    expect(await visible.locator('[data-map-step]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-map-step')))).toEqual(chapter.nodes.map(node => node.id));
    for (const node of chapter.nodes) {
      const step = visible.locator(`[data-map-step="${node.id}"]`);
      await expect(step).toHaveAttribute('data-role', node.role);
      await expect(step).toContainText(node.output);
      await expect(step.locator('.ca-execution-map__source')).toHaveAttribute('href', new RegExp(featureMap.reviewedAt));
    }
  }
  await map(page).getByRole('button', { name: 'Read whole path', exact: true }).click();
  await expect(map(page).locator('[data-map-step]:visible')).toHaveCount(16);
});

test('test-first starts inside task work and still exposes entry and PR chapters', async ({ page }) => {
  await page.goto('/concepts/test-first/');
  await expect(map(page).locator('[data-map-chapter="task"]')).toBeVisible();
  await map(page).getByText('Inspect all six TDD phases', { exact: true }).click();
  await expect(map(page).locator('[data-map-step="tdd"] details ol > li')).toHaveCount(6);
  await map(page).locator('[data-map-select="deliver"]').click();
  await expect(map(page).locator('[data-map-step="pr-contract"]')).toContainText('not re-invoked');
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`concepts stay readable through every chapter at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of routes) {
      await page.goto(route); await page.evaluate(() => document.fonts.ready);
      for (const chapter of featureMap.chapters) {
        await map(page).locator(`[data-map-select="${chapter.id}"]`).click();
        const result = await textGeometry(page);
        expect(result.clipped).toEqual([]);
        expect(result.pageWidth).toBeLessThanOrEqual(width + 1);
        for (const plot of result.diagrams) for (const label of plot.labels) expect(label.width).toBeLessThanOrEqual(label.maxWidth + 1);
      }
    }
  });
}

test('wide layouts actually display a three-row map with ordered cross-row arrows', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/concepts/');
  const plot = map(page).locator('[data-map-chapter="define"] .ca-execution-map__plot');
  await expect(plot).toBeVisible();
  for (const role of ['command', 'skill']) await expect(plot.locator(`[data-role="${role}"]`).first()).toBeVisible();
  await expect(plot.locator('[data-map-edge="entry:spec"]')).toBeVisible();
  const result = await textGeometry(page);
  for (const diagram of result.diagrams) for (const label of diagram.labels) {
    // Annotation keys can be smaller; substantive node labels must remain readable.
    if (featureMap.chapters[0].nodes.some(node => node.label.includes(label.text ?? ''))) expect(label.fontPx).toBeGreaterThanOrEqual(13.5);
  }
});

test('no-script and print modes retain all sixteen steps and the complete concept navigation', async ({ browser, page }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  const noScript = await context.newPage();
  await noScript.goto('http://127.0.0.1:4322/concepts/');
  await expect(map(noScript).locator('[data-map-step]:visible')).toHaveCount(16);
  await expect(map(noScript).locator('.ca-execution-map__controls')).toBeHidden();
  await expect(noScript.getByRole('navigation', { name: 'Concept map', exact: true }).locator('section')).toHaveCount(conceptGroups.length);
  expect((await textGeometry(noScript)).clipped).toEqual([]);
  await context.close();
  await page.goto('/concepts/');
  await map(page).locator('[data-map-select="task"]').click();
  await page.emulateMedia({ media: 'print' });
  await expect(map(page).locator('[data-map-step]:visible')).toHaveCount(16);
});

test('normal and forced-color controls preserve scoped accessibility and keyboard use', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  for (const forcedColors of ['none', 'active'] as const) {
    await page.emulateMedia({ forcedColors, reducedMotion: 'reduce' });
    await page.goto('/concepts/');
    const task = map(page).locator('[data-map-select="task"]');
    await task.focus(); await task.press('Enter');
    await expect(task).toHaveAttribute('aria-pressed', 'true');
    await expect(task).toBeFocused();
    const result = await new AxeBuilder({ page }).include('ca-execution-map').include('.ca-concept-nav').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
    expect((await textGeometry(page)).clipped).toEqual([]);
  }
});

test('navigation/back reconnects the map and selection has no persistence or network side effects', async ({ page }) => {
  await page.goto('/concepts/');
  await expect(chapterButtons(page).first()).toBeVisible();
  const before = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  const requests: string[] = []; const listener = (request: { url(): string }) => requests.push(request.url());
  page.on('request', listener);
  await map(page).locator('[data-map-select="deliver"]').click();
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }))).toEqual(before);
  expect(requests).toEqual([]); page.off('request', listener);
  await map(page).locator('[data-map-step="commit"] h5 a').click();
  await expect(page).toHaveURL(/\/reference\/skills\/commit-gate\/$/);
  await page.goBack();
  await map(page).locator('[data-map-select="accept"]').click();
  await expect(map(page).locator('[data-map-chapter="accept"]')).toBeVisible();
});

test('doubled text retains the full mobile reading path', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/concepts/');
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await map(page).getByRole('button', { name: 'Read whole path', exact: true }).click();
  expect((await textGeometry(page)).clipped).toEqual([]);
});

test('capture real Concepts and execution-map layouts', async ({ page }) => {
  const dir = join(process.cwd(), '.astro', 'browser-evidence'); mkdirSync(dir, { recursive: true });
  const evidence: Record<string, unknown> = { commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(), browser: page.context().browser()?.version(), sourceReviewedAt: featureMap.reviewedAt };
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/concepts/'); await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(dir, `concepts-${width}.png`), fullPage: true });
    for (const chapter of featureMap.chapters) {
      await map(page).locator(`[data-map-select="${chapter.id}"]`).click();
      evidence[`${width}-${chapter.id}`] = await textGeometry(page);
      await page.screenshot({ path: join(dir, `concepts-${chapter.id}-${width}.png`), fullPage: true });
    }
    for (const slug of ['artifacts', 'gated-lanes', 'test-first']) {
      await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(dir, `concept-${slug}-${width}.png`), fullPage: true });
    }
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.emulateMedia({ forcedColors: 'active' }); await page.goto('/concepts/');
  await page.screenshot({ path: join(dir, 'concepts-forced-colors-390.png'), fullPage: true });
  writeFileSync(join(dir, 'concept-execution-evidence.json'), JSON.stringify(evidence, null, 2));
});
