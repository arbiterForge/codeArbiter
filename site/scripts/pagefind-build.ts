import type { AstroIntegration } from 'astro';
import * as pagefind from 'pagefind';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

type IndexFile = { path: string; content: Uint8Array };
type SearchService = Pick<typeof pagefind, 'createIndex' | 'close'>;
export type SearchBundleReport = {
  schemaVersion: 1;
  pageCount: number;
  files: Array<{ path: string; bytes: number; sha256: string }>;
};

/** Validate the complete in-memory bundle before any output is replaced. */
export function validateSearchFiles(files: readonly IndexFile[]): void {
  if (!files.length) throw new Error('Pagefind returned an empty bundle');
  const names = new Set<string>();
  for (const file of files) {
    // Pagefind returns URL-relative paths. Reject ambiguity instead of normalizing
    // traversals, Windows paths or URL escapes into a writable filesystem path.
    if (!/^[a-zA-Z0-9_.-]+(?:\/[a-zA-Z0-9_.-]+)*$/.test(file.path) ||
        file.path.split('/').some(part => part === '.' || part === '..') || names.has(file.path)) {
      throw new Error(`Invalid or duplicate Pagefind path: ${file.path}`);
    }
    if (!(file.content instanceof Uint8Array) || file.content.byteLength === 0) {
      throw new Error(`Empty or invalid Pagefind data: ${file.path}`);
    }
    names.add(file.path);
  }
  if (!names.has('pagefind.js') || !names.has('pagefind-entry.json')) {
    throw new Error('Pagefind omitted the search entry modules');
  }
  // Do not execute generated code. Parse every JS asset as an ECMAScript module,
  // including the observed failure shape: a main module cut off at 32 KiB.
  for (const file of files.filter(item => item.path.endsWith('.js'))) {
    try {
      execFileSync(process.execPath, ['--check', '--input-type=module'], {
        input: file.content, stdio: ['pipe', 'pipe', 'pipe'], timeout: 10_000,
      });
    } catch {
      throw new Error(`Pagefind JavaScript is incomplete or invalid: ${file.path}`);
    }
  }
  const entry = files.find(file => file.path === 'pagefind-entry.json')!;
  try { JSON.parse(Buffer.from(entry.content).toString('utf8')); }
  catch { throw new Error('Pagefind entry metadata is invalid JSON'); }
}

/** Await all local writes and verify their bytes, independently of native-service shutdown. */
export async function writeSearchFiles(output: string, files: readonly IndexFile[], pageCount: number): Promise<SearchBundleReport> {
  validateSearchFiles(files);
  const destination = join(output, 'pagefind');
  const previous = await lstat(destination).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'ENOENT') throw error;
    return undefined;
  });
  if (previous && (!previous.isDirectory() || previous.isSymbolicLink())) {
    throw new Error('Pagefind output must be an ordinary build directory');
  }
  const staging = await mkdtemp(join(output, '.pagefind-stage-'));
  try {
    const report: SearchBundleReport = { schemaVersion: 1, pageCount, files: [] };
    for (const file of files) {
      const path = join(staging, file.path);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, file.content, { flag: 'wx' });
      const written = await readFile(path);
      if (!written.equals(Buffer.from(file.content))) throw new Error(`Pagefind write mismatch: ${file.path}`);
      report.files.push({ path: file.path, bytes: written.length, sha256: createHash('sha256').update(written).digest('hex') });
    }
    // This is the build output, not a live deployment. Replace only its own search
    // directory after every asset has passed validation; never touch source files.
    await rm(destination, { force: true, recursive: true });
    await rename(staging, destination);
    return report;
  } finally {
    await rm(staging, { force: true, recursive: true });
  }
}

/** Preserve Starlight's indexing defaults; own serialization through the documented getFiles API. */
export async function buildSearchIndex(output: string, service: SearchService = pagefind): Promise<SearchBundleReport> {
  let files: IndexFile[];
  let count: number;
  try {
    const created = await service.createIndex();
    if (created.errors.length || !created.index) throw new Error(`Pagefind create failed: ${created.errors.join('; ')}`);
    const indexed = await created.index.addDirectory({ path: output });
    if (indexed.errors.length || !Number.isSafeInteger(indexed.page_count) || indexed.page_count <= 0) {
      throw new Error(`Pagefind indexed no complete pages: ${indexed.errors.join('; ')}`);
    }
    count = indexed.page_count;
    const generated = await created.index.getFiles();
    if (generated.errors.length) throw new Error(`Pagefind generation failed: ${generated.errors.join('; ')}`);
    files = generated.files;
  } finally {
    // No native output writes are pending: getFiles returns owned bytes, unlike
    // relying on a successful native write response as evidence of complete files.
    await service.close();
  }
  return writeSearchFiles(output, files!, count!);
}

/** Run in every Astro build, including the non-root build, not only npm postbuild. */
export function completePagefind(): AstroIntegration {
  return {
    name: 'codearbiter:complete-pagefind',
    hooks: {
      'astro:build:done': async ({ dir, logger }) => {
        const report = await buildSearchIndex(fileURLToPath(dir));
        const main = report.files.find(file => file.path === 'pagefind.js')!;
        logger.info(`Verified search bundle: ${report.pageCount} pages, ${report.files.length} assets; pagefind.js ${main.bytes} bytes (${main.sha256}).`);
      },
    },
  };
}
