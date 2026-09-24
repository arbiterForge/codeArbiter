import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';

it('feature diagram shows ordered routed handoffs instead of command/skill/agent buckets', () => {
  const diagram = readFileSync('public/diagrams/lane-feature.svg', 'utf8');
  expect(diagram).toContain('data-map-node="batch"');
  expect(diagram).toContain('data-map-edge="entry:spec"');
  expect(diagram).toContain('data-map-edge="author:tdd"');
  expect(diagram).toContain('data-map-node="finish"');
  expect(diagram).toContain('not re-invoked');
});
