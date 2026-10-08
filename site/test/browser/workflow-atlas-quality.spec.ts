import { expect, test, type Page } from '@playwright/test';
import type { Atlas } from '../../scripts/execution-maps/atlas-model';

const route = '/concepts/workflow-routes/';
const root = (page: Page) => page.locator('ca-workflow-atlas');
const settle = (page: Page) => page.evaluate(() => new Promise<void>(resolve => {
  requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
}));

test('permalinks keep DOM-derived identities in the fragment, never the URL scheme or HTML', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(route);
  await expect(root(page)).toHaveAttribute('data-active-view', 'all-routes');

  // Mutate the same DOM JSON source identified by CodeQL before reconnecting.
  // This is an adversarial input fixture, not a claim that such IDs are admitted
  // by the build-time validator. No script or external URL is executed.
  const attack = 'javascript:alert(1)/"><img id="atlas-injected" src=x onerror=alert(1)>?q=&';
  const result = await root(page).evaluate((element, value) => {
    const parent = element.parentElement!;
    const data = element.querySelector('[data-atlas-data]')!;
    const model = JSON.parse(data.textContent!) as Atlas;
    const previous = model.views[0].id;
    element.remove();
    model.views[0].id = value;
    data.textContent = JSON.stringify(model);
    for (const kind of ['svg-template', 'view-inspector']) {
      const template = [...element.querySelectorAll('template')]
        .find(candidate => candidate.getAttribute(`data-${kind}`) === previous)!;
      template.setAttribute(`data-${kind}`, value);
    }
    parent.append(element);
    const link = element.querySelector<HTMLAnchorElement>('[data-atlas-permalink]')!;
    const current = new URL(location.href);
    const target = new URL(link.href);
    return {
      sameDocument: ['protocol', 'origin', 'pathname', 'search'].every(key =>
        Reflect.get(current, key) === Reflect.get(target, key)),
      fragment: decodeURIComponent(target.hash),
      injected: element.querySelectorAll('#atlas-injected').length,
      label: link.textContent,
    };
  }, attack);

  expect(result).toEqual({
    sameDocument: true,
    fragment: '#atlas-view-' + attack,
    injected: 0,
    label: 'Link to view',
  });
  expect(errors).toEqual([]);
});

test('unowned headings and invalid route suffixes cannot change atlas selection', async ({ page }) => {
  await page.goto(route + '#atlas-view-context-layers~feature');
  const atlas = root(page);
  await expect(atlas).toHaveAttribute('data-route', 'feature');
  for (const fragment of [
    '#feature', '#release', '#context-layers', '#constructor',
    '#atlas-view-constructor', '#atlas-view-context-layers~',
    '#atlas-view-context-layers~missing', '#atlas-view-context-layers~feature~fix',
    '#atlas-node-context-layers-c-green~missing', '#%E0%A4%A',
  ]) {
    await page.evaluate(hash => {
      history.replaceState(history.state, '', hash);
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    }, fragment);
    await settle(page);
    await expect(atlas).toHaveAttribute('data-active-view', 'context-layers');
    await expect(atlas).toHaveAttribute('data-route', 'feature');
  }
  // Historical atlas-prefixed aliases still work; ordinary page headings do not.
  await page.goto(route + '#atlas-view-release');
  await expect(atlas).toHaveAttribute('data-active-view', 'review-delivery');
  await page.goto(route + '#atlas-text-context-layers');
  await expect(atlas.locator('.reading-wrap')).toHaveAttribute('open');
  await expect(atlas.locator('#atlas-text-context-layers')).toBeVisible();
});

