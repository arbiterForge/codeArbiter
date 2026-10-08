import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { loadAtlas, originalAtlas, REVALIDATED_AT } from './atlas';
import { geometryRecord, REVIEWED_AT } from './atlas-model';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const countReview = '81055792c71ba7aaeeaf5280e81ce2929bb25cc1';
const preflightReview = '97a2ea0fb1dd2983f2757f680cfb9a359cbf69aa';
const git = (...args: string[]): string => execFileSync('git', args, {
  cwd: root,
  encoding: 'utf8',
});

function changedProductInputs(from: string, to: string): string[] {
  const atlas = loadAtlas();
  const productInputs = new Set([
    ...atlas.sources.filter(source => !source.path.startsWith('site/')).map(source => source.path),
    ...atlas.commands.map(command => command.source!.path),
    'core/hosts.json',
    'core/surface/command-routes.json',
  ]);
  return git('diff', '--name-only', from, to, '--')
    .trim().split('\n').filter(path => productInputs.has(path));
}

describe('atlas source compatibility revalidation', () => {
  it('retains the exact historical PR936 count-only correction', () => {
    expect(changedProductInputs(REVIEWED_AT, countReview)).toEqual(['docs/parity.md']);
    const before = git('show', `${REVIEWED_AT}:docs/parity.md`);
    const after = git('show', `${countReview}:docs/parity.md`);
    const oldRow = '| Role charters | 19 current plugin agents |';
    expect(before).toContain(oldRow);
    expect(after).toBe(before.replace(oldRow, '| Role charters | 20 current plugin agents |'));
  });

  it('binds the reviewed preflight changelog addition without allowing arbitrary source drift', () => {
    expect(REVALIDATED_AT).toBe(preflightReview);
    expect(changedProductInputs(REVIEWED_AT, REVALIDATED_AT)).toEqual(['CHANGELOG.md', 'docs/parity.md']);
    expect(changedProductInputs(countReview, REVALIDATED_AT)).toEqual(['CHANGELOG.md']);

    const before = git('show', `${countReview}:CHANGELOG.md`);
    const after = git('show', `${REVALIDATED_AT}:CHANGELOG.md`);
    const boundary = '## [Unreleased]\n\n';
    const addition = '## [2.25.1] - 2026-10-07\n\n### Fixed\n\n' +
      '- Reduce plan approval preflight latency by batching validated task reads.\n\n';
    expect(before.split(boundary)).toHaveLength(2);
    expect(before).not.toContain(addition);
    expect(after).toBe(before.replace(boundary, boundary + addition));
    expect(git('show', `${REVALIDATED_AT}:docs/parity.md`))
      .toBe(git('show', `${countReview}:docs/parity.md`));
  });

  it('preserves original geometry and source links independently of the compatibility review', () => {
    const atlas = loadAtlas();
    const original = originalAtlas();
    expect(atlas.commit).toBe(REVIEWED_AT);
    expect(atlas.scope).toContain(REVALIDATED_AT);
    expect(atlas.sources).toEqual(original.sources);
    expect(atlas.views.map(geometryRecord)).toEqual(original.views.map(geometryRecord));
  });
});
