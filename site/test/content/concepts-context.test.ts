import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import capture from '../../src/data/context-examples.json';
import { GET } from '../../src/pages/examples/context-observations.json';

const read = (path: string) => readFileSync(path, 'utf8');
const source = (path: string) => read(`../${path}`);
const page = (slug: string) => read(`src/content/docs/concepts/${slug}.mdx`);
const old = (slug: string) => execFileSync('git', ['show', `${capture.source_revision}:site/src/content/docs/concepts/${slug}.md`], { encoding: 'utf8' });

describe('C03 actual helper observations', () => {
  it('reproduces the complete capture with native helpers and real Git hashes', () => {
    expect(execFileSync('python3', ['scripts/capture-context-examples.py', '--check'], { encoding: 'utf8', timeout: 20000 }))
      .toContain('matches exact sources');
  });
  it('binds inspected helpers to the exact source and publishes the same data once', async () => {
    for (const [path, hash] of Object.entries(capture.source_sha256)) {
      expect(createHash('sha256').update(readFileSync(`../${path}`)).digest('hex')).toBe(hash);
      const baseline = execFileSync('git', ['show', `${capture.source_revision}:${path}`]);
      expect(createHash('sha256').update(baseline).digest('hex')).toBe(hash);
    }
    const result = GET();
    expect(result.headers.get('Content-Type')).toContain('application/json');
    expect(await result.json()).toEqual(capture);
    expect(capture.evidence_kind).toBe('disposable-helper-observation');
    expect(capture.boundary).toContain('not an installed-host run');
  });
  it('composes all four tiers before bounding output rather than picking one winner', () => {
    const overlap = capture.cases.find(item => item.id === 'overlap')!;
    expect(overlap.candidate_pointers.map(pointer => pointer.tier)).toEqual(['security-controls', 'decisions', 'specs', 'standards']);
    for (const pointer of overlap.candidate_pointers) expect(overlap.emitted).toContain(pointer.text);
    expect(overlap.estimated_tokens).toBeLessThanOrEqual(capture.budget.limit);
    expect(overlap.hash_calls).toBe(1);
    expect(overlap.repeated_emitted).toBe(''); expect(overlap.repeat_hash_calls).toBe(0);
  });
  it('suppresses a now-false claim while keeping drift reporting distinct', () => {
    const fresh = capture.cases.find(item => item.id === 'fresh')!;
    const changed = capture.cases.find(item => item.id === 'changed')!;
    expect(fresh.emitted).toContain('declares module syntax');
    expect(changed.emitted).toBe(''); expect(changed.candidate_pointers).toEqual([]);
    expect(capture.drift_after_change).toEqual({ 'tech-stack': [{ path: 'package.json', kind: 'changed' }] });
    expect(capture.provenance_records['tech-stack'].entries[0].hash).not.toBe(capture.changed_source_hashes['package.json']);
  });
  it('retains early silent paths and the estimated pointer-only budget', () => {
    expect(capture.cases.find(item => item.id === 'unmapped')).toMatchObject({ emitted: '', hash_calls: 0 });
    expect(capture.self_read).toEqual({ emitted: '', hash_calls: 0 });
    expect(capture.budget.estimated_tokens).toBeLessThanOrEqual(150);
    expect(capture.budget.proxy).toBe('ceil(character_count / 4)');
    expect(capture.budget.emitted).toContain('Review this governing decision');
    expect(capture.budget.emitted.endsWith('…')).toBe(true);
  });
});

