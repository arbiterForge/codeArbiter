import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync, symlinkSync } from 'node:fs';
import * as fs from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { assertComplete, publishOwnedFiles } from './owned-output';
vi.mock('node:fs', async original => { const actual = await original<typeof import('node:fs')>(); return { ...actual, renameSync:vi.fn(actual.renameSync) }; });
beforeEach(async()=>{vi.mocked(fs.renameSync).mockImplementation((await vi.importActual<typeof import('node:fs')>('node:fs')).renameSync);});
const roots:string[]=[];
function fixture(){const root=mkdtempSync(join(tmpdir(),'ca-owned-generation-'));roots.push(root);return root;}
afterEach(()=>{vi.mocked(fs.renameSync).mockReset();for(const root of roots.splice(0))rmSync(root,{recursive:true,force:true});});
describe('owned generated publication',()=>{
 it('restores the complete old output after a late rename failure and reruns deterministically',async()=>{
  const root=fixture(),a=join(root,'a'),b=join(root,'b'),manual=join(root,'handwritten');
  writeFileSync(a,'old-a');writeFileSync(b,'old-b');writeFileSync(manual,'keep');
  const real=(await vi.importActual<typeof import('node:fs')>('node:fs')).renameSync;
  vi.mocked(fs.renameSync).mockImplementation((src,dst)=>{if(String(src).endsWith('.new') && dst===b)throw Error('late promotion failure');real(src,dst);});
  expect(()=>publishOwnedFiles(root,'test',new Map([[a,'new-a'],[b,'new-b']]))).toThrow('late promotion');
  expect(readFileSync(a,'utf8')).toBe('old-a');expect(readFileSync(b,'utf8')).toBe('old-b');assertComplete(root,'test');
  vi.mocked(fs.renameSync).mockImplementation(real);
  publishOwnedFiles(root,'test',new Map([[a,'new-a'],[b,'new-b']]));
  expect(readFileSync(a,'utf8')).toBe('new-a');expect(readFileSync(manual,'utf8')).toBe('keep');
 });
 it('refuses a second writer without touching its marker',()=>{
  const root=fixture(),marker=join(root,'.generated-test.lock');writeFileSync(marker,'other');
  expect(()=>publishOwnedFiles(root,'test',new Map([[join(root,'a'),'new']]))).toThrow();
  expect(readFileSync(marker,'utf8')).toBe('other');
 });
 it('refuses a linked owner before touching external files',()=>{
  const root=fixture(),outside=fixture(),link=join(root,'linked');writeFileSync(join(outside,'keep'),'outside');
  symlinkSync(outside,link,'junction');
  expect(()=>publishOwnedFiles(link,'test',new Map([[join(link,'keep'),'bad']]))).toThrow('symbolic link');
  expect(readFileSync(join(outside,'keep'),'utf8')).toBe('outside');
 });
 it('retains an unusable marker if recovery also fails',async()=>{
  const root=fixture(),a=join(root,'a'),b=join(root,'b');writeFileSync(a,'old-a');writeFileSync(b,'old-b');
  const real=(await vi.importActual<typeof import('node:fs')>('node:fs')).renameSync;
  vi.mocked(fs.renameSync).mockImplementation((src,dst)=>{if(dst===b || String(src).endsWith('rollback'))throw Error('promotion or rollback failure');real(src,dst);});
  expect(()=>publishOwnedFiles(root,'test',new Map([[a,'new-a'],[b,'new-b']]))).toThrow();
  expect(()=>assertComplete(root,'test')).toThrow('Incomplete');
  expect(existsSync(join(readFileSync(join(root,'.generated-test.lock'),'utf8'),'journal.json'))).toBe(true);
 });
});
