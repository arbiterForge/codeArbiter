import * as fs from 'node:fs';
import { mkdtemp, mkdir, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as pagefind from 'pagefind';
import { buildSearchIndex, completePagefind, validateSearchFiles, writeSearchFiles } from './pagefind-build';

vi.mock('node:fs', async original => {
  const actual = await original<typeof import('node:fs')>();
  return { ...actual, renameSync: vi.fn(actual.renameSync) };
});

const directories: string[] = [];
async function fixture() {
  const directory = await mkdtemp(join(tmpdir(), 'ca-search-build-'));
  directories.push(directory);
  return directory;
}
const bytes = (text: string) => Buffer.from(text);
const files = () => [
  { path: 'pagefind.js', content: bytes('export const search = async () => ({results: []});') },
  { path: 'pagefind-entry.json', content: bytes('{"languages":{"en":{}}}') },
  { path: 'fragment/example.pf_fragment', content: Uint8Array.from([0, 255, 1, 2, 3]) },
];
afterEach(async () => { vi.restoreAllMocks(); await Promise.all(directories.splice(0).map(dir => rm(dir, { recursive: true, force: true }))); });

describe('complete search bundle publication', () => {
  it('writes and reads back every byte, replacing only the previous generated search output', async () => {
    const directory = await fixture();
    await mkdir(join(directory, 'pagefind'));
    await writeFile(join(directory, 'pagefind/obsolete'), 'old index');
    await writeFile(join(directory, 'index.html'), 'keep page');
    const expected = files();
    const report = await writeSearchFiles(directory, expected, 1);
    expect(report.pageCount).toBe(1);
    expect(report.files.map(file => file.path)).toEqual(expected.map(file => file.path));
    for (const file of expected) expect(await readFile(join(directory, 'pagefind', file.path))).toEqual(Buffer.from(file.content));
    expect(await readFile(join(directory, 'index.html'), 'utf8')).toBe('keep page');
    expect(await readdir(join(directory, 'pagefind'))).not.toContain('obsolete');
    expect((await readdir(directory)).filter(name => name.startsWith('.pagefind-stage-'))).toEqual([]);
    expect(report.files.every(file => /^[a-f0-9]{64}$/.test(file.sha256) && file.bytes > 0)).toBe(true);
  });

  it('restores the previous search index after a late promotion failure and converges on rerun', async () => {
    const directory = fs.realpathSync(await fixture());
    const destination = join(directory, 'pagefind');
    const previous = files();
    await writeSearchFiles(directory, previous, 1);
    const obsolete = join(destination, 'obsolete');
    const article = join(directory, 'index.html');
    await writeFile(obsolete, 'previous search-only asset');
    await writeFile(article, 'handwritten page');
    const snapshot = () => Object.fromEntries(
      fs.readdirSync(directory, { recursive: true }).map(path => String(path)).sort()
        .filter(path => fs.lstatSync(join(directory, path)).isFile())
        .map(path => [path, fs.readFileSync(join(directory, path)).toString('hex')]),
    );
    const before = snapshot();
    const updated = files();
    updated[0].content = bytes('export const search = async () => ({results: [1]});');
    updated[2].content = Uint8Array.from([4, 255, 2, 1]);
    updated.push({ path: 'fragment/added.pf_fragment', content: Uint8Array.from([1, 0, 255]) });
    const early = join(destination, updated[2].path);
    const added = join(destination, 'fragment', 'added.pf_fragment');
    const late = join(destination, 'pagefind.js');
    const real = (await vi.importActual<typeof import('node:fs')>('node:fs')).renameSync;
    let failedPromotions = 0;
    vi.mocked(fs.renameSync).mockImplementation((from, to) => {
      if (String(from).endsWith('.new') && to === late) {
        expect(fs.readFileSync(early)).toEqual(Buffer.from(updated[2].content));
        expect(fs.existsSync(added)).toBe(true);
        expect(fs.existsSync(obsolete)).toBe(false);
        failedPromotions++;
        throw new Error('controlled late Pagefind promotion failure');
      }
      real(from, to);
    });
    try {
      await expect(writeSearchFiles(directory, updated, 1))
        .rejects.toThrow('controlled late Pagefind promotion failure');
    } finally {
      vi.mocked(fs.renameSync).mockImplementation(real);
    }
    expect(failedPromotions).toBe(1);
    expect(snapshot()).toEqual(before);
    expect((await readdir(directory)).sort()).toEqual(['index.html', 'pagefind']);

    const report = await writeSearchFiles(directory, updated, 1);
    expect(report.files.map(file => file.path)).toEqual(updated.map(file => file.path));
    for (const file of updated) {
      expect(await readFile(join(destination, file.path))).toEqual(Buffer.from(file.content));
    }
    expect(fs.existsSync(obsolete)).toBe(false);
    expect(await readFile(article, 'utf8')).toBe('handwritten page');
    const settled = snapshot();
    expect(await writeSearchFiles(directory, updated, 1)).toEqual(report);
    expect(snapshot()).toEqual(settled);
    expect((await readdir(directory)).sort()).toEqual(['index.html', 'pagefind']);
  });

  it('rejects the observed 32 KiB incomplete-module shape and preserves the prior output', async () => {
    const directory = await fixture();
    await mkdir(join(directory, 'pagefind'));
    await writeFile(join(directory, 'pagefind/complete'), 'previous complete bundle');
    const incomplete = bytes(`/*${'x'.repeat(32730)}*/\nexport function search() { return { results: [] }; }`).subarray(0, 32768);
    expect(incomplete.length).toBe(32768);
    const bundle = files(); bundle[0].content = incomplete;
    await expect(writeSearchFiles(directory, bundle, 1)).rejects.toThrow('JavaScript is incomplete or invalid');
    expect(await readFile(join(directory, 'pagefind/complete'), 'utf8')).toBe('previous complete bundle');
    expect(await readdir(directory)).toEqual(['pagefind']);
  });

  it('checks JavaScript syntax without executing emitted code', async () => {
    const directory = await fixture();
    const bundle = files();
    bundle[0].content = bytes('throw new Error("must not execute"); export function search() {}');
    await expect(writeSearchFiles(directory, bundle, 1)).resolves.toHaveProperty('pageCount', 1);
  });

  it.each(['../escape', '/absolute', 'a/../escape', 'C:/escape', 'a\\b', 'a//b', 'a/%2e%2e/b', '.', '..'])('rejects non-local output path %s', path => {
    expect(() => validateSearchFiles([...files(), { path, content: bytes('x') }])).toThrow('Invalid or duplicate');
  });
  it('requires unique nonempty assets, the module and valid entry metadata', () => {
    expect(() => validateSearchFiles([])).toThrow('empty bundle');
    expect(() => validateSearchFiles([...files(), files()[0]])).toThrow('duplicate');
    expect(() => validateSearchFiles(files().slice(1))).toThrow('omitted');
    const empty = files(); empty[2].content = bytes('');
    expect(() => validateSearchFiles(empty)).toThrow('Empty or invalid');
    const brokenJson = files(); brokenJson[1].content = bytes('{');
    expect(() => validateSearchFiles(brokenJson)).toThrow('invalid JSON');
  });
  it('does not follow an existing search-output symlink', async () => {
    const directory = await fixture(); const outside = await fixture();
    await writeFile(join(outside, 'keep'), 'do not replace');
    await symlink(outside, join(directory, 'pagefind'), 'junction');
    await expect(writeSearchFiles(directory, files(), 1)).rejects.toThrow('ordinary build directory');
    expect(await readFile(join(outside, 'keep'), 'utf8')).toBe('do not replace');
  });
  it('waits for the in-memory result and closes the service without asking it to write files', async () => {
    const directory = await fixture(); const order: string[] = [];
    const nativeWrite = vi.fn(() => { throw new Error('native disk writes not used'); });
    const service = {
      createIndex: async () => ({ errors: [], index: {
        addDirectory: async ({ path }: { path: string }) => { expect(path).toBe(directory); order.push('index'); return { errors: [], page_count: 1 }; },
        getFiles: async () => { await Promise.resolve(); order.push('serialized'); return { errors: [], files: files() }; },
        writeFiles: nativeWrite,
      } }),
      close: async () => { order.push('close'); expect(await readdir(directory)).toEqual([]); return null; },
    } as unknown as Pick<typeof pagefind, 'createIndex' | 'close'>;
    await buildSearchIndex(directory, service);
    expect(order).toEqual(['index', 'serialized', 'close']);
    expect(nativeWrite).not.toHaveBeenCalled();
    expect(await readFile(join(directory, 'pagefind/pagefind.js'))).toEqual(files()[0].content);
  });
  it.each(['create', 'index', 'serialize'])('fails closed and closes the service on %s failure', async stage => {
    const directory = await fixture();
    const close = vi.fn(async () => null);
    const service = {
      createIndex: async () => ({ errors: stage === 'create' ? ['creation failed'] : [], index: {
        addDirectory: async () => ({ errors: stage === 'index' ? ['index failed'] : [], page_count: 1 }),
        getFiles: async () => ({ errors: stage === 'serialize' ? ['serialization failed'] : [], files: files() }),
      } }), close,
    } as unknown as Pick<typeof pagefind, 'createIndex' | 'close'>;
    await expect(buildSearchIndex(directory, service)).rejects.toThrow(/Pagefind/);
    expect(close).toHaveBeenCalledOnce();
    expect(await readdir(directory)).toEqual([]);
  });
  it('indexes real HTML with the locked engine and publishes its exact complete in-memory output', async () => {
    const directory = await fixture();
    await writeFile(join(directory, 'index.html'), '<html lang="en"><body><main data-pagefind-body><h1>Find the workflow</h1><p>Greenfield architecture plan backlog.</p></main></body></html>');
    const report = await buildSearchIndex(directory);
    expect(report.pageCount).toBe(1);
    const main = report.files.find(file => file.path === 'pagefind.js')!;
    expect(main.bytes).toBeGreaterThan(32768);
    expect(report.files.some(file => file.path.endsWith('.pf_fragment'))).toBe(true);
    const text = await readFile(join(directory, 'pagefind/pagefind.js'), 'utf8');
    expect(text).toContain('search');
    expect((await import('node:child_process')).spawnSync(process.execPath, ['--check', '--input-type=module'], { input: text }).status).toBe(0);
  });
  it('is wired to every Astro build instead of an optional postbuild command', async () => {
    expect(completePagefind().hooks['astro:build:done']).toBeTypeOf('function');
    const config = await readFile('astro.config.mjs', 'utf8');
    expect(config).toContain('pagefind: false');
    expect(config).toContain('completePagefind(),');
    expect(config).toContain('Search: "./src/components/Search.astro"');
    const pkg = JSON.parse(await readFile('package.json', 'utf8'));
    const lock = JSON.parse(await readFile('package-lock.json', 'utf8'));
    expect(pkg.devDependencies.pagefind).toBe(lock.packages['node_modules/pagefind'].version);
    expect(lock.packages[''].devDependencies.pagefind).toBe(pkg.devDependencies.pagefind);
  });
});
