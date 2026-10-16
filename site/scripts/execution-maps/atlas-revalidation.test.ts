import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import { loadAtlas, originalAtlas, retainsReviewedChangelog, REVALIDATED_AT, DRAFT_PREVIEW_SOURCE_BLOBS, UNITTEST_COLLECTOR_BLOB, BROWNFIELD_SOURCE_BLOBS, LEGACY_CODE_MAP_SOURCE_BLOBS, CONTEXT_MAINTENANCE_SOURCE_BLOBS, RUNTIME_COMPATIBILITY_SOURCE_BLOBS, ASSISTIVE_SOURCE_BLOBS } from './atlas';
import { geometryRecord, invocation, REVIEWED_AT, type HostDescriptor } from './atlas-model';
import { commandMetadata } from './atlas-command';
import packetPreparationSnapshot from './atlas-data/packet-preparation-review.json';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const countReview = '81055792c71ba7aaeeaf5280e81ce2929bb25cc1';
const preflightReview = '97a2ea0fb1dd2983f2757f680cfb9a359cbf69aa';
const piReview = '6a243348a0e74b0a50c37eccf4d61520129a5c1c';
const completionReview = '0192dc314817ffab18219d6485c11ac1531bbc5c';
const nativeV2Review = '25980c292b529fca90c39f5f26d69a1c0674de44';
const packetPreparationReview = '5e909cfab72e4e7793b3ffa7b62c2239632f80d1';
const packetPreparationMain = '4c2529e2f3804d38855094e1c11d36178067c826';
// Main960 retains the exact two reviewed a968 guide blobs after its squash.
const legacyDeliveryReview = 'd547f82777111bc20001a977719307d3d68fc13e';
const runtimeCompatibilityBaseline = 'e33bb87b30d4a3ac3286378ad9ec5bff70140392';
const packetInventoryHash = 'faee422cbe0747004b85660ce6c1bf54a730759c83435dd5d9c69469a06e0baf';
const packetChangelogHash = '8d299cd300ea41b7dae51e89a8caa418eafff0066173ac8ab1ae55030772f7a4';
const git = (...args: string[]): string => execFileSync('git', args, {
  cwd: root,
  encoding: 'utf8',
});

let atlas: ReturnType<typeof loadAtlas>;
let productInputs: Set<string>;
beforeAll(() => {
  atlas = loadAtlas();
  productInputs = new Set([
    ...atlas.sources.filter(source => !source.path.startsWith('site/')).map(source => source.path),
    ...atlas.commands.map(command => `core/surface/commands/${command.name}.md`),
    ...atlas.commands.map(command => command.source!.path),
    'core/hosts.json',
    'core/surface/command-routes.json',
  ]);
});

function changedProductInputs(from: string, to: string): string[] {
  return git('diff', '--name-only', from, to, '--')
    .trim().split('\n').filter(path => productInputs.has(path));
}

// The packet's original branch commit need not survive a squash. Retain its
// entire actual input inventory and unique draft changelog as inert fixtures;
// resolve every other blob through stable reviewed/main ancestors. No fetch,
// object creation or current-main substitution supplies a missing historical read.
function historicalBlobBatch(blobs: string[]): Buffer[] {
  const response = execFileSync('git', ['--no-replace-objects', '--no-lazy-fetch', 'cat-file', '--batch'], {
    cwd: root, input: blobs.map(blob => `${blob}\n`).join(''), maxBuffer: 4 * 1024 * 1024,
  });
  const result: Buffer[] = [];
  let offset = 0;
  for (const blob of blobs) {
    const end = response.indexOf(10, offset);
    const header = end < offset ? null : /^([0-9a-f]{40}) blob (\d+)$/.exec(response.subarray(offset, end).toString('utf8'));
    if (!header || header[1] !== blob) throw new Error('Missing or invalid historical packet blob');
    const size = Number(header[2]);
    if (!Number.isSafeInteger(size) || size < 0 || end + 1 + size >= response.length || response[end + 1 + size] !== 10) {
      throw new Error('Malformed historical packet blob batch');
    }
    result.push(response.subarray(end + 1, end + 1 + size));
    offset = end + 2 + size;
  }
  if (offset !== response.length) throw new Error('Unexpected historical packet batch bytes');
  return result;
}

function historicalChangelogFixture(
  encoded = readFileSync(new URL('./atlas-data/packet-preparation-changelog.json', import.meta.url), 'utf8'),
): Buffer {
  const decoded: unknown = JSON.parse(encoded);
  if (typeof decoded !== 'string') throw new Error('Historical packet changelog fixture must be a JSON string');
  return Buffer.from(decoded, 'utf8');
}

