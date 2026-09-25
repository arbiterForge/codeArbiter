import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { adrCases, auditCases, evidenceSourceRevision } from '../../scripts/decision-evidence';

const pages = ['smarts','adrs','checkpoints','auditability'];
const roots = '.ca-smarts-comparison, .ca-decision-routes, .ca-decision-evidence, .ca-checkpoint-map';
/** Inspect visible text, including nested nodes; page overflow alone misses clipped children. */
async function readable(page: Page) {
  const observations = await page.locator(roots).evaluateAll(regions => regions.map(region => {
    const problems: string[] = [];
    const walker = document.createTreeWalker(region,NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      if (!node.textContent?.trim()) continue;
      const parent = node.parentElement;
      if (!parent?.checkVisibility() || parent.closest('svg,script,[hidden]')) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      for (const box of Array.from(range.getClientRects())) if (box.width && (box.left < -1 || box.right > innerWidth+1)) problems.push(node.textContent.slice(0,100));
    }
    return { className: region.className, width: region.getBoundingClientRect().width, problems };
  }));
  expect(observations.length).toBeGreaterThan(0);
  observations.forEach(item => expect(item.problems).toEqual([]));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0)+1);
  return observations;
}
async function compareAll(page: Page) {
  const all = page.locator('ca-decision-evidence').getByRole('button',{name:'Compare all',exact:true});
  if (await all.count()) await all.click();
}

for (const width of [320,390,768,1024,1440]) test(`C02 concepts retain every evidence field at ${width}px`, async ({ page }) => {
  await page.setViewportSize({width,height:1000});
  for (const slug of pages) {
    await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
    await compareAll(page); await readable(page);
    await expect(page.getByRole('heading',{level:1})).toHaveCount(1);
  }
});

test('the complete comparison and distinct caller handoffs are visible without scoring controls', async ({ page }) => {
  await page.goto('/concepts/smarts/');
  await expect(page.locator('[data-smarts-lens]')).toHaveCount(6);
  await expect(page.locator('[data-smarts-option]')).toHaveCount(12);
  await expect(page.locator('[data-decision-route] ol > li')).toHaveCount(8);
  await expect(page.locator('.ca-smarts-comparison button')).toHaveCount(0);
  await expect(page.locator('[data-decision-route="reconcile"]')).toContainText('user resolves each variance');
  await expect(page.locator('[data-decision-route="sprint"]')).toContainText('not an autonomous merge');
});

test('checkpoint flow retains seven ordered roles, a separate writer and no invented PR endpoint', async ({ page }) => {
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/concepts/checkpoints/');
  await expect(page.locator('[data-checkpoint-step]')).toHaveCount(7);
  const ids = await page.locator('[data-checkpoint-step]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-checkpoint-step')));
  expect(ids.indexOf('sweep-verdict')).toBeLessThan(ids.indexOf('sweep-write'));
  await expect(page.locator('.ca-checkpoint-map__plot').first()).toBeVisible();
  await expect(page.locator('.ca-checkpoint-map svg [data-map-node]')).toHaveCount(7);
  await expect(page.locator('.ca-checkpoint-map')).toContainText('No code repair, commit, PR');
});

test('all evidence selections remain labelled, complete and read-only across navigation', async ({ page }) => {
  for (const [slug,cases] of [['adrs',adrCases],['auditability',auditCases]] as const) {
    await page.goto(`/concepts/${slug}/`);
    const region = page.locator('ca-decision-evidence');
    await expect(region.getByRole('button',{name:cases[0].label,exact:true})).toBeVisible();
    const before = await page.evaluate(() => ({local:{...localStorage}, session:{...sessionStorage}}));
    const requests: string[]=[]; const listener=(request:{url():string})=>requests.push(request.url());
    page.on('request',listener);
    for (const item of cases) {
      const button=region.getByRole('button',{name:item.label,exact:true}); await button.click();
      await expect(button).toHaveAttribute('aria-pressed','true');
      await expect(region.locator('[data-evidence-case]:visible')).toHaveCount(1);
      await expect(region.locator(`[data-evidence-case="${item.id}"]`)).toContainText(item.missing);
      await readable(page);
    }
    expect(await page.evaluate(() => ({local:{...localStorage},session:{...sessionStorage}}))).toEqual(before);
    expect(requests).toEqual([]); page.off('request',listener);
    await compareAll(page); await expect(region.locator('[data-evidence-case]:visible')).toHaveCount(cases.length);
  }
  await page.goto('/concepts/adrs/');
  await page.locator('[data-evidence-case="accepted"] a').first().click();
  // Astro's client navigation completes after the click. Back must leave the
  // actual destination, not race against history insertion on the origin page.
  await expect(page).toHaveURL(/\/reference\/skills\/decision-lifecycle\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/concepts\/adrs\/$/);
  const restored = page.locator('ca-decision-evidence').getByRole('button',{name:'Verified',exact:true});
  await expect(restored).toBeVisible();
  await restored.click();
  await expect(restored).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-evidence-case="verified"]')).toBeVisible();
});

