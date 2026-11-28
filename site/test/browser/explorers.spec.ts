/// <reference lib="dom" />
/** explorers.spec.ts - the reference explorers: Hook Gates, the command matrix and the changelog. */
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const axe = (page: Page, selector: string) => new AxeBuilder({ page }).include(selector).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
/** Resolves once the page has not scrolled for ten animation frames in a row. */
const settle = (page: Page) =>
  page.evaluate(() => new Promise<void>((resolve) => {
    let last = window.scrollY;
    let still = 0;
    const tick = () => {
      still = window.scrollY === last ? still + 1 : 0;
      last = window.scrollY;
      if (still >= 10) resolve();
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }));

test.describe('Hook Gates explorer', () => {
  test('decodes the captured refusal to its gate and the line that printed it', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const explorer = page.locator('ca-gate-explorer');
    await explorer.locator('button[data-example]').first().click();
    const result = explorer.locator('[data-gate-result]');
    await expect(result).toContainText('Exact match');
    await expect(result.locator('.ca-gates__match-tag')).toHaveText('H-03');
    await expect(result.locator('a[href*="/plugins/ca/hooks/_bashguardlib.py#L"]')).toBeVisible();
    await expect(explorer.locator('.ca-gate[data-gate="H-03"]')).toHaveAttribute('data-match', '');
    await result.locator('a.ca-button').click();
    await expect(page).toHaveURL(/#h-03$/);
  });

  test('a gate ID this version does not print is named as unknown', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    await page.locator('#gate-decode-input').fill('BLOCKED [H-42]: something');
    await expect(page.locator('[data-gate-result]')).toContainText('H-42 is not a gate ID');
  });

  test('filters the gates by what they do and where they fire', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const explorer = page.locator('ca-gate-explorer');
    await explorer.getByRole('radio', { name: /^Reminds/ }).check();
    await expect(explorer.locator('[data-gate-count]')).toHaveText('8 of 22 gates');
    for (const tile of await explorer.locator('.ca-gates__board .ca-gate:visible').all()) await expect(tile).toHaveAttribute('data-kind', 'remind');
    await explorer.getByRole('radio', { name: 'Git backstop' }).check();
    await expect(explorer.locator('[data-gate-empty]')).toBeVisible();
    await explorer.getByRole('radio', { name: /^Blocks/ }).check();
    await expect(explorer.locator('[data-gate-count]')).toHaveText('5 of 22 gates');
  });

  test('every gate link lands on its entry', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const targets = await page.locator('ca-gate-explorer a[href^="#"]').evaluateAll((links) => [...new Set(links.map((link) => link.getAttribute('href')!.slice(1)))]);
    expect(targets.length).toBeGreaterThanOrEqual(22);
    const missing = await page.evaluate((ids) => ids.filter((id) => !document.getElementById(id)), targets);
    expect(missing).toEqual([]);
  });

  test('without JavaScript the map and the gate list stay, and the tools that need a script do not show', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto('/reference/hooks-gates/');
    await expect(page.locator('[data-gate-decoder]')).toBeHidden();
    await expect(page.locator('[data-gate-filters]')).toBeHidden();
    await expect(page.locator('.ca-gates__board .ca-gate')).toHaveCount(22);
    await expect(page.locator('.ca-gates__lane')).toHaveCount(4);
    await context.close();
  });

  test('passes automated accessibility checks and fits a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/reference/hooks-gates/');
    await page.locator('ca-gate-explorer button[data-example]').first().click();
    expect((await axe(page, 'ca-gate-explorer')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });

  test('a message two gates share names both, and the printed ID picks one', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const input = page.locator('#gate-decode-input');
    const result = page.locator('[data-gate-result]');
    await input.fill('No security-gate PASS is recorded for this staged candidate.');
    await expect(result.locator('.ca-gates__match-tag')).toHaveText(['H-09b', 'H-10b']);
    await expect(result).toContainText('print this text word for word');
    await expect(page.locator('.ca-gate[data-gate="H-10b"]')).toHaveAttribute('data-match', '');
    await input.fill('BLOCKED [H-10b]: No security-gate PASS is recorded for this staged candidate.');
    await expect(result.locator('.ca-gates__match-tag')).toHaveText(['H-10b']);
  });

  test('the same text printed in two files lists both call sites', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    await page.locator('#gate-decode-input').fill('BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr.');
    const source = page.locator('[data-gate-result] .ca-gates__match-source');
    await expect(source).toContainText('pre-write.py:');
    await expect(source).toContainText('pre-edit.py:');
  });

  test('a long pasted log, wrapped mid-word, decodes at once', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const line = 'REMINDER [H-12]: src/app.ts is governed by ADR-0007 (Keep exports synchronous). If this change contra\ndicts it, route to /ca:reconcile or /ca:adr — do not drift silently.\n';
    const elapsed = await page.evaluate((value) => {
      const input = document.querySelector<HTMLTextAreaElement>('#gate-decode-input')!;
      input.value = value;
      const started = performance.now();
      input.dispatchEvent(new Event('input'));
      return performance.now() - started;
    }, line.repeat(30).slice(0, 4000));
    expect(elapsed).toBeLessThan(250);
    await expect(page.locator('[data-gate-result] .ca-gates__match-how')).toHaveText('Exact match');
    await expect(page.locator('[data-gate-result] .ca-gates__match-tag')).toHaveText(['H-12']);
  });

  test('the map shows two paths of two steps, with the tools each script is registered for', async ({ page }) => {
    await page.goto('/reference/hooks-gates/');
    const paths = page.locator('.ca-gates__path');
    await expect(paths.locator('.ca-gates__path-title')).toHaveText(['A shell command', 'A file write or edit']);
    await expect(paths.nth(0).locator('.ca-gates__lane')).toHaveCount(2);
    await expect(paths.nth(1).locator('.ca-gates__lane')).toHaveCount(2);
    await expect(paths.nth(0)).toContainText('pre-bash.py for Bash and PowerShell');
    await expect(paths.nth(1)).toContainText('post-write-edit.py for Write and Edit');
    await expect(page.locator('ca-gate-explorer')).not.toContainText('four points in order');
  });
});

