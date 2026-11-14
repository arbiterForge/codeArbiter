/** Publish complete, bounded generated files; a pending marker blocks consumption. */
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';

export function commonOwner(paths: readonly string[]): string {
  let owner = resolve(paths[0]);
  while (paths.some(path => { const rel = relative(owner, resolve(path)); return rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel); })) {
    const parent = dirname(owner);
    if (parent === owner) throw new Error('Generated outputs have no bounded common owner');
    owner = parent;
  }
  if (dirname(owner) === owner) throw new Error('Generated outputs cannot own a filesystem root');
  return owner;
}
export function assertComplete(root: string, namespace: string): void {
  const marker = join(root, `.generated-${namespace}.lock`);
  if (existsSync(marker)) throw new Error(`Incomplete or concurrent ${namespace} generation: ${marker}`);
}
function safeTarget(root: string, path: string): string {
  path = resolve(path);
  const rel = relative(root, path);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) throw new Error(`Generated target escapes owner: ${path}`);
  // Check every ancestor, including the owning root and its ancestors.
  let cursor = path;
  while (true) {
    try { if (lstatSync(cursor).isSymbolicLink()) throw new Error(`Generated target traverses symbolic link: ${cursor}`); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    const parent = dirname(cursor); if (parent === cursor) break; cursor = parent;
  }
  return path;
}
function filesUnder(root: string, directory: string): string[] {
  directory = safeTarget(root, directory);
  if (!existsSync(directory)) return [];
  const stat = lstatSync(directory);
  if (!stat.isDirectory()) return [directory];
  return readdirSync(directory).flatMap(name => filesUnder(root, join(directory, name)));
}
export function assertOwnedOutput(root: string): void {
  safeTarget(resolve(root), join(resolve(root), '.generation-owner-check'));
}
export function publishOwnedFiles(root: string, namespace: string, updates: ReadonlyMap<string, string | Uint8Array>, ownedDirectories: readonly string[] = []): void {
  root = resolve(root);
  assertOwnedOutput(root);
  mkdirSync(root, { recursive: true });
  const marker = join(root, `.generated-${namespace}.lock`);
  writeFileSync(marker, 'publication pending; generated output is unusable', { flag: 'wx' });
  let staging: string | undefined;
  let retain = false;
  const old = new Map<string, Buffer | undefined>();
  const applied: string[] = [];
  try {
    const rendered = new Map([...updates].map(([path, data]) => [safeTarget(root, path), Buffer.from(data)]));
    const removed = ownedDirectories.flatMap(directory => filesUnder(root, directory)).filter(path => !rendered.has(path));
    staging = mkdtempSync(join(root, `.generated-${namespace}-`));
    const pending = new Map<string, string>();
    const targets = [...new Set([...rendered.keys(), ...removed])].sort();
    for (const [index, path] of targets.entries()) {
      if (existsSync(path) && !lstatSync(path).isFile()) throw new Error(`Generated target is not a regular file: ${path}`);
      const before = existsSync(path) ? readFileSync(path) : undefined;
      old.set(path, before);
      if (before) writeFileSync(join(staging, `${index}.old`), before, { flag: 'wx' });
      const data = rendered.get(path);
      if (data !== undefined) {
        const staged = join(staging, `${index}.new`);
        writeFileSync(staged, data, { flag: 'wx' });
        if (!readFileSync(staged).equals(data)) throw new Error(`Generated staged bytes differ: ${path}`);
        pending.set(path, staged);
      }
    }
    writeFileSync(join(staging, 'journal.json'), JSON.stringify(targets.map(path => ({ path: relative(root, path), existed: old.get(path) !== undefined }))));
    writeFileSync(marker, staging);
    for (const path of targets) {
      safeTarget(root, path);
      mkdirSync(dirname(path), { recursive: true });
      const staged = pending.get(path);
      if (staged) renameSync(staged, path); else rmSync(path);
      applied.push(path);
    }
  } catch (error) {
    for (const path of applied.reverse()) {
      try {
        safeTarget(root, path);
        const before = old.get(path);
        if (before === undefined) rmSync(path, { force: true });
        else { const rollback = join(staging!, 'rollback'); writeFileSync(rollback, before); renameSync(rollback, path); }
      } catch { retain = true; }
    }
    throw error;
  } finally {
    if (!retain) {
      if (staging) rmSync(staging, { recursive: true, force: true });
      rmSync(marker);
    }
  }
}
