import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { workflows, getWorkflow } from './workflows';
import { validateExecutionMap } from './model';
import { renderExecutionSvg, renderAlternativeMaps, chapterOffset } from './render';
import { auditDiagram } from '../diagram-audit';

const root = new URL('../../../', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), 'utf8');
const mapText = (id: string) => JSON.stringify(getWorkflow(id));
const ids = (id: string) => getWorkflow(id).map.chapters.flatMap(chapter => chapter.nodes.map(node => node.id));
const presentation = (id: string) => { const w = getWorkflow(id); return { kicker: `${id.toUpperCase()} • COMMANDS / SKILLS / AGENTS`, summary: w.summary, endpoint: w.endpoint }; };

describe('C04 distinct workflow routes', () => {
  it('covers every approved remaining lane and rejects unknown routes', () => {
    expect(workflows.map(w => w.id)).toEqual(['sprint', 'dependency', 'adr', 'release', 'greenfield', 'brownfield']);
    expect(new Set(workflows.map(w => w.asset)).size).toBe(workflows.length);
    expect(() => getWorkflow('invented')).toThrow(/Unknown workflow/);
  });
  for (const w of workflows) {
    it(`${w.id} has a connected, source-owned path and actual endpoint`, () => {
      expect(validateExecutionMap(w.map)).toEqual([]);
      for (const source of Object.values(w.map.sources)) {
        expect(read(source.path)).toContain(source.quote);
        expect(execFileSync('git', ['show', `${w.map.reviewedAt}:${source.path}`], { encoding: 'utf8' })).toContain(source.quote);
      }
      for (const note of w.notes) { expect(w.map.sources[note.source]).toBeDefined(); expect(note.detail.length).toBeGreaterThan(30); }
      expect(w.endpoint.length).toBeGreaterThan(20);
      expect(w.map.chapters[0].nodes[0].role).toBe('command');
    });
    it(`${w.id} retains continuous numbering and all nodes in a readable asset`, () => {
      const svg = renderExecutionSvg(w.map, presentation(w.id));
      expect(auditDiagram(svg, w.asset)).toEqual([]);
      let count = 0;
      w.map.chapters.forEach((chapter, index) => {
        expect(chapterOffset(w.map, index)).toBe(count);
        for (const node of chapter.nodes) { count++; expect(svg.split(`data-map-node="${node.id}"`)).toHaveLength(2); }
      });
      expect(svg).toContain(w.endpoint);
      expect(svg).not.toContain('<script'); expect(svg).not.toContain('<foreignObject');
      expect(svg).toContain('>Commands</text>'); expect(svg).toContain('>Skills</text>'); expect(svg).toContain('>Agents</text>');
    });
  }
  it('initialization alternatives remain separate, with no edge between their models', () => {
    const entries = ['greenfield', 'brownfield'].map(id => ({ map: getWorkflow(id).map, presentation: presentation(id) }));
    const svg = renderAlternativeMaps(entries);
    expect(auditDiagram(svg, 'lane-opt-in.svg')).toEqual([]);
    expect(svg).toContain('alternatives, not consecutive phases');
    expect(svg).toContain('data-execution-map="greenfield"'); expect(svg).toContain('data-execution-map="brownfield"');
    const allEdges = [...svg.matchAll(/data-map-edge="([^:]+):([^"]+)"/g)];
    allEdges.forEach(([, from, to]) => expect(from.split('-')[0]).toBe(to.split('-')[0]));
    expect(mapText('greenfield')).toContain('01-architecture-breakdown.md');
    expect(mapText('greenfield')).toContain('02-phased-build-plan.md');
    expect(mapText('greenfield')).toContain('03-task-backlog.md');
    expect(mapText('greenfield')).toContain('all three outputs are approved');
    expect(mapText('brownfield')).toContain('Six isolated');
    expect(mapText('brownfield')).toContain('does not invent');
    expect(mapText('brownfield')).toContain('conditional on real evidence');
  });
  it('sprint goes directly to the task engine and preserves initial-pair approval', () => {
    const map = getWorkflow('sprint').map;
    expect(ids('sprint').indexOf('sprint-approve')).toBeLessThan(ids('sprint').indexOf('sprint-engine'));
    expect(ids('sprint')).not.toContain('executing-plans');
    expect(mapText('sprint')).toContain('in a recoverable transaction');
    expect(mapText('sprint')).toContain('not re-invoked');
    expect(map.outcome).toContain('never merges');
    expect(mapText('sprint')).toContain('HTML'); expect(mapText('sprint')).toContain('farm');
  });
  it('dependency review returns before installation and invents no intermediate skill', () => {
    expect(ids('dependency')).toEqual(['dep-entry', 'dep-reviewer', 'dep-confirm', 'dep-change']);
    expect(getWorkflow('dependency').map.chapters.flatMap(chapter => chapter.nodes).some(node => node.role === 'skill')).toBe(false);
    expect(mapText('dependency')).toContain('orchestrator-enforced');
    expect(mapText('dependency')).toContain('one-time');
  });
  it('ADR acceptance binds the already-created source commit and is not a status query', () => {
    expect(ids('adr').indexOf('adr-source-commit')).toBeLessThan(ids('adr').indexOf('adr-binding'));
    expect(ids('adr').at(-1)).toBe('adr-binding-commit');
    expect(getWorkflow('adr').map.chapters.flatMap(c => c.nodes).some(node => node.title.startsWith('/ca:adr-status'))).toBe(false);
    expect(mapText('adr')).toContain('Remaining Proposed is valid');
    expect(mapText('adr')).toContain('Accepted/Planned does not prove implementation');
  });
  it('release has a mandatory PR stop before exact-head hosted tag composition', () => {
    const order = ids('release');
    expect(order.indexOf('release-pr')).toBeLessThan(order.indexOf('release-hosted'));
    expect(order.indexOf('release-hosted')).toBeLessThan(order.indexOf('release-tag'));
    expect(order.indexOf('release-tag')).toBeLessThan(order.indexOf('release-publish'));
    expect(order.at(-1)).toBe('release-receipt');
    expect(mapText('release')).toContain('CI success alone cannot');
    expect(mapText('release')).toContain('never the interactive checkout');
    expect(mapText('release')).toContain('closeout remains pending');
  });
});