function historicalPacketInputs(
  review = packetPreparationSnapshot,
  changelog = historicalChangelogFixture(),
  readBlobs = historicalBlobBatch,
): Map<string, string> {
  const keys = ['format', 'source_commit', 'baseline_commit', 'evidence_kind', 'changed_paths', 'input_count', 'inputs', 'changelog_sha256'];
  if (JSON.stringify(Object.keys(review).sort()) !== JSON.stringify(keys.sort()) ||
    review.format !== 'codearbiter.atlas-historical-inputs/1' || review.source_commit !== packetPreparationReview ||
    review.baseline_commit !== nativeV2Review || review.evidence_kind !== 'historical-draft-source-snapshot-not-publication' ||
    review.input_count !== 71 || !Array.isArray(review.inputs) || review.inputs.length !== 71 ||
    review.inputs.some(row => JSON.stringify(Object.keys(row).sort()) !== '["blob","path","sha256"]' ||
      typeof row.path !== 'string' || typeof row.blob !== 'string' || !/^[0-9a-f]{40}$/.test(row.blob) ||
      typeof row.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(row.sha256)) ||
    JSON.stringify(review.inputs.map(row => row.path)) !== JSON.stringify([...productInputs].sort()) ||
    createHash('sha256').update(JSON.stringify(review.inputs)).digest('hex') !== packetInventoryHash) {
    throw new Error('Historical packet input inventory is missing, malformed or changed');
  }
  const changes = ['CHANGELOG.md', 'core/surface/commands/init.md', 'core/surface/skills/debug/SKILL.md'];
  if (JSON.stringify(review.changed_paths) !== JSON.stringify(changes)) throw new Error('Historical packet changed-path scope changed');
  if (review.changelog_sha256 !== packetChangelogHash || createHash('sha256').update(changelog).digest('hex') !== packetChangelogHash) {
    throw new Error('Historical packet changelog SHA-256 changed');
  }
  const changed: string[] = [];
  const result = new Map<string, string>();
  const references = [...review.inputs.map(row => `${nativeV2Review}:${row.path}`),
    ...Object.keys(BROWNFIELD_SOURCE_BLOBS).map(path => `${packetPreparationMain}:${path}`)];
  const identities = git('--no-replace-objects', '--no-lazy-fetch', 'rev-parse', ...references).trim().split('\n');
  if (identities.length !== references.length || identities.some(blob => !/^[0-9a-f]{40}$/.test(blob))) {
    throw new Error('Historical packet ancestor inventory is incomplete');
  }
  const mainBlobs = new Map(Object.keys(BROWNFIELD_SOURCE_BLOBS).map((path, index) => [path, identities[71 + index]]));
  const objects = readBlobs(review.inputs.filter(row => row.path !== 'CHANGELOG.md').map(row => row.blob));
  if (objects.length !== 70) throw new Error('Historical packet blob inventory is incomplete');
  let objectIndex = 0;
  for (const [index, row] of review.inputs.entries()) {
    const before = identities[index];
    if (row.blob !== before) changed.push(row.path);
    const bytes = row.path === 'CHANGELOG.md' ? changelog : objects[objectIndex++];
    if (createHash('sha256').update(bytes).digest('hex') !== row.sha256) throw new Error(`Historical packet blob changed: ${row.path}`);
    if (row.path === 'CHANGELOG.md' && execFileSync('git', ['hash-object', '--stdin'], {cwd: root, input: bytes, encoding: 'utf8'}).trim() !== row.blob) {
      throw new Error('Historical packet retained changelog blob identity changed');
    }
    if (row.path !== 'CHANGELOG.md') {
      if ((mainBlobs.get(row.path) ?? before) !== row.blob) {
        throw new Error(`Historical packet ancestor identity changed: ${row.path}`);
      }
    }
    result.set(row.path, bytes.toString('utf8'));
  }
  if (JSON.stringify(changed) !== JSON.stringify(changes)) throw new Error('Historical packet exact three-path delta changed');
  return result;
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

  it('binds only the reviewed native V2 owners and preserved changelog history', () => {
    expect(changedProductInputs(completionReview, nativeV2Review)).toEqual([
      'CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py', 'core/surface/includes/artifacts.md',
      'docs/hooks.md',
    ]);
    const reviewedBlobs = {
      'core/pysrc/_artifactauthoritylib.py': '796471d01306edddb3c4b5af26b9f740d2c81fc7',
      'core/surface/includes/artifacts.md': 'ff55bc49e336ef6ddf6498c55d7993a137214532',
      'docs/hooks.md': '7e7312aefd548049e54b98a53297b0e19213477a',
    };
    for (const [path, blob] of Object.entries(reviewedBlobs)) {
      expect(git('rev-parse', `${nativeV2Review}:${path}`).trim()).toBe(blob);
    }
    expect(retainsReviewedChangelog(git('show', `${nativeV2Review}:CHANGELOG.md`),
      git('show', `${completionReview}:CHANGELOG.md`))).toBe(true);
  });

  it('binds the exact draft-preview documents and the complete combined product input set', () => {
    const inputs = new Set(productInputs);
    for (const command of originalAtlas().commands) commandMetadata(command.name, path => {
      inputs.add(path);
      return readFileSync(resolve(root, path), 'utf8');
    });
    const current = (path: string): string => readFileSync(resolve(root, path), 'utf8').replace(/\r\n/g, '\n');
    // One Git object query for the complete current set and one for its
    // reviewed baseline. Spawning a separate Git process per source grew
    // past Vitest's 5s limit on Windows as the real input set expanded.
    // Hashes are Git's own object identities; the exact pinned blob probes
    // below remain independently byte-strict.
    const paths = [...inputs].sort();
    const observed = git('hash-object', '--', ...paths).trim().split('\n');
    const reviewed = git('rev-parse', ...paths.map(path => `${nativeV2Review}:${path}`)).trim().split('\n');
    expect(observed).toHaveLength(paths.length);
    expect(reviewed).toHaveLength(paths.length);
    const changed = paths.filter((_, index) => observed[index] !== reviewed[index]);
    expect(changed).toEqual(['CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py',
      'core/surface/COMMANDS.md', 'core/surface/SPRINT.md', 'core/surface/arbiter.md',
      'core/surface/commands/feature.md', 'core/surface/commands/init.md',
      'core/surface/commands/sprint.md', 'core/surface/commands/status.md', 'core/surface/includes/artifacts.md',
      'core/surface/includes/routing-table.md', 'core/surface/skills/INDEX.md',
      'core/surface/skills/commit-gate/SKILL.md', 'core/surface/skills/debug/SKILL.md',
      'core/surface/skills/finishing-a-development-branch/SKILL.md',
      'core/surface/skills/subagent-driven-development/SKILL.md', 'core/surface/skills/tdd/SKILL.md',
      'docs/hooks.md', 'docs/parity.md']);
    expect(DRAFT_PREVIEW_SOURCE_BLOBS).toEqual({
      'core/surface/SPRINT.md': 'c3c47d38028fb3a8141fe1235957e827031acd43',
      'core/surface/includes/artifacts.md': '8a834b919fb81c77213086a1b1661d16b5290bbe',
    });
    for (const [path, blob] of Object.entries(DRAFT_PREVIEW_SOURCE_BLOBS)) {
      expect(git('rev-parse', `${runtimeCompatibilityBaseline}:${path}`).trim()).toBe(blob);
      const currentBlob = ASSISTIVE_SOURCE_BLOBS[path] ?? RUNTIME_COMPATIBILITY_SOURCE_BLOBS[path] ?? blob;
      // The canonical tracked file retains this blob through a squash; no PR
      // commit has to remain reachable in a subsequent main-only clone.
      expect(git('ls-files', '--error-unmatch', '--', path).trim()).toBe(path);
      expect(execFileSync('git', ['hash-object', '--stdin'], {
        cwd: root, input: current(path), encoding: 'utf8',
      }).trim()).toBe(currentBlob);
      expect(git('--no-replace-objects', 'cat-file', 'blob', currentBlob)).toBe(current(path));
    }
    expect(retainsReviewedChangelog(current('CHANGELOG.md'),
      git('--no-replace-objects', 'cat-file', 'blob', `${nativeV2Review}:CHANGELOG.md`))).toBe(true);
  });

  it('binds the reviewed unittest collector and exact combined source changes', () => {
    expect(UNITTEST_COLLECTOR_BLOB).toBe('76a2998f4bd5b6f441f5fd162bbe810b2de2ee93');
    expect(productInputs.size).toBe(71);
    const paths = [...productInputs];
    const current = git('hash-object', '--', ...paths).trim().split('\n');
    const reviewed = git('rev-parse', ...paths.map(path => `${nativeV2Review}:${path}`)).trim().split('\n');
    expect(current).toHaveLength(paths.length);
    expect(reviewed).toHaveLength(paths.length);
    const changed = paths.filter((_, index) => current[index] !== reviewed[index]);
    expect(changed.sort()).toEqual([
      'CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py',
      'core/surface/COMMANDS.md', 'core/surface/SPRINT.md', 'core/surface/arbiter.md',
      'core/surface/commands/feature.md',
      'core/surface/commands/init.md', 'core/surface/commands/sprint.md',
      'core/surface/commands/status.md',
      'core/surface/includes/artifacts.md', 'core/surface/includes/routing-table.md',
      'core/surface/skills/INDEX.md', 'core/surface/skills/commit-gate/SKILL.md',
      'core/surface/skills/debug/SKILL.md',
      'core/surface/skills/finishing-a-development-branch/SKILL.md',
      'core/surface/skills/subagent-driven-development/SKILL.md',
      'core/surface/skills/tdd/SKILL.md', 'docs/hooks.md', 'docs/parity.md',
    ]);
    const path = 'core/pysrc/_artifactauthoritylib.py';
    expect(git('rev-parse', `${runtimeCompatibilityBaseline}:${path}`).trim()).toBe(UNITTEST_COLLECTOR_BLOB);
    expect(git('hash-object', '--', path).trim()).toBe(RUNTIME_COMPATIBILITY_SOURCE_BLOBS[path]);
    expect(git('cat-file', 'blob', UNITTEST_COLLECTOR_BLOB).split('\n').slice(0, 190))
      .toEqual(git('show', `${nativeV2Review}:${path}`).split('\n').slice(0, 190));
    expect(retainsReviewedChangelog(readFileSync(new URL('../../../CHANGELOG.md', import.meta.url), 'utf8'),
      git('show', `${nativeV2Review}:CHANGELOG.md`))).toBe(true);
  });

  it('binds only the reviewed packet preparation and init prerequisites', () => {
    expect(REVALIDATED_AT).toBe(nativeV2Review);
    const historical = historicalPacketInputs();
    expect([...historical.keys()]).toHaveLength(71);
    expect(packetPreparationSnapshot.changed_paths).toEqual([
      'CHANGELOG.md', 'core/surface/commands/init.md', 'core/surface/skills/debug/SKILL.md',
    ]);
    const reviewedBlobs = {
      'core/surface/commands/init.md': 'c3de948de1617aa323e310eefee7fde2bd8a65fc',
      'core/surface/skills/debug/SKILL.md': '6a791230cdbfa0916c63d2b1dcc6431d1625b1a3',
    };
    for (const [path, blob] of Object.entries(reviewedBlobs)) {
      expect(git('rev-parse', `${packetPreparationMain}:${path}`).trim()).toBe(blob);
      expect(BROWNFIELD_SOURCE_BLOBS[path]).toBe(blob);
      expect(git('--no-replace-objects', 'cat-file', 'blob', blob))
        .toBe(historical.get(path));
      expect(git('hash-object', '--', path).trim()).toBe(CONTEXT_MAINTENANCE_SOURCE_BLOBS[path] ?? blob);
    }
    expect(retainsReviewedChangelog(historical.get('CHANGELOG.md')!,
      git('show', `${nativeV2Review}:CHANGELOG.md`))).toBe(true);
  });

  it('refuses missing, malformed or changed historical packet inventories', () => {
    const removed = structuredClone(packetPreparationSnapshot);
    removed.inputs.pop();
    const duplicate = structuredClone(packetPreparationSnapshot);
    duplicate.inputs[1] = duplicate.inputs[0];
    const changed = structuredClone(packetPreparationSnapshot);
    changed.inputs[0].blob = '0'.repeat(40);
    for (const review of [removed, duplicate, changed]) expect(() => historicalPacketInputs(review)).toThrow(/input inventory/);
  });

  it('strictly decodes the historical changelog JSON string without changing its bytes', () => {
    const bytes = historicalChangelogFixture();
    expect(bytes.length).toBe(185147);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(packetChangelogHash);
    expect(execFileSync('git', ['hash-object', '--stdin'], {cwd: root, input: bytes, encoding: 'utf8'}).trim())
      .toBe('0290d678905fd2853ff2132e0ce8151155129bd6');
    // The original historical trailing space is data, preserved inside JSON.
    expect(bytes.toString('utf8').split('\n')[2692]).toBe(
      '## [2026-05-13] — token efficiency pass, added missing slash commands, added local context caching to decompose ',
    );
    expect(() => historicalChangelogFixture('{')).toThrow(SyntaxError);
    for (const value of [null, false, 185147, {}, [], ['historical changelog']]) {
      expect(() => historicalChangelogFixture(JSON.stringify(value))).toThrow(/must be a JSON string/);
    }
    expect(() => historicalPacketInputs(packetPreparationSnapshot, historicalChangelogFixture(JSON.stringify('changed snapshot'))))
      .toThrow(/changelog SHA-256/);
  });

  it('refuses missing or changed historical packet blob bytes and scope', () => {
    expect(() => historicalPacketInputs(packetPreparationSnapshot, Buffer.from('changed snapshot'))).toThrow(/changelog SHA-256/);
    expect(() => historicalPacketInputs(packetPreparationSnapshot, undefined, () => { throw new Error('missing historical blob fixture'); }))
      .toThrow(/missing historical blob/);
    expect(() => historicalPacketInputs(packetPreparationSnapshot, undefined, blobs => blobs.map(() => Buffer.from('wrong blob')))).toThrow(/blob changed/);
    const widened = structuredClone(packetPreparationSnapshot);
    widened.changed_paths.push('core/surface/SPRINT.md');
    expect(() => historicalPacketInputs(widened)).toThrow(/changed-path scope/);
    // A real offline batch lookup of a nonexistent identity must refuse; it
    // cannot fetch an object, synthesize one or treat the missing line as bytes.
    expect(() => historicalBlobBatch(['0'.repeat(40)])).toThrow(/Missing or invalid historical packet blob/);
  });

  it('preserves original geometry and source links independently of the compatibility review', () => {
    const original = originalAtlas();
    expect(atlas.commit).toBe(REVIEWED_AT);
    expect(atlas.scope).toContain(REVALIDATED_AT);
    expect(atlas.sources).toEqual(original.sources);
    expect(atlas.views.map(geometryRecord)).toEqual(original.views.map(geometryRecord));
  });

  it('binds only the three reviewed runtime compatibility owners and preserves cited document ranges', () => {
    expect(RUNTIME_COMPATIBILITY_SOURCE_BLOBS).toEqual({
      'core/surface/includes/artifacts.md': 'c10c13162e63699c3748809f3ef2448bc8b07fb9',
      'core/pysrc/_artifactauthoritylib.py': '8dbbfdbae637e79dea52181b01e328a21efe3a06',
      'docs/hooks.md': 'd4726a5fdbc6175498ab03ac47fe8ee66c2bf36a',
    });
    expect(changedProductInputs(runtimeCompatibilityBaseline, '045c0812888f20f4c843677cfb37b802e2084770')).toEqual([
      'CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py',
      'core/surface/includes/artifacts.md', 'docs/hooks.md',
    ]);
    // S10 and S17 cite these unchanged historical ranges. The Codex protocol
    // clarification is later in each owner; source review, not these slices,
    // establishes compatibility of the authority claims that refer to them.
    for (const [path, start, end] of [
      ['core/surface/includes/artifacts.md', 0, 210], ['docs/hooks.md', 34, 150],
    ] as const) {
      const before = git('show', `${runtimeCompatibilityBaseline}:${path}`).split('\n');
      const retained = git('--no-replace-objects', 'cat-file', 'blob', RUNTIME_COMPATIBILITY_SOURCE_BLOBS[path]).split('\n');
      expect(retained.slice(start, end)).toEqual(before.slice(start, end));
    }
  });

  it('retains the exact historical legacy delivery documents separately from current maintenance', () => {
    for (const [path, blob] of Object.entries(LEGACY_CODE_MAP_SOURCE_BLOBS)) {
      expect(git('rev-parse', `${legacyDeliveryReview}:${path}`).trim()).toBe(blob);
      expect(git('--no-replace-objects', 'cat-file', 'blob', blob))
        .toBe(git('--no-replace-objects', 'cat-file', 'blob', `${legacyDeliveryReview}:${path}`));
    }
  });

  it('binds the complete current input set to the reviewed historical and runtime compatibility owners', () => {
    const inputs = new Set(productInputs);
    for (const command of originalAtlas().commands) commandMetadata(command.name, path => {
      inputs.add(path);
      return readFileSync(resolve(root, path), 'utf8');
    });
    const current = (path: string): string => readFileSync(resolve(root, path), 'utf8').replace(/\r\n/g, '\n');
    const ordered = [...inputs].sort();
    const reviewed = execFileSync('git', ['--no-replace-objects', 'cat-file', '--batch'], {
      cwd: root, input: ordered.map(path => `${nativeV2Review}:${path}\n`).join(''), maxBuffer: 4 * 1024 * 1024,
    });
    const changed: string[] = [];
    let offset = 0;
    for (const path of ordered) {
      const end = reviewed.indexOf(10, offset);
      expect(end).toBeGreaterThanOrEqual(offset);
      const header = /^([0-9a-f]{40}) blob (\d+)$/.exec(reviewed.subarray(offset, end).toString('utf8'));
      if (!header) throw new Error(`Missing or invalid reviewed source object: ${path}`);
      const size = Number(header[2]);
      expect(Number.isSafeInteger(size)).toBe(true);
      const bytes = reviewed.subarray(end + 1, end + 1 + size);
      expect(bytes.length).toBe(size);
      expect(reviewed[end + 1 + size]).toBe(10);
      if (current(path) !== bytes.toString('utf8')) changed.push(path);
      offset = end + 2 + size;
    }
    expect(offset).toBe(reviewed.length);
    expect(changed).toEqual(['CHANGELOG.md', 'core/pysrc/_artifactauthoritylib.py',
      'core/surface/COMMANDS.md', 'core/surface/SPRINT.md', 'core/surface/arbiter.md',
      'core/surface/commands/feature.md', 'core/surface/commands/init.md',
      'core/surface/commands/sprint.md', 'core/surface/commands/status.md', 'core/surface/includes/artifacts.md',
      'core/surface/includes/routing-table.md', 'core/surface/skills/INDEX.md',
      'core/surface/skills/commit-gate/SKILL.md', 'core/surface/skills/debug/SKILL.md',
      'core/surface/skills/finishing-a-development-branch/SKILL.md',
      'core/surface/skills/subagent-driven-development/SKILL.md', 'core/surface/skills/tdd/SKILL.md',
      'docs/hooks.md', 'docs/parity.md']);
    expect(BROWNFIELD_SOURCE_BLOBS).toEqual({
      'core/surface/commands/init.md': 'c3de948de1617aa323e310eefee7fde2bd8a65fc',
      'core/surface/skills/debug/SKILL.md': '6a791230cdbfa0916c63d2b1dcc6431d1625b1a3',
    });
    expect(LEGACY_CODE_MAP_SOURCE_BLOBS).toEqual({
      'core/surface/skills/commit-gate/SKILL.md': '8818ab0ae6230aafcc42b48f72190e0e4ec9adcb',
      'core/surface/skills/finishing-a-development-branch/SKILL.md': '7e495efd47875a05560c34634c46b59b71838ee5',
    });
    expect(CONTEXT_MAINTENANCE_SOURCE_BLOBS).toEqual({
      'core/surface/commands/init.md': '83afa327833ff6f76379389b6d1b80c4978f332b',
      'core/surface/skills/commit-gate/SKILL.md': 'bbfc5054fe7ac94309ded7b8cdd6073b3ad65c9d',
      'core/surface/skills/finishing-a-development-branch/SKILL.md': 'c9b8bc36934e5b79f0e4ec72c35c69997519378f',
    });
    for (const [path, blob] of Object.entries({...DRAFT_PREVIEW_SOURCE_BLOBS, ...BROWNFIELD_SOURCE_BLOBS, ...LEGACY_CODE_MAP_SOURCE_BLOBS,
      ...CONTEXT_MAINTENANCE_SOURCE_BLOBS,
      'core/pysrc/_artifactauthoritylib.py': UNITTEST_COLLECTOR_BLOB,
      ...RUNTIME_COMPATIBILITY_SOURCE_BLOBS, ...ASSISTIVE_SOURCE_BLOBS})) {
      expect(git('ls-files', '--error-unmatch', '--', path).trim()).toBe(path);
      expect(execFileSync('git', ['hash-object', '--stdin'], {cwd: root, input: current(path), encoding: 'utf8'}).trim()).toBe(blob);
      expect(git('--no-replace-objects', 'cat-file', 'blob', blob)).toBe(current(path));
    }
    expect(retainsReviewedChangelog(current('CHANGELOG.md'),
      git('--no-replace-objects', 'cat-file', 'blob', `${nativeV2Review}:CHANGELOG.md`))).toBe(true);
  });
});
