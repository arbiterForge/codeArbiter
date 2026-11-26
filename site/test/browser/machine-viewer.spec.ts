import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { loadMachine } from '../../scripts/machine/machine-model';

const route = '/concepts/machine/?debug';
const machine = loadMachine();

// Headless Chrome only offers WebGL through its software rasterizer; the flags apply to this file only.
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] } });

const stage = (page: Page) => page.locator('[data-machine-stage]');
const viewer = (page: Page) => page.evaluate(() => (window as unknown as { __machine?: { story: { active: boolean } } }).__machine);
const storyActive = (page: Page) => page.evaluate(() => (window as unknown as { __machine?: { story: { active: boolean } } }).__machine?.story.active ?? null);

async function running(page: Page) {
  await expect(stage(page)).toHaveAttribute('data-state', 'running', { timeout: 25_000 });
}

function watch(page: Page) {
  const offsite: string[] = [];
  const errors: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol.startsWith('http') && url.hostname !== '127.0.0.1') offsite.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  return { offsite, errors };
}

test.describe('codeArbiter as a machine: 3D viewer', () => {
  test('starts only when asked, from the site build, and plays nothing on its own', async ({ page }) => {
    const seen = watch(page);
    await page.goto(route);
    await expect(stage(page)).toHaveAttribute('data-state', 'idle');
    expect(await stage(page).evaluate((el) => el.shadowRoot)).toBeNull();
    await page.getByRole('button', { name: 'Start the 3D machine' }).click();
    await running(page);
    await expect(stage(page).locator('canvas')).toHaveCount(1);
    await page.waitForTimeout(2500);
    expect(await storyActive(page)).toBe(false);
    await stage(page).locator('#b-session').click();
    await expect.poll(() => storyActive(page)).toBe(true);
    await expect(stage(page).locator('#b-session')).toHaveAttribute('aria-pressed', 'true');
    expect(seen.offsite).toEqual([]);
    expect(seen.errors).toEqual([]);
  });

  test('plays a tour from its written description', async ({ page }) => {
    await page.goto(route);
    await page.locator('#tour-force-push summary').click();
    await page.locator('#tour-force-push [data-machine-route="tour-force-push"]').click();
    await running(page);
    await expect(stage(page).locator('#player')).toBeVisible();
    await expect(stage(page).locator('#pl-h')).toHaveText(machine.tours.find((tour) => tour.id === 'tour-force-push')!.steps[0].title);
  });

  test('prints the hook\'s own block message in the Guard lab', async ({ page }) => {
    await page.goto(route);
    await page.locator('#lab-guard [data-machine-route="lab-guard"]').click();
    await running(page);
    const lab = stage(page).locator('#lab');
    await lab.locator('[data-ex="git push --force origin feature/login"]').click();
    const shellGate = machine.gates['H-02'].sites.find((site) => !site.backstop)!;
    await expect(lab).toContainText(shellGate.message);
  });

  test('releases the viewer when it is closed and when the page is left', async ({ page }) => {
    const seen = watch(page);
    await page.goto(route);
    await page.getByRole('button', { name: 'Start the 3D machine' }).click();
    await running(page);
    await stage(page).locator('#b-close').click();
    await expect(stage(page)).toHaveAttribute('data-state', 'idle');
    await expect(stage(page).locator('canvas')).toHaveCount(0);
    expect(await viewer(page)).toBeUndefined();
    await expect(page.getByRole('button', { name: 'Start the 3D machine' })).toBeFocused();

    await page.getByRole('button', { name: 'Start the 3D machine' }).click();
    await running(page);
    await page.locator('.sidebar-content a', { hasText: 'Compare Workflow Routes' }).click();
    await expect(page).toHaveURL(/\/concepts\/workflow-routes\/$/);
    expect(await viewer(page)).toBeUndefined();
    await page.goBack();
    await expect(page).toHaveURL(/\/concepts\/machine\//);
    await page.getByRole('button', { name: 'Start the 3D machine' }).click();
    await running(page);
    expect(seen.errors).toEqual([]);
  });

  test('respects reduced motion, and its keys work only inside the viewer', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(route);
    await page.getByRole('button', { name: 'Start the 3D machine' }).focus();
    await page.keyboard.press('Enter');
    await running(page);
    await page.waitForTimeout(1500);
    expect(await storyActive(page)).toBe(false);
    await expect(stage(page).locator('#b-motion')).toHaveAttribute('aria-pressed', 'false');
    await stage(page).focus();
    await page.keyboard.press('t');
    await expect(stage(page).locator('#drawer')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(stage(page).locator('#drawer')).toBeHidden();
    await page.locator('h1').click();
    await page.keyboard.press('t');
    await expect(stage(page).locator('#drawer')).toBeHidden();
  });

  test('has no axe violations in the viewer and its panels', async ({ page }) => {
    await page.goto(route);
    await page.getByRole('button', { name: 'Start the 3D machine' }).click();
    await running(page);
    const scan = async (state: string) => {
      const result = await new AxeBuilder({ page }).include('[data-machine-stage]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      return result.violations.map((violation) => `${state} ${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).slice(0, 3).join(' | ')}`);
    };
    const violations: string[] = [];
    await stage(page).locator('#b-tours').click();
    violations.push(...await scan('tours'));
    await stage(page).locator('#b-labs').click();
    await stage(page).locator('#lab [data-lab="guard"]').click();
    violations.push(...await scan('guard lab'));
    await stage(page).locator('#lab [data-lab="tokens"]').click();
    violations.push(...await scan('tokens lab'));
    await stage(page).locator('#lab [data-act="close"]').click();
    await stage(page).locator('#b-session').click();
    await expect(stage(page).locator('.bubble')).toBeVisible({ timeout: 15_000 });
    violations.push(...await scan('example session'));
    expect(violations).toEqual([]);
  });
});
