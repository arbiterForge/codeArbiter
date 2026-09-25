import { test, expect, type Page, type Locator } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { workflows, type WorkflowDefinition } from '../../scripts/execution-maps/workflows';

const route = (w: WorkflowDefinition) => ['greenfield', 'brownfield'].includes(w.id) ? '/guides/opt-in-a-repo/' : w.guide;
const root = (page: Page, w: WorkflowDefinition) => page.locator(`[data-workflow="${w.id}"]`);

/** Use the actual native disclosures, outermost first; never reveal content by patching app state. */
async function openMap(page: Page, w: WorkflowDefinition) {
  // URL changes precede Astro's DOM replacement on Back. Wait for the actual
  // destination map before discovering its (possibly nested) closed ancestors.
  await expect(root(page, w)).toHaveCount(1);
  const ancestors = page.locator(`details:has([data-workflow="${w.id}"])`);
  for (let index = 0; index < await ancestors.count(); index++) {
    const details = ancestors.nth(index);
    if (await details.getAttribute('open') === null) {
      const summary = details.locator(':scope > summary');
      await summary.focus(); await summary.press('Enter');
      await expect(details).toHaveAttribute('open', '');
    }
  }
  await expect(root(page, w)).toBeVisible();
}

/** Measure actual text, diagram labels, and connector endpoint geometry after site styles. */
async function inspect(page: Page, w: WorkflowDefinition) {
  const result = await root(page, w).evaluate(region => {
    const problems: string[] = [];
    const box = region.getBoundingClientRect();
    const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!node.textContent?.trim() || !parent || parent.closest('svg,script,style') || !parent.checkVisibility({ contentVisibilityAuto: true })) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      for (const rect of Array.from(range.getClientRects())) {
        if (rect.width && rect.height && (rect.left < Math.max(0, box.left) - 1 || rect.right > Math.min(innerWidth, box.right) + 1)) problems.push(node.textContent.slice(0, 90));
      }
    }
    const diagrams = Array.from(region.querySelectorAll<SVGSVGElement>('.ca-execution-map__plot svg'))
      .filter(svg => svg.checkVisibility()).map(svg => ({
        chapter: svg.dataset.executionChapter,
        width: svg.getBoundingClientRect().width,
        labels: Array.from(svg.querySelectorAll('text')).map(label => ({ text: label.textContent,
          width: label.getBBox().width, maximum: Number(label.getAttribute('data-max-width')) })),
        arrows: Array.from(svg.querySelectorAll<SVGPathElement>('[data-map-edge]')).map(path => {
          const id = path.getAttribute('marker-end')!.match(/#([^)]*)/)![1];
          const marker = svg.querySelector<SVGMarkerElement>(`#${id}`)!;
          const end = path.getPointAtLength(path.getTotalLength());
          const prior = path.getPointAtLength(path.getTotalLength() - 12);
          return { edge: path.dataset.mapEdge, units: marker.getAttribute('markerUnits'),
            refX: marker.refX.baseVal.value, refY: marker.refY.baseVal.value,
            approachX: end.x - prior.x, approachY: end.y - prior.y };
        }),
      }));
    return { width: box.width, viewport: innerWidth, pageWidth: document.documentElement.scrollWidth, problems, diagrams };
  });
  expect(result.problems, w.id).toEqual([]);
  expect(result.pageWidth, w.id).toBeLessThanOrEqual(result.viewport + 1);
  for (const plot of result.diagrams) {
    for (const label of plot.labels) expect(label.width, label.text ?? '').toBeLessThanOrEqual(label.maximum + 1);
    for (const arrow of plot.arrows) {
      expect(arrow.units).toBe('userSpaceOnUse'); expect(arrow.refX).toBe(9); expect(arrow.refY).toBe(4);
      expect(arrow.approachX).toBeCloseTo(12, 2); expect(arrow.approachY).toBeCloseTo(0, 2);
    }
  }
  return result;
}

async function selectAll(map: Locator) {
  await map.locator('[data-map-select="all"]').click();
}

