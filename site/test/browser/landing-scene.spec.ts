/// <reference lib="dom" />
/** landing-scene.spec.ts - the landing's machine trace, machine section and host picker, in a real browser. */
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const scene = '[data-scene="hero-trace"]';
const step = (page: import('@playwright/test').Page) => page.locator(scene).getAttribute('data-step');

test('the hero trace plays on its own with a working pause control', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  const toggle = root.locator('[data-scene-toggle]');
  await expect(toggle).toHaveText(/Pause/);
  await expect.poll(async () => Number(await step(page)), { timeout: 9000 }).toBeGreaterThan(0);
  await toggle.click();
  await expect(toggle).toHaveText(/Play/);
  const held = await step(page);
  await page.waitForTimeout(3500);
  expect(await step(page)).toBe(held);
});

test('pausing while the token travels stops it at once and settles the step', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  const token = root.locator('.ca-scene__svg--wide [data-token]');
  // Wait for the token to be on a handoff, then pause in the middle of its travel and read
  // the result in the same task, before any animation frame could run.
  await expect(token).toHaveAttribute('data-on', 'true', { timeout: 9000 });
  const atPause = await root.evaluate((el) => {
    el.querySelector<HTMLButtonElement>('[data-scene-toggle]')!.click();
    const focus = el.querySelector('.ca-scene__svg--wide [data-focus]');
    return {
      moving: el.querySelector('.ca-scene__svg--wide [data-token]')!.hasAttribute('data-on'),
      settled: Boolean(focus?.getAttribute('data-verdict')),
    };
  });
  expect(atPause).toEqual({ moving: false, settled: true });
  const held = await step(page);
  const before = await token.getAttribute('transform');
  for (let sample = 0; sample < 6; sample += 1) {
    await page.waitForTimeout(250);
    expect(await token.getAttribute('data-on')).toBeNull();
    expect(await token.getAttribute('transform')).toBe(before);
  }
  expect(await step(page)).toBe(held);
});

test('keyboard steps the scene and hands control to the reader', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await root.locator('[data-scene-go="3"]').focus();
  await page.keyboard.press('Enter');
  await expect(root).toHaveAttribute('data-step', '3');
  await expect(root.locator('[data-scene-toggle]')).toHaveText(/Play/);
  await expect(root.locator('.ca-scene__step[aria-current="step"]')).toContainText('BLOCKED [H-03]');
  await expect(root.locator('.ca-scene__svg--wide [data-el="guard"]')).toHaveAttribute('data-verdict', 'block');
  await page.keyboard.press('ArrowRight');
  await expect(root).toHaveAttribute('data-step', '4');
  await expect(root.locator('[data-scene-go="4"]')).toBeFocused();
  await page.keyboard.press('Home');
  await expect(root).toHaveAttribute('data-step', '0');
  await page.waitForTimeout(3200);
  await expect(root).toHaveAttribute('data-step', '0');
});

test('reduced motion keeps the complete, still scene', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).not.toHaveAttribute('data-js', /.*/);
  await expect(root.locator('[data-scene-controls]')).toBeHidden();
  const steps = root.locator('.ca-scene__step');
  await expect(steps).toHaveCount(7);
  for (const item of await steps.all()) await expect(item).toBeVisible();
  await expect(root.locator('[data-state]')).toHaveCount(0);
});

test('without JavaScript the scene reads as the full ordered steps', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root.locator('.ca-scene__step')).toHaveCount(7);
  await expect(root.locator('.ca-scene__step').nth(3)).toContainText("BLOCKED [H-03]: 'git add -A'");
  await expect(root.locator('[data-scene-controls]')).toBeHidden();
  await expect(root.locator('.ca-scene__svg--wide')).toBeVisible();
  await context.close();
});

test('phones get the tall composition without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root.locator('.ca-scene__svg--wide')).toBeHidden();
  await expect(root.locator('.ca-scene__svg--tall')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
  await root.locator('[data-scene-go="3"]').click();
  await expect(root.locator('.ca-scene__step[aria-current="step"] .ca-scene__terminal')).toBeVisible();
});

test('the host picker spells a command in every host and names an omission', async ({ page }) => {
  await page.goto('/');
  const hosts = page.locator('[data-host-switch]');
  await hosts.getByRole('button', { name: 'statusline', exact: true }).click();
  await expect(hosts.locator('[data-host="claude"] code')).toHaveText('/ca:statusline');
  await expect(hosts.locator('[data-host="claude"] code')).not.toHaveAttribute('data-omitted', /.*/);
  await expect(hosts.locator('[data-host="codex"] code')).toHaveAttribute('data-omitted', '');
  await expect(hosts.locator('[data-host="codex"]')).toContainText('Not available on Codex');
  await hosts.getByRole('button', { name: 'pr', exact: true }).click();
  await expect(hosts.locator('[data-host="codex"] code')).toHaveText('$ca-pr');
  await expect(hosts.locator('[data-host="pi"] code')).toHaveText('/ca-pr');
  await expect(hosts.locator('[data-host="codex"] .ca-host__omitted')).toBeHidden();
});

