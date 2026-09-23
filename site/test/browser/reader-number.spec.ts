import { test, expect } from '@playwright/test';

for (const width of [320, 390]) {
  test(`reader-map numbers remain on one line at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    for (const slug of ['opt-in-a-repo', 'feature-lane', 'autonomous-sprints']) {
      await page.goto(`/guides/${slug}/`);
      await page.evaluate(() => document.fonts.ready);
      const numbers = page.locator('.ca-reader-journey__number');
      await expect(numbers).toHaveText(['01', '02', '03', '04']);
      for (const number of await numbers.all()) {
        const geometry = await number.evaluate(node => ({
          height: node.getBoundingClientRect().height,
          lineHeight: parseFloat(getComputedStyle(node).lineHeight),
        }));
        expect(geometry.height, `${slug}: ${await number.textContent()} wrapped`).toBeLessThanOrEqual(geometry.lineHeight + 1);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    }
  });
}
