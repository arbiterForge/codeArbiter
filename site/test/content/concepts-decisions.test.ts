import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { adrCases, auditCases, decisionRoutes, evidenceSources, evidenceSourceRevision,
  smartsExample, validateDecisionEvidence } from '../../scripts/decision-evidence';
import { checkpointMap } from '../../scripts/execution-maps/checkpoint';
import { validateExecutionMap } from '../../scripts/execution-maps/model';
import { renderChapterSvg } from '../../scripts/execution-maps/render';

const read = (path: string) => readFileSync(path, 'utf8');
const page = (slug: string) => read(`src/content/docs/concepts/${slug}.mdx`);
const baseline = (path: string) => execFileSync('git', ['show', `${evidenceSourceRevision}:${path}`], { encoding: 'utf8' });

describe('C02 source and evidence distinctions', () => {
  it('binds editorial claims to inspected current and pinned canonical source', () => {
    expect(validateDecisionEvidence()).toEqual([]);
    for (const source of Object.values(evidenceSources)) {
      expect(read(`../${source.path}`)).toContain(source.quote);
      const revision = 'revision' in source ? source.revision : evidenceSourceRevision;
      expect(execFileSync('git', ['show', `${revision}:${source.path}`], { encoding: 'utf8' })).toContain(source.quote);
    }
  });
  it('retains every former public section heading when the source moves to MDX', () => {
    for (const slug of ['smarts', 'adrs', 'checkpoints', 'auditability']) {
      const old = baseline(`site/src/content/docs/concepts/${slug}.md`);
      for (const heading of old.match(/^## .+$/gm) ?? []) expect(page(slug)).toContain(heading);
    }
  });
  it('uses six even-handed non-numeric lenses with valid short cells', () => {
    expect(smartsExample.lenses.map(lens => lens.name)).toEqual(['Scalable','Maintainable','Available','Reliable','Testable','Securable']);
    expect(smartsExample.lenses.every(lens => lens.cells.length === smartsExample.options.length)).toBe(true);
    for (const lens of smartsExample.lenses) for (const cell of lens.cells) {
      expect(['Strong','Adequate','Weak','Indifferent']).toContain(cell.verdict);
      expect(cell.reason.split(/\s+/).length).toBeLessThanOrEqual(20);
    }
    expect(smartsExample.scenario).toContain('Illustrative');
    expect(smartsExample.intent).toContain('cannot reopen');
  });
  it('rejects broken destinations and incomplete evidence case data rather than hiding it', () => {
    const original = adrCases[0].href;
    try { adrCases[0].href = '//untrusted.invalid'; expect(validateDecisionEvidence()).toContain('invalid continuation'); }
    finally { adrCases[0].href = original; }
    const label = auditCases[0].label;
    try { auditCases[0].label = ''; expect(validateDecisionEvidence()).toContain('incomplete case'); }
    finally { auditCases[0].label = label; }
    expect(validateDecisionEvidence()).toEqual([]);
  });
  it('distinguishes sprint delegation, arbitration choice and typed steps-only authority', () => {
    const smarts = page('smarts');
    for (const phrase of ['recorded-intent check', 'Step 0 applies to sprint and brainstorming', 'moderate and tied non-hard-gate choices', '`delegate-methods`', '`smarts-apply`', 'does not confer prerequisite, security,', 'Artifact-section-hash']) expect(smarts).toContain(phrase);
    expect(decisionRoutes.map(route => route.id)).toEqual(['reconcile','sprint']);
    expect(decisionRoutes[0].endpoint).toContain('separately directed');
    expect(decisionRoutes[1].endpoint).toContain('not an autonomous merge');
  });
  it('separates governance, immutable record identity and derived current delivery', () => {
    const adr = page('adrs');
    for (const phrase of ['full filename stem', 'adr-lifecycle.jsonl', 'Accepted/Planned', 'unsealed baseline', 'Partial', 'expiry', 'source ancestry']) expect(adr).toContain(phrase);
    expect(adrCases.map(item => item.id)).toEqual(['accepted','implemented','verified','stale']);
    expect(read('../core/pysrc/_adrlifecycle.py')).toContain('claim_scope');
    expect(read('../core/pysrc/_adrlifecyclegit.py')).toContain('source_ancestry');
  });
  it('keeps report persistence and the override counter separate from verdict and acceptance', () => {
    const checkpoint = page('checkpoints');
    for (const phrase of ['verdict-aggregator', 'separate caller-owned step', 'bare integer', 'historical rows remain', 'It does not write', 'no promotion sign-off']) expect(checkpoint).toContain(phrase);
    const curated = read('src/curated/commands/checkpoint.md');
    expect(curated).toContain('verdict-aggregator');
    expect(curated).toContain('incomplete-unit result');
    expect(curated).not.toContain('finding-triage` then `checkpoint-aggregator');
  });
  it('does not turn packet assembly into historical reconstruction or missing evidence into none', () => {
    const audit = page('auditability');
    for (const phrase of ['small-lane classifications', 'currently unresolved', 'most recent', 'integer override-count baseline', 'source-contract discrepancy', 'labelled redacted derivative', 'not a byte-exact copy']) expect(audit).toContain(phrase);
    expect(read('src/curated/commands/audit.md')).toContain('not a commit or date');
    const record = read('reviews/CONCEPTS-C02-SOURCES.md');
    expect(record).toContain('State: OPEN'); expect(record).toContain('last-checkpoint');
    expect(record).toContain('not documentation-closed');
  });
});

describe('periodic checkpoint map', () => {
  it('has seven complete source-owned steps and the actual non-delivery endpoint', () => {
    expect(validateExecutionMap(checkpointMap)).toEqual([]);
    const nodes = checkpointMap.chapters.flatMap(chapter => chapter.nodes);
    expect(nodes.map(node => node.id)).toEqual(['sweep-entry','sweep-dispatch','sweep-reviewers','sweep-triage','sweep-verdict','sweep-write','sweep-return']);
    for (const source of Object.values(checkpointMap.sources)) expect(read(`../${source.path}`)).toContain(source.quote);
    expect(checkpointMap.outcome).toContain('No code repair, commit, PR');
    expect(nodes[6].detail).toContain('not a second invocation');
  });
  it('rejects loss of the verdict-before-writer boundary', () => {
    const altered = structuredClone(checkpointMap);
    altered.chapters[1].nodes.reverse();
    expect(validateExecutionMap(altered)).toContain('unknown or unordered chapter edge');
  });
  it('renders each distinct node once with continuous ordinal labels', () => {
    const svg = checkpointMap.chapters.map((chapter,i) => renderChapterSvg(chapter,`checkpoint-test-${i}`,i*4)).join('');
    expect(svg.match(/data-map-node=/g)).toHaveLength(7);
    expect(svg).toContain('Commands'); expect(svg).toContain('Skills'); expect(svg).toContain('Agents');
    expect(svg).toContain('>07</text>');
    expect(svg).not.toContain('/ca:pr');
  });
});


describe('ADR owner modes', () => {
  it('documents a read-only status path without authoring prerequisites', () => {
    const owner = read('src/curated/skills/decision-lifecycle.md').replace(/\s+/g, ' ');
    expect(owner).toContain('A status request reads existing records without loading the authoring procedure.');
    expect(owner).toContain('does not create a missing decisions directory');
    expect(owner).toContain('only after explicit intent and');
    expect(owner).not.toContain('3. (Status mode)');
  });
  it('preserves numeric-selector ambiguity and reports full-stem delivery state', () => {
    const status = read('src/curated/commands/adr-status.md');
    expect(status).toContain('exactly one full filename stem');
    expect(status).toContain('No match or multiple matches is reported');
    expect(status).toContain('delivery: Accepted/Planned');
    expect(status).toContain('Illustrative report, not a captured run');
    expect(status).not.toMatch(/- ADR-\d{4} —/);
  });
  it('keeps command and natural-language authoring under the same attribution gate', () => {
    const author = read('src/curated/commands/adr.md');
    expect(author).toContain('The explicit entry and a direct request to record a decision use the same owner.');
    expect(author).toContain('on-demand authoring procedure');
    expect(author).toContain('explicit instruction');
    expect(author).not.toContain('`/adr` is the only path that can arm it');
  });
});