test('every view preserves contrast and keyboard focus in normal and forced colors', async ({ page }) => {
  test.setTimeout(90000);
  await page.setViewportSize({width:390,height:1000});
  for (const forcedColors of ['none','active'] as const) {
    await page.emulateMedia({forcedColors});
    for (const slug of pages) {
      await page.goto(`/concepts/${slug}/`);
      const buttons = page.locator('[data-evidence-select]');
      for (let i=0; i<await buttons.count(); i++) {
        await buttons.nth(i).focus(); await page.keyboard.press('Enter');
        await expect(buttons.nth(i)).toBeFocused(); await readable(page);
      }
      // Compare-all exposes every case to axe, rather than only the initial view.
      const results=await new AxeBuilder({page}).include(roots).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
      expect(results.violations).toEqual([]);
    }
  }
});

for (const slug of pages) test(`${slug}: no-script, doubled text and printing retain the entire reading path`, async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 1000 } });
  try {
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:4322/concepts/${slug}/`);
    const cases = page.locator('[data-evidence-case]:visible');
    if (slug === 'adrs') await expect(cases).toHaveCount(adrCases.length);
    if (slug === 'auditability') await expect(cases).toHaveCount(auditCases.length);
    await expect(page.locator('[data-evidence-select]:visible')).toHaveCount(0);
    const originalText = await page.locator(roots).allTextContents();
    await readable(page);
    // The test driver can change a DOM style with site JavaScript disabled.
    // Avoid addStyleTag's load-event wait, and prove the computed size doubled.
    const originalSize = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    await page.evaluate(size => { document.documentElement.style.fontSize = `${size * 2}px`; }, originalSize);
    expect(await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))).toBeCloseTo(originalSize * 2, 2);
    expect(await page.locator(roots).allTextContents()).toEqual(originalText);
    await readable(page);
    await page.emulateMedia({ media: 'print' });
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    if (slug === 'adrs') await expect(cases).toHaveCount(adrCases.length);
    if (slug === 'auditability') await expect(cases).toHaveCount(auditCases.length);
    expect(await page.locator(roots).allTextContents()).toEqual(originalText);
    await expect(page.locator('[data-evidence-select]:visible')).toHaveCount(0);
    await readable(page);
  } finally {
    await context.close();
  }
});

test('printing a selected evidence view restores the others', async ({ page }) => {
  await page.goto('/concepts/adrs/');
  await page.locator('ca-decision-evidence').getByRole('button',{name:'Verified',exact:true}).click();
  await expect(page.locator('[data-evidence-case]:visible')).toHaveCount(1);
  await page.emulateMedia({media:'print'});
  await expect(page.locator('[data-evidence-case]:visible')).toHaveCount(4);
  await expect(page.locator('[data-evidence-select]:visible')).toHaveCount(0);
});

test('capture C02 pages, decision states and checkpoint maps from the built candidate', async ({ page }) => {
  const directory=join(process.cwd(),'.astro','browser-evidence'); mkdirSync(directory,{recursive:true});
  const observations: Record<string,unknown>={
    commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
    tree:execFileSync('git',['rev-parse','HEAD^{tree}'],{encoding:'utf8'}).trim(),
    reviewedSource:evidenceSourceRevision,browser:page.context().browser()?.version(),
  };
  for (const width of [390,1440]) {
    await page.setViewportSize({width,height:1000});
    for (const slug of pages) {
      await page.goto(`/concepts/${slug}/`); await page.evaluate(() => document.fonts.ready);
      await compareAll(page); await page.evaluate(() => scrollTo(0,0));
      observations[`${slug}-${width}`]=await readable(page);
      await page.screenshot({path:join(directory,`c02-${slug}-${width}.png`),fullPage:true});
    }
    await page.goto('/concepts/adrs/');
    for (const item of adrCases) {
      await page.locator('ca-decision-evidence').getByRole('button',{name:item.label,exact:true}).click();
      await page.locator('ca-decision-evidence').screenshot({path:join(directory,`c02-adr-${item.id}-${width}.png`)});
    }
    await page.goto('/concepts/checkpoints/');
    if(width===1440)for(let i=0;i<2;i++) await page.locator('.ca-checkpoint-map__plot').nth(i).screenshot({path:join(directory,`c02-checkpoint-map-${i+1}-${width}.png`)});
  }
  await page.setViewportSize({width:390,height:1000});await page.emulateMedia({forcedColors:'active'});
  await page.goto('/concepts/auditability/');await compareAll(page);await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:join(directory,'c02-auditability-forced-colors-390.png'),fullPage:true});
  writeFileSync(join(directory,'c02-decision-evidence.json'),JSON.stringify(observations,null,2));
});
