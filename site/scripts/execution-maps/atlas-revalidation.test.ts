import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { loadAtlas, originalAtlas, REVALIDATED_AT } from './atlas';
import { geometryRecord, REVIEWED_AT } from './atlas-model';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const git = (...args: string[]): string => execFileSync('git', args, {
  cwd: root,
  encoding: 'utf8',
});

describe('PR936 atlas source compatibility revalidation', () => {
  it('binds the count-only correction without changing original geometry or source links', () => {
    const atlas = loadAtlas();
    const original = originalAtlas();
    const productInputs = new Set([
      ...atlas.sources.filter(source => !source.path.startsWith('site/')).map(source => source.path),
      ...atlas.commands.map(command => command.source!.path),
      'core/hosts.json',
      'core/surface/command-routes.json',
    ]);
    const changed = git('diff', '--name-only', REVIEWED_AT, REVALIDATED_AT, '--')
      .trim().split('\n').filter(path => productInputs.has(path));
    expect(changed).toEqual(['docs/parity.md']);

    const before = git('show', `${REVIEWED_AT}:docs/parity.md`);
    const after = git('show', `${REVALIDATED_AT}:docs/parity.md`);
    const oldRow = '| Role charters | 19 current plugin agents |';
    expect(before).toContain(oldRow);
    expect(after).toBe(before.replace(oldRow, '| Role charters | 20 current plugin agents |'));
    expect(atlas.commit).toBe(REVIEWED_AT);
    expect(atlas.scope).toContain(REVALIDATED_AT);
    expect(atlas.sources).toEqual(original.sources);
    expect(atlas.views.map(geometryRecord)).toEqual(original.views.map(geometryRecord));
  });
});
