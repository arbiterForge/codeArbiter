import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { getWorkflow } from '../../scripts/execution-maps/workflows';

const guides = ['opt-in-a-repo', 'feature-lane', 'autonomous-sprints'];
const routes = ['/', '/academy/', '/academy/f01-fork-clone-doctor/', '/product-tour/', ...guides.map(slug => `/guides/${slug}/`)];

/** Inspect visible peer boxes, including their margins rather than just overflow. */
async function peerGeometry(page: Page) {
  return page.locator('[data-ca-layout="peers"]').evaluateAll(elements => elements
    .filter(element => element.checkVisibility())
    .map(element => {
      const css = getComputedStyle(element);
      return {
        name: element.className,
        display: css.display,
        columns: css.display === 'grid' ? css.gridTemplateColumns.split(' ').length : 0,
        children: Array.from(element.children).filter(child => child.checkVisibility()).map(child => {
          const box = child.getBoundingClientRect();
          const style = getComputedStyle(child);
          return { text: child.textContent?.trim().slice(0, 60), x: box.x, y: box.y,
            width: box.width, height: box.height,
            marginStart: parseFloat(style.marginBlockStart), marginEnd: parseFloat(style.marginBlockEnd) };
        }),
      };
    }));
}

/** A single-column layout may have different content heights; a shared row may not stagger. */
function assertPeerGeometry(groups: Awaited<ReturnType<typeof peerGeometry>>, route: string) {
  expect(groups.length, `${route}: no peer groups were exercised`).toBeGreaterThan(0);
  for (const group of groups) {
    expect(group.children.length, `${route}: empty ${group.name}`).toBeGreaterThan(0);
    for (const child of group.children) {
      expect(child.marginStart, `${route} ${group.name}: ${child.text} starts with a prose margin`).toBe(0);
      expect(child.marginEnd, `${route} ${group.name}: ${child.text} ends with a prose margin`).toBe(0);
    }
    if (group.columns > 1) {
      for (let index = 0; index < group.children.length; index += group.columns) {
        const row = group.children.slice(index, index + group.columns);
        for (const child of row) {
          expect(Math.abs(child.y - row[0].y), `${group.name}: staggered row`).toBeLessThanOrEqual(1);
          expect(Math.abs(child.width - row[0].width), `${group.name}: uneven peer widths`).toBeLessThanOrEqual(1);
          expect(Math.abs(child.height - row[0].height), `${group.name}: uneven peer heights`).toBeLessThanOrEqual(1);
        }
      }
    }
  }
}

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`peer cards own their spacing at ${width}px, including expanded Academy states`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of routes) {
      await page.goto(route);
      await page.evaluate(() => document.fonts.ready);
      assertPeerGeometry(await peerGeometry(page), route);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      if (route === '/academy/') {
        await page.locator('[data-academy-show-all]').click();
        await expect(page.locator('.academy-overview__more[open]')).toHaveCount(3);
        assertPeerGeometry(await peerGeometry(page), `${route} expanded`);
      }
    }
  });
}