for (const w of workflows) test(`${w.id}: the full route retains exact stages, outputs and continuous numbering`, async ({ page }) => {
  await page.goto(route(w)); await openMap(page, w);
  let number = 0;
  for (const chapter of w.map.chapters) {
    const control = root(page, w).locator(`[data-map-select="${chapter.id}"]`);
    await control.click(); await expect(control).toHaveAttribute('aria-pressed', 'true');
    const visible = root(page, w).locator('[data-map-chapter]:visible');
    await expect(visible).toHaveCount(1);
    expect(await visible.locator('[data-map-step]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-map-step')))).toEqual(chapter.nodes.map(node => node.id));
    for (const node of chapter.nodes) {
      number++;
      const step = visible.locator(`[data-map-step="${node.id}"]`);
      await expect(step).toHaveAttribute('data-role', node.role);
      await expect(step.locator('.ca-execution-map__number')).toHaveText(String(number).padStart(2, '0'));
      await expect(step).toContainText(node.detail); await expect(step).toContainText(node.output);
      await expect(step.locator('.ca-execution-map__source')).toHaveAttribute('href', `https://github.com/arbiterForge/codeArbiter/blob/${w.map.reviewedAt}/${w.map.sources[node.source].path}`);
    }
    await expect(visible).toContainText(chapter.output);
  }
  await selectAll(root(page, w));
  await expect(root(page, w).locator('[data-map-step]:visible')).toHaveCount(number);
  await expect(root(page, w)).toContainText(w.map.outcome);
  await expect(root(page, w).locator(`a[href="/diagrams/${w.asset}"]`)).toHaveCount(1);
});

for (const width of [320, 390, 768, 1024, 1440]) test(`all C04 workflow chapters remain readable at ${width}px`, async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width, height: 1000 });
  for (const w of workflows) {
    await page.goto(route(w)); await page.evaluate(() => document.fonts.ready); await openMap(page, w);
    for (const chapter of w.map.chapters) {
      await root(page, w).locator(`[data-map-select="${chapter.id}"]`).click();
      const result = await inspect(page, w);
      if (width === 1440) expect(result.diagrams.length, w.id).toBeGreaterThan(0);
    }
  }
});

for (const w of workflows) test(`${w.id}: native disclosure, no-script and doubled text preserve the entire reading path`, async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage(); await page.goto(`http://127.0.0.1:4322${route(w)}`); await openMap(page, w);
    await expect(root(page, w).locator('[data-map-select]:visible')).toHaveCount(0);
    await expect(root(page, w).locator('[data-map-step]:visible')).toHaveCount(w.map.chapters.reduce((count, chapter) => count + chapter.nodes.length, 0));
    const content = await root(page, w).textContent(); await inspect(page, w);
    const size = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    await page.evaluate(value => { document.documentElement.style.fontSize = `${value * 2}px`; }, size);
    expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))).toBeCloseTo(size * 2, 2);
    expect(await root(page, w).textContent()).toBe(content); await inspect(page, w);
    await page.emulateMedia({ media: 'print' }); await inspect(page, w);
    expect(await root(page, w).textContent()).toBe(content);
  } finally { await context.close(); }
});

for (const forcedColors of ['none', 'active'] as const) test(`C04 keyboard selections and diagram alternatives retain ${forcedColors} color accessibility`, async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.emulateMedia({ forcedColors, reducedMotion: 'reduce' });
  for (const w of workflows) {
    await page.goto(route(w)); await openMap(page, w);
    const buttons = root(page, w).locator('[data-map-select]');
    for (let i = 0; i < await buttons.count(); i++) {
      await buttons.nth(i).focus(); await page.keyboard.press('Enter');
      await expect(buttons.nth(i)).toBeFocused(); await inspect(page, w);
    }
    const result = await new AxeBuilder({ page }).include(`[data-workflow="${w.id}"]`).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
  }
});

test('C04 selections are reading-only and reconnect after the reference round trip', async ({ page }) => {
  const w = workflows[0];
  await page.goto(route(w)); await openMap(page, w); await page.evaluate(() => document.fonts.ready);
  const before = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, url: location.href }));
  const requests: string[] = []; const listen = (request: { url(): string }) => requests.push(request.url());
  page.on('request', listen);
  await selectAll(root(page, w));
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, url: location.href }))).toEqual(before);
  expect(requests).toEqual([]); page.off('request', listen);
  await root(page, w).locator('[data-map-step="sprint-plan"] h5 a').click();
  await expect(page).toHaveURL(/\/reference\/skills\/writing-plans\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.goBack(); await expect(page).toHaveURL(/\/guides\/autonomous-sprints\/$/); await openMap(page, w);
  await root(page, w).locator('[data-map-select="handoff"]').click();
  await expect(root(page, w).locator('[data-map-chapter="handoff"]')).toBeVisible();
});