test('node links retain the independent trace in native and generated offline editions', async ({ page }) => {
  await page.goto(route);
  const offline = await root(page).locator('.atlas-downloads a').first().getAttribute('href');
  expect(offline).toMatch(/\/workflow-atlas\/[0-9a-f]{40}\/atlas.html$/);
  for (const destination of [route, offline!]) {
    await page.goto(destination + '#atlas-view-context-layers~feature');
    const atlas = root(page);
    const node = atlas.locator('[data-atlas-stage] [data-node="c-green"]');
    await expect(atlas).toHaveAttribute('data-route', 'feature');
    await node.focus();
    await page.keyboard.press('Enter');
    await atlas.locator('[data-atlas-permalink]').click();
    await expect(page).toHaveURL(/#atlas-node-context-layers-c-green~feature$/);
    await page.reload();
    await expect(atlas).toHaveAttribute('data-selected-node', 'c-green');
    await expect(atlas).toHaveAttribute('data-route', 'feature');
    await expect(atlas.locator('[data-atlas-select]')).toHaveValue('feature');
    await expect(atlas.locator('[data-atlas-stage] .dim').first()).toBeVisible();

    // A previously shared node-only URL keeps its original no-highlight meaning.
    await page.goto(destination + '#atlas-node-context-layers-c-green');
    await expect(atlas).toHaveAttribute('data-selected-node', 'c-green');
    await expect(atlas).toHaveAttribute('data-route', '');
  }
});

test('new reading choices supersede queued navigation and automatic fitting', async ({ page }) => {
  await page.addInitScript(() => {
    const NativeObserver = window.ResizeObserver;
    window.ResizeObserver = class extends NativeObserver {
      constructor(private notify: ResizeObserverCallback) {
        super(notify);
      }
      observe(target: Element, options?: ResizeObserverOptions): void {
        super.observe(target, options);
        if (target.matches('[data-atlas-stage]')) {
          Reflect.set(window, 'atlasTestResize', () => this.notify([], this));
        }
      }
    };
  });
  await page.goto(route);
  const atlas = root(page);
  await expect(atlas).toHaveAttribute('data-active-view', 'all-routes');
  await settle(page);
  await atlas.locator('[data-action="fit-width"]').click();
  await atlas.evaluate(element => {
    const notify = Reflect.get(window, 'atlasTestResize') as (() => void) | undefined;
    if (!notify) throw new Error('Atlas resize observer was not registered');
    notify();
    notify();
    element.querySelector<HTMLButtonElement>('[data-action="read-size"]')!.click();
  });
  await settle(page);
  await expect(atlas).toHaveAttribute('data-zoom', '0.85');

  await atlas.evaluate(element => {
    history.replaceState(history.state, '', '#atlas-node-context-layers-c-green');
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    element.querySelector<HTMLButtonElement>('[data-atlas-view="review-delivery"]')!.click();
    element.querySelector<HTMLButtonElement>('[data-action="fit-all"]')!.click();
  });
  await settle(page);
  await expect(atlas).toHaveAttribute('data-active-view', 'review-delivery');
  await expect(atlas).toHaveAttribute('data-selected-node', '');
  expect(Number(await atlas.getAttribute('data-zoom'))).toBeLessThan(0.85);
});

test('reconnecting clears stale controls and tears down pending export work', async ({ page }) => {
  await page.addInitScript(() => {
    const create = URL.createObjectURL.bind(URL);
    const revoke = URL.revokeObjectURL.bind(URL);
    const pending = new Set<string>();
    Reflect.set(window, 'atlasTestObjectUrls', pending);
    URL.createObjectURL = object => {
      const url = create(object);
      pending.add(url);
      return url;
    };
    URL.revokeObjectURL = url => {
      pending.delete(url);
      revoke(url);
    };
  });
  await page.goto(route);
  const atlas = root(page);
  await expect(atlas).toHaveAttribute('data-active-view', 'all-routes');
  await atlas.locator('[data-atlas-select]').selectOption('fix');
  await atlas.evaluate(element => {
    history.replaceState(history.state, '', '#unrelated-page-heading');
    element.querySelector<HTMLButtonElement>('[data-action="export"]')!.click();
    const pending = Reflect.get(window, 'atlasTestObjectUrls') as Set<string>;
    if (pending.size !== 1) throw new Error('Expected one pending SVG export');
    const parent = element.parentElement!;
    element.remove();
    if (Number(pending.size) !== 0) throw new Error('Disconnected atlas retained an object URL');
    parent.append(element);
  });
  await settle(page);
  await expect(atlas).toHaveAttribute('data-route', '');
  await expect(atlas.locator('[data-atlas-select]')).toHaveValue('');
  await expect(atlas.locator('[data-atlas-stage] .dim')).toHaveCount(0);
  await expect(atlas.locator('[data-atlas-stage]')).not.toHaveClass(/dragging/);
  await atlas.locator('[data-action="read-size"]').click();
  await atlas.locator('[data-action="plus"]').click();
  // A reconnect must not leave a duplicate listener applying zoom twice.
  expect(Number(await atlas.getAttribute('data-zoom'))).toBeCloseTo(0.85 * 1.22, 5);
});