test.describe('Command matrix', () => {
  test('spells every command for every host and filters by host, level and word', async ({ page }) => {
    await page.goto('/reference/commands/');
    const matrix = page.locator('ca-command-matrix');
    await expect(matrix.locator('[data-matrix-row]')).toHaveCount(33);
    const feature = matrix.locator('[data-matrix-row]').filter({ has: page.locator('a', { hasText: /^feature$/ }) });
    await expect(feature.locator('td[data-host="codex"] code')).toHaveText('$ca-feature');
    await expect(feature.locator('td[data-host="pi"] code')).toHaveText('/ca-feature');
    await matrix.getByRole('radio', { name: /^Codex CLI/ }).check();
    const codexCount = await matrix.locator('[data-matrix-row]:visible').count();
    expect(codexCount).toBeLessThan(33);
    for (const row of await matrix.locator('[data-matrix-row]:visible').all()) await expect(row.locator('td[data-host="codex"] code')).toBeVisible();
    await matrix.getByRole('radio', { name: 'Every host' }).check();
    await page.locator('#matrix-find').fill('adr');
    await expect(matrix.locator('[data-matrix-count]')).toHaveText(/^\d+ of 33 commands$/);
    for (const row of await matrix.locator('[data-matrix-row]:visible').all()) expect((await row.textContent())!.toLowerCase()).toContain('adr');
  });

  test('copies a spelling and says so', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/reference/commands/');
    const button = page.locator('ca-command-matrix [data-copy="$ca-feature"]');
    await button.click();
    await expect(page.locator('[data-matrix-copied]')).toHaveText('Copied $ca-feature');
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('$ca-feature');
  });

  test('an alias names the command that replaces it', async ({ page }) => {
    await page.goto('/reference/commands/');
    const cleanup = page.locator('[data-matrix-row]').filter({ has: page.locator('a', { hasText: /^cleanup$/ }) });
    await expect(cleanup).toContainText('Now runs pr --cleanup');
  });

  test('passes automated accessibility checks and becomes cards on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/reference/commands/');
    expect((await axe(page, 'ca-command-matrix')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await expect(page.locator('ca-command-matrix thead')).toHaveCSS('position', 'absolute');
  });

  test('fits the page at desktop widths', async ({ page }) => {
    for (const width of [1152, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/reference/commands/');
      expect(await overflow(page), `${width}px`).toBeLessThanOrEqual(0);
    }
  });
});

