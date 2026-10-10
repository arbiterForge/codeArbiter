import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { loadAtlas, originalAtlas, retainsReviewedChangelog, REVALIDATED_AT } from './atlas';
import { geometryRecord, invocation, REVIEWED_AT, type HostDescriptor } from './atlas-model';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const countReview = '81055792c71ba7aaeeaf5280e81ce2929bb25cc1';
const preflightReview = '97a2ea0fb1dd2983f2757f680cfb9a359cbf69aa';
const piReview = '6a243348a0e74b0a50c37eccf4d61520129a5c1c';
const completionReview = '0192dc314817ffab18219d6485c11ac1531bbc5c';
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

  it('retains the exact historical preflight changelog review', () => {
    expect(changedProductInputs(REVIEWED_AT, preflightReview)).toEqual(['CHANGELOG.md', 'docs/parity.md']);
    expect(changedProductInputs(countReview, preflightReview)).toEqual(['CHANGELOG.md']);

    const before = git('show', `${countReview}:CHANGELOG.md`);
    const after = git('show', `${preflightReview}:CHANGELOG.md`);
    const boundary = '## [Unreleased]\n\n';
    const addition = '## [2.25.1] - 2026-10-07\n\n### Fixed\n\n' +
      '- Reduce plan approval preflight latency by batching validated task reads.\n\n';
    expect(before.split(boundary)).toHaveLength(2);
    expect(before).not.toContain(addition);
    expect(after).toBe(before.replace(boundary, boundary + addition));
    expect(git('show', `${preflightReview}:docs/parity.md`))
      .toBe(git('show', `${countReview}:docs/parity.md`));
  });

  it('binds only the reviewed Pi target changes and preserved changelog history', () => {
    expect(changedProductInputs(preflightReview, piReview)).toEqual([
      'CHANGELOG.md', 'core/hosts.json', 'core/surface/commands/doctor.md', 'docs/parity.md',
    ]);
    const replacements: Record<string, string[]> = {
      'core/hosts.json': ['"1.0.2": "12632f365440b07d5183cff871d889b796a3c711b6b49df20f95d9bc198d6c51"'],
      'core/surface/commands/doctor.md': ['supported Pi 1.0.2 public extension'],
      'docs/parity.md': [
        'contracts target exact Pi 1.0.2. The completed hosted',
        'Public 1.0.2 APIs cannot submit the deterministic wrapper probe through active dispatch.',
        'added only after the committed Windows/macOS/Linux by Pi 1.0.2 matrix',
      ],
    };
    for (const [path, fragments] of Object.entries(replacements)) {
      let expected = git('show', `${preflightReview}:${path}`);
      for (const fragment of fragments) {
        expect(expected.split(fragment)).toHaveLength(2);
        expected = expected.replace(fragment, fragment.replace('1.0.2', '1.1.0'));
      }
      expect(git('show', `${piReview}:${path}`)).toBe(expected);
    }
    expect(retainsReviewedChangelog(git('show', `${piReview}:CHANGELOG.md`),
      git('show', `${preflightReview}:CHANGELOG.md`))).toBe(true);
  });

  it('preserves every host invocation and exclusion across the Pi target update', () => {
    const before = JSON.parse(git('show', `${preflightReview}:core/hosts.json`)).hosts as HostDescriptor[];
    const after = JSON.parse(git('show', `${piReview}:core/hosts.json`)).hosts as HostDescriptor[];
    expect(after.map(host => host.name)).toEqual(before.map(host => host.name));
    for (const [index, host] of after.entries()) {
      expect(host.command_form).toBe(before[index].command_form);
      expect(host.surface).toEqual(before[index].surface);
      for (const command of originalAtlas().commands) {
        expect(invocation(host, command.name)).toBe(invocation(before[index], command.name));
      }
    }
  });

  it('binds only the reviewed completion owners and preserved changelog history', () => {
    expect(REVALIDATED_AT).toBe(completionReview);
    expect(changedProductInputs(piReview, completionReview)).toEqual([
      'CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py', 'core/surface/includes/artifacts.md',
    ]);
    const reviewedBlobs = {
      'core/pysrc/_artifactauthoritylib.py': '6ddbf7268705ca649b77450d544477ea3fc56b60',
      'core/surface/includes/artifacts.md': '4241e8bc3ebf22296f2e6174548b9de06491e09f',
    };
    for (const [path, blob] of Object.entries(reviewedBlobs)) {
      expect(git('rev-parse', `${completionReview}:${path}`).trim()).toBe(blob);
    }
    expect(retainsReviewedChangelog(git('show', `${completionReview}:CHANGELOG.md`),
      git('show', `${piReview}:CHANGELOG.md`))).toBe(true);
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
