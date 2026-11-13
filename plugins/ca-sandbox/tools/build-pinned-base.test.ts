/** Actual default framework generator/build code through a controlled spawn seam.
 * No acquired binary, daemon, or real image execution is claimed here. */
import { beforeAll,beforeEach,afterAll,afterEach,describe,expect,it,vi } from 'vitest';
import { EventEmitter } from 'node:events';
import { mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,existsSync,symlinkSync,lstatSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
const seam=vi.hoisted(()=>({spawn:vi.fn()}));
vi.mock('node:child_process',async original=>({...await original<typeof import('node:child_process')>(),spawn:seam.spawn}));
const PIN='ghcr.io/railwayapp/nixpacks@sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de';
let build:typeof import('./build.ts'),repo:string,generated:string|undefined;
let calls:Array<{command:string;args:string[];env:NodeJS.ProcessEnv}>,dockerfiles:string[],images:Map<string,{id:string;key:string}>;
beforeAll(async()=>{vi.stubEnv('CA_NIXPACKS_SECRET_FIXTURE','not-a-real-credential');vi.stubEnv('NIXPACKS_START_CMD','must-not-be-ambient-input');build=await import('./build.ts');});
afterAll(()=>vi.unstubAllEnvs());
beforeEach(()=>{
 repo=mkdtempSync(path.join(tmpdir(),'ca-pinned-nixpacks-'));writeFileSync(path.join(repo,'package.json'),'{"name":"fixture","version":"1.0.0"}');
 generated=undefined;calls=[];dockerfiles=[];images=new Map();
 seam.spawn.mockImplementation((command:string,args:string[],options:{env:NodeJS.ProcessEnv})=>{
  calls.push({command,args:[...args],env:{...options.env}});
  const child=new EventEmitter() as EventEmitter & {stdout:EventEmitter;stderr:EventEmitter;kill:()=>boolean};
  child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.kill=()=>true;
  setImmediate(()=>{let code=0,stdout='',stderr='';try{
   if(command==='nixpacks' && args[0]==='--version')stdout='nixpacks 1.41.0';
   else if(command==='wsl.exe' && args[0]==='wslpath')stdout='/mnt/fixture';
   else if((command==='nixpacks' && args[0]==='build') || (command==='wsl.exe' && args.includes('--json-plan'))){
    const pos=args.indexOf('--json-plan'),plan=pos<0?{}:JSON.parse(args[pos+1]);mkdirSync(path.join(repo,'.nixpacks'),{recursive:true});
    writeFileSync(path.join(repo,'.nixpacks/Dockerfile'),generated??`FROM ${plan.buildImage??'ghcr.io/railwayapp/nixpacks:ubuntu-latest'} AS build\nWORKDIR /app\n`);
   }else if(command==='docker' && args[0]==='version')stdout='linux/amd64';
   else if(command==='docker' && args[0]==='image' && args[1]==='inspect'){
    const image=images.get(args[2]);if(image)stdout=JSON.stringify([{Id:image.id,Config:{Labels:{[build.CACHE_LABEL]:image.key}}}]);else{code=1;stderr='No such image';}
   }else if(command==='docker' && args[0]==='build'){
    const tag=args[args.indexOf('-t')+1],label=args[args.indexOf('--label')+1];dockerfiles.push(readFileSync(args[args.indexOf('-f')+1],'utf8'));images.set(tag,{id:'sha256:'+'a'.repeat(64),key:label.split('=')[1]});
   }else throw Error('Unexpected controlled subprocess '+command+' '+args.join(' '));
  }catch(error){code=1;stderr=String(error);}if(stdout)child.stdout.emit('data',stdout);if(stderr)child.stderr.emit('data',stderr);child.emit('close',code);});
  return child;
 });
});
afterEach(()=>rmSync(repo,{recursive:true,force:true}));
describe('fixed Nixpacks image inputs through the default generator',()=>{
 it.each(['nixpacks.toml','nixpacks.json'])('refuses project %s before generation without modifying it',async(name)=>{
  const target=path.join(repo,name),text=name.endsWith('json')?'{"staticAssets":{"../../../outside":"untrusted"}}':'[staticAssets]\n"../../../outside" = "untrusted"';
  writeFileSync(target,text);
  await expect(build.buildOrReuseImage(repo,'fixture-manifests')).rejects.toThrow(/unsupported.*Nixpacks.*input/i);
  expect(calls.some(c=>c.args[0]==='build')).toBe(false);expect(readFileSync(target,'utf8')).toBe(text);
 });
 it.each(['.nixpacks','.ca-sandbox.nixpacks.Dockerfile'])('preserves preexisting %s and refuses before generation/cleanup',async(name)=>{
  const target=path.join(repo,name);if(name==='.nixpacks'){mkdirSync(target);writeFileSync(path.join(target,'sentinel'),'keep');}else writeFileSync(target,'keep');
  await expect(build.buildOrReuseImage(repo,'fixture-manifests')).rejects.toThrow(/unsupported.*Nixpacks.*input/i);
  expect(calls.some(c=>c.args[0]==='build')).toBe(false);expect(readFileSync(name==='.nixpacks'?path.join(target,'sentinel'):target,'utf8')).toBe('keep');
 });
 it('refuses a dangling output link without following or deleting it',async()=>{
  const target=path.join(repo,'.nixpacks');symlinkSync(path.join(repo,'absent'),target,process.platform==='win32'?'junction':'dir');
  await expect(build.buildOrReuseImage(repo,'fixture-manifests')).rejects.toThrow(/unsupported.*Nixpacks.*input/i);
  expect(calls.some(c=>c.args[0]==='build')).toBe(false);expect(lstatSync(target).isSymbolicLink()).toBe(true);
 });
 it.each([['node',['node']],['python',['python']],['both',['node','python']]])('pins reviewed %s providers instead of automatic discovery',async(kind,providers)=>{
  if(kind!=='node'){if(kind==='python')rmSync(path.join(repo,'package.json'));writeFileSync(path.join(repo,'requirements.txt'),'');}
  await build.buildOrReuseImage(repo,'fixture-'+kind);
  const args=calls.find(c=>c.command==='nixpacks' && c.args[0]==='build')!.args;
  expect(JSON.parse(args[args.indexOf('--json-plan')+1])).toEqual({buildImage:PIN,providers});
 });
 it('refuses unreviewed provider discovery before generation',async()=>{
  rmSync(path.join(repo,'package.json'));writeFileSync(path.join(repo,'composer.json'),'{}');
  await expect(build.buildOrReuseImage(repo,'fixture-php')).rejects.toThrow(/supported.*Node.*Python/i);
  expect(calls.some(c=>c.args[0]==='build')).toBe(false);
 });
 it('supplies supported merge-last JSON plan and excludes ambient credentials/configuration',async()=>{
  const result=await build.buildOrReuseImage(repo,'fixture-manifests');expect(result.built).toBe(true);
  const g=calls.find(c=>c.command==='nixpacks' && c.args[0]==='build')!;
  expect(g.args).toEqual(['build',repo,'--out',repo,'--no-error-without-start','--json-plan',JSON.stringify({buildImage:PIN,providers:['node']})]);
  expect(g.args).not.toContain('--build-image');expect(g.args).not.toContain('--env');expect(g.args).not.toContain('--incremental-cache-image');
  expect(g.env).not.toHaveProperty('CA_NIXPACKS_SECRET_FIXTURE');expect(g.env).not.toHaveProperty('NIXPACKS_START_CMD');expect(dockerfiles[0]).toContain('FROM '+PIN+' AS build');
 });
 it.each([
  ['mutable primary','FROM ubuntu:noble\n'],
  ['mutable runImage',`FROM ${PIN} AS build\nFROM ubuntu:noble\nCOPY --from=build /app /app\n`],
  ['variable runImage',`FROM ${PIN} AS build\nFROM \${RUN_IMAGE}\n`],
  ['platform mutable runImage',`FROM ${PIN} AS build\nFrOm --platform=linux/amd64 ubuntu:noble AS runtime\n`],
  ['mutable frontend',`# syntax=docker/dockerfile:1\nFROM ${PIN}\n`],
  ['unknown stage alias',`FROM ${PIN} AS build\nFROM unknown_stage\n`],
  ['continued mutable FROM',['FROM '+String.fromCharCode(92),' ubuntu:noble',''].join('\n')],
  ['comment hiding mutable FROM',[`FROM ${PIN} AS build`,'# ordinary comment '+String.fromCharCode(92),'FROM ubuntu:noble',''].join('\n')],
  ['mutable COPY source',`FROM ${PIN} AS build\nRUN true\nCOPY --from=ubuntu:noble /etc/os-release /injected\n`],
  ['quoted COPY flag before mutable source',`FROM ${PIN} AS build\nCOPY --chown="user group" --from=ubuntu:noble /x /x\n`],
  ['mutable RUN mount',`FROM ${PIN} AS build\nRUN --mount=from=ubuntu:noble,target=/ext echo hi\n`],
  ['quoted mutable RUN mount',`FROM ${PIN} AS build\nRUN --mount="from=ubuntu:noble,target=/ext" echo hi\n`],
  ['second mutable RUN mount',`FROM ${PIN} AS build\nFROM scratch AS runtime\nRUN --mount=from=build,target=/safe --mount=from=ubuntu:noble,target=/ext echo hi\n`],
  ['deferred image source',`FROM ${PIN} AS build\nONBUILD COPY --from=ubuntu:noble /x /x\n`],
 ])('refuses %s before Docker build and cleans generated files',async(_name,text)=>{
  generated=text;await expect(build.buildOrReuseImage(repo,'fixture-manifests')).rejects.toThrow(/pinned|FROM/);expect(dockerfiles).toHaveLength(0);
  expect(existsSync(path.join(repo,'.nixpacks'))).toBe(false);expect(existsSync(path.join(repo,'.ca-sandbox.nixpacks.Dockerfile'))).toBe(false);
 });
 it('accepts pinned multistage references, prior aliases and scratch',async()=>{
  generated=`FROM ${PIN} AS build\nFROM build AS runtime\nFROM scratch AS archive\nCOPY --from=runtime /app /app\n`;
  expect((await build.buildOrReuseImage(repo,'fixture-manifests')).built).toBe(true);expect(dockerfiles).toHaveLength(1);
 });
 it('accepts the native runImage numeric0 and prior-stage bind sources',async()=>{
  generated=`FROM ${PIN} AS build\nRUN true\nFROM ${PIN} AS runtime\nCOPY --from=0 /app /app\nRUN --mount=type=bind,from=build,target=/input echo hi\n`;
  expect((await build.buildOrReuseImage(repo,'fixture-manifests')).built).toBe(true);expect(dockerfiles).toHaveLength(1);
 });
 it('accepts immutable external COPY and bind image references',async()=>{
  generated=`FROM ${PIN} AS build\nCOPY --from=${PIN} /x /x\nRUN --mount=type=bind,from=${PIN},target=/input echo hi\n`;
  expect((await build.buildOrReuseImage(repo,'fixture-manifests')).built).toBe(true);expect(dockerfiles).toHaveLength(1);
 });
 it('invalidates the earlier FROM-only policy cache identity',async()=>{
  const oldKey=createHash('sha256').update(JSON.stringify({schema:2,manifests:'fixture-manifests',builder:'nixpacks',version:'1.41.0',platform:'linux/amd64',nixpacksProfile:{...build.NIXPACKS_BUILD_PROFILE,dockerfilePolicy:'all-from-sha256-no-frontend-v1'},fallback:build.generateDockerfile({node:true,python:true}),relocation:build.relocationOverlay()})).digest('hex');
  images.set(build.imageTag(repo,oldKey),{id:'sha256:'+'c'.repeat(64),key:oldKey});
  const result=await build.buildOrReuseImage(repo,'fixture-manifests');expect(result.reused).toBe(false);expect(result.cacheKey).not.toBe(oldKey);expect(dockerfiles).toHaveLength(1);
 });
 it('uses the same pinned profile and minimal environment through the WSL default generator seam',async()=>{
  const deps=build.defaultBuildDeps();deps.ensureNixpacks=async()=>({available:true,version:'1.41.0',via:{via:'wsl',bin:'/reviewed/nixpacks',distro:'Fixture'}});
  expect((await build.buildOrReuseImage(repo,'fixture-manifests',deps)).built).toBe(true);
  const generation=calls.find(c=>c.command==='wsl.exe' && c.args.includes('--json-plan'))!;
  expect(generation.args).toEqual(['-d','Fixture','--','/reviewed/nixpacks','build','/mnt/fixture','--out','/mnt/fixture','--no-error-without-start','--json-plan',JSON.stringify({buildImage:PIN,providers:['node']})]);
  for(const call of calls.filter(c=>c.command==='wsl.exe')){
   expect(call.env).not.toHaveProperty('CA_NIXPACKS_SECRET_FIXTURE');expect(call.env).not.toHaveProperty('NIXPACKS_START_CMD');
  }
 });
 it('reuses the same labeled immutable image across two independent staging names',async()=>{
  const first=await build.buildOrReuseImage(repo,'fixture-manifests');
  const other=mkdtempSync(path.join(tmpdir(),'ca-pinned-independent-'));
  try {
   writeFileSync(path.join(other,'package.json'),readFileSync(path.join(repo,'package.json')));
   const second=await build.buildOrReuseImage(other,'fixture-manifests');
   expect(first.built).toBe(true);expect(second.reused).toBe(true);expect(second.imageId).toBe(first.imageId);expect(second.tag).toBe(first.tag);expect(dockerfiles).toHaveLength(1);
  }finally{rmSync(other,{recursive:true,force:true});}
 });
 it('does not reuse a V2 cache tag that omitted the effective pinned generator profile',async()=>{
  const oldKey=createHash('sha256').update(JSON.stringify({schema:2,manifests:'fixture-manifests',builder:'nixpacks',version:'1.41.0',platform:'linux/amd64',fallback:build.generateDockerfile({node:true,python:true}),relocation:build.relocationOverlay()})).digest('hex');
  images.set(build.imageTag(repo,oldKey),{id:'sha256:'+'b'.repeat(64),key:oldKey});const result=await build.buildOrReuseImage(repo,'fixture-manifests');
  expect(result.reused).toBe(false);expect(result.cacheKey).not.toBe(oldKey);expect(dockerfiles).toHaveLength(1);
 });
});
