import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { loadMachine } from '../../scripts/machine/machine-model';

const route = '/concepts/machine/';
const machine = loadMachine();
const lanes = Object.values(machine.parts).filter((part) => part.kind === 'Lane');

test.describe('codeArbiter as a machine: static reading path', () => {
  test('renders every part, lane, tour and scenario as plain HTML inside the docs shell', async ({ page }) => {
    const offsite: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.protocol.startsWith('http') && url.hostname !== '127.0.0.1') offsite.push(request.url());
    });
    await page.goto(route);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveText('codeArbiter as a Machine');
    await expect(page.locator('.sidebar-content a[aria-current="page"]')).toHaveText('codeArbiter as a Machine');
    await expect(page.locator('.ca-machine__part')).toHaveCount(Object.keys(machine.parts).length);
    await expect(page.locator('#machine-key')).toContainText(`checked against codeArbiter ${machine.version}`);
    await expect(page.locator('.ca-machine__tour')).toHaveCount(machine.tours.length + machine.faults.filter((fault) => !fault.ref).length);
    for (const lane of lanes) await expect(page.locator(`#part-ca-${lane.cmd} h4`)).toHaveText(`/ca:${lane.cmd}`);
    expect(offsite).toEqual([]);
  });

  test('shows the hooks\' own block messages in the traced example', async ({ page }) => {
    await page.goto(route);
    const outputs = page.locator('.ca-machine__trace .ca-machine__output');
    const shell = machine.gates['H-02'].sites.find((site) => !site.backstop)!;
    const backstop = machine.gates['H-02'].sites.find((site) => site.backstop)!;
    await expect(outputs.nth(0)).toHaveText(`BLOCKED [H-02]: ${shell.message}`);
    await expect(outputs.nth(1)).toHaveText(`BLOCKED [H-02]: ${backstop.message}`);
  });

  test('spells each lane per host and marks commands a host leaves out', async ({ page }) => {
    await page.goto(route);
    for (const host of machine.hosts) {
      for (const cmd of host.omits) {
        await expect(page.locator(`#part-ca-${cmd} .ca-machine__hosts div`, { hasText: host.label })).toContainText('Not available');
      }
    }
    await expect(page.locator('#part-ca-fix .ca-machine__hosts')).toContainText('$ca-fix');
  });

  test('opens a deep-linked part and keeps its details readable by keyboard', async ({ page }) => {
    await page.goto(`${route}#part-guard-bash`);
    const part = page.locator('#part-guard-bash');
    await expect(part).toBeInViewport();
    const summary = part.locator('summary');
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(part.locator('details')).toHaveAttribute('open', '');
    await expect(part.locator('.ca-machine__refs a[href$="/reference/hooks-gates/#h-02"]')).toBeVisible();
  });

  test('has no axe violations and no horizontal overflow on a narrow screen', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(route);
    const result = await new AxeBuilder({ page }).include('.ca-machine').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