test.describe('Changelog navigator', () => {
  test('finds a gate across the whole history and lights its releases in the timeline', async ({ page }) => {
    await page.goto('/changelog/');
    const nav = page.locator('ca-changelog-navigator');
    await page.locator('#history-find').fill('H-22');
    await expect(nav.locator('[data-history-count]')).toHaveText(/^\d+ of \d+ entries, in \d+ releases?$/);
    const lit = await nav.locator('[data-history-bar]:not([data-dim])').count();
    expect(lit).toBeGreaterThan(0);
    expect(lit).toBeLessThan(20);
    for (const item of await page.locator('.sl-markdown-content li:visible').all()) expect(await item.textContent()).toContain('H-22');
    await page.locator('#history-find').fill('');
    await expect(nav.locator('[data-history-bar][data-dim]')).toHaveCount(0);
  });

  test('filters by kind and jumps to a release', async ({ page }) => {
    await page.goto('/changelog/');
    const nav = page.locator('ca-changelog-navigator');
    await nav.getByRole('radio', { name: 'Security' }).check();
    await expect(nav.locator('[data-history-count]')).toHaveText(/^\d+ of \d+ entries/);
    await nav.getByRole('radio', { name: 'All' }).check();
    await page.locator('#history-jump').selectOption({ index: 3 });
    await expect(page).toHaveURL(/#\d+---\d{4}-\d{2}-\d{2}$/);
  });

  test('without JavaScript the timeline is links to releases and the filters do not show', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto('/changelog/');
    await expect(page.locator('[data-history-filters]')).toBeHidden();
    const bars = page.locator('[data-history-bar]');
    expect(await bars.count()).toBeGreaterThan(150);
    const missing = await bars.evaluateAll((links) => links.map((link) => link.getAttribute('href')!.slice(1)).filter((id) => !document.getElementById(id)));
    expect(missing).toEqual([]);
    await context.close();
  });

  test('passes automated accessibility checks and fits a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/changelog/');
    expect((await axe(page, 'ca-changelog-navigator')).violations).toEqual([]);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });

  test('a dimmed bar clears the filter, goes to its release and says so', async ({ page }) => {
    await page.goto('/changelog/');
    const nav = page.locator('ca-changelog-navigator');
    await page.locator('#history-find').fill('H-22');
    const dim = nav.locator('[data-history-bar][data-dim]').first();
    const id = (await dim.getAttribute('data-history-bar'))!;
    await dim.dispatchEvent('click');
    await expect(page).toHaveURL(new RegExp(`#${id}$`));
    await expect(page.locator(`[id="${id}"]`)).toBeVisible();
    await expect(nav.locator('[data-history-count]')).toContainText('Filters cleared to show');
    await expect(page.locator('#history-find')).toHaveValue('');
  });

  test('jumping to the release already shown scrolls back to it', async ({ page }) => {
    await page.goto('/changelog/');
    await page.locator('#history-jump').selectOption({ index: 3 });
    await expect(page).toHaveURL(/#.+$/);
    const heading = page.locator(`[id="${new URL(page.url()).hash.slice(1)}"]`);
    await expect(heading).toBeInViewport();
    // The site scrolls smoothly. A scroll the test starts while that animation runs can land off
    // target in Chrome, so wait for the first jump to come to rest. The test then starts from a
    // settled top, and only the second jump can bring the release back.
    await settle(page);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await settle(page);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(heading).not.toBeInViewport();
    await page.locator('#history-jump').selectOption({ index: 3 });
    await expect(heading).toBeInViewport();
  });

  test('print shows every entry even while a filter is on', async ({ page }) => {
    await page.goto('/changelog/');
    await page.locator('#history-find').fill('H-22');
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.sl-markdown-content li[hidden]').first()).toHaveCSS('display', 'list-item');
    await expect(page.locator('[data-history-filters]')).toBeHidden();
  });
});

test.describe('Explorer filters in forced colours', () => {
  for (const path of ['/reference/hooks-gates/', '/reference/commands/', '/changelog/']) {
    test(`the chosen filter keeps its label on ${path}`, async ({ page }) => {
      await page.emulateMedia({ forcedColors: 'active' });
      await page.goto(path);
      const chosen = page.locator('.ca-explorer__filters fieldset label:has(input:checked)').first();
      await expect(chosen).toBeVisible();
      await expect(chosen).toHaveCSS('forced-color-adjust', 'none');
    });
  }
});