for (const width of [390, 1440]) {
  test(`every exhibit selection retains peer geometry at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/product-tour/');
    const examples = page.locator('ca-example-choices');
    await expect(examples).toHaveCount(4);
    for (const example of await examples.all()) {
      const buttons = example.locator(':scope > .ca-example-controls > button');
      expect(await buttons.count()).toBeGreaterThan(1);
      for (const button of await buttons.all()) {
        await button.click();
        await expect(button).toHaveAttribute('aria-pressed', 'true');
        assertPeerGeometry(await peerGeometry(page), `exhibit: ${await button.textContent()}`);
      }
    }
  });
}

test('the first peer has no layout privilege when content and order change', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await page.locator('.ca-host-grid').evaluate(grid => {
    // Identical content removes text length as an explanation for unequal boxes.
    const original = grid.firstElementChild!;
    grid.replaceChildren(original, original.cloneNode(true), original.cloneNode(true));
    grid.append(grid.firstElementChild!);
  });
  assertPeerGeometry(await peerGeometry(page), 'equal-content reordered hosts');
  const paragraph = page.locator('.ca-host-grid p').first();
  expect(await paragraph.evaluate(node => getComputedStyle(node).lineHeight)).not.toBe('0px');
});

/** Exercise every native disclosure, including both independent init routes. */
async function readImplementation(page: Page, slug: string, script: boolean) {
  const disclosures = page.locator('details.ca-implementation-view');
  await expect(disclosures).toHaveCount(slug === 'opt-in-a-repo' ? 3 : 1);
  for (const detail of await disclosures.all()) await expect(detail).not.toHaveAttribute('open');
  // DOM order is outer-first. Scope to the immediate summary, never descendants.
  for (const detail of await disclosures.all()) {
    const summary = detail.locator(':scope > summary');
    await summary.focus(); await summary.press('Enter');
    await expect(detail).toHaveAttribute('open', '');
  }
  if (slug === 'feature-lane') {
    await expect(disclosures.locator('img')).toBeVisible();
    return;
  }
  for (const id of slug === 'opt-in-a-repo' ? ['greenfield', 'brownfield'] : ['sprint']) {
    const model = getWorkflow(id).map;
    const map = page.locator(`[data-workflow="${id}"]`);
    await expect(map).toBeVisible();
    if (script) await map.getByRole('button', { name: 'Read whole path', exact: true }).click();
    else await expect(map.locator('[data-map-select]:visible')).toHaveCount(0);
    await expect(map.locator('[data-map-step]:visible')).toHaveCount(model.chapters.flatMap(c => c.nodes).length);
    for (const chapter of model.chapters) {
      await expect(map.locator(`[data-map-chapter="${chapter.id}"]`)).toContainText(chapter.output);
    }
    await expect(map).toContainText(model.outcome);
  }
}

test('reader maps precede optional implementation detail and preserve authority boundaries', async ({ page }) => {
  for (const slug of guides) {
    await page.goto(`/guides/${slug}/`);
    const map = page.locator('[data-reader-journey]');
    await expect(map.locator('ol > li')).toHaveCount(4);
    await expect(map.getByText('What you get', { exact: true })).toHaveCount(4);
    await expect(map.getByText('Before moving on', { exact: true })).toHaveCount(4);
    await expect(map).toContainText('Reading map, not a captured run or live status');
    expect(await map.evaluate(node => Array.from(document.querySelectorAll('.ca-implementation-view'))
      .every(detail => !!(node.compareDocumentPosition(detail) & Node.DOCUMENT_POSITION_FOLLOWING)))).toBe(true);
    await readImplementation(page, slug, true);
    const result = await new AxeBuilder({ page }).include('[data-reader-journey]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
  }
  await expect(page.locator('[data-reader-journey]')).toContainText('currently limited to Codex and Claude Code');
  await expect(page.locator('[data-reader-journey]')).toContainText('a generic reply or an unobserved approval cannot start execution');
  await expect(page.locator('[data-reader-journey]')).toContainText('One host-observed reply approving both exact initial artifact identities');
});

test('maps and implementation disclosure work without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    for (const slug of guides) {
      await page.goto(`/guides/${slug}/`);
      await expect(page.locator('.ca-reader-journey__step')).toHaveCount(4);
      await readImplementation(page, slug, false);
      await page.locator('.ca-reader-journey__step a').first().click();
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('h1')).not.toHaveText('404');
    }
  } finally { await context.close(); }
});

test('maps retain focus in forced colors, reduced motion, and printable implementation detail', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.goto('/guides/feature-lane/');
  const summary = page.locator('.ca-implementation-view > summary');
  await summary.focus();
  expect(await summary.evaluate(node => getComputedStyle(node).outlineStyle)).not.toBe('none');
  await page.keyboard.press('Enter');
  await expect(page.locator('.ca-implementation-view img')).toBeVisible();
  await summary.click();
  await page.emulateMedia({ media: 'print', forcedColors: 'none' });
  await expect(page.locator('.ca-reader-journey__step')).toHaveCount(4);
  const printDetail = await page.locator('.ca-implementation-view').evaluate(node => {
    const css = getComputedStyle(node, '::details-content');
    return { display: css.display, visibility: css.contentVisibility };
  });
  expect(printDetail).toEqual({ display: 'block', visibility: 'visible' });
});

/** Retain actual geometry and full-page screenshots, not synthetic pixel approvals. */
test('capture corrected card groups and reader maps', async ({ page }) => {
  const out = join(process.cwd(), '.astro/browser-evidence');
  mkdirSync(out, { recursive: true });
  const captures = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/', '/academy/', ...guides.map(slug => `/guides/${slug}/`)]) {
      await page.goto(route);
      await page.evaluate(() => document.fonts.ready);
      const name = route.replaceAll('/', '-').replace(/^-|-$/g, '') || 'home';
      const filename = `visual-${name}-${width}.png`;
      await page.screenshot({ path: join(out, filename), fullPage: true });
      captures.push({ route, width, filename, groups: await peerGeometry(page) });
    }
  }
  writeFileSync(join(out, 'peer-layout-geometry.json'), JSON.stringify({
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(),
    browser: page.context().browser()?.version(), captures,
  }, null, 2));
});