test('the machine section opens the 3D machine page', async ({ page }) => {
  await page.goto('/');
  const poster = page.locator('.ca-machine-teaser__poster');
  await expect(poster.locator('img')).toHaveAttribute('alt', /3D machine/);
  await poster.click();
  await expect(page).toHaveURL(/\/concepts\/machine\/$/);
});

test('play stops while less than a third of the hero is on screen', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await page.evaluate(() => {
    const box = document.querySelector('[data-scene="hero-trace"]')!.getBoundingClientRect();
    window.scrollTo(0, window.scrollY + box.top + box.height * 0.8);
  });
  await expect(root.locator('[data-scene-toggle]')).toHaveText(/Play/);
  const held = await step(page);
  await page.waitForTimeout(5500);
  expect(await step(page)).toBe(held);
});

test('forced colours keep the running scene readable', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await root.locator('[data-scene-go="3"]').click();
  const colours = await page.evaluate(() => {
    const ink = getComputedStyle(document.body).color;
    const note = document.querySelector('.ca-scene__svg--wide [data-el="n-block"] text')!;
    const box = document.querySelector('.ca-scene__svg--wide [data-el="guard"] .ca-scene__box')!;
    const canvas = getComputedStyle(document.body).backgroundColor;
    return { ink, note: getComputedStyle(note).fill, box: getComputedStyle(box).fill, canvas };
  });
  expect(colours.note).toBe(colours.ink);
  expect(colours.box).toBe(colours.canvas);
  await expect(root.locator('.ca-scene__step[aria-current="step"] .ca-scene__terminal')).toBeVisible();
});

test('turning on reduced motion mid-play returns the still scene', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(root).not.toHaveAttribute('data-js', /.*/);
  await expect(root.locator('[data-scene-controls]')).toBeHidden();
  await expect(root.locator('[data-token][data-on]')).toHaveCount(0);
  await expect(root.locator('[data-state]')).toHaveCount(0);
});

test('print shows every step and every note, without the token', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  await page.emulateMedia({ media: 'print' });
  for (const item of await root.locator('.ca-scene__step').all()) await expect(item).toHaveCSS('opacity', '1');
  await expect(root.locator('.ca-scene__svg--wide [data-el="n-block"] text')).toHaveCSS('opacity', '1');
  await expect(root.locator('.ca-scene__svg--wide [data-token]').first()).toBeHidden();
});

test('print draws every handoff in full, even one that was mid-draw on screen', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const root = page.locator(scene);
  await expect(root).toHaveAttribute('data-js', 'on');
  // Step 3 (the hook) draws a handoff: it is the active edge, dashed out until its draw
  // animation runs.
  await root.locator('[data-scene-go="2"]').click();
  const active = root.locator('.ca-scene__svg--wide .ca-scene__edge[data-state="active"]');
  await expect(active).toHaveCount(1);
  await page.emulateMedia({ media: 'print' });
  await expect(active).toHaveCSS('stroke-dashoffset', '0px');
  for (const edge of await root.locator('.ca-scene__svg--wide .ca-scene__edge').all()) {
    await expect(edge).toHaveCSS('opacity', '1');
    await expect(edge).toHaveCSS('stroke-dasharray', 'none');
  }
});

test('the landing passes automated accessibility checks', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.locator(scene)).toHaveAttribute('data-js', 'on');
  const result = await new AxeBuilder({ page }).include('.ca-landing').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`)).toEqual([]);
});

test('outcome drawings assemble with page scrolling, and stay finished under reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const podAt = async (offset: number) =>
    page.evaluate((delta) => {
      const pod = document.querySelector<SVGGElement>('.ca-vignette__pod')!;
      const card = pod.closest('.ca-feature')!;
      scrollTo({ top: card.getBoundingClientRect().top + scrollY + delta, behavior: 'instant' });
      return new Promise<number>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(Math.round(new DOMMatrix(getComputedStyle(pod).transform).e)))));
    }, offset);
  await page.goto('/');
  // The card's top at the bottom edge of the viewport: the drawing has not started.
  expect(await podAt(-900)).toBe(0);
  // Well inside the viewport: the drawing is finished.
  expect(await podAt(-300)).toBe(118);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  expect(await podAt(-900)).toBe(118);
});
