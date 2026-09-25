import { test, expect } from '@playwright/test';
import { workflows } from '../../scripts/execution-maps/workflows';
import { workflowMapHref } from '../../scripts/execution-maps/locations';

for (const w of workflows) test(`${w.id}: the directory opens the exact map, not a closed or sibling route`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/concepts/workflow-routes/');
  const link = page.locator(`[data-workflow-link="${w.id}"] [data-workflow-map-link]`);
  await expect(link).toHaveAttribute('href', workflowMapHref(w));
  await link.focus(); await link.press('Enter');
  await expect(page).toHaveURL(new RegExp(workflowMapHref(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
  const map = page.locator(`[data-workflow="${w.id}"]`);
  const first = map.locator(`[data-map-chapter="${w.map.chapters[0].id}"]`);
  await expect(first).toBeVisible();
  await expect(map.locator(`[data-map-select="${w.map.chapters[0].id}"]`)).toHaveAttribute('aria-pressed', 'true');
  if (w.id === 'greenfield' || w.id === 'brownfield') {
    const other = w.id === 'greenfield' ? 'brownfield' : 'greenfield';
    await expect(page.locator(`[data-workflow="${other}"]`)).toBeHidden();
  }
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('chapter links advance, restore Back, reload and same-fragment selection without a saved bookmark', async ({ page }) => {
  const w = workflows[0];
  await page.goto(workflowMapHref(w));
  const map = page.locator('[data-workflow="sprint"]');
  const state = () => page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
  const before = await state();
  const first = map.locator('[data-map-chapter="review-pair"]');
  await expect(first).toBeVisible();
  await first.locator('[data-map-next]').focus(); await page.keyboard.press('Enter');
  const second = map.locator('[data-map-chapter="execute-tasks"]');
  await expect(second).toBeVisible(); await expect(first).toBeHidden();
  await expect(page).toHaveURL(/#sprint-execution-map-execute-tasks$/);
  await page.reload(); await expect(second).toBeVisible();
  await map.locator('[data-map-select="all"]').click();
  await second.locator('[data-map-permalink]').click(); // Same hash still restores this view.
  await expect(map.locator('[data-map-chapter]:visible')).toHaveCount(1);
  await page.goBack(); await expect(first).toBeVisible();
  await expect(page).toHaveURL(/#sprint-execution-map-review-pair$/);
  expect(await state()).toEqual(before);
});

test('all chapter permalinks, previous/next links and final outcomes agree with the source map', async ({ page }) => {
  for (const w of workflows) {
    await page.goto(workflowMapHref(w));
    const map = page.locator(`[data-workflow="${w.id}"]`);
    const id = await map.locator('ca-execution-map').getAttribute('id');
    for (const [index, chapter] of w.map.chapters.entries()) {
      const section = map.locator(`[data-map-chapter="${chapter.id}"]`);
      await map.locator(`[data-map-select="${chapter.id}"]`).click();
      await expect(section.locator('[data-map-permalink]')).toHaveAttribute('href', `#${id}-${chapter.id}`);
      await expect(section.locator('[data-map-previous]')).toHaveCount(index > 0 ? 1 : 0);
      if (index > 0) await expect(section.locator('[data-map-previous]')).toHaveAttribute('href', `#${id}-${w.map.chapters[index - 1].id}`);
      if (index + 1 < w.map.chapters.length) await expect(section.locator('[data-map-next]')).toHaveAttribute('href', `#${id}-${w.map.chapters[index + 1].id}`);
      else {
        await expect(section.locator('[data-map-next]')).toHaveCount(0);
        await expect(section.locator('[data-map-end]')).toHaveAttribute('href', '/concepts/workflow-routes/');
        await expect(map).toContainText(w.map.outcome);
      }
    }
  }
});

test('unknown and malformed fragments do not execute selectors or open unrelated disclosures', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  for (const hash of ['#%E0%A4%A', '#unrelated', '#%23%5Bdata-map-chapter%5D']) {
    await page.goto(`/guides/opt-in-a-repo/${hash}`);
    await expect(page.locator('#initialization-routes')).not.toHaveAttribute('open');
    await expect(page.locator('[data-workflow="greenfield"]')).toBeHidden();
  }
  expect(errors).toEqual([]);
});

test('native chapter links and all content survive without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage();
    for (const w of [workflows[0], workflows[4], workflows[5]]) {
      await page.goto(`http://127.0.0.1:4322${workflowMapHref(w)}`);
      const chapter = page.locator(`[data-workflow="${w.id}"] [data-map-chapter]`).first();
      await expect(chapter).toBeVisible();
      await expect(page.locator(`[data-workflow="${w.id}"] [data-map-step]:visible`)).toHaveCount(w.map.chapters.flatMap(c => c.nodes).length);
      await expect(page.locator(`[data-workflow="${w.id}"] [data-map-select]:visible`)).toHaveCount(0);
    }
  } finally { await context.close(); }
});
