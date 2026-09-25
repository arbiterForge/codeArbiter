import { describe, expect, it } from 'vitest';
import { featureMap } from '../../scripts/execution-maps/model';
import { checkpointMap } from '../../scripts/execution-maps/checkpoint';
import { workflows } from '../../scripts/execution-maps/workflows';
import { renderChapterSvg } from '../../scripts/execution-maps/render';

/** Verify the generated geometry, not just a screenshot's page-width bounds. */
describe('execution-map arrow approaches', () => {
  for (const map of [featureMap, checkpointMap, ...workflows.map(workflow => workflow.map)]) {
    for (const chapter of map.chapters) it(`${map.id}/${chapter.id}: joins the arrow at its centre behind the tip`, () => {
      const svg = renderChapterSvg(chapter, `test-${map.id}-${chapter.id}`);
      const marker = svg.match(/<marker\b([^>]+)>/)?.[1] ?? '';
      expect(marker).toContain('markerUnits="userSpaceOnUse"');
      expect(marker).toContain('viewBox="0 0 9 8"');
      expect(marker).toContain('refX="9"');
      expect(marker).toContain('refY="4"');
      expect(marker).toContain('orient="auto"');
      expect(svg).toContain('d="M0 0L9 4L0 8Z"');
      const paths = [...svg.matchAll(/<path data-map-edge="([^"]+)"[^>]+ d="M([\d.]+) ([\d.]+)H([\d.]+)V([\d.]+)H([\d.]+)"/g)];
      expect(paths).toHaveLength(chapter.edges.length);
      for (const [, edge, x1, , elbow, , tip] of paths) {
        // The straight stem must reach behind the complete 9-unit marker,
        // leaving visible separation from its vertical elbow.
        expect(Number(tip) - Number(elbow), edge).toBeGreaterThanOrEqual(13);
        expect(Number(elbow) - Number(x1), edge).toBeGreaterThanOrEqual(4);
        const target = edge.split(':')[1];
        const x = svg.match(new RegExp(`data-map-node="${target}"[\\s\\S]*?<rect x="([\\d.]+)"`))?.[1];
        expect(x, edge).toBeDefined();
        expect(Number(x) - Number(tip), edge).toBeCloseTo(2, 6);
      }
    });
  }
});