test('printing restores maps even when their native guide disclosures are closed', async ({ page }) => {
  for (const slug of ['autonomous-sprints', 'opt-in-a-repo', 'adding-a-dependency', 'recording-adrs', 'releasing-a-version']) {
    await page.goto(`/guides/${slug}/`);
    await page.emulateMedia({ media: 'print' });
    const expected = workflows.filter(w => route(w) === `/guides/${slug}/`).reduce((count, w) => count + w.map.chapters.reduce((sum, c) => sum + c.nodes.length, 0), 0);
    await expect(page.locator('[data-workflow] [data-map-step]:visible')).toHaveCount(expected);
    await expect(page.locator('[data-workflow] [data-map-select]:visible')).toHaveCount(0);
    await page.emulateMedia({ media: 'screen' });
  }
});

test('the route chooser and full-text search reach current procedures rather than raw source alone', async ({ page }) => {
  await page.goto('/concepts/workflow-routes/');
  const cards = page.locator('[data-workflow-link]'); await expect(cards).toHaveCount(workflows.length);
  for (const w of workflows) {
    await expect(page.locator(`[data-workflow-link="${w.id}"]`)).toContainText(w.endpoint);
    await expect(page.locator(`[data-workflow-link="${w.id}"] a`).first()).toHaveAttribute('href', w.guide);
  }
  const results = await page.evaluate(async () => {
    const moduleUrl = '/pagefind/pagefind.js';
    const search = await import(moduleUrl);
    const observations: Record<string, string[]> = {};
    for (const query of ['arm-sprint', 'release PR', 'subsequent commit']) {
      const result = await search.search(query);
      const data = await Promise.all(result.results.slice(0, 10).map((item: { data(): Promise<{ url: string }> }) => item.data()));
      observations[query] = data.map((item: { url: string }) => new URL(item.url, location.origin).pathname);
    }
    return observations;
  });
  expect(results['arm-sprint']).toContain('/guides/autonomous-sprints/');
  expect(results['release PR']).toContain('/guides/releasing-a-version/');
  expect(results['subsequent commit']).toContain('/guides/recording-adrs/');
  await cards.first().getByRole('link', { name: 'Read the procedure', exact: true }).click();
  await expect(page).toHaveURL(/\/guides\/autonomous-sprints\/$/); await openMap(page, workflows[0]);
});

/** Record the actual final tree and full, unchanged browser renders, not constructed artwork. */
test('record C04 full guide pages, role-row chapters and mobile reading paths', async ({ page }) => {
  test.setTimeout(120_000);
  const directory = join(process.cwd(), '.astro/browser-evidence'); mkdirSync(directory, { recursive: true });
  const evidence: Record<string, unknown> = {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(), source: workflows[0].map.reviewedAt,
  };
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/concepts/workflow-routes/'); await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(directory, `c04-routes-${width}.png`), fullPage: true });
    for (const w of workflows) {
      await page.goto(route(w)); await page.evaluate(() => document.fonts.ready); await openMap(page, w);
      for (const chapter of w.map.chapters) {
        await root(page, w).locator(`[data-map-select="${chapter.id}"]`).click();
        evidence[`${w.id}-${chapter.id}-${width}`] = await inspect(page, w);
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
        if (chapter === w.map.chapters[0]) await page.screenshot({ path: join(directory, `c04-${w.id}-${width}.png`), fullPage: true });
        // Capture beyond the viewport without locator.screenshot scrolling the
        // chapter beneath the sticky header. No page styles or content are changed.
        const box = await root(page, w).locator(`[data-map-chapter="${chapter.id}"]`).boundingBox();
        expect(box).not.toBeNull();
        await page.screenshot({ path: join(directory, `c04-${w.id}-${chapter.id}-${width}.png`), clip: box! });
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 1000 }); await page.emulateMedia({ forcedColors: 'active' });
  const w = workflows.find(w => w.id === 'release')!;
  await page.goto(route(w)); await openMap(page, w); await selectAll(root(page, w));
  await inspect(page, w);
  await root(page, w).screenshot({ path: join(directory, 'c04-release-forced-colors-390.png') });
  writeFileSync(join(directory, 'c04-workflow-evidence.json'), JSON.stringify(evidence, null, 2));
});
