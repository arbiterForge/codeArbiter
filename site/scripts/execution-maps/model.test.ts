import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { featureMap, validateExecutionMap } from './model';
import { renderChapterSvg, renderExecutionSvg } from './render';
import { auditDiagram } from '../diagram-audit';

const root = new URL('../../../', import.meta.url);
describe('source-traced execution map', () => {
  it('has one connected feature path with role rows, not role buckets', () => {
    expect(validateExecutionMap(featureMap)).toEqual([]);
    expect(featureMap.chapters).toHaveLength(4);
    const nodes = featureMap.chapters.flatMap(chapter => chapter.nodes);
    expect(nodes[0]).toMatchObject({ id: 'entry', role: 'command' });
    expect(nodes.map(node => node.id)).toContain('tdd');
    expect(nodes.map(node => node.id)).toContain('checkpoint');
    expect(nodes.at(-1)?.id).toBe('pr-review');
    expect(featureMap.outcome).toContain('PR');
    expect(featureMap.alternatives.some(edge => edge.kind === 'repeat')).toBe(true);
    expect(featureMap.alternatives.some(edge => edge.kind === 'return')).toBe(true);
  });
  it('binds every handoff to an existing canonical source and reviewed excerpt', () => {
    for (const source of Object.values(featureMap.sources)) {
      expect(source.path).toMatch(/^core\/surface\//);
      expect(readFileSync(new URL(source.currentPath ?? source.path, root), 'utf8')).toContain(source.currentQuote ?? source.quote);
      expect(execFileSync('git', ['show', `${featureMap.reviewedAt}:${source.path}`], { cwd: root, encoding: 'utf8' })).toContain(source.quote);
    }
    for (const chapter of featureMap.chapters) {
      for (const node of chapter.nodes) expect(featureMap.sources[node.source]).toBeDefined();
      for (const edge of chapter.edges) expect(featureMap.sources[edge.source]).toBeDefined();
    }
    for (const edge of featureMap.alternatives) expect(featureMap.sources[edge.source]).toBeDefined();
  });
  it('teaches current authorized progress, proportional verification and real delivery boundaries', () => {
    expect(featureMap.reviewedAt).toBe('a9f63fc481385680987f2ccbecede82603f011eb');
    const text = JSON.stringify(featureMap);
    for (const phrase of ['direct implementation', 'characterization', 'advisory', 'DONE', 'base-to-HEAD', 'user-requested pause']) expect(text).toContain(phrase);
    expect(text).not.toMatch(/Historical attended|fresh author|Wait for acknowledgement|scope acceptance through|current context ticket|Missing obligation returns to red/);
    const author = featureMap.chapters.flatMap(chapter => chapter.nodes).find(node => node.id === 'author');
    expect(author?.conditional).toBe(true);
  });
  it('rejects duplicate IDs, orphan edges, missing owners and lost outcomes', () => {
    const copy = () => structuredClone(featureMap);
    const duplicate = copy(); duplicate.chapters[1].nodes[0].id = 'entry';
    expect(validateExecutionMap(duplicate).join(' ')).toContain('duplicate');
    const orphan = copy(); orphan.chapters[0].edges[0].to = 'missing';
    expect(validateExecutionMap(orphan).join(' ')).toContain('unknown');
    const owner = copy(); owner.chapters[0].nodes[0].source = 'missing';
    expect(validateExecutionMap(owner).join(' ')).toContain('owner');
    const disconnected = copy(); disconnected.alternatives = [];
    expect(validateExecutionMap(disconnected).join(' ')).toContain('disconnected');
    const outcome = copy(); outcome.outcome = '';
    expect(validateExecutionMap(outcome).join(' ')).toContain('outcome');
  });
  it('preserves the caller return and avoids reinvoking the PR command', () => {
    expect(featureMap.chapters[3].nodes.find(node => node.id === 'pr-contract')?.detail)
      .toContain('not re-invoked');
    expect(featureMap.alternatives.find(edge => edge.to === 'task-select')?.detail).toContain('scope');
    expect(featureMap.chapters.flatMap(chapter => chapter.nodes).find(node => node.id === 'tdd')?.checks).toHaveLength(6);
  });
  it('renders every node and directed edge once per diagram, using three role rows', () => {
    const svg = renderExecutionSvg(featureMap);
    expect(auditDiagram(svg, 'lane-feature.svg')).toEqual([]);
    for (const chapter of featureMap.chapters) {
      for (const node of chapter.nodes) expect(svg.split(`data-map-node="${node.id}"`)).toHaveLength(2);
      for (const edge of chapter.edges) expect(svg).toContain(`data-map-edge="${edge.from}:${edge.to}"`);
      const part = renderChapterSvg(chapter, `test-${chapter.id}`);
      for (const role of ['Commands', 'Skills', 'Agents']) expect(part).toContain(`>${role}</text>`);
    }
    expect(svg).not.toContain('<foreignObject');
    expect(svg).not.toContain('<script');
  });
  it('publishes the same current feature map in the downloadable diagram', () => {
    const asset = readFileSync(new URL('site/public/diagrams/lane-feature.svg', root), 'utf8');
    expect(asset.replace(/\r\n/g, '\n')).toBe(renderExecutionSvg(featureMap));
    expect(asset).not.toMatch(/Fresh author|Human checkpoint|scope acceptance/);
  });
  it('escapes authored diagram text and rejects markup-like IDs', () => {
    const altered = structuredClone(featureMap.chapters[0]);
    altered.nodes[0].label = ['<script>alert(1)</script>'];
    expect(renderChapterSvg(altered, 'safe')).not.toContain('<script>');
    const invalid = structuredClone(featureMap); invalid.chapters[0].nodes[0].id = '<bad>';
    expect(validateExecutionMap(invalid).length).toBeGreaterThan(0);
  });
});
