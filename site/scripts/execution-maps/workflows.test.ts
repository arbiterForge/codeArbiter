import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { workflows, getWorkflow } from './workflows';
import { featureMap, validateExecutionMap } from './model';
import { renderExecutionSvg, renderAlternativeMaps, chapterOffset } from './render';
import { auditDiagram } from '../diagram-audit';

const root = new URL('../../../', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), 'utf8');
const mapText = (id: string) => JSON.stringify(getWorkflow(id));
const ids = (id: string) => getWorkflow(id).map.chapters.flatMap(chapter => chapter.nodes.map(node => node.id));
const presentation = (id: string) => { const w = getWorkflow(id); return { kicker: `${id.toUpperCase()} • COMMANDS / SKILLS / AGENTS`, summary: w.summary, endpoint: w.endpoint }; };

describe('C04 distinct workflow routes', () => {
  it('keeps historical map sources reachable from the inspected main history', () => {
    // Main's 9292293 commit was inspected before this correction. A fresh main
    // clone must retain the cited objects after the stacked branches are removed.
    const retainedMain = '929229354e3a15ae3002c82116b66c837ab43729';
    for (const revision of new Set(workflows.map(w => w.map.reviewedAt))) {
      execFileSync('git', ['merge-base', '--is-ancestor', revision, retainedMain]);
    }
  });

  it('binds relocated ADR quotes to historical evidence and the current owner', () => {
    const adr = getWorkflow('adr').map;
    expect(adr.reviewedAt).toBe('929229354e3a15ae3002c82116b66c837ab43729');
    for (const source of Object.values(adr.sources)) {
      expect(source.currentPath).toBe('core/surface/skills/decision-lifecycle/references/authoring.md');
      expect(read(source.currentPath!)).toContain(source.quote);
      expect(execFileSync('git', ['show', `${adr.reviewedAt}:${source.path}`], { encoding: 'utf8' })).toContain(source.quote);
    }
  });
  it('rejects invalid relocated paths while retaining historical source checks', () => {
    const malformed = structuredClone(getWorkflow('adr').map);
    malformed.sources.adr.currentPath = 'outside.md';
    expect(validateExecutionMap(malformed)).toContain('invalid current source anchor');
    const historical = structuredClone(getWorkflow('adr').map);
    historical.sources.adr.path = 'outside.md';
    expect(validateExecutionMap(historical)).toContain('invalid source anchor');
    const noRelocation = structuredClone(getWorkflow('adr').map);
    delete noRelocation.sources.adr.currentPath;
    expect(validateExecutionMap(noRelocation)).toEqual([]);
  });

  it('binds finishing reuse claims to actual historical and current procedure text', () => {
    for (const map of [featureMap, getWorkflow('sprint').map]) {
      const source = map.sources.finish;
      const currentQuote = source.currentQuote ?? source.quote;
      expect(source.quote).toMatch(/do not re-invoke|Do not load or re-invoke/);
      expect(currentQuote).toContain('execute the **Open-PR procedure**');
      expect(currentQuote).toContain('Do not load or re-invoke the PR command wrapper.');
      expect(read(source.path)).toContain(currentQuote);
      expect(execFileSync('git', ['show', `${map.reviewedAt}:${source.path}`], { encoding: 'utf8' })).toContain(source.quote);
      expect(currentQuote).not.toBe('MUST NOT auto-merge under `/sprint`');
    }
    const empty = structuredClone(getWorkflow('sprint').map);
    empty.sources.finish.currentQuote = '  ';
    expect(validateExecutionMap(empty)).toContain('invalid current source quote');
  });

  it('covers every approved remaining lane and rejects unknown routes', () => {
    expect(workflows.map(w => w.id)).toEqual(['sprint', 'dependency', 'adr', 'release', 'greenfield', 'brownfield']);
    expect(new Set(workflows.map(w => w.asset)).size).toBe(workflows.length);
    expect(() => getWorkflow('invented')).toThrow(/Unknown workflow/);
  });
  for (const w of workflows) {
    it(`${w.id} has a connected, source-owned path and actual endpoint`, () => {
      expect(validateExecutionMap(w.map)).toEqual([]);
      for (const source of Object.values(w.map.sources)) {
        expect(read(source.currentPath ?? source.path)).toContain(source.currentQuote ?? source.quote);
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
    for (const record of ['capability', 'component', 'phase', 'work-item']) expect(mapText('greenfield')).toContain(record);
    expect(mapText('greenfield')).toContain('confirms the records match their choices');
    expect(mapText('greenfield')).not.toContain('01-architecture-breakdown.md');
    const brownfield = getWorkflow('brownfield').map;
    const scouts = brownfield.chapters.flatMap(chapter => chapter.nodes).find(node => node.id === 'brown-scouts')!;
    const scoutSource = brownfield.sources.scouts;
    expect(scoutSource.quote).toContain('Dispatch six isolated `scout` subagents simultaneously.');
    expect(scoutSource.currentQuote).toContain('direct bounded inspection or optional scoped agents');
    expect(read(scoutSource.path)).toContain(scoutSource.currentQuote!);
    expect(brownfield.boundary).toContain('six logical categories');
    expect(brownfield.boundary).toContain('scoped refreshes cover only declared affected categories');
    expect(brownfield.boundary).toContain('Actual host permissions');
    expect(scouts.href).toBe('/reference/skills/context-creation/');
    expect(scouts.role).toBe('skill');
    expect(brownfield.chapters[0].edges.find(edge => edge.to === scouts.id)?.kind).toBe('sequence');
    expect(scouts.detail).toContain('Optional agents');
    expect(brownfield.alternatives.find(edge => edge.from === 'brown-scouts' && edge.to === 'brown-synthesis')?.detail)
      .toContain('exactly the affected categories for scoped refresh');
    for (const page of [
      'site/src/content/docs/concepts/workflow-routes.mdx',
      'site/src/content/docs/guides/understand-an-existing-project.md',
    ]) {
      const prose = read(page).replace(/\s+/g, ' ');
      expect(prose).toContain('six logical');
      expect(prose.toLowerCase()).toContain('scoped refresh');
      expect(prose).toContain('optional scoped agents');
    }
    expect(brownfield.sources.writeContext.currentQuote).toContain('No document approval receipt');
    expect(brownfield.sources.brownLock.currentQuote).toBe('Run `knowledge.py initialize`.');
    expect(mapText('brownfield')).toContain('does not invent');
    expect(mapText('brownfield')).toContain('conditional on real evidence');
    expect(brownfield.outcome).toContain('Material user-owned questions');
    expect(brownfield.outcome).toContain('other unknowns remain visible');
  });
  it('sprint proceeds under existing authorization and keeps progress separate from verification', () => {
    const map = getWorkflow('sprint').map;
    expect(ids('sprint').indexOf('sprint-approve')).toBeLessThan(ids('sprint').indexOf('sprint-engine'));
    expect(ids('sprint')).not.toContain('executing-plans');
    const nodes = map.chapters.flatMap(chapter => chapter.nodes);
    expect(nodes.find(node => node.id === 'sprint-approve')?.title).toContain('maintain the agreement');
    expect(nodes.find(node => node.id === 'sprint-author')?.role).toBe('skill');
    expect(nodes.find(node => node.id === 'sprint-tdd')?.conditional).toBe(true);
    expect(map.alternatives.find(edge => edge.from === 'sprint-author' && edge.to === 'sprint-proof')?.label)
      .toBe('concrete validation');
    expect(map.alternatives.find(edge => edge.from === 'sprint-approve' && edge.to === 'sprint-engine')?.label)
      .toBe('authorized work');
    expect(map.alternatives.find(edge => edge.from === 'sprint-proof' && edge.to === 'sprint-quality')?.kind)
      .toBe('dispatch');
    expect(map.alternatives.find(edge => edge.from === 'sprint-proof' && edge.to === 'sprint-accepted')?.kind)
      .toBe('sequence');
    expect(nodes.find(node => node.id === 'sprint-quality')?.conditional).toBe(true);
    expect(nodes.find(node => node.id === 'sprint-accepted')?.detail).toContain('do not certify');
    expect(map.sources.pair.quote).toContain('recoverable native transaction');
    expect(read(map.sources.pair.path)).toContain(map.sources.pair.currentQuote!);
    expect(mapText('sprint')).toContain('not re-invoked');
    expect(map.outcome).toContain('never infers merge');
    const finish=nodes.find(node => node.id === 'sprint-finish')!;
    expect(finish.detail).toContain('earlier same-scope merge grant');
    expect(finish.detail).toContain('exact-head checks and review');
    expect(finish.detail).toContain('Discard still needs named-branch confirmation');
    expect(getWorkflow('sprint').endpoint).toContain('prior same-scope grant');
    expect(mapText('sprint')).toContain('HTML'); expect(mapText('sprint')).toContain('farm');
  });
  it('current sprint advice preserves ancestry, bounded delivery and proportional checks', () => {
    const nodes = getWorkflow('sprint').map.chapters.flatMap(chapter => chapter.nodes);
    expect(nodes.find(node => node.id === 'sprint-engine')?.detail).toContain('full dependency ancestry');
    expect(nodes.find(node => node.id === 'sprint-engine')?.detail).toContain('independently blocked tasks');
    expect(nodes.find(node => node.id === 'sprint-author')?.detail).toContain('two attempts');
    expect(nodes.find(node => node.id === 'sprint-author')?.detail).toContain('advisory unknown observation');
    const verify=nodes.find(node => node.id === 'sprint-tdd')!.detail;
    expect(verify).toContain('regression RED/GREEN for fixes');
    expect(verify).toContain('criterion-focused checks for features');
    expect(verify).toContain('passing characterization baselines for refactors');
  });
  it('greenfield resumes saved answers and initializes structurally from records', () => {
    const nodes=getWorkflow('greenfield').map.chapters.flatMap(chapter=>chapter.nodes);
    const resume=nodes.find(node=>node.id==='green-resume')!.detail;
    expect(resume).toContain('Answered questions stay settled');
    expect(resume).not.toContain('first unfinished step');
    const populate=nodes.find(node=>node.id==='green-populate')!.detail;
    for(const operation of ['knowledge.py promote','decision-lifecycle','unknowns stay unknown','proposed and unrun'])
      expect(populate).toContain(operation);
    const initialize=nodes.find(node=>node.id==='green-lock')!.detail;
    expect(initialize).toContain('knowledge.py initialize');
    expect(initialize).toContain('Open questions do not prevent it');
    expect(mapText('greenfield')).not.toContain('all thirteen required outputs');
    expect(mapText('greenfield')).not.toContain('provenance stubs');
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
