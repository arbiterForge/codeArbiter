import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { featureMap } from '../../scripts/execution-maps/model';

/** Inspect SVG geometry in the actual production browser, after all site CSS. */
test('arrowheads have a centred straight approach clear of every execution-map elbow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const records = [];
  const output = join(process.cwd(), '.astro/browser-evidence');
  mkdirSync(output, { recursive: true });
  for (const route of ['/concepts/', '/concepts/checkpoints/']) {
    await page.goto(route);
    await page.evaluate(() => document.fonts.ready);
    const chapters = route === '/concepts/' ? featureMap.chapters.map(c => c.id) : ['all'];
    for (const chapter of chapters) {
      if (chapter !== 'all') await page.locator(`[data-map-select="${chapter}"]`).click();
      const plots = page.locator('.ca-execution-map__plot:visible svg, .ca-checkpoint-map__plot:visible svg');
      expect(await plots.count()).toBeGreaterThan(0);
      for (const svg of await plots.all()) {
        const arrows = await svg.evaluate(root => Array.from(root.querySelectorAll<SVGPathElement>('path[data-map-edge]')).map(path => {
          const markerId = path.getAttribute('marker-end')!.match(/#([^)]*)/)![1];
          const marker = root.querySelector<SVGMarkerElement>(`#${markerId}`)!;
          const end = path.getPointAtLength(path.getTotalLength());
          const approach = path.getPointAtLength(path.getTotalLength() - 12);
          return { edge: path.dataset.mapEdge, units: marker.getAttribute('markerUnits'),
            width: marker.markerWidth.baseVal.value, refX: marker.refX.baseVal.value,
            refY: marker.refY.baseVal.value, end: { x: end.x, y: end.y },
            approach: { x: approach.x, y: approach.y } };
        }));
        for (const arrow of arrows) {
          expect(arrow.units).toBe('userSpaceOnUse');
          expect(arrow.width).toBe(9); expect(arrow.refX).toBe(9); expect(arrow.refY).toBe(4);
          expect(arrow.end.y).toBeCloseTo(arrow.approach.y, 2);
          expect(arrow.end.x - arrow.approach.x).toBeCloseTo(12, 2);
        }
        records.push({ route, chapter: await svg.getAttribute('data-execution-chapter'), arrows });
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      if (route === '/concepts/checkpoints/') await plots.last().screenshot({ path: join(output, 'execution-arrows-checkpoint.png') });
      if (chapter === 'define') await plots.first().screenshot({ path: join(output, 'execution-arrows-feature.png') });
    }
  }
  writeFileSync(join(output, 'execution-arrow-evidence.json'), JSON.stringify({
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    tree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim(), records,
  }, null, 2));
});
