import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { checkReviewedSource, gitBlob, retainsReviewedChangelog, REVALIDATED_AT } from './atlas';

const boundary = '## [Unreleased]\n\n';
const preamble = '# Changelog\n\nImmutable historical citations.\n\n' + boundary;
const history = '## [1.0.0] - 2026-01-01\n\n### Fixed\n\n- Reviewed behavior.\n';
const reviewed = preamble + history;
const newer = '## [1.0.1] - 2026-01-02\n\n### Fixed\n\n- Later behavior.\n\n';

describe('historical changelog growth', () => {
  it('accepts the identical history and an empty insertion', () => {
    expect(retainsReviewedChangelog(reviewed, reviewed)).toBe(true);
  });
  it('accepts new release sections only above the complete old history', () => {
    expect(retainsReviewedChangelog(preamble + newer + history, reviewed)).toBe(true);
    expect(retainsReviewedChangelog(preamble + newer.replace('[1.0.1]', '[1.0.2]') + newer + history, reviewed)).toBe(true);
  });
  it('allows new Unreleased notes without treating them as reviewed evidence', () => {
    expect(retainsReviewedChangelog(preamble + '### Added\n\n- Not reviewed.\n\n' + history, reviewed)).toBe(true);
  });
  it('preserves logical CRLF checkout support', () => {
    expect(retainsReviewedChangelog((preamble + newer + history).replace(/\n/g, '\r\n'), reviewed)).toBe(true);
    expect(retainsReviewedChangelog(preamble + newer + history, reviewed.replace(/\n/g, '\r\n'))).toBe(true);
  });
  it.each([
    ['edited historical text', preamble + newer + history.replace('Reviewed behavior.', 'Changed behavior.')],
    ['deleted historical text', preamble + newer + history.replace('- Reviewed behavior.\n', '')],
    ['renamed historical release', preamble + newer + history.replace('[1.0.0]', '[1.0.2]')],
    ['new text inside old history', reviewed.replace('### Fixed', newer + '### Fixed')],
    ['new text after old history', reviewed + '\n' + newer],
    ['changed preamble', reviewed.replace('Immutable', 'Mutable')],
    ['removed Unreleased boundary', reviewed.replace(boundary, '')],
    ['duplicate Unreleased boundary', preamble + boundary + history],
    ['removed all history', preamble + newer],
  ])('refuses %s', (_name, current) => {
    expect(retainsReviewedChangelog(current, reviewed)).toBe(false);
  });
  it.each([
    ['absent boundary', '# Changelog\n' + history],
    ['ambiguous boundary', preamble + boundary + history],
    ['empty history', preamble],
    ['unstructured history', preamble + 'no release heading\n'],
  ])('refuses a changed file against %s in the review object', (_name, invalid) => {
    expect(retainsReviewedChangelog(invalid + newer, invalid)).toBe(false);
  });
});

describe('changelog exception stays bound to actual reviewed Git history', () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  let dir: string;
  let baseline: string;
  const git = (...args: string[]): string => execFileSync('git', args, {
    cwd: dir, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 10_000,
  });
  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'ca-atlas-history-'));
    // Local object sharing only: no network, checkout, source edits or hooks.
    execFileSync('git', ['clone', '--shared', '--no-checkout', root, dir], {
      stdio: ['ignore', 'pipe', 'pipe'], timeout: 10_000,
    });
    baseline = git('show', `${REVALIDATED_AT}:CHANGELOG.md`);
  }, 15_000);
  afterAll(() => { if (dir) rmSync(dir, { recursive: true, force: true }); });

  it('accepts release growth through the actual implicit-pin source check', () => {
    expect(baseline.split(boundary)).toHaveLength(2);
    writeFileSync(join(dir, 'CHANGELOG.md'), baseline.replace(boundary, boundary + newer));
    expect(() => checkReviewedSource(dir, 'CHANGELOG.md')).not.toThrow();
  });
  it('still refuses an explicit changelog blob mismatch', () => {
    writeFileSync(join(dir, 'CHANGELOG.md'), baseline.replace(boundary, boundary + newer));
    expect(() => checkReviewedSource(dir, 'CHANGELOG.md', gitBlob(Buffer.from(baseline))))
      .toThrow(/Atlas source changed: CHANGELOG.md/);
  });
  it('refuses changed or missing historical notes after new notes are added', () => {
    const oldNote = '- Reduce plan approval preflight latency by batching validated task reads.';
    expect(baseline).toContain(oldNote);
    writeFileSync(join(dir, 'CHANGELOG.md'), baseline.replace(boundary, boundary + newer)
      .replace(oldNote, '- Changed historical behavior.'));
    expect(() => checkReviewedSource(dir, 'CHANGELOG.md')).toThrow(/Atlas source changed/);
  });
  it('does not extend the exception to a workflow owner or nested changelog', () => {
    mkdirSync(join(dir, 'core'), { recursive: true });
    const hosts = git('show', `${REVALIDATED_AT}:core/hosts.json`);
    writeFileSync(join(dir, 'core/hosts.json'), hosts + '\n');
    expect(() => checkReviewedSource(dir, 'core/hosts.json')).toThrow(/Atlas source changed/);
    mkdirSync(join(dir, 'plugins/ca-pi'), { recursive: true });
    const sibling = git('show', `${REVALIDATED_AT}:plugins/ca-pi/CHANGELOG.md`);
    writeFileSync(join(dir, 'plugins/ca-pi/CHANGELOG.md'), sibling.replace(boundary, boundary + newer) + '\n');
    expect(() => checkReviewedSource(dir, 'plugins/ca-pi/CHANGELOG.md')).toThrow(/Atlas source changed/);
  });
  it('requires the old Git object rather than substituting current text or main', () => {
    const empty = mkdtempSync(join(tmpdir(), 'ca-atlas-missing-history-'));
    try {
      writeFileSync(join(empty, 'CHANGELOG.md'), baseline.replace(boundary, boundary + newer));
      expect(() => checkReviewedSource(empty, 'CHANGELOG.md')).toThrow(/needs reviewed Git object/);
    } finally { rmSync(empty, { recursive: true, force: true }); }
  });
  it('refuses a symlink even when its target preserves the reviewed history', () => {
    rmSync(join(dir, 'CHANGELOG.md'));
    writeFileSync(join(dir, 'actual.md'), baseline.replace(boundary, boundary + newer));
    symlinkSync(join(dir, 'actual.md'), join(dir, 'CHANGELOG.md'));
    expect(() => checkReviewedSource(dir, 'CHANGELOG.md')).toThrow(/symlink/);
  });
});