describe('C03 teaching and historical boundaries', () => {
  it('retains each former public heading through the concept source moves', () => {
    for (const slug of ['provenance-drift', 'jit-context-injection', 'persona-and-context']) {
      for (const heading of old(slug).match(/^## .+$/gm) ?? []) expect(page(slug)).toContain(heading);
    }
    for (const slug of ['persona-research-basis', 'hardening-history']) {
      for (const heading of old(slug).match(/^## .+$/gm) ?? []) expect(read(`src/content/docs/concepts/${slug}.md`)).toContain(heading);
    }
  });
  it('keeps advisory read behavior distinct from typed execution authority', () => {
    const jit = page('jit-context-injection');
    for (const phrase of ['ordered collection', 'not a first-match-only switch', 'ceil(character_count / 4)', 'deduplication epoch', 'diagnostic is not an approved-spec pointer', 'must stop']) expect(jit).toContain(phrase);
    expect(source('core/pysrc/pre-read.py')).toContain('except Exception');
    expect(source('core/pysrc/_readinjectlib.py')).toContain('authority_verified');
    expect(jit).toContain("does not parse that document into a complete security map");
  });
  it('does not promise universal provenance or silently convert missing data to fresh', () => {
    const provenance = page('provenance-drift');
    for (const phrase of ['drift_trigger', 'before', 'missing', 'interview', 'defer', 'silence']) expect(provenance.toLowerCase()).toContain(phrase.toLowerCase());
    const curated = read('src/curated/commands/context-check.md');
    expect(curated).not.toContain('commits ago'); expect(curated).not.toContain('auth/**');
    expect(curated).toContain('not repaired by re-baselining');
    expect(source('core/surface/skills/context-check/SKILL.md')).toContain('No staging, no commits here');
  });
  it('names the report writer exception and keeps role labels from becoming isolation proof', () => {
    const roles = page('persona-and-context');
    for (const phrase of ['classification: reviewer', 'checkpoint-aggregator', 'ERRORED', 'DEFERRED', 'SessionStart', 'ticket', 'host-provided threads']) expect(roles).toContain(phrase);
    const writer = source('core/surface/agents/checkpoint-aggregator.md');
    expect(writer).toMatch(/tools:.*Write/);
    expect(source('core/pysrc/session-start.py')).toContain('persona injection REMOVED');
    expect(source('core/pysrc/prompt-submit.py')).toContain('_compose_persona');
    expect(roles).toContain('initial="task"');
  });
  it('preserves the historical bibliography verbatim without current benchmark claims', () => {
    const current = read('src/content/docs/concepts/persona-research-basis.md');
    const references = old('persona-research-basis').match(/^\d+\. .+$/gm)!;
    expect(references).toHaveLength(20);
    references.forEach(reference => expect(current).toContain(reference));
    expect(current).toContain('not a live benchmark');
    expect(current).toContain(capture.source_revision);
    expect(current).toContain('not rerun or independently revalidated');
    const hardening = read('src/content/docs/concepts/hardening-history.md');
    expect(hardening).toContain('v2.5.2 (2026-06-25)');
    expect(hardening).not.toContain('eliminated by construction');
    expect(hardening).toContain('archival sweep');
    expect(hardening).toContain('not acquire and rerun');
  });
  it('keeps C03 in the existing PR and C04 open rather than closing the program', () => {
    const plan = read('CONCEPTS-OVERHAUL.md');
    expect(plan).toContain('C03 baseline'); expect(plan).toContain('/pull/859');
    expect(plan).toContain('### C04: diagram propagation');
    expect(plan).toContain('Status: NOT_STARTED. Depends on C01-C03.');
    expect(read('reviews/CONCEPTS-C03-SOURCES.md')).toContain('Existing C02 contradictions remain open');
  });
  it('aligns generated pointer semantics and user-space arrowheads across all assets', () => {
    const tiers = read('public/diagrams/four-tier-map.svg');
    expect(tiers).toContain('ALL APPLICABLE ENTRIES');
    expect(tiers).not.toContain('Inject highest-priority pointer');
    expect(tiers).toContain('character proxy');
    const drift = read('public/diagrams/provenance-drift-flow.svg');
    expect(drift).toContain('Before commit'); expect(drift).toContain('neither stages nor commits');
    const generator = read('scripts/generate-diagrams.ts');
    expect(generator).not.toContain('markerUnits="strokeWidth"');
    expect(generator).toContain('refX="9" refY="4"');
  });
});
